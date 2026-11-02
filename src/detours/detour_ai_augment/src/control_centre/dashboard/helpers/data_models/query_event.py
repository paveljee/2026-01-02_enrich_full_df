from __future__ import annotations

from http import HTTPStatus
from typing import Annotated, Literal, Self

from pydantic import Field, NonNegativeInt, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import ControlCentreComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_GET_METHOD,
    QUERY_PATH,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

from .....backend.helpers.data_models.ai_augment_http_request_log_record import (
    RequestRecord,
    ResponseRecord,
)
from .....backend.helpers.data_models.ai_augment_singular_outer_dict import (
    AiAugmentSingularOuterDict,
    _AiAugmentSingularOuterDictJson,
)


@implements[ControlCentreComponent.BackendPort.QueryRequestRecordProperty]()
class QueryRequestRecord(RequestRecord):
    method: Annotated[str, Field(pattern=f"^{HTTP_GET_METHOD}$")]
    path: Annotated[str, Field(pattern=f"^{QUERY_PATH}$")]
    # Reject explicit URL ports before a query reaches the read-only Store port.
    port: None = None
    query: Literal[""] = ""
    request_body: None = None
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


class _QueryResponseBodyJson(FrozenStrictModel):
    ai_augment_singular_outerdicts: tuple[_AiAugmentSingularOuterDictJson, ...]


@implements[ControlCentreComponent.BackendPort.QueryResponseRecordProperty]()
class QueryResponseRecord(ResponseRecord):
    method: Annotated[str, Field(pattern=f"^{HTTP_GET_METHOD}$")]
    path: Annotated[str, Field(pattern=f"^{QUERY_PATH}$")]
    # Store-produced replies keep the same portless IPC contour on conversion.
    port: None = None
    received_at_unix_usec: None = None
    ready_to_respond_at_unix_usec: int
    duration_usec: NonNegativeInt

    ai_augment_singular_outerdicts: tuple[AiAugmentSingularOuterDict, ...] = Field(
        exclude=True,
    )

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return super().http_request_log_record

    @classmethod
    def outerdicts_from_response_body(
        cls, value: str | bytes,
    ) -> tuple[AiAugmentSingularOuterDict, ...]:
        serialized = _QueryResponseBodyJson.model_validate_json(value)
        return tuple(
            AiAugmentSingularOuterDict.from_serialized(item.model_dump(mode="json"))
            for item in serialized.ai_augment_singular_outerdicts
        )

    @classmethod
    def from_http_request_log_record(
        cls, *, http_request_log_record: HttpRequestLogRecord,
    ) -> Self:
        body = http_request_log_record.response_body
        if body is None:
            raise ValueError(Locale.QUERY_RESPONSE_BODY_MISMATCH)
        return cls(
            **http_request_log_record.model_dump(mode="python"),
            ai_augment_singular_outerdicts=cls.outerdicts_from_response_body(body),
        )

    @classmethod
    def from_serialized_json(cls, *, value: str) -> Self:
        return cls.from_http_request_log_record(
            http_request_log_record=HttpRequestLogRecord.model_validate_json(value),
        )

    def serialize(self) -> dict[str, object]:
        return self.http_request_log_record.model_dump(mode="json")

    @model_validator(mode="after")
    def _validate_query(self) -> Self:
        if self.response_code != HTTPStatus.OK or self.response_body is None:
            raise ValueError(Locale.QUERY_RESPONSE_BODY_MISMATCH)
        body = _QueryResponseBodyJson.model_validate_json(self.response_body)
        expected_body = _QueryResponseBodyJson(
            ai_augment_singular_outerdicts=tuple(
                _AiAugmentSingularOuterDictJson.from_ai_augment_singular_outerdict(value)
                for value in self.ai_augment_singular_outerdicts
            )
        )
        if (
            self.response_body != body.model_dump_json()
            or body.model_dump(mode="json") != expected_body.model_dump(mode="json")
        ):
            raise ValueError(Locale.QUERY_RESPONSE_BODY_MISMATCH)
        return self
