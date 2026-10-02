from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from http import HTTPStatus
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid7

import duckdb
import pytest
import requests
from fastapi import FastAPI
from starlette.types import Message, Scope

from src.detours.detour_ai_augment.protected.src.backend import api
from src.detours.detour_ai_augment.protected.src.backend.helpers import codex_parse
from src.detours.detour_ai_augment.protected.src.backend.helpers import vars as backend_vars
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.post_commit_validation import (  # noqa: E501
    PostCommitValidation,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    CODEX_RUN_OUTCOME_RECORD_ID_COL,
    CODEX_RUN_OUTCOME_RECORDS_TABLE,
    CODEX_RUN_OUTCOME_SERIALIZED_JSON_COL,
    DOCX_COLUMNS,
    HTTP_CONTENT_TYPE_HEADER,
    HTTP_GET_METHOD,
    KTP_AI_AUGMENT_EDUCATION_COL,
    KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL,
    PULL_PATH,
    SOURCE_KEY_HEADER,
    ContentType,
)
from src.detours.detour_ai_augment.src.backend import server
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_backend_store import (  # noqa: E501
    AiAugmentBackendStore,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (  # noqa: E501
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.codex_innerdict import (
    _RunOutcomeResponseRecordJson,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_request import (
    BackendCommitRequestRecord,
    CodexRolloutRecord,
    CodexSessionRecord,
    _synthetic_commit_request_record,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.lifecycle import (
    BackendLifecycle,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.model_http_interceptor import (  # noqa: E501
    ModelHttpInterceptor,
    ReplayInputMissing,
    RequestsBinding,
    model_http_context,
    request_body,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.pull_event import (
    PullRequestRecord,
    PullResponseRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.push_event import (
    PushRequestRecord,
    PushResponseRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.response_record_promise import (
    BackendStoreAcknowledgment,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.validation_request import (  # noqa: E501
    VALIDATE_PATH,
    BackendValidationRequestRecord,
    ValidationRequestBody,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.dashboard_query_snapshot import (  # noqa: E501
    DashboardQuerySnapshot,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome_event import (  # noqa: E501
    NAME_KEY_HEADER,
    RunOutcomePath,
    RunOutcomeRequestRecord,
    RunOutcomeResponseRecord,
)
from src.detours.detour_ai_augment.tests.backend import test_api as fixtures
from src.detours.detour_ai_augment.tests.backend.test_api import (
    OPERATOR_CAPTURED_SESSION_ID,
    TEST_NAMEKEY,
    TEST_NAMEKEY_MODEL,
    BackendTestPaths,
    backend_store_for_test,
    create_operator_capture_source_database,
    operator_capture_rollout,
    persisted_http_record,
    report_for_rollout,
    runtime_for_test,
    standardized_submission_body,
    valid_submission_body,
)
from src.helpers.data_models.http_request_log import HttpRequestLogRecord
from src.helpers.vars import (
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_LAST_NAME_COL,
)

backend_test_paths = fixtures.backend_test_paths


@pytest.fixture
def validation_http_record() -> BackendValidationRequestRecord:
    _pull, commit = fixtures.retry_commit_records(
        original_pull_record_id=uuid7(), session_id=uuid7(),
        synthetic_record_id_seed="validation-model",
    )
    body = ValidationRequestBody(
        commit_request_record=commit,
        post_commit_validation=PostCommitValidation(
            stage=BackendLifecycle.PYDANTIC_VALIDATION,
            result=BackendLifecycle.REJECTED,
            detail="invalid submission",
            submission_type=None,
            submission=None,
        ),
        initial_validation_request_record=None,
    )
    record = HttpRequestLogRecord(
        schema_version="1.1", method="POST", scheme="http", host="invalid",
        path=VALIDATE_PATH, query="",
        request_headers=dict(commit.request_headers),
        request_body=body.model_dump_json(),
        response_code=None, response_headers=None, response_body=None,
        received_at_unix_usec=None, ready_to_respond_at_unix_usec=None, duration_usec=None,
    )
    return BackendValidationRequestRecord(
        **record.model_dump(mode="python"), validation_request_body=body,
    )


def test_validation_record_preserves_wire_json_and_uuid(
    validation_http_record: BackendValidationRequestRecord,
) -> None:
    body = validation_http_record.validation_request_body
    record = BackendValidationRequestRecord.from_http_request_log_record(
        validation_http_record.http_request_log_record,
        validation_request_body=body,
    )
    assert record.model_dump_json() == validation_http_record.model_dump_json()
    assert record.record_id == validation_http_record.record_id
    assert record.http_request_log_record is record
    assert record.validation_request_body == body
    assert record.validation_request_body.commit_request_record is body.commit_request_record
    assert AiAugmentBackendStore._validated_http_record(record).model_dump() == (
        validation_http_record.model_dump()
    )


@pytest.mark.parametrize(("field", "value"), (
    ("method", "GET"), ("path", "/commit"), ("host", "localhost"),
    ("port", 80), ("query", "extra=1"), ("request_headers", {}),
    ("response_code", 200), ("response_headers", {}), ("response_body", "{}"),
    ("received_at_unix_usec", 1), ("ready_to_respond_at_unix_usec", 2),
    ("duration_usec", 1), ("request_body", None),
))
def test_validation_record_rejects_invalid_envelope(
    validation_http_record: BackendValidationRequestRecord, field: str, value: Any,
) -> None:
    invalid = validation_http_record.model_copy(update={field: value})
    with pytest.raises(ValueError, match="validation .* (invalid contour|missing)"):
        BackendValidationRequestRecord.from_http_request_log_record(
            invalid,
            validation_request_body=validation_http_record.validation_request_body,
        )


def test_validation_record_rejects_mismatched_parsed_body(
    validation_http_record: BackendValidationRequestRecord,
) -> None:
    body = validation_http_record.validation_request_body
    with pytest.raises(ValueError, match="body does not match its record"):
        BackendValidationRequestRecord(
            **validation_http_record.model_dump(),
            validation_request_body=body.model_copy(update={
                "post_commit_validation": body.post_commit_validation.model_copy(
                    update={"detail": "different"},
                ),
            }),
        )


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

    return runtime


@pytest.fixture
def backend_store(runtime: AiAugmentBackendContext) -> AiAugmentBackendStore:
    store = backend_store_for_test(runtime)
    store._rebuild_from_log(runtime, reset_confirmed=True)
    return store


def query_snapshot(store: AiAugmentBackendStore) -> DashboardQuerySnapshot:
    return DashboardQuerySnapshot(
        ai_augment_singular_outerdicts=store.ai_augment_singular_outerdicts(),
    )


def commit(
    store: AiAugmentBackendStore,
    payload: dict[str, Any],
    rollout_payload: dict[str, Any],
    pull: HttpRequestLogRecord | None = None,
    *,
    session_id: UUID = UUID(OPERATOR_CAPTURED_SESSION_ID),
    rollout_suffix: bytes = b"",
    web_arguments: dict[str, object] | None = None,
) -> UUID:
    if pull is None:
        pull = persisted_http_record(
            record_id=uuid7(),
            method="GET",
            path="/pull",
            response_code=200,
        ).model_copy(
            update={
                "response_headers": {"content-type": ContentType.NDJSON},
                "response_body": api.json_line({
                    KTP_FIRST_NAME_COL: TEST_NAMEKEY_MODEL.first_name,
                    KTP_LAST_NAME_COL: TEST_NAMEKEY_MODEL.last_name,
                }),
            }
        )
        pull = store._append_authoritative_record(pull)
    assert isinstance(pull, PullResponseRecord)
    push = store._append_authoritative_record(
        persisted_http_record(
            record_id=uuid7(),
            method="POST",
            path="/push",
            response_code=202,
            request_body=json.dumps(payload),
        )
    )
    assert isinstance(push, PushResponseRecord)
    rollout_bytes = operator_capture_rollout(rollout_payload, session_id=session_id)
    if web_arguments is not None:
        records = [json.loads(line) for line in rollout_bytes.splitlines()]
        for record in records:
            if record["payload"].get("type") == "function_call":
                record["payload"]["arguments"] = json.dumps(web_arguments)
        rollout_bytes = b"".join(
            json.dumps(record, separators=(",", ":")).encode() + b"\n" for record in records
        )
    rollout_bytes += rollout_suffix
    digest = hashlib.sha256(rollout_bytes).hexdigest()
    store.rollout_cas.initialize()
    blob = store.rollout_cas.path / digest[:2] / digest[2:4] / digest
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(rollout_bytes)
    relative = PurePosixPath(
        f"2026/09/03/rollout-2026-09-03T15-16-00-{session_id}.jsonl"
    )
    draft = _synthetic_commit_request_record(
        pull_response_record=pull,
        push_response_record=push,
        session_id=session_id,
        rollout=CodexRolloutRecord(
            sha256=digest,
            size=len(rollout_bytes),
            line_count=rollout_bytes.count(b"\n"),
        ),
        rollout_filename=relative.name,
        appendwatch_report=report_for_rollout(relative).encode(),
        namekey=TEST_NAMEKEY_MODEL,
    )
    return store._append_authoritative_record(draft).record_id


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
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = backend_store
    captured: list[str] = []
    monkeypatch.setenv("OPENALEX_API_KEY", "isolated-test-key")

    def send(
        _session: requests.Session, request: requests.PreparedRequest, **kwargs: Any
    ) -> requests.Response:
        assert kwargs["allow_redirects"] is False
        # Provider I/O follows independently projected push and commit records;
        # a concurrent busy pull projects in its own transaction.
        assert not store._transaction_active
        observed: list[BackendStoreAcknowledgment] = []

        def busy_pull() -> None:
            record = PullRequestRecord.model_validate(
                persisted_http_record(
                    record_id=uuid7(),
                    method="GET",
                    path="/pull",
                    response_code=503,
                ).model_dump()
            )
            pulled = store.promise_pull_response_record(record)
            observed.append(pulled.acknowledgment)
            pull_response, pull_error = asyncio.run(pulled.response_record_promise())
            assert pull_error is None and pull_response is not None
            rejected = PushRequestRecord(
                **persisted_http_record(
                    record_id=uuid7(), method="POST", path="/push",
                    response_code=HTTPStatus.CONFLICT, request_body="{}",
                ).model_dump(),
            )
            immediate, result = store.promise_push_response_record(rejected, session_id=None)
            observed.append(result.acknowledgment)
            response, error = asyncio.run(result.response_record_promise())
            assert error is None and response is not None
            assert immediate is response
            assert response.response_code == HTTPStatus.CONFLICT
            assert response.pull_response_record is None

        thread = threading.Thread(target=busy_pull)
        thread.start()
        thread.join(timeout=2)
        assert not thread.is_alive(), "provider I/O held the Store mutex"
        assert observed == [BackendStoreAcknowledgment.ACK, BackendStoreAcknowledgment.ACK]
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
    with store._writable(runtime):
        assert store.current_replayed_record is None
        baseline_id = commit(store, baseline, accepted)
        assert all(
            not researcher.codex_innerdicts
            for researcher in query_snapshot(store).ai_augment_singular_outerdicts
        )
        rejected = store._validate_commit(baseline_id)
        assert (
            rejected.validation_request_body.post_commit_validation.result
            == BackendLifecycle.REJECTED
        )
        initial = store.current_replayed_record
        assert isinstance(initial, BackendValidationRequestRecord)
        assert initial.validation_request_body.initial_validation_request_record is None
        assert initial.validation_request_body.commit_request_record.model_dump(
            mode="json"
        ) == rejected.validation_request_body.commit_request_record.model_dump(mode="json")
        retry_pull = store._append_authoritative_record(
            persisted_http_record(
                record_id=uuid7(),
                method="GET",
                path="/pull",
                response_code=200,
            ).model_copy(
                update={
                    "response_headers": {"content-type": ContentType.MARKDOWN},
                    "response_body": rejected.validation_request_body.post_commit_validation.detail,
                }
            )
        )
        # Repeated polling must not replace the retry baseline or infer a different root.
        retry_pull = store._append_authoritative_record(
            retry_pull.model_copy(update={"record_id": uuid7()})
        )
        commit_id = commit(store, accepted, accepted, retry_pull)
        result = store._validate_commit(commit_id)
        assert (
            result.validation_request_body.post_commit_validation.result
            == BackendLifecycle.ACCEPTED
        )
        assert len(captured) == 2
        assert len(result.validation_request_body.openalex_ror_records) == 2
        assert result is not None
        validation = store.current_replayed_record
        assert isinstance(validation, BackendValidationRequestRecord)
        assert validation.model_dump_json() == result.model_dump_json()
        assert validation.validation_request_body.initial_validation_request_record == initial
        assert validation.validation_request_body.commit_request_record.model_dump(
            mode="json"
        ) == result.validation_request_body.commit_request_record.model_dump(mode="json")
        envelope = json.loads(validation.request_body or "")
        assert PostCommitValidation.model_validate(
            envelope["post_commit_validation"], strict=False,
        ) == validation.validation_request_body.post_commit_validation
        assert validation.model_dump_json() == (
            store._http_record(validation.record_id).model_dump_json()
        )
        assert tuple(UUID(value) for value in envelope["openalex_ror_records_ids"]) == tuple(
            record.record_id for record in result.validation_request_body.openalex_ror_records
        )
        assert validation.path == VALIDATE_PATH
        assert (
            validation.request_headers
            == result.validation_request_body.commit_request_record.request_headers
        )
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
        for record in result.validation_request_body.openalex_ror_records:
            assert record == store._http_record(record.record_id)
        snapshot = query_snapshot(store).model_dump_json()
        # A later observation of the same URL must not replace the linked validation input.
        store._append_authoritative_record(
            result.validation_request_body.openalex_ror_records[0].model_copy(
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
    restored = DashboardQuerySnapshot.from_serialized_json(snapshot)
    assert restored.model_dump_json() == snapshot
    assert "attempts" not in json.loads(snapshot)
    assert all(not item.codex_innerdicts for item in restored.ai_augment_singular_outerdicts)
    replay_store = AiAugmentBackendStore._from_resources(
        replay_log=runtime.pipeline_config.replay_log,
        detour_db=store._detour_db.model_copy(
            update={"path": store._detour_db_path.with_name("rebuilt.duckdb")}
        ),
        rollout_cas=store.rollout_cas,
    )
    live_database = fixtures.logical_database_snapshot(store._detour_db_path)
    mode = Path(runtime.pipeline_config.replay_log).stat().st_mode
    rebuild_for_test(replay_store, runtime)
    with replay_store._read_only(runtime):
        assert query_snapshot(replay_store).model_dump_json() == snapshot
        assert Path(runtime.pipeline_config.replay_log).read_bytes() == log_bytes
        with pytest.raises(RuntimeError):
            replay_store._append_authoritative_record(result.validation_request_body.openalex_ror_records[0])
    assert Path(runtime.pipeline_config.replay_log).stat().st_mode == mode
    assert fixtures.logical_database_snapshot(replay_store._detour_db_path) == live_database


@pytest.mark.parametrize(
    ("arguments", "accepted"),
    (
        ({"find": [{"ref_id": "turn0search0", "pattern": "evidence"}]}, True),
        ({"search_query": [{"q": "evidence"}], "open": [{"ref_id": "turn0search0"}]}, True),
        ({"image_query": [{"q": "evidence"}]}, False),
        ({"search_query": [{"q": "evidence"}], "image_query": [{"q": "evidence"}]}, False),
    ),
)
def test_web_argument_eligibility_drives_retry_and_replays_identically(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
    threaded_loop: asyncio.Runner,
    arguments: dict[str, object],
    accepted: bool,
) -> None:
    store = backend_store
    monkeypatch.setattr(requests.Session, "send", no_network)
    monkeypatch.setattr(api, "BACKEND_LIFECYCLE", BackendLifecycle.READY)
    payload = valid_submission_body()
    with store._writable(runtime):
        commit_id = commit(store, payload, payload, web_arguments=arguments)
        result = store._validate_commit(commit_id)
        assert result is not None
        validation = result.validation_request_body.post_commit_validation
        assert validation.result is (
            BackendLifecycle.ACCEPTED if accepted else BackendLifecycle.REJECTED
        )
        assert validation.stage is (
            BackendLifecycle.ACCEPTED if accepted else BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION
        )
        api.update_pull_state(result)
        response = threaded_loop.run(api.authoritative_pull(
            requests.Request("GET", "http://invalid/pull").prepare(), store,
        ))
        assert response.status_code == (HTTPStatus.GONE if accepted else HTTPStatus.OK)
        if not accepted:
            assert response.headers["content-type"].startswith(ContentType.MARKDOWN)
            assert validation.detail is not None
            assert response.text.strip() == validation.detail.strip()
            assert Locale.EVIDENCE_RETRY_INSTRUCTION in response.text
            assert store._execute(
                f"SELECT count(*) FROM {backend_vars.CODEX_RETRY_BASELINE_TABLE}"
            ).fetchone() == (1,)
            assert store._execute(
                f"SELECT {backend_vars.CODEX_EVIDENCE_ACCEPTED_COL} "
                f"FROM {backend_vars.CODEX_EVIDENCE_AUDIT_TABLE}"
            ).fetchall() == [(False,)]
        snapshot = query_snapshot(store).model_dump_json()
    log_bytes = Path(store._replay_log).read_bytes()
    live_database = fixtures.logical_database_snapshot(store._detour_db_path)
    rebuild_for_test(store, runtime)
    with store._read_only(runtime):
        assert query_snapshot(store).model_dump_json() == snapshot
    assert fixtures.logical_database_snapshot(store._detour_db_path) == live_database
    assert Path(store._replay_log).read_bytes() == log_bytes


def test_readback_failure_requires_explicit_new(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = backend_store
    draft = persisted_http_record(record_id=uuid7(), method="GET", path="/pull", response_code=200)
    original = AiAugmentBackendStore._http_record_with_ordinal
    with pytest.raises(RuntimeError, match="Backend Store failed"), store._writable(runtime):
        with monkeypatch.context() as patch:
            def fail_readback(*_args: Any, **_kwargs: Any) -> Any:
                log_bytes = Path(runtime.pipeline_config.replay_log).read_bytes()
                assert str(draft.record_id).encode() in log_bytes
                raise RuntimeError("injected DB readback failure")

            patch.setattr(AiAugmentBackendStore, "_http_record_with_ordinal", fail_readback)
            with pytest.raises(RuntimeError, match="injected DB readback failure"):
                store._append_authoritative_record(draft)
        with pytest.raises(RuntimeError, match="Backend Store failed"):
            query_snapshot(store)
    with duckdb.connect(str(store._detour_db_path), read_only=True) as connection:
        assert connection.execute(
            f"SELECT count(*) FROM {api.AUTHORITATIVE_RECORDS_TABLE}"
        ).fetchone() == (0,)
    fresh = AiAugmentBackendStore._from_resources(
        replay_log=store._replay_log,
        detour_db=store._detour_db,
        rollout_cas=store.rollout_cas,
    )
    with pytest.raises(ValueError, match="missing"):
        with fresh._read_only(runtime):
            pytest.fail("Resume must not apply the durable tail")
    rebuild_for_test(store, runtime)
    with store._read_only(runtime):
        stored = store._http_record(draft.record_id)
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
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
) -> None:
    store = backend_store
    with store._writable(runtime):
        result = store._execute("SELECT i FROM range(?) AS t(i) ORDER BY i", [3])
        # Another query on the shared connection cannot overwrite this result.
        assert store._execute("SELECT 99").fetchone() == (99,)
        assert result.fetchone() == (0,)
    # Fetching never depends on an open Store or borrowed DuckDB cursor.
    assert result.fetchall() == [(1,), (2,)]
    assert result.fetchone() is None
    assert result.fetchall() == []
    with store._read_only(runtime):
        assert store._execute("SELECT 1 WHERE false").fetchone() is None
        with pytest.raises(RuntimeError, match="transaction scope"):
            store._execute("CREATE TABLE forbidden_write (i INTEGER)")


def rebuild_for_test(store: AiAugmentBackendStore, runtime: AiAugmentBackendContext) -> None:
    # Emulate the operator repinning the hash before explicitly accepting --new replay.
    store._replay_log = store._replay_log.model_copy(update={
        "hash": hashlib.sha256(Path(store._replay_log).read_bytes()).hexdigest(),
    })
    store._rebuild_from_log(runtime, reset_confirmed=True, confirm_replay=lambda: True)


def no_network(*_args: Any, **_kwargs: Any) -> Any:
    pytest.fail("Card publication/replay attempted live HTTP")


def test_validation_preview_does_not_publish_zip(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = backend_store
    payload = valid_submission_body()
    monkeypatch.setattr(requests.Session, "send", no_network)
    with store._writable(runtime):
        commit_id = commit(store, payload, payload)
        original = AiAugmentBackendStore._append_authoritative_record
        before_preview = fixtures.store_database_snapshot(store)
        with monkeypatch.context() as patch:
            def interrupt(
                selected: AiAugmentBackendStore, record: HttpRequestLogRecord,
            ) -> HttpRequestLogRecord:
                if record.path == VALIDATE_PATH:
                    body = json.loads(record.request_body or "")
                    assert PostCommitValidation.model_validate(
                        body["post_commit_validation"],
                        strict=False,
                    ).result == BackendLifecycle.ACCEPTED
                    raise OSError("interrupted before validation append")
                return original(selected, record)

            patch.setattr(AiAugmentBackendStore, "_append_authoritative_record", interrupt)
            with pytest.raises(OSError, match="before validation append"):
                store._validate_commit(commit_id)
        assert fixtures.store_database_snapshot(store) == before_preview
        assert not list(runtime.pipeline_config.output_dir.iterdir())
        assert all(
            not researcher.codex_innerdicts
            for researcher in query_snapshot(store).ai_augment_singular_outerdicts
        )
        result = store._validate_commit(commit_id)
        assert (
            result.validation_request_body.post_commit_validation.result
            == BackendLifecycle.ACCEPTED
        )
        assert not list(runtime.pipeline_config.output_dir.iterdir())


def test_live_repeat_resume_and_explicit_replay_never_publish(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = backend_store
    payload = valid_submission_body()
    monkeypatch.setattr(requests.Session, "send", no_network)
    output = runtime.pipeline_config.output_dir
    output.mkdir(parents=True, exist_ok=True)
    old_archive = output / "existing.zip"
    old_archive.write_bytes(b"leave existing archives alone")
    before = old_archive.stat().st_mtime_ns
    with store._writable(runtime):
        commit_id = commit(store, payload, payload)
        result = store._validate_commit(commit_id)
        assert (
            result.validation_request_body.post_commit_validation.result
            == BackendLifecycle.ACCEPTED
        )
        assert store._validate_commit(commit_id) == result
        snapshot = query_snapshot(store).model_dump_json()
    with store._writable(runtime):
        assert query_snapshot(store).model_dump_json() == snapshot
    rebuild_for_test(store, runtime)
    with store._read_only(runtime):
        assert query_snapshot(store).model_dump_json() == snapshot
    assert list(output.iterdir()) == [old_archive]
    assert old_archive.read_bytes() == b"leave existing archives alone"
    assert old_archive.stat().st_mtime_ns == before


def outcome_for_commit(
    store: AiAugmentBackendStore,
    commit_request_record: BackendCommitRequestRecord,
    *,
    path: RunOutcomePath = RunOutcomePath.COMPLETED,
    partial: bool = False,
    no_session: bool = False,
    other_session: bool = False,
) -> RunOutcomeResponseRecord:
    body = commit_request_record.commit_request_body
    session = body.codex_session_record
    if partial or no_session:
        session = CodexSessionRecord(
            session_id=None if no_session else session.session_id,
            codex_rollout_record=None, appendwatch_report_record=None,
        )
    request = RunOutcomeRequestRecord.from_http_request(
        received_at_unix_usec=1, method="POST", scheme="http", host="invalid",
        port=None, path=path, query="",
        request_headers={
            NAME_KEY_HEADER: commit_request_record.request_headers[NAME_KEY_HEADER],
            **({"Session-ID": str(uuid7() if other_session else session.session_id)}
               if session.session_id is not None else {}),
            **(
                {"ETag": f'"{store.current_replayed_record.record_id}"'}
                if isinstance(store.current_replayed_record, BackendValidationRequestRecord)
                else {}
            ),
        },
        request_body=None,
    )
    return store._construct_run_outcome_response_record(
        request,
        codex_session_record=session,
        rollout_filename=(
            None if partial or no_session
            else AiAugmentBackendStore._parse_source_key_header(
                commit_request_record.request_headers[SOURCE_KEY_HEADER],
            )[0]
        ),
    )


@pytest.mark.parametrize("path", tuple(RunOutcomePath))
@pytest.mark.parametrize("partial", (False, True))
def test_outcome_materializes_persisted_ids_identically_live_and_replay(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
    path: RunOutcomePath,
    partial: bool,
) -> None:
    monkeypatch.setattr(requests.Session, "send", no_network)
    store = backend_store
    payload = valid_submission_body()
    with store._writable(runtime):
        commit_id = commit(store, payload, payload)
        result = store._validate_commit(commit_id)
        assert (
            result.validation_request_body.post_commit_validation.result
            is BackendLifecycle.ACCEPTED
        )
        assert result is not None
        interim = query_snapshot(store)
        assert (
            type(interim).from_serialized_json(interim.model_dump_json()).model_dump_json()
            == interim.model_dump_json()
        )
        assert not interim.ai_augment_singular_outerdicts[0].codex_innerdicts
        assert store._execute(
            f'SELECT "{KTP_FILENAME_COL}", "{KTP_FRAGMENT_COL}", '
            f'"{KTP_FRAGMENT_TYPE_COL}", '
            f'"{KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL}" '
            f'FROM {api.CODEX_OUTPUT_ROWS_TABLE}'
        ).fetchone() == (None, None, None, None)
        outcome = outcome_for_commit(
            store, result.validation_request_body.commit_request_record, path=path, partial=partial
        )
        stored = store._append_authoritative_record(outcome)
        assert RunOutcomeResponseRecord.from_http_request_log_record(
            stored
        ).model_dump_json() == stored.model_dump_json()
        assert stored.model_dump_json() == outcome.model_dump_json()
        query = query_snapshot(store)
        assert (
            type(query).from_serialized_json(query.model_dump_json()).model_dump_json()
            == query.model_dump_json()
        )
        assert outcome.response_code == (
            500 if partial else 409 if path is RunOutcomePath.FAILED else 200
        )
        if outcome.response_code != 200 or path is not RunOutcomePath.COMPLETED:
            assert not query.ai_augment_singular_outerdicts[0].codex_innerdicts
        else:
            singular_outerdict = query.ai_augment_singular_outerdicts[0]
            (innerdict,) = singular_outerdict.codex_innerdicts
            data = innerdict.innerdict.data
            for column in backend_vars.AI_AUGMENT_STANDARDIZED_COLUMNS:
                assert data[column].startswith(
                    f"{codex_parse.AI_GENERATED_TEXT_PREFIX} "
                )
            assert (
                api.selected_card_outer_dict(singular_outerdict).get_inner_by_key(
                    singular_outerdict.namekey.to_json_key()
                )[len(singular_outerdict.xlsx_innerdicts)]
                is innerdict.innerdict
            )
            run_outcome_json = store._execute(
                f"SELECT {CODEX_RUN_OUTCOME_SERIALIZED_JSON_COL} "
                f"FROM {CODEX_RUN_OUTCOME_RECORDS_TABLE} "
                f"WHERE {CODEX_RUN_OUTCOME_RECORD_ID_COL} = ?",
                [str(innerdict.run_outcome_response_record.record_id)],
            ).fetchone()
            assert run_outcome_json is not None
            assert _RunOutcomeResponseRecordJson.model_validate_json(
                run_outcome_json[0]
            ).to_run_outcome_response_record() == innerdict.run_outcome_response_record
            assert "run_outcome_response_record" not in data
            assert (
                innerdict.run_outcome_response_record.model_dump_json()
                == outcome.model_dump_json()
            )
            assert outcome.response_headers is not None
            filename, fragment = AiAugmentBackendStore._parse_source_key_header(
                outcome.response_headers[SOURCE_KEY_HEADER]
            )
            assert data[KTP_FILENAME_COL] == filename
            assert data[KTP_FRAGMENT_COL] == fragment
            assert data[KTP_FRAGMENT_TYPE_COL] == api.ROLLOUT_LINE_FRAGMENT_TYPE
            assert data[KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL] == outcome.response_body
            assert set(data) == {
                column for column, _data_type in api.CODEX_OUTPUT_SCHEMA
            }
        snapshot = query.model_dump_json()
        assert DashboardQuerySnapshot.from_serialized_json(snapshot).model_dump_json() == snapshot
    log_bytes = Path(store._replay_log).read_bytes()
    live_database = fixtures.logical_database_snapshot(store._detour_db_path)
    replay = AiAugmentBackendStore._from_resources(
        replay_log=store._replay_log,
        detour_db=store._detour_db.model_copy(
            update={
                "path": store._detour_db_path.with_name("outcome-replay.duckdb"),
            }
        ),
        rollout_cas=store.rollout_cas,
    )
    rebuild_for_test(replay, runtime)
    with replay._read_only(runtime):
        assert query_snapshot(replay).model_dump_json() == snapshot
    assert fixtures.logical_database_snapshot(replay._detour_db_path) == live_database
    assert Path(store._replay_log).read_bytes() == log_bytes


@pytest.mark.parametrize("case", ("unvalidated", "rejected", "no_session", "other_session"))
def test_outcome_without_matching_accepted_data_keeps_history_only(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    case: str,
) -> None:
    store = backend_store
    payload = valid_submission_body()
    if case == "unvalidated":
        with pytest.raises(RuntimeError, match="Backend Store failed"), store._writable(runtime):
            commit_id = commit(store, payload, payload)
            typed_commit = store._backend_commit_request_record(store._http_record(commit_id))
            with pytest.raises(ValueError, match="precedes validation"):
                store._append_authoritative_record(
                    outcome_for_commit(store, typed_commit, partial=True)
                )
        with duckdb.connect(str(store._detour_db_path), read_only=True) as connection:
            assert connection.execute(
                f"SELECT count(*) FROM {backend_vars.AUTHORITATIVE_RECORDS_TABLE}"
            ).fetchone() == (3,)
        return
    with store._writable(runtime):
        commit_id = commit(store, {} if case == "rejected" else payload, payload)
        typed_commit = store._backend_commit_request_record(store._http_record(commit_id))
        if case != "unvalidated":
            result = store._validate_commit(commit_id)
            assert result.validation_request_body.post_commit_validation.result is (
                BackendLifecycle.REJECTED if case == "rejected" else BackendLifecycle.ACCEPTED
            )
        outcome = outcome_for_commit(
            store, typed_commit, partial=True, no_session=case == "no_session",
            other_session=case == "other_session",
        )
        store._append_authoritative_record(outcome)
        query = query_snapshot(store)
        assert (
            type(query).from_serialized_json(query.model_dump_json()).model_dump_json()
            == query.model_dump_json()
        )
        assert not query.ai_augment_singular_outerdicts[0].codex_innerdicts
        assert store._http_record(outcome.record_id).model_dump() == (
            outcome.http_request_log_record.model_dump()
        )


def test_outcome_finalizes_only_linked_commit_once(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
) -> None:
    store = backend_store
    payload = valid_submission_body()
    with store._writable(runtime):
        first = store._validate_commit(commit(store, {}, payload))
        assert (
            first.validation_request_body.post_commit_validation.result
            is BackendLifecycle.REJECTED
        )
        assert (
            first.validation_request_body.post_commit_validation.stage
            is BackendLifecycle.PYDANTIC_VALIDATION
        )
        retry_pull = store._append_authoritative_record(persisted_http_record(
            record_id=uuid7(), method=HTTP_GET_METHOD, path=PULL_PATH,
            response_code=HTTPStatus.OK,
            response_headers={HTTP_CONTENT_TYPE_HEADER: ContentType.MARKDOWN_UTF8},
            response_body=(
                first.validation_request_body.post_commit_validation.detail
                or Locale.VALIDATION_ERROR_DETAIL
            ).rstrip() + "\n",
        ))
        assert isinstance(retry_pull, PullResponseRecord)
        assert retry_pull.validation_request_record is first

        result = store._validate_commit(commit(store, payload, payload, retry_pull))
        assert (
            result.validation_request_body.post_commit_validation.result
            is BackendLifecycle.ACCEPTED
        )
        outcome = outcome_for_commit(store, result.validation_request_body.commit_request_record)
        assert outcome.attempt is result
        assert outcome._body().commit_request_record_id == (
            result.validation_request_body.commit_request_record.record_id
        )
        assert outcome.response_code == HTTPStatus.OK
        store._append_authoritative_record(outcome)
        before = query_snapshot(store)
        assert len(before.ai_augment_singular_outerdicts[0].codex_innerdicts) == 1
        failed_outcome = outcome_for_commit(
            store,
            result.validation_request_body.commit_request_record,
            path=RunOutcomePath.FAILED,
        )
        assert failed_outcome.response_code == HTTPStatus.CONFLICT
        store._append_authoritative_record(failed_outcome)
        after = query_snapshot(store)
        assert (
            type(after).from_serialized_json(after.model_dump_json()).model_dump_json()
            == after.model_dump_json()
        )
        assert [
            item.serialize()
            for item in after.ai_augment_singular_outerdicts[0].codex_innerdicts
        ] == [
            item.serialize()
            for item in before.ai_augment_singular_outerdicts[0].codex_innerdicts
        ]


def test_validation_after_session_outcome_fails_without_materialization(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
) -> None:
    store = backend_store
    payload = valid_submission_body()
    with pytest.raises(RuntimeError, match="Backend Store failed"), store._writable(runtime):
        commit_id = commit(store, payload, payload)
        result = store._validate_commit(commit_id)
        store._append_authoritative_record(outcome_for_commit(
            store, result.validation_request_body.commit_request_record,
        ))
        later_id = commit(store, payload, payload)
        with pytest.raises(ReplayInputMissing, match="Validation must precede"):
            store._validate_commit(later_id)
    with duckdb.connect(str(store._detour_db_path), read_only=True) as connection:
        assert connection.execute(
            f"SELECT count(*) FROM {api.CODEX_INNERDICT_TABLE}"
        ).fetchone() == (1,)


def test_durable_validation_allows_410_before_outcome_and_ipc_waits_for_http_send(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
    threaded_loop: asyncio.Runner,
) -> None:
    store = backend_store
    monkeypatch.setattr(api, "BACKEND_LIFECYCLE", BackendLifecycle.READY)
    monkeypatch.setattr(api, "AUTHORITATIVE_BACKGROUND_TASKS", set())
    payload = valid_submission_body()
    with store._writable(runtime):
        commit_id = commit(store, payload, payload)
        result = store._validate_commit(commit_id)
        assert result is not None
        assert str(result.record_id).encode() in (
            Path(store._replay_log).read_bytes()
        )
        api.update_pull_state(result)
        assert api.BACKEND_LIFECYCLE is BackendLifecycle.COMPLETED
        interim = query_snapshot(store)
        assert not interim.ai_augment_singular_outerdicts[0].codex_innerdicts
        outcome = outcome_for_commit(store, result.validation_request_body.commit_request_record)

        async def exercise() -> None:
            app = FastAPI()
            gate = server._BackendRequestGate()
            app.state.request_gate = gate

            app.state.store = store
            app.get("/pull")(server.pull)

            app.add_middleware(server._BackendRequestMiddleware)
            sending = asyncio.Event()
            finish_send = asyncio.Event()
            outcomes: list[HttpRequestLogRecord] = []
            messages: list[Message] = []

            async def receive() -> Message:
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message: Message) -> None:
                messages.append(message)
                if message["type"] == "http.response.body":
                    sending.set()
                    await finish_send.wait()

            scope: Scope = {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": "GET", "scheme": "http", "path": "/pull", "raw_path": b"/pull",
                "query_string": b"", "headers": [(b"host", b"invalid")],
                "client": ("127.0.0.1", 1), "server": ("invalid", 80),
            }
            http = asyncio.create_task(app(scope, receive, send))
            await sending.wait()
            assert messages[0]["status"] == 410

            async def ipc_outcome() -> None:
                async with gate.ipc():
                    outcomes.append(store._append_authoritative_record(outcome))

            ipc_task = asyncio.create_task(ipc_outcome())
            await asyncio.sleep(0)
            assert not outcomes
            finish_send.set()
            await asyncio.gather(http, ipc_task)
            assert len(outcomes) == 1

        threaded_loop.run(asyncio.wait_for(exercise(), timeout=10))
        records = [
            record for record, _ in AiAugmentBackendStore._authoritative_log_records(
                Path(store._replay_log).read_bytes()
            )
        ]
        gone, = (
            record for record in records if record.path == "/pull" and record.response_code == 410
        )
        ids = [record.record_id for record in records]
        assert (
            ids.index(result.record_id)
            < ids.index(gone.record_id) < ids.index(outcome.record_id)
        )
        query = query_snapshot(store)
        assert len(query.ai_augment_singular_outerdicts[0].codex_innerdicts) == 1
        assert (
            type(query).from_serialized_json(query.model_dump_json()).model_dump_json()
            == query.model_dump_json()
        )


def test_initial_validation_is_lifecycle_scoped_and_replays_explicit_links(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
) -> None:
    payload = valid_submission_body()
    roots: list[UUID] = []
    snapshots: list[str] = []
    last_validation: BackendValidationRequestRecord | None = None
    for index, store in enumerate((backend_store, backend_store_for_test(runtime))):
        session_id = UUID(OPERATOR_CAPTURED_SESSION_ID) if index == 0 else uuid7()
        assert store.current_replayed_record is None
        with store._writable(runtime):
            first = store._validate_commit(commit(store, {}, payload, session_id=session_id))
            assert (
                first.validation_request_body.post_commit_validation.result
                is BackendLifecycle.REJECTED
            )
            assert (
                first.validation_request_body.post_commit_validation.stage
                is BackendLifecycle.PYDANTIC_VALIDATION
            )
            initial = store.current_replayed_record
            assert isinstance(initial, BackendValidationRequestRecord)
            assert first is not None
            assert initial.model_dump_json() == first.model_dump_json()
            assert initial.validation_request_body.initial_validation_request_record is None
            roots.append(initial.record_id)
            retry_pull = store._append_authoritative_record(persisted_http_record(
                record_id=uuid7(), method="GET", path="/pull", response_code=200,
            ))
            assert isinstance(retry_pull, PullResponseRecord)
            assert retry_pull.validation_request_record is initial
            second = store._validate_commit(commit(
                store, payload, payload, retry_pull, session_id=session_id,
            ))
            assert (
                second.validation_request_body.post_commit_validation.result
                is BackendLifecycle.ACCEPTED
            )
            last_validation = store.current_replayed_record
            assert isinstance(last_validation, BackendValidationRequestRecord)
            assert second is not None
            assert last_validation.model_dump_json() == second.model_dump_json()
            assert last_validation.record_id != initial.record_id
            assert (
                last_validation.validation_request_body.initial_validation_request_record
                is initial
            )
            snapshots.append(query_snapshot(store).model_dump_json())
            if index == 0:
                terminal_path = (
                    RunOutcomePath.COMPLETED
                    if (
                        second.validation_request_body.post_commit_validation.result
                        is BackendLifecycle.ACCEPTED
                    )
                    else RunOutcomePath.FAILED
                )
                terminal = outcome_for_commit(
                    store, second.validation_request_body.commit_request_record, path=terminal_path,
                )
                assert terminal.response_code == HTTPStatus.OK
                store._append_authoritative_record(terminal)
    assert roots[0] != roots[1]
    before = Path(runtime.pipeline_config.replay_log).read_bytes()
    replay = backend_store_for_test(runtime)
    rebuild_for_test(replay, runtime)
    replayed = replay.current_replayed_record
    assert isinstance(replayed, BackendValidationRequestRecord)
    assert replayed.validation_request_body.initial_validation_request_record is not None
    assert replayed.validation_request_body.initial_validation_request_record.record_id == roots[-1]
    assert replayed == last_validation
    with replay._read_only(runtime):
        assert query_snapshot(replay).model_dump_json() == snapshots[-1]
    assert Path(runtime.pipeline_config.replay_log).read_bytes() == before


@pytest.mark.parametrize("has_initial", (False, True))
def test_failed_validation_projection_does_not_advance_store_validation_state(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    monkeypatch: pytest.MonkeyPatch,
    has_initial: bool,
) -> None:
    store = backend_store
    payload = valid_submission_body()
    real_insert = AiAugmentBackendStore._insert_validation_request_record_id

    def fail_after_insert(
        subject: AiAugmentBackendStore, record: BackendValidationRequestRecord,
    ) -> None:
        real_insert(subject, record)
        raise RuntimeError("injected projection failure")

    with pytest.raises(RuntimeError, match="Store failed"), store._writable(runtime):
        retry_pull = None
        if has_initial:
            store._validate_commit(commit(store, {}, payload))
            initial = store.current_replayed_record
            assert isinstance(initial, BackendValidationRequestRecord)
            assert (
                initial.validation_request_body.post_commit_validation.result
                is BackendLifecycle.REJECTED
            )
            assert (
                initial.validation_request_body.post_commit_validation.stage
                is BackendLifecycle.PYDANTIC_VALIDATION
            )
            retry_pull = store._append_authoritative_record(persisted_http_record(
                record_id=uuid7(), method="GET", path="/pull", response_code=200,
            ))
            assert isinstance(retry_pull, PullResponseRecord)
            assert retry_pull.validation_request_record is initial
        commit_id = commit(store, payload, payload, retry_pull)
        current_commit = store.current_replayed_record
        assert isinstance(current_commit, BackendCommitRequestRecord)
        with monkeypatch.context() as patch:
            patch.setattr(
                AiAugmentBackendStore, "_insert_validation_request_record_id", fail_after_insert,
            )
            with pytest.raises(RuntimeError, match="injected projection failure"):
                store._validate_commit(commit_id)
        last_line = Path(runtime.pipeline_config.replay_log).read_bytes().splitlines()[-1]
        durable = HttpRequestLogRecord.model_validate_json(last_line)
        assert durable.request_body is not None
        serialized = json.loads(durable.request_body)
        assert UUID(serialized["commit_request_record_id"]) == commit_id
        assert store.current_replayed_record is current_commit
    assert store.current_replayed_record is current_commit
    with duckdb.connect(str(store._detour_db_path), read_only=True) as connection:
        assert connection.execute(
            f"SELECT count(*) FROM {backend_vars.AUTHORITATIVE_RECORDS_TABLE} "
            "WHERE path = '/validate'",
        ).fetchone() == (int(has_initial),)


@pytest.mark.parametrize(("changed_input", "error_type"), (
    ("initial", ValueError), ("commit", ValueError), ("provider", RuntimeError),
))
def test_validation_rejects_altered_embedded_inputs_after_durable_capture(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    changed_input: str,
    error_type: type[Exception],
) -> None:
    store = backend_store
    payload = valid_submission_body()
    with pytest.raises(RuntimeError, match="Store failed"), store._writable(runtime):
        store._validate_commit(commit(store, payload, payload))
        initial = store.current_replayed_record
        assert isinstance(initial, BackendValidationRequestRecord)
        provider = store._append_authoritative_record(persisted_http_record(
            record_id=uuid7(), method="GET", path="/institutions/I1", response_code=200,
        ).model_copy(update={"host": "api.openalex.org", "response_body": "{}"}))
        retry_pull = store._append_authoritative_record(persisted_http_record(
            record_id=uuid7(), method="GET", path="/pull", response_code=200,
        ))
        assert isinstance(retry_pull, PullResponseRecord)
        assert retry_pull.validation_request_record is initial
        commit_id = commit(store, payload, payload, retry_pull)
        current_commit = store.current_replayed_record
        assert isinstance(current_commit, BackendCommitRequestRecord)
        assert current_commit.record_id == commit_id
        candidate = ValidationRequestBody(
            commit_request_record=current_commit,
            post_commit_validation=initial.validation_request_body.post_commit_validation,
            initial_validation_request_record=initial,
            openalex_ror_records=(provider,) if changed_input == "provider" else (),
        ).http_record()
        body = json.loads(candidate.request_body or "")
        if changed_input == "initial":
            body["initial_validation_request_record_id"] = str(uuid7())
        elif changed_input == "commit":
            body["commit_request_record_id"] = str(uuid7())
        else:
            body["openalex_ror_records_ids"][0] = str(uuid7())
        captured = candidate.model_copy(update={"request_body": json.dumps(body)})
        with pytest.raises(
            error_type, match="(Initial validation|Validation commit|private commit references)",
        ):
            store._append_authoritative_record(captured)
        last_line = Path(runtime.pipeline_config.replay_log).read_bytes().splitlines()[-1]
        assert (
            HttpRequestLogRecord.model_validate_json(last_line).request_body
            == captured.request_body
        )
        assert store.current_replayed_record is current_commit
    assert store.current_replayed_record is current_commit
    with duckdb.connect(str(store._detour_db_path), read_only=True) as connection:
        assert connection.execute(
            f"SELECT count(*) FROM {backend_vars.AUTHORITATIVE_RECORDS_TABLE} "
            "WHERE path = '/validate'",
        ).fetchone() == (1,)
