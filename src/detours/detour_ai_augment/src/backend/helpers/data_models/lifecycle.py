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
        "field_validation",
        "researcher_resolution",
        "standardized_submission_required",
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
    FIELD_VALIDATION = "field_validation"
    RESEARCHER_RESOLUTION = "researcher_resolution"
    STANDARDIZED_SUBMISSION_REQUIRED = "standardized_submission_required"
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
    BackendLifecycle.FIELD_VALIDATION,
    BackendLifecycle.RESEARCHER_RESOLUTION,
    BackendLifecycle.STANDARDIZED_SUBMISSION_REQUIRED,
    BackendLifecycle.INNERDICT_AND_CARD,
    BackendLifecycle.ACCEPTED,
})
POST_COMMIT_VALIDATION_RESULTS: Final = frozenset({
    BackendLifecycle.ACCEPTED,
    BackendLifecycle.CONFIGURATION_ERROR,
    BackendLifecycle.REJECTED,
})
