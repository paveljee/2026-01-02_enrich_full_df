from __future__ import annotations

from http import HTTPStatus
from typing import Annotated, Literal, Self

from pydantic import Field, NonNegativeInt, model_validator
from requests.structures import CaseInsensitiveDict

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_CONTENT_TYPE_HEADER,
    HTTP_GET_METHOD,
    PULL_PATH,
    ContentType,
)
from src.helpers.architecture import implements
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

from .ai_augment_http_request_log_record import (
    RequestRecord,
    ResponseRecord,
)


@implements[BackendComponent.PullRequestRecordProperty]()
class PullRequestRecord(RequestRecord):
    method: Annotated[str, Field(pattern=f"^{HTTP_GET_METHOD}$")]
    path: Annotated[str, Field(pattern=f"^{PULL_PATH}$")]
    received_at_unix_usec: int
    ready_to_respond_at_unix_usec: None = None
    duration_usec: Literal[0]

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


@implements[BackendComponent.PullResponseRecordProperty]()
class PullResponseRecord(ResponseRecord):
    method: Annotated[str, Field(pattern=f"^{HTTP_GET_METHOD}$")]
    path: Annotated[str, Field(pattern=f"^{PULL_PATH}$")]
    received_at_unix_usec: None = None
    ready_to_respond_at_unix_usec: int
    duration_usec: NonNegativeInt

    validation_request_record: BackendValidationRequestRecord | None = Field(
        default=None, exclude=True
    )

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return super().http_request_log_record

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

    @classmethod
    def from_serialized_json(
        cls, *, value: str,
        validation_request_record: BackendValidationRequestRecord | None = None,
    ) -> Self:
        return cls.from_http_request_log_record(
            http_request_log_record=HttpRequestLogRecord.model_validate_json(value),
            validation_request_record=validation_request_record,
        )

    def serialize(self) -> dict[str, object]:
        return self.http_request_log_record.model_dump(mode="json")

    @property
    def pull_response_body(self) -> str:
        if self.response_body is None:
            raise ValueError(Locale.PULL_RESPONSE_BODY_MISSING)
        return self.response_body

    @model_validator(mode="after")
    def _validate_exchange(self) -> Self:
        content_type = CaseInsensitiveDict(self.response_headers or {}).get(
            HTTP_CONTENT_TYPE_HEADER
        )
        if self.response_code == HTTPStatus.OK:
            if (
                content_type == ContentType.NDJSON_UTF8
                and self.validation_request_record is not None
            ) or (
                content_type == ContentType.MARKDOWN_UTF8
                and self.validation_request_record is None
            ) or content_type not in {
                ContentType.NDJSON_UTF8, ContentType.MARKDOWN_UTF8,
            }:
                raise ValueError(Locale.PULL_RESPONSE_LINKAGE_INVALID)
        elif self.validation_request_record is not None:
            raise ValueError(Locale.PULL_RESPONSE_LINKAGE_INVALID)
        return self


# Deliberate post-definition import: pull and validation records refer to one
# another through earlier lifecycle objects. Define the Pydantic model first,
# then bind its concrete annotation name; moving this import to the header
# recreates a module-initialization cycle, not an object-instance cycle.
from .validation_request import BackendValidationRequestRecord  # noqa: E402
