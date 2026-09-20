from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, JsonValue, StrictStr, model_serializer, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import HTTP_POST_METHOD
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models.http_request_log import HttpRequestLogRecord
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

from ....control_centre.dashboard.helpers.data_models.run_outcome import NAME_KEY_HEADER
from .commit_event import (
    SOURCE_KEY_HEADER,
    SYNTHETIC_HOST,
    SYNTHETIC_SCHEME,
    BackendCommitRecord,
    BackendLifecycle,
)
from .committed_innerdict import _BackendCommitRecordJson

VALIDATE_PATH = "/validate"


@implements[BackendComponent.PostCommitValidationProperty]()
class PostCommitValidation(FrozenStrictModel):
    stage: BackendLifecycle
    result: BackendLifecycle
    detail: StrictStr | None = None
    submission_type: Literal["Submission", "StandardizedSubmission"] | None
    submission: dict[str, JsonValue] | None

    def validate_lifecycle(self) -> Self:
        if not self.stage.is_post_commit_validation_stage():
            raise ValueError(Locale.VALIDATION_STAGE_INVALID)
        if not self.result.is_post_commit_validation_result():
            raise ValueError(Locale.VALIDATION_RESULT_INVALID)
        if (self.stage is BackendLifecycle.ACCEPTED) != (
            self.result is BackendLifecycle.ACCEPTED
        ):
            raise ValueError(Locale.VALIDATION_ACCEPTANCE_MISMATCH)
        if (self.submission_type is None) != (self.submission is None):
            raise ValueError(Locale.VALIDATION_SUBMISSION_TYPE_MISMATCH)
        if self.result is BackendLifecycle.ACCEPTED and self.submission is None:
            raise ValueError(Locale.VALIDATION_SUBMISSION_MISSING)
        return self

    @model_validator(mode="after")
    def _validate_lifecycle(self) -> Self:
        return self.validate_lifecycle()


class _ValidationRequestBodyJson(FrozenStrictModel):
    commit_record: _BackendCommitRecordJson
    post_commit_validation: PostCommitValidation
    initial_validation_record: HttpRequestLogRecord | None
    openalex_ror_records: tuple[HttpRequestLogRecord, ...] = ()


@implements[BackendComponent.ValidationRequestBodyProperty]()
class ValidationRequestBody(FrozenStrictModel):
    commit_record: BackendCommitRecord
    post_commit_validation: PostCommitValidation
    initial_validation_record: BackendValidationRecord | None
    openalex_ror_records: tuple[HttpRequestLogRecord, ...] = ()

    def validate_body(self) -> Self:
        initial = self.initial_validation_record
        if initial is not None:
            initial_body = initial.validation_request_body
            if (
                initial_body.initial_validation_record is not None
                or initial_body.commit_record.record_id == self.commit_record.record_id
                or initial_body.commit_record.commit_request_body.codex_session_record.session_id
                != self.commit_record.commit_request_body.codex_session_record.session_id
                or initial.request_headers[NAME_KEY_HEADER]
                != self.commit_record.request_headers[NAME_KEY_HEADER]
            ):
                raise ValueError(Locale.VALIDATION_INITIAL_LINK_INVALID)
        ids = tuple(record.record_id for record in self.openalex_ror_records)
        if len(set(ids)) != len(ids) or any(record_id.version != 7 for record_id in ids):
            raise ValueError(Locale.VALIDATION_HTTP_REFERENCES_INVALID)
        return self

    @model_validator(mode="after")
    def _validate_body(self) -> Self:
        return self.validate_body()

    @classmethod
    def from_serialized_json(cls, value: str | bytes) -> Self:
        serialized = _ValidationRequestBodyJson.model_validate_json(value)
        initial = serialized.initial_validation_record
        return cls(
            commit_record=serialized.commit_record.to_commit_record(),
            post_commit_validation=serialized.post_commit_validation,
            initial_validation_record=(
                None if initial is None
                else BackendValidationRecord.from_http_request_log_record(initial)
            ),
            openalex_ror_records=serialized.openalex_ror_records,
        )

    @model_serializer
    def serialize(self) -> dict[str, object]:
        return _ValidationRequestBodyJson(
            commit_record=_BackendCommitRecordJson.from_commit_record(self.commit_record),
            post_commit_validation=self.post_commit_validation,
            initial_validation_record=self.initial_validation_record,
            openalex_ror_records=self.openalex_ror_records,
        ).model_dump(mode="json")

    def http_record(self) -> BackendValidationRecord:
        return BackendValidationRecord(
            validation_request_body=self,
            schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            method=HTTP_POST_METHOD,
            scheme=SYNTHETIC_SCHEME,
            host=SYNTHETIC_HOST,
            port=None,
            path=VALIDATE_PATH,
            query="",
            request_headers=dict(self.commit_record.request_headers),
            request_body=self.model_dump_json(by_alias=True),
            response_code=None,
            response_headers=None,
            response_body=None,
            received_at_unix_usec=None,
            ready_to_respond_at_unix_usec=None,
            duration_usec=None,
        )


@implements[BackendComponent.ValidationRecordProperty]()
class BackendValidationRecord(HttpRequestLogRecord):
    validation_request_body: ValidationRequestBody = Field(exclude=True)

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return self

    def validate_record(self) -> Self:
        if (
            self.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            or self.record_id.version != 7
            or self.method != HTTP_POST_METHOD
            or self.scheme != SYNTHETIC_SCHEME
            or self.host != SYNTHETIC_HOST
            or self.port is not None
            or self.path != VALIDATE_PATH
            or self.query
            or set(self.request_headers) != {SOURCE_KEY_HEADER, NAME_KEY_HEADER}
            or self.request_body is None
            or self.response_code is not None
            or self.response_headers is not None
            or self.response_body is not None
            or self.received_at_unix_usec is not None
            or self.ready_to_respond_at_unix_usec is not None
            or self.duration_usec is not None
        ):
            raise ValueError(Locale.VALIDATION_RECORD_INVALID)
        parsed = ValidationRequestBody.from_serialized_json(self.request_body)
        if (
            parsed != self.validation_request_body
            or self.request_headers != parsed.commit_record.request_headers
            or (parsed.initial_validation_record is not None
                and parsed.initial_validation_record.record_id == self.record_id)
        ):
            raise ValueError(Locale.VALIDATION_BODY_MISMATCH)
        return self

    @model_validator(mode="after")
    def _validate_record(self) -> Self:
        return self.validate_record()

    @classmethod
    def from_http_request_log_record(
        cls,
        record: HttpRequestLogRecord,
    ) -> Self:
        if record.request_body is None:
            raise ValueError(Locale.VALIDATION_BODY_MISSING)
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
            validation_request_body=ValidationRequestBody.from_serialized_json(
                record.request_body,
            ),
        )
