from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Literal, Protocol, Self, cast
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid7

import requests
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    ValidationError,
    model_serializer,
    model_validator,
)
from pydantic_core import InitErrorDetails

from src.helpers.architecture import implements
from src.helpers.vars import (
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
)

HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY: Final = "schema_version"
HTTP_REQUEST_LOG_RECORD_ID_KEY: Final = "record_id"
HTTP_REQUEST_LOG_PORT_KEY: Final = "port"
HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY: Final = "coerce_schema_v1"
HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY: Final = (
    "ready_to_respond_at_unix_usec"
)
HTTP_REQUEST_LOG_RESPONSE_BODY_KEY: Final = "response_body"
HTTP_REQUEST_LOG_RESPONSE_HEADERS_KEY: Final = "response_headers"
HTTP_REQUEST_LOG_DURATION_USEC_KEY: Final = "duration_usec"
HttpRequestLogSchemaVersionV1 = Literal[1, "1"]
HttpRequestLogSchemaVersion = Literal[1, "1", "1.1"]


class HttpRequestLogRecordProtocol(Protocol):
    """The v1.1 record fields and existing response-conversion interface.

    The shared model also accepts legacy v1, reflected by its schema-version type.
    Excluded coercion input and Pydantic implementation hooks are not record fields.
    """

    @property
    def schema_version(self) -> HttpRequestLogSchemaVersion: ...

    @property
    def record_id(self) -> UUID: ...

    @property
    def method(self) -> str: ...

    @property
    def scheme(self) -> str: ...

    @property
    def host(self) -> str: ...

    @property
    def port(self) -> int | None: ...

    @property
    def ready_to_respond_at_unix_usec(self) -> int | None: ...

    @property
    def path(self) -> str: ...

    @property
    def query(self) -> str: ...

    @property
    def request_headers(self) -> dict[str, str]: ...

    @property
    def request_body(self) -> str | None: ...

    @property
    def response_code(self) -> int | None: ...

    @property
    def response_headers(self) -> dict[str, str] | None: ...

    @property
    def response_body(self) -> str | None: ...

    @property
    def received_at_unix_usec(self) -> int | None: ...

    @property
    def duration_usec(self) -> int | None: ...

    @classmethod
    def from_response(
        cls,
        response: requests.Response,
        *,
        received_at_unix_usec: int | None = None,
        ready_to_respond_at_unix_usec: int | None = None,
        duration_usec: int | None = None,
    ) -> Self: ...

    def to_response(self) -> requests.Response: ...


def _is_http_request_log_schema_version_1(value: object) -> bool:
    return value == KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION or (
        isinstance(value, int) and not isinstance(value, bool) and value == 1
    )


@implements[HttpRequestLogRecordProtocol]()
class HttpRequestLogRecord(BaseModel):
    """JSONL record for cached HTTP requests made by pipeline helpers.

    Current provider uses expect JSON: OpenAlex /authors, /works,
    /institutions/{id}, and ROR /v2/organizations/{id}. Local recorded routes
    are /pull, /push, synthetic /commit and /validate, and /completed, /failed,
    /cancelled. These use JSON or empty bodies, except /pull also returns UTF-8
    NDJSON or Markdown; /push specifies application/json for its request body.

    These text-based uses retain v1.1: capture uses Response.text and replay
    reconstructs UTF-8, not original bytes. Review every new endpoint's body
    format and encoding case by case before using this class. A future v2 should
    explicitly serialize raw body bytes (including Response.content) without
    character decoding; v1/v1.1 text-body contracts remain unchanged.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: HttpRequestLogSchemaVersion
    record_id: UUID = Field(default_factory=uuid7)
    method: str
    scheme: str
    host: str
    port: int | None = None
    coerce_schema_v1: bool = Field(default=False, exclude=True)
    ready_to_respond_at_unix_usec: int | None = None
    path: str
    query: str
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: str | None = None
    response_code: int | None
    response_headers: dict[str, str] | None = Field(default_factory=dict)
    response_body: str | None
    received_at_unix_usec: int | None
    duration_usec: int | None

    @classmethod
    def from_response(
        cls,
        response: requests.Response,
        *,
        received_at_unix_usec: int | None = None,
        ready_to_respond_at_unix_usec: int | None = None,
        duration_usec: int | None = None,
    ) -> Self:
        """
        Captures one completed exchange, using the response's prepared request.

        Returns a `HttpRequestLogRecord(schema_version="1.1")`.
        """
        request = response.request
        if request is None or request.url is None or request.method is None:
            raise ValueError("HTTP response is missing its prepared request")
        target = urlsplit(request.url)
        body = request.body
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        if body is not None and not isinstance(body, str):
            raise ValueError("HTTP logging requires a text request body")
        return cls(
            schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            method=request.method,
            scheme=target.scheme,
            host=target.hostname or "",
            port=target.port,
            path=target.path,
            query=redact_http_request_log_query(target.query),
            request_headers=dict(request.headers),
            request_body=body,
            response_code=response.status_code,
            response_headers=dict(response.headers),
            response_body=response.text,
            received_at_unix_usec=received_at_unix_usec,
            ready_to_respond_at_unix_usec=ready_to_respond_at_unix_usec,
            duration_usec=duration_usec,
        )

    def to_response(self) -> requests.Response:
        """Reconstruct the recorded text response without performing HTTP I/O."""
        if self.response_code is None:
            raise OSError("Recorded request did not receive an HTTP response")
        if self.response_body is None or self.response_headers is None:
            raise ValueError("Recorded HTTP response is incomplete")
        response = requests.Response()
        response.status_code = self.response_code
        response.headers.update(self.response_headers)
        response.encoding = "utf-8"
        response._content = self.response_body.encode("utf-8")
        _ = response.content  # Finalize the buffered body through requests' public accessor.
        host = f"[{self.host}]" if ":" in self.host else self.host
        authority = host if self.port is None else f"{host}:{self.port}"
        response.url = urlunsplit((self.scheme, authority, self.path, self.query, ""))
        response.request = requests.Request(
            self.method, response.url, headers=self.request_headers, data=self.request_body,
        ).prepare()
        return response

    @model_validator(mode="before")
    @classmethod
    def validate_versioned_fields(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        schema_version = value.get(HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY)
        coerce_schema_v1 = (
            value.get(HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY) is True
        )
        if _is_http_request_log_schema_version_1(schema_version):
            if coerce_schema_v1:
                version_1 = dict(value)
                version_1.pop(HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY, None)
                cls.model_validate(version_1)
                version_1_1 = dict(value)
                version_1_1[HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY] = (
                    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
                )
                return version_1_1
            version_1_errors: list[InitErrorDetails] = []
            # disallow legacy typing
            for field, error_type in (
                (HTTP_REQUEST_LOG_RESPONSE_BODY_KEY, "string_type"),
                (HTTP_REQUEST_LOG_RESPONSE_HEADERS_KEY, "dict_type"),
                (HTTP_REQUEST_LOG_DURATION_USEC_KEY, "int_type"),
            ):
                if field in value and value[field] is None:
                    version_1_errors.append(
                        InitErrorDetails(
                            type=error_type,
                            loc=(field,),
                            input=None,
                        )
                    )
            # disallow extra fields
            for field in (
                HTTP_REQUEST_LOG_RECORD_ID_KEY,
                HTTP_REQUEST_LOG_PORT_KEY,
                HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY,
                # HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY,  # but allow coercion field
            ):
                if field in value:
                    version_1_errors.append(
                        InitErrorDetails(
                            type="extra_forbidden",
                            loc=(field,),
                            input=value[field],
                        )
                    )
            version_1_1 = dict(value)
            version_1_1[HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY] = (
                KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            )
            version_1_1.pop(HTTP_REQUEST_LOG_RECORD_ID_KEY, None)
            version_1_1.pop(HTTP_REQUEST_LOG_PORT_KEY, None)
            version_1_1.pop(
                HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY,
                None,
            )
            ordinary_errors: list[Any] = []
            try:
                cls.model_validate(version_1_1)
            except ValidationError as exc:
                ordinary_errors = exc.errors(include_url=False)
            # raise
            line_errors = ordinary_errors + version_1_errors
            if line_errors:
                raise ValidationError.from_exception_data(
                    cls.__name__,
                    line_errors,
                )
            return value
        return value

    @model_serializer(mode="wrap")
    def serialize_versioned_fields(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        serialized = cast(dict[str, Any], handler(self))
        if _is_http_request_log_schema_version_1(self.schema_version):
            serialized.pop(HTTP_REQUEST_LOG_RECORD_ID_KEY, None)
            serialized.pop(HTTP_REQUEST_LOG_PORT_KEY, None)
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
    schema_version: HttpRequestLogSchemaVersion,
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
                (
                    record.schema_version == schema_version
                    or (
                        _is_http_request_log_schema_version_1(record.schema_version)
                        and _is_http_request_log_schema_version_1(schema_version)
                    )
                )
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
    schema_version: HttpRequestLogSchemaVersionV1,
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
