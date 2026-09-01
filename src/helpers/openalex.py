from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import parse_qsl, quote, urlencode

import duckdb
import requests
from dotenv import dotenv_values
from pydantic import ValidationError

from .data_models import (
    HttpRequestLogRecord,
    RegisteredResource,
    append_http_request_log_record,
    http_request_log_record,
    matching_http_request_log_record,
    redact_http_request_log_query,
)
from .duckdb_utils import duckdb_string_literal
from .files import file_sha256
from .vars import (
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
    KTP_OPENALEX_RECEIVED_AT_UNIX_USEC_COL,
    OPENALEX_AUTHOR_SEARCH_LOG_PATH,
    OPENALEX_PAPER_TITLE_LOG_KEY,
    OPENALEX_PAPER_TITLE_LOG_PATH,
    OPENALEX_PAPER_TITLE_LOG_SHA256_METADATA_KEY,
    OPENALEX_PAPER_TITLE_PARQUET_KEY,
    OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION,
    OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION_METADATA_KEY,
    OPENALEX_TITLE_COL,
    SSNP_PAPERID_COL,
)

OPENALEX_SCHEME = "https"
OPENALEX_HOST = "api.openalex.org"
OPENALEX_AUTHOR_SEARCH_PATH = "/authors"
OPENALEX_WORKS_PATH = "/works"
OPENALEX_AUTHOR_SEARCH_TIMEOUT_SECONDS = 30.0
OPENALEX_WORK_TITLE_BATCH_SIZE = 100


class _ResponseLike(Protocol):
    status_code: int
    text: str


_RequestGet = Callable[..., _ResponseLike]


@dataclass(frozen=True)
class OpenAlexAuthorCheckResult:
    source_key: str
    selected_author_id: str
    query: str
    response_code: int | None
    top_author_id: str | None
    matched: bool
    reused: bool
    received_at_unix_usec: int | None
    duration_usec: int


@dataclass(frozen=True)
class OpenAlexWorkTitleBatchResult:
    paperids: tuple[str, ...]
    query: str
    response_code: int | None
    titles_by_paperid: dict[str, str | None]
    received_at_unix_usec: int | None
    duration_usec: int


def openalex_author_search_log_path() -> Path:
    return Path(OPENALEX_AUTHOR_SEARCH_LOG_PATH)


def openalex_paper_title_log_path() -> Path:
    return Path(OPENALEX_PAPER_TITLE_LOG_PATH)


def openalex_author_search_query(*, first_name: str, last_name: str, api_key: str) -> str:
    return urlencode(
        {
            "search": f"{first_name} {last_name}".strip(),
            "sort": "relevance_score:desc",
            "select": "id",
            "per_page": "1",
            "api_key": api_key,
        },
        quote_via=quote,
    )


def openalex_work_titles_batch_query(
    *,
    paperids: Sequence[str],
    api_key: str,
) -> str:
    cleaned_paperids = tuple(str(paperid) for paperid in paperids if str(paperid).strip())
    if not cleaned_paperids:
        raise ValueError("OpenAlex work-title batch requires at least one paper ID.")
    if len(cleaned_paperids) > OPENALEX_WORK_TITLE_BATCH_SIZE:
        raise ValueError(
            "OpenAlex work-title batch exceeds "
            f"{OPENALEX_WORK_TITLE_BATCH_SIZE} paper IDs."
        )
    return urlencode(
        {
            "filter": "openalex_id:" + "|".join(cleaned_paperids),
            "select": "id,title",
            "per_page": str(OPENALEX_WORK_TITLE_BATCH_SIZE),
            "api_key": api_key,
        },
        safe=":|,",
        quote_via=quote,
    )


def parse_openalex_top_author_id(response_body: str) -> str | None:
    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError:
        return None
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None
    first_result = results[0]
    if not isinstance(first_result, dict):
        return None
    author_url = first_result.get("id")
    if not isinstance(author_url, str) or not author_url:
        return None
    return author_url.rstrip("/").rsplit("/", 1)[-1]


def parse_openalex_work_titles_response(
    response_body: str,
    *,
    requested_paperids: Sequence[str],
) -> dict[str, str | None]:
    titles_by_paperid: dict[str, str | None] = {
        str(paperid): None for paperid in requested_paperids
    }
    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError:
        return titles_by_paperid
    if not isinstance(payload, dict):
        return titles_by_paperid
    results = payload.get("results")
    if not isinstance(results, list):
        return titles_by_paperid
    for result in results:
        if not isinstance(result, dict):
            continue
        work_url = result.get("id")
        if not isinstance(work_url, str) or not work_url:
            continue
        paperid = work_url.rstrip("/").rsplit("/", 1)[-1]
        if paperid not in titles_by_paperid:
            continue
        title = result.get("title")
        titles_by_paperid[paperid] = title if isinstance(title, str) and title.strip() else None
    return titles_by_paperid


def openalex_work_title_paperids_from_query(query: str) -> tuple[str, ...]:
    values = dict(parse_qsl(query, keep_blank_values=True))
    work_filter = values.get("filter")
    if work_filter is None or not work_filter.startswith("openalex_id:"):
        return ()
    raw_ids = work_filter.removeprefix("openalex_id:").split("|")
    return tuple(paperid for paperid in raw_ids if paperid)


def chunk_openalex_work_title_paperids(
    paperids: Sequence[str],
    *,
    batch_size: int = OPENALEX_WORK_TITLE_BATCH_SIZE,
) -> list[tuple[str, ...]]:
    if batch_size < 1 or batch_size > OPENALEX_WORK_TITLE_BATCH_SIZE:
        raise ValueError(
            "OpenAlex work-title batch size must be between 1 and "
            f"{OPENALEX_WORK_TITLE_BATCH_SIZE}."
        )
    distinct_paperids = list(dict.fromkeys(str(paperid) for paperid in paperids if str(paperid)))
    return [
        tuple(distinct_paperids[start : start + batch_size])
        for start in range(0, len(distinct_paperids), batch_size)
    ]


def _validate_openalex_work_title_log_record(
    record: HttpRequestLogRecord,
    *,
    line_number: int,
) -> tuple[str, ...]:
    if record.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION:
        raise ValueError(
            f"Invalid {OPENALEX_PAPER_TITLE_LOG_KEY} line {line_number}: "
            f"schema_version={record.schema_version!r}."
        )
    if (
        record.method != "GET"
        or record.scheme != OPENALEX_SCHEME
        or record.host != OPENALEX_HOST
        or record.path != OPENALEX_WORKS_PATH
    ):
        raise ValueError(
            f"Invalid {OPENALEX_PAPER_TITLE_LOG_KEY} line {line_number}: "
            "expected GET https://api.openalex.org/works."
        )
    query_values = dict(parse_qsl(record.query, keep_blank_values=True))
    if (
        query_values.get("select") != "id,title"
        or query_values.get("per_page") != str(OPENALEX_WORK_TITLE_BATCH_SIZE)
        or query_values.get("api_key") != "REDACTED"
    ):
        raise ValueError(
            f"Invalid {OPENALEX_PAPER_TITLE_LOG_KEY} line {line_number}: "
            "expected strict OpenAlex title batch query."
        )
    paperids = openalex_work_title_paperids_from_query(record.query)
    if not paperids:
        raise ValueError(
            f"Invalid {OPENALEX_PAPER_TITLE_LOG_KEY} line {line_number}: "
            "missing openalex_id filter."
        )
    return paperids


def openalex_work_title_rows_from_log(
    log_path: Path,
) -> list[tuple[str, str | None, int | None]]:
    rows_by_paperid: dict[str, tuple[tuple[int, int], str | None, int | None]] = {}
    with log_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped_line = line.strip()
            if not stripped_line:
                continue
            try:
                record = HttpRequestLogRecord.model_validate_json(stripped_line)
            except ValidationError as exc:
                raise ValueError(
                    f"Invalid {OPENALEX_PAPER_TITLE_LOG_KEY} JSONL record at line "
                    f"{line_number}."
                ) from exc
            paperids = _validate_openalex_work_title_log_record(
                record,
                line_number=line_number,
            )
            assert record.response_body is not None  # type safety - HttpRequestLogRecord v1
            titles = parse_openalex_work_titles_response(
                record.response_body,
                requested_paperids=paperids,
            )
            received_at = record.received_at_unix_usec
            received_at_sort = received_at if received_at is not None else -1
            for paperid in paperids:
                sort_key = (received_at_sort, line_number)
                current = rows_by_paperid.get(paperid)
                if current is None or sort_key >= current[0]:
                    rows_by_paperid[paperid] = (sort_key, titles.get(paperid), received_at)
    return [
        (paperid, title, received_at)
        for paperid, (_sort_key, title, received_at) in sorted(rows_by_paperid.items())
    ]


def openalex_paper_title_read_model_log_sha256(
    conn: duckdb.DuckDBPyConnection,
    parquet_path: Path,
) -> str | None:
    row = conn.execute(
        """
        SELECT decode(value)
        FROM parquet_kv_metadata(?)
        WHERE decode(key) = ?
        """,
        [str(parquet_path), OPENALEX_PAPER_TITLE_LOG_SHA256_METADATA_KEY],
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _openalex_paper_title_read_model_metadata(
    path: Path,
    *,
    conn: duckdb.DuckDBPyConnection | None,
) -> dict[str, str]:
    owns_conn = conn is None
    metadata_conn = duckdb.connect() if owns_conn else conn
    assert metadata_conn is not None
    try:
        rows = metadata_conn.execute(
            """
            SELECT decode(key), decode(value)
            FROM parquet_kv_metadata(?)
            """,
            [str(path)],
        ).fetchall()
    finally:
        if owns_conn:
            metadata_conn.close()
    return {str(key): str(value) for key, value in rows}


def validate_openalex_paper_title_read_model(
    path: Path,
    *,
    expected_log_sha256: str,
    conn: duckdb.DuckDBPyConnection | None,
) -> None:
    metadata = _openalex_paper_title_read_model_metadata(path, conn=conn)
    owns_conn = conn is None
    metadata_conn = duckdb.connect() if owns_conn else conn
    assert metadata_conn is not None
    try:
        column_rows = metadata_conn.execute(
            f"DESCRIBE SELECT * FROM read_parquet({duckdb_string_literal(str(path))})"
        ).fetchall()
    finally:
        if owns_conn:
            metadata_conn.close()
    columns = {str(row[0]) for row in column_rows}
    required_columns = {
        SSNP_PAPERID_COL,
        OPENALEX_TITLE_COL,
        KTP_OPENALEX_RECEIVED_AT_UNIX_USEC_COL,
    }
    missing_columns = sorted(required_columns - columns)
    if missing_columns:
        raise ValueError(
            f"{OPENALEX_PAPER_TITLE_PARQUET_KEY} is missing required columns: "
            f"{', '.join(missing_columns)}."
        )
    stored_hash = metadata.get(OPENALEX_PAPER_TITLE_LOG_SHA256_METADATA_KEY)
    if stored_hash != expected_log_sha256:
        raise ValueError(
            f"{OPENALEX_PAPER_TITLE_PARQUET_KEY} was built from OpenAlex title log "
            f"hash {stored_hash!r}; current log hash is {expected_log_sha256!r}."
        )
    stored_schema_version = metadata.get(OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION_METADATA_KEY)
    if stored_schema_version != str(OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION):
        raise ValueError(
            f"{OPENALEX_PAPER_TITLE_PARQUET_KEY} has schema version "
            f"{stored_schema_version!r}; expected "
            f"{OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION}."
        )


def write_openalex_paper_title_read_model(
    conn: duckdb.DuckDBPyConnection,
    *,
    openalex_paper_title_log_resource: RegisteredResource,
    output_path: Path,
) -> str:
    """
    Always recalculates hash
    from `openalex_paper_title_log_resource.log_path`
    before writing.

    Returns
    the recalculated log hash,
    not the parquet hash.
    """
    log_path = Path(openalex_paper_title_log_resource.__fspath__())
    log_sha256 = file_sha256(log_path)
    title_rows = openalex_work_title_rows_from_log(log_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    temp_table = "openalex_paper_title_rows_to_copy"
    conn.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {temp_table} (
            paperid VARCHAR,
            title VARCHAR,
            received_at_unix_usec BIGINT
        )
        """
    )
    if title_rows:
        conn.executemany(
            f"""
            INSERT INTO {temp_table} (paperid, title, received_at_unix_usec)
            VALUES (?, ?, ?)
            """,
            title_rows,
        )
    metadata_sql = (
        "KV_METADATA {"
        f"{duckdb_string_literal(OPENALEX_PAPER_TITLE_LOG_SHA256_METADATA_KEY)}: "
        f"{duckdb_string_literal(log_sha256)}, "
        f"{duckdb_string_literal(OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION_METADATA_KEY)}: "
        f"{duckdb_string_literal(str(OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION))}"
        "}"
    )
    conn.execute(
        f"""
        COPY (
            SELECT
                paperid AS "{SSNP_PAPERID_COL}",
                title AS "{OPENALEX_TITLE_COL}",
                received_at_unix_usec AS "{KTP_OPENALEX_RECEIVED_AT_UNIX_USEC_COL}"
            FROM {temp_table}
            ORDER BY paperid
        ) TO {duckdb_string_literal(str(output_path))} (FORMAT PARQUET, {metadata_sql})
        """
    )
    conn.execute(f"DROP TABLE IF EXISTS {temp_table}")
    return log_sha256


def _api_key_from_env(env_path: Path) -> str:
    values = dotenv_values(env_path)
    api_key = values.get("OPENALEX_API_KEY") or os.environ.get("OPENALEX_API_KEY")
    if not api_key:
        raise ValueError(f"Missing OPENALEX_API_KEY in {env_path}")
    return api_key


def _result_from_record(
    *,
    source_key: str,
    selected_author_id: str,
    query: str,
    record: HttpRequestLogRecord,
    reused: bool,
) -> OpenAlexAuthorCheckResult:
    assert record.response_body is not None  # type safety - HttpRequestLogRecord v1
    assert record.duration_usec is not None  # type safety - HttpRequestLogRecord v1
    top_author_id = parse_openalex_top_author_id(record.response_body)
    return OpenAlexAuthorCheckResult(
        source_key=source_key,
        selected_author_id=selected_author_id,
        query=query,
        response_code=record.response_code,
        top_author_id=top_author_id,
        matched=top_author_id == selected_author_id,
        reused=reused,
        received_at_unix_usec=record.received_at_unix_usec,
        duration_usec=record.duration_usec,
    )


def check_openalex_author(
    *,
    source_key: str,
    first_name: str,
    last_name: str,
    selected_author_id: str,
    log_path: Path | None = None,
    env_path: Path = Path(".env"),
    api_key: str | None = None,
    request_get: _RequestGet | None = None,
) -> OpenAlexAuthorCheckResult:
    resolved_log_path = log_path or openalex_author_search_log_path()
    resolved_api_key = api_key or _api_key_from_env(env_path)
    query = openalex_author_search_query(
        first_name=first_name,
        last_name=last_name,
        api_key=resolved_api_key,
    )
    redacted_query = redact_http_request_log_query(query)
    cached_record = matching_http_request_log_record(
        log_path=resolved_log_path,
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme=OPENALEX_SCHEME,
        host=OPENALEX_HOST,
        path=OPENALEX_AUTHOR_SEARCH_PATH,
        redacted_query=redacted_query,
    )
    if cached_record is not None:
        return _result_from_record(
            source_key=source_key,
            selected_author_id=selected_author_id,
            query=redacted_query,
            record=cached_record,
            reused=True,
        )

    url = f"{OPENALEX_SCHEME}://{OPENALEX_HOST}{OPENALEX_AUTHOR_SEARCH_PATH}?{query}"
    resolved_request_get = request_get or cast(_RequestGet, requests.get)
    start_ns = time.monotonic_ns()
    response = resolved_request_get(url, timeout=OPENALEX_AUTHOR_SEARCH_TIMEOUT_SECONDS)
    duration_usec = (time.monotonic_ns() - start_ns) // 1_000
    received_at_unix_usec = time.time_ns() // 1_000
    top_author_id = parse_openalex_top_author_id(response.text)
    matched = top_author_id == selected_author_id
    record = http_request_log_record(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme=OPENALEX_SCHEME,
        host=OPENALEX_HOST,
        path=OPENALEX_AUTHOR_SEARCH_PATH,
        redacted_query=redacted_query,
        response_code=response.status_code,
        response_body=response.text,
        received_at_unix_usec=received_at_unix_usec,
        duration_usec=duration_usec,
    )
    append_http_request_log_record(log_path=resolved_log_path, record=record)
    return OpenAlexAuthorCheckResult(
        source_key=source_key,
        selected_author_id=selected_author_id,
        query=redacted_query,
        response_code=response.status_code,
        top_author_id=top_author_id,
        matched=matched,
        reused=False,
        received_at_unix_usec=received_at_unix_usec,
        duration_usec=duration_usec,
    )


def fetch_openalex_work_titles_batch(
    *,
    paperids: Sequence[str],
    log_path: Path | None = None,
    env_path: Path = Path(".env"),
    api_key: str | None = None,
    request_get: _RequestGet | None = None,
) -> OpenAlexWorkTitleBatchResult:
    cleaned_paperids = tuple(str(paperid) for paperid in paperids if str(paperid).strip())
    resolved_log_path = log_path or openalex_paper_title_log_path()
    resolved_api_key = api_key or _api_key_from_env(env_path)
    query = openalex_work_titles_batch_query(
        paperids=cleaned_paperids,
        api_key=resolved_api_key,
    )
    redacted_query = redact_http_request_log_query(query, safe=":|,")
    url = f"{OPENALEX_SCHEME}://{OPENALEX_HOST}{OPENALEX_WORKS_PATH}?{query}"
    resolved_request_get = request_get or cast(_RequestGet, requests.get)
    start_ns = time.monotonic_ns()
    response = resolved_request_get(url, timeout=OPENALEX_AUTHOR_SEARCH_TIMEOUT_SECONDS)
    duration_usec = (time.monotonic_ns() - start_ns) // 1_000
    received_at_unix_usec = time.time_ns() // 1_000
    titles_by_paperid = parse_openalex_work_titles_response(
        response.text,
        requested_paperids=cleaned_paperids,
    )
    record = http_request_log_record(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme=OPENALEX_SCHEME,
        host=OPENALEX_HOST,
        path=OPENALEX_WORKS_PATH,
        redacted_query=redacted_query,
        response_code=response.status_code,
        response_body=response.text,
        received_at_unix_usec=received_at_unix_usec,
        duration_usec=duration_usec,
    )
    append_http_request_log_record(log_path=resolved_log_path, record=record)
    return OpenAlexWorkTitleBatchResult(
        paperids=cleaned_paperids,
        query=redacted_query,
        response_code=response.status_code,
        titles_by_paperid=titles_by_paperid,
        received_at_unix_usec=received_at_unix_usec,
        duration_usec=duration_usec,
    )
