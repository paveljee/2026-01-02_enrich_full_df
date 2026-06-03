from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import parse_qsl, quote, urlencode

import requests
from dotenv import dotenv_values

from .vars import (
    KTP_SOURCE_KEY_COL,
    OPENALEX_AUTHOR_SEARCH_LOG_PATH,
    OPENALEX_AUTHOR_SEARCH_LOG_SCHEMA_VERSION,
)

OPENALEX_SCHEME = "https"
OPENALEX_HOST = "api.openalex.org"
OPENALEX_AUTHOR_SEARCH_PATH = "/authors"
OPENALEX_AUTHOR_SEARCH_TIMEOUT_SECONDS = 30.0


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


def openalex_author_search_log_path() -> Path:
    return Path(OPENALEX_AUTHOR_SEARCH_LOG_PATH)


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


def _redact_openalex_author_search_query(query: str) -> str:
    return urlencode(
        [
            (key, "REDACTED" if key == "api_key" else value)
            for key, value in parse_qsl(query, keep_blank_values=True)
        ],
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


def _api_key_from_env(env_path: Path) -> str:
    values = dotenv_values(env_path)
    api_key = values.get("OPENALEX_API_KEY") or os.environ.get("OPENALEX_API_KEY")
    if not api_key:
        raise ValueError(f"Missing OPENALEX_API_KEY in {env_path}")
    return api_key


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return None


def _matching_cached_record(
    *,
    log_path: Path,
    source_key: str,
    query: str,
) -> dict[str, object] | None:
    if not log_path.exists():
        return None
    match: dict[str, object] | None = None
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            record_query = record.get("query")
            if (
                record.get("schema_version") == OPENALEX_AUTHOR_SEARCH_LOG_SCHEMA_VERSION
                and record.get("method") == "GET"
                and record.get("scheme") == OPENALEX_SCHEME
                and record.get("host") == OPENALEX_HOST
                and record.get("path") == OPENALEX_AUTHOR_SEARCH_PATH
                and isinstance(record_query, str)
                and _redact_openalex_author_search_query(record_query) == query
                and record.get(KTP_SOURCE_KEY_COL) == source_key
            ):
                match = record
    return match


def _result_from_record(
    *,
    source_key: str,
    selected_author_id: str,
    query: str,
    record: dict[str, object],
    reused: bool,
) -> OpenAlexAuthorCheckResult:
    response_body = record.get("response_body")
    body_text = response_body if isinstance(response_body, str) else ""
    top_author_id = parse_openalex_top_author_id(body_text)
    response_code = record.get("response_code")
    duration_usec = record.get("duration_usec")
    received_at_unix_usec = record.get("received_at_unix_usec")
    return OpenAlexAuthorCheckResult(
        source_key=source_key,
        selected_author_id=selected_author_id,
        query=query,
        response_code=_optional_int(response_code),
        top_author_id=top_author_id,
        matched=top_author_id == selected_author_id,
        reused=reused,
        received_at_unix_usec=_optional_int(received_at_unix_usec),
        duration_usec=_optional_int(duration_usec) or 0,
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
    redacted_query = _redact_openalex_author_search_query(query)
    cached_record = _matching_cached_record(
        log_path=resolved_log_path,
        source_key=source_key,
        query=redacted_query,
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
    record = {
        "schema_version": OPENALEX_AUTHOR_SEARCH_LOG_SCHEMA_VERSION,
        "method": "GET",
        "scheme": OPENALEX_SCHEME,
        "host": OPENALEX_HOST,
        "path": OPENALEX_AUTHOR_SEARCH_PATH,
        "query": redacted_query,
        "request_headers": {},
        "request_body": None,
        "response_code": response.status_code,
        "response_headers": {},
        "response_body": response.text,
        "received_at_unix_usec": received_at_unix_usec,
        "duration_usec": duration_usec,
        KTP_SOURCE_KEY_COL: source_key,
        "selected_ssn_author_id": selected_author_id,
        "openalex_top_author_id": top_author_id,
        "openalex_match": matched,
    }
    resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
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
