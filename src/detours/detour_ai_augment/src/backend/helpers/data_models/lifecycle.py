from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.helpers.architecture import implements


@implements[BackendComponent.LifecycleProperty]()
class BackendLifecycle(StrEnum):
    value: Literal[
        "ready",
        "busy",
        "configuration",
        "appendwatch_report_validation",
        "rollout_index",
        "pydantic_validation",
        "duckdb_evidence_validation",
        "researcher_resolution",
        "innerdict_and_card",
        "accepted",
        "configuration_error",
        "rejected",
        "retry",
        "completed",
        "failed",
    ]

    READY = "ready"
    BUSY = "busy"
    CONFIGURATION = "configuration"
    APPENDWATCH_REPORT_VALIDATION = "appendwatch_report_validation"
    ROLLOUT_INDEX = "rollout_index"
    PYDANTIC_VALIDATION = "pydantic_validation"
    DUCKDB_EVIDENCE_VALIDATION = "duckdb_evidence_validation"
    RESEARCHER_RESOLUTION = "researcher_resolution"
    INNERDICT_AND_CARD = "innerdict_and_card"
    ACCEPTED = "accepted"
    CONFIGURATION_ERROR = "configuration_error"
    REJECTED = "rejected"
    RETRY = "retry"
    COMPLETED = "completed"
    FAILED = "failed"

    def is_post_commit_validation_stage(self) -> bool:
        return self in POST_COMMIT_VALIDATION_STAGES

    def is_post_commit_validation_result(self) -> bool:
        return self in POST_COMMIT_VALIDATION_RESULTS


POST_COMMIT_VALIDATION_STAGES: Final = frozenset({
    BackendLifecycle.CONFIGURATION,
    BackendLifecycle.APPENDWATCH_REPORT_VALIDATION,
    BackendLifecycle.ROLLOUT_INDEX,
    BackendLifecycle.PYDANTIC_VALIDATION,
    BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION,
    BackendLifecycle.RESEARCHER_RESOLUTION,
    BackendLifecycle.INNERDICT_AND_CARD,
    BackendLifecycle.ACCEPTED,
})
POST_COMMIT_VALIDATION_RESULTS: Final = frozenset({
    BackendLifecycle.ACCEPTED,
    BackendLifecycle.CONFIGURATION_ERROR,
    BackendLifecycle.REJECTED,
})
