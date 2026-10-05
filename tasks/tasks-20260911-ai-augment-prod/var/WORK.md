# AI augment production — current workbook (2026-10-05)

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
