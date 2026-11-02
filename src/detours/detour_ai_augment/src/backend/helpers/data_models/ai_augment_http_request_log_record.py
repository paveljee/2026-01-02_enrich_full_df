from __future__ import annotations

from typing import Literal, Self
from uuid import uuid7

from pydantic import UUID7, Field

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
)


@implements[BackendComponent.AiAugmentHttpRequestLogRecordProperty]()
class AiAugmentHttpRequestLogRecord(
    HttpRequestLogRecord,
    FrozenStrictModel,
):
    schema_version: Literal["1.1"]
    record_id: UUID7 = Field(default_factory=uuid7)

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
    response_code: None = None
    response_headers: None = None
    response_body: None = None

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


@implements[BackendComponent.ResponseRecordProperty]()
class ResponseRecord(AiAugmentHttpRequestLogRecord):
    response_code: int
    response_headers: dict[str, str]
    response_body: str

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
