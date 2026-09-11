from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.helpers.architecture import implements
from src.helpers.data_models import NameKey

from src.detours.detour_ai_augment.protected.src.architecture import (
    ControlCentreComponent,
)
from .....backend.helpers.data_models.query_response import AgentRuntimeAttempt
from .....backend.helpers.data_models.run_outcome_response import RunOutcomeResponse
from .run_outcome import RunLifecycle

MICROSECONDS_PER_SECOND = 1_000_000


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
    run_outcome: RunLifecycle | None = None
    events: tuple[RunEvent, ...] = ()
    attempts: tuple[AgentRuntimeAttempt, ...] = ()
    run_outcome_record: RunOutcomeResponse | None = None

    queued_at: datetime
    started_at: datetime | None = None
    session_id: UUID | None = None
    session_timestamp: datetime | None = None
    rollout_jsonl: PurePosixPath | None = None
    remote_pid: int | None = Field(default=None, gt=0)
    accepted_commit_record_id: UUID | None = None
    accepted_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    codex_exit_code: int | None = None
    exited_at: datetime | None = None
    failure_detail: str | None = None
    dashboard_owned: bool = True

    def is_queued(self) -> bool:
        return self.lifecycle is RunLifecycle.QUEUED and self.run_outcome is None

    def is_running(self) -> bool:
        return self.lifecycle is not RunLifecycle.QUEUED and self.run_outcome is None

    def is_finished(self) -> bool:
        return self.run_outcome is not None


@implements[ControlCentreComponent.RunEventProperty]()
class RunEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    namekey: NameKey
    occurred_at_unix_usec: int
    lifecycle: RunLifecycle
    session_id: UUID | None = None
    rollout_jsonl: str | None = None
    remote_pid: int | None = Field(default=None, gt=0)
    accepted_commit_record_id: UUID | None = None
    codex_exit_code: int | None = None
    detail: str | None = None

    @property
    def occurred_at(self) -> datetime:
        return datetime.fromtimestamp(
            self.occurred_at_unix_usec / MICROSECONDS_PER_SECOND,
            tz=timezone.utc,
        )
