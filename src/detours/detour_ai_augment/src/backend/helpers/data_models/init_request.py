from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_POST_METHOD,
    INIT_PATH,
    NAME_KEY_HEADER,
    SYNTHETIC_COMMIT_HOST,
    SYNTHETIC_COMMIT_SCHEME,
)
from src.detours.detour_ai_augment.protected.src.shared import name_key_from_header_value
from src.helpers.architecture import implements
from src.helpers.data_models import HttpRequestLogRecord, NameKey

from .ai_augment_http_request_log_record import RequestRecord


@implements[BackendComponent.InitRequestRecordProperty]()
class BackendInitRequestRecord(RequestRecord):
    method: Annotated[str, Field(pattern=f"^{HTTP_POST_METHOD}$")]
    scheme: Annotated[str, Field(pattern=f"^{SYNTHETIC_COMMIT_SCHEME}$")]
    host: Annotated[str, Field(pattern=f"^{SYNTHETIC_COMMIT_HOST}$")]
    port: None = None
    path: Annotated[str, Field(pattern=f"^{INIT_PATH}$")]
    query: Literal[""] = ""
    request_headers: Annotated[
        dict[Annotated[str, Field(pattern=f"^{NAME_KEY_HEADER}$")], str],
        Field(min_length=1, max_length=1),
    ]
    request_body: None = None
    received_at_unix_usec: None = None
    ready_to_respond_at_unix_usec: int
    duration_usec: Literal[0]

    @property
    def namekey(self) -> NameKey:
        return name_key_from_header_value(self.request_headers[NAME_KEY_HEADER])

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
    def _validate_contour(self) -> Self:
        try:
            self.namekey
        except ValueError as exc:
            raise ValueError(Locale.INIT_REQUEST_RECORD_INVALID) from exc
        return self
