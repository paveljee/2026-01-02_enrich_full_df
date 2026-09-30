from __future__ import annotations

import json
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, Self
from uuid import UUID

from pydantic import (
    model_serializer,
    model_validator,
)

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models import (
    InnerDict,
    NameKey,
)
from src.helpers.vars import (
    KTP_NAMEKEY_COL,
)

from ....control_centre.dashboard.helpers.data_models.run_outcome_event import (
    RunOutcome,
    RunOutcomeResponseRecord,
)
from .commit_request import (
    CodexRolloutRecord,
)


class _CodexInnerDictProcedure:
    dataset_id_field = KTP_NAMEKEY_COL


class _CodexInnerDictJson(FrozenStrictModel):
    innerdict: dict[str, Any]
    run_outcome_response_record: dict[str, object]

    @classmethod
    def from_codex_innerdict(cls, value: CodexInnerDict) -> Self:
        return cls(
            innerdict=value.innerdict.data,
            run_outcome_response_record=value.run_outcome_response_record.serialize(),
        )


@implements[BackendComponent.CodexInnerDictProperty]()
class CodexInnerDict(FrozenStrictModel):
    innerdict: InnerDict
    run_outcome_response_record: RunOutcomeResponseRecord

    def text(self, column: str) -> str | None:
        value = self.innerdict.data.get(column)
        if value is not None and not isinstance(value, str):
            raise ValueError(Locale.CODEX_INNERDICT_TEXT_INVALID)
        return value

    def _required_text(self, column: str) -> str:
        value = self.text(column)
        if value is None:
            raise ValueError(Locale.CODEX_INNERDICT_REQUIRED_TEXT_MISSING)
        return value

    def validate_codex_innerdict(self) -> Self:
        stored_namekey = NameKey.from_json_key(self._required_text(KTP_NAMEKEY_COL))
        outcome = self.run_outcome_response_record
        if (
            outcome.response_code != HTTPStatus.OK
            or outcome.run_outcome_request_record.run_outcome is not RunOutcome.COMPLETED
            or outcome.run_outcome_request_record.namekey != stored_namekey
        ):
            raise ValueError(Locale.INNERDICT_OUTCOME_MISMATCH)
        session_id = outcome._codex_session_record().session_id
        if session_id is None:
            raise ValueError(Locale.INNERDICT_OUTCOME_MISMATCH)
        summary = CodexRolloutRecord.parse_summary_json(
            self._required_text(KTP_AI_AUGMENT_SESSION_METADATA_COL)
        )
        if UUID(summary["session_id"]) != session_id:
            raise ValueError(Locale.INNERDICT_OUTCOME_MISMATCH)
        return self

    @model_validator(mode="after")
    def _validate_codex_innerdict(self) -> Self:
        return self.validate_codex_innerdict()

    @classmethod
    def from_serialized(cls, value: Mapping[str, object]) -> Self:
        serialized = _CodexInnerDictJson.model_validate_json(json.dumps(value))
        return cls(
            innerdict=InnerDict.from_mapping(
                serialized.innerdict,
                _CodexInnerDictProcedure(),
            ),
            run_outcome_response_record=RunOutcomeResponseRecord.from_serialized_json(
                value=json.dumps(serialized.run_outcome_response_record),
            ),
        )

    def serialize(self) -> dict[str, object]:
        return _CodexInnerDictJson.from_codex_innerdict(self).model_dump(
            mode="json"
        )

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()
