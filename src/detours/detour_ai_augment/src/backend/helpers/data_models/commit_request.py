from __future__ import annotations

import base64
from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictStr, model_serializer, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    BASE64_TEXT_ENCODING,
    HTTP_POST_METHOD,
    NAME_KEY_HEADER,
    SOURCE_KEY_HEADER,
    SYNTHETIC_COMMIT_HOST,
    SYNTHETIC_COMMIT_SCHEME,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models import HttpRequestLogRecord

from .ai_augment_http_request_log_record import RequestRecord

COMMIT_PATH = "/commit"


@implements[BackendComponent.AppendwatchReportEncodingProperty]()
class AppendwatchReportEncoding(StrEnum):
    value: Literal["base64"]

    BASE64 = "base64"


@implements[BackendComponent.AppendwatchReportRecordProperty]()
class AppendwatchReportRecord(FrozenStrictModel):
    encoding: AppendwatchReportEncoding
    data: StrictStr

    def validate_canonical_base64(self) -> Self:
        try:
            decoded = base64.b64decode(self.data, validate=True)
        except ValueError as exc:
            raise ValueError(Locale.APPENDWATCH_BASE64_INVALID) from exc
        if base64.b64encode(decoded).decode(BASE64_TEXT_ENCODING) != self.data:
            raise ValueError(Locale.APPENDWATCH_BASE64_NONCANONICAL)
        return self

    @model_validator(mode="after")
    def _validate_canonical_base64(self) -> Self:
        return self.validate_canonical_base64()

    def decoded_bytes(self) -> bytes:
        return base64.b64decode(self.data, validate=True)


# Import the concrete rollout model here before CodexSessionRecord uses it.
# codex_rollout_record has no commit/validation dependency, so direct config/context
# imports cannot re-enter a partially initialized cas module through commit.
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.codex_rollout_record import (  # noqa: E402, E501
    CodexRolloutRecord,
)


@implements[BackendComponent.CodexSessionRecordProperty]()
class CodexSessionRecord(FrozenStrictModel):
    session_id: UUID | None
    codex_rollout_record: CodexRolloutRecord | None
    appendwatch_report_record: AppendwatchReportRecord | None


class _CodexSessionRecordJson(FrozenStrictModel):
    codex_session_id: UUID | None
    codex_rollout_record: CodexRolloutRecord | None
    appendwatch_report_record: AppendwatchReportRecord | None


class _CommitRequestBodyJson(FrozenStrictModel):
    pull_record_id: UUID
    push_record_id: UUID
    codex_session_record: _CodexSessionRecordJson

    @model_validator(mode="after")
    def validate_complete_codex_session_record(self) -> Self:
        session = self.codex_session_record
        if (
            session.codex_session_id is None
            or session.codex_rollout_record is None
            or session.appendwatch_report_record is None
        ):
            raise ValueError(Locale.COMMIT_SESSION_INCOMPLETE)
        return self


@implements[BackendComponent.CommitRequestBodyProperty]()
class CommitRequestBody(FrozenStrictModel):
    pull_response_record: PullResponseRecord
    push_response_record: PushResponseRecord
    codex_session_record: CodexSessionRecord

    def validate_complete_commit(self) -> Self:
        session = self.codex_session_record
        if (
            session.session_id is None
            or session.codex_rollout_record is None
            or session.appendwatch_report_record is None
        ):
            raise ValueError(Locale.COMMIT_SESSION_INCOMPLETE)
        return self

    @model_validator(mode="after")
    def _validate_complete_commit(self) -> Self:
        return self.validate_complete_commit()

    @classmethod
    def validate_serialized_json(cls, value: str) -> None:
        _CommitRequestBodyJson.model_validate_json(value)

    @classmethod
    def from_serialized_json(
        cls,
        value: str,
        *,
        resolve_http_record: Callable[
            [UUID], PullResponseRecord | PushResponseRecord
        ],
    ) -> Self:
        serialized = _CommitRequestBodyJson.model_validate_json(value)
        session = serialized.codex_session_record
        pull_response_record = resolve_http_record(serialized.pull_record_id)
        push_response_record = resolve_http_record(serialized.push_record_id)
        if not isinstance(pull_response_record, PullResponseRecord) or not isinstance(
            push_response_record, PushResponseRecord
        ):
            raise ValueError(Locale.COMMIT_BODY_RECORDS_MISMATCH)
        return cls(
            pull_response_record=pull_response_record,
            push_response_record=push_response_record,
            codex_session_record=CodexSessionRecord(
                session_id=session.codex_session_id,
                codex_rollout_record=session.codex_rollout_record,
                appendwatch_report_record=session.appendwatch_report_record,
            ),
        )

    def serialize(self) -> dict[str, object]:
        session_id = self.codex_session_record.session_id
        rollout = self.codex_session_record.codex_rollout_record
        report = self.codex_session_record.appendwatch_report_record
        assert session_id is not None
        assert rollout is not None
        assert report is not None
        return {
            "pull_record_id": self.pull_response_record.record_id,
            "push_record_id": self.push_response_record.record_id,
            "codex_session_record": _CodexSessionRecordJson(
                codex_session_id=session_id,
                codex_rollout_record=rollout,
                appendwatch_report_record=report,
            ),
        }

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()


@implements[BackendComponent.CommitRequestRecordProperty]()
class BackendCommitRequestRecord(RequestRecord):
    method: Annotated[str, Field(pattern=f"^{HTTP_POST_METHOD}$")]
    scheme: Annotated[str, Field(pattern=f"^{SYNTHETIC_COMMIT_SCHEME}$")]
    host: Annotated[str, Field(pattern=f"^{SYNTHETIC_COMMIT_HOST}$")]
    port: None = None
    path: Annotated[str, Field(pattern=f"^{COMMIT_PATH}$")]
    query: Literal[""] = ""
    request_headers: Annotated[
        dict[
            Annotated[
                str,
                Field(pattern=f"^(?:{SOURCE_KEY_HEADER}|{NAME_KEY_HEADER})$"),
            ],
            str,
        ],
        Field(min_length=2, max_length=2),
    ]
    request_body: str
    received_at_unix_usec: None = None
    ready_to_respond_at_unix_usec: int
    duration_usec: Literal[0]

    commit_request_body: CommitRequestBody = Field(exclude=True)

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return super().http_request_log_record

    @classmethod
    def from_serialized_json(
        cls,
        *,
        value: str,
        resolve_http_record: Callable[
            [UUID], PullResponseRecord | PushResponseRecord
        ] | None = None,
    ) -> Self:
        if resolve_http_record is None:
            raise ValueError(Locale.COMMIT_REFERENCES_REQUIRED)
        return cls.from_http_request_log_record(
            HttpRequestLogRecord.model_validate_json(value),
            resolve_http_record=resolve_http_record,
        )

    def serialize(self) -> dict[str, object]:
        return self.http_request_log_record.model_dump(mode="json")

    @model_validator(mode="after")
    def _validate_commit_request_record(self) -> Self:
        expected = self.commit_request_body
        refs: dict[UUID, PullResponseRecord | PushResponseRecord] = {
            expected.pull_response_record.record_id: expected.pull_response_record,
            expected.push_response_record.record_id: expected.push_response_record,
        }
        parsed = CommitRequestBody.from_serialized_json(
            self.request_body,
            resolve_http_record=lambda record_id: refs[record_id],
        )
        if parsed != expected:
            raise ValueError(Locale.COMMIT_BODY_RECORDS_MISMATCH)
        return self

    @classmethod
    def from_http_request_log_record(
        cls,
        http_request_log_record: HttpRequestLogRecord,
        *,
        resolve_http_record: Callable[
            [UUID], PullResponseRecord | PushResponseRecord
        ] | None = None,
    ) -> Self:
        if resolve_http_record is None:
            raise ValueError(Locale.COMMIT_REFERENCES_REQUIRED)
        record = http_request_log_record
        if record.request_body is None:
            raise ValueError(Locale.COMMIT_BODY_MISSING)
        body = CommitRequestBody.from_serialized_json(
            record.request_body,
            resolve_http_record=resolve_http_record,
        )
        return cls.model_validate({
            **record.model_dump(),
            "commit_request_body": body,
        })


# Deliberate post-definition imports: the concrete pull/push response types
# form a Pydantic annotation ring with commit and validation. All commit
# models must exist before
# importing those modules. These names then resolve to the actual classes;
# no generic HTTP field or manual model_rebuild is used for the links.
from .pull_event import PullResponseRecord  # noqa: E402
from .push_event import PushResponseRecord  # noqa: E402
