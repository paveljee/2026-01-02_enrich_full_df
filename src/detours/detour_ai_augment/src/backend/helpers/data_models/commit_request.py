from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, StrictStr, model_serializer, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    BASE64_TEXT_ENCODING,
    HTTP_POST_METHOD,
    NAME_KEY_HEADER,
    SOURCE_KEY_HEADER,
    SYNTHETIC_COMMIT_HOST,
    SYNTHETIC_COMMIT_SCHEME,
)
from src.detours.detour_ai_augment.src.shared import (
    name_key_header_value,
    source_key_header_value,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models import HttpRequestLogRecord, NameKey
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

from .ai_augment_http_request_log_record import RequestRecord

COMMIT_PATH = "/commit"


@implements[BackendComponent.AppendwatchReportEncodingProperty]()
class AppendwatchReportEncoding(StrEnum):
    value: Literal["base64"]

    BASE64 = "base64"


class _CodexRolloutRecordSummaryJson(FrozenStrictModel):
    originator: StrictStr
    source: StrictStr
    cli_version: StrictStr
    model_provider: StrictStr
    model: StrictStr
    reasoning_effort: StrictStr
    session_id: StrictStr
    timestamp: StrictStr

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        if any(not value.strip() for value in self.model_dump().values()):
            raise ValueError(Locale.CODEX_ROLLOUT_SUMMARY_BLANK)
        return self


@implements[BackendComponent.CodexRolloutRecordProperty]()
class CodexRolloutRecord(FrozenStrictModel):
    sha256: StrictStr
    size: int = Field(ge=0)
    line_count: int = Field(ge=1)

    @classmethod
    def build_summary_json(
        cls,
        values: Mapping[str, object],
    ) -> str:
        return _CodexRolloutRecordSummaryJson.model_validate(values).model_dump_json()

    @classmethod
    def parse_summary_json(
        cls,
        value: str,
    ) -> dict[str, str]:
        summary = _CodexRolloutRecordSummaryJson.model_validate_json(value)
        return {
            "originator": summary.originator,
            "source": summary.source,
            "cli_version": summary.cli_version,
            "model_provider": summary.model_provider,
            "model": summary.model,
            "reasoning_effort": summary.reasoning_effort,
            "session_id": summary.session_id,
            "timestamp": summary.timestamp,
        }


@implements[BackendComponent.AppendwatchReportRecordProperty]()
class AppendwatchReportRecord(FrozenStrictModel):
    encoding: AppendwatchReportEncoding
    data: StrictStr

    def validate_canonical_base64(self) -> Self:
        try:
            decoded = base64.b64decode(self.data, validate=True)
        except ValueError as exc:
            raise ValueError(Locale.APPENDWATCH_BASE64_INVALID) from exc
        if base64.b64encode(decoded).decode(BASE64_TEXT_ENCODING) != self.data:
            raise ValueError(Locale.APPENDWATCH_BASE64_NONCANONICAL)
        return self

    @model_validator(mode="after")
    def _validate_canonical_base64(self) -> Self:
        return self.validate_canonical_base64()

    def decoded_bytes(self) -> bytes:
        return base64.b64decode(self.data, validate=True)


@implements[BackendComponent.CodexSessionRecordProperty]()
class CodexSessionRecord(FrozenStrictModel):
    session_id: UUID | None
    codex_rollout_record: CodexRolloutRecord | None
    appendwatch_report_record: AppendwatchReportRecord | None


class _CodexSessionRecordJson(FrozenStrictModel):
    codex_session_id: UUID | None
    codex_rollout_record: CodexRolloutRecord | None
    appendwatch_report_record: AppendwatchReportRecord | None


class _CommitRequestBodyJson(FrozenStrictModel):
    pull_record_id: UUID
    push_record_id: UUID
    codex_session_record: _CodexSessionRecordJson

    @model_validator(mode="after")
    def validate_complete_codex_session_record(self) -> Self:
        session = self.codex_session_record
        if (
            session.codex_session_id is None
            or session.codex_rollout_record is None
            or session.appendwatch_report_record is None
        ):
            raise ValueError(Locale.COMMIT_SESSION_INCOMPLETE)
        return self


@implements[BackendComponent.CommitRequestBodyProperty]()
class CommitRequestBody(FrozenStrictModel):
    pull_response_record: PullResponseRecord
    push_response_record: PushResponseRecord
    codex_session_record: CodexSessionRecord

    def validate_complete_commit(self) -> Self:
        session = self.codex_session_record
        if (
            session.session_id is None
            or session.codex_rollout_record is None
            or session.appendwatch_report_record is None
        ):
            raise ValueError(Locale.COMMIT_SESSION_INCOMPLETE)
        return self

    @model_validator(mode="after")
    def _validate_complete_commit(self) -> Self:
        return self.validate_complete_commit()

    @classmethod
    def validate_serialized_json(cls, value: str) -> None:
        _CommitRequestBodyJson.model_validate_json(value)

    @classmethod
    def from_serialized_json(
        cls,
        value: str,
        *,
        resolve_http_record: Callable[
            [UUID], PullResponseRecord | PushResponseRecord
        ],
    ) -> Self:
        serialized = _CommitRequestBodyJson.model_validate_json(value)
        session = serialized.codex_session_record
        pull_response_record = resolve_http_record(serialized.pull_record_id)
        push_response_record = resolve_http_record(serialized.push_record_id)
        if not isinstance(pull_response_record, PullResponseRecord) or not isinstance(
            push_response_record, PushResponseRecord
        ):
            raise ValueError(Locale.COMMIT_BODY_RECORDS_MISMATCH)
        return cls(
            pull_response_record=pull_response_record,
            push_response_record=push_response_record,
            codex_session_record=CodexSessionRecord(
                session_id=session.codex_session_id,
                codex_rollout_record=session.codex_rollout_record,
                appendwatch_report_record=session.appendwatch_report_record,
            ),
        )

    def serialize(self) -> dict[str, object]:
        session_id = self.codex_session_record.session_id
        rollout = self.codex_session_record.codex_rollout_record
        report = self.codex_session_record.appendwatch_report_record
        assert session_id is not None
        assert rollout is not None
        assert report is not None
        return {
            "pull_record_id": self.pull_response_record.record_id,
            "push_record_id": self.push_response_record.record_id,
            "codex_session_record": _CodexSessionRecordJson(
                codex_session_id=session_id,
                codex_rollout_record=rollout,
                appendwatch_report_record=report,
            ),
        }

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()


@implements[BackendComponent.CommitRequestRecordProperty]()
class BackendCommitRequestRecord(RequestRecord):
    commit_request_body: CommitRequestBody = Field(exclude=True)

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return super().http_request_log_record

    @classmethod
    def from_serialized_json(
        cls,
        *,
        value: str,
        resolve_http_record: Callable[
            [UUID], PullResponseRecord | PushResponseRecord
        ] | None = None,
    ) -> Self:
        if resolve_http_record is None:
            raise ValueError(Locale.COMMIT_REFERENCES_REQUIRED)
        return cls.from_http_request_log_record(
            HttpRequestLogRecord.model_validate_json(value),
            resolve_http_record=resolve_http_record,
        )

    def serialize(self) -> dict[str, object]:
        return self.http_request_log_record.model_dump(mode="json")

    def validate_commit_request_record(self) -> Self:
        if (
            self.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            or self.record_id.version != 7
            or self.method != HTTP_POST_METHOD
            or self.scheme != SYNTHETIC_COMMIT_SCHEME
            or self.host != SYNTHETIC_COMMIT_HOST
            or self.port is not None
            or self.ready_to_respond_at_unix_usec is not None
            or self.path != COMMIT_PATH
            or self.query
            or set(self.request_headers) != {SOURCE_KEY_HEADER, NAME_KEY_HEADER}
            or self.request_body is None
            or self.response_code is not None
            or self.response_headers is not None
            or self.response_body is not None
            or self.received_at_unix_usec is not None
            or self.duration_usec is not None
        ):
            raise ValueError(Locale.COMMIT_HTTP_CONTOUR_INVALID)
        expected = self.commit_request_body
        refs: dict[UUID, PullResponseRecord | PushResponseRecord] = {
            expected.pull_response_record.record_id: expected.pull_response_record,
            expected.push_response_record.record_id: expected.push_response_record,
        }
        parsed = CommitRequestBody.from_serialized_json(
            self.request_body,
            resolve_http_record=lambda record_id: refs[record_id],
        )
        if parsed != expected:
            raise ValueError(Locale.COMMIT_BODY_RECORDS_MISMATCH)
        return self

    @model_validator(mode="after")
    def _validate_commit_request_record(self) -> Self:
        return self.validate_commit_request_record()

    @classmethod
    def from_http_request_log_record(
        cls,
        http_request_log_record: HttpRequestLogRecord,
        *,
        resolve_http_record: Callable[
            [UUID], PullResponseRecord | PushResponseRecord
        ] | None = None,
    ) -> Self:
        if resolve_http_record is None:
            raise ValueError(Locale.COMMIT_REFERENCES_REQUIRED)
        record = http_request_log_record
        if record.request_body is None:
            raise ValueError(Locale.COMMIT_BODY_MISSING)
        body = CommitRequestBody.from_serialized_json(
            record.request_body,
            resolve_http_record=resolve_http_record,
        )
        return cls(
            schema_version=record.schema_version,
            record_id=record.record_id,
            method=record.method,
            scheme=record.scheme,
            host=record.host,
            port=record.port,
            path=record.path,
            query=record.query,
            request_headers=record.request_headers,
            request_body=record.request_body,
            response_code=record.response_code,
            response_headers=record.response_headers,
            response_body=record.response_body,
            received_at_unix_usec=record.received_at_unix_usec,
            ready_to_respond_at_unix_usec=record.ready_to_respond_at_unix_usec,
            duration_usec=record.duration_usec,
            commit_request_body=body,
        )


def _synthetic_commit_request_record(
    *,
    pull_response_record: PullResponseRecord,
    push_response_record: PushResponseRecord,
    session_id: UUID,
    rollout: CodexRolloutRecord,
    rollout_filename: str,
    appendwatch_report: bytes,
    namekey: NameKey,
) -> BackendCommitRequestRecord:
    session = CodexSessionRecord(
        session_id=session_id,
        codex_rollout_record=rollout,
        appendwatch_report_record=AppendwatchReportRecord(
            encoding=AppendwatchReportEncoding.BASE64,
            data=base64.b64encode(appendwatch_report).decode(BASE64_TEXT_ENCODING),
        ),
    )
    body = CommitRequestBody(
        pull_response_record=pull_response_record,
        push_response_record=push_response_record,
        codex_session_record=session,
    )
    assert body.pull_response_record is pull_response_record
    assert body.push_response_record is push_response_record
    return BackendCommitRequestRecord(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        method=HTTP_POST_METHOD,
        scheme=SYNTHETIC_COMMIT_SCHEME,
        host=SYNTHETIC_COMMIT_HOST,
        port=None,
        ready_to_respond_at_unix_usec=None,
        path=COMMIT_PATH,
        query="",
        request_headers={
            SOURCE_KEY_HEADER: source_key_header_value(rollout_filename, rollout.line_count),
            NAME_KEY_HEADER: name_key_header_value(namekey),
        },
        request_body=body.model_dump_json(),
        response_code=None,
        response_headers=None,
        response_body=None,
        received_at_unix_usec=None,
        duration_usec=None,
        commit_request_body=body,
    )


# Deliberate post-definition imports: the concrete pull/push response types
# form a Pydantic annotation ring with commit and validation. All commit
# models must exist before
# importing those modules. These names then resolve to the actual classes;
# no generic HTTP field or manual model_rebuild is used for the links.
from .pull_event import PullResponseRecord  # noqa: E402
from .push_event import PushResponseRecord  # noqa: E402
