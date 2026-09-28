from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Self

from src.detours.detour_ai_augment.protected.src.architecture import ControlCentreComponent
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (
    Locale,
)
from src.helpers.architecture import implements

if TYPE_CHECKING:
    from .run_outcome_event import RunOutcome, RunOutcomePath


@implements[ControlCentreComponent.LifecycleProperty]()
class RunLifecycle(StrEnum):
    value: Literal[
        "ready",
        "queued",
        "running",
        "started",
        "remote_pid_discovered",
        "session_discovered",
        "rollout_discovered",
        "push_accepted",
        "cancel_requested",
        "codex_exited",
        "completed",
        "failed",
        "cancelled",
    ]

    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    STARTED = "started"
    REMOTE_PID_DISCOVERED = "remote_pid_discovered"
    SESSION_DISCOVERED = "session_discovered"
    ROLLOUT_DISCOVERED = "rollout_discovered"
    PUSH_ACCEPTED = "push_accepted"
    CANCEL_REQUESTED = "cancel_requested"
    CODEX_EXITED = "codex_exited"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_run_outcome(self) -> bool:
        return self in {
            RunLifecycle.COMPLETED,
            RunLifecycle.FAILED,
            RunLifecycle.CANCELLED,
        }

    def to_run_outcome(self) -> RunOutcome:
        from .run_outcome_event import RunOutcome

        if not self.is_run_outcome():
            raise ValueError(Locale.RUN_LIFECYCLE_NOT_OUTCOME)
        return RunOutcome(self.value)

    @classmethod
    def from_run_outcome(
        cls,
        run_outcome: ControlCentreComponent.BackendPort.RunOutcomeProperty,
    ) -> Self:
        return cls(run_outcome.value)

    def to_run_outcome_path(
        self,
    ) -> RunOutcomePath:
        from .run_outcome_event import CANCELLED_PATH, COMPLETED_PATH, FAILED_PATH

        if self is RunLifecycle.COMPLETED:
            return COMPLETED_PATH
        if self is RunLifecycle.FAILED:
            return FAILED_PATH
        if self is RunLifecycle.CANCELLED:
            return CANCELLED_PATH
        raise ValueError(Locale.RUN_LIFECYCLE_NO_OUTCOME_PATH)

    @classmethod
    def from_run_outcome_path(
        cls,
        path: str,
    ) -> Self:
        from .run_outcome_event import (
            CANCELLED_PATH,
            COMPLETED_PATH,
            FAILED_PATH,
            RunOutcomePath,
        )

        try:
            run_outcome_path = RunOutcomePath(path)
        except ValueError as exc:
            raise ValueError(Locale.RUN_OUTCOME_PATH_INVALID) from exc
        if run_outcome_path is COMPLETED_PATH:
            return cls.COMPLETED
        if run_outcome_path is FAILED_PATH:
            return cls.FAILED
        if run_outcome_path is CANCELLED_PATH:
            return cls.CANCELLED
        raise ValueError(Locale.RUN_OUTCOME_PATH_INVALID)
