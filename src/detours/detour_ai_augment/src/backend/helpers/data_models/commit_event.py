from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable, Mapping
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Final, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    model_serializer,
    model_validator,
)

from src.helpers.architecture import implements
from src.helpers.data_models import FragmentType, HttpRequestLogRecord
from src.helpers.vars import (
    KTP_FILENAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
)

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from ....control_centre.dashboard.helpers.data_models.run_outcome import (
    NAME_KEY_HEADER,
)

COMMIT_PATH = "/commit"
HTTP_POST_METHOD = "POST"
SYNTHETIC_SCHEME = "http"
SYNTHETIC_HOST = "invalid"
SOURCE_KEY_HEADER = "Source-Key"
BASE64_TEXT_ENCODING = "ascii"
ROLLOUT_LINE_FRAGMENT_TYPE = FragmentType.LINE_NUMBER.value
STRUCTURED_FIELD_JSON_STRING = r'"(?:\\.|[^"\\])*"'
SOURCE_KEY_PATTERN = re.compile(
    rf"^{re.escape(KTP_FILENAME_COL)}=(?P<filename>{STRUCTURED_FIELD_JSON_STRING}), "
    rf"{re.escape(KTP_FRAGMENT_COL)}=(?P<fragment>[0-9]+), "
    rf'{re.escape(KTP_FRAGMENT_TYPE_COL)}="{ROLLOUT_LINE_FRAGMENT_TYPE}"$'
)


def source_key_header_value(filename: str, line_count: int) -> str:
    return (
        f"{KTP_FILENAME_COL}={json.dumps(filename, ensure_ascii=False)}, "
        f"{KTP_FRAGMENT_COL}={line_count}, "
        f'{KTP_FRAGMENT_TYPE_COL}="{ROLLOUT_LINE_FRAGMENT_TYPE}"'
    )


def source_key_from_header_value(value: object) -> tuple[str, int]:
    if not isinstance(value, str):
        raise ValueError("Source-Key header is missing")
    matched = SOURCE_KEY_PATTERN.fullmatch(value)
    if matched is None:
        raise ValueError("Source-Key header is malformed")
    try:
        filename = json.loads(matched.group("filename"))
        line_count = int(matched.group("fragment"))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Source-Key header is malformed") from exc
    if (
        not isinstance(filename, str)
        or not filename
        or PurePosixPath(filename).name != filename
        or line_count < 1
        or value != source_key_header_value(filename, line_count)
    ):
        raise ValueError("Source-Key header is not canonical")
    return filename, line_count


@implements[BackendComponent.AgentRuntimePort.AppendwatchReportEncodingProperty]()
class AppendwatchReportEncoding(StrEnum):
    value: Literal["base64"]

    BASE64 = "base64"


@implements[BackendComponent.LifecycleProperty]()
class BackendLifecycle(StrEnum):
    value: Literal[
        "ready",
        "busy",
        "configuration",
        "appendwatch_report_validation",
        "rollout_index",
        "pydantic_validation",
        "duckdb_evidence_validation",
        "researcher_resolution",
        "innerdict_and_card",
        "accepted",
        "configuration_error",
        "rejected",
        "retry",
        "complete",
        "failed",
    ]

    READY = "ready"
    BUSY = "busy"
    CONFIGURATION = "configuration"
    APPENDWATCH_REPORT_VALIDATION = "appendwatch_report_validation"
    ROLLOUT_INDEX = "rollout_index"
    PYDANTIC_VALIDATION = "pydantic_validation"
    DUCKDB_EVIDENCE_VALIDATION = "duckdb_evidence_validation"
    RESEARCHER_RESOLUTION = "researcher_resolution"
    INNERDICT_AND_CARD = "innerdict_and_card"
    ACCEPTED = "accepted"
    CONFIGURATION_ERROR = "configuration_error"
    REJECTED = "rejected"
    RETRY = "retry"
    COMPLETE = "complete"
    FAILED = "failed"

    def is_post_commit_validation_stage(self) -> bool:
        return self in POST_COMMIT_VALIDATION_STAGES

    def is_post_commit_validation_result(self) -> bool:
        return self in POST_COMMIT_VALIDATION_RESULTS


POST_COMMIT_VALIDATION_STAGES: Final = frozenset({
    BackendLifecycle.CONFIGURATION,
    BackendLifecycle.APPENDWATCH_REPORT_VALIDATION,
    BackendLifecycle.ROLLOUT_INDEX,
    BackendLifecycle.PYDANTIC_VALIDATION,
    BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION,
    BackendLifecycle.RESEARCHER_RESOLUTION,
    BackendLifecycle.INNERDICT_AND_CARD,
    BackendLifecycle.ACCEPTED,
})
POST_COMMIT_VALIDATION_RESULTS: Final = frozenset({
    BackendLifecycle.ACCEPTED,
    BackendLifecycle.CONFIGURATION_ERROR,
    BackendLifecycle.REJECTED,
})


class _CodexRolloutRecordSummaryJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

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
            raise ValueError("Codex rollout summary values must be nonblank")
        return self


@implements[BackendComponent.AgentRuntimePort.CodexRolloutRecordProperty]()
class CodexRolloutRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

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


@implements[BackendComponent.AgentRuntimePort.AppendwatchReportRecordProperty]()
class AppendwatchReportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    encoding: AppendwatchReportEncoding
    data: StrictStr

    def validate_canonical_base64(self) -> Self:
        try:
            decoded = base64.b64decode(self.data, validate=True)
        except ValueError as exc:
            raise ValueError("appendwatch report is not valid base64") from exc
        if base64.b64encode(decoded).decode(BASE64_TEXT_ENCODING) != self.data:
            raise ValueError("appendwatch report is not canonical base64")
        return self

    @model_validator(mode="after")
    def _validate_canonical_base64(self) -> Self:
        return self.validate_canonical_base64()

    def decoded_bytes(self) -> bytes:
        return base64.b64decode(self.data, validate=True)


@implements[BackendComponent.CodexSessionRecordProperty]()
class CodexSessionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    session_id: UUID | None
    codex_rollout_record: CodexRolloutRecord | None
    appendwatch_report_record: AppendwatchReportRecord | None


class _CodexSessionRecordJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    codex_session_id: UUID | None
    codex_rollout_record: CodexRolloutRecord | None
    appendwatch_report_record: AppendwatchReportRecord | None


class _CommitRequestBodyJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

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
            raise ValueError("commit requires a complete Codex session record")
        return self


@implements[BackendComponent.CommitRequestBodyProperty]()
class CommitRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pull_record: HttpRequestLogRecord
    push_record: HttpRequestLogRecord
    codex_session_record: CodexSessionRecord

    def validate_complete_commit(self) -> Self:
        session = self.codex_session_record
        if (
            session.session_id is None
            or session.codex_rollout_record is None
            or session.appendwatch_report_record is None
        ):
            raise ValueError("commit requires a complete Codex session record")
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
        resolve_http_record: Callable[[UUID], HttpRequestLogRecord],
    ) -> Self:
        serialized = _CommitRequestBodyJson.model_validate_json(value)
        session = serialized.codex_session_record
        return cls(
            pull_record=resolve_http_record(serialized.pull_record_id),
            push_record=resolve_http_record(serialized.push_record_id),
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
            "pull_record_id": self.pull_record.record_id,
            "push_record_id": self.push_record.record_id,
            "codex_session_record": _CodexSessionRecordJson(
                codex_session_id=session_id,
                codex_rollout_record=rollout,
                appendwatch_report_record=report,
            ),
        }

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()


@implements[BackendComponent.CommitRecordProperty]()
class BackendCommitRecord(HttpRequestLogRecord):
    commit_request_body: CommitRequestBody = Field(exclude=True)

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return self

    def validate_commit_record(self) -> Self:
        if (
            self.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            or self.record_id.version != 7
            or self.method != HTTP_POST_METHOD
            or self.scheme != SYNTHETIC_SCHEME
            or self.host != SYNTHETIC_HOST
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
            raise ValueError("commit HTTP record has an invalid contour")
        expected = self.commit_request_body
        parsed = CommitRequestBody.from_serialized_json(
            self.request_body,
            resolve_http_record=lambda record_id: {
                expected.pull_record.record_id: expected.pull_record,
                expected.push_record.record_id: expected.push_record,
            }[record_id],
        )
        if parsed != expected:
            raise ValueError("commit request body does not match its records")
        return self

    @model_validator(mode="after")
    def _validate_commit_record(self) -> Self:
        return self.validate_commit_record()

    @classmethod
    def from_http_request_log_record(
        cls,
        record: HttpRequestLogRecord,
        *,
        resolve_http_record: Callable[[UUID], HttpRequestLogRecord],
    ) -> Self:
        if record.request_body is None:
            raise ValueError("commit request body is missing")
        body = CommitRequestBody.from_serialized_json(
            record.request_body,
            resolve_http_record=resolve_http_record,
        )
        return cls(
            **record.model_dump(),
            commit_request_body=body,
        )


@implements[BackendComponent.PostCommitValidationProperty]()
class PostCommitValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    stage: BackendLifecycle
    result: BackendLifecycle
    detail: StrictStr | None = None

    def validate_lifecycle(self) -> Self:
        if not self.stage.is_post_commit_validation_stage():
            raise ValueError("invalid post-commit validation stage")
        if not self.result.is_post_commit_validation_result():
            raise ValueError("invalid post-commit validation result")
        if (self.stage is BackendLifecycle.ACCEPTED) != (
            self.result is BackendLifecycle.ACCEPTED
        ):
            raise ValueError("accepted validation stage and result must agree")
        return self

    @model_validator(mode="after")
    def _validate_lifecycle(self) -> Self:
        return self.validate_lifecycle()
