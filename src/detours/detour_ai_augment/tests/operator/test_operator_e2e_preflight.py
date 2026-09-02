from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.detours.detour_ai_augment.tests import conftest as operator_preflight


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

    def unexpected_input(_prompt: str) -> str:
        pytest.fail("existing Codex authentication must not prompt")

    monkeypatch.setattr(operator_preflight.subprocess, "run", run)
    monkeypatch.setattr("builtins.input", unexpected_input)

    operator_preflight._ensure_codex_is_authenticated(
        {},
        repository_root=repository_root,
    )

    assert observed == [operator_preflight.AIVM_CODEX_AUTH_STATUS_COMMAND]


def test_missing_codex_authentication_runs_device_auth_and_rechecks(
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

    monkeypatch.setattr(operator_preflight.subprocess, "run", run)
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")

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

    monkeypatch.setattr(operator_preflight.subprocess, "run", run)
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")

    with pytest.raises(
        pytest.UsageError,
        match=operator_preflight.OPERATOR_CODEX_AUTH_REQUIRED,
    ):
        operator_preflight._ensure_codex_is_authenticated(
            {},
            repository_root=repository_root,
        )
