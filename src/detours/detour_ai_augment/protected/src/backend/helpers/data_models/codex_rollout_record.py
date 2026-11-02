from __future__ import annotations

from collections.abc import Mapping
from typing import Self

from pydantic import Field, StrictStr, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.helpers.architecture import FrozenStrictModel, implements


class _CodexRolloutRecordSummaryJson(FrozenStrictModel):
    originator: StrictStr
    source: StrictStr
    cli_version: StrictStr
    model_provider: StrictStr
    model: StrictStr
    reasoning_effort: StrictStr
    session_id: StrictStr
    timestamp: StrictStr

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        if any(not value.strip() for value in self.model_dump().values()):
            raise ValueError(Locale.CODEX_ROLLOUT_SUMMARY_BLANK)
        return self


@implements[BackendComponent.CodexRolloutRecordProperty]()
class CodexRolloutRecord(FrozenStrictModel):
    sha256: StrictStr
    size: int = Field(ge=0)
    line_count: int = Field(ge=1)

    @classmethod
    def build_summary_json(
        cls,
        values: Mapping[str, object],
    ) -> str:
        return _CodexRolloutRecordSummaryJson.model_validate(values).model_dump_json()

    @classmethod
    def parse_summary_json(
        cls,
        value: str,
    ) -> dict[str, str]:
        summary = _CodexRolloutRecordSummaryJson.model_validate_json(value)
        return {
            "originator": summary.originator,
            "source": summary.source,
            "cli_version": summary.cli_version,
            "model_provider": summary.model_provider,
            "model": summary.model,
            "reasoning_effort": summary.reasoning_effort,
            "session_id": summary.session_id,
            "timestamp": summary.timestamp,
        }
