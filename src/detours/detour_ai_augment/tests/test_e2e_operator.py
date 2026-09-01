from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Generator, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO, cast
from urllib import error as urllib_error
from urllib import request as urllib_request

import duckdb
import psutil
import pytest
from playwright.sync_api import ViewportSize, expect, sync_playwright

from src.detours.detour_ai_augment.src.backend import api as backend_api
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DETOUR_ROOT = Path(__file__).resolve().parents[1]
REAL_CONFIG_PATH = REPOSITORY_ROOT / "config_ai_augment.json"
PRODUCTION_DATA_DIRECTORIES = (
    REPOSITORY_ROOT / "data",
    DETOUR_ROOT / "data",
)
CONTROL_CENTRE_MODULE = "src.detours.detour_ai_augment.src.control_centre.dashboard.ui"
CONTROL_CENTRE_COMMAND_PREFIX = (
    sys.executable,
    "-m",
    CONTROL_CENTRE_MODULE,
    backend_api.CONFIG_OPTION,
)
CONTROL_CENTRE_URL = control_ui.CONTROL_CENTRE_BASE_URL
CONTROL_CENTRE_READY_LOG = control_ui.Locale.READY_LOG_TEMPLATE.format(
    url=CONTROL_CENTRE_URL
)
CONTROL_CENTRE_PORTS = (control_ui.CONTROL_CENTRE_PORT, control_ui.BACKEND_PORT)
TEXT_ENCODING = "utf-8"
HASH_ALGORITHM = "sha256"
HASH_SEPARATOR = b"\0"
EMPTY_FILE_SHA256 = hashlib.sha256(b"").hexdigest()
PROCESS_START_TIMEOUT_SECONDS = 300
PROCESS_STOP_TIMEOUT_SECONDS = 30
PROCESS_POLL_SECONDS = 0.1
FULL_WORKFLOW_TIMEOUT_SECONDS = 1_800
OPERATOR_HEARTBEAT_SECONDS = 10
BROWSER_ASSERTION_TIMEOUT_MILLISECONDS = 30_000
BROWSER_VIEWPORT: ViewportSize = {"width": 1_600, "height": 1_000}
BROWSER_CHANNEL = "chrome"
GRID_ROW_SELECTOR = ".ag-center-cols-container .ag-row"
OPERATOR_TARGET_DRAW_NUMBER = "146"
DARWIN_AF_UNIX_PATH_CAPACITY_BYTES = 104
PYTEST_CURRENT_TEST_ENV_NAME = "PYTEST_CURRENT_TEST"
OPERATOR_LIVE_OUTPUT = sys.__stdout__ or sys.stdout
FAILED_RUN_LOG_PREFIX = f"{control_ui.Locale.CONTROL_CENTRE_LOG_PREFIX} run failed:"

pytestmark = pytest.mark.operator


@dataclass(frozen=True, slots=True)
class OperatorRuntime:
    config_path: Path
    detour_db_path: Path
    replay_log_path: Path
    rollout_cas_dir: Path
    dashboard_socket_path: Path


@dataclass(slots=True)
class DashboardProcess:
    process: subprocess.Popen[str]
    output: list[str]
    output_thread: threading.Thread

    def wait_until_ready(self) -> None:
        _operator_log("waiting for Control Centre readiness")
        started_at = time.monotonic()
        deadline = time.monotonic() + PROCESS_START_TIMEOUT_SECONDS
        next_heartbeat = started_at + OPERATOR_HEARTBEAT_SECONDS
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    "Control Centre exited during startup:\n" + "".join(self.output)
                )
            if CONTROL_CENTRE_READY_LOG not in "".join(self.output):
                time.sleep(PROCESS_POLL_SECONDS)
                continue
            try:
                with urllib_request.urlopen(
                    CONTROL_CENTRE_URL,
                    timeout=control_ui.CONTROL_HTTP_TIMEOUT_SECONDS,
                ):
                    _operator_log("Control Centre is ready")
                    return
            except (OSError, urllib_error.URLError):
                time.sleep(PROCESS_POLL_SECONDS)
            now = time.monotonic()
            if now >= next_heartbeat:
                _operator_log(
                    f"still waiting for Control Centre ({now - started_at:.0f}s elapsed)"
                )
                next_heartbeat = now + OPERATOR_HEARTBEAT_SECONDS
        raise TimeoutError("Control Centre did not become ready:\n" + "".join(self.output))

    def stop(self) -> None:
        _operator_log("stopping Control Centre and its child processes")
        descendants = self._descendants()
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
            try:
                self.process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
        self._stop_descendants(descendants)
        self.output_thread.join(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
        if self.process.stdout is not None:
            self.process.stdout.close()
        _wait_for_ports_released()
        _operator_log("Control Centre and child processes stopped")

    def _descendants(self) -> list[psutil.Process]:
        try:
            return psutil.Process(self.process.pid).children(recursive=True)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return []

    @staticmethod
    def _stop_descendants(descendants: list[psutil.Process]) -> None:
        _, alive = psutil.wait_procs(descendants, timeout=0)
        for process in alive:
            with suppress(psutil.AccessDenied, psutil.NoSuchProcess):
                process.terminate()
        _, alive = psutil.wait_procs(alive, timeout=PROCESS_STOP_TIMEOUT_SECONDS)
        for process in alive:
            with suppress(psutil.AccessDenied, psutil.NoSuchProcess):
                process.kill()
        _, alive = psutil.wait_procs(alive, timeout=PROCESS_STOP_TIMEOUT_SECONDS)
        if alive:
            pids = ", ".join(str(process.pid) for process in alive)
            raise RuntimeError(f"operator child processes did not stop: {pids}")


def _operator_log(message: str, *, separate: bool = False) -> None:
    separator = "\n" if separate else ""
    OPERATOR_LIVE_OUTPUT.write(f"{separator}[operator-test] {message}\n")
    OPERATOR_LIVE_OUTPUT.flush()


def _file_digest(path: Path) -> bytes:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, HASH_ALGORITHM).digest()


def _tree_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in (directory, *sorted(directory.rglob("*"))):
        digest.update(path.relative_to(directory).as_posix().encode(TEXT_ENCODING))
        digest.update(HASH_SEPARATOR)
        if path.is_symlink():
            digest.update(b"symlink")
            digest.update(path.readlink().as_posix().encode(TEXT_ENCODING))
        elif path.is_dir():
            digest.update(b"directory")
        elif path.is_file():
            digest.update(b"file")
            digest.update(_file_digest(path))
        else:
            digest.update(b"other")
        digest.update(HASH_SEPARATOR)
    return digest.hexdigest()


@pytest.fixture(autouse=True)
def production_data_unchanged(operator_aivm: None) -> Iterator[None]:
    _operator_log("hashing production data before the test")
    before = {path: _tree_digest(path) for path in PRODUCTION_DATA_DIRECTORIES}
    _operator_log("production-data pre-test hashes completed")
    yield
    _operator_log("verifying production data remains unchanged", separate=True)
    assert {path: _tree_digest(path) for path in PRODUCTION_DATA_DIRECTORIES} == before
    _operator_log("production data is unchanged")


def _operator_runtime(
    tmp_path: Path,
    *,
    dashboard_socket_path: Path,
) -> OperatorRuntime:
    replay_log_path = tmp_path / "backend-replay.jsonl"
    rollout_cas_dir = tmp_path / "rollout-cas"
    config_path = tmp_path / "config.operator.json"
    config_value: object = json.loads(REAL_CONFIG_PATH.read_text(encoding=TEXT_ENCODING))
    if not isinstance(config_value, dict):
        raise AssertionError("operator configuration must be a JSON object")
    config = cast(dict[str, Any], config_value)
    configured_source = Path(str(config["db_file"]))
    source = (
        configured_source
        if configured_source.is_absolute()
        else REPOSITORY_ROOT / configured_source
    )
    source_link = tmp_path / source.name
    source_link.symlink_to(source)
    replay_log_path.write_bytes(b"")
    files_config = cast(dict[str, Any], config["files_config"])
    replay_config = cast(
        dict[str, Any],
        files_config[backend_api.REPLAY_LOG_RESOURCE_KEY],
    )
    replay_config[backend_api.RESOURCE_PATH_KEY] = str(replay_log_path)
    replay_config[backend_api.RESOURCE_SHA256_KEY] = EMPTY_FILE_SHA256
    config.update({
        "db_file": str(source_link),
        "state_file": str(tmp_path / "state.json"),
        "output_dir": str(tmp_path / "output"),
        "rollout_cas_dir": str(rollout_cas_dir),
    })
    config_path.write_text(json.dumps(config, indent=2), encoding=TEXT_ENCODING)
    return OperatorRuntime(
        config_path=config_path,
        detour_db_path=backend_api._detour_db_path(source_link),
        replay_log_path=replay_log_path,
        rollout_cas_dir=rollout_cas_dir,
        dashboard_socket_path=dashboard_socket_path,
    )


@pytest.fixture
def operator_runtime(tmp_path: Path) -> Iterator[OperatorRuntime]:
    with tempfile.TemporaryDirectory(prefix="detour-operator-", dir="/tmp") as directory:
        dashboard_socket_path = Path(directory) / "dashboard.sock"
        if len(os.fsencode(dashboard_socket_path)) >= DARWIN_AF_UNIX_PATH_CAPACITY_BYTES:
            raise RuntimeError("operator dashboard socket path exceeds Darwin AF_UNIX capacity")
        yield _operator_runtime(
            tmp_path,
            dashboard_socket_path=dashboard_socket_path,
        )


def _collect_output(stream: TextIO, output: list[str]) -> None:
    for line in stream:
        output.append(line)
        OPERATOR_LIVE_OUTPUT.write(line)
        OPERATOR_LIVE_OUTPUT.flush()


def _assert_ports_available() -> None:
    for port in CONTROL_CENTRE_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            if client.connect_ex((control_ui.CONTROL_CENTRE_HOST, port)) == 0:
                _operator_log(
                    f"local port {port} is already in use; no operator-owned "
                    "Control Centre or Backend process was started"
                )
                pytest.fail(f"operator test requires unused local port {port}")


def _wait_for_ports_released() -> None:
    deadline = time.monotonic() + PROCESS_STOP_TIMEOUT_SECONDS
    occupied: list[int] = []
    while time.monotonic() < deadline:
        occupied = []
        for port in CONTROL_CENTRE_PORTS:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                if client.connect_ex((control_ui.CONTROL_CENTRE_HOST, port)) == 0:
                    occupied.append(port)
        if not occupied:
            return
        time.sleep(PROCESS_POLL_SECONDS)
    raise RuntimeError(f"operator processes retained local ports: {occupied}")


@contextmanager
def running_dashboard(runtime: OperatorRuntime) -> Generator[DashboardProcess]:
    _operator_log("checking that Control Centre and Backend ports are free")
    _assert_ports_available()
    environment = os.environ.copy()
    environment.pop(PYTEST_CURRENT_TEST_ENV_NAME, None)
    environment["PYTHONUNBUFFERED"] = "1"
    environment[backend_api.DASHBOARD_SOCKET_PATH_ENV_NAME] = str(
        runtime.dashboard_socket_path
    )
    process = subprocess.Popen(
        (*CONTROL_CENTRE_COMMAND_PREFIX, str(runtime.config_path)),
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=TEXT_ENCODING,
        bufsize=1,
        start_new_session=True,
    )
    dashboard: DashboardProcess | None = None
    try:
        _operator_log(f"started Control Centre process {process.pid}")
        if process.stdout is None:
            raise RuntimeError("Control Centre output pipe is unavailable")
        output: list[str] = []
        output_thread = threading.Thread(
            target=_collect_output,
            args=(process.stdout, output),
            daemon=True,
        )
        output_thread.start()
        dashboard = DashboardProcess(process, output, output_thread)
        dashboard.wait_until_ready()
        yield dashboard
    finally:
        if dashboard is None:
            _operator_log("stopping partially started Control Centre process")
            if process.poll() is None:
                process.kill()
                process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
            if process.stdout is not None:
                process.stdout.close()
            _operator_log("partially started Control Centre process stopped")
        else:
            dashboard.stop()


def target_namekey(runtime: OperatorRuntime) -> control_ui.Namekey:
    _operator_log("selecting the operator workflow target")
    configuration = control_ui.AiAugmentCtlCtrContext(config_path=runtime.config_path)
    namekey = next(
        item.namekey
        for item in control_ui.SourceRepository(
            configuration=configuration
        ).load_researchers()
        if OPERATOR_TARGET_DRAW_NUMBER in item.draw_numbers
        and item.cohort is not control_ui.ResearcherCohort.INELIGIBLE
    )
    _operator_log(f"selected workflow target {namekey}")
    return namekey


def queue_in_browser(namekey: control_ui.Namekey) -> None:
    _operator_log("opening the Control Centre in Playwright")
    with sync_playwright() as playwright:
        browser = None
        try:
            browser = playwright.chromium.launch(channel=BROWSER_CHANNEL, headless=True)
            page = browser.new_page(viewport=BROWSER_VIEWPORT)
            page.set_default_timeout(BROWSER_ASSERTION_TIMEOUT_MILLISECONDS)
            page.goto(CONTROL_CENTRE_URL, wait_until="networkidle")
            page.get_by_label(control_ui.Locale.SEARCH_FILTER).fill(namekey)
            rows = page.get_by_test_id(control_ui.RESEARCHER_GRID_TEST_ID).locator(
                GRID_ROW_SELECTOR
            )
            expect(rows).to_have_count(1)
            rows.first.click()
            execute = page.get_by_test_id(control_ui.EXECUTE_ACTION_TEST_ID)
            expect(execute).to_be_enabled()
            execute.click()
            _operator_log("queued the workflow through the browser")
        finally:
            if browser is not None:
                browser.close()
            _operator_log("closed the operator-test browser")


def authoritative_records(path: Path) -> tuple[HttpRequestLogRecord, ...]:
    if not path.exists():
        return ()
    return tuple(
        HttpRequestLogRecord.model_validate_json(line)
        for line in path.read_bytes().splitlines()
        if line
    )


def wait_for_terminal_pull(
    runtime: OperatorRuntime,
    dashboard: DashboardProcess,
) -> tuple[HttpRequestLogRecord, ...]:
    _operator_log("waiting for the Backend terminal pull")
    started_at = time.monotonic()
    deadline = time.monotonic() + FULL_WORKFLOW_TIMEOUT_SECONDS
    next_heartbeat = started_at + OPERATOR_HEARTBEAT_SECONDS
    previous_record_count = -1
    while time.monotonic() < deadline:
        if dashboard.process.poll() is not None:
            raise RuntimeError("dashboard exited:\n" + "".join(dashboard.output))
        failed_run_lines = [
            line for line in dashboard.output if line.startswith(FAILED_RUN_LOG_PREFIX)
        ]
        if failed_run_lines:
            raise RuntimeError("workflow failed:\n" + "".join(failed_run_lines))
        records = authoritative_records(runtime.replay_log_path)
        if len(records) != previous_record_count:
            _operator_log(f"authoritative request log contains {len(records)} record(s)")
            previous_record_count = len(records)
        if any(
            (record.method, record.path, record.response_code)
            == (
                backend_api.HTTP_GET_METHOD,
                backend_api.PULL_PATH,
                backend_api.status.HTTP_410_GONE,
            )
            for record in records
        ):
            _operator_log("Backend reached the terminal pull")
            return records
        now = time.monotonic()
        if now >= next_heartbeat:
            _operator_log(
                f"workflow is still running ({now - started_at:.0f}s elapsed, "
                f"{len(records)} request-log record(s))"
            )
            next_heartbeat = now + OPERATOR_HEARTBEAT_SECONDS
        time.sleep(PROCESS_POLL_SECONDS)
    raise TimeoutError("workflow did not reach terminal pull:\n" + "".join(dashboard.output))


def _record_ordinal(
    records: Sequence[HttpRequestLogRecord],
    record_id: object,
) -> int:
    return next(
        index for index, record in enumerate(records) if record.record_id == record_id
    )


def test_existing_aivm_exposes_the_persisted_appendwatch_topology(
    operator_runtime: OperatorRuntime,
) -> None:
    _operator_log("preparing isolated topology-test runtime")

    _operator_log("loading the deployed appendwatch topology")
    configuration = control_ui.AiAugmentCtlCtrContext(
        config_path=operator_runtime.config_path
    )

    assert configuration.appendwatch_report.is_file()
    assert configuration.appendwatch_report.stat().st_size
    _operator_log("deployed appendwatch topology is readable")


def test_complete_dashboard_backend_codex_commit_and_replay_workflow(
    operator_runtime: OperatorRuntime,
) -> None:
    _operator_log("preparing isolated full-workflow runtime")
    namekey = target_namekey(operator_runtime)

    with running_dashboard(operator_runtime) as dashboard:
        queue_in_browser(namekey)
        records = wait_for_terminal_pull(operator_runtime, dashboard)
        assert stat.S_ISSOCK(operator_runtime.dashboard_socket_path.stat().st_mode)
        assert stat.S_IMODE(operator_runtime.dashboard_socket_path.stat().st_mode) == 0o600

    _operator_log("validating authoritative workflow artifacts")
    assert not operator_runtime.dashboard_socket_path.exists()

    assert all(record.schema_version == "1.1" for record in records)
    assert all(record.record_id.version == 7 for record in records)
    assert {
        (record.method, record.path) for record in records
    } <= backend_api.AUTHORITATIVE_PUBLIC_ROUTES | {
        backend_api.AUTHORITATIVE_COMMIT_ROUTE
    }
    assert not any(record.path.startswith("/_control/") for record in records)

    terminal_pull = next(
        record
        for record in reversed(records)
        if (record.method, record.path, record.response_code)
        == (
            backend_api.HTTP_GET_METHOD,
            backend_api.PULL_PATH,
            backend_api.status.HTTP_410_GONE,
        )
    )
    accepted_commits: list[tuple[HttpRequestLogRecord, backend_api.ReplayCommit]] = []
    for record in records:
        if (record.method, record.path) != backend_api.AUTHORITATIVE_COMMIT_ROUTE:
            continue
        commit = backend_api._replay_commit(record.request_body)
        with duckdb.connect(
            str(operator_runtime.detour_db_path), read_only=True
        ) as connection:
            row = connection.execute(
                f"SELECT {backend_api.AUTHORITATIVE_OUTCOME_PAYLOAD_COLUMN} "
                f"FROM {backend_api.AUTHORITATIVE_OUTCOMES_TABLE} "
                f"WHERE {backend_api.AUTHORITATIVE_OUTCOME_COMMIT_ID_COLUMN} = ?",
                [str(record.record_id)],
            ).fetchone()
        if row is not None:
            outcome = backend_api.ProjectedValidationOutcome.model_validate_json(str(row[0]))
            if outcome.result == backend_api.ATTEMPT_RESULT_ACCEPTED:
                accepted_commits.append((record, commit))
    assert len(accepted_commits) == 1
    commit_record, commit = accepted_commits[0]
    assert backend_api._validated_readme_record(commit_record) == commit_record
    pull_ordinal = _record_ordinal(records, commit.pull_record_id)
    push_ordinal = _record_ordinal(records, commit.push_record_id)
    commit_ordinal = _record_ordinal(records, commit_record.record_id)
    terminal_ordinal = _record_ordinal(records, terminal_pull.record_id)
    assert pull_ordinal < push_ordinal < commit_ordinal < terminal_ordinal
    push_record = records[push_ordinal]
    assert push_record.response_code == backend_api.status.HTTP_202_ACCEPTED
    assert push_record.response_headers is not None
    assert push_record.response_headers["location"] == backend_api.PULL_PATH
    rollout_blob = operator_runtime.rollout_cas_dir / (
        backend_api.ROLLOUT_CAS_FILENAME_TEMPLATE.format(
            sha256=commit.rollout.sha256
        )
    )
    assert rollout_blob.is_file()
    assert rollout_blob.stat().st_size == commit.rollout.size
    assert _file_digest(rollout_blob).hex() == commit.rollout.sha256
    assert len(rollout_blob.read_bytes().splitlines()) == commit.rollout.line_count
    assert terminal_pull.response_body
    assert json.loads(terminal_pull.response_body.splitlines()[0])
    _operator_log("full operator workflow contract validated")
