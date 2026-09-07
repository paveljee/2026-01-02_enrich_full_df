from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from nicegui import app

from src.detours.detour_ai_augment.src.backend import api
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers import (
    vars as control_vars,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    ai_augment_context as context_models,
)

NAMEKEY = control_ui.Namekey("Jane Doe [1]")
SECOND_NAMEKEY = control_ui.Namekey("John Doe [2]")
SESSION_ID = control_ui.SessionId("019fb000-0000-7000-8000-000000000001")
SESSION_TIMESTAMP = datetime(2026, 8, 7, tzinfo=timezone.utc)
ROLLOUT_PATH = PurePosixPath(
    "/home/ai/.codex/sessions/2026/08/07/"
    "rollout-2026-08-07T00-00-00-019fb000-0000-7000-8000-000000000001.jsonl"
)


@pytest.fixture(autouse=True)
def isolated_general_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.storage, "_general", {})


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def researcher(namekey: control_ui.Namekey = NAMEKEY) -> control_ui.Researcher:
    return control_ui.Researcher(
        namekey=namekey,
        rnd=1,
        draw_numbers=("1",),
        first_name="Jane",
        last_name="Doe",
        cohort=control_ui.ResearcherCohort.NO_GROUND_TRUTH,
    )


class FakeSourceRepository:
    def __init__(self) -> None:
        self.researchers = (researcher(),)

    def load_researchers(self) -> tuple[control_ui.Researcher, ...]:
        return self.researchers

    def load_ground_truth_by_namekey(
        self,
    ) -> dict[control_ui.Namekey, control_ui.GroundTruthRecord]:
        return {}


class FakeBackendDatabase:
    def __init__(self, *, available: bool = False) -> None:
        self.pull_calls = 0
        self.ipc_available = available
        self.response = api.DashboardQueryResponse(
            attempts=(),
            accepted_attempts=(),
        )

    def pull(self) -> api.DashboardQueryResponse:
        self.pull_calls += 1
        return self.response

    def available(self) -> bool:
        return self.ipc_available


class FakeBackend:
    def __init__(
        self,
        order: list[str] | None = None,
        *,
        full_api_available: bool = False,
    ) -> None:
        self.order = [] if order is None else order
        self.started_namekeys: list[control_ui.Namekey] = []
        self.supplied_session_ids: list[control_ui.SessionId] = []
        self.status = control_ui.BackendStatus.STOPPED
        self.api_available = full_api_available

    def full_api_available(self) -> bool:
        return self.api_available

    async def start(self, *, namekey: control_ui.Namekey) -> None:
        self.order.append("backend-start")
        self.started_namekeys.append(namekey)
        self.status = control_ui.BackendStatus.RUNNING

    async def probe_pull(self) -> None:
        self.order.append("backend-pull")

    async def supply_session_id(self, session_id: control_ui.SessionId) -> None:
        self.order.append("backend-session")
        self.supplied_session_ids.append(session_id)

    async def stop(self) -> None:
        self.order.append("backend-stop")
        self.status = control_ui.BackendStatus.STOPPED


class FakeCodex:
    def __init__(self, order: list[str] | None = None) -> None:
        self.order = [] if order is None else order

    async def is_busy(self) -> bool:
        return False

    async def start(
        self,
        *,
        run_id: UUID,
        on_handle: Any = None,
    ) -> SimpleNamespace:
        self.order.append("codex-start")
        handle = SimpleNamespace(
            run_id=run_id,
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

    async def terminate_abandoned_run(self, _run_id: UUID) -> None:
        return None


def controller(
    *,
    backend: FakeBackend | None = None,
    backend_database: FakeBackendDatabase | None = None,
    codex: FakeCodex | None = None,
) -> control_ui.ControlCentreController:
    return control_ui.ControlCentreController(
        source_repository=cast(control_ui.SourceRepository, FakeSourceRepository()),
        backend=cast(control_ui.BackendSupervisor, backend or FakeBackend()),
        backend_database=cast(
            control_ui.BackendDatabaseClient,
            backend_database or FakeBackendDatabase(),
        ),
        codex=cast(control_ui.CodexRunner, codex or FakeCodex()),
        reconciler=control_ui.AttemptReconciler(),
        projector=control_ui.VariableProjector(),
    )


def test_variable_specs_cover_every_ai_augment_column() -> None:
    assert tuple(item.ai_column for item in control_ui.VARIABLE_SPECS) == (
        api.AI_AUGMENT_COLUMNS
    )


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
    card = control_ui.ResearcherCardView(
        namekey=NAMEKEY,
        draw_number="1, pilot.2",
        first_name="Jane",
        last_name="Doe-Smith",
        markdown="## Exact displayed card\n\nbody\n",
    )
    subject = control_ui.ControlCentrePage(
        controller=cast(control_ui.ControlCentreController, object()),
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
    monkeypatch.setattr(control_ui.ui, "download", download)
    monkeypatch.setattr(control_ui.asyncio, "to_thread", in_event_loop)

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


def test_dashboard_paths_resolve_from_repository_root(repository_root: Path) -> None:
    assert control_vars.REPOSITORY_ROOT == repository_root
    assert control_ui.REPOSITORY_ROOT == repository_root
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
    pipeline_config = SimpleNamespace(
        db_file=source_db_path,
        sample_seed=42,
        timezone="UTC",
    )
    source_population = cast(tuple[Any, ...], (object(),))
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

    monkeypatch.setenv(context_models.EXPORT_OPENALEX_API_KEY, "host-openalex-key")
    monkeypatch.setattr(context_models, "LIMA_CONFIG_PATH", lima_config_path)
    monkeypatch.setattr(
        context_models.AiAugmentDetourConfig,
        "from_json",
        lambda _path: pipeline_config,
    )
    monkeypatch.setattr(context_models, "registered_release_map", lambda _config: {})
    monkeypatch.setattr(
        context_models,
        "load_release_batches",
        lambda _release_map: "release-batches",
    )
    monkeypatch.setattr(context_models, "derive_source_population", derive)
    monkeypatch.setattr(
        context_models,
        "eligible_cohorts",
        lambda population: {} if population is source_population else None,
    )
    monkeypatch.setattr(context_models.duckdb, "connect", connect)

    context = context_models.AiAugmentCtlCtrContext(config_path=tmp_path / "config.json")

    assert context.source_population is source_population
    assert context.source_db_path == source_db_path
    assert calls == [(str(source_db_path), True)]


@pytest.mark.anyio
async def test_dashboard_start_prepares_population_and_ground_truth_before_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = researcher()
    ground_truth = control_ui.GroundTruthRecord(namekey=source.namekey, values={})
    order: list[str] = []

    class ObservedSourceRepository(FakeSourceRepository):
        def load_researchers(self) -> tuple[control_ui.Researcher, ...]:
            order.append("source-population")
            return (source,)

        def load_ground_truth_by_namekey(
            self,
        ) -> dict[control_ui.Namekey, control_ui.GroundTruthRecord]:
            order.append("linked-ground-truth")
            return {source.namekey: ground_truth}

    subject = control_ui.ControlCentreController(
        source_repository=cast(control_ui.SourceRepository, ObservedSourceRepository()),
        backend=cast(control_ui.BackendSupervisor, FakeBackend(order)),
        backend_database=cast(control_ui.BackendDatabaseClient, FakeBackendDatabase()),
        codex=cast(control_ui.CodexRunner, FakeCodex(order)),
        reconciler=control_ui.AttemptReconciler(),
        projector=control_ui.VariableProjector(),
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
    assert subject._ground_truth == {source.namekey: ground_truth}


@pytest.mark.anyio
@pytest.mark.parametrize(
    (
        "full_api_available",
        "ipc_available",
        "expected_status",
    ),
    (
        (True, True, control_ui.BackendStatus.RUNNING_EXTERNALLY),
        (True, False, control_ui.BackendStatus.RUNNING_EXTERNALLY),
        (False, True, control_ui.BackendStatus.STOPPED),
        (False, False, control_ui.BackendStatus.STOPPED),
    ),
)
async def test_dashboard_start_detects_backend_availability_without_querying_history(
    monkeypatch: pytest.MonkeyPatch,
    full_api_available: bool,
    ipc_available: bool,
    expected_status: control_ui.BackendStatus,
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
        assert subject.backend_availability == control_ui.BackendAvailability(
            full_api_available=full_api_available,
            ipc_available=ipc_available,
        )
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
        backend_availability = control_ui.BackendAvailability(
            full_api_available=True,
            ipc_available=False,
        )

        async def snapshot(
            self,
            *,
            selection: control_ui.UiSelection,
        ) -> control_ui.UiSnapshot:
            del selection
            return control_ui.UiSnapshot(
                counts=control_ui.DashboardCounts(
                    total=0,
                    ground_truth=0,
                    no_ground_truth=0,
                    ineligible=0,
                    ready=0,
                    queued=0,
                    running=0,
                    complete=0,
                    failed=0,
                    canceled=0,
                ),
                rows=(),
                backend_status=(
                    control_ui.BackendStatus.RUNNING_EXTERNALLY
                    if self.backend_availability.full_api_available
                    else control_ui.BackendStatus.STOPPED
                ),
                backend_availability=self.backend_availability,
                active_run_id=None,
            )

    controller = Controller()
    backend_label = Label()
    ipc_label = Label()
    refresh_button = Button()
    subject = control_ui.ControlCentrePage(
        controller=cast(control_ui.ControlCentreController, controller),
        reference_docx=Path("unused.docx"),
    )
    subject._handles.backend_status_label = backend_label
    subject._handles.backend_ipc_status_label = ipc_label
    subject._handles.backend_refresh_button = refresh_button

    await subject.refresh()

    assert backend_label.text == "Backend API: running externally"
    assert ipc_label.text == "IPC: unavailable"
    assert refresh_button.enabled is False

    controller.backend_availability = control_ui.BackendAvailability(
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
    attempt = api.AttemptRecord(
        attempt_id="attempt-1",
        transaction_id=str(uuid4()),
        request_sha256="0" * 64,
        stage=api.ATTEMPT_STAGE_ACCEPTED,
        result=api.ATTEMPT_RESULT_ACCEPTED,
        updated_at=SESSION_TIMESTAMP,
        namekey=NAMEKEY,
        session_id=SESSION_ID,
        response_code=api.status.HTTP_410_GONE,
        response_body="accepted\n",
    )
    backend_database.response = api.DashboardQueryResponse(
        attempts=(attempt,),
        accepted_attempts=(),
    )
    subject = controller(backend_database=backend_database)

    await subject.start()
    try:
        assert subject.backend_status is control_ui.BackendStatus.STOPPED
        assert subject.backend_availability == control_ui.BackendAvailability(
            full_api_available=False,
            ipc_available=True,
        )
        assert backend_database.pull_calls == 0

        await subject.refresh_from_ipc()

        assert backend_database.pull_calls == 1
        assert subject._attempt_records == {NAMEKEY: (attempt,)}
        assert app.storage.general[control_ui.BACKEND_DATABASE_STORAGE_KEY] == (
            backend_database.response.model_dump(mode="json")
        )
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_dashboard_refresh_preserves_api_observation_when_ipc_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def in_event_loop(function: Any, /, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    class FailingBackendDatabase(FakeBackendDatabase):
        def pull(self) -> api.DashboardQueryResponse:
            raise OSError("IPC query failed")

    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)
    subject = controller(
        backend=FakeBackend(full_api_available=True),
        backend_database=FailingBackendDatabase(available=True),
    )

    await subject.start()
    try:
        assert subject.backend_availability == control_ui.BackendAvailability(
            full_api_available=True,
            ipc_available=True,
        )

        with pytest.raises(OSError, match="IPC query failed"):
            await subject.refresh_from_ipc()

        assert subject.backend_availability == control_ui.BackendAvailability(
            full_api_available=True,
            ipc_available=False,
        )
        assert subject.backend_status is control_ui.BackendStatus.RUNNING_EXTERNALLY
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_dashboard_start_restores_refreshed_backend_data_without_querying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def in_event_loop(function: Any, /, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)
    attempt = api.AttemptRecord(
        attempt_id="attempt-1",
        transaction_id=str(uuid4()),
        request_sha256="0" * 64,
        stage=api.ATTEMPT_STAGE_ACCEPTED,
        result=api.ATTEMPT_RESULT_ACCEPTED,
        updated_at=SESSION_TIMESTAMP,
        namekey=NAMEKEY,
        session_id=SESSION_ID,
        response_code=api.status.HTTP_410_GONE,
        response_body="accepted\n",
    )
    app.storage.general[control_ui.BACKEND_DATABASE_STORAGE_KEY] = (
        api.DashboardQueryResponse(
            attempts=(attempt,),
            accepted_attempts=(),
        ).model_dump(mode="json")
    )
    backend_database = FakeBackendDatabase()
    subject = controller(backend_database=backend_database)

    await subject.start()
    try:
        assert backend_database.pull_calls == 0
        assert subject._attempt_records == {NAMEKEY: (attempt,)}
    finally:
        await subject.shutdown()


@pytest.mark.anyio
async def test_failed_run_events_are_logged(
    capsys: pytest.CaptureFixture[str],
) -> None:
    subject = controller()
    run_id = uuid4()
    await subject._append_run_event(
        control_ui.RunEvent(
            run_id=run_id,
            namekey=NAMEKEY,
            at=SESSION_TIMESTAMP,
            kind=control_ui.RunEventKind.QUEUED,
        )
    )
    capsys.readouterr()
    event = control_ui.RunEvent(
        run_id=run_id,
        namekey=NAMEKEY,
        at=SESSION_TIMESTAMP,
        kind=control_ui.RunEventKind.FAILED,
        detail=control_ui.Locale.BACKEND_EXITED_EARLY,
    )

    await subject._append_run_event(event)

    assert capsys.readouterr().out == (
        f"{control_ui.Locale.CONTROL_CENTRE_LOG_PREFIX} run failed: "
        f"run_id={event.run_id} namekey={NAMEKEY} "
        f"detail={control_ui.Locale.BACKEND_EXITED_EARLY}\n"
    )


def test_backend_database_client_queries_unix_socket_without_authentication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, float, str, str]] = []
    response_body = api.DashboardQueryResponse(
        attempts=(),
        accepted_attempts=(),
        card_markdown=None,
    ).model_dump_json().encode()

    class FakeResponse:
        status = api.status.HTTP_200_OK

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

    monkeypatch.setattr(control_ui, "UnixSocketHttpConnection", FakeConnection)
    socket_path = tmp_path / "dashboard.sock"
    client = control_ui.BackendDatabaseClient(socket_path=socket_path)

    assert client.available() is True
    response = client.pull()

    assert response == api.DashboardQueryResponse(
        attempts=(),
        accepted_attempts=(),
        card_markdown=None,
    )
    assert calls == [
        (
            socket_path,
            control_ui.CONTROL_HTTP_TIMEOUT_SECONDS,
            control_ui.HTTP_OPTIONS_METHOD,
            api.DASHBOARD_QUERY_PATH,
        ),
        (
            socket_path,
            control_ui.CONTROL_HTTP_TIMEOUT_SECONDS,
            control_ui.HTTP_GET_METHOD,
            api.DASHBOARD_QUERY_PATH,
        )
    ]


def test_run_event_replay_keeps_dashboard_queue_ownership() -> None:
    run_id = uuid4()
    queued = control_ui.RunEvent(
        run_id=run_id,
        namekey=NAMEKEY,
        at=SESSION_TIMESTAMP,
        kind=control_ui.RunEventKind.QUEUED,
    )
    started = control_ui.RunEvent(
        run_id=run_id,
        namekey=NAMEKEY,
        at=SESSION_TIMESTAMP,
        kind=control_ui.RunEventKind.STARTED,
    )

    run = control_ui.replay_run_events((queued, started))[run_id]

    assert run.dashboard_owned is True
    assert run.status is control_ui.RunStatus.RUNNING
    assert run.started_at == SESSION_TIMESTAMP


@pytest.mark.anyio
async def test_queue_is_persisted_only_in_nicegui_general_storage() -> None:
    backend_database = FakeBackendDatabase()
    subject = controller(backend_database=backend_database)
    source = researcher()
    subject._researchers_by_namekey = {source.namekey: source}

    run_id = await subject.queue(namekey=source.namekey)

    assert run_id.version == 7
    assert app.storage.general[control_ui.QUEUE_STORAGE_KEY] == [str(run_id)]
    stored_events = app.storage.general[control_ui.RUN_EVENTS_STORAGE_KEY]
    assert [event["kind"] for event in stored_events] == [
        control_ui.RunEventKind.QUEUED.value
    ]
    assert backend_database.pull_calls == 0


@pytest.mark.anyio
async def test_queued_cancellation_removes_persisted_queue_without_starting_processes() -> None:
    backend = FakeBackend()
    codex = FakeCodex()
    subject = controller(backend=backend, codex=codex)
    source = researcher()
    subject._researchers_by_namekey = {source.namekey: source}
    run_id = await subject.queue(namekey=source.namekey)

    await subject.cancel(run_id=run_id)

    assert app.storage.general[control_ui.QUEUE_STORAGE_KEY] == []
    assert subject._runs[run_id].status is control_ui.RunStatus.CANCELED
    assert backend.started_namekeys == []
    assert codex.order == []


def test_dashboard_queue_and_journal_survive_controller_reconstruction() -> None:
    run_id = uuid4()
    event = control_ui.RunEvent(
        run_id=run_id,
        namekey=NAMEKEY,
        at=SESSION_TIMESTAMP,
        kind=control_ui.RunEventKind.QUEUED,
    )
    app.storage.general[control_ui.RUN_EVENTS_STORAGE_KEY] = [
        event.model_dump(mode="json")
    ]
    app.storage.general[control_ui.QUEUE_STORAGE_KEY] = [str(run_id)]
    subject = controller()

    subject._load_dashboard_storage()

    assert subject._runs[run_id].status is control_ui.RunStatus.QUEUED
    assert app.storage.general[control_ui.QUEUE_STORAGE_KEY] == [str(run_id)]


@pytest.mark.anyio
async def test_execution_starts_fresh_backend_before_codex_and_hands_off_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    backend = FakeBackend(order)
    codex = FakeCodex(order)
    subject = controller(backend=backend, codex=codex)
    run_id = uuid4()
    await subject._append_run_event(
        control_ui.RunEvent(
            run_id=run_id,
            namekey=NAMEKEY,
            at=SESSION_TIMESTAMP,
            kind=control_ui.RunEventKind.QUEUED,
        )
    )
    subject._active_run_id = run_id

    async def complete_run(
        _subject: control_ui.ControlCentreController,
        *,
        run_id: UUID,
        codex_exit_code: int,
    ) -> control_ui.RunStatus:
        assert run_id
        assert codex_exit_code == 0
        return control_ui.RunStatus.COMPLETE

    monkeypatch.setattr(control_ui.ControlCentreController, "_finalize_run", complete_run)

    await subject._execute_run(run_id=run_id)

    assert order[:4] == [
        "backend-start",
        "codex-start",
        "backend-session",
        "codex-wait",
    ]
    assert backend.started_namekeys == [NAMEKEY]
    assert backend.supplied_session_ids == [SESSION_ID]
    assert [event.kind for event in subject._events].count(
        control_ui.RunEventKind.SESSION_DISCOVERED
    ) == 1
    assert [event.kind for event in subject._events][-2:] == [
        control_ui.RunEventKind.CODEX_EXITED,
        control_ui.RunEventKind.COMPLETE,
    ]
    assert subject._runs[run_id].codex_exit_code == 0
    assert subject._runs[run_id].status is control_ui.RunStatus.COMPLETE


@pytest.mark.anyio
async def test_worker_stops_backend_before_starting_next_queued_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    backend = FakeBackend(order)
    codex = FakeCodex(order)
    subject = controller(backend=backend, codex=codex)
    first = researcher()
    second = researcher(SECOND_NAMEKEY)
    subject._researchers_by_namekey = {
        first.namekey: first,
        second.namekey: second,
    }

    async def complete_run(
        _subject: control_ui.ControlCentreController,
        *,
        run_id: UUID,
        codex_exit_code: int,
    ) -> control_ui.RunStatus:
        assert run_id in subject._runs
        assert codex_exit_code == 0
        return control_ui.RunStatus.COMPLETE

    monkeypatch.setattr(control_ui.ControlCentreController, "_finalize_run", complete_run)
    first_run_id = await subject.queue(namekey=first.namekey)
    second_run_id = await subject.queue(namekey=second.namekey)

    assert await subject._queue.get() == first_run_id
    await subject._process_queued_run(first_run_id)
    assert await subject._queue.get() == second_run_id
    await subject._process_queued_run(second_run_id)

    assert backend.started_namekeys == [first.namekey, second.namekey]
    assert order == [
        "backend-start",
        "codex-start",
        "backend-session",
        "codex-wait",
        "backend-stop",
        "backend-start",
        "codex-start",
        "backend-session",
        "codex-wait",
        "backend-stop",
    ]


@pytest.mark.anyio
async def test_backend_start_failure_still_winds_down_owned_processes() -> None:
    order: list[str] = []

    class FailingBackend(FakeBackend):
        async def start(self, *, namekey: control_ui.Namekey) -> None:
            self.order.append("backend-start")
            self.started_namekeys.append(namekey)
            raise RuntimeError("backend start failed")

    backend = FailingBackend(order)
    subject = controller(backend=backend, codex=FakeCodex(order))
    source = researcher()
    subject._researchers_by_namekey = {source.namekey: source}
    run_id = await subject.queue(namekey=source.namekey)

    assert await subject._queue.get() == run_id
    await subject._process_queued_run(run_id)

    assert subject._runs[run_id].status is control_ui.RunStatus.FAILED
    assert order == ["backend-start", "backend-stop"]


@pytest.mark.anyio
async def test_codex_start_failure_stops_registered_codex_then_backend() -> None:
    order: list[str] = []

    class FailingCodex(FakeCodex):
        async def start(
            self,
            *,
            run_id: UUID,
            on_handle: Any = None,
        ) -> SimpleNamespace:
            self.order.append("codex-start")
            handle = SimpleNamespace(
                run_id=run_id,
                remote_pid=None,
                process=SimpleNamespace(returncode=None),
            )
            assert on_handle is not None
            await on_handle(handle)
            raise RuntimeError("Codex start failed")

    backend = FakeBackend(order)
    subject = controller(backend=backend, codex=FailingCodex(order))
    source = researcher()
    subject._researchers_by_namekey = {source.namekey: source}
    run_id = await subject.queue(namekey=source.namekey)

    assert await subject._queue.get() == run_id
    await subject._process_queued_run(run_id)

    assert subject._runs[run_id].status is control_ui.RunStatus.FAILED
    assert order == [
        "backend-start",
        "codex-start",
        "codex-cancel",
        "backend-stop",
    ]


@pytest.mark.anyio
async def test_failed_finalization_stops_backend_after_terminal_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    backend = FakeBackend(order)
    subject = controller(backend=backend, codex=FakeCodex(order))
    source = researcher()
    subject._researchers_by_namekey = {source.namekey: source}

    async def fail_run(
        _subject: control_ui.ControlCentreController,
        *,
        run_id: UUID,
        codex_exit_code: int,
    ) -> control_ui.RunStatus:
        assert run_id in subject._runs
        assert codex_exit_code == 0
        assert backend.status is control_ui.BackendStatus.RUNNING
        return control_ui.RunStatus.FAILED

    monkeypatch.setattr(control_ui.ControlCentreController, "_finalize_run", fail_run)
    run_id = await subject.queue(namekey=source.namekey)

    assert await subject._queue.get() == run_id
    await subject._process_queued_run(run_id)

    assert subject._runs[run_id].status is control_ui.RunStatus.FAILED
    assert [event.kind for event in subject._events][-2:] == [
        control_ui.RunEventKind.CODEX_EXITED,
        control_ui.RunEventKind.FAILED,
    ]
    assert order[-1] == "backend-stop"


@pytest.mark.anyio
async def test_active_cancellation_stops_codex_then_backend() -> None:
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
    subject = controller(backend=backend, codex=BlockingCodex(order))
    source = researcher()
    subject._researchers_by_namekey = {source.namekey: source}
    run_id = await subject.queue(namekey=source.namekey)
    worker = asyncio.create_task(subject._worker())
    try:
        await asyncio.wait_for(codex_waiting.wait(), timeout=1)
        await subject.cancel(run_id=run_id)
        await asyncio.wait_for(backend_stopped.wait(), timeout=1)
        await asyncio.wait_for(subject._queue.join(), timeout=1)
    finally:
        subject._shutting_down = True
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker

    assert subject._runs[run_id].status is control_ui.RunStatus.CANCELED
    assert order[-2:] == ["codex-cancel", "backend-stop"]


@pytest.mark.anyio
async def test_dashboard_shutdown_stops_inflight_codex_and_backend() -> None:
    order: list[str] = []
    codex_waiting = asyncio.Event()

    class BlockingCodex(FakeCodex):
        async def wait(self, _handle: object) -> int:
            self.order.append("codex-wait")
            codex_waiting.set()
            await asyncio.Event().wait()
            return 0

    backend = FakeBackend(order)
    subject = controller(backend=backend, codex=BlockingCodex(order))
    source = researcher()
    subject._researchers_by_namekey = {source.namekey: source}
    run_id = await subject.queue(namekey=source.namekey)
    subject._worker_task = asyncio.create_task(subject._worker())

    await asyncio.wait_for(codex_waiting.wait(), timeout=1)
    await subject.shutdown()

    assert subject._runs[run_id].status is control_ui.RunStatus.FAILED
    assert order.index("codex-cancel") < order.index("backend-stop")
    assert order[-1] == "backend-stop"
    assert backend.status is control_ui.BackendStatus.STOPPED


@pytest.mark.anyio
async def test_backend_acceptance_remains_running_until_codex_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    backend_run_id = uuid4()
    accepted_attempt_id = "01a068a7-0721-72e9-9439-dbdcd8ffc855"
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

    subject = controller(
        backend=FakeBackend(),
        codex=BlockingCodex(),
    )
    source = researcher()
    subject._researchers = (source,)
    subject._researchers_by_namekey = {source.namekey: source}
    accepted = control_ui.AcceptedAttempt(
        namekey=NAMEKEY,
        attempt_id=control_ui.AttemptId(accepted_attempt_id),
        session_metadata=control_ui.SessionMetadata(
            originator="codex_cli_rs",
            source="exec",
            cli_version="test",
            model_provider="openai",
            model="test-model",
            reasoning_effort="high",
            session_id=SESSION_ID,
            timestamp=SESSION_TIMESTAMP,
        ),
        values={variable.ai_column: accepted_value},
        footnotes=None,
        footnote_arguments=None,
    )
    subject._attempt_records = {
        NAMEKEY: (
            api.AttemptRecord(
                attempt_id=accepted_attempt_id,
                transaction_id=str(uuid4()),
                request_sha256="0" * 64,
                stage=api.ATTEMPT_STAGE_ACCEPTED,
                result=api.ATTEMPT_RESULT_ACCEPTED,
                updated_at=datetime.now(timezone.utc) + timedelta(minutes=1),
                run_id=backend_run_id,
                namekey=NAMEKEY,
                session_id=SESSION_ID,
                rollout_sha256="1" * 64,
                response_code=api.status.HTTP_410_GONE,
                response_body="accepted\n",
            ),
        )
    }
    subject._accepted_attempts = {NAMEKEY: (accepted,)}

    async def preserve_backend_snapshot() -> None:
        return None

    async def accepted_attempt_for_session(
        *,
        namekey: control_ui.Namekey,
        session_id: control_ui.SessionId,
    ) -> control_ui.AcceptedAttempt | None:
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
        control_ui.RunEvent(
            run_id=run_id,
            namekey=NAMEKEY,
            at=SESSION_TIMESTAMP,
            kind=control_ui.RunEventKind.QUEUED,
        )
    )
    subject._active_run_id = run_id

    execution = asyncio.create_task(subject._execute_run(run_id=run_id))
    await codex_waiting.wait()
    running = await subject.snapshot(
        selection=control_ui.UiSelection(variable_key=variable.key)
    )

    assert running.counts.running == 1
    assert running.counts.complete == 0
    assert len(running.rows) == 1
    assert running.rows[0].latest.attempt_status is control_ui.RunStatus.RUNNING
    assert running.rows[0].latest.ai_value is None

    allow_codex_exit.set()
    await execution
    completed = await subject.snapshot(
        selection=control_ui.UiSelection(variable_key=variable.key)
    )

    assert completed.counts.running == 0
    assert completed.counts.complete == 1
    assert completed.rows[0].latest.attempt_status is control_ui.RunStatus.COMPLETE
    assert completed.rows[0].latest.ai_value == accepted_value
    assert [event.kind for event in subject._events][-3:] == [
        control_ui.RunEventKind.CODEX_EXITED,
        control_ui.RunEventKind.PUSH_ACCEPTED,
        control_ui.RunEventKind.COMPLETE,
    ]


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

    async def ready(_subject: control_ui.BackendSupervisor) -> None:
        return None

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(control_ui.BackendSupervisor, "wait_until_ready", ready)
    subject = control_ui.BackendSupervisor(
        repository_root=tmp_path,
        config_path=tmp_path / "config.json",
        openalex_api_key="key",
        appendwatch_report=PurePosixPath("/mounted/appendwatch.txt"),
        dashboard_socket_path=tmp_path / "dashboard.sock",
    )

    await subject.start(namekey=NAMEKEY)
    first_process = calls[0][2]
    await subject.supply_session_id(SESSION_ID)
    with pytest.raises(RuntimeError, match=control_ui.Locale.BACKEND_ALREADY_OWNED):
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
    assert first_environment[api.NAMEKEY_ENV_NAME] == NAMEKEY
    assert second_environment[api.NAMEKEY_ENV_NAME] == SECOND_NAMEKEY
    assert second_environment[api.CODEX_SESSIONS_ROOT_ENV_NAME] == str(
        control_ui.CODEX_SESSIONS_ROOT
    )
    assert second_environment[api.APPENDWATCH_REPORT_ENV_NAME] == (
        "/mounted/appendwatch.txt"
    )
    assert second_environment[api.DASHBOARD_SOCKET_PATH_ENV_NAME] == str(
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
        assert timeout == control_ui.CONTROL_HTTP_TIMEOUT_SECONDS
        url = cast(Any, request).full_url
        requested_urls.append(url)
        return FakeResponse(
            api.status.HTTP_200_OK
            if url == control_ui.BACKEND_OPENAPI_URL
            else api.status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    async def to_thread(function: Any, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(control_ui.urllib_request, "urlopen", urlopen)
    monkeypatch.setattr(control_ui.asyncio, "to_thread", to_thread)
    subject = control_ui.BackendSupervisor(
        repository_root=tmp_path,
        config_path=tmp_path / "config.json",
        openalex_api_key="key",
        appendwatch_report=PurePosixPath("/mounted/appendwatch.txt"),
        dashboard_socket_path=tmp_path / "dashboard.sock",
    )
    subject._process = cast(
        Any,
        SimpleNamespace(process=SimpleNamespace(returncode=None)),
    )

    with pytest.raises(RuntimeError, match=control_ui.Locale.BACKEND_PULL_NOT_READY):
        await asyncio.wait_for(subject.wait_until_ready(), timeout=1)

    assert requested_urls == [
        control_ui.BACKEND_OPENAPI_URL,
        control_ui.BACKEND_PULL_URL,
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
        _handle: control_ui.CodexProcessHandle,
    ) -> tuple[control_ui.SessionId, datetime]:
        return SESSION_ID, SESSION_TIMESTAMP

    async def discover_rollout_path(
        *,
        session_id: control_ui.SessionId,
        session_timestamp: datetime,
    ) -> PurePosixPath:
        assert session_id == SESSION_ID
        assert session_timestamp == SESSION_TIMESTAMP
        return ROLLOUT_PATH

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    runner = control_ui.CodexRunner(
        timezone=ZoneInfo("UTC"),
    )
    monkeypatch.setattr(runner, "_remote_command", remote_command)
    monkeypatch.setattr(runner, "discover_session", discover_session)
    monkeypatch.setattr(runner, "discover_rollout_path", discover_rollout_path)

    await runner.start(run_id=uuid4())
    await runner.start(run_id=uuid4())

    assert len(process_calls) == 2
    assert all("resume" not in " ".join(map(str, call)) for call in process_calls)
    assert all(str(control_ui.CODEX_ENV_PATH) in str(call[-1]) for call in process_calls)
    assert all("key" not in str(call[-1]) for call in process_calls)
    assert [process.stdin.writes for process in processes] == [
        [f"{control_ui.BACKEND_OPENAPI_URL}\n".encode()],
        [f"{control_ui.BACKEND_OPENAPI_URL}\n".encode()],
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
    runner = control_ui.CodexRunner(timezone=ZoneInfo("UTC"))

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
    assert commands == [control_ui.CODEX_REMOTE_BUSY_COMMAND]
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
    runner = control_ui.CodexRunner(
        timezone=ZoneInfo("UTC"),
    )

    async def terminate_remote_pid(value: control_ui.RemotePid) -> None:
        assert value == remote_pid

    monkeypatch.setattr(runner, "terminate_remote_pid", terminate_remote_pid)
    handle = control_ui.CodexProcessHandle(
        run_id=run_id,
        process=cast(Any, process),
        remote_pid=remote_pid,
        session_id=SESSION_ID,
    )

    await runner.cancel(handle)

    assert capsys.readouterr().out == (
        f"{control_ui.Locale.CONTROL_CENTRE_LOG_PREFIX} "
        "stopping recorded remote Codex process: "
        f"run_id={run_id} session_id={SESSION_ID} remote_pid={remote_pid}\n"
        f"{control_ui.Locale.CONTROL_CENTRE_LOG_PREFIX} "
        "recorded remote Codex process stopped: "
        f"run_id={run_id} remote_pid={remote_pid}\n"
        f"{control_ui.Locale.CONTROL_CENTRE_LOG_PREFIX} "
        f"stopping local Codex SSH process: run_id={run_id} pid={process.pid}\n"
        f"{control_ui.Locale.CONTROL_CENTRE_LOG_PREFIX} "
        f"local Codex SSH process stopped: run_id={run_id} pid={process.pid} "
        f"return_code={process.returncode}\n"
    )
