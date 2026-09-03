from __future__ import annotations

import argparse
import asyncio
import contextlib
import http.client
import json
import os
import re
import shlex
import socket
import sys
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Final, NewType
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlencode
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import duckdb
from fastapi import status
from nicegui import app, ui
from pydantic import ValidationError

from src.helpers.vars import (
    DRAW_LABEL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
)

from ...backend.api import (
    APPENDWATCH_REPORT_ENV_NAME,
    ATTEMPT_RESULT_ACCEPTED,
    ATTEMPT_RESULT_CONFIGURATION_ERROR,
    ATTEMPT_RESULT_REJECTED,
    CODEX_SESSIONS_ROOT_ENV_NAME,
    CONFIG_OPTION,
    CONTROL_PARENT_PID_ENV_NAME,
    DASHBOARD_QUERY_PATH,
    DASHBOARD_SOCKET_PATH,
    DASHBOARD_SOCKET_PATH_ENV_NAME,
    DOCX_TO_AI_AUGMENT_COLUMNS,
    DRAW_VALUE_SEPARATOR,
    EXPECTED_GROUND_TRUTH_RESEARCHERS,
    EXPECTED_INELIGIBILITY_COUNTS,
    EXPECTED_INELIGIBLE_RESEARCHERS,
    EXPECTED_NO_GROUND_TRUTH_RESEARCHERS,
    EXPECTED_SOURCE_RESEARCHERS,
    HTTP_GET_METHOD,
    NAMEKEY_ENV_NAME,
    SERVER_PORT,
    AttemptRecord,
    DashboardQueryResponse,
    IneligibilityCategory,
    ground_truth_for_researcher,
    load_source_researcher,
)
from ...backend.api import (
    SourceCohort as ResearcherCohort,
)
from ...backend.helpers.data_models.pydantic_to_paste import EXPORT_OPENALEX_API_KEY
from ...backend.helpers.vars import (
    AI_AUGMENT_COLUMN_PREFIX,
    KTP_AI_AUGMENT_ATTEMPT_ID_COL,
    KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL,
    KTP_AI_AUGMENT_FOOTNOTES_COL,
)
from .helpers.aggrid import AgGrid
from .helpers.data_models.ai_augment_context import (
    AiAugmentCtlCtrContext,
)
from .helpers.data_models.run_event import RunEvent, RunEventKind
from .helpers.locale import Locale
from .helpers.vars import (
    AIVM_SSH_CONNECTION_COMMAND,
    AIVM_SSH_FORWARD_COMMAND,
    AIVM_SSH_TARGET,
    BACKEND_MODULE,
    BACKEND_OPENAPI_URL,
    BACKEND_PULL_URL,
    BACKEND_READY_POLL_SECONDS,
    BACKEND_READY_TIMEOUT_SECONDS,
    CHROME_DEVTOOLS_PATH,
    CODEX_CANCEL_TIMEOUT_SECONDS,
    CODEX_DISCOVERY_POLL_SECONDS,
    CODEX_DISCOVERY_TIMEOUT_SECONDS,
    CODEX_ENV_EXPORT_TEMPLATE,
    CODEX_ENV_PATH,
    CODEX_EXEC_COMMAND,
    CODEX_INPUT_TEMPLATE,
    CODEX_REMOTE_BUSY_COMMAND,
    CODEX_REMOTE_BUSY_MARKER,
    CODEX_REMOTE_EXEC_COMMAND_TEMPLATE,
    CODEX_REMOTE_FIND_NEW_ROLLOUT_COMMAND_TEMPLATE,
    CODEX_REMOTE_FIND_ROLLOUT_COMMAND_TEMPLATE,
    CODEX_REMOTE_FIRST_LINE_COMMAND_TEMPLATE,
    CODEX_REMOTE_KILL_SIGNAL,
    CODEX_REMOTE_PID_READ_COMMAND_TEMPLATE,
    CODEX_REMOTE_PREPARE_RUN_COMMAND_TEMPLATE,
    CODEX_REMOTE_PROCESS_ALIVE_COMMAND_TEMPLATE,
    CODEX_REMOTE_PROCESS_ALIVE_MARKER,
    CODEX_REMOTE_SIGNAL_COMMAND_TEMPLATE,
    CODEX_REMOTE_TERMINATE_SIGNAL,
    CODEX_REMOTE_WRITE_FILE_COMMAND_TEMPLATE,
    CODEX_ROLLOUT_FILENAME_TEMPLATE,
    CODEX_RUN_MARKER_TEMPLATE,
    CODEX_RUN_PID_TEMPLATE,
    CODEX_SESSIONS_ROOT,
    CODEX_WORKDIR,
    CONTROL_CENTRE_BASE_URL,
    CONTROL_CENTRE_HOST,
    CONTROL_CENTRE_PORT,
    CONTROL_HTTP_TIMEOUT_SECONDS,
    DEFAULT_CONFIG_PATH,
    PROCESS_STOP_TIMEOUT_SECONDS,
    REPOSITORY_ROOT,
    TEXT_DECODE_ERROR_POLICY,
    TEXT_ENCODING,
)


class NiceGui:
    TABLE_COLUMN_NAME: Final = "name"
    TABLE_COLUMN_LABEL: Final = "label"
    TABLE_COLUMN_FIELD: Final = "field"
    TABLE_COLUMN_ALIGN: Final = "align"
    TABLE_COLUMN_SORTABLE: Final = "sortable"
    TABLE_LEFT_ALIGNMENT: Final = "left"
    MOUSE_DOWN_EVENT: Final = "mousedown"
    PRESERVE_SELECTION_HANDLER: Final = "event => event.preventDefault()"
    CLEARABLE_PROP: Final = "clearable"
    TEST_ID_PROP_TEMPLATE: Final = "data-testid={test_id}"


# =============================================================================
# Paths / process configuration
# =============================================================================


BACKEND_COMMAND_PREFIX: Final = (
    sys.executable,
    "-m",
    BACKEND_MODULE,
    CONFIG_OPTION,
)
BACKEND_PORT: Final = SERVER_PORT

QUEUE_STORAGE_KEY: Final = "detour_ai_augment_queue"
RUN_EVENTS_STORAGE_KEY: Final = "detour_ai_augment_run_events"

LIMA_APPENDWATCH_REPORT_PARAM: Final = APPENDWATCH_REPORT_ENV_NAME

FOOTNOTE_MARKER = re.compile(r"\^(?P<numbers>[0-9]+(?:,[0-9]+)*)\^")
UI_REFRESH_SECONDS: Final = 1
GRID_ROW_ID_FIELD: Final = "row_id"
GRID_NAMEKEY_FIELD: Final = KTP_NAMEKEY_COL
COMPACT_LINE_HEIGHT: Final = 1.25
CARD_PARAGRAPH_MARGIN_REM: Final = 0
FULL_WIDTH_STYLE: Final = "width: 100%; max-width: 100%; min-width: 0; box-sizing: border-box;"
PAGE_CONTAINER_STYLE: Final = f"{FULL_WIDTH_STYLE} align-items: stretch;"
RESPONSIVE_ROW_STYLE: Final = f"{FULL_WIDTH_STYLE} flex-wrap: wrap; align-items: center;"
GRID_STYLE: Final = f"{FULL_WIDTH_STYLE} height: 60vh; min-height: 24rem; overflow: hidden;"
CARD_CONTAINER_STYLE: Final = f"{FULL_WIDTH_STYLE} overflow: hidden;"
CARD_MARKDOWN_STYLE: Final = (
    f"{FULL_WIDTH_STYLE} overflow-wrap: anywhere; word-break: break-word; "
    f"line-height: {COMPACT_LINE_HEIGHT};"
)
ATTEMPT_HISTORY_STYLE: Final = f"{FULL_WIDTH_STYLE} overflow: hidden;"
ATTEMPT_HISTORY_TABLE_STYLE: Final = (
    f"{FULL_WIDTH_STYLE} overflow-wrap: anywhere; word-break: break-word;"
)
ATTEMPT_HISTORY_TABLE_PROPS: Final = "flat bordered wrap-cells"
ACTION_BUTTON_STYLE: Final = "min-width: 10rem;"
GRID_DRAW_COLUMN_WIDTH: Final = 110
GRID_RND_COLUMN_WIDTH: Final = 90
GRID_NAME_COLUMN_WIDTH: Final = 150
GRID_COHORT_COLUMN_WIDTH: Final = 150
GRID_INELIGIBILITY_COLUMN_WIDTH: Final = 260
GRID_CONTENT_COLUMN_WIDTH: Final = 320
GRID_ATTEMPT_COLUMN_WIDTH: Final = 190
GRID_TIME_COLUMN_WIDTH: Final = 180
GRID_STATUS_COLUMN_WIDTH: Final = 110
DRAW_PILOT_PREFIX: Final = "pilot."
NATURAL_SORT_PART = re.compile(r"\d+|\D+")
ACTION_LABEL_BY_VALUE: Final = {
    "queue": Locale.ACTION_QUEUE,
    "cancel": Locale.ACTION_CANCEL,
    "rerun": Locale.ACTION_RERUN,
    "disabled": Locale.ACTION_DISABLED,
}
GRID_RUN_ID_FIELD: Final = "run_id"
GRID_RND_FIELD: Final = "rnd"
GRID_DRAW_FIELD: Final = "draw_number"
GRID_FIRST_NAME_FIELD: Final = "first_name"
GRID_LAST_NAME_FIELD: Final = "last_name"
GRID_COHORT_FIELD: Final = "cohort"
GRID_INELIGIBILITY_FIELD: Final = "ineligibility_category"
GRID_AI_VALUE_FIELD: Final = "ai_value"
GRID_TABLE_1_VALUE_FIELD: Final = "table_1_value"
GRID_FOOTNOTES_FIELD: Final = "footnotes"
GRID_FOOTNOTE_ARGUMENTS_FIELD: Final = "footnote_arguments"
GRID_ATTEMPT_ID_FIELD: Final = "attempt_id"
GRID_ATTEMPT_TIMESTAMP_FIELD: Final = "attempt_timestamp"
GRID_STATUS_FIELD: Final = "status"
GRID_ACTION_FIELD: Final = "action"
PAGE_CONTAINER_TEST_ID: Final = "page-container"
PAGE_HEADER_TEST_ID: Final = "page-header"
PAGE_SUMMARY_TEST_ID: Final = "page-summary"
PAGE_FILTERS_TEST_ID: Final = "page-filters"
RESEARCHER_GRID_TEST_ID: Final = "researcher-grid"
ACTION_PANEL_TEST_ID: Final = "action-panel"
EXECUTE_ACTION_TEST_ID: Final = "execute-action"
VIEW_CARD_TEST_ID: Final = "view-researcher-card"
ATTEMPT_HISTORY_PANEL_TEST_ID: Final = "attempt-history-panel"
ATTEMPT_HISTORY_TABLE_TEST_ID: Final = "attempt-history-table"
PAGE_FOOTER_TEST_ID: Final = "page-footer"
CARD_RESPONSIVE_CSS: Final = f"""
[data-testid=\"{RESEARCHER_GRID_TEST_ID}\"] .ag-cell-value {{
    line-height: {COMPACT_LINE_HEIGHT};
}}
[data-testid=\"{PAGE_FOOTER_TEST_ID}\"] p {{
    margin-block: {CARD_PARAGRAPH_MARGIN_REM}rem;
    line-height: {COMPACT_LINE_HEIGHT};
}}
[data-testid=\"{PAGE_FOOTER_TEST_ID}\"] .nicegui-markdown {{
    white-space: normal;
}}
[data-testid=\"{PAGE_FOOTER_TEST_ID}\"] .nicegui-markdown *,
[data-testid=\"{PAGE_FOOTER_TEST_ID}\"] pre,
[data-testid=\"{PAGE_FOOTER_TEST_ID}\"] code {{
    max-width: 100%;
    overflow-wrap: anywhere;
    word-break: break-word;
}}
[data-testid=\"{PAGE_FOOTER_TEST_ID}\"] pre,
[data-testid=\"{PAGE_FOOTER_TEST_ID}\"] code {{
    white-space: pre-wrap;
}}
"""

# =============================================================================
# Strong-ish scalar identities
# =============================================================================

Namekey = NewType("Namekey", str)
SessionId = NewType("SessionId", str)
AttemptId = NewType("AttemptId", str)
RemotePid = NewType("RemotePid", int)


def emit_log(prefix: str, message: str) -> None:
    print(f"{prefix} {message}", flush=True)


def natural_sort_tokens(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in NATURAL_SORT_PART.findall(value)
    )


def draw_sort_key(
    value: str,
) -> tuple[int, tuple[tuple[int, int | str], ...], str]:
    raw = value.strip()
    normalized = raw.casefold()
    if normalized.startswith(DRAW_PILOT_PREFIX):
        return (0, natural_sort_tokens(normalized.removeprefix(DRAW_PILOT_PREFIX)), normalized)
    if raw:
        group = 1 if raw.isdigit() else 2
        return (group, natural_sort_tokens(normalized), normalized)
    return (3, (), normalized)


def researcher_sort_key(
    researcher: Researcher,
) -> tuple[
    tuple[tuple[int, tuple[tuple[int, int | str], ...], str], ...],
    str,
    str,
    Namekey,
]:
    return (
        tuple(draw_sort_key(draw) for draw in researcher.draw_numbers),
        researcher.first_name.casefold(),
        researcher.last_name.casefold(),
        researcher.namekey,
    )


def nicegui_table_column(
    *,
    field: str,
    label: str,
) -> dict[str, object]:
    return {
        NiceGui.TABLE_COLUMN_NAME: field,
        NiceGui.TABLE_COLUMN_LABEL: label,
        NiceGui.TABLE_COLUMN_FIELD: field,
        NiceGui.TABLE_COLUMN_ALIGN: NiceGui.TABLE_LEFT_ALIGNMENT,
        NiceGui.TABLE_COLUMN_SORTABLE: True,
    }


# =============================================================================
# Variable selection
# =============================================================================


@dataclass(frozen=True, slots=True)
class VariableSpec:
    key: str
    ai_column: str
    table_1_column: str


VARIABLE_SPECS: Final[tuple[VariableSpec, ...]] = tuple(
    VariableSpec(
        key=ai_column.removeprefix(AI_AUGMENT_COLUMN_PREFIX),
        ai_column=ai_column,
        table_1_column=table_1_column,
    )
    for table_1_column, ai_column in DOCX_TO_AI_AUGMENT_COLUMNS
)

VARIABLE_SPEC_BY_KEY: Final = {variable.key: variable for variable in VARIABLE_SPECS}


# =============================================================================
# Enumerations
# =============================================================================


class RunStatus(StrEnum):
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELED = "canceled"


LIVE_RUN_STATUSES: Final = frozenset({RunStatus.QUEUED, RunStatus.RUNNING})
ARCHIVED_ATTEMPT_STATUS_BY_RESULT: Final = {
    ATTEMPT_RESULT_ACCEPTED: RunStatus.COMPLETE,
    ATTEMPT_RESULT_CONFIGURATION_ERROR: RunStatus.FAILED,
    ATTEMPT_RESULT_REJECTED: RunStatus.FAILED,
}


class BackendStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


class RunAction(StrEnum):
    QUEUE = "queue"
    CANCEL = "cancel"
    RERUN = "rerun"
    DISABLED = "disabled"


# =============================================================================
# Source / database domain models
# =============================================================================


@dataclass(frozen=True, slots=True)
class Researcher:
    namekey: Namekey
    rnd: int
    draw_numbers: tuple[str, ...]
    first_name: str
    last_name: str
    cohort: ResearcherCohort
    ineligibility_category: IneligibilityCategory | None = None

    @property
    def draw_number(self) -> str:
        return DRAW_VALUE_SEPARATOR.join(self.draw_numbers)


@dataclass(frozen=True, slots=True)
class GroundTruthRecord:
    namekey: Namekey
    values: Mapping[str, str | None]


@dataclass(frozen=True, slots=True)
class SessionMetadata:
    originator: str
    source: str
    cli_version: str
    model_provider: str
    model: str
    reasoning_effort: str
    session_id: SessionId
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class AcceptedAttempt:
    namekey: Namekey
    attempt_id: AttemptId
    session_metadata: SessionMetadata
    values: Mapping[str, str | None]
    footnotes: str | None
    footnote_arguments: str | None


# =============================================================================
# Dashboard-owned run history persisted in NiceGUI general storage.
# =============================================================================


@dataclass(slots=True)
class RunRecord:
    run_id: UUID
    namekey: Namekey
    status: RunStatus

    queued_at: datetime

    started_at: datetime | None = None

    session_id: SessionId | None = None
    session_timestamp: datetime | None = None
    rollout_jsonl: PurePosixPath | None = None
    remote_pid: RemotePid | None = None

    accepted_attempt_id: AttemptId | None = None
    accepted_at: datetime | None = None

    cancel_requested_at: datetime | None = None

    codex_exit_code: int | None = None
    exited_at: datetime | None = None

    failure_detail: str | None = None

    dashboard_owned: bool = True


# =============================================================================
# View models
# =============================================================================


@dataclass(frozen=True, slots=True)
class AttemptView:
    run_id: UUID
    namekey: Namekey

    status: RunStatus

    attempt_id: AttemptId | None
    session_id: SessionId | None

    timestamp: datetime | None
    ended_at: datetime | None

    accepted: AcceptedAttempt | None

    failure_detail: str | None


@dataclass(frozen=True, slots=True)
class ResearcherView:
    researcher: Researcher

    # Oldest -> newest.
    attempts: tuple[AttemptView, ...]

    # Same object as attempts[-1], or None when never attempted.
    latest_attempt: AttemptView | None

    current_status: RunStatus


@dataclass(frozen=True, slots=True)
class AttemptVariableProjection:
    run_id: UUID | None

    namekey: Namekey
    draw_number: str
    first_name: str
    last_name: str

    ai_column: str
    ai_value: str | None

    table_1_column: str
    table_1_value: str | None

    footnotes: str | None
    footnote_arguments: str | None

    attempt_id: AttemptId | None
    attempt_timestamp: datetime | None
    attempt_status: RunStatus

    action: RunAction


@dataclass(frozen=True, slots=True)
class ResearcherGridRow:
    namekey: Namekey
    rnd: int
    cohort: ResearcherCohort
    ineligibility_category: IneligibilityCategory | None

    # Collapsed row: latest attempt projection, or synthetic ready projection.
    latest: AttemptVariableProjection

    # Expanded row content: every attempt, oldest -> newest.
    attempts: tuple[AttemptVariableProjection, ...]


@dataclass(frozen=True, slots=True)
class ResearcherCardView:
    namekey: Namekey
    draw_number: str
    first_name: str
    last_name: str
    markdown: str


@dataclass(frozen=True, slots=True)
class DashboardCounts:
    total: int
    ground_truth: int
    no_ground_truth: int
    ineligible: int

    ready: int
    queued: int
    running: int
    complete: int
    failed: int
    canceled: int


@dataclass(slots=True)
class UiSelection:
    variable_key: str
    status_filter: RunStatus | None = None
    cohort_filter: ResearcherCohort | None = None
    search_text: str = ""

    selected_namekey: Namekey | None = None
    selected_run_id: UUID | None = None
    selected_action: RunAction | None = None


@dataclass(frozen=True, slots=True)
class UiSnapshot:
    counts: DashboardCounts
    rows: tuple[ResearcherGridRow, ...]
    backend_status: BackendStatus
    active_run_id: UUID | None


# =============================================================================
# Source DuckDB reads
#
# The source DB is read-only from both the backend and Control Centre and may
# therefore be consulted while an agent run is active.
# =============================================================================


class SourceRepository:
    def __init__(
        self,
        *,
        configuration: AiAugmentCtlCtrContext,
    ) -> None:
        self._configuration = configuration

    def connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(
            str(self._configuration.source_db_path),
            read_only=True,
        )

    def load_researchers(self) -> tuple[Researcher, ...]:
        result = tuple(
            Researcher(
                namekey=Namekey(source.namekey),
                rnd=source.rnd,
                draw_numbers=tuple(sorted(source.draw_numbers, key=draw_sort_key)),
                first_name=source.first_name,
                last_name=source.last_name,
                cohort=ResearcherCohort(source.cohort),
                ineligibility_category=(
                    None
                    if source.ineligibility_category is None
                    else IneligibilityCategory(source.ineligibility_category)
                ),
            )
            for source in self._configuration.source_population
        )
        result = tuple(sorted(result, key=researcher_sort_key))
        self.assert_population_invariants(result)
        return result

    def load_ground_truth(
        self,
        namekey: Namekey,
    ) -> GroundTruthRecord | None:
        connection = self.connect()
        try:
            researcher = load_source_researcher(
                connection,
                self._configuration.eligible_cohorts,
                namekey=namekey,
            )
            values = ground_truth_for_researcher(researcher)
        finally:
            connection.close()
        if values is None:
            return None
        return GroundTruthRecord(
            namekey=namekey,
            values={
                column: None if value is None else str(value) for column, value in values.items()
            },
        )

    def load_ground_truth_by_namekey(
        self,
    ) -> Mapping[Namekey, GroundTruthRecord]:
        result: dict[Namekey, GroundTruthRecord] = {}
        cohorts = self._configuration.eligible_cohorts
        connection = self.connect()
        try:
            for namekey, cohort in sorted(cohorts.items()):
                if ResearcherCohort(cohort) is not ResearcherCohort.GROUND_TRUTH:
                    continue
                researcher = load_source_researcher(
                    connection,
                    self._configuration.eligible_cohorts,
                    namekey=namekey,
                )
                values = ground_truth_for_researcher(researcher)
                if values is None:
                    raise RuntimeError(Locale.GROUND_TRUTH_MISSING)
                typed_namekey = Namekey(namekey)
                result[typed_namekey] = GroundTruthRecord(
                    namekey=typed_namekey,
                    values={
                        column: None if value is None else str(value)
                        for column, value in values.items()
                    },
                )
        finally:
            connection.close()
        return result

    def assert_population_invariants(
        self,
        researchers: Sequence[Researcher],
    ) -> None:
        namekeys = [researcher.namekey for researcher in researchers]
        ground_truth_count = sum(
            researcher.cohort is ResearcherCohort.GROUND_TRUTH for researcher in researchers
        )
        no_ground_truth_count = sum(
            researcher.cohort is ResearcherCohort.NO_GROUND_TRUTH for researcher in researchers
        )
        if len(set(namekeys)) != len(namekeys):
            raise RuntimeError(Locale.NAMEKEYS_NOT_UNIQUE)
        ineligible_count = sum(
            researcher.cohort is ResearcherCohort.INELIGIBLE for researcher in researchers
        )
        ineligibility_counts = Counter(
            researcher.ineligibility_category
            for researcher in researchers
            if researcher.ineligibility_category is not None
        )
        if (
            ground_truth_count,
            no_ground_truth_count,
            ineligible_count,
            len(researchers),
        ) != (
            EXPECTED_GROUND_TRUTH_RESEARCHERS,
            EXPECTED_NO_GROUND_TRUTH_RESEARCHERS,
            EXPECTED_INELIGIBLE_RESEARCHERS,
            EXPECTED_SOURCE_RESEARCHERS,
        ):
            raise RuntimeError(Locale.POPULATION_INVARIANTS_FAILED)
        if ineligibility_counts != EXPECTED_INELIGIBILITY_COUNTS:
            raise RuntimeError(Locale.INELIGIBILITY_INVARIANTS_FAILED)


# =============================================================================
# Backend database IPC client
# =============================================================================


class UnixSocketHttpConnection(http.client.HTTPConnection):
    def __init__(
        self,
        *,
        socket_path: Path,
        timeout: float,
    ) -> None:
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self._socket_path))


class BackendDatabaseClient:
    def __init__(self, *, socket_path: Path) -> None:
        self._socket_path = socket_path
        self._card_cache: dict[Namekey, str] = {}

    def _request(self, *, target: str) -> bytes:
        connection = UnixSocketHttpConnection(
            socket_path=self._socket_path,
            timeout=CONTROL_HTTP_TIMEOUT_SECONDS,
        )
        try:
            connection.request(HTTP_GET_METHOD, target)
            response = connection.getresponse()
            body = response.read()
            if response.status != status.HTTP_200_OK:
                raise RuntimeError(Locale.BACKEND_DATABASE_REQUEST_FAILED)
            return body
        except (OSError, http.client.HTTPException) as exc:
            raise RuntimeError(Locale.BACKEND_DATABASE_REQUEST_FAILED) from exc
        finally:
            connection.close()

    def pull(self, namekey: Namekey | None = None) -> DashboardQueryResponse:
        target = DASHBOARD_QUERY_PATH
        if namekey is not None:
            target = f"{target}?{urlencode({KTP_NAMEKEY_COL: namekey})}"
        try:
            return DashboardQueryResponse.model_validate_json(
                self._request(target=target)
            )
        except ValidationError as exc:
            raise RuntimeError(Locale.BACKEND_DATABASE_RESPONSE_INVALID) from exc

    def card(self, namekey: Namekey) -> str:
        cached = self._card_cache.get(namekey)
        if cached is not None:
            return cached
        markdown = self.pull(namekey=namekey).card_markdown
        if markdown is None:
            raise RuntimeError(Locale.BACKEND_CARD_MISSING)
        self._card_cache[namekey] = markdown
        return markdown

# =============================================================================
# Backend event projection
# =============================================================================


def replay_run_events(events: Sequence[RunEvent]) -> Mapping[UUID, RunRecord]:
    runs: dict[UUID, RunRecord] = {}
    for event in events:
        run = runs.get(event.run_id)
        if run is None:
            if event.kind is not RunEventKind.QUEUED:
                raise RuntimeError(Locale.JOURNAL_EVENT_WITHOUT_RUN)
            run = RunRecord(
                run_id=event.run_id,
                namekey=Namekey(event.namekey),
                status=RunStatus.QUEUED,
                queued_at=event.at,
                dashboard_owned=True,
            )
            runs[event.run_id] = run
        elif run.namekey != event.namekey:
            raise RuntimeError(Locale.JOURNAL_EVENT_WITHOUT_RUN)
        elif event.kind is RunEventKind.QUEUED:
            raise RuntimeError(Locale.JOURNAL_DUPLICATE_RUN_ID)

        if event.kind is RunEventKind.STARTED:
            run.status = RunStatus.RUNNING
            run.started_at = event.at
            run.remote_pid = None if event.remote_pid is None else RemotePid(event.remote_pid)
        elif event.kind is RunEventKind.REMOTE_PID_DISCOVERED:
            if event.remote_pid is None:
                raise RuntimeError(Locale.JOURNAL_REMOTE_PID_MISSING)
            run.remote_pid = RemotePid(event.remote_pid)
        elif event.kind is RunEventKind.SESSION_DISCOVERED:
            if event.session_id is None:
                raise RuntimeError(Locale.JOURNAL_SESSION_ID_MISSING)
            run.session_id = SessionId(event.session_id)
            run.session_timestamp = event.at
        elif event.kind is RunEventKind.ROLLOUT_DISCOVERED:
            if event.rollout_jsonl is None:
                raise RuntimeError(Locale.JOURNAL_ROLLOUT_PATH_MISSING)
            run.rollout_jsonl = PurePosixPath(event.rollout_jsonl)
        elif event.kind is RunEventKind.PUSH_ACCEPTED:
            if event.accepted_attempt_id is None:
                raise RuntimeError(Locale.JOURNAL_ATTEMPT_ID_MISSING)
            run.accepted_attempt_id = AttemptId(event.accepted_attempt_id)
            run.accepted_at = event.at
        elif event.kind is RunEventKind.CANCEL_REQUESTED:
            run.cancel_requested_at = event.at
        elif event.kind is RunEventKind.CODEX_EXITED:
            run.codex_exit_code = event.codex_exit_code
            run.exited_at = event.at
        elif event.kind is RunEventKind.COMPLETE:
            run.status = RunStatus.COMPLETE
        elif event.kind is RunEventKind.FAILED:
            run.status = RunStatus.FAILED
            run.failure_detail = event.detail
        elif event.kind is RunEventKind.CANCELED:
            run.status = RunStatus.CANCELED
    return runs


# =============================================================================
# Backend process ownership
# =============================================================================


@dataclass(slots=True)
class BackendProcessHandle:
    process: asyncio.subprocess.Process
    started_at: datetime
    log_task: asyncio.Task[None]


class BackendSupervisor:
    def __init__(
        self,
        *,
        repository_root: Path,
        config_path: Path,
        openalex_api_key: str,
        appendwatch_report: Path,
        dashboard_socket_path: Path,
    ) -> None:
        self._repository_root = repository_root
        self._config_path = config_path
        self._openalex_api_key = openalex_api_key
        self._appendwatch_report = appendwatch_report
        self._dashboard_socket_path = dashboard_socket_path
        self._process: BackendProcessHandle | None = None
        self._status = BackendStatus.STOPPED

    @property
    def status(self) -> BackendStatus:
        if (
            self._process is not None
            and self._process.process.returncode is not None
            and self._status is BackendStatus.RUNNING
        ):
            self._status = BackendStatus.FAILED
        return self._status

    @property
    def process(self) -> BackendProcessHandle | None:
        return self._process

    async def start(self, *, namekey: Namekey) -> None:
        if self._process is not None:
            await self.stop()
        self._status = BackendStatus.STARTING
        process = await asyncio.create_subprocess_exec(
            *BACKEND_COMMAND_PREFIX,
            str(self._config_path),
            cwd=self._repository_root,
            env=self.environment(namekey=namekey),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        log_task = asyncio.create_task(self.forward_output(process))
        self._process = BackendProcessHandle(
            process=process,
            started_at=datetime.now(timezone.utc),
            log_task=log_task,
        )
        try:
            await self.wait_until_ready()
        except (Exception, asyncio.CancelledError):
            self._status = BackendStatus.FAILED
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(
                        process.wait(),
                        timeout=PROCESS_STOP_TIMEOUT_SECONDS,
                    )
                except TimeoutError:
                    process.kill()
                    await process.wait()
            await log_task
            raise
        self._status = BackendStatus.RUNNING

    async def forward_output(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        if process.stdout is None:
            raise RuntimeError(Locale.BACKEND_OUTPUT_PIPE_MISSING)
        async for raw_line in process.stdout:
            emit_log(
                Locale.BACKEND_LOG_PREFIX,
                raw_line.decode(
                    TEXT_ENCODING,
                    errors=TEXT_DECODE_ERROR_POLICY,
                ).rstrip(),
            )

    async def wait_until_ready(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + BACKEND_READY_TIMEOUT_SECONDS

        def request_openapi() -> None:
            request = urllib_request.Request(BACKEND_OPENAPI_URL, method=HTTP_GET_METHOD)
            with urllib_request.urlopen(
                request,
                timeout=CONTROL_HTTP_TIMEOUT_SECONDS,
            ) as response:
                if response.status != status.HTTP_200_OK:
                    raise RuntimeError(Locale.BACKEND_OPENAPI_NOT_READY)

        while loop.time() < deadline:
            if self._process is None or self._process.process.returncode is not None:
                raise RuntimeError(Locale.BACKEND_EXITED_EARLY)
            try:
                await asyncio.to_thread(request_openapi)
                break
            except (
                OSError,
                RuntimeError,
                urllib_error.URLError,
                urllib_error.HTTPError,
            ):
                await asyncio.sleep(BACKEND_READY_POLL_SECONDS)
        else:
            raise TimeoutError(Locale.BACKEND_READY_TIMEOUT)

        await self.probe_pull()
        try:
            await asyncio.to_thread(
                BackendDatabaseClient(socket_path=self._dashboard_socket_path).pull
            )
        except (OSError, RuntimeError, ValidationError) as exc:
            raise RuntimeError(Locale.BACKEND_DATABASE_REQUEST_FAILED) from exc

    async def probe_pull(self) -> None:
        def request_pull() -> None:
            request = urllib_request.Request(BACKEND_PULL_URL, method=HTTP_GET_METHOD)
            with urllib_request.urlopen(
                request,
                timeout=CONTROL_HTTP_TIMEOUT_SECONDS,
            ) as response:
                if response.status != status.HTTP_200_OK:
                    raise RuntimeError(Locale.BACKEND_PULL_NOT_READY)
                response.read()

        try:
            await asyncio.to_thread(request_pull)
        except (OSError, urllib_error.URLError, urllib_error.HTTPError) as exc:
            raise RuntimeError(Locale.BACKEND_PULL_NOT_READY) from exc

    async def stop(self) -> None:
        if self._process is None:
            self._status = BackendStatus.STOPPED
            return
        process = self._process.process
        emit_log(
            Locale.CONTROL_CENTRE_LOG_PREFIX,
            Locale.BACKEND_STOPPING_LOG_TEMPLATE.format(pid=process.pid),
        )
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=PROCESS_STOP_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
        await self._process.log_task
        emit_log(
            Locale.CONTROL_CENTRE_LOG_PREFIX,
            Locale.BACKEND_STOPPED_LOG_TEMPLATE.format(
                pid=process.pid,
                return_code=process.returncode,
            ),
        )
        self._process = None
        self._status = BackendStatus.STOPPED

    async def supply_session_id(self, session_id: SessionId) -> None:
        if self._process is None or self._process.process.returncode is not None:
            raise RuntimeError(Locale.BACKEND_NOT_RUNNING)
        stream = self._process.process.stdin
        if stream is None:
            raise RuntimeError(Locale.BACKEND_STDIN_MISSING)
        stream.write(f"{session_id}\n".encode(TEXT_ENCODING))
        await stream.drain()
        stream.close()
        await stream.wait_closed()

    async def wait(self) -> int:
        if self._process is None:
            raise RuntimeError(Locale.BACKEND_NOT_RUNNING)
        return await self._process.process.wait()

    def environment(self, *, namekey: Namekey) -> Mapping[str, str]:
        environment = os.environ.copy()
        environment[EXPORT_OPENALEX_API_KEY] = self._openalex_api_key
        environment[APPENDWATCH_REPORT_ENV_NAME] = str(self._appendwatch_report)
        environment[CONTROL_PARENT_PID_ENV_NAME] = str(os.getpid())
        environment[DASHBOARD_SOCKET_PATH_ENV_NAME] = str(self._dashboard_socket_path)
        environment[NAMEKEY_ENV_NAME] = str(namekey)
        environment[CODEX_SESSIONS_ROOT_ENV_NAME] = str(CODEX_SESSIONS_ROOT)
        return environment


# =============================================================================
# AIVM / Codex process ownership
# =============================================================================


@dataclass(slots=True)
class CodexProcessHandle:
    run_id: UUID
    process: asyncio.subprocess.Process

    remote_pid: RemotePid | None = None
    session_id: SessionId | None = None
    session_timestamp: datetime | None = None
    rollout_jsonl: PurePosixPath | None = None


@dataclass(frozen=True, slots=True)
class CodexStartResult:
    handle: CodexProcessHandle
    session_id: SessionId
    session_timestamp: datetime
    rollout_jsonl: PurePosixPath


class CodexRunner:
    def __init__(
        self,
        *,
        timezone: ZoneInfo,
        openalex_api_key: str,
        openapi_url: str = BACKEND_OPENAPI_URL,
    ) -> None:
        self._timezone = timezone
        self._openalex_api_key = openalex_api_key
        self._openapi_url = openapi_url

    def ssh_connection_command(self) -> tuple[str, ...]:
        return AIVM_SSH_CONNECTION_COMMAND

    def ssh_base_command(self) -> tuple[str, ...]:
        return AIVM_SSH_FORWARD_COMMAND

    def codex_remote_command(
        self,
        *,
        run_id: UUID,
    ) -> str:
        pid_path = CODEX_WORKDIR / CODEX_RUN_PID_TEMPLATE.format(run_id=run_id)
        return CODEX_REMOTE_EXEC_COMMAND_TEMPLATE.format(
            pid_path=shlex.quote(str(pid_path)),
            environment_path=shlex.quote(str(CODEX_ENV_PATH)),
            codex_command=shlex.join(CODEX_EXEC_COMMAND),
        )

    async def _remote_command(
        self,
        command: str,
        *,
        input_bytes: bytes | None = None,
        check: bool = True,
    ) -> bytes:
        process = await asyncio.create_subprocess_exec(
            *self.ssh_connection_command(),
            AIVM_SSH_TARGET,
            command,
            stdin=asyncio.subprocess.PIPE if input_bytes is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await process.communicate(input_bytes)
        except asyncio.CancelledError:
            await self._stop_process(process)
            raise
        if check and process.returncode != 0:
            raise RuntimeError(
                Locale.AIVM_COMMAND_FAILED_TEMPLATE.format(
                    return_code=process.returncode,
                    stderr=stderr.decode(
                        TEXT_ENCODING,
                        errors=TEXT_DECODE_ERROR_POLICY,
                    ).strip(),
                )
            )
        return stdout

    async def _write_remote_file(self, path: PurePosixPath, content: bytes) -> None:
        command = CODEX_REMOTE_WRITE_FILE_COMMAND_TEMPLATE.format(
            parent_path=shlex.quote(str(path.parent)),
            file_path=shlex.quote(str(path)),
        )
        await self._remote_command(command, input_bytes=content)

    async def is_busy(self) -> bool:
        output = await self._remote_command(CODEX_REMOTE_BUSY_COMMAND)
        return output.decode(TEXT_ENCODING) == CODEX_REMOTE_BUSY_MARKER

    async def start(
        self,
        *,
        run_id: UUID,
        on_handle: (Callable[[CodexProcessHandle], Awaitable[None]] | None) = None,
    ) -> CodexStartResult:
        environment_bytes = CODEX_ENV_EXPORT_TEMPLATE.format(
            name=EXPORT_OPENALEX_API_KEY,
            value=shlex.quote(self._openalex_api_key),
        ).encode(TEXT_ENCODING)
        await self._write_remote_file(CODEX_ENV_PATH, environment_bytes)
        marker_path = CODEX_WORKDIR / CODEX_RUN_MARKER_TEMPLATE.format(run_id=run_id)
        pid_path = CODEX_WORKDIR / CODEX_RUN_PID_TEMPLATE.format(run_id=run_id)
        await self._remote_command(
            CODEX_REMOTE_PREPARE_RUN_COMMAND_TEMPLATE.format(
                workdir=shlex.quote(str(CODEX_WORKDIR)),
                pid_path=shlex.quote(str(pid_path)),
                marker_path=shlex.quote(str(marker_path)),
            )
        )
        process = await asyncio.create_subprocess_exec(
            *self.ssh_base_command(),
            self.codex_remote_command(run_id=run_id),
            stdin=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        handle = CodexProcessHandle(run_id=run_id, process=process)
        try:
            if process.stdin is None:
                raise RuntimeError(Locale.CODEX_STDIN_UNAVAILABLE)
            process.stdin.write(
                CODEX_INPUT_TEMPLATE.format(openapi_url=self._openapi_url).encode(
                    TEXT_ENCODING
                )
            )
            await process.stdin.drain()
            process.stdin.close()
            await process.stdin.wait_closed()
            if on_handle is not None:
                await on_handle(handle)
            session_id, session_timestamp = await self.discover_session(handle)
            if on_handle is not None and handle.remote_pid is not None:
                await on_handle(handle)
            rollout_jsonl = await self.discover_rollout_path(
                session_id=session_id,
                session_timestamp=session_timestamp,
            )
        except asyncio.CancelledError:
            await self.cancel(handle)
            raise
        except Exception:
            with contextlib.suppress(Exception):
                await self.cancel(handle)
            raise
        handle.session_id = session_id
        handle.session_timestamp = session_timestamp
        handle.rollout_jsonl = rollout_jsonl
        return CodexStartResult(
            handle=handle,
            session_id=session_id,
            session_timestamp=session_timestamp,
            rollout_jsonl=rollout_jsonl,
        )

    async def discover_session(
        self,
        handle: CodexProcessHandle,
    ) -> tuple[SessionId, datetime]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CODEX_DISCOVERY_TIMEOUT_SECONDS
        marker_path = CODEX_WORKDIR / CODEX_RUN_MARKER_TEMPLATE.format(run_id=handle.run_id)
        pid_path = CODEX_WORKDIR / CODEX_RUN_PID_TEMPLATE.format(run_id=handle.run_id)
        find_command = CODEX_REMOTE_FIND_NEW_ROLLOUT_COMMAND_TEMPLATE.format(
            sessions_root=shlex.quote(str(CODEX_SESSIONS_ROOT)),
            marker_path=shlex.quote(str(marker_path)),
        )
        while loop.time() < deadline:
            pid_text = (
                (
                    await self._remote_command(
                        CODEX_REMOTE_PID_READ_COMMAND_TEMPLATE.format(
                            pid_path=shlex.quote(str(pid_path)),
                        ),
                        check=False,
                    )
                )
                .decode(TEXT_ENCODING)
                .strip()
            )
            if pid_text.isdecimal():
                handle.remote_pid = RemotePid(int(pid_text))
            rollout_text = (await self._remote_command(find_command)).decode(TEXT_ENCODING).strip()
            if rollout_text:
                rollout_path = PurePosixPath(rollout_text)
                first_line = (
                    await self._remote_command(
                        CODEX_REMOTE_FIRST_LINE_COMMAND_TEMPLATE.format(
                            rollout_path=shlex.quote(str(rollout_path))
                        )
                    )
                ).decode(TEXT_ENCODING)
                try:
                    record = json.loads(first_line)
                    payload = record["payload"]
                    session_id = SessionId(str(payload["session_id"]))
                    session_timestamp = datetime.fromisoformat(str(payload["timestamp"]))
                except KeyError, TypeError, ValueError, json.JSONDecodeError:
                    await asyncio.sleep(CODEX_DISCOVERY_POLL_SECONDS)
                    continue
                handle.rollout_jsonl = rollout_path
                return session_id, session_timestamp
            if handle.process.returncode is not None:
                raise RuntimeError(Locale.CODEX_EXITED_BEFORE_DISCOVERY)
            await asyncio.sleep(CODEX_DISCOVERY_POLL_SECONDS)
        raise TimeoutError(Locale.CODEX_SESSION_DISCOVERY_TIMEOUT)

    async def discover_rollout_path(
        self,
        *,
        session_id: SessionId,
        session_timestamp: datetime,
    ) -> PurePosixPath:
        local_timestamp = session_timestamp.astimezone(self._timezone)
        rollout_name = CODEX_ROLLOUT_FILENAME_TEMPLATE.format(
            local_timestamp=local_timestamp,
            session_id=session_id,
        )
        output = await self._remote_command(
            CODEX_REMOTE_FIND_ROLLOUT_COMMAND_TEMPLATE.format(
                sessions_root=shlex.quote(str(CODEX_SESSIONS_ROOT)),
                rollout_name=shlex.quote(rollout_name),
            )
        )
        paths = [PurePosixPath(line) for line in output.decode(TEXT_ENCODING).splitlines() if line]
        if len(paths) != 1:
            raise RuntimeError(Locale.CODEX_ROLLOUT_NOT_UNIQUE)
        return paths[0]

    async def wait(
        self,
        handle: CodexProcessHandle,
    ) -> int:
        return await handle.process.wait()

    async def cancel(
        self,
        handle: CodexProcessHandle,
    ) -> None:
        remote_error: Exception | None = None
        try:
            remote_pid = await self._remote_pid_for_cancel(handle)
            if remote_pid is not None:
                emit_log(
                    Locale.CONTROL_CENTRE_LOG_PREFIX,
                    Locale.CODEX_REMOTE_STOPPING_LOG_TEMPLATE.format(
                        run_id=handle.run_id,
                        session_id=handle.session_id,
                        remote_pid=remote_pid,
                    ),
                )
                await self.terminate_remote_pid(remote_pid)
                emit_log(
                    Locale.CONTROL_CENTRE_LOG_PREFIX,
                    Locale.CODEX_REMOTE_STOPPED_LOG_TEMPLATE.format(
                        run_id=handle.run_id,
                        remote_pid=remote_pid,
                    ),
                )
            elif handle.process.returncode is None:
                raise RuntimeError(Locale.CODEX_REMOTE_PID_MISSING)
        except Exception as exc:
            remote_error = exc
        finally:
            emit_log(
                Locale.CONTROL_CENTRE_LOG_PREFIX,
                Locale.CODEX_SSH_STOPPING_LOG_TEMPLATE.format(
                    run_id=handle.run_id,
                    pid=handle.process.pid,
                ),
            )
            await self._stop_process(handle.process)
            emit_log(
                Locale.CONTROL_CENTRE_LOG_PREFIX,
                Locale.CODEX_SSH_STOPPED_LOG_TEMPLATE.format(
                    run_id=handle.run_id,
                    pid=handle.process.pid,
                    return_code=handle.process.returncode,
                ),
            )
        if handle.process.returncode is None:
            raise RuntimeError(Locale.CODEX_SSH_DID_NOT_EXIT)
        if remote_error is not None:
            raise remote_error

    async def _remote_pid_for_cancel(
        self,
        handle: CodexProcessHandle,
    ) -> RemotePid | None:
        if handle.remote_pid is not None:
            return handle.remote_pid
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CODEX_CANCEL_TIMEOUT_SECONDS
        pid_path = CODEX_WORKDIR / CODEX_RUN_PID_TEMPLATE.format(run_id=handle.run_id)
        while loop.time() < deadline:
            pid_text = (
                (
                    await self._remote_command(
                        CODEX_REMOTE_PID_READ_COMMAND_TEMPLATE.format(
                            pid_path=shlex.quote(str(pid_path)),
                        ),
                        check=False,
                    )
                )
                .decode(TEXT_ENCODING)
                .strip()
            )
            if pid_text.isdecimal() and int(pid_text) > 0:
                handle.remote_pid = RemotePid(int(pid_text))
                return handle.remote_pid
            if handle.process.returncode is not None:
                return None
            await asyncio.sleep(CODEX_DISCOVERY_POLL_SECONDS)
        return None

    @staticmethod
    async def _stop_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=CODEX_CANCEL_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            process.kill()
            await process.wait()

    async def _remote_pid_is_alive(
        self,
        remote_pid: RemotePid,
    ) -> bool:
        output = await self._remote_command(
            CODEX_REMOTE_PROCESS_ALIVE_COMMAND_TEMPLATE.format(
                remote_pid=int(remote_pid),
                alive_marker=shlex.quote(CODEX_REMOTE_PROCESS_ALIVE_MARKER),
            ),
            check=False,
        )
        return output.decode(TEXT_ENCODING) == CODEX_REMOTE_PROCESS_ALIVE_MARKER

    async def _wait_for_remote_pid_exit(
        self,
        remote_pid: RemotePid,
    ) -> bool:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CODEX_CANCEL_TIMEOUT_SECONDS
        while loop.time() < deadline:
            if not await self._remote_pid_is_alive(remote_pid):
                return True
            await asyncio.sleep(CODEX_DISCOVERY_POLL_SECONDS)
        return not await self._remote_pid_is_alive(remote_pid)

    async def terminate_remote_pid(
        self,
        remote_pid: RemotePid,
    ) -> None:
        pid = int(remote_pid)
        if pid <= 0:
            raise ValueError(Locale.CODEX_REMOTE_PID_NOT_POSITIVE)
        await self._remote_command(
            CODEX_REMOTE_SIGNAL_COMMAND_TEMPLATE.format(
                signal=CODEX_REMOTE_TERMINATE_SIGNAL,
                remote_pid=pid,
            ),
            check=False,
        )
        if await self._wait_for_remote_pid_exit(remote_pid):
            return
        await self._remote_command(
            CODEX_REMOTE_SIGNAL_COMMAND_TEMPLATE.format(
                signal=CODEX_REMOTE_KILL_SIGNAL,
                remote_pid=pid,
            ),
            check=False,
        )
        if not await self._wait_for_remote_pid_exit(remote_pid):
            raise RuntimeError(Locale.CODEX_REMOTE_DID_NOT_EXIT)

    async def terminate_abandoned_run(self, run_id: UUID) -> None:
        pid_path = CODEX_WORKDIR / CODEX_RUN_PID_TEMPLATE.format(run_id=run_id)
        pid_text = (
            await self._remote_command(
                CODEX_REMOTE_PID_READ_COMMAND_TEMPLATE.format(
                    pid_path=shlex.quote(str(pid_path)),
                ),
                check=False,
            )
        ).decode(TEXT_ENCODING).strip()
        if not pid_text.isdecimal():
            return
        remote_pid = RemotePid(int(pid_text))
        if await self._remote_pid_is_alive(remote_pid):
            await self.terminate_remote_pid(remote_pid)


# =============================================================================
# Reconciliation of backend-projected runs and accepted output
# =============================================================================


class AttemptReconciler:
    def reconcile(
        self,
        *,
        researcher: Researcher,
        runs: Sequence[RunRecord],
        attempt_records: Sequence[AttemptRecord],
        accepted_attempts: Sequence[AcceptedAttempt],
    ) -> ResearcherView:
        accepted_by_attempt_id = {attempt.attempt_id: attempt for attempt in accepted_attempts}
        live_dashboard_run_ids = {
            run.run_id
            for run in runs
            if run.dashboard_owned and run.status in LIVE_RUN_STATUSES
        }
        attempts: list[AttemptView] = []
        for record in sorted(
            attempt_records,
            key=lambda item: (item.updated_at, item.attempt_id),
        ):
            attempt_id = AttemptId(record.attempt_id)
            accepted = accepted_by_attempt_id.pop(attempt_id, None)
            attempt_status = ARCHIVED_ATTEMPT_STATUS_BY_RESULT.get(record.result)
            if (
                attempt_status is None
                or record.run_id is None
                or record.updated_at.tzinfo is None
                or record.namekey != researcher.namekey
                or (attempt_status is RunStatus.COMPLETE) != (accepted is not None)
                or (
                    accepted is not None
                    and (
                        record.session_id is None
                        or record.session_id != accepted.session_metadata.session_id
                    )
                )
            ):
                raise RuntimeError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
            attempts.append(
                AttemptView(
                    run_id=record.run_id,
                    namekey=researcher.namekey,
                    status=attempt_status,
                    attempt_id=attempt_id,
                    session_id=(
                        accepted.session_metadata.session_id
                        if accepted is not None
                        else (
                            None
                            if record.session_id is None
                            else SessionId(record.session_id)
                        )
                    ),
                    timestamp=record.updated_at,
                    ended_at=record.updated_at,
                    accepted=accepted,
                    failure_detail=record.response_detail,
                )
            )
        for run in sorted(runs, key=lambda item: (item.queued_at, str(item.run_id))):
            if run.accepted_attempt_id in {
                attempt.attempt_id for attempt in attempts if attempt.attempt_id is not None
            }:
                continue
            attempts.append(
                AttemptView(
                    run_id=run.run_id,
                    namekey=researcher.namekey,
                    status=run.status,
                    attempt_id=run.accepted_attempt_id,
                    session_id=run.session_id,
                    timestamp=run.started_at or run.queued_at,
                    ended_at=run.exited_at,
                    accepted=None,
                    failure_detail=run.failure_detail,
                )
            )
        if accepted_by_attempt_id:
            raise RuntimeError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
        ordered = tuple(
            sorted(
                attempts,
                key=lambda attempt: (
                    attempt.run_id in live_dashboard_run_ids,
                    attempt.timestamp or datetime.min.replace(tzinfo=timezone.utc),
                    str(attempt.run_id),
                ),
            )
        )
        latest = ordered[-1] if ordered else None
        return ResearcherView(
            researcher=researcher,
            attempts=ordered,
            latest_attempt=latest,
            current_status=RunStatus.READY if latest is None else latest.status,
        )

    def reconcile_all(
        self,
        *,
        researchers: Sequence[Researcher],
        runs: Mapping[UUID, RunRecord],
        attempt_records: Mapping[Namekey, tuple[AttemptRecord, ...]],
        accepted_attempts: Mapping[Namekey, tuple[AcceptedAttempt, ...]],
    ) -> tuple[ResearcherView, ...]:
        runs_by_namekey: dict[Namekey, list[RunRecord]] = {}
        for run in runs.values():
            runs_by_namekey.setdefault(run.namekey, []).append(run)
        return tuple(
            self.reconcile(
                researcher=researcher,
                runs=runs_by_namekey.get(researcher.namekey, ()),
                attempt_records=attempt_records.get(researcher.namekey, ()),
                accepted_attempts=accepted_attempts.get(researcher.namekey, ()),
            )
            for researcher in researchers
        )


# =============================================================================
# Per-variable table projection
# =============================================================================


class VariableProjector:
    @staticmethod
    def action_for_status(
        status: RunStatus,
        *,
        eligible: bool,
        codex_busy: bool = False,
    ) -> RunAction:
        if not eligible:
            return RunAction.DISABLED
        if status in {RunStatus.QUEUED, RunStatus.RUNNING}:
            return RunAction.CANCEL
        if status is RunStatus.READY or codex_busy:
            return RunAction.QUEUE
        return RunAction.RERUN

    def project_attempt(
        self,
        *,
        researcher: Researcher,
        attempt: AttemptView,
        ground_truth: GroundTruthRecord | None,
        variable: VariableSpec,
        codex_busy: bool,
    ) -> AttemptVariableProjection:
        accepted = attempt.accepted
        return AttemptVariableProjection(
            run_id=attempt.run_id,
            namekey=researcher.namekey,
            draw_number=researcher.draw_number,
            first_name=researcher.first_name,
            last_name=researcher.last_name,
            ai_column=variable.ai_column,
            ai_value=(None if accepted is None else accepted.values.get(variable.ai_column)),
            table_1_column=variable.table_1_column,
            table_1_value=(
                None if ground_truth is None else ground_truth.values.get(variable.table_1_column)
            ),
            footnotes=(
                None
                if accepted is None
                else self.footnotes_for_variable(attempt=accepted, variable=variable)
            ),
            footnote_arguments=(
                None
                if accepted is None
                else self.footnote_arguments_for_variable(
                    attempt=accepted,
                    variable=variable,
                )
            ),
            attempt_id=attempt.attempt_id,
            attempt_timestamp=attempt.timestamp,
            attempt_status=attempt.status,
            action=self.action_for_status(
                attempt.status,
                eligible=researcher.cohort is not ResearcherCohort.INELIGIBLE,
                codex_busy=codex_busy,
            ),
        )

    def project_ready_researcher(
        self,
        *,
        researcher: Researcher,
        ground_truth: GroundTruthRecord | None,
        variable: VariableSpec,
        codex_busy: bool,
    ) -> AttemptVariableProjection:
        return AttemptVariableProjection(
            run_id=None,
            namekey=researcher.namekey,
            draw_number=researcher.draw_number,
            first_name=researcher.first_name,
            last_name=researcher.last_name,
            ai_column=variable.ai_column,
            ai_value=None,
            table_1_column=variable.table_1_column,
            table_1_value=(
                None if ground_truth is None else ground_truth.values.get(variable.table_1_column)
            ),
            footnotes=None,
            footnote_arguments=None,
            attempt_id=None,
            attempt_timestamp=None,
            attempt_status=RunStatus.READY,
            action=self.action_for_status(
                RunStatus.READY,
                eligible=researcher.cohort is not ResearcherCohort.INELIGIBLE,
                codex_busy=codex_busy,
            ),
        )

    def project_researcher(
        self,
        *,
        researcher_view: ResearcherView,
        ground_truth: GroundTruthRecord | None,
        variable: VariableSpec,
        codex_busy: bool,
    ) -> ResearcherGridRow:
        attempts = tuple(
            self.project_attempt(
                researcher=researcher_view.researcher,
                attempt=attempt,
                ground_truth=ground_truth,
                variable=variable,
                codex_busy=codex_busy,
            )
            for attempt in researcher_view.attempts
        )
        latest = (
            attempts[-1]
            if attempts
            else self.project_ready_researcher(
                researcher=researcher_view.researcher,
                ground_truth=ground_truth,
                variable=variable,
                codex_busy=codex_busy,
            )
        )
        return ResearcherGridRow(
            namekey=researcher_view.researcher.namekey,
            rnd=researcher_view.researcher.rnd,
            cohort=researcher_view.researcher.cohort,
            ineligibility_category=(researcher_view.researcher.ineligibility_category),
            latest=latest,
            attempts=attempts,
        )

    def footnotes_for_variable(
        self,
        *,
        attempt: AcceptedAttempt,
        variable: VariableSpec,
    ) -> str | None:
        numbers = self._footnote_numbers(attempt, variable)
        return self._matching_numbered_lines(attempt.footnotes, numbers)

    def footnote_arguments_for_variable(
        self,
        *,
        attempt: AcceptedAttempt,
        variable: VariableSpec,
    ) -> str | None:
        numbers = self._footnote_numbers(attempt, variable)
        return self._matching_numbered_lines(attempt.footnote_arguments, numbers)

    @staticmethod
    def _footnote_numbers(
        attempt: AcceptedAttempt,
        variable: VariableSpec,
    ) -> tuple[int, ...]:
        value = attempt.values.get(variable.ai_column)
        if value is None:
            return ()
        match = FOOTNOTE_MARKER.search(value)
        if match is None:
            return ()
        return tuple(int(number) for number in match.group("numbers").split(","))

    @staticmethod
    def _matching_numbered_lines(
        value: str | None,
        numbers: tuple[int, ...],
    ) -> str | None:
        if value is None or not numbers:
            return None
        prefixes = tuple(f"{number}. " for number in numbers)
        selected = [line for line in value.splitlines() if line.startswith(prefixes)]
        return "\n".join(selected) or None


# =============================================================================
# Main orchestration
#
# Exactly one Codex attempt may be running at a time.
#
# The dashboard owns queue/run history in NiceGUI storage. Backend owns
# attempts, accepted output, cards, the authoritative log, and the detour DB.
# =============================================================================


class ControlCentreController:
    def __init__(
        self,
        *,
        source_repository: SourceRepository,
        backend: BackendSupervisor,
        backend_database: BackendDatabaseClient,
        codex: CodexRunner,
        reconciler: AttemptReconciler,
        projector: VariableProjector,
    ) -> None:
        self._source_repository = source_repository
        self._backend = backend
        self._backend_database = backend_database
        self._codex = codex
        self._reconciler = reconciler
        self._projector = projector
        self._queue: asyncio.Queue[UUID] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._active_run_id: UUID | None = None
        self._active_codex: CodexProcessHandle | None = None
        self._external_codex_busy = False
        self._shutting_down = False
        self._idle_refresh_lock = asyncio.Lock()
        self._events: list[RunEvent] = []
        self._runs: dict[UUID, RunRecord] = {}
        self._researchers: tuple[Researcher, ...] = ()
        self._researchers_by_namekey: dict[Namekey, Researcher] = {}
        self._ground_truth: Mapping[Namekey, GroundTruthRecord] = {}
        self._attempt_records: Mapping[Namekey, tuple[AttemptRecord, ...]] = {}
        self._accepted_attempts: Mapping[Namekey, tuple[AcceptedAttempt, ...]] = {}

    @property
    def active_run_id(self) -> UUID | None:
        return self._active_run_id

    @property
    def codex_busy(self) -> bool:
        return self._active_run_id is not None or self._external_codex_busy

    @property
    def backend_status(self) -> BackendStatus:
        return self._backend.status

    async def start(self) -> None:
        self._researchers = await asyncio.to_thread(self._source_repository.load_researchers)
        self._researchers_by_namekey = {
            researcher.namekey: researcher for researcher in self._researchers
        }
        self._ground_truth = await asyncio.to_thread(
            self._source_repository.load_ground_truth_by_namekey
        )
        self._load_dashboard_storage()
        restart_time = datetime.now(timezone.utc)
        for run in tuple(self._runs.values()):
            if run.dashboard_owned and run.status is RunStatus.RUNNING:
                await self._codex.terminate_abandoned_run(run.run_id)
                await self._append_run_event(
                    RunEvent(
                        run_id=run.run_id,
                        namekey=run.namekey,
                        at=restart_time,
                        kind=RunEventKind.FAILED,
                        detail=Locale.RESTART_INTERRUPTED_RUN,
                    )
                )
        for value in app.storage.general.get(QUEUE_STORAGE_KEY, []):
            run_id = UUID(str(value))
            queued_run = self._runs.get(run_id)
            if queued_run is not None and queued_run.status is RunStatus.QUEUED:
                await self._queue.put(run_id)
        self._worker_task = asyncio.create_task(self._worker())

    async def shutdown(self) -> None:
        self._shutting_down = True
        active_codex = self._active_codex
        if self._worker_task is not None:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None
        if active_codex is not None:
            with contextlib.suppress(Exception):
                await self._codex.cancel(active_codex)
        shutdown_time = datetime.now(timezone.utc)
        for run in tuple(self._runs.values()):
            if run.dashboard_owned and run.status is RunStatus.RUNNING:
                await self._append_run_event(
                    RunEvent(
                        run_id=run.run_id,
                        namekey=run.namekey,
                        at=shutdown_time,
                        kind=RunEventKind.FAILED,
                        detail=Locale.SHUTDOWN_INTERRUPTED_RUN,
                    )
                )
        await self._backend.stop()

    async def queue(
        self,
        *,
        namekey: Namekey,
    ) -> UUID:
        researcher = self._researchers_by_namekey.get(namekey)
        if researcher is None:
            raise KeyError(Locale.UNKNOWN_NAMEKEY_TEMPLATE.format(namekey=namekey))
        if researcher.cohort is ResearcherCohort.INELIGIBLE:
            raise ValueError(Locale.INELIGIBLE_QUEUE)
        run_id = uuid7()
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                namekey=namekey,
                at=datetime.now(timezone.utc),
                kind=RunEventKind.QUEUED,
            )
        )
        queued = list(app.storage.general.get(QUEUE_STORAGE_KEY, []))
        queued.append(str(run_id))
        app.storage.general[QUEUE_STORAGE_KEY] = queued
        await self._queue.put(run_id)
        return run_id

    async def rerun(
        self,
        *,
        namekey: Namekey,
    ) -> UUID:
        return await self.queue(namekey=namekey)

    async def cancel(
        self,
        *,
        run_id: UUID,
    ) -> None:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(Locale.UNKNOWN_RUN_ID_TEMPLATE.format(run_id=run_id))
        if run.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
            return
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                namekey=run.namekey,
                at=datetime.now(timezone.utc),
                kind=RunEventKind.CANCEL_REQUESTED,
            )
        )
        if self._active_run_id == run_id:
            if self._active_codex is not None:
                try:
                    await self._codex.cancel(self._active_codex)
                except Exception as exc:
                    await self._append_run_event(
                        RunEvent(
                            run_id=run_id,
                            namekey=run.namekey,
                            at=datetime.now(timezone.utc),
                            kind=RunEventKind.FAILED,
                            detail=Locale.CODEX_CANCEL_FAILED_TEMPLATE.format(error=exc),
                        )
                    )
                    raise
            return
        if run.status is RunStatus.QUEUED:
            await self._append_run_event(
                RunEvent(
                    run_id=run_id,
                    namekey=run.namekey,
                    at=datetime.now(timezone.utc),
                    kind=RunEventKind.CANCELED,
                )
            )

    async def refresh_idle_state(self) -> None:
        if self._shutting_down:
            return
        async with self._idle_refresh_lock:
            if self._shutting_down:
                return
            if self._backend.status is BackendStatus.RUNNING:
                await self._refresh_backend_state()
            else:
                self._runs = dict(replay_run_events(self._events))
            if self._active_run_id is not None:
                self._external_codex_busy = False
                return
            try:
                self._external_codex_busy = await self._codex.is_busy()
            except Exception:
                if self._shutting_down:
                    return
                raise

    async def _refresh_backend_state(self) -> None:
        snapshot = await asyncio.to_thread(self._backend_database.pull)
        self._runs = dict(replay_run_events(self._events))

        attempt_records: dict[Namekey, list[AttemptRecord]] = {}
        for record in snapshot.attempts:
            if record.namekey is None:
                raise RuntimeError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
            attempt_records.setdefault(Namekey(record.namekey), []).append(record)
        self._attempt_records = {
            namekey: tuple(records) for namekey, records in attempt_records.items()
        }

        accepted_attempts: dict[Namekey, list[AcceptedAttempt]] = {}
        for attempt in snapshot.accepted_attempts:
            metadata = attempt.session_metadata
            timestamp = datetime.fromisoformat(metadata.timestamp)
            if timestamp.tzinfo is None:
                raise RuntimeError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
            namekey = Namekey(attempt.namekey)
            accepted_attempts.setdefault(namekey, []).append(
                AcceptedAttempt(
                    namekey=namekey,
                    attempt_id=AttemptId(attempt.attempt_id),
                    session_metadata=SessionMetadata(
                        originator=metadata.originator,
                        source=metadata.source,
                        cli_version=metadata.cli_version,
                        model_provider=metadata.model_provider,
                        model=metadata.model,
                        reasoning_effort=metadata.reasoning_effort,
                        session_id=SessionId(metadata.session_id),
                        timestamp=timestamp,
                    ),
                    values=attempt.values,
                    footnotes=attempt.footnotes,
                    footnote_arguments=attempt.footnote_arguments,
                )
            )
        self._accepted_attempts = {
            namekey: tuple(attempts) for namekey, attempts in accepted_attempts.items()
        }

    async def snapshot(
        self,
        *,
        selection: UiSelection,
    ) -> UiSnapshot:
        await self.refresh_idle_state()
        variable = VARIABLE_SPEC_BY_KEY[selection.variable_key]
        views = self._reconciler.reconcile_all(
            researchers=self._researchers,
            runs=self._runs,
            attempt_records=self._attempt_records,
            accepted_attempts=self._accepted_attempts,
        )
        all_rows = tuple(
            self._projector.project_researcher(
                researcher_view=view,
                ground_truth=self._ground_truth.get(view.researcher.namekey),
                variable=variable,
                codex_busy=self.codex_busy,
            )
            for view in views
        )
        search_text = (selection.search_text or "").casefold().strip()
        rows = tuple(
            row
            for row, view in zip(all_rows, views, strict=True)
            if (selection.status_filter is None or view.current_status is selection.status_filter)
            and (
                selection.cohort_filter is None or view.researcher.cohort is selection.cohort_filter
            )
            and (
                not search_text
                or search_text in view.researcher.first_name.casefold()
                or search_text in view.researcher.last_name.casefold()
                or search_text in view.researcher.draw_number.casefold()
                or search_text == str(view.researcher.rnd)
                or search_text in view.researcher.namekey.casefold()
                or (
                    view.researcher.ineligibility_category is not None
                    and search_text in view.researcher.ineligibility_category.value.casefold()
                )
            )
        )
        statuses = [
            view.current_status
            for view in views
            if view.researcher.cohort is not ResearcherCohort.INELIGIBLE
        ]
        counts = DashboardCounts(
            total=len(views),
            ground_truth=sum(
                view.researcher.cohort is ResearcherCohort.GROUND_TRUTH for view in views
            ),
            no_ground_truth=sum(
                view.researcher.cohort is ResearcherCohort.NO_GROUND_TRUTH for view in views
            ),
            ineligible=sum(view.researcher.cohort is ResearcherCohort.INELIGIBLE for view in views),
            ready=statuses.count(RunStatus.READY),
            queued=statuses.count(RunStatus.QUEUED),
            running=statuses.count(RunStatus.RUNNING),
            complete=statuses.count(RunStatus.COMPLETE),
            failed=statuses.count(RunStatus.FAILED),
            canceled=statuses.count(RunStatus.CANCELED),
        )
        return UiSnapshot(
            counts=counts,
            rows=rows,
            backend_status=self.backend_status,
            active_run_id=self.active_run_id,
        )

    async def researcher_card(
        self,
        *,
        namekey: Namekey,
    ) -> ResearcherCardView:
        researcher = self._researchers_by_namekey.get(namekey)
        if researcher is None:
            raise KeyError(Locale.UNKNOWN_NAMEKEY_TEMPLATE.format(namekey=namekey))
        markdown = await asyncio.to_thread(self._backend_database.card, namekey)
        return ResearcherCardView(
            namekey=namekey,
            draw_number=researcher.draw_number,
            first_name=researcher.first_name,
            last_name=researcher.last_name,
            markdown=markdown,
        )

    async def _worker(self) -> None:
        while True:
            run_id = await self._queue.get()
            try:
                queued = list(app.storage.general.get(QUEUE_STORAGE_KEY, []))
                if str(run_id) in queued:
                    queued.remove(str(run_id))
                    app.storage.general[QUEUE_STORAGE_KEY] = queued
                run = self._runs[run_id]
                if run.status is RunStatus.CANCELED:
                    continue
                if not await self._wait_until_codex_idle(run_id=run_id):
                    continue
                self._active_run_id = run_id
                await self._execute_run(run_id=run_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._active_codex is not None:
                    with contextlib.suppress(Exception):
                        await self._codex.cancel(self._active_codex)
                run = self._runs[run_id]
                canceled = run.cancel_requested_at is not None and run.failure_detail is None
                await self._append_run_event(
                    RunEvent(
                        run_id=run_id,
                        namekey=run.namekey,
                        at=datetime.now(timezone.utc),
                        kind=(RunEventKind.CANCELED if canceled else RunEventKind.FAILED),
                        detail=None if canceled else str(exc),
                    )
                )
            finally:
                self._active_codex = None
                self._active_run_id = None
                self._queue.task_done()
                if not self._shutting_down:
                    await self.refresh_idle_state()

    async def _wait_until_codex_idle(self, *, run_id: UUID) -> bool:
        while True:
            await self.refresh_idle_state()
            if self._runs[run_id].status is RunStatus.CANCELED:
                return False
            if not self._external_codex_busy:
                return True
            await asyncio.sleep(UI_REFRESH_SECONDS)

    async def _execute_run(
        self,
        *,
        run_id: UUID,
    ) -> None:
        run = self._runs[run_id]
        await self._backend.start(namekey=run.namekey)
        result = await self._codex.start(
            run_id=run_id,
            on_handle=self._register_active_codex,
        )
        if self._runs[run_id].cancel_requested_at is not None:
            await self._codex.cancel(result.handle)
            raise RuntimeError(Locale.CODEX_CANCELED_BEFORE_SESSION_HANDOFF)
        self._active_codex = result.handle
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                namekey=run.namekey,
                at=result.session_timestamp,
                kind=RunEventKind.SESSION_DISCOVERED,
                session_id=result.session_id,
            )
        )

        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                namekey=run.namekey,
                at=datetime.now(timezone.utc),
                kind=RunEventKind.ROLLOUT_DISCOVERED,
                session_id=result.session_id,
                rollout_jsonl=str(result.rollout_jsonl),
            )
        )
        await self._backend.supply_session_id(result.session_id)
        exit_code = await self._codex.wait(result.handle)
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                namekey=run.namekey,
                at=datetime.now(timezone.utc),
                kind=RunEventKind.CODEX_EXITED,
                codex_exit_code=exit_code,
            )
        )
        final_status = await self._finalize_run(
            run_id=run_id,
            codex_exit_code=exit_code,
        )
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                namekey=run.namekey,
                at=datetime.now(timezone.utc),
                kind=RunEventKind(final_status.value),
                codex_exit_code=exit_code,
            )
        )

    async def _register_active_codex(
        self,
        handle: CodexProcessHandle,
    ) -> None:
        if self._active_run_id != handle.run_id:
            raise RuntimeError(Locale.CODEX_HANDLE_MISMATCH)
        self._active_codex = handle
        run = self._runs[handle.run_id]
        if run.started_at is None:
            event_kind = RunEventKind.STARTED
        elif handle.remote_pid is not None and run.remote_pid != handle.remote_pid:
            event_kind = RunEventKind.REMOTE_PID_DISCOVERED
        else:
            return
        await self._append_run_event(
            RunEvent(
                run_id=handle.run_id,
                namekey=run.namekey,
                at=datetime.now(timezone.utc),
                kind=event_kind,
                remote_pid=(None if handle.remote_pid is None else int(handle.remote_pid)),
            )
        )
        if self._runs[handle.run_id].cancel_requested_at is not None:
            await self._codex.cancel(handle)

    async def _finalize_run(
        self,
        *,
        run_id: UUID,
        codex_exit_code: int,
    ) -> RunStatus:
        run = self._runs[run_id]
        if run.cancel_requested_at is not None:
            return RunStatus.CANCELED
        if run.accepted_attempt_id is not None:
            return RunStatus.COMPLETE
        if run.session_id is not None:
            accepted = await self._accepted_attempt_for_session(
                namekey=run.namekey,
                session_id=run.session_id,
            )
            if accepted is not None:
                await self._append_run_event(
                    RunEvent(
                        run_id=run_id,
                        namekey=run.namekey,
                        at=datetime.now(timezone.utc),
                        kind=RunEventKind.PUSH_ACCEPTED,
                        session_id=run.session_id,
                        accepted_attempt_id=accepted.attempt_id,
                    )
                )
                return RunStatus.COMPLETE
        return RunStatus.FAILED

    async def _accepted_attempt_for_session(
        self,
        *,
        namekey: Namekey,
        session_id: SessionId,
    ) -> AcceptedAttempt | None:
        await self._refresh_backend_state()
        attempts = self._accepted_attempts.get(namekey, ())
        matches = [
            attempt for attempt in attempts if attempt.session_metadata.session_id == session_id
        ]
        if len(matches) > 1:
            raise RuntimeError(Locale.ACCEPTED_SESSION_DUPLICATE)
        return matches[0] if matches else None

    async def _append_run_event(
        self,
        event: RunEvent,
    ) -> None:
        self._events.append(event)
        app.storage.general[RUN_EVENTS_STORAGE_KEY] = [
            item.model_dump(mode="json") for item in self._events
        ]
        self._runs = dict(replay_run_events(self._events))
        if event.kind is RunEventKind.FAILED:
            emit_log(
                Locale.CONTROL_CENTRE_LOG_PREFIX,
                Locale.RUN_FAILED_LOG_TEMPLATE.format(
                    run_id=event.run_id,
                    namekey=event.namekey,
                    detail=event.detail or "unspecified",
                ),
            )

    def _load_dashboard_storage(self) -> None:
        raw_events = app.storage.general.get(RUN_EVENTS_STORAGE_KEY, [])
        if not isinstance(raw_events, list):
            raise RuntimeError(Locale.JOURNAL_STORAGE_INVALID)
        try:
            self._events = [RunEvent.model_validate(value) for value in raw_events]
        except ValidationError as exc:
            raise RuntimeError(Locale.JOURNAL_STORAGE_INVALID) from exc
        self._runs = dict(replay_run_events(self._events))


# =============================================================================
# NiceGUI page
# =============================================================================


@dataclass(slots=True)
class UiHandles:
    backend_status_label: Any | None = None
    summary_label: Any | None = None

    variable_select: Any | None = None
    status_select: Any | None = None
    cohort_select: Any | None = None
    search_input: Any | None = None

    grid: Any | None = None
    execute_button: Any | None = None
    view_card_button: Any | None = None

    selected_researcher_label: Any | None = None
    attempt_history_expansion: Any | None = None
    attempt_history_table: Any | None = None
    card_container: Any | None = None
    card_markdown: Any | None = None


class ControlCentrePage:
    def __init__(
        self,
        *,
        controller: ControlCentreController,
    ) -> None:
        self._controller = controller
        self._selection = UiSelection(variable_key=VARIABLE_SPECS[0].key)
        self._handles = UiHandles()
        self._grid_initialized = False
        self._grid_variable_key = self._selection.variable_key
        self._grid_rows_by_id: dict[str, dict[str, Any]] = {}
        self._row_views_by_namekey: dict[Namekey, ResearcherGridRow] = {}
        self._expanded_history_namekey: Namekey | None = None
        self._card_cache: dict[Namekey, ResearcherCardView] = {}

    @property
    def selection(self) -> UiSelection:
        return self._selection

    def build(self) -> None:
        ui.add_css(CARD_RESPONSIVE_CSS)
        with (
            ui
            .column()
            .style(PAGE_CONTAINER_STYLE)
            .props(NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_CONTAINER_TEST_ID))
        ):
            self.build_header()
            self.build_summary()
            self.build_filters()
            self.build_grid()
            self.build_attempt_history_panel()
            self.build_action_panel()
            self.build_card_panel()
        ui.timer(UI_REFRESH_SECONDS, self.refresh)

    def build_header(self) -> None:
        with (
            ui
            .row()
            .style(RESPONSIVE_ROW_STYLE)
            .props(NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_HEADER_TEST_ID))
        ):
            ui.label(Locale.PAGE_TITLE)
            self._handles.backend_status_label = ui.label(Locale.BACKEND_STARTING)

    def build_summary(self) -> None:
        self._handles.summary_label = (
            ui
            .label(Locale.SUMMARY_LOADING)
            .style(FULL_WIDTH_STYLE)
            .props(NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_SUMMARY_TEST_ID))
        )

    def build_filters(self) -> None:
        with (
            ui
            .row()
            .style(RESPONSIVE_ROW_STYLE)
            .props(NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_FILTERS_TEST_ID))
        ):
            self._handles.variable_select = ui.select(
                {variable.key: variable.ai_column for variable in VARIABLE_SPECS},
                value=self._selection.variable_key,
                label=Locale.VARIABLE_FILTER,
                on_change=lambda event: self.on_variable_changed(event.value),
            )
            self._handles.status_select = ui.select(
                {
                    "": Locale.ALL_STATUSES,
                    **{status.value: status.value for status in RunStatus},
                },
                value="",
                label=Locale.STATUS_FILTER,
                on_change=lambda event: self.on_status_filter_changed(event.value or None),
            )
            self._handles.cohort_select = ui.select(
                {
                    "": Locale.ALL_COHORTS,
                    **{cohort.value: cohort.value for cohort in ResearcherCohort},
                },
                value="",
                label=Locale.COHORT_FILTER,
                on_change=lambda event: self.on_cohort_filter_changed(event.value or None),
            )
            self._handles.search_input = ui.input(
                label=Locale.SEARCH_FILTER,
                on_change=lambda event: self.on_search_changed(event.value),
            ).props(NiceGui.CLEARABLE_PROP)

    def build_grid(self) -> None:
        variable = VARIABLE_SPEC_BY_KEY[self._selection.variable_key]
        self._handles.grid = (
            ui
            .aggrid(
                AgGrid.options(
                    columns=self.grid_column_definitions(variable=variable),
                    rows=[],
                    row_id_field=GRID_ROW_ID_FIELD,
                ),
                auto_size_columns=False,
            )
            .style(GRID_STYLE)
            .props(NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=RESEARCHER_GRID_TEST_ID))
        )
        self._handles.grid.on(
            AgGrid.CELL_CLICKED_EVENT,
            self._on_grid_cell_clicked,
        )

    def build_action_panel(self) -> None:
        with (
            ui
            .row()
            .style(RESPONSIVE_ROW_STYLE)
            .props(NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=ACTION_PANEL_TEST_ID))
        ):
            self._handles.selected_researcher_label = ui.label(Locale.NO_RESEARCHER_SELECTED)
            self._handles.execute_button = (
                ui
                .button(
                    Locale.ACTION_SELECT_RESEARCHER,
                    on_click=self.on_execute_selected,
                )
                .style(ACTION_BUTTON_STYLE)
                .props(NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=EXECUTE_ACTION_TEST_ID))
                .on(
                    NiceGui.MOUSE_DOWN_EVENT,
                    js_handler=NiceGui.PRESERVE_SELECTION_HANDLER,
                )
            )
            self._handles.execute_button.disable()
            self._handles.view_card_button = (
                ui
                .button(
                    Locale.ACTION_VIEW_CARD,
                    on_click=self.refresh_card,
                )
                .style(ACTION_BUTTON_STYLE)
                .props(NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=VIEW_CARD_TEST_ID))
                .on(
                    NiceGui.MOUSE_DOWN_EVENT,
                    js_handler=NiceGui.PRESERVE_SELECTION_HANDLER,
                )
            )
            self._handles.view_card_button.disable()

    def build_attempt_history_panel(self) -> None:
        variable = VARIABLE_SPEC_BY_KEY[self._selection.variable_key]
        self._handles.attempt_history_expansion = (
            ui
            .expansion(Locale.ATTEMPT_HISTORY)
            .style(ATTEMPT_HISTORY_STYLE)
            .props(NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=ATTEMPT_HISTORY_PANEL_TEST_ID))
        )
        with self._handles.attempt_history_expansion:
            self._handles.attempt_history_table = (
                ui
                .table(
                    rows=[],
                    columns=self.attempt_history_column_definitions(variable=variable),
                    row_key=GRID_ROW_ID_FIELD,
                )
                .style(ATTEMPT_HISTORY_TABLE_STYLE)
                .props(
                    f"{ATTEMPT_HISTORY_TABLE_PROPS} "
                    f"{NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=ATTEMPT_HISTORY_TABLE_TEST_ID)}"
                )
            )
        self._handles.attempt_history_expansion.set_visibility(False)

    def build_card_panel(self) -> None:
        self._handles.card_container = (
            ui
            .card()
            .style(CARD_CONTAINER_STYLE)
            .props(NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_FOOTER_TEST_ID))
        )
        with self._handles.card_container:
            self._handles.card_markdown = ui.markdown("").style(CARD_MARKDOWN_STYLE)

    def grid_column_definitions(
        self,
        *,
        variable: VariableSpec,
    ) -> list[dict[str, Any]]:
        return [
            AgGrid.column(
                field=GRID_RND_FIELD,
                header=GRID_RND_FIELD,
                width=GRID_RND_COLUMN_WIDTH,
            ),
            AgGrid.column(
                field=GRID_DRAW_FIELD,
                header=DRAW_LABEL,
                width=GRID_DRAW_COLUMN_WIDTH,
                comparator=AgGrid.DRAW_COMPARATOR,
            ),
            AgGrid.column(
                field=GRID_FIRST_NAME_FIELD,
                header=KTP_FIRST_NAME_COL,
                width=GRID_NAME_COLUMN_WIDTH,
            ),
            AgGrid.column(
                field=GRID_LAST_NAME_FIELD,
                header=KTP_LAST_NAME_COL,
                width=GRID_NAME_COLUMN_WIDTH,
            ),
            AgGrid.column(
                field=GRID_COHORT_FIELD,
                header=GRID_COHORT_FIELD,
                width=GRID_COHORT_COLUMN_WIDTH,
            ),
            AgGrid.column(
                field=GRID_INELIGIBILITY_FIELD,
                header=GRID_INELIGIBILITY_FIELD,
                width=GRID_INELIGIBILITY_COLUMN_WIDTH,
            ),
            AgGrid.column(
                field=GRID_AI_VALUE_FIELD,
                header=variable.ai_column,
                width=GRID_CONTENT_COLUMN_WIDTH,
                wrap_text=True,
            ),
            AgGrid.column(
                field=GRID_TABLE_1_VALUE_FIELD,
                header=variable.table_1_column,
                width=GRID_CONTENT_COLUMN_WIDTH,
                wrap_text=True,
            ),
            AgGrid.column(
                field=GRID_FOOTNOTES_FIELD,
                header=KTP_AI_AUGMENT_FOOTNOTES_COL,
                width=GRID_CONTENT_COLUMN_WIDTH,
                wrap_text=True,
            ),
            AgGrid.column(
                field=GRID_FOOTNOTE_ARGUMENTS_FIELD,
                header=KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL,
                width=GRID_CONTENT_COLUMN_WIDTH,
                wrap_text=True,
            ),
            AgGrid.column(
                field=GRID_ATTEMPT_ID_FIELD,
                header=KTP_AI_AUGMENT_ATTEMPT_ID_COL,
                width=GRID_ATTEMPT_COLUMN_WIDTH,
            ),
            AgGrid.column(
                field=GRID_ATTEMPT_TIMESTAMP_FIELD,
                header=GRID_ATTEMPT_TIMESTAMP_FIELD,
                width=GRID_TIME_COLUMN_WIDTH,
            ),
            AgGrid.column(
                field=GRID_STATUS_FIELD,
                header=GRID_STATUS_FIELD,
                width=GRID_STATUS_COLUMN_WIDTH,
            ),
        ]

    def attempt_history_column_definitions(
        self,
        *,
        variable: VariableSpec,
    ) -> list[dict[str, Any]]:
        return [
            nicegui_table_column(
                field=GRID_ATTEMPT_TIMESTAMP_FIELD,
                label=GRID_ATTEMPT_TIMESTAMP_FIELD,
            ),
            nicegui_table_column(
                field=GRID_STATUS_FIELD,
                label=GRID_STATUS_FIELD,
            ),
            nicegui_table_column(
                field=GRID_ATTEMPT_ID_FIELD,
                label=KTP_AI_AUGMENT_ATTEMPT_ID_COL,
            ),
            nicegui_table_column(
                field=GRID_AI_VALUE_FIELD,
                label=variable.ai_column,
            ),
            nicegui_table_column(
                field=GRID_TABLE_1_VALUE_FIELD,
                label=variable.table_1_column,
            ),
            nicegui_table_column(
                field=GRID_FOOTNOTES_FIELD,
                label=KTP_AI_AUGMENT_FOOTNOTES_COL,
            ),
            nicegui_table_column(
                field=GRID_FOOTNOTE_ARGUMENTS_FIELD,
                label=KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL,
            ),
        ]

    def grid_options(
        self,
        *,
        snapshot: UiSnapshot,
        variable: VariableSpec,
    ) -> dict[str, Any]:
        return AgGrid.options(
            columns=self.grid_column_definitions(variable=variable),
            rows=self.grid_rows(snapshot=snapshot),
            row_id_field=GRID_ROW_ID_FIELD,
        )

    def grid_rows(
        self,
        *,
        snapshot: UiSnapshot,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in snapshot.rows:
            latest = row.latest
            rows.append({
                GRID_ROW_ID_FIELD: row.namekey,
                GRID_NAMEKEY_FIELD: row.namekey,
                GRID_RUN_ID_FIELD: (None if latest.run_id is None else str(latest.run_id)),
                GRID_RND_FIELD: row.rnd,
                GRID_DRAW_FIELD: latest.draw_number,
                GRID_LAST_NAME_FIELD: latest.last_name,
                GRID_FIRST_NAME_FIELD: latest.first_name,
                GRID_COHORT_FIELD: row.cohort.value,
                GRID_INELIGIBILITY_FIELD: (
                    None if row.ineligibility_category is None else row.ineligibility_category.value
                ),
                GRID_AI_VALUE_FIELD: latest.ai_value,
                GRID_TABLE_1_VALUE_FIELD: latest.table_1_value,
                GRID_FOOTNOTES_FIELD: latest.footnotes,
                GRID_FOOTNOTE_ARGUMENTS_FIELD: latest.footnote_arguments,
                GRID_ATTEMPT_ID_FIELD: latest.attempt_id,
                GRID_ATTEMPT_TIMESTAMP_FIELD: (
                    None
                    if latest.attempt_timestamp is None
                    else latest.attempt_timestamp.isoformat()
                ),
                GRID_STATUS_FIELD: latest.attempt_status.value,
                GRID_ACTION_FIELD: latest.action.value,
            })
        return rows

    def attempt_detail_rows(
        self,
        *,
        row: ResearcherGridRow,
    ) -> list[dict[str, Any]]:
        return [
            {
                GRID_ROW_ID_FIELD: str(
                    attempt.run_id if attempt.run_id is not None else attempt.attempt_id
                ),
                GRID_RUN_ID_FIELD: (str(attempt.run_id) if attempt.run_id is not None else None),
                GRID_ATTEMPT_ID_FIELD: attempt.attempt_id,
                GRID_ATTEMPT_TIMESTAMP_FIELD: (
                    None
                    if attempt.attempt_timestamp is None
                    else attempt.attempt_timestamp.isoformat()
                ),
                GRID_STATUS_FIELD: attempt.attempt_status.value,
                GRID_AI_VALUE_FIELD: attempt.ai_value,
                GRID_TABLE_1_VALUE_FIELD: attempt.table_1_value,
                GRID_FOOTNOTES_FIELD: attempt.footnotes,
                GRID_FOOTNOTE_ARGUMENTS_FIELD: attempt.footnote_arguments,
            }
            for attempt in row.attempts
        ]

    async def refresh(self) -> None:
        snapshot = await self._controller.snapshot(selection=self._selection)
        if self._handles.backend_status_label is not None:
            self._handles.backend_status_label.set_text(
                Locale.BACKEND_STATUS_TEMPLATE.format(status=snapshot.backend_status.value)
            )
        if self._handles.summary_label is not None:
            counts = snapshot.counts
            self._handles.summary_label.set_text(
                Locale.SUMMARY_TEMPLATE.format(
                    total=counts.total,
                    ground_truth=counts.ground_truth,
                    no_ground_truth=counts.no_ground_truth,
                    ineligible=counts.ineligible,
                    ready=counts.ready,
                    queued=counts.queued,
                    running=counts.running,
                    complete=counts.complete,
                    failed=counts.failed,
                    canceled=counts.canceled,
                )
            )
        await self.refresh_grid(snapshot=snapshot)

    async def refresh_grid(
        self,
        *,
        snapshot: UiSnapshot | None = None,
    ) -> None:
        if self._handles.grid is None:
            return
        if snapshot is None:
            snapshot = await self._controller.snapshot(selection=self._selection)
        variable = VARIABLE_SPEC_BY_KEY[self._selection.variable_key]
        self._row_views_by_namekey = {row.namekey: row for row in snapshot.rows}
        self.refresh_attempt_history()
        rows = self.grid_rows(snapshot=snapshot)
        self.sync_selected_action(rows)
        if not self._grid_initialized:
            options = self.grid_options(
                snapshot=snapshot,
                variable=variable,
            )
            self._handles.grid.options.update(options)
            self._handles.grid.update()
            self._grid_rows_by_id = {str(row[GRID_ROW_ID_FIELD]): row for row in rows}
            self._grid_variable_key = self._selection.variable_key
            self._grid_initialized = True
            return
        if self._grid_variable_key != self._selection.variable_key:
            await self._handles.grid.run_grid_method(
                AgGrid.SET_GRID_OPTION_METHOD,
                AgGrid.COLUMN_DEFINITIONS_OPTION,
                self.grid_column_definitions(variable=variable),
            )
            self._grid_variable_key = self._selection.variable_key
        desired_by_id = {str(row[GRID_ROW_ID_FIELD]): row for row in rows}
        if tuple(self._grid_rows_by_id) != tuple(desired_by_id):
            await self._handles.grid.run_grid_method(
                AgGrid.SET_GRID_OPTION_METHOD,
                AgGrid.ROW_DATA_OPTION,
                rows,
            )
            self._grid_rows_by_id = desired_by_id
            return
        for row in rows:
            row_id = str(row[GRID_ROW_ID_FIELD])
            previous = self._grid_rows_by_id.get(row_id)
            if previous != row:
                await self._handles.grid.run_row_method(
                    row_id,
                    AgGrid.UPDATE_DATA_METHOD,
                    row,
                )
        self._grid_rows_by_id = desired_by_id

    def refresh_attempt_history(self) -> None:
        namekey = self._expanded_history_namekey
        table = self._handles.attempt_history_table
        if namekey is None or table is None:
            return
        row = self._row_views_by_namekey.get(namekey)
        if row is None:
            return
        table.update_rows(
            self.attempt_detail_rows(row=row),
            clear_selection=False,
        )

    async def refresh_card(self) -> None:
        namekey = self._selection.selected_namekey
        if namekey is None:
            return
        card = self._card_cache.get(namekey)
        if card is None:
            card = await self._controller.researcher_card(namekey=namekey)
            self._card_cache[namekey] = card
        await self._show_card(card)

    async def _show_card(self, card: ResearcherCardView) -> None:
        if self._handles.selected_researcher_label is not None:
            self._handles.selected_researcher_label.set_text(
                Locale.RESEARCHER_SELECTION_TEMPLATE.format(
                    first_name=card.first_name,
                    last_name=card.last_name,
                    draw_number=card.draw_number,
                )
            )
        if self._handles.card_markdown is not None:
            self._handles.card_markdown.set_content(card.markdown)

    def show_attempt_history(
        self,
        namekey: Namekey,
    ) -> None:
        expansion = self._handles.attempt_history_expansion
        table = self._handles.attempt_history_table
        row = self._row_views_by_namekey.get(namekey)
        if expansion is None or table is None or row is None:
            return
        variable = VARIABLE_SPEC_BY_KEY[self._selection.variable_key]
        table.columns = self.attempt_history_column_definitions(variable=variable)
        table.update_rows(self.attempt_detail_rows(row=row), clear_selection=False)
        expansion.set_text(
            Locale.ATTEMPT_HISTORY_TEMPLATE.format(
                first_name=row.latest.first_name,
                last_name=row.latest.last_name,
            )
        )
        expansion.set_visibility(True)
        expansion.open()
        self._expanded_history_namekey = namekey

    async def on_variable_changed(
        self,
        variable_key: str,
    ) -> None:
        if variable_key not in VARIABLE_SPEC_BY_KEY:
            raise KeyError(Locale.UNKNOWN_VARIABLE_TEMPLATE.format(variable_key=variable_key))
        self._selection.variable_key = variable_key
        await self.refresh_grid()
        expanded_namekey = self._expanded_history_namekey
        if expanded_namekey is not None:
            self.show_attempt_history(expanded_namekey)

    async def on_status_filter_changed(
        self,
        status: str | None,
    ) -> None:
        self._selection.status_filter = None if status is None else RunStatus(status)
        await self.refresh_grid()

    async def on_cohort_filter_changed(
        self,
        cohort: str | None,
    ) -> None:
        self._selection.cohort_filter = None if cohort is None else ResearcherCohort(cohort)
        await self.refresh_grid()

    async def on_search_changed(
        self,
        search_text: str | None,
    ) -> None:
        self._selection.search_text = "" if search_text is None else search_text
        await self.refresh_grid()

    async def on_researcher_selected(
        self,
        namekey: Namekey,
    ) -> None:
        self._selection.selected_namekey = namekey
        await self.refresh_card()

    def sync_selected_action(
        self,
        rows: Sequence[Mapping[str, object]],
    ) -> None:
        selected_namekey = self._selection.selected_namekey
        selected = next(
            (row for row in rows if row.get(GRID_NAMEKEY_FIELD) == selected_namekey),
            None,
        )
        if selected is None:
            self._selection.selected_run_id = None
            self._selection.selected_action = None
            if self._handles.execute_button is not None:
                self._handles.execute_button.set_text(Locale.ACTION_SELECT_RESEARCHER)
                self._handles.execute_button.disable()
            if self._handles.view_card_button is not None:
                self._handles.view_card_button.disable()
            return
        run_id_value = selected.get(GRID_RUN_ID_FIELD)
        action = RunAction(str(selected[GRID_ACTION_FIELD]))
        self._selection.selected_run_id = None if run_id_value is None else UUID(str(run_id_value))
        self._selection.selected_action = action
        if self._handles.selected_researcher_label is not None:
            self._handles.selected_researcher_label.set_text(
                Locale.RESEARCHER_SELECTION_TEMPLATE.format(
                    first_name=selected[GRID_FIRST_NAME_FIELD],
                    last_name=selected[GRID_LAST_NAME_FIELD],
                    draw_number=selected[GRID_DRAW_FIELD],
                )
            )
        if self._handles.view_card_button is not None:
            if self._controller.active_run_id is None:
                self._handles.view_card_button.enable()
            else:
                self._handles.view_card_button.disable()
        if self._handles.execute_button is not None:
            self._handles.execute_button.set_text(ACTION_LABEL_BY_VALUE[action.value])
            if action is RunAction.DISABLED:
                self._handles.execute_button.disable()
            else:
                self._handles.execute_button.enable()

    async def on_queue(
        self,
        namekey: Namekey,
    ) -> None:
        self._card_cache.pop(namekey, None)
        run_id = await self._controller.queue(namekey=namekey)
        self._selection.selected_run_id = run_id
        self._selection.selected_action = RunAction.CANCEL
        self.update_execute_button()

    async def on_rerun(
        self,
        namekey: Namekey,
    ) -> None:
        self._card_cache.pop(namekey, None)
        run_id = await self._controller.rerun(namekey=namekey)
        self._selection.selected_run_id = run_id
        self._selection.selected_action = RunAction.CANCEL
        self.update_execute_button()

    async def on_cancel(
        self,
        run_id: UUID,
    ) -> None:
        await self._controller.cancel(run_id=run_id)
        self._selection.selected_action = RunAction.RERUN
        self.update_execute_button()

    def update_execute_button(self) -> None:
        button = self._handles.execute_button
        action = self._selection.selected_action
        if button is None or action is None:
            return
        button.set_text(ACTION_LABEL_BY_VALUE[action.value])
        if action is RunAction.DISABLED:
            button.disable()
        else:
            button.enable()

    async def on_grid_action(
        self,
        *,
        action: RunAction,
        namekey: Namekey,
        run_id: UUID | None,
    ) -> None:
        if action is RunAction.QUEUE:
            await self.on_queue(namekey)
        elif action is RunAction.RERUN:
            await self.on_rerun(namekey)
        elif action is RunAction.CANCEL and run_id is not None:
            await self.on_cancel(run_id)

    async def on_execute_selected(self) -> None:
        namekey = self._selection.selected_namekey
        action = self._selection.selected_action
        if namekey is None or action is None or action is RunAction.DISABLED:
            return
        await self.on_grid_action(
            action=action,
            namekey=namekey,
            run_id=self._selection.selected_run_id,
        )

    async def _on_grid_cell_clicked(self, event: Any) -> None:
        arguments = event.args
        data = arguments.get(AgGrid.EVENT_DATA, {})
        namekey = Namekey(str(data.get(GRID_NAMEKEY_FIELD, "")))
        if not namekey:
            return
        self._selection.selected_namekey = namekey
        self.sync_selected_action((data,))
        self.show_attempt_history(namekey)


# =============================================================================
# Application-level dependency graph
# =============================================================================


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    configuration: AiAugmentCtlCtrContext

    source_repository: SourceRepository

    backend: BackendSupervisor
    backend_database: BackendDatabaseClient
    codex: CodexRunner

    reconciler: AttemptReconciler
    projector: VariableProjector

    controller: ControlCentreController


SERVICES: ApplicationServices | None = None
APPLICATION_LIFECYCLE_CONFIGURED = False
APPLICATION_CONFIG_PATH = DEFAULT_CONFIG_PATH


def create_services(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> ApplicationServices:
    configuration = AiAugmentCtlCtrContext(config_path=config_path)
    source_repository = SourceRepository(configuration=configuration)
    backend = BackendSupervisor(
        repository_root=REPOSITORY_ROOT,
        config_path=configuration.config_path,
        openalex_api_key=configuration.openalex_api_key,
        appendwatch_report=configuration.appendwatch_report,
        dashboard_socket_path=DASHBOARD_SOCKET_PATH,
    )
    backend_database = BackendDatabaseClient(socket_path=DASHBOARD_SOCKET_PATH)
    codex = CodexRunner(
        timezone=configuration.timezone,
        openalex_api_key=configuration.openalex_api_key,
    )
    reconciler = AttemptReconciler()
    projector = VariableProjector()
    controller = ControlCentreController(
        source_repository=source_repository,
        backend=backend,
        backend_database=backend_database,
        codex=codex,
        reconciler=reconciler,
        projector=projector,
    )
    return ApplicationServices(
        configuration=configuration,
        source_repository=source_repository,
        backend=backend,
        backend_database=backend_database,
        codex=codex,
        reconciler=reconciler,
        projector=projector,
        controller=controller,
    )


def require_services() -> ApplicationServices:
    if SERVICES is None:
        raise RuntimeError(Locale.SERVICES_NOT_STARTED)
    return SERVICES


@app.get(CHROME_DEVTOOLS_PATH, include_in_schema=False)
async def chrome_devtools_probe() -> dict[str, object]:
    return {}


# =============================================================================
# Browser-facing NiceGUI page
# =============================================================================


@ui.page("/")
async def control_centre_page() -> None:
    page = ControlCentrePage(controller=require_services().controller)
    page.build()
    await page.refresh()


# =============================================================================
# NiceGUI / backend lifecycle
# =============================================================================


async def application_startup() -> None:
    global SERVICES

    if SERVICES is None:
        SERVICES = create_services(config_path=APPLICATION_CONFIG_PATH)
    await SERVICES.controller.start()
    emit_log(
        Locale.CONTROL_CENTRE_LOG_PREFIX,
        Locale.READY_LOG_TEMPLATE.format(url=CONTROL_CENTRE_BASE_URL),
    )


async def application_shutdown() -> None:
    if SERVICES is not None:
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, Locale.STOPPING_LOG)
        await SERVICES.controller.shutdown()
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, Locale.STOPPED_LOG)


def configure_application_lifecycle() -> None:
    global APPLICATION_LIFECYCLE_CONFIGURED

    if APPLICATION_LIFECYCLE_CONFIGURED:
        return
    app.on_startup(application_startup)
    app.on_shutdown(application_shutdown)
    APPLICATION_LIFECYCLE_CONFIGURED = True


def main() -> None:
    global APPLICATION_CONFIG_PATH

    parser = argparse.ArgumentParser()
    parser.add_argument(CONFIG_OPTION, type=Path, default=DEFAULT_CONFIG_PATH)
    arguments = parser.parse_args()
    APPLICATION_CONFIG_PATH = arguments.config
    configure_application_lifecycle()
    with contextlib.suppress(KeyboardInterrupt):
        ui.run(
            host=CONTROL_CENTRE_HOST,
            port=CONTROL_CENTRE_PORT,
            reload=False,
            show=False,
            show_welcome_message=False,
        )


if __name__ == "__main__":
    main()
