from __future__ import annotations

from collections.abc import Callable
from typing import Self
from uuid import UUID

from pydantic import Field, model_serializer, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_POST_METHOD,
    NAME_KEY_HEADER,
    SOURCE_KEY_HEADER,
    SYNTHETIC_COMMIT_HOST,
    SYNTHETIC_COMMIT_SCHEME,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models.http_request_log import HttpRequestLogRecord
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

from .ai_augment_http_request_log_record import RequestRecord

VALIDATE_PATH = "/validate"


class _ValidationRequestBodyJson(FrozenStrictModel):
    commit_request_record_id: UUID
    post_commit_validation: PostCommitValidation
    initial_validation_request_record_id: UUID | None
    openalex_ror_records_ids: tuple[UUID, ...]


@implements[BackendComponent.ValidationRequestBodyProperty]()
class ValidationRequestBody(FrozenStrictModel):
    commit_request_record: BackendCommitRequestRecord
    post_commit_validation: PostCommitValidation
    initial_validation_request_record: BackendValidationRequestRecord | None
    openalex_ror_records: tuple[HttpRequestLogRecord, ...] = ()

    def validate_body(self) -> Self:
        initial = self.initial_validation_request_record
        if initial is not None:
            initial_body = initial.validation_request_body
            if (
                initial_body.initial_validation_request_record is not None
                or initial_body.commit_request_record.record_id
                == self.commit_request_record.record_id
                or initial_body.commit_request_record.commit_request_body
                .codex_session_record.session_id
                != self.commit_request_record.commit_request_body.codex_session_record.session_id
                or initial.request_headers[NAME_KEY_HEADER]
                != self.commit_request_record.request_headers[NAME_KEY_HEADER]
            ):
                raise ValueError(Locale.VALIDATION_INITIAL_LINK_INVALID)
        ids = tuple(record.record_id for record in self.openalex_ror_records)
        if len(set(ids)) != len(ids) or any(record_id.version != 7 for record_id in ids):
            raise ValueError(Locale.VALIDATION_HTTP_REFERENCES_INVALID)
        return self

    @model_validator(mode="after")
    def _validate_body(self) -> Self:
        return self.validate_body()

    @model_serializer
    def serialize(self) -> dict[str, object]:
        return _ValidationRequestBodyJson(
            commit_request_record_id=self.commit_request_record.record_id,
            post_commit_validation=self.post_commit_validation,
            initial_validation_request_record_id=(
                None if self.initial_validation_request_record is None
                else self.initial_validation_request_record.record_id
            ),
            openalex_ror_records_ids=tuple(
                record.record_id for record in self.openalex_ror_records
            ),
        ).model_dump(mode="json")

    @classmethod
    def from_serialized_json(
        cls,
        value: str,
        *,
        commit_request_record: BackendCommitRequestRecord,
        initial_validation_request_record: BackendValidationRequestRecord | None,
        resolve_http_record: Callable[[UUID], HttpRequestLogRecord],
    ) -> Self:
        parsed = _ValidationRequestBodyJson.model_validate_json(value)
        if parsed.commit_request_record_id != commit_request_record.record_id:
            raise ValueError(Locale.VALIDATION_COMMIT_LINK_INVALID)
        if parsed.initial_validation_request_record_id != (
            None if initial_validation_request_record is None
            else initial_validation_request_record.record_id
        ):
            raise ValueError(Locale.VALIDATION_INITIAL_LINK_INVALID)
        return cls(
            commit_request_record=commit_request_record,
            post_commit_validation=parsed.post_commit_validation,
            initial_validation_request_record=initial_validation_request_record,
            openalex_ror_records=tuple(
                resolve_http_record(record_id)
                for record_id in parsed.openalex_ror_records_ids
            ),
        )


@implements[BackendComponent.ValidationRequestRecordProperty]()
class BackendValidationRequestRecord(RequestRecord):
    validation_request_body: ValidationRequestBody = Field(exclude=True)

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return super().http_request_log_record

    def validate_record(self) -> Self:
        if (
            self.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            or self.record_id.version != 7
            or self.method != HTTP_POST_METHOD
            or self.scheme != SYNTHETIC_COMMIT_SCHEME
            or self.host != SYNTHETIC_COMMIT_HOST
            or self.port is not None
            or self.path != VALIDATE_PATH
            or self.query
            or set(self.request_headers) != {SOURCE_KEY_HEADER, NAME_KEY_HEADER}
            or self.request_body is None
            or self.response_code is not None
            or self.response_headers is not None
            or self.response_body is not None
            or self.received_at_unix_usec is not None
            or self.ready_to_respond_at_unix_usec is None
            or self.duration_usec != 0
        ):
            raise ValueError(Locale.VALIDATION_RECORD_INVALID)
        parsed = _ValidationRequestBodyJson.model_validate_json(self.request_body)
        initial = self.validation_request_body.initial_validation_request_record
        if (
            parsed.model_dump(mode="json") != self.validation_request_body.serialize()
            or self.request_headers
            != self.validation_request_body.commit_request_record.request_headers
            or (initial is not None and initial.record_id == self.record_id)
        ):
            raise ValueError(Locale.VALIDATION_BODY_MISMATCH)
        return self

    @model_validator(mode="after")
    def _validate_record(self) -> Self:
        return self.validate_record()

    @classmethod
    def from_http_request_log_record(
        cls,
        http_request_log_record: HttpRequestLogRecord,
        *,
        validation_request_body: ValidationRequestBody | None = None,
    ) -> Self:
        record = http_request_log_record
        if record.request_body is None:
            raise ValueError(Locale.VALIDATION_BODY_MISSING)
        if validation_request_body is None:
            raise ValueError(Locale.VALIDATION_COMMIT_LINK_INVALID)
        return cls(
            schema_version=record.schema_version,
            record_id=record.record_id,
            method=record.method,
            scheme=record.scheme,
            host=record.host,
            port=record.port,
            path=record.path,
            query=record.query,
            request_headers=record.request_headers,
            request_body=record.request_body,
            response_code=record.response_code,
            response_headers=record.response_headers,
            response_body=record.response_body,
            received_at_unix_usec=record.received_at_unix_usec,
            ready_to_respond_at_unix_usec=record.ready_to_respond_at_unix_usec,
            duration_usec=record.duration_usec,
            validation_request_body=validation_request_body,
        )

    @classmethod
    def from_serialized_json(
        cls,
        *,
        value: str,
        commit_request_record: BackendCommitRequestRecord | None = None,
        initial_validation_request_record: BackendValidationRequestRecord | None = None,
        resolve_http_record: Callable[[UUID], HttpRequestLogRecord] | None = None,
    ) -> Self:
        if commit_request_record is None:
            raise ValueError(Locale.VALIDATION_COMMIT_LINK_INVALID)
        if resolve_http_record is None:
            raise ValueError(Locale.VALIDATION_HTTP_REFERENCES_INVALID)
        record = HttpRequestLogRecord.model_validate_json(value)
        if record.request_body is None:
            raise ValueError(Locale.VALIDATION_BODY_MISSING)
        body = ValidationRequestBody.from_serialized_json(
            record.request_body,
            commit_request_record=commit_request_record,
            initial_validation_request_record=initial_validation_request_record,
            resolve_http_record=resolve_http_record,
        )
        return cls.from_http_request_log_record(
            record, validation_request_body=body,
        )

    def serialize(self) -> dict[str, object]:
        return self.http_request_log_record.model_dump(mode="json")


# Deliberate post-definition imports: validation refers to a prior commit,
# while retry pulls refer back to a prior validation. The response models
# must be defined before these concrete names are imported; postponed
# annotations let Pydantic resolve them without weakening the field types.
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.post_commit_validation import (  # noqa: E402, E501
    PostCommitValidation,
)

from .commit_request import BackendCommitRequestRecord  # noqa: E402
