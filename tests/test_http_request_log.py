from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.helpers.data_models.http_request_log import (
    HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY,
    HTTP_REQUEST_LOG_PORT_KEY,
    HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY,
    HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY,
    HttpRequestLogRecord,
    append_http_request_log_record,
    http_request_log_record,
    matching_http_request_log_record,
    redact_http_request_log_query,
)
from src.helpers.vars import (
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V2,
)

TEST_HTTP_HOST = "api.openalex.org"
TEST_HTTP_IPV6_HOST = "::1"
TEST_HTTP_DEFAULT_HTTPS_PORT = 443
TEST_HTTP_LOCAL_PORT = 8612
TEST_HTTP_READY_TO_RESPOND_AT_UNIX_USEC = 123457


def test_append_http_request_log_record_writes_escaped_unicode_jsonl(
    tmp_path,
) -> None:
    log_path = tmp_path / "logs" / "http.jsonl"
    record = http_request_log_record(
        schema_version=1,
        method="GET",
        scheme="https",
        host="api.openalex.org",
        path="/works/W123",
        redacted_query="select=title&api_key=REDACTED",
        response_code=200,
        response_body='{"title":"A Fine Paper 你好"}',
        received_at_unix_usec=123456,
        duration_usec=789,
    )

    append_http_request_log_record(log_path=log_path, record=record)

    raw = log_path.read_text(encoding="utf-8")
    assert "你好" not in raw
    assert "\\u4f60\\u597d" in raw
    assert raw.endswith("\n")


def test_appended_http_request_log_record_roundtrips_unicode(tmp_path) -> None:
    log_path = tmp_path / "http.jsonl"
    record = http_request_log_record(
        schema_version=1,
        method="GET",
        scheme="https",
        host="api.openalex.org",
        path="/works/W123",
        redacted_query="select=title&api_key=REDACTED",
        response_code=200,
        response_body='{"title":"A Fine Paper 你好"}',
        received_at_unix_usec=123456,
        duration_usec=789,
    )

    append_http_request_log_record(log_path=log_path, record=record)

    restored = matching_http_request_log_record(
        log_path=log_path,
        schema_version=1,
        method="GET",
        scheme="https",
        host="api.openalex.org",
        path="/works/W123",
        redacted_query="select=title&api_key=REDACTED",
    )

    assert restored is not None
    assert restored.response_body == '{"title":"A Fine Paper 你好"}'


def test_http_request_log_schema_version_1_omits_and_rejects_v2_fields() -> None:
    record = http_request_log_record(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme="https",
        host=TEST_HTTP_HOST,
        path="/works/W123",
        redacted_query="select=title&api_key=REDACTED",
        response_code=200,
        response_body='{"title":"A Fine Paper"}',
        received_at_unix_usec=123456,
        duration_usec=789,
    )
    serialized = record.model_dump()

    assert HTTP_REQUEST_LOG_PORT_KEY not in serialized
    assert HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY not in serialized
    assert HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY not in serialized
    with pytest.raises(ValidationError, match="port is not defined"):
        HttpRequestLogRecord.model_validate(
            serialized | {HTTP_REQUEST_LOG_PORT_KEY: None}
        )
    with pytest.raises(ValidationError, match="coerce_schema_v1 is not defined"):
        HttpRequestLogRecord.model_validate(
            serialized | {HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY: False}
        )
    with pytest.raises(
        ValidationError,
        match="ready_to_respond_at_unix_usec is not defined",
    ):
        HttpRequestLogRecord.model_validate(
            serialized | {HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY: None}
        )


@pytest.mark.parametrize(
    ("host", "port"),
    [
        (TEST_HTTP_HOST, None),
        (TEST_HTTP_HOST, TEST_HTTP_DEFAULT_HTTPS_PORT),
        ("127.0.0.1", TEST_HTTP_LOCAL_PORT),
        (TEST_HTTP_IPV6_HOST, TEST_HTTP_LOCAL_PORT),
    ],
)
def test_http_request_log_schema_version_2_roundtrips_optional_port(
    host: str,
    port: int | None,
) -> None:
    version_1 = http_request_log_record(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme="https",
        host=host,
        path="/works/W123",
        redacted_query="select=title&api_key=REDACTED",
        response_code=200,
        response_body='{"title":"A Fine Paper"}',
        received_at_unix_usec=123456,
        duration_usec=789,
    ).model_dump()
    version_2 = version_1 | {
        HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY: KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V2,
        HTTP_REQUEST_LOG_PORT_KEY: port,
    }
    expected_version_2 = version_2 | {
        HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY: False,
        HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY: None,
    }

    restored = HttpRequestLogRecord.model_validate_json(
        HttpRequestLogRecord.model_validate(version_2).model_dump_json()
    )

    assert restored.model_dump() == expected_version_2


def test_http_request_log_schema_version_2_defaults_port_and_coerces_v1() -> None:
    version_1 = http_request_log_record(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme="https",
        host=TEST_HTTP_HOST,
        path="/works/W123",
        redacted_query="select=title&api_key=REDACTED",
        response_code=200,
        response_body='{"title":"A Fine Paper"}',
        received_at_unix_usec=123456,
        duration_usec=789,
    ).model_dump()
    version_2 = version_1 | {
        HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY: KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V2
    }

    native = HttpRequestLogRecord.model_validate_json(
        HttpRequestLogRecord.model_validate(
            version_2
            | {
                HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY: (
                    TEST_HTTP_READY_TO_RESPOND_AT_UNIX_USEC
                )
            }
        ).model_dump_json()
    )
    coerced = HttpRequestLogRecord.model_validate(
        version_2 | {HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY: True}
    )
    json_schema = HttpRequestLogRecord.model_json_schema()

    assert HTTP_REQUEST_LOG_PORT_KEY in json_schema["properties"]
    assert HTTP_REQUEST_LOG_PORT_KEY not in json_schema["required"]
    assert (
        HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY
        in json_schema["properties"]
    )
    assert (
        HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY
        not in json_schema["required"]
    )
    assert native.port is None
    assert native.coerce_schema_v1 is False
    assert (
        native.ready_to_respond_at_unix_usec
        == TEST_HTTP_READY_TO_RESPOND_AT_UNIX_USEC
    )
    assert native.model_dump()[HTTP_REQUEST_LOG_PORT_KEY] is None
    assert coerced.port is None
    assert coerced.coerce_schema_v1 is True
    assert coerced.ready_to_respond_at_unix_usec is None
    assert coerced.model_dump()[HTTP_REQUEST_LOG_PORT_KEY] is None


def test_redact_http_request_log_query_can_preserve_filter_separators() -> None:
    query = "filter=openalex_id:W123|W456&select=title&api_key=test-key"

    assert redact_http_request_log_query(query, safe=":|") == (
        "filter=openalex_id:W123|W456&select=title&api_key=REDACTED"
    )
