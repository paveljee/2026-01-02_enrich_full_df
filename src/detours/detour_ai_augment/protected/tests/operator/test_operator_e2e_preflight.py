from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from src.detours.detour_ai_augment.protected.src.backend import ipc as backend_ipc
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers import (
    vars as control_vars,
)
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


@pytest.mark.parametrize("query_fails", [False, True])
def test_operator_query_button_uses_production_lifecycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, query_fails: bool,
) -> None:
    socket_path = Mock(spec=Path)
    socket_path.exists.return_value = False
    runtime = cast(workflow.OperatorRuntime, SimpleNamespace(
        config_path=tmp_path / "config.json", dashboard_socket_path=socket_path,
    ))
    # The fixture must not prepare a DB or start an IPC server itself.
    monkeypatch.setattr(backend_server, "configure_runtime", Mock(side_effect=AssertionError))
    monkeypatch.setattr(
        backend_ipc, "start_dashboard_query_server", Mock(side_effect=AssertionError),
    )
    page = Mock()
    expectation = Mock()
    if query_fails:
        expectation.to_be_visible.side_effect = RuntimeError("query failed")
    monkeypatch.setattr(workflow, "expect", lambda _locator: expectation)
    if query_fails:
        with pytest.raises(RuntimeError, match="query failed"):
            workflow.query_snapshot_in_browser(page, runtime)
    else:
        workflow.query_snapshot_in_browser(page, runtime)
    page.get_by_test_id.assert_called_once_with(control_ui.BACKEND_REFRESH_TEST_ID)
    page.get_by_test_id.return_value.click.assert_called_once_with()
    expectation.to_be_visible.assert_called_once_with(
        timeout=round(control_vars.BACKEND_REBUILD_TIMEOUT_SECONDS * 1_000),
    )
