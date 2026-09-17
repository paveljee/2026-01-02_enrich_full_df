from __future__ import annotations

import asyncio
import base64
import csv
import fcntl
import hashlib
import io
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, Literal, cast
from unittest.mock import AsyncMock, Mock
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import duckdb
import pytest
from fastapi import status
from nicegui import app, ui
from pydantic import ValidationError

from src.detours.detour_ai_augment.protected.src.backend import ipc
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (  # noqa: E501
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_init import (  # noqa: E501
    Submission,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AI_AUGMENT_COLUMNS,
    BACKEND_STORE_CLOSED_CLEANLY,
    DOCX_COLUMNS,
    EXCLUDED_NAMEKEY,
    KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL,
    KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL,
    KTP_AI_AUGMENT_FOOTNOTES_COL,
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
    MAP_SUBSET_0_TO_BATCH_KEY,
    REPLAY_LOG_KEY,
    AiAugmentCohort,
    AiAugmentIneligibilityCategory,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers import (
    vars as control_vars,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (
    Locale,
)
from src.detours.detour_ai_augment.src.backend import api
from src.detours.detour_ai_augment.src.backend import server as backend_server
from src.detours.detour_ai_augment.src.backend.helpers.data_models import (
    ai_augment_context as backend_context_models,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_singular_outer_dict import (  # noqa: E501
    AiAugmentSingularOuterDict,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_event import (
    SOURCE_KEY_HEADER,
    AppendwatchReportEncoding,
    AppendwatchReportRecord,
    BackendCommitRecord,
    BackendLifecycle,
    CodexRolloutRecord,
    CodexSessionRecord,
    CommitRequestBody,
    PostCommitValidation,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.committed_innerdict import (  # noqa: E501
    CommittedInnerDict,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.query_response import (
    AgentRuntimeAttempt,
    AgentRuntimeAttemptRecord,
    QueryResponse,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.run_outcome_response import (
    RunOutcomeResponse,
    RunOutcomeResponseBody,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    ai_augment_context as context_models,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    ai_augment_dashboard_storage as storage_models,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    run_event as run_event_models,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    run_outcome as run_outcome_models,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.query_request import (  # noqa: E501
    QueryRequest,
)
from src.helpers.architecture import FrozenStrictModel
from src.helpers.data_models import HttpRequestLogRecord, InnerDict, NameKey
from src.helpers.duckdb_utils import duckdb_quote_identifier as quote
from src.helpers.procedures import DocxMatchProcedure, XlsxMatchProcedure
from src.helpers.schema import (
    CARD_PARTITION_TABLE,
    DOCX_INNERDICT_TABLE,
    PARQUET_INNERDICT_TABLE,
    XLSX_INNERDICT_TABLE,
)
from src.helpers.vars import (
    BATCH_LABEL,
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_INNERDICT_JSONLINES_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
    KTP_PARTITION_COL,
    KTP_PARTITION_FLAG_SSN_COUNT_COL,
    KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
)

RunEvent = run_event_models.RunEvent
RunLifecycle = run_outcome_models.RunLifecycle

NAMEKEY = NameKey(first_name="Jane", last_name="Doe")
SECOND_NAMEKEY = NameKey(first_name="John", last_name="Doe")
SESSION_ID = UUID("019fb000-0000-7000-8000-000000000001")
SESSION_TIMESTAMP = datetime(2026, 8, 7, tzinfo=timezone.utc)
ROLLOUT_PATH = PurePosixPath(
    "/home/ai/.codex/sessions/2026/08/07/"
    "rollout-2026-08-07T00-00-00-019fb000-0000-7000-8000-000000000001.jsonl"
)


def configured_pipeline_config() -> AiAugmentDetourConfig:
    pipeline_config = Mock(spec=AiAugmentDetourConfig)
    pipeline_config.total_draws = 1
    pipeline_config.timezone = "UTC"
    pipeline_config.registered_resources = (
        SimpleNamespace(verify_hash_on_init=True),
    )
    return pipeline_config


def http_record(
    *,
    method: str,
    path: str,
    response_code: int,
    request_body: str | None = None,
) -> HttpRequestLogRecord:
    return HttpRequestLogRecord(
        schema_version="1.1",
        record_id=uuid7(),
        method=method,
        scheme="http",
        host="testserver",
        port=None,
        ready_to_respond_at_unix_usec=2,
        path=path,
        query="",
        request_headers={},
        request_body=request_body,
        response_code=response_code,
        response_headers={},
        response_body="",
        received_at_unix_usec=1,
        duration_usec=1,
    )


def run_outcome_response(
    *,
    namekey: NameKey = NAMEKEY,
    run_outcome: RunLifecycle = RunLifecycle.COMPLETED,
    response_code: int = status.HTTP_200_OK,
) -> RunOutcomeResponse:
    request = run_outcome_models.RunOutcomeRequest.from_http_request(
        received_at_unix_usec=1,
        method=api.HTTP_POST_METHOD,
        scheme="http",
        host="invalid",
        port=None,
        path=run_outcome.to_run_outcome_path(),
        query="",
        request_headers={
            run_outcome_models.NAME_KEY_HEADER: api._name_key_header(namekey)
        },
        request_body=b"",
    )
    if response_code == status.HTTP_200_OK:
        rollout_filename = f"{api.ROLLOUT_FILENAME_PREFIX}{SESSION_ID}.jsonl"
        report = f".\n└── {api.APPENDWATCH_OK_PREFIX}{rollout_filename}\n".encode()
        response_headers = {
            SOURCE_KEY_HEADER: api._source_key_header(rollout_filename, 1)
        }
        body = RunOutcomeResponseBody(
            pull_record_id=None,
            push_record_id=None,
            codex_session_record=CodexSessionRecord(
                session_id=SESSION_ID,
                codex_rollout_record=CodexRolloutRecord(
                    sha256="0" * 64,
                    size=1,
                    line_count=1,
                ),
                appendwatch_report_record=AppendwatchReportRecord(
                    encoding=AppendwatchReportEncoding.BASE64,
                    data=base64.b64encode(report).decode("ascii"),
                ),
            ),
        )
    else:
        response_headers = None
        body = RunOutcomeResponseBody(
            pull_record_id=None,
            push_record_id=None,
            codex_session_record=CodexSessionRecord(
                session_id=None,
                codex_rollout_record=None,
                appendwatch_report_record=None,
            ),
        )
    return RunOutcomeResponse.from_run_outcome_request(
        request,
        response_code=response_code,
        response_headers=response_headers,
        response_body=body,
        ready_to_respond_at_unix_usec=2,
    )


def agent_runtime_attempt(
    *,
    result: BackendLifecycle = BackendLifecycle.ACCEPTED,
    commit_record_id: UUID | None = None,
    session_id: UUID = SESSION_ID,
) -> AgentRuntimeAttemptRecord:
    pull_record = http_record(
        method=api.HTTP_GET_METHOD,
        path=api.PULL_PATH,
        response_code=status.HTTP_200_OK,
    )
    push_record = http_record(
        method=api.HTTP_POST_METHOD,
        path=api.PUSH_PATH,
        response_code=status.HTTP_202_ACCEPTED,
        request_body="{}",
    )
    codex_session_record = CodexSessionRecord(
        session_id=session_id,
        codex_rollout_record=CodexRolloutRecord(
            sha256="0" * 64,
            size=3,
            line_count=1,
        ),
        appendwatch_report_record=AppendwatchReportRecord(
            encoding=AppendwatchReportEncoding.BASE64,
            data="Lgo=",
        ),
    )
    commit_body = CommitRequestBody(
        pull_record=pull_record,
        push_record=push_record,
        codex_session_record=codex_session_record,
    )
    commit_record = BackendCommitRecord(
        schema_version="1.1",
        record_id=commit_record_id or uuid7(),
        method=api.HTTP_POST_METHOD,
        scheme="http",
        host="invalid",
        port=None,
        ready_to_respond_at_unix_usec=None,
        path="/commit",
        query="",
        request_headers={
            "SourceKey": (
                'ktp.filename="rollout.jsonl", '
                'ktp.fragment;type="line_number";line_number="1"'
            ),
            "NameKey": 'ktp.first_name="Jane", ktp.last_name="Doe"',
        },
        request_body=commit_body.model_dump_json(),
        response_code=None,
        response_headers=None,
        response_body=None,
        received_at_unix_usec=None,
        duration_usec=None,
        commit_request_body=commit_body,
    )
    return AgentRuntimeAttemptRecord(
        attempt=AgentRuntimeAttempt(
            pull_record=pull_record,
            commit_record=commit_record,
            post_commit_validation=PostCommitValidation(
                stage=(
                    BackendLifecycle.ACCEPTED
                    if result is BackendLifecycle.ACCEPTED
                    else BackendLifecycle.PYDANTIC_VALIDATION
                ),
                result=result,
                detail=None if result is BackendLifecycle.ACCEPTED else "failed",
            ),
        ),
        submission=(
            Submission.model_validate(api.EVIDENCE_SUBMISSION_EXAMPLE)
            if result is BackendLifecycle.ACCEPTED
            else None
        ),
        ground_truth_innerdict=None,
    )


@pytest.fixture(autouse=True)
def isolated_general_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.storage, "_general", {})


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def researcher(
    namekey: NameKey = NAMEKEY,
    *,
    cohort: AiAugmentCohort = AiAugmentCohort.NO_GROUND_TRUTH,
    ineligibility_category: AiAugmentIneligibilityCategory | None = None,
) -> AiAugmentSingularOuterDict:
    xlsx_innerdict = InnerDict.from_mapping(
        {
            KTP_NAMEKEY_COL: namekey.to_json_key(),
            KTP_FIRST_NAME_COL: namekey.first_name,
            KTP_LAST_NAME_COL: namekey.last_name,
            DRAW_LABEL: "1",
        },
        XlsxMatchProcedure(),
    )
    docx_innerdicts: tuple[InnerDict, ...] = ()
    if cohort is AiAugmentCohort.GROUND_TRUTH:
        docx_innerdicts = (
            InnerDict.from_mapping(
                {
                    KTP_NAMEKEY_COL: namekey.to_json_key(),
                    KTP_FIRST_NAME_COL: namekey.first_name,
                    KTP_LAST_NAME_COL: namekey.last_name,
                    DRAW_LABEL: "1",
                    **{column: "value" for column in DOCX_COLUMNS},
                },
                DocxMatchProcedure(),
            ),
        )
    return AiAugmentSingularOuterDict(
        namekey=namekey,
        xlsx_innerdicts=(xlsx_innerdict,),
        ssn_innerdicts=(),
        docx_innerdicts=docx_innerdicts,
        ai_augment_rnd=1,
        ai_augment_cohort=cohort,
        ai_augment_ineligibility_category=ineligibility_category,
    )


def cached_source_population_row() -> AiAugmentSingularOuterDict:
    return researcher(cohort=AiAugmentCohort.GROUND_TRUTH)


def queued_run(
    run_id: UUID | None = None,
    *,
    namekey: NameKey = NAMEKEY,
) -> run_event_models.Run:
    return run_event_models.Run(
        run_id=run_id or uuid7(),
        namekey=namekey,
        lifecycle=RunLifecycle.QUEUED,
        queued_at=SESSION_TIMESTAMP,
    )


class FakeBackendDatabase:
    def __init__(
        self,
        order: list[str] | None = None,
        *,
        available: bool = False,
    ) -> None:
        self.order = [] if order is None else order
        self.query_calls = 0
        self.run_outcome_calls: list[
            tuple[RunLifecycle, NameKey]
        ] = []
        self.ipc_available = available
        self.response = QueryResponse(
            attempts=(),
            ai_augment_singular_outerdicts=(researcher(),),
        )

    def send_query_request(self, request: QueryRequest) -> QueryResponse:
        assert isinstance(request, QueryRequest)
        self.query_calls += 1
        return self.response

    def card(self, researcher: AiAugmentSingularOuterDict) -> str:
        return f"card for {researcher.namekey}"

    def available(self) -> bool:
        return self.ipc_available

    def record_run_outcome(
        self,
        *,
        run_outcome: RunLifecycle,
        namekey: NameKey,
    ) -> int:
        self.order.append(
            f"run-outcome:{run_outcome.to_run_outcome_path()}"
        )
        self.run_outcome_calls.append((run_outcome, namekey))
        response = run_outcome_response(
            namekey=namekey,
            run_outcome=run_outcome,
        )
        self.response = self.response.model_copy(
            update={
                "run_outcome_records": (*self.response.run_outcome_records, response)
            }
        )
        assert response.response_code is not None
        return response.response_code


class FakeBackend:
    @asynccontextmanager
    async def query_connection(self, _client: object) -> AsyncIterator[None]:
        yield

    def __init__(
        self,
        order: list[str] | None = None,
        *,
        full_api_available: bool = False,
    ) -> None:
        self.order = [] if order is None else order
        self.started_namekeys: list[NameKey] = []
        self.supplied_session_ids: list[UUID] = []
        self.status = control_ui._BackendStatus.STOPPED
        self.api_available = full_api_available
        self.pull_status = status.HTTP_200_OK

    def full_api_available(self) -> bool:
        return self.api_available

    async def start(self, *, namekey: NameKey) -> None:
        self.order.append("backend-start")
        self.started_namekeys.append(namekey)
        self.status = control_ui._BackendStatus.RUNNING

    async def probe_pull(self) -> int:
        self.order.append("backend-pull")
        return self.pull_status

    async def supply_session_id(self, session_id: UUID) -> None:
        self.order.append("backend-session")
        self.supplied_session_ids.append(session_id)

    async def stop(self) -> None:
        self.order.append("backend-stop")
        self.status = control_ui._BackendStatus.STOPPED


class FakeCodex:
    def __init__(self, order: list[str] | None = None) -> None:
        self.order = [] if order is None else order

    async def probe_ssh(self) -> bool:
        return True

    async def probe_auth(self) -> bool:
        return True

    async def is_busy(self) -> bool:
        return False

    async def start(
        self,
        *,
        run: run_event_models.Run,
        on_handle: Any = None,
    ) -> SimpleNamespace:
        self.order.append("codex-start")
        handle = SimpleNamespace(
            run=run,
            remote_pid=None,
            process=SimpleNamespace(returncode=None),
        )
        if on_handle is not None:
            await on_handle(handle)
        return SimpleNamespace(
            handle=handle,
            session_id=SESSION_ID,
            session_timestamp=SESSION_TIMESTAMP,
            rollout_jsonl=ROLLOUT_PATH,
        )

    async def wait(self, handle: object) -> int:
        self.order.append("codex-wait")
        cast(Any, handle).process.returncode = 0
        return 0

    async def cancel(self, handle: object) -> None:
        self.order.append("codex-cancel")
        cast(Any, handle).process.returncode = -15

    async def terminate_abandoned_run(self, _run: run_event_models.Run) -> None:
        return None


def services(
    *,
    backend: FakeBackend | None = None,
    backend_database: FakeBackendDatabase | None = None,
    codex: FakeCodex | None = None,
    seed: bool = True,
) -> control_ui._ApplicationServices:
    storage = storage_models.AiAugmentDashboardStorage()
    if seed and storage_models.BACKEND_DATABASE_STORAGE_KEY not in app.storage.general:
        storage.replace_query_response(QueryResponse(
            attempts=(), ai_augment_singular_outerdicts=(researcher(),),
        ))
    pipeline = configured_pipeline_config()
    configuration = SimpleNamespace(
        pipeline_config=pipeline, openalex_api_key="test-key",
        lima_configuration=SimpleNamespace(param={api.APPENDWATCH_REPORT_ENV_NAME: "/test/report"}),
    )
    application_services = control_ui._ApplicationServices
    # Exercise production composition/query closure with hermetic transport/process doubles.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(AiAugmentDetourConfig, "from_json", lambda *_a, **_kw: pipeline)
        patch.setattr(control_ui, "AiAugmentControlCentreContext", lambda **_kw: configuration)
        patch.setattr(control_ui, "AiAugmentDashboardStorage", lambda: storage)
        patch.setattr(control_ui, "_BackendSupervisor", lambda **_kw: backend or FakeBackend())
        patch.setattr(control_ui, "_BackendDatabaseClient",
                      lambda **_kw: backend_database or FakeBackendDatabase())
        patch.setattr(control_ui, "_CodexRunner", lambda **_kw: codex or FakeCodex())
        patch.setattr(control_ui, "_ApplicationServices", application_services.model_construct)
        selected = control_ui.create_services(config_path=Path("unused-config.json"))
    selected.controller._load_dashboard_storage()
    return selected


def controller(
    *,
    backend: FakeBackend | None = None,
    backend_database: FakeBackendDatabase | None = None,
    codex: FakeCodex | None = None,
    seed: bool = True,
) -> control_ui._ControlCentreController:
    return services(
        backend=backend, backend_database=backend_database, codex=codex, seed=seed,
    ).controller


def set_researchers(
    subject: control_ui._ControlCentreController,
    researchers: tuple[AiAugmentSingularOuterDict, ...],
) -> None:
    subject._snapshot = subject._storage.replace_query_response(QueryResponse(
        attempts=(), ai_augment_singular_outerdicts=researchers,
    ))


async def run_sync_in_test(function: Any, /, *args: object, **kwargs: object) -> Any:
    return function(*args, **kwargs)


@pytest.fixture
def inline_controller_io(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "to_thread", run_sync_in_test)


def test_researcher_vars_cover_every_ai_augment_column() -> None:
    assert tuple(item.ai_column for item in control_ui.RESEARCHER_VARS) == (AI_AUGMENT_COLUMNS)


@pytest.mark.anyio
@pytest.mark.parametrize("output_format", ("docx", "txt"))
async def test_displayed_card_download_uses_exact_markdown_and_shared_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    output_format: Literal["docx", "txt"],
) -> None:
    class Button:
        enabled = False

        def enable(self) -> None:
            self.enabled = True

        def disable(self) -> None:
            self.enabled = False

    class Markdown:
        content = ""

        def set_content(self, content: str) -> None:
            self.content = content

    button_docx = Button()
    button_txt = Button()
    button = button_docx if output_format == "docx" else button_txt
    markdown = Markdown()
    reference_docx = tmp_path / "reference.docx"
    card = control_ui._ResearcherCardView(
        researcher=researcher(
            NameKey(first_name="Jane", last_name="Doe-Smith")
        ).model_copy(
            update={
                "xlsx_innerdicts": (
                    InnerDict.from_mapping(
                        {
                            KTP_NAMEKEY_COL: NameKey(
                                first_name="Jane",
                                last_name="Doe-Smith",
                            ).to_json_key(),
                            KTP_FIRST_NAME_COL: "Jane",
                            KTP_LAST_NAME_COL: "Doe-Smith",
                            DRAW_LABEL: "1, pilot.2",
                        },
                        XlsxMatchProcedure(),
                    ),
                )
            }
        ),
        card_markdown="## Exact displayed card\n\n**Café — 研究**\n",
    )
    subject = control_ui._ControlCentrePage(
        controller=cast(control_ui._ControlCentreController, object()),
        query_ipc=AsyncMock(),
        reference_docx=reference_docx,
    )
    subject._handles.download_card_button_docx = button_docx
    subject._handles.download_card_button_txt = button_txt
    subject._handles.card_markdown = markdown
    rendered: list[tuple[str, Path]] = []
    downloads: list[tuple[bytes, str | None, str]] = []

    def render(markdown_value: str, supplied_reference: Path) -> bytes:
        assert not button.enabled
        rendered.append((markdown_value, supplied_reference))
        return b"PK\x03\x04docx"

    def download(
        source: bytes,
        filename: str | None = None,
        media_type: str = "",
    ) -> None:
        assert not button.enabled
        downloads.append((source, filename, media_type))

    async def in_event_loop(
        function: Any,
        *args: object,
        **kwargs: object,
    ) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(control_ui, "render_docx_bytes", render)
    monkeypatch.setattr(ui, "download", download)
    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)

    await subject._show_card(card)
    assert markdown.content == card.card_markdown
    assert button_docx.enabled and button_txt.enabled

    await subject.download_displayed_card(output_format=output_format)

    if output_format == "docx":
        assert rendered == [(card.card_markdown, reference_docx)]
        expected_bytes = b"PK\x03\x04docx"
        expected_media_type = control_ui.DOCX_MEDIA_TYPE
    else:
        assert rendered == []
        expected_bytes = "## Exact displayed card\n\n**Café — 研究**\n".encode("utf-8")
        expected_media_type = "text/plain; charset=utf-8"
    filename = f"1_pilot2_Jane_DoeSmith.{output_format}"
    assert downloads == [(expected_bytes, filename, expected_media_type)]
    assert button_docx.enabled and button_txt.enabled
    output = capsys.readouterr().out
    assert f"Rendering {output_format.upper()} download: {filename}" in output
    assert (
        f"{output_format.upper()} sent to browser: {filename}; {len(expected_bytes)} bytes"
        in output
    )

    subject._clear_displayed_card()
    assert markdown.content == ""
    assert not button_docx.enabled and not button_txt.enabled
    await subject.download_displayed_card(output_format=output_format)
    assert len(downloads) == 1
    assert f"{output_format.upper()} download skipped:" in capsys.readouterr().out


def test_dashboard_paths_resolve_from_repository_root(
    pytestconfig: pytest.Config,
) -> None:
    repository_root = pytestconfig.rootpath
    assert control_vars.REPOSITORY_ROOT == repository_root
    assert control_vars.REPOSITORY_ROOT == repository_root
    assert control_vars.DEFAULT_CONFIG_PATH == repository_root / "config_ai_augment.json"


def test_dashboard_context_has_no_backend_factory() -> None:
    assert not issubclass(context_models.AiAugmentControlCentreContext,
                         backend_context_models.AiAugmentBackendContext)
    assert not hasattr(context_models.AiAugmentControlCentreContext,
                       "ai_augment_singular_outerdicts_factory")


@pytest.mark.anyio
async def test_dashboard_start_empty_and_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    database = FakeBackendDatabase()
    subject = controller(seed=False, backend_database=database)

    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("startup/repaint must not load source data or probe")
    monkeypatch.setattr(duckdb, "connect", unexpected)
    monkeypatch.setattr(subject._backend, "full_api_available", unexpected)
    monkeypatch.setattr(subject, "_probe_ipc", unexpected)
    assert not hasattr(subject, "_backend_database")
    monkeypatch.setattr(subject._codex, "is_busy", unexpected)
    await subject.start()
    try:
        snapshot = await subject.snapshot(selection=control_ui._UiSelection(
            researcher_varname=control_ui.RESEARCHER_VARS[0].varname,
        ))
        assert snapshot.researcher_var_views == ()
        assert snapshot.counts.total == 0
        assert app.storage.general == {}
        assert database.query_calls == 0
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_application_startup_publishes_services_only_after_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject = controller()
    services = cast(control_ui._ApplicationServices, SimpleNamespace(controller=subject))

    async def start(*, publishing: bool = False) -> None:
        assert not publishing
        assert control_ui.SERVICES is None
    monkeypatch.setattr(subject, "start", start)
    monkeypatch.setattr(control_ui, "SERVICES", None)
    monkeypatch.setattr(control_ui, "create_services", lambda **kwargs: services)
    await control_ui.application_startup()
    assert control_ui.SERVICES is services


@pytest.mark.anyio
async def test_application_startup_does_not_publish_failed_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject = controller()

    async def start(*, publishing: bool = False) -> None:
        raise RuntimeError("failed storage")
    monkeypatch.setattr(subject, "start", start)
    monkeypatch.setattr(control_ui, "SERVICES", None)
    monkeypatch.setattr(
        control_ui, "create_services", lambda **kwargs: SimpleNamespace(controller=subject),
    )
    shutdown = Mock()
    monkeypatch.setattr(app, "shutdown", shutdown)
    monkeypatch.setattr(control_ui, "APPLICATION_EXIT_CODE", 0)
    await control_ui.application_startup()
    assert control_ui.SERVICES is None
    assert control_ui.APPLICATION_EXIT_CODE == 1
    shutdown.assert_called_once_with()


@pytest.mark.anyio
@pytest.mark.parametrize(
    (
        "full_api_available",
        "ipc_available",
        "expected_status",
    ),
    (
        (True, True, control_ui._BackendStatus.RUNNING_EXTERNALLY),
        (True, False, control_ui._BackendStatus.RUNNING_EXTERNALLY),
        (False, True, control_ui._BackendStatus.STOPPED),
        (False, False, control_ui._BackendStatus.STOPPED),
    ),
)
async def test_explicit_probe_detects_backend_availability_without_querying_history(
    monkeypatch: pytest.MonkeyPatch,
    full_api_available: bool,
    ipc_available: bool,
    expected_status: control_ui._BackendStatus,
) -> None:
    async def in_event_loop(function: Any, /, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)
    backend = FakeBackend(full_api_available=full_api_available)
    backend_database = FakeBackendDatabase(available=ipc_available)
    subject = controller(backend=backend, backend_database=backend_database)

    await subject.start()
    try:
        assert subject.backend_availability == control_ui._BackendAvailability()
        await subject.probe_all()
        assert subject.backend_status is expected_status
        assert subject.backend_availability.full_api_available is full_api_available
        assert subject.backend_availability.ipc_available is ipc_available
        assert subject.backend_availability.checked_at is not None
        assert backend_database.query_calls == 0
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_backend_availability_redetection_observes_later_ipc_without_querying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def in_event_loop(function: Any, /, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)
    backend = FakeBackend()
    backend_database = FakeBackendDatabase()
    subject = controller(backend=backend, backend_database=backend_database)

    await subject.start()
    try:
        assert subject.backend_availability == control_ui._BackendAvailability()

        backend.api_available = True
        backend_database.ipc_available = True
        await subject.probe_all()
        availability = subject.backend_availability

        assert availability.full_api_available is True
        assert availability.ipc_available is True
        assert subject.backend_status is control_ui._BackendStatus.RUNNING_EXTERNALLY
        assert backend_database.query_calls == 0
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_page_shows_backend_and_ipc_without_gating_explicit_query() -> None:
    class Label:
        text = ""

        def set_text(self, value: str) -> None:
            self.text = value

    class Button:
        enabled = True

        def enable(self) -> None:
            self.enabled = True

        def disable(self) -> None:
            self.enabled = False

    class Controller:
        backend_availability = control_ui._BackendAvailability(
            full_api_available=True,
            ipc_available=False,
        )

        async def snapshot(
            self,
            *,
            selection: control_ui._UiSelection,
        ) -> control_ui._DashboardView:
            del selection
            return control_ui._DashboardView(
                counts=control_ui._DashboardCounts(
                    total=0,
                    ground_truth=0,
                    no_ground_truth=0,
                    ineligible=0,
                    ready=0,
                    queued=0,
                    running=0,
                    completed=0,
                    failed=0,
                    cancelled=0,
                ),
                researcher_var_views=(),
                backend_status=(
                    control_ui._BackendStatus.RUNNING_EXTERNALLY
                    if self.backend_availability.full_api_available
                    else control_ui._BackendStatus.STOPPED
                ),
                backend_availability=self.backend_availability,
                active_run_id=None,
            )

        @staticmethod
        def drain_notifications() -> tuple[str, ...]:
            return ()

    controller = Controller()
    backend_label = Label()
    ipc_label = Label()
    refresh_button = Button()
    subject = control_ui._ControlCentrePage(
        controller=cast(control_ui._ControlCentreController, controller),
        query_ipc=AsyncMock(),
        reference_docx=Path("unused.docx"),
    )
    subject._handles.backend_status_label = backend_label
    subject._handles.backend_ipc_status_label = ipc_label
    subject._handles.backend_refresh_button = refresh_button

    await subject.refresh()

    assert backend_label.text == "Backend API: available"
    assert ipc_label.text == "IPC: unavailable"
    assert refresh_button.enabled is True

    controller.backend_availability = control_ui._BackendAvailability(
        full_api_available=False,
        ipc_available=True,
    )
    await subject.refresh()

    assert backend_label.text == "Backend API: unavailable"
    assert ipc_label.text == "IPC: available"
    assert refresh_button.enabled is True


@pytest.mark.anyio
async def test_dashboard_refresh_explicitly_hydrates_attempts_from_ipc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def in_event_loop(function: Any, /, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)
    backend_database = FakeBackendDatabase(available=True)
    attempt = agent_runtime_attempt(result=BackendLifecycle.REJECTED)
    backend_database.response = QueryResponse(
        attempts=(attempt,),
        ai_augment_singular_outerdicts=(researcher(),),
    )
    application = services(backend_database=backend_database)
    subject = application.controller

    await subject.start()
    try:
        assert subject.backend_status is control_ui._BackendStatus.STOPPED
        assert subject.backend_availability == control_ui._BackendAvailability()
        assert backend_database.query_calls == 0

        await application.query_ipc()

        assert backend_database.query_calls == 1
        assert subject._snapshot.attempts_by_namekey == {NAMEKEY.to_json_key(): (attempt,)}
        assert app.storage.general[storage_models.BACKEND_DATABASE_STORAGE_KEY] == (
            backend_database.response.model_dump(mode="json")
        )
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_dashboard_refresh_preserves_availability_when_ipc_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def in_event_loop(function: Any, /, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    class FailingBackendDatabase(FakeBackendDatabase):
        def send_query_request(self, request: QueryRequest) -> QueryResponse:
            raise OSError("IPC query failed")

    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)
    application = services(
        backend=FakeBackend(full_api_available=True),
        backend_database=FailingBackendDatabase(available=True),
    )
    subject = application.controller

    await subject.start()
    try:
        assert subject.backend_availability == control_ui._BackendAvailability()

        with pytest.raises(RuntimeError, match=Locale.BACKEND_DATABASE_RESPONSE_INVALID):
            await application.query_ipc()

        assert subject.backend_availability == control_ui._BackendAvailability()
        assert subject.backend_status is control_ui._BackendStatus.STOPPED
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_dashboard_start_restores_refreshed_backend_data_without_querying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def in_event_loop(function: Any, /, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)
    attempt = agent_runtime_attempt(result=BackendLifecycle.REJECTED)
    app.storage.general[storage_models.BACKEND_DATABASE_STORAGE_KEY] = QueryResponse(
        attempts=(attempt,),
        ai_augment_singular_outerdicts=(researcher(),),
    ).model_dump(mode="json")
    backend_database = FakeBackendDatabase()
    subject = controller(backend_database=backend_database)

    await subject.start()
    try:
        assert backend_database.query_calls == 0
        assert subject._snapshot.attempts_by_namekey == {NAMEKEY.to_json_key(): (attempt,)}
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_failed_run_events_are_logged(
    capsys: pytest.CaptureFixture[str],
) -> None:
    subject = controller()
    run_id = uuid7()
    await subject._append_run_event(
        RunEvent(
            run_id=run_id,
            namekey=NAMEKEY,
            occurred_at_unix_usec=control_ui.datetime_to_unix_usec(SESSION_TIMESTAMP),
            lifecycle=RunLifecycle.QUEUED,
        )
    )
    capsys.readouterr()
    event = RunEvent(
        run_id=run_id,
        namekey=NAMEKEY,
        occurred_at_unix_usec=control_ui.datetime_to_unix_usec(SESSION_TIMESTAMP),
        lifecycle=RunLifecycle.FAILED,
        detail=Locale.BACKEND_EXITED_EARLY,
    )

    await subject._append_run_event(event)

    assert capsys.readouterr().out == (
        f"{Locale.CONTROL_CENTRE_LOG_PREFIX} run failed: "
        f"run_id={event.run_id} namekey={NAMEKEY} "
        f"detail={Locale.BACKEND_EXITED_EARLY}\n"
    )


def test_backend_database_client_queries_unix_socket_without_authentication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, float, str, str]] = []
    response_body = (
        QueryResponse(
            attempts=(),
            ai_augment_singular_outerdicts=(),
        )
        .model_dump_json()
        .encode()
    )

    class FakeResponse:
        status = status.HTTP_200_OK

        @staticmethod
        def read() -> bytes:
            return response_body

    class FakeConnection:
        def __init__(self, *, socket_path: Path, timeout: float) -> None:
            self.socket_path = socket_path
            self.timeout = timeout

        def request(self, method: str, target: str) -> None:
            calls.append((self.socket_path, self.timeout, method, target))

        @staticmethod
        def getresponse() -> FakeResponse:
            return FakeResponse()

        @staticmethod
        def close() -> None:
            return None

    monkeypatch.setattr(control_ui, "_UnixSocketHttpConnection", FakeConnection)
    socket_path = tmp_path / "dashboard.sock"
    client = control_ui._BackendDatabaseClient(
        socket_path=socket_path,
        pipeline_config=configured_pipeline_config(),
    )

    assert client.available() is True
    response = client.send_query_request(QueryRequest())

    assert response == QueryResponse(
        attempts=(),
        ai_augment_singular_outerdicts=(),
    )
    assert calls == [
        (
            socket_path,
            control_vars.BACKEND_AVAILABILITY_TIMEOUT_SECONDS,
            control_ui.HTTP_OPTIONS_METHOD,
            ipc.DASHBOARD_QUERY_PATH,
        ),
        (
            socket_path,
            control_vars.CONTROL_HTTP_TIMEOUT_SECONDS,
            api.HTTP_GET_METHOD,
            ipc.DASHBOARD_QUERY_PATH,
        ),
    ]


@pytest.mark.parametrize(
    ("response_code", "expected_saved"),
    (
        (status.HTTP_200_OK, True),
        (status.HTTP_500_INTERNAL_SERVER_ERROR, False),
    ),
)
def test_backend_database_client_posts_exact_run_outcome_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response_code: int,
    expected_saved: bool,
) -> None:
    calls: list[tuple[str, str, dict[str, str]]] = []
    namekey = NameKey(first_name="Jane", last_name="Doe")
    session_id = UUID(str(SESSION_ID))
    rollout_filename = f"{api.ROLLOUT_FILENAME_PREFIX}{session_id}.jsonl"
    report = f".\n└── {api.APPENDWATCH_OK_PREFIX}{rollout_filename}\n".encode()
    snapshot = RunOutcomeResponseBody(
        pull_record_id=None,
        push_record_id=None,
        codex_session_record=CodexSessionRecord(
            session_id=session_id,
            codex_rollout_record=CodexRolloutRecord(
                sha256="0" * 64,
                size=1,
                line_count=1,
            ),
            appendwatch_report_record=AppendwatchReportRecord(
                encoding=AppendwatchReportEncoding.BASE64,
                data=base64.b64encode(report).decode("ascii"),
            ),
        ),
    )
    source_key = api._source_key_header(rollout_filename, 1)

    class FakeResponse:
        status = response_code

        @staticmethod
        def read() -> bytes:
            return snapshot.model_dump_json().encode()

        @staticmethod
        def getheader(name: str) -> str | None:
            return source_key if name == SOURCE_KEY_HEADER else None

        @staticmethod
        def getheaders() -> list[tuple[str, str]]:
            return [(SOURCE_KEY_HEADER, source_key)]

    class FakeConnection:
        def __init__(self, *, socket_path: Path, timeout: float) -> None:
            assert socket_path == tmp_path / "dashboard.sock"
            assert timeout == control_vars.CONTROL_HTTP_TIMEOUT_SECONDS

        def request(
            self,
            method: str,
            target: str,
            *,
            headers: dict[str, str],
        ) -> None:
            calls.append((method, target, headers))

        @staticmethod
        def getresponse() -> FakeResponse:
            return FakeResponse()

        @staticmethod
        def close() -> None:
            return None

    monkeypatch.setattr(control_ui, "_UnixSocketHttpConnection", FakeConnection)
    client = control_ui._BackendDatabaseClient(
        socket_path=tmp_path / "dashboard.sock",
        pipeline_config=configured_pipeline_config(),
    )

    response_code = client.record_run_outcome(
        run_outcome=RunLifecycle.COMPLETED,
        namekey=namekey,
    )

    assert calls == [
        (
            api.HTTP_POST_METHOD,
            run_outcome_models.COMPLETED_PATH,
            {
                run_outcome_models.NAME_KEY_HEADER: api._name_key_header(namekey)
            },
        )
    ]
    assert (response_code == status.HTTP_200_OK) is expected_saved


def test_run_outcome_snapshot_decodes_appendwatch_for_display_only() -> None:
    response = run_outcome_response(
        namekey=NAMEKEY,
        run_outcome=RunLifecycle.COMPLETED,
    )
    attempt = control_ui._RunCommitView(
        attempt_record=None,
        run=run_event_models.Run(
            run_id=uuid7(),
            namekey=NAMEKEY,
            lifecycle=RunLifecycle.COMPLETED,
            run_outcome=RunLifecycle.COMPLETED,
            queued_at=SESSION_TIMESTAMP,
            session_id=SESSION_ID,
        ),
        accepted=None,
        run_outcome_response=response,
    )

    assert attempt.run_outcome_response is response
    assert attempt.run_outcome_saved is True
    assert (
        response.run_outcome_response_body.codex_session_record.session_id
        == SESSION_ID
    )
    assert attempt.run_outcome_session_status == Locale.SESSION_STATUS_OK


@pytest.mark.anyio
async def test_run_outcome_snapshot_500_is_kept_separate_from_run_outcome(
    inline_controller_io: None,
) -> None:
    class PartialBackendDatabase(FakeBackendDatabase):
        def record_run_outcome(
            self,
            *,
            run_outcome: RunLifecycle,
            namekey: NameKey,
        ) -> int:
            self.run_outcome_calls.append((run_outcome, namekey))
            response = run_outcome_response(
                namekey=namekey,
                run_outcome=run_outcome,
                response_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
            self.response = self.response.model_copy(
                update={
                    "run_outcome_records": (
                        *self.response.run_outcome_records,
                        response,
                    )
                }
            )
            return status.HTTP_500_INTERNAL_SERVER_ERROR

    backend = FakeBackend()
    backend.status = control_ui._BackendStatus.RUNNING
    backend_database = PartialBackendDatabase()
    application = services(backend=backend, backend_database=backend_database)
    subject = application.controller
    run_id = uuid7()
    await subject._append_run_event(
        RunEvent(
            run_id=run_id,
            namekey=NAMEKEY,
            occurred_at_unix_usec=control_ui.datetime_to_unix_usec(SESSION_TIMESTAMP),
            lifecycle=RunLifecycle.QUEUED,
        )
    )

    await subject._record_run_outcome(
        run=subject._runs[run_id],
        run_outcome=RunLifecycle.FAILED,
    )

    assert subject._runs[run_id].lifecycle is RunLifecycle.QUEUED
    assert backend_database.run_outcome_calls == [
        (RunLifecycle.FAILED, NAMEKEY)
    ]
    assert backend_database.query_calls == 0
    assert not subject._snapshot.query_response.run_outcome_records
    await application.query_ipc()
    response = subject._snapshot.query_response.run_outcome_records[-1]
    assert response.run_outcome is RunLifecycle.FAILED
    assert response.response_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    await subject._append_run_event(
        RunEvent(
            run_id=run_id,
            namekey=NAMEKEY,
            occurred_at_unix_usec=control_ui.datetime_to_unix_usec(SESSION_TIMESTAMP),
            lifecycle=RunLifecycle.FAILED,
        )
    )
    subject._runs[run_id].session_id = SESSION_ID
    reconciled = control_ui._ResearcherView.from_snapshot(
        researcher(), subject._snapshot, tuple(subject._runs.values()),
    )
    assert reconciled.latest_run_commit_view is not None
    assert reconciled.latest_run_commit_view.lifecycle is RunLifecycle.FAILED
    # A partial capture without a session UUID cannot be assigned to this local run.
    assert response.run_outcome_response_body.codex_session_record.session_id is None
    assert reconciled.latest_run_commit_view.run_outcome_response is None
    assert reconciled.latest_run_commit_view.run_outcome_saved is None
    assert subject.drain_notifications() == (
        Locale.RUN_OUTCOME_SNAPSHOT_PARTIAL_TEMPLATE.format(
            run_id=run_id,
            outcome=RunLifecycle.FAILED.value,
        ),
    )


def test_backend_api_availability_uses_short_fail_fast_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_timeouts: list[float] = []

    class FakeResponse:
        status = status.HTTP_200_OK

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def urlopen(_request: object, *, timeout: float) -> FakeResponse:
        observed_timeouts.append(timeout)
        return FakeResponse()

    monkeypatch.setattr(urllib_request, "urlopen", urlopen)
    subject = control_ui._BackendSupervisor(
        repository_root=tmp_path,
        config_path=tmp_path / "config.json",
        openalex_api_key="key",
        appendwatch_report=PurePosixPath("/mounted/appendwatch.txt"),
        dashboard_socket_path=tmp_path / "dashboard.sock",
        configuration=context_models.AiAugmentControlCentreContext.model_construct(
            pipeline_config=configured_pipeline_config(),
        ),
    )

    assert subject.full_api_available() is True
    assert observed_timeouts == [control_vars.BACKEND_AVAILABILITY_TIMEOUT_SECONDS]
    assert 0 < control_vars.BACKEND_AVAILABILITY_TIMEOUT_SECONDS <= 1


def test_run_event_replay_keeps_dashboard_queue_ownership() -> None:
    run_id = uuid7()
    queued = RunEvent(
        run_id=run_id,
        namekey=NAMEKEY,
        occurred_at_unix_usec=control_ui.datetime_to_unix_usec(SESSION_TIMESTAMP),
        lifecycle=RunLifecycle.QUEUED,
    )
    started = RunEvent(
        run_id=run_id,
        namekey=NAMEKEY,
        occurred_at_unix_usec=control_ui.datetime_to_unix_usec(SESSION_TIMESTAMP),
        lifecycle=RunLifecycle.STARTED,
    )

    run = control_ui.replay_run_events((queued, started))[run_id]

    assert run.dashboard_owned is True
    assert run.is_running()
    assert run.run_outcome is None
    assert run.events == (queued, started)
    assert run.started_at == SESSION_TIMESTAMP


@pytest.mark.anyio
async def test_queue_is_persisted_only_in_nicegui_general_storage() -> None:
    backend_database = FakeBackendDatabase()
    subject = controller(backend_database=backend_database)
    source = researcher()
    set_researchers(subject, (source,))

    run_id = await subject.queue(namekey=source.namekey)

    assert run_id.version == 7
    assert app.storage.general[storage_models.QUEUE_STORAGE_KEY] == [str(run_id)]
    stored_events = app.storage.general[storage_models.RUN_EVENTS_STORAGE_KEY]
    assert [event["lifecycle"] for event in stored_events] == [
        RunLifecycle.QUEUED.value
    ]
    assert backend_database.query_calls == 0


@pytest.mark.anyio
async def test_queued_cancellation_removes_persisted_queue_without_starting_processes() -> None:
    backend = FakeBackend()
    codex = FakeCodex()
    subject = controller(backend=backend, codex=codex)
    source = researcher()
    set_researchers(subject, (source,))
    run_id = await subject.queue(namekey=source.namekey)

    await subject.cancel(run_id=run_id)

    assert app.storage.general[storage_models.QUEUE_STORAGE_KEY] == []
    assert subject._runs[run_id].is_finished()
    assert subject._runs[run_id].run_outcome is RunLifecycle.CANCELLED
    assert backend.started_namekeys == []
    assert codex.order == []


def test_dashboard_queue_and_journal_survive_controller_reconstruction() -> None:
    run_id = uuid7()
    event = RunEvent(
        run_id=run_id,
        namekey=NAMEKEY,
        occurred_at_unix_usec=control_ui.datetime_to_unix_usec(SESSION_TIMESTAMP),
        lifecycle=RunLifecycle.QUEUED,
    )
    app.storage.general[storage_models.RUN_EVENTS_STORAGE_KEY] = [event.model_dump(mode="json")]
    app.storage.general[storage_models.QUEUE_STORAGE_KEY] = [str(run_id)]
    subject = controller()

    subject._load_dashboard_storage()

    assert subject._runs[run_id].lifecycle is RunLifecycle.QUEUED
    assert subject._runs[run_id].run_outcome is None
    assert app.storage.general[storage_models.QUEUE_STORAGE_KEY] == [str(run_id)]


@pytest.mark.anyio
async def test_execution_starts_fresh_backend_before_codex_and_hands_off_session(
    inline_controller_io: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    backend = FakeBackend(order)
    codex = FakeCodex(order)
    backend_database = FakeBackendDatabase(order)
    subject = controller(
        backend=backend,
        backend_database=backend_database,
        codex=codex,
    )
    run_id = uuid7()
    await subject._append_run_event(
        RunEvent(
            run_id=run_id,
            namekey=NAMEKEY,
            occurred_at_unix_usec=control_ui.datetime_to_unix_usec(SESSION_TIMESTAMP),
            lifecycle=RunLifecycle.QUEUED,
        )
    )
    run = subject._runs[run_id]
    subject._active_run = run

    async def complete_run(
        _subject: control_ui._ControlCentreController,
        *,
        run: run_event_models.Run,
    ) -> RunLifecycle:
        assert run.run_id == run_id
        return RunLifecycle.COMPLETED

    monkeypatch.setattr(control_ui._ControlCentreController, "_finalize_run", complete_run)

    await subject._execute_run(run=run)

    assert order == [
        "backend-start",
        "codex-start",
        "backend-session",
        "codex-wait",
        f"run-outcome:{run_outcome_models.COMPLETED_PATH}",
    ]
    assert backend_database.run_outcome_calls == [
        (RunLifecycle.COMPLETED, NAMEKEY)
    ]
    assert backend.started_namekeys == [NAMEKEY]
    assert backend.supplied_session_ids == [SESSION_ID]
    assert [event.lifecycle for event in subject._events].count(
        RunLifecycle.SESSION_DISCOVERED
    ) == 1
    assert [event.lifecycle for event in subject._events][-2:] == [
        RunLifecycle.CODEX_EXITED,
        RunLifecycle.COMPLETED,
    ]
    assert subject._runs[run_id].codex_exit_code == 0
    assert subject._runs[run_id].is_finished()
    assert subject._runs[run_id].run_outcome is RunLifecycle.COMPLETED


@pytest.mark.anyio
async def test_worker_stops_backend_before_starting_next_queued_run(
    inline_controller_io: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    backend = FakeBackend(order)
    codex = FakeCodex(order)
    subject = controller(
        backend=backend,
        backend_database=FakeBackendDatabase(order),
        codex=codex,
    )
    first = researcher()
    second = researcher(SECOND_NAMEKEY)
    set_researchers(subject, (first, second))

    async def complete_run(
        _subject: control_ui._ControlCentreController,
        *,
        run: run_event_models.Run,
    ) -> RunLifecycle:
        assert run.run_id in subject._runs
        return RunLifecycle.COMPLETED

    monkeypatch.setattr(control_ui._ControlCentreController, "_finalize_run", complete_run)
    first_run_id = await subject.queue(namekey=first.namekey)
    second_run_id = await subject.queue(namekey=second.namekey)

    first_run = await subject._queue.get()
    assert first_run.run_id == first_run_id
    await subject._process_queued_run(first_run)
    second_run = await subject._queue.get()
    assert second_run.run_id == second_run_id
    await subject._process_queued_run(second_run)

    assert backend.started_namekeys == [first.namekey, second.namekey]
    assert order == [
        "backend-start",
        "codex-start",
        "backend-session",
        "codex-wait",
        f"run-outcome:{run_outcome_models.COMPLETED_PATH}",
        "backend-stop",
        "backend-start",
        "codex-start",
        "backend-session",
        "codex-wait",
        f"run-outcome:{run_outcome_models.COMPLETED_PATH}",
        "backend-stop",
    ]


@pytest.mark.anyio
async def test_backend_start_failure_still_winds_down_owned_processes() -> None:
    order: list[str] = []

    class FailingBackend(FakeBackend):
        async def start(self, *, namekey: NameKey) -> None:
            self.order.append("backend-start")
            self.started_namekeys.append(namekey)
            raise RuntimeError("backend start failed")

    backend = FailingBackend(order)
    subject = controller(backend=backend, codex=FakeCodex(order))
    source = researcher()
    set_researchers(subject, (source,))
    run_id = await subject.queue(namekey=source.namekey)

    run = await subject._queue.get()
    assert run.run_id == run_id
    await subject._process_queued_run(run)

    assert subject._runs[run_id].is_finished()
    assert subject._runs[run_id].run_outcome is RunLifecycle.FAILED
    assert order == ["backend-start", "backend-stop"]


@pytest.mark.anyio
async def test_codex_start_failure_stops_registered_codex_then_backend(
    inline_controller_io: None,
) -> None:
    order: list[str] = []

    class FailingCodex(FakeCodex):
        async def start(
            self,
            *,
            run: run_event_models.Run,
            on_handle: Any = None,
        ) -> SimpleNamespace:
            self.order.append("codex-start")
            handle = SimpleNamespace(
                run=run,
                remote_pid=None,
                process=SimpleNamespace(returncode=None),
            )
            assert on_handle is not None
            await on_handle(handle)
            raise RuntimeError("Codex start failed")

    backend = FakeBackend(order)
    subject = controller(
        backend=backend,
        backend_database=FakeBackendDatabase(order),
        codex=FailingCodex(order),
    )
    source = researcher()
    set_researchers(subject, (source,))
    run_id = await subject.queue(namekey=source.namekey)

    run = await subject._queue.get()
    assert run.run_id == run_id
    await subject._process_queued_run(run)

    assert subject._runs[run_id].is_finished()
    assert subject._runs[run_id].run_outcome is RunLifecycle.FAILED
    assert order == [
        "backend-start",
        "codex-start",
        f"run-outcome:{run_outcome_models.FAILED_PATH}",
        "codex-cancel",
        "backend-stop",
    ]


@pytest.mark.anyio
async def test_failed_finalization_stops_backend_after_run_outcome_event(
    inline_controller_io: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    backend = FakeBackend(order)
    subject = controller(
        backend=backend,
        backend_database=FakeBackendDatabase(order),
        codex=FakeCodex(order),
    )
    source = researcher()
    set_researchers(subject, (source,))

    async def fail_run(
        _subject: control_ui._ControlCentreController,
        *,
        run: run_event_models.Run,
    ) -> RunLifecycle:
        assert run.run_id in subject._runs
        assert backend.status is control_ui._BackendStatus.RUNNING
        return RunLifecycle.FAILED

    monkeypatch.setattr(control_ui._ControlCentreController, "_finalize_run", fail_run)
    run_id = await subject.queue(namekey=source.namekey)

    run = await subject._queue.get()
    assert run.run_id == run_id
    await subject._process_queued_run(run)

    assert subject._runs[run_id].is_finished()
    assert subject._runs[run_id].run_outcome is RunLifecycle.FAILED
    assert [event.lifecycle for event in subject._events][-2:] == [
        RunLifecycle.CODEX_EXITED,
        RunLifecycle.FAILED,
    ]
    assert order[-2:] == [
        f"run-outcome:{run_outcome_models.FAILED_PATH}",
        "backend-stop",
    ]


@pytest.mark.anyio
async def test_active_cancellation_stops_codex_then_backend(
    inline_controller_io: None,
) -> None:
    order: list[str] = []
    codex_waiting = asyncio.Event()
    codex_stopped = asyncio.Event()
    backend_stopped = asyncio.Event()

    class BlockingCodex(FakeCodex):
        async def wait(self, handle: object) -> int:
            self.order.append("codex-wait")
            codex_waiting.set()
            await codex_stopped.wait()
            return cast(int, cast(Any, handle).process.returncode)

        async def cancel(self, handle: object) -> None:
            await super().cancel(handle)
            codex_stopped.set()

    class ObservedBackend(FakeBackend):
        async def stop(self) -> None:
            await super().stop()
            backend_stopped.set()

    backend = ObservedBackend(order)
    subject = controller(
        backend=backend,
        backend_database=FakeBackendDatabase(order),
        codex=BlockingCodex(order),
    )
    source = researcher()
    set_researchers(subject, (source,))
    run_id = await subject.queue(namekey=source.namekey)
    run = await subject._queue.get()
    assert run.run_id == run_id
    execution = asyncio.create_task(subject._process_queued_run(run))

    await asyncio.wait_for(codex_waiting.wait(), timeout=1)
    await subject.cancel(run_id=run_id)
    await asyncio.wait_for(execution, timeout=1)

    assert backend_stopped.is_set()
    assert subject._runs[run_id].is_finished()
    assert subject._runs[run_id].run_outcome is RunLifecycle.CANCELLED
    assert order[-3:] == [
        f"run-outcome:{run_outcome_models.CANCELLED_PATH}",
        "codex-cancel",
        "backend-stop",
    ]


@pytest.mark.anyio
async def test_cancellation_waits_for_codex_handle_before_run_outcome_snapshot() -> None:
    order: list[str] = []
    backend = FakeBackend(order)
    backend.status = control_ui._BackendStatus.RUNNING
    backend_database = FakeBackendDatabase(order)
    subject = controller(
        backend=backend,
        backend_database=backend_database,
        codex=FakeCodex(order),
    )
    run_id = uuid7()
    await subject._append_run_event(
        RunEvent(
            run_id=run_id,
            namekey=NAMEKEY,
            occurred_at_unix_usec=control_ui.datetime_to_unix_usec(SESSION_TIMESTAMP),
            lifecycle=RunLifecycle.QUEUED,
        )
    )
    subject._active_run = subject._runs[run_id]

    await subject.cancel(run_id=run_id)

    assert subject._runs[run_id].cancel_requested_at is not None
    assert backend_database.run_outcome_calls == []
    assert order == []


@pytest.mark.anyio
async def test_dashboard_shutdown_stops_inflight_codex_and_backend(
    inline_controller_io: None,
) -> None:
    order: list[str] = []
    codex_waiting = asyncio.Event()

    class BlockingCodex(FakeCodex):
        async def wait(self, _handle: object) -> int:
            self.order.append("codex-wait")
            codex_waiting.set()
            await asyncio.Event().wait()
            return 0

    backend = FakeBackend(order)
    subject = controller(
        backend=backend,
        backend_database=FakeBackendDatabase(order),
        codex=BlockingCodex(order),
    )
    source = researcher()
    set_researchers(subject, (source,))
    run_id = await subject.queue(namekey=source.namekey)
    subject.set_queue_processing(True)
    subject._worker_task = asyncio.create_task(subject._worker())

    await asyncio.wait_for(codex_waiting.wait(), timeout=1)
    await subject.shutdown()

    assert subject._runs[run_id].is_finished()
    assert subject._runs[run_id].run_outcome is RunLifecycle.FAILED
    assert order.index(f"run-outcome:{run_outcome_models.FAILED_PATH}") < order.index(
        "codex-cancel"
    )
    assert order.index("codex-cancel") < order.index("backend-stop")
    assert order[-1] == "backend-stop"
    assert backend.status is control_ui._BackendStatus.STOPPED


@pytest.mark.anyio
@pytest.mark.parametrize("pull_status, expected_outcome", [
    (410, RunLifecycle.COMPLETED), (503, RunLifecycle.FAILED),
])
async def test_backend_acceptance_remains_running_until_codex_exits(
    pull_status: int, expected_outcome: RunLifecycle,
    inline_controller_io: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid7()
    accepted_commit_record_id = uuid7()
    accepted_value = "Professor Sir Aziz Sheikh OBE"
    researcher_var = control_ui.RESEARCHER_VARS[0]
    codex_waiting = asyncio.Event()
    allow_codex_exit = asyncio.Event()

    class BlockingCodex(FakeCodex):
        async def wait(self, _handle: object) -> int:
            self.order.append("codex-wait")
            codex_waiting.set()
            await allow_codex_exit.wait()
            return 0

    order: list[str] = []
    backend_database = FakeBackendDatabase(order)
    application = services(
        backend=FakeBackend(order),
        backend_database=backend_database,
        codex=BlockingCodex(order),
    )
    subject = application.controller
    source = researcher()
    set_researchers(subject, (source,))
    session_metadata = CodexRolloutRecord.build_summary_json({
        "originator": "codex_cli_rs",
        "source": "exec",
        "cli_version": "test",
        "model_provider": "openai",
        "model": "test-model",
        "reasoning_effort": "high",
        "session_id": str(SESSION_ID),
        "timestamp": SESSION_TIMESTAMP.isoformat(),
    })
    accepted_attempt = agent_runtime_attempt(
        commit_record_id=accepted_commit_record_id,
        session_id=SESSION_ID,
    )
    accepted = CommittedInnerDict(
        innerdict=InnerDict.from_mapping(
            {
                KTP_NAMEKEY_COL: NAMEKEY.to_json_key(),
                KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL: str(accepted_commit_record_id),
                KTP_AI_AUGMENT_SESSION_METADATA_COL: session_metadata,
                researcher_var.ai_column: accepted_value,
                KTP_AI_AUGMENT_FOOTNOTES_COL: None,
                KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL: None,
            },
            api._CodexMatchProcedure(),
        ),
        commit_record=accepted_attempt.attempt.commit_record,
    )
    source.committed_innerdicts = (accepted,)
    backend_database.response = QueryResponse(
        attempts=(accepted_attempt,),
        ai_augment_singular_outerdicts=(source,),
    )

    cast(FakeBackend, subject._backend).pull_status = pull_status
    await subject._append_run_event(
        RunEvent(
            run_id=run_id,
            namekey=NAMEKEY,
            occurred_at_unix_usec=control_ui.datetime_to_unix_usec(SESSION_TIMESTAMP),
            lifecycle=RunLifecycle.QUEUED,
        )
    )
    run = subject._runs[run_id]
    subject._active_run = run

    execution = asyncio.create_task(subject._execute_run(run=run))
    await codex_waiting.wait()
    selection = control_ui._UiSelection(researcher_varname=researcher_var.varname)
    running = await subject.snapshot(selection=selection)

    assert running.counts.running == 1
    assert running.counts.completed == 0
    assert len(running.researcher_var_views) == 1
    assert running.researcher_var_views[0].latest_run_commit_var_view.lifecycle is (
        RunLifecycle.RUNNING
    )
    assert running.researcher_var_views[0].latest_run_commit_var_view.ai_value is None

    allow_codex_exit.set()
    await execution
    completed = await subject.snapshot(selection=selection)

    assert completed.counts.running == 0
    assert completed.counts.completed == int(expected_outcome is RunLifecycle.COMPLETED)
    assert completed.researcher_var_views[0].latest_run_commit_var_view.lifecycle is (
        expected_outcome
    )
    assert completed.researcher_var_views[0].latest_run_commit_var_view.ai_value is None
    journal_before_query = list(subject._events)
    await application.query_ipc()
    completed = await subject.snapshot(selection=selection)
    assert completed.researcher_var_views[0].latest_run_commit_var_view.ai_value == accepted_value
    assert subject._events == journal_before_query
    assert [event.lifecycle for event in subject._events][-2:] == [
        RunLifecycle.CODEX_EXITED,
        expected_outcome,
    ]
    display = completed.researcher_var_views[0].latest_run_commit_var_view
    assert display.lifecycle is expected_outcome
    assert display.backend_lifecycle is RunLifecycle.COMPLETED
    assert order[-1] == f"run-outcome:{expected_outcome.to_run_outcome_path()}"


class FakeInputStream:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class EmptyAsyncLines:
    def __aiter__(self) -> EmptyAsyncLines:
        return self

    async def __anext__(self) -> bytes:
        raise StopAsyncIteration


class FakeProcess(Mock):
    def __init__(self) -> None:
        super().__init__(spec=asyncio.subprocess.Process)
        self.pid = 12345
        self.stdin = FakeInputStream()
        self.stdout: AsyncIterator[bytes] = EmptyAsyncLines()
        self.returncode: int | None = None

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


@pytest.mark.anyio
async def test_backend_supervisor_refuses_replacement_and_uses_stdin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object], FakeProcess]] = []

    async def create_process(*args: object, **kwargs: object) -> FakeProcess:
        process = FakeProcess()
        calls.append((args, kwargs, process))
        return process

    async def ready(_subject: control_ui._BackendSupervisor) -> None:
        return None

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(control_ui._BackendSupervisor, "wait_until_ready", ready)
    subject = control_ui._BackendSupervisor(
        repository_root=tmp_path,
        config_path=tmp_path / "config.json",
        openalex_api_key="key",
        appendwatch_report=PurePosixPath("/mounted/appendwatch.txt"),
        dashboard_socket_path=tmp_path / "dashboard.sock",
        configuration=context_models.AiAugmentControlCentreContext.model_construct(
            pipeline_config=configured_pipeline_config(),
        ),
    )

    await subject.start(namekey=NAMEKEY)
    first_process = calls[0][2]
    await subject.supply_session_id(SESSION_ID)
    with pytest.raises(RuntimeError, match=Locale.BACKEND_ALREADY_OWNED):
        await subject.start(namekey=SECOND_NAMEKEY)

    assert len(calls) == 1
    assert first_process.returncode is None
    assert subject.process is not None
    subject.process.store_closed_cleanly.set()
    await subject.stop()
    await subject.start(namekey=SECOND_NAMEKEY)

    assert len(calls) == 2
    first_options = calls[0][1]
    second_options = calls[1][1]
    first_environment = cast(dict[str, str], first_options["env"])
    second_environment = cast(dict[str, str], second_options["env"])
    assert first_options["cwd"] == tmp_path
    assert first_options["stdin"] is asyncio.subprocess.PIPE
    assert first_options["start_new_session"] is True
    assert first_environment[api.NAMEKEY_ENV_NAME] == NAMEKEY.to_json_key()
    assert second_environment[api.NAMEKEY_ENV_NAME] == SECOND_NAMEKEY.to_json_key()
    assert second_environment[api.CODEX_SESSIONS_ROOT_ENV_NAME] == str(
        control_vars.CODEX_SESSIONS_ROOT
    )
    assert second_environment[api.APPENDWATCH_REPORT_ENV_NAME] == ("/mounted/appendwatch.txt")
    assert second_environment[ipc.DASHBOARD_SOCKET_PATH_ENV_NAME] == str(
        tmp_path / "dashboard.sock"
    )
    assert api.ROLLOUT_ENV_NAME not in second_environment
    assert first_process.stdin.writes == [f"{SESSION_ID}\n".encode()]
    assert first_process.stdin.closed is True
    assert first_process.returncode == -15
    await subject.stop()


@pytest.mark.anyio
async def test_backend_readiness_fails_immediately_after_pull_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []

    class FakeResponse:
        def __init__(self, response_status: int) -> None:
            self.status = response_status

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def read() -> bytes:
            return b""

    def urlopen(request: object, *, timeout: float) -> FakeResponse:
        assert timeout == control_vars.CONTROL_HTTP_TIMEOUT_SECONDS
        url = cast(Any, request).full_url
        requested_urls.append(url)
        return FakeResponse(
            response_status=status.HTTP_200_OK
            if url == control_vars.BACKEND_OPENAPI_URL
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    async def to_thread(function: Any, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(urllib_request, "urlopen", urlopen)
    monkeypatch.setattr(asyncio, "to_thread", to_thread)
    subject = control_ui._BackendSupervisor(
        repository_root=tmp_path,
        config_path=tmp_path / "config.json",
        openalex_api_key="key",
        appendwatch_report=PurePosixPath("/mounted/appendwatch.txt"),
        dashboard_socket_path=tmp_path / "dashboard.sock",
        configuration=context_models.AiAugmentControlCentreContext.model_construct(
            pipeline_config=configured_pipeline_config(),
        ),
    )
    subject._process = cast(
        Any,
        SimpleNamespace(process=SimpleNamespace(returncode=None), rebuilding=False, ipc_only=False),
    )

    with pytest.raises(RuntimeError, match=Locale.BACKEND_PULL_NOT_READY):
        await asyncio.wait_for(subject.wait_until_ready(), timeout=1)

    assert requested_urls == [
        control_vars.BACKEND_OPENAPI_URL,
        control_vars.BACKEND_PULL_URL,
    ]


@pytest.mark.anyio
async def test_codex_runner_starts_fresh_exec_process_and_sends_only_openapi_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processes: list[FakeProcess] = []
    process_calls: list[tuple[object, ...]] = []

    async def create_process(*args: object, **_kwargs: object) -> FakeProcess:
        process_calls.append(args)
        process = FakeProcess()
        processes.append(process)
        return process

    async def remote_command(
        _command: str,
        *,
        input_bytes: bytes | None = None,
        check: bool = True,
    ) -> bytes:
        assert input_bytes is None
        assert check is True
        return b""

    async def discover_session(
        _handle: control_ui._CodexProcessHandle,
    ) -> tuple[UUID, datetime]:
        return SESSION_ID, SESSION_TIMESTAMP

    async def discover_rollout_path(
        *,
        session_id: UUID,
        session_timestamp: datetime,
    ) -> PurePosixPath:
        assert session_id == SESSION_ID
        assert session_timestamp == SESSION_TIMESTAMP
        return ROLLOUT_PATH

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    runner = control_ui._CodexRunner(
        timezone=ZoneInfo("UTC"),
    )
    monkeypatch.setattr(runner, "_remote_command", remote_command)
    monkeypatch.setattr(runner, "discover_session", discover_session)
    monkeypatch.setattr(runner, "discover_rollout_path", discover_rollout_path)

    await runner.start(run=queued_run())
    await runner.start(run=queued_run())

    assert len(process_calls) == 2
    assert all("resume" not in " ".join(map(str, call)) for call in process_calls)
    assert all(str(control_vars.CODEX_ENV_PATH) in str(call[-1]) for call in process_calls)
    assert all("key" not in str(call[-1]) for call in process_calls)
    assert [process.stdin.writes for process in processes] == [
        [f"{control_vars.BACKEND_OPENAPI_URL}\n".encode()],
        [f"{control_vars.BACKEND_OPENAPI_URL}\n".encode()],
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("remote_output", "expected"),
    ((b"busy", True), (b"", False)),
)
async def test_codex_busy_probe_covers_every_runtime_account_codex_process(
    monkeypatch: pytest.MonkeyPatch,
    remote_output: bytes,
    expected: bool,
) -> None:
    commands: list[str] = []
    runner = control_ui._CodexRunner(timezone=ZoneInfo("UTC"))

    async def remote_command(
        command: str,
        *,
        input_bytes: bytes | None = None,
        check: bool = True,
    ) -> bytes:
        assert input_bytes is None
        assert check is True
        commands.append(command)
        return remote_output

    monkeypatch.setattr(runner, "_remote_command", remote_command)

    assert await runner.is_busy() is expected
    assert commands == [control_vars.CODEX_REMOTE_BUSY_COMMAND]
    assert 'pgrep -u "$(id -u)" -x codex' in commands[0]
    assert "codex exec" not in commands[0]


@pytest.mark.anyio
async def test_codex_cancel_logs_recorded_remote_and_local_processes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id = UUID("019fb000-0000-7000-8000-000000000002")
    remote_pid = control_ui.RemotePid(67890)
    process = FakeProcess()
    runner = control_ui._CodexRunner(
        timezone=ZoneInfo("UTC"),
    )

    async def terminate_remote_pid(value: control_ui.RemotePid) -> None:
        assert value == remote_pid

    monkeypatch.setattr(runner, "terminate_remote_pid", terminate_remote_pid)
    handle = control_ui._CodexProcessHandle(
        run=queued_run(run_id),
        process=cast(Any, process),
        remote_pid=remote_pid,
        session_id=SESSION_ID,
    )

    await runner.cancel(handle)

    assert capsys.readouterr().out == (
        f"{Locale.CONTROL_CENTRE_LOG_PREFIX} "
        "stopping recorded remote Codex process: "
        f"run_id={run_id} session_id={SESSION_ID} remote_pid={remote_pid}\n"
        f"{Locale.CONTROL_CENTRE_LOG_PREFIX} "
        "recorded remote Codex process stopped: "
        f"run_id={run_id} remote_pid={remote_pid}\n"
        f"{Locale.CONTROL_CENTRE_LOG_PREFIX} "
        f"stopping local Codex SSH process: run_id={run_id} pid={process.pid}\n"
        f"{Locale.CONTROL_CENTRE_LOG_PREFIX} "
        f"local Codex SSH process stopped: run_id={run_id} pid={process.pid} "
        f"return_code={process.returncode}\n"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("pull_status, expected", [
    (410, RunLifecycle.COMPLETED), (200, RunLifecycle.FAILED),
    (500, RunLifecycle.FAILED), (503, RunLifecycle.FAILED),
])
async def test_final_pull_is_single_and_after_persisted_codex_exit(
    pull_status: int, expected: RunLifecycle, inline_controller_io: None,
) -> None:
    order: list[str] = []

    class Backend(FakeBackend):
        async def probe_pull(self) -> int:
            assert subject._events[-1].lifecycle is RunLifecycle.CODEX_EXITED
            assert app.storage.general[storage_models.RUN_EVENTS_STORAGE_KEY][-1][
                "lifecycle"
            ] == RunLifecycle.CODEX_EXITED.value
            snapshot = await subject.snapshot(selection=control_ui._UiSelection(
                researcher_varname=control_ui.RESEARCHER_VARS[0].varname,
            ))
            assert snapshot.researcher_var_views[0].latest_run_commit_var_view.lifecycle is (
                RunLifecycle.CODEX_EXITED
            )
            assert snapshot.counts.running == 1
            return await super().probe_pull()

        async def stop(self) -> None:
            assert subject._events[-1].lifecycle is expected
            assert order[-1] == f"run-outcome:{expected.to_run_outcome_path()}"
            await super().stop()

    backend = Backend(order)
    backend.pull_status = pull_status
    database = FakeBackendDatabase(order)
    subject = controller(backend=backend, backend_database=database, codex=FakeCodex(order))
    before = deepcopy(app.storage.general[storage_models.BACKEND_DATABASE_STORAGE_KEY])
    await subject.queue(namekey=NAMEKEY)
    await subject._process_queued_run(await subject._queue.get())
    assert order.count("backend-pull") == 1
    assert database.query_calls == 0
    assert order[-1] == "backend-stop"
    assert app.storage.general[storage_models.BACKEND_DATABASE_STORAGE_KEY] == before
    assert all(event.lifecycle is not RunLifecycle.PUSH_ACCEPTED for event in subject._events)


@pytest.mark.anyio
async def test_cancelled_finalization_does_not_pull() -> None:
    backend = FakeBackend()
    subject = controller(backend=backend)
    run = queued_run()
    run.cancel_requested_at = SESSION_TIMESTAMP
    assert await subject._finalize_run(run=run) is RunLifecycle.CANCELLED
    assert backend.order == []


@pytest.mark.anyio
@pytest.mark.parametrize("response_status", [200, 410, 500, 503])
async def test_pull_status_including_http_errors_consumes_and_closes_body(
    response_status: int, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    inline_controller_io: None,
) -> None:
    body = io.BytesIO(b"response bytes")
    response = urllib_error.HTTPError(
        control_vars.BACKEND_PULL_URL, response_status, "test", Message(), body,
    )
    calls: list[str] = []

    def urlopen(request: urllib_request.Request, *, timeout: float) -> object:
        calls.append(request.full_url)
        assert request.get_method() == "GET"
        assert timeout == control_vars.CONTROL_HTTP_TIMEOUT_SECONDS
        if response_status >= 400:
            raise response
        return response

    monkeypatch.setattr(urllib_request, "urlopen", urlopen)
    backend = control_ui._BackendSupervisor(
        repository_root=tmp_path, config_path=tmp_path / "config.json",
        openalex_api_key="test", appendwatch_report=PurePosixPath("/test/report"),
        dashboard_socket_path=tmp_path / "ipc.sock",
        configuration=context_models.AiAugmentControlCentreContext.model_construct(
            pipeline_config=configured_pipeline_config(),
        ),
    )
    assert await backend.probe_pull() == response_status
    assert calls == [control_vars.BACKEND_PULL_URL]
    assert body.closed


@pytest.mark.anyio
@pytest.mark.parametrize("ssh_ok", [False, True])
async def test_probe_stages_are_separate_repeatable_and_storage_free(
    ssh_ok: bool, monkeypatch: pytest.MonkeyPatch, inline_controller_io: None,
) -> None:
    database = FakeBackendDatabase()
    subject = controller(backend_database=database)
    order: list[str] = []

    def ipc_probe() -> bool:
        order.append("ipc")
        return False

    def api_probe() -> bool:
        order.append("api")
        assert subject.backend_availability.ipc_available is False
        return False

    async def ssh_probe() -> bool:
        order.append("ssh")
        assert subject.backend_availability.full_api_available is False
        return ssh_ok

    async def auth_probe() -> bool:
        order.append("auth")
        assert subject.backend_availability.ssh_available is True
        return False

    monkeypatch.setattr(subject, "_probe_ipc", ipc_probe)
    monkeypatch.setattr(subject._backend, "full_api_available", api_probe)
    monkeypatch.setattr(subject._codex, "probe_ssh", ssh_probe)
    monkeypatch.setattr(subject._codex, "probe_auth", auth_probe)
    before = deepcopy(dict(app.storage.general))
    for _ in range(2):
        await subject.probe_all()
        assert subject.backend_availability.checked_at is not None
        assert subject.backend_availability.codex_authenticated is (False if ssh_ok else None)
        await subject.snapshot(selection=control_ui._UiSelection(
            researcher_varname=control_ui.RESEARCHER_VARS[0].varname,
        ))
    assert order == (["ipc", "api", "ssh", "auth"] if ssh_ok else ["ipc", "api", "ssh"]) * 2
    assert dict(app.storage.general) == before
    assert not hasattr(subject, "_backend_database")
    assert database.query_calls == 0
    assert cast(FakeBackend, subject._backend).order == []


@pytest.mark.anyio
async def test_ssh_auth_probes_use_existing_route_and_bound_command_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = control_ui._CodexRunner(timezone=ZoneInfo("UTC"))
    calls: list[tuple[str, bytes | None]] = []

    async def remote(command: str, *, input_bytes: bytes | None = None) -> bytes:
        calls.append((command, input_bytes))
        return input_bytes or b"Logged in"

    monkeypatch.setattr(runner, "_remote_command", remote)
    assert await runner.probe_ssh()
    assert await runner.probe_auth()
    assert calls == [
        ("cat", control_ui.SSH_PROBE_MARKER),
        (f"{control_vars.CODEX_CLI_BIN_PATH} login status", None),
    ]
    cancelled = asyncio.Event()

    async def blocked(*args: object, **kwargs: object) -> bytes:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return b""

    monkeypatch.setattr(runner, "_remote_command", blocked)
    monkeypatch.setattr(control_ui, "PROBE_TIMEOUT_SECONDS", 0.001)
    assert not await runner.probe_ssh()
    assert cancelled.is_set()


@pytest.mark.anyio
async def test_query_replaces_whole_snapshot_and_invalid_response_keeps_previous(
    inline_controller_io: None,
) -> None:
    database = FakeBackendDatabase()
    application = services(backend_database=database)
    subject = application.controller
    await subject.queue(namekey=NAMEKEY)
    journal = deepcopy(app.storage.general[storage_models.RUN_EVENTS_STORAGE_KEY])
    old = subject._snapshot
    stored = deepcopy(app.storage.general[storage_models.BACKEND_DATABASE_STORAGE_KEY])
    database.response = QueryResponse(
        attempts=(), ai_augment_singular_outerdicts=(researcher(SECOND_NAMEKEY),),
        run_outcome_records=(run_outcome_response(namekey=NAMEKEY),),
    )
    with pytest.raises(RuntimeError, match=Locale.BACKEND_DATABASE_RESPONSE_INVALID):
        await application.query_ipc()
    assert subject._snapshot is old
    assert app.storage.general[storage_models.BACKEND_DATABASE_STORAGE_KEY] == stored
    database.response = QueryResponse(
        attempts=(),
        ai_augment_singular_outerdicts=(
            researcher(SECOND_NAMEKEY, cohort=AiAugmentCohort.GROUND_TRUTH),
        ),
    )
    await application.query_ipc()
    assert subject._snapshot is not old
    assert tuple(subject._researchers_by_namekey) == (SECOND_NAMEKEY.to_json_key(),)
    assert subject._snapshot.ground_truth_by_namekey[SECOND_NAMEKEY.to_json_key()] is not None
    assert NAMEKEY.to_json_key() in old.researchers_by_namekey
    assert app.storage.general[storage_models.RUN_EVENTS_STORAGE_KEY] == journal
    restored = subject._storage.load_query_snapshot()
    assert restored is not None
    # MatchingProcedure instances are re-created; compare the serialized contract.
    assert restored.query_response.serialize() == subject._snapshot.query_response.serialize()


@pytest.mark.anyio
@pytest.mark.parametrize("cleanup_fails", (False, True))
async def test_page_query_uses_composed_operation_and_publishes_only_after_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inline_controller_io: None,
    cleanup_fails: bool,
) -> None:
    order: list[str] = []
    database = FakeBackendDatabase()

    class Backend(FakeBackend):
        @asynccontextmanager
        async def query_connection(self, client: object) -> AsyncIterator[None]:
            assert client is database
            order.append("query-enter")
            try:
                yield
            finally:
                assert database.query_calls == 1
                assert subject._snapshot is old
                assert app.storage.general[storage_models.BACKEND_DATABASE_STORAGE_KEY] == stored
                order.append("query-exit")
                if cleanup_fails:
                    raise RuntimeError("cleanup failed")

    application = services(backend=Backend(), backend_database=database)
    subject = application.controller
    assert not hasattr(subject, "_backend_database")
    assert not hasattr(subject, "refresh_from_ipc")
    await subject.queue(namekey=NAMEKEY)
    journal = deepcopy(app.storage.general[storage_models.RUN_EVENTS_STORAGE_KEY])
    old = subject._snapshot
    stored = deepcopy(app.storage.general[storage_models.BACKEND_DATABASE_STORAGE_KEY])
    database.response = QueryResponse(
        attempts=(), ai_augment_singular_outerdicts=(researcher(SECOND_NAMEKEY),),
    )
    page = control_ui._ControlCentrePage(
        controller=subject, query_ipc=application.query_ipc, reference_docx=tmp_path / "ref",
    )
    notify = Mock()
    monkeypatch.setattr(ui, "notify", notify)
    await page.refresh()
    assert database.query_calls == 0

    await page.refresh_from_ipc()

    assert order == ["query-enter", "query-exit"]
    assert database.query_calls == 1
    assert app.storage.general[storage_models.RUN_EVENTS_STORAGE_KEY] == journal
    if cleanup_fails:
        assert subject._snapshot is old
        assert app.storage.general[storage_models.BACKEND_DATABASE_STORAGE_KEY] == stored
        notify.assert_called_once_with(Locale.BACKEND_DATABASE_REQUEST_FAILED, type="negative")
    else:
        assert tuple(subject._researchers_by_namekey) == (SECOND_NAMEKEY.to_json_key(),)
        assert app.storage.general[storage_models.BACKEND_DATABASE_STORAGE_KEY] == (
            database.response.model_dump(mode="json")
        )
        notify.assert_called_once_with(Locale.QUERY_SNAPSHOT_REPLACED, type="positive")


def test_multiple_commits_for_same_session_remain_distinct_display_rows(tmp_path: Path) -> None:
    records = tuple(agent_runtime_attempt(result=BackendLifecycle.REJECTED) for _ in range(2))
    storage = storage_models.AiAugmentDashboardStorage()
    snapshot = storage.replace_query_response(QueryResponse(
        attempts=records, ai_augment_singular_outerdicts=(researcher(),),
        run_outcome_records=(run_outcome_response(),),
    ))
    run = queued_run()
    run.session_id = SESSION_ID
    view = control_ui._ResearcherView.from_snapshot(researcher(), snapshot, (run,))
    row = view.to_var_view(
        ground_truth=None, researcher_var=control_ui.RESEARCHER_VARS[0], codex_busy=False,
    )
    assert len(row.run_commit_var_views) == 2
    assert all(item.run_id == run.run_id for item in row.run_commit_var_views)
    page = control_ui._ControlCentrePage(
        controller=controller(), query_ipc=AsyncMock(), reference_docx=tmp_path / "ref",
    )
    ids = [item[control_ui.GRID_ROW_ID_FIELD] for item in page.attempt_detail_rows(row=row)]
    assert len(set(ids)) == 2
    with pytest.raises(ValidationError, match="frozen"):
        row.latest_run_commit_var_view.ai_value = "changed"  # type: ignore[misc]


@pytest.mark.anyio
async def test_cards_render_offline_from_replacement_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, inline_controller_io: None,
) -> None:
    database = FakeBackendDatabase()
    application = services(backend_database=database)
    subject = application.controller
    client = control_ui._BackendDatabaseClient(
        socket_path=tmp_path / "missing.sock", pipeline_config=configured_pipeline_config(),
    )
    monkeypatch.setattr(subject, "_render_card", client.card)
    seen: list[object] = []

    def cards(outer_dict: object, **kwargs: object) -> dict[str, str]:
        seen.append(outer_dict)
        return {"test": f"card-{len(seen)}"}

    monkeypatch.setattr(control_ui, "build_cards", cards)
    first = await subject.researcher_card(namekey=NAMEKEY)
    assert database.query_calls == 0
    await application.query_ipc()
    second = await subject.researcher_card(namekey=NAMEKEY)
    assert first.researcher is not second.researcher
    assert (first.card_markdown, second.card_markdown) == ("card-1", "card-2")
    assert database.query_calls == 1


@pytest.mark.anyio
async def test_snapshot_replacement_clears_other_page_card_and_removed_history(
    tmp_path: Path, inline_controller_io: None,
) -> None:
    database = FakeBackendDatabase()
    application = services(backend_database=database)
    subject = application.controller
    page = control_ui._ControlCentrePage(
        controller=subject, query_ipc=application.query_ipc, reference_docx=tmp_path / "ref",
    )
    page.selection.selected_namekey = NAMEKEY
    page._handles.grid = SimpleNamespace(
        options={}, update=Mock(), run_grid_method=AsyncMock(), run_row_method=AsyncMock(),
    )
    await page.refresh_grid()
    await page._show_card(control_ui._ResearcherCardView(
        researcher=subject._researchers[0], card_markdown="old card",
    ))
    await page.refresh_grid()
    assert page._displayed_card is not None
    # Query on a different page still invalidates this page's old object on repaint.
    await application.query_ipc()
    await page.refresh_grid()
    assert page._displayed_card is None
    page._expanded_history_namekey = NAMEKEY
    history = Mock()
    expansion = Mock()
    page._handles.attempt_history_table = history
    page._handles.attempt_history_expansion = expansion
    database.response = QueryResponse(attempts=(), ai_augment_singular_outerdicts=())
    await application.query_ipc()
    await page.refresh_grid()
    history.update_rows.assert_called_once_with([], clear_selection=True)
    expansion.set_visibility.assert_called_once_with(False)
    assert page._expanded_history_namekey is None


@pytest.mark.anyio
@pytest.mark.parametrize("query_first", (False, True))
@pytest.mark.parametrize("clean", (False, True))
async def test_owned_query_and_codex_launch_share_rebuild_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, query_first: bool, clean: bool,
    inline_controller_io: None,
) -> None:
    calls: list[tuple[object, ...]] = []

    async def spawn(*args: object, **_kwargs: object) -> FakeProcess:
        calls.append(args)
        process = FakeProcess()
        stopped = asyncio.Event()

        async def output() -> AsyncIterator[bytes]:
            await stopped.wait()
            if clean:
                yield (BACKEND_STORE_CLOSED_CLEANLY + "\n").encode()

        terminate = process.terminate

        def stop() -> None:
            terminate()
            stopped.set()

        monkeypatch.setattr(process, "terminate", stop)
        process.stdout = output()
        return process

    context = context_models.AiAugmentControlCentreContext.model_construct(
        pipeline_config=configured_pipeline_config(),
    )
    subject = control_ui._BackendSupervisor(
        repository_root=tmp_path, config_path=tmp_path / "config.json",
        openalex_api_key="key", appendwatch_report=PurePosixPath("/mounted/report"),
        dashboard_socket_path=tmp_path / "ipc.sock", configuration=context,
    )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(control_ui._BackendSupervisor, "wait_until_ready", AsyncMock())
    client = cast(control_ui._BackendDatabaseClient, SimpleNamespace(available=lambda: False))

    async def query() -> None:
        async with subject.query_connection(client):
            assert subject.process is not None and subject.process.ipc_only
            # Starting a queued run must wait for the query child to close.
            queued = asyncio.create_task(subject.start(namekey=NAMEKEY))
            await asyncio.sleep(0)
            assert not queued.done()
        await queued
        await subject.stop()

    if not query_first:
        await subject.start(namekey=NAMEKEY)
        await subject.stop()
    if not query_first and not clean:
        with pytest.raises(RuntimeError, match="operator intervention"):
            await query()
    else:
        await query()
    full_calls = [args for args in calls if "--ipc-only" not in args]
    assert "--new" in full_calls[0]
    for args in full_calls:
        assert "--yes" in args
        assert backend_server.DANGER_NO_VERIFY_HASH_OPTION in args
    for args in full_calls[1:]:
        assert "--resume" in args
    query_calls = [args for args in calls if "--ipc-only" in args]
    assert len(query_calls) == 1
    assert not set(query_calls[0]) & {"--new", "--resume", "--yes"}
    fresh = context_models.AiAugmentControlCentreContext.model_construct(
        pipeline_config=configured_pipeline_config(),
    )
    assert fresh.begin_backend_start() == ("--new", "--yes")


@pytest.mark.anyio
async def test_external_query_does_not_initialize_dashboard_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inline_controller_io: None,
) -> None:
    context = context_models.AiAugmentControlCentreContext.model_construct(
        pipeline_config=configured_pipeline_config(),
    )
    subject = control_ui._BackendSupervisor(
        repository_root=tmp_path, config_path=tmp_path / "config.json",
        openalex_api_key="key", appendwatch_report=PurePosixPath("/mounted/report"),
        dashboard_socket_path=tmp_path / "ipc.sock", configuration=context,
    )
    spawn = AsyncMock(side_effect=AssertionError("must borrow external Backend"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    client = cast(control_ui._BackendDatabaseClient, SimpleNamespace(available=lambda: True))
    async with subject.query_connection(client):
        assert subject.process is None
    assert context.begin_backend_start() == ("--new", "--yes")
    spawn.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ("startup", "forced-stop", "crash"))
async def test_failed_owned_cycle_blocks_retry_despite_close_ack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    context = context_models.AiAugmentControlCentreContext.model_construct(
        pipeline_config=configured_pipeline_config(),
    )
    context.finish_backend_stop(startup_succeeded=True, shutdown_succeeded=True)
    subject = control_ui._BackendSupervisor(
        repository_root=tmp_path, config_path=tmp_path / "config.json",
        openalex_api_key="key", appendwatch_report=PurePosixPath("/mounted/report"),
        dashboard_socket_path=tmp_path / "ipc.sock", configuration=context,
    )
    process = FakeProcess()

    async def output() -> AsyncIterator[bytes]:
        yield (BACKEND_STORE_CLOSED_CLEANLY + "\n").encode()

    process.stdout = output()
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    ready = AsyncMock(side_effect=RuntimeError("startup failed") if failure == "startup" else None)
    monkeypatch.setattr(control_ui._BackendSupervisor, "wait_until_ready", ready)
    if failure == "startup":
        with pytest.raises(RuntimeError, match="startup failed"):
            await subject.start(namekey=NAMEKEY)
    else:
        await subject.start(namekey=NAMEKEY)
        if failure == "crash":
            process.returncode = 1
        else:
            monkeypatch.setattr(process, "wait", AsyncMock(side_effect=[TimeoutError(), -9]))
        await subject.stop()
    assert "--resume" in spawn.call_args.args
    with pytest.raises(RuntimeError, match="operator intervention"):
        context.begin_backend_start()
    assert subject.process is None


@pytest.mark.anyio
async def test_queue_gate_holds_next_run_without_interrupting_active_run(
    monkeypatch: pytest.MonkeyPatch, inline_controller_io: None,
) -> None:
    subject = controller()
    started = asyncio.Event()
    release = asyncio.Event()
    processed: list[UUID] = []

    async def process(run: run_event_models.Run) -> None:
        processed.append(run.run_id)
        started.set()
        await release.wait()
        subject._queue.task_done()

    monkeypatch.setattr(subject, "_process_queued_run", process)
    await subject.start()
    try:
        worker = subject._worker_task
        first = await subject.queue(namekey=NAMEKEY)
        await asyncio.sleep(0)
        assert not subject.queue_processing and processed == []
        subject.set_queue_processing(True)
        subject.set_queue_processing(True)
        assert subject._worker_task is worker
        await asyncio.wait_for(started.wait(), 1)
        subject.set_queue_processing(False)
        second = await subject.queue(namekey=NAMEKEY)
        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert processed == [first]
        subject.set_queue_processing(True)
        await asyncio.wait_for(subject._queue.join(), 1)
        assert processed == [first, second]
        # Stop while empty must gate even a later enqueue.
        subject.set_queue_processing(False)
        third = await subject.queue(namekey=NAMEKEY)
        await asyncio.sleep(0)
        assert processed == [first, second]
        assert third in subject._storage.load_queue()
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_restored_queue_stays_stopped_and_publish_skips_remote_and_journal_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = controller()
    queued_id = await original.queue(namekey=NAMEKEY)
    active_id = await original.queue(namekey=NAMEKEY)
    await original._append_run_event(RunEvent(
        run_id=active_id, namekey=NAMEKEY, lifecycle=RunLifecycle.CODEX_EXITED,
        occurred_at_unix_usec=control_ui.datetime_to_unix_usec(SESSION_TIMESTAMP),
        codex_exit_code=0,
    ))
    original.set_queue_processing(True)
    before = deepcopy(app.storage.general)
    published = controller()
    abandon = AsyncMock(side_effect=AssertionError("publish cannot cancel remote runs"))
    monkeypatch.setattr(published._codex, "terminate_abandoned_run", abandon)
    await published.start(publishing=True)
    await published.shutdown()
    assert not published.queue_processing and published._worker_task is None
    assert app.storage.general == before
    assert queued_id in published._storage.load_queue()
    assert published._runs[active_id].run_outcome is None
    abandon.assert_not_called()
    restarted = controller()
    await restarted.start()
    try:
        await asyncio.sleep(0)
        assert not restarted.queue_processing
        assert restarted._queue.qsize() == 1
    finally:
        await restarted.shutdown()


@pytest.mark.anyio
async def test_publish_completed_filters_current_display_and_uses_shared_renderer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    inline_controller_io: None,
) -> None:
    application = services()
    subject = application.controller
    configuration = application.configuration.pipeline_config
    configuration.output_dir = tmp_path / "output"  # type: ignore[misc]
    configuration.pandoc_reference_docx = tmp_path / "reference.docx"  # type: ignore[misc]
    sources = tuple(researcher(NameKey(first_name=f"Person{i}", last_name="Test"))
                    for i in range(3)) + (
        researcher(NameKey(first_name="Person3", last_name="Test"),
                   cohort=AiAugmentCohort.INELIGIBLE,
                   ineligibility_category=next(iter(AiAugmentIneligibilityCategory))),
    )
    set_researchers(subject, sources)
    for source in sources:
        run = queued_run(namekey=source.namekey)
        run.lifecycle = RunLifecycle.COMPLETED
        run.run_outcome = RunLifecycle.COMPLETED
        subject._runs[run.run_id] = run
    # A queued current run excludes a researcher even with a completed predecessor.
    pending = queued_run(namekey=sources[1].namekey)
    subject._runs[pending.run_id] = pending
    monkeypatch.setattr(subject, "_render_card",
                        lambda source: "" if source is sources[2] else "shared card")
    calls: list[tuple[str, Path]] = []

    def render(markdown: str, reference: Path) -> bytes:
        calls.append((markdown, reference))
        return b"rendered docx"

    monkeypatch.setattr(control_ui, "render_docx_bytes", render)
    before = deepcopy(app.storage.general)
    await control_ui.publish_completed(application)
    card = await subject.researcher_card(namekey=sources[0].namekey)
    assert list(configuration.output_dir.iterdir()) == [
        configuration.output_dir / card.docx_filename,
    ]
    assert (configuration.output_dir / card.docx_filename).read_bytes() == b"rendered docx"
    assert calls == [("shared card", configuration.pandoc_reference_docx)]
    assert app.storage.general == before
    assert not subject.queue_processing
    assert "4 researchers; 2 eligible and completed; 1 DOCX" in capsys.readouterr().out


@pytest.mark.anyio
async def test_probe_and_docx_failures_emit_operator_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    inline_controller_io: None,
) -> None:
    subject = controller()
    await subject.probe_all()
    output = capsys.readouterr().out
    for action in ("IPC OPTIONS /query", "Backend API GET /openapi.json", "Lima/SSH connect",
                   "Codex login status"):
        assert f"Probing {action}" in output and f"Probe {action}:" in output
    page = control_ui._ControlCentrePage(
        controller=subject, query_ipc=AsyncMock(), reference_docx=tmp_path / "reference.docx",
    )
    page._displayed_card = control_ui._ResearcherCardView(
        researcher=researcher(), card_markdown="card",
    )
    monkeypatch.setattr(control_ui, "render_docx_bytes", Mock(side_effect=OSError("pandoc detail")))
    monkeypatch.setattr(ui, "notify", Mock())
    await page.download_displayed_card()
    output = capsys.readouterr().out
    assert "Rendering DOCX download:" in output
    assert "DOCX download failed:" in output and "pandoc detail" in output


@pytest.mark.anyio
@pytest.mark.parametrize("fail_second", (False, True))
async def test_publish_one_shot_shutdown_noop_or_first_error_keeps_written_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_second: bool,
    capsys: pytest.CaptureFixture[str], inline_controller_io: None,
) -> None:
    application = services()
    subject = application.controller
    config = application.configuration.pipeline_config
    config.output_dir = tmp_path / "published"  # type: ignore[misc]
    config.pandoc_reference_docx = tmp_path / "reference.docx"  # type: ignore[misc]
    if fail_second:
        sources = (researcher(), researcher(SECOND_NAMEKEY))
        set_researchers(subject, sources)
        for source in sources:
            run = queued_run(namekey=source.namekey)
            run.lifecycle = RunLifecycle.COMPLETED
            run.run_outcome = RunLifecycle.COMPLETED
            subject._runs[run.run_id] = run
    render = Mock(side_effect=[b"first document", OSError("second render failed")])
    monkeypatch.setattr(control_ui, "render_docx_bytes", render)
    shutdown = Mock()
    monkeypatch.setattr(app, "shutdown", shutdown)
    monkeypatch.setattr(control_ui, "SERVICES", application)
    monkeypatch.setattr(control_ui, "APPLICATION_EXIT_CODE", 0)
    before = deepcopy(app.storage.general)
    await control_ui.publish_completed_and_shutdown()
    shutdown.assert_called_once_with()
    assert control_ui.APPLICATION_EXIT_CODE == int(fail_second)
    assert app.storage.general == before
    if fail_second:
        paths = list(config.output_dir.iterdir())
        assert len(paths) == 1 and paths[0].read_bytes() == b"first document"
        assert "second render failed" in capsys.readouterr().out
    else:
        assert not config.output_dir.exists()
        render.assert_not_called()
        assert "Publishing finished: 0 DOCX files" in capsys.readouterr().out


@pytest.mark.parametrize("publish", (False, True))
@pytest.mark.parametrize("failure", ("config", "storage"))
def test_startup_failure_exits_through_framework_shutdown(publish: bool, failure: str) -> None:
    """Exercise NiceGUI's real background dispatch/shutdown flag without binding sockets."""
    script = '''
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import patch
from nicegui import app, core, server, ui
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as dashboard

async def start(**kwargs):
    raise ValueError("invalid persisted storage")

async def stop():
    print("CONTROLLER_CLEANED", flush=True)

def create(**kwargs):
    if sys.argv[1] == "config":
        raise ValueError("invalid configuration hash")
    return SimpleNamespace(controller=SimpleNamespace(start=start, shutdown=stop))

def run(**kwargs):
    # Substitute only the socket-serving loop. Framework callback dispatch, shutdown
    # signalling, shutdown hooks and the application's exit code are real.
    async def lifecycle():
        core.loop = asyncio.get_running_loop()
        server.Server.instance = SimpleNamespace(
            should_exit=False, config=SimpleNamespace(should_reload=False),
        )
        app.config.reload = False
        app.safe_invoke(dashboard.application_startup)
        async with asyncio.timeout(2):
            while not server.Server.instance.should_exit:
                await asyncio.sleep(0)
        print("FRAMEWORK_SHUTDOWN_REQUESTED", flush=True)
        await app.stop()
        print("FRAMEWORK_STOPPED", flush=True)
    asyncio.run(lifecycle())

with patch.object(ui, "run", run), patch.object(dashboard, "create_services", create):
    raise SystemExit(dashboard.main(sys.argv[2:]))
'''
    command = [sys.executable, "-c", script, failure]
    if publish:
        command += ["publish", "completed"]
    command += ["--config", "unused.json"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 1, result.stderr
    assert "FRAMEWORK_SHUTDOWN_REQUESTED" in result.stdout
    assert "FRAMEWORK_STOPPED" in result.stdout
    if failure == "storage":
        assert "CONTROLLER_CLEANED" in result.stdout


ROOT = Path(__file__).resolve().parents[5]
MODES = ("ipc", "new", "resume", "continue")
STARTUP_NAMEKEY = NameKey(first_name="Case 000", last_name="Startup")

# Exercise production initialization boundaries, deliberately not the serving lifespan.
# No functions, transports, configuration objects or global constants are substituted.
STARTUP = """
import sys
from src.detours.detour_ai_augment.src.backend import api, server

args = server.parse_args(sys.argv[1:])
confirmed = False if args.ipc_only else server.confirm_startup(args)
api._acquire_backend_process_lock()
try:
    runtime = server.configure_runtime(
        args.config, require_namekey=not args.ipc_only,
        verify_hash_on_init=not args.danger_no_verify_hash,
    )
    store = runtime.pipeline_config.backend_store
    boundary = (
        store.read_only() if args.ipc_only else server.backend_store_lifecycle(
            runtime, new=args.new, confirmed=confirmed, yes=args.yes,
        )
    )
    with boundary:
        rows = store.execute("SELECT count(*) FROM detour_http_records").fetchone()
        print("STARTUP_READY", rows[0], len(runtime.ai_augment_singular_outerdicts))
finally:
    api._release_backend_process_lock()
"""


class StartupFiles(FrozenStrictModel):
    config: Path
    source: Path
    replay: Path
    detour: Path
    process_temp: Path

    def environment(self, namekey: str | None = STARTUP_NAMEKEY.to_json_key()) -> dict[str, str]:
        environment = dict(os.environ, TMPDIR=str(self.process_temp))
        environment.pop("FASTAPI_DETOUR_NAMEKEY", None)
        if namekey is not None:
            environment["FASTAPI_DETOUR_NAMEKEY"] = namekey
        return environment

    def repin(self) -> None:
        config = json.loads(self.config.read_text())
        config["files_config"][REPLAY_LOG_KEY]["sha256"] = hashlib.sha256(
            self.replay.read_bytes()
        ).hexdigest()
        self.config.write_text(json.dumps(config))


def source_population(path: Path, release_map: Path) -> None:
    """Synthetic source tables satisfy the real 307-person population invariants."""
    groups = (
        (196, "subset 1", 1, False, 0),
        (78, "unreleased", 4, False, 1),
        (1, "subset 1", 1, False, 0),  # the explicitly excluded duplicate identity
        (3, "subset 8", 1, False, 0),
        (7, "unreleased", 2, False, 0),
        (6, "unreleased", 4, True, 1),
        (16, "unreleased", 4, False, 2),
    )
    with duckdb.connect(str(path)) as connection, release_map.open("w") as mapping:
        writer = csv.writer(mapping)
        writer.writerow((DRAW_LABEL, BATCH_LABEL))
        for table in (XLSX_INNERDICT_TABLE, PARQUET_INNERDICT_TABLE, DOCX_INNERDICT_TABLE):
            connection.execute(
                f"CREATE TABLE {quote(table)} ("
                f"{quote(KTP_NAMEKEY_COL)} VARCHAR, {quote(KTP_INNERDICT_JSONLINES_COL)} VARCHAR)"
            )
        connection.execute(
            f"CREATE TABLE {quote(CARD_PARTITION_TABLE)} ("
            f"{quote(KTP_NAMEKEY_COL)} VARCHAR, {quote(KTP_PARTITION_COL)} INTEGER, "
            f"{quote(KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL)} BOOLEAN, "
            f"{quote(KTP_PARTITION_FLAG_SSN_COUNT_COL)} INTEGER)"
        )
        source_rows: list[tuple[str, str]] = []
        classifications: list[tuple[str, int, bool, int]] = []
        for count, batch, partition, nonexact, ssn_count in groups:
            for _ in range(count):
                index = len(source_rows)
                namekey = (
                    NameKey.from_json_key(EXCLUDED_NAMEKEY) if index == 274
                    else NameKey(first_name=f"Case {index:03}", last_name="Startup")
                )
                draws = (str(index), f"extra-{index}") if index < 5 else (str(index),)
                rows = []
                for draw in draws:
                    writer.writerow((draw, batch))
                    rows.append(json.dumps({
                        KTP_NAMEKEY_COL: namekey.to_json_key(),
                        KTP_FIRST_NAME_COL: namekey.first_name,
                        KTP_LAST_NAME_COL: namekey.last_name,
                        KTP_FILENAME_COL: "startup.xlsx",
                        KTP_FRAGMENT_COL: index + 1,
                        KTP_FRAGMENT_TYPE_COL: "csv_row",
                        DRAW_LABEL: draw,
                    }))
                source_rows.append((namekey.to_json_key(), "\n".join(rows)))
                classifications.append((namekey.to_json_key(), partition, nonexact, ssn_count))
        connection.executemany(f"INSERT INTO {quote(XLSX_INNERDICT_TABLE)} VALUES (?, ?)",
                               source_rows)
        connection.executemany(f"INSERT INTO {quote(CARD_PARTITION_TABLE)} VALUES (?, ?, ?, ?)",
                               classifications)


@pytest.fixture
def startup_files(tmp_path: Path) -> StartupFiles:
    source = tmp_path / "source.duckdb"
    release_map = tmp_path / "release-map.csv"
    source_population(source, release_map)
    replay = tmp_path / "replay.jsonl"
    replay.write_bytes(b"")
    config: dict[str, Any] = json.loads((ROOT / "config_ai_augment.json").read_text())
    config.update(db_file=str(source), output_dir=str(tmp_path / "output"),
                  state_file=str(tmp_path / "state.json"), rollout_cas_dir=str(tmp_path / "cas"))
    for key, path in ((MAP_SUBSET_0_TO_BATCH_KEY, release_map), (REPLAY_LOG_KEY, replay)):
        config["files_config"][key] = {
            "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "desc": "isolated startup fixture",
        }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    runtime = backend_server.configure_runtime(config_path, require_namekey=False)
    store = runtime.pipeline_config.backend_store
    store.rebuild_from_log(runtime, reset_confirmed=True)
    source.chmod(0o400)
    process_temp = tmp_path / "process-temp"
    process_temp.mkdir()
    return StartupFiles(config=config_path, source=source, replay=replay,
                        detour=store.detour_db_path, process_temp=process_temp)


def argv(mode: str, config: Path, *, yes: bool = True) -> list[str]:
    return ["--config", str(config), "--ipc-only" if mode == "ipc" else f"--{mode}",
            *(["--yes"] if yes else [])]


def start(files: StartupFiles, mode: str, *, stdin: str = "", yes: bool = True,
          namekey: str | None = STARTUP_NAMEKEY.to_json_key()) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", STARTUP, *argv(mode, files.config, yes=yes)],
        cwd=ROOT, env=files.environment(namekey), input=stdin,
        capture_output=True, text=True, timeout=20, check=False,
    )


def record_line() -> bytes:
    return (HttpRequestLogRecord(
        schema_version="1.1", record_id=uuid7(), method="GET", scheme="https",
        host="startup.invalid", port=None, path="/fixture", query="", request_headers={},
        request_body=None, response_code=200, response_headers={}, response_body="{}",
        received_at_unix_usec=1, ready_to_respond_at_unix_usec=2, duration_usec=1,
    ).model_dump_json() + "\n").encode()


class TestBackendStartupConditions:
    """Real initialization only; do not inherit the surrounding UI tests' mocks."""

    @pytest.fixture(autouse=True)
    def isolated_lima_configuration(self) -> None:
        """No Lima configuration replacement for these local startup checks."""

    @pytest.fixture(autouse=True)
    def isolated_general_storage(self) -> None:
        """These checks do not access NiceGUI storage."""

    @pytest.fixture(autouse=True)
    def inline_controller_io(self) -> None:
        """Keep production dispatch untouched; these checks exercise no controller."""

    @pytest.mark.parametrize("mode", MODES)
    @pytest.mark.parametrize("condition", (
        "ready", "missing_config", "malformed_config", "invalid_config", "missing_source",
        "corrupt_source", "missing_replay", "hash_mismatch", "missing_db", "corrupt_db",
        "missing_anchor", "unprojected_record", "empty_object_lf", "empty_object_no_lf",
        "missing_namekey", "unknown_namekey", "ineligible_namekey", "lock_held",
    ))
    @staticmethod
    def test_startup_conditions(startup_files: StartupFiles, mode: str, condition: str) -> None:
        files = startup_files
        namekey: str | None = STARTUP_NAMEKEY.to_json_key()
        success = condition == "ready"
        if condition == "missing_config":
            files.config.unlink()
        elif condition in {"malformed_config", "invalid_config"}:
            files.config.write_text("{" if condition == "malformed_config" else "{}")
        elif condition == "missing_source":
            files.source.unlink()
        elif condition == "corrupt_source":
            files.source.chmod(0o600)
            files.source.write_bytes(b"not DuckDB")
        elif condition == "missing_replay":
            files.replay.unlink()
        elif condition == "missing_db":
            files.detour.unlink()
            success = mode == "new"
        elif condition == "corrupt_db":
            files.detour.chmod(0o600)
            files.detour.write_bytes(b"not DuckDB")
            success = mode == "new"
        elif condition == "missing_anchor":
            files.detour.chmod(0o600)
            with duckdb.connect(str(files.detour)) as connection:
                connection.execute("COMMENT ON TABLE detour_http_records IS NULL")
            success = mode == "new"
        elif condition in {"hash_mismatch", "unprojected_record", "empty_object_lf",
                           "empty_object_no_lf"}:
            files.replay.chmod(0o600)
            payload = {"empty_object_lf": b"{}\n", "empty_object_no_lf": b"{}"}.get(
                condition, record_line(),
            )
            files.replay.write_bytes(payload)
            if condition != "hash_mismatch":
                files.repin()
            success = condition == "unprojected_record" and mode == "new"
        elif condition in {"missing_namekey", "unknown_namekey", "ineligible_namekey"}:
            namekey = {
                "missing_namekey": None,
                "unknown_namekey": NameKey(first_name="Absent", last_name="Startup").to_json_key(),
                "ineligible_namekey": EXCLUDED_NAMEKEY,
            }[condition]
            success = mode == "ipc"

        before = {path: path.read_bytes() if path.exists() else None
                  for path in (files.source, files.replay, files.detour)}
        with ExitStack() as stack:
            if condition == "lock_held":
                lock = stack.enter_context(
                    (files.process_temp / "ktp-hcr-detour-ai-augment-backend.lock").open("wb")
                )
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = start(files, mode, namekey=namekey)
        details = result.stdout + result.stderr
        assert (result.returncode == 0) is success, details
        assert ("STARTUP_READY" in result.stdout) is success, details
        if success:
            expected_rows = 1 if condition == "unprojected_record" else 0
            assert f"STARTUP_READY {expected_rows} 307" in result.stdout
        for path in (files.source, files.replay):
            assert (path.read_bytes() if path.exists() else None) == before[path]
        # Only explicit new can change/reconstruct DB contents, even when startup fails.
        if mode != "new":
            after_db = files.detour.read_bytes() if files.detour.exists() else None
            assert after_db == before[files.detour]

    @pytest.mark.parametrize("mode", ("new", "resume", "continue"))
    @pytest.mark.parametrize("stdin,yes,success", (
        ("", False, False), ("\n", False, False), ("n\n", False, False),
        ("y\n", False, True), ("", True, True),
    ))
    @staticmethod
    def test_real_startup_confirmation(
        startup_files: StartupFiles, mode: str, stdin: str, yes: bool, success: bool,
    ) -> None:
        result = start(startup_files, mode, stdin=stdin, yes=yes)
        assert (result.returncode == 0) is success, result.stdout + result.stderr
        assert ("[y/N]" not in result.stdout) is yes
        assert ("STARTUP_READY" in result.stdout) is success

    @pytest.mark.parametrize("stdin,yes,success", (
        ("y\n", False, False), ("y\nn\n", False, False),
        ("y\ny\n", False, True), ("", True, True),
    ))
    @staticmethod
    def test_real_second_replay_confirmation_preserves_old_db_on_refusal(
        startup_files: StartupFiles, stdin: str, yes: bool, success: bool,
    ) -> None:
        files = startup_files
        files.replay.chmod(0o600)
        files.replay.write_bytes(record_line())
        files.repin()
        old_db = files.detour.read_bytes()
        log = files.replay.read_bytes()
        result = start(files, "new", stdin=stdin, yes=yes)
        assert (result.returncode == 0) is success, result.stdout + result.stderr
        assert ("Registered a nonempty replay log" in result.stdout) is not yes
        assert files.replay.read_bytes() == log
        if not success:
            assert files.detour.read_bytes() == old_db

    @pytest.mark.parametrize("ipc_only", (False, True))
    @pytest.mark.parametrize("flags,valid", (
        ((), False), (("--new",), True), (("--resume",), True), (("--continue",), True),
        (("--new", "--resume"), False), (("--new", "--continue"), False),
        (("--resume", "--continue"), True), (("--new", "--resume", "--continue"), False),
    ))
    @staticmethod
    def test_real_mode_parser(ipc_only: bool, flags: tuple[str, ...], valid: bool) -> None:
        arguments = ["--config", "unused.json", *(["--ipc-only"] if ipc_only else []), *flags]
        if not ipc_only and not valid:
            with pytest.raises(SystemExit) as error:
                backend_server.parse_args(arguments)
            assert error.value.code == 2
            return
        parsed = backend_server.parse_args(arguments)
        assert parsed.ipc_only is ipc_only
        if ipc_only:
            assert not parsed.new and not parsed.resume
        else:
            assert parsed.new is ("--new" in flags)
            assert parsed.resume is ("--new" not in flags)

    @pytest.mark.parametrize("mode", MODES)
    @staticmethod
    def test_config_argument_is_required(mode: str) -> None:
        with pytest.raises(SystemExit) as error:
            backend_server.parse_args(["--ipc-only" if mode == "ipc" else f"--{mode}"])
        assert error.value.code == 2
