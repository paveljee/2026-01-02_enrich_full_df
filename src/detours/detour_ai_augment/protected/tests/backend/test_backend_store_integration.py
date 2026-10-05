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
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.replay_log import (  # noqa: E501
    READ_ONLY_PERMISSIONS,
    READ_WRITE_PERMISSIONS,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AUTHORITATIVE_RECORDS_TABLE,
    EXCLUDED_NAMEKEY,
    HTTP_GET_METHOD,
    HTTP_POST_METHOD,
    NAME_KEY_HEADER,
    PULL_PATH,
    PUSH_PATH,
    REPLAY_LOG_KEY,
    TEXT_ENCODING,
    AiAugmentCohort,
    AiAugmentIneligibilityCategory,
)
from src.detours.detour_ai_augment.protected.tests.fixtures.pytest_fixtures import (
    STARTUP_NAMEKEY,
    StartupFiles,
    init_request_record,
)
from src.detours.detour_ai_augment.src.backend import server
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_backend_store import (  # noqa: E501
    AiAugmentBackendStore,
    _ReplayCommitInvalidError,
    initialize_backend_store,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (  # noqa: E501
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_http_request_log_record import (  # noqa: E501
    ResponseRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_request import (
    COMMIT_PATH,
    BackendCommitRequestRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.init_request import (
    BackendInitRequestRecord,
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
from src.detours.detour_ai_augment.src.backend.helpers.data_models.push_event import (
    PushResponseRecord,
)
from src.detours.detour_ai_augment.src.shared import name_key_header_value
from src.detours.detour_ai_augment.tests.backend import test_http_interceptor as store_tests
from src.detours.detour_ai_augment.tests.backend.test_api import (
    TEST_NAMEKEY_MODEL,
    persisted_http_record,
    valid_submission_body,
)
from src.helpers.data_models import NameKey
from src.helpers.data_models.http_request_log import HttpRequestLogRecord
from src.helpers.vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL

backend_test_paths = store_tests.backend_test_paths
runtime = store_tests.runtime
backend_store = store_tests.backend_store
commit = store_tests.commit


@pytest.mark.python_subprocess
@pytest.mark.parametrize("mode", ("new", "resume", "continue"))
@pytest.mark.parametrize("startup_namekey, expected_detail", (
    pytest.param(
        NameKey(first_name="Absent", last_name="Startup"),
        Locale.CONFIGURED_NAMEKEY_NOT_FOUND,
        id="unknown",
    ),
    pytest.param(
        NameKey(
            first_name=STARTUP_NAMEKEY.first_name + " ",
            last_name=STARTUP_NAMEKEY.last_name,
        ),
        Locale.CONFIGURED_NAMEKEY_NOT_FOUND_SUGGESTIONS_TEMPLATE.format(
            suggestions=STARTUP_NAMEKEY.to_json_key(),
        ),
        id="suggestion",
    ),
    pytest.param(
        NameKey.from_json_key(EXCLUDED_NAMEKEY),
        Locale.CONFIGURED_NAMEKEY_INELIGIBLE_TEMPLATE.format(
            category=AiAugmentIneligibilityCategory.EXCLUDED_DUPLICATE_NAMEKEY.value,
        ),
        id="ineligible",
    ),
))
def test_invalid_launch_namekey_is_rejected_before_replay(
    startup_files: StartupFiles,
    pytestconfig: pytest.Config,
    mode: str,
    startup_namekey: NameKey,
    expected_detail: str,
) -> None:
    """Reject a launch selection before replay; preserve exact NameKey suggestions.

    Previously --new rebuilt the DB before rejecting an unknown or ineligible
    NameKey. Exercise the production CLI and Store startup with isolated faithful
    files, including a whitespace mismatch that must suggest the canonical key.
    """
    files = startup_files
    before = {
        path: hashlib.sha256(path.read_bytes()).digest()
        for path in (files.source, files.replay, files.detour)
    }
    result = subprocess.run(
        [
            sys.executable, "-m", server.__name__,
            server.CONFIG_OPTION, str(files.config), f"--{mode}", "--yes",
        ],
        cwd=pytestconfig.rootpath,
        env=files.environment(startup_namekey.to_json_key()),
        input="",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    details = result.stdout + result.stderr
    assert result.returncode != 0, details
    assert expected_detail in details
    assert (
        Locale.BACKEND_HTTP_STARTING_LOG % (backend_api.SERVER_HOST, backend_api.SERVER_PORT)
    ) not in details
    for path, digest in before.items():
        assert hashlib.sha256(path.read_bytes()).digest() == digest, path

    context = server.configure_runtime(files.config)
    with (
        pytest.raises(ValueError) as rejected,
        initialize_backend_store(
            context, ipc_only=False,
            init_request_record=init_request_record(startup_namekey),
            new=mode == "new", confirmed=True, confirm_replay=lambda: True,
        ),
    ):
        pass
    assert str(rejected.value) == expected_detail
    for path, digest in before.items():
        assert hashlib.sha256(path.read_bytes()).digest() == digest, path


def test_replay_rejects_commit_namekey_mismatched_with_init(
    startup_files: StartupFiles,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reproduce the operator's altered-init replay failure at commit.

    Keep the faithful pull/push/commit history and change only the latest
    init's NameKey. End the log at commit so later validation cannot
    conceal a missing commit-stage check.
    """
    files = startup_files
    context = server.configure_runtime(files.config)
    requested_init = init_request_record(STARTUP_NAMEKEY)
    payload = valid_submission_body()

    with initialize_backend_store(
        context,
        ipc_only=False,
        init_request_record=requested_init,
        new=False,
        confirmed=True,
        confirm_replay=lambda: False,
    ) as store:
        commit_request_record_id = commit(
            store, payload, payload, namekey=STARTUP_NAMEKEY,
        )
        assert isinstance(store.current_replayed_record, BackendCommitRequestRecord)
        assert store.current_replayed_record.record_id == commit_request_record_id

    lines = files.replay.read_bytes().splitlines(keepends=True)
    records = tuple(HttpRequestLogRecord.model_validate_json(line) for line in lines)
    assert records[-1].path == COMMIT_PATH
    assert records[-1].record_id == commit_request_record_id

    wrong_namekey = next(
        blueprint.namekey
        for blueprint in context.ai_augment_singular_outerdict_blueprints
        if blueprint.namekey != STARTUP_NAMEKEY
        and blueprint.ai_augment_cohort is not AiAugmentCohort.INELIGIBLE
    )
    init_line_index = next(
        index for index, record in enumerate(records)
        if record.record_id == requested_init.record_id
    )
    serialized_init = requested_init.serialize()
    serialized_init["request_headers"] = {
        NAME_KEY_HEADER: name_key_header_value(wrong_namekey),
    }
    changed_init = BackendInitRequestRecord.from_serialized_json(
        value=json.dumps(serialized_init),
    )
    assert changed_init.record_id == requested_init.record_id
    assert changed_init.namekey == wrong_namekey
    lines[init_line_index] = (
        json.dumps(changed_init.serialize(), ensure_ascii=True) + "\n"
    ).encode(TEXT_ENCODING)

    files.replay.chmod(READ_WRITE_PERMISSIONS)
    try:
        files.replay.write_bytes(b"".join(lines))
    finally:
        files.replay.chmod(READ_ONLY_PERMISSIONS)
    files.repin()
    context = server.configure_runtime(files.config)

    with (
        pytest.raises(
            _ReplayCommitInvalidError,
            match=Locale.REPLAY_COMMIT_NAME_KEY_INVALID,
        ),
        initialize_backend_store(
            context,
            ipc_only=False,
            init_request_record=init_request_record(wrong_namekey),
            new=True,
            confirmed=True,
            confirm_replay=lambda: True,
        ),
    ):
        pass

    assert Locale.REPLAY_RECORD_FAILED_LOG % len(lines) in caplog.text
    with duckdb.connect(str(files.detour), read_only=True) as connection:
        assert connection.execute(
            f"SELECT count(*) FROM {AUTHORITATIVE_RECORDS_TABLE}"
        ).fetchone() == (len(records) - 1,)


def test_second_same_session_acceptance_fails_loudly(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
) -> None:
    """A second Backend launch cannot accept duplicate session metadata."""
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
        backend_store._append_authoritative_record(init_request_record(TEST_NAMEKEY_MODEL))
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
    context = server.configure_runtime(startup_files.config)
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
            context, ipc_only=False, init_request_record=init_request_record(STARTUP_NAMEKEY),
            new=False, confirmed=True,
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
    log_lines = log_bytes.splitlines(keepends=True)
    assert log_bytes.endswith(b"\n") and len(log_lines) == 3
    assert HttpRequestLogRecord.model_validate_json(log_lines[-1]).record_id == record.record_id
    with duckdb.connect(str(db_path), read_only=True) as connection:
        projected = connection.execute(
            f"SELECT record_ordinal, record_id, raw_line_sha256 "
            f"FROM {AUTHORITATIVE_RECORDS_TABLE} WHERE record_id = ?",
            [str(record.record_id)],
        ).fetchone()
        anchor_row = connection.execute(
            "SELECT comment FROM duckdb_tables() WHERE table_name = ?",
            [AUTHORITATIVE_RECORDS_TABLE],
        ).fetchone()
    assert projected == (3, str(record.record_id), hashlib.sha256(log_lines[-1]).hexdigest())
    assert anchor_row is not None
    assert json.loads(anchor_row[0]) == {
        "sha256": hashlib.sha256(log_lines[0]).hexdigest(),
        "ordinal": 1,
        "byte_offset": len(log_lines[0]),
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
        startup_files.config, verify_hash_on_init=False,
    )
    with initialize_backend_store(
        resumed_context, ipc_only=False,
        init_request_record=init_request_record(STARTUP_NAMEKEY),
        new=False, confirmed=True,
        confirm_replay=lambda: False,  # for mypy
    ) as resumed:
        assert resumed._append_ordinal == 4
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
        ).fetchone() == (5,)

    # An operator can also repin only this temporary config and use the normal
    # hash-verifying startup; it still does not detect the old postcommit failure.
    startup_files.repin()
    verified_context = server.configure_runtime(startup_files.config)
    with initialize_backend_store(
        verified_context, ipc_only=False,
        init_request_record=init_request_record(STARTUP_NAMEKEY),
        new=False, confirmed=True,
        confirm_replay=lambda: False,
    ) as verified_resume:
        assert verified_resume._append_ordinal == 6


@pytest.mark.parametrize(
    "second_namekey",
    (STARTUP_NAMEKEY, NameKey(first_name="Case 001", last_name="Startup")),
    ids=("same-namekey", "different-namekey"),
)
def test_replay_keeps_backend_launch_boundaries(
    startup_files: StartupFiles,
    second_namekey: NameKey,
) -> None:
    """An interrupted Backend launch cannot lend its pull to the next launch."""
    context = server.configure_runtime(startup_files.config)
    with initialize_backend_store(
        context, ipc_only=False,
        init_request_record=init_request_record(STARTUP_NAMEKEY),
        new=False, confirmed=True, confirm_replay=lambda: False,
    ) as first:
        first_pull = first._append_authoritative_record(persisted_http_record(
            record_id=uuid7(), method=HTTP_GET_METHOD, path=PULL_PATH,
            response_code=HTTPStatus.OK,
            response_body=backend_api.json_line({
                KTP_FIRST_NAME_COL: STARTUP_NAMEKEY.first_name,
                KTP_LAST_NAME_COL: STARTUP_NAMEKEY.last_name,
            }),
        ))
        assert isinstance(first_pull, PullResponseRecord)
        assert first_pull.validation_request_record is None

    startup_files.repin()
    context = server.configure_runtime(startup_files.config)
    with initialize_backend_store(
        context, ipc_only=False,
        init_request_record=init_request_record(second_namekey),
        new=True, confirmed=True, confirm_replay=lambda: True,
    ) as second:
        replayed_init = second._init_request_record
        assert replayed_init is not None
        assert replayed_init is second.current_replayed_record
        assert replayed_init.namekey == second_namekey
        rejected = second._append_authoritative_record(persisted_http_record(
            record_id=uuid7(), method=HTTP_POST_METHOD, path=PUSH_PATH,
            response_code=HTTPStatus.CONFLICT,
        ))
        assert isinstance(rejected, PushResponseRecord)
        assert rejected.pull_response_record is None
        assert second.current_replayed_record is second._init_request_record
        second_pull = second._append_authoritative_record(persisted_http_record(
            record_id=uuid7(), method=HTTP_GET_METHOD, path=PULL_PATH,
            response_code=HTTPStatus.OK,
        ))
        assert isinstance(second_pull, PullResponseRecord)
        assert second_pull.validation_request_record is None
        rejected_with_pull = second._append_authoritative_record(persisted_http_record(
            record_id=uuid7(), method=HTTP_POST_METHOD, path=PUSH_PATH,
            response_code=HTTPStatus.CONFLICT,
        ))
        assert isinstance(rejected_with_pull, PushResponseRecord)
        assert rejected_with_pull.pull_response_record is None
        assert second._current_replayed_record is second_pull
        accepted = second._append_authoritative_record(persisted_http_record(
            record_id=uuid7(), method=HTTP_POST_METHOD, path=PUSH_PATH,
            response_code=HTTPStatus.ACCEPTED,
        ))
        assert isinstance(accepted, PushResponseRecord)
        assert accepted.pull_response_record is second_pull

    startup_files.repin()
    second._replay_log = second._replay_log.model_copy(update={
        "hash": hashlib.sha256(startup_files.replay.read_bytes()).hexdigest(),
    })
    second._rebuild_from_log(context, reset_confirmed=True, confirm_replay=lambda: True)
    replayed = second.current_replayed_record
    assert isinstance(replayed, PushResponseRecord)
    assert replayed.record_id == accepted.record_id
    assert replayed.pull_response_record is not None
    assert replayed.pull_response_record.record_id == second_pull.record_id
    assert replayed.pull_response_record.record_id != first_pull.record_id
    assert replayed.pull_response_record.validation_request_record is None


def test_historical_validation_replays_under_its_backend_launch_namekey(
    startup_files: StartupFiles,
) -> None:
    """A later Backend launch cannot change an earlier validation's researcher."""
    context = server.configure_runtime(startup_files.config)
    with initialize_backend_store(
        context, ipc_only=False,
        init_request_record=init_request_record(STARTUP_NAMEKEY),
        new=False, confirmed=True, confirm_replay=lambda: False,
    ) as first:
        first_pull = first._append_authoritative_record(persisted_http_record(
            record_id=uuid7(), method=HTTP_GET_METHOD, path=PULL_PATH,
            response_code=HTTPStatus.OK,
            response_body=backend_api.json_line({
                KTP_FIRST_NAME_COL: STARTUP_NAMEKEY.first_name,
                KTP_LAST_NAME_COL: STARTUP_NAMEKEY.last_name,
            }),
        ))
        assert isinstance(first_pull, PullResponseRecord)
        commit_id = commit(
            first, {}, valid_submission_body(), first_pull,
            namekey=STARTUP_NAMEKEY,
        )
        validation = first._validate_commit(commit_id)
        assert validation.validation_request_body.commit_request_record.record_id == commit_id

    startup_files.repin()
    context = server.configure_runtime(startup_files.config)
    later_namekey = NameKey(first_name="Case 001", last_name="Startup")
    with initialize_backend_store(
        context, ipc_only=False,
        init_request_record=init_request_record(later_namekey),
        new=True, confirmed=True, confirm_replay=lambda: True,
    ) as second:
        replayed_init = second._init_request_record
        assert replayed_init is not None
        assert replayed_init is second.current_replayed_record
        assert replayed_init.namekey == later_namekey
        assert second._http_record(validation.record_id).model_dump(mode="json") == (
            validation.http_request_log_record.model_dump(mode="json")
        )
