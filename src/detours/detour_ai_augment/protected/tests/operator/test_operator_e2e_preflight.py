from __future__ import annotations

import inspect
import json
import os
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from src.detours.detour_ai_augment.protected.src.backend import ipc as backend_ipc
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (
    Locale,
)
from src.detours.detour_ai_augment.protected.tests import (
    pytest_plugin as operator_preflight,
)
from src.detours.detour_ai_augment.protected.tests.operator import (
    test_operator_e2e as workflow,
)
from src.detours.detour_ai_augment.src.backend import server as backend_server
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui


@pytest.mark.python_subprocess
def test_nicegui_children_have_private_persistent_storage(
    tmp_path: Path, python_process: operator_preflight.PythonProcess,
    monkeypatch: pytest.MonkeyPatch, nicegui_storage_path: Path,
) -> None:
    original = tmp_path / ".nicegui"
    original.mkdir()
    sentinel = original / "storage-general.json"
    sentinel.write_text('{"operator_sentinel": "untouched"}')
    before = workflow._tree_digest(original)
    monkeypatch.setenv("NICEGUI_STORAGE_PATH", str(original))
    monkeypatch.setenv("NICEGUI_REDIS_URL", "redis://must-not-connect.invalid")
    for path, previous, value in (
        (nicegui_storage_path, {}, "first"),
        (nicegui_storage_path, {"test_value": "first"}, "restart"),
        (tmp_path / "other-test", {}, "separate"),
    ):
        result = python_process.run(
            operator_preflight.nicegui_persistence_process, json.dumps(previous), value,
            cwd=tmp_path, env=operator_preflight.nicegui_test_environment(path), timeout=20,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads((path / "storage-general.json").read_text()) == {"test_value": value}
        assert workflow._tree_digest(original) == before


@pytest.mark.python_subprocess
@pytest.mark.parametrize("collection_failure", (False, True))
def test_nicegui_isolated_before_collection_and_cleaned_after_exit(
    tmp_path: Path, python_process: operator_preflight.PythonProcess,
    collection_failure: bool,
) -> None:
    original = tmp_path / "operator-storage"
    original.mkdir()
    (original / "storage-general.json").write_text('{"operator_sentinel": "untouched"}')
    before = workflow._tree_digest(original)
    environment = dict(os.environ, NICEGUI_STORAGE_PATH=str(original),
                       NICEGUI_REDIS_URL="redis://must-not-connect.invalid",
                       TEST_ORIGINAL_STORAGE=str(original),
                       TEST_STORAGE_RECEIPT=str(tmp_path / "receipt"),
                       TEST_COLLECTION_FAILURE=str(int(collection_failure)))
    result = python_process.run(
        operator_preflight.nicegui_collection_process, str(tmp_path),
        "2" if collection_failure else "0", env=environment, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COLLECTION_STORAGE_CLEANED" in result.stdout
    assert workflow._tree_digest(original) == before


@pytest.mark.parametrize("initially_present", (False, True))
def test_operator_preservation_guard_covers_original_storage(
    tmp_path: Path, initially_present: bool,
) -> None:
    storage = tmp_path / "nicegui"
    if initially_present:
        storage.mkdir()
        (storage / "storage-general.json").write_text("{}")
    config = cast(pytest.Config, SimpleNamespace(stash={
        operator_preflight.ORIGINAL_NICEGUI_STORAGE_PATH: storage,
    }))
    guard = inspect.unwrap(workflow.production_data_unchanged)(
        operator_aivm=None, repository_root=tmp_path / "repo",
        detour_root=tmp_path / "detour", pytestconfig=config,
    )
    next(guard)
    storage.mkdir(exist_ok=True)
    (storage / "storage-general.json").write_text('{"test_data": true}')
    with pytest.raises(AssertionError):
        next(guard)


@pytest.mark.parametrize("launcher", ("operator", "browser", "browser-contract"))
def test_dashboard_launchers_pass_private_storage(
    launcher: str, tmp_path: Path, nicegui_storage_path: Path,
    pytestconfig: pytest.Config, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.detours.detour_ai_augment.tests.control_centre import test_ui_e2e as browser

    class LaunchCaptured(Exception):
        pass

    def capture(*_args: object, **kwargs: object) -> None:
        environment = cast(dict[str, str], kwargs["env"])
        assert environment["NICEGUI_STORAGE_PATH"] == str(nicegui_storage_path.resolve())
        assert "NICEGUI_REDIS_URL" not in environment
        raise LaunchCaptured

    monkeypatch.setenv("NICEGUI_STORAGE_PATH", str(tmp_path / "must-not-use"))
    monkeypatch.setenv("NICEGUI_REDIS_URL", "redis://must-not-connect.invalid")
    monkeypatch.setattr(subprocess, "Popen", capture)
    monkeypatch.setattr(workflow, "_assert_ports_available", lambda: None)
    monkeypatch.setattr(browser, "available_e2e_port", lambda: 12345)
    runtime = cast(workflow.OperatorRuntime, SimpleNamespace(
        config_path=tmp_path / "config.json", repository_root=pytestconfig.rootpath,
        dashboard_socket_path=tmp_path / "ipc.sock",
    ))
    with pytest.raises(LaunchCaptured):
        if launcher == "operator":
            with workflow.running_dashboard(runtime):
                pytest.fail("must stop at launch")
        elif launcher == "browser":
            with browser.control_centre_browser(pytestconfig, nicegui_storage_path):
                pytest.fail("must stop at launch")
        else:
            browser.test_control_centre_browser_contract(pytestconfig, nicegui_storage_path)


@pytest.mark.parametrize("outcome", ("success", "savedness-pending", "failed", "cancelled"))
def test_operator_completion_wait_reports_actual_conditions(
    monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    cells = [Mock() for _ in range(5)]
    values = ["", "completed", "commit-id", "pending", "OK"]
    if outcome in {"failed", "cancelled"}:
        values[1] = outcome
    for index, cell in enumerate(cells):
        cell.inner_text.side_effect = lambda index=index: values[index]
    history_rows = Mock()
    history_rows.count.return_value = 1
    history_rows.nth.return_value.locator.return_value.nth.side_effect = lambda index: cells[index]
    history = Mock()
    history.locator.return_value = history_rows
    execute = Mock()
    execute.inner_text.return_value = "RERUN"
    execute.text_content.return_value = "Rerun"
    card = Mock()
    card.is_enabled.return_value = True
    page = Mock()
    page.get_by_test_id.side_effect = {
        control_ui.RESEARCHER_GRID_TEST_ID: Mock(),
        control_ui.ATTEMPT_HISTORY_TABLE_TEST_ID: history,
        control_ui.EXECUTE_ACTION_TEST_ID: execute,
        control_ui.VIEW_CARD_TEST_ID: card,
    }.__getitem__
    clock = iter(range(100))
    monkeypatch.setattr(workflow, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr(workflow, "FULL_WORKFLOW_TIMEOUT_SECONDS", 12)
    monkeypatch.setattr(workflow, "OPERATOR_HEARTBEAT_SECONDS", 0)
    monkeypatch.setattr(workflow, "expect", Mock())
    query = Mock()
    monkeypatch.setattr(workflow, "query_snapshot_in_browser", query)
    logs: list[str] = []
    monkeypatch.setattr(workflow, "_operator_log", logs.append)
    dashboard = Mock()
    dashboard.process.poll.return_value = None
    dashboard.output = []
    if outcome == "success":
        page.wait_for_timeout.side_effect = lambda _ms: values.__setitem__(
            3, Locale.RUN_OUTCOME_SNAPSHOT_SAVED,
        )
        values[4] = Locale.SESSION_STATUS_OK
        _, commit = workflow.wait_for_completed_grid_row(
            page, dashboard, Mock(), queued_at_monotonic=0,
        )
        assert commit == "commit-id"
    elif outcome == "savedness-pending":
        with pytest.raises(TimeoutError, match="savedness='pending'"):
            workflow.wait_for_completed_grid_row(page, dashboard, Mock(), queued_at_monotonic=0)
    else:
        with pytest.raises(RuntimeError, match="failed run activity"):
            workflow.wait_for_completed_grid_row(page, dashboard, Mock(), queued_at_monotonic=0)
    assert query.call_count == int(outcome not in {"failed", "cancelled"})
    if outcome in {"success", "savedness-pending"}:
        diagnostic = "\n".join(logs)
        assert "queried_after_completion=True" in diagnostic
        assert "savedness='pending'" in diagnostic
        assert "action='Rerun'" in diagnostic
        assert "waiting for Codex to exit" not in diagnostic


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
