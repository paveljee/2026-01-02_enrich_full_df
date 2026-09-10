from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable, Mapping
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    model_serializer,
    model_validator,
)

from src.helpers.data_models import FragmentType, HttpRequestLogRecord, InnerDict, NameKey
from src.helpers.vars import (
    KTP_FILENAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
    KTP_NAMEKEY_COL,
)

from ....architecture import (
    AgentRuntimeComponent,
    BackendComponent,
    implements,
)
from ....control_centre.dashboard.helpers.data_models.run_outcome import (
    NAME_KEY_HEADER,
    RunOutcome,
    RunOutcomeRequest,
)
from ..vars import (
    KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL,
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
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


@implements[BackendComponent.PostCommitValidationStageProperty]()
class PostCommitValidationStage(StrEnum):
    value: Literal[
        "transport",
        "configuration",
        "rollout_copy",
        "appendwatch_report_copy",
        "appendwatch_report_validation",
        "rollout_index",
        "pydantic_validation",
        "duckdb_evidence_validation",
        "researcher_resolution",
        "innerdict_and_card",
        "accepted",
    ]

    TRANSPORT = "transport"
    CONFIGURATION = "configuration"
    ROLLOUT_COPY = "rollout_copy"
    APPENDWATCH_REPORT_COPY = "appendwatch_report_copy"
    APPENDWATCH_REPORT_VALIDATION = "appendwatch_report_validation"
    ROLLOUT_INDEX = "rollout_index"
    PYDANTIC_VALIDATION = "pydantic_validation"
    DUCKDB_EVIDENCE_VALIDATION = "duckdb_evidence_validation"
    RESEARCHER_RESOLUTION = "researcher_resolution"
    INNERDICT_AND_CARD = "innerdict_and_card"
    ACCEPTED = "accepted"


@implements[BackendComponent.PostCommitValidationResultProperty]()
class PostCommitValidationResult(StrEnum):
    value: Literal[
        "accepted",
        "configuration_error",
        "rejected",
    ]

    ACCEPTED = "accepted"
    CONFIGURATION_ERROR = "configuration_error"
    REJECTED = "rejected"


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
    def record_ids_from_serialized_json(cls, value: str) -> tuple[UUID, UUID]:
        serialized = _CommitRequestBodyJson.model_validate_json(value)
        return serialized.pull_record_id, serialized.push_record_id

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
    pull_record: HttpRequestLogRecord = Field(exclude=True)
    push_record: HttpRequestLogRecord = Field(exclude=True)
    codex_session_record: CodexSessionRecord = Field(exclude=True)

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
        expected = CommitRequestBody(
            pull_record=self.pull_record,
            push_record=self.push_record,
            codex_session_record=self.codex_session_record,
        )
        parsed = CommitRequestBody.from_serialized_json(
            self.request_body,
            resolve_http_record=lambda record_id: {
                self.pull_record.record_id: self.pull_record,
                self.push_record.record_id: self.push_record,
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
            pull_record=body.pull_record,
            push_record=body.push_record,
            codex_session_record=body.codex_session_record,
        )


@implements[BackendComponent.PostCommitValidationProperty]()
class PostCommitValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    stage: PostCommitValidationStage
    result: PostCommitValidationResult
    detail: StrictStr | None = None


class PreparedPullResponse(BaseModel):
    """Post-commit result retained to serve the next authoritative pull."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    commit_record_id: UUID
    post_commit_validation: PostCommitValidation
    response_code: int
    response_headers: dict[StrictStr, StrictStr]
    response_body: StrictStr


@implements[AgentRuntimeComponent.AttemptProperty]()
class AgentRuntimeAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pull_record: HttpRequestLogRecord
    commit_record: BackendCommitRecord
    post_commit_validation: PostCommitValidation


@implements[BackendComponent.ControlCentrePort.AcceptedInnerDictSummaryProperty]()
class AcceptedInnerDictSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    innerdict: InnerDict

    def text(self, column: str) -> str | None:
        value = self.innerdict.data.get(column)
        if value is not None and not isinstance(value, str):
            raise ValueError("accepted innerdict text value is invalid")
        return value

    def _required_text(self, column: str) -> str:
        value = self.text(column)
        if value is None:
            raise ValueError("accepted innerdict required text value is missing")
        return value

    @property
    def namekey(self) -> NameKey:
        serialized = self._required_text(KTP_NAMEKEY_COL)
        namekey = NameKey.from_json_key(serialized)
        if namekey.to_json_key() != serialized:
            raise ValueError("accepted innerdict namekey is not canonical")
        return namekey

    @property
    def commit_record_id(self) -> UUID:
        return UUID(self._required_text(KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL))

    @property
    def codex_session_id(self) -> UUID:
        summary = CodexRolloutRecord.parse_summary_json(
            self._required_text(KTP_AI_AUGMENT_SESSION_METADATA_COL)
        )
        return UUID(summary["session_id"])

    def validate_accepted_innerdict(self) -> Self:
        self.namekey
        self.commit_record_id
        self.codex_session_id
        return self

    @model_validator(mode="after")
    def _validate_accepted_innerdict(self) -> Self:
        return self.validate_accepted_innerdict()

    @classmethod
    def from_innerdict(cls, innerdict: InnerDict) -> Self:
        return cls(innerdict=innerdict)


class _RunOutcomeResponseBodyJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pull_record_id: UUID | None
    push_record_id: UUID | None
    codex_session_record: _CodexSessionRecordJson


@implements[BackendComponent.ControlCentrePort.RunOutcomeResponseBodyProperty]()
class RunOutcomeResponseBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pull_record_id: UUID | None
    push_record_id: UUID | None
    codex_session_record: CodexSessionRecord

    @classmethod
    def from_serialized_json(cls, value: str | bytes) -> Self:
        serialized = _RunOutcomeResponseBodyJson.model_validate_json(value)
        session = serialized.codex_session_record
        return cls(
            pull_record_id=serialized.pull_record_id,
            push_record_id=serialized.push_record_id,
            codex_session_record=CodexSessionRecord(
                session_id=session.codex_session_id,
                codex_rollout_record=session.codex_rollout_record,
                appendwatch_report_record=session.appendwatch_report_record,
            ),
        )

    def serialize(self) -> dict[str, object]:
        session = self.codex_session_record
        return {
            "pull_record_id": self.pull_record_id,
            "push_record_id": self.push_record_id,
            "codex_session_record": _CodexSessionRecordJson(
                codex_session_id=session.session_id,
                codex_rollout_record=session.codex_rollout_record,
                appendwatch_report_record=session.appendwatch_report_record,
            ),
        }

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()


@implements[BackendComponent.ControlCentrePort.RunOutcomeResponseProperty]()
class RunOutcomeResponse(HttpRequestLogRecord):
    run_outcome_request: RunOutcomeRequest = Field(exclude=True)
    run_outcome_response_body: RunOutcomeResponseBody = Field(exclude=True)

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return HttpRequestLogRecord.model_validate(self.model_dump())

    @property
    def run_outcome(self) -> RunOutcome:
        return self.run_outcome_request.run_outcome

    @classmethod
    def from_run_outcome_request(
        cls,
        request: RunOutcomeRequest,
        *,
        response_code: int,
        response_headers: Mapping[str, str] | None,
        response_body: RunOutcomeResponseBody,
        ready_to_respond_at_unix_usec: int,
    ) -> Self:
        request_record = request.http_request_log_record
        received_at_unix_usec = request_record.received_at_unix_usec
        if received_at_unix_usec is None:
            raise ValueError("run-outcome HTTP request receipt time is missing")
        return cls.model_validate(
            request_record.model_dump()
            | {
                "ready_to_respond_at_unix_usec": ready_to_respond_at_unix_usec,
                "response_code": response_code,
                "response_headers": (
                    None if response_headers is None else dict(response_headers)
                ),
                "response_body": response_body.model_dump_json(),
                "duration_usec": (
                    ready_to_respond_at_unix_usec - received_at_unix_usec
                ),
                "run_outcome_request": request,
                "run_outcome_response_body": response_body,
            }
        )

    def validate_run_outcome_response(self) -> Self:
        projected_request_record = HttpRequestLogRecord.model_validate(
            self.model_dump()
            | {
                "ready_to_respond_at_unix_usec": None,
                "response_code": None,
                "response_headers": None,
                "response_body": None,
                "duration_usec": None,
            }
        )
        session = self.run_outcome_response_body.codex_session_record
        rollout = session.codex_rollout_record
        report = session.appendwatch_report_record
        complete_capture = (
            session.session_id is not None
            and rollout is not None
            and report is not None
        )
        if rollout is None:
            expected_response_headers = None
        else:
            if self.response_headers is None:
                raise ValueError("run-outcome Source-Key response header is missing")
            filename, line_count = source_key_from_header_value(
                self.response_headers.get(SOURCE_KEY_HEADER)
            )
            if line_count != rollout.line_count:
                raise ValueError("run-outcome Source-Key line count is inconsistent")
            expected_response_headers = {
                SOURCE_KEY_HEADER: source_key_header_value(filename, line_count)
            }
        received_at_unix_usec = self.received_at_unix_usec
        ready_to_respond_at_unix_usec = self.ready_to_respond_at_unix_usec
        if (
            projected_request_record
            != self.run_outcome_request.http_request_log_record
            or self.response_code not in {200, 500}
            or self.response_body is None
            or ready_to_respond_at_unix_usec is None
            or received_at_unix_usec is None
            or self.duration_usec is None
            or self.duration_usec < 0
            or self.duration_usec
            != ready_to_respond_at_unix_usec - received_at_unix_usec
            or self.response_headers != expected_response_headers
            or (self.response_code == 200) is not complete_capture
        ):
            raise ValueError("run-outcome HTTP record has an invalid contour")
        parsed = RunOutcomeResponseBody.from_serialized_json(self.response_body)
        if parsed != self.run_outcome_response_body:
            raise ValueError("run-outcome response body does not match its record")
        return self

    @model_validator(mode="after")
    def _validate_run_outcome_response(self) -> Self:
        return self.validate_run_outcome_response()

    @classmethod
    def from_http_request_log_record(
        cls,
        record: HttpRequestLogRecord,
    ) -> Self:
        if record.response_body is None:
            raise ValueError("run-outcome HTTP record is incomplete")
        request_record = HttpRequestLogRecord.model_validate(
            record.model_dump()
            | {
                "ready_to_respond_at_unix_usec": None,
                "response_code": None,
                "response_headers": None,
                "response_body": None,
                "duration_usec": None,
            }
        )
        return cls(
            **record.model_dump(),
            run_outcome_request=(
                RunOutcomeRequest.from_http_request_log_record(request_record)
            ),
            run_outcome_response_body=(
                RunOutcomeResponseBody.from_serialized_json(record.response_body)
            ),
        )


@implements[BackendComponent.ControlCentrePort.QueryResponseProperty]()
class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    attempts: tuple[AgentRuntimeAttempt, ...]
    accepted_innerdict_summaries: tuple[AcceptedInnerDictSummary, ...]
    run_outcome_records: tuple[RunOutcomeResponse, ...] = ()
    card_markdown: StrictStr | None = None

    @classmethod
    def from_serialized_json(cls, value: str | bytes) -> Self:
        serialized = _QueryResponseJson.model_validate_json(value)
        attempts: list[AgentRuntimeAttempt] = []
        for attempt in serialized.attempts:
            commit = attempt.commit_record
            commit_record = BackendCommitRecord(
                **commit.http_record.model_dump(),
                pull_record=commit.pull_record,
                push_record=commit.push_record,
                codex_session_record=commit.codex_session_record,
            )
            attempts.append(
                AgentRuntimeAttempt(
                    pull_record=attempt.pull_record,
                    commit_record=commit_record,
                    post_commit_validation=attempt.post_commit_validation,
                )
            )
        return cls(
            attempts=tuple(attempts),
            accepted_innerdict_summaries=tuple(
                AcceptedInnerDictSummary.from_innerdict(
                    InnerDict.from_mapping(
                        innerdict,
                        _CodexInnerDictProcedure(),
                    )
                )
                for innerdict in serialized.accepted_innerdict_summaries
            ),
            run_outcome_records=tuple(
                RunOutcomeResponse.from_http_request_log_record(record)
                for record in serialized.run_outcome_records
            ),
            card_markdown=serialized.card_markdown,
        )

    def serialize(self) -> dict[str, object]:
        return {
            "attempts": tuple(
                _AgentRuntimeAttemptJson(
                    pull_record=attempt.pull_record,
                    commit_record=_BackendCommitRecordJson(
                        http_record=HttpRequestLogRecord.model_validate(
                            attempt.commit_record.model_dump()
                        ),
                        pull_record=attempt.commit_record.pull_record,
                        push_record=attempt.commit_record.push_record,
                        codex_session_record=(attempt.commit_record.codex_session_record),
                    ),
                    post_commit_validation=attempt.post_commit_validation,
                )
                for attempt in self.attempts
            ),
            "accepted_innerdict_summaries": tuple(
                accepted.innerdict.data
                for accepted in self.accepted_innerdict_summaries
            ),
            "run_outcome_records": tuple(
                record.http_request_log_record
                for record in self.run_outcome_records
            ),
            "card_markdown": self.card_markdown,
        }

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()


class _BackendCommitRecordJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    http_record: HttpRequestLogRecord
    pull_record: HttpRequestLogRecord
    push_record: HttpRequestLogRecord
    codex_session_record: CodexSessionRecord


class _AgentRuntimeAttemptJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pull_record: HttpRequestLogRecord
    commit_record: _BackendCommitRecordJson
    post_commit_validation: PostCommitValidation


class _CodexInnerDictProcedure:
    dataset_id_field = KTP_NAMEKEY_COL


class _QueryResponseJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    attempts: tuple[_AgentRuntimeAttemptJson, ...]
    accepted_innerdict_summaries: tuple[dict[str, object], ...]
    run_outcome_records: tuple[HttpRequestLogRecord, ...] = ()
    card_markdown: StrictStr | None = None
