from __future__ import annotations

from collections.abc import Mapping
from typing import Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_serializer,
    model_validator,
)

from src.helpers.architecture import implements
from src.helpers.data_models import HttpRequestLogRecord

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from ....control_centre.dashboard.helpers.data_models.run_outcome import (
    RunOutcome,
    RunOutcomeRequest,
)
from .commit_event import (
    SOURCE_KEY_HEADER,
    CodexSessionRecord,
    _CodexSessionRecordJson,
    source_key_from_header_value,
    source_key_header_value,
)

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
