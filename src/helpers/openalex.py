from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import quote, urlencode

import requests
from dotenv import dotenv_values

from .data_models import (
    HttpRequestLogRecord,
    append_http_request_log_record,
    http_request_log_record,
    matching_http_request_log_record,
    redact_http_request_log_query,
)
from .vars import (
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
    OPENALEX_AUTHOR_SEARCH_LOG_PATH,
    OPENALEX_PAPER_TITLE_LOG_PATH,
)

OPENALEX_SCHEME = "https"
OPENALEX_HOST = "api.openalex.org"
OPENALEX_AUTHOR_SEARCH_PATH = "/authors"
OPENALEX_WORK_PATH_PREFIX = "/works/"
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


@dataclass(frozen=True)
class OpenAlexWorkTitleResult:
    paperid: str
    query: str
    response_code: int | None
    title: str | None
    reused: bool
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


def openalex_work_title_query(*, api_key: str) -> str:
    return urlencode(
        {
            "select": "title",
            "per_page": "1",
            "api_key": api_key,
        },
        quote_via=quote,
    )


def _redact_openalex_author_search_query(query: str) -> str:
    return redact_http_request_log_query(query)


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


def parse_openalex_work_title(response_body: str) -> str | None:
    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    return title


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


def _work_title_result_from_record(
    *,
    paperid: str,
    query: str,
    record: HttpRequestLogRecord,
    reused: bool,
) -> OpenAlexWorkTitleResult:
    return OpenAlexWorkTitleResult(
        paperid=paperid,
        query=query,
        response_code=record.response_code,
        title=parse_openalex_work_title(record.response_body),
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
    redacted_query = _redact_openalex_author_search_query(query)
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


def check_openalex_work_title(
    *,
    paperid: str,
    log_path: Path | None = None,
    env_path: Path = Path(".env"),
    api_key: str | None = None,
    request_get: _RequestGet | None = None,
) -> OpenAlexWorkTitleResult:
    paperid_str = str(paperid)
    resolved_log_path = log_path or openalex_paper_title_log_path()
    resolved_api_key = api_key or _api_key_from_env(env_path)
    query = openalex_work_title_query(api_key=resolved_api_key)
    redacted_query = redact_http_request_log_query(query)
    path = f"{OPENALEX_WORK_PATH_PREFIX}{paperid_str}"
    cached_record = matching_http_request_log_record(
        log_path=resolved_log_path,
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme=OPENALEX_SCHEME,
        host=OPENALEX_HOST,
        path=path,
        redacted_query=redacted_query,
    )
    if cached_record is not None:
        return _work_title_result_from_record(
            paperid=paperid_str,
            query=redacted_query,
            record=cached_record,
            reused=True,
        )

    url = f"{OPENALEX_SCHEME}://{OPENALEX_HOST}{path}?{query}"
    resolved_request_get = request_get or cast(_RequestGet, requests.get)
    start_ns = time.monotonic_ns()
    response = resolved_request_get(url, timeout=OPENALEX_AUTHOR_SEARCH_TIMEOUT_SECONDS)
    duration_usec = (time.monotonic_ns() - start_ns) // 1_000
    received_at_unix_usec = time.time_ns() // 1_000
    title = parse_openalex_work_title(response.text)
    record = http_request_log_record(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme=OPENALEX_SCHEME,
        host=OPENALEX_HOST,
        path=path,
        redacted_query=redacted_query,
        response_code=response.status_code,
        response_body=response.text,
        received_at_unix_usec=received_at_unix_usec,
        duration_usec=duration_usec,
    )
    append_http_request_log_record(log_path=resolved_log_path, record=record)
    return OpenAlexWorkTitleResult(
        paperid=paperid_str,
        query=redacted_query,
        response_code=response.status_code,
        title=title,
        reused=False,
        received_at_unix_usec=received_at_unix_usec,
        duration_usec=duration_usec,
    )
