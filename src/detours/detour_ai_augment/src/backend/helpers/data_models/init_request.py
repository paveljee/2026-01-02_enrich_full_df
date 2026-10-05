from __future__ import annotations

from typing import Self

from pydantic import model_validator

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_POST_METHOD,
    INIT_PATH,
    NAME_KEY_HEADER,
    SYNTHETIC_COMMIT_HOST,
    SYNTHETIC_COMMIT_SCHEME,
)
from src.detours.detour_ai_augment.src.shared import name_key_from_header_value
from src.helpers.architecture import implements
from src.helpers.data_models import HttpRequestLogRecord, NameKey
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

from .ai_augment_http_request_log_record import RequestRecord


@implements[BackendComponent.InitRequestRecordProperty]()
class BackendInitRequestRecord(RequestRecord):
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
        if (
            self.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            or self.record_id.version != 7
            or (self.method, self.scheme, self.host, self.path) != (
                HTTP_POST_METHOD, SYNTHETIC_COMMIT_SCHEME,
                SYNTHETIC_COMMIT_HOST, INIT_PATH,
            )
            or self.port is not None
            or self.query
            or set(self.request_headers) != {NAME_KEY_HEADER}
            or self.request_body is not None
            or self.response_code is not None
            or self.response_headers is not None
            or self.response_body is not None
            or self.received_at_unix_usec is not None
            or self.ready_to_respond_at_unix_usec is None
            or self.duration_usec != 0
        ):
            raise ValueError(Locale.INIT_REQUEST_RECORD_INVALID)
        try:
            self.namekey
        except ValueError as exc:
            raise ValueError(Locale.INIT_REQUEST_RECORD_INVALID) from exc
        return self
