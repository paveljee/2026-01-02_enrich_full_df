# AI augment production — current workbook (2026-10-05)

## Approved commit/init NameKey guard and serial socket exception

Operator approval: "your proposed init/commit guard is approved exactly as you
ptoposed in chat. put it to WORK excactly as shown before implementing. also show
the actual code for your proposed regresssion before i can approve it."

Insert exactly this block in `_apply_durable_record()`'s commit branch, after
existing pull/push by-reference checks and before `reconstructed = commit`:

```python
init_request_record = self._init_request_record
if (
    init_request_record is None
    or self._parse_name_key_header(commit.request_headers.get(NAME_KEY_HEADER))
    != init_request_record.namekey
):
    raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_NAME_KEY_INVALID)
```

Operator's subsequent approval, verbatim:

> ok approved this nullable change - exaxtlu as you proposed here in chat, type change. also approved your regression test above also exactly as presented in chat char for char inclusing docstring etc. put all od this to WORK verbatim and only then implement. and then continue your serial suite

Only the type-only declaration and regression below are additionally approved.
Record this approval before editing source, implement the existing exact code
blocks (including the regression docstring), run focused checks, then resume
the serial suite under the socket exception below.

Operator directs serial continuation: stop at any failure except socket
unavailability, record those exact test names and their count, and continue.
The previously failed `test_completed_grid_row_uses_real_query_ipc` is already
proven blocked by socket creation errno1 before Dashboard startup. Do not alter
or mock socket/browser tests to make them pass. Record both environment-failed
attempts and tests skipped at setup due to unavailable sockets, keeping them
separate from unrelated skips and from tests not reached at a non-socket failure.
One pytest/type/lint process at a time, low priority, actual repository only.


### Guard verification — runtime pass, type-only blocker

The guard is applied verbatim, with no other production changes. Ruff and
`git diff --check` pass. All 14 existing protected backend integration cases
pass in 94.02 seconds, including same-/different-NameKey Backend launch replay.
Reports: `logs/ai-augment-agent-checks/commit-init-guard-integration.{log,xml}`.

`mypy-detour-ai-augment` fails at Store:1398: the earlier init branch first assigns
`init_request_record` a non-optional BackendInitRequestRecord, so mypy rejects the
approved guard's later assignment of BackendInitRequestRecord | None to that
same function-scoped local. No runtime failure. Report:
`logs/ai-augment-agent-checks/commit-init-guard-mypy.log`.

**Approved type-only correction, implemented verbatim:** immediately before the
existing init branch's first assignment, declare the local's full type:

```python
init_request_record: BackendInitRequestRecord | None
init_request_record = BackendInitRequestRecord.from_http_request_log_record(
    http_request_log_record=record,
)
```

This adds one annotation line, leaves the approved guard and runtime logic
unchanged, and introduces no helper or field. Stop verification at this non-
socket failure as instructed; 147 remaining serial cases are selected but not
started. Existing socket-unavailability evidence covers exactly two distinct
cases: test_ipc.py::test_dashboard_client_queries_real_mode_0600_unix_socket
(setup skip), and test_ui_e2e.py::test_completed_grid_row_uses_real_query_ipc
(attempt failed creating AF_INET socket before Dashboard startup). Do not classify
unattempted browser cases as socket-blocked without evidence.

### Approved regression — exact presented shape, implemented verbatim

Add to `protected/tests/backend/test_backend_store_integration.py`. Additional
imports (merge names into existing import groups where applicable):

```python
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.replay_log import (  # noqa: E501
    READ_ONLY_PERMISSIONS,
    READ_WRITE_PERMISSIONS,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    NAME_KEY_HEADER,
    TEXT_ENCODING,
    AiAugmentCohort,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_backend_store import (  # noqa: E501
    _ReplayCommitInvalidError,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_request import (
    COMMIT_PATH,
    BackendCommitRequestRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.init_request import (
    BackendInitRequestRecord,
)
from src.detours.detour_ai_augment.src.shared import name_key_header_value
```

```python
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
```

Only the deliberately altered init JSON header differs; UUID and other fields
are preserved. Faithful history/DB/CAS remain wholly under startup_files' tmp_path.
Hash is repinned so unrelated resource verification cannot mask the guard failure.
No validation follows commit; regression proves the exact failing line and that
its DB transaction did not insert the mismatched commit. No mocks or new helper.

### Latest approval implemented and focused verification complete

Recorded the latest approval before editing. Added only the one nullable local
annotation and the approved regression/imports. The complete regression body,
including its docstring, matches the WORK block verbatim. No deviation or helper.
The faithful regression passes: 1/1 in 8.93 seconds. It rebuilds the deliberately
altered init history, rejects the commit at that line, and verifies that commit
was not inserted into the DB. Reports:
`logs/ai-augment-agent-checks/commit-init-regression.{log,xml}`.
Affected-file Ruff and `git diff --check` pass. Detour mypy passes all 65 files;
report `logs/ai-augment-agent-checks/commit-init-guard-mypy-rerun.log`.

The serial continuation is complete: 147 collected, **138 passed / 9 skipped**
in 63.26 seconds, no failures. Reports:
`logs/ai-augment-agent-checks/serial-after-socket.{log,xml}`. All nine skips are
socket-unavailability setup checks: seven browser tests plus two appendwatch
cases. Together with the earlier IPC setup skip and browser socket-creation
failure, **11 distinct tests are socket-blocked** (10 skipped, 1 failed before
Dashboard startup). No test source skip, mock, bypass, or unrelated fix added.

Fresh collection confirms **789 tests in the configured hermetic directories,
785 selected / 4 deselected**. Combining the serial runs and focused reruns by
exact node ID (not summing duplicate executions): **772 passed / 12 skipped /
1 environment-failed / 0 unreached**. The two non-socket skips are the optional
historical Haanen rollout fixtures being unavailable and the pre-existing skip
for currently allowed multiple evidence matches. Three needs_sudo tests and one
real_api test are marker-deselected as explicitly authorized. This is the
configured hermetic selection, not a full-repository or live-operator count.

| Verification | Passed | Skipped | Failed | Not reached |
|---|---:|---:|---:|---:|
| New approved commit/init regression | 1 | 0 | 0 | 0 |
| Latest 147-case serial continuation | 138 | 9 | 0 | 0 |
| Cumulative distinct selected cases | 772 | 12 | 1 (socket restriction) | 0 |

Per-test outcomes with run/line evidence:
`logs/ai-augment-agent-checks/serial-current-status.tsv`.
Exact socket-blocked names, reasons, and evidence:
`logs/ai-augment-agent-checks/socket-unavailable-tests.tsv` (11 tests).
All selected skips/environment failure plus the four deselections:
`logs/ai-augment-agent-checks/serial-not-completed-tests.tsv` (17 tests).
Horizontal module breakdown:
`logs/ai-augment-agent-checks/serial-module-outcomes.md`.
Collection evidence: `serial-final-collection.log` and
`serial-final-all-markers-collection.log` in the same directory.

All approved blocks match WORK verbatim, including the new regression docstring.
No outstanding observed code failure in this selection. Detour mypy65 and
changed-file Ruff pass. Available serial verification is complete; operator
verification of socket/browser, sudo, real-API and live-AIVM categories remains
outside this host's proven results. Do not claim a full pre-commit-operator pass
or guarantee production Dashboard startup from these host-limited runs.
Git remains read-only; no temporary source/suite copies introduced; no test/type/
lint process remains running.

## Approved operator-fixture and artifact-validator correction (2026-10-05)

Operator approval: "okay. approve your suggested six changes above, in *exact
shape i saw in chat**, plus your added assers in *exact shape proposed.* prior
to implementing put all this in the exact this shape into WORK".

The six approved changes and added closure assertions are recorded below exactly
as presented. This approval supersedes the earlier pending/unapproved status of
these two operator issues. All six shapes and the closure assertions are now
implemented; verification stopped at the first focused failure below.

**Four test files; no production code or hash-policy changes.**

### 1. Prepare the operator DB without creating a Backend launch

In `protected/tests/operator/test_operator_e2e.py::_operator_runtime`, replace the
full-startup block and subsequent replay-hash repinning with:

```python
_operator_log("preparing isolated Backend DB without a Backend launch")
context = backend_server.configure_runtime(config_path)
pipeline_config = context.pipeline_config
backend_store = AiAugmentBackendStore._from_resources(
    replay_log=pipeline_config.replay_log,
    detour_db=AiAugmentDetourDB.from_pipeline_db(
        pipeline_config.db_file,
        duckdb_extensions=pipeline_config.duckdb_extensions,
    ),
    rollout_cas=pipeline_config.rollout_cas,
)
backend_store._rebuild_from_log(context, reset_confirmed=True)
_operator_log("isolated Backend DB prepared; replay log remains empty")
```

The existing `return OperatorRuntime(...)` remains unchanged. Add the existing
`AiAugmentDetourDB` import. This uses Store's existing rebuild machinery. It does
not select a researcher, construct init, or invoke serving startup.

### 2. Artifact validation must open a fresh Store

Add `initialize_backend_store` to the existing Store import. Replace:

```python
with operator_runtime.backend_store._read_only(runtime) as backend_store:
```

with:

```python
with initialize_backend_store(runtime, ipc_only=True) as query_store:
    backend_store = query_store._engine
```

The following SQL and all validation assertions stay unchanged. The fresh Store
receives the replay resource from the validator's already-loaded current
configuration; it still performs normal DB/log verification.

### 3. Correct the bootstrap expectations

In `protected/tests/pytest_plugin.py::operator_fixture_bootstrap_process`:

```diff
- assert len(replay_before_query.splitlines()) == 1
+ assert replay_before_query == b""
```

Keep the existing assertions that query returns all researchers and leaves the
log unchanged. In `tests/control_centre/test_ui.py`, remove:

```python
assert BACKEND_STORE_CLOSED_CLEANLY in result.stdout
```

That acknowledgement came from the unwanted full launch. Keep subprocess
success, `OPERATOR_BOOTSTRAP_QUERY_OK`, and source-preservation checks.

### 4. Regression: preparation writes nothing; launch writes exactly its selected init

Add to `protected/tests/operator/test_operator_e2e_preflight.py`:

```python
def test_operator_preparation_does_not_create_a_backend_launch(
    startup_files: StartupFiles,
    tmp_path: Path,
) -> None:
    """DB preparation must not invent a launch for the first eligible NameKey."""
    repository = tmp_path / "operator-repository"
    repository.mkdir()
    (repository / "config_ai_augment.json").write_bytes(
        startup_files.config.read_bytes()
    )
    run_directory = tmp_path / "operator-runtime"
    run_directory.mkdir()
    operator_runtime = workflow._operator_runtime(
        run_directory,
        repository_root=repository,
        dashboard_socket_path=run_directory / "dashboard.sock",
    )

    assert operator_runtime.replay_log_path.read_bytes() == b""
    context = backend_server.configure_runtime(operator_runtime.config_path)
    with initialize_backend_store(context, ipc_only=True) as query_store:
        assert query_store._engine.current_replayed_record is None
        assert query_store._engine._execute(
            f"SELECT count(*) FROM {AUTHORITATIVE_RECORDS_TABLE}"
        ).fetchone() == (0,)

    eligible_blueprints = tuple(
        blueprint
        for blueprint in context.ai_augment_singular_outerdict_blueprints
        if blueprint.ai_augment_cohort is not AiAugmentCohort.INELIGIBLE
    )
    assert len(eligible_blueprints) >= 2
    selected_blueprint = eligible_blueprints[1]
    requested_init = init_request_record(selected_blueprint.namekey)

    with initialize_backend_store(
        context,
        ipc_only=False,
        init_request_record=requested_init,
        new=True,
        confirmed=True,
        confirm_replay=lambda: False,
    ) as backend_store:
        replayed_init = backend_store.current_replayed_record
        assert isinstance(replayed_init, BackendInitRequestRecord)
        assert replayed_init is backend_store._init_request_record
        assert replayed_init is not requested_init
        assert replayed_init.record_id == requested_init.record_id
        assert replayed_init.namekey == selected_blueprint.namekey
        assert (
            backend_store.selected_ai_augment_singular_outerdict()
            is selected_blueprint
        )
        assert backend_store._execute(
            f"SELECT count(*) FROM {AUTHORITATIVE_RECORDS_TABLE}"
        ).fetchone() == (1,)

    lines = operator_runtime.replay_log_path.read_bytes().splitlines()
    assert len(lines) == 1
    logged_init = BackendInitRequestRecord.from_serialized_json(
        value=lines[0].decode(workflow.TEXT_ENCODING),
    )
    assert logged_init.record_id == requested_init.record_id
    assert logged_init.namekey == selected_blueprint.namekey
```

Uses existing globals, models, and faithful `startup_files`; no mocks.

### 5. Regression: retained Store is stale, but artifact validation succeeds

Also add:

```python
def test_operator_artifact_validator_opens_a_fresh_store(
    completed_query_files: StartupFiles,
    tmp_path: Path,
) -> None:
    """A later rebuild must not make validation reuse obsolete replay metadata."""
    files = completed_query_files
    completed_context = backend_server.configure_runtime(files.config)

    repository = tmp_path / "validator-repository"
    repository.mkdir()
    (repository / "config_ai_augment.json").write_bytes(
        files.config.read_bytes()
    )
    run_directory = tmp_path / "validator-runtime"
    run_directory.mkdir()
    operator_runtime = workflow._operator_runtime(
        run_directory,
        repository_root=repository,
        dashboard_socket_path=run_directory / "dashboard.sock",
    )
    assert (
        operator_runtime.backend_store._replay_log.hash
        == workflow.EMPTY_FILE_SHA256
    )

    # Reuse faithfully produced completed history and its actual CAS bytes.
    operator_runtime.replay_log_path.write_bytes(files.replay.read_bytes())
    shutil.copytree(
        completed_context.pipeline_config.rollout_cas.path,
        operator_runtime.rollout_cas_dir,
        dirs_exist_ok=True,
    )
    config = json.loads(
        operator_runtime.config_path.read_text(encoding=workflow.TEXT_ENCODING)
    )
    config["files_config"][workflow.REPLAY_LOG_KEY][
        workflow.RESOURCE_SHA256_KEY
    ] = hashlib.sha256(operator_runtime.replay_log_path.read_bytes()).hexdigest()
    operator_runtime.config_path.write_text(
        json.dumps(config),
        encoding=workflow.TEXT_ENCODING,
    )

    context = backend_server.configure_runtime(operator_runtime.config_path)
    pipeline_config = context.pipeline_config
    rebuilding_store = AiAugmentBackendStore._from_resources(
        replay_log=pipeline_config.replay_log,
        detour_db=AiAugmentDetourDB.from_pipeline_db(
            pipeline_config.db_file,
            duckdb_extensions=pipeline_config.duckdb_extensions,
        ),
        rollout_cas=pipeline_config.rollout_cas,
    )
    rebuilding_store._rebuild_from_log(
        context,
        reset_confirmed=True,
        confirm_replay=lambda: True,
    )

    # The existing hash guard must still reject the obsolete Store.
    with (
        pytest.raises(ValueError, match="Hash verification failed"),
        operator_runtime.backend_store._read_only(context),
    ):
        pass

    # The validator must obtain a fresh Store, not bypass that guard.
    workflow.validate_workflow_artifacts(
        operator_runtime,
        namekey=STARTUP_NAMEKEY,
        expected_run_outcome_path=RunLifecycle.COMPLETED.to_run_outcome_path(),
    )
```

Required imports are existing `AiAugmentBackendStore`, `AiAugmentDetourDB`,
`BackendInitRequestRecord`, `init_request_record`, `AUTHORITATIVE_RECORDS_TABLE`,
`AiAugmentCohort`, plus standard-library `shutil`. The first regression fails
against the phantom-launch preparation. The second fails against the retained-
Store validator.

### 6. Assert the actual operator scenario has exactly one launch

In `assert_completed_dashboard_backend_codex_workflow_renders_researcher_card()`,
immediately before artifact validation:

```python
logged_init_requests = tuple(
    BackendInitRequestRecord.from_http_request_log_record(
        http_request_log_record=record,
    )
    for record in authoritative_records(operator_runtime.replay_log_path)
    if (record.method, record.path) == (HTTP_POST_METHOD, INIT_PATH)
)
assert len(logged_init_requests) == 1
assert logged_init_requests[0].namekey == namekey
```

This restriction belongs to that **single-launch operator scenario**, not the
general validator; legitimate multi-launch history tests remain valid.

### Additional approved closure assertions

Add these to `operator_fixture_bootstrap_process()`, immediately after its
existing `with` block and before printing `OPERATOR_BOOTSTRAP_QUERY_OK`:

```python
assert store._engine._mode is None
assert store._engine._context is None
assert store._engine._detour_db._conn is None
```

Then the parent test's success-marker assertion means actual Store/DB closure
checks passed—not merely that an acknowledgement string appeared. Fixture
preparation stops exercising the unwanted full serving startup; the new
regression checks the intended launch, and the live operator test still exercises
actual startup/shutdown. Artifact validation retains every existing assertion and
DB check. Hash rejection remains enforced. The one-init assertion is confined to
the single-launch operator scenario; legitimate multi-launch coverage remains.

After implementation: run focused checks serially, then continue the unfinished
actual-repository serial suite, stopping at its first failure. Never run concurrent
pytest/type/lint processes on this 1-CPU / 961-MiB host. No temporary source copies,
Git mutations, unapproved follow-up fixes, or full shipping-readiness claim before
the required verification is complete.


### Implementation and first-failure checkpoint

All six changes plus closure assertions implemented in exactly the four test files
above. Every approved Python block compared verbatim against WORK and matches;
required imports only, no production edits or deviations. Affected-file Ruff and
`git diff --check` pass. Git remains read-only.

Focused run stopped (`-x`): 4 collected, 1 passed, 1 failed, 2 not reached in
30.75 seconds. `test_operator_preparation_does_not_create_a_backend_launch` passed.
`test_operator_artifact_validator_opens_a_fresh_store` failed at preflight line168,
before CAS copying/rebuild/validator assertions: `Path.write_bytes()` cannot replace
`validator-runtime/backend-replay.jsonl`. Actual isolated file mode is 0400;
production `ReplayLogRegisteredResource._locked()` sets READ_ONLY_PERMISSIONS
at replay_log.py:65 during the preceding DB preparation. This is a flaw in the
approved regression setup, not evidence of a fresh-Store/hash failure. The
existing completed-history validator test and bootstrap test were not reached.
Mypy and serial-suite continuation have not run after these edits. Reports:
`logs/ai-augment-agent-checks/operator-fixture-correction.{log,xml}`.

**Operator approved exactly:** "ok i allow your proposed five line change to the
test exactly as proposed above." Record approval before implementation; wrap only this regression's history
copy in a temporary write-permission window, then restore read-only permissions,
using the existing replay-log permission constants:

```python
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.replay_log import (  # noqa: E501
    READ_ONLY_PERMISSIONS,
    READ_WRITE_PERMISSIONS,
)
```

```python
# Reuse faithfully produced completed history and its actual CAS bytes.
operator_runtime.replay_log_path.chmod(READ_WRITE_PERMISSIONS)
try:
    operator_runtime.replay_log_path.write_bytes(files.replay.read_bytes())
finally:
    operator_runtime.replay_log_path.chmod(READ_ONLY_PERMISSIONS)
```

The permission-window follow-up is now authorized; apply only these five lines
and their existing-constant imports, then rerun focused checks before continuing
the unfinished serial suite. No production changes or readiness claim.
No temporary source/suite copies introduced; only ordinary isolated pytest data.


### Approved permission-window implementation and focused rerun

Applied the exact five-line permission window and imports from existing
`replay_log.py` constants. No production edits. Focused rerun: all 4 passed in
57.52 seconds, including both new regressions, existing completed-history artifact
validation, and bootstrap query/closure/source preservation. The stale-Store
regression proves the old hash guard still rejects the obsolete Store while
fresh-Store artifact validation succeeds. Reports:
`logs/ai-augment-agent-checks/operator-fixture-correction-rerun.{log,xml}`.
Affected-file Ruff and `git diff --check` pass. Detour mypy stopped with the
two implicit-re-export errors recorded below; serial continuation remains pending.

The removed stdout ACK belonged to the fixture's full Store startup lifecycle
(not Uvicorn), which unnecessarily appended an init for the first eligible
NameKey before the Dashboard's actual selected launch. Empty-log DB preparation
now uses existing `_from_resources()` / `_rebuild_from_log()` without init.
Actual bootstrap Store closure remains asserted through `_mode`, `_context`, and
`_detour_db._conn` being `None` before the parent-observed success marker.


### Mypy first-failure checkpoint — pending exact test-import correction

`mypy-detour-ai-augment` checked 65 source files and failed only at
`test_operator_e2e_preflight.py:185-186`: the approved new regression references
`workflow.REPLAY_LOG_KEY` and `workflow.RESOURCE_SHA256_KEY`, which that module
imports but does not explicitly export. This is a typing mistake in the proposed
regression. Four focused runtime tests passed; no production failure was observed.
Report: `logs/ai-augment-agent-checks/operator-fixture-mypy.log`.
Stopped verification, no implicit re-export workaround or fix applied. The
unfinished broader serial suite has not resumed yet.

**Approved exactly:** "separately, i allow your proposed correction exactly as
you proposed regarding the two mypy's errors." Record before implementation;
import existing constants from their defining
modules in `test_operator_e2e_preflight.py`:

```python
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_registered_resource import (  # noqa: E501
    RESOURCE_SHA256_KEY,
)
```

Add `REPLAY_LOG_KEY` to the already-existing backend `helpers.vars` import, and
replace only the two implicit re-export accesses:

```python
config["files_config"][REPLAY_LOG_KEY][
    RESOURCE_SHA256_KEY
] = hashlib.sha256(operator_runtime.replay_log_path.read_bytes()).hexdigest()
```

The constant values, bytes, hash computation, checks, and production behavior are
unchanged. Apply exactly these direct imports and two qualifier removals, then
rerun mypy serially. Separately investigate the reported replayed commit/init
NameKey mismatch read-only; no production correction is authorized by that report.


### Direct-import correction and replay NameKey investigation

Applied exactly the approved direct imports plus two qualifier removals.
`mypy-detour-ai-augment` now passes all 65 source files. Ruff passes all four
changed test files; no test logic or production edits in this follow-up. Report:
`logs/ai-augment-agent-checks/operator-fixture-mypy-rerun.log`.

Operator reported intentionally changing init's NameKey and observing a different-
NameKey commit replay successfully. Read-only inspection confirms the gap:
`_apply_durable_record()` commit branch (Store:1375-1398) enforces accepted current
push and exact byrefs but not header NameKey equality with replayed init.
`_assert_lifecycle_links()` likewise checks only commit's pull/push object identity.
Live `_capture_push_commit()` checks original pull versus init (Store:788-790),
but historical replay does not call that capture function. The header→original
pull→init equality is checked only later in `_validated_commit_inputs()`
(Store:1739-1752), used during live/replayed validation. Thus a log ending at
commit can replay the mismatched commit; a following validation should reject
there, which is too late for the commit invariant. No altered operator log was
examined and no reproduction test or production fix has been made for this issue.

Pending proposed correction (NOT approved/applied): in `_apply_durable_record()`'s
commit branch, after existing pull/push identity checks and before assigning
`reconstructed = commit`, enforce the replayed init/header equality:

```python
init_request_record = self._init_request_record
if (
    init_request_record is None
    or self._parse_name_key_header(commit.request_headers.get(NAME_KEY_HEADER))
    != init_request_record.namekey
):
    raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_NAME_KEY_INVALID)
```

Corresponding regression should use faithful isolated history with a different
eligible init NameKey and stop the log at commit; assert rejection at that line,
not accidentally at a later validation or unrelated hash check. This would reuse
the same Store apply path for live append and rebuild; no new helper/model/validator.
No shipping-readiness claim while this reported invariant gap remains unresolved.
Approved unfinished serial-suite verification may continue with production untouched.


### Actual-repository serial continuation in progress

Collection with the same hermetic directories/marker selection: 788 collected,
4 deselected, 784 selected. Original serial pass/skip records plus the passing
14-case backend integration run, four original startup-failure reruns, and four
operator-fixture focused checks cover 588 distinct selected cases. Continue
exactly the remaining 196 actual-repository node IDs (not source copies), recorded
in `logs/ai-augment-agent-checks/serial-remaining-nodeids.txt`.

One low-priority pytest process only, `-x -vv -ra`, same detour environment and
APPENDWATCH/Playwright variables. Reports `serial-continuation.{log,xml}` in the
same reports directory. It started with
`test_startup_conditions[ineligible_namekey-ipc]`; report first failure immediately
and make no unapproved fixes. The newly reported commit/init NameKey gap remains
unmodified and is not covered by a new regression yet; passing this suite cannot
establish that gap is closed.


### Serial continuation stopped at environment-denied browser socket

196 collected for continuation; 48 passed, 1 failed, 147 not reached in
172.69 seconds. First failure:
`tests/control_centre/test_ui_e2e.py::test_completed_grid_row_uses_real_query_ipc`.
Traceback reaches `operator.running_dashboard()` → `_assert_ports_available()`
(test_operator_e2e.py:541) → `socket.socket(AF_INET, SOCK_STREAM)`; creating the
socket raises PermissionError errno1. Dashboard/Backend subprocesses and browser
have not started at this point. Faithful completed-query fixture setup and the
preceding `test_completed_query_fixture_has_current_queryable_history` passed.
This is an execution-environment socket restriction, not a card/IPC assertion
failure. No production/test fix, bypass, mock, or skip change has been applied.
Stop as instructed; no further pytest process remains running.

Across the current 784-case hermetic selection, combining original serial and
focused reruns with this continuation: 633 distinct passed, 3 skipped, 1
environment-failed browser case, 147 not reached. Four further cases were marker-
deselected at collection (788 total in those directories; not a full-repository
count). Per-test status/evidence and unreached reasons:
`logs/ai-augment-agent-checks/serial-current-status.tsv`; continuation log/XML:
`logs/ai-augment-agent-checks/serial-continuation.{log,xml}`.

All authorized six shapes, closure assertions, permission window, and direct-import
follow-up are applied. Focused tests 4/4 pass; detour mypy65 and affected Ruff pass.
Only approved imports/permission window depart from the original six snippets,
exactly as subsequently approved. The commit/init NameKey gap and regression
remain proposed, not implemented. No full shipping-readiness claim. No temporary
source/suite copies introduced; normal isolated pytest files only.

## Immediate authorized restoration — reject invalid launch NameKey before replay

Operator directed immediate surgical implementation of early launch-NameKey
validation and regression coverage, restoring the existing suggestion behavior.
Do not implement the pending operator-fixture or artifact-validator proposals in
this change. No new resolver, fallback, architecture/model change, or historical
replay gating. Reuse `context.blueprint_for_namekey()` unchanged.

In `src/backend/server.py::main`, validate after parsing the launch NameKey and
before constructing init or starting Uvicorn:

```python
try:
    startup_namekey = NameKey.from_json_key(raw_namekey)
except (TypeError, ValueError) as exc:
    raise ValueError(Locale.CONFIGURED_NAMEKEY_MALFORMED) from exc
context.blueprint_for_namekey(startup_namekey)
init_request_record = BackendInitRequestRecord(
    # Existing construction remains unchanged.
    ...
)
```

In `ai_augment_backend_store.py::_initialize_backend_store`, move the existing
eligibility call and its existing comments before `if new`, after requiring init:

```python
if init_request_record is None:
    raise ValueError(Locale.INIT_REQUEST_RECORD_REQUIRED)
# Line below checks the init'd namekey's eligibility:
# (Exact NameKey exists in Context's frozen blueprints
# AND its cohort is not AiAugmentCohort.INELIGIBLE)
# *before* openining store for writing.
context.blueprint_for_namekey(init_request_record.namekey)
if new:
    store._rebuild_from_log(
        context, reset_confirmed=confirmed, confirm_replay=confirm_replay,
    )
```

Add `test_invalid_launch_namekey_is_rejected_before_replay` in
`protected/tests/backend/test_backend_store_integration.py`. For each of
`--new`, `--resume`, and `--continue`, exercise an unknown NameKey, a whitespace
mismatch with the existing exact suggested NameKey, and the existing excluded
ineligible NameKey. Invoke the actual Backend CLI in an isolated subprocess and
also the production Store initializer, with the faithful `startup_files` fixture.
Assert the exact existing error/suggestion, CLI failure before the HTTP-start log,
and unchanged source/log/DB SHA-256 after each rejection. No mocks/monkeypatches,
new helpers, production data writes, or server started for the invalid selection.
Run focused tests serially in the detour Pixi environment; stop on any failure.

Implemented exactly this restoration: one existing resolver call added before
init construction in CLI; Store's existing call/comments moved before rebuild.
The resolver/suggestions themselves are unchanged. Verification: the full
protected backend integration module passed 14/14 in 100.10 seconds, including
all nine new rejection/suggestion cases and existing same-/different-NameKey
launch and historical-validation replay regressions. Affected-file Ruff passes;
`mypy-detour-ai-augment` passes for 65 files; `git diff --check` passes. Reports:
`logs/ai-augment-agent-checks/early-namekey.{log,xml}` and
`early-namekey-mypy.log`. No fixture bootstrap, artifact-validator, timestamp,
architecture, or replay-hash policy edits were made in this restoration.

The four originally reported startup failures were rerun after this restoration:
unknown/ineligible NameKey × resume/continue, all 4 passed in 29.70 seconds
(`four-startup-failures.{log,xml}`). Shipping readiness is NOT claimed. The actual
serial suite stopped at 564 passed / 3 skipped / 1 failed; 205 selected cases were
not reached by that run (some subsequently passed focused runs). The separate API
timing run completed: 278 passed / 2 skipped, 411.24 seconds. No full serial pytest
process remains running. Its remaining coverage is still unfinished.

Outstanding read-only operator audit, not implemented: `_operator_runtime()`
manufactures an init for the first eligible researcher during DB preparation;
the actual Dashboard Backend launch then appends its intended init. Retained
`tmp/test.m3b9l8lg` confirms line 1 Beatriz Roldan/Cuenya and line 2 A./Sheikh.
Its config/DB anchor covers line 1, while artifact validation reuses the fixture's
Store whose resource still expects the empty-log hash. That causes the separately
reported live operator hash failure; the NameKey restoration does not fix either
issue. Proposed direction remains DB preparation via existing rebuild machinery
without a launch, and fresh query-only Store construction for artifact validation,
with faithful regressions. No implementation approval or source edits for these.

## Active surgical chore — `dashboard markdown completed` (2026-10-05)

Operator authorizes changes to `src/control_centre/dashboard/ui.py` and
`tests/control_centre/test_ui.py`, with dashboard `vars.py` only if necessary.
Add `dashboard markdown completed`: use the existing completed-publish population
and card construction unchanged, but write one UTF-8 `.txt` file per researcher
containing the exact `card.card_markdown` source, without Pandoc or value changes.
Reuse `publish_completed` via its existing-style `output_format` choice (`docx` or
`txt`), add the command flag to CLI/startup/one-shot shutdown dispatch, and keep
DOCX and spreadsheet behavior intact. Extend the existing faithful publishing
tests for TXT selection, exact contents, unchanged storage, no-op, and partial
write failure. No mocks of card/export behavior, new helpers/models, architecture
edits, or resumption of the paused timing implementation. Before editing source,
run the existing publish success test as a baseline.

Operator additionally authorizes surgical spreadsheet progress logging, using
publish_completed's existing emit_log/logger conventions: announce completed-run
and column counts, destination before CSV export, and successful file write with
byte count. Reuse existing applicable log templates; no export/data changes.
Extend the existing faithful spreadsheet test to assert these messages.

Baseline executed in the detour Pixi environment: one test collected, one failed
before publishing. `test_ui.py:250` still supplies
`received_at_unix_usec=1` to `RunOutcomeRequestRecord.from_http_request`, whose
partially updated timing implementation no longer accepts that argument.
Operator rejected that fixture alignment and explicitly directed implementation
of only the requested export changes. Leave the helper and all timing code intact;
the pre-existing baseline failure is not authority to fix them. Operator also
authorizes correcting CSV order to narrative AI → standardized AI → ground truth;
comments have no standardized partner and retain their adjacent ground-truth column.

Implementation contour:

```python
async def publish_completed(
    services: _ApplicationServices,
    *,
    output_format: Literal["docx", "txt"] = "docx",
) -> None:
    # Existing population selection and card construction remain unchanged.
    ...
    destination = config.output_dir / f"{card.filename_stem}.{output_format}"
    if output_format == "docx":
        content = await asyncio.to_thread(card.render_docx, config.pandoc_reference_docx)
    else:
        content = card.card_markdown.encode(TEXT_ENCODING)
    await asyncio.to_thread(destination.write_bytes, content)
```

Add `APPLICATION_MARKDOWN_COMPLETED` alongside the existing export flags; accept
`markdown completed` in main; include its flag in publishing startup mode and
dispatch it through `publish_completed(..., output_format="txt")`. For spreadsheet
column placement, reuse `AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS`:

```python
for plain_column, standardized_column in AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS:
    ground_truth_by_ai[standardized_column] = ground_truth_by_ai.pop(plain_column)
```

Keep existing data values, CSV row sorting, storage isolation, DOCX behavior, and
card population unchanged. Extend existing export tests only; preserve their
fixtures without the rejected timing correction.

Implemented in exactly `ui.py` and `test_ui.py`; no `vars.py`, model, fixture, or
timing changes. `markdown completed` is wired through CLI/startup/one-shot shutdown
and writes raw card Markdown as UTF-8 `.txt`. Spreadsheet order now places each
ground-truth column after its standardized AI partner; logs announce run/column
counts, destination, and bytes written. Existing publish tests now cover DOCX/TXT,
and the existing spreadsheet assertions cover column order and progress logs.
Verification: affected-file Ruff passes; `git diff --check` passes; CLI `--help`
lists `publish,markdown,spreadsheet`. The two faithful empty-population DOCX/TXT
one-shot cases pass. The populated-export focused run collected five cases and
stopped at its first failure (DOCX), the exact pre-existing rejected fixture issue
at `test_ui.py:250`; four remaining cases were not executed. No follow-up fix or
broader test run made. Passing populated exports and operator readiness are not
claimed. No departure from the three requested export changes.

## Active implementation checkpoint — `/init` Backend-launch boundary (2026-10-03)

Operator-directed surgical addition applied: synthetic `/init`, `/commit`, and `/validate` requests now set `ready_to_respond_at_unix_usec` at construction and `duration_usec=0`; model/Store replay contour checks require these, with receipt/response fields still absent. The shared init fixture and two affected test constructors/assertions were adjusted. Model focused tests passed 14/14; `test_backend_store.py` passed its 48 cases before the HTTP test's stale timestamp assertion stopped the combined run, and after that assertion's correction `test_http_interceptor.py` passed 45/45. Ruff passed for all affected files. No full suite or mypy gate has been rerun for this addition yet. Startup-matrix expectations below remain unapproved and unchanged.

Operator requested a comprehensive timing audit. **Operator's exact rule:** for responses Backend sends (`/pull`, `/push`, IPC query and run outcome), `received_at_unix_usec` stays `None`; capture a transient monotonic start when request arrives, then wall-clock `ready_to_respond_at_unix_usec` and monotonic elapsed duration. For external responses Backend receives (OpenAlex/ROR), capture transient monotonic start when request is sent; record wall-clock response arrival as `received_at_unix_usec`, keep ready-to-respond absent, and monotonic elapsed duration. Unsent synthetic init/commit/validation have ready wall time at construction, receipt absent, duration zero. The audit found late public starts, wall-subtraction and improper receipt in IPC, and provider response-arrival stored in ready instead of received. README examples at lines 217/222 are stale regarding synthetic timestamps and run-outcome receipt.

### Operator-approved timing correction (2026-10-03)

Operator explicitly authorized fixing **the exact gaps in the audit**, surgically. Preserve these direction-specific field semantics without inventing a persisted request-receipt timestamp:

| Exchange | `received_at_unix_usec` | `ready_to_respond_at_unix_usec` | `duration_usec` |
|---|---|---|---|
| Backend sends `/pull`, `/push`, IPC query, run outcome | `None` | wall time once response body is ready | monotonic delta from request arrival |
| Backend receives OpenAlex/ROR response | wall time when response arrives | `None` | monotonic delta from dispatch |
| Unsent synthetic `/init`, `/commit`, `/validate` | `None` | wall time at construction | `0` |

Exact audited gaps/owners: `backend/server.py:215-265` prepares public requests before `api.py:515/558` starts monotonic timing; move transient start to route entry and pass it into `authoritative_pull/push`, while `api.py:906` keeps receipt `None`. `backend/server.py:create_dashboard_query_app` prepares IPC requests before `backend/ipc.py:54/111`; begin a transient timer at route entry, carry it through IPC→Store response construction, and do not put receipt time into `QueryRequestRecord` or `RunOutcomeRequestRecord`. `dashboard/helpers/data_models/query_event.py:116-147` and `run_outcome_event.py:179-228,295-340,345-405,460-512` currently require/copy the incorrect request receipt and subtract wall times; remove those dependencies and compute duration from the transient monotonic start, while keeping ready wall time after response-body assembly. `backend_store.py:1026-1071` puts provider arrival in ready and receipt absent; reverse field placement for received response, with monotonic duration from dispatch. `backend_store.py:1580-1602,1930-1937` currently demands provider ready time; enforce received-response contour instead. `_validate_public_exchange` should require receipt `None` for sent responses. No new wrapper/model or fallback. The stale README examples can be revised post hoc after code and tests stabilize, per the standing architecture-first instruction. Provider transport failure is a request-only log line for which the audit noted no specified end-timestamp meaning; **no correction to that case is approved**.

Operator additionally requires test coverage proving **every approved timing point** above: sent public and IPC responses keep received absent and use a monotonic start from before request preparation; received provider responses have received wall time, ready absent, monotonic elapsed from dispatch; synthetic init/commit/validation have construction-time ready, receipt absent, duration zero. Strengthen existing backend/API/IPC tests and add focused checks only where needed. Operator **rejected** changing the architectural `QueryOnlyStoreProperty.query_response_record` signature to accept `started_ns`; architecture.py remains untouched. This leaves a design tension for exact IPC-query timing because route owns the arrival timer and Store owns response construction. Operator directed a full stop before any further change outside the approved WORK scope. **Paused with a partial, not-yet-runnable implementation**: public route/API transient start is wired; IPC route/callback/handler start propagation is partly wired; run-outcome model/Store timing is partly wired; query response model/Store, provider capture/replay, tests, and full verification remain undone. No further source/test changes until an architecture-preserving query handoff is concretely proposed and approved; do not silently approximate with a Store-started timer or hidden state.

Operator approved the exact `/init` shape below, with `_init_request_record` as the Store private reference, no compatibility path, a same-namekey second-launch regression, a short architecture docstring distinguishing Backend launches from Agent Runtime attempts and Control Centre runs, and a narrow manual-launch README update. Source wiring is in place: full startup constructs a synthetic typed init request; Store appends/replays/readbacks it before serving; each replayed init resets the one lifecycle cursor; Context retains only frozen config/blueprints; live and historical validation resolve the relevant namekey from the replayed launch and original pull. Push links only accepted 202 to current 200 pull; initial 200 NDJSON and retry 200 Markdown links are distinct. Standard HTTP header names are compared case-insensitively because real ASGI response headers are lowercase. IPC-only startup does not append init.

Focused integration tests passed 2/2 before the new launch regression; the launch regression passed both same-namekey and different-namekey cases (2/2), including rejected pushes before/after the second pull. A further focused regression constructs a real rejected validation for the first launch and verifies successful historical replay when the next launch chooses a different namekey (1/1). The initial→retry validation/byref link test passed (1/1). The added init makes existing fixture log/table counts and ordinals increase by one; those assertions were adapted surgically. Full `test_backend_store.py` passed 48/48. Ruff and detour mypy pass (65 files). `test_api.py` passed all its cases cumulatively under stepwise continuation; its IPC-only startup fixture repins the replay-log hash after a full launch, accepted-push log assertions include `/init`, and the fsync-failure test uses a rejected pull that requires no launch link. Each focused correction passed. The provider-I/O concurrency test passed 1/1 in isolation after twice exceeding its two-second thread deadline during concurrent suites; no timing/locking changes made. Operator-directed same-launch-after-outcome regression passed 1/1, then a second same-namekey `/init` was inserted into the existing duplicate-validation test; both focused tests passed 2/2. The first broader hermetic rerun stopped at 367 passed, 2 skipped, 4 deselected; operator-approved Markdown/rejected-initial fixture corrections passed all five focused cases. The next serial rerun cleared these and stopped at its first new failure: 426 passed, 3 skipped, 4 deselected in 13:21. Operator-approved test-helper correction added optional response headers to `tests/control_centre/test_ui.py::http_record`, with the `agent_runtime_attempt` initial pull explicitly carrying NDJSON media type; its 3 focused response cases passed 3/3. Operator-approved `_operator_runtime` config repin plus query-only log-unchanged assertion passed focused test 1/1. Downstream rerun stopped at its next first failure: 94 passed, 4 deselected; startup matrix `ready-ipc` expected 0 rows but fixture has one `/init` row, and IPC-only correctly leaves it at one. Related startup-matrix assertions need coordinated test-only adjustment, **not yet approved or applied**: baseline IPC row count 1; successful full `new`/`resume`/`continue` append one init and yield 2; the `unprojected_record` case should append its generic provider line *after* existing init before `new` rebuild, then yield 3 after new init; successful full launches extend replay by exactly one typed init line, while IPC-only and failed starts leave it unchanged; successful resume is allowed to update DB by projecting init, while IPC-only and failed non-new starts remain byte-identical. The neighboring second-replay-confirmation test similarly should append its synthetic provider line after existing init and expect one new init appended only on successful full launch. Await operator approval for this surgical test-only matrix correction before editing. Operational hash pinning remains as documented; no production hash policy change proposed. `protected/tests/operator/README.md` states manual launch records/replays selected NameKey before `/pull`, without discussing compatibility.

## Approved `/init` lifecycle shape (2026-10-03)

**The startup namekey will exist only long enough to construct `BackendInitRequestRecord`.** Context will hold config and frozen blueprints, but no namekey. Store will append, replay, and hold the *reconstructed* init object by identity. Older logs without `/init` will be incompatible—no fallback or migration path.

### 1. Contract and init model

In `architecture.py`, add:

```python
class InitRequestRecordProperty(RequestRecordProperty, Protocol):
    """Durable NameKey selected by the operator for one Backend launch.

    A Backend launch is distinct from Agent Runtime attempts and Control
    Centre runs. Replaying this record starts a fresh lifecycle boundary.
    """

    @property
    def namekey(self) -> NameKey: ...
```

Remove `ContextProperty.configured_namekey`; add `InitRequestRecordProperty` to the `FullStoreProperty.current_replayed_record` union. Clarify the push-link docstring: only an accepted `202 /push` refers to its current `200 /pull`.

In a small `init_request.py`, `BackendInitRequestRecord(RequestRecord)` implements that property by parsing its sole `NameKey` header. Its validator requires precisely the synthetic `POST http://invalid/init` contour: empty query and body, no response, receipt absent, ready time at construction, duration zero. It explicitly defines the usual four record methods, delegating to its base where no override is needed. The only new route constant is `INIT_PATH = "/init"`; existing method, scheme, host, header, and schema-version constants are reused.

### 2. Startup and the single replay contour

In `server.py`, `configure_runtime()` constructs only `AiAugmentBackendContext`. On a **full** startup, `main()` parses the environment namekey and uses it once:

```python
init_request_record = BackendInitRequestRecord(
    schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
    method=HTTP_POST_METHOD,
    scheme=SYNTHETIC_COMMIT_SCHEME,
    host=SYNTHETIC_COMMIT_HOST,
    port=None,
    path=INIT_PATH,
    query="",
    request_headers={NAME_KEY_HEADER: name_key_header_value(startup_namekey)},
    request_body=None,
    response_code=None,
    response_headers=None,
    response_body=None,
    received_at_unix_usec=None,
    ready_to_respond_at_unix_usec=None,
    duration_usec=None,
)
```

Pass **that record**, not `startup_namekey`, through `full_backend_application → lifespan → backend_store_lifecycle → initialize_backend_store`. After any requested rebuild and after opening writable Store—but before yielding it to the server—Store checks the record’s namekey against its frozen blueprints and calls its existing `_append_authoritative_record(init_request_record)`. Failure prevents startup. IPC-only startup constructs no init and writes nothing.

Store recognizes `/init` in `_validated_http_record()` and `_apply_durable_record()`, projecting and reading it back through the **same** persist→replay→DB-readback path as other records. `_remember_reconstructed_record()` does:

```python
if isinstance(record, BackendInitRequestRecord):
    self._init_request_record = record
    self._current_replayed_record = record
```

`_init_request_record` is a private, fixed reference to this Backend instance’s replayed start record; it is **not a second lifecycle cursor**. After live append, assert `store._init_request_record is reconstructed`. Each historical `/init` replaces both references during rebuild, defining the missing process boundary. Reject any non-init lifecycle line before an init. Remove the pre-writable cursor reset: the newly appended init itself resets the cursor. No compatibility handling for older logs.

### 3. Selection and downstream provenance

Move Context’s existing exact-match, eligibility, and suggestion logic into `blueprint_for_namekey(namekey)`. It returns the existing frozen tuple member by reference. Store exposes a selection method for API `/pull` that uses **only** `self._init_request_record.namekey`; API does not read the init object or Context directly.

For commit capture, follow the accepted push’s pull reference. For a retry, follow its prior validation to the original NDJSON pull. Derive the commit header NameKey from that original pull, and require it to equal the replayed init’s namekey:

```python
original_pull = (
    pull
    if pull.validation_request_record is None
    else (
        pull.validation_request_record.validation_request_body
        .initial_validation_request_record
        or pull.validation_request_record
    ).validation_request_body.commit_request_record.commit_request_body.pull_response_record
)
namekey = self._namekey_from_original_pull_response_record(original_pull)
if namekey != self._init_request_record.namekey:
    raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_NAME_KEY_INVALID)
```

Keep the existing commit-header-versus-original-pull check in `_validated_commit_inputs()`. Its lazy `draw_number()` now selects `context.blueprint_for_namekey(namekey)`, **not** a currently configured researcher. It retains the existing lazy `(value, error)` behavior.

Both live `_run_outcome_response_parts()` and replay `_verify_run_outcome_record()` use the replayed init’s namekey as the expected identity. This covers outcomes with no pull or commit. Replay must still accept a logged `400` *when that identity check fails*; it must reject a logged `400` when the check would now succeed. It must not compare a request namekey against itself, as replay currently does.

### 4. Close the two link loopholes

For `PushResponseRecord`, attach a pull **only** if the response is `202` and the cursor is a `200 PullResponseRecord`; require `None` for every rejected push. Update Store’s identity assertion and API’s immediate-response assertion accordingly:

```python
expected_pull = (
    current
    if record.response_code == HTTPStatus.ACCEPTED
    and isinstance(current, PullResponseRecord)
    and current.response_code == HTTPStatus.OK
    else None
)
assert reconstructed_push.pull_response_record is expected_pull
```

For `PullResponseRecord`, a `200` NDJSON initial pull has `validation_request_record=None`. A `200` Markdown retry must refer **by identity** to the current retryable, rejected validation (or the same validation already held by a repeated retry pull). Other responses attach none. Store performs this selection on both live append and log replay; the model enforces the corresponding media-type/link contour. The existing prohibition on a new `200 /pull` immediately after an accepted push or commit can remain: a *new Backend instance* begins with `/init`, so it no longer needs an artificial exception to that rule.

Surgically adapt existing startup/record tests and add one focused integration regression for two different-namekey Backend launches in one log, including an interrupted first launch. Operator additionally requires a same-namekey, two-launch case in that regression: the `/init` boundary must reset lineage even when namekey values are equal. Assert that replay gives the second initial pull no prior validation and that accepted push, retry, validation, and outcome links retain their intended object identities. Use “Backend launch,” not “run,” for these instances. No changes to dashboard startup policy, query serialization, or source-version pinning are proposed. Surgically update `protected/tests/operator/README.md` only for the current manual launch procedure; do not add any explanation of older logs, fallbacks, or compatibility.
