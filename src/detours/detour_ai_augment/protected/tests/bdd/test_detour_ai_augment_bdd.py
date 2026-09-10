from __future__ import annotations

import asyncio
import inspect
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from io import StringIO
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException, status
from fastapi.responses import Response
from nicegui import app
from pytest_bdd import given, scenario, then, when

from src.detours.detour_ai_augment.src.backend import api, ipc
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.server_event import (
    QueryResponse,
)
from src.detours.detour_ai_augment.src.backend.helpers.locale import Locale as BackendLocale
from src.detours.detour_ai_augment.src.backend.helpers.vars import AI_AUGMENT_COLUMNS
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers import (
    vars as control_vars,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    run_outcome as run_outcome_models,
)
from src.detours.detour_ai_augment.tests.backend import test_api as backend_support
from src.detours.detour_ai_augment.tests.backend import (
    test_appendwatch as appendwatch_support,
)
from src.detours.detour_ai_augment.tests.control_centre import test_ui as dashboard_support
from src.detours.detour_ai_augment.tests.operator import test_operator_e2e as operator_support
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

FEATURE_PATH = "features/detour_ai_augment_lifecycle.feature"
TEXT_ENCODING = "utf-8"
LIFECYCLE_ITEM_COUNT = 32

TRACEABILITY_SCENARIOS = {
    "Provisioning separates the runtime credentials and protected audit data": (1, 2, 3, 4),
    "Backend startup is exclusive and prepares one configured profile": (5, 6, 7, 8, 9, 32),
    "Dashboard owns only its private queue and processes one run at a time": (
        10,
        11,
        12,
        13,
        14,
    ),
    "A fresh Codex session can pull before session handoff": (15, 16, 17, 18, 19, 20, 21, 22),
    "Public exchanges are opaque validated durable and projected in order": (),
    "Accepted pushes commit validate retry terminate and replay": (23, 24, 25, 26, 27, 28, 29, 30),
    "Human-operated AIVM completes the Lifecycle and renders the researcher card": (31,),
}

PREAMBLE_PHRASES = (
    "acts either manually",
    "interactive",
    "non-interactive",
    "Multi-agent mode",
    "opaque to the client",
    'HttpRequestLogRecord(schema_version="1.1")',
    "UUIDv7",
    "appends, and `fsync`s",
    "every unprojected replay-log record in append order",
)


@dataclass(slots=True)
class LifecycleState:
    lifecycle_text: str = ""
    lifecycle_items: tuple[str, ...] = ()
    provisioning_files: dict[str, str] | None = None
    runtime: AiAugmentBackendContext | None = None
    backend_observations: dict[str, Any] | None = None
    dashboard_observations: dict[str, Any] | None = None
    session_observations: dict[str, Any] | None = None
    middleware_observations: dict[str, Any] | None = None
    captured_contour_passed: bool = False
    appendwatch_contour_passed: bool = False
    operator_contour_passed: bool = False


@pytest.fixture
def lifecycle_state() -> LifecycleState:
    return LifecycleState()


@pytest.fixture(autouse=True)
def isolate_lifecycle_process_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    monkeypatch.setattr(app.storage, "_general", {})
    monkeypatch.setattr(api, "BACKEND_PROCESS_LOCK_PATH", tmp_path / "backend.lock")
    api._release_backend_process_lock()
    api._release_authoritative_process_lock()
    api.close_backend_detour_database()
    monkeypatch.setattr(api, "BACKEND_SESSION_ID", None)
    monkeypatch.setattr(api, "BACKEND_CURRENT_PULL_RECORD_ID", None)
    monkeypatch.setattr(api, "BACKEND_PENDING_PULL_RECORD_ID", None)
    monkeypatch.setattr(api, "BACKEND_WORKFLOW_OUTCOME", None)
    monkeypatch.setattr(api, "BACKEND_WORKFLOW_STATUS", api.BackendWorkflowStatus.READY)
    yield
    api.close_backend_detour_database()
    api._release_authoritative_process_lock()
    api._release_backend_process_lock()


@pytest.fixture
def lifecycle_backend_paths(
    repository_root: Path,
    detour_root: Path,
) -> backend_support.BackendTestPaths:
    return backend_support.BackendTestPaths(
        config=repository_root / "config.repl.json",
        ai_augment_config=repository_root / "config_ai_augment.json",
        source_database=repository_root / "data" / "scisci_process.duckdb",
        reference_docx=repository_root / "resources" / "pandoc-custom-reference.docx",
        pydantic_to_paste=(
            detour_root / "src" / "backend" / "helpers" / "data_models" / "pydantic_to_paste.py"
        ),
        july_rollout=(
            detour_root
            / "data"
            / "sample_run"
            / ".codex"
            / "sessions"
            / Path(*backend_support.JULY_ROLLOUT_RELATIVE_PATH.parts)
        ),
        haanen_rejected_rollout=repository_root / "tmp" / "unused-rejected.jsonl",
        haanen_accepted_rollout=repository_root / "tmp" / "unused-accepted.jsonl",
    )


@pytest.fixture
def lifecycle_running_watchers() -> Iterator[list[appendwatch_support.RunningWatcher]]:
    running: list[appendwatch_support.RunningWatcher] = []
    yield running
    for watcher in running:
        if watcher.process.poll() is None:
            watcher.stop()


@pytest.fixture
def lifecycle_operator_runtime(
    tmp_path: Path,
    repository_root: Path,
) -> Iterator[operator_support.OperatorRuntime]:
    with tempfile.TemporaryDirectory(prefix="detour-bdd-operator-", dir="/tmp") as directory:
        socket_path = Path(directory) / "dashboard.sock"
        assert len(os.fsencode(socket_path)) < operator_support.DARWIN_AF_UNIX_PATH_CAPACITY_BYTES
        yield operator_support._operator_runtime(
            tmp_path,
            repository_root=repository_root,
            dashboard_socket_path=socket_path,
        )


@pytest.fixture(autouse=True)
def preserve_operator_production_data(
    request: pytest.FixtureRequest,
    operator_aivm: None,
    repository_root: Path,
    detour_root: Path,
) -> Iterator[None]:
    del operator_aivm
    if request.node.get_closest_marker("operator") is None:
        yield
        return
    directories = (repository_root / "data", detour_root / "data")
    operator_support._operator_log("hashing production data before the BDD scenario")
    before = {path: operator_support._tree_digest(path) for path in directories}
    yield
    operator_support._operator_log(
        "verifying production data remains unchanged after the BDD scenario",
        separate=True,
    )
    assert {path: operator_support._tree_digest(path) for path in directories} == before
    operator_support._operator_log("production data is unchanged")


@scenario(FEATURE_PATH, "Every Lifecycle statement has executable traceability")
def test_lifecycle_traceability() -> None:
    pass


@scenario(
    FEATURE_PATH,
    "Provisioning separates the runtime credentials and protected audit data",
)
def test_runtime_provisioning_contract() -> None:
    pass


@scenario(FEATURE_PATH, "Backend startup is exclusive and prepares one configured profile")
def test_backend_startup_contract() -> None:
    pass


@scenario(
    FEATURE_PATH,
    "Dashboard owns only its private queue and processes one run at a time",
)
def test_dashboard_orchestration_contract() -> None:
    pass


@scenario(FEATURE_PATH, "A fresh Codex session can pull before session handoff")
def test_session_handoff_contract() -> None:
    pass


@scenario(
    FEATURE_PATH,
    "Public exchanges are opaque validated durable and projected in order",
)
def test_authoritative_exchange_contract() -> None:
    pass


@scenario(FEATURE_PATH, "Accepted pushes commit validate retry terminate and replay")
def test_commit_validation_and_replay_contract() -> None:
    pass


@scenario(FEATURE_PATH, "Appendwatch fails closed across an inaccessible runtime path")
def test_appendwatch_privilege_contract() -> None:
    pass


@scenario(
    FEATURE_PATH,
    "Human-operated AIVM completes the Lifecycle and renders the researcher card",
)
def test_human_operated_lifecycle() -> None:
    pass


@given("the authoritative Lifecycle section")
def given_authoritative_lifecycle(
    lifecycle_state: LifecycleState,
    detour_root: Path,
) -> None:
    readme = (detour_root / "README.md").read_text(encoding=TEXT_ENCODING)
    lifecycle = readme.split("## Lifecycle", 1)[1].split("\n## ", 1)[0]
    lifecycle_state.lifecycle_text = lifecycle
    lifecycle_state.lifecycle_items = tuple(
        line.removeprefix("1. ") for line in lifecycle.splitlines() if line.startswith("1. ")
    )


@then("every Lifecycle preamble invariant is assigned executable evidence")
def then_preamble_is_traced(lifecycle_state: LifecycleState) -> None:
    assert all(phrase in lifecycle_state.lifecycle_text for phrase in PREAMBLE_PHRASES)
    feature_text = (
        Path(__file__)
        .with_name("features")
        .joinpath("detour_ai_augment_lifecycle.feature")
        .read_text(encoding=TEXT_ENCODING)
    )
    assert all(scenario_name in feature_text for scenario_name in TRACEABILITY_SCENARIOS)


@then("all 32 numbered Lifecycle items are assigned executable scenarios")
def then_items_are_traced(lifecycle_state: LifecycleState) -> None:
    assert len(lifecycle_state.lifecycle_items) == LIFECYCLE_ITEM_COUNT
    traced = {
        item_number
        for item_numbers in TRACEABILITY_SCENARIOS.values()
        for item_number in item_numbers
    }
    assert traced == set(range(1, LIFECYCLE_ITEM_COUNT + 1))


@given("the AI Agent Runtime deployment and provisioning programs")
def given_provisioning_programs(
    lifecycle_state: LifecycleState,
    detour_root: Path,
) -> None:
    runtime_root = detour_root / "src" / "agent_runtime"
    lifecycle_state.provisioning_files = {
        name: (runtime_root / name).read_text(encoding=TEXT_ENCODING)
        for name in ("deploy.sh", "provision.sh")
    }


@then("the Runtime is isolated and supports interactive and non-interactive Codex")
def then_runtime_modes_are_supported(lifecycle_state: LifecycleState) -> None:
    files = lifecycle_state.provisioning_files
    assert files is not None
    deploy = files["deploy.sh"]
    provision = files["provision.sh"]
    assert "limactl" in deploy
    assert 'AIVM_USER="ai"' in deploy
    assert "AIVM_CODEX_VSCE" in provision
    assert "AIVM_CODEX_CLI_BIN_PATH" in provision


@then("multi-agent mode is disabled")
def then_multi_agent_is_disabled(lifecycle_state: LifecycleState) -> None:
    files = lifecycle_state.provisioning_files
    assert files is not None
    provision = files["provision.sh"]
    assert "[agents]\nenabled = false" in provision


@then("appendwatch and the restricted audit reader enforce separate privileges")
def then_audit_privileges_are_separate(lifecycle_state: LifecycleState) -> None:
    files = lifecycle_state.provisioning_files
    assert files is not None
    deploy = files["deploy.sh"]
    provision = files["provision.sh"]
    assert 'AIVM_AUDIT_USER="aivm-audit"' in deploy
    assert 'restrict,command="%s" %s' in provision
    assert "AIVM_AUDIT_ENTRYPOINT" in provision
    assert "Start appendwatch before anything Codex-capable" in provision
    assert "--report-mode 0640" in provision
    assert 'setfacl -m "u:$AIVM_USER:---"' in provision


@then("guest and Backend OpenAlex credentials have independent delivery paths")
def then_openalex_credentials_are_separate(lifecycle_state: LifecycleState) -> None:
    files = lifecycle_state.provisioning_files
    assert files is not None
    deploy = files["deploy.sh"]
    assert "OPENALEX_API_KEY" in deploy
    assert not hasattr(control_ui._CodexRunner(timezone=ZoneInfo("UTC")), "_openalex_api_key")
    backend_environment_source = inspect.getsource(control_ui._BackendSupervisor.environment)
    assert "EXPORT_OPENALEX_API_KEY" in backend_environment_source


@given("an isolated Backend configuration for one eligible namekey")
def given_isolated_backend(
    lifecycle_state: LifecycleState,
    tmp_path: Path,
    lifecycle_backend_paths: backend_support.BackendTestPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = backend_support.runtime_for_test(
        tmp_path,
        lifecycle_backend_paths,
        namekey=backend_support.TEST_NAMEKEY,
    )
    assert runtime.source_researcher is not None
    lifecycle_state.runtime = runtime
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)


@when("Backend startup prerequisites are evaluated")
def when_backend_startup_is_evaluated(
    lifecycle_state: LifecycleState,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = lifecycle_state.runtime
    assert runtime is not None
    api._acquire_backend_process_lock()
    try:
        with pytest.raises(
            api._PushConfigurationError,
            match=BackendLocale.BACKEND_ALREADY_RUNNING,
        ):
            api._acquire_backend_process_lock()
    finally:
        api._release_backend_process_lock()
    api._acquire_backend_process_lock()
    api._release_backend_process_lock()

    configuration = SimpleNamespace(
        appendwatch_report=PurePosixPath("/guest/appendwatch-tree.txt"),
        lima_ssh_config=tmp_path / "ssh.config",
        identity_file=tmp_path / "id_ed25519",
        known_hosts_file=tmp_path / "known_hosts",
        ssh_user=api.AIVM_AUDIT_USER,
        ssh_target=f"{api.AIVM_INSTANCE}-{api.AIVM_AUDIT_USER}",
        host_key_alias=f"lima-{api.AIVM_INSTANCE}-{api.AIVM_AUDIT_USER}",
    )
    observed_commands: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        assert kwargs["check"] is True
        observed_commands.append(command)
        stdout: bytes | str = (
            b"appendwatch\n"
            if command[-1].startswith(api.AUDIT_READ_APPENDWATCH_REPORT_COMMAND)
            else ""
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(api, "push_configuration", lambda _path=None: configuration)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(
        api,
        "StreamingResponse",
        lambda content, *, media_type: Response(
            content="".join(content),
            media_type=media_type,
        ),
    )
    api.prove_workflow_inputs_readable()

    response = api.authoritative_pull()
    initial_body = response.body
    failed_runtime = SimpleNamespace(
        namekey=runtime.namekey,
        source_researcher=None,
    )
    monkeypatch.setattr(api, "runtime_configuration", lambda: failed_runtime)
    with pytest.raises(HTTPException) as failure:
        api.authoritative_pull()

    lifecycle_state.backend_observations = {
        "commands": observed_commands,
        "initial_response": response,
        "initial_body": initial_body,
        "failure": failure.value,
    }


@then("only one Backend process can hold the host singleton")
def then_backend_is_singleton(lifecycle_state: LifecycleState) -> None:
    assert lifecycle_state.backend_observations is not None
    assert api.BACKEND_PROCESS_LOCK_DESCRIPTOR is None


@then("the guest report and Codex sessions are probed through the restricted credential")
def then_guest_inputs_are_probed(lifecycle_state: LifecycleState) -> None:
    observations = lifecycle_state.backend_observations
    assert observations is not None
    commands = observations["commands"]
    assert len(commands) == 2
    assert all(api.AIVM_AUDIT_USER in command[-2] for command in commands)
    assert commands[0][-1].startswith(api.AUDIT_READ_APPENDWATCH_REPORT_COMMAND)
    assert commands[1][-1] == api.AUDIT_PROBE_COMMAND


@then("source rows are prepared read-only before the initial pull")
def then_source_is_prepared_read_only(lifecycle_state: LifecycleState) -> None:
    runtime = lifecycle_state.runtime
    assert runtime is not None
    assert runtime.source_researcher is not None
    assert runtime.source_researcher.namekey == backend_support.TEST_NAMEKEY
    assert "read_only=True" in inspect.getsource(api.open_source_database)
    assert "runtime.source_researcher" in inspect.getsource(api.authoritative_pull)


@then("the initial pull returns JSON Lines or an opaque internal error")
def then_initial_pull_contract(lifecycle_state: LifecycleState) -> None:
    observations = lifecycle_state.backend_observations
    assert observations is not None
    response = observations["initial_response"]
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == f"{api.MEDIA_TYPE}; charset=utf-8"
    assert observations["initial_body"].endswith(b"\n")
    failure = cast(HTTPException, observations["failure"])
    assert failure.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert failure.detail == BackendLocale.CONFIGURATION_ERROR_DETAIL


@given("a Dashboard with prepared source rows and linked ground truth")
def given_prepared_dashboard(lifecycle_state: LifecycleState) -> None:
    lifecycle_state.dashboard_observations = {}


@when("two eligible runs and one queued cancellation are processed")
def when_dashboard_runs_are_processed(
    lifecycle_state: LifecycleState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    first = dashboard_support.researcher()
    second = dashboard_support.researcher(dashboard_support.SECOND_NAMEKEY)
    third_namekey = control_ui.Namekey("Third Researcher [3]")
    third = dashboard_support.researcher(third_namekey)
    ground_truth = control_ui._GroundTruthRecord(namekey=first.namekey, values={})

    class Source:
        @staticmethod
        def load_researchers() -> tuple[control_ui._Researcher, ...]:
            order.append("source-population")
            return first, second, third

        @staticmethod
        def load_ground_truth_by_namekey() -> dict[
            control_ui.Namekey, control_ui._GroundTruthRecord
        ]:
            order.append("linked-ground-truth")
            return {first.namekey: ground_truth}

    backend = dashboard_support.FakeBackend(order)
    backend_database = dashboard_support.FakeBackendDatabase()
    codex = dashboard_support.FakeCodex(order)
    subject = control_ui._ControlCentreController(
        source_repository=cast(control_ui._SourceRepository, Source()),
        backend=cast(control_ui._BackendSupervisor, backend),
        backend_database=cast(control_ui._BackendDatabaseClient, backend_database),
        codex=cast(control_ui._CodexRunner, codex),
        reconciler=control_ui._AttemptReconciler(),
        projector=control_ui._VariableProjector(),
    )

    async def in_event_loop(function: Any, /, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    async def completed_worker() -> None:
        order.append("worker-started")

    async def complete_run(
        _subject: control_ui._ControlCentreController,
        *,
        run_id: UUID,
    ) -> run_outcome_models.RunOutcome:
        assert run_id in subject._runs
        return run_outcome_models.RunOutcome.COMPLETED

    monkeypatch.setattr(asyncio, "to_thread", in_event_loop)
    monkeypatch.setattr(subject, "_worker", completed_worker)
    monkeypatch.setattr(control_ui._ControlCentreController, "_finalize_run", complete_run)

    async def exercise() -> tuple[UUID, UUID, UUID, list[str]]:
        await subject.start()
        await asyncio.sleep(0)
        first_run = await subject.queue(namekey=first.namekey)
        second_run = await subject.queue(namekey=second.namekey)
        canceled_run = await subject.queue(namekey=third.namekey)
        persisted_before = list(app.storage.general[control_ui.QUEUE_STORAGE_KEY])
        await subject.cancel(run_id=canceled_run)
        assert await subject._queue.get() == first_run
        await subject._process_queued_run(first_run)
        assert await subject._queue.get() == second_run
        await subject._process_queued_run(second_run)
        assert await subject._queue.get() == canceled_run
        await subject._process_queued_run(canceled_run)
        await subject.shutdown()
        return first_run, second_run, canceled_run, persisted_before

    first_run, second_run, canceled_run, persisted_before = asyncio.run(exercise())

    socket_calls: list[tuple[Path, str, str]] = []
    response_body = (
        QueryResponse(
            attempts=(),
            accepted_innerdict_summaries=(),
            card_markdown=None,
        )
        .model_dump_json()
        .encode(TEXT_ENCODING)
    )

    class Response:
        status = status.HTTP_200_OK

        @staticmethod
        def read() -> bytes:
            return response_body

    class UnixConnection:
        def __init__(self, *, socket_path: Path, timeout: float) -> None:
            del timeout
            self.socket_path = socket_path

        def request(self, method: str, target: str) -> None:
            socket_calls.append((self.socket_path, method, target))

        @staticmethod
        def getresponse() -> Response:
            return Response()

        @staticmethod
        def close() -> None:
            return None

    monkeypatch.setattr(control_ui, "_UnixSocketHttpConnection", UnixConnection)
    socket_path = Path("/tmp/lifecycle-dashboard.sock")
    control_ui._BackendDatabaseClient(socket_path=socket_path).pull()

    lifecycle_state.dashboard_observations = {
        "controller": subject,
        "backend": backend,
        "backend_database": backend_database,
        "order": order,
        "run_ids": (first_run, second_run, canceled_run),
        "persisted_before": persisted_before,
        "socket_calls": socket_calls,
    }


@then("the queue persists only in NiceGUI general storage")
def then_queue_is_dashboard_private(lifecycle_state: LifecycleState) -> None:
    observations = lifecycle_state.dashboard_observations
    assert observations is not None
    first_run, second_run, canceled_run = observations["run_ids"]
    assert observations["persisted_before"] == [
        str(first_run),
        str(second_run),
        str(canceled_run),
    ]
    assert app.storage.general[control_ui.QUEUE_STORAGE_KEY] == []
    assert (
        observations["controller"]._runs[canceled_run].outcome
        is run_outcome_models.RunOutcome.CANCELLED
    )
    assert observations["backend_database"].pull_calls == 0


@then("each terminal run winds down its owned processes before the next run")
def then_runs_are_serial_and_cleaned(lifecycle_state: LifecycleState) -> None:
    observations = lifecycle_state.dashboard_observations
    assert observations is not None
    backend = observations["backend"]
    order = observations["order"]
    assert backend.started_namekeys == [
        dashboard_support.NAMEKEY,
        dashboard_support.SECOND_NAMEKEY,
    ]
    first_stop = order.index("backend-stop")
    second_start = order.index("backend-start", order.index("backend-start") + 1)
    assert first_stop < second_start
    assert order.count("backend-start") == 2
    assert order.count("codex-start") == 2
    assert order.count("backend-stop") >= 2


@then("detour database reads use the private unauthenticated Unix socket")
def then_dashboard_uses_private_ipc(lifecycle_state: LifecycleState) -> None:
    observations = lifecycle_state.dashboard_observations
    assert observations is not None
    assert observations["socket_calls"] == [
        (Path("/tmp/lifecycle-dashboard.sock"), api.HTTP_GET_METHOD, ipc.DASHBOARD_QUERY_PATH)
    ]
    assert ipc.DASHBOARD_QUERY_PATH not in {
        getattr(route, "path", None) for route in api.app.routes
    }


@given("a running Backend whose Codex session ID is not yet known")
def given_backend_before_session_handoff(
    lifecycle_state: LifecycleState,
    tmp_path: Path,
    lifecycle_backend_paths: backend_support.BackendTestPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = backend_support.runtime_for_test(
        tmp_path,
        lifecycle_backend_paths,
        namekey=backend_support.TEST_NAMEKEY,
    )
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    monkeypatch.setattr(
        api,
        "StreamingResponse",
        lambda content, *, media_type: Response(
            content="".join(content),
            media_type=media_type,
        ),
    )
    api.BACKEND_SESSION_ID = None
    lifecycle_state.runtime = runtime


@when("the Runtime retrieves the initial task and the operator supplies the session ID")
def when_pull_precedes_session_handoff(lifecycle_state: LifecycleState) -> None:
    assert api.BACKEND_SESSION_ID is None
    response = api.authoritative_pull()
    pull_body = response.body
    session_id = "019d0000-0000-7000-8000-000000000040"
    api.read_backend_session_id(StringIO(session_id + "\n"))
    runner = control_ui._CodexRunner(timezone=ZoneInfo("UTC"))
    run_id = UUID("019d0000-0000-7000-8000-000000000041")
    lifecycle_state.session_observations = {
        "response": response,
        "pull_body": pull_body,
        "session_id": session_id,
        "prompt": control_vars.CODEX_INPUT_TEMPLATE.format(
            openapi_url=control_vars.BACKEND_OPENAPI_URL
        ),
        "remote_command": runner.codex_remote_command(run_id=run_id),
    }


@then("the pull is JSON Lines and precedes the stdin session handoff")
def then_pull_precedes_handoff(lifecycle_state: LifecycleState) -> None:
    observations = lifecycle_state.session_observations
    assert observations is not None
    assert observations["response"].status_code == status.HTTP_200_OK
    assert observations["response"].headers["content-type"] == (f"{api.MEDIA_TYPE}; charset=utf-8")
    assert observations["pull_body"].endswith(b"\n")
    assert api.BACKEND_SESSION_ID == observations["session_id"]


@then("Codex receives only the OpenAPI URL as its initial prompt")
def then_codex_receives_openapi_prompt(lifecycle_state: LifecycleState) -> None:
    observations = lifecycle_state.session_observations
    assert observations is not None
    assert observations["prompt"] == f"{control_vars.BACKEND_OPENAPI_URL}\n"
    command = observations["remote_command"]
    assert str(control_vars.CODEX_ENV_PATH) in command
    assert "exec" in command
    assert "resume" not in command


@then("tool use push timing and stopping remain agent discretion boundaries")
def then_agent_discretion_is_bounded(lifecycle_state: LifecycleState) -> None:
    observations = lifecycle_state.session_observations
    assert observations is not None
    prompt = observations["prompt"]
    assert api.PUSH_PATH not in prompt
    assert api.PULL_PATH not in prompt
    assert control_vars.CODEX_EXEC_COMMAND[-1] == "-"


@given("a complete public HTTP exchange")
def given_public_exchange(lifecycle_state: LifecycleState) -> None:
    lifecycle_state.middleware_observations = {}


@when("the authoritative HTTP middleware records it")
def when_middleware_records_exchange(
    lifecycle_state: LifecycleState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authoritative_append_source = inspect.getsource(api.append_authoritative_record)
    events: list[str] = []
    records: list[HttpRequestLogRecord] = []
    sent: list[dict[str, object]] = []

    async def endpoint(_scope: object, _receive: object, send: Any) -> None:
        await send({
            api.ASGI_TYPE_KEY: api.ASGI_HTTP_RESPONSE_START_MESSAGE_TYPE,
            api.ASGI_STATUS_KEY: status.HTTP_200_OK,
            api.ASGI_HEADERS_KEY: [(b"content-type", b"application/json")],
        })
        await send({
            api.ASGI_TYPE_KEY: api.ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE,
            api.ASGI_BODY_KEY: b'{"ok":true}',
        })

    def append(record: HttpRequestLogRecord) -> None:
        records.append(record)
        events.append("append-fsync-project")

    async def after(_record: HttpRequestLogRecord) -> None:
        events.append("after-record")

    async def exchange() -> None:
        request_pending = True
        disconnected = asyncio.Event()

        async def receive() -> dict[str, object]:
            nonlocal request_pending
            if request_pending:
                request_pending = False
                return {
                    api.ASGI_TYPE_KEY: api.ASGI_HTTP_REQUEST_MESSAGE_TYPE,
                    api.ASGI_BODY_KEY: b"",
                    api.ASGI_MORE_BODY_KEY: False,
                }
            await disconnected.wait()
            return {api.ASGI_TYPE_KEY: api.ASGI_HTTP_DISCONNECT_MESSAGE_TYPE}

        async def send(message: dict[str, object]) -> None:
            events.append("send")
            sent.append(message)

        scope = {
            api.ASGI_TYPE_KEY: api.ASGI_HTTP_SCOPE_TYPE,
            api.ASGI_METHOD_KEY: api.HTTP_GET_METHOD,
            api.ASGI_PATH_KEY: api.PULL_PATH,
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "raw_path": api.PULL_PATH.encode(),
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "http_version": "1.1",
            "root_path": "",
        }
        await api._AuthoritativeHttpMiddleware(cast(Any, endpoint))(
            cast(Any, scope),
            receive,
            cast(Any, send),
        )

    monkeypatch.setattr(api, "AUTHORITATIVE_BACKEND_HEALTHY", True)
    monkeypatch.setattr(api, "append_authoritative_record", append)
    monkeypatch.setattr(api, "_after_authoritative_public_record", after)
    asyncio.run(exchange())

    synchronized: list[str] = []
    connection = object()
    monkeypatch.setattr(api, "_backend_detour_database", lambda _runtime: connection)
    monkeypatch.setattr(
        api,
        "_synchronize_authoritative_projection_locked",
        lambda _runtime, supplied: synchronized.append(
            "synchronize" if supplied is connection else "wrong-connection"
        ),
    )
    with api.synchronized_detour_database(
        cast(AiAugmentBackendContext, SimpleNamespace())
    ) as supplied:
        assert supplied is connection
        synchronized.append("use")

    lifecycle_state.middleware_observations = {
        "events": events,
        "records": records,
        "sent": sent,
        "synchronized": synchronized,
        "authoritative_append_source": authoritative_append_source,
    }


@then("the record is schema 1.1 with a UUIDv7 identity before response delivery")
def then_exchange_is_validated_before_send(lifecycle_state: LifecycleState) -> None:
    observations = lifecycle_state.middleware_observations
    assert observations is not None
    records = observations["records"]
    assert len(records) == 1
    record = records[0]
    assert record.schema_version == "1.1"
    assert record.record_id.version == 7
    assert HttpRequestLogRecord.model_validate_json(record.model_dump_json()) == record
    assert observations["events"][:2] == ["append-fsync-project", "after-record"]
    assert observations["events"][2:] == ["send", "send"]
    assert "os.fsync(descriptor)" in observations["authoritative_append_source"]


@then("client errors stay opaque while server diagnostics remain differentiated")
def then_errors_are_opaque() -> None:
    public_detail = BackendLocale.CONFIGURATION_ERROR_DETAIL
    assert "Contact the human operator" in public_detail
    assert BackendLocale.SOURCE_DUCKDB_OPEN_FAILED not in public_detail
    assert BackendLocale.APPENDWATCH_REPORT_UNREADABLE not in public_detail
    assert str(BackendLocale.SOURCE_DUCKDB_OPEN_FAILED) != str(
        BackendLocale.APPENDWATCH_REPORT_UNREADABLE
    )


@then("detour database access synchronizes replay records first")
def then_projection_precedes_database_use(lifecycle_state: LifecycleState) -> None:
    observations = lifecycle_state.middleware_observations
    assert observations is not None
    assert observations["synchronized"] == ["synchronize", "use"]


@given("the accepted production-captured push fixture")
def given_captured_push(detour_root: Path) -> None:
    fixture = detour_root / "tests" / "fixtures" / backend_support.OPERATOR_ACCEPTED_PUSH_FIXTURE
    value = json.loads(fixture.read_text(encoding=TEXT_ENCODING))
    assert set(AI_AUGMENT_COLUMNS) <= set(value)


@when("the captured push contour is replayed against an isolated Backend")
def when_captured_push_is_replayed(
    lifecycle_state: LifecycleState,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lifecycle_backend_paths: backend_support.BackendTestPaths,
    detour_root: Path,
) -> None:
    backend_support.assert_captured_operator_push_contour(
        tmp_path,
        monkeypatch,
        lifecycle_backend_paths,
        detour_root,
    )
    lifecycle_state.captured_contour_passed = True


@then("the push is preserved exactly through commit validation and terminal 410 replay")
def then_commit_and_replay_passed(lifecycle_state: LifecycleState) -> None:
    assert lifecycle_state.captured_contour_passed


@then("the completed researcher card is queryable from the Backend-owned database")
def then_card_is_queryable(lifecycle_state: LifecycleState) -> None:
    assert lifecycle_state.captured_contour_passed


@given("a root-run appendwatch permission contour")
def given_root_appendwatch() -> None:
    if sys.platform != "linux":
        pytest.skip("appendwatch uses Linux inotify")
    if os.geteuid() != 0:
        pytest.fail("needs_sudo Lifecycle scenario must run as root")


@when("a watched directory becomes inaccessible and later recovers")
def when_appendwatch_loses_access(
    lifecycle_state: LifecycleState,
    lifecycle_running_watchers: list[appendwatch_support.RunningWatcher],
) -> None:
    appendwatch_support.assert_static_eacces_is_scoped_and_recovered_files_fail_closed(
        lifecycle_running_watchers
    )
    lifecycle_state.appendwatch_contour_passed = True


@then("appendwatch scopes the error and marks files first seen while blind compromised")
def then_appendwatch_fails_closed(lifecycle_state: LifecycleState) -> None:
    assert lifecycle_state.appendwatch_contour_passed


@given("a provisioned reachable AIVM with its restricted appendwatch topology")
def given_operator_aivm(
    lifecycle_operator_runtime: operator_support.OperatorRuntime,
) -> None:
    operator_support._assert_deployed_appendwatch_topology(lifecycle_operator_runtime)


@when("the Human Operator runs the queued Dashboard Backend and Codex contour")
def when_operator_runs_lifecycle(
    lifecycle_state: LifecycleState,
    lifecycle_operator_runtime: operator_support.OperatorRuntime,
) -> None:
    started_at = time.monotonic()
    operator_support.assert_completed_dashboard_backend_codex_workflow_renders_researcher_card(
        lifecycle_operator_runtime
    )
    operator_support._operator_log(
        f"BDD Lifecycle scenario elapsed time: {time.monotonic() - started_at:.3f}s"
    )
    lifecycle_state.operator_contour_passed = True


@then("the terminal workflow artifacts and Playwright researcher card prove the Lifecycle")
def then_operator_lifecycle_passed(lifecycle_state: LifecycleState) -> None:
    assert lifecycle_state.operator_contour_passed
