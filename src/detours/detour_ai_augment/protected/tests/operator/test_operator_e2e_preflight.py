from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from src.detours.detour_ai_augment.protected.src.backend import ipc as backend_ipc
from src.detours.detour_ai_augment.protected.tests import (
    pytest_plugin as operator_preflight,
)
from src.detours.detour_ai_augment.protected.tests.operator import (
    test_operator_e2e as workflow,
)
from src.detours.detour_ai_augment.src.backend import server as backend_server
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui


def test_existing_codex_authentication_does_not_prompt(
    monkeypatch: pytest.MonkeyPatch,
    repository_root: Path,
) -> None:
    observed: list[tuple[str, ...]] = []

    def run(
        command: tuple[str, ...],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        observed.append(command)
        return subprocess.CompletedProcess(command, 0)

    def unexpected_input() -> str:
        pytest.fail("existing Codex authentication must not prompt")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("builtins.input", unexpected_input)

    operator_preflight._ensure_codex_is_authenticated(
        {},
        repository_root=repository_root,
    )

    assert observed == [operator_preflight.AIVM_CODEX_AUTH_STATUS_COMMAND]


def test_missing_codex_authentication_runs_device_auth_and_rechecks(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    repository_root: Path,
) -> None:
    observed: list[tuple[str, ...]] = []
    status_return_codes = iter((1, 0))

    def run(
        command: tuple[str, ...],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        observed.append(command)
        return_code = (
            next(status_return_codes)
            if command == operator_preflight.AIVM_CODEX_AUTH_STATUS_COMMAND
            else 0
        )
        return subprocess.CompletedProcess(command, return_code)

    def approve_authentication() -> str:
        assert capsys.readouterr().out.endswith(
            "[operator-preflight] "
            f"{operator_preflight.OPERATOR_CODEX_AUTH_PROMPT.rstrip()}\n"
        )
        return "yes"

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("builtins.input", approve_authentication)

    operator_preflight._ensure_codex_is_authenticated(
        {},
        repository_root=repository_root,
    )

    assert observed == [
        operator_preflight.AIVM_CODEX_AUTH_STATUS_COMMAND,
        operator_preflight.AIVM_CODEX_DEVICE_AUTH_COMMAND,
        operator_preflight.AIVM_CODEX_AUTH_STATUS_COMMAND,
    ]


def test_missing_codex_authentication_refusal_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
    repository_root: Path,
) -> None:
    def run(
        command: tuple[str, ...],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("builtins.input", lambda: "no")

    with pytest.raises(
        pytest.UsageError,
        match=operator_preflight.OPERATOR_CODEX_AUTH_REQUIRED,
    ):
        operator_preflight._ensure_codex_is_authenticated(
            {},
            repository_root=repository_root,
        )


@pytest.mark.parametrize(
    "outcome", ("success", "startup_failed", "query_failed", "exited", "stale"),
)
def test_operator_query_button_uses_production_lifecycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: str,
) -> None:
    runtime = cast(workflow.OperatorRuntime, SimpleNamespace(
        config_path=tmp_path / "config.json", dashboard_socket_path=tmp_path / "ipc.sock",
    ))
    # Query itself must not initialize a DB or bypass the Dashboard-owned IPC lifetime.
    monkeypatch.setattr(backend_server, "configure_runtime", Mock(side_effect=AssertionError))
    monkeypatch.setattr(
        backend_ipc, "start_dashboard_query_server", Mock(side_effect=AssertionError),
    )
    process = Mock()
    process.poll.return_value = None
    output = ["Dashboard snapshot replaced: previous query\n"]
    dashboard = cast(workflow.DashboardProcess, SimpleNamespace(process=process, output=output))
    page = Mock()
    page.get_by_text.return_value.is_visible.return_value = True

    def click() -> None:
        if outcome == "exited":
            process.poll.return_value = 1
        elif outcome != "stale":
            output.append({
                "success": "Dashboard snapshot replaced: fresh query\n",
                "startup_failed": "Backend startup failed: missing DB\n",
                "query_failed": "Query IPC failed: invalid response\n",
            }[outcome])

    page.get_by_test_id.return_value.click.side_effect = click
    if outcome == "stale":
        page.wait_for_timeout.side_effect = lambda _timeout: output.append(
            "Dashboard snapshot replaced: fresh query\n",
        )
    else:
        page.wait_for_timeout.side_effect = AssertionError("must not wait after known result")
    if outcome in {"success", "stale"}:
        workflow.query_snapshot_in_browser(page, runtime, dashboard)
        assert page.wait_for_timeout.call_count == int(outcome == "stale")
    else:
        diagnostic = {"startup_failed": "missing DB", "query_failed": "invalid response",
                      "exited": "dashboard exited"}[outcome]
        with pytest.raises(RuntimeError, match=diagnostic):
            workflow.query_snapshot_in_browser(page, runtime, dashboard)
        page.wait_for_timeout.assert_not_called()
    page.get_by_test_id.assert_called_once_with(control_ui.BACKEND_REFRESH_TEST_ID)
    page.get_by_test_id.return_value.click.assert_called_once_with()


@pytest.mark.parametrize("failure", ("none", "install", "browser"))
def test_elevate_retains_failures_and_reports_failed_lines(
    tmp_path: Path, repository_root: Path, failure: str,
) -> None:
    """Execute the real elevate shell/PTY logger with controlled leaf-command outcomes."""
    command = tomllib.loads((repository_root / "pyproject.toml").read_text())["tool"]["pixi"][
        "feature"
    ]["detour-ai-augment"]["tasks"]["elevate"]
    binary = tmp_path / "bin"
    binary.mkdir()
    (tmp_path / "logs/from_operator").mkdir(parents=True)
    stages = tmp_path / "stages"
    executable = binary / "python"
    executable.write_text(
        '#!/bin/sh\n'
        'case "$2" in playwright) stage=install ;; *) stage=browser ;; esac\n'
        'printf "%s\\n" "$stage" >> "$STAGES_FILE"\n'
        'if [ "$FAIL_STAGE" = "$stage" ]; then\n'
        '  echo "FAILED controlled-$stage"; exit 7\n'
        'fi\necho "passed controlled-$stage"\n',
    )
    executable.chmod(0o700)
    result = subprocess.run(
        ["bash", "-c", command], cwd=tmp_path,
        env=dict(os.environ, CONDA_PREFIX=str(tmp_path), PIXI_PROJECT_ROOT=str(tmp_path),
                 PATH=f"{binary}{os.pathsep}{os.environ['PATH']}",
                 STAGES_FILE=str(stages), FAIL_STAGE=failure),
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == int(failure != "none"), result.stdout + result.stderr
    assert stages.read_text().splitlines() == ["install", "browser"]
    if failure == "none":
        assert "grep: no FAILED" in result.stdout
    else:
        assert f"FAILED controlled-{failure}" in result.stdout
        assert "grep: FAILED matches shown above" in result.stdout
    assert "Test output:" in result.stdout
