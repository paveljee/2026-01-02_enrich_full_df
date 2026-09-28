from __future__ import annotations

from typing import Self

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
)
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1


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


@implements[BackendComponent.AiAugmentHttpRequestLogRecordProperty]()
class AiAugmentHttpRequestLogRecord(
    HttpRequestLogRecord,
    FrozenStrictModel,
):
    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return self

    @classmethod
    def from_http_request_log_record(
        cls, *, http_request_log_record: HttpRequestLogRecord,
    ) -> Self:
        return cls.model_validate(http_request_log_record.model_dump(mode="python"))

    @classmethod
    def from_serialized_json(cls, *, value: str) -> Self:
        return cls.model_validate_json(value)

    def serialize(self) -> dict[str, object]:
        return self.model_dump(mode="json")


@implements[BackendComponent.RequestRecordProperty]()
class RequestRecord(AiAugmentHttpRequestLogRecord):
    pass


@implements[BackendComponent.ResponseRecordProperty]()
class ResponseRecord(AiAugmentHttpRequestLogRecord):
    pass
