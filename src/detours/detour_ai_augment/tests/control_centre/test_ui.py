from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, cast
from urllib import request as urllib_request
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import duckdb
import pytest
from fastapi import status
from nicegui import app, ui

from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (  # noqa: E501
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.pydantic_to_paste import (  # noqa: E501
    EXPORT_OPENALEX_API_KEY,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_init import (  # noqa: E501
    Submission,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AI_AUGMENT_COLUMNS,
    DOCX_COLUMNS,
    KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL,
    KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL,
    KTP_AI_AUGMENT_FOOTNOTES_COL,
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
    AiAugmentCohort,
    AiAugmentIneligibilityCategory,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers import (
    vars as control_vars,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (
    Locale,
)
from src.detours.detour_ai_augment.src.backend import api, ipc
from src.detours.detour_ai_augment.src.backend.helpers.data_models import (
    ai_augment_context as backend_context_models,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_outer_dict import (
    AiAugmentOuterDict,
    CommittedInnerDict,
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
    run_event as run_event_models,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    run_outcome as run_outcome_models,
)
from src.helpers.data_models import HttpRequestLogRecord, InnerDict, NameKey
from src.helpers.procedures import DocxMatchProcedure, XlsxMatchProcedure
from src.helpers.vars import (
    DRAW_LABEL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
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
    return AiAugmentDetourConfig.model_construct(  # type: ignore[call-arg]
        total_draws=1,
        timezone="UTC",
        resources=SimpleNamespace(  # type: ignore[arg-type]
            registered_resources=(
                SimpleNamespace(verify_hash_on_init=True),
            )
        ),
    )


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
            "Source-Key": 'ktp.filename="rollout.jsonl", ktp.fragment=1, '
            'ktp.fragment_type="line_number"',
            "Name-Key": 'ktp.first_name="Jane", ktp.last_name="Doe"',
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
) -> AiAugmentOuterDict:
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
    return AiAugmentOuterDict(
        namekey=namekey,
        xlsx_innerdicts=(xlsx_innerdict,),
        ssn_innerdicts=(),
        docx_innerdicts=docx_innerdicts,
        ai_augment_rnd=1,
        ai_augment_cohort=cohort,
        ai_augment_ineligibility_category=ineligibility_category,
    )


def cached_source_population_row() -> AiAugmentOuterDict:
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


def source_input_fingerprint(
    *,
    mtime_ns: int = 2,
) -> control_ui._SourceInputFingerprint:
    return control_ui._SourceInputFingerprint(
        schema_version=control_ui.SOURCE_DATA_CACHE_SCHEMA_VERSION,
        source_database_path="/source.duckdb",
        source_database_size=1,
        source_database_mtime_ns=mtime_ns,
        source_database_ctime_ns=3,
        source_database_device=4,
        source_database_inode=5,
        release_map_sha256="0" * 64,
        sample_seed=42,
    )


class FakeSourceRepository:
    def __init__(self) -> None:
        self.researchers = (researcher(),)

    def load_researchers(self) -> tuple[AiAugmentOuterDict, ...]:
        return self.researchers

    def load_ground_truth_by_namekey(
        self,
    ) -> dict[str, InnerDict]:
        return {}


class FakeBackendDatabase:
    def __init__(
        self,
        order: list[str] | None = None,
        *,
        available: bool = False,
    ) -> None:
        self.order = [] if order is None else order
        self.pull_calls = 0
        self.run_outcome_calls: list[
            tuple[RunLifecycle, NameKey]
        ] = []
        self.ipc_available = available
        self.response = QueryResponse(
            attempts=(),
            ai_augment_outerdicts=(),
        )

    def pull(self) -> QueryResponse:
        self.pull_calls += 1
        return self.response

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

    def full_api_available(self) -> bool:
        return self.api_available

    async def start(self, *, namekey: NameKey) -> None:
        self.order.append("backend-start")
        self.started_namekeys.append(namekey)
        self.status = control_ui._BackendStatus.RUNNING

    async def probe_pull(self) -> None:
        self.order.append("backend-pull")

    async def supply_session_id(self, session_id: UUID) -> None:
        self.order.append("backend-session")
        self.supplied_session_ids.append(session_id)

    async def stop(self) -> None:
        self.order.append("backend-stop")
        self.status = control_ui._BackendStatus.STOPPED


class FakeCodex:
    def __init__(self, order: list[str] | None = None) -> None:
        self.order = [] if order is None else order

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


def controller(
    *,
    backend: FakeBackend | None = None,
    backend_database: FakeBackendDatabase | None = None,
    codex: FakeCodex | None = None,
) -> control_ui._ControlCentreController:
    return control_ui._ControlCentreController(
        source_repository=cast(control_ui._SourceRepository, FakeSourceRepository()),
        backend=cast(control_ui._BackendSupervisor, backend or FakeBackend()),
        backend_database=cast(
            control_ui._BackendDatabaseClient,
            backend_database or FakeBackendDatabase(),
        ),
        codex=cast(control_ui._CodexRunner, codex or FakeCodex()),
        reconciler=control_ui._AttemptReconciler(),
        projector=control_ui._VariableProjector(),
    )


async def run_sync_in_test(function: Any, /, *args: object, **kwargs: object) -> Any:
    return function(*args, **kwargs)


@pytest.fixture
def inline_controller_io(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "to_thread", run_sync_in_test)


def test_variable_specs_cover_every_ai_augment_column() -> None:
    assert tuple(item.ai_column for item in control_ui.VARIABLE_SPECS) == (AI_AUGMENT_COLUMNS)


@pytest.mark.anyio
async def test_displayed_card_download_uses_exact_markdown_and_shared_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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

    button = Button()
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
        markdown="## Exact displayed card\n\nbody\n",
    )
    subject = control_ui._ControlCentrePage(
        controller=cast(control_ui._ControlCentreController, object()),
        reference_docx=reference_docx,
    )
    subject._handles.download_card_button = button
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
    assert markdown.content == card.markdown
    assert button.enabled

    await subject.download_displayed_card()

    assert rendered == [(card.markdown, reference_docx)]
    assert downloads == [
        (
            b"PK\x03\x04docx",
            "1_pilot2_Jane_DoeSmith.docx",
            control_ui.DOCX_MEDIA_TYPE,
        )
    ]
    assert button.enabled

    subject._clear_displayed_card()
    assert markdown.content == ""
    assert not button.enabled


def test_dashboard_paths_resolve_from_repository_root(
    pytestconfig: pytest.Config,
) -> None:
    repository_root = pytestconfig.rootpath
    assert control_vars.REPOSITORY_ROOT == repository_root
    assert control_vars.REPOSITORY_ROOT == repository_root
    assert control_vars.DEFAULT_CONFIG_PATH == repository_root / "config_ai_augment.json"


def test_dashboard_context_prepares_source_population_from_read_only_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lima_config_path = tmp_path / "lima.yaml"
    lima_config_path.write_text(
        '{"param":{"FASTAPI_DETOUR_APPENDWATCH_REPORT":'
        '"/home/ai/.aivm-control/appendwatch/appendwatch-tree.txt"},"mounts":[]}',
        encoding="utf-8",
    )
    source_db_path = tmp_path / "source.duckdb"
    pipeline_config = AiAugmentDetourConfig.model_construct(  # type: ignore[call-arg]
        db_file=source_db_path,
        sample_seed=42,
        timezone="UTC",
        resources=SimpleNamespace(  # type: ignore[arg-type]
            release_map=Path("/release-map.csv")
        ),
    )
    source_population = (researcher(),)
    connection = SimpleNamespace(close=lambda: None)
    calls: list[tuple[str, bool]] = []

    def connect(path: str, *, read_only: bool) -> SimpleNamespace:
        calls.append((path, read_only))
        return connection

    def derive(
        supplied_connection: object,
        release_batches: object,
        *,
        sample_seed: int,
    ) -> tuple[Any, ...]:
        assert supplied_connection is connection
        assert release_batches == "release-batches"
        assert sample_seed == 42
        return source_population

    monkeypatch.setenv(EXPORT_OPENALEX_API_KEY, "host-openalex-key")
    monkeypatch.setattr(context_models, "LIMA_CONFIG_PATH", lima_config_path)
    monkeypatch.setattr(
        backend_context_models,
        "_load_release_batches",
        lambda _release_map: "release-batches",
    )
    monkeypatch.setattr(backend_context_models, "_derive_ai_augment_outerdicts", derive)
    monkeypatch.setattr(duckdb, "connect", connect)

    context = context_models.AiAugmentControlCentreContext.model_construct(
        pipeline_config=pipeline_config
    )

    assert context.ai_augment_outerdicts is source_population
    assert calls == [(str(source_db_path), True)]


def test_dashboard_context_accepts_cached_population_without_opening_source_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lima_config_path = tmp_path / "lima.yaml"
    lima_config_path.write_text(
        '{"param":{"FASTAPI_DETOUR_APPENDWATCH_REPORT":'
        '"/home/ai/.aivm-control/appendwatch/appendwatch-tree.txt"},"mounts":[]}',
        encoding="utf-8",
    )
    pipeline_config = AiAugmentDetourConfig.model_construct(  # type: ignore[call-arg]
        db_file=tmp_path / "source.duckdb",
        timezone="UTC",
    )
    source_population = (cached_source_population_row(),)

    monkeypatch.setenv(EXPORT_OPENALEX_API_KEY, "host-openalex-key")
    monkeypatch.setattr(context_models, "LIMA_CONFIG_PATH", lima_config_path)
    monkeypatch.setattr(
        duckdb,
        "connect",
        lambda *_args, **_kwargs: pytest.fail(
            "source database should not be opened on a cache hit"
        ),
    )

    context = context_models.AiAugmentControlCentreContext.model_construct(
        pipeline_config=pipeline_config,
        cached_ai_augment_outerdicts=source_population,
    )

    assert context.ai_augment_outerdicts == source_population


def test_cached_source_data_round_trips_and_rejects_a_stale_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fingerprint = source_input_fingerprint()
    source_population = (cached_source_population_row(),)
    control_ui.store_cached_source_data(
        fingerprint=fingerprint,
        ai_augment_outerdicts=source_population,
    )
    monkeypatch.setattr(
        control_ui,
        "source_input_fingerprint",
        lambda _config: fingerprint,
    )

    pipeline_config = AiAugmentDetourConfig.model_construct()  # type: ignore[call-arg]
    observed_fingerprint, cached = control_ui.load_cached_source_data(pipeline_config)

    assert observed_fingerprint == fingerprint
    assert cached is not None
    assert tuple(value.serialize() for value in cached) == tuple(
        value.serialize() for value in source_population
    )

    stale_fingerprint = source_input_fingerprint(mtime_ns=99)
    monkeypatch.setattr(
        control_ui,
        "source_input_fingerprint",
        lambda _config: stale_fingerprint,
    )

    observed_fingerprint, cached = control_ui.load_cached_source_data(pipeline_config)

    assert observed_fingerprint == stale_fingerprint
    assert cached is None


def test_source_input_fingerprint_stats_database_without_reading_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_database = tmp_path / "source.duckdb"
    source_database.write_bytes(b"source")
    pipeline_config = AiAugmentDetourConfig.model_construct(  # type: ignore[call-arg]
        db_file=source_database,
        sample_seed=42,
        resources=SimpleNamespace(  # type: ignore[arg-type]
            release_map=SimpleNamespace(hash="a" * 64),
        ),
    )
    monkeypatch.setattr(
        Path,
        "open",
        lambda *_args, **_kwargs: pytest.fail(
            "the source database must not be read for its startup fingerprint"
        ),
    )

    fingerprint = control_ui.source_input_fingerprint(pipeline_config)

    source_database_stat = source_database.stat()
    assert fingerprint.source_database_path == str(source_database.resolve())
    assert fingerprint.source_database_size == source_database_stat.st_size
    assert fingerprint.source_database_mtime_ns == source_database_stat.st_mtime_ns
    assert fingerprint.release_map_sha256 == "a" * 64
    assert fingerprint.sample_seed == 42


def test_source_repository_uses_cached_ground_truth_without_opening_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_population = (cached_source_population_row(),)
    ground_truth = source_population[0].ground_truth_innerdict()
    assert ground_truth is not None
    configuration = context_models.AiAugmentControlCentreContext.model_construct(
        pipeline_config=AiAugmentDetourConfig.model_construct(),  # type: ignore[call-arg]
        cached_ai_augment_outerdicts=source_population,
    )
    subject = control_ui._SourceRepository(
        configuration=configuration,
    )

    assert subject.load_ground_truth_by_namekey() == {
        NAMEKEY.to_json_key(): ground_truth
    }
    assert subject.load_ground_truth(NAMEKEY) == ground_truth


@pytest.mark.anyio
async def test_dashboard_start_prepares_population_and_ground_truth_before_worker(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = researcher(cohort=AiAugmentCohort.GROUND_TRUTH)
    ground_truth = source.ground_truth_innerdict()
    assert ground_truth is not None
    required_ground_truth = ground_truth
    order: list[str] = []

    class ObservedSourceRepository(FakeSourceRepository):
        def load_researchers(self) -> tuple[AiAugmentOuterDict, ...]:
            order.append("source-population")
            return (source,)

        def load_ground_truth_by_namekey(
            self,
        ) -> dict[str, InnerDict]:
            order.append("linked-ground-truth")
            return {source.namekey.to_json_key(): required_ground_truth}

    subject = control_ui._ControlCentreController(
        source_repository=cast(control_ui._SourceRepository, ObservedSourceRepository()),
        backend=cast(control_ui._BackendSupervisor, FakeBackend(order)),
        backend_database=cast(control_ui._BackendDatabaseClient, FakeBackendDatabase()),
        codex=cast(control_ui._CodexRunner, FakeCodex(order)),
        reconciler=control_ui._AttemptReconciler(),
        projector=control_ui._VariableProjector(),
    )

    async def in_event_loop(function: Any, /, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    async def observed_worker() -> None:
        order.append("worker")

    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)
    monkeypatch.setattr(subject, "_worker", observed_worker)

    await subject.start()
    await asyncio.sleep(0)
    await subject.shutdown()

    assert order[:3] == ["source-population", "linked-ground-truth", "worker"]
    assert subject._researchers == (source,)
    assert subject._ground_truth == {source.namekey.to_json_key(): ground_truth}
    startup_log = capsys.readouterr().out
    logged_stages = [
        "preparing source population",
        "source population ready: 1 researcher(s)",
        "preparing linked ground truth",
        "linked ground truth ready: 1 researcher(s)",
        "restoring persisted Dashboard state",
        "persisted Dashboard state restored",
        "checking Backend API and IPC availability",
        "Backend API unavailable; IPC unavailable",
        "queue worker ready",
    ]
    offsets = [startup_log.index(stage) for stage in logged_stages]
    assert offsets == sorted(offsets)


@pytest.mark.anyio
async def test_application_startup_publishes_cached_services_only_after_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fingerprint = source_input_fingerprint()
    source_population = (cached_source_population_row(),)
    order: list[str] = []

    class FakeController:
        async def start(self) -> None:
            assert control_ui.SERVICES is None
            order.append("controller-ready")

        async def shutdown(self) -> None:
            order.append("controller-stopped")

    services = cast(
        control_ui._ApplicationServices,
        SimpleNamespace(
            controller=FakeController(),
            source_repository=SimpleNamespace(
                ai_augment_outerdicts=source_population,
            ),
        ),
    )
    monkeypatch.setattr(control_ui, "SERVICES", None)
    monkeypatch.setattr(control_ui, "APPLICATION_CONFIG_PATH", tmp_path / "config.json")

    def create_services(
        *,
        config_path: Path,
    ) -> tuple[
        control_ui._ApplicationServices,
        control_ui._SourceInputFingerprint,
        tuple[AiAugmentOuterDict, ...],
    ]:
        assert config_path == tmp_path / "config.json"
        order.append("services-created")
        return services, fingerprint, source_population

    monkeypatch.setattr(control_ui, "create_services", create_services)
    monkeypatch.setattr(
        control_ui,
        "store_cached_source_data",
        lambda **_kwargs: pytest.fail("a matching cache must not be replaced"),
    )

    await control_ui.application_startup()

    assert order == ["services-created", "controller-ready"]
    assert control_ui.SERVICES is services
    assert capsys.readouterr().out.splitlines() == [
        "[control-centre] checking cached source data",
        "[control-centre] cached source data matches configured inputs",
        f"[control-centre] ready at {control_vars.CONTROL_CENTRE_BASE_URL}",
    ]


@pytest.mark.anyio
async def test_application_startup_updates_source_cache_before_publishing_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fingerprint = source_input_fingerprint()
    source_population = (cached_source_population_row(),)
    order: list[str] = []

    class FakeController:
        async def start(self) -> None:
            assert control_ui.SERVICES is None
            order.append("controller-ready")

        async def shutdown(self) -> None:
            order.append("controller-stopped")

    services = cast(
        control_ui._ApplicationServices,
        SimpleNamespace(
            controller=FakeController(),
            source_repository=SimpleNamespace(
                ai_augment_outerdicts=source_population,
            ),
        ),
    )
    monkeypatch.setattr(control_ui, "SERVICES", None)
    monkeypatch.setattr(control_ui, "APPLICATION_CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(
        control_ui,
        "create_services",
        lambda **_kwargs: (services, fingerprint, None),
    )

    def store_cache(**kwargs: object) -> None:
        assert control_ui.SERVICES is None
        assert kwargs == {
            "fingerprint": fingerprint,
            "ai_augment_outerdicts": source_population,
        }
        order.append("cache-updated")

    monkeypatch.setattr(control_ui, "store_cached_source_data", store_cache)

    await control_ui.application_startup()

    assert order == ["controller-ready", "cache-updated"]
    assert control_ui.SERVICES is services


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
async def test_dashboard_start_detects_backend_availability_without_querying_history(
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
        assert subject.backend_status is expected_status
        assert subject.backend_availability == control_ui._BackendAvailability(
            full_api_available=full_api_available,
            ipc_available=ipc_available,
        )
        assert backend_database.pull_calls == 0
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
        assert subject.backend_availability == control_ui._BackendAvailability(
            full_api_available=False,
            ipc_available=False,
        )

        backend.api_available = True
        backend_database.ipc_available = True
        availability = await subject.detect_backend_availability()

        assert availability == control_ui._BackendAvailability(
            full_api_available=True,
            ipc_available=True,
        )
        assert subject.backend_status is control_ui._BackendStatus.RUNNING_EXTERNALLY
        assert backend_database.pull_calls == 0
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_page_shows_backend_and_ipc_separately_and_gates_refresh() -> None:
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
        ) -> control_ui._UiSnapshot:
            del selection
            return control_ui._UiSnapshot(
                counts=control_ui._DashboardCounts(
                    total=0,
                    ground_truth=0,
                    no_ground_truth=0,
                    ineligible=0,
                    ready=0,
                    queued=0,
                    running=0,
                    complete=0,
                    failed=0,
                    cancelled=0,
                ),
                rows=(),
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
        reference_docx=Path("unused.docx"),
    )
    subject._handles.backend_status_label = backend_label
    subject._handles.backend_ipc_status_label = ipc_label
    subject._handles.backend_refresh_button = refresh_button

    await subject.refresh()

    assert backend_label.text == "Backend API: running externally"
    assert ipc_label.text == "IPC: unavailable"
    assert refresh_button.enabled is False

    controller.backend_availability = control_ui._BackendAvailability(
        full_api_available=False,
        ipc_available=True,
    )
    await subject.refresh()

    assert backend_label.text == "Backend API: stopped"
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
    attempt = agent_runtime_attempt()
    backend_database.response = QueryResponse(
        attempts=(attempt,),
        ai_augment_outerdicts=(),
    )
    subject = controller(backend_database=backend_database)

    await subject.start()
    try:
        assert subject.backend_status is control_ui._BackendStatus.STOPPED
        assert subject.backend_availability == control_ui._BackendAvailability(
            full_api_available=False,
            ipc_available=True,
        )
        assert backend_database.pull_calls == 0

        await subject.refresh_from_ipc()

        assert backend_database.pull_calls == 1
        assert subject._attempt_records == {NAMEKEY.to_json_key(): (attempt,)}
        assert app.storage.general[control_ui.BACKEND_DATABASE_STORAGE_KEY] == (
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
        def pull(self) -> QueryResponse:
            raise OSError("IPC query failed")

    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)
    subject = controller(
        backend=FakeBackend(full_api_available=True),
        backend_database=FailingBackendDatabase(available=True),
    )

    await subject.start()
    try:
        assert subject.backend_availability == control_ui._BackendAvailability(
            full_api_available=True,
            ipc_available=True,
        )

        with pytest.raises(OSError, match="IPC query failed"):
            await subject.refresh_from_ipc()

        assert subject.backend_availability == control_ui._BackendAvailability(
            full_api_available=True,
            ipc_available=True,
        )
        assert subject.backend_status is control_ui._BackendStatus.RUNNING_EXTERNALLY
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_dashboard_start_restores_refreshed_backend_data_without_querying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def in_event_loop(function: Any, /, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)
    attempt = agent_runtime_attempt()
    app.storage.general[control_ui.BACKEND_DATABASE_STORAGE_KEY] = QueryResponse(
        attempts=(attempt,),
        ai_augment_outerdicts=(),
    ).model_dump(mode="json")
    backend_database = FakeBackendDatabase()
    subject = controller(backend_database=backend_database)

    await subject.start()
    try:
        assert backend_database.pull_calls == 0
        assert subject._attempt_records == {NAMEKEY.to_json_key(): (attempt,)}
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
            ai_augment_outerdicts=(),
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
    response = client.pull()

    assert response == QueryResponse(
        attempts=(),
        ai_augment_outerdicts=(),
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
    attempt = control_ui._AttemptView(
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
    subject = controller(backend=backend, backend_database=backend_database)
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
    response = subject._run_outcome_responses[NAMEKEY.to_json_key()][-1]
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
    reconciled = control_ui._AttemptReconciler().reconcile(
        researcher=researcher(),
        runs=tuple(subject._runs.values()),
        attempt_records=(),
        committed_innerdicts=(),
        run_outcome_responses=subject._run_outcome_responses[NAMEKEY.to_json_key()],
    )
    assert reconciled.latest_attempt is not None
    assert reconciled.latest_attempt.lifecycle is RunLifecycle.FAILED
    assert reconciled.latest_attempt.run_outcome_response is response
    assert reconciled.latest_attempt.run_outcome_saved is False
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
        pipeline_config=configured_pipeline_config(),
    )

    assert subject.full_api_available() is True
    assert observed_timeouts == [control_vars.BACKEND_AVAILABILITY_TIMEOUT_SECONDS]
    assert control_vars.BACKEND_AVAILABILITY_TIMEOUT_SECONDS < 1


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
    subject._researchers_by_namekey = {source.namekey.to_json_key(): source}

    run_id = await subject.queue(namekey=source.namekey)

    assert run_id.version == 7
    assert app.storage.general[control_ui.QUEUE_STORAGE_KEY] == [str(run_id)]
    stored_events = app.storage.general[control_ui.RUN_EVENTS_STORAGE_KEY]
    assert [event["lifecycle"] for event in stored_events] == [
        RunLifecycle.QUEUED.value
    ]
    assert backend_database.pull_calls == 0


@pytest.mark.anyio
async def test_queued_cancellation_removes_persisted_queue_without_starting_processes() -> None:
    backend = FakeBackend()
    codex = FakeCodex()
    subject = controller(backend=backend, codex=codex)
    source = researcher()
    subject._researchers_by_namekey = {source.namekey.to_json_key(): source}
    run_id = await subject.queue(namekey=source.namekey)

    await subject.cancel(run_id=run_id)

    assert app.storage.general[control_ui.QUEUE_STORAGE_KEY] == []
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
    app.storage.general[control_ui.RUN_EVENTS_STORAGE_KEY] = [event.model_dump(mode="json")]
    app.storage.general[control_ui.QUEUE_STORAGE_KEY] = [str(run_id)]
    subject = controller()

    subject._load_dashboard_storage()

    assert subject._runs[run_id].lifecycle is RunLifecycle.QUEUED
    assert subject._runs[run_id].run_outcome is None
    assert app.storage.general[control_ui.QUEUE_STORAGE_KEY] == [str(run_id)]


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
    subject._researchers_by_namekey = {
        first.namekey.to_json_key(): first,
        second.namekey.to_json_key(): second,
    }

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
    subject._researchers_by_namekey = {source.namekey.to_json_key(): source}
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
    subject._researchers_by_namekey = {source.namekey.to_json_key(): source}
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
    subject._researchers_by_namekey = {source.namekey.to_json_key(): source}

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
    subject._researchers_by_namekey = {source.namekey.to_json_key(): source}
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
    subject._researchers_by_namekey = {source.namekey.to_json_key(): source}
    run_id = await subject.queue(namekey=source.namekey)
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
async def test_backend_acceptance_remains_running_until_codex_exits(
    inline_controller_io: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid7()
    accepted_commit_record_id = uuid7()
    accepted_value = "Professor Sir Aziz Sheikh OBE"
    variable = control_ui.VARIABLE_SPECS[0]
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
    subject = controller(
        backend=FakeBackend(order),
        backend_database=backend_database,
        codex=BlockingCodex(order),
    )
    source = researcher()
    subject._researchers = (source,)
    subject._researchers_by_namekey = {source.namekey.to_json_key(): source}
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
                variable.ai_column: accepted_value,
                KTP_AI_AUGMENT_FOOTNOTES_COL: None,
                KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL: None,
            },
            api._CodexMatchProcedure(),
        ),
        commit_record=accepted_attempt.attempt.commit_record,
    )
    source.committed_innerdicts = (accepted,)
    subject._attempt_records = {NAMEKEY.to_json_key(): (accepted_attempt,)}
    subject._committed_innerdicts = {NAMEKEY.to_json_key(): (accepted,)}
    backend_database.response = QueryResponse(
        attempts=(accepted_attempt,),
        ai_augment_outerdicts=(source,),
    )

    async def preserve_backend_snapshot() -> None:
        return None

    async def accepted_attempt_for_session(
        *,
        namekey: NameKey,
        session_id: UUID,
    ) -> CommittedInnerDict | None:
        assert namekey == NAMEKEY
        assert session_id == SESSION_ID
        return accepted

    monkeypatch.setattr(subject, "refresh_idle_state", preserve_backend_snapshot)
    monkeypatch.setattr(
        subject,
        "_accepted_attempt_for_session",
        accepted_attempt_for_session,
    )
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
    running = await subject.snapshot(selection=control_ui._UiSelection(variable_key=variable.key))

    assert running.counts.running == 1
    assert running.counts.complete == 0
    assert len(running.rows) == 1
    assert running.rows[0].latest.attempt_lifecycle is RunLifecycle.RUNNING
    assert running.rows[0].latest.ai_value is None

    allow_codex_exit.set()
    await execution
    completed = await subject.snapshot(selection=control_ui._UiSelection(variable_key=variable.key))

    assert completed.counts.running == 0
    assert completed.counts.complete == 1
    assert completed.rows[0].latest.attempt_lifecycle is RunLifecycle.COMPLETED
    assert completed.rows[0].latest.ai_value == accepted_value
    assert [event.lifecycle for event in subject._events][-3:] == [
        RunLifecycle.CODEX_EXITED,
        RunLifecycle.PUSH_ACCEPTED,
        RunLifecycle.COMPLETED,
    ]
    assert order[-1] == f"run-outcome:{run_outcome_models.COMPLETED_PATH}"


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


class FakeProcess:
    def __init__(self) -> None:
        self.pid = 12345
        self.stdin = FakeInputStream()
        self.stdout = EmptyAsyncLines()
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
        pipeline_config=configured_pipeline_config(),
    )

    await subject.start(namekey=NAMEKEY)
    first_process = calls[0][2]
    await subject.supply_session_id(SESSION_ID)
    with pytest.raises(RuntimeError, match=Locale.BACKEND_ALREADY_OWNED):
        await subject.start(namekey=SECOND_NAMEKEY)

    assert len(calls) == 1
    assert first_process.returncode is None
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
            status.HTTP_200_OK
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
        pipeline_config=configured_pipeline_config(),
    )
    subject._process = cast(
        Any,
        SimpleNamespace(process=SimpleNamespace(returncode=None)),
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
