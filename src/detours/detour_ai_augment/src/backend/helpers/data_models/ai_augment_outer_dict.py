from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_serializer,
    model_validator,
)

from src.helpers.architecture import implements
from src.helpers.data_models import (
    HttpRequestLogRecord,
    InnerDict,
    NameKey,
    RegisteredResource,
)
from src.helpers.procedures import (
    DocxMatchProcedure,
    ParquetMatchProcedure,
    XlsxMatchProcedure,
)
from src.helpers.vars import DRAW_LABEL, KTP_NAMEKEY_COL

from ....architecture import BackendComponent
from ....control_centre.dashboard.helpers.data_models.run_outcome import (
    NAME_KEY_HEADER,
    name_key_from_header_value,
)
from ..vars import (
    KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL,
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
)
from .ai_augment_config import AiAugmentDetourConfig
from .server_event import (
    AgentRuntimeAttempt,
    BackendCommitRecord,
    CodexRolloutRecord,
    CodexSessionRecord,
    CommitRequestBody,
    PostCommitValidation,
    RunOutcomeResponse,
)


class _CodexInnerDictProcedure:
    dataset_id_field = KTP_NAMEKEY_COL


class _BackendCommitRecordJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

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


class _CommittedInnerDictJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

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
class CommittedInnerDict(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        strict=True,
    )

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


class _AiAugmentOuterDictJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    namekey: NameKey
    xlsx_innerdicts: tuple[dict[str, Any], ...]
    ssn_innerdicts: tuple[dict[str, Any], ...]
    docx_innerdicts: tuple[dict[str, Any], ...]
    committed_innerdicts: tuple[_CommittedInnerDictJson, ...]
    ai_augment_rnd: int = Field(ge=1)
    ai_augment_cohort: AiAugmentCohort
    ai_augment_ineligibility_category: AiAugmentIneligibilityCategory | None

    @classmethod
    def from_ai_augment_outerdict(cls, value: AiAugmentOuterDict) -> Self:
        return cls(
            namekey=value.namekey,
            xlsx_innerdicts=tuple(
                innerdict.data for innerdict in value.xlsx_innerdicts
            ),
            ssn_innerdicts=tuple(
                innerdict.data for innerdict in value.ssn_innerdicts
            ),
            docx_innerdicts=tuple(
                innerdict.data for innerdict in value.docx_innerdicts
            ),
            committed_innerdicts=tuple(
                _CommittedInnerDictJson.from_committed_innerdict(innerdict)
                for innerdict in value.committed_innerdicts
            ),
            ai_augment_rnd=value.ai_augment_rnd,
            ai_augment_cohort=value.ai_augment_cohort,
            ai_augment_ineligibility_category=(
                value.ai_augment_ineligibility_category
            ),
        )


@implements[BackendComponent.ControlCentrePort.AiAugmentOuterDictProperty]()
class AiAugmentOuterDict(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )

    namekey: NameKey
    xlsx_innerdicts: tuple[InnerDict, ...]
    ssn_innerdicts: tuple[InnerDict, ...]
    docx_innerdicts: tuple[InnerDict, ...]
    committed_innerdicts: tuple[CommittedInnerDict, ...] = ()
    ai_augment_rnd: int = Field(ge=1)
    ai_augment_cohort: AiAugmentCohort
    ai_augment_ineligibility_category: AiAugmentIneligibilityCategory | None = None

    @property
    def draw_numbers(self) -> tuple[str, ...]:
        return tuple(
            sorted({
                str(value).strip()
                for innerdict in (
                    *self.xlsx_innerdicts,
                    *self.ssn_innerdicts,
                    *self.docx_innerdicts,
                )
                if (value := innerdict.data.get(DRAW_LABEL)) is not None
                and str(value).strip()
            })
        )

    @property
    def draw_number(self) -> str:
        return ", ".join(self.draw_numbers)

    def validate_ai_augment_outerdict(self) -> Self:
        if (
            self.ai_augment_cohort is AiAugmentCohort.INELIGIBLE
        ) is not (self.ai_augment_ineligibility_category is not None):
            raise ValueError("AI augment eligibility classification is inconsistent")
        if not self.xlsx_innerdicts:
            raise ValueError("AI augment XLSX source rows are missing")
        commit_ids = tuple(
            committed.commit_record.record_id
            for committed in self.committed_innerdicts
        )
        if len(set(commit_ids)) != len(commit_ids):
            raise ValueError("AI augment committed innerdict IDs are duplicated")
        if commit_ids != tuple(sorted(commit_ids, key=lambda value: value.int)):
            raise ValueError("AI augment committed innerdicts are not ordered")
        for committed in self.committed_innerdicts:
            committed_namekey = name_key_from_header_value(
                committed.commit_record.request_headers.get(NAME_KEY_HEADER)
            )
            if committed_namekey != self.namekey:
                raise ValueError("AI augment committed innerdict has another namekey")
        return self

    @model_validator(mode="after")
    def _validate_ai_augment_outerdict(self) -> Self:
        return self.validate_ai_augment_outerdict()

    @classmethod
    def from_serialized(cls, value: Mapping[str, object]) -> Self:
        serialized = _AiAugmentOuterDictJson.model_validate_json(json.dumps(value))
        return cls(
            namekey=serialized.namekey,
            xlsx_innerdicts=tuple(
                InnerDict.from_mapping(innerdict, XlsxMatchProcedure())
                for innerdict in serialized.xlsx_innerdicts
            ),
            ssn_innerdicts=tuple(
                InnerDict.from_mapping(innerdict, ParquetMatchProcedure())
                for innerdict in serialized.ssn_innerdicts
            ),
            docx_innerdicts=tuple(
                InnerDict.from_mapping(innerdict, DocxMatchProcedure())
                for innerdict in serialized.docx_innerdicts
            ),
            committed_innerdicts=tuple(
                CommittedInnerDict.from_serialized(innerdict.model_dump(mode="json"))
                for innerdict in serialized.committed_innerdicts
            ),
            ai_augment_rnd=serialized.ai_augment_rnd,
            ai_augment_cohort=serialized.ai_augment_cohort,
            ai_augment_ineligibility_category=(
                serialized.ai_augment_ineligibility_category
            ),
        )

    def serialize(self) -> dict[str, object]:
        return _AiAugmentOuterDictJson.from_ai_augment_outerdict(self).model_dump(
            mode="json"
        )

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()
