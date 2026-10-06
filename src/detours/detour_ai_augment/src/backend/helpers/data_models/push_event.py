from __future__ import annotations

from http import HTTPStatus
from typing import Self

from pydantic import Field, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_POST_METHOD,
    PUSH_PATH,
)
from src.helpers.architecture import implements
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

from .ai_augment_http_request_log_record import (
    RequestRecord,
    ResponseRecord,
    _validate_public_exchange,
)


@implements[BackendComponent.PushRequestRecordProperty]()
class PushRequestRecord(RequestRecord):
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

    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        if (
            self.method != HTTP_POST_METHOD
            or self.path != PUSH_PATH
            or self.response_code is not None
            or self.response_headers is not None
            or self.response_body is not None
            or self.received_at_unix_usec is None
            or self.ready_to_respond_at_unix_usec is not None
            or self.duration_usec != 0
        ):
            raise ValueError(Locale.PUBLIC_HTTP_EXCHANGE_INVALID)
        return self


@implements[BackendComponent.PushResponseRecordProperty]()
class PushResponseRecord(ResponseRecord):
    pull_response_record: PullResponseRecord | None = Field(default=None, exclude=True)

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return super().http_request_log_record

    @classmethod
    def from_http_request_log_record(
        cls,
        *,
        http_request_log_record: HttpRequestLogRecord,
        pull_response_record: PullResponseRecord | None = None,
    ) -> Self:
        return cls(
            **http_request_log_record.model_dump(mode="python"),
            pull_response_record=pull_response_record,
        )

    @classmethod
    def from_serialized_json(
        cls, *, value: str, pull_response_record: PullResponseRecord | None = None,
    ) -> Self:
        return cls.from_http_request_log_record(
            http_request_log_record=HttpRequestLogRecord.model_validate_json(value),
            pull_response_record=pull_response_record,
        )

    def serialize(self) -> dict[str, object]:
        return self.http_request_log_record.model_dump(mode="json")

    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, HTTP_POST_METHOD, PUSH_PATH)
        if self.response_code == HTTPStatus.ACCEPTED:
            if (
                self.pull_response_record is None
                or self.pull_response_record.response_code != HTTPStatus.OK
            ):
                raise ValueError(Locale.PUSH_RESULT_LINKAGE_INVALID)
        elif self.pull_response_record is not None:
            raise ValueError(Locale.PUSH_RESULT_LINKAGE_INVALID)
        return self


# Deliberate post-definition import: define PushResponseRecord before binding
# the concrete pull type so commit/pull/validation modules can import this
# module in either order without observing a half-defined response class.
from .pull_event import PullResponseRecord  # noqa: E402
