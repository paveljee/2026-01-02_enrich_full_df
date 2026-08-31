from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.helpers.data_models.http_request_log import (
    HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY,
    HTTP_REQUEST_LOG_PORT_KEY,
    HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY,
    HTTP_REQUEST_LOG_RECORD_ID_KEY,
    HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY,
    HttpRequestLogRecord,
    HttpRequestLogSchemaVersion,
    HttpRequestLogSchemaVersionV1,
    append_http_request_log_record,
    http_request_log_record,
    matching_http_request_log_record,
    redact_http_request_log_query,
)
from src.helpers.vars import (
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
)

TEST_HTTP_HOST = "api.openalex.org"
TEST_HTTP_IPV6_HOST = "::1"
TEST_HTTP_DEFAULT_HTTPS_PORT = 443
TEST_HTTP_LOCAL_PORT = 8612
TEST_HTTP_READY_TO_RESPOND_AT_UNIX_USEC = 123457


def test_http_request_log_schema_version_uses_strings_and_legacy_v1_int() -> None:
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
    version_1_1 = HttpRequestLogRecord.model_validate(
        version_1
        | {
            HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY: (
                KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            )
        }
    )
    legacy_version_1 = HttpRequestLogRecord.model_validate(
        version_1 | {HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY: 1}
    )
    restored_legacy_version_1 = HttpRequestLogRecord.model_validate_json(
        legacy_version_1.model_dump_json()
    )

    assert version_1[HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY] == "1"
    assert isinstance(version_1[HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY], str)
    assert legacy_version_1.schema_version == 1
    assert isinstance(legacy_version_1.schema_version, int)
    assert HTTP_REQUEST_LOG_RECORD_ID_KEY not in legacy_version_1.model_dump()
    assert restored_legacy_version_1.schema_version == 1
    assert version_1_1.schema_version == "1.1"
    assert isinstance(version_1_1.schema_version, str)
    for invalid_schema_version in ("1.0", 1.1, 2):
        with pytest.raises(ValidationError):
            HttpRequestLogRecord.model_validate(
                version_1
                | {HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY: invalid_schema_version}
            )


def test_http_request_log_record_id_defaults_to_unique_uuid7_in_v1_1() -> None:
    version_1 = http_request_log_record(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme="https",
        host="api.openalex.org",
        path="/works/W123",
        redacted_query="select=title&api_key=REDACTED",
        response_code=200,
        response_body='{"title":"A Fine Paper"}',
        received_at_unix_usec=123456,
        duration_usec=789,
    ).model_dump()
    version_1_1 = version_1 | {
        HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY: KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
    }
    record = HttpRequestLogRecord.model_validate(version_1_1)
    another = HttpRequestLogRecord.model_validate(version_1_1)
    restored = HttpRequestLogRecord.model_validate_json(record.model_dump_json())

    assert HTTP_REQUEST_LOG_RECORD_ID_KEY not in version_1
    assert record.record_id.version == 7
    assert another.record_id.version == 7
    assert another.record_id != record.record_id
    assert restored.record_id == record.record_id


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
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme="https",
        host="api.openalex.org",
        path="/works/W123",
        redacted_query="select=title&api_key=REDACTED",
    )

    assert restored is not None
    assert restored.response_body == '{"title":"A Fine Paper 你好"}'


def test_http_request_log_schema_version_1_omits_and_rejects_v1_1_fields() -> None:
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

    assert HTTP_REQUEST_LOG_RECORD_ID_KEY not in serialized
    assert HTTP_REQUEST_LOG_PORT_KEY not in serialized
    assert HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY not in serialized
    assert HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY not in serialized
    for field in (
        HTTP_REQUEST_LOG_RECORD_ID_KEY,
        HTTP_REQUEST_LOG_PORT_KEY,
        HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY,
    ):
        with pytest.raises(ValidationError) as raised:
            HttpRequestLogRecord.model_validate(serialized | {field: None})

        assert raised.value.errors(include_url=False) == [
            {
                "type": "extra_forbidden",
                "loc": (field,),
                "msg": "Extra inputs are not permitted",
                "input": None,
            }
        ]
    explicit_false = HttpRequestLogRecord.model_validate(
        serialized | {HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY: False}
    )

    assert explicit_false.schema_version == KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION
    assert explicit_false.coerce_schema_v1 is False
    assert explicit_false.model_dump() == serialized


@pytest.mark.parametrize(
    ("host", "port"),
    [
        (TEST_HTTP_HOST, None),
        (TEST_HTTP_HOST, TEST_HTTP_DEFAULT_HTTPS_PORT),
        ("127.0.0.1", TEST_HTTP_LOCAL_PORT),
        (TEST_HTTP_IPV6_HOST, TEST_HTTP_LOCAL_PORT),
    ],
)
def test_http_request_log_schema_version_1_1_roundtrips_optional_port(
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
    version_1_1 = version_1 | {
        HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY: KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        HTTP_REQUEST_LOG_PORT_KEY: port,
    }
    expected_version_1_1 = version_1_1 | {
        HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY: False,
        HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY: None,
    }

    record = HttpRequestLogRecord.model_validate(version_1_1)
    restored = HttpRequestLogRecord.model_validate_json(record.model_dump_json())

    assert restored.model_dump(exclude={HTTP_REQUEST_LOG_RECORD_ID_KEY}) == (
        expected_version_1_1
    )
    assert restored.record_id == record.record_id


@pytest.mark.parametrize("schema_version", [1, "1"])
def test_http_request_log_schema_version_1_is_promoted_only_with_opt_in(
    schema_version: HttpRequestLogSchemaVersionV1,
) -> None:
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
    version_1[HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY] = schema_version
    version_1_1 = version_1 | {
        HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY: KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
    }

    native_version_1 = HttpRequestLogRecord.model_validate(version_1)
    native = HttpRequestLogRecord.model_validate_json(
        HttpRequestLogRecord.model_validate(
            version_1_1
            | {
                HTTP_REQUEST_LOG_READY_TO_RESPOND_AT_UNIX_USEC_KEY: (
                    TEST_HTTP_READY_TO_RESPOND_AT_UNIX_USEC
                )
            }
        ).model_dump_json()
    )
    coerced = HttpRequestLogRecord.model_validate(
        version_1 | {HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY: True}
    )
    restored_coerced = HttpRequestLogRecord.model_validate_json(
        coerced.model_dump_json()
    )
    json_schema = HttpRequestLogRecord.model_json_schema()

    assert HTTP_REQUEST_LOG_RECORD_ID_KEY in json_schema["properties"]
    assert HTTP_REQUEST_LOG_RECORD_ID_KEY not in json_schema["required"]
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
    assert (
        native_version_1.schema_version
        == schema_version
    )
    assert HTTP_REQUEST_LOG_RECORD_ID_KEY not in native_version_1.model_dump()
    assert HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY not in native_version_1.model_dump()
    assert native.port is None
    assert native.coerce_schema_v1 is False
    assert (
        native.ready_to_respond_at_unix_usec
        == TEST_HTTP_READY_TO_RESPOND_AT_UNIX_USEC
    )
    assert native.model_dump()[HTTP_REQUEST_LOG_PORT_KEY] is None
    assert coerced.schema_version == KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
    assert coerced.record_id.version == 7
    assert HTTP_REQUEST_LOG_RECORD_ID_KEY in coerced.model_dump()
    assert coerced.port is None
    assert coerced.coerce_schema_v1 is True
    assert coerced.ready_to_respond_at_unix_usec is None
    assert coerced.model_dump()[HTTP_REQUEST_LOG_PORT_KEY] is None
    assert restored_coerced == coerced


def test_invalid_schema_version_1_is_rejected_before_opt_in_migration() -> None:
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
    version_1["method"] = 1

    with pytest.raises(ValidationError) as raised:
        HttpRequestLogRecord.model_validate(
            version_1 | {HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY: True}
        )

    assert raised.value.errors(include_url=False) == [
        {
            "type": "string_type",
            "loc": ("method",),
            "msg": "Input should be a valid string",
            "input": 1,
        }
    ]


def test_schema_version_1_reports_ordinary_and_versioned_pydantic_errors() -> None:
    version_1 = http_request_log_record(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme="https",
        host=TEST_HTTP_HOST,
        path="/works/W123",
        redacted_query="select=title&api_key=REDACTED",
        response_code=200,
        response_body="response",
        received_at_unix_usec=123456,
        duration_usec=789,
    ).model_dump() | {
        "method": 1,
        "response_body": None,
        HTTP_REQUEST_LOG_PORT_KEY: None,
    }

    with pytest.raises(ValidationError) as raised:
        HttpRequestLogRecord.model_validate(version_1)

    assert raised.value.errors(include_url=False) == [
        {
            "type": "string_type",
            "loc": ("method",),
            "msg": "Input should be a valid string",
            "input": 1,
        },
        {
            "type": "string_type",
            "loc": ("response_body",),
            "msg": "Input should be a valid string",
            "input": None,
        },
        {
            "type": "extra_forbidden",
            "loc": (HTTP_REQUEST_LOG_PORT_KEY,),
            "msg": "Extra inputs are not permitted",
            "input": None,
        },
    ]


def test_redact_http_request_log_query_can_preserve_filter_separators() -> None:
    query = "filter=openalex_id:W123|W456&select=title&api_key=test-key"

    assert redact_http_request_log_query(query, safe=":|") == (
        "filter=openalex_id:W123|W456&select=title&api_key=REDACTED"
    )


@pytest.mark.parametrize(
    (
        "schema_version",
        "response_body",
        "coerce_schema_v1",
        "valid",
        "expected_schema_version",
    ),
    [
        # Schema v1 requires a string response body.
        (
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
            "response",
            None,
            True,
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        ),
        (
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
            "response",
            False,
            True,
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        ),
        (KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION, None, None, False, None),
        # Opt-in migration promotes only valid v1 input.
        (
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
            "response",
            True,
            True,
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        ),
        (KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION, None, True, False, None),
        # Native schema v1.1 allows either string or null.
        (
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            "response",
            False,
            True,
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        ),
        (
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            None,
            False,
            True,
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        ),
        # Schema v1.1 ignores the migration flag.
        (
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            "response",
            True,
            True,
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        ),
        (
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            None,
            True,
            True,
            KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        ),
    ],
)
def test_http_request_log_response_body_is_required_in_v1_and_nullable_in_v1_1(
    schema_version: HttpRequestLogSchemaVersion,
    response_body: str | None,
    coerce_schema_v1: bool | None,
    valid: bool,
    expected_schema_version: HttpRequestLogSchemaVersion | None,
) -> None:
    value = http_request_log_record(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme="https",
        host=TEST_HTTP_HOST,
        path="/works/W123",
        redacted_query="select=title&api_key=REDACTED",
        response_code=200,
        response_body="response",
        received_at_unix_usec=123456,
        duration_usec=789,
    ).model_dump()

    value[HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY] = schema_version
    value["response_body"] = response_body

    if coerce_schema_v1 is not None:
        value[HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY] = coerce_schema_v1

    if valid:
        record = HttpRequestLogRecord.model_validate(value)
        restored = HttpRequestLogRecord.model_validate_json(
            record.model_dump_json()
        )

        assert restored.response_body == response_body
        assert restored.schema_version == expected_schema_version
    else:
        with pytest.raises(ValidationError) as raised:
            HttpRequestLogRecord.model_validate(value)

        assert raised.value.errors(include_url=False) == [
            {
                "type": "string_type",
                "loc": ("response_body",),
                "msg": "Input should be a valid string",
                "input": None,
            }
        ]


@pytest.mark.parametrize("coerce_schema_v1", [None, False, True])
def test_invalid_schema_version_1_1_ignores_v1_coercion_flag(
    coerce_schema_v1: bool | None,
) -> None:
    value = http_request_log_record(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method="GET",
        scheme="https",
        host=TEST_HTTP_HOST,
        path="/works/W123",
        redacted_query="select=title&api_key=REDACTED",
        response_code=200,
        response_body="response",
        received_at_unix_usec=123456,
        duration_usec=789,
    ).model_dump() | {
        HTTP_REQUEST_LOG_SCHEMA_VERSION_KEY: KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        HTTP_REQUEST_LOG_PORT_KEY: "8612",
    }
    if coerce_schema_v1 is not None:
        value[HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY] = coerce_schema_v1

    with pytest.raises(ValidationError) as raised:
        HttpRequestLogRecord.model_validate(value)

    assert raised.value.errors(include_url=False) == [
        {
            "type": "int_type",
            "loc": ("port",),
            "msg": "Input should be a valid integer",
            "input": "8612",
        }
    ]
