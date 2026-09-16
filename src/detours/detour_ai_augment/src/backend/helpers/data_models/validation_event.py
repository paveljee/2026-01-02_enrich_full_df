from __future__ import annotations

from typing import Literal, Self
from uuid import UUID

from pydantic import JsonValue, model_validator

from src.helpers.architecture import FrozenStrictModel
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

from .commit_event import BackendCommitRecord, PostCommitValidation

VALIDATE_PATH = "/validate"


class ValidationRequestBody(FrozenStrictModel):
    commit_id: UUID
    post_commit_validation: PostCommitValidation
    submission_type: Literal["Submission", "StandardizedSubmission"] | None
    submission: dict[str, JsonValue] | None
    http_record_ids: tuple[UUID, ...] = ()

    @model_validator(mode="after")
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

    def http_record(self, commit: BackendCommitRecord) -> HttpRequestLogRecord:
        if self.commit_id != commit.record_id:
            raise ValueError("Validation refers to a different commit")
        return HttpRequestLogRecord(
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
