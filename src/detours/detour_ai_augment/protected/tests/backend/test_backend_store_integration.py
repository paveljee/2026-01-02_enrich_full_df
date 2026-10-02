from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from http import HTTPStatus
from uuid import uuid7

import duckdb
import pytest

from src.detours.detour_ai_augment.protected.src.backend import api as backend_api
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AUTHORITATIVE_RECORDS_TABLE,
    HTTP_GET_METHOD,
    PULL_PATH,
    REPLAY_LOG_KEY,
)
from src.detours.detour_ai_augment.protected.tests.fixtures.pytest_fixtures import (
    StartupFiles,
)
from src.detours.detour_ai_augment.src.backend import server
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_backend_store import (  # noqa: E501
    AiAugmentBackendStore,
    initialize_backend_store,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (  # noqa: E501
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_http_request_log_record import (  # noqa: E501
    ResponseRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.lifecycle import (
    BackendLifecycle,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.model_http_interceptor import (  # noqa: E501
    ReplayInputMissing,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.pull_event import (
    PullResponseRecord,
)
from src.detours.detour_ai_augment.tests.backend import test_http_interceptor as store_tests
from src.detours.detour_ai_augment.tests.backend.test_api import (
    persisted_http_record,
    valid_submission_body,
)
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

backend_test_paths = store_tests.backend_test_paths
runtime = store_tests.runtime
backend_store = store_tests.backend_store
commit = store_tests.commit


def test_second_same_session_acceptance_fails_loudly(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
) -> None:
    """Synthetic second same-session acceptance bypasses the API lifecycle and collides with unique session metadata before outcome-link assertions"""  # noqa: E501
    payload = valid_submission_body()
    with pytest.raises(RuntimeError, match="Backend Store failed"), (
        backend_store._writable(runtime)
    ):
        first = backend_store._validate_commit(
            commit(backend_store, payload, payload)
        )
        assert (
            first.validation_request_body.post_commit_validation.result
            is BackendLifecycle.ACCEPTED
        )
        second_commit_id = commit(
            backend_store, payload, payload,
            rollout_suffix=(
                b'{"type":"event_msg","timestamp":"2026-09-03T15:17:00Z",'
                b'"payload":{"type":"task_complete"}}\n'
            ),
        )
        with pytest.raises(
            ReplayInputMissing, match=Locale.ACCEPTED_IDENTITY_DUPLICATE
        ):
            backend_store._validate_commit(second_commit_id)


def test_resume_after_committed_row_and_postcommit_failure(
    startup_files: StartupFiles,
    pytestconfig: pytest.Config,
) -> None:
    # The startup fixture builds a synthetic 307-person source, replay log,
    # registered release map, config, and detour DB entirely under tmp_path.
    context = server.configure_runtime(startup_files.config, require_namekey=False)
    # The existing typed record becomes a base HTTP record when read from the
    # log. Store notices that type mismatch only after its DB transaction commits.
    record = ResponseRecord.from_http_request_log_record(
        http_request_log_record=persisted_http_record(
            record_id=uuid7(), method=HTTP_GET_METHOD,
            path="/provider-capture", response_code=HTTPStatus.OK,
        ),
    )
    with pytest.raises(RuntimeError, match=Locale.STORE_FAILED_REBUILD_REQUIRED):
        with initialize_backend_store(
            context, ipc_only=False, new=False, confirmed=True,
            confirm_replay=lambda: False,
        ) as store:
            db_path = store._detour_db_path
            with pytest.raises(
                RuntimeError, match=Locale.STORE_RECONSTRUCTION_ORIGINAL_MISMATCH,
            ):
                store._append_authoritative_record(record)
            with pytest.raises(RuntimeError, match=Locale.STORE_FAILED_REBUILD_REQUIRED):
                store.ai_augment_singular_outerdicts()

    log_bytes = startup_files.replay.read_bytes()
    assert log_bytes.endswith(b"\n") and log_bytes.count(b"\n") == 1
    assert HttpRequestLogRecord.model_validate_json(log_bytes).record_id == record.record_id
    with duckdb.connect(str(db_path), read_only=True) as connection:
        projected = connection.execute(
            f"SELECT record_ordinal, record_id, raw_line_sha256 "
            f"FROM {AUTHORITATIVE_RECORDS_TABLE}"
        ).fetchone()
        anchor_row = connection.execute(
            "SELECT comment FROM duckdb_tables() WHERE table_name = ?",
            [AUTHORITATIVE_RECORDS_TABLE],
        ).fetchone()
    assert projected == (1, str(record.record_id), hashlib.sha256(log_bytes).hexdigest())
    assert anchor_row is not None
    assert json.loads(anchor_row[0]) == {
        "sha256": hashlib.sha256(b"").hexdigest(),
        "ordinal": 0,
        "byte_offset": 0,
    }

    # The real manual --resume CLI checks the pinned hash before opening Store.
    manual_resume = subprocess.run(
        [
            sys.executable, "-m", server.__name__, server.CONFIG_OPTION,
            str(startup_files.config), "--resume", "--yes",
        ],
        cwd=pytestconfig.rootpath,
        env=startup_files.environment(),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert manual_resume.returncode != 0
    assert Locale.CONFIG_INVALID_TEMPLATE.format(
        config_path=startup_files.config,
    ) in manual_resume.stderr
    assert REPLAY_LOG_KEY in manual_resume.stderr
    assert (
        startup_files.process_temp / backend_api.BACKEND_PROCESS_LOCK_PATH.name
    ).is_file()
    assert startup_files.replay.read_bytes() == log_bytes
    assert json.loads(startup_files.config.read_text())["files_config"][REPLAY_LOG_KEY][
        "sha256"
    ] != hashlib.sha256(log_bytes).hexdigest()

    # Dashboard children bypass the duplicated config hash check; Store still
    # verifies log/DB coverage on --resume, but does not replay the typed record.
    resumed_context = server.configure_runtime(
        startup_files.config, require_namekey=False, verify_hash_on_init=False,
    )
    with initialize_backend_store(
        resumed_context, ipc_only=False, new=False, confirmed=True,
        confirm_replay=lambda: False,  # for mypy
    ) as resumed:
        assert resumed._append_ordinal == 1
        assert resumed._http_record(record.record_id).model_dump(mode="json") == (
            record.model_dump(mode="json")
        )
        continued = resumed._append_authoritative_record(persisted_http_record(
            record_id=uuid7(), method=HTTP_GET_METHOD,
            path=PULL_PATH, response_code=HTTPStatus.OK,
        ))
        assert isinstance(continued, PullResponseRecord)
    with duckdb.connect(str(db_path), read_only=True) as connection:
        assert connection.execute(
            f"SELECT count(*) FROM {AUTHORITATIVE_RECORDS_TABLE}"
        ).fetchone() == (2,)

    # An operator can also repin only this temporary config and use the normal
    # hash-verifying startup; it still does not detect the old postcommit failure.
    startup_files.repin()
    verified_context = server.configure_runtime(startup_files.config, require_namekey=False)
    with initialize_backend_store(
        verified_context, ipc_only=False, new=False, confirmed=True,
        confirm_replay=lambda: False,
    ) as verified_resume:
        assert verified_resume._append_ordinal == 2
