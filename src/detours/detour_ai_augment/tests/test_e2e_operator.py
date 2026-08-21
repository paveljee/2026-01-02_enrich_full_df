from __future__ import annotations

import hashlib
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Generator, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO, cast
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import UUID

import duckdb
import pytest
from fastapi import status
from playwright.sync_api import expect, sync_playwright

from src.detours.detour_ai_augment.src.backend import api as backend_api
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.helpers.data_models import NameKey
from src.helpers.data_models.http_request_log import HttpRequestLogRecord
from src.helpers.duckdb_utils import duckdb_quote_identifier

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DETOUR_ROOT = Path(__file__).resolve().parents[1]
REAL_CONFIG_PATH = REPOSITORY_ROOT / "config_ai_augment.json"
REPOSITORY_DATA_DIR = REPOSITORY_ROOT / "data"
DETOUR_DATA_DIR = DETOUR_ROOT / "data"
PRODUCTION_DATA_DIRECTORIES = (REPOSITORY_DATA_DIR, DETOUR_DATA_DIR)
CONTROL_CENTRE_MODULE = "src.detours.detour_ai_augment.src.control_centre.dashboard.ui"
CONTROL_CENTRE_COMMAND_PREFIX = (
    sys.executable,
    "-m",
    CONTROL_CENTRE_MODULE,
    backend_api.CONFIG_OPTION,
)
CONTROL_CENTRE_URL = control_ui.CONTROL_CENTRE_BASE_URL
CONTROL_CENTRE_PORTS = (control_ui.CONTROL_CENTRE_PORT, control_ui.BACKEND_PORT)
CONTROL_CENTRE_READY_LOG = control_ui.Locale.READY_LOG_TEMPLATE.format(
    url=CONTROL_CENTRE_URL
)
PYTEST_CURRENT_TEST_ENV_NAME = "PYTEST_CURRENT_TEST"
PYTHON_UNBUFFERED_ENV_NAME = "PYTHONUNBUFFERED"
PYTHON_UNBUFFERED_VALUE = "1"
TEXT_ENCODING = "utf-8"
TEMP_CONFIG_FILENAME = "config_ai_augment.operator.json"
TEMP_STATE_FILENAME = "pipeline_state.json"
TEMP_OUTPUT_DIRECTORY = "output"
TEMP_REPLAY_LOG_FILENAME = "detour_ai_augment_backend_api_replay_log.jsonl"
TEMP_ROLLOUT_CAS_DIRECTORY = "rollout-cas"
CONFIG_DB_FILE_KEY = "db_file"
CONFIG_STATE_FILE_KEY = "state_file"
CONFIG_OUTPUT_DIR_KEY = "output_dir"
CONFIG_ROLLOUT_CAS_DIR_KEY = "rollout_cas_dir"
CONFIG_FILES_CONFIG_KEY = "files_config"
PROCESS_START_TIMEOUT_SECONDS = 300
PROCESS_STOP_TIMEOUT_SECONDS = 30
PROCESS_POLL_SECONDS = 0.1
SANCTION_TIMEOUT_SECONDS = 300
FULL_WORKFLOW_TIMEOUT_SECONDS = 1_800
REMOTE_COMMAND_TIMEOUT_SECONDS = 30
BROWSER_ASSERTION_TIMEOUT_MILLISECONDS = 30_000
BROWSER_CHANNEL = "chrome"
BROWSER_VIEWPORT = {"width": 1600, "height": 1000}
GRID_ROW_SELECTOR = ".ag-center-cols-container .ag-row"
HASH_ALGORITHM = "sha256"
EMPTY_FILE_SHA256 = hashlib.new(HASH_ALGORITHM).hexdigest()
JSONL_LINE_ENDING = b"\n"
HASH_SEPARATOR = b"\0"
HASH_DIRECTORY_MARKER = b"directory"
HASH_FILE_MARKER = b"file"
HASH_SYMLINK_MARKER = b"symlink"
HASH_OTHER_MARKER = b"other"
CANONICAL_TABLES_SQL = (
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'main' AND table_type = 'BASE TABLE' ORDER BY table_name"
)
SELECT_ALL_SQL_TEMPLATE = "SELECT * FROM {table_name}"
CANONICAL_SEQUENCES_SQL = (
    "SELECT sequence_name, start_value, increment_by, last_value "
    "FROM duckdb_sequences() ORDER BY sequence_name"
)
EXPECTED_RESEARCHER_COUNT = backend_api.EXPECTED_SOURCE_RESEARCHERS
OPERATOR_TARGET_DRAW_NUMBER = "146"
TRACEBACK_MARKER = "Traceback"
TERMINAL_RUN_STATUSES = frozenset({
    control_ui.RunStatus.COMPLETE,
    control_ui.RunStatus.FAILED,
    control_ui.RunStatus.CANCELED,
})
CONTROL_TERMINATION_SIGNALS = (
    signal.SIGINT,
    signal.SIGTERM,
    signal.SIGKILL,
)
OPERATOR_LIVE_OUTPUT = sys.__stdout__ or sys.stdout

pytestmark = pytest.mark.operator


@dataclass(frozen=True, slots=True)
class AuthoritativeRuntime:
    config_path: Path
    detour_db_path: Path
    replay_log_path: Path
    rollout_cas_dir: Path


@dataclass(frozen=True, slots=True)
class CanonicalDatabaseSnapshot:
    tables: tuple[tuple[str, tuple[str, ...]], ...]
    sequences: tuple[tuple[object, ...], ...]


@dataclass(frozen=True, slots=True)
class BrowserTarget:
    attempt_id: str | None
    namekey: str


@dataclass(frozen=True, slots=True)
class BrowserState:
    attempt_history: str
    researcher_card: str


@dataclass(slots=True)
class DashboardProcess:
    process: subprocess.Popen[str]
    output: list[str]
    output_thread: threading.Thread

    def wait_until_ready(self) -> None:
        deadline = time.monotonic() + PROCESS_START_TIMEOUT_SECONDS
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
                    return
            except OSError, urllib_error.URLError:
                time.sleep(PROCESS_POLL_SECONDS)
        raise TimeoutError(
            "Control Centre did not become ready:\n" + "".join(self.output)
        )

    def stop(self) -> None:
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
        self.output_thread.join(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
        if self.process.stdout is not None:
            self.process.stdout.close()

    def wait_until_exit(self) -> None:
        try:
            self.process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("Control Centre did not exit after the operator signal") from exc


def _regular_file_digest(path: Path) -> bytes:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, HASH_ALGORITHM).digest()


def production_data_hash(directory: Path) -> str:
    paths = (directory, *sorted(directory.rglob("*"), key=lambda path: path.as_posix()))
    regular_files = tuple(
        path for path in paths if not path.is_symlink() and path.is_file()
    )
    with ThreadPoolExecutor() as executor:
        file_digests = dict(
            zip(
                regular_files,
                executor.map(_regular_file_digest, regular_files),
                strict=True,
            )
        )
    digest = hashlib.new(HASH_ALGORITHM)
    for path in paths:
        relative_path = path.relative_to(directory).as_posix().encode(TEXT_ENCODING)
        digest.update(relative_path)
        digest.update(HASH_SEPARATOR)
        if path.is_symlink():
            digest.update(HASH_SYMLINK_MARKER)
            digest.update(path.readlink().as_posix().encode(TEXT_ENCODING))
        elif path.is_dir():
            digest.update(HASH_DIRECTORY_MARKER)
        elif path.is_file():
            digest.update(HASH_FILE_MARKER)
            digest.update(file_digests[path])
        else:
            digest.update(HASH_OTHER_MARKER)
        digest.update(HASH_SEPARATOR)
    return digest.hexdigest()


@pytest.fixture(autouse=True)
def production_data_unchanged(operator_aivm: None) -> Iterator[None]:
    before = {
        directory: production_data_hash(directory)
        for directory in PRODUCTION_DATA_DIRECTORIES
    }
    yield
    after = {
        directory: production_data_hash(directory)
        for directory in PRODUCTION_DATA_DIRECTORIES
    }
    assert after == before


def authoritative_runtime(tmp_path: Path) -> AuthoritativeRuntime:
    replay_log_path = tmp_path / TEMP_REPLAY_LOG_FILENAME
    rollout_cas_dir = tmp_path / TEMP_ROLLOUT_CAS_DIRECTORY
    state_path = tmp_path / TEMP_STATE_FILENAME
    output_dir = tmp_path / TEMP_OUTPUT_DIRECTORY
    config_path = tmp_path / TEMP_CONFIG_FILENAME

    config_value: object = json.loads(REAL_CONFIG_PATH.read_text(encoding=TEXT_ENCODING))
    if not isinstance(config_value, dict):
        raise AssertionError("operator configuration must be a JSON object")
    config = cast(dict[str, Any], config_value)
    configured_source_db = Path(str(config[CONFIG_DB_FILE_KEY]))
    source_db = (
        configured_source_db
        if configured_source_db.is_absolute()
        else REPOSITORY_ROOT / configured_source_db
    )
    source_db_link = tmp_path / source_db.name
    source_db_link.symlink_to(source_db)
    replay_log_path.write_text("", encoding=TEXT_ENCODING)

    files_config = config[CONFIG_FILES_CONFIG_KEY]
    if not isinstance(files_config, dict):
        raise AssertionError("files_config must be a JSON object")
    replay_config = files_config[backend_api.REPLAY_LOG_RESOURCE_KEY]
    if not isinstance(replay_config, dict):
        raise AssertionError("replay-log configuration must be a JSON object")
    replay_config[backend_api.RESOURCE_PATH_KEY] = str(replay_log_path)
    replay_config[backend_api.RESOURCE_SHA256_KEY] = EMPTY_FILE_SHA256
    config[CONFIG_DB_FILE_KEY] = str(source_db_link)
    config[CONFIG_STATE_FILE_KEY] = str(state_path)
    config[CONFIG_OUTPUT_DIR_KEY] = str(output_dir)
    config[CONFIG_ROLLOUT_CAS_DIR_KEY] = str(rollout_cas_dir)
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding=TEXT_ENCODING,
    )
    return AuthoritativeRuntime(
        config_path=config_path,
        detour_db_path=backend_api._detour_db_path(source_db_link),
        replay_log_path=replay_log_path,
        rollout_cas_dir=rollout_cas_dir,
    )


def register_current_replay_log_hash(runtime: AuthoritativeRuntime) -> None:
    config_value: object = json.loads(
        runtime.config_path.read_text(encoding=TEXT_ENCODING)
    )
    if not isinstance(config_value, dict):
        raise AssertionError("operator configuration must be a JSON object")
    config = cast(dict[str, Any], config_value)
    files_config = config[CONFIG_FILES_CONFIG_KEY]
    if not isinstance(files_config, dict):
        raise AssertionError("files_config must be a JSON object")
    replay_config = files_config[backend_api.REPLAY_LOG_RESOURCE_KEY]
    if not isinstance(replay_config, dict):
        raise AssertionError("replay-log configuration must be a JSON object")
    with runtime.replay_log_path.open("rb") as replay_stream:
        replay_sha256 = hashlib.file_digest(
            replay_stream,
            HASH_ALGORITHM,
        ).hexdigest()
    replay_config[backend_api.RESOURCE_SHA256_KEY] = replay_sha256
    runtime.config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding=TEXT_ENCODING,
    )


def _collect_process_output(stream: TextIO, output: list[str]) -> None:
    for line in stream:
        output.append(line)
        OPERATOR_LIVE_OUTPUT.write(line)
        OPERATOR_LIVE_OUTPUT.flush()


def _assert_control_centre_ports_available() -> None:
    for port in CONTROL_CENTRE_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            if client.connect_ex((control_ui.CONTROL_CENTRE_HOST, port)) == 0:
                pytest.fail(f"operator test requires unused local port {port}")


@contextmanager
def _running_dashboard_process(
    config_path: Path,
) -> Generator[DashboardProcess]:
    _assert_control_centre_ports_available()
    environment = os.environ.copy()
    environment.pop(PYTEST_CURRENT_TEST_ENV_NAME, None)
    environment[PYTHON_UNBUFFERED_ENV_NAME] = PYTHON_UNBUFFERED_VALUE
    process = subprocess.Popen(
        (*CONTROL_CENTRE_COMMAND_PREFIX, str(config_path)),
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=TEXT_ENCODING,
        bufsize=1,
    )
    if process.stdout is None:
        process.kill()
        raise RuntimeError("Control Centre output pipe is unavailable")
    output: list[str] = []
    output_thread = threading.Thread(
        target=_collect_process_output,
        args=(process.stdout, output),
        daemon=True,
    )
    output_thread.start()
    dashboard = DashboardProcess(
        process=process,
        output=output,
        output_thread=output_thread,
    )
    try:
        dashboard.wait_until_ready()
        yield dashboard
    finally:
        dashboard.stop()


@contextmanager
def running_authoritative_dashboard(
    runtime: AuthoritativeRuntime,
) -> Generator[DashboardProcess]:
    with _running_dashboard_process(runtime.config_path) as dashboard:
        yield dashboard


def canonical_database_snapshot(database_path: Path) -> CanonicalDatabaseSnapshot:
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        table_names = tuple(row[0] for row in connection.execute(CANONICAL_TABLES_SQL).fetchall())
        tables = tuple(
            (
                str(table_name),
                tuple(
                    sorted(
                        repr(row)
                        for row in connection.execute(
                            SELECT_ALL_SQL_TEMPLATE.format(
                                table_name=duckdb_quote_identifier(str(table_name))
                            )
                        ).fetchall()
                    )
                ),
            )
            for table_name in table_names
        )
        sequences = tuple(connection.execute(CANONICAL_SEQUENCES_SQL).fetchall())
    finally:
        connection.close()
    return CanonicalDatabaseSnapshot(tables=tables, sequences=sequences)


def browser_state(
    *,
    target: BrowserTarget,
) -> BrowserState:
    name = NameKey.from_json_key(target.namekey)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=BROWSER_CHANNEL,
            headless=True,
        )
        page = browser.new_page(viewport=BROWSER_VIEWPORT)
        page.set_default_timeout(BROWSER_ASSERTION_TIMEOUT_MILLISECONDS)
        browser_errors: list[str] = []
        page.on(
            "console",
            lambda message: (
                browser_errors.append(message.text) if message.type == "error" else None
            ),
        )
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        page.goto(CONTROL_CENTRE_URL, wait_until="networkidle")
        summary = page.get_by_test_id(control_ui.PAGE_SUMMARY_TEST_ID)
        expect(summary).to_contain_text(f"Total {EXPECTED_RESEARCHER_COUNT}")
        search = page.get_by_label(control_ui.Locale.SEARCH_FILTER)
        search.fill(target.namekey)
        rows = page.get_by_test_id(control_ui.RESEARCHER_GRID_TEST_ID).locator(
            GRID_ROW_SELECTOR
        )
        expect(rows).to_have_count(1)
        rows.first.click()
        history = page.get_by_test_id(control_ui.ATTEMPT_HISTORY_TABLE_TEST_ID)
        expect(history).to_be_visible()
        if target.attempt_id is not None:
            expect(history).to_contain_text(target.attempt_id)
        view_card = page.get_by_test_id(control_ui.VIEW_CARD_TEST_ID)
        expect(view_card).to_be_enabled()
        view_card.click()
        card = page.get_by_test_id(control_ui.PAGE_FOOTER_TEST_ID)
        expect(card).to_contain_text(name.first_name)
        expect(card).to_contain_text(name.last_name)
        state = BrowserState(
            attempt_history=history.inner_text(),
            researcher_card=card.inner_text(),
        )
        browser.close()
    assert browser_errors == [], Counter(browser_errors)
    return state


def operator_target(runtime: AuthoritativeRuntime) -> BrowserTarget:
    configuration = control_ui.RuntimeConfiguration(config_path=runtime.config_path)
    researcher = next(
        item
        for item in control_ui.SourceRepository(
            configuration=configuration
        ).load_researchers()
        if OPERATOR_TARGET_DRAW_NUMBER in item.draw_numbers
        and item.cohort is not control_ui.ResearcherCohort.INELIGIBLE
    )
    return BrowserTarget(attempt_id=None, namekey=str(researcher.namekey))


def browser_execute_action(
    *,
    target: BrowserTarget,
    action: control_ui.RunAction,
) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=BROWSER_CHANNEL,
            headless=True,
        )
        page = browser.new_page(viewport=BROWSER_VIEWPORT)
        page.set_default_timeout(BROWSER_ASSERTION_TIMEOUT_MILLISECONDS)
        browser_errors: list[str] = []
        page.on(
            "console",
            lambda message: (
                browser_errors.append(message.text) if message.type == "error" else None
            ),
        )
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        page.goto(CONTROL_CENTRE_URL, wait_until="networkidle")
        search = page.get_by_label(control_ui.Locale.SEARCH_FILTER)
        search.fill(target.namekey)
        rows = page.get_by_test_id(control_ui.RESEARCHER_GRID_TEST_ID).locator(
            GRID_ROW_SELECTOR
        )
        expect(rows).to_have_count(1)
        rows.first.click()
        execute = page.get_by_test_id(control_ui.EXECUTE_ACTION_TEST_ID)
        action_label = control_ui.ACTION_LABEL_BY_VALUE[action.value]
        expect(execute).to_be_enabled()
        expect(execute).to_have_text(action_label)
        execute.click()
        next_action = (
            control_ui.RunAction.RERUN
            if action is control_ui.RunAction.CANCEL
            else control_ui.RunAction.CANCEL
        )
        expect(execute).to_have_text(
            control_ui.ACTION_LABEL_BY_VALUE[next_action.value],
            timeout=BROWSER_ASSERTION_TIMEOUT_MILLISECONDS,
        )
        browser.close()
    assert browser_errors == [], Counter(browser_errors)


def authoritative_records(
    runtime: AuthoritativeRuntime,
) -> tuple[HttpRequestLogRecord, ...]:
    raw_log = runtime.replay_log_path.read_bytes()
    complete_lines = raw_log.split(JSONL_LINE_ENDING)[:-1]
    return tuple(HttpRequestLogRecord.model_validate_json(line) for line in complete_lines)


def authoritative_request_text(record: HttpRequestLogRecord) -> str:
    if not isinstance(record.request_body, str):
        raise AssertionError("authoritative request body is not text")
    return record.request_body


def authoritative_header(
    headers: Mapping[str, object],
    name: str,
) -> str | None:
    normalized_name = name.casefold()
    for key, value in headers.items():
        if key.casefold() == normalized_name and isinstance(value, str):
            return value
    return None


def authoritative_control_events(
    runtime: AuthoritativeRuntime,
) -> tuple[backend_api.ControlRunEvent, ...]:
    events: list[backend_api.ControlRunEvent] = []
    for record in authoritative_records(runtime):
        if (
            (record.method, record.path)
            != (backend_api.HTTP_POST_METHOD, backend_api.CONTROL_PUSH_PATH)
            or record.response_code != status.HTTP_200_OK
        ):
            continue
        response = backend_api.ControlPushResponse.model_validate_json(
            record.response_body
        )
        if response.duplicate:
            continue
        request = backend_api.ControlPushRequest.model_validate_json(
            authoritative_request_text(record)
        )
        events.append(request.event)
    return tuple(events)


def wait_for_authoritative_sanction(
    *,
    runtime: AuthoritativeRuntime,
    dashboard: DashboardProcess,
    target: BrowserTarget,
) -> backend_api.ControlRun:
    deadline = time.monotonic() + SANCTION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if dashboard.process.poll() is not None:
            raise RuntimeError(
                "Control Centre exited before sanctioning:\n" + "".join(dashboard.output)
            )
        sanctioned = next(
            (
                event
                for event in reversed(authoritative_control_events(runtime))
                if event.kind is backend_api.ControlRunEventKind.SANCTIONED
                and event.namekey == target.namekey
            ),
            None,
        )
        if sanctioned is not None:
            if sanctioned.session_id is None or sanctioned.rollout_jsonl is None:
                raise AssertionError("sanction event is incomplete")
            return backend_api.ControlRun(
                run_id=sanctioned.run_id,
                namekey=sanctioned.namekey,
                session_id=sanctioned.session_id,
                rollout_jsonl=sanctioned.rollout_jsonl,
            )
        time.sleep(PROCESS_POLL_SECONDS)
    raise TimeoutError("Control Centre did not durably sanction the queued operator run")


def wait_for_authoritative_run_status(
    *,
    runtime: AuthoritativeRuntime,
    dashboard: DashboardProcess,
    run_id: UUID,
) -> control_ui.RunRecord:
    deadline = time.monotonic() + FULL_WORKFLOW_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if dashboard.process.poll() is not None:
            raise RuntimeError(
                "Control Centre exited before completion:\n" + "".join(dashboard.output)
            )
        run = control_ui.replay_run_events(
            authoritative_control_events(runtime)
        ).get(run_id)
        if run is not None and run.status in TERMINAL_RUN_STATUSES:
            return run
        time.sleep(PROCESS_POLL_SECONDS)
    raise TimeoutError(f"operator run {run_id} did not reach a terminal status")


def accepted_submission_commit(
    *,
    runtime: AuthoritativeRuntime,
    attempt_id: str,
) -> tuple[int, backend_api.SubmissionCommit]:
    matches: list[tuple[int, backend_api.SubmissionCommit]] = []
    for line_number, record in enumerate(
        authoritative_records(runtime),
        start=backend_api.AUTHORITATIVE_FIRST_LINE,
    ):
        if (
            (record.method, record.path) != backend_api.AUTHORITATIVE_COMMIT_ROUTE
            or record.response_code != status.HTTP_200_OK
        ):
            continue
        commit = backend_api.SubmissionCommit.model_validate_json(
            authoritative_request_text(record)
        )
        if commit.attempt_id == attempt_id:
            matches.append((line_number, commit))
    if len(matches) != 1:
        raise AssertionError(
            f"expected one accepted commit for {attempt_id}, found {len(matches)}"
        )
    return matches[0]


def public_push_line_number(
    *,
    runtime: AuthoritativeRuntime,
    transaction_id: str,
) -> int:
    matches = tuple(
        line_number
        for line_number, record in enumerate(
            authoritative_records(runtime),
            start=backend_api.AUTHORITATIVE_FIRST_LINE,
        )
        if (record.method, record.path)
        == (backend_api.HTTP_POST_METHOD, backend_api.PUSH_PATH)
        and authoritative_header(
            record.response_headers,
            backend_api.HTTP_TRANSACTION_ID_HEADER,
        )
        == transaction_id
    )
    if len(matches) != 1:
        raise AssertionError(
            f"expected one public push for {transaction_id}, found {len(matches)}"
        )
    return matches[0]


def stored_attempt_record(
    *,
    runtime: AuthoritativeRuntime,
    attempt_id: str,
) -> backend_api.AttemptRecord:
    connection = duckdb.connect(str(runtime.detour_db_path), read_only=True)
    try:
        row = connection.execute(
            f"SELECT {backend_api.CONTROL_ATTEMPT_RECORD_COLUMN} "
            f"FROM {backend_api.CONTROL_ATTEMPTS_TABLE} "
            f"WHERE {backend_api.ATTEMPT_ID_KEY} = ?",
            [attempt_id],
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise AssertionError(f"detour DB has no attempt {attempt_id}")
    return backend_api.AttemptRecord.model_validate_json(str(row[0]))


def aivm_ai_command(command: str, *, check: bool = True) -> str:
    completed = subprocess.run(
        (*control_ui.AIVM_SSH_CONNECTION_COMMAND, control_ui.AIVM_SSH_TARGET, command),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        encoding=TEXT_ENCODING,
        timeout=REMOTE_COMMAND_TIMEOUT_SECONDS,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"AIVM command failed with {completed.returncode}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def remote_run_pid(run_id: UUID) -> control_ui.RemotePid:
    pid_path = control_ui.CODEX_WORKDIR / control_ui.CODEX_RUN_PID_TEMPLATE.format(
        run_id=run_id
    )
    pid_text = aivm_ai_command(
        control_ui.CODEX_REMOTE_PID_READ_COMMAND_TEMPLATE.format(
            pid_path=shlex.quote(str(pid_path)),
        )
    )
    if not pid_text.isdecimal():
        raise AssertionError(f"operator run {run_id} has no remote PID")
    return control_ui.RemotePid(int(pid_text))


def remote_pid_is_alive(remote_pid: control_ui.RemotePid) -> bool:
    output = aivm_ai_command(
        control_ui.CODEX_REMOTE_PROCESS_ALIVE_COMMAND_TEMPLATE.format(
            remote_pid=int(remote_pid),
            alive_marker=shlex.quote(control_ui.CODEX_REMOTE_PROCESS_ALIVE_MARKER),
        ),
        check=False,
    )
    return output == control_ui.CODEX_REMOTE_PROCESS_ALIVE_MARKER


def kill_remote_pid(remote_pid: control_ui.RemotePid) -> None:
    aivm_ai_command(
        control_ui.CODEX_REMOTE_SIGNAL_COMMAND_TEMPLATE.format(
            signal=control_ui.CODEX_REMOTE_KILL_SIGNAL,
            remote_pid=int(remote_pid),
        ),
        check=False,
    )


def wait_for_control_centre_ports_available() -> None:
    deadline = time.monotonic() + PROCESS_STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        occupied = False
        for port in CONTROL_CENTRE_PORTS:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                occupied = occupied or (
                    client.connect_ex((control_ui.CONTROL_CENTRE_HOST, port)) == 0
                )
        if not occupied:
            return
        time.sleep(PROCESS_POLL_SECONDS)
    raise TimeoutError("Control Centre/backend ports remained occupied after termination")


# Deferred operator scenarios. Do not delete: adapt these from their former
# attempts-directory/manifest assertions to authoritative replay JSONL fixtures
# after the accepted-run operator contour is proven.
#
# def test_fresh_start_rebuilds_canonical_detour_database(tmp_path: Path) -> None:
#     runtime = isolated_runtime(tmp_path)
#     assert not runtime.detour_db_path.exists()
#
#     with running_dashboard(runtime) as dashboard:
#         assert runtime.detour_db_path.is_file()
#         counts = reconciliation_counts(dashboard.output)
#     manifests = archived_manifests(runtime.detour_db_path)
#
#     assert counts.discovered > 0
#     assert counts.discovered == attempt_directory_count(runtime)
#     assert counts.skipped == 0
#     assert counts.restored == len(manifests)
#     assert counts.accepted == sum(
#         manifest[backend_api.ATTEMPT_RESULT_KEY]
#         == backend_api.ATTEMPT_RESULT_ACCEPTED
#         for manifest in manifests
#     )
#     assert counts.restored + counts.invalid == counts.discovered
#
#
# def test_real_browser_exposes_rebuilt_history_and_researcher_card(
#     tmp_path: Path,
# ) -> None:
#     runtime = isolated_runtime(tmp_path)
#
#     with running_dashboard(runtime) as dashboard:
#         reconciliation_counts(dashboard.output)
#     target = browser_target(runtime, runtime.detour_db_path)
#     with running_dashboard(runtime) as dashboard:
#         reconciliation_counts(dashboard.output)
#         state = browser_state(target=target)
#
#     if target.attempt_id is not None:
#         assert target.attempt_id in state.attempt_history
#     assert state.researcher_card.strip()
#
#
# def test_restart_is_idempotent_for_database_history_and_card(
#     tmp_path: Path,
# ) -> None:
#     runtime = isolated_runtime(tmp_path)
#
#     with running_dashboard(runtime) as first_dashboard:
#         first_counts = reconciliation_counts(first_dashboard.output)
#     target = browser_target(runtime, runtime.detour_db_path)
#     first_database = canonical_database_snapshot(runtime.detour_db_path)
#
#     with running_dashboard(runtime) as second_dashboard:
#         second_counts = reconciliation_counts(second_dashboard.output)
#         first_browser = browser_state(target=target)
#     second_database = canonical_database_snapshot(runtime.detour_db_path)
#
#     with running_dashboard(runtime) as third_dashboard:
#         third_counts = reconciliation_counts(third_dashboard.output)
#         second_browser = browser_state(target=target)
#     third_database = canonical_database_snapshot(runtime.detour_db_path)
#
#     assert second_database == first_database
#     assert third_database == first_database
#     assert second_browser == first_browser
#     assert second_counts.restored == 0
#     assert second_counts.accepted == 0
#     assert second_counts.skipped == first_counts.restored
#     assert second_counts.invalid == first_counts.invalid
#     assert second_counts.discovered == first_counts.discovered
#     assert third_counts == second_counts


def test_existing_aivm_exposes_the_persisted_appendwatch_topology(
    tmp_path: Path,
) -> None:
    runtime = authoritative_runtime(tmp_path)

    configuration = control_ui.RuntimeConfiguration(config_path=runtime.config_path)

    assert configuration.appendwatch_report.is_file()
    assert configuration.appendwatch_report.stat().st_size


def test_sanctioned_pull_succeeds_through_the_real_dashboard_and_aivm(
    tmp_path: Path,
) -> None:
    runtime = authoritative_runtime(tmp_path)
    target = operator_target(runtime)

    with running_authoritative_dashboard(runtime) as dashboard:
        browser_execute_action(target=target, action=control_ui.RunAction.QUEUE)
        sanctioned = wait_for_authoritative_sanction(
            runtime=runtime,
            dashboard=dashboard,
            target=target,
        )
        request = urllib_request.Request(
            control_ui.BACKEND_PULL_URL,
            method=backend_api.HTTP_GET_METHOD,
        )
        with urllib_request.urlopen(
            request,
            timeout=control_ui.CONTROL_HTTP_TIMEOUT_SECONDS,
        ) as response:
            pull_rows = tuple(
                json.loads(line)
                for line in response.read().decode(TEXT_ENCODING).splitlines()
            )
        browser_execute_action(target=target, action=control_ui.RunAction.CANCEL)
        terminal = wait_for_authoritative_run_status(
            runtime=runtime,
            dashboard=dashboard,
            run_id=sanctioned.run_id,
        )

    events = authoritative_control_events(runtime)
    name = NameKey.from_json_key(target.namekey)
    assert pull_rows[-1][backend_api.KTP_FIRST_NAME_COL] == name.first_name
    assert pull_rows[-1][backend_api.KTP_LAST_NAME_COL] == name.last_name
    assert terminal.status is control_ui.RunStatus.CANCELED
    assert events[-1].run_id == sanctioned.run_id
    assert events[-1].kind is backend_api.ControlRunEventKind.CANCELED


def test_terminal_pre_push_failure_persists_in_db_and_browser_after_restart(
    tmp_path: Path,
) -> None:
    runtime = authoritative_runtime(tmp_path)
    target = operator_target(runtime)

    with running_authoritative_dashboard(runtime) as dashboard:
        browser_execute_action(target=target, action=control_ui.RunAction.QUEUE)
        sanctioned = wait_for_authoritative_sanction(
            runtime=runtime,
            dashboard=dashboard,
            target=target,
        )
        remote_pid = remote_run_pid(sanctioned.run_id)
        kill_remote_pid(remote_pid)
        terminal = wait_for_authoritative_run_status(
            runtime=runtime,
            dashboard=dashboard,
            run_id=sanctioned.run_id,
        )

    stored_events = authoritative_control_events(runtime)
    register_current_replay_log_hash(runtime)
    with running_authoritative_dashboard(runtime):
        restarted_browser = browser_state(target=target)

    assert terminal.status is control_ui.RunStatus.FAILED
    assert stored_events[-1].run_id == sanctioned.run_id
    assert stored_events[-1].kind is backend_api.ControlRunEventKind.FAILED
    assert control_ui.RunStatus.FAILED.value in restarted_browser.attempt_history.casefold()


def test_dashboard_rebuilds_exact_db_and_history_after_database_deletion(
    tmp_path: Path,
) -> None:
    runtime = authoritative_runtime(tmp_path)
    target = operator_target(runtime)

    with running_authoritative_dashboard(runtime) as dashboard:
        browser_execute_action(target=target, action=control_ui.RunAction.QUEUE)
        sanctioned = wait_for_authoritative_sanction(
            runtime=runtime,
            dashboard=dashboard,
            target=target,
        )
        kill_remote_pid(remote_run_pid(sanctioned.run_id))
        terminal = wait_for_authoritative_run_status(
            runtime=runtime,
            dashboard=dashboard,
            run_id=sanctioned.run_id,
        )
        first_browser = browser_state(target=target)
    events = authoritative_control_events(runtime)
    first_database = canonical_database_snapshot(runtime.detour_db_path)
    assert terminal.status is control_ui.RunStatus.FAILED

    register_current_replay_log_hash(runtime)
    runtime.detour_db_path.unlink()

    with running_authoritative_dashboard(runtime):
        rebuilt_browser = browser_state(target=target)
    rebuilt_database = canonical_database_snapshot(runtime.detour_db_path)

    assert authoritative_control_events(runtime) == events
    assert rebuilt_database == first_database
    assert rebuilt_browser == first_browser
    assert control_ui.RunStatus.FAILED.value in rebuilt_browser.attempt_history.casefold()


@pytest.mark.parametrize(
    "termination_signal",
    CONTROL_TERMINATION_SIGNALS,
    ids=lambda value: signal.Signals(value).name,
)
def test_dashboard_signal_chaos_leaves_no_orphans_and_recovers_run_history(
    termination_signal: signal.Signals,
    tmp_path: Path,
) -> None:
    runtime = authoritative_runtime(tmp_path)
    target = operator_target(runtime)

    with running_authoritative_dashboard(runtime) as dashboard:
        browser_execute_action(target=target, action=control_ui.RunAction.QUEUE)
        sanctioned = wait_for_authoritative_sanction(
            runtime=runtime,
            dashboard=dashboard,
            target=target,
        )
        remote_pid = remote_run_pid(sanctioned.run_id)
        dashboard.process.send_signal(termination_signal)
        dashboard.wait_until_exit()
        interrupted_output = "".join(dashboard.output)

    wait_for_control_centre_ports_available()
    register_current_replay_log_hash(runtime)
    with running_authoritative_dashboard(runtime) as restarted_dashboard:
        terminal = wait_for_authoritative_run_status(
            runtime=runtime,
            dashboard=restarted_dashboard,
            run_id=sanctioned.run_id,
        )
        recovered_browser = browser_state(target=target)
        restarted_output = "".join(restarted_dashboard.output)

    assert terminal.status is control_ui.RunStatus.FAILED
    assert not remote_pid_is_alive(remote_pid)
    assert control_ui.RunStatus.FAILED.value in recovered_browser.attempt_history.casefold()
    assert TRACEBACK_MARKER not in interrupted_output
    assert TRACEBACK_MARKER not in restarted_output


def test_complete_dashboard_aivm_codex_push_db_and_card_workflow(
    tmp_path: Path,
) -> None:
    runtime = authoritative_runtime(tmp_path)
    target = operator_target(runtime)

    with running_authoritative_dashboard(runtime) as dashboard:
        browser_execute_action(target=target, action=control_ui.RunAction.QUEUE)
        sanctioned = wait_for_authoritative_sanction(
            runtime=runtime,
            dashboard=dashboard,
            target=target,
        )
        terminal = wait_for_authoritative_run_status(
            runtime=runtime,
            dashboard=dashboard,
            run_id=sanctioned.run_id,
        )
        assert terminal.status is control_ui.RunStatus.COMPLETE, "".join(dashboard.output)
        assert terminal.accepted_attempt_id is not None
        accepted_target = BrowserTarget(
            attempt_id=str(terminal.accepted_attempt_id),
            namekey=target.namekey,
        )
        completed_browser = browser_state(target=accepted_target)

    accepted_attempt_id = str(terminal.accepted_attempt_id)
    commit_line, commit = accepted_submission_commit(
        runtime=runtime,
        attempt_id=accepted_attempt_id,
    )
    push_line = public_push_line_number(
        runtime=runtime,
        transaction_id=commit.transaction_id,
    )
    stored_attempt = stored_attempt_record(
        runtime=runtime,
        attempt_id=accepted_attempt_id,
    )
    assert commit_line < push_line
    assert commit.sanction == sanctioned
    assert commit.outcome.result == backend_api.ATTEMPT_RESULT_ACCEPTED
    assert stored_attempt.run_id == sanctioned.run_id
    assert stored_attempt.namekey == target.namekey
    assert stored_attempt.result == backend_api.ATTEMPT_RESULT_ACCEPTED
    assert commit.rollout is not None
    rollout_blob = runtime.rollout_cas_dir / backend_api.ROLLOUT_CAS_FILENAME_TEMPLATE.format(
        sha256=commit.rollout.sha256
    )
    assert rollout_blob.is_file()
    assert rollout_blob.stat().st_size == commit.rollout.size
    assert _regular_file_digest(rollout_blob).hex() == commit.rollout.sha256

    register_current_replay_log_hash(runtime)
    with running_authoritative_dashboard(runtime):
        restarted_browser = browser_state(target=accepted_target)

    assert completed_browser == restarted_browser
    assert accepted_attempt_id in restarted_browser.attempt_history
    assert restarted_browser.researcher_card.strip()
