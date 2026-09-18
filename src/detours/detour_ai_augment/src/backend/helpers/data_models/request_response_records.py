from __future__ import annotations

from http import HTTPStatus
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.helpers.architecture import implements
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
)

from .commit_event import BackendCommitRecord, CodexSessionRecord
from .query_response import QueryResponse
from .validation_event import BackendValidationRecord


def _validate_public_exchange(record: HttpRequestLogRecord, method: str, path: str) -> None:
    if (
        record.schema_version != "1.1"
        or record.record_id.version != 7
        or (record.method, record.path) != (method, path)
        or record.response_code is None
        or record.response_headers is None
        or record.response_body is None
        or record.ready_to_respond_at_unix_usec is None
        or record.duration_usec is None
    ):
        raise ValueError(Locale.PUBLIC_HTTP_EXCHANGE_INVALID)


@implements[BackendComponent.RequestRecordProperty]()
@implements[BackendComponent.PullRequestRecordProperty]()
class PullRequestRecord(HttpRequestLogRecord):
    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, "GET", "/pull")
        return self


@implements[BackendComponent.ResponseRecordProperty]()
@implements[BackendComponent.PullResponseRecordProperty]()
class PullResponseRecord(HttpRequestLogRecord):
    @property
    def pull_response_body(self) -> str:
        if self.response_body is None:
            raise ValueError(Locale.PULL_RESPONSE_BODY_MISSING)
        return self.response_body

    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, "GET", "/pull")
        return self


@implements[BackendComponent.PushRequestRecordProperty]()
class PushRequestRecord(HttpRequestLogRecord):
    pull_record_id: UUID | None = Field(exclude=True)
    session_id: UUID | None = Field(exclude=True)

    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, "POST", "/push")
        if self.response_code == HTTPStatus.ACCEPTED and (
            self.pull_record_id is None or self.session_id is None
        ):
            raise ValueError(Locale.PUSH_CAPTURED_LINKAGE_REQUIRED)
        return self


@implements[BackendComponent.PushResponseRecordProperty]()
class PushResponseRecord(HttpRequestLogRecord):
    commit_record: BackendCommitRecord | None = Field(exclude=True)
    validation_record: BackendValidationRecord | None = Field(exclude=True)

    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, "POST", "/push")
        commit, validation = self.commit_record, self.validation_record
        if self.response_code == HTTPStatus.ACCEPTED:
            if (
                commit is None
                or validation is None
                or commit.commit_request_body.push_record.record_id != self.record_id
                or validation.validation_request_body.commit_id != commit.record_id
                or validation.request_headers != commit.request_headers
            ):
                raise ValueError(Locale.PUSH_RESULT_LINKAGE_INVALID)
        elif commit is not None or validation is not None:
            raise ValueError(Locale.PUSH_REJECTED_LINKAGE_INVALID)
        return self


@implements[BackendComponent.QueryRequestRecordProperty]()
class QueryRequestRecord(HttpRequestLogRecord):
    @model_validator(mode="after")
    def _validate_query(self) -> Self:
        if (
            self.schema_version != "1.1"
            or self.record_id.version != 7
            or (self.method, self.path) != ("GET", "/query")
            or self.query
            or self.request_body not in (None, "")
            or self.response_code is not None
            or self.response_headers is not None
            or self.response_body is not None
            or self.ready_to_respond_at_unix_usec is not None
            or self.duration_usec is not None
        ):
            raise ValueError(Locale.QUERY_REQUEST_INVALID)
        return self


@implements[BackendComponent.QueryResponseRecordProperty]()
class QueryResponseRecord(HttpRequestLogRecord):
    query_response_body: QueryResponse = Field(exclude=True)

    @model_validator(mode="after")
    def _validate_query(self) -> Self:
        _validate_public_exchange(self, "GET", "/query")
        if (
            self.response_code != HTTPStatus.OK
            or self.response_body != self.query_response_body.model_dump_json()
        ):
            raise ValueError(Locale.QUERY_RESPONSE_BODY_MISMATCH)
        return self


@implements[BackendComponent.RunOutcomeRequestRecordProperty]()
class RunOutcomeRequestRecord(HttpRequestLogRecord):
    pull_record_id: UUID | None = Field(exclude=True)
    push_record_id: UUID | None = Field(exclude=True)
    codex_session_record: CodexSessionRecord = Field(exclude=True)
    rollout_filename: str | None = Field(exclude=True)
