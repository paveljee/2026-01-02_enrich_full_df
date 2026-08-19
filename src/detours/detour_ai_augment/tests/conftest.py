from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from dotenv import dotenv_values

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DOTENV_PATH = REPOSITORY_ROOT / ".env"
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
OPERATOR_REDEPLOY_OPTION = "always_redeploy"
OPERATOR_YES_OPTION = "operator_yes"
OPENALEX_API_KEY_ENV_NAME = "OPENALEX_API_KEY"
REPOSITORY_ROOT_ENV_NAME = "REPO_DIR"
AIVM_INSTANCE = "aivm"
DEPLOY_COMMAND = ("bash", str(DEPLOY_SCRIPT_PATH), "--yes")
AIVM_PROBE_COMMAND = ("limactl", "shell", "--workdir=/", AIVM_INSTANCE, "true")
OPERATOR_PROMPT = "Redeploy AIVM before each operator test? [y/N] "
OPERATOR_MARK_DESCRIPTION = "real operator-machine AIVM and full-stack contour"
OPERATOR_SKIP_REASON = "operator test (run with: pytest -m operator)"
OPERATOR_KEY_MISSING = f"{OPENALEX_API_KEY_ENV_NAME} is unavailable in {DOTENV_PATH}"
OPERATOR_SANCTUARY_NOTICE = (
    "Operator sanctuary: repository production access is limited to the read-only "
    "main database and archived attempts. Every test verifies complete pre/post "
    "hashes of both production data trees. The Lima aivm instance is ephemeral "
    "and is outside this preservation guarantee."
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


def _operator_requested(config: pytest.Config) -> bool:
    return (config.option.markexpr or "").strip() == OPERATOR_MARKER


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


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{OPERATOR_MARKER}: {OPERATOR_MARK_DESCRIPTION}",
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
    if _operator_requested(config):
        return
    skip_operator = pytest.mark.skip(reason=OPERATOR_SKIP_REASON)
    for item in items:
        if OPERATOR_MARKER in item.keywords:
            item.add_marker(skip_operator)


@pytest.fixture(autouse=True)
def operator_aivm(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if OPERATOR_MARKER not in request.node.keywords:
        return
    openalex_api_key = os.environ.get(OPENALEX_API_KEY_ENV_NAME, "").strip()
    if not openalex_api_key:
        openalex_api_key = str(
            dotenv_values(DOTENV_PATH).get(OPENALEX_API_KEY_ENV_NAME) or ""
        ).strip()
    if not openalex_api_key:
        raise pytest.UsageError(OPERATOR_KEY_MISSING)
    monkeypatch.setenv(OPENALEX_API_KEY_ENV_NAME, openalex_api_key)
    deployment_environment = os.environ.copy()
    deployment_environment[REPOSITORY_ROOT_ENV_NAME] = str(REPOSITORY_ROOT)
    if request.config.stash[OPERATOR_REDEPLOY_STASH_KEY]:
        subprocess.run(
            DEPLOY_COMMAND,
            cwd=REPOSITORY_ROOT,
            env=deployment_environment,
            check=True,
        )
    subprocess.run(
        AIVM_PROBE_COMMAND,
        cwd=REPOSITORY_ROOT,
        env=deployment_environment,
        check=True,
    )
