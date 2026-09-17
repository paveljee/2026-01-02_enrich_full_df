from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid7

import duckdb
import pytest
import requests

from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    DOCX_COLUMNS,
    KTP_AI_AUGMENT_EDUCATION_COL,
)
from src.detours.detour_ai_augment.src.backend import api
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_backend_store import (  # noqa: E501
    AiAugmentBackendStore,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (  # noqa: E501
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_event import (
    BackendLifecycle,
    CodexRolloutRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.model_http_interceptor import (  # noqa: E501
    ModelHttpInterceptor,
    ReplayInputMissing,
    RequestsBinding,
    model_http_context,
    request_body,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.query_response import (
    QueryResponse,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.validation_event import (  # noqa: E501
    VALIDATE_PATH,
    ValidationRequestBody,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.query_request import (  # noqa: E501
    QueryRequest,
)
from src.detours.detour_ai_augment.tests.backend import test_api as fixtures
from src.detours.detour_ai_augment.tests.backend.test_api import (
    OPERATOR_CAPTURED_SESSION_ID,
    TEST_NAMEKEY,
    TEST_NAMEKEY_MODEL,
    BackendTestPaths,
    create_operator_capture_source_database,
    operator_capture_rollout,
    persisted_http_record,
    report_for_rollout,
    runtime_for_test,
    standardized_submission_body,
    valid_submission_body,
)
from src.helpers.data_models.http_request_log import HttpRequestLogRecord
from src.helpers.vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL

backend_test_paths = fixtures.backend_test_paths


@pytest.fixture
def runtime(tmp_path: Path, backend_test_paths: BackendTestPaths) -> AiAugmentBackendContext:
    source = tmp_path / "source.duckdb"
    create_operator_capture_source_database(source, {key: "NR" for key in DOCX_COLUMNS})
    runtime = runtime_for_test(
        tmp_path,
        backend_test_paths,
        source_database=source,
        namekey=TEST_NAMEKEY,
        codex_match_version=1,
    )

    runtime.pipeline_config.backend_store.rebuild_from_log(runtime, reset_confirmed=True)
    return runtime


def commit(
    store: AiAugmentBackendStore,
    payload: dict[str, Any],
    rollout_payload: dict[str, Any],
    pull: HttpRequestLogRecord | None = None,
    *,
    rollout_suffix: bytes = b"",
) -> UUID:
    if pull is None:
        pull = persisted_http_record(
            record_id=uuid7(),
            method="GET",
            path="/pull",
            response_code=200,
        ).model_copy(
            update={
                "response_headers": {"content-type": api.MEDIA_TYPE},
                "response_body": api.json_line({
                    KTP_FIRST_NAME_COL: TEST_NAMEKEY_MODEL.first_name,
                    KTP_LAST_NAME_COL: TEST_NAMEKEY_MODEL.last_name,
                }),
            }
        )
        pull = store.append_authoritative_record(pull)
    push = store.append_authoritative_record(
        persisted_http_record(
            record_id=uuid7(),
            method="POST",
            path="/push",
            response_code=202,
            request_body=json.dumps(payload),
        )
    )
    rollout_bytes = operator_capture_rollout(rollout_payload) + rollout_suffix
    digest = hashlib.sha256(rollout_bytes).hexdigest()
    store.rollout_cas.initialize()
    blob = store.rollout_cas.path / digest[:2] / digest[2:4] / digest
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(rollout_bytes)
    relative = PurePosixPath(
        f"2026/09/03/rollout-2026-09-03T15-16-00-{OPERATOR_CAPTURED_SESSION_ID}.jsonl"
    )
    draft = api._synthetic_commit_record(
        pull_record=pull,
        push_record=push,
        session_id=UUID(OPERATOR_CAPTURED_SESSION_ID),
        rollout=CodexRolloutRecord(
            sha256=digest,
            size=len(rollout_bytes),
            line_count=rollout_bytes.count(b"\n"),
        ),
        rollout_filename=relative.name,
        appendwatch_report=report_for_rollout(relative).encode(),
        namekey=TEST_NAMEKEY_MODEL,
    )
    return store.append_authoritative_record(draft).record_id


def standardized_payload() -> dict[str, Any]:
    payload = standardized_submission_body(valid_submission_body())
    education = payload[KTP_AI_AUGMENT_EDUCATION_COL]
    assert isinstance(education, dict)
    education["standardized_value"] = [
        {
            "degree_conferred": "PhD",
            "isced_level": "8",
            "year_conferred": 2000,
            "place_conferred": {
                "organization_name": "Stanford University",
                "openalex_id": "https://openalex.org/I97018004",
                "ror": "https://ror.org/00f54p054",
            },
        }
    ]
    return payload


def test_live_validation_replays_with_only_referenced_http(
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = runtime.pipeline_config.backend_store
    captured: list[str] = []
    monkeypatch.setenv("OPENALEX_API_KEY", "isolated-test-key")

    def send(
        _session: requests.Session, request: requests.PreparedRequest, **kwargs: Any
    ) -> requests.Response:
        assert kwargs["allow_redirects"] is False
        # Capture is outside both the Store lock and its speculative transaction.
        assert store._lock.acquire(blocking=False)
        store._lock.release()
        assert not store._transaction_active
        assert store._detour_db._conn is None
        captured.append(request.url or "")
        response = requests.Response()
        response.status_code = 200
        response.request = request
        response.url = request.url or ""
        response.headers = requests.structures.CaseInsensitiveDict({
            "Content-Type": "application/json"
        })
        payload = (
            {"display_name": "Stanford University", "ror": "https://ror.org/00f54p054"}
            if "openalex.org" in response.url
            else {"names": [{"value": "Stanford University", "types": ["ror_display"]}]}
        )
        response._content = json.dumps(payload).encode()
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    accepted = standardized_payload()
    baseline = valid_submission_body()
    education = baseline[KTP_AI_AUGMENT_EDUCATION_COL]
    assert isinstance(education, dict)
    education["web_search_excerpts"][0]["excerpt"] = "not verified"
    with store.writable(runtime):
        baseline_id = commit(store, baseline, accepted)
        assert store.query(runtime, QueryRequest()).attempts == ()
        rejected = store.validate_commit(baseline_id)
        assert rejected.attempt.post_commit_validation.result == BackendLifecycle.REJECTED
        retry_pull = store.append_authoritative_record(
            persisted_http_record(
                record_id=uuid7(),
                method="GET",
                path="/pull",
                response_code=200,
            ).model_copy(
                update={
                    "response_headers": {"content-type": api.MARKDOWN_MEDIA_TYPE},
                    "response_body": rejected.attempt.post_commit_validation.detail,
                }
            )
        )
        commit_id = commit(store, accepted, accepted, retry_pull)
        result = store.validate_commit(commit_id)
        assert result.attempt.post_commit_validation.result == BackendLifecycle.ACCEPTED
        assert len(captured) == 2
        assert len(result.http_records) == 2
        assert result.validation_record is not None
        validation = result.validation_record
        envelope = ValidationRequestBody.model_validate_json(validation.request_body or "")
        assert envelope.http_record_ids == tuple(r.record_id for r in result.http_records)
        assert validation.path == VALIDATE_PATH
        assert validation.request_headers == result.attempt.commit_record.request_headers
        assert all(
            getattr(validation, name) is None
            for name in (
                "response_code",
                "response_headers",
                "response_body",
                "received_at_unix_usec",
                "ready_to_respond_at_unix_usec",
                "duration_usec",
            )
        )
        for record in result.http_records:
            assert record == store.http_record(record.record_id)
        snapshot = store.query(runtime, QueryRequest()).model_dump_json()
        # A later observation of the same URL must not replace the linked validation input.
        store.append_authoritative_record(
            result.http_records[0].model_copy(
                update={
                    "record_id": uuid7(),
                    "response_body": "{}",
                }
            )
        )
        log_bytes = Path(runtime.pipeline_config.replay_log).read_bytes()
        assert b"isolated-test-key" not in log_bytes
        assert not list(runtime.pipeline_config.output_dir.iterdir())

    def no_network(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("Replay/QueryResponse restoration attempted live HTTP")

    monkeypatch.setattr(requests.Session, "send", no_network)
    monkeypatch.delenv("OPENALEX_API_KEY")
    restored = QueryResponse.from_serialized_json(snapshot)
    assert restored.model_dump_json() == snapshot
    replay_store = AiAugmentBackendStore.from_resources(
        replay_log=runtime.pipeline_config.replay_log,
        detour_db=store._detour_db.model_copy(
            update={"path": store.detour_db_path.with_name("rebuilt.duckdb")}
        ),
        rollout_cas=store.rollout_cas,
    )
    live_database = fixtures.logical_database_snapshot(store.detour_db_path)
    mode = Path(runtime.pipeline_config.replay_log).stat().st_mode
    rebuild_for_test(replay_store, runtime)
    with replay_store.read_only():
        assert replay_store.query(runtime, QueryRequest()).model_dump_json() == snapshot
        assert Path(runtime.pipeline_config.replay_log).read_bytes() == log_bytes
        with pytest.raises(RuntimeError):
            replay_store.append_authoritative_record(result.http_records[0])
    assert Path(runtime.pipeline_config.replay_log).stat().st_mode == mode
    assert fixtures.logical_database_snapshot(replay_store.detour_db_path) == live_database


def test_readback_failure_requires_explicit_new(
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = runtime.pipeline_config.backend_store
    draft = persisted_http_record(record_id=uuid7(), method="GET", path="/pull", response_code=200)
    original = AiAugmentBackendStore.http_record_with_ordinal
    with pytest.raises(RuntimeError, match="Backend Store failed"), store.writable(runtime):
        with monkeypatch.context() as patch:
            def fail_readback(*_args: Any, **_kwargs: Any) -> Any:
                log_bytes = Path(runtime.pipeline_config.replay_log).read_bytes()
                assert str(draft.record_id).encode() in log_bytes
                raise RuntimeError("injected DB readback failure")

            patch.setattr(AiAugmentBackendStore, "http_record_with_ordinal", fail_readback)
            with pytest.raises(RuntimeError, match="injected DB readback failure"):
                store.append_authoritative_record(draft)
        with pytest.raises(RuntimeError, match="Backend Store failed"):
            store.query(runtime, QueryRequest())
    with duckdb.connect(str(store.detour_db_path), read_only=True) as connection:
        assert connection.execute(
            f"SELECT count(*) FROM {api.AUTHORITATIVE_RECORDS_TABLE}"
        ).fetchone() == (0,)
    fresh = AiAugmentBackendStore.from_resources(
        replay_log=store._replay_log, detour_db=store._detour_db, rollout_cas=store.rollout_cas,
    )
    with pytest.raises(ValueError, match="missing"):
        with fresh.read_only():
            pytest.fail("Resume must not apply the durable tail")
    rebuild_for_test(store, runtime)
    with store.read_only():
        stored = store.http_record(draft.record_id)
        assert stored == draft and stored is not draft
        assert original(store, draft.record_id)[1] == stored


def test_generic_interception_matches_method_headers_and_body() -> None:
    observed: list[HttpRequestLogRecord] = []

    def resolve(request: requests.PreparedRequest, **_kwargs: Any) -> HttpRequestLogRecord:
        target = urlsplit(request.url or "")
        record = HttpRequestLogRecord(
            schema_version="1.1",
            method=request.method or "",
            scheme=target.scheme,
            host=target.hostname or "",
            port=target.port,
            path=target.path,
            query=target.query,
            request_headers=dict(request.headers),
            request_body=request_body(request),
            response_code=200,
            response_headers={},
            response_body=request_body(request) or "GET",
            received_at_unix_usec=None,
            ready_to_respond_at_unix_usec=1,
            duration_usec=1,
        )
        observed.append(record)
        return record

    http = ModelHttpInterceptor(record_get=resolve)
    binding = RequestsBinding()
    with model_http_context(http):
        assert binding.get("https://model.invalid/value").text == "GET"
        assert binding.post("https://model.invalid/value", data="one").text == "one"
        assert binding.post("https://model.invalid/value", data="two").text == "two"
        assert binding.post("https://model.invalid/value", data="one").text == "one"
    assert len(observed) == 3
    with model_http_context(ModelHttpInterceptor.from_records(observed)):
        assert binding.post("https://model.invalid/value", data="two").text == "two"
        with pytest.raises(ReplayInputMissing):
            binding.post(
                "https://model.invalid/value", data="one", headers={"X-Variant": "changed"}
            )


def test_execute_results_are_detached_and_consumed(
    runtime: AiAugmentBackendContext,
) -> None:
    store = runtime.pipeline_config.backend_store
    with store.writable(runtime):
        result = store.execute("SELECT i FROM range(?) AS t(i) ORDER BY i", [3])
        # Another query on the shared connection cannot overwrite this result.
        assert store.execute("SELECT 99").fetchone() == (99,)
        assert result.fetchone() == (0,)
    # Fetching never depends on an open Store or borrowed DuckDB cursor.
    assert result.fetchall() == [(1,), (2,)]
    assert result.fetchone() is None
    assert result.fetchall() == []
    with store.read_only():
        assert store.execute("SELECT 1 WHERE false").fetchone() is None
        with pytest.raises(RuntimeError, match="transaction scope"):
            store.execute("CREATE TABLE forbidden_write (i INTEGER)")


def rebuild_for_test(store: AiAugmentBackendStore, runtime: AiAugmentBackendContext) -> None:
    # Emulate the operator repinning the hash before explicitly accepting --new replay.
    store._replay_log = store._replay_log.model_copy(update={
        "hash": hashlib.sha256(Path(store._replay_log).read_bytes()).hexdigest(),
    })
    store.rebuild_from_log(runtime, reset_confirmed=True, confirm_replay=lambda: True)


def no_network(*_args: Any, **_kwargs: Any) -> Any:
    pytest.fail("Card publication/replay attempted live HTTP")


def test_validation_preview_does_not_publish_zip(
    runtime: AiAugmentBackendContext, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = runtime.pipeline_config.backend_store
    payload = valid_submission_body()
    monkeypatch.setattr(requests.Session, "send", no_network)
    with store.writable(runtime):
        commit_id = commit(store, payload, payload)
        original = AiAugmentBackendStore.append_authoritative_record
        before_preview = fixtures.logical_database_snapshot(store.detour_db_path)
        with monkeypatch.context() as patch:
            def interrupt(
                selected: AiAugmentBackendStore, record: HttpRequestLogRecord,
            ) -> HttpRequestLogRecord:
                if record.path == VALIDATE_PATH:
                    body = ValidationRequestBody.model_validate_json(record.request_body or "")
                    assert body.post_commit_validation.result == BackendLifecycle.ACCEPTED
                    raise OSError("interrupted before validation append")
                return original(selected, record)
            patch.setattr(AiAugmentBackendStore, "append_authoritative_record", interrupt)
            with pytest.raises(OSError, match="before validation append"):
                store.validate_commit(commit_id)
        assert fixtures.logical_database_snapshot(store.detour_db_path) == before_preview
        assert not list(runtime.pipeline_config.output_dir.iterdir())
        assert store.query(runtime, QueryRequest()).attempts == ()
        result = store.validate_commit(commit_id)
        assert result.attempt.post_commit_validation.result == BackendLifecycle.ACCEPTED
        assert not list(runtime.pipeline_config.output_dir.iterdir())


def test_live_repeat_resume_and_explicit_replay_never_publish(
    runtime: AiAugmentBackendContext, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = runtime.pipeline_config.backend_store
    payload = valid_submission_body()
    monkeypatch.setattr(requests.Session, "send", no_network)
    output = runtime.pipeline_config.output_dir
    output.mkdir(parents=True, exist_ok=True)
    old_archive = output / "existing.zip"
    old_archive.write_bytes(b"leave existing archives alone")
    before = old_archive.stat().st_mtime_ns
    with store.writable(runtime):
        commit_id = commit(store, payload, payload)
        result = store.validate_commit(commit_id)
        assert result.attempt.post_commit_validation.result == BackendLifecycle.ACCEPTED
        assert store.validate_commit(commit_id) == result
        snapshot = store.query(runtime, QueryRequest()).model_dump_json()
    with store.writable(runtime):
        assert store.query(runtime, QueryRequest()).model_dump_json() == snapshot
    rebuild_for_test(store, runtime)
    with store.read_only():
        assert store.query(runtime, QueryRequest()).model_dump_json() == snapshot
    assert list(output.iterdir()) == [old_archive]
    assert old_archive.read_bytes() == b"leave existing archives alone"
    assert old_archive.stat().st_mtime_ns == before
