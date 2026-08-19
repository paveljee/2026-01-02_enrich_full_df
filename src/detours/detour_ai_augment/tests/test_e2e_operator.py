from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Generator, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from urllib import error as urllib_error
from urllib import request as urllib_request

import duckdb
import pytest
from playwright.sync_api import expect, sync_playwright

from src.detours.detour_ai_augment.src.backend import api as backend_api
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.helpers.data_models import NameKey
from src.helpers.duckdb_utils import duckdb_quote_identifier

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
REAL_CONFIG_PATH = REPOSITORY_ROOT / "config_ai_augment.json"
ATTEMPTS_DIR = backend_api.ATTEMPTS_DIR
REPOSITORY_DATA_DIR = REPOSITORY_ROOT / "data"
DETOUR_DATA_DIR = control_ui.DETOUR_DATA_DIR
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
PROCESS_START_TIMEOUT_SECONDS = 300
PROCESS_STOP_TIMEOUT_SECONDS = 30
PROCESS_POLL_SECONDS = 0.1
LOG_WAIT_TIMEOUT_SECONDS = 10
BROWSER_ASSERTION_TIMEOUT_MILLISECONDS = 30_000
BROWSER_CHANNEL = "chrome"
BROWSER_VIEWPORT = {"width": 1600, "height": 1000}
GRID_ROW_SELECTOR = ".ag-center-cols-container .ag-row"
HASH_ALGORITHM = "sha256"
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
RECONCILIATION_LOG_PATTERN = re.compile(
    r"archived attempts reconciled into the detour DB from .*: "
    r"restored (?P<restored>[0-9]+), accepted (?P<accepted>[0-9]+), "
    r"already present and skipped (?P<skipped>[0-9]+), "
    r"invalid (?P<invalid>[0-9]+), discovered (?P<discovered>[0-9]+)"
)
EXPECTED_RESEARCHER_COUNT = backend_api.EXPECTED_SOURCE_RESEARCHERS

pytestmark = pytest.mark.operator


@dataclass(frozen=True, slots=True)
class IsolatedRuntime:
    config_path: Path
    detour_db_path: Path


@dataclass(frozen=True, slots=True)
class ReconciliationCounts:
    restored: int
    accepted: int
    skipped: int
    invalid: int
    discovered: int


@dataclass(frozen=True, slots=True)
class CanonicalDatabaseSnapshot:
    tables: tuple[tuple[str, tuple[str, ...]], ...]
    sequences: tuple[tuple[object, ...], ...]


@dataclass(frozen=True, slots=True)
class BrowserTarget:
    attempt_id: str | None
    source_key: str


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


def isolated_runtime(tmp_path: Path) -> IsolatedRuntime:
    config = json.loads(REAL_CONFIG_PATH.read_text(encoding=TEXT_ENCODING))
    configured_source_db = Path(config["db_file"])
    source_db = (
        configured_source_db
        if configured_source_db.is_absolute()
        else REPOSITORY_ROOT / configured_source_db
    )
    source_db_link = tmp_path / source_db.name
    source_db_link.symlink_to(source_db)
    config["db_file"] = str(source_db_link)
    config["state_file"] = str(tmp_path / TEMP_STATE_FILENAME)
    config["output_dir"] = str(tmp_path / TEMP_OUTPUT_DIRECTORY)
    config_path = tmp_path / TEMP_CONFIG_FILENAME
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding=TEXT_ENCODING,
    )
    return IsolatedRuntime(
        config_path=config_path,
        detour_db_path=backend_api._detour_db_path(source_db_link),
    )


def _collect_process_output(stream: TextIO, output: list[str]) -> None:
    output.extend(stream)


def _assert_control_centre_ports_available() -> None:
    for port in CONTROL_CENTRE_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            if client.connect_ex((control_ui.CONTROL_CENTRE_HOST, port)) == 0:
                pytest.fail(f"operator test requires unused local port {port}")


def _assert_run_journal_idle() -> None:
    active_statuses = {control_ui.RunStatus.QUEUED, control_ui.RunStatus.RUNNING}
    active_runs = tuple(
        run
        for run in control_ui.RunJournal().load_runs().values()
        if run.status in active_statuses
    )
    if active_runs:
        pytest.fail("operator test requires no queued or running dashboard journal entries")


@contextmanager
def running_dashboard(runtime: IsolatedRuntime) -> Generator[DashboardProcess]:
    _assert_control_centre_ports_available()
    _assert_run_journal_idle()
    environment = os.environ.copy()
    environment.pop(PYTEST_CURRENT_TEST_ENV_NAME, None)
    environment[PYTHON_UNBUFFERED_ENV_NAME] = PYTHON_UNBUFFERED_VALUE
    process = subprocess.Popen(
        (*CONTROL_CENTRE_COMMAND_PREFIX, str(runtime.config_path)),
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


def reconciliation_counts(output: list[str]) -> ReconciliationCounts:
    deadline = time.monotonic() + LOG_WAIT_TIMEOUT_SECONDS
    matches: list[tuple[str, str, str, str, str]] = []
    while time.monotonic() < deadline:
        matches = RECONCILIATION_LOG_PATTERN.findall("".join(output))
        if matches:
            break
        time.sleep(PROCESS_POLL_SECONDS)
    if len(matches) != 1:
        raise AssertionError(
            f"expected one archive reconciliation summary, found {len(matches)}:\n"
            + "".join(output)
        )
    restored, accepted, skipped, invalid, discovered = map(int, matches[0])
    return ReconciliationCounts(
        restored=restored,
        accepted=accepted,
        skipped=skipped,
        invalid=invalid,
        discovered=discovered,
    )


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


def archived_manifests(database_path: Path) -> tuple[dict[str, object], ...]:
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        rows = connection.execute(
            f"SELECT {backend_api.ARCHIVED_ATTEMPT_MANIFEST_COLUMN} "
            f"FROM {backend_api.ARCHIVED_ATTEMPTS_TABLE} "
            f"ORDER BY {backend_api.ATTEMPT_ID_KEY}"
        ).fetchall()
    finally:
        connection.close()
    return tuple(json.loads(str(row[0])) for row in rows)


def browser_target(
    runtime: IsolatedRuntime,
    database_path: Path,
) -> BrowserTarget:
    manifests = archived_manifests(database_path)
    accepted = tuple(
        manifest
        for manifest in manifests
        if manifest[backend_api.ATTEMPT_RESULT_KEY] == backend_api.ATTEMPT_RESULT_ACCEPTED
    )
    if accepted:
        manifest = accepted[0]
        return BrowserTarget(
            attempt_id=str(manifest[backend_api.ATTEMPT_ID_KEY]),
            source_key=str(manifest[backend_api.ATTEMPT_SOURCE_KEY]),
        )
    configuration = control_ui.RuntimeConfiguration(config_path=runtime.config_path)
    researcher = next(
        researcher
        for researcher in control_ui.SourceRepository(
            configuration=configuration
        ).load_researchers()
        if researcher.cohort is not control_ui.ResearcherCohort.INELIGIBLE
    )
    return BrowserTarget(
        attempt_id=None,
        source_key=str(researcher.source_key),
    )


def browser_state(
    *,
    target: BrowserTarget,
) -> BrowserState:
    name = NameKey.from_json_key(target.source_key)
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
        search.fill(target.source_key)
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


def attempt_directory_count() -> int:
    return sum(
        path.is_dir() or path.is_symlink()
        for path in ATTEMPTS_DIR.iterdir()
    )


def test_fresh_start_rebuilds_canonical_detour_database(tmp_path: Path) -> None:
    runtime = isolated_runtime(tmp_path)
    assert not runtime.detour_db_path.exists()

    with running_dashboard(runtime) as dashboard:
        assert runtime.detour_db_path.is_file()
        counts = reconciliation_counts(dashboard.output)
    manifests = archived_manifests(runtime.detour_db_path)

    assert counts.discovered > 0
    assert counts.discovered == attempt_directory_count()
    assert counts.skipped == 0
    assert counts.restored == len(manifests)
    assert counts.accepted == sum(
        manifest[backend_api.ATTEMPT_RESULT_KEY] == backend_api.ATTEMPT_RESULT_ACCEPTED
        for manifest in manifests
    )
    assert counts.restored + counts.invalid == counts.discovered


def test_real_browser_exposes_rebuilt_history_and_researcher_card(tmp_path: Path) -> None:
    runtime = isolated_runtime(tmp_path)

    with running_dashboard(runtime) as dashboard:
        reconciliation_counts(dashboard.output)
    target = browser_target(runtime, runtime.detour_db_path)
    with running_dashboard(runtime) as dashboard:
        reconciliation_counts(dashboard.output)
        state = browser_state(target=target)

    if target.attempt_id is not None:
        assert target.attempt_id in state.attempt_history
    assert state.researcher_card.strip()


def test_restart_is_idempotent_for_database_history_and_card(tmp_path: Path) -> None:
    runtime = isolated_runtime(tmp_path)

    with running_dashboard(runtime) as first_dashboard:
        first_counts = reconciliation_counts(first_dashboard.output)
    target = browser_target(runtime, runtime.detour_db_path)
    first_database = canonical_database_snapshot(runtime.detour_db_path)

    with running_dashboard(runtime) as second_dashboard:
        second_counts = reconciliation_counts(second_dashboard.output)
        first_browser = browser_state(target=target)
    second_database = canonical_database_snapshot(runtime.detour_db_path)

    with running_dashboard(runtime) as third_dashboard:
        third_counts = reconciliation_counts(third_dashboard.output)
        second_browser = browser_state(target=target)
    third_database = canonical_database_snapshot(runtime.detour_db_path)

    assert second_database == first_database
    assert third_database == first_database
    assert second_browser == first_browser
    assert second_counts.restored == 0
    assert second_counts.accepted == 0
    assert second_counts.skipped == first_counts.restored
    assert second_counts.invalid == first_counts.invalid
    assert second_counts.discovered == first_counts.discovered
    assert third_counts == second_counts
