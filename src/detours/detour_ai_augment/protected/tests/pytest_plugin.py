from __future__ import annotations

import asyncio
import inspect
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

import pytest
from pydantic import PrivateAttr

from src.helpers.architecture import FrozenStrictModel

DEPLOY_SCRIPT_RELATIVE_PATH = (
    Path("src")
    / "detours"
    / "detour_ai_augment"
    / "protected"
    / "src"
    / "agent_runtime"
    / "deploy.sh"
)
OPERATOR_MARKER = "operator"
USE_ROOTPATH_TMP_MARKER = "use_rootpath_tmp"
REQUIRES_CODEX_AUTH_MARKER = "requires_codex_auth"
EXCLUDED_FROM_SUITES_MARKER = "excluded_from_suites"
NEEDS_SUDO_MARKER = "needs_sudo"
OPERATOR_REDEPLOY_OPTION = "always_redeploy"
OPERATOR_YES_OPTION = "operator_yes"
RUN_EXCLUDED_FROM_SUITES_OPTION = "run_excluded_from_suites"
PLAYWRIGHT_CHROMIUM_OPTION = "playwright_chromium"
PLAYWRIGHT_CHROMIUM_CLI_OPTION = "--playwright-chromium"
OPENALEX_API_KEY_ENV_NAME = "OPENALEX_API_KEY"
REPOSITORY_ROOT_ENV_NAME = "REPO_DIR"
AIVM_INSTANCE = "aivm"
AIVM_USER = "ai"
AIVM_CODEX_BIN_PATH = "/home/ai/.local/bin/codex"
AIVM_OPENALEX_ENV_PATH = "/home/ai/workdir/.openalex.env"
AIVM_START_COMMAND = ("limactl", "start", AIVM_INSTANCE)
AIVM_PROBE_COMMAND = ("limactl", "shell", "--workdir=/", AIVM_INSTANCE, "true")
AIVM_CODEX_COMMAND_PREFIX = (
    "limactl",
    "shell",
    "--workdir=/",
    AIVM_INSTANCE,
    "sudo",
    "--user",
    AIVM_USER,
    "--set-home",
    AIVM_CODEX_BIN_PATH,
)
AIVM_CODEX_AUTH_STATUS_COMMAND = (*AIVM_CODEX_COMMAND_PREFIX, "login", "status")
AIVM_CODEX_DEVICE_AUTH_COMMAND = (
    *AIVM_CODEX_COMMAND_PREFIX,
    "login",
    "--device-auth",
)
AIVM_OPENALEX_KEY_COMMAND = (
    "limactl",
    "shell",
    "--workdir=/",
    AIVM_INSTANCE,
    "sudo",
    "--user",
    AIVM_USER,
    "bash",
    "-lc",
    f"test -f {AIVM_OPENALEX_ENV_PATH} "
    f'&& test "$(stat -c %a {AIVM_OPENALEX_ENV_PATH})" = 600 '
    f"&& . {AIVM_OPENALEX_ENV_PATH} "
    f'&& test -n "${{{OPENALEX_API_KEY_ENV_NAME}:-}}" '
    f'&& printf \'%s\' "${OPENALEX_API_KEY_ENV_NAME}"',
)
AIVM_APPENDWATCH_PROBE_COMMAND = (
    "limactl",
    "shell",
    "--workdir=/",
    AIVM_INSTANCE,
    "sudo",
    "systemctl",
    "is-active",
    "--quiet",
    "aivm-appendwatch.service",
)
TEST_LIMA_CONFIG_FILENAME = "lima.yaml"
TEST_LIMA_MOUNT_DIRECTORY = "lima-mount"
TEST_GUEST_MOUNT_POINT = "/home/ai/operator-fixture"
TEST_APPENDWATCH_RELATIVE_PATH = ".aivm-control/appendwatch/appendwatch-tree.txt"
TEST_APPENDWATCH_CONTENT = ".\n"
TEXT_ENCODING = "utf-8"
OPERATOR_PROBE_TIMEOUT_SECONDS = 10
OPERATOR_START_TIMEOUT_SECONDS = 300
OPERATOR_DEPLOY_TIMEOUT_SECONDS = 1_800
OPERATOR_CODEX_AUTH_TIMEOUT_SECONDS = 900
OPERATOR_PROMPT = "Redeploy AIVM before each operator test? [y/N] "
OPERATOR_START_PROMPT = (
    "AIVM is not reachable. Start it for operator tests? "
    "Note it will remain running after the tests. [y/N] "
)
OPERATOR_CODEX_AUTH_PROMPT = (
    "Codex is not authenticated inside AIVM. Run "
    "`codex login --device-auth` now? [y/N] "
)
OPERATOR_MARK_DESCRIPTION = "real operator-machine AIVM and full-stack contour"
REQUIRES_CODEX_AUTH_MARK_DESCRIPTION = (
    "requires an authenticated Codex CLI in the AI Agent Runtime"
)
EXCLUDED_FROM_SUITES_MARK_DESCRIPTION = (
    "excluded from default test suites; run only when explicitly requested"
)
NEEDS_SUDO_MARK_DESCRIPTION = "requires pytest to run with root privileges"
OPERATOR_SKIP_REASON = "operator test (run with: pytest -m operator)"
EXCLUDED_FROM_SUITES_SKIP_REASON = (
    "excluded from default suites (run its node ID with "
    "--run-excluded-from-suites and any required suite marker)"
)
OPERATOR_AIVM_UNAVAILABLE = (
    f"AIVM instance {AIVM_INSTANCE!r} is not running or reachable"
)
OPERATOR_AIVM_START_REFUSED = (
    f"AIVM instance {AIVM_INSTANCE!r} must be running for operator tests"
)
OPERATOR_AIVM_START_FAILED = (
    f"AIVM instance {AIVM_INSTANCE!r} could not be started"
)
OPERATOR_DEPLOY_KEY_MISSING = (
    f"{OPENALEX_API_KEY_ENV_NAME} is required in the operator environment "
    "when redeploying AIVM"
)
OPERATOR_GUEST_KEY_MISSING = (
    f"{OPENALEX_API_KEY_ENV_NAME} is unavailable through "
    f"{AIVM_OPENALEX_ENV_PATH} in AIVM instance {AIVM_INSTANCE!r}"
)
OPERATOR_APPENDWATCH_UNAVAILABLE = (
    f"appendwatch is not active in AIVM instance {AIVM_INSTANCE!r}"
)
OPERATOR_CODEX_AUTH_REQUIRED = (
    f"Codex authentication is required in AIVM instance {AIVM_INSTANCE!r}"
)
OPERATOR_CODEX_AUTH_FAILED = (
    f"Codex device authentication failed in AIVM instance {AIVM_INSTANCE!r}"
)
OPERATOR_SANCTUARY_NOTICE = (
    "Operator sanctuary: repository production access is read-only. Every test "
    "verifies complete pre/post hashes of both production data trees and the original "
    "file-based NiceGUI storage path. The Lima "
    "aivm instance is ephemeral and is outside this preservation guarantee."
)
OPERATOR_REDEPLOY_NOTICE = (
    "Redeploy enabled: before every test, deploy.sh may delete and recreate aivm "
    "and provision its OS packages, ai user, SSH and appendwatch services, "
    "VS Code/Codex installations, and guest configuration, work, and session "
    "files. The instance remains after the test."
)
OPERATOR_REUSE_NOTICE = (
    "Redeploy disabled: the existing aivm must be reachable and the real contour "
    "may inspect or modify it as ephemeral state. The instance remains after the "
    "test."
)
OPERATOR_REDEPLOY_STASH_KEY = pytest.StashKey[bool]()
ORIGINAL_NICEGUI_STORAGE_PATH = pytest.StashKey[Path]()


def _operator_log(message: str) -> None:
    print(f"[operator-preflight] {message}", flush=True)


def _operator_requested(config: pytest.Config) -> bool:
    """
    Note: only recognizes exactly `-m operator`, so
    not intended to be combined with any markers.

    signed off: human
    """
    return (config.option.markexpr or "").strip() == OPERATOR_MARKER


def _codex_is_authenticated(
    deployment_environment: dict[str, str],
    *,
    repository_root: Path,
) -> bool:
    try:
        result = subprocess.run(
            AIVM_CODEX_AUTH_STATUS_COMMAND,
            cwd=repository_root,
            env=deployment_environment,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=OPERATOR_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise pytest.UsageError(OPERATOR_CODEX_AUTH_REQUIRED) from exc
    return result.returncode == 0


def _ensure_codex_is_authenticated(
    deployment_environment: dict[str, str],
    *,
    repository_root: Path,
) -> None:
    _operator_log("checking guest Codex authentication")
    if _codex_is_authenticated(
        deployment_environment,
        repository_root=repository_root,
    ):
        _operator_log("guest Codex authentication is available")
        return
    _operator_log("guest Codex authentication is unavailable")
    _operator_log(OPERATOR_CODEX_AUTH_PROMPT.rstrip())
    try:
        reply = input().strip().casefold()
    except EOFError as exc:
        raise pytest.UsageError(OPERATOR_CODEX_AUTH_REQUIRED) from exc
    if reply not in {"y", "yes"}:
        raise pytest.UsageError(OPERATOR_CODEX_AUTH_REQUIRED)
    _operator_log("starting guest Codex device authentication")
    try:
        subprocess.run(
            AIVM_CODEX_DEVICE_AUTH_COMMAND,
            cwd=repository_root,
            env=deployment_environment,
            check=True,
            timeout=OPERATOR_CODEX_AUTH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise pytest.UsageError(OPERATOR_CODEX_AUTH_FAILED) from exc
    if not _codex_is_authenticated(
        deployment_environment,
        repository_root=repository_root,
    ):
        raise pytest.UsageError(OPERATOR_CODEX_AUTH_FAILED)
    _operator_log("guest Codex device authentication completed")


def pytest_addoption(parser: pytest.Parser) -> None:
    browser_group = parser.getgroup("control-centre UI E2E")
    browser_group.addoption(
        PLAYWRIGHT_CHROMIUM_CLI_OPTION,
        action="store_true",
        dest=PLAYWRIGHT_CHROMIUM_OPTION,
        default=False,
        help="use Playwright Chromium instead of the default Google Chrome channel",
    )
    group = parser.getgroup(OPERATOR_MARKER)
    group.addoption(
        "--always-redeploy",
        action="store_true",
        dest=OPERATOR_REDEPLOY_OPTION,
        default=True,
    )
    group.addoption(
        "--no-redeploy",
        action="store_false",
        dest=OPERATOR_REDEPLOY_OPTION,
    )
    group.addoption(
        "--yes",
        action="store_true",
        dest=OPERATOR_YES_OPTION,
        default=False,
    )
    group.addoption(
        "--run-excluded-from-suites",
        action="store_true",
        dest=RUN_EXCLUDED_FROM_SUITES_OPTION,
        default=False,
    )


def pytest_configure(config: pytest.Config) -> None:
    # NiceGUI initializes general persistence at import, before ordinary fixtures run.
    if "nicegui" in sys.modules:
        raise pytest.UsageError("NiceGUI imported before test storage isolation")
    config.stash[ORIGINAL_NICEGUI_STORAGE_PATH] = Path(
        os.environ.get("NICEGUI_STORAGE_PATH", ".nicegui"),
    ).resolve()
    directory = tempfile.TemporaryDirectory(prefix="ai-augment-pytest-nicegui-")
    environment = pytest.MonkeyPatch()
    environment.setenv("NICEGUI_STORAGE_PATH", directory.name)
    environment.delenv("NICEGUI_REDIS_URL", raising=False)
    config.add_cleanup(environment.undo)
    config.add_cleanup(directory.cleanup)
    config.addinivalue_line(
        "markers",
        f"{USE_ROOTPATH_TMP_MARKER}: retain tmp_path data under project-root/tmp",
    )
    config.addinivalue_line(
        "markers", "python_subprocess: isolated Python child process via explicit shared fixture",
    )
    config.addinivalue_line(
        "markers", "socketless_lifecycle: framework lifecycle with socket serving substituted",
    )
    config.addinivalue_line(
        "markers",
        f"{OPERATOR_MARKER}: {OPERATOR_MARK_DESCRIPTION}",
    )
    config.addinivalue_line(
        "markers",
        f"{REQUIRES_CODEX_AUTH_MARKER}: {REQUIRES_CODEX_AUTH_MARK_DESCRIPTION}",
    )
    config.addinivalue_line(
        "markers",
        f"{EXCLUDED_FROM_SUITES_MARKER}: {EXCLUDED_FROM_SUITES_MARK_DESCRIPTION}",
    )
    config.addinivalue_line(
        "markers",
        f"{NEEDS_SUDO_MARKER}: {NEEDS_SUDO_MARK_DESCRIPTION}",
    )
    redeploy = bool(config.getoption(OPERATOR_REDEPLOY_OPTION))
    operator_requested = _operator_requested(config)
    if operator_requested:
        print(OPERATOR_SANCTUARY_NOTICE)
    if operator_requested and redeploy and not config.getoption(OPERATOR_YES_OPTION):
        try:
            reply = input(OPERATOR_PROMPT).strip().casefold()
        except EOFError as exc:
            raise pytest.UsageError(
                "operator redeployment confirmation requires --yes or --no-redeploy"
            ) from exc
        redeploy = reply in {"y", "yes"}
    if operator_requested:
        print(OPERATOR_REDEPLOY_NOTICE if redeploy else OPERATOR_REUSE_NOTICE)
    config.stash[OPERATOR_REDEPLOY_STASH_KEY] = redeploy


@pytest.fixture
def tmp_path(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Path:
    if request.node.get_closest_marker(USE_ROOTPATH_TMP_MARKER) is None:
        return tmp_path

    root = request.config.rootpath / "tmp"
    root.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="test.", dir=root))
    print(
        f"[test-data] {request.node.nodeid}: retained {directory}",
        flush=True,
    )
    return directory


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption(RUN_EXCLUDED_FROM_SUITES_OPTION):
        skip_excluded = pytest.mark.skip(reason=EXCLUDED_FROM_SUITES_SKIP_REASON)
        for item in items:
            if item.get_closest_marker(EXCLUDED_FROM_SUITES_MARKER) is not None:
                item.add_marker(skip_excluded)
    if _operator_requested(config):
        return
    skip_operator = pytest.mark.skip(reason=OPERATOR_SKIP_REASON)
    for item in items:
        if item.get_closest_marker(OPERATOR_MARKER) is not None:
            item.add_marker(skip_operator)


class PythonProcess(FrozenStrictModel):
    """Own bounded Python children; do not alter their environment or mock their code."""

    _children: list[subprocess.Popen[str]] = PrivateAttr(default_factory=list)

    @staticmethod
    def source(target: Callable[[], None]) -> str:
        # Serialize only the helper function, not plugin imports or parent globals. The
        # deployed-layout check must resolve its imports from the isolated child cwd/env.
        return f"{textwrap.dedent(inspect.getsource(target))}\n{target.__name__}()\n"

    def popen(
        self, target: Callable[[], None], *args: str, cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.Popen[str]:
        child = subprocess.Popen(
            [sys.executable, "-c", self.source(target), *args], cwd=cwd, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self._children.append(child)
        return child

    def run(
        self, target: Callable[[], None], *args: str, timeout: float, stdin: str = "",
        cwd: Path | None = None, env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        child = self.popen(target, *args, cwd=cwd, env=env)
        try:
            stdout, stderr = child.communicate(input=stdin, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            child.kill()
            stdout, stderr = child.communicate(timeout=5)
            exc.output, exc.stderr = stdout.encode(), stderr.encode()
            raise
        assert child.returncode is not None
        return subprocess.CompletedProcess(child.args, child.returncode, stdout, stderr)

    def close(self) -> None:
        for child in reversed(self._children):
            try:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.communicate(timeout=5)
            finally:
                for stream in (child.stdin, child.stdout, child.stderr):
                    if stream is not None:
                        stream.close()


@pytest.fixture
def python_process() -> Iterator[PythonProcess]:
    process = PythonProcess()
    try:
        yield process
    finally:
        process.close()


class SocketlessDashboardLifecycle(Protocol):
    def __call__(self, *, publish: bool, failure: str) -> subprocess.CompletedProcess[str]: ...


def nicegui_test_environment(
    storage_path: Path, *, base: dict[str, str] | None = None,
) -> dict[str, str]:
    environment = os.environ.copy() if base is None else base.copy()
    environment["NICEGUI_STORAGE_PATH"] = str(storage_path.resolve())
    environment.pop("NICEGUI_REDIS_URL", None)
    return environment


@pytest.fixture
def nicegui_storage_path(tmp_path: Path) -> Path:
    return tmp_path / "nicegui"


def nicegui_persistence_process() -> None:
    import json
    import os
    import sys
    from pathlib import Path

    from nicegui import app
    from nicegui.storage import Storage

    assert Storage.path == Path(os.environ["NICEGUI_STORAGE_PATH"])
    assert Storage.redis_url is None
    assert dict(app.storage.general) == json.loads(sys.argv[1])
    app.storage.general["test_value"] = sys.argv[2]
    print("NICEGUI_PERSISTED", Storage.path)


def test_nicegui_collection_storage() -> None:
    """Serialized into an isolated test module; also called during its collection."""
    import os
    from pathlib import Path

    from nicegui import app
    from nicegui.storage import Storage

    assert Storage.path != Path(os.environ["TEST_ORIGINAL_STORAGE"])
    assert Storage.redis_url is None
    assert "operator_sentinel" not in app.storage.general
    app.storage.general["test_value"] = "collection"
    Path(os.environ["TEST_STORAGE_RECEIPT"]).write_text(str(Storage.path))
    assert os.environ["TEST_COLLECTION_FAILURE"] == "0"


def nicegui_collection_process() -> None:
    import os
    import sys
    import tempfile
    from pathlib import Path

    import pytest

    from src.detours.detour_ai_augment.protected.tests import pytest_plugin

    root = Path(sys.argv[1])
    original = os.environ["NICEGUI_STORAGE_PATH"]
    redis = os.environ.get("NICEGUI_REDIS_URL")
    original_tmpdir = os.environ.get("TMPDIR")
    tempfile.gettempdir()  # Initialize the cache before pytest's FD capture does.
    original_tempdir = tempfile.tempdir
    test_path = root / "test_collection.py"
    test_path.write_text(pytest_plugin.PythonProcess.source(
        pytest_plugin.test_nicegui_collection_storage,
    ))
    ini = root / "pytest.ini"
    ini.write_text("[pytest]\n")
    result = pytest.main([
        "-q", "-p", pytest_plugin.__name__, "-c", str(ini),
        "--confcutdir", str(root), str(test_path),
    ])
    assert int(result) == int(sys.argv[2])
    storage_path = Path(Path(os.environ["TEST_STORAGE_RECEIPT"]).read_text())
    assert not storage_path.exists()
    assert os.environ.get("TMPDIR") == original_tmpdir
    assert tempfile.tempdir == original_tempdir
    assert os.environ["NICEGUI_STORAGE_PATH"] == original
    assert os.environ.get("NICEGUI_REDIS_URL") == redis
    print("COLLECTION_STORAGE_CLEANED")


def artifact_configuration_process() -> None:
    import sys

    import pytest

    result = pytest.main(sys.argv[1:])
    assert "nicegui" not in sys.modules
    raise SystemExit(result)


def test_pytest_requested_temporary_path(tmp_path: Path) -> None:
    import os
    from pathlib import Path

    assert tmp_path.parent == Path(os.environ["TEST_EXPECTED_BASETEMP"])


def test_rootpath_tmp_directory(
    tmp_path: Path, nicegui_storage_path: Path, request: pytest.FixtureRequest, case: int,
) -> None:
    import os
    from pathlib import Path

    import pytest

    assert Path.cwd() != request.config.rootpath
    assert tmp_path.parent == request.config.rootpath / "tmp"
    assert nicegui_storage_path == tmp_path / "nicegui"
    (tmp_path / "retained.txt").write_text(str(case))
    if os.environ["TEST_FAIL_AFTER_WRITE"] == "1":
        pytest.fail("intentional failure after writing retained data")


def test_artifact_discovery_ordinary_control() -> None:
    from pathlib import Path

    Path("ordinary-executed").write_text("ran")


@pytest.mark.real_api
def test_artifact_discovery_real_api_control() -> None:
    from pathlib import Path

    Path("real-api-executed").write_text("ran")


def artifact_discovery_import_failure() -> None:
    raise RuntimeError("Retained test artifact was imported")


def watcher_fixture_process() -> None:
    import sys

    import pytest

    class ImportAudit:
        def pytest_runtest_call(self, item: pytest.Item) -> None:
            assert isinstance(item, pytest.Function)
            assert "isolated_lima_configuration" not in item.fixturenames
            assert not any(name == "nicegui" or name.startswith("nicegui.")
                           for name in sys.modules)
            assert "fastapi" not in sys.modules

    result = pytest.main(["-q", sys.argv[1]], plugins=[ImportAudit()])
    assert result == 0
    print("WATCHER_FIXTURES_INDEPENDENT")


def backend_startup_process() -> None:
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
        from src.detours.detour_ai_augment.src.backend.helpers.data_models import (
            ai_augment_backend_store as store_models,
        )

        boundary = (
            store_models.initialize_backend_store(runtime, ipc_only=True)
            if args.ipc_only
            else server.backend_store_lifecycle(
                runtime,
                new=args.new,
                confirmed=confirmed,
                yes=args.yes,
            )
        )
        with boundary as capability:
            store = (
                capability._engine
                if isinstance(capability, store_models.AiAugmentQueryBackendStore)
                else capability
            )
            rows = store._execute("SELECT count(*) FROM detour_http_records").fetchone()
            assert rows is not None
            print("STARTUP_READY", rows[0], len(runtime.ai_augment_singular_outerdicts))
    finally:
        api._release_backend_process_lock()


def operator_fixture_bootstrap_process() -> None:
    import sys
    from pathlib import Path

    import requests

    from src.detours.detour_ai_augment.protected.src.backend import ipc
    from src.detours.detour_ai_augment.protected.tests.operator import test_operator_e2e as workflow
    from src.detours.detour_ai_augment.protected.tests.pytest_plugin import threaded_loop_runner
    from src.detours.detour_ai_augment.src.backend import server
    from src.detours.detour_ai_augment.src.backend.helpers.data_models import (
        ai_augment_backend_store as store_models,
    )
    from src.detours.detour_ai_augment.src.backend.helpers.data_models.query_response import (
        QueryResponse,
    )

    root, isolated = map(Path, sys.argv[1:])
    assert not list(isolated.iterdir())
    runtime = workflow._operator_runtime(
        isolated, repository_root=root, dashboard_socket_path=isolated / "ipc.sock",
    )
    assert runtime.backend_store._detour_db_path.is_file()
    context = server.configure_runtime(runtime.config_path, require_namekey=False)
    with (
        store_models.initialize_backend_store(context, ipc_only=True) as store,
        threaded_loop_runner() as runner,
    ):
        response = QueryResponse.from_serialized_json(
            runner.run(
                ipc.handle_query_request(
                    store,
                    requests.Request("GET", "http://invalid/query").prepare(),
                )
            ).content
        )
        assert len(response.ai_augment_singular_outerdicts) == 307
        assert response.attempts == () and response.run_outcome_records == ()
    assert runtime.replay_log_path.read_bytes() == b""
    assert not runtime.dashboard_socket_path.exists()
    print("OPERATOR_BOOTSTRAP_QUERY_OK")


def completed_query_fixture_process() -> None:
    """Seed real Store history and a deliberately stale, private Dashboard snapshot."""
    print("Completed-query fixture: importing dependencies", flush=True)
    import hashlib
    import json
    import os
    import sys
    import time
    from http import HTTPStatus
    from pathlib import Path, PurePosixPath
    from uuid import UUID, uuid7

    import duckdb
    from nicegui import app

    from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
        DOCX_COLUMNS,
        ETAG_HEADER,
        HTTP_CONTENT_TYPE_HEADER,
        HTTP_GET_METHOD,
        PULL_PATH,
        REPLAY_LOG_KEY,
        ContentType,
    )
    from src.detours.detour_ai_augment.protected.tests.pytest_plugin import threaded_loop_runner
    from src.detours.detour_ai_augment.src.backend import api, server
    from src.detours.detour_ai_augment.src.backend.api import LOCATION_HEADER
    from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_event import (
        SOURCE_KEY_HEADER,
        BackendLifecycle,
        CodexRolloutRecord,
    )
    from src.detours.detour_ai_augment.src.backend.helpers.data_models.run_outcome_record import (
        RunOutcomeResponseBody,
        RunOutcomeResponseRecord,
    )
    from src.detours.detour_ai_augment.src.control_centre.dashboard import ui
    from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
        ai_augment_context,
    )
    from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.ai_augment_dashboard_storage import (  # noqa: E501
        AiAugmentDashboardStorage,
    )
    from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_event import (  # noqa: E501
        RunEvent,
    )
    from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome import (  # noqa: E501
        NAME_KEY_HEADER,
        SYNTHETIC_HOST,
        SYNTHETIC_SCHEME,
        RunLifecycle,
        RunOutcomeRequest,
    )
    from src.detours.detour_ai_augment.tests.backend.test_api import (
        OPERATOR_CAPTURED_SESSION_ID,
        operator_capture_rollout,
        persisted_http_record,
        report_for_rollout,
        valid_submission_body,
    )
    from src.detours.detour_ai_augment.tests.control_centre.test_ui import STARTUP_NAMEKEY
    from src.helpers.duckdb_utils import duckdb_quote_identifier as quote
    from src.helpers.schema import DOCX_INNERDICT_TABLE, XLSX_INNERDICT_TABLE
    from src.helpers.vars import (
        KTP_FILENAME_COL,
        KTP_FIRST_NAME_COL,
        KTP_FRAGMENT_COL,
        KTP_FRAGMENT_TYPE_COL,
        KTP_INNERDICT_JSONLINES_COL,
        KTP_LAST_NAME_COL,
        KTP_NAMEKEY_COL,
    )

    config_path = Path(sys.argv[1])
    print("Completed-query fixture: preparing synthetic source", flush=True)
    config = json.loads(config_path.read_text())
    config["match_rule_version"]["codex_match"] = 1
    config_path.write_text(json.dumps(config))
    # Startup-only fixtures omit DOCX contents; the real Dashboard requires ground truth.
    # This is the owned synthetic SOURCE DB, never the detour DB or a production database.
    source = Path(config["db_file"])
    assert source.parent == config_path.parent
    source.chmod(0o600)
    try:
        with duckdb.connect(str(source)) as connection:
            rows = connection.execute(
                f"SELECT {quote(KTP_NAMEKEY_COL)}, {quote(KTP_INNERDICT_JSONLINES_COL)} "
                f"FROM {quote(XLSX_INNERDICT_TABLE)}"
            ).fetchall()
            documents = []
            for namekey, lines in rows:
                row = json.loads(lines.splitlines()[0])
                row.update(dict.fromkeys(DOCX_COLUMNS, "NR"))
                row.update({KTP_FILENAME_COL: "fixture.docx", KTP_FRAGMENT_COL: 1,
                            KTP_FRAGMENT_TYPE_COL: "docx_table"})
                documents.append((namekey, json.dumps(row)))
            connection.executemany(
                f"INSERT INTO {quote(DOCX_INNERDICT_TABLE)} VALUES (?, ?)", documents,
            )
    finally:
        source.chmod(0o400)
    runtime = server.configure_runtime(config_path, require_namekey=False)
    print("Completed-query fixture: runtime ready", flush=True)
    payload = valid_submission_body()
    rollout_bytes = operator_capture_rollout(payload)
    digest = hashlib.sha256(rollout_bytes).hexdigest()
    runtime.pipeline_config.rollout_cas.initialize()
    blob = runtime.pipeline_config.rollout_cas.path / digest[:2] / digest[2:4] / digest
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(rollout_bytes)
    session_id = UUID(OPERATOR_CAPTURED_SESSION_ID)
    relative = PurePosixPath(f"2026/09/03/rollout-2026-09-03T15-16-00-{session_id}.jsonl")
    with server.backend_store_lifecycle(runtime, new=False, confirmed=True, yes=True) as store:
        stale = store._query_snapshot()
        pull = store._append_authoritative_record(
            persisted_http_record(
                record_id=uuid7(),
                method="GET",
                path="/pull",
                response_code=200,
            ).model_copy(
                update={
                    "response_headers": {"content-type": ContentType.NDJSON},
                    "response_body": api.json_line({
                        KTP_FIRST_NAME_COL: STARTUP_NAMEKEY.first_name,
                        KTP_LAST_NAME_COL: STARTUP_NAMEKEY.last_name,
                    }),
                }
            )
        )
        push = store._append_authoritative_record(
            persisted_http_record(
                record_id=uuid7(),
                method="POST",
                path="/push",
                response_code=202,
                request_body=json.dumps(payload),
                response_headers={LOCATION_HEADER: PULL_PATH},
            )
        )
        draft = api._synthetic_commit_record(
            pull_record=pull, push_record=push, session_id=session_id,
            rollout=CodexRolloutRecord(
                sha256=digest, size=len(rollout_bytes), line_count=rollout_bytes.count(b"\n"),
            ),
            rollout_filename=relative.name,
            appendwatch_report=report_for_rollout(relative).encode(),
            namekey=STARTUP_NAMEKEY,
        )
        commit = store._append_authoritative_record(draft)
        print("Completed-query fixture: validating synthetic commit", flush=True)
        validated = store._validate_commit(commit.record_id)
        assert validated.attempt.post_commit_validation.result is BackendLifecycle.ACCEPTED
        assert validated.validation_record is not None
        assert validated.http_records == ()  # Plain initial submission needs no provider requests.
        assert validated.submission is not None
        lines = [api.json_line(validated.submission.normalized_values())]
        if validated.ground_truth_innerdict is not None:
            lines.append(api.json_line(api.select_columns(validated.ground_truth_innerdict.data)))
        gone_pull = store._append_authoritative_record(persisted_http_record(
            record_id=uuid7(),
            method=HTTP_GET_METHOD,
            path=PULL_PATH,
            response_code=HTTPStatus.GONE,
            response_headers={
                HTTP_CONTENT_TYPE_HEADER: ContentType.NDJSON_UTF8,
                ETAG_HEADER: f'"{validated.validation_record.record_id}"',
            },
            response_body="".join(lines),
        ))
        occurred_at = commit.record_id.time * 1000
        request = RunOutcomeRequest.from_http_request(
            received_at_unix_usec=occurred_at + 6, method="POST", scheme=SYNTHETIC_SCHEME,
            host=SYNTHETIC_HOST,
            port=None, path=RunLifecycle.COMPLETED.to_run_outcome_path(), query="",
            request_headers={
                NAME_KEY_HEADER: api.name_key_header(STARTUP_NAMEKEY),
                "Session-ID": str(session_id),
                "ETag": f'"{validated.validation_record.record_id}"',
            },
            request_body=None,
        )
        outcome = RunOutcomeResponseRecord.from_run_outcome_request(
            request,
            response_code=HTTPStatus.OK,
            response_headers={SOURCE_KEY_HEADER: draft.request_headers[SOURCE_KEY_HEADER]},
            response_body=RunOutcomeResponseBody(
                pull_record_id=gone_pull.record_id,
                push_record_id=push.record_id,
                commit_record_id=commit.record_id,
                validation_record_id=validated.validation_record.record_id,
                run_outcome_record_id=request.http_request_log_record.record_id,
                codex_session_record=draft.commit_request_body.codex_session_record,
            ),
            ready_to_respond_at_unix_usec=occurred_at + 7,
        )
        store._append_authoritative_record(outcome.http_request_log_record)
        fresh = store._query_snapshot()
        assert len(fresh.attempts) == len(fresh.run_outcome_records) == 1

    # A fresh Dashboard/IPC startup verifies the new fixture log through normal config mechanics.
    config["files_config"][REPLAY_LOG_KEY]["sha256"] = hashlib.sha256(
        Path(config["files_config"][REPLAY_LOG_KEY]["path"]).read_bytes(),
    ).hexdigest()
    config_path.write_text(json.dumps(config))
    run_id = uuid7()
    events = [
        RunEvent(run_id=run_id, namekey=STARTUP_NAMEKEY,
                 occurred_at_unix_usec=occurred_at - 5 + index,
                 lifecycle=lifecycle, session_id=session_id)
        for index, lifecycle in enumerate((RunLifecycle.QUEUED, RunLifecycle.STARTED,
                                          RunLifecycle.SESSION_DISCOVERED,
                                          RunLifecycle.CODEX_EXITED, RunLifecycle.COMPLETED))
    ]
    storage = AiAugmentDashboardStorage()
    storage.replace_query_response(stale)
    storage.save_run_events(events)
    storage.save_queue([])
    # The real FilePersistentDict writes synchronously outside a running event loop.
    assert app.storage.general
    (config_path.parent / "lima.json").write_text(json.dumps({
        "param": {"FASTAPI_DETOUR_APPENDWATCH_REPORT": "/fixture/appendwatch.txt"},
        "mounts": [{"location": str(config_path.parent), "mountPoint": "/fixture"}],
    }))
    setattr(ai_augment_context, "LIMA_CONFIG_PATH", config_path.parent / "lima.json")
    os.environ["OPENALEX_API_KEY"] = "isolated-unused-query-key"
    services = ui.create_services(config_path=config_path)
    services.controller._load_dashboard_storage()
    # Exercise real filtering before asking a browser to render it; no services are started.
    selection = ui._UiSelection(researcher_varname=ui.RESEARCHER_VARS[0].varname)
    started = time.monotonic()
    with threaded_loop_runner() as runner:
        unfiltered = runner.run(services.controller.snapshot(selection=selection))
        assert len(unfiltered.researcher_var_views) == len(stale.ai_augment_singular_outerdicts)
        selection.search_text = STARTUP_NAMEKEY.to_json_key()
        filtered = runner.run(services.controller.snapshot(selection=selection))
    assert len(filtered.researcher_var_views) == 1
    row = filtered.researcher_var_views[0]
    assert row.researcher.namekey == STARTUP_NAMEKEY
    assert row.latest_run_commit_var_view.lifecycle is RunLifecycle.COMPLETED
    assert row.latest_run_commit_var_view.action is ui._RunAction.RERUN
    assert row.latest_run_commit_var_view.commit_record_id is None
    print(f"Completed-query fixture: real 307-to-1 filter passed in "
          f"{time.monotonic() - started:.3f}s", flush=True)
    (config_path.parent / "completed-query.json").write_text(json.dumps({
        "commit_id": str(commit.record_id), "namekey": STARTUP_NAMEKEY.to_json_key(),
    }))
    print("COMPLETED_QUERY_FIXTURE_READY", flush=True)


def completed_query_dashboard_process() -> None:
    """Only point real Dashboard configuration at the fixture's local Lima metadata."""
    import sys
    from pathlib import Path

    from src.detours.detour_ai_augment.src.control_centre.dashboard import ui
    from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
        ai_augment_context,
    )

    setattr(ai_augment_context, "LIMA_CONFIG_PATH", Path(sys.argv[1]).parent / "lima.json")
    raise SystemExit(ui.main(["--config", sys.argv[1]]))


def audit_probe_process() -> None:
    import sys

    from src.detours.detour_ai_augment.src.control_centre.appendwatch import audit_read

    configured = audit_read.AuditReadConfiguration.model_validate_json(sys.argv[1])
    audit_read.execute(
        configured,
        audit_read.PROBE_COMMAND,
        output=sys.stdout.buffer,
    )


def deployed_guest_imports_process() -> None:
    import runpy
    from pathlib import Path

    from src.helpers.architecture import FrozenStrictModel
    audit = runpy.run_path("libexec/aivm-audit-read", run_name="deployed_audit")
    assert issubclass(audit["AuditReadConfiguration"], FrozenStrictModel)
    model = audit["AuditReadConfiguration"](
        runtime_user="ai", audit_user="audit", sessions_root=Path("/sessions"),
        appendwatch_report=Path("/report"),
    )
    assert model.runtime_user == "ai"
    watch = runpy.run_path("appendwatch.py", run_name="deployed_watch")
    record = watch["Record"](dev=1, ino=2, size=0, mtime_ns=0, ctime_ns=0, digest=b"a")
    record.size = 2
    copied = record.model_copy(update={"exists": False})
    assert record.exists and not copied.exists and copied.size == 2
    print("DEPLOYED_MODELS_OK")


def backend_lock_holder_process() -> None:
    import fcntl
    import os
    import sys

    descriptor = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    print("locked", flush=True)
    sys.stdin.read(1)


def sleeping_process() -> None:
    import os
    import time

    print(os.getpid(), flush=True)
    time.sleep(60)


def backend_stop_child_process() -> None:
    import signal
    import sys

    from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
        BACKEND_STORE_CLOSED_CLEANLY,
    )

    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
    print("READY", flush=True)
    signal.sigwait({signal.SIGTERM})
    print("STOPPING", flush=True)
    if sys.argv[1] == "child-exit":
        sys.stdin.readline()
    print(BACKEND_STORE_CLOSED_CLEANLY, flush=True)


def stdin_waiting_process() -> None:
    import sys

    print("ready", flush=True)
    sys.stdin.read()


def watcher_import_process() -> None:
    import os
    import subprocess
    import sys

    print(f"pytest interpreter: {sys.executable}", flush=True)
    for name in (
        "PIXI_PROJECT_ROOT", "CONDA_PREFIX", "APPENDWATCH_PYTHON", "APPENDWATCH_SCRIPT",
    ):
        print(f"{name}={os.environ.get(name)!r}", flush=True)

    subprocess.run([
        os.environ["APPENDWATCH_PYTHON"], os.environ["APPENDWATCH_SCRIPT"], "--help",
    ], check=True)
    print("TASK_WATCHER_IMPORT_OK")


def socketless_dashboard_process() -> None:
    import asyncio
    import sys
    from types import SimpleNamespace
    from typing import Any, cast
    from unittest.mock import patch

    from nicegui import app, core, server, ui

    from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as dashboard

    async def start(**kwargs: object) -> None:
        raise ValueError("invalid persisted storage")

    async def stop() -> None:
        print("CONTROLLER_CLEANED", flush=True)

    def create(**kwargs: object) -> Any:
        if sys.argv[1] == "config":
            raise ValueError("invalid configuration hash")
        return SimpleNamespace(controller=SimpleNamespace(start=start, shutdown=stop))

    def run(**kwargs: object) -> None:
        # Substitute only the socket-serving loop. Framework callback dispatch, shutdown
        # signalling, shutdown hooks and the application's exit code are real.
        async def lifecycle() -> None:
            core.loop = asyncio.get_running_loop()
            server.Server.instance = cast(server.Server, SimpleNamespace(
                should_exit=False, config=SimpleNamespace(should_reload=False),
            ))
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


@pytest.fixture
def socketless_dashboard_lifecycle(
    python_process: PythonProcess,
    nicegui_storage_path: Path,
) -> SocketlessDashboardLifecycle:
    def run(*, publish: bool, failure: str) -> subprocess.CompletedProcess[str]:
        args = [failure, *(["publish", "completed"] if publish else []),
                "--config", "unused.json"]
        return python_process.run(
            socketless_dashboard_process, *args, timeout=15,
            env=nicegui_test_environment(nicegui_storage_path),
        )
    return run


@pytest.fixture(scope="session")
def repository_root(pytestconfig: pytest.Config) -> Path:
    return pytestconfig.rootpath


@pytest.fixture(scope="session")
def detour_root(repository_root: Path) -> Path:
    return repository_root / "src" / "detours" / "detour_ai_augment"


@pytest.fixture
def isolated_lima_configuration(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if request.node.get_closest_marker(OPERATOR_MARKER) is not None:
        return
    from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
        ai_augment_context,
    )

    host_mount = tmp_path / TEST_LIMA_MOUNT_DIRECTORY
    report_path = host_mount / TEST_APPENDWATCH_RELATIVE_PATH
    report_path.parent.mkdir(parents=True)
    report_path.write_text(TEST_APPENDWATCH_CONTENT, encoding=TEXT_ENCODING)
    guest_report = f"{TEST_GUEST_MOUNT_POINT}/{TEST_APPENDWATCH_RELATIVE_PATH}"
    lima_config_path = tmp_path / TEST_LIMA_CONFIG_FILENAME
    lima_config_path.write_text(
        json.dumps({
            "param": {
                ai_augment_context.LIMA_APPENDWATCH_REPORT_PARAM: guest_report,
            },
            "mounts": [{
                "location": str(host_mount),
                "mountPoint": TEST_GUEST_MOUNT_POINT,
            }],
        }),
        encoding=TEXT_ENCODING,
    )
    monkeypatch.setattr(ai_augment_context, "LIMA_CONFIG_PATH", lima_config_path)


@pytest.fixture(autouse=True)
def operator_aivm(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    repository_root: Path,
) -> None:
    if request.node.get_closest_marker(OPERATOR_MARKER) is None:
        return
    # ======================================
    # OpenAlex key must come explicitly
    # from Human Operator at deploy-time and
    # from within Agent Runtime at run time.
    # Therefore, the below is commented out.
    #
    # Signed-off: Human Operator
    # ======================================
    # openalex_api_key = os.environ.get(OPENALEX_API_KEY_ENV_NAME, "").strip()
    #
    # if not openalex_api_key:
    #     openalex_api_key = str(
    #         dotenv_values(DOTENV_PATH).get(OPENALEX_API_KEY_ENV_NAME) or ""
    #     ).strip()
    # if not openalex_api_key:
    #     raise pytest.UsageError(OPERATOR_KEY_MISSING)
    # monkeypatch.setenv(OPENALEX_API_KEY_ENV_NAME, openalex_api_key)
    deployment_environment = os.environ.copy()
    deployment_environment[REPOSITORY_ROOT_ENV_NAME] = str(repository_root)
    if request.config.stash[OPERATOR_REDEPLOY_STASH_KEY]:
        _operator_log("validating host deployment requirements")
        deploy_key = os.environ.get(OPENALEX_API_KEY_ENV_NAME, "").strip()
        if not deploy_key:
            raise pytest.UsageError(OPERATOR_DEPLOY_KEY_MISSING)
        deployment_environment[OPENALEX_API_KEY_ENV_NAME] = deploy_key
        _operator_log("redeploying AIVM")
        try:
            subprocess.run(
                ("bash", str(repository_root / DEPLOY_SCRIPT_RELATIVE_PATH), "--yes"),
                cwd=repository_root,
                env=deployment_environment,
                check=True,
                timeout=OPERATOR_DEPLOY_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise pytest.UsageError(str(exc)) from exc
        _operator_log("AIVM redeploy completed")
    _operator_log(
        f"probing AIVM reachability (timeout {OPERATOR_PROBE_TIMEOUT_SECONDS}s)"
    )
    try:
        probe = subprocess.run(
            AIVM_PROBE_COMMAND,
            cwd=repository_root,
            env=deployment_environment,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=OPERATOR_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise pytest.UsageError(OPERATOR_AIVM_UNAVAILABLE) from exc
    if probe.returncode != 0:
        _operator_log("AIVM is not reachable")
        if request.config.getoption(OPERATOR_YES_OPTION):
            start_aivm = True
        else:
            try:
                reply = input(OPERATOR_START_PROMPT).strip().casefold()
            except EOFError as exc:
                raise pytest.UsageError(OPERATOR_AIVM_START_REFUSED) from exc
            start_aivm = reply in {"y", "yes"}
        if not start_aivm:
            raise pytest.UsageError(OPERATOR_AIVM_START_REFUSED)
        _operator_log("starting AIVM")
        try:
            subprocess.run(
                AIVM_START_COMMAND,
                cwd=repository_root,
                env=deployment_environment,
                check=True,
                timeout=OPERATOR_START_TIMEOUT_SECONDS,
            )
            subprocess.run(
                AIVM_PROBE_COMMAND,
                cwd=repository_root,
                env=deployment_environment,
                check=True,
                timeout=OPERATOR_PROBE_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise pytest.UsageError(OPERATOR_AIVM_START_FAILED) from exc
        _operator_log("AIVM started and is reachable")
    else:
        _operator_log("AIVM is reachable")
    _operator_log("checking the guest OpenAlex credential")
    try:
        guest_key_process = subprocess.run(
            AIVM_OPENALEX_KEY_COMMAND,
            cwd=repository_root,
            env=deployment_environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=OPERATOR_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise pytest.UsageError(OPERATOR_GUEST_KEY_MISSING) from exc
    guest_key = guest_key_process.stdout.strip()
    if not guest_key:
        raise pytest.UsageError(OPERATOR_GUEST_KEY_MISSING)
    _operator_log("guest OpenAlex credential is available")
    _operator_log("checking appendwatch service health")
    try:
        subprocess.run(
            AIVM_APPENDWATCH_PROBE_COMMAND,
            cwd=repository_root,
            env=deployment_environment,
            check=True,
            timeout=OPERATOR_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise pytest.UsageError(OPERATOR_APPENDWATCH_UNAVAILABLE) from exc
    if request.node.get_closest_marker(REQUIRES_CODEX_AUTH_MARKER) is not None:
        _ensure_codex_is_authenticated(
            deployment_environment,
            repository_root=repository_root,
        )
    _operator_log("operator AIVM preflight completed")


@contextmanager
def threaded_loop_runner() -> Iterator[asyncio.Runner]:
    # Drive cross-thread callbacks even on hosts without self-pipe wakeups, including
    # Runner's executor cleanup. This does not substitute the gate/bridge/thread offload.
    with asyncio.Runner() as runner:
        loop = runner.get_loop()

        def tick() -> None:
            loop.call_later(0.01, tick)

        loop.call_soon(tick)
        yield runner


@pytest.fixture
def threaded_loop() -> Iterator[asyncio.Runner]:
    with threaded_loop_runner() as runner:
        yield runner
