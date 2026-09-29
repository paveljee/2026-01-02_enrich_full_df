from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_GET_METHOD,
    PULL_PATH,
)
from src.helpers.architecture import implements
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

from .ai_augment_http_request_log_record import (
    RequestRecord,
    ResponseRecord,
    _validate_public_exchange,
)


@implements[BackendComponent.PullRequestRecordProperty]()
class PullRequestRecord(RequestRecord):
    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, HTTP_GET_METHOD, PULL_PATH)
        return self


@implements[BackendComponent.PullResponseRecordProperty]()
class PullResponseRecord(ResponseRecord):
    validation_request_record: BackendValidationRequestRecord | None = Field(
        default=None, exclude=True
    )

    @classmethod
    def from_http_request_log_record(
        cls,
        *,
        http_request_log_record: HttpRequestLogRecord,
        validation_request_record: BackendValidationRequestRecord | None = None,
    ) -> Self:
        return cls(
            **http_request_log_record.model_dump(mode="python"),
            validation_request_record=validation_request_record,
        )

    @property
    def pull_response_body(self) -> str:
        if self.response_body is None:
            raise ValueError(Locale.PULL_RESPONSE_BODY_MISSING)
        return self.response_body

    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        _validate_public_exchange(self, HTTP_GET_METHOD, PULL_PATH)
        return self


# Deliberate post-definition import: pull and validation records refer to one
# another through earlier lifecycle objects. Define the Pydantic model first,
# then bind its concrete annotation name; moving this import to the header
# recreates a module-initialization cycle, not an object-instance cycle.
from .validation_request import BackendValidationRequestRecord  # noqa: E402
