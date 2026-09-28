from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import UUID

from nicegui import app
from pydantic import ValidationError

from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (
    Locale,
)

from .dashboard_query_snapshot import DashboardQuerySnapshot
from .run_event import Run, RunEvent

QUEUE_STORAGE_KEY = "detour_ai_augment_queue"
RUN_EVENTS_STORAGE_KEY = "detour_ai_augment_run_events"
RUNS_STORAGE_KEY = "detour_ai_augment_runs"
BACKEND_DATABASE_STORAGE_KEY = "detour_ai_augment_backend_database"


class AiAugmentDashboardStorage:
    """The only Dashboard accessor to NiceGUI general storage; retains existing formats."""

    def load_query_snapshot(self) -> DashboardQuerySnapshot | None:
        raw = app.storage.general.get(BACKEND_DATABASE_STORAGE_KEY)
        if raw is None:
            return None
        try:
            return DashboardQuerySnapshot.from_serialized_json(json.dumps(raw))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(Locale.BACKEND_DATABASE_RESPONSE_INVALID) from exc

    def replace_query_snapshot(self, snapshot: DashboardQuerySnapshot) -> DashboardQuerySnapshot:
        app.storage.general[BACKEND_DATABASE_STORAGE_KEY] = snapshot.model_dump(mode="json")
        return snapshot

    def load_run_events(self) -> list[RunEvent]:
        raw = app.storage.general.get(RUN_EVENTS_STORAGE_KEY, [])
        if not isinstance(raw, list):
            raise RuntimeError(Locale.JOURNAL_STORAGE_INVALID)
        try:
            return [RunEvent.model_validate(value) for value in raw]
        except ValidationError as exc:
            raise RuntimeError(Locale.JOURNAL_STORAGE_INVALID) from exc

    def save_run_events(self, events: Sequence[RunEvent]) -> None:
        serialized = [event.model_dump(mode="json") for event in events]
        app.storage.general[RUN_EVENTS_STORAGE_KEY] = serialized

    def load_runs(self) -> dict[UUID, Run]:
        raw = app.storage.general.get(RUNS_STORAGE_KEY, [])
        if not isinstance(raw, list):
            raise RuntimeError(Locale.JOURNAL_STORAGE_INVALID)
        try:
            runs = tuple(Run.model_validate_json(json.dumps(value)) for value in raw)
        except ValidationError as exc:
            raise RuntimeError(Locale.JOURNAL_STORAGE_INVALID) from exc
        if len({run.run_id for run in runs}) != len(runs):
            raise RuntimeError(Locale.JOURNAL_DUPLICATE_RUN_ID)
        return {run.run_id: run for run in runs}

    def save_runs(self, runs: Sequence[Run]) -> None:
        app.storage.general[RUNS_STORAGE_KEY] = [run.model_dump(mode="json") for run in runs]

    def load_queue(self) -> list[UUID]:
        raw = app.storage.general.get(QUEUE_STORAGE_KEY, [])
        if not isinstance(raw, list) or any(not isinstance(value, str) for value in raw):
            raise RuntimeError(Locale.JOURNAL_STORAGE_INVALID)
        try:
            return [UUID(value) for value in raw]
        except ValueError as exc:
            raise RuntimeError(Locale.JOURNAL_STORAGE_INVALID) from exc

    def save_queue(self, run_ids: Sequence[UUID]) -> None:
        app.storage.general[QUEUE_STORAGE_KEY] = [str(run_id) for run_id in run_ids]
