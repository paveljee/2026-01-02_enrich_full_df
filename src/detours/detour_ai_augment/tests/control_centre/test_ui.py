from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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
    def __init__(self) -> None:
        self.pull_calls = 0

    def pull(self) -> SimpleNamespace:
        self.pull_calls += 1
        return SimpleNamespace(attempts=(), accepted_attempts=())


class FakeBackend:
    def __init__(self, order: list[str] | None = None) -> None:
        self.order = [] if order is None else order
        self.started_namekeys: list[control_ui.Namekey] = []
        self.supplied_session_ids: list[control_ui.SessionId] = []
        self.status = control_ui.BackendStatus.STOPPED

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

    async def wait(self, _handle: object) -> int:
        self.order.append("codex-wait")
        return 0

    async def cancel(self, _handle: object) -> None:
        return None

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


def test_dashboard_paths_resolve_from_repository_root(repository_root: Path) -> None:
    assert control_vars.REPOSITORY_ROOT == repository_root
    assert control_ui.REPOSITORY_ROOT == repository_root
    assert control_vars.DEFAULT_CONFIG_PATH == repository_root / "config_ai_augment.json"


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

    response = control_ui.BackendDatabaseClient(socket_path=socket_path).pull()

    assert response == api.DashboardQueryResponse(
        attempts=(),
        accepted_attempts=(),
        card_markdown=None,
    )
    assert calls == [
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
async def test_backend_supervisor_replaces_process_per_namekey_and_uses_stdin(
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
        appendwatch_report=tmp_path / "appendwatch.txt",
        dashboard_socket_path=tmp_path / "dashboard.sock",
    )

    await subject.start(namekey=NAMEKEY)
    first_process = calls[0][2]
    await subject.supply_session_id(SESSION_ID)
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
        appendwatch_report=tmp_path / "appendwatch.txt",
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

    async def write_remote_file(_path: PurePosixPath, _content: bytes) -> None:
        return None

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
        openalex_api_key="key",
    )
    monkeypatch.setattr(runner, "_write_remote_file", write_remote_file)
    monkeypatch.setattr(runner, "_remote_command", remote_command)
    monkeypatch.setattr(runner, "discover_session", discover_session)
    monkeypatch.setattr(runner, "discover_rollout_path", discover_rollout_path)

    await runner.start(run_id=uuid4())
    await runner.start(run_id=uuid4())

    assert len(process_calls) == 2
    assert all("resume" not in " ".join(map(str, call)) for call in process_calls)
    assert [process.stdin.writes for process in processes] == [
        [f"{control_ui.BACKEND_OPENAPI_URL}\n".encode()],
        [f"{control_ui.BACKEND_OPENAPI_URL}\n".encode()],
    ]


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
        openalex_api_key="key",
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
