from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class HttpRequestLogRecord(BaseModel):
    """JSONL record for cached HTTP requests made by pipeline helpers."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: int
    method: str
    scheme: str
    host: str
    path: str
    query: str
    request_headers: dict[str, Any] = Field(default_factory=dict)
    request_body: Any | None = None
    response_code: int | None
    response_headers: dict[str, Any] = Field(default_factory=dict)
    response_body: str
    received_at_unix_usec: int | None
    duration_usec: int


def redact_http_request_log_query(
    query: str,
    *,
    sensitive_keys: set[str] | None = None,
    safe: str = "",
) -> str:
    keys = sensitive_keys or {"api_key"}
    return urlencode(
        [
            (key, "REDACTED" if key in keys else value)
            for key, value in parse_qsl(query, keep_blank_values=True)
        ],
        safe=safe,
        quote_via=quote,
    )


def matching_http_request_log_record(
    *,
    log_path: Path,
    schema_version: int,
    method: str,
    scheme: str,
    host: str,
    path: str,
    redacted_query: str,
) -> HttpRequestLogRecord | None:
    if not log_path.exists():
        return None
    match: HttpRequestLogRecord | None = None
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = HttpRequestLogRecord.model_validate_json(line)
            except ValidationError:
                continue
            if (
                record.schema_version == schema_version
                and record.method == method
                and record.scheme == scheme
                and record.host == host
                and record.path == path
                and redact_http_request_log_query(record.query) == redacted_query
            ):
                match = record
    return match


def http_request_log_record(
    *,
    schema_version: int,
    method: str,
    scheme: str,
    host: str,
    path: str,
    redacted_query: str,
    response_code: int,
    response_body: str,
    received_at_unix_usec: int,
    duration_usec: int,
) -> HttpRequestLogRecord:
    return HttpRequestLogRecord(
        schema_version=schema_version,
        method=method,
        scheme=scheme,
        host=host,
        path=path,
        query=redacted_query,
        request_headers={},
        request_body=None,
        response_code=response_code,
        response_headers={},
        response_body=response_body,
        received_at_unix_usec=received_at_unix_usec,
        duration_usec=duration_usec,
    )


def append_http_request_log_record(*, log_path: Path, record: HttpRequestLogRecord) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json(ensure_ascii=False) + "\n")
