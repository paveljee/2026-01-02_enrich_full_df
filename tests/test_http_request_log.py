from __future__ import annotations

from src.helpers.data_models.http_request_log import (
    append_http_request_log_record,
    http_request_log_record,
    matching_http_request_log_record,
    redact_http_request_log_query,
)


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


def test_redact_http_request_log_query_can_preserve_filter_separators() -> None:
    query = "filter=openalex_id:W123|W456&select=title&api_key=test-key"

    assert redact_http_request_log_query(query, safe=":|") == (
        "filter=openalex_id:W123|W456&select=title&api_key=REDACTED"
    )
