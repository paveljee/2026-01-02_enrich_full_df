from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.helpers.data_models import NameKey

from .....architecture import ControlCentreComponent, implements
from .....backend.helpers.data_models.server_event import (
    AgentRuntimeAttempt,
    RunOutcomeResponse,
)
from .run_outcome import RunOutcome

MICROSECONDS_PER_SECOND = 1_000_000


@implements[ControlCentreComponent.RunPhaseProperty]()
class RunPhase(StrEnum):
    value: Literal[
        "queued",
        "running",
        "finished",
    ]

    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"


@implements[ControlCentreComponent.RunEventKindProperty]()
class RunEventKind(StrEnum):
    value: Literal[
        "queued",
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

    QUEUED = "queued"
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


@implements[ControlCentreComponent.RunProperty]()
class Run(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )

    run_id: UUID
    namekey: NameKey
    phase: RunPhase
    outcome: RunOutcome | None = None
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


@implements[ControlCentreComponent.RunEventProperty]()
class RunEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    namekey: NameKey
    occurred_at_unix_usec: int
    kind: RunEventKind
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
