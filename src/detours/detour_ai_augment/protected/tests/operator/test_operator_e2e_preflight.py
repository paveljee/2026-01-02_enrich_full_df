from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
import tempfile
import threading
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock
from uuid import uuid7

import pytest

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
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_backend_store import (
    initialize_backend_store,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_event import (
    BackendLifecycle,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.validation_event import (
    BackendValidationRecord,
    PostCommitValidation,
    ValidationRequestBody,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    run_outcome,
)
from src.detours.detour_ai_augment.tests.backend import test_api as api_fixtures
from src.detours.detour_ai_augment.tests.control_centre import test_ui as ui_tests
from src.detours.detour_ai_augment.tests.control_centre import test_ui_e2e as browser_tests
from src.helpers.data_models import HttpRequestLogRecord

startup_files = browser_tests.startup_files
completed_query_files = browser_tests.completed_query_files


@pytest.mark.python_subprocess
def test_operator_artifact_validator_accepts_completed_store_history(
    completed_query_files: ui_tests.StartupFiles,
    pytestconfig: pytest.Config,
) -> None:
    files = completed_query_files
    with initialize_backend_store(
        backend_server.configure_runtime(files.config, require_namekey=False),
        ipc_only=True,
    ) as query_store:
        fixture_store = query_store._engine
    runtime = workflow.OperatorRuntime(
        repository_root=pytestconfig.rootpath,
        config_path=files.config,
        backend_store=fixture_store,
        replay_log_path=files.replay,
        rollout_cas_dir=files.config.parent / "cas",
        dashboard_socket_path=files.config.parent / "dashboard.sock",
    )
    workflow.validate_workflow_artifacts(
        runtime,
        namekey=ui_tests.STARTUP_NAMEKEY,
        expected_run_outcome_path=run_outcome.RunLifecycle.COMPLETED.to_run_outcome_path(),
    )


def _workflow_http_records(
    *,
    provider_targets: tuple[tuple[str, str], ...],
    provider_status: HTTPStatus = HTTPStatus.OK,
    with_initial: bool = True,
) -> tuple[HttpRequestLogRecord, ...]:
    session_id = uuid7()
    records: list[HttpRequestLogRecord] = []
    initial: BackendValidationRecord | None = None
    for index in range(2 if with_initial else 1):
        pull, commit = api_fixtures.retry_attempt_records(
            original_pull_record_id=uuid7(), session_id=session_id,
            attempt_id=f"operator-history-{index}",
        )
        providers = tuple(
            HttpRequestLogRecord(
                schema_version="1.1", record_id=uuid7(), method="GET", scheme="https",
                host=host, port=None, path=path, query="", request_headers={},
                request_body=None, response_code=provider_status, response_headers={},
                response_body='{"provider": "fixture"}', received_at_unix_usec=1,
                ready_to_respond_at_unix_usec=2, duration_usec=1,
            )
            for host, path in provider_targets
            if not with_initial or index == 1
        )
        validation = ValidationRequestBody(
            commit_record=commit,
            post_commit_validation=PostCommitValidation(
                stage=BackendLifecycle.PYDANTIC_VALIDATION,
                result=BackendLifecycle.REJECTED,
                detail="synthetic model rejection",
                submission_type=None,
                submission=None,
            ),
            initial_validation_record=initial,
            openalex_ror_records=providers,
        ).http_record()
        records.extend((pull, commit.commit_request_body.push_record, commit,
                        *providers, validation))
        if initial is None:
            initial = validation
    return tuple(records)


@pytest.mark.parametrize("provider_targets", (
    (),
    (("api.openalex.org", "/institutions/I97018004"),),
    (("api.ror.org", "/v2/organizations/00f54p054"),),
    (("api.openalex.org", "/institutions/I97018004"),
     ("api.ror.org", "/v2/organizations/00f54p054")),
))
@pytest.mark.parametrize("provider_status", (HTTPStatus.OK, HTTPStatus.NOT_FOUND))
@pytest.mark.parametrize("with_initial", (False, True))
def test_operator_http_history_accepts_only_linked_current_records(
    provider_targets: tuple[tuple[str, str], ...], provider_status: HTTPStatus,
    with_initial: bool,
) -> None:
    records = _workflow_http_records(
        provider_targets=provider_targets, provider_status=provider_status,
        with_initial=with_initial,
    )
    validations = workflow._validate_workflow_http_records(records)
    assert len(validations) == (2 if with_initial else 1)
    assert validations[records[-1].record_id].model_dump() == records[-1].model_dump()


@pytest.mark.parametrize("mutation, target", (
    ("unknown-route", ""),
    ("unreferenced-provider", ""),
    ("wrong-endpoint", ""),
    ("duplicate", ""),
    *((mutation, target)
      for mutation in ("missing", "changed", "after-validation")
      for target in ("provider", "commit", "pull", "push", "initial")),
))
def test_operator_http_history_rejects_corrupt_or_unreferenced_records(
    mutation: str, target: str,
) -> None:
    records = list(_workflow_http_records(
        provider_targets=(("api.openalex.org", "/institutions/I97018004"),),
    ))
    validation = BackendValidationRecord.from_http_request_log_record(records[-1])
    body = validation.validation_request_body
    assert body.initial_validation_record is not None
    provider = body.openalex_ror_records[0]
    if mutation == "unknown-route":
        records.append(api_fixtures.persisted_http_record(
            record_id=uuid7(), method="GET", path="/unexpected",
            response_code=HTTPStatus.OK,
        ))
    elif mutation == "unreferenced-provider":
        records.append(provider.model_copy(update={"record_id": uuid7()}))
    elif mutation == "wrong-endpoint":
        changed = provider.model_copy(update={"host": "unapproved.invalid"})
        records[records.index(provider)] = changed
        changed_body = body.model_copy(update={"openalex_ror_records": (changed,)})
        records[-1] = validation.model_copy(update={
            "request_body": changed_body.model_dump_json(),
            "validation_request_body": changed_body,
        })
    elif mutation == "duplicate":
        records.append(records[0])
    else:
        linked = {
            "provider": provider,
            "commit": body.commit_record,
            "pull": body.commit_record.commit_request_body.pull_record,
            "push": body.commit_record.commit_request_body.push_record,
            "initial": body.initial_validation_record,
        }[target]
        position = next(
            index for index, record in enumerate(records) if record.record_id == linked.record_id
        )
        if mutation == "missing":
            records.pop(position)
        elif mutation == "after-validation":
            records.append(records.pop(position))
        else:
            assert mutation == "changed"
            if target == "initial":
                initial = body.initial_validation_record
                initial_body = initial.validation_request_body
                changed_body = initial_body.model_copy(update={
                    "post_commit_validation": initial_body.post_commit_validation.model_copy(
                        update={"detail": "changed persisted validation"},
                    ),
                })
                records[position] = initial.model_copy(update={
                    "request_body": changed_body.model_dump_json(),
                    "validation_request_body": changed_body,
                })
            else:
                records[position] = linked.model_copy(update={"query": "changed=1"})
    with pytest.raises(AssertionError):
        workflow._validate_workflow_http_records(records)


def test_operator_run_directories_are_unique_retained_and_contained(
    startup_files: ui_tests.StartupFiles, pytestconfig: pytest.Config,
) -> None:
    files = startup_files
    source_before = hashlib.sha256(files.source.read_bytes()).hexdigest()
    assert files.source.stat().st_mode & 0o222 == 0
    artifacts_root = pytestconfig.rootpath / "tmp"
    artifacts_root.mkdir(exist_ok=True)
    # Short test-repository prefix preserves the real Darwin socket-path limit.
    with tempfile.TemporaryDirectory(prefix="p.", dir=artifacts_root) as directory:
        repository = Path(directory)
        (repository / "config_ai_augment.json").write_bytes(files.config.read_bytes())
        run_dirs: list[Path] = []
        for _ in range(2):
            fixture = inspect.unwrap(workflow.operator_runtime)(repository_root=repository)
            runtime = next(fixture)
            run_dir = runtime.config_path.parent
            run_dirs.append(run_dir)
            assert run_dir.parent == repository / "tmp"
            assert run_dir.name.startswith("operator-test.")
            assert (
                len(os.fsencode(runtime.dashboard_socket_path))
                < workflow.DARWIN_AF_UNIX_PATH_CAPACITY_BYTES
            )
            config = json.loads(runtime.config_path.read_text())
            for path in (
                runtime.config_path, runtime.replay_log_path, runtime.rollout_cas_dir,
                runtime.dashboard_socket_path, runtime.backend_store._detour_db_path,
                Path(config["db_file"]), Path(config["state_file"]),
                Path(config["output_dir"]), run_dir / "nicegui",
            ):
                assert path.is_relative_to(run_dir), path
            source_link = Path(config["db_file"])
            assert source_link.is_symlink()
            assert source_link.resolve() == files.source.resolve()
            retained = (runtime.config_path, runtime.replay_log_path,
                        runtime.backend_store._detour_db_path)
            before_close = {path: path.read_bytes() for path in retained}
            with pytest.raises(StopIteration):
                next(fixture)
            assert run_dir.is_dir()
            assert {path: path.read_bytes() for path in retained} == before_close
        assert run_dirs[0] != run_dirs[1]
        assert all(path.is_dir() for path in run_dirs)
    assert hashlib.sha256(files.source.read_bytes()).hexdigest() == source_before
    assert files.source.stat().st_mode & 0o222 == 0


def test_operator_run_directory_rejects_overlong_socket_path(tmp_path: Path) -> None:
    repository = tmp_path / ("long-checkout-" * 9)
    repository.mkdir()
    fixture = inspect.unwrap(workflow.operator_runtime)(repository_root=repository)
    with pytest.raises(RuntimeError, match="exceeds Darwin AF_UNIX capacity"):
        next(fixture)
    run_dirs = tuple((repository / "tmp").iterdir())
    assert len(run_dirs) == 1 and run_dirs[0].is_dir()
    assert not (run_dirs[0] / "config.operator.json").exists()


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
        backend_server,
        "start_dashboard_query_server",
        Mock(side_effect=AssertionError),
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


@pytest.mark.parametrize("full_stop", ("clean", "missing", "no-ack", "forced-kill"))
def test_operator_requires_clean_stop_for_each_owned_backend(full_stop: str) -> None:
    prefix = Locale.CONTROL_CENTRE_LOG_PREFIX
    output = [f"{prefix} Owned Backend ready: pid={pid}\n" for pid in (101, 102)]
    output.append(
        f"{prefix} " + Locale.BACKEND_STOPPED_LOG_TEMPLATE.format(
            pid=101, return_code=0, clean_close_ack=True,
            forced_kill=False, shutdown_succeeded=True,
        ) + "\n",
    )
    if full_stop != "missing":
        output.append(
            f"{prefix} " + Locale.BACKEND_STOPPED_LOG_TEMPLATE.format(
                pid=102, return_code=0, clean_close_ack=full_stop != "no-ack",
                forced_kill=full_stop == "forced-kill", shutdown_succeeded=full_stop == "clean",
            ) + "\n",
        )
    if full_stop == "clean":
        workflow.assert_owned_backends_stopped(output, [])
    else:
        with pytest.raises(AssertionError, match=r"PIDs.*\[102\]"):
            workflow.assert_owned_backends_stopped(output, [])


def test_operator_failure_includes_captured_backend_reason() -> None:
    summary = f"{workflow.FAILED_RUN_LOG_PREFIX} detail=unspecified\n"
    reason = (
        f"{Locale.BACKEND_LOG_PREFIX} WARNING:backend.api:"
        "validation rejected at rollout_index: broken supported citation chain\n"
    )
    informational = f"{Locale.BACKEND_LOG_PREFIX} INFO:backend.api:Pull: HTTP 500\n"
    process = Mock(spec=subprocess.Popen)
    process.poll.return_value = None
    dashboard = workflow.DashboardProcess(
        process=process, output=[reason, informational, summary],
        output_thread=threading.Thread(),
    )
    with pytest.raises(RuntimeError) as caught:
        workflow.raise_for_dashboard_failure(dashboard)
    assert str(caught.value) == "workflow failed:\n" + summary + reason
