from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus
from typing import Literal, Self
from uuid import UUID

import requests
from pydantic import Field, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import (
    ControlCentreComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ETAG_HEADER,
    HTTP_CONTENT_LENGTH_HEADER,
    HTTP_CONTENT_TYPE_HEADER,
    HTTP_POST_METHOD,
    SESSION_ID_HEADER,
    SOURCE_KEY_HEADER,
    SYNTHETIC_COMMIT_HOST,
    SYNTHETIC_COMMIT_SCHEME,
    TEXT_ENCODING,
    ContentType,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    NAME_KEY_HEADER as NAME_KEY_HEADER,
)
from src.detours.detour_ai_augment.protected.src.shared import (
    name_key_from_header_value,
    source_key_from_header_value,
    source_key_header_value,
)
from src.detours.detour_ai_augment.protected.src.shared import (
    name_key_header_value as name_key_header_value,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models import HttpRequestLogRecord, NameKey
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

from .....agent_runtime.helpers.data_models.attempt import AgentRuntimeAttempt
from .....backend.helpers.data_models.ai_augment_http_request_log_record import (
    RequestRecord,
    ResponseRecord,
)
from .....backend.helpers.data_models.commit_request import (
    CodexSessionRecord,
    _CodexSessionRecordJson,
)
from .lifecycle import RunLifecycle


@implements[ControlCentreComponent.BackendPort.RunOutcomeProperty]()
class RunOutcome(StrEnum):
    value: Literal["completed", "failed", "cancelled"]

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def from_url_path(cls, url_path: str) -> Self:
        try:
            return cls(url_path.removeprefix("/")) if url_path.startswith("/") else cls("")
        except ValueError as exc:
            raise ValueError(Locale.RUN_OUTCOME_REQUEST_PATH_INVALID) from exc

    @property
    def to_url_path(self) -> Literal["/completed", "/failed", "/cancelled"]:
        if self is RunOutcome.COMPLETED:
            return "/completed"
        if self is RunOutcome.FAILED:
            return "/failed"
        return "/cancelled"


class RunOutcomePath(StrEnum):
    value: Literal["/completed", "/failed", "/cancelled"]

    COMPLETED = "/completed"
    FAILED = "/failed"
    CANCELLED = "/cancelled"


COMPLETED_PATH = RunOutcomePath.COMPLETED
FAILED_PATH = RunOutcomePath.FAILED
CANCELLED_PATH = RunOutcomePath.CANCELLED
RUN_OUTCOME_PATHS: frozenset[RunOutcomePath] = frozenset(RunOutcomePath)


def _http_header_value(
    headers: Mapping[str, str],
    name: str,
) -> str | None:
    normalized_name = name.casefold()
    for key, value in headers.items():
        if key.casefold() == normalized_name:
            return value
    return None


def _request_uuid(value: str | None, *, quoted: bool = False) -> UUID | None:
    if value is None:
        return None
    if quoted:
        if len(value) < 2 or value[0] != '"' or value[-1] != '"':
            return None
        value = value[1:-1]
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return parsed if parsed.version == 7 and str(parsed) == value else None


@implements[ControlCentreComponent.BackendPort.RunOutcomeRequestRecordProperty]()
class RunOutcomeRequestRecord(RequestRecord):
    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return super().http_request_log_record

    @classmethod
    def from_http_request_log_record(
        cls, *, http_request_log_record: HttpRequestLogRecord,
    ) -> Self:
        return super().from_http_request_log_record(
            http_request_log_record=http_request_log_record,
        )

    @classmethod
    def from_serialized_json(cls, *, value: str) -> Self:
        return super().from_serialized_json(value=value)

    def serialize(self) -> dict[str, object]:
        return super().serialize()

    @property
    def namekey(self) -> NameKey | None:
        try:
            return name_key_from_header_value(
                _http_header_value(self.request_headers, NAME_KEY_HEADER)
            )
        except ValueError:
            return None

    @property
    def session_id(self) -> UUID | None:
        return _request_uuid(_http_header_value(self.request_headers, SESSION_ID_HEADER))

    @property
    def validation_request_record_id(self) -> UUID | None:
        return _request_uuid(
            _http_header_value(self.request_headers, ETAG_HEADER), quoted=True
        )

    @property
    def run_outcome(self) -> RunOutcome:
        return RunOutcome.from_url_path(self.path)

    @classmethod
    def outbound_http(
        cls,
        *,
        run_outcome: RunLifecycle,
        namekey: NameKey,
        session_id: UUID | None,
        validation_record_id: UUID | None,
    ) -> tuple[
        RunOutcomePath,
        Mapping[str, str],
    ]:
        headers = {NAME_KEY_HEADER: name_key_header_value(namekey)}
        if session_id is not None:
            headers[SESSION_ID_HEADER] = str(session_id)
        if run_outcome is RunLifecycle.COMPLETED and validation_record_id is not None:
            headers[ETAG_HEADER] = f'"{validation_record_id}"'
        return run_outcome.to_run_outcome_path(), headers

    def validate_http_request_log_record(self) -> Self:
        record = self.http_request_log_record
        if (
            record.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            or record.record_id.version != 7
            or record.method != HTTP_POST_METHOD
            or record.scheme != SYNTHETIC_COMMIT_SCHEME
            or record.host != SYNTHETIC_COMMIT_HOST
            or record.port is not None
            or record.ready_to_respond_at_unix_usec is not None
            or record.path not in RUN_OUTCOME_PATHS
            or record.response_code is not None
            or record.response_headers is not None
            or record.response_body is not None
            or record.received_at_unix_usec is None
            or record.duration_usec != 0
        ):
            raise ValueError(Locale.RUN_OUTCOME_REQUEST_CONTOUR_INVALID)
        return self

    @model_validator(mode="after")
    def _validate_http_request_log_record(self) -> Self:
        return self.validate_http_request_log_record()


class _RunOutcomeResponseBodyJson(FrozenStrictModel):
    pull_record_id: UUID | None
    push_record_id: UUID | None
    commit_request_record_id: UUID | None
    validation_record_id: UUID | None
    run_outcome_record_id: UUID
    codex_session_record: _CodexSessionRecordJson


@implements[ControlCentreComponent.BackendPort.RunOutcomeResponseRecordProperty]()
class RunOutcomeResponseRecord(ResponseRecord):
    run_outcome_request_record: RunOutcomeRequestRecord = Field(exclude=True)
    attempt: AgentRuntimeAttempt | None = Field(default=None, exclude=True)

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return super().http_request_log_record

    @classmethod
    def _parse_response_body(cls, value: str | bytes) -> _RunOutcomeResponseBodyJson:
        return _RunOutcomeResponseBodyJson.model_validate_json(value)

    def _body(self) -> _RunOutcomeResponseBodyJson:
        if self.response_body is None:
            raise ValueError(Locale.RUN_OUTCOME_RECORD_INCOMPLETE)
        return self._parse_response_body(self.response_body)

    def _codex_session_record(self) -> CodexSessionRecord:
        session = self._body().codex_session_record
        return CodexSessionRecord(
            session_id=session.codex_session_id,
            codex_rollout_record=session.codex_rollout_record,
            appendwatch_report_record=session.appendwatch_report_record,
        )

    @property
    def run_outcome(self) -> RunLifecycle:
        return RunLifecycle.from_run_outcome(self.run_outcome_request_record.run_outcome)

    @classmethod
    def from_serialized_json(
        cls, *, value: str, attempt: AgentRuntimeAttempt | None = None,
    ) -> Self:
        outcome = cls.from_http_request_log_record(
            HttpRequestLogRecord.model_validate_json(value),
            attempt=attempt,
        )
        if outcome._body().validation_record_id != (
            None if attempt is None else attempt.record_id
        ):
            raise ValueError(Locale.RUN_OUTCOME_ATTEMPT_LINK_INVALID)
        return outcome

    def serialize(self) -> dict[str, object]:
        return self.http_request_log_record.model_dump(mode="json")

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
            received_at_unix_usec=(
                self.ready_to_respond_at_unix_usec - self.duration_usec
                if self.ready_to_respond_at_unix_usec is not None
                and self.duration_usec is not None else None
            ),
            ready_to_respond_at_unix_usec=None,
            duration_usec=0,
        )
        session = self._codex_session_record()
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
                raise ValueError(Locale.RUN_OUTCOME_SOURCE_KEY_MISSING)
            filename, line_count = source_key_from_header_value(
                _http_header_value(self.response_headers, SOURCE_KEY_HEADER)
            )
            if line_count != rollout.line_count:
                raise ValueError(Locale.RUN_OUTCOME_SOURCE_KEY_LINE_COUNT_INVALID)
            expected_response_headers = {
                SOURCE_KEY_HEADER: source_key_header_value(filename, line_count)
            }
        received_at_unix_usec = self.received_at_unix_usec
        ready_to_respond_at_unix_usec = self.ready_to_respond_at_unix_usec
        if (
            projected_request_record.model_dump(mode="json", exclude={"record_id"})
            != self.run_outcome_request_record.model_dump(mode="json", exclude={"record_id"})
            or self.response_code not in {
                HTTPStatus.OK, HTTPStatus.BAD_REQUEST, HTTPStatus.CONFLICT,
                HTTPStatus.INTERNAL_SERVER_ERROR,
            }
            or self.response_body is None
            or ready_to_respond_at_unix_usec is None
            or received_at_unix_usec is not None
            or self.duration_usec is None
            or self.duration_usec < 0
            or self.response_headers is None
            or _http_header_value(self.response_headers, HTTP_CONTENT_TYPE_HEADER)
            != ContentType.JSON
            or _http_header_value(self.response_headers, HTTP_CONTENT_LENGTH_HEADER)
            != str(len(self.response_body.encode(TEXT_ENCODING)))
            or {
                key.casefold() for key in self.response_headers
            } != {
                HTTP_CONTENT_TYPE_HEADER.casefold(), "content-length",
                *({SOURCE_KEY_HEADER.casefold()} if expected_response_headers else set()),
            }
            or (
                expected_response_headers is not None
                and _http_header_value(self.response_headers, SOURCE_KEY_HEADER)
                != expected_response_headers[SOURCE_KEY_HEADER]
            )
            or (
                self.response_code != HTTPStatus.BAD_REQUEST
                and (self.response_code in {HTTPStatus.OK, HTTPStatus.CONFLICT})
                is not complete_capture
            )
        ):
            raise ValueError(Locale.RUN_OUTCOME_RECORD_CONTOUR_INVALID)
        parsed = self._body()
        if self.attempt is not None and (
            parsed.validation_record_id != self.attempt.record_id
            or parsed.commit_request_record_id
            != self.attempt.validation_request_body.commit_request_record.record_id
        ):
            raise ValueError(Locale.RUN_OUTCOME_ATTEMPT_LINK_INVALID)
        if parsed.run_outcome_record_id != self.record_id:
            raise ValueError(Locale.RUN_OUTCOME_SELF_ID_INCONSISTENT)
        if (
            self.response_code != HTTPStatus.BAD_REQUEST
            and parsed.validation_record_id is not None and parsed.commit_request_record_id is None
        ):
            raise ValueError(Locale.RUN_OUTCOME_VALIDATION_COMMIT_REQUIRED)
        if any(
            value is not None and value.version != 7
            for value in (
                parsed.commit_request_record_id,
                parsed.validation_record_id,
                parsed.run_outcome_record_id,
            )
        ):
            raise ValueError(Locale.RUN_OUTCOME_REFERENCE_UUID_INVALID)
        return self

    def to_response(self) -> requests.Response:
        # Absence of SourceKey is intentional for an incomplete outcome capture.
        # Adapt only at this transport boundary; do not alter the durable record.
        return super().to_response()

    @model_validator(mode="after")
    def _validate_run_outcome_record(self) -> Self:
        return self.validate_record()

    @classmethod
    def from_http_request_log_record(
        cls,
        http_request_log_record: HttpRequestLogRecord,
        *,
        attempt: AgentRuntimeAttempt | None = None,
    ) -> Self:
        record = http_request_log_record
        if (record.response_body is None or record.ready_to_respond_at_unix_usec is None
                or record.duration_usec is None):
            raise ValueError(Locale.RUN_OUTCOME_RECORD_INCOMPLETE)
        request_record = HttpRequestLogRecord(
            schema_version=record.schema_version,
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
            received_at_unix_usec=(
                record.ready_to_respond_at_unix_usec - record.duration_usec
            ),
            ready_to_respond_at_unix_usec=None,
            duration_usec=0,
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
            run_outcome_request_record=RunOutcomeRequestRecord.from_http_request_log_record(
                http_request_log_record=request_record,
            ),
            attempt=attempt,
        )
