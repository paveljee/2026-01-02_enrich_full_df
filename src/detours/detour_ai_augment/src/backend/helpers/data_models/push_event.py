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
from .pull_event import PullResponseRecord


@implements[BackendComponent.PushRequestRecordProperty]()
class PushRequestRecord(RequestRecord):
    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, HTTP_POST_METHOD, PUSH_PATH)
        return self


@implements[BackendComponent.PushResponseRecordProperty]()
class PushResponseRecord(ResponseRecord):
    pull_response_record: PullResponseRecord | None = Field(default=None, exclude=True)

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

    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, HTTP_POST_METHOD, PUSH_PATH)
        if self.response_code == HTTPStatus.ACCEPTED:
            if (
                self.pull_response_record is None
                or self.pull_response_record.response_code != HTTPStatus.OK
            ):
                raise ValueError(Locale.PUSH_RESULT_LINKAGE_INVALID)
        return self
