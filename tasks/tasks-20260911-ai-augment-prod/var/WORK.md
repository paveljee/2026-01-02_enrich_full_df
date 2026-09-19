# AI augment production preparation

## Status and authorization

Active execution (2026-09-19): operator requested implementing exactly HUMANS corrections2
and4–7, whose approved snippets/boundaries are pinned below. All five code corrections are
now implemented and locally verified within the available boundaries; delegated verification
and full operator acceptance remain pending. Items1/3 were already complete. No P26–P30,
Backend/Store, CSS or ordinary-task changes. Human-maintained HUMANS remains unchanged;
its captured "proposed" labels do not supersede the later explicit approvals recorded here.

Current verification:
- Item2: reproduced all five stale IPC-target failures (4.04s); corrected only target/import;
  unchanged preflight module then20passed25.15s.
- Item4: exact ready-card checks and finite measurement diagnostics; every existing spacing/
  bounding-box assertion and timeout retained. Host Chrome execution remains pending.
- Item5: real-child cancellation regressions reproduce early ownership release (2failed7.40s).
  Exact wrapper/log implementation plus per-owned-PID operator teardown check now in place;
  focused supervisor/shutdown/teardown selection8passed7.79s. Named child helper lives in the
  existing plugin; test explicitly marked python_subprocess. Initial test harness loop wakeup
  issue interrupted48.56s; reused existing threaded_loop fixture. An initial child-exit wait also timed out; replaced signal-handler
  printing with explicit sigwait to eliminate that race opportunity (initial cause unproven); synchronized log-drain phase with actual child exit. No production
  timing/timeout change or skipped assertion. These harness-development failures are not passes.
- Item6: new diagnostic regression reproduced missing Backend reason (1failed3.16s), then
  exact approved error-prefix filtering applied.
- Item7: exact named audit subprocess helper/explicit marker, unchanged production audit.
  First combined preflight/audit run36passed1failed80.96s: new child exceeded approved10s
  bound during concurrent verification. No timeout increase/suppression. The unchanged test
  passed within the full feasible suite below; unchanged isolated recheck plus three nonsocket
  substitution cases passed4tests2.67s. Cause of the initial timeout remains unproven.
- Full ordinary AI feasible suite:620passed1existing skip12deselected818.49s. Includes all
  startup cases, API/replay/index/Store, UI/supervisor, audit and full operator preflight.
  Excluded real-provider/root, two historical captures, Unix IPC/socket-substitution and
  four nonregular substitution params; the three nonsocket params passed separately above.
  Host browser module explicitly ignored, not reported passed. Existing skip is the
  deliberately disabled multiple-evidence-match rejection test. No warnings in this run.
  Strict detour mypy PASS55files; full src/tests
  Ruff PASS after correcting only the approved helper snippet's import-spacing blank line.
  AST audit confirms old _stop body unchanged except approved extra log fields; every original
  compact-spacing/bounding-box assertion is unchanged.
  Main/default mypy PASS68files. Main suite on this x86 host is NOT wholly green:
  initial maxfail run20passed1skipped1deselected1failed12.43s (configuration lists only ARM
  extension binaries, not linux_amd64). Remaining main selection140passed3skipped2deselected
  2failed16.42s: configured ARM binary absent, reviewed workbook absent at production path.
  No fixture/config substitution, new skip, data search or test weakening. Verify these
  existing prerequisites on aicode through elevate; no out-of-scope implementation.
  Step4/Mode3:10passed1slow deselected17.80s (default environment). Mode0 import/isolation
  and normalization helpers:2passed2plot cases deselected2.60s (Mode0 environment). Plotting
  requires Kaleido sockets unavailable here; existing operator Mode0/root passes remain the
  retained evidence for unchanged boundaries, not newly executed checks. No full acceptance claim.

Priority remains a failure-free FULL pre-commit-operator run before P26. P26–P30 stay
approved/pending. Correction1 (find/supported-subset eligibility) remains implemented and
locally verified246passed1existing skip3deselected; seeded choice/retry behavior unchanged.
Correction3 deleted all elevate-triggering tests and preserved the then-idle task. The
Assistant-owned elevate is now prepared for the delegated checks described below, not
invoked by any test. Any further deviation/new defect requires explicit approval.

### Next operator verification — prepared, NOT executed

Run pixi run elevate; its embedded machine guard requires the macOS Dashboard host before
any log replacement or temporary files. It runs the entire9-test Chrome UI module on host,
including ready-card spacing and actual owned IPC cleanup. It then dispatches ONLY to the
named aicode guest (Linux ARM64 guard), never aivm:
- Real OpenAlex/ROR institution test (previously unreached leaf).
- Real0600 Unix IPC and the now-isolated audit probe.
- Two nonprivileged watcher socket-substitution cases unavailable here.
- Unchanged main-pipeline extension tests and reviewed-workbook prerequisite case (6tests)
  which cannot be certified on this x86 host without production resources.

Total targeted collection20cases:12host/IPC/audit/provider7.35s,2watcher0.50s,
6default-prerequisite6.27s. Collection is not execution/acceptance. All relevant skips,
failures, warnings, durations and cleanup evidence must be reviewed from elevate.log.
No sudo, password input, SSH debug/key output, live Codex, browser installation, fixture
substitution or ordinary-task edit. Preserve main test failures until the real prerequisites
pass; never add a fake extension/config, new skip or edited assertion to mask them.

Only elevate in pyproject.toml changed. Its temporary shell scripts are created in one
mktemp directory under the shared repository tmp (removed on EXIT), avoiding nested quote
explosion and allowing the guest to read the exact script. BSD script captures host/guest
output; an explicit batch-status file preserves failure independently of script's status.
All leaves run despite earlier failures; FAILED grep/log path remain. Guest stdin is closed.
TOML, four shell bodies, wrong-machine guard and equality of all other task/settings PASS.
An intermediate in-memory shell-decoding script used a wrong argv index and failed before
writing; corrected before the final syntax/guard checks. No delegated commands ran locally.
Restore idle Nothing-to-elevate script/log/status/grep scaffolding after this batch is reviewed
and no further delegated verification is needed. Full pre-commit-operator is NOT authorized
as acceptance-ready yet: review this targeted batch first, then run the full gate before P26.


Latest addition (2026-09-18): P30 is APPROVED/PENDING: Store-owned current pull/push/commit/
validation record instances; explicit session/current-record outcome linkage and completed
ETag handshake; full outcome-response-record innerdict metadata; re-hook original-pull/retry
bookkeeping to that model. It supersedes the conflicting historical lookup/metadata rules
in P25/P29, not their other approved work. Only WORK changed; no P30 source implementation.

P29 is APPROVED/PENDING: rename Backend retry bookkeeping's
misleading run_id to original_pull_record_id, including its column constant, SQL and direct
test callpoints. Dashboard run IDs remain unchanged. P30 additionally authorizes re-hooking
this bookkeeping; P29 by itself is still only the rename.
Only WORK changed for this addition; the rename is not implemented yet.

P28 is APPROVED/PENDING: specific request/response record
protocols inherit their common record protocol plus Protocol; downstream implementations
declare only the specific protocol. Centralize all corresponding request/response/body
properties directly in BackendComponent. Latest operator correction also renames the outcome
response protocol/model to RunOutcomeResponseRecordProperty/RunOutcomeResponseRecord.
Only WORK changed for this addition; no protocol/source implementation yet.

P27 is APPROVED/PENDING: audit all single-/double-quoted literals
introduced by P25, reuse authoritative definitions, centralize genuinely global/reusable
values and all text messages appropriately, and justify every retained inline literal.
Only WORK is changed for this new approval; the literal audit/corrections are not yet complete.

P26 is APPROVED/PENDING, narrowly extending P25 with explicit
typed request/response construction and one Backend ContentType StrEnum. Its exact query
constructor shape and enum wiring are pinned below. Only WORK is changed for this addition
so far; it is not an implementation/completion claim.

P25's exact proposed four-operation Store contract,
implementation boundary and code snippets are APPROVED, with two operator corrections:
use BackendStoreAcknowledgment.ACK/NAK (values "ack"/"nak") everywhere;
operator explicitly requires enum-member checks, never acknowledgment.value vs raw strings; reserve publishing
terminology for DOCX/TXT and use update_pull_state for the runtime pull-state update.
P25 baseline implementation is COMPLETE and locally verified (2026-09-18). TASK and WORK
were reread in full; verification results and corrected development failures are below.
The full approved contour/snippets below stand alone.
Any deviation or extension requires explicit approval before implementation.

P24 is implemented and locally verified after the operator's restore/reimplementation
instruction; its fresh evidence is below. P20/P21/P23 remain implemented. P22 is historical,
superseded by P24's persisted-ID/pure-renderer contour. P25 retains that contour while
changing Store/adapter boundaries and grouped processing only as explicitly pinned below.
P25 production wiring is implemented and its selected integration/startup checks pass.
The last full operator run exposed five missed preflight callpoints and three stale elevate
test expectations; both are corrected now, but fresh full acceptance remains pending. The
separate web-action correction1 is implemented. P26-P30 remain pending additions. P30 supersedes only the state ownership,
outcome reference selection and innerdict metadata decisions identified below. Preserve
operator edits/staging. Production acceptance and unrelated browser/root/pre-start findings
remain separate; these additions do not authorize their corrections.

## P25 — Implemented and locally verified: four-operation Store contract

Operator approved the exact preceding proposal and snippets, subject only to the naming
corrections incorporated below. This section consolidates the discussion into that approved
contour; it is not a further proposal or an implementation claim. This is a bounded structural
change, not merely a server gate cleanup. Preserve durable record linkage, pure innerdict
rendering, no recovery and common live/replay rules. P30 replaces the former metadata fields
with a full persisted outcome envelope. Unrelated browser/root/pre-start findings are excluded.

### Responsibility and persistence contract

Server owns ASGI/WSGI transport conversion, lifecycle and admission. API/IPC helpers exchange
Requests PreparedRequest/Response objects with server, app RequestRecord/ResponseRecordPromise
objects with Store. Requests is used as an in-process representation, never internal HTTP.
API retains existing transport/workflow response timing, including busy503, push409 and early202,
and updates pull state from final push results. It does not append/project/validate itself.
Existing evidence/SQL algorithms may remain private helpers invoked by Store; no wholesale
move of API algorithms into the Store module. Only Store owns DB/log operations/transactions.

BackendStoreAcknowledgment has exactly ACK/NAK and refers ONLY to request persistence.
ResponseRecordPromiseResult[R] is exactly (R, None) or (None, StoreExceptionProperty), with
concrete BackendStoreException implementing that protocol. Result errors are raised by the
adapter; they do not silently become HTTP409. Request persistence failure for API returns NAK
plus an already-resolved error result. IPC always expects NAK. ACK followed by a later error
remains ACK plus an error result. Invalid result tuples are contract failures, never fallbacks.
Normal Store failures resolve the tuple; they are not thrown directly from the completion
awaitable. API/IPC raise its returned real exception. Never return both tuple values or both
None. A failed append/fsync can leave bytes despite NAK: fail closed, no repair/retry or claim
of zero bytes written. Successful run-outcome409 is NAK plus (response_record, None) after
its response exchange is durably persisted/projected; HTTP status is independent of the gate.

| Operation | Gate | Operation/result boundary |
|---|---|---|
| pull | ACK after append/fsync; NAK on failure | project/read back exchange before result; preserve all existing HTTP statuses/bodies |
| push | ACK after append/fsync; NAK on failure | accepted202 may be sent before processing finishes; final result follows grouped commit/validation projection |
| run_outcome | NAK by policy | persist complete response exchange, including409, project/materialize eligible rows, then return successful result |
| query | NAK by policy | read-only wholesale snapshot, no log or DB content writes |

Approved record format: retain existing v1.1 COMPLETE pull/push HTTP exchange envelopes in
log. The app RequestRecord can contain the already-selected public response (202/409/etc.)
because it is an application input, not an alias for raw HTTP request. Do not introduce a
second request-only pull/push log entry, repeated record UUIDs, mutation of old JSONL lines,
or request/response pairing schema. Commit/validate retain their current synthetic shapes;
outcome logs its full response exchange only; query logs nothing. This is explicitly part
of the approved scope, not a new compatibility contour. Early202 establishes log durability,
NOT completion of grouped DB projection. Final result objects still come through Store
projection/readback. Extra application model fields are excluded from HTTP-log serialization.

Timing wording to make explicit in the promise protocol: Store performs required response
persistence before returning a SUCCESSFUL completed promise result. The initial handle and
its request gate are distinct from that final result. A response persistence failure yields
(None, exc), never a usable response. For push its public202 exchange is already persisted
at ACK; its added commit/validation properties become available only at completion. A literal
requirement to finish all final application-response work before returning the initial handle
would contradict early push acceptance; do not silently change that timing.

### Exact approved protocol and exception snippets

Architecture property definitions below live under BackendComponent in
protected/src/architecture.py (existing component bases retained). The latest operator
correction explicitly places StoreAcknowledgmentProperty and
ResponseRecordPromiseResultProperty there; concrete BackendStoreAcknowledgment and
ResponseRecordPromiseResult remain downstream in response_record_promise.py. The result
property is a tuple-union type alias, preserving the approved exact tuple contract; it is
not a new result wrapper model.
The structural exception includes raise_exception so protocol-typed consumers can raise the
real exception without casts or pretending a Protocol inherits Exception.

```python
# Nested under BackendComponent:
class StoreAcknowledgmentProperty(Protocol):
    @property
    def value(self) -> Literal["ack", "nak"]: ...

type ResponseRecordPromiseResultProperty[R] = (
    tuple[R, None]
    | tuple[None, BackendComponent.StoreExceptionProperty]
)

class RequestRecordProperty(HttpRequestLogRecordProtocol, Protocol):
    pass

class ResponseRecordProperty(HttpRequestLogRecordProtocol, Protocol):
    pass

class StoreExceptionProperty(Protocol):
    def raise_exception(self) -> NoReturn: ...

class ResponseRecordPromiseProperty[
    R: BackendComponent.ResponseRecordProperty,
](Protocol):
    """A request-persistence acknowledgment and an eventual application result.

    ACK means the request record was appended and fsynced in the replay log.
    NAK means it was not. IPC deliberately does not persist request records.
    Neither value describes response persistence or application success.

    Backend Store performs response persistence where required before returning
    the successful completed result. Response-persistence failure returns
    (None, exc); success returns (response_record, None).

    Returning the initial promise handle does not imply processing completion.
    """
    @property
    def acknowledgment(self) -> BackendComponent.StoreAcknowledgmentProperty: ...

    async def response_record(self) -> BackendComponent.ResponseRecordPromiseResultProperty[R]: ...
```

Concrete implementations in the new response_record_promise.py helper:

```python
@implements[BackendComponent.StoreAcknowledgmentProperty]()
class BackendStoreAcknowledgment(StrEnum):
    ACK = "ack"
    NAK = "nak"


@implements[BackendComponent.StoreExceptionProperty]()
class BackendStoreException(RuntimeError):
    def raise_exception(self) -> NoReturn:
        raise self


type ResponseRecordPromiseResult[R] = (
    tuple[R, None] | tuple[None, BackendStoreException]
)
```

Preserve the original cause when converting internal exceptions; log detailed errors, retain
existing fail-closed Store state, and never stringify away the cause or retry. The concrete
ResponseRecordPromise is a FrozenStrictModel: acknowledgment is its public field, task/result
state is PrivateAttr. Awaiters shield the Store-owned completion. No arbitrary_types_allowed,
new executor service, cast, type suppression or serialized Task/Future. Reuse existing thread
offload and tracked background work; no threaded IPC. Keep completion tracked through the
pull-state update and shutdown, including client disconnect and failed response sends.

### Route-specific records and Store surface

Add route-specific RequestRecordProperty/ResponseRecordProperty protocols under BackendComponent.
Their common base is the corresponding HTTP-record protocol. Concrete pull/push/query records
inherit HttpRequestLogRecord; reuse the existing outcome response model, renamed to
RunOutcomeResponseRecord by the later explicit P28 correction. Keep outbound Dashboard QueryRequest and
RunOutcomeRequest as existing client-facing types; add server-side record adapters, not duplicate
client protocols. Existing QueryResponse remains the wholesale response BODY, not the envelope.

Representative concrete shapes (constructors/validators preserve current wire fields):

```python
class PullRequestRecord(HttpRequestLogRecord):
    pass

class PullResponseRecord(HttpRequestLogRecord):
    @property
    def pull_response_body(self) -> str:
        if self.response_body is None:
            raise ValueError(Locale.PULL_RESPONSE_BODY_MISSING)
        return self.response_body

class PushResponseRecord(HttpRequestLogRecord):
    commit_record: BackendCommitRecord | None = Field(exclude=True)
    validation_record: BackendValidationRecord | None = Field(exclude=True)
```

Use existing @implements decorators and record validators; both extra push fields are explicit
at construction, not old-data fallbacks. Nonaccepted pushes have neither; accepted pushes return
matching typed records after completion. Preserve external session/pull linkage on PushRequestRecord
and captured outcome inputs on its server-side request model as excluded typed fields. API/IPC
helpers assemble/capture those external inputs at their existing lifecycle points; do not delay202
for rollout capture or duplicate that I/O. Store orchestrates the existing capture helpers when
processing needs them. QueryResponseRecord exposes typed query_response_body. No raw DB handle
or transport object in serialized records. Preserve intentional nullable outcome headers when
converting to Requests responses; do not change the shared v1/v1.1 converter or add old-schema code.

Public operations, abbreviated concrete names (P30 additionally exposes four read-only
current-record properties on the full Store only; query-only capability stays unchanged):

```python
class QueryOnlyStoreProperty(Protocol):
    def query(self, request: QueryRequestRecord) -> ResponseRecordPromise[QueryResponseRecord]: ...

class FullStoreProperty(QueryOnlyStoreProperty, Protocol):
    def pull(self, request: PullRequestRecord) -> ResponseRecordPromise[PullResponseRecord]: ...
    def push(self, request: PushRequestRecord) -> ResponseRecordPromise[PushResponseRecord]: ...
    def run_outcome(self, request: RunOutcomeRequestRecord) -> ResponseRecordPromise[RunOutcomeResponseRecord]: ...
```

The real architecture protocols use the corresponding component record/promise protocols.
Private constructors/lifecycle/SQL/append/readback/validation/materialization helpers remain
private; public Store operations are exactly these four, plus P30's read-only properties.
Query-only object actually has only
query, not a cast or full object hidden solely behind a narrower annotation.

Initialization overloads in the EXISTING Store module, preserving confirmation/hash/lock rules:

```python
@overload
def initialize_backend_store(
    runtime: AiAugmentBackendContext, *, ipc_only: Literal[True],
) -> AbstractContextManager[AiAugmentQueryBackendStore]: ...

@overload
def initialize_backend_store(
    runtime: AiAugmentBackendContext, *, ipc_only: Literal[False],
    new: bool, confirmed: bool, confirm_replay: Callable[[], bool],
) -> AbstractContextManager[AiAugmentBackendStore]: ...
```

One actual query-only wrapper, with its engine reference private, suffices; no hierarchy of
services. Config still registers/verifies resources but no longer exposes a full Store instance
before mode selection. Construct the owned Store at server lifecycle entry from those resources;
pass only selected capability to adapters. This requires the local ai_augment_config.py field/
construction removal and necessary runtime callpoint wiring. No JSON config/CLI change.
IPC-only still ignores new/resume flags, does not initialize DB, append-preflight or promote hashes.
Full new/resume/continue prompts, optional nonempty replay confirmation, permissions, process
lock and clean-close acknowledgment stay unchanged. No public Store open/execute/etc. loophole.
Construct config/source runtime once per server lifetime; mode-selected Store lives inside
the corresponding server context. No duplicate context/resource construction.

### Adapter/server snippets and boundary

API preserves current response selection/timing. It creates app RequestRecords from Requests
objects. Schematic accepted-push branch (new helper names are reviewable wiring, not extra Store
methods):

```python
promise = await asyncio.to_thread(store.push, request_record)
if promise.acknowledgment is BackendStoreAcknowledgment.NAK:
    response_record, error = await promise.response_record()
    if error is not None:
        error.raise_exception()
    raise BackendStoreException(Locale.PUSH_NAK_ERROR_MISSING)

# Register before serving 202; task updates pull state before leaving the gate.
register_processing(finish_push(promise))
return accepted_response
```

The candidate202 exchange in request_record is what was durably logged; ACK does not select
202 for a request whose existing API response decision was409/500. Later Store errors are
raised by the tracked completion task and retain existing fatal handling, never dropped.

```python
async def finish_push(promise: ResponseRecordPromise[PushResponseRecord]) -> None:
    response_record, error = await promise.response_record()
    if error is not None:
        error.raise_exception()
    if response_record is None:
        raise BackendStoreException(Locale.PUSH_RESPONSE_RECORD_MISSING)
    update_pull_state(response_record)
```

IPC requires NAK and resolves the same tuple before transport conversion:

```python
if promise.acknowledgment is not BackendStoreAcknowledgment.NAK:
    raise BackendStoreException(Locale.IPC_REQUEST_UNEXPECTEDLY_PERSISTED)
response_record, error = await promise.response_record()
if error is not None:
    error.raise_exception()
if response_record is None:
    raise BackendStoreException(Locale.IPC_RESPONSE_MISSING)
return response_record.to_response()
```

Move ONLY actual transport glue to server.py: FastAPI app/route registration and raw
ASGI request/response conversion; Flask app/route registration, _DashboardQueryApp and
Unix-socket start/stop/serve wrappers currently in protected IPC. Preserve route metadata,
OpenAPI output, socket permissions, signals and clean shutdown. Update direct test/import
callpoints rather than leaving compatibility aliases. API workflow input/session startup
remains its helper, called by server; evidence/validation algorithms are not part of this
transport move. Eliminate _AuthoritativeHttpMiddleware's independent persistence path once
Store operations own it, not a second append on top of the new flow.

Server receives Requests Response and serves status/headers/body unchanged. Retain separate
FastAPI and single-threaded Flask; gate ALL IPC including OPTIONS before Store work, through
response. Existing server-owned gate/bridge/shutdown offload can remain narrowly adapted:
wait for active HTTP exchanges plus registered API completion/pull-state-update tasks, prevent a
new HTTP request slipping through IPC admission, release on failures. No priority queue or
threaded Flask. Client timeout is explicitly allowed and never cancels durable work. No
need to reimplement the gate merely to make it shorter.
Keep the explicit IPC docstring: clients may time out while IPC waits for FastAPI and its
tracked processing to finish; their timeout does not cancel durable Backend work. Single-threaded
IPC naturally serializes outcome/query; no outcome-over-query overtaking policy. Shutdown drains
tracked processing through the pull-state update and responses, stops/joins transports without
blocking the server event loop, closes Store, then emits the existing clean-close acknowledgment
and releases the process lock. No public Store finish/poll operation or client-owned task lifetime.

### Grouped replay and outcome changes — not hidden in a protocol-only patch

Keep private append/fsync separate from common application; separate durable append
position from committed projection
position so an ACK can precede group completion. Keep exact raw bytes, SHA256, ordinals and
anchor coverage. Group an accepted202 push through its matching commit/provider/validate
records, preserving interleaved /pull503 and rejected /push409 records in append order.
Domain invalidity is a completed recorded validation, not a missing validation record.
Incomplete group on explicit replay fails at the originating push; no recovery/network.

Common group application uses ONE outer DB transaction; per-record applicators no longer
independently commit it. Provider rows may be provisionally inserted/read inside this
transaction before model validation, then all group rows become committed together. Do not
hold the append/DB mutex across external provider wait in a way that prevents current busy503
responses. An interleaved public exchange can enlist in the active group; it must not open
a competing/nested transaction or independently commit it. Query/outcome remain gated out.
This concurrency/cursor wiring is implemented and covered by the P25 checks below.

Rejected validation discards its rejected derived effects. Grouped rollback must
retain/reinsert ALL group raw HTTP rows/hashes/ordinals,
not only /validate, plus the recorded attempt, without retaining rejected derived output.
Preserve existing evidence/retry algorithms and which domain effects are retained. Final
accepted innerdicts still wait for outcome, as P24 specifies.

P30 supersedes historical latest-by-session reference searches here: outcome uses the
Store-owned current records and explicit session/ETag checks. It still checks persisted
reference consistency without reapplying side effects, and constructs response with
commit_record_id, validation_record_id and run_outcome_record_id, appends/fsyncs, then
projects outcome/materializes in the same
transaction before exposing success. Exact self ID is the exchange UUID, not a second UUID.
The exact additions to the existing RunOutcomeResponseBody are:

```python
commit_record_id: UUID | None
validation_record_id: UUID | None
run_outcome_record_id: UUID
```

These are required current fields (nullable references where genuinely absent), not defaults
or old-schema fallbacks. Update the corresponding protocol/DTO/readback consumers together.
Rejected409 is logged/history only: no finalization and no late-validation fence. Update P24
applicator/snapshot invariants accordingly, retaining all accepted rows/multiple commit links
and not choosing a different researcher's/session's latest commit. No synthetic missing data.

Approved outcome/record decisions (included in the accepted exact scope):

1. Preserve complete pull/push exchange envelopes as above, rather than add request-only logs.
2. With P30's current-record/session selection and completed ETag check replacing historical
   selection: /completed200 only for a replay-consistent ACCEPTED validation; /failed200 when
   that current matching result is absent/not accepted
   (including replay-consistent rejected validation),
   otherwise409. Missing evidence is distinct from corrupt persisted evidence/DB, which
   remains a Store error. /cancelled requires no commit/validation. Existing capture failures
   remain separate from domain409; do not silently drop their500/history behavior.
3. P30 replaces latest-matching scans with Store-owned current commit/validation references
   and their exact link; its full outcome-envelope field replaces commit-centric innerdict
   metadata. Do not overwrite earlier finalized data or silently broaden/narrow acceptance
   eligibility. All body/DTO/protocol validators and query consumers must agree; no fallback
   for missing current fields. See P30 for the precise metadata/state boundary.
4. Dashboard's one-pull503=>failed policy is unchanged: if Store finishes successfully while
   outcome waits, /failed may then409. No automatic reclassification/retry/extra query is authorized.

### File boundary and upstream verification

Latest narrow operator corrections (2026-09-18): within P25 only, HTTP status decisions,
parameters/return annotations and newly changed comparisons must use HTTPStatus, not plain
int/numeric literals. Preserve the shared v1/v1.1 serialized numeric field contract; convert
at the typed boundary rather than change that shared schema. Move P25's hardcoded exception
and operator-facing log messages to the appropriate existing locale.py, preserving wording
and behavior. No unrelated codebase-wide status/localization refactor is authorized.

Existing production files: protected architecture.py, backend API/server/Store and config,
protected IPC, run_outcome_record.py, query_response.py; necessary concrete context typing/
initialization callpoints; Dashboard snapshot/run-outcome DTO consumers ONLY as needed to
understand outcome IDs/409 without treating rejection as finalization. No UI layout/queue/
render/export redesign or extra query. Apply P28's explicit outcome response rename and
P30's narrowly authorized outcome-envelope metadata and ETag/sender wiring; retain dump-only
rendering rather than the superseded separate card-ID presentation.
New small modules only: response_record_promise.py and request_response_records.py under
existing Backend helpers/data_models. Keep private Store lifecycle/query-only implementation
in its current module. Necessary imports/calls/tests only; no broad module reorganization.

Existing relevant tests: test_api, test_ipc, test_backend_store, test_http_interceptor,
startup cases in test_ui and isolated browser/operator fixture callpoints affected by Store
construction. Test real synthetic Store/log/DB and transport adapters, not source-string tests.
Cover all ACK/NAK/result combinations; fsync/request/response/projection failures; early202
and later pull update; callback failure/shutdown/client disconnect; read-only no-write query;
actual query-only capability; grouped exact-byte live/replay equivalence including interleaved
503/409 and rejected validation; truncated groups; outcome200/409/cancellation; finalization
IDs and pure cards. Test existing IPC gate with real in-process ASGI/WSGI and background tasks.
Run applicable Ruff/strict mypy without casts/suppressions and existing meaningful regressions.
Real socket/browser/operator verification is a separate boundary; no live Codex needed to
catch these contract errors. Do not alter ordinary tasks or touch production artifacts.

Excluded: shared HttpRequestLogRecord v1/v1.1 implementation, pasted models/StrictModel,
main pipeline/other detours, sample_deploy, TASK/HUMANS/README, CAS layout, hash/config auto-
updates, compatibility/migration/fallbacks, recovery, wrapper tasks, unrelated operator fixes.
Grouped persistence and the request/response API are implemented; P26-P30 are separate pending additions.

### Latest approved P25 test-helper correction

Operator approved exactly these separate ownership entry points, not a Path | Store union:

```python
def logical_database_snapshot(path: Path) -> DatabaseSnapshot:
    # Own a read-only connection; close it before returning.
    ...

def store_database_snapshot(store: AiAugmentBackendStore) -> DatabaseSnapshot:
    # Read through Store; do not open or close a connection.
    ...
```

DatabaseSnapshot only names the existing return type. Both delegate to one private snapshot
builder receiving a row-fetching callable. No isinstance dispatch, new model, changed SQL/
assertion or production API. Update only the corresponding test callpoints. Implemented;
existing snapshot/replay checks passed2 in25.84s.

## P25 execution checkpoint

- Completed instruction: P25 only, including the approved snapshot helper split.
  P26-P30 remain separately pending. Do not implement their changes silently or reintroduce
  their superseded historical selection/card rules as the final design. Operator has staged
  in-progress files; preserve the index and signed human comments.
- Production wiring is implemented: four Store operations/private lifecycle/SQL; actual
  query-only capability; ACK/NAK promises and grouped push projection; Requests adapter and
  server transport/admission; outcome IDs/409 handling; necessary config/consumer wiring.
  Evidence/retry algorithms stay in API helpers called by Store. No shared HTTP-schema,
  CAS, ordinary-task, pasted-model or unrelated operator correction.
- Architecture owns StoreAcknowledgmentProperty and ResponseRecordPromiseResultProperty;
  concrete implementations remain downstream. The result alias's human-signed Annotated
  comment/import is preserved. Explicit promise @implements checks the tuple return through
  method compatibility. New record/capability/exception/enum protocols have downstream
  @implements; P28 separately removes the redundant Pull common-base decorators.
- Enum comparisons use BackendStoreAcknowledgment.ACK/NAK, not raw .value strings. P25
  status decisions/constructor annotations use HTTPStatus; shared numeric wire fields stay.
  P26/P27 typed construction/content types and full literal audit remain pending.
- Actual fsync -> readback failure now preserves ACK plus error (never NAK). Grouped raw
  records/hashes/ordinals survive rejected-derived-effects rollback. Busy503 and rejected409
  can enlist during provider capture; IPC waits through HTTP and tracked pull-state update.
- Existing tests now call actual Request/Response/Store boundaries, not removed middleware,
  config.backend_store or _apply_log_record. Snapshot helpers have separate Path/read-only
  and Store-owned entry points, sharing unchanged SQL/assertions (2passed25.84s).
- test_run_outcome_http_exchange_is_logged_and_replays_as_raw_history remains. Its obsolete
  fake-Store/two-case parametrization became all three paths x complete/incomplete capture,
  exercising real IPC/Store/log/DB/replay (6passed48.24s). No accepted validation means
  completed409, not200. Separate materialization matrix covers accepted completed200.
  Exact canonical headers, full serialized envelope, typed body, live/replay query JSON,
  logical DB and unchanged replay bytes are checked. Initial header/base-subclass equality
  test errors were corrected without weakening the stored-record assertions.
- Real early202/durable push/interleaved503/final commit-validation and captured provenance
  checks passed2 in35.52s. The adapter-before-send test exposed a missing nonaccepted-push
  record-UUID log; restored one message via Backend Locale, retaining assertions (2passed).
- Latest additional boundary selection:17passed45.49s. Covers outcome NAK with response fsync/
  projection failure and no usable result; Store-owned completion surviving waiter cancellation;
  incomplete groups ending after push/commit failing at originating replay line2 without
  projection/recovery; provider capture allowing interleaved503/409; actual accepted-push
  completion after client cancellation/response-send failure; successful public outcome200,
  linked IDs and materialization. No real provider/SSH/network calls.
- Fresh static checks: Ruff PASS, full strict mypy PASS56files, git diff whitespace PASS.
  Initial mypy182/105/37/7/1-error migration checkpoints are superseded by this pass.
  Initial broad API check167pass/1skip/2fail/1error: one adjacent action parametrization was
  accidentally lost during migration (restored exactly); closed Store now raises the typed
  runtime-unavailable error under mode-specific construction; provenance test used the wrong
  fixture object's session member (fixed). All five affected cases then passed10.60s.
-410 hang: bounded45s diagnostic showed only main-thread selector polling during Runner
  cleanup, not a Store-lock worker. Moved existing explicit threaded_loop fixture from
  test_ipc to protected pytest plugin and reused it for new async/offloaded test callpoints;
  unchanged410 timeout/assertions now pass1 in4.99s. Timer drives cross-thread callbacks
  through executor cleanup; no production timing/locking change, fallback or skip.
- Final diff audit: current API/IPC adapters no longer reference config.backend_store,
  removed middleware or _apply_log_record; direct detour-DB handles remain inside Store/
  its resource, with source-DB reads explicitly readonly. No new cast/type suppression or
  acknowledgment.value comparison. AST comparison found only the two obsolete middleware
  tests replaced by the actual adapter test; other parametrizations retained except the
  documented outcome matrix and HTTPStatus enum migration. The accidentally lost unrelated
  action parametrization is restored. Human-signed promise alias comment remains unchanged.
  Paused/excluded protected BDD still references api.app and the removed middleware; it is
  outside this implementation/test scope and was not changed or run. No compatibility alias.
- Earlier focused P25 evidence: Store integrity/startup26passed33.83s; initial public
  operations7passed7.87s; interceptor/group33passed71.75s; IPC22passed2.99s; Store/IPC56passed
 69.74s (overlapping selections, not additive). Real socket/historical capture exclusions
  remain; historical callpoints updated statically, never executed/accessed.
- Combined feasible API/Store/interceptor/IPC/UI regression:379passed,1existing skip,
 102deselected in273.33s. Deselections cover subprocess/browser/socket/historical boundaries.
  Startup subprocess batch stopped after5 failures: two migrated named child helpers used
  relative imports despite being executed standalone. Corrected to absolute imports; focused
  bootstrap then reached clean Store closure but timed out in the async query check. Reused
  the existing test-only ticking Runner through a shared context helper for standalone child
  callers as well as the explicit fixture; unchanged timeouts, real adapters/offload retained.
  Bootstrap, all four ready modes and completed-query fixture recheck:6passed46.08s.
  Remaining startup-condition/confirmation matrix:87passed,25deselected443.65s. Also moved the completed-
  query helper's HTTPStatus import inside its standalone body and added a browser-free test
  executing that actual fixture and checking its queryable linked history. P25 baseline is
  implemented and locally verified. Browser/root/live-Codex/operator acceptance is not claimed; remaining
  independent production findings are recorded below.
- Delegated check completed (2026-09-18): reviewed elevate.log; both existing tests PASS,
  2passed43.48s, command exit0: real0600 Unix-socket query/cleanup and real browser/owned
  IPC wholesale-query. Browser setup10.56s/call30.24s; repeated missing-socket readiness
  polls eventually succeed, no timeout/interruption. Snapshot307researchers/1attempt/1outcome
  replaces storage only after Backend clean-close acknowledgment/exit0; Dashboard exits0.
  Uses explicitly selected Playwright Chromium (installs only its headless shell), isolated
  test storage, existing timeouts/assertions and detailed elevate.log/FAILED grep/status.
  No live Codex, provider or sudo tests; ordinary tasks unchanged.
  P25's targeted real-transport check now passes, but does not resolve browser-test placement,
  root watcher access or the live-operator pre-start hang. Full acceptance
  readiness remains unestablished; recommend resolving those known independent blockers
  before another expensive pre-commit-operator run. P26-P30 still pending. Local preparation:
  TOML/shell syntax PASS, both exact nodes collected (2tests3.42s), diff whitespace PASS;
  collection is not an execution pass.

## P26 — Approved, pending: typed record construction and Backend content types

Operator approved the explicit QueryResponseRecord constructor/factory shown in chat,
including rejection of a missing receipt timestamp instead of inventing zero duration.
Operator then approved a narrow addition: represent the content types used by these
request/response paths with a StrEnum in protected/src/backend/helpers/vars.py and wire it
through all P25 RequestRecord/ResponseRecord construction/consumer paths. This supersedes
the proposed standalone JSON_MEDIA_TYPE constant, not P25's persistence/lifecycle contract.

Scope:

- Explicit typed model construction with named arguments, not model_dump dictionary merges
  or string-key overrides, for the request/response records introduced/rewired by P25.
  Keep route-owned envelope decisions in the corresponding record constructor/factory;
  Store orchestrates operations and passes typed inputs. No generic builder/service layer,
  model_construct validation bypass, cast, compatibility alias or schema fallback.
- Explicit operator-flagged instance, covered by P26/P27 rather than a new scope item:
  RunOutcomeRecord.to_response (RunOutcomeResponseRecord after P28) currently reconstructs
  an HTTP record via self.model_dump() | {"response_headers": ...}, then sets literal
  "Content-Type"/"application/json" on the converted response. Replace this shape with
  explicit typed construction and the authoritative header constant/ContentType.JSON;
  keep the response-specific header decision owned by the response model. Any temporary
  transport-envelope adaptation must leave the durable record and its intentional nullable
  headers unchanged. Reuse the existing shared HTTP converter; no shared-schema change.
- One ContentType StrEnum and authoritative Content-Type header-name constant in existing
  Backend vars.py. Wire relevant API/IPC/server/record constants, comparisons and helper
  annotations to enum members; update their direct test/import callpoints. No raw-string
  enum comparisons or duplicated application media-type definitions in these paths.
- Preserve actual wire values and charset behavior, including NDJSON/Markdown UTF8 responses
  and existing JSON/plain-text responses. Do not add headers to synthetic /commit or
  /validate or change intentional nullable outcome headers in durable records. Do not
  coerce/restrict captured external-provider headers to this application enum.
- Existing protected Backend locale.py owns the missing-timestamp error. Preserve HTTPStatus,
  request ACK/NAK, complete-exchange serialization, response timing and query's no-write rule.
- Only necessary record/helper/callpoint/test changes within P25 plus Backend vars/locale;
  no shared HttpRequestLogRecord/Protocol v1/v1.1 schema change, unrelated media-type cleanup,
  Dashboard redesign, new module or new endpoint.

Exact enum/constant shape for the currently used application content types:

```python
# protected/src/backend/helpers/vars.py
from enum import StrEnum
from typing import Final

HTTP_CONTENT_TYPE_HEADER: Final = "Content-Type"


class ContentType(StrEnum):
    JSON = "application/json"
    NDJSON = "application/x-ndjson"
    MARKDOWN = "text/markdown"
    PLAIN_TEXT = "text/plain"
    NDJSON_UTF8 = "application/x-ndjson; charset=utf-8"
    MARKDOWN_UTF8 = "text/markdown; charset=utf-8"
```

The UTF8 members retain the existing complete header values; base members are used where
the existing code checks the media type without parameters. These are not new response formats.

Approved query factory, retaining existing fields and validators on QueryResponseRecord:

```python
@classmethod
def from_query_request(
    cls,
    request: QueryRequestRecord,
    *,
    body: QueryResponse,
    ready_to_respond_at_unix_usec: int,
) -> Self:
    received = request.received_at_unix_usec
    if received is None:
        raise ValueError(Locale.QUERY_REQUEST_RECEIPT_TIME_MISSING)

    return cls(
        schema_version=request.schema_version,
        record_id=request.record_id,
        method=request.method,
        scheme=request.scheme,
        host=request.host,
        port=request.port,
        path=request.path,
        query=request.query,
        request_headers=request.request_headers,
        request_body=request.request_body,
        response_code=HTTPStatus.OK,
        response_headers={HTTP_CONTENT_TYPE_HEADER: ContentType.JSON},
        response_body=body.model_dump_json(),
        received_at_unix_usec=received,
        ready_to_respond_at_unix_usec=ready_to_respond_at_unix_usec,
        duration_usec=ready_to_respond_at_unix_usec - received,
        query_response_body=body,
    )
```

```python
# Existing Backend Locale:
QUERY_REQUEST_RECEIPT_TIME_MISSING: Final = (
    "Query request receipt time is missing"
)

# Store query operation; existing promise/error handling remains:
selected = QueryRequestRecord.model_validate(request, from_attributes=True)
snapshot = self._query_snapshot()
response = QueryResponseRecord.from_query_request(
    selected,
    body=snapshot,
    ready_to_respond_at_unix_usec=time.time_ns() // NANOSECONDS_PER_MICROSECOND,
)
```

Wire the same enum into P25's response helper, retaining all other arguments and behavior:

```python
def _response(
    request: requests.PreparedRequest,
    code: HTTPStatus,
    body: str = "",
    *,
    content_type: ContentType | None = None,
    headers: Mapping[str, str] | None = None,
) -> requests.Response:
    # Existing response assembly remains; its header assignment uses:
    # response.headers[HTTP_CONTENT_TYPE_HEADER] = content_type
    ...
```

Verification: existing real record/adapter/Store tests must retain the same wire codes,
headers, bodies and persistence behavior; cover query receipt time0 (valid) versus None
(error), exact response duration and continued read-only query behavior. Ruff/strict mypy
for affected paths. No source-string tests or relaxed assertions/prerequisites.

## P27 — Approved, pending: P25 literal audit and authoritative definitions

Exact narrow operator instruction:

> "1.1" literal has an authoritative global in vars. you must add, as another approved
> narrow scope addition, grep of all changes introduced in P25 for literal quot marks
> single and double and each must be really justified if inline. there needs to be balance:
> if this already exists in vars or locale, ofc use it. if it's truly globabl/reusable, put
> in vars or locale as appropriate. all text messages should ofc go to lcoale. this must
> be enforced.

Execution and acceptance, limited to that instruction:

- Grep/rg all changes introduced by P25 for both single- and double-quoted literals,
  including multiline/f-string forms; inspect both staged and unstaged changes and the
  affected surrounding code. Do not audit only exception messages or only the unstaged diff.
- For every occurrence, first check existing authoritative vars/locale definitions and
  reuse them when available. No duplicate constant or raw literal in their place.
- If a value is genuinely global/reusable and lacks an authoritative definition, place it
  in the appropriate existing vars.py or locale.py and wire the in-scope consumers to it.
  All text messages go to the appropriate locale.py. Preserve text and runtime behavior.
- Retain inline literals only with a concrete justification. Exercise balance: do not
  mechanically extract every quote into a global. Record audit coverage and the rationale
  for retained inline occurrences in WORK; identical uses may share a rationale only when
  it genuinely covers each occurrence. P27 is not complete until every occurrence is covered.
- Integrate with P26's ContentType enum, not a parallel media-type constant scheme. Preserve
  P25's HTTPStatus/ACK/NAK typing and all existing shared HTTP-record wire/schema contracts.
- Scope is P25-introduced changes and necessary definitions/imports/direct callpoints only;
  no unrelated repository-wide literal cleanup, behavioral redesign, compatibility fallback,
  new lint framework or source-string tests. Preserve operator staging/human-signed comments.

Confirmed authoritative definition: src/helpers/vars.py already declares
KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1. Import/use it in the affected construction and
validation paths; do not redefine it or change shared HttpRequestLogRecord behavior:

```python
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

# Named HTTP-record construction argument:
schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,

# Existing schema validation condition:
record.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
```

Recheck the changed literals after corrections and run affected Ruff/strict mypy and
existing relevant behavior tests. This is an enforced completion review, not a claim that
the earlier partial Locale migration already satisfied it.

## P28 — Approved, pending: centralized request/response/body protocols

Exact narrow operator direction: specific request record properties inherit
BackendComponent.RequestRecordProperty and Protocol; apply the corresponding rule to
response records. Do not duplicate the common-base @implements on downstream classes.
All specific request/response properties and existing body properties belong directly
under BackendComponent for consistent ownership. Latest explicit operator correction:
RunOutcomeRecordProperty becomes RunOutcomeResponseRecordProperty and its concrete model
RunOutcomeRecord becomes RunOutcomeResponseRecord. This supersedes the earlier instruction
to retain P21's name; the existing model/contract is renamed, not duplicated.

Current finding: Pull/Push/Query/RunOutcomeRequest record protocols already inherit the
appropriate common base plus Protocol. The additional downstream Pull base decorators
therefore add no required check. Commit/Validation record protocols currently inherit
the shared HTTP protocol directly; RunOutcomeRecordProperty is still nested in a port.

Approved implementation boundary:

- Keep common RequestRecordProperty/ResponseRecordProperty under BackendComponent, retaining
  their HttpRequestLogRecordProtocol and component-property bases.
- Every specific request record protocol inherits RequestRecordProperty plus Protocol;
  every specific response record protocol inherits ResponseRecordProperty plus Protocol.
  This includes existing synthetic CommitRecordProperty and ValidationRecordProperty as
  request records, and RunOutcomeResponseRecordProperty as the outcome response record.
  Preserve members/signatures and all other names; no duplicate response-record model.
- Keep only the specific record @implements on each concrete downstream model. Its protocol
  inheritance supplies the common contract. Retain required decorators on body implementations
  and other unrelated protocols; this is not removal of structural conformance checking.
- Centralize existing request/response/body protocols directly in BackendComponent. Apart
  from the explicit outcome response rename, keep existing names; update annotations,
  references/imports and downstream @implements together.
  No old-path aliases or duplicate definitions. In particular, move:

| Existing property location | Authoritative location |
|---|---|
| BackendComponent.ControlCentrePort.RunOutcomeRecordProperty | BackendComponent.RunOutcomeResponseRecordProperty |
| BackendComponent.ControlCentrePort.RunOutcomeResponseBodyProperty | BackendComponent.RunOutcomeResponseBodyProperty |
| BackendComponent.ControlCentrePort.QueryResponseProperty | BackendComponent.QueryResponseProperty |
| ControlCentreComponent.BackendPort.QueryRequestProperty | BackendComponent.QueryRequestProperty |
| ControlCentreComponent.BackendPort.RunOutcomeRequestProperty | BackendComponent.RunOutcomeRequestProperty |

- CommitRequestBodyProperty and ValidationRequestBodyProperty already reside directly under
  BackendComponent; retain that ownership. Existing body/client-request properties remain
  their existing contracts, not HTTP-record envelopes: do not invent HTTP fields or force
  a body/parameterless outbound QueryRequest to inherit a record protocol. Use the existing
  component-property base plus Protocol when moving a property out of a port.
- Rename the concrete model to RunOutcomeResponseRecord and update every direct producer,
  consumer, annotation, promise specialization, import, decorator and affected test. Do not
  retain aliases for either old name. Keep current module location and serialized field
  names (including run_outcome_records); this is a Python model/protocol naming correction,
  not a wire-format or lifecycle change.
- No unrelated port/domain-property relocation, concrete-model module move, protocol rename,
  wire/schema/default change, new abstraction or behavior change. This explicitly authorizes
  only the listed ownership/inheritance corrections, explicit outcome response rename and
  necessary direct callpoints/tests.

Representative approved shape (existing members omitted here remain unchanged):

```python
class BackendComponent(ComponentProtocol, Protocol):
    class RequestRecordProperty(
        HttpRequestLogRecordProtocol, ComponentProtocol.PropertyProtocol, Protocol,
    ):
        pass

    class ResponseRecordProperty(
        HttpRequestLogRecordProtocol, ComponentProtocol.PropertyProtocol, Protocol,
    ):
        pass

    class PullRequestRecordProperty(RequestRecordProperty, Protocol):
        pass

    class PullResponseRecordProperty(ResponseRecordProperty, Protocol):
        @property
        def pull_response_body(self) -> str: ...

    class CommitRecordProperty(RequestRecordProperty, Protocol):
        ...  # Retain all existing members.

    class ValidationRecordProperty(RequestRecordProperty, Protocol):
        ...  # Retain all existing members.

    class RunOutcomeResponseBodyProperty(ComponentProtocol.PropertyProtocol, Protocol):
        ...  # Retain all existing members.

    class RunOutcomeResponseRecordProperty(ResponseRecordProperty, Protocol):
        @property
        def run_outcome_request(self) -> BackendComponent.RunOutcomeRequestProperty: ...

        @property
        def run_outcome_response_body(
            self,
        ) -> BackendComponent.RunOutcomeResponseBodyProperty: ...

        ...  # Retain the other existing members.
```

Within the BackendComponent class body, unqualified nested base names above refer to the
same component-owned protocols. Downstream declarations become:

```python
@implements[BackendComponent.PullRequestRecordProperty]()
class PullRequestRecord(HttpRequestLogRecord):
    ...  # Existing implementation unchanged.

@implements[BackendComponent.PullResponseRecordProperty]()
class PullResponseRecord(HttpRequestLogRecord):
    ...  # Existing implementation unchanged.

@implements[BackendComponent.RunOutcomeResponseRecordProperty]()
class RunOutcomeResponseRecord(HttpRequestLogRecord):
    ...  # Existing implementation unchanged.

@implements[BackendComponent.RunOutcomeResponseBodyProperty]()
class RunOutcomeResponseBody(FrozenStrictModel):
    ...  # Existing implementation unchanged.
```

Apply the same ownership to QueryResponse/QueryRequest/RunOutcomeRequest conformance checks
and update Store promise/query-body annotations to the direct BackendComponent paths.
Verify with strict mypy/Ruff and existing affected record/adapter tests; no casts, type
suppressions, source-string tests or weakening of member signatures.

## P29 — Approved, pending: original pull record ID naming

Operator authorized the narrow rename of Backend retry bookkeeping's run_id to
original_pull_record_id. This is the existing original_pull.record_id, NOT Dashboard's
UUIDv7 run ID or the Codex session ID. No new identifier or linkage contract is introduced.

Meaning verified in api.py: _original_pull_record starts with the commit's linked pull.
For a Markdown retry pull it follows the latest preceding projected commit's linked pull
recursively; _namekey_from_original_pull then requires the resolved initial-task record to
be HTTP200, NDJSON and nonempty, and checks its researcher identity at the caller. Retry
Markdown pulls are also HTTP200: status200 alone does not identify the original. Nor does
original mean the first-ever200 in the log: repeated initial-task pulls have distinct UUIDs,
and the commit's linked pull determines which is used. This describes the current code,
not the desired P30 contour: P29 itself is only a rename, but the later P30 explicitly
supersedes retaining this heuristic and authorizes re-hooking its related machinery.

Exact narrow change boundary:

- In src/backend/api.py rename CODEX_RETRY_RUN_ID_COL to
  CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL and its column value from run_id to
  original_pull_record_id in both CODEX_RETRY_BASELINE_TABLE and CODEX_EVIDENCE_AUDIT_TABLE.
  Update all direct DDL/insert/select/returning/filter references through the constant.
  Preserve types, constraints, values and retry grouping/evidence behavior.
- Rename run_id_text to original_pull_record_id_text in _process_retry_attempt.
  Rename corresponding Backend test helper arguments, fixture constants/locals and direct
  assertions/import references where they denote this pull UUID. Leave unrelated run IDs
  untouched. Existing original_pull record-object arguments already describe their content.
- No Dashboard run-event/queue/storage/protocol changes, new backend-disclosed Dashboard ID,
  replay-log wire change, runtime identifier generation change or broader naming cleanup.
- Current schema only: no old-column alias, migration, fallback or automatic DB repair.
  Existing explicit --new/replay machinery remains the way to build the current schema.

Approved rename shape (existing surrounding logic remains):

```python
CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL = "original_pull_record_id"

# In _process_retry_attempt:
original_pull_record_id_text = str(original_pull.record_id)
```

Wire the renamed column constant and local through their existing SQL/parameter callpoints;
no SQL algorithm rewrite under P29 alone (P30's explicit linkage rewiring is additional).
Verify existing synthetic retry-baseline/evidence tests and affected
Ruff/strict mypy checks. Historical capture fixtures remain unexecuted/inaccessible. Check
that Backend retry references no longer use the misleading name, without renaming legitimate
Dashboard run_id fields. Status: approved, pending; documentation only in this turn.

## P30 — Approved, pending: Store-owned current records and session outcome linkage

Approval sequence: operator specified explicit pull -> commit -> validation linkage, a
session-scoped outcome with Session-ID confirmation and a completed-only ETag handshake,
and outcome-response-record innerdict metadata. Operator then corrected ownership: current
records belong to Backend Store, not API globals; expose actual model instances, not just
UUIDs, by reference without deepcopy. Assistant restated persist/fsync -> DB projection ->
typed DB readback before exposure; operator approved recording this shape. Latest explicit
addition: original_pull_record_id and its related machinery must be re-hooked to this model
in this same P. Status: approved, pending; this turn edits documentation only.

### Current record ownership and access

- Full Store owns current_pull_record, current_push_record, current_commit_record and
  current_validation_record. Each is a read-only property returning the actual typed record
  instance or None when absent; no detached/deep-copied object and no parallel API globals.
- Store replaces the corresponding state as records pass through the common live/replay
  processing path. Preserve the approved ordering: persist/fsync, project, construct the
  typed DB-readback record, then expose that instance. Never expose an unpersisted input
  as authoritative, or leave an aborted projection exposed as successfully applied state.
  Replay does not append/fsync again; it consumes the existing durable log into the same
  projection/readback/state-update logic. No extra replay/recovery contour.
- API/IPC consume references; they do not own/update these four slots. Existing four Store
  operations remain; these four read-only properties are the explicit narrow extension to
  P25's full-Store surface. Query-only wrapper still exposes only query.
- Initial absence is None, not a fabricated record. Preserve current initialized session
  identity: old-session records must not silently become a new session's commit/validation.
  No duplicate context/service, mutable public setter or new record-ID generation scheme.
- Preserve the accepted push's captured pull reference and the actual accepted push while
  processing it. Later/interleaved pulls or rejected pushes must not silently change that
  commit's inputs merely because a current-record slot was subsequently updated.

The preceding chat named these four properties and their behavior but contained no fenced
Python block. Do not claim an earlier verbatim code approval that did not occur. The snippet
below spells out that agreed reference-returning shape using existing persisted-record types;
pull/push are HTTP-log envelopes, not a fabricated completed PushResponseRecord requiring
commit/validation before those exist. Necessary FullStoreProperty annotations mirror these
through existing HTTP/commit/validation protocols; use @implements and no cast/type weakening.

```python
# Additions inside AiAugmentBackendStore; existing lifecycle/operations remain.
_current_pull_record: HttpRequestLogRecord | None = PrivateAttr(default=None)
_current_push_record: HttpRequestLogRecord | None = PrivateAttr(default=None)
_current_commit_record: BackendCommitRecord | None = PrivateAttr(default=None)
_current_validation_record: BackendValidationRecord | None = PrivateAttr(default=None)

@property
def current_pull_record(self) -> HttpRequestLogRecord | None:
    return self._current_pull_record

@property
def current_push_record(self) -> HttpRequestLogRecord | None:
    return self._current_push_record

@property
def current_commit_record(self) -> BackendCommitRecord | None:
    return self._current_commit_record

@property
def current_validation_record(self) -> BackendValidationRecord | None:
    return self._current_validation_record
```

This is the accessor/storage shape, not permission to bypass the existing lock, transaction,
mode or readback rules. Wire assignments into the owned common processing path, not into
these getters or the adapters; no catch-up projection from a getter.

### Explicit session, commit/validation and completed handshake

- Commit contains the latest served pull selected for the accepted push and that accepted
  push; validation identifies that exact commit UUID. Outcome concerns the current Codex
  session, not Dashboard's local run UUID and not an independently guessed retry group.
- RunOutcomeRequest retains its outcome path and NameKey header; add Session-ID, and check
  both supplied identities against the running Backend session/researcher. Dashboard passes
  its known Codex session ID, not its Dashboard run ID; manual callers must confirm likewise.
- Simplify/remove _run_outcome_references' historical scans: use Store's current commit and
  validation instances, verify their persisted counterparts and the exact validation.commit_id
  == commit.record_id linkage. No latest-by-name/session SQL guessing or replaying side effects
  merely to choose records. Replay checks the recorded explicit links in ordered Store state.
- For /completed, require ETag in RunOutcomeRequest. /pull410 alone supplies ETag equal to the
  UUID of the persisted validation on which that410 is based; no ETag on200/503/other pulls.
  Dashboard's existing single ordinary post-exit pull captures this ETag and forwards it in
  /completed. Backend compares it with current_validation_record.record_id and requires the
  matching accepted validation/commit. Preserve actual HTTP header encoding consistently;
  compare parsed UUIDs, not loose string/enum coercions.
- Session/identity/linkage/ETag inconsistency fails through the existing promise result
  (None, BackendStoreException), not silent fallback, guessed references or an invented
  successful response. Use the existing ResponseRecordPromiseResult naming/architecture
  alias; do not invent a parallel RunOutcomeResponsePromiseResult class.
- /failed and /cancelled still support legitimately absent commit/validation records;
  present-but-inconsistent references are errors. Cancellation does not require accepted
  validation or the completed ETag. Preserve the separately approved domain200/409 and
  evidence-capture500 behavior except where these explicit identity/linkage checks apply.
  If a genuinely missing session at early cancellation requires a new policy, obtain approval
  rather than fabricating an ID or silently rejecting previously supported cancellation.
- Retain NAK for outcome request persistence; required outcome response persistence precedes
  successful completion. Server gate/client-timeout tolerance and Dashboard one-pull503=>failed
  behavior stay unchanged. No extra pull/query, retry or automatic outcome reclassification.

The exact link check uses the existing models and Locale definition; surrounding Store
promise/error handling converts the raised exception to (None, exc):

```python
commit = store.current_commit_record
validation = store.current_validation_record
if validation is not None and (
    commit is None
    or validation.validation_request_body.commit_id != commit.record_id
):
    raise BackendStoreException(Locale.RUN_OUTCOME_VALIDATION_LINKAGE_CORRUPT)
```

This check does not replace the separately required session/NameKey, completed acceptance
and ETag checks, or the durable DB-readback requirement above.

### Innerdict metadata and original-pull/retry rewiring

- Replace commit-ID/commit-request-body-centric innerdict metadata with
  ktp.ai_augment_run_outcome_response_record containing the FULL serialized
  RunOutcomeResponseRecord: envelope, request headers, response body, record UUID and other
  current HTTP-log fields, not just the body or a second hand-assembled summary.
- Store persists/projects the outcome and materializes this field in the outcome transaction.
  Update only the necessary innerdict model/protocol, query snapshot validation/serialization,
  record consumers and card field wiring. Keep other researcher/evidence/result data intact.
  DOCX/TXT/card remains a dumb innerdict renderer, with no transient enrichment or extra IPC.
  No old metadata/schema alias, alternate parser, migration or fallback.
- Full outcome serialization identifies its exact commit/validation/pull/push/session and
  log/CAS evidence; it is not an embedded copy of every earlier retry/provider response.
  Do not silently imply that a reference-only outcome embeds the full evidence archive.
- Explicit latest addition: re-hook original_pull_record_id and dependent retry baseline/
  obligation/evidence bookkeeping to this Store-owned record/session model and explicit links.
  P29's rename remains; P30 supersedes preserving _original_pull_record's Markdown detection
  plus latest-preceding-commit scan. Do not retain that heuristic as a fallback or introduce
  a second parallel run identifier. Keep existing retry evidence rules and actual record
  UUIDs, and preserve live/replay agreement through the same Store processing path.
- The root link must follow authoritative captured relationships, not another researcher's
  or session's nearest record. Current record pointers alone must not erase ancestry needed
  by retry checks. Any further wire field, new root-selection policy or change in innerdict
  cardinality not specified here requires a concrete proposal/approval before implementation;
  do not invent it while implementing the required rewiring.

Exact agreed new innerdict key, defined once alongside existing Backend column constants:

```python
KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_RECORD_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}run_outcome_response_record"
)

# Value stored through the existing innerdict projection is the whole record:
outcome.model_dump_json()
```

Reuse P26 content types, P27 authoritative header/schema constants and Locale text, and P28's
RunOutcomeResponseRecord/Property names. Preserve P25 grouped durability/ACK timing and raw
HTTP history. This item does not authorize removing attempts/audit tables, replay-log records,
provider captures, existing evidence validation or unrelated UI/storage/queue behavior.

### Narrow implementation boundary and verification

Files: Store, API, IPC/server direct transport/ETag callpoints; protected architecture/Backend
vars/Locale; existing run-outcome request/response and innerdict/query/snapshot models; Dashboard
single-pull/outcome sender and pure-card metadata consumers; corresponding existing tests only.
No new public Store operation, unrelated context refactor or ordinary task changes.

Use real synthetic Store/log/DB and in-process adapters to verify: reference-returning getters
and None state; durable/readback timing and failed processing; live/replay agreement; captured
pull/push stable across interleaved requests; matching and mismatched session/NameKey/linkage;
ETag only on410, forwarded on completed, missing/wrong ETag failure; failed/cancelled legitimate
absence; full outcome envelope roundtrip in query/innerdict and unchanged dump-only export;
retry chains with repeated pulls and other-session records, no historical-nearest inference.
Update affected direct callpoints and run Ruff/strict mypy. No source-string assertions,
mocked replacement of the tested persistence boundary, skipped prerequisites or network calls.

P30 supersedes only the earlier API-global current-record ownership, historical outcome/root
selection and commit-centric innerdict metadata instructions. Remaining P25-P29 work and
unresolved operator acceptance boundaries remain pending as recorded elsewhere.

## Completed scope index

| ID | Implemented scope | Main locations |
|---|---|---|
| P1 | Exact JSONL hashes, typed table-comment anchor, independent prefix/suffix verification, safe transactional promotion | Store + replay_log.py |
| P2 | Full --new empty baseline or separately confirmed nonempty replay; strict resume never heals | server.py + Store |
| P3 | Real append-open/close preflight without writing, writable mode only | replay_log.py + Store |
| P4 | Historical verdict substitution removed; failed full-child cycle blocks unattended retry/reset | api.py + Dashboard context |
| P5 | Launcher independence; IPC-only ignores modes/bypasses initialization; full-only Dashboard bookkeeping | server.py, api.py, ui.py, context, launcher help |
| P6 | Non-locking IPC signal flag; unchanged clean-close token in protected Backend vars | ipc.py + vars.py + import points |
| P7 | Empty parameterless QueryRequestProperty; concrete outbound_http retained | protected/src/architecture.py |
| P8 | Single Start/Stop queue-processing switch, stopped at Dashboard startup | Dashboard controller/page |
| P9 | No Backend card/ZIP publishing; explicit Dashboard publish completed shares DOCX renderer | Store, api.py, ui.py |
| P10 | Dashboard background-startup failure requests normal shutdown and unsuccessful process exit | ui.py application lifecycle |
| P11 | All25 in-scope remaining detour dataclasses converted, with standalone dependency/constructor integration | Backend models, watcher/audit and corresponding test helpers |
| P12 | Missing operator-terminal logs for existing UI actions/results/errors, including probes/download/publishing | ui.py |
| P13 | Extensionless two-level SHA256 CAS shards, symlink guards and directory fsync | ai_augment_cas.py + corresponding test fixtures |
| P14 | Current lifecycle review and 111 mock-free parametrized startup-condition cases | tests/control_centre/test_ui.py |
| P15 | Operator test moves preserved; import, constant and fixture collisions corrected | test_ui.py, test_audit_read.py, test_backend_store.py |
| P16 | Markdown/TXT button shares DOCX download contour; symmetric format-specific handles/selectors | ui.py, locale.py, existing UI tests |
| P17 | Header grouping, horizontal DOCX/Markdown buttons, localized queue-processing labels | ui.py + protected Dashboard locale |
| P18 | Original operator fixture/query/queue corrections, watcher interpreter, shared lint and graph review | Approved code implemented; F4 real query/browser check passed; F3/F7 diagnostics implemented, runtime findings unresolved; F5 replacement withdrawn; production acceptance pending |
| P19 | Named subprocess helpers, shared explicit fixture and selectable markers; preserved isolation/timeouts | protected/tests/pytest_plugin.py + existing test callpoints |
| P20 | Typed /validate record/body protocols and readback, unchanged wire format | validation_event.py, architecture.py, api.py, query_response.py |
| P21 | Existing full run-outcome exchange renamed RunOutcomeRecord throughout | renamed run_outcome_record.py + direct protocol/consumer/test callpoints |
| P22 | Completed historical display-only card-ID scope; superseded by P24 | ui.py + Control Centre Locale + test_ui.py |
| P23 | Shared v1.1 HTTP-record structural protocol, model conformance and three record-protocol bases | shared http_request_log.py + protected architecture.py |
| P24 | Persisted validation/outcome IDs, outcome-triggered materialization, pure card renderer, server-owned HTTP/IPC admission | Backend API/Store/server/IPC/models; Dashboard snapshot/card callpoints |


All P1-P24 code changes are implemented (P22 superseded by P24); this is not production
acceptance or fresh P25 verification. No additional pending historical implementation is
revived. Current approved implementation is P25 plus its narrow P26-P30 additions. F7 remains an unresolved report,
not a proven task defect to patch speculatively.

## Retained contracts — baseline and P25 boundaries

### Store, integrity and startup

- Backend Store exclusively owns detour DB/replay I/O, locks, permissions and transactions;
  domain SQL/evidence algorithms remain API private helpers. Main source DB is read-only.
  Low-level Store operations become private under P25, not DB handles exposed to adapters.
- Exact JSONL bytes including LF are SHA256-hashed into detour_http_records.raw_line_sha256
  in the projection transaction. _ReplayAnchor (sha256, ordinal, byte_offset) is JSON in that
  table's DuckDB TABLE COMMENT: _write_anchor uses COMMENT ON TABLE; _verify_log_projection
  reads duckdb_tables().comment for current DB/main schema. No separate anchor table or
  detour_authoritative_projection. P25 preserves this metadata/verification mechanism.
- Resume/continue/IPC independently hash the saved prefix, verify complete ordered DB/log
  coverage and per-line suffix hashes through EOF. Same config hash never skips coverage.
  Missing/extra/gapped rows, truncated/invalid tail or anchor fail. No tail repair, catch-up,
  migration, shadow rebuild, replay fallback, automatic config update or recovery.
- Config hashes use RegisteredResource mechanics; human recalculates/updates config between
  launches. Dashboard verifies resources and deliberately passes --danger-no-verify-hash to
  owned children. Changed anchor promotion requires verification and successful append-open
  preflight and transaction; readonly IPC never promotes. Failed preflight leaves anchor intact.
- Full --new or --resume/--continue required, with default-No confirmation unless --yes.
  Nonempty --new asks a second default-No replay question BEFORE deleting old DB/WAL;
  --yes accepts both. Empty baseline uses SHA256(empty), ordinal/byte0. Explicit replay must
  reproduce recorded results without network or fabricated missing records; fail at first
  invalid record/group. P25 adds the expressly approved grouped projection contour only.
- Writable startup checks actual O_WRONLY|O_APPEND open/close without create/truncate/write,
  no-follow/same-inode, then restores0400. Retained log FD is readonly. Store alone opens
  write windows. IPC-only ignores even conflicting initialization flags, has no prompts,
  requires an existing valid DB, serves only wholesale /query and OPTIONS, and never
  rebuilds/appends/append-preflights/promotes. --config remains required in both modes.
- Full mode requires an eligible selected researcher; IPC-only does not. Both retain exclusive
  process lock, config/source construction and verification. No Backend parent watcher or
  launcher knowledge. Orphan Backend after Dashboard SIGKILL is intentionally external on
  restart: it may be borrowed, never adopted/reset/stopped. No startup automatic probe/query.
- Store closes successfully before BACKEND_STORE_CLOSED_CLEANLY is emitted; constant lives
  in protected Backend vars.py. Signal handlers remain simple non-locking flags in IPC-only.
  Full shutdown must keep the event loop alive while draining/stopping IPC/background work.
- Dashboard first owned FULL cycle uses --new --yes; only successful start AND clean stop
  permits future --resume --yes. Failed full cycle blocks unattended retry/reset. IPC-only
  and borrowed lifetimes do not affect that private instance policy. Owned stop: SIGTERM,
 10s wait then SIGKILL; clean means accepted exit + token + no forced kill. Borrowed not stopped.

### Records, validation, innerdicts and Dashboard

- Shared HttpRequestLogRecord/Protocol v1/v1.1 fields/conversion remain untouched in P25.
  Its docstring already records Response.text/UTF8 limitations and desirable raw-byte v2.
  Current provider endpoints: main OpenAlex /authors(select=id), /works(select=id,title);
  detour OpenAlex /institutions/{id}, ROR /v2/organizations/{id}, all JSON. Local /push is
  application/json; /pull also returns Markdown/NDJSON. New endpoints need individual review.
  No tagged-base64 v1.1 or v2 implementation/migration approved.
- /commit and /validate remain synthetic request-only HTTP records with null response
  fields. Typed BackendValidationRecord/body stay; P28 explicitly renames the outcome model
  to RunOutcomeResponseRecord without changing its wire shape. Validation
  contains commit ID, serialized PostCommitValidation and submission/discriminator, provider
  UUIDs. Unchanged pasted model performs intercepted validation using persisted DB-readback
  responses; no replay provider calls or swallowed replay inconsistency.
- P24 baseline: accepted output rows initially have null validation/outcome IDs; /pull410
  uses durably persisted accepted validation/submission, not final innerdicts. Only matching
  outcome application sets final IDs and materializes codex_innerdicts in its transaction.
  Query reads that table, not unfinished flat output rows. P30 supersedes the baseline's
  separate commit/validation/outcome card metadata with the full stored outcome response
  record; pure innerdict rendering remains, with no transient UI enrichment. P25 changes
  grouped transaction/response409 eligibility exactly as specified above.
- Preserve exact researcher/session/commit/validation linkage, prior finalized IDs and multiple
  eligible commits. Missing/rejected data never becomes an accepted placeholder. Cancellation
  preserves durable data and fabricates nothing. No default/schema audit outside P25 fields.
- CAS layout is extensionless <root>/ab/cd/<full SHA256>; symlink guards and fsync cover blob,
  both shards/root. Missing/corrupt blobs fail, never redownload/migrate. No P25 CAS changes.
- NiceGUI owns wholesale query snapshot independently of run journal/queue. Explicit Query IPC
  composition callback owns query capability, not controller. QueryRequestProperty remains
  parameterless; concrete outbound_http stays. No filtered/per-person, startup, repaint or
  card queries; replacement follows successful owned-child cleanup.
- Dashboard CODEX_EXITED -> one ordinary /pull:410 completed, all others including503 failed
  -> outcome IPC -> owned Backend shutdown. Cancellation separate. P25 permits /failed409
  after waiting for successful processing; no automatic retry/reclassification/extra query.
- Queue switch starts stopped each Dashboard process; Stop affects next dequeue only. Cancel
  actually stops/removes the current run and does not alter the switch/re-enqueue. Existing
  remote interrupted-run cleanup remains interactive-start-only, skipped for publishing.
- No Backend card/ZIP publication or recovery. Display and DOCX/TXT downloads share Markdown
  renderer; TXT uses raw Markdown UTF8/.txt, main-pipeline basename, symmetric handles.
  Explicit Dashboard `publish completed --config ...` shares DOCX path, stored eligible
  completed snapshot, no automatic query/Backend/queue start, normal shutdown, detailed logs.
- Layout and localized queue labels unchanged; probe/query/start-stop alongside title,
  statuses next row; DOCX then Markdown together. P25 does not redesign UI/export/queue/logging.
- In-scope dataclasses already converted: FrozenStrictModel where feasible; explicit BaseModel
  ConfigDict for mutable/opaque handles. Do not change pasted StrictModel. Standalone deployment
  installs unchanged shared architecture plus Pydantic2 in the provisioned model environment;
  no deploy/provision change under P25. sample_deploy excluded.

## Verification baseline — before P25, not evidence for the new implementation

P24's fresh local checks (overlapping selections, not additive):

| Check | Result and boundary |
|---|---|
| Live/replay outcome matrix and negative ordering/history | 12 passed (70.86s): complete/partial snapshots across completed/failed/cancelled; exact query JSON/logical DB equality, unchanged log; no-validation/rejected/no-session/other-session; two accepted commits, finalized IDs not rewritten, late validation rejected |
| Existing Store/interceptor selection | 47 passed,13 deselected (103.71s); excludes the above outcome cases and410 integration |
| Real Store/ASGI410 integration plus four card cases | 5 passed (32.00s): validation durable before410, no early innerdict, IPC waits through actual response send, validate < pull410 < outcome in durable history; card/interim-state checks |
| Gate/WSGI/lifespan composition | 21 passed,1 real-socket case deselected (9.81s): response/background wait, new-HTTP exclusion, ordinary503 availability, exception cleanup, OPTIONS/errors and real threaded bridge/shutdown |
| Factory registration plus final card-ID checks | 5 passed (7.61s); subsequent type-safe factory assertion alone1 passed (6.20s). Covers one-time outer gate registration and missing/malformed/unlinked/cross-NameKey/cross-session ID rejection |
| Existing API feasible selection | 166 passed,1 existing skip,4 deselected (80.28s). Preserved skip for currently allowed multiple evidence matches. No historical capture execution |
| Existing UI feasible selection | 84 passed,1 new negative-fixture failure (11.10s), then all four card cases passed in the focused checks above. Existing download/publishing/queue/autonomy checks passed |
| Final static checks | Ruff PASS; strict detour/shared-record mypy PASS54files; diff whitespace PASS |


P24 test-development failures were corrected without weakening production checks: real UUIDv7
negative fixture, serialized readback comparisons and typed middleware-factory assertion.
Threaded gate tests use a test-only loop timer through Runner cleanup; actual gate/ASGI/WSGI/
thread bridge executes but not real network serving. The410 case uses real Store/middleware
with an async test route around the sync pull handler. Historical capture callpoints were
updated statically, not executed/accessed. P25 needs fresh boundary checks after its edits.

Additional baseline evidence:

- P20:21 focused validation/replay/query cases; P21:21 outcome/query/UI cases; P23:53 shared
  HTTP/model cases; Ruff and strict detour mypy54files passed. Main mypy68files passed using
  designated default executable; earlier AI-stub main check had20 unrelated errors, not a pass.
- F8 IPC-only opening log fixed exactly to logger.info("Opening read-only Backend Store");
  unchanged test_main_ipc_only_runs_only_the_dashboard_query_server passed1 in1.94s after
  reproducing AttributeError from unnecessary detour_db_path access on its minimal fixture.
- Prefix verification log-only fix: one prefix summary/match, per-line messages only for
  hashed suffix;12 Store integrity cases passed. No verification/hash behavior changed.
- P14:111 real startup/confirmation cases passed in538.68s; P19 migrated to shared subprocess
  helpers. Later91-case run had90pass/1timeout, identical case passed alone unchanged7.65s;
  initial run not wholly green and timeout cause unproven. These stop before real serving.
- P19:11 subprocess cases and320 feasible nonsubprocess cases passed;102 marked subprocess,
 4 socketless lifecycle cases at that checkpoint. Names/markers may change only as direct
  P25 callpoints require; preserve case intent and isolation, no inline child Python bodies.
- P13:24 focused CAS cases; P16:7 DOCX/TXT cases; existing DOCX browser/layout cases passed
  delegated after initial startup timeouts. These do not certify browser TXT downloading.
- F1/F2: real NiceGUI persistence, early collection/child wiring, preservation guard and
  standalone watcher isolation checked. F4 actual browser/completion-helper/owned-query
  regression eventually passed47.19s after filtering5s and IPC-readiness30s timeouts;
  no timeout/assertion changes. Weak-host contention plausible, not proven cause.
- F3/F7 diagnostics:7 local cases; operator preflight23pass. Four actual-Pixi unset/stale-parent
  activation cases pass locally and PROD with15s bounds; sudo/pytest dispatch are sentinels,
  real watcher --help executes. These are not proof of nobody/root monitoring or resolution
  of the operator's original pixi-shell report.
- Mode3 approved test-only fix injects real Console(width=80), all assertions unchanged.
  Entire module6pass and actual -vv -srA PTYs80/92 both pass; production/tasks unchanged.
  Baseline aicode/staging (ef5ddef), not dc951fe. Staging source with current dependencies
  reproduces92-column wrap but does not establish historical failure; operator reports passes.

## Last full operator findings — corrections separate from P25; acceptance pending

Latest reviewed pre-commit-operator run:2026-09-18 15:37:17–15:46:13(-04),
logs/from_operator/pre-commit.log and pre-commit-extra.log. Full acceptance FAILED.
Operator explicitly requested findings independent of pending P26-P30; those approved items
remain unchanged/unimplemented. The initial review changed WORK only; correction1 was
subsequently approved and implemented below. Corrections2 and4–7 are implemented and locally verified; delegated/full verification remains pending;
correction3's approved test deletion is complete, not its original redesign. Line references below count LF lines
in the raw logs (terminal CR/ANSI sequences may affect rendered editor numbering).

| Finding in the last operator run | Evidence and present correction boundary |
|---|---|
| Live workflow blocker | Extra log4623–4629: rollout capture succeeds (856518bytes/178lines), commit and validation are persisted, but rollout_index rejects call_YiI9YVKmuEiZtIrZu1FI3vl2: “must contain exactly one eligible web action”. Pull then returns500, never410. Dashboard's ordinary final pull500 -> /failed200 follows its current contract. Recovered evidence identifies a find-only call excluded by that run's pre-fix whitelist (details below). Correction1 below implements the fix; full production acceptance has not been rerun. |
| Five stale preflight callpoints | test_operator_e2e_preflight.py:303 patches backend_ipc.start_dashboard_query_server, moved to backend_server by P25. All five then failed before exercising their behavior. Item2 now corrects the direct target/import, preserving cases/assertions; the20-case preflight run passed. No compatibility alias or production rollback. |
| Three stale elevate expectations | Same test module:344 assumes elevate always runs install+browser stages. Operator-requested idle “Nothing to elevate” correctly runs neither. The three tests failed on missing stages or expected nonzero status. Item3 deleted that parametrized test entirely; no obsolete batch or redesigned wrapper tests remain. |
| Host browser layout | pre-commit.log3267: card line-height ratio is NaN, so the compact-spacing assertion fails. Host module8passed/1failed34.11s; real query and DOCX download pass. The pre-correction test evaluated computed lineHeight/fontSize immediately after card click without content/visibility readiness; item4 now adds the exact approved readiness checks and diagnostics, pending host verification. Current CSS explicitly sets1.25; logs do not capture computed strings or element attachment, so a render/detachment race is plausible, NOT proven and not justification to relax the assertion or change production CSS blindly. |
| Full Backend shutdown evidence incomplete | Extra log5405–5415: test teardown signals Dashboard while its worker is already stopping Backend. All processes disappear, Dashboard exits0, no forced-kill report; however the full Backend clean-close token, final Uvicorn shutdown lines and Dashboard Backend-stopped log are absent. Query-only shutdown earlier has them. The prior code had a cancellation window: cancellation inside Backend._stop cleared self._process before a second stop could await it. Item5 now shields/awaits that cleanup and tests both cancellation points. The prior missing log was not proof of Store failure; full operator re-verification remains pending. |
| Normal AI suite | 578passed/8failed/1skip/3deselected/1warning116.24s. The eight failures above prevent the subsequent real OpenAlex/ROR institution test via task's &&. Do not report that provider leaf as tested. |
| Browser placement / root watcher | Routing now correctly runs Chrome tests on macOS; aicode privileged appendwatch3passed70deselected2.55s, unchanged real EACCES assertions. Earlier machine-placement/credential blockers are resolved, not reasons for this run's failures. |
| Timing / previous hang | Live case finishes1failed/2intentional skips332.21s, no Ctrl+C/KeyboardInterrupt/timeout. Full Backend starts, session supplied, Codex works for about280s before push; then failure/outcome within roughly30s. Repeated 2-record heartbeats during research are expected, not proof of a stuck Backend. The old pre-start hang did not recur; its historical cause remains unknown. |
| Preservation / prerequisite checks | Isolated NiceGUI path logged; production-data and original-NiceGUI preservation guard passes. Configured DuckDB checks pass. Actual root task starts correctly this run; the older F7 pixi-shell report remains unreproduced, not dismissed. |

Recovered-record follow-up (operator supplied tmp/run_h5f6hp6j20s6x8737ypcwxj40000gn,
explicitly authorizing read-only inspection of this recovered test run): the failing call is
now identified precisely. In BOTH captured CAS blobs, rollout lines74–76 are the function
call, web_search_end and single input_text function output for
call_YiI9YVKmuEiZtIrZu1FI3vl2. Its arguments are:

```json
{"find":[{"ref_id":"turn6search2","pattern":"Aziz Sheikh"},{"ref_id":"turn3search0","pattern":"NIHR Senior Investigator"},{"ref_id":"turn6search0","pattern":"Professorial Fellow"},{"ref_id":"turn4search3","pattern":"Languages"}],"response_length":"long"}
```

This is one find action with four searches, NOT mixed eligible actions. Before correction1,
_web_arguments counted zero because ELIGIBLE_WEB_ACTIONS contained only search_query/open/click. Event action is
find_in_page; the output has ordinary citation sections. Two result refs have valid URLs
(turn7view0/turn7view2); two are Internal Error entries with no URL (turn7view1/turn7view3),
which the existing downstream indexing logic already excludes. The entire cited rollout is
indexed before submission validation, so this action blocked the run regardless of whether
its particular excerpts are ultimately submitted. P26-P30 do not change this whitelist.

Read-only diagnostic through actual parse_rollout/build_rollout_index, using an ephemeral
pytest module and the existing isolation plugin: both captured snapshots reproduce the exact
pre-fix exception; a test-only monkeypatch adding find to ELIGIBLE_WEB_ACTIONS allowed BOTH
complete indexes:14calls/14outputs/254URL-backed refs, with exactly the two valid find refs.
4cases passed1.50s; no production file/fixture/test/task edit, provider request or writable
Store/replay operation. Temporary test module removed on completion. This verifies the narrow
candidate correction, NOT full submission acceptance or replay under changed validation rules.
The initial find-only whitelist proposal is superseded by the operator's subsequent
discussion below: unsupported actions should make evidence ineligible, not fail the whole
rollout. The diagnostic above establishes find support only, not that revised behavior.
Operator subsequently authorized correction1 below, then corrections2 and4–7 on2026-09-19,
and finally deletion of the elevate-triggering tests instead of the proposed correction3.
The existing rejected /validate record remains unchanged; changing the indexing rule can
change recomputed validation on explicit replay, so no compatibility/success claim is made.

Recovered persistence evidence:

- All10 JSONL lines are LF-terminated and validate as actual HttpRequestLogRecord v1.1.
  Read-only DuckDB has the same10 contiguous ordinals, IDs, methods, paths, full JSON payloads
  and exact LF-inclusive SHA256 hashes. Database bytes unchanged after inspection.
- Sequence:2pull200, push202, commit, validate,4pull500, failed200. One stored attempt;
  validation stage=rollout_index/result=rejected, null submission and empty provider-ID list.
  No accepted innerdict table: rejection predates derived schema/output, not lost acceptance.
- Outcome references exactly the committed pull/push/commit/validation and its own UUID.
  Both CAS blobs match their recorded hash/size/line count (856518bytes/178lines and
  879529bytes/204lines); final blob extends the exact commit snapshot. Both embedded
  appendwatch reports mark the session OK. No evidence of log/DB/CAS mismatch in this run.
- DuckDB TABLE COMMENT remains the expected initial empty-file anchor (ordinal0/byte0);
  per-line hashes cover all appended records. This is normal for a fresh --new lifetime,
  not an unpromoted-resume failure. No hash/config/anchor was modified.
- NiceGUI has7run events ending codex_exited(exit0) -> failed, an empty queue, and the
  original307-researcher snapshot with0attempts/0outcomes. This is expected autonomy: no
  post-run Query IPC occurred. Codex exit0 does not mean Backend validation passed.
- Matching persisted artifacts resolve the concern about missing projection for this run;
  they do not establish the missing clean-close acknowledgement or remove the cancellation
  window identified above. No other historical captures or original production paths opened.

Duplicate Backend warning lines occur during validation and authoritative replay verification,
not duplicate persisted /validate records (the recovered log confirms exactly one).

Diagnostics: Dashboard's failed-run summary says detail=unspecified despite the preceding
final pull500; its final exception alone loses the Backend's useful earlier rollout_index
reason. The Backend warning does report that reason, whereas generic client500 is intentional.
Initial missing-socket messages resolve through normal IPC startup/query/clean closure; no
new missing-file defect. No Playwright teardown warning in this run. Existing Mode0 Plotly/
Kaleido deprecations (11) and audit_read multithreaded fork warning (1) remain; neither is shown
to cause these failures. Main-pipeline XPASS is its explicitly documented stale reviewed note.

Fresh upstream reproduction: the exact eight failed preflight cases reproduce locally,
8failed/15deselected4.01s, through the isolated pytest plugin, no network/root/production data.
They should have been caught BEFORE another human acceptance run. Earlier selected P25 and
browser/root passes did not cover the full ordinary graph, despite the handoff claim. Next
correction must retain the five lifecycle cases and meaningful log/exit-failure coverage, run
these cheap leaves locally, and only then request another expensive live workflow. Do not
mask this with P26-P30 implementation, relaxed assertions/skips, old aliases or task rewrites.

Other fresh leaves: Ruff + default mypy68files + AI strict mypy55files PASS; main174passed,
5skipped,6xfailed,1documented XPASS; step4 normal4passed1skip, slow1skip4deselected; Mode3 all6
PASS; Mode0 all4PASS; main real API3passed1expected xfail. Live completion/card/export/replay
acceptance is NOT reached; host synthetic DOCX export passing is a distinct boundary.
Wrapper status/grep quirks are unchanged and previously rejected for modification; actual
leaf summaries/exit statuses, not “grep: no FAILED”, determine the result.

### Operator-log corrections — implemented; local evidence above, delegated gate pending

Scope is separate from P26-P30. All seven corrections are implemented; verification status is below. On2026-09-19 the operator approved
exactly HUMANS sections2 and4–7; their complete bodies and fenced code snippets are copied
verbatim below, with headings reflecting current implementation/verification status. This is the implementation
boundary, not permission for broader refactoring. Item3 is explicitly superseded by deletion
of elevate-triggering tests. Preserve existing assertions/timeouts in retained tests and all
isolation/ownership constraints; any deviation needs explicit approval before implementation.

1. **Web-action evidence eligibility — IMPLEMENTED, locally verified:** add find alongside
   search_query/open/click. Operator proposes unsupported arguments make the affected
   evidence ineligible rather than fail the whole rollout with pull500. Latest explicit
   refinement: KEEP the existing choice() and exclude unsupported calls from eligible
   candidates; no without-replacement loop. An exhausted eligible pool enters the existing
   evidence-retry handling. This supersedes the earlier proposal to retain fatal action-count
   enforcement and the briefly discussed resampling loop. Implementation is now explicitly
   authorized for this correction only, not the other operator-log findings.

```python
WEB_FIND_ACTION = "find"
ELIGIBLE_WEB_ACTIONS = frozenset({
    WEB_SEARCH_QUERY_ACTION,
    WEB_OPEN_ACTION,
    WEB_CLICK_ACTION,
    WEB_FIND_ACTION,
})
```

   Schema evidence: operator supplied
   chats/chats-20260911-ai-augment-prod/ChatGPT-Discover_Web_Run_Schema.md, specifically
   operator-designated message "## 25 - ChatGPT" (lines2206–2294), read in full. The tagged
   rust-v0.146.0-alpha.3.1 SearchCommands source reproduced there (encoded source at line486)
   has ten independent optional operation arrays: search_query, image_query, open, click,
   find, screenshot, finance, weather, sports, time; plus response_length. FindOperation
   requires ref_id/pattern. Multiple action arrays are allowed, not an exactly-one union;
   tool.rs command_action is only a lossy summary. Optional nulls/empty command input are
   accepted by the upstream deserializer; that does not make them eligible evidence here.
   calculator/product_query are not declared in this tagged schema. Source was inspected in the supplied
   export, not independently fetched. Treat our supported subset as evidence policy,
   not a claim that other valid web.run commands are malformed. response_length and known
   nested action parameters are not unsupported actions. Check all argument keys against
   the four supported actions plus response_length, with at least one nonempty supported
   action. Multiple supported actions are not an upstream schema error; any unsupported
   argument excludes the call, even when another key is supported. No full tool-schema
   model, support for the other six actions, event-summary inference or catch-all fallback.
   Operator additionally supplied protected/src/agent_runtime/docs/search.rs. Read in full;
   SearchCommands/FindOperation/response_length confirm this rule. File left untouched.
   Operator's follow-up explicitly supports combinations because upstream is authoritative.
   No additional Rust source needed for this change.

   Implementation: _web_arguments returns None for unsupported/no-active arguments, with
   one Locale-owned info log; JSON/non-object corruption still raises. _has_cite_marker
   separates output discovery from strict _cited_fco_text validation, which runs only after
   arguments qualify. Ineligible calls produce no indexed rows, so both exact and near
   candidate SQL naturally excludes them; no SQL, choice(), assessment or retry rewrite.
   Keep malformed supported chains, duplicate IDs, citation/result ambiguity, session/CAS/
   appendwatch corruption fail-closed; no generic catch-and-continue.
   _exact_evidence_candidates finds occurrences of the submitted excerpt; assessment then
   matches its exact URL and uses one seeded EVIDENCE_RANDOM.choice, not an existing
   without-replacement loop. The proposed alternatives are provenance for THAT submitted
   excerpt/URL, not unrelated evidence or automatic submission rewriting. Operator explicitly
   chose prefiltering unsupported candidates and retaining the existing seeded choice;
   no sampling-loop change is authorized or needed. Apply the same eligibility to
   near-match candidates so they
   cannot resurrect unsupported evidence. No cross-item/global non-reuse rule is proposed.
   Existing unmatched assessment -> _process_retry_attempt -> _assessment_public_detail ->
   DUCKDB_EVIDENCE_VALIDATION rejection already yields RETRY and pull200 Markdown guidance,
   not500. Preserve codex-match-v2 near-match distinction and all existing retry obligations.
   An unused unsupported call must not force an otherwise valid submission to retry.

   Update the existing minimal_rollout_records arguments map with find targets including
   ref_id and pattern; make the existing action-test parameters explicitly cover all four
   wire actions (not only derive expected coverage from the implementation's whitelist).
   Add a small sanitized four-target find chain with find_in_page event, two URL-backed
   results and two URL-less errors. Verify the existing index produces exactly the valid
   refs. Include coverage for unsupported-only and supported/unsupported mixed calls,
   alternate same-excerpt/URL provenance, exhausted candidates and existing retry guidance,
   ordinary response_length, plus unreferenced unsupported calls. Preserve negative
   missing/ambiguous/malformed supported-chain checks and verify current-rule live/replay
   behavior with synthetic records. Never modify supplied artifacts or substitute
   a saved historical verdict: the recovered rejected validation is not promised replayable
   under a rule that changes its recomputed result. No migration/fallback/version shortcut.

   Completion evidence (2026-09-18):
   - Production diff confined to api.py and Backend locale.py: find/response_length peer
     constants, supported-subset eligibility, early exclusion before strict output parsing,
     and one informative exclusion log. choice(), SQL, retry logic, Store, server, Dashboard,
     tasks and P26-P30 are unchanged. Original CAS/replay/DB artifacts were not modified.
   - Added focused tests to existing test_api.py/test_http_interceptor.py: each supported
     action and their combination; six upstream unsupported actions, unknown keys and mixed
     supported/unsupported calls; multi-block unsupported output; exact/near candidate pools;
     four-target find with two URL-less errors; malformed JSON/non-object/duplicate/order/
     citation-integrity failures; real persisted validation and pull410 versus retry200 with
     baseline/audit persistence; identical query/logical DB after explicit replay, unchanged log.
     Existing random-choice/seeded-selection and retry assertions remain.
   - Before fix: focused reproduction3failed/3passed at maxfail3 (find, supported combination,
     unsupported image action). After fix:32focused passed3.29s,7additional find/integrity
     passed2.48s,4real validation/replay passed19.45s. These overlap the final batch below.
   - Final feasible API + HTTP-interceptor regression:246passed,1existing skip,3deselected
     in212.19s. Command: pixi run -e detour-ai-augment env python -m pytest -q
     src/detours/detour_ai_augment/tests/backend/test_api.py
     src/detours/detour_ai_augment/tests/backend/test_http_interceptor.py
     -m 'not python_subprocess'
     -k 'not captured_operator_push and not historical_haanen_retry'.
     Exclusions: process-lock subprocess and two historical capture cases. Existing skip:
     multiple-match rejection test, because multiple matches are intentionally allowed.
   - Ruff PASS; configured strict mypy PASS4changed Python files; full diff whitespace PASS.
     Initial mypy caught heterogeneous empty-tuple chained comparisons and indirect Locale
     import in new tests; corrected to separate assertions/direct import, no casts/ignores.
   - No network/browser/root/live-Codex acceptance run. Current correction is complete, not
     a full pre-commit-operator acceptance claim. Corrections2 and4–7 are implemented and locally verified; delegated/full verification remains pending;
     correction3's authorized deletion is complete. P26–P30 remain separately approved/pending.

2. **IMPLEMENTED — Correct the five stale IPC test callpoints**

In `test_operator_e2e_preflight.py`:

```python
monkeypatch.setattr(
    backend_server,
    "start_dashboard_query_server",
    Mock(side_effect=AssertionError),
)
```

Remove the unused `backend_ipc` import. Preserve all five cases and assertions. No compatibility alias.

3. **IMPLEMENTED — Remove elevate-triggering tests entirely**

   Operator explicitly rejected the replacement-wrapper-test direction: "purge elevate
   triggering tests altogether". Remove test_elevate_retains_failures_and_reports_failed_lines
   and its none/install/browser parametrization from protected/tests/operator/
   test_operator_e2e_preflight.py, plus the now-unused tomllib import. Search the active detour
   tests for any other elevate-triggering tests and remove only those if present. Do not
   replace them with a shim, source-string assertion, skip or a different elevate invocation.
   Actual elevate command, log/status/FAILED-grep scaffolding and ordinary tasks stay untouched.
   Preserve the unrelated preflight tests. This supersedes the former unapproved item3 code
   snippets; they are deliberately removed from WORK, not retained as pending implementation.

   Provenance: git blame/show identifies introduction in commit
   2eeb7c4c0f754d483e975cb75376ec238fa91af7 (2026-09-17, "ai augment task: address test failures").
   Its historical WORK records P18 tests of the real GNU script/PTY logger, run-all behavior,
   retained failure status and FAILED reporting. The temporary verification batch was narrowed
   from five controlled cases to the committed three install/browser cases. The permanent
   preflight test reads current pyproject.toml's elevate command and runs the actual shell
   in tmp_path while replacing Python leaves with sentinel outcomes. It enters the ordinary
   suite because test-detour-ai-augment explicitly includes this preflight module; there is
   no recursive pixi run elevate. Binding those tests to the mutable install/browser payload
   was the mistake: correct restoration to "Nothing to elevate" broke all three. The operator
   now authorizes deleting that dependency entirely, not redesigning its coverage.

   Completion2026-09-19: removed the one parametrized test (all three cases) and unused
   tomllib import. No elevate references remain in the detour's tests. AST comparison to
   HEAD confirms every retained function/class is unchanged; only that test definition was
   removed. At item3 completion, the actual elevate task and all other pyproject tasks were unchanged. Ruff PASS;
   configured strict mypy PASS1file; pytest collection succeeded with20 remaining cases
   (6.11s), none targeting elevate. This is collection evidence, not a claim those20 tests
   pass; item2 was subsequently corrected and its full20-case preflight run passed above.

4. **IMPLEMENTED; HOST VERIFICATION PENDING — Make the spacing test measure a ready card**

Test-only changes in `test_ui_e2e.py`:

```python
card = page.get_by_test_id(control_ui.CARD_MARKDOWN_TEST_ID)

expect(
    card.locator("code", has_text=E2E_CARD_FILENAME)
).to_have_text(E2E_CARD_FILENAME)

expect(
    page.get_by_test_id(control_ui.DOWNLOAD_CARD_DOCX_TEST_ID)
).to_be_enabled()

card_paragraphs = card.locator("p")
```

Replace the uninformative bare ratio calculation with:

```python
def _line_height_ratio(locator: Locator) -> float:
    expect(locator).to_be_visible()
    measurement = locator.evaluate("""element => {
        const style = getComputedStyle(element);
        return {
            connected: element.isConnected,
            lineHeight: style.lineHeight,
            fontSize: style.fontSize,
            ratio: parseFloat(style.lineHeight) / parseFloat(style.fontSize),
        };
    }""")
    assert measurement["connected"], measurement
    ratio = float(measurement["ratio"])
    assert math.isfinite(ratio), measurement
    return ratio
```

Keep **every spacing/bounding-box assertion and timeout unchanged**. No CSS change, arbitrary sleep, NaN replacement or retry-until-spacing-passes. If a genuine CSS defect remains, return with that evidence before changing production styling.

5. **IMPLEMENTED; LOCAL VERIFICATION PASSED — Finish Backend shutdown before propagating cancellation**

In `_BackendSupervisor`, move the existing `_stop` body unchanged into `_stop_owned_process`, then wrap it:

```python
async def _stop(self) -> None:
    stop_task = asyncio.create_task(self._stop_owned_process())
    try:
        await asyncio.shield(stop_task)
    except asyncio.CancelledError:
        await stop_task
        raise

async def _stop_owned_process(self) -> None:
    # Existing _stop body:
    # terminate/wait, drain logs, check acknowledgement,
    # finish_backend_stop, then clear ownership.
    ...
```

Existing callers retain the lifecycle lock until this finishes. Preserve the existing SIGTERM/10-second/SIGKILL policy and clean-close requirements.

Extend the **existing** Locale-backed stop log:

```python
BACKEND_STOPPED_LOG_TEMPLATE: Final = (
    "Backend process stopped: pid={pid} return_code={return_code}; "
    "clean_close_ack={clean_close_ack}; forced_kill={forced_kill}; "
    "shutdown_succeeded={shutdown_succeeded}"
)
```

Pass the already-computed booleans.

Tests exercise actual supervisor cancellation during child exit and log draining. Operator teardown additionally verifies a successful stop **for each owned Backend PID**, after completing cleanup—an earlier IPC-only acknowledgement must not satisfy full-Backend shutdown.

No Backend/server/Store changes or borrowed-process handling changes.

6. **IMPLEMENTED; LOCAL VERIFICATION PASSED — Include the actual Backend error in operator-test failures**

Change only `raise_for_dashboard_failure`:

```python
if failed_run_lines:
    backend_error_prefixes = tuple(
        f"{Locale.BACKEND_LOG_PREFIX} {level}:"
        for level in ("WARNING", "ERROR", "CRITICAL")
    )
    diagnostics = [
        line for line in dashboard.output
        if line.startswith(backend_error_prefixes)
    ]
    raise RuntimeError(
        "workflow failed:\n"
        + "".join((*failed_run_lines, *diagnostics))
    )
```

Add a cheap regression proving the exception includes both the failed-run summary and captured rollout-index error.

Dashboard remains dumb: no additional query, Backend-state inspection or inferred validation reason.

7. **IMPLEMENTED; LOCAL VERIFICATION PASSED — Run the audit probe outside multithreaded pytest**

Move only the test’s in-process probe invocation into the existing shared subprocess mechanism.

Named helper in the protected pytest plugin:

```python
def audit_probe_process() -> None:
    import sys
    from src.detours.detour_ai_augment.src.control_centre.appendwatch import audit_read

    configured = audit_read.AuditReadConfiguration.model_validate_json(sys.argv[1])
    audit_read.execute(
        configured,
        audit_read.PROBE_COMMAND,
        output=sys.stdout.buffer,
    )
```

Existing test, explicitly marked `python_subprocess`:

```python
result = python_process.run(
    audit_probe_process,
    configured.model_dump_json(),
    timeout=10,
)
assert result.returncode == 0, result.stdout + result.stderr
assert result.stdout == result.stderr == ""
```

Production audit behavior remains unchanged. No warning suppression or new privilege requirement.

**No correction proposed for normal/unchanged observations:** initial missing-socket polls,
unchanged NiceGUI snapshot, duplicate live/replay warning, old unreproduced pre-start hang,
F7 report, documented main-pipeline XPASS. Mode0 dependency deprecations are outside this
isolated detour scope: no main-pipeline/other-detour/environment/lockfile changes. Existing
ordinary-wrapper status/grep restructuring remains rejected; no pyproject task edit proposed.
The skipped provider leaf is a verification gap to execute, not a reason to change && or tasks.

**Pre-handoff verification for approved corrections:** reproduce regressions before each fix; run all
feasible normal-suite leaves including operator preflight, changed API/index/replay and UI/
audit tests, Ruff and strict mypy. List environment-blocked leaves explicitly. Then prepare
only necessary delegated host-Chrome/layout/cleanup and previously blocked real-provider
checks in elevate, with machine checks, safe logging and preserved failure status/FAILED grep.
No password capture or SSH verbosity, no altered browser, no repeated root tests unless the
new diff touches their boundary. Full pre-commit-operator/live Codex only after those checks.
P26-P30 remain pending and outside these corrections. Operator now explicitly requires a
failure-free full pre-commit-operator run BEFORE starting P26: no failed test/check, hang,
operator interruption or silently unreached leaf may be reported as acceptance. Review each
leaf rather than unchanged wrapper status/grep quirks; retain existing intentional skips/
xfails and inspect warnings, waits, cleanup and preservation evidence. Correction1's local
passes do not satisfy this gate. Corrections2 and4–7 are implemented and locally verified; delegated/full verification remains pending; correction3's
authorized deletion is complete. New defects or scope deviations still need a narrow
proposal/approval rather than broadening implementation silently.

Latest operator-assisted diagnostics (2026-09-18): operator authorized putting the proposed
checks in elevate with embedded machine checks, rather than separate commands or instructions
about where to run them. The completed batch required macOS before diagnostics/log replacement,
ran test_ui_e2e with default Chrome and the exact Dashboard ProxyJump busy command
(15s diagnostic timeout), and automatically dispatched interpreter/appendwatch --help to
the named aicode guest via limactl. Guest verifies Linux ARM64; non-interactive sudo -n and
setpriv run the actual selected interpreter/watcher as nobody with no supplementary groups.
No interactive sudo authentication or script/PTY wrapper; guest dispatch has stdin closed.
Unavailable privileges fail explicitly without requesting a password. namei prints interpreter
traversal permissions. No browser install, permission change,
live Codex run or remote process killing. A timed-out diagnostic kills only its own local
SSH process group. Combined stdout/stderr goes to elevate.log; all three checks run despite
earlier failure, aggregate status and FAILED grep retained. Only elevate and WORK changed;
no ordinary task edits. TOML/outer+batch+guest shell syntax, embedded SSH Python compilation,
wrong-machine guard and comparison proving other TOML settings unchanged all PASS locally.
First reviewed delegated log: host module9passed29.53s (eight real Chrome browser tests plus one
browser-free fixture check); slowest call7.08s, real owned query4.43s, clean child/host shutdown,
no timeout/Ctrl+C. SSH probe to aivm:exit0,0.33s,empty stdout (idle). The root diagnostic DID
NOT RUN: limactl reports the explicitly targeted aicode instance is stopped. Combined status1
is therefore correct, not a browser/SSH failure or a new watcher result.
Machine roles: macOS is the production Dashboard/browser-test host; aicode is the Linux
ARM64 development/test guest; aivm is the remote agent runtime and only the SSH busy-check
target. Log platform/path confirms macOS execution; no test batch was dispatched to aivm.
Operator redacted SSH key details from the log. The added -v unnecessarily printed public-key
fingerprints/identity paths; removed it and clarified the SSH phase label. Preserve ordinary
SSH errors/status/timing, do not request unredacted key material. Existing optional known-host
file/security-key-provider debug messages were not connection failures (actual exchange exits0).
Operator also flagged the sudo password prompt in recorded execution. Removed sudo -v and
the guest script/PTY wrapper entirely, rather than try to transfer sudo authentication between
different TTYs. Only sudo -n remains and guest stdin is /dev/null. No password input is requested
or collected by this diagnostic. Do not read/request an unredacted credential-bearing log;
previous log files were not modified.
Latest rerun (log modified2026-09-18 19:00UTC): host9passed29.72s; slowest call7.11s,
real query4.26s; SSH to aivm exits0 in0.32s, idle. aicode now runs the noninteractive check:
Python starts but cannot locate its platform-independent/dependent libraries, then fatally
fails importing encodings. Watcher code never starts; no monitoring pass. Combined status1.
The follow-up below establishes the actual path/access failure rather than treating this as
a missing Pydantic package or changing Python environment variables.

Focused elevate batch completed: only the aicode runtime-access diagnosis; no repeated Chrome/
SSH checks. Retains macOS guard, named aicode dispatch, Linux ARM64 check, closed stdin and sudo -n.
Normal-user interpreter identifies its actual prefix/stdlib/encodings paths, then the batch
prints nobody identity, namei chains and actual read/traverse checks under that identity before
executing the unchanged watcher --help with the same interpreter. Every subprocess is bounded.
This launches a fresh nobody Python; no privileged import preload, PYTHONHOME/PYTHONPATH override,
package install, permission change or test weakening. TOML/outer+guest shell syntax, embedded
Python compilation, wrong-machine guard and unchanged-other-TOML comparison PASS locally.
Reviewed result: uid65534(nobody),gid65534(nogroup), no supplementary groups. Every tested runtime
path is unreadable to nobody; prefix/stdlib/encodings directories also fail traversal. Normal
user resolves those paths successfully. namei identifies /home/anonymous.linux as0750, while
the listed descendant directories are0775 and encodings/__init__.py is0664. The watcher source
outside that home is readable (access exit0). Fresh nobody Python fails encodings import,
watcher startup exit1 and combined status1. No monitoring tests ran. Enough evidence for a
test-runtime/credential mismatch; no further diagnostic rerun requested. Operator correctly
challenged granting nobody home access when the caller already owns the runtime. ACL proposal
withdrawn; the narrower proposed harness correction is recorded below.
All future operator execution requests must be prepared in elevate with embedded machine
checks, not pasted as separate manual commands.
Operator requested reverting idle elevate to the original "Nothing to elevate" shape:
restored that exact placeholder with script/log/FAILED-grep/exit-status scaffolding. No
further diagnostic run is pending; do not execute a permission change before approval.

Latest browser-routing correction is APPROVED and IMPLEMENTED, including the operator's
additional one-line comment directly above PYTEST_ADDOPTS. It supersedes the earlier
marker/new-task proposal: change ONLY pre-commit-operator, not test modules/plugin or other
tasks. Scoped PYTEST_ADDOPTS in the existing aicode shell excludes the entire test_ui_e2e
module from that guest invocation only. Existing macOS BSD script logging runs the entire
nine-test module on the host before pre-commit-extra-operator. Keep existing PYTEST_ADDOPTS,
Chrome selection, test bodies and all grep/status/run-all behavior. No new marker/task or
browser fallback. TOML and outer/guest/host shell syntax plus actual parsed routing checked;
comparison confirms other task/settings unchanged (elevate separately restored to its idle
placeholder as requested). No operator commands executed locally or full acceptance claimed.

```diff
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -341,12 +341,14 @@
 [tool.pixi.tasks.pre-commit-operator]
 cwd = "."
-# run all in lima except operator tests.
+# run non-browser tests in lima; browser and operator tests on macOS.
 # using bash -c so that pixi does not
 # exit on first failed command.
 cmd = """
 bash -c '
   limactl shell aicode -- bash -c '"'"'
     export PATH="$HOME/.pixi/bin:$PATH"
+    # Exclude browser tests in this guest invocation; run them with host Chrome below.
+    export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:+$PYTEST_ADDOPTS }--ignore=src/detours/detour_ai_augment/tests/control_centre/test_ui_e2e.py"
     script -e -c "
       {
         pixi run pre-commit
@@ -355,6 +357,10 @@
     grep -q "FAILED" logs/pre-commit.log &&
     echo "grep: no FAILED"
   '"'"'
+  script -a \
+    logs/pre-commit.log \
+    bash -c '"'"'pixi run -e detour-ai-augment python -m pytest -vv -srA \
+      src/detours/detour_ai_augment/tests/control_centre/test_ui_e2e.py 2>&1'"'"'
   pixi run pre-commit-extra-operator
 '
 """
```

Root test harness is a SEPARATE APPROVED and IMPLEMENTED correction, not part of the browser-routing patch.
The ACL proposal is withdrawn. Tests intentionally run pytest as root and launch the watcher
unprivileged via nobody_credentials/drop_privileges; moving its interpreter into the invoking
user's private Pixi environment made that identity incompatible with runtime access.
Approved exact fix: select the original non-root sudo invoker via SUDO_UID/SUDO_GID,
not nobody, for the existing privilege-drop helper and temporary-tree ownership. Fail clearly
if invoker credentials are missing/invalid or root; no invented account/fallback/new skip.
Keep supplementary-group clearing, root-owned0700 denial fixtures, real watcher subprocesses,
permission transitions and every EACCES assertion unchanged. Update only helper naming and
direct explanatory text/callpoints. No home ACL/chmod, package/runtime relocation or preload.
The three existing privileged tests were verified through elevate using sudo -n; ordinary root
task unchanged. That verification used the macOS guard, explicit aicode dispatch and Linux ARM64
guard, same root-test environment/selection, closed stdin and sudo -n. No authentication prompt,
SSH verbosity, ACL edit or repeated Chrome/busy-probe checks. After the passing run, restored
elevate to the requested "Nothing to elevate" placeholder with script/log/status/grep scaffolding.

Exact approved helper replacement, in protected/tests/backend/
test_appendwatch.py; remove now-unused pwd import and update the introductory explanation:

```python
def sudo_invoker_credentials() -> tuple[int, int] | None:
    if os.geteuid() != 0:
        return None
    try:
        uid = int(os.environ["SUDO_UID"])
        gid = int(os.environ["SUDO_GID"])
    except (KeyError, ValueError) as exc:
        pytest.fail(
            f"Permission tests require valid SUDO_UID/SUDO_GID: {exc}",
            pytrace=False,
        )
    if uid <= 0 or gid < 0:
        pytest.fail("Permission tests require a non-root sudo invoker", pytrace=False)
    return uid, gid


def _permission_test_tree() -> tuple[Path, Path, Path, int, int]:
    credentials = sudo_invoker_credentials()
    if credentials is None:
        pytest.skip("requires root for real EACCES integration")
    uid, gid = credentials
    # Existing temporary-tree creation/chown/chmod and return remain unchanged.
```

Existing drop_privileges continues clearing supplementary groups, setting gid then uid.
Only non-root pytest retains its existing skip; missing/bad invoker under root fails rather
than skips. No existing permission-denial assertion or root-owned0700 fixture changes.
Implementation audit confirms only the approved helper/callpoint, unused pwd import and
introductory docstring changed. Local evidence:42passed,8deselected18.43s for test_appendwatch
with -m "not needs_sudo" -k "not socket and not nonregular_substitution"; exclusions respect
the no-root/no-socket execution boundary, not a pass for those cases. Ruff PASS; configured
strict mypy PASS1file. Exact delegated selection collects3/73tests (70deselected) in0.36s.
elevate TOML/shell syntax and wrong-machine guard PASS; no privileged commands executed here.
First delegated root rerun failed3before startup using the pre-fix test file: all three
traceback callsites match the old revision,12lines before the corrected version. Operator
confirmed forgetting to pull, then updated and reran. Latest reviewed elevate.log confirms
3passed,70deselected1.54s, root test status0. No additional implementation change or proposed
source-hash guard was applied between runs. Root verification is complete.
That targeted result supported the subsequent full operator run, now reviewed above.
Chrome placement/root credentials are resolved; full acceptance remains blocked by the
independent current findings, including cheap preflight cases missed before handoff.
That earlier review required no further batch. The current post-correction elevate batch
is recorded at the top; P26-P30 remain separate pending work.

Rejected changes MUST NOT return: root preload-before-drop, synthetic DuckDB config/binary
that conceals prerequisites, substituted-query browser test, raised launcher timeout,
pre-commit wrapper restructuring/status/grep corrections. No production storage cleanup.
A prior direct importlib.find_spec on a NiceGUI submodule imported NiceGUI outside isolation;
default storage may have been accessed. No preservation claim for that command and no cleanup
followed. Never repeat ad-hoc NiceGUI imports; use installed-source reads or isolated tests.

## Verification discipline and operator command graph

TASK requires cheap upstream coverage before costly human production E2E. Review changed
callers AND fixtures/imports/launchers: passing unit models or startup conditions do not prove
real interpreter selection, queue Start, query helper or browser channel. Never replace the
boundary under assertion, silently skip prerequisites or weaken assertions/timeouts. Record
initial failures separately from eventual passes. Reuse valid evidence; broad unrelated edits
are not authorized by testing requirements.

Operator runs exactly pixi run pre-commit-operator. Recheck actual pyproject definitions before
handoff; inspect every independently runnable leaf and shell short-circuit/environment:

```text
pre-commit-operator
  Lima aicode: pre-commit
    lint -> default Ruff + default mypy + AI strict mypy
    test-repl -> default test .
    test-detours
      step4 normal + slow (default)
      mode3 (default)
      mode0 (mode0 env)
      AI normal/backend/operator-preflight, then real_api institution if success
  macOS host: test_ui_e2e (Chrome), appended to pre-commit.log
  pre-commit-extra-operator
    Lima aicode: default real_api then AI needs_sudo backend tests
    host: real AI operator workflow
```

Fresh per-leaf results and skipped downstream leaves are in the operator findings above.
Unchanged wrappers retain known status/grep quirks; inspect actual leaves. The operator review
exposed incomplete upstream graph coverage; selected passing batches must not be presented
as full ordinary-suite coverage.

Only Assistant-owned elevate can be freely adjusted for targeted delegated verification,
with detailed logs/from_operator/elevate.log, failure status and FAILED grep retained. Prepare
small concrete batches AFTER feasible local checks, then request operator execution; no
assumed pass or hidden live-Codex run. Ordinary task edits need explicit approval except the
already approved interpreter substitutions, narrowly approved pre-commit-operator macOS
browser routing, and F7 fixes for a proven variable defect.

Tests: existing protected/tests/pytest_plugin.py isolates NICEGUI_STORAGE_PATH before import,
unsets NICEGUI_REDIS_URL, fails if NiceGUI imported too early. Children use per-test
nicegui_test_environment; original-storage preservation checks remain. Explicit Lima fixture
only for real consumers. Named python_process helpers and python_subprocess/socketless_lifecycle
markers stay in protected plugin; sockets are not bypassed by subprocesses. Do not run
browser/operator/network/privileged/historical-capture tests here. Use real synthetic Store,
DB/log, in-process ASGI/WSGI, startup CLI and meaningful error paths for P25.

Relevant modules: tests/backend/{test_api,test_ipc,test_backend_store,test_http_interceptor}.py,
tests/control_centre/test_ui.py (includes startup conditions), protected test/plugin/operator
fixture callpoints and repository-root tests/test_http_request_log.py. Exclude real_api,
operator, needs_sudo, captured_operator_push, historical_haanen_retry, real_mode_0600_unix_socket.
Do not execute main CLI, inaccessible artifact fixtures, paused BDD or sample_deploy.

```bash
pixi run -e detour-ai-augment env ruff check src/detours/detour_ai_augment src/helpers/data_models/http_request_log.py
pixi run -e detour-ai-augment env mypy --config-file src/detours/detour_ai_augment/mypy.ini src/detours/detour_ai_augment src/helpers/data_models/http_request_log.py
```

## Mandatory constraints for continuation

- After compaction reread TASK and WORK IN FULL. Keep WORK current, remove stale pending claims.
- Only the current detour contract exists: no historical-schema special cases, shape-based
  migration or alternate parser. No special output-schema guard. P24 is complete; current
  implementation is ONLY P25's exact approved contour/snippets above, with ACK/NAK and
  update_pull_state, plus the approved P26 typed-construction/content-type, P27 literal-audit,
  P28 protocol-ownership/inheritance, P29 original-pull-ID rename and P30 Store-owned
  current-record/session/outcome-metadata/linkage additions.
  Current priority is verification of the now-implemented operator-log corrections2–7
  above; item3 was limited to deleting elevate-triggering tests. Do not start P26 until the full
  pre-commit-operator acceptance gate is met. No unrelated audit, DTO-default removal or
  card-format tightening.
- Operator forbids cast: changes must use genuinely compatible types, not cast or substitute
  type suppressions. No unrelated codebase-wide refactor. Store persistence and pull-state
  updates must not be named publishing; that term is reserved for DOCX/TXT in the new scope.
- All commands via pixi run -e detour-ai-augment; Ruff/mypy/pytest via env. Git read-only.
- Task edits: prior interpreter substitutions, agent-owned elevate, approved pre-commit-operator host-browser routing, and F7 fixes for proven environment-variable expansion defects only. Other pre-commit structure/status/grep changes remain rejected.
- Never run/import src.repl, edit src/cli.py, import another detour or edit TASK. HUMANS is
  human-maintained; the operator explicitly authorized only this 2026-09-18 post-find
  proposal/status update. No broader HUMANS editing permission is inferred.
- Only allowed production data is data/scisci_process.duckdb READ ONLY. No other data/,
  .aicode/ or historical captures. Isolated temporary test fixtures are permitted.
- No network/socket probes/escalation. Paused BDD permits only its completed model conversion.
- Preserve operator edits/staging, human-signed comments and narrowly approved boundaries.
- sample_deploy is excluded from edits, conversion inventories and test execution.
