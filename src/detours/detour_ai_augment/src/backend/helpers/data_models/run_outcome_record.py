from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Self
from uuid import UUID

import requests
from pydantic import Field, model_serializer, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_CONTENT_TYPE_HEADER,
    ContentType,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models import HttpRequestLogRecord

from ....control_centre.dashboard.helpers.data_models.run_outcome import (
    RunLifecycle,
    RunOutcomeRequest,
)
from .commit_event import (
    SOURCE_KEY_HEADER,
    CodexSessionRecord,
    _CodexSessionRecordJson,
    source_key_from_header_value,
    source_key_header_value,
)


class _RunOutcomeResponseBodyJson(FrozenStrictModel):
    pull_record_id: UUID | None
    push_record_id: UUID | None
    commit_record_id: UUID | None
    validation_record_id: UUID | None
    run_outcome_record_id: UUID
    codex_session_record: _CodexSessionRecordJson


@implements[BackendComponent.RunOutcomeResponseBodyProperty]()
class RunOutcomeResponseBody(FrozenStrictModel):
    pull_record_id: UUID | None
    push_record_id: UUID | None
    commit_record_id: UUID | None
    validation_record_id: UUID | None
    run_outcome_record_id: UUID
    codex_session_record: CodexSessionRecord

    @classmethod
    def from_serialized_json(cls, value: str | bytes) -> Self:
        serialized = _RunOutcomeResponseBodyJson.model_validate_json(value)
        session = serialized.codex_session_record
        return cls(
            pull_record_id=serialized.pull_record_id,
            push_record_id=serialized.push_record_id,
            commit_record_id=serialized.commit_record_id,
            validation_record_id=serialized.validation_record_id,
            run_outcome_record_id=serialized.run_outcome_record_id,
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
            "commit_record_id": self.commit_record_id,
            "validation_record_id": self.validation_record_id,
            "run_outcome_record_id": self.run_outcome_record_id,
            "codex_session_record": _CodexSessionRecordJson(
                codex_session_id=session.session_id,
                codex_rollout_record=session.codex_rollout_record,
                appendwatch_report_record=session.appendwatch_report_record,
            ),
        }

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()


@implements[BackendComponent.RunOutcomeResponseRecordProperty]()
class RunOutcomeResponseRecord(HttpRequestLogRecord):
    run_outcome_request: RunOutcomeRequest = Field(exclude=True)
    run_outcome_response_body: RunOutcomeResponseBody = Field(exclude=True)

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return self

    @property
    def run_outcome(self) -> RunLifecycle:
        return self.run_outcome_request.run_outcome

    @classmethod
    def from_run_outcome_request(
        cls,
        request: RunOutcomeRequest,
        *,
        response_code: HTTPStatus,
        response_headers: Mapping[str, str] | None,
        response_body: RunOutcomeResponseBody,
        ready_to_respond_at_unix_usec: int,
    ) -> Self:
        request_record = request.http_request_log_record
        received_at_unix_usec = request_record.received_at_unix_usec
        if received_at_unix_usec is None:
            raise ValueError("run-outcome HTTP request receipt time is missing")
        return cls(
            schema_version=request_record.schema_version,
            record_id=request_record.record_id,
            method=request_record.method,
            scheme=request_record.scheme,
            host=request_record.host,
            port=request_record.port,
            path=request_record.path,
            query=request_record.query,
            request_headers=request_record.request_headers,
            request_body=request_record.request_body,
            response_code=response_code,
            response_headers=None if response_headers is None else dict(response_headers),
            response_body=response_body.model_dump_json(),
            received_at_unix_usec=received_at_unix_usec,
            ready_to_respond_at_unix_usec=ready_to_respond_at_unix_usec,
            duration_usec=ready_to_respond_at_unix_usec - received_at_unix_usec,
            run_outcome_request=request,
            run_outcome_response_body=response_body,
        )

    def validate_record(self) -> Self:
        projected_request_record = HttpRequestLogRecord(
            schema_version=self.schema_version,
            record_id=self.record_id,
            method=self.method,
            scheme=self.scheme,
            host=self.host,
            port=self.port,
            path=self.path,
            query=self.query,
            request_headers=self.request_headers,
            request_body=self.request_body,
            response_code=None,
            response_headers=None,
            response_body=None,
            received_at_unix_usec=self.received_at_unix_usec,
            ready_to_respond_at_unix_usec=None,
            duration_usec=None,
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
                raise ValueError("run-outcome SourceKey response header is missing")
            filename, line_count = source_key_from_header_value(
                self.response_headers.get(SOURCE_KEY_HEADER)
            )
            if line_count != rollout.line_count:
                raise ValueError("run-outcome SourceKey line count is inconsistent")
            expected_response_headers = {
                SOURCE_KEY_HEADER: source_key_header_value(filename, line_count)
            }
        received_at_unix_usec = self.received_at_unix_usec
        ready_to_respond_at_unix_usec = self.ready_to_respond_at_unix_usec
        if (
            projected_request_record != self.run_outcome_request.http_request_log_record
            or self.response_code not in {
                HTTPStatus.OK, HTTPStatus.BAD_REQUEST, HTTPStatus.CONFLICT,
                HTTPStatus.INTERNAL_SERVER_ERROR,
            }
            or self.response_body is None
            or ready_to_respond_at_unix_usec is None
            or received_at_unix_usec is None
            or self.duration_usec is None
            or self.duration_usec < 0
            or self.duration_usec != ready_to_respond_at_unix_usec - received_at_unix_usec
            or self.response_headers != expected_response_headers
            or (
                self.response_code != HTTPStatus.BAD_REQUEST
                and (self.response_code in {HTTPStatus.OK, HTTPStatus.CONFLICT})
                is not complete_capture
            )
        ):
            raise ValueError("run-outcome HTTP record has an invalid contour")
        parsed = RunOutcomeResponseBody.from_serialized_json(self.response_body)
        if parsed.run_outcome_record_id != self.record_id:
            raise ValueError(Locale.RUN_OUTCOME_SELF_ID_INCONSISTENT)
        if (
            self.response_code != HTTPStatus.BAD_REQUEST
            and parsed.validation_record_id is not None and parsed.commit_record_id is None
        ):
            raise ValueError(Locale.RUN_OUTCOME_VALIDATION_COMMIT_REQUIRED)
        if any(
            value is not None and value.version != 7
            for value in (
                parsed.commit_record_id,
                parsed.validation_record_id,
                parsed.run_outcome_record_id,
            )
        ):
            raise ValueError(Locale.RUN_OUTCOME_REFERENCE_UUID_INVALID)
        if parsed != self.run_outcome_response_body:
            raise ValueError("run-outcome response body does not match its record")
        return self

    def to_response(self) -> requests.Response:
        # Absence of SourceKey is intentional for an incomplete outcome capture.
        # Adapt only at this transport boundary; do not alter the durable record.
        response_headers = dict(self.response_headers or {})
        response_headers[HTTP_CONTENT_TYPE_HEADER] = ContentType.JSON
        record = HttpRequestLogRecord(
            schema_version=self.schema_version,
            record_id=self.record_id,
            method=self.method,
            scheme=self.scheme,
            host=self.host,
            port=self.port,
            path=self.path,
            query=self.query,
            request_headers=self.request_headers,
            request_body=self.request_body,
            response_code=self.response_code,
            response_headers=response_headers,
            response_body=self.response_body,
            received_at_unix_usec=self.received_at_unix_usec,
            ready_to_respond_at_unix_usec=self.ready_to_respond_at_unix_usec,
            duration_usec=self.duration_usec,
        )
        return record.to_response()

    @model_validator(mode="after")
    def _validate_run_outcome_record(self) -> Self:
        return self.validate_record()

    @classmethod
    def from_http_request_log_record(
        cls,
        record: HttpRequestLogRecord,
    ) -> Self:
        if record.response_body is None:
            raise ValueError("run-outcome HTTP record is incomplete")
        request_record = HttpRequestLogRecord(
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
            response_code=None,
            response_headers=None,
            response_body=None,
            received_at_unix_usec=record.received_at_unix_usec,
            ready_to_respond_at_unix_usec=None,
            duration_usec=None,
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
            run_outcome_request=(
                RunOutcomeRequest.from_http_request_log_record(request_record)
            ),
            run_outcome_response_body=(
                RunOutcomeResponseBody.from_serialized_json(record.response_body)
            ),
        )
