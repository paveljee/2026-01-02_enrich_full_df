from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import shlex
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
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

import duckdb
import yaml
from fastapi import HTTPException, status
from nicegui import app, ui
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.helpers.cards import build_cards
from src.helpers.config import PipelineConfig
from src.helpers.data_models import NameKey, OuterDict
from src.helpers.duckdb_utils import (
    append_innerdicts_from_jsonlines_table,
    duckdb_quote_identifier,
)
from src.helpers.procedures import DocxMatchProcedure, ParquetMatchProcedure, XlsxMatchProcedure
from src.helpers.schema import (
    DOCX_INNERDICT_TABLE,
    PARQUET_INNERDICT_TABLE,
    XLSX_INNERDICT_TABLE,
)
from src.helpers.vars import (
    CARD_INTRODUCTION,
    DRAW_LABEL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
)

from ...backend.api import (
    AI_AUGMENT_COLUMNS,
    APPENDWATCH_REPORT_ENV_NAME,
    ARCHIVED_ATTEMPT_MANIFEST_COLUMN,
    ARCHIVED_ATTEMPTS_TABLE,
    ATTEMPT_ID_KEY,
    ATTEMPT_RESULT_ACCEPTED,
    ATTEMPT_RESULT_CONFIGURATION_ERROR,
    ATTEMPT_RESULT_REJECTED,
    CARD_EXCLUDED_COLUMNS,
    CODEX_INNERDICT_TABLE,
    CODEX_OUTPUT_VIEW,
    CONFIG_OPTION,
    CONTROL_PARENT_PID_ENV_NAME,
    CONTROL_RUN_EVENTS_PATH,
    CONTROL_RUN_EVENTS_TOKEN_ENV_NAME,
    CONTROL_RUN_EVENTS_TOKEN_HEADER,
    DOCX_TO_AI_AUGMENT_COLUMNS,
    DRAW_VALUE_SEPARATOR,
    EXPECTED_GROUND_TRUTH_RESEARCHERS,
    EXPECTED_INELIGIBILITY_COUNTS,
    EXPECTED_INELIGIBLE_RESEARCHERS,
    EXPECTED_NO_GROUND_TRUTH_RESEARCHERS,
    EXPECTED_SOURCE_RESEARCHERS,
    FORBIDDEN_NORMALIZED_PATH_PARTS,
    HOST_WORKBOOK_PATH,
    HTTP_CONTENT_TYPE_HEADER,
    HTTP_GET_METHOD,
    HTTP_PUT_METHOD,
    JSON_MEDIA_TYPE,
    KTP_AI_AUGMENT_ATTEMPT_ID_COL,
    KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL,
    KTP_AI_AUGMENT_FOOTNOTES_COL,
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
    ArchivedAttemptManifest,
    ArchivedAttemptRecovery,
    CodexMatchProcedure,
    CompactSessionMetadata,
    ControlRunEventsRequest,
    ControlRunEventsResponse,
    IneligibilityCategory,
    _detour_db_path,
    derive_source_population,
    eligible_cohorts,
    ground_truth_for_researcher,
    load_control_run_events,
    load_release_batches,
    load_source_researcher,
    persist_control_run_events,
    registered_release_map,
    restore_archived_attempts,
)
from ...backend.api import (
    ControlRunEvent as RunEvent,
)
from ...backend.api import (
    ControlRunEventKind as RunEventKind,
)
from ...backend.api import (
    RuntimeConfiguration as BackendRuntimeConfiguration,
)
from ...backend.api import (
    SourceCohort as ResearcherCohort,
)
from ...backend.helpers.data_models.pydantic_to_paste import EXPORT_OPENALEX_API_KEY
from ...backend.helpers.vars import AI_AUGMENT_COLUMN_PREFIX
from .helpers.aggrid import AgGrid
from .helpers.locale import Locale


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

REPOSITORY_ROOT_PARENT_INDEX: Final = 6
DETOUR_ROOT_PARENT_INDEX: Final = 3
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[REPOSITORY_ROOT_PARENT_INDEX]
DETOUR_ROOT: Final = Path(__file__).resolve().parents[DETOUR_ROOT_PARENT_INDEX]
DETOUR_DATA_DIR: Final = DETOUR_ROOT / "data"

DEFAULT_CONFIG_PATH: Final = REPOSITORY_ROOT / "config_ai_augment.json"

RUN_JOURNAL_PATH: Final = DETOUR_DATA_DIR / "control_centre_runs.jsonl"

BACKEND_MODULE: Final = "src.detours.detour_ai_augment.src.backend.api"
BACKEND_COMMAND_PREFIX: Final = (
    sys.executable,
    "-m",
    BACKEND_MODULE,
    CONFIG_OPTION,
)

BACKEND_HOST: Final = "127.0.0.1"
BACKEND_PORT: Final = 8612
BACKEND_BASE_URL: Final = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
BACKEND_OPENAPI_URL: Final = f"{BACKEND_BASE_URL}/openapi.json"
BACKEND_PULL_URL: Final = f"{BACKEND_BASE_URL}/pull"
BACKEND_CONTROL_RUN_EVENTS_URL: Final = f"{BACKEND_BASE_URL}{CONTROL_RUN_EVENTS_PATH}"
BACKEND_READY_TIMEOUT_SECONDS: Final = 30
BACKEND_READY_POLL_SECONDS: Final = 0.1
PROCESS_STOP_TIMEOUT_SECONDS: Final = 10
TEXT_ENCODING: Final = "utf-8"
TEXT_DECODE_ERROR_POLICY: Final = "replace"
CONTROL_CENTRE_HOST: Final = "127.0.0.1"
CONTROL_CENTRE_PORT: Final = 8611
CONTROL_CENTRE_BASE_URL: Final = f"http://{CONTROL_CENTRE_HOST}:{CONTROL_CENTRE_PORT}"

CONTROL_API_PREFIX: Final = "/_control"
CONTROL_CURRENT_PATH: Final = f"{CONTROL_API_PREFIX}/current"
CONTROL_ACCEPTED_PATH_TEMPLATE: Final = f"{CONTROL_API_PREFIX}/runs/{{run_id}}/accepted"
CHROME_DEVTOOLS_PATH: Final = "/.well-known/appspecific/com.chrome.devtools.json"

CONTROL_URL_ENV_NAME: Final = "FASTAPI_DETOUR_CONTROL_URL"
CONTROL_HTTP_TIMEOUT_SECONDS: Final = 10
RUN_JOURNAL_FILE_MODE: Final = 0o600

AIVM_INSTANCE: Final = "aivm"
AIVM_USER: Final = "ai"
AIVM_HOME: Final = PurePosixPath("/home/ai")
AIVM_SSH_PORT: Final = "22022"

AIVM_KEY_DIR: Final = Path.home() / ".local" / "share" / "aivm" / ".ssh"
AIVM_IDENTITY_FILE: Final = AIVM_KEY_DIR / "id_ed25519"
AIVM_KNOWN_HOSTS_FILE: Final = AIVM_KEY_DIR / "known_hosts"
LIMA_CONFIG_PATH: Final = Path.home() / ".lima" / AIVM_INSTANCE / "lima.yaml"
LIMA_SSH_CONFIG_PATH: Final = Path.home() / ".lima" / AIVM_INSTANCE / "ssh.config"
LIMA_APPENDWATCH_REPORT_PARAM: Final = APPENDWATCH_REPORT_ENV_NAME

AIVM_SSH_TARGET: Final = f"{AIVM_INSTANCE}-{AIVM_USER}"
AIVM_HOST_KEY_ALIAS: Final = f"lima-{AIVM_INSTANCE}-{AIVM_USER}"
SSH_EXECUTABLE: Final = "ssh"
SSH_CONFIG_FLAG: Final = "-F"
SSH_OPTION_FLAG: Final = "-o"
SSH_REMOTE_FORWARD_FLAG: Final = "-R"
AIVM_SSH_CONNECTION_COMMAND: Final = (
    SSH_EXECUTABLE,
    SSH_CONFIG_FLAG,
    str(LIMA_SSH_CONFIG_PATH),
    SSH_OPTION_FLAG,
    f"ProxyJump=lima-{AIVM_INSTANCE}",
    SSH_OPTION_FLAG,
    "HostName=127.0.0.1",
    SSH_OPTION_FLAG,
    f"Port={AIVM_SSH_PORT}",
    SSH_OPTION_FLAG,
    f"User={AIVM_USER}",
    SSH_OPTION_FLAG,
    f"IdentityFile={AIVM_IDENTITY_FILE}",
    SSH_OPTION_FLAG,
    "IdentitiesOnly=yes",
    SSH_OPTION_FLAG,
    "BatchMode=yes",
    SSH_OPTION_FLAG,
    "PasswordAuthentication=no",
    SSH_OPTION_FLAG,
    "KbdInteractiveAuthentication=no",
    SSH_OPTION_FLAG,
    "ForwardAgent=no",
    SSH_OPTION_FLAG,
    "ClearAllForwardings=no",
    SSH_OPTION_FLAG,
    f"UserKnownHostsFile={AIVM_KNOWN_HOSTS_FILE}",
    SSH_OPTION_FLAG,
    f"HostKeyAlias={AIVM_HOST_KEY_ALIAS}",
    SSH_OPTION_FLAG,
    "StrictHostKeyChecking=accept-new",
)

CODEX_SESSIONS_ROOT: Final = AIVM_HOME / ".codex" / "sessions"
CODEX_WORKDIR: Final = AIVM_HOME / "workdir"
CODEX_WORKBOOK_PATH: Final = CODEX_WORKDIR / "WORKBOOK.md"
CODEX_PROMPT_PATH: Final = CODEX_WORKDIR / "PROMPT.md"
CODEX_ENV_PATH: Final = CODEX_WORKDIR / ".openalex.env"
CODEX_CLI_BIN_PATH: Final = AIVM_HOME / ".local" / "bin" / "codex"
CODEX_RUN_MARKER_TEMPLATE: Final = ".codex-run-{run_id}.marker"
CODEX_RUN_PID_TEMPLATE: Final = ".codex-run-{run_id}.pid"
CODEX_DISCOVERY_TIMEOUT_SECONDS: Final = 30
CODEX_DISCOVERY_POLL_SECONDS: Final = 0.1
CODEX_CANCEL_TIMEOUT_SECONDS: Final = 10
CODEX_REMOTE_PROCESS_ALIVE_MARKER: Final = "alive"
CODEX_REMOTE_BUSY_MARKER: Final = "busy"
CODEX_REMOTE_PID_READ_COMMAND_TEMPLATE: Final = "cat -- {pid_path}"
CODEX_REMOTE_PROCESS_ALIVE_COMMAND_TEMPLATE: Final = (
    "if kill -0 -- {remote_pid} 2>/dev/null; then printf '%s' {alive_marker}; fi"
)
CODEX_REMOTE_SIGNAL_COMMAND_TEMPLATE: Final = "kill -{signal} -- {remote_pid}"
CODEX_REMOTE_TERMINATE_SIGNAL: Final = "TERM"
CODEX_REMOTE_KILL_SIGNAL: Final = "KILL"
CODEX_REMOTE_EXEC_COMMAND_TEMPLATE: Final = (
    "printf '%s\\n' \"$$\" > {pid_path}; . {environment_path}; exec {codex_command} < {prompt_path}"
)
CODEX_ENV_EXPORT_TEMPLATE: Final = "export {name}={value}\\n"
CODEX_REMOTE_WRITE_FILE_COMMAND_TEMPLATE: Final = (
    "mkdir -p -- {parent_path} && umask 077 && cat > {file_path}"
)
CODEX_REMOTE_PREPARE_RUN_COMMAND_TEMPLATE: Final = (
    "mkdir -p -- {workdir} && rm -f -- {pid_path} && touch -- {marker_path}"
)
CODEX_REMOTE_FIND_NEW_ROLLOUT_COMMAND_TEMPLATE: Final = (
    "find {sessions_root} -type f -name 'rollout-*.jsonl' "
    "-newer {marker_path} -print | LC_ALL=C sort | tail -n 1"
)
CODEX_REMOTE_FIRST_LINE_COMMAND_TEMPLATE: Final = "head -n 1 -- {rollout_path}"
CODEX_REMOTE_FIND_ROLLOUT_COMMAND_TEMPLATE: Final = (
    "find {sessions_root} -type f -name {rollout_name} -print | LC_ALL=C sort"
)
CODEX_ROLLOUT_FILENAME_TEMPLATE: Final = (
    "rollout-{local_timestamp:%Y-%m-%dT%H-%M-%S}-{session_id}.jsonl"
)
CODEX_PROMPT_TEMPLATE: Final = "{openapi_url}\n\n{workbook}"
CODEX_EXEC_COMMAND: Final = (
    str(CODEX_CLI_BIN_PATH),
    "exec",
    "--skip-git-repo-check",
    "-",
)
CODEX_REMOTE_PROCESS_PATTERN: Final = " ".join(
    (
        str(CODEX_CLI_BIN_PATH.parent / "[c]odex"),
        *CODEX_EXEC_COMMAND[1:],
    )
)
CODEX_REMOTE_BUSY_COMMAND_TEMPLATE: Final = (
    "if pgrep -f -- {process_pattern} >/dev/null; then printf '%s' {busy_marker}; fi"
)
CODEX_REMOTE_BUSY_COMMAND: Final = CODEX_REMOTE_BUSY_COMMAND_TEMPLATE.format(
    process_pattern=shlex.quote(CODEX_REMOTE_PROCESS_PATTERN),
    busy_marker=shlex.quote(CODEX_REMOTE_BUSY_MARKER),
)
CODEX_REMOTE_FORWARD: Final = f"{BACKEND_HOST}:{BACKEND_PORT}:{BACKEND_HOST}:{BACKEND_PORT}"
AIVM_SSH_FORWARD_COMMAND: Final = (
    *AIVM_SSH_CONNECTION_COMMAND,
    SSH_OPTION_FLAG,
    "ExitOnForwardFailure=yes",
    SSH_REMOTE_FORWARD_FLAG,
    CODEX_REMOTE_FORWARD,
    AIVM_SSH_TARGET,
)
DETOUR_VIEW_EXISTS_SQL: Final = "SELECT count(*) FROM information_schema.views WHERE table_name = ?"
DETOUR_TABLE_EXISTS_SQL: Final = (
    "SELECT count(*) FROM information_schema.tables WHERE table_name = ?"
)
ACCEPTED_ATTEMPTS_SQL_TEMPLATE: Final = (
    "SELECT {projection} FROM {output_view} ORDER BY {source_key_column}, {attempt_id_column}"
)
ARCHIVED_ATTEMPT_MANIFESTS_SQL: Final = (
    f"SELECT {duckdb_quote_identifier(ATTEMPT_ID_KEY)}, "
    f"{duckdb_quote_identifier(ARCHIVED_ATTEMPT_MANIFEST_COLUMN)} "
    f"FROM {duckdb_quote_identifier(ARCHIVED_ATTEMPTS_TABLE)} "
    f"ORDER BY {duckdb_quote_identifier(ATTEMPT_ID_KEY)}"
)
SQL_COLUMN_SEPARATOR: Final = ", "
RECONCILED_RUN_ID_TEMPLATE: Final = "{source_key}:{attempt_id}"
FOOTNOTE_MARKER = re.compile(r"\^(?P<numbers>[0-9]+(?:,[0-9]+)*)\^")
UI_REFRESH_SECONDS: Final = 1
GRID_ROW_ID_FIELD: Final = "row_id"
GRID_SOURCE_KEY_FIELD: Final = "source_key"
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

SourceKey = NewType("SourceKey", str)
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
    SourceKey,
]:
    return (
        tuple(draw_sort_key(draw) for draw in researcher.draw_numbers),
        researcher.first_name.casefold(),
        researcher.last_name.casefold(),
        researcher.source_key,
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
class DatabasePaths:
    source_db: Path
    detour_db: Path


@dataclass(frozen=True, slots=True)
class Researcher:
    source_key: SourceKey
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
    source_key: SourceKey
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
    source_key: SourceKey
    attempt_id: AttemptId
    session_metadata: SessionMetadata
    values: Mapping[str, str | None]
    footnotes: str | None
    footnote_arguments: str | None


# =============================================================================
# UI-owned durable run journal. Its validated DuckDB projection is the only
# source used to render run history.
# =============================================================================


@dataclass(slots=True)
class RunRecord:
    run_id: UUID
    source_key: SourceKey
    status: RunStatus

    queued_at: datetime

    started_at: datetime | None = None

    session_id: SessionId | None = None
    session_timestamp: datetime | None = None
    rollout_jsonl: PurePosixPath | None = None
    remote_pid: RemotePid | None = None

    sanctioned_at: datetime | None = None

    accepted_attempt_id: AttemptId | None = None
    accepted_at: datetime | None = None

    cancel_requested_at: datetime | None = None

    codex_exit_code: int | None = None
    exited_at: datetime | None = None

    failure_detail: str | None = None


# =============================================================================
# Control-plane protocol exposed by NiceGUI's FastAPI application
# =============================================================================


class ControlRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run_id: UUID
    source_key: str
    session_id: str
    rollout_jsonl: str


class ControlSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    sanctioned_run: ControlRunResponse | None


class PushAcceptedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_key: str
    session_id: str
    attempt_id: str

    @field_validator("source_key", "session_id", "attempt_id")
    @classmethod
    def normalized_nonblank(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError(Locale.ACCEPTED_IDENTIFIERS_INVALID)
        return value


class PushAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    acknowledged: bool


# =============================================================================
# View models
# =============================================================================


@dataclass(frozen=True, slots=True)
class AttemptView:
    run_id: UUID
    source_key: SourceKey

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

    source_key: SourceKey
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
    source_key: SourceKey
    rnd: int
    cohort: ResearcherCohort
    ineligibility_category: IneligibilityCategory | None

    # Collapsed row: latest attempt projection, or synthetic ready projection.
    latest: AttemptVariableProjection

    # Expanded row content: every attempt, oldest -> newest.
    attempts: tuple[AttemptVariableProjection, ...]


@dataclass(frozen=True, slots=True)
class ResearcherCardView:
    source_key: SourceKey
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

    selected_source_key: SourceKey | None = None
    selected_run_id: UUID | None = None
    selected_action: RunAction | None = None


@dataclass(frozen=True, slots=True)
class UiSnapshot:
    counts: DashboardCounts
    rows: tuple[ResearcherGridRow, ...]
    backend_status: BackendStatus
    active_run_id: UUID | None


class LimaMount(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    location: str
    mount_point: str = Field(alias="mountPoint")


class LimaConfiguration(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    param: Mapping[str, str]
    mounts: tuple[LimaMount, ...]


# =============================================================================
# Configuration / database location
# =============================================================================


class RuntimeConfiguration:
    def __init__(
        self,
        *,
        config_path: Path = DEFAULT_CONFIG_PATH,
    ) -> None:
        openalex_api_key = os.environ.get(EXPORT_OPENALEX_API_KEY, "").strip()
        if not openalex_api_key:
            raise RuntimeError(Locale.OPENALEX_API_KEY_MISSING)
        try:
            if LIMA_CONFIG_PATH.is_symlink() or not LIMA_CONFIG_PATH.is_file():
                raise OSError(Locale.LIMA_CONFIG_UNREADABLE)
            lima_value = yaml.safe_load(LIMA_CONFIG_PATH.read_text(encoding=TEXT_ENCODING))
            lima_configuration = LimaConfiguration.model_validate(lima_value)
            guest_report_value = lima_configuration.param[LIMA_APPENDWATCH_REPORT_PARAM]
            guest_report = PurePosixPath(guest_report_value)
            if (
                not guest_report.is_absolute()
                or str(guest_report) != guest_report_value
                or any(part in FORBIDDEN_NORMALIZED_PATH_PARTS for part in guest_report.parts)
            ):
                raise ValueError(Locale.LIMA_APPENDWATCH_PATH_INVALID)
            host_reports: list[Path] = []
            for mount in lima_configuration.mounts:
                host_root = Path(mount.location)
                guest_root = PurePosixPath(mount.mount_point)
                if (
                    not host_root.is_absolute()
                    or str(host_root) != mount.location
                    or not guest_root.is_absolute()
                    or str(guest_root) != mount.mount_point
                    or any(
                        part in FORBIDDEN_NORMALIZED_PATH_PARTS
                        for part in guest_root.parts
                    )
                ):
                    raise ValueError(Locale.LIMA_MOUNT_INVALID)
                try:
                    relative_report = guest_report.relative_to(guest_root)
                except ValueError:
                    continue
                host_reports.append(host_root.joinpath(*relative_report.parts))
        except (
            KeyError, OSError, UnicodeError, ValueError, ValidationError, yaml.YAMLError
        ) as exc:
            raise RuntimeError(Locale.LIMA_CONFIG_INVALID) from exc
        if len(host_reports) != 1:
            raise RuntimeError(Locale.LIMA_APPENDWATCH_MOUNT_INVALID)
        appendwatch_report = host_reports[0]
        if (
            appendwatch_report.is_symlink()
            or not appendwatch_report.is_file()
            or not os.access(appendwatch_report, os.R_OK)
        ):
            raise RuntimeError(Locale.LIMA_APPENDWATCH_REPORT_UNREADABLE)
        pipeline_config = PipelineConfig.from_json(config_path)
        release_map = registered_release_map(pipeline_config)
        release_batches = load_release_batches(release_map)
        source_connection = duckdb.connect(str(pipeline_config.db_file), read_only=True)
        try:
            source_population = derive_source_population(
                source_connection,
                release_batches,
                sample_seed=pipeline_config.sample_seed,
            )
        finally:
            source_connection.close()
        self._config_path = config_path
        self._pipeline_config = pipeline_config
        self._openalex_api_key = openalex_api_key
        self._appendwatch_report = appendwatch_report
        self._timezone = ZoneInfo(pipeline_config.timezone)
        self._database_paths = DatabasePaths(
            source_db=pipeline_config.db_file,
            detour_db=_detour_db_path(pipeline_config.db_file),
        )
        self._backend_runtime = BackendRuntimeConfiguration(
            pipeline=pipeline_config,
            detour_db_path=self._database_paths.detour_db,
            release_map=release_map,
            source_population=source_population,
            eligible_cohorts=eligible_cohorts(source_population),
        )

    @property
    def pipeline_config(self) -> PipelineConfig:
        return self._pipeline_config

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def openalex_api_key(self) -> str:
        return self._openalex_api_key

    @property
    def appendwatch_report(self) -> Path:
        return self._appendwatch_report

    @property
    def run_journal_path(self) -> Path:
        return self._database_paths.detour_db.parent / RUN_JOURNAL_PATH.name

    @property
    def timezone(self) -> ZoneInfo:
        return self._timezone

    @property
    def database_paths(self) -> DatabasePaths:
        return self._database_paths

    @property
    def backend_runtime(self) -> BackendRuntimeConfiguration:
        return self._backend_runtime


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
        configuration: RuntimeConfiguration,
    ) -> None:
        self._configuration = configuration

    def connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(
            str(self._configuration.database_paths.source_db),
            read_only=True,
        )

    def load_researchers(self) -> tuple[Researcher, ...]:
        result = tuple(
            Researcher(
                source_key=SourceKey(source.source_key),
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
            for source in self._configuration.backend_runtime.source_population
        )
        result = tuple(sorted(result, key=researcher_sort_key))
        self.assert_population_invariants(result)
        return result

    def load_ground_truth(
        self,
        source_key: SourceKey,
    ) -> GroundTruthRecord | None:
        connection = self.connect()
        try:
            researcher = load_source_researcher(
                connection,
                self._configuration.backend_runtime,
                source_key=source_key,
            )
            values = ground_truth_for_researcher(researcher)
        finally:
            connection.close()
        if values is None:
            return None
        return GroundTruthRecord(
            source_key=source_key,
            values={
                column: None if value is None else str(value) for column, value in values.items()
            },
        )

    def load_ground_truth_by_source_key(
        self,
    ) -> Mapping[SourceKey, GroundTruthRecord]:
        result: dict[SourceKey, GroundTruthRecord] = {}
        cohorts = self._configuration.backend_runtime.eligible_cohorts
        if cohorts is None:
            raise RuntimeError(Locale.ELIGIBLE_COHORTS_NOT_CONFIGURED)
        connection = self.connect()
        try:
            for source_key, cohort in sorted(cohorts.items()):
                if ResearcherCohort(cohort) is not ResearcherCohort.GROUND_TRUTH:
                    continue
                researcher = load_source_researcher(
                    connection,
                    self._configuration.backend_runtime,
                    source_key=source_key,
                )
                values = ground_truth_for_researcher(researcher)
                if values is None:
                    raise RuntimeError(Locale.GROUND_TRUTH_MISSING)
                typed_source_key = SourceKey(source_key)
                result[typed_source_key] = GroundTruthRecord(
                    source_key=typed_source_key,
                    values={
                        column: None if value is None else str(value)
                        for column, value in values.items()
                    },
                )
        finally:
            connection.close()
        return result

    def load_source_card_innerdicts(
        self,
        source_key: SourceKey,
    ) -> OuterDict:
        name_key = NameKey.from_json_key(source_key)
        outer_dict = OuterDict.from_name_keys([name_key])
        connection = self.connect()
        try:
            for table_name, procedure in (
                (XLSX_INNERDICT_TABLE, XlsxMatchProcedure()),
                (DOCX_INNERDICT_TABLE, DocxMatchProcedure()),
                (PARQUET_INNERDICT_TABLE, ParquetMatchProcedure()),
            ):
                append_innerdicts_from_jsonlines_table(
                    connection,
                    table_name=table_name,
                    outer_dict=outer_dict,
                    procedure=procedure,
                )
        finally:
            connection.close()
        return outer_dict

    def assert_population_invariants(
        self,
        researchers: Sequence[Researcher],
    ) -> None:
        source_keys = [researcher.source_key for researcher in researchers]
        ground_truth_count = sum(
            researcher.cohort is ResearcherCohort.GROUND_TRUTH for researcher in researchers
        )
        no_ground_truth_count = sum(
            researcher.cohort is ResearcherCohort.NO_GROUND_TRUTH for researcher in researchers
        )
        if len(set(source_keys)) != len(source_keys):
            raise RuntimeError(Locale.SOURCE_KEYS_NOT_UNIQUE)
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
# Detour DuckDB reads
#
# These calls are permitted only while no Codex/backend write transaction can
# be active. ControlCentreController owns that scheduling invariant.
# =============================================================================


class DetourRepository:
    def __init__(
        self,
        *,
        configuration: RuntimeConfiguration,
    ) -> None:
        self._configuration = configuration

    def connect_read_only(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(
            str(self._configuration.database_paths.detour_db),
            read_only=True,
        )

    def reconcile_archived_attempts(
        self,
        *,
        attempts_dir: Path | None = None,
    ) -> ArchivedAttemptRecovery:
        if attempts_dir is None:
            attempts_dir = self._configuration.backend_runtime.attempts_dir
        recovery = restore_archived_attempts(
            self._configuration.backend_runtime,
            attempts_dir=attempts_dir,
        )
        emit_log(
            Locale.CONTROL_CENTRE_LOG_PREFIX,
            Locale.ARCHIVED_ATTEMPTS_RECONCILED_TEMPLATE.format(
                restored=len(recovery.restored_attempt_ids),
                accepted=len(recovery.restored_accepted_attempt_ids),
                skipped=len(recovery.skipped_attempt_ids),
                invalid=recovery.invalid,
                discovered=recovery.discovered,
                directory=attempts_dir,
            ),
        )
        return recovery

    def persist_control_run_events(
        self,
        events: Sequence[RunEvent],
    ) -> int:
        return persist_control_run_events(
            self._configuration.backend_runtime,
            events,
        )

    def load_control_run_events(self) -> tuple[RunEvent, ...]:
        return load_control_run_events(self._configuration.backend_runtime)

    def load_accepted_attempts(
        self,
    ) -> Mapping[SourceKey, tuple[AcceptedAttempt, ...]]:
        database_path = self._configuration.database_paths.detour_db
        if not database_path.is_file():
            return {}
        connection = self.connect_read_only()
        try:
            view_exists = connection.execute(
                "SELECT count(*) FROM information_schema.views WHERE table_name = ?",
                [CODEX_OUTPUT_VIEW],
            ).fetchone()
            if view_exists is None or view_exists[0] != 1:
                return {}
            columns = (
                KTP_NAMEKEY_COL,
                KTP_AI_AUGMENT_ATTEMPT_ID_COL,
                KTP_AI_AUGMENT_SESSION_METADATA_COL,
                *AI_AUGMENT_COLUMNS,
                KTP_AI_AUGMENT_FOOTNOTES_COL,
                KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL,
            )
            projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
            rows = connection.execute(
                f"SELECT {projection} FROM {CODEX_OUTPUT_VIEW} "
                f"ORDER BY {duckdb_quote_identifier(KTP_NAMEKEY_COL)}, "
                f"{duckdb_quote_identifier(KTP_AI_AUGMENT_ATTEMPT_ID_COL)}"
            ).fetchall()
        finally:
            connection.close()

        attempts: dict[SourceKey, list[AcceptedAttempt]] = {}
        for row in rows:
            values = dict(zip(columns, row, strict=True))
            source_key = SourceKey(str(values[KTP_NAMEKEY_COL]))
            try:
                metadata_value = CompactSessionMetadata.model_validate_json(
                    str(values[KTP_AI_AUGMENT_SESSION_METADATA_COL])
                )
                metadata = SessionMetadata(
                    originator=metadata_value.originator,
                    source=metadata_value.source,
                    cli_version=metadata_value.cli_version,
                    model_provider=metadata_value.model_provider,
                    model=metadata_value.model,
                    reasoning_effort=metadata_value.reasoning_effort,
                    session_id=SessionId(metadata_value.session_id),
                    timestamp=datetime.fromisoformat(metadata_value.timestamp),
                )
            except (ValidationError, ValueError) as exc:
                raise RuntimeError(Locale.ACCEPTED_METADATA_INVALID) from exc
            attempts.setdefault(source_key, []).append(
                AcceptedAttempt(
                    source_key=source_key,
                    attempt_id=AttemptId(str(values[KTP_AI_AUGMENT_ATTEMPT_ID_COL])),
                    session_metadata=metadata,
                    values={
                        column: None if values[column] is None else str(values[column])
                        for column in AI_AUGMENT_COLUMNS
                    },
                    footnotes=(
                        None
                        if values[KTP_AI_AUGMENT_FOOTNOTES_COL] is None
                        else str(values[KTP_AI_AUGMENT_FOOTNOTES_COL])
                    ),
                    footnote_arguments=(
                        None
                        if values[KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL] is None
                        else str(values[KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL])
                    ),
                )
            )
        return {
            source_key: tuple(
                sorted(
                    source_attempts,
                    key=lambda attempt: (
                        attempt.session_metadata.timestamp,
                        attempt.attempt_id,
                    ),
                )
            )
            for source_key, source_attempts in attempts.items()
        }

    def load_attempt_manifests(
        self,
    ) -> Mapping[SourceKey, tuple[ArchivedAttemptManifest, ...]]:
        database_path = self._configuration.database_paths.detour_db
        if not database_path.is_file():
            return {}
        connection = self.connect_read_only()
        try:
            table_exists = connection.execute(
                DETOUR_TABLE_EXISTS_SQL,
                [ARCHIVED_ATTEMPTS_TABLE],
            ).fetchone()
            if table_exists is None or table_exists[0] != 1:
                return {}
            rows = connection.execute(ARCHIVED_ATTEMPT_MANIFESTS_SQL).fetchall()
        finally:
            connection.close()

        manifests: dict[SourceKey, list[ArchivedAttemptManifest]] = {}
        try:
            for stored_attempt_id, manifest_json in rows:
                manifest = ArchivedAttemptManifest.model_validate_json(str(manifest_json))
                if manifest.attempt_id != stored_attempt_id:
                    raise ValueError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
                if manifest.source_key is not None:
                    manifests.setdefault(SourceKey(manifest.source_key), []).append(manifest)
        except (ValidationError, ValueError) as exc:
            raise RuntimeError(Locale.ATTEMPT_DATABASE_INCONSISTENT) from exc
        return {
            source_key: tuple(source_manifests)
            for source_key, source_manifests in manifests.items()
        }

    def load_accepted_attempts_for_source_key(
        self,
        source_key: SourceKey,
    ) -> tuple[AcceptedAttempt, ...]:
        return self.load_accepted_attempts().get(source_key, ())

    def load_codex_card_innerdicts(
        self,
        source_key: SourceKey,
    ) -> OuterDict:
        name_key = NameKey.from_json_key(source_key)
        outer_dict = OuterDict.from_name_keys([name_key])
        database_path = self._configuration.database_paths.detour_db
        if not database_path.is_file():
            return outer_dict
        connection = self.connect_read_only()
        try:
            table_exists = connection.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
                [CODEX_INNERDICT_TABLE],
            ).fetchone()
            if table_exists is not None and table_exists[0] == 1:
                append_innerdicts_from_jsonlines_table(
                    connection,
                    table_name=CODEX_INNERDICT_TABLE,
                    outer_dict=outer_dict,
                    procedure=CodexMatchProcedure(),
                )
        finally:
            connection.close()
        return outer_dict


# =============================================================================
# Run journal
# =============================================================================


class RunJournal:
    def __init__(
        self,
        *,
        path: Path = RUN_JOURNAL_PATH,
    ) -> None:
        self._path = path

    def append(
        self,
        event: RunEvent,
    ) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = (event.model_dump_json() + "\n").encode(TEXT_ENCODING)
        descriptor = os.open(
            self._path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            RUN_JOURNAL_FILE_MODE,
        )
        try:
            if os.write(descriptor, payload) != len(payload):
                raise OSError(Locale.JOURNAL_APPEND_INCOMPLETE)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def load_events(self) -> tuple[RunEvent, ...]:
        if not self._path.exists():
            return ()
        events: list[RunEvent] = []
        with self._path.open(encoding=TEXT_ENCODING) as stream:
            for line_number, line in enumerate(stream, start=1):
                try:
                    events.append(RunEvent.model_validate_json(line))
                except ValidationError as exc:
                    raise RuntimeError(
                        Locale.JOURNAL_MALFORMED_TEMPLATE.format(line_number=line_number)
                    ) from exc
        return tuple(events)

    def load_runs(self) -> Mapping[UUID, RunRecord]:
        return self.replay(self.load_events())

    @staticmethod
    def replay(events: Sequence[RunEvent]) -> Mapping[UUID, RunRecord]:
        runs: dict[UUID, RunRecord] = {}
        for event in events:
            if event.kind is RunEventKind.QUEUED:
                if event.run_id in runs:
                    raise RuntimeError(Locale.JOURNAL_DUPLICATE_RUN_ID)
                runs[event.run_id] = RunRecord(
                    run_id=event.run_id,
                    source_key=SourceKey(event.source_key),
                    status=RunStatus.QUEUED,
                    queued_at=event.at,
                )
                continue
            run = runs.get(event.run_id)
            if run is None or run.source_key != event.source_key:
                raise RuntimeError(Locale.JOURNAL_EVENT_WITHOUT_RUN)
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
            elif event.kind is RunEventKind.SANCTIONED:
                run.sanctioned_at = event.at
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

    def runs_for_source_key(
        self,
        source_key: SourceKey,
    ) -> tuple[RunRecord, ...]:
        return tuple(
            sorted(
                (run for run in self.load_runs().values() if run.source_key == source_key),
                key=lambda run: (run.queued_at, str(run.run_id)),
            )
        )


# =============================================================================
# Card rendering
# =============================================================================


class ResearcherCardRenderer:
    def __init__(
        self,
        *,
        source_repository: SourceRepository,
        detour_repository: DetourRepository,
        configuration: RuntimeConfiguration,
    ) -> None:
        self._source_repository = source_repository
        self._detour_repository = detour_repository
        self._configuration = configuration

    def render(
        self,
        source_key: SourceKey,
    ) -> ResearcherCardView:
        researchers = {
            researcher.source_key: researcher
            for researcher in self._source_repository.load_researchers()
        }
        researcher = researchers.get(source_key)
        if researcher is None:
            raise KeyError(Locale.UNKNOWN_SOURCE_KEY_TEMPLATE.format(source_key=source_key))
        cards = build_cards(
            self.build_outer_dict(source_key),
            total_draws=self._configuration.pipeline_config.total_draws,
            intro=CARD_INTRODUCTION.format(
                datetime.now(self._configuration.timezone).strftime(Locale.CARD_INTRO_DATE_FORMAT)
            ),
            excluded_cols=CARD_EXCLUDED_COLUMNS,
        )
        if len(cards) != 1:
            raise RuntimeError(Locale.CARD_COUNT_INVALID)
        return ResearcherCardView(
            source_key=source_key,
            draw_number=researcher.draw_number,
            first_name=researcher.first_name,
            last_name=researcher.last_name,
            markdown=next(iter(cards.values())),
        )

    def build_outer_dict(
        self,
        source_key: SourceKey,
    ) -> OuterDict:
        name_key = NameKey.from_json_key(source_key)
        source_outer = self._source_repository.load_source_card_innerdicts(source_key)
        codex_outer = self._detour_repository.load_codex_card_innerdicts(source_key)
        source_inners = source_outer.get_inner_by_key(source_key)
        xlsx_inners = tuple(
            inner for inner in source_inners if isinstance(inner.procedure, XlsxMatchProcedure)
        )
        docx_inners = tuple(
            inner for inner in source_inners if isinstance(inner.procedure, DocxMatchProcedure)
        )
        ssn_inners = tuple(
            inner for inner in source_inners if isinstance(inner.procedure, ParquetMatchProcedure)
        )
        return OuterDict(
            data={
                name_key.to_json_key(): [
                    *xlsx_inners,
                    *codex_outer.get_inner_by_key(source_key),
                    *docx_inners,
                    *ssn_inners,
                ]
            }
        )


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
        control_url: str,
        openalex_api_key: str,
        appendwatch_report: Path,
        control_run_events_token: str,
    ) -> None:
        self._repository_root = repository_root
        self._config_path = config_path
        self._control_url = control_url
        self._openalex_api_key = openalex_api_key
        self._appendwatch_report = appendwatch_report
        self._control_run_events_token = control_run_events_token
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

    async def start(self) -> None:
        if self._process is not None and self._process.process.returncode is None:
            return
        self._status = BackendStatus.STARTING
        process = await asyncio.create_subprocess_exec(
            *BACKEND_COMMAND_PREFIX,
            str(self._config_path),
            cwd=self._repository_root,
            env=self.environment(),
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
                return
            except OSError, urllib_error.URLError, urllib_error.HTTPError:
                await asyncio.sleep(BACKEND_READY_POLL_SECONDS)
        raise TimeoutError(Locale.BACKEND_READY_TIMEOUT)

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

    def persist_run_events(self, events: Sequence[RunEvent]) -> int:
        body = ControlRunEventsRequest(events=tuple(events)).model_dump_json().encode(
            TEXT_ENCODING
        )
        request = urllib_request.Request(
            BACKEND_CONTROL_RUN_EVENTS_URL,
            data=body,
            headers={
                HTTP_CONTENT_TYPE_HEADER: JSON_MEDIA_TYPE,
                CONTROL_RUN_EVENTS_TOKEN_HEADER: self._control_run_events_token,
            },
            method=HTTP_PUT_METHOD,
        )
        try:
            with urllib_request.urlopen(
                request,
                timeout=CONTROL_HTTP_TIMEOUT_SECONDS,
            ) as response:
                result = ControlRunEventsResponse.model_validate_json(response.read())
        except (OSError, urllib_error.URLError, urllib_error.HTTPError, ValidationError) as exc:
            raise RuntimeError(Locale.CONTROL_RUN_EVENTS_PERSIST_FAILED) from exc
        return result.persisted

    async def stop(self) -> None:
        if self._process is None:
            self._status = BackendStatus.STOPPED
            return
        process = self._process.process
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
        self._process = None
        self._status = BackendStatus.STOPPED

    async def wait(self) -> int:
        if self._process is None:
            raise RuntimeError(Locale.BACKEND_NOT_RUNNING)
        return await self._process.process.wait()

    def environment(self) -> Mapping[str, str]:
        environment = os.environ.copy()
        environment[CONTROL_URL_ENV_NAME] = self._control_url
        environment[EXPORT_OPENALEX_API_KEY] = self._openalex_api_key
        environment[APPENDWATCH_REPORT_ENV_NAME] = str(self._appendwatch_report)
        environment[CONTROL_PARENT_PID_ENV_NAME] = str(os.getpid())
        environment[CONTROL_RUN_EVENTS_TOKEN_ENV_NAME] = self._control_run_events_token
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
            prompt_path=shlex.quote(str(CODEX_PROMPT_PATH)),
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
        HOST_WORKBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not HOST_WORKBOOK_PATH.exists():
            HOST_WORKBOOK_PATH.write_bytes(b"")
        workbook_bytes = HOST_WORKBOOK_PATH.read_bytes()
        workbook_text = workbook_bytes.decode(TEXT_ENCODING)
        await self._write_remote_file(CODEX_WORKBOOK_PATH, workbook_bytes)
        prompt_bytes = CODEX_PROMPT_TEMPLATE.format(
            openapi_url=self._openapi_url,
            workbook=workbook_text,
        ).encode(TEXT_ENCODING)
        await self._write_remote_file(CODEX_PROMPT_PATH, prompt_bytes)
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
            start_new_session=True,
        )
        handle = CodexProcessHandle(run_id=run_id, process=process)
        try:
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
                await self.terminate_remote_pid(remote_pid)
            elif handle.process.returncode is None:
                raise RuntimeError(Locale.CODEX_REMOTE_PID_MISSING)
        except Exception as exc:
            remote_error = exc
        finally:
            await self._stop_process(handle.process)
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
# Control-plane state
#
# This is the authoritative current human sanction presented to api.py.
# It is intentionally independent of the durable accepted-output database.
# =============================================================================


@dataclass(frozen=True, slots=True)
class SanctionedRun:
    run_id: UUID
    source_key: SourceKey
    session_id: SessionId
    rollout_jsonl: PurePosixPath
    sanctioned_at: datetime


class ControlPlane:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sanctioned_run: SanctionedRun | None = None

    async def sanction(
        self,
        run: SanctionedRun,
    ) -> None:
        async with self._lock:
            if self._sanctioned_run is not None:
                raise RuntimeError(Locale.SANCTION_ALREADY_ACTIVE)
            self._sanctioned_run = run

    async def revoke(
        self,
        *,
        run_id: UUID,
    ) -> None:
        async with self._lock:
            if self._sanctioned_run is not None and self._sanctioned_run.run_id == run_id:
                self._sanctioned_run = None

    async def clear(self) -> None:
        async with self._lock:
            self._sanctioned_run = None

    async def current(self) -> SanctionedRun | None:
        async with self._lock:
            return self._sanctioned_run

    async def snapshot(self) -> ControlSnapshotResponse:
        run = await self.current()
        return ControlSnapshotResponse(
            sanctioned_run=(
                None
                if run is None
                else ControlRunResponse(
                    run_id=run.run_id,
                    source_key=run.source_key,
                    session_id=run.session_id,
                    rollout_jsonl=str(run.rollout_jsonl),
                )
            )
        )


# =============================================================================
# Reconciliation of local runs with authoritative accepted DuckDB output
# =============================================================================


class AttemptReconciler:
    def reconcile(
        self,
        *,
        researcher: Researcher,
        runs: Sequence[RunRecord],
        attempt_manifests: Sequence[ArchivedAttemptManifest],
        accepted_attempts: Sequence[AcceptedAttempt],
    ) -> ResearcherView:
        accepted_by_attempt_id = {attempt.attempt_id: attempt for attempt in accepted_attempts}
        attempts: list[AttemptView] = []
        for manifest in sorted(attempt_manifests, key=lambda item: item.attempt_id):
            attempt_id = AttemptId(manifest.attempt_id)
            accepted = accepted_by_attempt_id.pop(attempt_id, None)
            status = ARCHIVED_ATTEMPT_STATUS_BY_RESULT.get(manifest.result)
            try:
                timestamp = datetime.fromisoformat(manifest.updated_at)
            except ValueError as exc:
                raise RuntimeError(Locale.ATTEMPT_DATABASE_INCONSISTENT) from exc
            if (
                status is None
                or timestamp.tzinfo is None
                or manifest.source_key != researcher.source_key
                or (status is RunStatus.COMPLETE) != (accepted is not None)
                or (
                    accepted is not None
                    and (
                        manifest.session_id is None
                        or manifest.session_id != accepted.session_metadata.session_id
                    )
                )
            ):
                raise RuntimeError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
            attempts.append(
                AttemptView(
                    run_id=(
                        manifest.run_id
                        if manifest.run_id is not None
                        else uuid5(
                            NAMESPACE_URL,
                            RECONCILED_RUN_ID_TEMPLATE.format(
                                source_key=researcher.source_key,
                                attempt_id=attempt_id,
                            ),
                        )
                    ),
                    source_key=researcher.source_key,
                    status=status,
                    attempt_id=attempt_id,
                    session_id=(
                        accepted.session_metadata.session_id
                        if accepted is not None
                        else (
                            None
                            if manifest.session_id is None
                            else SessionId(manifest.session_id)
                        )
                    ),
                    timestamp=timestamp,
                    ended_at=timestamp,
                    accepted=accepted,
                    failure_detail=None,
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
                    source_key=researcher.source_key,
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
        attempt_manifests: Mapping[SourceKey, tuple[ArchivedAttemptManifest, ...]],
        accepted_attempts: Mapping[SourceKey, tuple[AcceptedAttempt, ...]],
    ) -> tuple[ResearcherView, ...]:
        runs_by_source_key: dict[SourceKey, list[RunRecord]] = {}
        for run in runs.values():
            runs_by_source_key.setdefault(run.source_key, []).append(run)
        return tuple(
            self.reconcile(
                researcher=researcher,
                runs=runs_by_source_key.get(researcher.source_key, ()),
                attempt_manifests=attempt_manifests.get(researcher.source_key, ()),
                accepted_attempts=accepted_attempts.get(researcher.source_key, ()),
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
            source_key=researcher.source_key,
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
            source_key=researcher.source_key,
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
            source_key=researcher_view.researcher.source_key,
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
# During that attempt:
#   - source DB reads remain allowed;
#   - detour DB reads from this process are suspended;
#   - api.py remains the only detour DB writer;
#   - current sanction is served from ControlPlane.
# =============================================================================


class ControlCentreController:
    def __init__(
        self,
        *,
        configuration: RuntimeConfiguration,
        source_repository: SourceRepository,
        detour_repository: DetourRepository,
        journal: RunJournal,
        card_renderer: ResearcherCardRenderer,
        backend: BackendSupervisor,
        codex: CodexRunner,
        control_plane: ControlPlane,
        reconciler: AttemptReconciler,
        projector: VariableProjector,
    ) -> None:
        self._configuration = configuration
        self._source_repository = source_repository
        self._detour_repository = detour_repository
        self._journal = journal
        self._card_renderer = card_renderer
        self._backend = backend
        self._codex = codex
        self._control_plane = control_plane
        self._reconciler = reconciler
        self._projector = projector
        self._queue: asyncio.Queue[UUID] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._active_run_id: UUID | None = None
        self._active_codex: CodexProcessHandle | None = None
        self._external_codex_busy = False
        self._archive_rescan_required = True
        self._shutting_down = False
        self._idle_refresh_lock = asyncio.Lock()
        self._runs: dict[UUID, RunRecord] = dict(journal.load_runs())
        self._researchers: tuple[Researcher, ...] = ()
        self._researchers_by_source_key: dict[SourceKey, Researcher] = {}
        self._ground_truth: Mapping[SourceKey, GroundTruthRecord] = {}
        self._attempt_manifests: Mapping[
            SourceKey,
            tuple[ArchivedAttemptManifest, ...],
        ] = {}
        self._accepted_attempts: Mapping[SourceKey, tuple[AcceptedAttempt, ...]] = {}

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
        self._researchers_by_source_key = {
            researcher.source_key: researcher for researcher in self._researchers
        }
        self._ground_truth = await asyncio.to_thread(
            self._source_repository.load_ground_truth_by_source_key
        )
        await self._reconcile_and_load_attempts()
        restart_time = datetime.now(timezone.utc)
        for run in tuple(self._runs.values()):
            if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
                await self._codex.terminate_abandoned_run(run.run_id)
                await self._append_run_event(
                    RunEvent(
                        run_id=run.run_id,
                        source_key=run.source_key,
                        at=restart_time,
                        kind=RunEventKind.FAILED,
                        detail=Locale.RESTART_INTERRUPTED_RUN,
                    )
                )
        await self.refresh_idle_state(reconcile_before_busy_probe=True)
        await self._backend.start()
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
        await self._control_plane.clear()
        shutdown_time = datetime.now(timezone.utc)
        for run in tuple(self._runs.values()):
            if run.status in LIVE_RUN_STATUSES:
                await self._append_run_event(
                    RunEvent(
                        run_id=run.run_id,
                        source_key=run.source_key,
                        at=shutdown_time,
                        kind=RunEventKind.FAILED,
                        detail=Locale.SHUTDOWN_INTERRUPTED_RUN,
                    )
                )
        await self._backend.stop()

    async def queue(
        self,
        *,
        source_key: SourceKey,
    ) -> UUID:
        researcher = self._researchers_by_source_key.get(source_key)
        if researcher is None:
            raise KeyError(Locale.UNKNOWN_SOURCE_KEY_TEMPLATE.format(source_key=source_key))
        if researcher.cohort is ResearcherCohort.INELIGIBLE:
            raise ValueError(Locale.INELIGIBLE_QUEUE)
        run_id = uuid4()
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                source_key=source_key,
                at=datetime.now(timezone.utc),
                kind=RunEventKind.QUEUED,
            )
        )
        await self._queue.put(run_id)
        return run_id

    async def rerun(
        self,
        *,
        source_key: SourceKey,
    ) -> UUID:
        return await self.queue(source_key=source_key)

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
                source_key=run.source_key,
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
                            source_key=run.source_key,
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
                    source_key=run.source_key,
                    at=datetime.now(timezone.utc),
                    kind=RunEventKind.CANCELED,
                )
            )

    async def acknowledge_push(
        self,
        *,
        run_id: UUID,
        request: PushAcceptedRequest,
    ) -> None:
        sanctioned = await self._control_plane.current()
        if (
            sanctioned is None
            or sanctioned.run_id != run_id
            or sanctioned.source_key != request.source_key
            or sanctioned.session_id != request.session_id
        ):
            raise ValueError(Locale.ACCEPTED_PUSH_MISMATCH)
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                source_key=sanctioned.source_key,
                at=datetime.now(timezone.utc),
                kind=RunEventKind.PUSH_ACCEPTED,
                session_id=sanctioned.session_id,
                accepted_attempt_id=request.attempt_id,
            )
        )
        await self._control_plane.revoke(run_id=run_id)

    async def refresh_idle_state(
        self,
        *,
        reconcile_before_busy_probe: bool = False,
    ) -> None:
        if self._shutting_down:
            return
        async with self._idle_refresh_lock:
            if self._shutting_down:
                return
            if self._active_run_id is not None or await self._control_plane.current() is not None:
                return
            if not reconcile_before_busy_probe:
                try:
                    self._external_codex_busy = await self._codex.is_busy()
                except Exception:
                    if self._shutting_down:
                        return
                    raise
                if self._external_codex_busy:
                    self._archive_rescan_required = True
                    return
            if self._archive_rescan_required:
                await self._reconcile_and_load_attempts()
            if reconcile_before_busy_probe:
                self._external_codex_busy = await self._codex.is_busy()
                if self._external_codex_busy:
                    self._archive_rescan_required = True

    async def _reconcile_and_load_attempts(self) -> None:
        await asyncio.to_thread(self._detour_repository.reconcile_archived_attempts)
        await asyncio.to_thread(
            self._detour_repository.persist_control_run_events,
            self._journal.load_events(),
        )
        control_run_events = await asyncio.to_thread(
            self._detour_repository.load_control_run_events
        )
        self._runs = dict(RunJournal.replay(control_run_events))
        self._archive_rescan_required = False
        await self._load_attempts_from_database()

    async def _load_attempts_from_database(self) -> None:
        self._attempt_manifests = await asyncio.to_thread(
            self._detour_repository.load_attempt_manifests
        )
        self._accepted_attempts = await asyncio.to_thread(
            self._detour_repository.load_accepted_attempts
        )

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
            attempt_manifests=self._attempt_manifests,
            accepted_attempts=self._accepted_attempts,
        )
        all_rows = tuple(
            self._projector.project_researcher(
                researcher_view=view,
                ground_truth=self._ground_truth.get(view.researcher.source_key),
                variable=variable,
                codex_busy=self.codex_busy,
            )
            for view in views
        )
        search_text = selection.search_text.casefold().strip()
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
                or search_text in view.researcher.source_key.casefold()
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
        source_key: SourceKey,
    ) -> ResearcherCardView:
        if self.codex_busy:
            raise RuntimeError(Locale.CARD_READ_SUSPENDED)
        return await asyncio.to_thread(self._card_renderer.render, source_key)

    async def _worker(self) -> None:
        while True:
            run_id = await self._queue.get()
            try:
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
                        source_key=run.source_key,
                        at=datetime.now(timezone.utc),
                        kind=(RunEventKind.CANCELED if canceled else RunEventKind.FAILED),
                        detail=None if canceled else str(exc),
                    )
                )
            finally:
                await self._control_plane.revoke(run_id=run_id)
                self._active_codex = None
                self._active_run_id = None
                self._queue.task_done()
                if not self._shutting_down:
                    await self._load_attempts_from_database()
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
        result = await self._codex.start(
            run_id=run_id,
            on_handle=self._register_active_codex,
        )
        if self._runs[run_id].cancel_requested_at is not None:
            await self._codex.cancel(result.handle)
            raise RuntimeError(Locale.CODEX_CANCELED_BEFORE_SANCTION)
        self._active_codex = result.handle
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                source_key=run.source_key,
                at=result.session_timestamp,
                kind=RunEventKind.SESSION_DISCOVERED,
                session_id=result.session_id,
            )
        )

        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                source_key=run.source_key,
                at=datetime.now(timezone.utc),
                kind=RunEventKind.ROLLOUT_DISCOVERED,
                session_id=result.session_id,
                rollout_jsonl=str(result.rollout_jsonl),
            )
        )
        sanctioned_at = datetime.now(timezone.utc)
        await self._control_plane.sanction(
            SanctionedRun(
                run_id=run_id,
                source_key=run.source_key,
                session_id=result.session_id,
                rollout_jsonl=result.rollout_jsonl,
                sanctioned_at=sanctioned_at,
            )
        )
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                source_key=run.source_key,
                at=sanctioned_at,
                kind=RunEventKind.SANCTIONED,
                session_id=result.session_id,
                rollout_jsonl=str(result.rollout_jsonl),
            )
        )
        await self._backend.probe_pull()
        exit_code = await self._codex.wait(result.handle)
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                source_key=run.source_key,
                at=datetime.now(timezone.utc),
                kind=RunEventKind.CODEX_EXITED,
                codex_exit_code=exit_code,
            )
        )
        await self._control_plane.revoke(run_id=run_id)
        final_status = await self._finalize_run(
            run_id=run_id,
            codex_exit_code=exit_code,
        )
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                source_key=run.source_key,
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
                source_key=run.source_key,
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
                source_key=run.source_key,
                session_id=run.session_id,
            )
            if accepted is not None:
                await self._append_run_event(
                    RunEvent(
                        run_id=run_id,
                        source_key=run.source_key,
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
        source_key: SourceKey,
        session_id: SessionId,
    ) -> AcceptedAttempt | None:
        attempts = await asyncio.to_thread(
            self._detour_repository.load_accepted_attempts_for_source_key,
            source_key,
        )
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
        self._journal.append(event)
        events = self._journal.load_events()
        if self._backend.status is BackendStatus.RUNNING:
            await asyncio.to_thread(self._backend.persist_run_events, events)
            persisted_events = events
        else:
            await asyncio.to_thread(
                self._detour_repository.persist_control_run_events,
                events,
            )
            persisted_events = await asyncio.to_thread(
                self._detour_repository.load_control_run_events
            )
        self._runs = dict(RunJournal.replay(persisted_events))


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
        self._row_views_by_source_key: dict[SourceKey, ResearcherGridRow] = {}
        self._expanded_history_source_key: SourceKey | None = None
        self._card_cache: dict[SourceKey, ResearcherCardView] = {}

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
                GRID_ROW_ID_FIELD: row.source_key,
                GRID_SOURCE_KEY_FIELD: row.source_key,
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
        self._row_views_by_source_key = {row.source_key: row for row in snapshot.rows}
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
        source_key = self._expanded_history_source_key
        table = self._handles.attempt_history_table
        if source_key is None or table is None:
            return
        row = self._row_views_by_source_key.get(source_key)
        if row is None:
            return
        table.update_rows(
            self.attempt_detail_rows(row=row),
            clear_selection=False,
        )

    async def refresh_card(self) -> None:
        source_key = self._selection.selected_source_key
        if source_key is None or self._controller.codex_busy:
            return
        card = self._card_cache.get(source_key)
        if card is None:
            card = await self._controller.researcher_card(source_key=source_key)
            self._card_cache[source_key] = card
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
        source_key: SourceKey,
    ) -> None:
        expansion = self._handles.attempt_history_expansion
        table = self._handles.attempt_history_table
        row = self._row_views_by_source_key.get(source_key)
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
        self._expanded_history_source_key = source_key

    async def on_variable_changed(
        self,
        variable_key: str,
    ) -> None:
        if variable_key not in VARIABLE_SPEC_BY_KEY:
            raise KeyError(Locale.UNKNOWN_VARIABLE_TEMPLATE.format(variable_key=variable_key))
        self._selection.variable_key = variable_key
        await self.refresh_grid()
        expanded_source_key = self._expanded_history_source_key
        if expanded_source_key is not None:
            self.show_attempt_history(expanded_source_key)

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
        source_key: SourceKey,
    ) -> None:
        self._selection.selected_source_key = source_key
        await self.refresh_card()

    def sync_selected_action(
        self,
        rows: Sequence[Mapping[str, object]],
    ) -> None:
        selected_source_key = self._selection.selected_source_key
        selected = next(
            (row for row in rows if row.get(GRID_SOURCE_KEY_FIELD) == selected_source_key),
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
        source_key: SourceKey,
    ) -> None:
        self._card_cache.pop(source_key, None)
        run_id = await self._controller.queue(source_key=source_key)
        self._selection.selected_run_id = run_id
        self._selection.selected_action = RunAction.CANCEL
        self.update_execute_button()

    async def on_rerun(
        self,
        source_key: SourceKey,
    ) -> None:
        self._card_cache.pop(source_key, None)
        run_id = await self._controller.rerun(source_key=source_key)
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
        source_key: SourceKey,
        run_id: UUID | None,
    ) -> None:
        if action is RunAction.QUEUE:
            await self.on_queue(source_key)
        elif action is RunAction.RERUN:
            await self.on_rerun(source_key)
        elif action is RunAction.CANCEL and run_id is not None:
            await self.on_cancel(run_id)

    async def on_execute_selected(self) -> None:
        source_key = self._selection.selected_source_key
        action = self._selection.selected_action
        if source_key is None or action is None or action is RunAction.DISABLED:
            return
        await self.on_grid_action(
            action=action,
            source_key=source_key,
            run_id=self._selection.selected_run_id,
        )

    async def _on_grid_cell_clicked(self, event: Any) -> None:
        arguments = event.args
        data = arguments.get(AgGrid.EVENT_DATA, {})
        source_key = SourceKey(str(data.get(GRID_SOURCE_KEY_FIELD, "")))
        if not source_key:
            return
        self._selection.selected_source_key = source_key
        self.sync_selected_action((data,))
        self.show_attempt_history(source_key)


# =============================================================================
# Application-level dependency graph
# =============================================================================


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    configuration: RuntimeConfiguration

    source_repository: SourceRepository
    detour_repository: DetourRepository
    journal: RunJournal
    card_renderer: ResearcherCardRenderer

    backend: BackendSupervisor
    codex: CodexRunner
    control_plane: ControlPlane

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
    configuration = RuntimeConfiguration(config_path=config_path)
    source_repository = SourceRepository(configuration=configuration)
    detour_repository = DetourRepository(configuration=configuration)
    journal = RunJournal(path=configuration.run_journal_path)
    card_renderer = ResearcherCardRenderer(
        source_repository=source_repository,
        detour_repository=detour_repository,
        configuration=configuration,
    )
    backend = BackendSupervisor(
        repository_root=REPOSITORY_ROOT,
        config_path=configuration.config_path,
        control_url=CONTROL_CENTRE_BASE_URL,
        openalex_api_key=configuration.openalex_api_key,
        appendwatch_report=configuration.appendwatch_report,
        control_run_events_token=uuid4().hex,
    )
    codex = CodexRunner(
        timezone=configuration.timezone,
        openalex_api_key=configuration.openalex_api_key,
    )
    control_plane = ControlPlane()
    reconciler = AttemptReconciler()
    projector = VariableProjector()
    controller = ControlCentreController(
        configuration=configuration,
        source_repository=source_repository,
        detour_repository=detour_repository,
        journal=journal,
        card_renderer=card_renderer,
        backend=backend,
        codex=codex,
        control_plane=control_plane,
        reconciler=reconciler,
        projector=projector,
    )
    return ApplicationServices(
        configuration=configuration,
        source_repository=source_repository,
        detour_repository=detour_repository,
        journal=journal,
        card_renderer=card_renderer,
        backend=backend,
        codex=codex,
        control_plane=control_plane,
        reconciler=reconciler,
        projector=projector,
        controller=controller,
    )


def require_services() -> ApplicationServices:
    if SERVICES is None:
        raise RuntimeError(Locale.SERVICES_NOT_STARTED)
    return SERVICES


# =============================================================================
# Backend-facing loopback control API
# =============================================================================


@app.get(
    CONTROL_CURRENT_PATH,
    response_model=ControlSnapshotResponse,
    include_in_schema=False,
)
async def control_current() -> ControlSnapshotResponse:
    return await require_services().control_plane.snapshot()


@app.post(
    CONTROL_ACCEPTED_PATH_TEMPLATE,
    response_model=PushAcceptedResponse,
    include_in_schema=False,
)
async def control_push_accepted(
    run_id: UUID,
    request: PushAcceptedRequest,
) -> PushAcceptedResponse:
    try:
        await require_services().controller.acknowledge_push(
            run_id=run_id,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from None
    return PushAcceptedResponse(acknowledged=True)


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
