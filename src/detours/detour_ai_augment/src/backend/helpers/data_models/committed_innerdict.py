from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Self
from uuid import UUID

from pydantic import (
    model_serializer,
    model_validator,
)

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL,
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models import (
    HttpRequestLogRecord,
    InnerDict,
    NameKey,
)
from src.helpers.vars import (
    KTP_NAMEKEY_COL,
)

from ....control_centre.dashboard.helpers.data_models.run_outcome import (
    NAME_KEY_HEADER,
    name_key_from_header_value,
)
from .commit_event import (
    BackendCommitRecord,
    CodexRolloutRecord,
    CodexSessionRecord,
    CommitRequestBody,
)


class _CodexInnerDictProcedure:
    dataset_id_field = KTP_NAMEKEY_COL


class _BackendCommitRecordJson(FrozenStrictModel):
    http_record: HttpRequestLogRecord
    pull_record: HttpRequestLogRecord
    push_record: HttpRequestLogRecord
    codex_session_record: CodexSessionRecord

    @classmethod
    def from_commit_record(cls, value: BackendCommitRecord) -> Self:
        body = value.commit_request_body
        return cls(
            http_record=value.http_request_log_record,
            pull_record=body.pull_record,
            push_record=body.push_record,
            codex_session_record=body.codex_session_record,
        )

    def to_commit_record(self) -> BackendCommitRecord:
        return BackendCommitRecord(
            **self.http_record.model_dump(),
            commit_request_body=CommitRequestBody(
                pull_record=self.pull_record,
                push_record=self.push_record,
                codex_session_record=self.codex_session_record,
            ),
        )


class _CommittedInnerDictJson(FrozenStrictModel):
    innerdict: dict[str, Any]
    commit_record: _BackendCommitRecordJson

    @classmethod
    def from_committed_innerdict(cls, value: CommittedInnerDict) -> Self:
        return cls(
            innerdict=value.innerdict.data,
            commit_record=_BackendCommitRecordJson.from_commit_record(
                value.commit_record
            ),
        )


@implements[BackendComponent.ControlCentrePort.CommittedInnerDictProperty]()
class CommittedInnerDict(FrozenStrictModel):
    innerdict: InnerDict
    commit_record: BackendCommitRecord

    def text(self, column: str) -> str | None:
        value = self.innerdict.data.get(column)
        if value is not None and not isinstance(value, str):
            raise ValueError("committed innerdict text value is invalid")
        return value

    def _required_text(self, column: str) -> str:
        value = self.text(column)
        if value is None:
            raise ValueError("committed innerdict required text value is missing")
        return value

    def validate_committed_innerdict(self) -> Self:
        body = self.commit_record.commit_request_body
        stored_namekey = NameKey.from_json_key(self._required_text(KTP_NAMEKEY_COL))
        committed_namekey = name_key_from_header_value(
            self.commit_record.request_headers.get(NAME_KEY_HEADER)
        )
        if stored_namekey != committed_namekey:
            raise ValueError("committed innerdict namekey does not match its commit")
        if UUID(self._required_text(KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL)) != (
            self.commit_record.record_id
        ):
            raise ValueError("committed innerdict ID does not match its commit")
        session_id = body.codex_session_record.session_id
        if session_id is None:
            raise ValueError("committed innerdict Codex session ID is missing")
        summary = CodexRolloutRecord.parse_summary_json(
            self._required_text(KTP_AI_AUGMENT_SESSION_METADATA_COL)
        )
        if UUID(summary["session_id"]) != session_id:
            raise ValueError("committed innerdict Codex session does not match its commit")
        return self

    @model_validator(mode="after")
    def _validate_committed_innerdict(self) -> Self:
        return self.validate_committed_innerdict()

    @classmethod
    def from_serialized(cls, value: Mapping[str, object]) -> Self:
        serialized = _CommittedInnerDictJson.model_validate_json(json.dumps(value))
        return cls(
            innerdict=InnerDict.from_mapping(
                serialized.innerdict,
                _CodexInnerDictProcedure(),
            ),
            commit_record=serialized.commit_record.to_commit_record(),
        )

    def serialize(self) -> dict[str, object]:
        return _CommittedInnerDictJson.from_committed_innerdict(self).model_dump(
            mode="json"
        )

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()
