from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Final, Literal, NewType
from uuid import UUID
from zoneinfo import ZoneInfo

import duckdb
from fastapi import Header
from nicegui import app, ui
from pydantic import BaseModel, ConfigDict

from src.helpers.cards import build_cards
from src.helpers.config import PipelineConfig
from src.helpers.data_models import OuterDict
from src.helpers.vars import (
    DRAW_LABEL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_SOURCE_KEY_COL,
)


# =============================================================================
# Paths / process configuration
# =============================================================================

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[5]
DETOUR_ROOT: Final = Path(__file__).resolve().parents[2]
DETOUR_DATA_DIR: Final = DETOUR_ROOT / "data"

DEFAULT_CONFIG_PATH: Final = REPOSITORY_ROOT / "config.repl.json"

RUN_JOURNAL_PATH: Final = DETOUR_DATA_DIR / "control_centre_runs.jsonl"

BACKEND_PIXI_ENVIRONMENT: Final = "detour-ai-augment-backend-api"
BACKEND_PIXI_TASK: Final = "serve"
BACKEND_COMMAND: Final = (
    "pixi",
    "run",
    "-e",
    BACKEND_PIXI_ENVIRONMENT,
    BACKEND_PIXI_TASK,
)

BACKEND_HOST: Final = "127.0.0.1"
BACKEND_PORT: Final = 8612
BACKEND_BASE_URL: Final = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
BACKEND_OPENAPI_URL: Final = f"{BACKEND_BASE_URL}/openapi.json"

CONTROL_CENTRE_HOST: Final = "127.0.0.1"
CONTROL_CENTRE_PORT: Final = 8611
CONTROL_CENTRE_BASE_URL: Final = (
    f"http://{CONTROL_CENTRE_HOST}:{CONTROL_CENTRE_PORT}"
)

CONTROL_API_PREFIX: Final = "/_control"
CONTROL_CURRENT_PATH: Final = f"{CONTROL_API_PREFIX}/current"
CONTROL_ACCEPTED_PATH_TEMPLATE: Final = (
    f"{CONTROL_API_PREFIX}/runs/{{run_id}}/accepted"
)

CONTROL_URL_ENV_NAME: Final = "FASTAPI_DETOUR_CONTROL_URL"

AIVM_INSTANCE: Final = "aivm"
AIVM_USER: Final = "ai"
AIVM_HOME: Final = PurePosixPath("/home/ai")
AIVM_SSH_PORT: Final = "22022"

AIVM_KEY_DIR: Final = Path.home() / ".local" / "share" / "aivm" / ".ssh"
AIVM_IDENTITY_FILE: Final = AIVM_KEY_DIR / "id_ed25519"
AIVM_KNOWN_HOSTS_FILE: Final = AIVM_KEY_DIR / "known_hosts"
LIMA_SSH_CONFIG_PATH: Final = Path.home() / ".lima" / AIVM_INSTANCE / "ssh.config"

AIVM_SSH_TARGET: Final = f"{AIVM_INSTANCE}-{AIVM_USER}"
AIVM_HOST_KEY_ALIAS: Final = f"lima-{AIVM_INSTANCE}-{AIVM_USER}"

CODEX_SESSIONS_ROOT: Final = AIVM_HOME / ".codex" / "sessions"

CARD_PARTITION_TABLE: Final = "card_partitions"
CODEX_OUTPUT_ROWS_TABLE: Final = "codex_output_rows"
CODEX_OUTPUT_VIEW: Final = "codex_output"
CODEX_INNERDICT_TABLE: Final = "codex_innerdicts"

EXPECTED_GROUND_TRUTH_RESEARCHERS: Final = 196
EXPECTED_NO_GROUND_TRUTH_RESEARCHERS: Final = 78
EXPECTED_ELIGIBLE_RESEARCHERS: Final = 274

INELIGIBLE_SHIPPED_DRAW_NUMBERS: Final = frozenset({"45", "172", "256"})


# =============================================================================
# Detour-owned schema labels
# =============================================================================

KTP_AI_AUGMENT_ATTEMPT_ID_COL: Final = "ktp.ai_augment_attempt_id"
KTP_AI_AUGMENT_SESSION_METADATA_COL: Final = "ktp.ai_augment_session_metadata"

KTP_AI_AUGMENT_FOOTNOTES_COL: Final = "ktp.ai_augment_footnotes"
KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL: Final = (
    "ktp.ai_augment_footnote_arguments"
)

KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL: Final = (
    "ktp.ai_augment_researcher_author"
)
KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL: Final = (
    "ktp.ai_augment_place_of_residence"
)
KTP_AI_AUGMENT_GENDER_COL: Final = "ktp.ai_augment_gender"
KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL: Final = (
    "ktp.ai_augment_age_first_publication_according_to_openalex_profile"
)
KTP_AI_AUGMENT_EDUCATION_COL: Final = "ktp.ai_augment_education"
KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL: Final = (
    "ktp.ai_augment_academic_position_s_"
)
KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL: Final = (
    "ktp.ai_augment_social_capital"
)
KTP_AI_AUGMENT_LINKS_COL: Final = "ktp.ai_augment_links_"
KTP_AI_AUGMENT_COMMENTS_COL: Final = "ktp.ai_augment_comments"

KTP_TABLE_1_RESEARCHER_AUTHOR_COL: Final = "ktp.table_1_researcher_author"
KTP_TABLE_1_PLACE_OF_RESIDENCE_COL: Final = (
    "ktp.table_1_place_of_residence"
)
KTP_TABLE_1_GENDER_COL: Final = "ktp.table_1_gender"
KTP_TABLE_1_AGE_FIRST_PUBLICATION_COL: Final = (
    "ktp.table_1_age_first_publication_according_to_openalex_profile"
)
KTP_TABLE_1_EDUCATION_COL: Final = "ktp.table_1_education"
KTP_TABLE_1_ACADEMIC_POSITIONS_COL: Final = (
    "ktp.table_1_academic_position_s_"
)
KTP_TABLE_1_SOCIAL_CAPITAL_COL: Final = "ktp.table_1_social_capital"
KTP_TABLE_1_LINKS_COL: Final = "ktp.table_1_links_"
KTP_TABLE_1_COMMENTS_COL: Final = "ktp.table_1_comments"


# =============================================================================
# Strong-ish scalar identities
# =============================================================================

SourceKey = NewType("SourceKey", str)
SessionId = NewType("SessionId", str)
AttemptId = NewType("AttemptId", str)
RemotePid = NewType("RemotePid", int)


# =============================================================================
# Variable selection
# =============================================================================


@dataclass(frozen=True, slots=True)
class VariableSpec:
    key: str
    ai_column: str
    table_1_column: str


VARIABLE_SPECS: Final[tuple[VariableSpec, ...]] = (
    VariableSpec(
        key="researcher_author",
        ai_column=KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
        table_1_column=KTP_TABLE_1_RESEARCHER_AUTHOR_COL,
    ),
    VariableSpec(
        key="place_of_residence",
        ai_column=KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
        table_1_column=KTP_TABLE_1_PLACE_OF_RESIDENCE_COL,
    ),
    VariableSpec(
        key="gender",
        ai_column=KTP_AI_AUGMENT_GENDER_COL,
        table_1_column=KTP_TABLE_1_GENDER_COL,
    ),
    VariableSpec(
        key="age_first_publication_according_to_openalex_profile",
        ai_column=KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
        table_1_column=KTP_TABLE_1_AGE_FIRST_PUBLICATION_COL,
    ),
    VariableSpec(
        key="education",
        ai_column=KTP_AI_AUGMENT_EDUCATION_COL,
        table_1_column=KTP_TABLE_1_EDUCATION_COL,
    ),
    VariableSpec(
        key="academic_position_s_",
        ai_column=KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
        table_1_column=KTP_TABLE_1_ACADEMIC_POSITIONS_COL,
    ),
    VariableSpec(
        key="social_capital",
        ai_column=KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
        table_1_column=KTP_TABLE_1_SOCIAL_CAPITAL_COL,
    ),
    VariableSpec(
        key="links_",
        ai_column=KTP_AI_AUGMENT_LINKS_COL,
        table_1_column=KTP_TABLE_1_LINKS_COL,
    ),
    VariableSpec(
        key="comments",
        ai_column=KTP_AI_AUGMENT_COMMENTS_COL,
        table_1_column=KTP_TABLE_1_COMMENTS_COL,
    ),
)

VARIABLE_SPEC_BY_KEY: Final = {
    variable.key: variable
    for variable in VARIABLE_SPECS
}


# =============================================================================
# Enumerations
# =============================================================================


class ResearcherCohort(StrEnum):
    GROUND_TRUTH = "ground_truth"
    NO_GROUND_TRUTH = "no_ground_truth"


class RunStatus(StrEnum):
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELED = "canceled"


class RunEventKind(StrEnum):
    QUEUED = "queued"
    STARTED = "started"
    SESSION_DISCOVERED = "session_discovered"
    ROLLOUT_DISCOVERED = "rollout_discovered"
    SANCTIONED = "sanctioned"
    PUSH_ACCEPTED = "push_accepted"
    CANCEL_REQUESTED = "cancel_requested"
    CODEX_EXITED = "codex_exited"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELED = "canceled"


class BackendStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


class RunAction(StrEnum):
    QUEUE = "queue"
    CANCEL = "cancel"
    RERUN = "rerun"


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
    draw_number: str
    first_name: str
    last_name: str
    cohort: ResearcherCohort


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
# UI-owned run journal
#
# Accepted output is authoritative in DuckDB.
# Failed / canceled / process lifecycle information cannot be recovered from
# accepted output, so these are represented separately as UI-owned run events.
# =============================================================================


class RunEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1

    run_id: UUID
    source_key: str
    at: datetime
    kind: RunEventKind

    session_id: str | None = None
    rollout_jsonl: str | None = None
    remote_pid: int | None = None

    accepted_attempt_id: str | None = None
    codex_exit_code: int | None = None
    detail: str | None = None


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
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_key: str
    session_id: str
    rollout_jsonl: str


class ControlSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sanctioned_run: ControlRunResponse | None


class PushAcceptedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_key: str
    session_id: str
    attempt_id: str


class PushAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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


@dataclass(frozen=True, slots=True)
class UiSnapshot:
    counts: DashboardCounts
    rows: tuple[ResearcherGridRow, ...]
    card: ResearcherCardView | None
    backend_status: BackendStatus
    active_run_id: UUID | None


# =============================================================================
# Configuration / database location
# =============================================================================


class RuntimeConfiguration:
    def __init__(
        self,
        *,
        config_path: Path = DEFAULT_CONFIG_PATH,
    ) -> None:
        ...

    @property
    def pipeline_config(self) -> PipelineConfig:
        ...

    @property
    def timezone(self) -> ZoneInfo:
        ...

    @property
    def database_paths(self) -> DatabasePaths:
        ...


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
        ...

    def connect(self) -> duckdb.DuckDBPyConnection:
        ...

    def load_eligible_researchers(self) -> tuple[Researcher, ...]:
        ...

    def load_ground_truth(
        self,
        source_key: SourceKey,
    ) -> GroundTruthRecord | None:
        ...

    def load_ground_truth_by_source_key(
        self,
    ) -> Mapping[SourceKey, GroundTruthRecord]:
        ...

    def load_source_card_innerdicts(
        self,
        source_key: SourceKey,
    ) -> OuterDict:
        ...

    def assert_population_invariants(
        self,
        researchers: Sequence[Researcher],
    ) -> None:
        ...


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
        ...

    def connect_read_only(self) -> duckdb.DuckDBPyConnection:
        ...

    def load_accepted_attempts(
        self,
    ) -> Mapping[SourceKey, tuple[AcceptedAttempt, ...]]:
        ...

    def load_accepted_attempts_for_source_key(
        self,
        source_key: SourceKey,
    ) -> tuple[AcceptedAttempt, ...]:
        ...

    def load_codex_card_innerdicts(
        self,
        source_key: SourceKey,
    ) -> OuterDict:
        ...


# =============================================================================
# Run journal
# =============================================================================


class RunJournal:
    def __init__(
        self,
        *,
        path: Path = RUN_JOURNAL_PATH,
    ) -> None:
        ...

    def append(
        self,
        event: RunEvent,
    ) -> None:
        ...

    def load_events(self) -> tuple[RunEvent, ...]:
        ...

    def load_runs(self) -> Mapping[UUID, RunRecord]:
        ...

    def runs_for_source_key(
        self,
        source_key: SourceKey,
    ) -> tuple[RunRecord, ...]:
        ...


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
        ...

    def render(
        self,
        source_key: SourceKey,
    ) -> ResearcherCardView:
        ...

    def build_outer_dict(
        self,
        source_key: SourceKey,
    ) -> OuterDict:
        ...


# =============================================================================
# Backend process ownership
# =============================================================================


@dataclass(slots=True)
class BackendProcessHandle:
    process: asyncio.subprocess.Process
    started_at: datetime


class BackendSupervisor:
    def __init__(
        self,
        *,
        repository_root: Path,
        control_url: str,
        control_token: str,
    ) -> None:
        ...

    @property
    def status(self) -> BackendStatus:
        ...

    @property
    def process(self) -> BackendProcessHandle | None:
        ...

    async def start(self) -> None:
        ...

    async def wait_until_ready(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    async def wait(self) -> int:
        ...

    def environment(self) -> Mapping[str, str]:
        ...


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
        openapi_url: str = BACKEND_OPENAPI_URL,
    ) -> None:
        ...

    def ssh_base_command(self) -> tuple[str, ...]:
        ...

    def codex_remote_command(
        self,
        *,
        run_id: UUID,
    ) -> str:
        ...

    async def start(
        self,
        *,
        run_id: UUID,
    ) -> CodexStartResult:
        ...

    async def discover_session(
        self,
        handle: CodexProcessHandle,
    ) -> tuple[SessionId, datetime]:
        ...

    async def discover_rollout_path(
        self,
        *,
        session_id: SessionId,
        session_timestamp: datetime,
    ) -> PurePosixPath:
        ...

    async def wait(
        self,
        handle: CodexProcessHandle,
    ) -> int:
        ...

    async def cancel(
        self,
        handle: CodexProcessHandle,
    ) -> None:
        ...

    async def terminate_remote_pid(
        self,
        remote_pid: RemotePid,
    ) -> None:
        ...


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
        ...

    async def sanction(
        self,
        run: SanctionedRun,
    ) -> None:
        ...

    async def revoke(
        self,
        *,
        run_id: UUID,
    ) -> None:
        ...

    async def clear(self) -> None:
        ...

    async def current(self) -> SanctionedRun | None:
        ...

    async def snapshot(self) -> ControlSnapshotResponse:
        ...


# =============================================================================
# Reconciliation of local runs with authoritative accepted DuckDB output
# =============================================================================


class AttemptReconciler:
    def reconcile(
        self,
        *,
        researcher: Researcher,
        runs: Sequence[RunRecord],
        accepted_attempts: Sequence[AcceptedAttempt],
    ) -> ResearcherView:
        ...

    def reconcile_all(
        self,
        *,
        researchers: Sequence[Researcher],
        runs: Mapping[UUID, RunRecord],
        accepted_attempts: Mapping[SourceKey, tuple[AcceptedAttempt, ...]],
    ) -> tuple[ResearcherView, ...]:
        ...


# =============================================================================
# Per-variable table projection
# =============================================================================


class VariableProjector:
    def project_attempt(
        self,
        *,
        researcher: Researcher,
        attempt: AttemptView,
        ground_truth: GroundTruthRecord | None,
        variable: VariableSpec,
    ) -> AttemptVariableProjection:
        ...

    def project_ready_researcher(
        self,
        *,
        researcher: Researcher,
        ground_truth: GroundTruthRecord | None,
        variable: VariableSpec,
    ) -> AttemptVariableProjection:
        ...

    def project_researcher(
        self,
        *,
        researcher_view: ResearcherView,
        ground_truth: GroundTruthRecord | None,
        variable: VariableSpec,
    ) -> ResearcherGridRow:
        ...

    def footnotes_for_variable(
        self,
        *,
        attempt: AcceptedAttempt,
        variable: VariableSpec,
    ) -> str | None:
        ...

    def footnote_arguments_for_variable(
        self,
        *,
        attempt: AcceptedAttempt,
        variable: VariableSpec,
    ) -> str | None:
        ...


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
        ...

    @property
    def active_run_id(self) -> UUID | None:
        ...

    @property
    def backend_status(self) -> BackendStatus:
        ...

    async def start(self) -> None:
        ...

    async def shutdown(self) -> None:
        ...

    async def queue(
        self,
        *,
        source_key: SourceKey,
    ) -> UUID:
        ...

    async def rerun(
        self,
        *,
        source_key: SourceKey,
    ) -> UUID:
        ...

    async def cancel(
        self,
        *,
        run_id: UUID,
    ) -> None:
        ...

    async def acknowledge_push(
        self,
        *,
        run_id: UUID,
        request: PushAcceptedRequest,
    ) -> None:
        ...

    async def refresh_idle_state(self) -> None:
        ...

    async def snapshot(
        self,
        *,
        selection: UiSelection,
    ) -> UiSnapshot:
        ...

    async def researcher_card(
        self,
        *,
        source_key: SourceKey,
    ) -> ResearcherCardView:
        ...

    async def _worker(self) -> None:
        ...

    async def _execute_run(
        self,
        *,
        run_id: UUID,
    ) -> None:
        ...

    async def _finalize_run(
        self,
        *,
        run_id: UUID,
        codex_exit_code: int,
    ) -> RunStatus:
        ...

    async def _accepted_attempt_for_session(
        self,
        *,
        source_key: SourceKey,
        session_id: SessionId,
    ) -> AcceptedAttempt | None:
        ...

    def _append_run_event(
        self,
        event: RunEvent,
    ) -> None:
        ...


# =============================================================================
# NiceGUI page
# =============================================================================


@dataclass(slots=True)
class UiHandles:
    backend_status_label: Any | None = None

    variable_select: Any | None = None
    status_select: Any | None = None
    cohort_select: Any | None = None
    search_input: Any | None = None

    grid: Any | None = None

    selected_researcher_label: Any | None = None
    card_container: Any | None = None
    card_markdown: Any | None = None


class ControlCentrePage:
    def __init__(
        self,
        *,
        controller: ControlCentreController,
    ) -> None:
        ...

    @property
    def selection(self) -> UiSelection:
        ...

    def build(self) -> None:
        ...

    def build_header(self) -> None:
        ...

    def build_summary(self) -> None:
        ...

    def build_filters(self) -> None:
        ...

    def build_grid(self) -> None:
        ...

    def build_card_panel(self) -> None:
        ...

    def grid_column_definitions(
        self,
        *,
        variable: VariableSpec,
    ) -> list[dict[str, Any]]:
        ...

    def grid_options(
        self,
        *,
        snapshot: UiSnapshot,
        variable: VariableSpec,
    ) -> dict[str, Any]:
        ...

    def grid_rows(
        self,
        *,
        snapshot: UiSnapshot,
    ) -> list[dict[str, Any]]:
        ...

    def attempt_detail_rows(
        self,
        *,
        row: ResearcherGridRow,
    ) -> list[dict[str, Any]]:
        ...

    async def refresh(self) -> None:
        ...

    async def refresh_grid(self) -> None:
        ...

    async def refresh_card(self) -> None:
        ...

    async def on_variable_changed(
        self,
        variable_key: str,
    ) -> None:
        ...

    async def on_status_filter_changed(
        self,
        status: str | None,
    ) -> None:
        ...

    async def on_cohort_filter_changed(
        self,
        cohort: str | None,
    ) -> None:
        ...

    async def on_search_changed(
        self,
        search_text: str,
    ) -> None:
        ...

    async def on_researcher_selected(
        self,
        source_key: SourceKey,
    ) -> None:
        ...

    async def on_queue(
        self,
        source_key: SourceKey,
    ) -> None:
        ...

    async def on_rerun(
        self,
        source_key: SourceKey,
    ) -> None:
        ...

    async def on_cancel(
        self,
        run_id: UUID,
    ) -> None:
        ...

    async def on_grid_action(
        self,
        *,
        action: RunAction,
        source_key: SourceKey,
        run_id: UUID | None,
    ) -> None:
        ...


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


def create_services() -> ApplicationServices:
    ...


def require_services() -> ApplicationServices:
    ...


# =============================================================================
# Backend-facing loopback control API
# =============================================================================


@app.get(
    CONTROL_CURRENT_PATH,
    response_model=ControlSnapshotResponse,
    include_in_schema=False,
)
async def control_current() -> ControlSnapshotResponse:
    ...


@app.post(
    CONTROL_ACCEPTED_PATH_TEMPLATE,
    response_model=PushAcceptedResponse,
    include_in_schema=False,
)
async def control_push_accepted(
    run_id: UUID,
    request: PushAcceptedRequest,
) -> PushAcceptedResponse:
    ...


# =============================================================================
# Browser-facing NiceGUI page
# =============================================================================


@ui.page("/")
async def control_centre_page() -> None:
    ...


# =============================================================================
# NiceGUI / backend lifecycle
# =============================================================================


async def application_startup() -> None:
    ...


async def application_shutdown() -> None:
    ...


def configure_application_lifecycle() -> None:
    ...


def main() -> None:
    ...


if __name__ == "__main__":
    main()
