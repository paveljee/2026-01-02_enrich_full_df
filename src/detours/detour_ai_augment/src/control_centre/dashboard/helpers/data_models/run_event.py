from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RunEventKind(StrEnum):
    QUEUED = "queued"
    STARTED = "started"
    REMOTE_PID_DISCOVERED = "remote_pid_discovered"
    SESSION_DISCOVERED = "session_discovered"
    ROLLOUT_DISCOVERED = "rollout_discovered"
    PUSH_ACCEPTED = "push_accepted"
    CANCEL_REQUESTED = "cancel_requested"
    CODEX_EXITED = "codex_exited"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELED = "canceled"


class RunEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: UUID
    namekey: str
    at: datetime
    kind: RunEventKind
    session_id: str | None = None
    rollout_jsonl: str | None = None
    remote_pid: int | None = Field(default=None, gt=0)
    accepted_attempt_id: str | None = None
    codex_exit_code: int | None = None
    detail: str | None = None
