from __future__ import annotations

import asyncio
import hashlib
import json
import os
from http import HTTPStatus
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid7

import duckdb
import pytest

from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.src.backend import api, server
from src.detours.detour_ai_augment.src.backend.helpers.data_models import (
    ai_augment_backend_store as store_models,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_event import (
    CodexSessionRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.request_response_records import (
    PullRequestRecord,
    QueryRequestRecord,
    RunOutcomeRequestRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.response_record_promise import (
    BackendStoreAcknowledgment,
    BackendStoreException,
    ResponseRecordPromise,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    run_outcome,
)
from src.detours.detour_ai_augment.tests.backend import test_http_interceptor as fixtures
from src.detours.detour_ai_augment.tests.backend.test_api import (
    persisted_http_record,
    valid_submission_body,
)
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

backend_test_paths = fixtures.backend_test_paths
runtime = fixtures.runtime
backend_store = fixtures.backend_store


def append(
    runtime: AiAugmentBackendContext, backend_store: store_models.AiAugmentBackendStore
) -> bytes:
    store = backend_store
    with store._writable(runtime):
        store._append_authoritative_record(
            persisted_http_record(
                record_id=uuid7(),
                method="GET",
                path="/pull",
                response_code=200,
            )
        )
    return Path(store._replay_log).read_bytes()


def anchor(
    runtime: AiAugmentBackendContext, backend_store: store_models.AiAugmentBackendStore
) -> dict[str, Any]:
    with duckdb.connect(str(backend_store._detour_db_path), read_only=True) as connection:
        row = connection.execute(
            "SELECT comment FROM duckdb_tables() WHERE table_name = 'detour_http_records'"
        ).fetchone()
    assert row is not None
    return dict(json.loads(row[0]))


def repin(
    runtime: AiAugmentBackendContext, backend_store: store_models.AiAugmentBackendStore
) -> None:
    store = backend_store
    store._replay_log = store._replay_log.model_copy(update={
        "hash": hashlib.sha256(Path(store._replay_log).read_bytes()).hexdigest(),
        "verify_hash_on_init": False,
    })


def test_stale_dashboard_hash_retains_boundary_and_verified_hash_promotes_only_writable(
    backend_store: store_models.AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
) -> None:
    store = backend_store
    initial = anchor(runtime, backend_store)
    line = append(runtime, backend_store)
    with store._read_only(runtime):
        assert store._execute("SELECT raw_line_sha256 FROM detour_http_records").fetchone() == (
            hashlib.sha256(line).hexdigest(),
        )
    with store._writable(runtime):
        pass
    assert anchor(runtime, backend_store) == initial
    repin(runtime, backend_store)
    with store._read_only(runtime):
        pass
    assert anchor(runtime, backend_store) == initial
    with store._writable(runtime):
        pass
    assert anchor(runtime, backend_store) == {
        "sha256": hashlib.sha256(line).hexdigest(),
        "ordinal": 1,
        "byte_offset": len(line),
    }
    # An unverified changed config cannot authorize promotion, even in a delegated child.
    store._replay_log = store._replay_log.model_copy(update={"hash": "0" * 64})
    saved = store._detour_db_path.read_bytes()
    with pytest.raises(ValueError, match="Hash verification failed"):
        with store._writable(runtime):
            pytest.fail("unverified hash accepted")
    assert store._detour_db_path.read_bytes() == saved


@pytest.mark.parametrize("damage", (
    "prefix", "suffix", "missing_row", "extra_row", "gap", "truncated", "tail",
    "anchor_boundary", "missing_anchor", "legacy_schema",
))
def test_mismatch_fails_without_any_healing(
    backend_store: store_models.AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    damage: str,
) -> None:
    store = backend_store
    first = append(runtime, backend_store)
    if damage in {"prefix", "truncated"}:
        repin(runtime, backend_store)
        with store._writable(runtime):
            pass
    append(runtime, backend_store)
    log = Path(store._replay_log)
    if damage in {"prefix", "suffix", "truncated", "tail"}:
        content = log.read_bytes()
        if damage in {"prefix", "suffix"}:
            offset = 0 if damage == "prefix" else len(first)
            content = content[:offset] + content[offset:].replace(b"/pull", b"/poll", 1)
        elif damage == "truncated":
            content = first[:-1]
        else:
            content = content[:-1]
        log.chmod(0o600)
        log.write_bytes(content)
        repin(runtime, backend_store)
    else:
        store._detour_db_path.chmod(0o600)
        with duckdb.connect(str(store._detour_db_path)) as connection:
            sql = {
                "missing_row": "DELETE FROM detour_http_records WHERE record_ordinal = 2",
                "extra_row": "INSERT INTO detour_http_records VALUES "
                    "(3, 'extra', 'GET', '/pull', '{}', repeat('0', 64))",
                "gap": "UPDATE detour_http_records SET record_ordinal = 3 WHERE record_ordinal = 2",
                "anchor_boundary": "COMMENT ON TABLE detour_http_records IS '"
                    + json.dumps({"sha256": hashlib.sha256(b"").hexdigest(),
                                  "ordinal": 0, "byte_offset": 1}) + "'",
                "missing_anchor": "COMMENT ON TABLE detour_http_records IS NULL",
                "legacy_schema": "ALTER TABLE detour_http_records DROP raw_line_sha256",
            }[damage]
            connection.execute(sql)
    saved_db = store._detour_db_path.read_bytes()
    saved_log = log.read_bytes()
    for scope in (store._read_only(runtime), store._writable(runtime)):
        with pytest.raises((ValueError, duckdb.Error)):
            with scope:
                pytest.fail("mismatch accepted")
    assert store._detour_db_path.read_bytes() == saved_db
    assert log.read_bytes() == saved_log


def test_append_preflight_uses_real_append_flags_and_never_writes(
    backend_store: store_models.AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = backend_store
    opened: list[int] = []
    original = os.open

    def opening(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if flags & os.O_APPEND:
            assert flags & os.O_WRONLY
            assert not flags & (os.O_CREAT | os.O_TRUNC)
            opened.append(flags)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", opening)
    monkeypatch.setattr(os, "write", lambda *_a: pytest.fail("preflight wrote bytes"))
    with store._writable(runtime):
        pass
    assert len(opened) == 1
    with store._read_only(runtime):
        pass
    assert len(opened) == 1
    assert Path(store._replay_log).read_bytes() == b""
    assert Path(store._replay_log).stat().st_mode & 0o777 == 0o400

    def denied(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if flags & os.O_APPEND:
            raise PermissionError("append denied")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", denied)
    with pytest.raises(PermissionError, match="append denied"):
        with store._writable(runtime):
            pytest.fail("ready despite append failure")
    assert Path(store._replay_log).stat().st_mode & 0o777 == 0o400
    with store._read_only(runtime):
        pass


def test_nonempty_replay_refusal_preserves_db_then_exact_raw_line_is_bootstrapped(
    backend_store: store_models.AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
) -> None:
    store = backend_store
    record = persisted_http_record(record_id=uuid7(), method="GET", path="/pull", response_code=200)
    raw = ("  " + record.model_dump_json() + "  \n").encode()
    log = Path(store._replay_log)
    log.chmod(0o600)
    log.write_bytes(raw)
    repin(runtime, backend_store)
    before = store._detour_db_path.read_bytes()
    with pytest.raises(ValueError, match="replay confirmation"):
        store._rebuild_from_log(runtime, reset_confirmed=True)
    assert store._detour_db_path.read_bytes() == before
    store._rebuild_from_log(runtime, reset_confirmed=True, confirm_replay=lambda: True)
    with store._read_only(runtime):
        assert store._http_record(record.record_id) == record
        assert store._execute("SELECT raw_line_sha256 FROM detour_http_records").fetchone() == (
            hashlib.sha256(raw).hexdigest(),
        )
    assert log.read_bytes() == raw
    assert anchor(runtime, backend_store)["byte_offset"] == len(raw)


@pytest.mark.parametrize("tail", (b"{}\n", b"{}", b"\n"))
def test_new_replay_stops_at_first_invalid_line_and_keeps_empty_anchor(
    backend_store: store_models.AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    tail: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = backend_store
    log = Path(store._replay_log)
    log.chmod(0o600)
    log.write_bytes(tail)
    repin(runtime, backend_store)
    with pytest.raises((api._PushValidationError, IndexError)):
        store._rebuild_from_log(runtime, reset_confirmed=True, confirm_replay=lambda: True)
    assert "Replay failed at line 1" in caplog.text
    assert anchor(runtime, backend_store)["ordinal"] == 0
    assert log.read_bytes() == tail
    with pytest.raises(RuntimeError, match="Store failed"):
        with store._writable(runtime):
            pytest.fail("failed replay became writable")


@pytest.mark.parametrize("modes", ([], ["--new"], ["--resume"], ["--continue"],
                                    ["--new", "--resume", "--continue"]))
def test_ipc_ignores_initialization_arguments(modes: list[str]) -> None:
    args = server.parse_args(["--config", "unused.json", "--ipc-only", *modes])
    assert not args.new and not args.resume


@pytest.mark.parametrize("answer", ("", "n", "y"))
def test_replay_prompt_defaults_no_and_yes_bypasses(
    answer: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("rich.console.Console.input", lambda *_a, **_k: answer)
    assert server.confirm_nonempty_replay(yes=False) is (answer == "y")
    monkeypatch.setattr("rich.console.Console.input", lambda *_a, **_k: pytest.fail("prompted"))
    assert server.confirm_nonempty_replay(yes=True)


@pytest.mark.parametrize("failure", ("append_preflight", "anchor_transaction"))
def test_failed_open_never_promotes_verified_anchor(
    backend_store: store_models.AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    store = backend_store
    append(runtime, backend_store)
    old_anchor = anchor(runtime, backend_store)
    repin(runtime, backend_store)
    if failure == "append_preflight":
        def denied(_self: object) -> None:
            raise OSError("preflight failed")
        monkeypatch.setattr(type(store._replay_log), "_preflight_append", denied)
    else:
        original = store_models.AiAugmentBackendStore._write_anchor

        def interrupted(
            selected: store_models.AiAugmentBackendStore, value: store_models._ReplayAnchor,
        ) -> None:
            original(selected, value)
            raise OSError("anchor transaction failed")
        monkeypatch.setattr(store_models.AiAugmentBackendStore, "_write_anchor", interrupted)
    with pytest.raises(OSError, match="failed"):
        with store._writable(runtime):
            pytest.fail("failed opening became ready")
    assert anchor(runtime, backend_store) == old_anchor


@pytest.mark.parametrize("failure", (None, "fsync", "readback", "projection"))
def test_pull_ack_means_only_request_fsync_and_result_reports_processing_error(
    runtime: AiAugmentBackendContext,
    backend_store: store_models.AiAugmentBackendStore,
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None,
) -> None:
    store = backend_store
    record = PullRequestRecord.model_validate(
        persisted_http_record(
            record_id=uuid7(),
            method="GET",
            path="/pull",
            response_code=200,
        ).model_dump()
    )

    def broken(*_args: object, **_kwargs: object) -> None:
        raise OSError(f"{failure} interrupted")

    async def exercise() -> None:
        promise = store.pull(record)
        expected = (
            BackendStoreAcknowledgment.NAK if failure == "fsync" else BackendStoreAcknowledgment.ACK
        )
        assert promise.acknowledgment is expected
        response, error = await promise.response_record()
        if failure is None:
            assert error is None and response is not None
            assert response.model_dump() == record.model_dump()
            assert store._http_record(record.record_id).model_dump() == response.model_dump()
        else:
            assert response is None and error is not None
            with pytest.raises(BackendStoreException, match="interrupted") as caught:
                error.raise_exception()
            assert isinstance(caught.value.__cause__, OSError)

    if failure is None:
        with store._writable(runtime):
            asyncio.run(exercise())
    else:
        with pytest.raises(RuntimeError, match="Store failed"), store._writable(runtime):
            with monkeypatch.context() as patch:
                if failure == "fsync":
                    patch.setattr(os, "fsync", broken)
                elif failure == "readback":
                    patch.setattr(type(store), "_read_appended_record", broken)
                else:
                    patch.setattr(type(store), "_apply_durable_record", broken)
                asyncio.run(exercise())


@pytest.mark.parametrize("received_at_unix_usec", (1, 0, None))
def test_query_only_capability_returns_nak_snapshot_and_never_changes_log_or_db(
    runtime: AiAugmentBackendContext,
    received_at_unix_usec: int | None,
) -> None:
    with store_models.initialize_backend_store(
        runtime,
        ipc_only=False,
        new=True,
        confirmed=True,
        confirm_replay=lambda: False,
    ) as writable:
        db_path = writable._detour_db_path
    before_db = db_path.read_bytes()
    before_log = Path(runtime.pipeline_config.replay_log).read_bytes()
    request = QueryRequestRecord(
        schema_version="1.1",
        method="GET",
        scheme="http",
        host="invalid",
        port=None,
        path="/query",
        query="",
        request_headers={},
        request_body=None,
        response_code=None,
        response_headers=None,
        response_body=None,
        received_at_unix_usec=received_at_unix_usec,
        ready_to_respond_at_unix_usec=None,
        duration_usec=None,
    )
    with store_models.initialize_backend_store(runtime, ipc_only=True) as store:
        assert not any(hasattr(store, name) for name in ("pull", "push", "run_outcome", "execute"))
        promise = store.query(request)
        assert promise.acknowledgment is BackendStoreAcknowledgment.NAK
        response, error = asyncio.run(promise.response_record())
        if received_at_unix_usec is None:
            assert response is None and error is not None
            assert str(error) == Locale.QUERY_REQUEST_RECEIPT_TIME_MISSING
        else:
            assert error is None and response is not None
            assert response.record_id == request.record_id
            assert response.ready_to_respond_at_unix_usec is not None
            assert response.duration_usec == (
                response.ready_to_respond_at_unix_usec - received_at_unix_usec
            )
            assert response.response_headers == {"Content-Type": "application/json"}
            assert len(response.query_response_body.ai_augment_singular_outerdicts) == 1
    assert db_path.read_bytes() == before_db
    assert Path(runtime.pipeline_config.replay_log).read_bytes() == before_log


@pytest.mark.parametrize("failure", (None, "fsync", "projection"))
@pytest.mark.parametrize("path", ("/completed", "/failed", "/cancelled"))
def test_missing_identity_outcome_is_nak_with_durable_400_and_self_id(
    runtime: AiAugmentBackendContext,
    backend_store: store_models.AiAugmentBackendStore,
    path: str,
    failure: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = backend_store
    assert runtime.configured_namekey is not None
    record = RunOutcomeRequestRecord(
        schema_version="1.1",
        method="POST",
        scheme="http",
        host="invalid",
        port=None,
        path=path,
        query="",
        request_headers={
            run_outcome.NAME_KEY_HEADER: run_outcome.name_key_header_value(
                runtime.configured_namekey,
            ),
        },
        request_body=None,
        response_code=None,
        response_headers=None,
        response_body=None,
        received_at_unix_usec=1,
        ready_to_respond_at_unix_usec=None,
        duration_usec=None,
        pull_record_id=None,
        push_record_id=None,
        rollout_filename=None,
        codex_session_record=CodexSessionRecord(
            session_id=None,
            codex_rollout_record=None,
            appendwatch_report_record=None,
        ),
    )

    def exercise() -> None:
        promise = store.run_outcome(record)
        assert promise.acknowledgment is BackendStoreAcknowledgment.NAK
        response, error = asyncio.run(promise.response_record())
        if failure is not None:
            assert response is None and error is not None
            with pytest.raises(BackendStoreException, match="interrupted") as caught:
                error.raise_exception()
            assert isinstance(caught.value.__cause__, OSError)
            return
        assert error is None and response is not None
        assert response.response_code == HTTPStatus.BAD_REQUEST
        assert response.run_outcome_response_body.run_outcome_record_id == record.record_id
        assert response.run_outcome_response_body.commit_record_id is None
        assert response.run_outcome_response_body.validation_record_id is None
        assert response.to_response().status_code == HTTPStatus.BAD_REQUEST
        assert store._http_record(record.record_id).model_dump() == response.model_dump()

    if failure is None:
        with store._writable(runtime):
            exercise()
    else:
        def broken(*_args: object, **_kwargs: object) -> None:
            raise OSError(f"{failure} interrupted")

        with pytest.raises(RuntimeError, match="Store failed"), store._writable(runtime):
            with monkeypatch.context() as patch:
                if failure == "fsync":
                    patch.setattr(os, "fsync", broken)
                else:
                    patch.setattr(type(store), "_apply_durable_record", broken)
                exercise()
        with duckdb.connect(str(store._detour_db_path), read_only=True) as connection:
            assert connection.execute("SELECT count(*) FROM detour_http_records").fetchone() == (0,)
    # fsync failure need not mean zero bytes: no automatic retry or repair is permitted.
    assert len(Path(store._replay_log).read_bytes().splitlines()) == 1


@pytest.mark.parametrize("fails", (False, True))
def test_response_record_promise_waiter_cancellation_preserves_completion(
    fails: bool, threaded_loop: asyncio.Runner,
) -> None:
    entered = Event()
    release = Event()
    record = persisted_http_record(
        record_id=uuid7(), method="GET", path="/pull", response_code=HTTPStatus.OK,
    )
    failure = OSError("response processing failed")

    def work() -> HttpRequestLogRecord:
        entered.set()
        assert release.wait(timeout=5), "test did not release completion work"
        if fails:
            raise failure
        return record

    async def exercise() -> None:
        promise = ResponseRecordPromise[HttpRequestLogRecord]._start(
            BackendStoreAcknowledgment.ACK, work, asyncio.get_running_loop(),
        )
        waiting = asyncio.create_task(promise.response_record())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
        finally:
            release.set()
        response, error = await promise.response_record()
        assert promise.acknowledgment is BackendStoreAcknowledgment.ACK
        if fails:
            assert response is None and error is not None
            assert error.__cause__ is failure
        else:
            assert response is record and error is None
        assert await promise.response_record() == (response, error)

    threaded_loop.run(asyncio.wait_for(exercise(), timeout=10))


@pytest.mark.parametrize("line_count", (2, 3))
def test_explicit_replay_rejects_incomplete_push_group_without_projecting_it(
    backend_store: store_models.AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    line_count: int,
) -> None:
    store = backend_store
    with pytest.raises(RuntimeError, match="interrupted push"), store._writable(runtime):
        payload = valid_submission_body()
        fixtures.commit(store, payload, payload)
        raise RuntimeError("interrupted push")
    # Construct a synthetic log ending after the accepted push or its commit.
    log = Path(store._replay_log)
    lines = log.read_bytes().splitlines(keepends=True)[:line_count]
    log.chmod(0o600)
    log.write_bytes(b"".join(lines))
    repin(runtime, store)
    with pytest.raises(ValueError, match="Incomplete push group at replay line 2"):
        store._rebuild_from_log(runtime, reset_confirmed=True, confirm_replay=lambda: True)
    with duckdb.connect(str(store._detour_db_path), read_only=True) as connection:
        assert connection.execute(
            "SELECT record_ordinal, method, path FROM detour_http_records ORDER BY record_ordinal"
        ).fetchall() == [(1, "GET", "/pull")]
        assert connection.execute(
            f"SELECT count(*) FROM {api.AUTHORITATIVE_ATTEMPTS_TABLE}"
        ).fetchone() == (0,)
    assert log.read_bytes() == b"".join(lines)


@pytest.mark.parametrize("path", ("/commit", "/validate"))
def test_invalid_synthetic_envelope_is_fsynced_before_domain_rejection(
    runtime: AiAugmentBackendContext,
    backend_store: store_models.AiAugmentBackendStore,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    record = HttpRequestLogRecord(
        schema_version="1.1", method="POST", scheme="http", host="invalid", port=None,
        path=path, query="", request_headers={}, request_body="{}",
        response_code=None, response_headers=None, response_body=None,
        received_at_unix_usec=None, ready_to_respond_at_unix_usec=None, duration_usec=None,
    )
    fsynced: list[bytes] = []
    real_fsync = os.fsync
    log_path = Path(backend_store._replay_log)

    def fsync(descriptor: int) -> None:
        real_fsync(descriptor)
        if os.fstat(descriptor).st_ino == log_path.stat().st_ino:
            fsynced.append(log_path.read_bytes())

    with pytest.raises(RuntimeError, match="Store failed"), backend_store._writable(runtime):
        monkeypatch.setattr(os, "fsync", fsync)
        with pytest.raises(api._PushValidationError):
            backend_store._append_authoritative_record(record)
        payload = log_path.read_bytes()
        assert fsynced == [payload]
        assert payload.endswith(b"\n")
        assert HttpRequestLogRecord.model_validate_json(payload) == record
        assert backend_store.current_commit_record is None
        assert backend_store.current_validation_record is None
        assert backend_store.initial_validation_record is None
    with duckdb.connect(str(backend_store._detour_db_path), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM detour_http_records").fetchone() == (0,)
