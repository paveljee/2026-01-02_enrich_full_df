from __future__ import annotations

import hashlib
import json
import os
import shlex
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
from playwright.sync_api import Locator, Page, ViewportSize, expect, sync_playwright

from src.detours.detour_ai_augment.src.backend import api as backend_api
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

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
ATTEMPT_HISTORY_ROW_SELECTOR = "tbody tr"
OPERATOR_TARGET_DRAW_NUMBER = "146"
DARWIN_AF_UNIX_PATH_CAPACITY_BYTES = 104
PYTEST_CURRENT_TEST_ENV_NAME = "PYTEST_CURRENT_TEST"
OPERATOR_LIVE_OUTPUT = sys.__stdout__ or sys.stdout
FAILED_RUN_LOG_PREFIX = f"{control_ui.Locale.CONTROL_CENTRE_LOG_PREFIX} run failed:"
RESEARCHER_CARD_BEGIN = "Playwright researcher card begin"
RESEARCHER_CARD_END = "Playwright researcher card end"

pytestmark = pytest.mark.operator


@dataclass(frozen=True, slots=True)
class OperatorRuntime:
    repository_root: Path
    config_path: Path
    detour_db_path: Path
    replay_log_path: Path
    rollout_cas_dir: Path
    dashboard_socket_path: Path


@dataclass(frozen=True, slots=True)
class TerminalWorkflowCheckpoint:
    records: tuple[HttpRequestLogRecord, ...]
    queued_at_monotonic: float


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
            control_centre = _process_snapshot(
                psutil.Process(self.process.pid),
                role="Control Centre",
            )
            _operator_process_log(
                "sending SIGINT",
                control_centre,
            )
            self.process.send_signal(signal.SIGINT)
            try:
                self.process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                _operator_process_log(
                    "SIGINT timed out; sending SIGTERM",
                    control_centre,
                )
                self.process.terminate()
                try:
                    self.process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    _operator_process_log(
                        "SIGTERM timed out; sending SIGKILL",
                        control_centre,
                    )
                    self.process.kill()
                    self.process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
            _operator_log(
                "Control Centre process exited: "
                f"pid={self.process.pid} return_code={self.process.returncode}"
            )
        else:
            _operator_log(
                "Control Centre process had already exited: "
                f"pid={self.process.pid} return_code={self.process.returncode}"
            )
        self._stop_descendants(descendants)
        self.output_thread.join(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
        if self.process.stdout is not None:
            self.process.stdout.close()
        _wait_for_ports_released()
        _operator_log("Control Centre and child processes stopped")

    def _descendants(self) -> list[OperatorProcessSnapshot]:
        try:
            return [
                _process_snapshot(process)
                for process in psutil.Process(self.process.pid).children(recursive=True)
            ]
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return []

    @staticmethod
    def _stop_descendants(descendants: list[OperatorProcessSnapshot]) -> None:
        snapshots = {snapshot.pid: snapshot for snapshot in descendants}
        gone, alive = psutil.wait_procs(
            [snapshot.process for snapshot in descendants],
            timeout=0,
        )
        for process in gone:
            _operator_process_log(
                "exited during graceful Control Centre shutdown",
                snapshots[process.pid],
            )
        for process in alive:
            _operator_process_log("sending fallback SIGTERM", snapshots[process.pid])
            with suppress(psutil.AccessDenied, psutil.NoSuchProcess):
                process.terminate()
        gone, alive = psutil.wait_procs(alive, timeout=PROCESS_STOP_TIMEOUT_SECONDS)
        for process in gone:
            _operator_process_log("stopped after fallback SIGTERM", snapshots[process.pid])
        for process in alive:
            _operator_process_log("sending fallback SIGKILL", snapshots[process.pid])
            with suppress(psutil.AccessDenied, psutil.NoSuchProcess):
                process.kill()
        gone, alive = psutil.wait_procs(alive, timeout=PROCESS_STOP_TIMEOUT_SECONDS)
        for process in gone:
            _operator_process_log("stopped after fallback SIGKILL", snapshots[process.pid])
        if alive:
            processes = ", ".join(
                f"{snapshots[process.pid].role} pid={process.pid}" for process in alive
            )
            raise RuntimeError(f"operator child processes did not stop: {processes}")


@dataclass(frozen=True, slots=True)
class OperatorProcessSnapshot:
    process: psutil.Process
    pid: int
    parent_pid: int | None
    role: str
    command: tuple[str, ...]


def _process_snapshot(
    process: psutil.Process,
    *,
    role: str | None = None,
) -> OperatorProcessSnapshot:
    try:
        command = tuple(process.cmdline())
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        command = ()
    try:
        parent_pid = process.ppid()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        parent_pid = None
    return OperatorProcessSnapshot(
        process=process,
        pid=process.pid,
        parent_pid=parent_pid,
        role=role or _process_role(command),
        command=command,
    )


def _process_role(command: tuple[str, ...]) -> str:
    command_text = " ".join(command)
    executable = Path(command[0]).name if command else ""
    if control_ui.BACKEND_MODULE in command_text:
        return "Backend"
    if str(control_ui.CODEX_EXEC_COMMAND[0]) in command_text:
        return "Codex SSH transport"
    if executable == backend_api.SSH_EXECUTABLE:
        if any(
            command in command_text
            for command in (
                backend_api.AUDIT_FIND_ROLLOUT_COMMAND,
                backend_api.AUDIT_READ_ROLLOUT_COMMAND,
                backend_api.AUDIT_READ_APPENDWATCH_REPORT_COMMAND,
                backend_api.AUDIT_PROBE_COMMAND,
            )
        ):
            return "Backend audit reader"
        return "AIVM SSH helper"
    return "unclassified Control Centre descendant"


def _operator_process_log(action: str, snapshot: OperatorProcessSnapshot) -> None:
    _operator_log(
        f"{action}: role={snapshot.role} pid={snapshot.pid} "
        f"parent_pid={snapshot.parent_pid} command={json.dumps(snapshot.command)}"
    )


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
def production_data_unchanged(
    operator_aivm: None,
    repository_root: Path,
    detour_root: Path,
) -> Iterator[None]:
    production_data_directories = (
        repository_root / "data",
        detour_root / "data",
    )
    _operator_log("hashing production data before the test")
    before = {path: _tree_digest(path) for path in production_data_directories}
    _operator_log("production-data pre-test hashes completed")
    yield
    _operator_log("verifying production data remains unchanged", separate=True)
    assert {path: _tree_digest(path) for path in production_data_directories} == before
    _operator_log("production data is unchanged")


def _operator_runtime(
    tmp_path: Path,
    *,
    repository_root: Path,
    dashboard_socket_path: Path,
) -> OperatorRuntime:
    replay_log_path = tmp_path / "backend-replay.jsonl"
    rollout_cas_dir = tmp_path / "rollout-cas"
    config_path = tmp_path / "config.operator.json"
    config_value: object = json.loads(
        (repository_root / "config_ai_augment.json").read_text(
            encoding=TEXT_ENCODING
        )
    )
    if not isinstance(config_value, dict):
        raise AssertionError("operator configuration must be a JSON object")
    config = cast(dict[str, Any], config_value)
    configured_source = Path(str(config["db_file"]))
    source = (
        configured_source
        if configured_source.is_absolute()
        else repository_root / configured_source
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
        repository_root=repository_root,
        config_path=config_path,
        detour_db_path=backend_api._detour_db_path(source_link),
        replay_log_path=replay_log_path,
        rollout_cas_dir=rollout_cas_dir,
        dashboard_socket_path=dashboard_socket_path,
    )


@pytest.fixture
def operator_runtime(
    tmp_path: Path,
    repository_root: Path,
) -> Iterator[OperatorRuntime]:
    with tempfile.TemporaryDirectory(prefix="detour-operator-", dir="/tmp") as directory:
        dashboard_socket_path = Path(directory) / "dashboard.sock"
        if len(os.fsencode(dashboard_socket_path)) >= DARWIN_AF_UNIX_PATH_CAPACITY_BYTES:
            raise RuntimeError("operator dashboard socket path exceeds Darwin AF_UNIX capacity")
        yield _operator_runtime(
            tmp_path,
            repository_root=repository_root,
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
        cwd=runtime.repository_root,
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


def queue_in_browser(namekey: control_ui.Namekey) -> float:
    _operator_log("opening the Control Centre in Playwright")
    queued_at_monotonic: float | None = None
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
            queued_at_monotonic = time.monotonic()
            execute.click()
            _operator_log("queued the workflow through the browser")
        finally:
            if browser is not None:
                browser.close()
            _operator_log("closed the operator-test browser")
    if queued_at_monotonic is None:
        raise RuntimeError("operator workflow was not queued")
    return queued_at_monotonic


def authoritative_records(path: Path) -> tuple[HttpRequestLogRecord, ...]:
    if not path.exists():
        return ()
    return tuple(
        HttpRequestLogRecord.model_validate_json(line)
        for line in path.read_bytes().splitlines()
        if line
    )


def raise_for_dashboard_failure(dashboard: DashboardProcess) -> None:
    if dashboard.process.poll() is not None:
        raise RuntimeError("dashboard exited:\n" + "".join(dashboard.output))
    failed_run_lines = [
        line for line in dashboard.output if line.startswith(FAILED_RUN_LOG_PREFIX)
    ]
    if failed_run_lines:
        raise RuntimeError("workflow failed:\n" + "".join(failed_run_lines))


def wait_for_terminal_pull(
    runtime: OperatorRuntime,
    dashboard: DashboardProcess,
) -> tuple[HttpRequestLogRecord, ...]:
    _operator_log("waiting for the Backend terminal pull")
    started_at = time.monotonic()
    deadline = time.monotonic() + FULL_WORKFLOW_TIMEOUT_SECONDS
    next_heartbeat = started_at + OPERATOR_HEARTBEAT_SECONDS
    previous_record_count = 0
    previous_exchange: tuple[str, str, int | None] | None = None
    _operator_log("authoritative request log initially contains 0 record(s)")
    while time.monotonic() < deadline:
        raise_for_dashboard_failure(dashboard)
        records = authoritative_records(runtime.replay_log_path)
        for record in records[previous_record_count:]:
            exchange = (record.method, record.path, record.response_code)
            if exchange != previous_exchange:
                response = (
                    "no response"
                    if record.response_code is None
                    else str(record.response_code)
                )
                _operator_log(
                    f"observed authoritative {record.method} {record.path} -> {response}"
                )
                previous_exchange = exchange
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


def run_workflow_to_terminal_pull(
    runtime: OperatorRuntime,
    dashboard: DashboardProcess,
    namekey: control_ui.Namekey,
) -> TerminalWorkflowCheckpoint:
    queued_at_monotonic = queue_in_browser(namekey)
    records = wait_for_terminal_pull(runtime, dashboard)
    assert stat.S_ISSOCK(runtime.dashboard_socket_path.stat().st_mode)
    assert stat.S_IMODE(runtime.dashboard_socket_path.stat().st_mode) == 0o600
    return TerminalWorkflowCheckpoint(
        records=records,
        queued_at_monotonic=queued_at_monotonic,
    )


def wait_for_completed_grid_row(
    page: Page,
    dashboard: DashboardProcess,
    *,
    queued_at_monotonic: float,
) -> tuple[Locator, str]:
    rows = page.get_by_test_id(control_ui.RESEARCHER_GRID_TEST_ID).locator(
        GRID_ROW_SELECTOR
    )
    expect(rows).to_have_count(1)
    row = rows.first
    row.click()
    history = page.get_by_test_id(control_ui.ATTEMPT_HISTORY_TABLE_TEST_ID)
    expect(history).to_be_visible()
    history_rows = history.locator(ATTEMPT_HISTORY_ROW_SELECTOR)
    execute = page.get_by_test_id(control_ui.EXECUTE_ACTION_TEST_ID)
    view_card = page.get_by_test_id(control_ui.VIEW_CARD_TEST_ID)
    deadline = queued_at_monotonic + FULL_WORKFLOW_TIMEOUT_SECONDS
    next_heartbeat = time.monotonic() + OPERATOR_HEARTBEAT_SECONDS
    previous_status: str | None = None
    while time.monotonic() < deadline:
        raise_for_dashboard_failure(dashboard)
        history_count = history_rows.count()
        current_status = (
            ""
            if history_count == 0
            else history_rows.nth(history_count - 1).locator("td").nth(1).inner_text().strip()
        )
        if current_status != previous_status:
            _operator_log(
                f"Control Centre attempt history reports workflow status {current_status!r}"
            )
            previous_status = current_status
        if (
            current_status == control_ui.RunStatus.COMPLETE.value
            and execute.inner_text().strip()
            == control_ui.ACTION_LABEL_BY_VALUE[control_ui.RunAction.RERUN.value]
            and view_card.is_enabled()
        ):
            attempt_id = (
                history_rows.nth(history_count - 1).locator("td").nth(2).inner_text().strip()
            )
            if not attempt_id:
                raise RuntimeError("completed Control Centre history has no accepted attempt ID")
            _operator_log("Control Centre projected the completed post-Codex run")
            return row, attempt_id
        if current_status in {
            control_ui.RunStatus.FAILED.value,
            control_ui.RunStatus.CANCELED.value,
        }:
            raise RuntimeError(
                f"Control Centre projected terminal workflow status {current_status!r}"
            )
        now = time.monotonic()
        if now >= next_heartbeat:
            _operator_log(
                "waiting for Codex to exit and Control Centre to complete the run "
                f"({now - queued_at_monotonic:.0f}s elapsed)"
            )
            next_heartbeat = now + OPERATOR_HEARTBEAT_SECONDS
        page.wait_for_timeout(round(PROCESS_POLL_SECONDS * 1_000))
    raise TimeoutError(
        "workflow did not reach the completed Control Centre state:\n"
        + "".join(dashboard.output)
    )


def capture_completed_researcher_card(
    dashboard: DashboardProcess,
    *,
    namekey: control_ui.Namekey,
    queued_at_monotonic: float,
) -> str:
    _operator_log("opening the completed workflow in Playwright")
    with sync_playwright() as playwright:
        browser = None
        try:
            browser = playwright.chromium.launch(channel=BROWSER_CHANNEL, headless=True)
            page = browser.new_page(viewport=BROWSER_VIEWPORT)
            page.set_default_timeout(BROWSER_ASSERTION_TIMEOUT_MILLISECONDS)
            browser_errors: list[str] = []
            page.on(
                "console",
                lambda message: (
                    browser_errors.append(message.text)
                    if message.type == "error"
                    else None
                ),
            )
            page.on("pageerror", lambda error: browser_errors.append(str(error)))
            page.goto(CONTROL_CENTRE_URL, wait_until="networkidle")
            page.get_by_label(control_ui.Locale.SEARCH_FILTER).fill(namekey)
            _row, attempt_id = wait_for_completed_grid_row(
                page,
                dashboard,
                queued_at_monotonic=queued_at_monotonic,
            )
            history = page.get_by_test_id(control_ui.ATTEMPT_HISTORY_TABLE_TEST_ID)
            expect(history).to_be_visible()
            expect(history.locator(ATTEMPT_HISTORY_ROW_SELECTOR)).not_to_have_count(0)
            expect(history).to_contain_text(attempt_id)
            execute = page.get_by_test_id(control_ui.EXECUTE_ACTION_TEST_ID)
            expect(execute).to_have_text(
                control_ui.ACTION_LABEL_BY_VALUE[control_ui.RunAction.RERUN.value]
            )
            view_card = page.get_by_test_id(control_ui.VIEW_CARD_TEST_ID)
            expect(view_card).to_be_enabled()
            view_card.click()
            card = page.get_by_test_id(control_ui.PAGE_FOOTER_TEST_ID)
            expect(card).not_to_have_text("")
            card_text = card.inner_text().strip()
            if not card_text:
                raise RuntimeError("Playwright captured an empty researcher card")
            assert browser_errors == []
            _operator_log(
                "Playwright confirmed the completed attempt and captured its researcher card"
            )
            return card_text
        finally:
            if browser is not None:
                browser.close()
            _operator_log("closed the completed-workflow browser")


def emit_researcher_card(card_text: str) -> None:
    OPERATOR_LIVE_OUTPUT.write(
        f"\n[operator-test] {RESEARCHER_CARD_BEGIN}\n"
        f"{card_text}\n"
        f"[operator-test] {RESEARCHER_CARD_END}\n"
    )
    OPERATOR_LIVE_OUTPUT.flush()


def _record_ordinal(
    records: Sequence[HttpRequestLogRecord],
    record_id: object,
) -> int:
    return next(
        index for index, record in enumerate(records) if record.record_id == record_id
    )


def _assert_deployed_appendwatch_topology(
    operator_runtime: OperatorRuntime,
) -> None:
    _operator_log("loading the deployed appendwatch topology")
    identity_file = backend_api.AIVM_IDENTITY_FILE
    assert identity_file is not None
    configuration = control_ui.AiAugmentCtlCtrContext(
        config_path=operator_runtime.config_path
    )
    assert configuration.appendwatch_report.is_absolute()
    options = backend_api._aivm_connection_options(
        lima_ssh_config=backend_api.LIMA_SSH_CONFIG_PATH,
        identity_file=identity_file,
        known_hosts_file=backend_api.AIVM_KNOWN_HOSTS_FILE,
        ssh_user=backend_api.AIVM_AUDIT_USER,
        host_key_alias=(
            f"lima-{backend_api.AIVM_INSTANCE}-{backend_api.AIVM_AUDIT_USER}"
        ),
    )
    completed = subprocess.run(
        [
            backend_api.SSH_EXECUTABLE,
            *options,
            "--",
            f"{backend_api.AIVM_INSTANCE}-{backend_api.AIVM_AUDIT_USER}",
            shlex.join([
                backend_api.AUDIT_READ_APPENDWATCH_REPORT_COMMAND,
                str(configuration.appendwatch_report),
            ]),
        ],
        check=True,
        capture_output=True,
        timeout=backend_api.SSH_TIMEOUT_SECONDS,
    )
    assert completed.stdout
    _operator_log("deployed appendwatch topology is readable")


@pytest.mark.excluded_from_suites
def test_existing_aivm_exposes_the_persisted_appendwatch_topology(
    operator_runtime: OperatorRuntime,
) -> None:
    _operator_log("preparing isolated topology-test runtime")
    _assert_deployed_appendwatch_topology(operator_runtime)


def validate_workflow_artifacts(
    operator_runtime: OperatorRuntime,
    records: Sequence[HttpRequestLogRecord],
) -> None:
    _operator_log("validating authoritative workflow artifacts")
    assert not operator_runtime.dashboard_socket_path.exists()

    assert all(record.schema_version == "1.1" for record in records)
    assert all(record.record_id.version == 7 for record in records)
    assert {
        (record.method, record.path) for record in records
    } <= backend_api.AUTHORITATIVE_PUBLIC_ROUTES | {
        backend_api.AUTHORITATIVE_COMMIT_ROUTE
    }

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


@pytest.mark.requires_codex_auth
@pytest.mark.excluded_from_suites
def test_complete_dashboard_backend_codex_commit_and_replay_workflow(
    operator_runtime: OperatorRuntime,
) -> None:
    _assert_deployed_appendwatch_topology(operator_runtime)
    _operator_log("preparing isolated durable-410 checkpoint runtime")
    namekey = target_namekey(operator_runtime)

    with running_dashboard(operator_runtime) as dashboard:
        checkpoint = run_workflow_to_terminal_pull(
            operator_runtime,
            dashboard,
            namekey,
        )

    validate_workflow_artifacts(operator_runtime, checkpoint.records)


@pytest.mark.requires_codex_auth
def test_completed_dashboard_backend_codex_workflow_renders_researcher_card(
    operator_runtime: OperatorRuntime,
) -> None:
    _assert_deployed_appendwatch_topology(operator_runtime)
    _operator_log("preparing isolated completed-workflow runtime")
    namekey = target_namekey(operator_runtime)

    with running_dashboard(operator_runtime) as dashboard:
        checkpoint = run_workflow_to_terminal_pull(
            operator_runtime,
            dashboard,
            namekey,
        )
        card_text = capture_completed_researcher_card(
            dashboard,
            namekey=namekey,
            queued_at_monotonic=checkpoint.queued_at_monotonic,
        )
        elapsed_seconds = time.monotonic() - checkpoint.queued_at_monotonic

    validate_workflow_artifacts(operator_runtime, checkpoint.records)
    emit_researcher_card(card_text)
    _operator_log(
        "full end-to-end execution elapsed time from queue submission through "
        f"final Playwright verification: {elapsed_seconds:.3f}s"
    )
