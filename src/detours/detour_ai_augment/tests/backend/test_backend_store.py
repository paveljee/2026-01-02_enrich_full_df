from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid7

import duckdb
import pytest

from src.detours.detour_ai_augment.src.backend import api, server
from src.detours.detour_ai_augment.src.backend.helpers.data_models import (
    ai_augment_backend_store as store_models,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.tests.backend import test_http_interceptor as fixtures
from src.detours.detour_ai_augment.tests.backend.test_api import persisted_http_record

backend_test_paths = fixtures.backend_test_paths
runtime = fixtures.runtime


def append(runtime: AiAugmentBackendContext) -> bytes:
    store = runtime.pipeline_config.backend_store
    with store.writable(runtime):
        store.append_authoritative_record(persisted_http_record(
            record_id=uuid7(), method="GET", path="/pull", response_code=200,
        ))
    return Path(store._replay_log).read_bytes()


def anchor(runtime: AiAugmentBackendContext) -> dict[str, Any]:
    with duckdb.connect(str(runtime.pipeline_config.backend_store.detour_db_path),
                        read_only=True) as connection:
        row = connection.execute(
            "SELECT comment FROM duckdb_tables() WHERE table_name = 'detour_http_records'"
        ).fetchone()
    assert row is not None
    return dict(json.loads(row[0]))


def repin(runtime: AiAugmentBackendContext) -> None:
    store = runtime.pipeline_config.backend_store
    store._replay_log = store._replay_log.model_copy(update={
        "hash": hashlib.sha256(Path(store._replay_log).read_bytes()).hexdigest(),
        "verify_hash_on_init": False,
    })


def test_stale_dashboard_hash_retains_boundary_and_verified_hash_promotes_only_writable(
    runtime: AiAugmentBackendContext,
) -> None:
    store = runtime.pipeline_config.backend_store
    initial = anchor(runtime)
    line = append(runtime)
    with store.read_only():
        assert store.execute("SELECT raw_line_sha256 FROM detour_http_records").fetchone() == (
            hashlib.sha256(line).hexdigest(),
        )
    with store.writable(runtime):
        pass
    assert anchor(runtime) == initial
    repin(runtime)
    with store.read_only():
        pass
    assert anchor(runtime) == initial
    with store.writable(runtime):
        pass
    assert anchor(runtime) == {
        "sha256": hashlib.sha256(line).hexdigest(), "ordinal": 1, "byte_offset": len(line),
    }
    # An unverified changed config cannot authorize promotion, even in a delegated child.
    store._replay_log = store._replay_log.model_copy(update={"hash": "0" * 64})
    saved = store.detour_db_path.read_bytes()
    with pytest.raises(ValueError, match="Hash verification failed"):
        with store.writable(runtime):
            pytest.fail("unverified hash accepted")
    assert store.detour_db_path.read_bytes() == saved


@pytest.mark.parametrize("damage", (
    "prefix", "suffix", "missing_row", "extra_row", "gap", "truncated", "tail",
    "anchor_boundary", "missing_anchor", "legacy_schema",
))
def test_mismatch_fails_without_any_healing(
    runtime: AiAugmentBackendContext, damage: str,
) -> None:
    store = runtime.pipeline_config.backend_store
    first = append(runtime)
    if damage in {"prefix", "truncated"}:
        repin(runtime)
        with store.writable(runtime):
            pass
    append(runtime)
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
        repin(runtime)
    else:
        store.detour_db_path.chmod(0o600)
        with duckdb.connect(str(store.detour_db_path)) as connection:
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
    saved_db = store.detour_db_path.read_bytes()
    saved_log = log.read_bytes()
    for mode in (store.read_only, lambda: store.writable(runtime)):
        with pytest.raises((ValueError, duckdb.Error)):
            with mode():
                pytest.fail("mismatch accepted")
    assert store.detour_db_path.read_bytes() == saved_db
    assert log.read_bytes() == saved_log


def test_append_preflight_uses_real_append_flags_and_never_writes(
    runtime: AiAugmentBackendContext, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = runtime.pipeline_config.backend_store
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
    with store.writable(runtime):
        pass
    assert len(opened) == 1
    with store.read_only():
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
        with store.writable(runtime):
            pytest.fail("ready despite append failure")
    assert Path(store._replay_log).stat().st_mode & 0o777 == 0o400
    with store.read_only():
        pass


def test_nonempty_replay_refusal_preserves_db_then_exact_raw_line_is_bootstrapped(
    runtime: AiAugmentBackendContext,
) -> None:
    store = runtime.pipeline_config.backend_store
    record = persisted_http_record(record_id=uuid7(), method="GET", path="/pull", response_code=200)
    raw = ("  " + record.model_dump_json() + "  \n").encode()
    log = Path(store._replay_log)
    log.chmod(0o600)
    log.write_bytes(raw)
    repin(runtime)
    before = store.detour_db_path.read_bytes()
    with pytest.raises(ValueError, match="replay confirmation"):
        store.rebuild_from_log(runtime, reset_confirmed=True)
    assert store.detour_db_path.read_bytes() == before
    store.rebuild_from_log(runtime, reset_confirmed=True, confirm_replay=lambda: True)
    with store.read_only():
        assert store.http_record(record.record_id) == record
        assert store.execute("SELECT raw_line_sha256 FROM detour_http_records").fetchone() == (
            hashlib.sha256(raw).hexdigest(),
        )
    assert log.read_bytes() == raw
    assert anchor(runtime)["byte_offset"] == len(raw)


@pytest.mark.parametrize("tail", (b"{}\n", b"{}", b"\n"))
def test_new_replay_stops_at_first_invalid_line_and_keeps_empty_anchor(
    runtime: AiAugmentBackendContext, tail: bytes, caplog: pytest.LogCaptureFixture,
) -> None:
    store = runtime.pipeline_config.backend_store
    log = Path(store._replay_log)
    log.chmod(0o600)
    log.write_bytes(tail)
    repin(runtime)
    with pytest.raises((api._PushValidationError, IndexError)):
        store.rebuild_from_log(runtime, reset_confirmed=True, confirm_replay=lambda: True)
    assert "Replay failed at line 1" in caplog.text
    assert anchor(runtime)["ordinal"] == 0
    assert log.read_bytes() == tail
    with pytest.raises(RuntimeError, match="Store failed"):
        with store.writable(runtime):
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
    runtime: AiAugmentBackendContext, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    store = runtime.pipeline_config.backend_store
    append(runtime)
    old_anchor = anchor(runtime)
    repin(runtime)
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
        with store.writable(runtime):
            pytest.fail("failed opening became ready")
    assert anchor(runtime) == old_anchor
