from __future__ import annotations

import argparse
import asyncio
import contextlib
import http.client
import json
import logging
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timezone
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path, PurePosixPath
from typing import Any, Final, Literal, NewType, Protocol, Self
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

from fastapi import status
from nicegui import app, ui
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (  # noqa: E501
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.pydantic_to_paste import (  # noqa: E501
    EXPORT_OPENALEX_API_KEY,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AI_AUGMENT_COLUMN_PREFIX,
    BACKEND_STORE_CLOSED_CLEANLY,
    DOCX_TO_AI_AUGMENT_COLUMNS,
    KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL,
    KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL,
    KTP_AI_AUGMENT_FOOTNOTES_COL,
    AiAugmentCohort,
)
from src.detours.detour_ai_augment.protected.src.backend.ipc import (
    DASHBOARD_IPC_HOST,
    DASHBOARD_QUERY_PATH,
    DASHBOARD_SOCKET_PATH,
    DASHBOARD_SOCKET_PATH_ENV_NAME,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (
    Locale,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.vars import (
    AIVM_SSH_CONNECTION_COMMAND,
    AIVM_SSH_FORWARD_COMMAND,
    AIVM_SSH_TARGET,
    BACKEND_AVAILABILITY_TIMEOUT_SECONDS,
    BACKEND_MODULE,
    BACKEND_OPENAPI_URL,
    BACKEND_PULL_URL,
    BACKEND_READY_POLL_SECONDS,
    BACKEND_READY_TIMEOUT_SECONDS,
    BACKEND_REBUILD_TIMEOUT_SECONDS,
    CHROME_DEVTOOLS_PATH,
    CODEX_CANCEL_TIMEOUT_SECONDS,
    CODEX_CLI_BIN_PATH,
    CODEX_DISCOVERY_POLL_SECONDS,
    CODEX_DISCOVERY_TIMEOUT_SECONDS,
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
from src.helpers.architecture import FrozenStrictModel
from src.helpers.cards import build_cards, card_filename, render_docx_bytes
from src.helpers.data_models import InnerDict, NameKey
from src.helpers.vars import (
    CARD_INTRODUCTION,
    DRAW_LABEL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
)

from ...backend.api import (
    APPENDWATCH_REPORT_ENV_NAME,
    CARD_EXCLUDED_COLUMNS,
    CODEX_SESSIONS_ROOT_ENV_NAME,
    HTTP_GET_METHOD,
    HTTP_POST_METHOD,
    NAMEKEY_ENV_NAME,
    SERVER_PORT,
    _PushValidationError,
    parse_appendwatch_report_bytes,
    parse_source_key_header,
    selected_card_outer_dict,
)
from ...backend.helpers.data_models.ai_augment_singular_outer_dict import (
    AiAugmentSingularOuterDict,
)
from ...backend.helpers.data_models.commit_event import (
    SOURCE_KEY_HEADER,
    BackendLifecycle,
)
from ...backend.helpers.data_models.committed_innerdict import CommittedInnerDict
from ...backend.helpers.data_models.query_response import (
    AgentRuntimeAttemptRecord,
    QueryResponse,
)
from ...backend.helpers.data_models.run_outcome_record import (
    RunOutcomeRecord,
    RunOutcomeResponseBody,
)
from ...backend.server import (
    CONFIG_OPTION,
    DANGER_NO_VERIFY_HASH_OPTION,
)
from .helpers.aggrid import AgGrid
from .helpers.data_models.ai_augment_context import (
    AiAugmentControlCentreContext,
)
from .helpers.data_models.ai_augment_dashboard_storage import AiAugmentDashboardStorage
from .helpers.data_models.dashboard_query_snapshot import DashboardQuerySnapshot
from .helpers.data_models.query_request import QueryRequest
from .helpers.data_models.run_event import (
    Run,
    RunEvent,
)
from .helpers.data_models.run_outcome import (
    RunLifecycle,
    RunOutcomeRequest,
)

type _Researcher = AiAugmentSingularOuterDict

logger = logging.getLogger(__name__)


class _NiceGui:
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


LIMA_APPENDWATCH_REPORT_PARAM: Final = APPENDWATCH_REPORT_ENV_NAME

FOOTNOTE_MARKER = re.compile(r"\^(?P<numbers>[0-9]+(?:,[0-9]+)*)\^")
UI_REFRESH_SECONDS: Final = 1
PROBE_TIMEOUT_SECONDS: Final = 3
SSH_PROBE_MARKER: Final = b"ai-augment-probe"
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
HTTP_OPTIONS_METHOD: Final = "OPTIONS"
DOCX_MEDIA_TYPE: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TXT_MEDIA_TYPE: Final = "text/plain; charset=utf-8"
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
GRID_COMMIT_RECORD_ID_FIELD: Final = "commit_record_id"
GRID_ATTEMPT_TIMESTAMP_FIELD: Final = "attempt_timestamp"
GRID_STATUS_FIELD: Final = "status"
GRID_RUN_OUTCOME_SNAPSHOT_FIELD: Final = "run_outcome_snapshot"
GRID_SESSION_STATUS_FIELD: Final = "session_status"
GRID_ACTION_FIELD: Final = "action"
PAGE_CONTAINER_TEST_ID: Final = "page-container"
PAGE_HEADER_TEST_ID: Final = "page-header"
BACKEND_IPC_STATUS_TEST_ID: Final = "backend-ipc-status"
BACKEND_REFRESH_TEST_ID: Final = "backend-refresh"
PAGE_SUMMARY_TEST_ID: Final = "page-summary"
PAGE_FILTERS_TEST_ID: Final = "page-filters"
RESEARCHER_GRID_TEST_ID: Final = "researcher-grid"
ACTION_PANEL_TEST_ID: Final = "action-panel"
EXECUTE_ACTION_TEST_ID: Final = "execute-action"
VIEW_CARD_TEST_ID: Final = "view-researcher-card"
DOWNLOAD_CARD_DOCX_TEST_ID: Final = "download-researcher-card-docx"
DOWNLOAD_CARD_TXT_TEST_ID: Final = "download-researcher-card-txt"
CARD_MARKDOWN_TEST_ID: Final = "researcher-card-markdown"
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
# Scalar identities
# =============================================================================

RemotePid = NewType("RemotePid", int)


def datetime_to_unix_usec(value: datetime) -> int:
    if value.tzinfo is None:
        raise ValueError("run-event time must be timezone-aware")
    return int(value.timestamp() * 1_000_000)


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
    researcher: _Researcher,
) -> tuple[
    tuple[tuple[int, tuple[tuple[int, int | str], ...], str], ...],
    str,
    str,
    str,
]:
    return (
        tuple(draw_sort_key(draw) for draw in researcher.draw_numbers),
        researcher.namekey.first_name.casefold(),
        researcher.namekey.last_name.casefold(),
        researcher.namekey.to_json_key(),
    )


def nicegui_table_column(
    *,
    field: str,
    label: str,
) -> dict[str, object]:
    return {
        _NiceGui.TABLE_COLUMN_NAME: field,
        _NiceGui.TABLE_COLUMN_LABEL: label,
        _NiceGui.TABLE_COLUMN_FIELD: field,
        _NiceGui.TABLE_COLUMN_ALIGN: _NiceGui.TABLE_LEFT_ALIGNMENT,
        _NiceGui.TABLE_COLUMN_SORTABLE: True,
    }


# =============================================================================
# Researcher var selection
# =============================================================================


class _ResearcherVar(FrozenStrictModel):
    """A varname and paired AI/Table1 column names, not cell values.

    The varname is the AI column name without AI_AUGMENT_COLUMN_PREFIX;
    it identifies the selected researcher var, not a researcher's NameKey.
    """

    varname: str
    ai_column: str
    table_1_column: str


RESEARCHER_VARS: Final[tuple[_ResearcherVar, ...]] = tuple(
    _ResearcherVar(
        varname=ai_column.removeprefix(AI_AUGMENT_COLUMN_PREFIX),
        ai_column=ai_column,
        table_1_column=table_1_column,
    )
    for table_1_column, ai_column in DOCX_TO_AI_AUGMENT_COLUMNS
)

RESEARCHER_VARS_BY_VARNAME: Final = {
    researcher_var.varname: researcher_var for researcher_var in RESEARCHER_VARS
}


# =============================================================================
# Enumerations
# =============================================================================


RESEARCHER_LIFECYCLES: Final = (
    RunLifecycle.READY,
    RunLifecycle.QUEUED,
    RunLifecycle.RUNNING,
    RunLifecycle.CODEX_EXITED,
    RunLifecycle.COMPLETED,
    RunLifecycle.FAILED,
    RunLifecycle.CANCELLED,
)
LIVE_RESEARCHER_LIFECYCLES: Final = frozenset({
    RunLifecycle.QUEUED,
    RunLifecycle.RUNNING,
    RunLifecycle.CODEX_EXITED,
})
AGENT_RUNTIME_ATTEMPT_LIFECYCLE_BY_RESULT: Final = {
    BackendLifecycle.ACCEPTED: RunLifecycle.COMPLETED,
    BackendLifecycle.CONFIGURATION_ERROR: RunLifecycle.FAILED,
    BackendLifecycle.REJECTED: RunLifecycle.FAILED,
}


def run_namekey(run: Run) -> NameKey:
    return run.namekey


class _BackendStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RUNNING_EXTERNALLY = "running externally"
    FAILED = "failed"


class _RunAction(StrEnum):
    QUEUE = "queue"
    CANCEL = "cancel"
    RERUN = "rerun"
    DISABLED = "disabled"


# =============================================================================
# Availability observations
# =============================================================================


class _BackendAvailability(FrozenStrictModel):
    full_api_available: bool | None = None
    ipc_available: bool | None = None
    ssh_available: bool | None = None
    codex_authenticated: bool | None = None
    checked_at: datetime | None = None

    @staticmethod
    def status_text(value: bool | None) -> str:
        if value is None:
            return Locale.PROBE_NOT_CHECKED
        return Locale.IPC_AVAILABLE if value else Locale.IPC_UNAVAILABLE


# =============================================================================
# View models
# =============================================================================


class _RunCommitView(FrozenStrictModel):
    attempt_record: AgentRuntimeAttemptRecord | None
    run: Run | None
    accepted: CommittedInnerDict | None
    run_outcome_record: RunOutcomeRecord | None

    @model_validator(mode="after")
    def validate_run_or_commit(self) -> Self:
        if self.attempt_record is None and self.run is None:
            raise ValueError("Run/commit view requires a Backend commit or Dashboard run")
        return self

    @property
    def row_id(self) -> UUID:
        if self.attempt_record is not None:
            return self.attempt_record.attempt.commit_record.record_id
        assert self.run is not None
        return self.run.run_id

    @property
    def run_id(self) -> UUID | None:
        return None if self.run is None else self.run.run_id

    @property
    def backend_lifecycle(self) -> RunLifecycle | None:
        if self.attempt_record is None:
            return None
        result = self.attempt_record.attempt.post_commit_validation.result
        lifecycle = AGENT_RUNTIME_ATTEMPT_LIFECYCLE_BY_RESULT.get(result)
        if lifecycle is None:
            raise RuntimeError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
        return lifecycle

    @property
    def lifecycle(self) -> RunLifecycle:
        if self.run is None:
            lifecycle = self.backend_lifecycle
            assert lifecycle is not None
            return lifecycle
        if self.run.lifecycle is RunLifecycle.CODEX_EXITED:
            return RunLifecycle.CODEX_EXITED
        if self.run.is_queued():
            return RunLifecycle.QUEUED
        if self.run.is_running():
            return RunLifecycle.RUNNING
        assert self.run.run_outcome is not None
        return self.run.run_outcome

    @property
    def commit_record_id(self) -> UUID | None:
        if self.attempt_record is not None:
            return self.attempt_record.attempt.commit_record.record_id
        assert self.run is not None
        return self.run.accepted_commit_record_id

    @property
    def timestamp(self) -> datetime:
        if self.attempt_record is not None:
            return datetime.fromtimestamp(
                self.attempt_record.attempt.commit_record.record_id.time / 1_000,
                tz=timezone.utc,
            )
        assert self.run is not None
        return self.run.started_at or self.run.queued_at

    @property
    def failure_detail(self) -> str | None:
        if self.attempt_record is not None:
            return self.attempt_record.attempt.post_commit_validation.detail
        assert self.run is not None
        return self.run.failure_detail

    @property
    def run_outcome_saved(self) -> bool | None:
        if self.run_outcome_record is None:
            return None
        return self.run_outcome_record.response_code == status.HTTP_200_OK

    @property
    def run_outcome_session_status(self) -> str | None:
        response = self.run_outcome_record
        if response is None:
            return None
        session = response.run_outcome_response_body.codex_session_record
        report = session.appendwatch_report_record
        rollout = session.codex_rollout_record
        if report is None:
            return None
        source_key = (response.response_headers or {}).get(SOURCE_KEY_HEADER)
        if rollout is None or source_key is None:
            return Locale.SESSION_STATUS_UNAVAILABLE
        try:
            filename, line_count = parse_source_key_header(source_key)
            if line_count != rollout.line_count:
                raise _PushValidationError(Locale.RUN_OUTCOME_SNAPSHOT_INVALID)
            parse_appendwatch_report_bytes(
                report.decoded_bytes(),
                PurePosixPath(filename),
            )
        except (_PushValidationError, ValueError) as exc:
            return Locale.SESSION_STATUS_NOT_OK_TEMPLATE.format(detail=exc)
        return Locale.SESSION_STATUS_OK

    def to_var_view(
        self,
        *,
        researcher: _Researcher,
        ground_truth: InnerDict | None,
        researcher_var: _ResearcherVar,
        codex_busy: bool,
    ) -> _RunCommitVarView:
        accepted = self.accepted
        return _RunCommitVarView(
            run_id=self.run_id,
            namekey=researcher.namekey,
            draw_number=researcher.draw_number,
            first_name=researcher.namekey.first_name,
            last_name=researcher.namekey.last_name,
            ai_column=researcher_var.ai_column,
            ai_value=(
                None if accepted is None else accepted.text(researcher_var.ai_column)
            ),
            table_1_column=researcher_var.table_1_column,
            table_1_value=(
                None
                if ground_truth is None
                or (value := ground_truth.data[researcher_var.table_1_column]) is None
                else str(value)
            ),
            footnotes=(
                None
                if accepted is None
                else self.footnotes_for_researcher_var(
                    attempt=accepted, researcher_var=researcher_var,
                )
            ),
            footnote_arguments=(
                None
                if accepted is None
                else self.footnote_arguments_for_researcher_var(
                    attempt=accepted,
                    researcher_var=researcher_var,
                )
            ),
            commit_record_id=self.commit_record_id,
            timestamp=self.timestamp,
            lifecycle=self.lifecycle,
            backend_lifecycle=self.backend_lifecycle,
            run_outcome_snapshot_savedness=(
                None
                if self.run_outcome_saved is None
                else (
                    Locale.RUN_OUTCOME_SNAPSHOT_SAVED
                    if self.run_outcome_saved
                    else Locale.RUN_OUTCOME_SNAPSHOT_FAILED
                )
            ),
            session_status=self.run_outcome_session_status,
            action=_RunCommitVarView.action_for_lifecycle(
                self.lifecycle,
                eligible=(
                    researcher.ai_augment_cohort is not AiAugmentCohort.INELIGIBLE
                ),
                codex_busy=codex_busy,
            ),
        )

    def footnotes_for_researcher_var(
        self,
        *,
        attempt: CommittedInnerDict,
        researcher_var: _ResearcherVar,
    ) -> str | None:
        numbers = self._footnote_numbers(attempt, researcher_var)
        return self._matching_numbered_lines(
            attempt.text(KTP_AI_AUGMENT_FOOTNOTES_COL),
            numbers,
        )

    def footnote_arguments_for_researcher_var(
        self,
        *,
        attempt: CommittedInnerDict,
        researcher_var: _ResearcherVar,
    ) -> str | None:
        numbers = self._footnote_numbers(attempt, researcher_var)
        return self._matching_numbered_lines(
            attempt.text(KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL),
            numbers,
        )

    @staticmethod
    def _footnote_numbers(
        attempt: CommittedInnerDict,
        researcher_var: _ResearcherVar,
    ) -> tuple[int, ...]:
        value = attempt.text(researcher_var.ai_column)
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


class _ResearcherView(FrozenStrictModel):
    researcher: _Researcher

    # Oldest -> newest.
    run_commit_views: tuple[_RunCommitView, ...]

    # Same object as run_commit_views[-1], or None when there are no runs/commits.
    latest_run_commit_view: _RunCommitView | None

    current_lifecycle: RunLifecycle

    @classmethod
    def from_snapshot(
        cls,
        researcher: _Researcher,
        snapshot: DashboardQuerySnapshot,
        runs: Sequence[Run],
    ) -> _ResearcherView:
        by_session: dict[UUID, Run] = {}
        for run in runs:
            if run.session_id is not None:
                if run.session_id in by_session:
                    raise RuntimeError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
                by_session[run.session_id] = run
        namekey = researcher.namekey.to_json_key()
        represented: set[UUID] = set()
        run_commit_views: list[_RunCommitView] = []
        for record in snapshot.attempts_by_namekey.get(namekey, ()):
            commit = record.attempt.commit_record
            session_id = commit.commit_request_body.codex_session_record.session_id
            matched_run = None if session_id is None else by_session.get(session_id)
            if matched_run is not None:
                represented.add(matched_run.run_id)
            run_commit_views.append(_RunCommitView(
                attempt_record=record,
                run=matched_run,
                accepted=snapshot.committed_by_id.get(commit.record_id),
                run_outcome_record=(
                    None if session_id is None
                    else snapshot.outcomes_by_session.get((namekey, session_id))
                ),
            ))
        for run in runs:
            if run.run_id not in represented:
                run_commit_views.append(_RunCommitView(
                    attempt_record=None,
                    run=run,
                    accepted=None,
                    run_outcome_record=(
                        None if run.session_id is None
                        else snapshot.outcomes_by_session.get((namekey, run.session_id))
                    ),
                ))
        ordered = tuple(sorted(run_commit_views, key=lambda run_commit_view: (
            run_commit_view.run is not None and not run_commit_view.run.is_finished(),
            run_commit_view.timestamp,
            str(run_commit_view.row_id),
        )))
        latest = ordered[-1] if ordered else None
        return cls(
            researcher=researcher,
            run_commit_views=ordered,
            latest_run_commit_view=latest,
            current_lifecycle=RunLifecycle.READY if latest is None else latest.lifecycle,
        )

    def to_var_view(
        self,
        *,
        ground_truth: InnerDict | None,
        researcher_var: _ResearcherVar,
        codex_busy: bool,
    ) -> _ResearcherVarView:
        run_commit_var_views = tuple(
            run_commit_view.to_var_view(
                researcher=self.researcher,
                ground_truth=ground_truth,
                researcher_var=researcher_var,
                codex_busy=codex_busy,
            )
            for run_commit_view in self.run_commit_views
        )
        latest = (
            run_commit_var_views[-1]
            if run_commit_var_views
            else _RunCommitVarView.ready(
                researcher=self.researcher,
                ground_truth=ground_truth,
                researcher_var=researcher_var,
                codex_busy=codex_busy,
            )
        )
        return _ResearcherVarView(
            researcher=self.researcher,
            latest_run_commit_var_view=latest,
            run_commit_var_views=run_commit_var_views,
        )


class _RunCommitVarView(FrozenStrictModel):
    run_id: UUID | None

    namekey: NameKey
    draw_number: str
    first_name: str
    last_name: str

    ai_column: str
    ai_value: str | None

    table_1_column: str
    table_1_value: str | None

    footnotes: str | None
    footnote_arguments: str | None

    commit_record_id: UUID | None
    timestamp: datetime | None
    lifecycle: RunLifecycle
    backend_lifecycle: RunLifecycle | None
    run_outcome_snapshot_savedness: str | None
    session_status: str | None

    action: _RunAction

    @staticmethod
    def action_for_lifecycle(
        lifecycle: RunLifecycle,
        *,
        eligible: bool,
        codex_busy: bool = False,
    ) -> _RunAction:
        if not eligible:
            return _RunAction.DISABLED
        if lifecycle in LIVE_RESEARCHER_LIFECYCLES:
            return _RunAction.CANCEL
        if lifecycle is RunLifecycle.READY or codex_busy:
            return _RunAction.QUEUE
        return _RunAction.RERUN

    @classmethod
    def ready(
        cls,
        *,
        researcher: _Researcher,
        ground_truth: InnerDict | None,
        researcher_var: _ResearcherVar,
        codex_busy: bool,
    ) -> _RunCommitVarView:
        return cls(
            run_id=None,
            namekey=researcher.namekey,
            draw_number=researcher.draw_number,
            first_name=researcher.namekey.first_name,
            last_name=researcher.namekey.last_name,
            ai_column=researcher_var.ai_column,
            ai_value=None,
            table_1_column=researcher_var.table_1_column,
            table_1_value=(
                None
                if ground_truth is None
                or (value := ground_truth.data[researcher_var.table_1_column]) is None
                else str(value)
            ),
            footnotes=None,
            footnote_arguments=None,
            commit_record_id=None,
            timestamp=None,
            lifecycle=RunLifecycle.READY,
            backend_lifecycle=None,
            run_outcome_snapshot_savedness=None,
            session_status=None,
            action=cls.action_for_lifecycle(
                RunLifecycle.READY,
                eligible=(
                    researcher.ai_augment_cohort is not AiAugmentCohort.INELIGIBLE
                ),
                codex_busy=codex_busy,
            ),
        )


class _ResearcherVarView(FrozenStrictModel):
    researcher: _Researcher

    # Upper table: latest var view, or a ready placeholder.
    latest_run_commit_var_view: _RunCommitVarView

    # Lower table: all var views, oldest -> newest.
    run_commit_var_views: tuple[_RunCommitVarView, ...]


class _ResearcherCardView(FrozenStrictModel):
    researcher: _Researcher
    card_markdown: str

    @property
    def download_available(self) -> bool:
        return bool(self.card_markdown)

    @property
    def filename_stem(self) -> str:
        return card_filename(
            draw_label=self.researcher.draw_number,
            first_name=self.researcher.namekey.first_name,
            last_name=self.researcher.namekey.last_name,
        )

    @property
    def docx_filename(self) -> str:
        return f"{self.filename_stem}.docx"

    def render_docx(self, reference_docx: Path) -> bytes:
        return render_docx_bytes(self.card_markdown, reference_docx)


class _DashboardCounts(FrozenStrictModel):
    total: int
    ground_truth: int
    no_ground_truth: int
    ineligible: int

    ready: int
    queued: int
    running: int
    completed: int
    failed: int
    cancelled: int


class _UiSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    researcher_varname: str
    lifecycle_filter: RunLifecycle | None = None
    cohort_filter: AiAugmentCohort | None = None
    search_text: str = ""

    selected_namekey: NameKey | None = None
    selected_run_id: UUID | None = None
    selected_action: _RunAction | None = None


class _DashboardView(FrozenStrictModel):
    counts: _DashboardCounts
    researcher_var_views: tuple[_ResearcherVarView, ...]
    backend_status: _BackendStatus
    backend_availability: _BackendAvailability
    active_run_id: UUID | None


# =============================================================================
# Backend database IPC client
# =============================================================================


class _UnixSocketHttpConnection(http.client.HTTPConnection):
    def __init__(
        self,
        *,
        socket_path: Path,
        timeout: float,
    ) -> None:
        super().__init__(DASHBOARD_IPC_HOST, timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self._socket_path))


class _BackendDatabaseClient:
    def __init__(
        self,
        *,
        socket_path: Path,
        pipeline_config: AiAugmentDetourConfig,
    ) -> None:
        self._socket_path = socket_path
        self._pipeline_config = pipeline_config

    def _request(self, *, method: str, target: str) -> bytes:
        connection = _UnixSocketHttpConnection(
            socket_path=self._socket_path,
            timeout=CONTROL_HTTP_TIMEOUT_SECONDS,
        )
        try:
            connection.request(method, target)
            response = connection.getresponse()
            body = response.read()
            if response.status != status.HTTP_200_OK:
                raise RuntimeError(Locale.BACKEND_DATABASE_REQUEST_FAILED)
            return body
        except (OSError, http.client.HTTPException) as exc:
            raise RuntimeError(Locale.BACKEND_DATABASE_REQUEST_FAILED) from exc
        finally:
            connection.close()

    def send_query_request(self, request: QueryRequest) -> QueryResponse:
        method, target = request.outbound_http()
        try:
            return QueryResponse.from_serialized_json(self._request(method=method, target=target))
        except ValidationError as exc:
            raise RuntimeError(Locale.BACKEND_DATABASE_RESPONSE_INVALID) from exc

    def record_run_outcome(
        self,
        *,
        run_outcome: RunLifecycle,
        namekey: NameKey,
    ) -> HTTPStatus:
        request_path, request_headers = RunOutcomeRequest.outbound_http(
            run_outcome=run_outcome,
            namekey=namekey,
        )
        connection = _UnixSocketHttpConnection(
            socket_path=self._socket_path,
            timeout=CONTROL_HTTP_TIMEOUT_SECONDS,
        )
        try:
            connection.request(
                HTTP_POST_METHOD,
                request_path,
                headers=dict(request_headers),
            )
            response = connection.getresponse()
            body = response.read()
            if response.status not in {
                HTTPStatus.OK,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                HTTPStatus.CONFLICT,
            }:
                raise RuntimeError(Locale.RUN_OUTCOME_SNAPSHOT_REQUEST_FAILED)
            try:
                RunOutcomeResponseBody.from_serialized_json(body)
            except ValidationError as exc:
                raise RuntimeError(Locale.BACKEND_DATABASE_RESPONSE_INVALID) from exc
            return HTTPStatus(response.status)
        except (OSError, http.client.HTTPException) as exc:
            raise RuntimeError(Locale.RUN_OUTCOME_SNAPSHOT_REQUEST_FAILED) from exc
        finally:
            connection.close()

    def available(self) -> bool:
        connection = _UnixSocketHttpConnection(
            socket_path=self._socket_path,
            timeout=BACKEND_AVAILABILITY_TIMEOUT_SECONDS,
        )
        try:
            connection.request(HTTP_OPTIONS_METHOD, DASHBOARD_QUERY_PATH)
            response = connection.getresponse()
            response.read()
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"IPC probe HTTP status: {response.status}")
            return response.status == status.HTTP_200_OK
        except FileNotFoundError as exc:
            emit_log(
                Locale.CONTROL_CENTRE_LOG_PREFIX,
                f"IPC unavailable; socket not present: {self._socket_path}; {exc!r}",
            )
            return False
        except (OSError, http.client.HTTPException) as exc:
            emit_log(
                Locale.CONTROL_CENTRE_LOG_PREFIX,
                f"IPC probe error: {self._socket_path}; {exc!r}",
            )
            return False
        finally:
            connection.close()

    def card(self, researcher: _Researcher) -> str:
        selected = selected_card_outer_dict(researcher)
        cards = build_cards(
            selected,
            total_draws=self._pipeline_config.total_draws,
            intro=CARD_INTRODUCTION.format(
                datetime.now(ZoneInfo(self._pipeline_config.timezone)).strftime(
                    Locale.CARD_INTRO_DATE_FORMAT
                )
            ),
            excluded_cols=CARD_EXCLUDED_COLUMNS,
        )
        if len(cards) != 1:
            raise RuntimeError(Locale.BACKEND_CARD_MISSING)
        markdown = next(iter(cards.values()))
        return markdown


# =============================================================================
# Control Centre run projection
# =============================================================================


def apply_run_event(run: Run | None, event: RunEvent) -> Run:
    if run is None:
        if event.lifecycle is not RunLifecycle.QUEUED:
            raise RuntimeError(Locale.JOURNAL_EVENT_WITHOUT_RUN)
        run = Run(
            run_id=event.run_id,
            namekey=event.namekey,
            lifecycle=RunLifecycle.QUEUED,
            queued_at=event.occurred_at,
            dashboard_owned=True,
        )
    elif run.namekey != event.namekey:
        raise RuntimeError(Locale.JOURNAL_EVENT_WITHOUT_RUN)
    elif event.lifecycle is RunLifecycle.QUEUED:
        raise RuntimeError(Locale.JOURNAL_DUPLICATE_RUN_ID)

    if event.lifecycle is RunLifecycle.STARTED:
        run.started_at = event.occurred_at
        run.remote_pid = event.remote_pid
    elif event.lifecycle is RunLifecycle.REMOTE_PID_DISCOVERED:
        if event.remote_pid is None:
            raise RuntimeError(Locale.JOURNAL_REMOTE_PID_MISSING)
        run.remote_pid = event.remote_pid
    elif event.lifecycle is RunLifecycle.SESSION_DISCOVERED:
        if event.session_id is None:
            raise RuntimeError(Locale.JOURNAL_SESSION_ID_MISSING)
        run.session_id = event.session_id
        run.session_timestamp = event.occurred_at
    elif event.lifecycle is RunLifecycle.ROLLOUT_DISCOVERED:
        if event.rollout_jsonl is None:
            raise RuntimeError(Locale.JOURNAL_ROLLOUT_PATH_MISSING)
        run.rollout_jsonl = event.rollout_jsonl
    elif event.lifecycle is RunLifecycle.PUSH_ACCEPTED:
        if event.accepted_commit_record_id is None:
            raise RuntimeError(Locale.JOURNAL_COMMIT_RECORD_ID_MISSING)
        run.accepted_commit_record_id = event.accepted_commit_record_id
        run.accepted_at = event.occurred_at
    elif event.lifecycle is RunLifecycle.CANCEL_REQUESTED:
        run.cancel_requested_at = event.occurred_at
    elif event.lifecycle is RunLifecycle.CODEX_EXITED:
        run.codex_exit_code = event.codex_exit_code
        run.exited_at = event.occurred_at
    elif event.lifecycle is RunLifecycle.COMPLETED:
        run.run_outcome = RunLifecycle.COMPLETED
    elif event.lifecycle is RunLifecycle.FAILED:
        run.run_outcome = RunLifecycle.FAILED
        run.failure_detail = event.detail
    elif event.lifecycle is RunLifecycle.CANCELLED:
        run.run_outcome = RunLifecycle.CANCELLED
    run.lifecycle = event.lifecycle
    run.events += (event,)
    return run


def replay_run_events(events: Sequence[RunEvent]) -> Mapping[UUID, Run]:
    runs: dict[UUID, Run] = {}
    for event in events:
        runs[event.run_id] = apply_run_event(runs.get(event.run_id), event)
    return runs


# =============================================================================
# Backend process ownership
# =============================================================================


class _BackendProcessHandle(BaseModel):
    # Process and Task are live handles, not serializable model data.
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, arbitrary_types_allowed=True,
    )

    process: asyncio.subprocess.Process
    started_at: datetime
    log_task: asyncio.Task[None]
    store_closed_cleanly: asyncio.Event
    ipc_only: bool = False
    rebuilding: bool = False
    startup_succeeded: bool = False


class _BackendSupervisor:
    def __init__(
        self,
        *,
        repository_root: Path,
        config_path: Path,
        openalex_api_key: str,
        appendwatch_report: PurePosixPath,
        dashboard_socket_path: Path,
        configuration: AiAugmentControlCentreContext,
    ) -> None:
        self._repository_root = repository_root
        self._config_path = config_path
        self._openalex_api_key = openalex_api_key
        self._appendwatch_report = appendwatch_report
        self._dashboard_socket_path = dashboard_socket_path
        self._context = configuration
        self._pipeline_config = configuration.pipeline_config
        self._lifecycle_lock = asyncio.Lock()
        self._process: _BackendProcessHandle | None = None
        self._status = _BackendStatus.STOPPED

    @property
    def status(self) -> _BackendStatus:
        if (
            self._process is not None
            and self._process.process.returncode is not None
            and self._status is _BackendStatus.RUNNING
        ):
            self._status = _BackendStatus.FAILED
        return self._status

    @property
    def process(self) -> _BackendProcessHandle | None:
        return self._process

    def full_api_available(self) -> bool:
        request = urllib_request.Request(BACKEND_OPENAPI_URL, method=HTTP_GET_METHOD)
        try:
            with urllib_request.urlopen(
                request,
                timeout=BACKEND_AVAILABILITY_TIMEOUT_SECONDS,
            ) as response:
                emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                         f"Backend API probe HTTP status: {response.status}")
                return int(response.status) == status.HTTP_200_OK
        except (OSError, urllib_error.URLError, urllib_error.HTTPError) as exc:
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Backend API probe error: {exc!r}")
            return False

    async def start(self, *, namekey: NameKey) -> None:
        async with self._lifecycle_lock:
            await self._start(namekey=namekey, ipc_only=False)

    async def _start(self, *, namekey: NameKey | None, ipc_only: bool) -> None:
        if not all(
            resource.verify_hash_on_init
            for resource in self._pipeline_config.registered_resources
        ):
            raise RuntimeError(Locale.BACKEND_RESOURCES_NOT_VERIFIED)
        if self._process is not None:
            raise RuntimeError(Locale.BACKEND_ALREADY_OWNED)
        arguments = (() if ipc_only else self._context.begin_backend_start())
        self._status = _BackendStatus.STARTING
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                 f"Starting owned Backend: ipc_only={ipc_only}, mode={arguments}, "
                 f"namekey={namekey}")
        try:
            process = await asyncio.create_subprocess_exec(
                *BACKEND_COMMAND_PREFIX,
                str(self._config_path),
                *arguments,
                DANGER_NO_VERIFY_HASH_OPTION,
                *(("--ipc-only",) if ipc_only else ()),
                cwd=self._repository_root,
                env=self.environment(namekey=namekey),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
            closed_cleanly = asyncio.Event()
            log_task = asyncio.create_task(self.forward_output(process, closed_cleanly))
            self._process = _BackendProcessHandle(
                process=process,
                started_at=datetime.now(timezone.utc),
                log_task=log_task,
                store_closed_cleanly=closed_cleanly,
                ipc_only=ipc_only,
                rebuilding="--new" in arguments,
            )
            await self.wait_until_ready()
            self._process = self._process.model_copy(update={"startup_succeeded": True})
        except BaseException as exc:
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Backend startup failed: {exc!r}")
            try:
                await self._stop()
            finally:
                self._status = _BackendStatus.FAILED
            raise
        self._status = _BackendStatus.RUNNING
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Owned Backend ready: pid={process.pid}")

    @contextlib.asynccontextmanager
    async def query_connection(self, client: _BackendDatabaseClient) -> AsyncIterator[None]:
        # Serialize temporary-child lifetime with queued Backend starts/stops.
        async with self._lifecycle_lock:
            if self._process is not None or await asyncio.to_thread(client.available):
                emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                         "Query IPC borrowing available Backend; ownership unchanged")
                yield  # Borrow an existing Backend; never reset or stop it.
                return
            await self._start(namekey=None, ipc_only=True)
            try:
                yield
            finally:
                await self._stop()

    async def forward_output(
        self,
        process: asyncio.subprocess.Process,
        closed_cleanly: asyncio.Event,
    ) -> None:
        if process.stdout is None:
            raise RuntimeError(Locale.BACKEND_OUTPUT_PIPE_MISSING)
        async for raw_line in process.stdout:
            line = raw_line.decode(TEXT_ENCODING, errors=TEXT_DECODE_ERROR_POLICY)
            if line.strip() == BACKEND_STORE_CLOSED_CLEANLY:
                closed_cleanly.set()
            emit_log(Locale.BACKEND_LOG_PREFIX, line.rstrip())

    async def wait_until_ready(self) -> None:
        loop = asyncio.get_running_loop()
        assert self._process is not None
        timeout = (
            BACKEND_REBUILD_TIMEOUT_SECONDS if self._process.rebuilding
            else BACKEND_READY_TIMEOUT_SECONDS
        )
        deadline = loop.time() + timeout
        query_client = _BackendDatabaseClient(
            socket_path=self._dashboard_socket_path, pipeline_config=self._pipeline_config,
        )

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
                if self._process.ipc_only:
                    if not await asyncio.to_thread(query_client.available):
                        raise RuntimeError(Locale.BACKEND_OPENAPI_NOT_READY)
                else:
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

        if not self._process.ipc_only and await self.probe_pull() != status.HTTP_200_OK:
            raise RuntimeError(Locale.BACKEND_PULL_NOT_READY)

    async def probe_pull(self) -> int:
        def request_pull() -> int:
            request = urllib_request.Request(BACKEND_PULL_URL, method=HTTP_GET_METHOD)
            try:
                response = urllib_request.urlopen(request, timeout=CONTROL_HTTP_TIMEOUT_SECONDS)
            except urllib_error.HTTPError as exc:
                with exc:
                    exc.read()
                    return int(exc.code)
            with response:
                response.read()
                return int(response.status)

        try:
            return await asyncio.to_thread(request_pull)
        except (OSError, urllib_error.URLError) as exc:
            raise RuntimeError(Locale.BACKEND_PULL_NOT_READY) from exc

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            await self._stop()

    async def _stop(self) -> None:
        if self._process is None:
            self._status = _BackendStatus.STOPPED
            return
        handle = self._process
        process = handle.process
        forced_kill = False
        shutdown_succeeded = False
        emit_log(
            Locale.CONTROL_CENTRE_LOG_PREFIX,
            Locale.BACKEND_STOPPING_LOG_TEMPLATE.format(pid=process.pid),
        )
        try:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=PROCESS_STOP_TIMEOUT_SECONDS)
                except TimeoutError:
                    forced_kill = True
                    process.kill()
                    await asyncio.wait_for(process.wait(), timeout=PROCESS_STOP_TIMEOUT_SECONDS)
            await asyncio.wait_for(handle.log_task, timeout=PROCESS_STOP_TIMEOUT_SECONDS)
            shutdown_succeeded = (
                handle.store_closed_cleanly.is_set()
                and not forced_kill
                and process.returncode in {0, -signal.SIGTERM, -signal.SIGINT}
            )
            emit_log(
                Locale.CONTROL_CENTRE_LOG_PREFIX,
                Locale.BACKEND_STOPPED_LOG_TEMPLATE.format(
                    pid=process.pid, return_code=process.returncode,
                ),
            )
        finally:
            if not handle.ipc_only:
                self._context.finish_backend_stop(
                    startup_succeeded=handle.startup_succeeded,
                    shutdown_succeeded=shutdown_succeeded,
                )
            self._process = None
            self._status = _BackendStatus.STOPPED

    async def supply_session_id(self, session_id: UUID) -> None:
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

    def environment(self, *, namekey: NameKey | None) -> Mapping[str, str]:
        environment = os.environ.copy()
        environment[EXPORT_OPENALEX_API_KEY] = self._openalex_api_key
        environment[APPENDWATCH_REPORT_ENV_NAME] = str(self._appendwatch_report)
        environment[DASHBOARD_SOCKET_PATH_ENV_NAME] = str(self._dashboard_socket_path)
        if namekey is None:
            environment.pop(NAMEKEY_ENV_NAME, None)
        else:
            environment[NAMEKEY_ENV_NAME] = namekey.to_json_key()
        environment[CODEX_SESSIONS_ROOT_ENV_NAME] = str(CODEX_SESSIONS_ROOT)
        return environment


# =============================================================================
# AIVM / Codex process ownership
# =============================================================================


class _CodexProcessHandle(BaseModel):
    # Discovery fills metadata while retaining the live subprocess handle.
    model_config = ConfigDict(
        extra="forbid", strict=True, validate_assignment=True, arbitrary_types_allowed=True,
    )

    run: Run
    process: asyncio.subprocess.Process

    remote_pid: RemotePid | None = None
    session_id: UUID | None = None
    session_timestamp: datetime | None = None
    rollout_jsonl: PurePosixPath | None = None


class _CodexStartResult(FrozenStrictModel):
    handle: _CodexProcessHandle
    session_id: UUID
    session_timestamp: datetime
    rollout_jsonl: PurePosixPath


class _CodexRunner:
    def __init__(
        self,
        *,
        timezone: ZoneInfo,
        openapi_url: str = BACKEND_OPENAPI_URL,
    ) -> None:
        self._timezone = timezone
        self._openapi_url = openapi_url

    def ssh_connection_command(self) -> tuple[str, ...]:
        return AIVM_SSH_CONNECTION_COMMAND

    def ssh_base_command(self) -> tuple[str, ...]:
        return AIVM_SSH_FORWARD_COMMAND

    def codex_remote_command(
        self,
        *,
        run: Run,
    ) -> str:
        pid_path = CODEX_WORKDIR / CODEX_RUN_PID_TEMPLATE.format(run_id=run.run_id)
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

    async def probe_ssh(self) -> bool:
        try:
            output = await asyncio.wait_for(
                self._remote_command("cat", input_bytes=SSH_PROBE_MARKER),
                timeout=PROBE_TIMEOUT_SECONDS,
            )
            if output != SSH_PROBE_MARKER:
                emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                         f"SSH probe unexpected response: {output!r}")
            return output == SSH_PROBE_MARKER
        except (OSError, RuntimeError, TimeoutError) as exc:
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"SSH probe error: {exc!r}")
            return False

    async def probe_auth(self) -> bool:
        try:
            await asyncio.wait_for(
                self._remote_command(shlex.join([str(CODEX_CLI_BIN_PATH), "login", "status"])),
                timeout=PROBE_TIMEOUT_SECONDS,
            )
            return True
        except (OSError, RuntimeError, TimeoutError) as exc:
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Codex authentication probe error: {exc!r}")
            return False

    async def is_busy(self) -> bool:
        output = await self._remote_command(CODEX_REMOTE_BUSY_COMMAND)
        return output.decode(TEXT_ENCODING) == CODEX_REMOTE_BUSY_MARKER

    async def start(
        self,
        *,
        run: Run,
        on_handle: (Callable[[_CodexProcessHandle], Awaitable[None]] | None) = None,
    ) -> _CodexStartResult:
        marker_path = CODEX_WORKDIR / CODEX_RUN_MARKER_TEMPLATE.format(run_id=run.run_id)
        pid_path = CODEX_WORKDIR / CODEX_RUN_PID_TEMPLATE.format(run_id=run.run_id)
        await self._remote_command(
            CODEX_REMOTE_PREPARE_RUN_COMMAND_TEMPLATE.format(
                workdir=shlex.quote(str(CODEX_WORKDIR)),
                pid_path=shlex.quote(str(pid_path)),
                marker_path=shlex.quote(str(marker_path)),
            )
        )
        process = await asyncio.create_subprocess_exec(
            *self.ssh_base_command(),
            self.codex_remote_command(run=run),
            stdin=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        handle = _CodexProcessHandle(run=run, process=process)
        try:
            if process.stdin is None:
                raise RuntimeError(Locale.CODEX_STDIN_UNAVAILABLE)
            process.stdin.write(
                CODEX_INPUT_TEMPLATE.format(openapi_url=self._openapi_url).encode(TEXT_ENCODING)
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
        return _CodexStartResult(
            handle=handle,
            session_id=session_id,
            session_timestamp=session_timestamp,
            rollout_jsonl=rollout_jsonl,
        )

    async def discover_session(
        self,
        handle: _CodexProcessHandle,
    ) -> tuple[UUID, datetime]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CODEX_DISCOVERY_TIMEOUT_SECONDS
        marker_path = CODEX_WORKDIR / CODEX_RUN_MARKER_TEMPLATE.format(
            run_id=handle.run.run_id
        )
        pid_path = CODEX_WORKDIR / CODEX_RUN_PID_TEMPLATE.format(run_id=handle.run.run_id)
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
                    session_id = UUID(str(payload["session_id"]))
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
        session_id: UUID,
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
        handle: _CodexProcessHandle,
    ) -> int:
        return await handle.process.wait()

    async def cancel(
        self,
        handle: _CodexProcessHandle,
    ) -> None:
        remote_error: Exception | None = None
        try:
            remote_pid = await self._remote_pid_for_cancel(handle)
            if remote_pid is not None:
                emit_log(
                    Locale.CONTROL_CENTRE_LOG_PREFIX,
                    Locale.CODEX_REMOTE_STOPPING_LOG_TEMPLATE.format(
                        run_id=handle.run.run_id,
                        session_id=handle.session_id,
                        remote_pid=remote_pid,
                    ),
                )
                await self.terminate_remote_pid(remote_pid)
                emit_log(
                    Locale.CONTROL_CENTRE_LOG_PREFIX,
                    Locale.CODEX_REMOTE_STOPPED_LOG_TEMPLATE.format(
                        run_id=handle.run.run_id,
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
                    run_id=handle.run.run_id,
                    pid=handle.process.pid,
                ),
            )
            await self._stop_process(handle.process)
            emit_log(
                Locale.CONTROL_CENTRE_LOG_PREFIX,
                Locale.CODEX_SSH_STOPPED_LOG_TEMPLATE.format(
                    run_id=handle.run.run_id,
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
        handle: _CodexProcessHandle,
    ) -> RemotePid | None:
        if handle.remote_pid is not None:
            return handle.remote_pid
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CODEX_CANCEL_TIMEOUT_SECONDS
        pid_path = CODEX_WORKDIR / CODEX_RUN_PID_TEMPLATE.format(run_id=handle.run.run_id)
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

    async def terminate_abandoned_run(self, run: Run) -> None:
        pid_path = CODEX_WORKDIR / CODEX_RUN_PID_TEMPLATE.format(run_id=run.run_id)
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
        if not pid_text.isdecimal():
            return
        remote_pid = RemotePid(int(pid_text))
        if await self._remote_pid_is_alive(remote_pid):
            await self.terminate_remote_pid(remote_pid)


# =============================================================================
# Main orchestration
#
# Exactly one Codex attempt may be running at a time.
#
# The dashboard owns queue/run history in NiceGUI storage. Backend owns
# attempts, accepted output, cards, the authoritative log, and the detour DB.
# =============================================================================


class _RecordRunOutcome(Protocol):
    def __call__(self, *, run_outcome: RunLifecycle, namekey: NameKey) -> int: ...


class _ControlCentreController:
    def __init__(
        self,
        *,
        storage: AiAugmentDashboardStorage,
        backend: _BackendSupervisor,
        probe_ipc: Callable[[], bool],
        record_run_outcome: _RecordRunOutcome,
        render_card: Callable[[_Researcher], str],
        codex: _CodexRunner,
    ) -> None:
        self._storage = storage
        self._backend = backend
        self._probe_ipc = probe_ipc
        self._send_run_outcome = record_run_outcome
        self._render_card = render_card
        self._codex = codex
        self._queue: asyncio.Queue[Run] = asyncio.Queue()
        self._queue_processing = False
        self._queue_wakeup = asyncio.Event()
        self._publishing = False
        self._worker_task: asyncio.Task[None] | None = None
        self._active_run: Run | None = None
        self._active_codex: _CodexProcessHandle | None = None
        self._external_codex_busy = False
        self._shutting_down = False
        self._idle_refresh_lock = asyncio.Lock()
        self._events: list[RunEvent] = []
        self._runs: dict[UUID, Run] = {}
        self._snapshot = DashboardQuerySnapshot(query_response=QueryResponse(
            attempts=(), ai_augment_singular_outerdicts=(),
        ))
        self._run_outcome_recorded_run_ids: set[UUID] = set()
        self._run_outcome_lock = asyncio.Lock()
        self._notifications: list[str] = []
        self._backend_availability = _BackendAvailability()
        self._probe_lock = asyncio.Lock()

    @property
    def _researchers(self) -> tuple[_Researcher, ...]:
        return self._snapshot.ai_augment_singular_outerdicts

    @property
    def _researchers_by_namekey(self) -> Mapping[str, _Researcher]:
        return self._snapshot.researchers_by_namekey

    @property
    def active_run_id(self) -> UUID | None:
        return None if self._active_run is None else self._active_run.run_id

    @property
    def codex_busy(self) -> bool:
        return self._active_run is not None or self._external_codex_busy

    @property
    def backend_status(self) -> _BackendStatus:
        owned_status = self._backend.status
        if owned_status is not _BackendStatus.STOPPED:
            return owned_status
        if self._backend_availability.full_api_available:
            return _BackendStatus.RUNNING_EXTERNALLY
        return _BackendStatus.STOPPED

    @property
    def backend_availability(self) -> _BackendAvailability:
        return self._backend_availability

    @property
    def queue_processing(self) -> bool:
        return self._queue_processing

    def set_queue_processing(self, enabled: bool) -> None:
        self._queue_processing = enabled
        if enabled:
            self._queue_wakeup.set()
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                 "Queue processing started" if enabled else "Queue processing stopped")

    async def start(self, *, publishing: bool = False) -> None:
        self._publishing = publishing
        self._load_dashboard_storage()
        emit_log(
            Locale.CONTROL_CENTRE_LOG_PREFIX,
            Locale.DASHBOARD_STORAGE_READY_LOG,
        )
        if publishing:
            return
        restart_time = datetime.now(timezone.utc)
        for run in tuple(self._runs.values()):
            if run.dashboard_owned and run.is_running():
                await self._codex.terminate_abandoned_run(run)
                await self._append_run_event(
                    RunEvent(
                        run_id=run.run_id,
                        namekey=run.namekey,
                        occurred_at_unix_usec=datetime_to_unix_usec(restart_time),
                        lifecycle=RunLifecycle.FAILED,
                        detail=Locale.RESTART_INTERRUPTED_RUN,
                    )
                )
        for run_id in self._storage.load_queue():
            queued_run = self._runs.get(run_id)
            if queued_run is not None and queued_run.is_queued():
                await self._queue.put(queued_run)
        self._worker_task = asyncio.create_task(self._worker())
        emit_log(
            Locale.CONTROL_CENTRE_LOG_PREFIX,
            Locale.QUEUE_WORKER_READY_LOG,
        )

    async def shutdown(self) -> None:
        self._shutting_down = True
        if self._worker_task is not None:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None
        if self._publishing:
            return
        await self._wind_down_owned_run_processes()
        shutdown_time = datetime.now(timezone.utc)
        for run in tuple(self._runs.values()):
            if run.dashboard_owned and run.is_running():
                await self._append_run_event(
                    RunEvent(
                        run_id=run.run_id,
                        namekey=run.namekey,
                        occurred_at_unix_usec=datetime_to_unix_usec(shutdown_time),
                        lifecycle=RunLifecycle.FAILED,
                        detail=Locale.SHUTDOWN_INTERRUPTED_RUN,
                    )
                )

    async def queue(
        self,
        *,
        namekey: NameKey,
    ) -> UUID:
        researcher = self._researchers_by_namekey.get(namekey.to_json_key())
        if researcher is None:
            raise KeyError(Locale.UNKNOWN_NAMEKEY_TEMPLATE.format(namekey=namekey))
        if researcher.ai_augment_cohort is AiAugmentCohort.INELIGIBLE:
            raise ValueError(Locale.INELIGIBLE_QUEUE)
        run_id = uuid7()
        run = await self._append_run_event(
            RunEvent(
                run_id=run_id,
                namekey=namekey,
                occurred_at_unix_usec=datetime_to_unix_usec(datetime.now(timezone.utc)),
                lifecycle=RunLifecycle.QUEUED,
            )
        )
        queued = self._storage.load_queue()
        queued.append(run_id)
        self._storage.save_queue(queued)
        self._queue.put_nowait(run)
        self._queue_wakeup.set()
        return run_id

    async def rerun(
        self,
        *,
        namekey: NameKey,
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
        if run.is_finished():
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                     f"Cancel skipped: run {run_id} already finished")
            return
        was_queued = run.is_queued()
        await self._append_run_event(
            RunEvent(
                run_id=run_id,
                namekey=run.namekey,
                occurred_at_unix_usec=datetime_to_unix_usec(datetime.now(timezone.utc)),
                lifecycle=RunLifecycle.CANCEL_REQUESTED,
            )
        )
        if self._active_run is run:
            active_codex = self._active_codex
            if active_codex is None:
                return
            await self._record_run_outcome(
                run=run,
                run_outcome=RunLifecycle.CANCELLED,
            )
            try:
                await self._codex.cancel(active_codex)
            except Exception as exc:
                await self._append_run_event(
                    RunEvent(
                        run_id=run_id,
                        namekey=run.namekey,
                        occurred_at_unix_usec=datetime_to_unix_usec(datetime.now(timezone.utc)),
                        lifecycle=RunLifecycle.FAILED,
                        detail=Locale.CODEX_CANCEL_FAILED_TEMPLATE.format(error=exc),
                    )
                )
                raise
            return
        if was_queued:
            queued = self._storage.load_queue()
            if run_id in queued:
                queued.remove(run_id)
                self._storage.save_queue(queued)
            await self._append_run_event(
                RunEvent(
                    run_id=run_id,
                    namekey=run.namekey,
                    occurred_at_unix_usec=datetime_to_unix_usec(datetime.now(timezone.utc)),
                    lifecycle=RunLifecycle.CANCELLED,
                )
            )

    async def refresh_idle_state(self) -> None:
        if self._shutting_down:
            return
        async with self._idle_refresh_lock:
            if self._shutting_down:
                return
            backend_status = self._backend.status
            if backend_status is _BackendStatus.FAILED:
                self._backend_availability = _BackendAvailability(**{
                    **self._backend_availability.model_dump(),
                    'full_api_available': False, 'ipc_available': False,
                })
            if self._active_run is not None:
                self._external_codex_busy = False
                return
            try:
                self._external_codex_busy = await self._codex.is_busy()
            except Exception:
                if self._shutting_down:
                    return
                raise

    async def probe_all(self) -> None:
        if self._probe_lock.locked():
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, "Probe skipped: already in progress")
            return
        async with self._probe_lock:
            self._backend_availability = _BackendAvailability()
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, "Probing IPC OPTIONS /query")
            ipc_available = await asyncio.to_thread(self._probe_ipc)
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                     f"Probe IPC OPTIONS /query: {ipc_available}")
            self._backend_availability = _BackendAvailability(**{
                **self._backend_availability.model_dump(),
                "ipc_available": ipc_available,
            })
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, "Probing Backend API GET /openapi.json")
            full_api_available = await asyncio.to_thread(self._backend.full_api_available)
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                     f"Probe Backend API GET /openapi.json: {full_api_available}")
            self._backend_availability = _BackendAvailability(**{
                **self._backend_availability.model_dump(),
                "full_api_available": full_api_available,
            })
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, "Probing Lima/SSH connect")
            ssh_available = await self._codex.probe_ssh()
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                     f"Probe Lima/SSH connect: {ssh_available}")
            self._backend_availability = _BackendAvailability(**{
                **self._backend_availability.model_dump(),
                "ssh_available": ssh_available,
            })
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, "Probing Codex login status")
            codex_authenticated = await self._codex.probe_auth() if ssh_available else None
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                     f"Probe Codex login status: {codex_authenticated} (None = SSH unavailable)")
            self._backend_availability = _BackendAvailability(**{
                **self._backend_availability.model_dump(),
                "codex_authenticated": codex_authenticated,
                "checked_at": datetime.now(timezone.utc),
            })
            logger.info("Dashboard probes: %s", self._backend_availability)

    def accept_query_snapshot(self, snapshot: DashboardQuerySnapshot) -> None:
        self._snapshot = snapshot
        self._backend_availability = _BackendAvailability(**{
            **self._backend_availability.model_dump(),
            "ipc_available": True,
        })

    async def snapshot(
        self,
        *,
        selection: _UiSelection,
    ) -> _DashboardView:
        researcher_var = RESEARCHER_VARS_BY_VARNAME[selection.researcher_varname]
        runs_by_namekey: dict[str, list[Run]] = {}
        for run in self._runs.values():
            runs_by_namekey.setdefault(run.namekey.to_json_key(), []).append(run)
        views = tuple(
            _ResearcherView.from_snapshot(
                researcher, self._snapshot,
                runs_by_namekey.get(researcher.namekey.to_json_key(), ()),
            )
            for researcher in self._researchers
        )
        all_rows = tuple(
            view.to_var_view(
                ground_truth=self._snapshot.ground_truth_by_namekey.get(
                    view.researcher.namekey.to_json_key(),
                ),
                researcher_var=researcher_var,
                codex_busy=self.codex_busy,
            )
            for view in views
        )
        search_text = (selection.search_text or "").casefold().strip()
        rows = tuple(
            row
            for row, view in zip(all_rows, views, strict=True)
            if (
                selection.lifecycle_filter is None
                or view.current_lifecycle is selection.lifecycle_filter
            )
            and (
                selection.cohort_filter is None
                or view.researcher.ai_augment_cohort is selection.cohort_filter
            )
            and (
                not search_text
                or search_text in view.researcher.namekey.first_name.casefold()
                or search_text in view.researcher.namekey.last_name.casefold()
                or search_text in view.researcher.draw_number.casefold()
                or search_text == str(view.researcher.ai_augment_rnd)
                or search_text in view.researcher.namekey.to_json_key().casefold()
                or (
                    view.researcher.ai_augment_ineligibility_category is not None
                    and search_text
                    in view.researcher.ai_augment_ineligibility_category.value.casefold()
                )
            )
        )
        lifecycles = [
            view.current_lifecycle
            for view in views
            if view.researcher.ai_augment_cohort is not AiAugmentCohort.INELIGIBLE
        ]
        counts = _DashboardCounts(
            total=len(views),
            ground_truth=sum(
                view.researcher.ai_augment_cohort is AiAugmentCohort.GROUND_TRUTH
                for view in views
            ),
            no_ground_truth=sum(
                view.researcher.ai_augment_cohort is AiAugmentCohort.NO_GROUND_TRUTH
                for view in views
            ),
            ineligible=sum(
                view.researcher.ai_augment_cohort is AiAugmentCohort.INELIGIBLE
                for view in views
            ),
            ready=lifecycles.count(RunLifecycle.READY),
            queued=lifecycles.count(RunLifecycle.QUEUED),
            running=sum(lifecycle in {RunLifecycle.RUNNING, RunLifecycle.CODEX_EXITED}
                        for lifecycle in lifecycles),
            completed=lifecycles.count(RunLifecycle.COMPLETED),
            failed=lifecycles.count(RunLifecycle.FAILED),
            cancelled=lifecycles.count(RunLifecycle.CANCELLED),
        )
        return _DashboardView(
            counts=counts,
            researcher_var_views=rows,
            backend_status=self.backend_status,
            backend_availability=self.backend_availability,
            active_run_id=self.active_run_id,
        )

    async def researcher_card(
        self,
        *,
        namekey: NameKey,
    ) -> _ResearcherCardView:
        snapshot = self._snapshot
        researcher = snapshot.researchers_by_namekey.get(namekey.to_json_key())
        if researcher is None:
            raise KeyError(Locale.UNKNOWN_NAMEKEY_TEMPLATE.format(namekey=namekey))
        markdown = await asyncio.to_thread(self._render_card, researcher)
        return _ResearcherCardView(
            researcher=researcher,
            card_markdown=markdown,
        )

    async def _worker(self) -> None:
        while True:
            if not self._queue_processing or self._queue.empty():
                self._queue_wakeup.clear()
                await self._queue_wakeup.wait()
                continue
            # No await between permission check and dequeue; Stop gates the next run.
            run = self._queue.get_nowait()
            await self._process_queued_run(run)

    async def _process_queued_run(self, run: Run) -> None:
        try:
            queued = self._storage.load_queue()
            if run.run_id in queued:
                queued.remove(run.run_id)
                self._storage.save_queue(queued)
            if run.run_outcome is RunLifecycle.CANCELLED:
                return
            if not await self._wait_until_codex_idle(run=run):
                return
            self._active_run = run
            await self._execute_run(run=run)
        except asyncio.CancelledError:
            if run.is_running():
                await asyncio.shield(
                    self._record_run_outcome(
                        run=run,
                        run_outcome=RunLifecycle.FAILED,
                    )
                )
            raise
        except Exception as exc:
            cancelled = run.cancel_requested_at is not None and run.failure_detail is None
            if not run.is_finished():
                run_outcome = (
                    RunLifecycle.CANCELLED if cancelled else RunLifecycle.FAILED
                )
                await self._record_run_outcome(
                    run=run,
                    run_outcome=run_outcome,
                )
                await self._append_run_event(
                    RunEvent(
                        run_id=run.run_id,
                        namekey=run.namekey,
                        occurred_at_unix_usec=datetime_to_unix_usec(datetime.now(timezone.utc)),
                        lifecycle=run_outcome,
                        detail=None if cancelled else str(exc),
                    )
                )
                # Run.lifecycle -> run_outcome
        finally:
            cleanup_error: Exception | None = None
            try:
                await self._wind_down_owned_run_processes()
            except Exception as exc:
                cleanup_error = exc
            try:
                if cleanup_error is not None:
                    await self._append_run_event(
                        RunEvent(
                            run_id=run.run_id,
                            namekey=run.namekey,
                            occurred_at_unix_usec=datetime_to_unix_usec(datetime.now(timezone.utc)),
                            lifecycle=RunLifecycle.FAILED,
                            detail=Locale.RUN_PROCESS_CLEANUP_FAILED_TEMPLATE.format(
                                error=cleanup_error
                            ),
                        )
                    )
                    # Run.lifecycle -> RunLifecycle.FAILED
            finally:
                self._active_codex = None
                self._active_run = None
                self._queue.task_done()
                if not self._shutting_down:
                    await self.refresh_idle_state()

    async def _wind_down_owned_run_processes(self) -> None:
        codex_error: Exception | None = None
        active_codex = self._active_codex
        if active_codex is not None and active_codex.process.returncode is None:
            try:
                await self._codex.cancel(active_codex)
            except Exception as exc:
                codex_error = exc
        try:
            await self._backend.stop()
            self._backend_availability = _BackendAvailability(
                full_api_available=False,
                ipc_available=False,
            )
        except Exception as backend_error:
            if codex_error is not None:
                raise ExceptionGroup(
                    "Codex and Backend cleanup failed",
                    (codex_error, backend_error),
                )
            raise
        if codex_error is not None:
            raise codex_error

    async def _wait_until_codex_idle(self, *, run: Run) -> bool:
        while True:
            await self.refresh_idle_state()
            if run.run_outcome is RunLifecycle.CANCELLED:
                return False
            if not self._external_codex_busy:
                return True
            await asyncio.sleep(UI_REFRESH_SECONDS)

    async def _execute_run(
        self,
        *,
        run: Run,
    ) -> None:
        self._backend_availability = _BackendAvailability(
            full_api_available=False,
            ipc_available=False,
        )
        await self._backend.start(namekey=run_namekey(run))
        self._backend_availability = _BackendAvailability(
            full_api_available=True,
            ipc_available=True,
        )
        result = await self._codex.start(
            run=run,
            on_handle=self._register_active_codex,
        )
        # Run.lifecycle -> RunLifecycle.STARTED
        self._active_codex = result.handle
        await self._append_run_event(
            RunEvent(
                run_id=run.run_id,
                namekey=run.namekey,
                occurred_at_unix_usec=datetime_to_unix_usec(result.session_timestamp),
                lifecycle=RunLifecycle.SESSION_DISCOVERED,
                session_id=result.session_id,
            )
        )
        # Run.lifecycle -> RunLifecycle.SESSION_DISCOVERED

        await self._append_run_event(
            RunEvent(
                run_id=run.run_id,
                namekey=run.namekey,
                occurred_at_unix_usec=datetime_to_unix_usec(datetime.now(timezone.utc)),
                lifecycle=RunLifecycle.ROLLOUT_DISCOVERED,
                session_id=result.session_id,
                rollout_jsonl=result.rollout_jsonl,
            )
        )
        # Run.lifecycle -> RunLifecycle.ROLLOUT_DISCOVERED
        await self._backend.supply_session_id(result.session_id)
        if run.cancel_requested_at is not None:
            await self._record_run_outcome(
                run=run,
                run_outcome=RunLifecycle.CANCELLED,
            )
            await self._codex.cancel(result.handle)
        exit_code = await self._codex.wait(result.handle)
        await self._append_run_event(
            RunEvent(
                run_id=run.run_id,
                namekey=run.namekey,
                occurred_at_unix_usec=datetime_to_unix_usec(datetime.now(timezone.utc)),
                lifecycle=RunLifecycle.CODEX_EXITED,
                codex_exit_code=exit_code,
            )
        )
        # Run.lifecycle -> RunLifecycle.CODEX_EXITED
        run_outcome = await self._finalize_run(run=run)
        await self._record_run_outcome(
            run=run,
            run_outcome=run_outcome,
        )
        await self._append_run_event(
            RunEvent(
                run_id=run.run_id,
                namekey=run.namekey,
                occurred_at_unix_usec=datetime_to_unix_usec(datetime.now(timezone.utc)),
                lifecycle=run_outcome,
                codex_exit_code=exit_code,
            )
        )
        # Run.lifecycle -> run_outcome

    async def _register_active_codex(
        self,
        handle: _CodexProcessHandle,
    ) -> None:
        if self._active_run is not handle.run:
            raise RuntimeError(Locale.CODEX_HANDLE_MISMATCH)
        self._active_codex = handle
        run = handle.run
        if run.started_at is None:
            lifecycle = RunLifecycle.STARTED
        elif handle.remote_pid is not None and run.remote_pid != handle.remote_pid:
            lifecycle = RunLifecycle.REMOTE_PID_DISCOVERED
        else:
            return
        await self._append_run_event(
            RunEvent(
                run_id=run.run_id,
                namekey=run.namekey,
                occurred_at_unix_usec=datetime_to_unix_usec(datetime.now(timezone.utc)),
                lifecycle=lifecycle,
                remote_pid=(None if handle.remote_pid is None else int(handle.remote_pid)),
            )
        )

    async def _finalize_run(self, *, run: Run) -> RunLifecycle:
        if run.cancel_requested_at is not None:
            return RunLifecycle.CANCELLED
        response_code = await self._backend.probe_pull()
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                 f"Run {run.run_id} final /pull: HTTP {response_code}")
        return (RunLifecycle.COMPLETED if response_code == status.HTTP_410_GONE
                else RunLifecycle.FAILED)

    async def _record_run_outcome(
        self,
        *,
        run: Run,
        run_outcome: RunLifecycle,
    ) -> None:
        async with self._run_outcome_lock:
            if run.run_id in self._run_outcome_recorded_run_ids:
                return
            if self._backend.status is not _BackendStatus.RUNNING:
                return
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                     f"Sending run outcome: run={run.run_id}, outcome={run_outcome.value}")
            try:
                response_code = await asyncio.to_thread(
                    self._send_run_outcome,
                    run_outcome=run_outcome,
                    namekey=run_namekey(run),
                )
            except RuntimeError as exc:
                message = Locale.RUN_OUTCOME_SNAPSHOT_REQUEST_FAILED_TEMPLATE.format(
                    run_id=run.run_id,
                    error=exc,
                )
                self._notifications.append(message)
                emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, message)
                return
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                     f"Run outcome response: run={run.run_id}, HTTP {response_code}")
            self._run_outcome_recorded_run_ids.add(run.run_id)
            if response_code == status.HTTP_500_INTERNAL_SERVER_ERROR:
                message = Locale.RUN_OUTCOME_SNAPSHOT_PARTIAL_TEMPLATE.format(
                    run_id=run.run_id,
                    outcome=run_outcome.value,
                )
                self._notifications.append(message)
                emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, message)

    def drain_notifications(self) -> tuple[str, ...]:
        notifications = tuple(self._notifications)
        self._notifications.clear()
        return notifications

    async def _append_run_event(
        self,
        event: RunEvent,
    ) -> Run:
        events = [*self._events, event]
        self._storage.save_run_events(events)
        self._events = events
        run = apply_run_event(self._runs.get(event.run_id), event)
        self._runs[event.run_id] = run
        if event.lifecycle is not RunLifecycle.FAILED:
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                     f"Run {event.run_id}: {event.lifecycle.value}; namekey={event.namekey}; "
                     f"detail={event.detail or ''}")
        if event.lifecycle is RunLifecycle.FAILED:
            emit_log(
                Locale.CONTROL_CENTRE_LOG_PREFIX,
                Locale.RUN_FAILED_LOG_TEMPLATE.format(
                    run_id=event.run_id,
                    namekey=event.namekey,
                    detail=event.detail or "unspecified",
                ),
            )
        return run

    def _load_dashboard_storage(self) -> None:
        self._events = self._storage.load_run_events()
        self._runs = dict(replay_run_events(self._events))
        snapshot = self._storage.load_query_snapshot()
        if snapshot is not None:
            self._snapshot = snapshot

# =============================================================================
# NiceGUI page
# =============================================================================


class _UiHandles(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)

    backend_status_label: Any | None = None
    backend_ipc_status_label: Any | None = None
    backend_refresh_button: Any | None = None
    probe_button: Any | None = None
    queue_processing_button: Any | None = None
    ssh_status_label: Any | None = None
    codex_status_label: Any | None = None
    probe_time_label: Any | None = None
    summary_label: Any | None = None

    researcher_var_select: Any | None = None
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
    download_card_button_docx: Any | None = None
    download_card_button_txt: Any | None = None


class _ControlCentrePage:
    def __init__(
        self,
        *,
        controller: _ControlCentreController,
        query_ipc: Callable[[], Awaitable[None]],
        reference_docx: Path,
    ) -> None:
        self._controller = controller
        self._query_ipc = query_ipc
        self._reference_docx = reference_docx
        self._selection = _UiSelection(researcher_varname=RESEARCHER_VARS[0].varname)
        self._handles = _UiHandles()
        self._grid_initialized = False
        self._grid_researcher_varname = self._selection.researcher_varname
        self._grid_rows_by_id: dict[str, dict[str, Any]] = {}
        self._researcher_var_views_by_namekey: dict[str, _ResearcherVarView] = {}
        self._expanded_history_namekey: NameKey | None = None
        self._displayed_card: _ResearcherCardView | None = None

    @property
    def selection(self) -> _UiSelection:
        return self._selection

    def build(self) -> None:
        ui.add_css(CARD_RESPONSIVE_CSS)
        with (
            ui
            .column()
            .style(PAGE_CONTAINER_STYLE)
            .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_CONTAINER_TEST_ID))
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
            ui.column().style(FULL_WIDTH_STYLE)
            .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_HEADER_TEST_ID))
        ):
            with ui.row().style(RESPONSIVE_ROW_STYLE):
                ui.label(Locale.PAGE_TITLE)
                self._handles.probe_button = ui.button(Locale.ACTION_PROBE, on_click=self.probe_all)
                self._handles.backend_refresh_button = ui.button(
                    Locale.ACTION_QUERY_IPC, on_click=self.refresh_from_ipc,
                ).props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=BACKEND_REFRESH_TEST_ID))
                self._handles.queue_processing_button = ui.button(
                    Locale.ACTION_STOP_QUEUE_PROCESSING if self._controller.queue_processing
                    else Locale.ACTION_START_QUEUE_PROCESSING,
                    on_click=self.toggle_queue_processing,
                )
            with ui.row().style(RESPONSIVE_ROW_STYLE):
                self._handles.backend_status_label = ui.label()
                self._handles.backend_ipc_status_label = ui.label().props(
                    _NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=BACKEND_IPC_STATUS_TEST_ID)
                )
                self._handles.ssh_status_label = ui.label()
                self._handles.codex_status_label = ui.label()
                self._handles.probe_time_label = ui.label()

    def build_summary(self) -> None:
        self._handles.summary_label = (
            ui
            .label(Locale.SUMMARY_LOADING)
            .style(FULL_WIDTH_STYLE)
            .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_SUMMARY_TEST_ID))
        )

    def build_filters(self) -> None:
        with (
            ui
            .row()
            .style(RESPONSIVE_ROW_STYLE)
            .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_FILTERS_TEST_ID))
        ):
            self._handles.researcher_var_select = ui.select(
                {
                    researcher_var.varname: researcher_var.ai_column
                    for researcher_var in RESEARCHER_VARS
                },
                value=self._selection.researcher_varname,
                label=Locale.VARIABLE_FILTER,
                on_change=lambda event: self.on_researcher_var_changed(event.value),
            )
            self._handles.status_select = ui.select(
                {
                    "": Locale.ALL_STATUSES,
                    **{
                        lifecycle.value: lifecycle.value
                        for lifecycle in RESEARCHER_LIFECYCLES
                    },
                },
                value="",
                label=Locale.STATUS_FILTER,
                on_change=lambda event: self.on_lifecycle_filter_changed(
                    None if not event.value else RunLifecycle(event.value)
                ),
            )
            self._handles.cohort_select = ui.select(
                {
                    "": Locale.ALL_COHORTS,
                    **{cohort.value: cohort.value for cohort in AiAugmentCohort},
                },
                value="",
                label=Locale.COHORT_FILTER,
                on_change=lambda event: self.on_cohort_filter_changed(event.value or None),
            )
            self._handles.search_input = ui.input(
                label=Locale.SEARCH_FILTER,
                on_change=lambda event: self.on_search_changed(event.value),
            ).props(_NiceGui.CLEARABLE_PROP)

    def build_grid(self) -> None:
        researcher_var = RESEARCHER_VARS_BY_VARNAME[self._selection.researcher_varname]
        self._handles.grid = (
            ui
            .aggrid(
                AgGrid.options(
                    columns=self.grid_column_definitions(researcher_var=researcher_var),
                    rows=[],
                    row_id_field=GRID_ROW_ID_FIELD,
                ),
                auto_size_columns=False,
            )
            .style(GRID_STYLE)
            .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=RESEARCHER_GRID_TEST_ID))
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
            .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=ACTION_PANEL_TEST_ID))
        ):
            self._handles.selected_researcher_label = ui.label(Locale.NO_RESEARCHER_SELECTED)
            self._handles.execute_button = (
                ui
                .button(
                    Locale.ACTION_SELECT_RESEARCHER,
                    on_click=self.on_execute_selected,
                )
                .style(ACTION_BUTTON_STYLE)
                .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=EXECUTE_ACTION_TEST_ID))
                .on(
                    _NiceGui.MOUSE_DOWN_EVENT,
                    js_handler=_NiceGui.PRESERVE_SELECTION_HANDLER,
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
                .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=VIEW_CARD_TEST_ID))
                .on(
                    _NiceGui.MOUSE_DOWN_EVENT,
                    js_handler=_NiceGui.PRESERVE_SELECTION_HANDLER,
                )
            )
            self._handles.view_card_button.disable()

    def build_attempt_history_panel(self) -> None:
        researcher_var = RESEARCHER_VARS_BY_VARNAME[self._selection.researcher_varname]
        self._handles.attempt_history_expansion = (
            ui
            .expansion(Locale.ATTEMPT_HISTORY)
            .style(ATTEMPT_HISTORY_STYLE)
            .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=ATTEMPT_HISTORY_PANEL_TEST_ID))
        )
        with self._handles.attempt_history_expansion:
            self._handles.attempt_history_table = (
                ui
                .table(
                    rows=[],
                    columns=self.attempt_history_column_definitions(researcher_var=researcher_var),
                    row_key=GRID_ROW_ID_FIELD,
                )
                .style(ATTEMPT_HISTORY_TABLE_STYLE)
                .props(
                    f"{ATTEMPT_HISTORY_TABLE_PROPS} "
                    f"{_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=ATTEMPT_HISTORY_TABLE_TEST_ID)}"
                )
            )
        self._handles.attempt_history_expansion.set_visibility(False)

    def build_card_panel(self) -> None:
        self._handles.card_container = (
            ui
            .card()
            .style(CARD_CONTAINER_STYLE)
            .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_FOOTER_TEST_ID))
        )
        with self._handles.card_container:
            with ui.row().style(RESPONSIVE_ROW_STYLE):
                self._handles.download_card_button_docx = (
                    ui
                    .button(
                        Locale.ACTION_DOWNLOAD_DOCX,
                        on_click=self.download_displayed_card,
                    )
                    .style(ACTION_BUTTON_STYLE)
                    .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=DOWNLOAD_CARD_DOCX_TEST_ID))
                )
                self._handles.download_card_button_docx.disable()
                self._handles.download_card_button_txt = (
                    ui
                    .button(
                        Locale.ACTION_DOWNLOAD_TXT,
                        on_click=lambda: self.download_displayed_card(output_format="txt"),
                    )
                    .style(ACTION_BUTTON_STYLE)
                    .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=DOWNLOAD_CARD_TXT_TEST_ID))
                )
                self._handles.download_card_button_txt.disable()
            self._handles.card_markdown = (
                ui
                .markdown("")
                .style(CARD_MARKDOWN_STYLE)
                .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=CARD_MARKDOWN_TEST_ID))
            )

    def grid_column_definitions(
        self,
        *,
        researcher_var: _ResearcherVar,
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
                header=researcher_var.ai_column,
                width=GRID_CONTENT_COLUMN_WIDTH,
                wrap_text=True,
            ),
            AgGrid.column(
                field=GRID_TABLE_1_VALUE_FIELD,
                header=researcher_var.table_1_column,
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
                field=GRID_COMMIT_RECORD_ID_FIELD,
                header=KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL,
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
            AgGrid.column(
                field=GRID_RUN_OUTCOME_SNAPSHOT_FIELD,
                header=GRID_RUN_OUTCOME_SNAPSHOT_FIELD,
                width=GRID_STATUS_COLUMN_WIDTH,
            ),
            AgGrid.column(
                field=GRID_SESSION_STATUS_FIELD,
                header=GRID_SESSION_STATUS_FIELD,
                width=GRID_CONTENT_COLUMN_WIDTH,
                wrap_text=True,
            ),
        ]

    def attempt_history_column_definitions(
        self,
        *,
        researcher_var: _ResearcherVar,
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
                field=GRID_COMMIT_RECORD_ID_FIELD,
                label=KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL,
            ),
            nicegui_table_column(
                field=GRID_RUN_OUTCOME_SNAPSHOT_FIELD,
                label=GRID_RUN_OUTCOME_SNAPSHOT_FIELD,
            ),
            nicegui_table_column(
                field=GRID_SESSION_STATUS_FIELD,
                label=GRID_SESSION_STATUS_FIELD,
            ),
            nicegui_table_column(
                field=GRID_AI_VALUE_FIELD,
                label=researcher_var.ai_column,
            ),
            nicegui_table_column(
                field=GRID_TABLE_1_VALUE_FIELD,
                label=researcher_var.table_1_column,
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
        snapshot: _DashboardView,
        researcher_var: _ResearcherVar,
    ) -> dict[str, Any]:
        return AgGrid.options(
            columns=self.grid_column_definitions(researcher_var=researcher_var),
            rows=self.grid_rows(snapshot=snapshot),
            row_id_field=GRID_ROW_ID_FIELD,
        )

    def grid_rows(
        self,
        *,
        snapshot: _DashboardView,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in snapshot.researcher_var_views:
            researcher = row.researcher
            latest = row.latest_run_commit_var_view
            rows.append({
                GRID_ROW_ID_FIELD: researcher.namekey.to_json_key(),
                GRID_NAMEKEY_FIELD: researcher.namekey.to_json_key(),
                GRID_RUN_ID_FIELD: (None if latest.run_id is None else str(latest.run_id)),
                GRID_RND_FIELD: researcher.ai_augment_rnd,
                GRID_DRAW_FIELD: latest.draw_number,
                GRID_LAST_NAME_FIELD: latest.last_name,
                GRID_FIRST_NAME_FIELD: latest.first_name,
                GRID_COHORT_FIELD: researcher.ai_augment_cohort.value,
                GRID_INELIGIBILITY_FIELD: (
                    None
                    if researcher.ai_augment_ineligibility_category is None
                    else researcher.ai_augment_ineligibility_category.value
                ),
                GRID_AI_VALUE_FIELD: latest.ai_value,
                GRID_TABLE_1_VALUE_FIELD: latest.table_1_value,
                GRID_FOOTNOTES_FIELD: latest.footnotes,
                GRID_FOOTNOTE_ARGUMENTS_FIELD: latest.footnote_arguments,
                GRID_COMMIT_RECORD_ID_FIELD: latest.commit_record_id,
                GRID_ATTEMPT_TIMESTAMP_FIELD: (
                    None
                    if latest.timestamp is None
                    else latest.timestamp.isoformat()
                ),
                GRID_STATUS_FIELD: latest.lifecycle.value,
                GRID_RUN_OUTCOME_SNAPSHOT_FIELD: latest.run_outcome_snapshot_savedness,
                GRID_SESSION_STATUS_FIELD: latest.session_status,
                GRID_ACTION_FIELD: latest.action.value,
            })
        return rows

    def attempt_detail_rows(
        self,
        *,
        row: _ResearcherVarView,
    ) -> list[dict[str, Any]]:
        return [
            {
                GRID_ROW_ID_FIELD: str(
                    attempt.commit_record_id if attempt.commit_record_id is not None
                    else attempt.run_id
                ),
                GRID_RUN_ID_FIELD: (str(attempt.run_id) if attempt.run_id is not None else None),
                GRID_COMMIT_RECORD_ID_FIELD: attempt.commit_record_id,
                GRID_ATTEMPT_TIMESTAMP_FIELD: (
                    None
                    if attempt.timestamp is None
                    else attempt.timestamp.isoformat()
                ),
                GRID_STATUS_FIELD: (attempt.backend_lifecycle or attempt.lifecycle).value,
                GRID_RUN_OUTCOME_SNAPSHOT_FIELD: attempt.run_outcome_snapshot_savedness,
                GRID_SESSION_STATUS_FIELD: attempt.session_status,
                GRID_AI_VALUE_FIELD: attempt.ai_value,
                GRID_TABLE_1_VALUE_FIELD: attempt.table_1_value,
                GRID_FOOTNOTES_FIELD: attempt.footnotes,
                GRID_FOOTNOTE_ARGUMENTS_FIELD: attempt.footnote_arguments,
            }
            for attempt in row.run_commit_var_views
        ]

    async def refresh(self) -> None:
        if self._handles.queue_processing_button is not None:
            self._handles.queue_processing_button.set_text(
                Locale.ACTION_STOP_QUEUE_PROCESSING if self._controller.queue_processing
                else Locale.ACTION_START_QUEUE_PROCESSING,
            )
        snapshot = await self._controller.snapshot(selection=self._selection)
        for message in self._controller.drain_notifications():
            ui.notify(message, type="negative")
        availability = snapshot.backend_availability
        for label, template, value in (
            (self._handles.backend_status_label, Locale.BACKEND_STATUS_TEMPLATE,
             availability.full_api_available),
            (self._handles.backend_ipc_status_label, Locale.IPC_STATUS_TEMPLATE,
             availability.ipc_available),
            (self._handles.ssh_status_label, Locale.SSH_STATUS_TEMPLATE,
             availability.ssh_available),
            (self._handles.codex_status_label, Locale.CODEX_AUTH_STATUS_TEMPLATE,
             availability.codex_authenticated),
        ):
            if label is not None:
                label.set_text(template.format(status=availability.status_text(value)))
        if self._handles.probe_time_label is not None:
            self._handles.probe_time_label.set_text(Locale.PROBE_TIME_TEMPLATE.format(
                timestamp=(Locale.PROBE_NOT_CHECKED if availability.checked_at is None
                           else availability.checked_at.isoformat(timespec="seconds")),
            ))
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
                    completed=counts.completed,
                    failed=counts.failed,
                    cancelled=counts.cancelled,
                )
            )
        await self.refresh_grid(snapshot=snapshot)

    async def toggle_queue_processing(self) -> None:
        self._controller.set_queue_processing(not self._controller.queue_processing)
        await self.refresh()

    async def probe_all(self) -> None:
        if self._handles.probe_button is not None:
            self._handles.probe_button.disable()
        try:
            await self._controller.probe_all()
        except Exception as exc:
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Dashboard probes failed: {exc!r}")
            raise
        finally:
            if self._handles.probe_button is not None:
                self._handles.probe_button.enable()
            await self.refresh()

    async def refresh_from_ipc(self) -> None:
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, "Query IPC requested")
        try:
            await self._query_ipc()
        except RuntimeError as exc:
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Query IPC failed: {exc!r}")
            ui.notify(Locale.BACKEND_DATABASE_REQUEST_FAILED, type="negative")
        else:
            self._clear_displayed_card()
            ui.notify(Locale.QUERY_SNAPSHOT_REPLACED, type="positive")
        await self.refresh()

    async def refresh_grid(
        self,
        *,
        snapshot: _DashboardView | None = None,
    ) -> None:
        if self._handles.grid is None:
            return
        if snapshot is None:
            snapshot = await self._controller.snapshot(selection=self._selection)
        researcher_var = RESEARCHER_VARS_BY_VARNAME[self._selection.researcher_varname]
        self._researcher_var_views_by_namekey = {
            row.researcher.namekey.to_json_key(): row for row in snapshot.researcher_var_views
        }
        card = self._displayed_card
        if card is not None:
            current = self._researcher_var_views_by_namekey.get(
                card.researcher.namekey.to_json_key(),
            )
            if current is None or current.researcher is not card.researcher:
                self._clear_displayed_card()
        self.refresh_attempt_history()
        rows = self.grid_rows(snapshot=snapshot)
        self.sync_selected_action(rows)
        if not self._grid_initialized:
            options = self.grid_options(
                snapshot=snapshot,
                researcher_var=researcher_var,
            )
            self._handles.grid.options.update(options)
            self._handles.grid.update()
            self._grid_rows_by_id = {str(row[GRID_ROW_ID_FIELD]): row for row in rows}
            self._grid_researcher_varname = self._selection.researcher_varname
            self._grid_initialized = True
            return
        if self._grid_researcher_varname != self._selection.researcher_varname:
            await self._handles.grid.run_grid_method(
                AgGrid.SET_GRID_OPTION_METHOD,
                AgGrid.COLUMN_DEFINITIONS_OPTION,
                self.grid_column_definitions(researcher_var=researcher_var),
            )
            self._grid_researcher_varname = self._selection.researcher_varname
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
        row = self._researcher_var_views_by_namekey.get(namekey.to_json_key())
        if row is None:
            table.update_rows([], clear_selection=True)
            if self._handles.attempt_history_expansion is not None:
                self._handles.attempt_history_expansion.set_visibility(False)
            self._expanded_history_namekey = None
            return
        table.update_rows(
            self.attempt_detail_rows(row=row),
            clear_selection=False,
        )

    async def refresh_card(self) -> None:
        namekey = self._selection.selected_namekey
        if namekey is None:
            return
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Rendering researcher card: {namekey}")
        try:
            card = await self._controller.researcher_card(namekey=namekey)
        except Exception as exc:
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                     f"Researcher card failed: {namekey}; {exc!r}")
            raise
        if self._selection.selected_namekey == namekey:
            await self._show_card(card)
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                     f"Researcher card displayed: {namekey}; "
                     f"DOCX/TXT available={card.download_available}")

    async def _show_card(self, card: _ResearcherCardView) -> None:
        if self._handles.selected_researcher_label is not None:
            self._handles.selected_researcher_label.set_text(
                Locale.RESEARCHER_SELECTION_TEMPLATE.format(
                    first_name=card.researcher.namekey.first_name,
                    last_name=card.researcher.namekey.last_name,
                    draw_number=card.researcher.draw_number,
                )
            )
        if self._handles.card_markdown is not None:
            self._handles.card_markdown.set_content(card.card_markdown)
        self._displayed_card = card if card.download_available else None
        for button in (
            self._handles.download_card_button_docx,
            self._handles.download_card_button_txt,
        ):
            if button is not None:
                if card.download_available:
                    button.enable()
                else:
                    button.disable()

    def _clear_displayed_card(self) -> None:
        self._displayed_card = None
        if self._handles.card_markdown is not None:
            self._handles.card_markdown.set_content("")
        for button in (
            self._handles.download_card_button_docx,
            self._handles.download_card_button_txt,
        ):
            if button is not None:
                button.disable()

    def _invalidate_card(self, namekey: NameKey) -> None:
        if (
            self._displayed_card is not None
            and self._displayed_card.researcher.namekey == namekey
        ):
            self._clear_displayed_card()

    async def download_displayed_card(
        self,
        *,
        output_format: Literal["docx", "txt"] = "docx",
    ) -> None:
        label = output_format.upper()
        card = self._displayed_card
        if card is None or not card.download_available:
            emit_log(
                Locale.CONTROL_CENTRE_LOG_PREFIX,
                f"{label} download skipped: no available card",
            )
            return
        button = (
            self._handles.download_card_button_docx
            if output_format == "docx"
            else self._handles.download_card_button_txt
        )
        filename = f"{card.filename_stem}.{output_format}"
        if button is not None:
            button.disable()
        emit_log(
            Locale.CONTROL_CENTRE_LOG_PREFIX,
            f"Rendering {label} download: {filename}",
        )
        try:
            if output_format == "docx":
                content = await asyncio.to_thread(card.render_docx, self._reference_docx)
                media_type = DOCX_MEDIA_TYPE
            else:
                content = card.card_markdown.encode(TEXT_ENCODING)
                media_type = TXT_MEDIA_TYPE
            ui.download(content, filename=filename, media_type=media_type)
            emit_log(
                Locale.CONTROL_CENTRE_LOG_PREFIX,
                f"{label} sent to browser: {filename}; {len(content)} bytes",
            )
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            emit_log(
                Locale.CONTROL_CENTRE_LOG_PREFIX,
                f"{label} download failed: {filename}; {exc!r}",
            )
            ui.notify(
                Locale.DOCX_DOWNLOAD_FAILED
                if output_format == "docx"
                else Locale.TXT_DOWNLOAD_FAILED,
                type="negative",
            )
        finally:
            if button is not None and self._displayed_card is card:
                button.enable()

    def show_attempt_history(
        self,
        namekey: NameKey,
    ) -> None:
        expansion = self._handles.attempt_history_expansion
        table = self._handles.attempt_history_table
        row = self._researcher_var_views_by_namekey.get(namekey.to_json_key())
        if expansion is None or table is None or row is None:
            return
        researcher_var = RESEARCHER_VARS_BY_VARNAME[self._selection.researcher_varname]
        table.columns = self.attempt_history_column_definitions(researcher_var=researcher_var)
        table.update_rows(self.attempt_detail_rows(row=row), clear_selection=False)
        expansion.set_text(
            Locale.ATTEMPT_HISTORY_TEMPLATE.format(
                first_name=row.latest_run_commit_var_view.first_name,
                last_name=row.latest_run_commit_var_view.last_name,
            )
        )
        expansion.set_visibility(True)
        expansion.open()
        self._expanded_history_namekey = namekey

    async def on_researcher_var_changed(
        self,
        researcher_varname: str,
    ) -> None:
        if researcher_varname not in RESEARCHER_VARS_BY_VARNAME:
            raise KeyError(Locale.UNKNOWN_VARIABLE_TEMPLATE.format(variable_key=researcher_varname))
        self._selection.researcher_varname = researcher_varname
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Researcher var selected: {researcher_varname}")
        await self.refresh_grid()
        expanded_namekey = self._expanded_history_namekey
        if expanded_namekey is not None:
            self.show_attempt_history(expanded_namekey)

    async def on_lifecycle_filter_changed(
        self,
        lifecycle: RunLifecycle | None,
    ) -> None:
        self._selection.lifecycle_filter = lifecycle
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Lifecycle filter: {lifecycle}")
        await self.refresh_grid()

    async def on_cohort_filter_changed(
        self,
        cohort: str | None,
    ) -> None:
        self._selection.cohort_filter = None if cohort is None else AiAugmentCohort(cohort)
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Cohort filter: {cohort}")
        await self.refresh_grid()

    async def on_search_changed(
        self,
        search_text: str | None,
    ) -> None:
        self._selection.search_text = "" if search_text is None else search_text
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Search filter: {search_text!r}")
        await self.refresh_grid()

    async def on_researcher_selected(
        self,
        namekey: NameKey,
    ) -> None:
        self._selection.selected_namekey = namekey
        await self.refresh_card()

    def sync_selected_action(
        self,
        rows: Sequence[Mapping[str, object]],
    ) -> None:
        selected_namekey = self._selection.selected_namekey
        selected_namekey_json = (
            None if selected_namekey is None else selected_namekey.to_json_key()
        )
        selected = next(
            (
                row
                for row in rows
                if row.get(GRID_NAMEKEY_FIELD) == selected_namekey_json
            ),
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
            self._clear_displayed_card()
            return
        if (
            self._displayed_card is not None
            and self._displayed_card.researcher.namekey != selected_namekey
        ):
            self._clear_displayed_card()
        run_id_value = selected.get(GRID_RUN_ID_FIELD)
        action = _RunAction(str(selected[GRID_ACTION_FIELD]))
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
            if action is _RunAction.DISABLED:
                self._handles.execute_button.disable()
            else:
                self._handles.execute_button.enable()

    async def on_queue(
        self,
        namekey: NameKey,
    ) -> None:
        self._invalidate_card(namekey)
        run_id = await self._controller.queue(namekey=namekey)
        self._selection.selected_run_id = run_id
        self._selection.selected_action = _RunAction.CANCEL
        self.update_execute_button()

    async def on_rerun(
        self,
        namekey: NameKey,
    ) -> None:
        self._invalidate_card(namekey)
        run_id = await self._controller.rerun(namekey=namekey)
        self._selection.selected_run_id = run_id
        self._selection.selected_action = _RunAction.CANCEL
        self.update_execute_button()

    async def on_cancel(
        self,
        run_id: UUID,
    ) -> None:
        await self._controller.cancel(run_id=run_id)
        self._selection.selected_action = _RunAction.RERUN
        self.update_execute_button()

    def update_execute_button(self) -> None:
        button = self._handles.execute_button
        action = self._selection.selected_action
        if button is None or action is None:
            return
        button.set_text(ACTION_LABEL_BY_VALUE[action.value])
        if action is _RunAction.DISABLED:
            button.disable()
        else:
            button.enable()

    async def on_grid_action(
        self,
        *,
        action: _RunAction,
        namekey: NameKey,
        run_id: UUID | None,
    ) -> None:
        if action is _RunAction.QUEUE:
            await self.on_queue(namekey)
        elif action is _RunAction.RERUN:
            await self.on_rerun(namekey)
        elif action is _RunAction.CANCEL and run_id is not None:
            await self.on_cancel(run_id)

    async def on_execute_selected(self) -> None:
        namekey = self._selection.selected_namekey
        action = self._selection.selected_action
        if namekey is None or action is None or action is _RunAction.DISABLED:
            return
        await self.on_grid_action(
            action=action,
            namekey=namekey,
            run_id=self._selection.selected_run_id,
        )

    async def _on_grid_cell_clicked(self, event: Any) -> None:
        arguments = event.args
        data = arguments.get(AgGrid.EVENT_DATA, {})
        namekey_json = str(data.get(GRID_NAMEKEY_FIELD, ""))
        if not namekey_json:
            return
        namekey = NameKey.from_json_key(namekey_json)
        self._selection.selected_namekey = namekey
        self.sync_selected_action((data,))
        self.show_attempt_history(namekey)


# =============================================================================
# Application-level dependency graph
# =============================================================================


class _ApplicationServices(BaseModel):
    # These are runtime service instances, not serialized configuration.
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, arbitrary_types_allowed=True,
    )

    configuration: AiAugmentControlCentreContext
    storage: AiAugmentDashboardStorage
    backend: _BackendSupervisor
    backend_database: _BackendDatabaseClient
    codex: _CodexRunner
    controller: _ControlCentreController
    query_ipc: Callable[[], Awaitable[None]]


SERVICES: _ApplicationServices | None = None
APPLICATION_LIFECYCLE_CONFIGURED = False
APPLICATION_CONFIG_PATH = DEFAULT_CONFIG_PATH
APPLICATION_PUBLISH_COMPLETED = False
APPLICATION_EXIT_CODE = 0


def create_services(*, config_path: Path) -> _ApplicationServices:
    pipeline_config = AiAugmentDetourConfig.from_json(config_path)
    configuration = AiAugmentControlCentreContext(pipeline_config=pipeline_config)
    storage = AiAugmentDashboardStorage()
    backend = _BackendSupervisor(
        repository_root=REPOSITORY_ROOT,
        config_path=config_path,
        openalex_api_key=configuration.openalex_api_key,
        appendwatch_report=PurePosixPath(
            configuration.lima_configuration.param[LIMA_APPENDWATCH_REPORT_PARAM]
        ),
        dashboard_socket_path=DASHBOARD_SOCKET_PATH,
        configuration=configuration,
    )
    backend_database = _BackendDatabaseClient(
        socket_path=DASHBOARD_SOCKET_PATH, pipeline_config=pipeline_config,
    )
    codex = _CodexRunner(timezone=ZoneInfo(pipeline_config.timezone))
    controller = _ControlCentreController(
        storage=storage, backend=backend, codex=codex,
        probe_ipc=backend_database.available,
        record_run_outcome=backend_database.record_run_outcome,
        render_card=backend_database.card,
    )

    async def query_ipc() -> None:
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, "Requesting wholesale Backend query snapshot")
        try:
            async with backend.query_connection(backend_database):
                response = await asyncio.to_thread(
                    backend_database.send_query_request, QueryRequest(),
                )
            # Storage and the controller reference change together, after child cleanup.
            snapshot = storage.replace_query_response(response)
            controller.accept_query_snapshot(snapshot)
        except Exception as exc:
            logger.exception("Dashboard query snapshot replacement failed")
            raise RuntimeError(Locale.BACKEND_DATABASE_RESPONSE_INVALID) from exc
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                 f"Dashboard snapshot replaced: {len(snapshot.ai_augment_singular_outerdicts)} "
                 f"researchers, {len(response.attempts)} attempts, "
                 f"{len(response.run_outcome_records)} run outcomes")

    return _ApplicationServices(
        configuration=configuration, storage=storage, backend=backend,
        backend_database=backend_database, codex=codex, controller=controller,
        query_ipc=query_ipc,
    )


def require_services() -> _ApplicationServices:
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
    services = require_services()
    page = _ControlCentrePage(
        controller=services.controller,
        query_ipc=services.query_ipc,
        reference_docx=services.configuration.pipeline_config.pandoc_reference_docx,
    )
    page.build()
    await page.refresh()


# =============================================================================
# NiceGUI / backend lifecycle
# =============================================================================


async def publish_completed(services: _ApplicationServices) -> None:
    controller = services.controller
    config = services.configuration.pipeline_config
    dashboard = await controller.snapshot(
        selection=_UiSelection(researcher_varname=RESEARCHER_VARS[0].varname),
    )
    candidates = [
        row for row in dashboard.researcher_var_views
        if row.researcher.ai_augment_cohort is not AiAugmentCohort.INELIGIBLE
        and row.latest_run_commit_var_view.lifecycle is RunLifecycle.COMPLETED
    ]
    cards = []
    for row in candidates:
        card = await controller.researcher_card(namekey=row.researcher.namekey)
        if card.download_available:
            cards.append(card)
    emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
             f"Publish completed: {dashboard.counts.total} researchers; {len(candidates)} eligible "
             f"and completed; {len(cards)} DOCX downloads available")
    logger.info(
        "Publish completed: %d researchers; %d eligible and completed; "
        "%d DOCX downloads available",
        dashboard.counts.total, len(candidates), len(cards),
    )
    if cards:
        config.output_dir.mkdir(parents=True, exist_ok=True)
    for index, card in enumerate(cards, start=1):
        destination = config.output_dir / card.docx_filename
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                 f"[{index}/{len(cards)}] Rendering {destination}")
        logger.info("[%d/%d] Rendering %s", index, len(cards), destination)
        docx = await asyncio.to_thread(card.render_docx, config.pandoc_reference_docx)
        await asyncio.to_thread(destination.write_bytes, docx)
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                 f"[{index}/{len(cards)}] Written {destination}: {len(docx)} bytes")
        logger.info("[%d/%d] Written %s", index, len(cards), destination)
    emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Publishing finished: {len(cards)} DOCX files")
    logger.info("Publishing finished: %d DOCX files", len(cards))


async def publish_completed_and_shutdown() -> None:
    global APPLICATION_EXIT_CODE
    try:
        await publish_completed(require_services())
    except Exception as exc:
        APPLICATION_EXIT_CODE = 1
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Publishing failed: {exc!r}")
        logger.exception("Publishing completed researchers failed")
    finally:
        app.shutdown()


async def application_startup() -> None:
    global SERVICES, APPLICATION_EXIT_CODE
    try:
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
                 f"Starting Dashboard with config {APPLICATION_CONFIG_PATH}")
        if SERVICES is None:
            services = create_services(config_path=APPLICATION_CONFIG_PATH)
            try:
                await services.controller.start(publishing=APPLICATION_PUBLISH_COMPLETED)
            except BaseException:
                await services.controller.shutdown()
                raise
            SERVICES = services
        else:
            await SERVICES.controller.start(publishing=APPLICATION_PUBLISH_COMPLETED)
        emit_log(
            Locale.CONTROL_CENTRE_LOG_PREFIX,
            Locale.READY_LOG_TEMPLATE.format(url=CONTROL_CENTRE_BASE_URL),
        )
        if APPLICATION_PUBLISH_COMPLETED:
            await publish_completed_and_shutdown()
    except Exception as exc:
        APPLICATION_EXIT_CODE = 1
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Dashboard startup failed: {exc!r}")
        logger.exception("Dashboard startup failed")
        app.shutdown()


async def application_shutdown() -> None:
    global APPLICATION_EXIT_CODE
    if SERVICES is not None:
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, Locale.STOPPING_LOG)
        try:
            await SERVICES.controller.shutdown()
        except Exception as exc:
            APPLICATION_EXIT_CODE = 1
            emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, f"Dashboard shutdown failed: {exc!r}")
            raise
        emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX, Locale.STOPPED_LOG)


def configure_application_lifecycle() -> None:
    global APPLICATION_LIFECYCLE_CONFIGURED

    if APPLICATION_LIFECYCLE_CONFIGURED:
        return
    app.on_startup(application_startup)
    app.on_shutdown(application_shutdown)
    APPLICATION_LIFECYCLE_CONFIGURED = True


def main(argv: list[str] | None = None) -> int:
    global APPLICATION_CONFIG_PATH, APPLICATION_PUBLISH_COMPLETED, APPLICATION_EXIT_CODE

    parser = argparse.ArgumentParser()
    parser.add_argument(CONFIG_OPTION, required=True, type=Path)
    parser.add_argument("operation", nargs="?", choices=["publish"])
    parser.add_argument("selection", nargs="?", choices=["completed"])
    arguments = parser.parse_args(argv)
    if (arguments.operation is None) != (arguments.selection is None):
        parser.error("Publishing requires: publish completed")
    APPLICATION_PUBLISH_COMPLETED = arguments.operation == "publish"
    APPLICATION_EXIT_CODE = 0
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
    return APPLICATION_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
