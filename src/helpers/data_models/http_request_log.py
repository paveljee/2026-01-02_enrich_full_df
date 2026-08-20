from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Literal, cast
from urllib.parse import parse_qsl, quote, urlencode

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    ValidationError,
    model_serializer,
    model_validator,
)

from src.helpers.vars import (
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V2,
)

HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY: Final = "schema_version"
HTTP_REQUEST_LOG_PORT_KEY: Final = "port"
HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY: Final = "coerce_schema_v1"
HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY: Final = (
    "ready_to_respond_at_unix_usec"
)
HTTP_REQUEST_LOG_V1_PORT_FORBIDDEN: Final = (
    "{} is not defined in schema version 1"
).format(HTTP_REQUEST_LOG_PORT_KEY)
HTTP_REQUEST_LOG_V1_COERCION_FORBIDDEN: Final = (
    "{} is not defined in schema version 1"
).format(HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY)
HTTP_REQUEST_LOG_V1_READY_TO_RESPOND_FORBIDDEN: Final = (
    "{} is not defined in schema version 1"
).format(HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY)
HttpRequestLogSchemaVersion = Literal[1, 2]


class HttpRequestLogRecord(BaseModel):
    """JSONL record for cached HTTP requests made by pipeline helpers."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: HttpRequestLogSchemaVersion
    method: str
    scheme: str
    host: str
    port: int | None = None
    coerce_schema_v1: bool = False
    ready_to_respond_at_unix_usec: int | None = None
    path: str
    query: str
    request_headers: dict[str, Any] = Field(default_factory=dict)
    request_body: Any | None = None
    response_code: int | None
    response_headers: dict[str, Any] = Field(default_factory=dict)
    response_body: str
    received_at_unix_usec: int | None
    duration_usec: int

    @model_validator(mode="before")
    @classmethod
    def validate_versioned_fields(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        schema_version = value.get(HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY)
        has_port = HTTP_REQUEST_LOG_PORT_KEY in value
        has_coerce_schema_v1 = HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY in value
        has_ready_to_respond = (
            HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY in value
        )
        if schema_version == KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION:
            if has_port:
                raise ValueError(HTTP_REQUEST_LOG_V1_PORT_FORBIDDEN)
            if has_coerce_schema_v1:
                raise ValueError(HTTP_REQUEST_LOG_V1_COERCION_FORBIDDEN)
            if has_ready_to_respond:
                raise ValueError(HTTP_REQUEST_LOG_V1_READY_TO_RESPOND_FORBIDDEN)
            return value
        if (
            schema_version == KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V2
            and value.get(HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY, False) is True
        ):
            version_1 = dict(value)
            version_1[HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY] = (
                KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION
            )
            version_1.pop(HTTP_REQUEST_LOG_PORT_KEY, None)
            version_1.pop(HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY, None)
            version_1.pop(HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY, None)
            cls.model_validate(version_1)
        return value

    @model_serializer(mode="wrap")
    def serialize_versioned_port(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        serialized = cast(dict[str, Any], handler(self))
        if self.schema_version == KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION:
            serialized.pop(HTTP_REQUEST_LOG_PORT_KEY, None)
            serialized.pop(HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY, None)
            serialized.pop(HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY, None)
        return serialized


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
    schema_version: Literal[1],
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
        # DO NOT REMOVE: I would prefer ensure_ascii=False,
        # but OpenAlex returns escaped, so am keeping this.
        # signed-off: human
        handle.write(record.model_dump_json(ensure_ascii=True) + "\n")
