from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEPLOY_SCRIPT_PATH = (
    REPOSITORY_ROOT
    / "src"
    / "detours"
    / "detour_ai_augment"
    / "src"
    / "agent_runtime"
    / "deploy.sh"
)
OPERATOR_MARKER = "operator"
REQUIRES_CODEX_AUTH_MARKER = "requires_codex_auth"
EXCLUDED_FROM_SUITES_MARKER = "excluded_from_suites"
NEEDS_SUDO_MARKER = "needs_sudo"
OPERATOR_REDEPLOY_OPTION = "always_redeploy"
OPERATOR_YES_OPTION = "operator_yes"
RUN_EXCLUDED_FROM_SUITES_OPTION = "run_excluded_from_suites"
OPENALEX_API_KEY_ENV_NAME = "OPENALEX_API_KEY"
REPOSITORY_ROOT_ENV_NAME = "REPO_DIR"
AIVM_INSTANCE = "aivm"
AIVM_USER = "ai"
AIVM_CODEX_BIN_PATH = "/home/ai/.local/bin/codex"
AIVM_OPENALEX_ENV_PATH = "/home/ai/workdir/.openalex.env"
DEPLOY_COMMAND = ("bash", str(DEPLOY_SCRIPT_PATH), "--yes")
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
    "verifies complete pre/post hashes of both production data trees. The Lima "
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


def _operator_log(message: str) -> None:
    print(f"[operator-preflight] {message}", flush=True)


def _operator_requested(config: pytest.Config) -> bool:
    """
    Note: only recognizes exactly `-m operator`, so
    not intended to be combined with any markers.

    signed off: human
    """
    return (config.option.markexpr or "").strip() == OPERATOR_MARKER


def _codex_is_authenticated(deployment_environment: dict[str, str]) -> bool:
    try:
        result = subprocess.run(
            AIVM_CODEX_AUTH_STATUS_COMMAND,
            cwd=REPOSITORY_ROOT,
            env=deployment_environment,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=OPERATOR_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise pytest.UsageError(OPERATOR_CODEX_AUTH_REQUIRED) from exc
    return result.returncode == 0


def _ensure_codex_is_authenticated(deployment_environment: dict[str, str]) -> None:
    _operator_log("checking guest Codex authentication")
    if _codex_is_authenticated(deployment_environment):
        _operator_log("guest Codex authentication is available")
        return
    _operator_log("guest Codex authentication is unavailable")
    try:
        reply = input(OPERATOR_CODEX_AUTH_PROMPT).strip().casefold()
    except EOFError as exc:
        raise pytest.UsageError(OPERATOR_CODEX_AUTH_REQUIRED) from exc
    if reply not in {"y", "yes"}:
        raise pytest.UsageError(OPERATOR_CODEX_AUTH_REQUIRED)
    _operator_log("starting guest Codex device authentication")
    try:
        subprocess.run(
            AIVM_CODEX_DEVICE_AUTH_COMMAND,
            cwd=REPOSITORY_ROOT,
            env=deployment_environment,
            check=True,
            timeout=OPERATOR_CODEX_AUTH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise pytest.UsageError(OPERATOR_CODEX_AUTH_FAILED) from exc
    if not _codex_is_authenticated(deployment_environment):
        raise pytest.UsageError(OPERATOR_CODEX_AUTH_FAILED)
    _operator_log("guest Codex device authentication completed")


def pytest_addoption(parser: pytest.Parser) -> None:
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


@pytest.fixture(autouse=True)
def isolated_lima_configuration(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if request.node.get_closest_marker(OPERATOR_MARKER) is not None:
        return
    from src.detours.detour_ai_augment.src.control_centre.dashboard import (
        ui as control_ui,
    )
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
                control_ui.LIMA_APPENDWATCH_REPORT_PARAM: guest_report,
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
    deployment_environment[REPOSITORY_ROOT_ENV_NAME] = str(REPOSITORY_ROOT)
    if request.config.stash[OPERATOR_REDEPLOY_STASH_KEY]:
        _operator_log("validating host deployment requirements")
        deploy_key = os.environ.get(OPENALEX_API_KEY_ENV_NAME, "").strip()
        if not deploy_key:
            raise pytest.UsageError(OPERATOR_DEPLOY_KEY_MISSING)
        deployment_environment[OPENALEX_API_KEY_ENV_NAME] = deploy_key
        _operator_log("redeploying AIVM")
        try:
            subprocess.run(
                DEPLOY_COMMAND,
                cwd=REPOSITORY_ROOT,
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
            cwd=REPOSITORY_ROOT,
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
                cwd=REPOSITORY_ROOT,
                env=deployment_environment,
                check=True,
                timeout=OPERATOR_START_TIMEOUT_SECONDS,
            )
            subprocess.run(
                AIVM_PROBE_COMMAND,
                cwd=REPOSITORY_ROOT,
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
            cwd=REPOSITORY_ROOT,
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
    monkeypatch.setenv(OPENALEX_API_KEY_ENV_NAME, guest_key)
    _operator_log("guest OpenAlex credential is available")
    _operator_log("checking appendwatch service health")
    try:
        subprocess.run(
            AIVM_APPENDWATCH_PROBE_COMMAND,
            cwd=REPOSITORY_ROOT,
            env=deployment_environment,
            check=True,
            timeout=OPERATOR_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise pytest.UsageError(OPERATOR_APPENDWATCH_UNAVAILABLE) from exc
    if request.node.get_closest_marker(REQUIRES_CODEX_AUTH_MARKER) is not None:
        _ensure_codex_is_authenticated(deployment_environment)
    _operator_log("operator AIVM preflight completed")
