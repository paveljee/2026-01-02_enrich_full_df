from __future__ import annotations

from http import HTTPStatus
from typing import Self

from pydantic import Field, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import ControlCentreComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_CONTENT_TYPE_HEADER,
    HTTP_GET_METHOD,
    QUERY_PATH,
    ContentType,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models.http_request_log import HttpRequestLogRecord
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

from .....backend.helpers.data_models.ai_augment_http_request_log_record import (
    RequestRecord,
    ResponseRecord,
    _validate_public_exchange,
)
from .....backend.helpers.data_models.ai_augment_singular_outer_dict import (
    AiAugmentSingularOuterDict,
    _AiAugmentSingularOuterDictJson,
)


@implements[ControlCentreComponent.BackendPort.QueryRequestRecordProperty]()
class QueryRequestRecord(RequestRecord):
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
    def _validate_query(self) -> Self:
        if (
            self.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            or self.record_id.version != 7
            or (self.method, self.path) != (HTTP_GET_METHOD, QUERY_PATH)
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


class _QueryResponseBodyJson(FrozenStrictModel):
    ai_augment_singular_outerdicts: tuple[_AiAugmentSingularOuterDictJson, ...]


@implements[ControlCentreComponent.BackendPort.QueryResponseRecordProperty]()
class QueryResponseRecord(ResponseRecord):
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

    @classmethod
    def from_query_request(
        cls,
        request: QueryRequestRecord,
        *,
        ai_augment_singular_outerdicts: tuple[AiAugmentSingularOuterDict, ...],
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
            response_body=_QueryResponseBodyJson(
                ai_augment_singular_outerdicts=tuple(
                    _AiAugmentSingularOuterDictJson.from_ai_augment_singular_outerdict(record)
                    for record in ai_augment_singular_outerdicts
                ),
            ).model_dump_json(),
            received_at_unix_usec=received,
            ready_to_respond_at_unix_usec=ready_to_respond_at_unix_usec,
            duration_usec=ready_to_respond_at_unix_usec - received,
            ai_augment_singular_outerdicts=ai_augment_singular_outerdicts,
        )

    @model_validator(mode="after")
    def _validate_query(self) -> Self:
        _validate_public_exchange(self, HTTP_GET_METHOD, QUERY_PATH)
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
