from __future__ import annotations

from http import HTTPStatus
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_CONTENT_TYPE_HEADER,
    HTTP_GET_METHOD,
    HTTP_POST_METHOD,
    PULL_PATH,
    PUSH_PATH,
    ContentType,
)
from src.helpers.architecture import implements
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
)
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

from ....control_centre.dashboard.helpers.data_models.query_request import QueryRequest
from .commit_event import BackendCommitRecord, CodexSessionRecord
from .query_response import QueryResponse
from .validation_event import BackendValidationRecord


def _validate_public_exchange(record: HttpRequestLogRecord, method: str, path: str) -> None:
    if (
        record.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
        or record.record_id.version != 7
        or (record.method, record.path) != (method, path)
        or record.response_code is None
        or record.response_headers is None
        or record.response_body is None
        or record.ready_to_respond_at_unix_usec is None
        or record.duration_usec is None
    ):
        raise ValueError(Locale.PUBLIC_HTTP_EXCHANGE_INVALID)


@implements[BackendComponent.PullRequestRecordProperty]()
class PullRequestRecord(HttpRequestLogRecord):
    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, HTTP_GET_METHOD, PULL_PATH)
        return self


@implements[BackendComponent.PullResponseRecordProperty]()
class PullResponseRecord(HttpRequestLogRecord):
    @property
    def pull_response_body(self) -> str:
        if self.response_body is None:
            raise ValueError(Locale.PULL_RESPONSE_BODY_MISSING)
        return self.response_body

    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, HTTP_GET_METHOD, PULL_PATH)
        return self


@implements[BackendComponent.PushRequestRecordProperty]()
class PushRequestRecord(HttpRequestLogRecord):
    pull_record_id: UUID | None = Field(exclude=True)
    session_id: UUID | None = Field(exclude=True)

    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, HTTP_POST_METHOD, PUSH_PATH)
        return self


@implements[BackendComponent.PushResponseRecordProperty]()
class PushResponseRecord(HttpRequestLogRecord):
    commit_record: BackendCommitRecord | None = Field(exclude=True)
    validation_record: BackendValidationRecord | None = Field(exclude=True)

    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, HTTP_POST_METHOD, PUSH_PATH)
        commit, validation = self.commit_record, self.validation_record
        if self.response_code == HTTPStatus.ACCEPTED:
            if (
                commit is None
                or validation is None
                or commit.commit_request_body.push_record.record_id != self.record_id
                or validation.validation_request_body.commit_record.record_id != commit.record_id
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
            self.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            or self.record_id.version != 7
            or (self.method, self.path) != QueryRequest().outbound_http()
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

    @classmethod
    def from_query_request(
        cls,
        request: QueryRequestRecord,
        *,
        body: QueryResponse,
        ready_to_respond_at_unix_usec: int,
    ) -> Self:
        received = request.received_at_unix_usec
        if received is None:
            raise ValueError(Locale.QUERY_REQUEST_RECEIPT_TIME_MISSING)
        return cls(
            schema_version=request.schema_version,
            record_id=request.record_id,
            method=request.method,
            scheme=request.scheme,
            host=request.host,
            port=request.port,
            path=request.path,
            query=request.query,
            request_headers=request.request_headers,
            request_body=request.request_body,
            response_code=HTTPStatus.OK,
            response_headers={HTTP_CONTENT_TYPE_HEADER: ContentType.JSON},
            response_body=body.model_dump_json(),
            received_at_unix_usec=received,
            ready_to_respond_at_unix_usec=ready_to_respond_at_unix_usec,
            duration_usec=ready_to_respond_at_unix_usec - received,
            query_response_body=body,
        )

    @model_validator(mode="after")
    def _validate_query(self) -> Self:
        _validate_public_exchange(self, *QueryRequest().outbound_http())
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
