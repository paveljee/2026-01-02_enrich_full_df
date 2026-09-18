from __future__ import annotations

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models.http_request_log import HttpRequestLogRecord
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

from ....control_centre.dashboard.helpers.data_models.run_outcome import NAME_KEY_HEADER
from .commit_event import (
    HTTP_POST_METHOD,
    SOURCE_KEY_HEADER,
    SYNTHETIC_HOST,
    SYNTHETIC_SCHEME,
    BackendCommitRecord,
    PostCommitValidation,
)

VALIDATE_PATH = "/validate"


@implements[BackendComponent.ValidationRequestBodyProperty]()
class ValidationRequestBody(FrozenStrictModel):
    commit_id: UUID
    post_commit_validation: PostCommitValidation
    submission_type: Literal["Submission", "StandardizedSubmission"] | None
    submission: dict[str, JsonValue] | None
    http_record_ids: tuple[UUID, ...] = ()

    def validate_body(self) -> Self:
        if self.commit_id.version != 7:
            raise ValueError("Validation commit ID must be UUIDv7")
        if (self.submission_type is None) != (self.submission is None):
            raise ValueError("Submission type and payload must agree")
        if self.post_commit_validation.result.value == "accepted" and self.submission is None:
            raise ValueError("Accepted validation requires the full submission")
        if len(set(self.http_record_ids)) != len(self.http_record_ids):
            raise ValueError("Model HTTP references must be unique")
        if any(record_id.version != 7 for record_id in self.http_record_ids):
            raise ValueError("Model HTTP references must be UUIDv7")
        return self

    @model_validator(mode="after")
    def _validate_body(self) -> Self:
        return self.validate_body()

    def http_record(self, commit: BackendCommitRecord) -> BackendValidationRecord:
        if self.commit_id != commit.record_id:
            raise ValueError("Validation refers to a different commit")
        return BackendValidationRecord(
            validation_request_body=self,
            schema_version="1.1",
            method="POST",
            scheme="http",
            host="invalid",
            port=None,
            path=VALIDATE_PATH,
            query="",
            request_headers=dict(commit.request_headers),
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
            raise ValueError("validation HTTP record has an invalid contour")
        parsed = ValidationRequestBody.model_validate_json(self.request_body)
        if parsed != self.validation_request_body:
            raise ValueError("validation request body does not match its record")
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
            raise ValueError("validation request body is missing")
        return cls(
            **record.model_dump(),
            validation_request_body=ValidationRequestBody.model_validate_json(
                record.request_body,
            ),
        )
