# AI augment production preparation

## Status and authorization

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
P25 production wiring and affected test callpoints are implemented; feasible integration and
startup checks pass. P26-P30 remain pending additions. P30 supersedes only the state ownership,
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

## Operator findings still open — not newly authorized by P25

Latest reviewed pre-commit-operator run:2026-09-17 14:55–14:59(-04), logs/from_operator/
pre-commit.log and pre-commit-extra.log, reviewed against then-f56fb8a. Full acceptance FAILED.

| Finding | Current state / boundary |
|---|---|
| Normal AI suite | 517passed,9failed,1skip,3deselected in110.02s. One IPC log/test failure subsequently fixed above; eight Chrome launch prerequisites still unresolved. Provider stage not reached because && stopped it. |
| Browser placement | Operator confirms Chrome is installed on the macOS host and production Dashboard runs there. Normal guest task incorrectly includes eight Chrome browser tests in aicode/Linux ARM64. Those must be tested on the host, not solved by installing/substituting Chrome in the guest. Passing the separate Chromium elevate batch does not prove host Chrome. Exact task/selection edits still require approval. |
| Root watcher | 3failed before monitoring. Correct AI interpreter cannot be reached through0750 /home/anonymous.linux after drop to nobody with empty groups. Diagnostics implemented, accessible-runtime/access correction unapproved; no preload/chmod/ACL/cache move. |
| Latest operator hang | Private initialization, Query IPC307rows, clean IPC stop, Queue and Start succeeded; then0records/no full Backend start, Ctrl+C at88.42s. Actual SSH occupancy/blockage not captured, cause unproven. |
| Pre-start boundary | _wait_until_codex_idle precedes Backend start; configured ProxyJump SSH pgrep may report busy or block. Preflight limactl shell does not prove this exact path. Proposed progress logs/diagnosis not implemented/approved by P25. No bypass, timeout increase, external-process killing or automatic query. |
| F7 variables | Operator explicitly reports pixi run failed before pixi shell. Not reproduced by local/PROD sanitized activation cases. Do not dismiss report or patch tasks without a proven defect. |
| Configured DuckDB binary | Latest PROD both actual configured-binary/config-path checks PASS; preserve absence detection, no synthetic replacement. |
| Preservation | Latest guard covers both data trees AND original NiceGUI directory and passed; old contaminated production storage untouched. |

Earlier expensive run reached three pushes/two retries/410 and completed200, then harness
hung because rendered RERUN differed from semantic Rerun. F4 now uses text_content and emits
actual phase/guards; real query regression passes. That interrupted live run never reached
card/artifact acceptance. Do not confuse it with the later pre-start hang. Original teardown
warnings followed Ctrl+C; latest run shutdown clean. Mode0 deprecations and Python3.14
multithreaded-fork warning remain observations, not proven causes. Expected negative-test
error logs/initial missing-socket polls are not additional hard failures.

Latest operator-assisted diagnostics (2026-09-18): operator authorized putting the proposed
checks in elevate with embedded machine checks, rather than separate commands or instructions
about where to run them. Prepared batch requires macOS before any diagnostics/log replacement,
runs test_ui_e2e with default Chrome and the exact Dashboard ProxyJump busy command (verbose
SSH,15s diagnostic timeout), and automatically dispatches interpreter/appendwatch --help to
the named aicode guest via limactl. Guest verifies Linux ARM64; sudo authenticates in a guest
PTY, then setpriv runs the actual selected interpreter/watcher as nobody with no supplementary
groups. namei prints interpreter traversal permissions. No browser install, permission change,
live Codex run or remote process killing. A timed-out diagnostic kills only its own local
SSH process group. Combined stdout/stderr goes to elevate.log; all three checks run despite
earlier failure, aggregate status and FAILED grep retained. Only elevate and WORK changed;
no ordinary task edits. TOML/outer+batch+guest shell syntax, embedded SSH Python compilation,
wrong-machine guard and comparison proving other TOML settings unchanged all PASS locally.
Actual delegated results pending. All future operator execution requests must be prepared
in elevate with embedded machine checks, not pasted as separate manual commands.

Permanent correction proposal remains NOT approved: explicit browser routing:
explicit dashboard_browser marker on the eight browser tests, exclude that marker from
the guest task and invoke it in a host task wired into pre-commit-operator's existing host
portion; keep the browser-free fixture regression in guest coverage. No automatic browser
fallback or pre-commit status/grep restructuring. No such source/task edits made yet.
Any root-access correction needs separate approval after current permission evidence;
an exact named-user traversal ACL is an option to review, not an authorized change.

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
  pre-commit-extra-operator
    Lima aicode: default real_api then AI needs_sudo backend tests
    host: real AI operator workflow
```

Last per-leaf results outside changed P25: default Ruff/mypy PASS68files; main174pass,
5skip,6xfail,1xpass; step4 synthetic4pass, slow unavailable5parquets/skip; Mode3 6pass;
Mode0 4pass/11deprecations; main OpenAlex3pass/1expectedxfail; normal watcher38pass.
AI/browser/root/operator boundaries are in the table above. These are pre-P25 evidence, not
new passes. Unchanged wrappers retain known status/grep quirks; inspect actual leaves.

Only Assistant-owned elevate can be freely adjusted for targeted delegated verification,
with detailed logs/from_operator/elevate.log, failure status and FAILED grep retained. Prepare
small concrete batches AFTER feasible local checks, then request operator execution; no
assumed pass or hidden live-Codex run. Ordinary task edits need explicit approval except the
already approved interpreter substitutions and F7 fixes for a proven variable defect.

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
  No unrelated audit, DTO-default removal or card-format tightening.
- Operator forbids cast: changes must use genuinely compatible types, not cast or substitute
  type suppressions. No unrelated codebase-wide refactor. Store persistence and pull-state
  updates must not be named publishing; that term is reserved for DOCX/TXT in the new scope.
- All commands via pixi run -e detour-ai-augment; Ruff/mypy/pytest via env. Git read-only.
- Task edits: prior interpreter substitutions, agent-owned elevate, and newly approved F7 fixes for proven environment-variable expansion defects only. Pre-commit structure/grep changes remain rejected.
- Never run/import src.repl, edit src/cli.py, import another detour or edit TASK/HUMANS.
- Only allowed production data is data/scisci_process.duckdb READ ONLY. No other data/,
  .aicode/ or historical captures. Isolated temporary test fixtures are permitted.
- No network/socket probes/escalation. Paused BDD permits only its completed model conversion.
- Preserve operator edits/staging, human-signed comments and narrowly approved boundaries.
- sample_deploy is excluded from edits, conversion inventories and test execution.
