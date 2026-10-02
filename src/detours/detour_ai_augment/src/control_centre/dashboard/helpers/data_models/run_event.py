from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.detours.detour_ai_augment.protected.src.architecture import ControlCentreComponent
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (
    Locale,  # noqa: E501
)
from src.helpers.architecture import implements
from src.helpers.data_models import NameKey

from .lifecycle import RunLifecycle
from .run_outcome_event import RunOutcomeResponseRecord

MICROSECONDS_PER_SECOND = 1_000_000


@implements[ControlCentreComponent.RunEventProperty]()
class RunEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    occurred_at_unix_usec: int
    lifecycle: RunLifecycle
    detail: str | None = None

    @property
    def occurred_at(self) -> datetime:
        return datetime.fromtimestamp(
            self.occurred_at_unix_usec / MICROSECONDS_PER_SECOND,
            tz=timezone.utc,
        )

    @staticmethod
    def datetime_to_unix_usec(value: datetime) -> int:
        """RunEvent-wide helper to construct a Unix timestamp in usec.
        Preserves `tz_info` of the argument, so ensure it is correct.

        signed off: human"""
        if value.tzinfo is None:
            raise ValueError(Locale.RUN_EVENT_TIMEZONE_REQUIRED)
        return int(value.timestamp() * 1_000_000)


@implements[ControlCentreComponent.RunProperty]()
class Run(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )

    run_id: UUID
    namekey: NameKey
    lifecycle: RunLifecycle
    session_id: UUID | None = None
    completed_attempt_id: UUID | None = None
    remote_pid: int | None = Field(default=None, gt=0)
    events: tuple[RunEvent, ...] = ()
    run_outcome_response_record: RunOutcomeResponseRecord | None = None

    def is_queued(self) -> bool:
        return self.lifecycle is RunLifecycle.QUEUED

    def is_running(self) -> bool:
        return not self.is_queued() and not self.is_finished()

    def is_finished(self) -> bool:
        return self.lifecycle.is_run_outcome()
