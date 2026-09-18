# AI augment production preparation

## Status and authorization

Latest implemented P24 authorization (2026-09-18): operator ran `git restore .` and authorized ONLY
reimplementation of P24's exact surgical shape. Staged P20/P21/P22/P23 remain; discarded
P24 implementation/checks are NOT evidence for this retry. P24 is now IMPLEMENTED
and locally verified with fresh evidence below.
No compatibility audit, removal of current defaults, stricter DTO/card parsing, schema
special cases or unrelated corrections are part of this retry. Preserve staged changes.
P22 is historical, superseded by P24's persisted-ID/pure-renderer contour.
P20/P21/P23 remain implemented; production acceptance remains separate.

### Current discussion — Store/transport boundary and grouped processing (not implemented)

Operator is refining a proposal; no exact new implementation/snippets are approved.
Current P24 remains implemented below: per-record DB transactions, outcome-triggered
materialization, and one undifferentiated IPC gate. Only WORK changed during this review.

Latest clarified responsibilities:
- server.py owns actual transports, configuration/resource/process lifecycle, and HTTP/IPC
  exclusion. API/IPC transport adapters exchange Requests-library request/response objects
  with server.py, used as in-process objects, not internal network calls.
- api.py/ipc.py construct app-specific RequestRecords from raw requests and necessary
  external inputs; talk to Store ONLY in RequestRecord/ResponseRecord objects. These are
  application operations/results, NOT aliases for HTTP request/response messages. Domain
  persistence/validation/projection/response-result formulation remains opaque to adapters.
- Full Store exposes exactly four public request operations: pull, push, run_outcome, query.
  No public execute/append/validate/materialize/readback/locking escape hatches. Construction
  and open/close remain lifecycle machinery rather than extra request operations.
- IPC-only initialization exposes ONLY query. Operator proposes separate full/query-only
  initialization behind an overloaded common initializer. Concrete design must enforce the
  capability boundary: overloading __init__ alone cannot hide methods on the same class.
- BackendComponent gains RequestRecordProperty/ResponseRecordProperty bases using the
  shared HTTP-record protocol, plus corresponding route-specific protocols/concrete records.
  Pull request adds no properties; pull response adds pull_response_body. Push response
  exposes commit_record/validation_record (absent when not produced). Outcome/query have
  corresponding typed records/bodies. No implicit duplicated serialization/wire changes.

Push TIMING remains current client-facing behavior: api.py dispatches PushRequestRecord
into Store and returns HTTP202 once accepted, without waiting for final validation. Store's
later PushResponseRecord carries the processing result; api.py uses it to update pull
contents. The earlier interpretation that HTTP202 must wait for final validation is
SUPERSEDED. API owns this asynchronous adaptation, not persistence/domain reimplementation.
Preserve durable push acceptance before202. Operator now proposes Store returning an
acknowledgement once the push exchange is durably appended/fsynced, together with an
awaitable final PushResponseRecord. API can immediately return202 from that acknowledgement
and separately await completion before publishing the new pull contents. Proposed acceptance
receipt identifies the persisted push exchange; it does not claim commit/validation or the
grouped DB transaction has finished. Append/fsync failure means no successful acknowledgement.
Store owns completion work; HTTP-client disconnect/API-waiter cancellation must not cancel
it. Server must register pending processing before202 and release it only after completion
and pull-state publication (or the existing explicit failure path); shutdown awaits it.
Latest operator clarification resolves the read-only query conflict and supersedes the
previous NAY-always-failure / completion-raises proposal:
- Name: ResponseRecordPromise. Synchronous gate is BackendStoreAcknowledgment, an enum
  containing ONLY ACK and NAY (no admission decision wrapper/third state).
- ACK: supplied request record was persisted in HttpRequestLogRecord form and fsynced in
  replay log. Does not assert final DB commit, validation success or HTTP status.
- NAY: request record was NOT successfully persisted. This is either a persistence failure
  for pull/push, or EXPECTED endpoint policy for both IPC operations. It is not intrinsically
  an error, nor a guarantee that failed append/fsync left zero bytes in the file.
- Pull/push expect ACK. Their NAY yields an already-resolved (None, BackendStoreException),
  which API retrieves and raises; no successful response/early202 on that failure.
- Query/run_outcome EXPECT NAY: neither appends a separate request record. Query never
  persists anything. Run outcome constructs and durably persists/replays/projects its
  RESPONSE record (the HTTP exchange includes its request fields), not an initial request
  append. Unexpected ACK in IPC is a contract error.
- ResponseRecordPromiseResult is the named awaited result, EXACTLY one of (ResponseRecord, None) or
  (None, BackendStoreException). Never both values or both None. Normal Store processing
  failures are represented by this tuple, rather than raised from the completion awaitable.
  API/IPC raise the returned exception. BackendStoreException is a real exception conforming
  to new BackendComponent.StoreExceptionProperty; exact protocol members remain to specify.
- ACK followed by a completion error remains ACK plus (None, exc): no retroactive gate
  change. Successful IPC is NAY plus (response_record, None). Thus a run-outcome409 has
  NAY (no request-only append) and a successful response tuple AFTER its response exchange
  is durably persisted/projected. HTTP409 does not imply a Store exception or failed fsync.

ResponseRecordPromise's task state stays private and unserialized. Store owns processing;
client cancellation must not cancel it. Full mode retains four methods; IPC-only exposes
query only. API registers pending work before202 and releases it only after the awaited
result is handled and pull state published (or existing failure handling). For push, a later
error is raised in the tracked completion task; it cannot replace an already-sent202.
ACK is a durability fact, not a replacement for existing HTTP acceptance/status decisions.
Synchronous gate follows required I/O without blocking ASGI's event loop. No public
Store finish/poll operation, third acknowledgment value, query writes or recovery contour.
The clarification question is answered by this explicit policy; no query decision pending.
No new implementation/snippets have yet been approved for execution.

Latest naming/docstring requirement, to include in the full proposed scope/snippets:
ResponseRecordPromiseResult (not ResponseRecordResult); BackendStoreAcknowledgment
(not RequestRecordAcknowledgment). The promise protocol docstring must explicitly state
that acknowledgment concerns ONLY REQUEST persistence. Store performs RESPONSE persistence
where the endpoint requires it before returning its completed response result; a response
persistence failure must resolve the promise to (None, BackendStoreException), never a
successful response. For asynchronous push, returning the promise handle is distinct from
resolving its result; final response persistence cannot precede initial handle return if
that response depends on ongoing work. The presentation must make that timing explicit.

Operator requested recording the complete discussion before preparing a full contract,
bounded surgical change scope and code snippets. This is proposal preparation, NOT approval
to implement the structural changes. Preserve current staged P24/F8 and operator edits.

IPC stays SINGLE-THREADED; no new concurrent IPC acceptance, priority queue or overtaking
between outcome/query. They naturally serialize and clients may wait/time out. Operator
explicitly superseded the earlier strict queued-outcome-over-query interpretation. Server
withholds IPC while FastAPI work is processing. Concrete scope must cover post202 Store
work and the subsequent pull-state publication, not just the HTTP coroutine lifetime.
Operator explicitly agreed that IPC waits before Store processing, not only socket response
emission; admission must prevent new HTTP work slipping through that gap. They also agreed
that the processing interval includes the post202 Store work and pull-state publication,
and that query-only construction must expose an actual narrowed capability, not rely on
__init__ overload annotations alone.
Client timeout does not cancel durable processing; no new timeout/retry/recovery policy.

Store processing proposal retained:
- Pull persists/replays/projects its exchange. Rejected push persists its exchange without
  manufacturing commit/validation. Accepted push progressively records push, commit,
  provider exchanges and validation, then completes their grouped DB projection transaction.
  Provider append -> DB-readback -> model validation must remain valid within that grouping.
- Outcome evaluates existing commit/validation through replay logic without inserting them
  or duplicating effects, decides the requested outcome response, persists it (including409),
  replays/projects it and materializes eligible innerdicts atomically before returning.
  Response body includes commit ID, validation ID and its own outcome record ID.409 records
  rejection, not successful finalization. Explicit replay rejects incomplete groups instead
  of fabricating missing records. Requested completed/failed eligibility versus replayable
  REJECTED validation, the existing final-pull503=>failed rule, and multiple commits per run
  still need exact definition in the concrete scope.
- Query remains read-only wholesale DB snapshot, including IPC-only: common record types
  do NOT imply appending query exchanges. Preserve startup confirmations/hash verification,
  Store DB/log ownership, no recovery, launcher independence and clean-close acknowledgement.

No production/test/task changes made for this discussion, no tests needed/run. Do not
silently implement a new transport/type/lifecycle design or revive unrelated scope.

## Proposed next scope — four-operation Store contract (approval pending)

Prepared only AFTER the preceding discussion/names were recorded. No production/test edits.
This is a bounded structural change, not merely a server gate cleanup. Preserve P24's persisted
IDs, pure card renderer, no recovery and common live/replay rules. Do not label this approved
or implemented until the operator approves the concrete scope. It does not include the
unrelated browser/root/pre-start operator findings.

### Responsibility and persistence contract

Server owns ASGI/WSGI transport conversion, lifecycle and admission. API/IPC helpers exchange
Requests PreparedRequest/Response objects with server, app RequestRecord/ResponseRecordPromise
objects with Store. Requests is used as an in-process representation, never internal HTTP.
API retains existing transport/workflow response timing, including busy503, push409 and early202,
and publishes final push results into pull state. It does not append/project/validate itself.
Existing evidence/SQL algorithms may remain private helpers invoked by Store; no wholesale
move of API algorithms into the Store module. Only Store owns DB/log operations/transactions.

BackendStoreAcknowledgment has exactly ACK/NAY and refers ONLY to request persistence.
ResponseRecordPromiseResult[R] is exactly (R, None) or (None, StoreExceptionProperty), with
concrete BackendStoreException implementing that protocol. Result errors are raised by the
adapter; they do not silently become HTTP409. Request persistence failure for API returns NAY
plus an already-resolved error result. IPC always expects NAY. ACK followed by a later error
remains ACK plus an error result. Invalid result tuples are contract failures, never fallbacks.

| Operation | Gate | Operation/result boundary |
|---|---|---|
| pull | ACK after append/fsync; NAY on failure | project/read back exchange before result; preserve all existing HTTP statuses/bodies |
| push | ACK after append/fsync; NAY on failure | accepted202 may be sent before processing finishes; final result follows grouped commit/validation projection |
| run_outcome | NAY by policy | persist complete response exchange, including409, project/materialize eligible rows, then return successful result |
| query | NAY by policy | read-only wholesale snapshot, no log or DB content writes |

Record-format proposal: retain existing v1.1 COMPLETE pull/push HTTP exchange envelopes in
log. The app RequestRecord can contain the already-selected public response (202/409/etc.)
because it is an application input, not an alias for raw HTTP request. Do not introduce a
second request-only pull/push log entry, repeated record UUIDs, mutation of old JSONL lines,
or request/response pairing schema. Commit/validate retain their current synthetic shapes;
outcome logs its full response exchange only; query logs nothing. This is explicitly part
of the proposal, not a new compatibility contour. Early202 establishes log durability,
NOT completion of grouped DB projection. Final result objects still come through Store
projection/readback. Extra application model fields are excluded from HTTP-log serialization.

Timing wording to make explicit in the promise protocol: Store performs required response
persistence before returning a SUCCESSFUL completed promise result. The initial handle and
its request gate are distinct from that final result. A response persistence failure yields
(None, exc), never a usable response. For push its public202 exchange is already persisted
at ACK; its added commit/validation properties become available only at completion. A literal
requirement to finish all final application-response work before returning the initial handle
would contradict early push acceptance; do not silently change that timing.

### Proposed protocol and exception snippets

Definitions below live in protected/src/architecture.py (existing component bases retained).
The structural exception includes raise_exception so protocol-typed consumers can raise the
real exception without casts or pretending a Protocol inherits Exception.

```python
class BackendStoreAcknowledgment(StrEnum):
    ACK = "ack"
    NAY = "nay"


type ResponseRecordPromiseResult[R] = (
    tuple[R, None]
    | tuple[None, BackendComponent.StoreExceptionProperty]
)

# Nested under BackendComponent:
class RequestRecordProperty(HttpRequestLogRecordProtocol, Protocol):
    pass

class ResponseRecordProperty(HttpRequestLogRecordProtocol, Protocol):
    pass

class StoreExceptionProperty(Protocol):
    def raise_exception(self) -> NoReturn: ...

class ResponseRecordPromiseProperty[
    R: BackendComponent.ResponseRecordProperty,
](Protocol):
    """An initial request-persistence gate and an eventual application result.

    ACK means the request record was appended and fsynced in the replay log.
    NAY means it was not; IPC intentionally does not persist request records.
    Neither value describes response persistence or application success.

    Store performs response persistence where required before returning the
    successful completed result. Response-persistence failure returns
    (None, exc). Other results are exactly (response_record, None).
    The promise handle can precede completion, notably for accepted pushes.
    """
    @property
    def acknowledgment(self) -> BackendStoreAcknowledgment: ...

    async def response_record(self) -> ResponseRecordPromiseResult[R]: ...
```

Concrete exception in the new response_record_promise.py helper:

```python
@implements[BackendComponent.StoreExceptionProperty]()
class BackendStoreException(RuntimeError):
    def raise_exception(self) -> NoReturn:
        raise self
```

Preserve the original cause when converting internal exceptions; log detailed errors, retain
existing fail-closed Store state, and never stringify away the cause or retry. The concrete
ResponseRecordPromise is a FrozenStrictModel: acknowledgment is its public field, task/result
state is PrivateAttr. Awaiters shield the Store-owned completion. No arbitrary_types_allowed,
new executor service, cast, type suppression or serialized Task/Future. Reuse existing thread
offload and tracked background work; no threaded IPC. Keep completion tracked through pull
publication and shutdown, including client disconnect and failed response sends.

### Route-specific records and Store surface

Add route-specific RequestRecordProperty/ResponseRecordProperty protocols under BackendComponent.
Their common base is the corresponding HTTP-record protocol. Concrete pull/push/query records
inherit HttpRequestLogRecord; reuse existing RunOutcomeRecord as the outcome response model,
adding conformance rather than undoing P21's naming. Keep outbound Dashboard QueryRequest and
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
            raise ValueError("Pull response body is missing")
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

Public surface, abbreviated concrete names:

```python
class QueryOnlyStoreProperty(Protocol):
    def query(self, request: QueryRequestRecord) -> ResponseRecordPromise[QueryResponseRecord]: ...

class FullStoreProperty(QueryOnlyStoreProperty, Protocol):
    def pull(self, request: PullRequestRecord) -> ResponseRecordPromise[PullResponseRecord]: ...
    def push(self, request: PushRequestRecord) -> ResponseRecordPromise[PushResponseRecord]: ...
    def run_outcome(self, request: RunOutcomeRequestRecord) -> ResponseRecordPromise[RunOutcomeRecord]: ...
```

The real architecture protocols use the corresponding component record/promise protocols.
Private constructors/lifecycle/SQL/append/readback/validation/materialization helpers remain
private; public Store operations are exactly these four. Query-only object actually has only
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

### Adapter/server snippets and boundary

API preserves current response selection/timing. It creates app RequestRecords from Requests
objects. Schematic accepted-push branch (new helper names are reviewable wiring, not extra Store
methods):

```python
promise = await asyncio.to_thread(store.push, request_record)
if promise.acknowledgment is BackendStoreAcknowledgment.NAY:
    response_record, error = await promise.response_record()
    if error is not None:
        error.raise_exception()
    raise BackendStoreException("Push NAY without persistence error")

# Register before serving202; task publishes pull state before leaving the gate.
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
        raise BackendStoreException("Missing push response record")
    publish_pull_result(response_record)
```

IPC requires NAY and resolves the same tuple before transport conversion:

```python
if promise.acknowledgment is not BackendStoreAcknowledgment.NAY:
    raise BackendStoreException("IPC unexpectedly persisted a request record")
response_record, error = await promise.response_record()
if error is not None:
    error.raise_exception()
if response_record is None:
    raise BackendStoreException("Missing IPC response record")
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
wait for active HTTP exchanges plus registered API completion/publication tasks, prevent a
new HTTP request slipping through IPC admission, release on failures. No priority queue or
threaded Flask. Client timeout is explicitly allowed and never cancels durable work. No
need to reimplement the gate merely to make it shorter.

### Grouped replay and outcome changes — not hidden in a protocol-only patch

Current append_authoritative_record projects/commits EACH record. Split its private append/
fsync and common apply stages; separate durable append position from committed projection
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
This concurrency/cursor wiring is a required part of the proposal, not presumed implemented.

Current validation rollback branch discards derived effects but retains its HTTP record.
For a grouped transaction it must retain/reinsert ALL group raw HTTP rows/hashes/ordinals,
not only /validate, plus the recorded attempt, without retaining rejected derived output.
Preserve existing evidence/retry algorithms and which domain effects are retained. Final
accepted innerdicts still wait for outcome, as P24 specifies.

Run outcome uses existing durable references, checks their replay consistency without
reapplying their side effects, constructs response with commit_record_id, validation_record_id
and run_outcome_record_id, appends/fsyncs, then projects outcome/materializes in the same
transaction before exposing success. Exact self ID is the exchange UUID, not a second UUID.
Rejected409 is logged/history only: no finalization and no late-validation fence. Update P24
applicator/snapshot invariants accordingly, retaining all accepted rows/multiple commit links
and not choosing a different researcher's/session's latest commit. No synthetic missing data.

Explicit choices needing review before execution (not silently approved):
1. Preserve complete pull/push exchange envelopes as above, rather than add request-only logs.
2. Propose /completed200 only when the latest matching commit has a replay-consistent
   ACCEPTED validation; /failed200 when that latest matching result is absent/not accepted
   (including replay-consistent rejected validation),
   otherwise409. Missing evidence is distinct from corrupt persisted evidence/DB, which
   remains a Store error. /cancelled requires no commit/validation. Existing capture failures
   remain separate from domain409; do not silently drop their500/history behavior.
3. For singular IDs in outcome body, propose identifying the latest matching commit and its
   exact validation within the current NameKey/session; existing per-innerdict links retain
   every eligible accepted commit. Never overwrite earlier finalized IDs. All body/DTO/
   protocol validators and query consumers must agree; no fallback for missing new fields.
4. Dashboard's one-pull503=>failed policy is unchanged: if Store finishes successfully while
   outcome waits, /failed may then409. No automatic reclassification/retry/extraquery proposed.

### File boundary and upstream verification

Existing production files: protected architecture.py, backend API/server/Store and config,
protected IPC, run_outcome_record.py, query_response.py; necessary concrete context typing/
initialization callpoints; Dashboard snapshot/run-outcome DTO consumers ONLY as needed to
understand outcome IDs/409 without treating rejection as finalization. No UI layout/queue/
render/export redesign or extra query. Preserve P21 naming and P24 stored ID/card contour.
New small modules only: response_record_promise.py and request_response_records.py under
existing Backend helpers/data_models. Keep private Store lifecycle/query-only implementation
in its current module. Necessary imports/calls/tests only; no broad module reorganization.

Existing relevant tests: test_api, test_ipc, test_backend_store, test_http_interceptor,
startup cases in test_ui and isolated browser/operator fixture callpoints affected by Store
construction. Test real synthetic Store/log/DB and transport adapters, not source-string tests.
Cover all ACK/NAY/result combinations; fsync/request/response/projection failures; early202
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
No claim that grouped persistence or the new request/response API is already implemented.

### F8 IPC-only opening-log correction — implemented and verified

Operator explicitly authorized the previously proposed narrow correction: replace ONLY
server.py's IPC-only opening log with `logger.info("Opening read-only Backend Store")`.
Remove its detour_db_path argument; preserve INFO emission, lifecycle behavior, and all
existing tests/assertions. No other F8 diagnostics, browser/task/access/pre-start changes
are authorized here. Applied exactly that log-only change. The unchanged
`test_main_ipc_only_runs_only_the_dashboard_query_server` now PASSES (1 test,1.94s),
after its recorded pre-fix failure. Server Ruff and diff whitespace checks PASS.
No test edits, new assertions, schema/Store/IPC behavior or task changes. This closes
only the IPC-only log/test regression; other handoff blockers below remain open.

### Post-P24 handoff readiness review — 2026-09-18

Operator asked what remains before pre-commit-operator. Read-only source/task review and
bounded local checks confirm: P24 is implemented; the FULL acceptance handoff is NOT ready.
This review does not authorize additional production/task/access changes.

- Re-ran the exact existing IPC-only lifecycle test:1 FAILED in2.79s, unchanged
  AttributeError at server.py's INFO argument backend_store.detour_db_path. This is the
  known F8 log/test-double mismatch, not a newly discovered P24 failure. Subsequently
  authorized and corrected by the log-only change above; unchanged test now passes.
- Existing completed-query browser test --setup-only succeeds (13.41s, exit0; no test body
  ran). Its real isolated Store/history/private-storage fixture accepts current P24.
  This is fresh fixture integration evidence, NOT browser/Unix-socket serving evidence.
- Actual normal AI task still selects default Chrome; elevate explicitly selects Chromium.
  Last PROD Chrome prerequisite failure is not cleared by earlier Chromium passes. Verify
  normal-task Chrome provisioning or obtain explicit approval for a browser-selection edit.
- Last PROD root tests still have no subsequent passing evidence after the identified0750
  home traversal denial. Preserve real drop-before-exec; no permission/preload workaround
  or launcher change was made. An approved accessible-runtime/access correction is needed.
- The pre-Backend dequeue/Codex-busy check still lacks the proposed progress/result logs;
  source remains unchanged. Last operator Ctrl+C cause is not established. Diagnose this
  actual SSH/occupancy boundary before another expensive live-Codex run; do not bypass it.

Recommended sequence: the IPC log/test correction is now closed; separately approve/resolve
browser/root/pre-start blockers, then targeted
real browser/IPC checks and the original three root cases, then pre-commit-operator. P24's
new gate has real in-process ASGI/WSGI/threaded tests, but actual full Backend/Uvicorn/SSH
lifecycle still awaits production acceptance. Do not treat another passing IPC-only smoke
as coverage of the full-Backend gate. Preserve the rejected pre-commit wrapper shape/grep;
inspect each graph leaf's result, not just the aggregate shell status. No code/task/index
or production-resource changes were made in this handoff review; only WORK was updated.

2026-09-17 latest production review: NOT acceptance-ready. New pre-commit-operator logs
expose a missed F8 IPC-only logging/test regression, eight browser-prerequisite failures,
the now-identified root interpreter traversal denial, and a silent pre-full-Backend wait
after queue Start. Review/findings and proposed follow-up (NOT newly authorized code changes)
are pinned below. Only WORK was edited during this review; the existing IPC-only test was
run locally and reproduced the failure. Do not recommend a blind full rerun.

P1-P19's pinned code changes are present; the applicable local/delegated
checks and their limitations are recorded below. The approved Mode-3 deterministic-console
fix is also implemented and verified, with all assertions unchanged. Previously approved
follow-up code is present, including F3/F7 diagnostics, the real F4 browser/query regression
and F8 Backend logs. The latest run exposed an IPC-only logging/test regression (now fixed
and locally verified above) and missing pre-start wait diagnostics (still unresolved).

Production acceptance is NOT complete. Current retained follow-up status:
- F1 NiceGUI isolation/preservation and F2 explicit Lima fixture: implemented, locally checked.
- F4 completion helper/diagnostics and real browser/query regression: implemented; latest
  delegated rerun PASSED the complete real-query contour (47.19s, exit0). Earlier filtering
  and Backend readiness timeouts remain qualified below, not erased by the rerun.
- F6 IPC diagnostics: implemented, locally checked.
- F3 original privilege-drop launcher preserved. New root diagnostics identify the0750
  /home/anonymous.linux traversal barrier; correction/actual monitoring remain pending.
  The rejected preload workaround must not return.
- F5 latest PROD configured-binary load and config-path fallback tests PASS. Prerequisite
  is now present there; no synthetic replacement was reapplied and no test was weakened.
- F7 operator's pixi-run variable failure remains unresolved on their Lima host. Local
  activation tests pass, which does not invalidate their report. No ordinary task fix made.
- F8 detailed Backend logs are present. The subsequently authorized IPC-only opening-log
  correction is implemented; its unchanged lifecycle test passes. Direct-terminal full-HTTP
  serving/production acceptance remains unverified by this local log-only check.
The rejected browser test that substituted query_snapshot_in_browser was removed, and the
launcher regression's original15s timeout restored. Neither counts as completed coverage.
A replacement root-launcher mechanism is not approved. The operator has now approved the
failure-only diagnostics and real-browser verification scope pinned immediately below.
F4 verification must not substitute the query helper it is meant to exercise. Preserve
pre-commit wrapper structure and grep. No hidden handoff implementation remains.

Do not conflate code implemented, upstream checks passed, and production acceptance.
The retained follow-up is MOSTLY test/harness corrections, not "only test infrastructure":
F6 changes production UI diagnostics. Production storage contamination is a real operator
impact even though the proposed prevention is test isolation. Completed Backend processing
in the original acceptance log does not certify production: card/artifact assertions were
unreached and privileged watcher monitoring never started. The completion-guard correction
now has a passing real browser/owned-IPC regression. No absence of additional production
defects is established. Latest root-launch and silent pre-start findings remain unresolved;
the configured DuckDB binary now loads successfully. F8's IPC-only regression is now fixed
and locally verified; the other production acceptance findings remain open.
Non-elevate Pixi task edits still require explicit per-change approval; rejected pre-commit
wrapper edits are NOT revived. Only the agent-owned elevate task may be adjusted for
bounded delegated verification after the relevant corrections are approved and ready.

The operator authorized implementation of all pending WORK, strictly narrowly as pinned.
During implementation they added P12: first probe logs, then a whole-ui.py missing-emit_log
review including DOCX download. No new service hierarchy, recovery contour or extra flags
were introduced. Any future deviation/scope extension requires explicit operator approval.
TASK + this WORK stand alone; HUMANS is a human-owned historical record, not another
verbatim backlog. The prior handoff/conversation reconciliation is complete. No hidden
pending approved implementation items remain from that reconciliation.

Git remains READ ONLY for the agent. The operator stages/commits concurrently; agent review
does not alter the index. The original follow-up review used ab8d761; the operator has since committed changes.
dc951fe is the original
implementation checkpoint, NOT the pre-change baseline for the Mode-3 investigation.
Paths below are detour-relative unless explicitly marked repository-root-relative.

Scope correction (2026-09-16): protected/src/llm_inference_api/sample_deploy is
OUT OF SCOPE, as pyproject.toml's pytest/Ruff exclusions and detour mypy.ini already
specified. Its optional illustrative proxy is not production detour code. The operator
reverted the mistakenly included proxy/models/tests/launcher changes; review confirms no
remaining staged or unstaged changes there and no in-scope dependency on those changes.
Do not edit or run its tests. The conversion inventory below excludes it.

## Body-capture decision — keep v1.1; v2 docstring note only

Operator rejected changing the v1.1 body format as breaking. Keep ALL v1/v1.1 body fields,
serialization, decoding, conversion and consumers unchanged. The proposed tagged-base64
v1.1 representation is NOT pending work and must not be implemented. Only a short docstring
note on shared HttpRequestLogRecord is authorized and now added: current v1.1 capture uses
Response.text and replay reconstructs UTF8, not original bytes; a future v2 should explicitly
serialize body bytes, including Response.content. No v2 model/protocol/version/flag/migration
is authorized or implemented. Materialization/IPC ordering is implemented under P24 below.

Installed Requests2.34.2 source reviewed to answer the operator's reliability question:
HTTPAdapter initializes Response.encoding from Content-Type charset; without charset it
uses ISO8859-1 for text content and UTF8 for application/json. Otherwise encoding is None.
Response.text uses that encoding (or any explicit override); only when None does it call
apparent_encoding, here backed by charset_normalizer. Decoding uses errors="replace";
unknown codecs fall back to UTF8 with replacement. Binary content is not rejected by MIME
or guaranteed to raise an error: it can produce gibberish/control characters/U+FFFD while
original Response.content stays untouched. The log retains only the decoded result.
Correct UTF8 JSON is suitable for current text consumers; this is not byte-level fidelity.
Docstring-only Ruff and diff whitespace checks PASS; no new tests or runtime changes.

Endpoint-specific source review: main pipeline uses OpenAlex /authors (select=id) and
/works (select=id,title); detour institution validation uses OpenAlex /institutions/{id}
and ROR /v2/organizations/{id}. All expect JSON, not binary payloads. Valid UTF8 with
application/json decodes deterministically, preserving Unicode titles/institution names.
Residual risk is malformed/mislabelled encoding: damaged strings can remain valid JSON,
so titles could be corrupted or exact institution-name checks could falsely fail. Author
IDs are ASCII. Detour live/replay both consume the same persisted decoded text through
to_response; that ensures consistent interpretation, not original-byte preservation.
Assessment is source-based, without fresh provider calls/header verification. No concrete
encoding failure identified; no further v1/v1.1 implementation change is proposed.

Operator authorized extending only the class docstring with the current provider/local
route inventory, retained-v1.1 rationale, mandatory case-by-case review of new endpoints,
and desirable raw-body-byte capture in v2. Applied. Local-format wording is deliberately
precise: /push specifies application/json in OpenAPI; /pull also returns UTF8 NDJSON or
Markdown, so not every local body is JSON. Synthetic /commit and /validate are identified
as such, with the recorded outcome routes enumerated. No runtime/schema changes.

## P24 — Implemented and locally verified after operator restore: outcome-triggered innerdict materialization

Operator requested a NEW scope item and concrete snippets, not a reopening of P22.
Keep existing Backend processing,
but defer innerdict materialization until the matching run outcome is applied.
The final persisted innerdict must contain the same data/ID order currently shown by the
Dashboard card; DOCX/TXT renderers merely render it, as the main pipeline does. Validation
and outcome IDs must not exist only in a transient UI copy. This section records the
exact revised scope, now explicitly approved by the operator: "approved within the narrow exact shape".
No casts, runtime argument to the outcome applicator, or unrelated changes are authorized.

Intended ordering, replacing the Assistant's previous "whichever prerequisite comes last"
proposal (DO NOT implement that alternative):
- Validation must be durably persisted/fsynced before a410 can be returned. Preserve the
  accepted validation/standardized-submission basis for410, independent of final innerdicts.
- server.py orchestrates IPC exclusion while FastAPI work is in progress. IPC must wait,
  including for durable completion of pending commit/validation work following accepted
  pushes; otherwise a202 response would leave the same ordering gap. A client may time out;
  no special timeout recovery, retry or fabricated result is requested.
- The admission boundary must ensure in-flight HTTP records have persisted before outcome
  logging and must prevent a new HTTP operation slipping through that boundary. Store locks
  alone protect transactions, not the entire request/background-work lifetime.
- Once outcome is durably logged/projected, Store has the prerequisites and materializes
  the final innerdict through the common live/replay applicator, without UI joins or live-only
  work. Do not infer a broad replacement of existing validation/evidence/output-row processing.
  Because current query builds committed innerdicts directly from codex_output_rows, simply
  moving the materialize_innerdicts call would still expose unfinished data there; the narrow
  query/invariant wiring must expose finalized persisted innerdicts instead.
- Cancellation records its cancellation outcome and does not invent/finish missing data,
  undo earlier durable data, or introduce recovery. Previously persisted data remains;
  work that was not persisted is not manufactured. Exact final row eligibility follows the
  existing accepted-data contour, not a new "completed-only" policy inferred by the agent.
- Current DashboardQuerySnapshot enforces accepted validation iff committed innerdict exists;
  the deferred-materialization interval requires a corresponding narrow invariant adjustment.

Approved implementation defers codex_innerdicts until outcome, queries that persisted grouped
table, validates both stored IDs, and removes P22's transient UI augmentation. /pull410
continues using accepted validation/submission, not output innerdicts. Store I/O ownership
and common replay application remain intact. No separate reconciliation/recovery mechanism.

### Approved file and behavior boundary

Production files: backend server.py/api.py/Store, protected backend ipc.py/vars.py,
committed_innerdict.py, Dashboard dashboard_query_snapshot.py/ui.py and its Locale.
Only necessary direct imports/callpoints and existing associated tests. No main-pipeline
or shared HttpRequestLogRecord changes, new HTTP model, route/body change, new service,
task/CLI/config change, automatic query, timeout/retry policy or DB recovery/migration.
All DB/log I/O remains owned by Store; domain SQL/algorithms stay in api.py.

1. Keep validation/evidence/accepted-output-row processing as now. Add two nullable
   output-row columns, in the desired card order immediately after commit ID. These are
   genuine Backend column constants, replacing the P22 display-only labels. Before outcome
   they remain internal NULLs, never placeholder-bearing committed innerdicts.

   ```python
   # protected Backend vars.py
   KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL = f"{AI_AUGMENT_COLUMN_PREFIX}validation_record_id"
   KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL = f"{AI_AUGMENT_COLUMN_PREFIX}run_outcome_record_id"

   # In CODEX_OUTPUT_SCHEMA, immediately after the existing commit-ID column:
   (KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL, "VARCHAR"),
   (KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL, "VARCHAR"),

   # In write_accepted_submission's output_row, in the same position:
   KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL: None,
   KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL: None,
   ```

   Remove ONLY append_codex_output's _replace_codex_output_view(store) call. Validation
   continues storing output rows/attempts and returning its DB-readback result. Preserve
   append/fsync -> projection/readback -> _apply_attempt_record -> /pull410 ordering.
   No need to make /pull wait for outcome; that would deadlock normal finalization.

2. In Store._apply_log_record, after the existing HTTP-row insertion/readback, add outcome
   dispatch alongside /validate, within the SAME existing transaction:

   ```python
   elif record.method == api.HTTP_POST_METHOD and record.path in RUN_OUTCOME_PATHS:
       api._apply_run_outcome_record(
           self,
           RunOutcomeRecord.from_http_request_log_record(record),
       )
   ```

   New narrow api._apply_run_outcome_record(store, outcome) selects only
   unfinalized accepted output rows for outcome.run_outcome_request.namekey. For each,
   resolve its typed commit from Store, require that commit's Codex session to equal
   outcome.run_outcome_response_body.codex_session_record.session_id, and load its existing
   typed validation record directly from persisted HTTP history. No runtime argument or
   runtime-dependent submission revalidation is needed for this linkage step. Require
   accepted validation, exact commit linkage and
   commit ordinal < validation ordinal < outcome ordinal. No session/matching accepted
   row means outcome history only. Do not choose a researcher's latest unrelated commit.
   Use these existing durable typed records to update the two columns:

   ```python
   def _apply_run_outcome_record(
       store: AiAugmentBackendStore,
       outcome: RunOutcomeRecord,
   ) -> None:
       # Matching, validation and update steps specified here.
       ...
   ```

   ```python
   # Inside that applicator, after the matching/ordinal checks above:
   store.execute(
       f"UPDATE {CODEX_OUTPUT_ROWS_TABLE} SET "
       f"{duckdb_quote_identifier(KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL)} = ?, "
       f"{duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL)} = ? "
       f"WHERE {duckdb_quote_identifier(KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL)} = ?",
       [str(validation.record_id), str(outcome.record_id), str(commit.record_id)],
   )
   # Once, after all matching rows were updated (only if at least one changed):
   _replace_codex_output_view(store)
   ```

   _replace_codex_output_view retains the existing shared materializer and ordered column
   projection, adding this filter to its SELECT:

   ```python
   WHERE {duckdb_quote_identifier(KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL)} IS NOT NULL
     AND {duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL)} IS NOT NULL
   ```

   Thus codex_innerdicts never contains an unfinished accepted section. The existing
   materializer still replaces its grouped table; no new append-only table algorithm.
   Later outcome records do not rewrite IDs on already finalized sections. A /validate
   arriving after a matching session outcome must fail rather than create a late dangling
   accepted row or trigger retrospective materialization. This is an ordering check, not
   automatic recovery. All three outcome paths use this contour, including logged500
   partial snapshots when the session is known. Do not infer completed-only eligibility.
   Cancellation adds no validation/capture beyond the existing outcome handler: it waits
   for already-running authoritative work, records its outcome, and preserves durable data.
   Missing/rejected validation never becomes an accepted row or invented placeholder.

3. Query must read codex_innerdicts, not reconstruct output from codex_output_rows.
   Preserve its absent-table empty result and typed commit linkage/error handling:

   ```python
   rows = store.execute(
       f"SELECT {duckdb_quote_identifier(KTP_NAMEKEY_COL)}, "
       f"{duckdb_quote_identifier(KTP_INNERDICT_JSONLINES_COL)} "
       f"FROM {CODEX_INNERDICT_TABLE} "
       f"ORDER BY {duckdb_quote_identifier(KTP_NAMEKEY_COL)}"
   ).fetchall()
   for namekey_json, payload in rows:
       for values in loads_jsonlines(payload):
           # The shared materializer puts NameKey in the grouping column, not JSONL.
           innerdict = InnerDict.from_mapping(
               {KTP_NAMEKEY_COL: namekey_json, **values}, _CodexMatchProcedure(),
           )
           # Existing typed commit lookup and CommittedInnerDict construction follow.
   ```

   CommittedInnerDict requires both new UUID fields. DashboardQuerySnapshot changes its
   accepted-iff-committed check to accepted-with-matching-outcome iff committed, permitting
   accepted-but-not-finalized records before outcome. Check the persisted validation UUID
   against that commit's typed validation, and resolve the persisted outcome UUID in query
   history to verify NameKey/session (not merely the latest outcome). Keep all existing
   uniqueness, researcher, commit and session checks; no permissive fallback.

4. server.py owns one instance-local admission gate for full Backend. Use a small
   _BackendRequestGate(FrozenStrictModel) with private asyncio.Condition/counter/boolean;
   no public config fields or arbitrary_types_allowed. Gate methods run only on the
   Uvicorn loop. Normal HTTP exchanges may remain concurrent; an IPC waiter blocks NEW
   admission, waits for current exchanges to finish, then awaits already-scheduled
   authoritative background work. Existing background tasks do not acquire this gate.
   Private state on the new server-local model:

   ```python
   class _BackendRequestGate(FrozenStrictModel):
       _condition: asyncio.Condition = PrivateAttr(default_factory=asyncio.Condition)
       _http_requests: int = PrivateAttr(default=0)
       _ipc_pending: bool = PrivateAttr(default=False)
   ```

   Core methods on that model:

   ```python
   @asynccontextmanager
   async def http(self) -> AsyncIterator[None]:
       async with self._condition:
           await self._condition.wait_for(lambda: not self._ipc_pending)
           self._http_requests += 1
       try:
           yield
       finally:
           async with self._condition:
               self._http_requests -= 1
               self._condition.notify_all()

   @asynccontextmanager
   async def ipc(self) -> AsyncIterator[None]:
       try:
           async with self._condition:
               self._ipc_pending = True
               await self._condition.wait_for(lambda: self._http_requests == 0)
           pending = tuple(api.AUTHORITATIVE_BACKGROUND_TASKS)
           if pending:
               await asyncio.gather(*(asyncio.shield(task) for task in pending))
           yield
       finally:
           async with self._condition:
               self._ipc_pending = False
               self._condition.notify_all()
   ```

   Existing IPC is single-threaded (threaded=False), hence one IPC scope at a time. A thin
   server-owned ASGI middleware surrounds the COMPLETE HTTP call, including authoritative
   record persistence and response send; non-HTTP/lifespan passes through untouched.
   Wire the gate via full_backend_application/app state, once per application lifecycle;
   register the middleware only once, so repeated factory calls cannot nest two gates.
   no gate inside Store or parent-process knowledge. An HTTP call does not retain its
   slot after202 while background validation runs, so ordinary /pull503 remains possible.

   Inside server.lifespan, bridge existing IPC thread to the loop with this context:

   ```python
   loop = asyncio.get_running_loop()

   @contextmanager
   def ipc_request_scope() -> Iterator[None]:
       scope = gate.ipc()
       asyncio.run_coroutine_threadsafe(scope.__aenter__(), loop).result()
       try:
           yield
       finally:
           asyncio.run_coroutine_threadsafe(
               scope.__aexit__(None, None, None), loop,
           ).result()
   ```

   Thread this optional scope factory through the existing ipc start/app functions; its
   default is nullcontext for IPC-only. Wrap the complete WSGI request/response iterable
   and its close in that scope, so OPTIONS and error responses cannot bypass the gate.
   Do not gate only domain handlers. The server-owned ASGI call has this exact boundary:

   ```python
   if scope["type"] != "http":
       await self.app(scope, receive, send)
       return
   async with scope["app"].state.request_gate.http():
       await self.app(scope, receive, send)
   ```

   Hold IPC admission through snapshot capture, outcome append/fsync/application, typed
   readback and response. No server-side deadline/retry/503 substitution for IPC; a client
   may time out without cancelling durable server work. Preserve existing fatal failures.
   Operator additionally requires an appropriate docstring explicitly stating that IPC
   intentionally permits client timeouts while waiting for FastAPI work to finish; such
   timeouts do not cancel Backend processing/persistence. Add this on the IPC gate method.
   Full lifespan MUST change synchronous IPC stop to the following, otherwise its join
   could block the loop which the waiting IPC request needs:

   ```python
   await asyncio.to_thread(ipc.stop_dashboard_query_server, dashboard_query_server)
   ```

   IPC-only serving/initialization/permissions are unchanged. Add concise existing-style
   waiting/admitted/materialized logs at the new boundaries, not a logging framework.

5. Remove P22's transient metadata-lookup/insertion block and unused display-only labels.
   Restore the pure card callback and direct caller (other card/export behavior unchanged):

   ```python
   def card(self, researcher: _Researcher) -> str:
       selected = selected_card_outer_dict(researcher)
       # Existing build_cards call, arguments and result checks unchanged.

   # Controller callback annotation and invocation:
   render_card: Callable[[_Researcher], str]
   markdown = await asyncio.to_thread(self._render_card, researcher)
   ```

   Existing value-formatting selection remains; no metadata augmentation or independent
   DOCX/TXT/export logic. Display, both downloads and publish completed use identical
   persisted metadata through existing rendering primitives.

### Current schema and verification for P24

Only the current schema exists. The operator explicitly removed the special output-schema
guard and its dedicated test; do not restore them. Required current columns and fields are
accessed/validated normally. No compatibility branches, migration, backfill, reconciliation,
snapshot enrichment or automatic query. Explicit confirmed --new remains ordinary current
initialization/replay, not a special handling path for another schema. Do not operate on
operator resources.

Extend existing test_api/test_backend_store/test_http_interceptor/test_ipc/test_ui coverage:
- Real Store append/fsync/readback: accepted validation and /pull410 before outcome, but
  no committed innerdict; outcome yields exact adjacent IDs and unchanged remaining data.
- Same replay inputs reproduce the exact materialized JSONL/query result, no network;
  cancelled/failed/no-session/rejected/no-validation cases preserve only eligible data.
- Correct NameKey/session binding, multiple commits, already-finalized IDs unchanged,
  malformed/mismatching IDs and late validation fail closed.
- Real gate/ASGI/WSGI in process with synchronization events: HTTP persistence/response
  blocks all IPC including OPTIONS; outstanding post202 work blocks IPC; new HTTP cannot
  slip through; /pull503 stays available before IPC admission; exceptions release gate;
  shutdown can finish an in-flight IPC request without event-loop deadlock.
- Actual card renderer/wholesale query roundtrip and existing DOCX/TXT/publish consumers:
  no metadata synthesis, original snapshot remains unchanged, interim accepted state valid.
Use synthetic fixtures and real DB/record paths, not assertions on source strings or mocked
materialization. Ruff/strict detour mypy plus relevant shared-consumer checks. No live Codex,
ordinary task edits or unrelated F3/F7/F8/browser corrections bundled in P24. Production
acceptance remains separate. Reimplementation and applicable local verification are complete.

### P24 retry implementation/evidence — 2026-09-18

Operator clarified the subsequent rollback message referred to the PRIOR restore, not
this execution. The brief mistaken pause did not alter work or authorization. The agent
made no Git mutation; preserve the operator's concurrent staging.

Implemented in exactly the nine pinned production files, with four existing test modules
and WORK. Domain SQL remains in API, all DB/log I/O in Store. No schema-specific guard,
compatibility audit, DTO-default removal, stricter card-format parser, extra casting or
suppression, task/config/CLI change, production data access or unrelated F3/F7/F8 fix.
Outcome linkage reads the exact accepted attempt's validation UUID and resolves it through
Store's typed HTTP readback. Card callbacks again consume only the researcher. IPC-only
uses nullcontext unchanged; full Backend owns the private-state FrozenStrictModel gate.
The small Flask adapter scopes the complete WSGI iterable and close, including OPTIONS
and errors, without reassigning methods or suppressing types. The IPC timeout docstring
is present. Full shutdown offloads IPC stop/join while retaining the server event loop.

Fresh checks (overlapping selections; do not add these into a claimed single suite run):

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

Development failures were corrected in the new tests, not concealed by production changes:
base-versus-specialized HTTP model and procedure-object identity comparisons became exact
serialized readback/data comparisons; the invalid-version test accidentally supplied a
valid UUIDv7 and now supplies UUID(int=0). The factory test now uses isinstance/issubclass
with the actual Starlette middleware factory types instead of a mypy-incompatible identity
comparison. No casts/suppressions or weakened existing production checks.

The existing synthetic flat-row materializer unit now explicitly materializes its finalized
rows; append no longer does so. The historical capture test's source callpoint explicitly
records its outcome before unchanged final card assertions. That capture was NOT accessed
or executed; it was statically checked. Its synthetic outcome helper lives in the existing
interceptor module and is imported only inside that consuming test helper.

Threaded bridge/shutdown tests use a test-only loop timer through Runner cleanup, retaining
the restriction-aware test boundary from the earlier discarded run. Actual gate, WSGI,
thread bridge and thread offload execute; this does NOT certify host self-pipe wakeup,
real Unix/TCP serving or the full Uvicorn/SSH/Codex lifecycle. No production timer/deadline/
retry was added. The410 test calls the real sync pull handler through an async test route,
avoiding an unrelated framework threadpool boundary; persistence middleware and Store are real.

No P24 implementation or feasible local check remains pending. Live socket/browser/root/
Codex production acceptance remains separate and unperformed here. Existing unrelated
production-review corrections remain awaiting approval; this item does not close them.

## P23 — Completed: shared HTTP-record protocol and record-protocol inheritance

Explicitly requested now, surgically. Only repository-root
src/helpers/data_models/http_request_log.py and detour protected/src/architecture.py plus
WORK need production edits. Add HttpRequestLogRecordProtocol alongside the existing model;
HttpRequestLogRecord gets @implements[HttpRequestLogRecordProtocol](). Add the shared protocol
as a base of CommitRecordProperty, ValidationRecordProperty and RunOutcomeRecordProperty.
Keep their existing specific properties/methods and concrete http_request_log_record getters.
RunOutcomeRequest is a wrapper, not an HTTP-record subclass; do NOT add inheritance there.

Core wiring (the shared protocol's fields/methods are specified below and in its source):

```python
@implements[HttpRequestLogRecordProtocol]()
class HttpRequestLogRecord(BaseModel):
    # Entire existing model body unchanged.
    ...

class CommitRecordProperty(
    HttpRequestLogRecordProtocol, ComponentProtocol.PropertyProtocol, Protocol,
):
    # Existing commit-specific members unchanged.
    ...
```

ValidationRecordProperty and RunOutcomeRecordProperty gain the same protocol base, keeping
their current ComponentProtocol bases/nesting. Their earlier pinned snippets below include
this P23 addition; no P20/P21 wire behavior is changed.

Protocol mirrors all16 serialized v1.1 fields, with the exact existing nullable/types and
from_response/to_response signatures. Read-only properties express structural access; no
runtime_checkable/extra framework. The shared model still supports schema_version1 as well
as1.1: retain its existing HttpRequestLogSchemaVersion union honestly, without silently
removing main-pipeline v1 compatibility. coerce_schema_v1 is excluded implementation input,
not a v1.1 record field; omit it and Pydantic validator/serializer internals from the protocol.
No Pydantic config, field, serialization, conversion, validation behavior, constructor or
runtime inheritance change. No broad consumer annotations, new shared re-exports or tasks.
Verify @implements conformance with strict mypy, shared/main mypy and existing HTTP-record
v1/v1.1/conversion and focused derived-record tests; no mock-only protocol test needed.

Implementation is present in exactly those two production files. Ruff PASS; strict detour
mypy PASS54files. Existing shared HTTP-record plus commit/validation/run-outcome selection:
53 passed,185 deselected (6.78s); no new test assertions or skips. AST comparison confirms
all16 serialized field types and both response-conversion signatures exactly match the
concrete model, whose entire body is unchanged from HEAD. Main mypy selection (src/tests)
invoked with AI-environment stubs reported20 errors in7 untouched pandas/docx consumers,
none in the modified HTTP model (68files checked). Rerun with the designated main-pipeline
executable (.pixi/envs/default/bin/mypy src tests, under the required outer Pixi invocation):
PASS68files, without source edits between runs. The initial AI-environment check was not
green and is not counted as a pass; no unrelated correction, dependency or task changes.
Final git diff HEAD --check PASS; agent Git use stayed read-only. P23 has no pending work.
Read-only main-pipeline review confirms step_10_build_cards passes the selected OuterDict
into shared build_cards, which renders innerdict.data in order; TXT/DOCX consume that same
Markdown. No main-pipeline runtime/data or card/IPC/lifecycle implementation was changed.

## P20 — Completed: /validate model/protocol consolidation

Operator approved the immediately preceding proposal/snippets and requested pinning them
in WORK. Implementation and focused verification are complete, not approval of other
operator-review corrections. Preserve the exact narrow shape below.

Four production files only:
- protected/src/architecture.py
- src/backend/helpers/data_models/validation_event.py
- src/backend/api.py
- src/backend/helpers/data_models/query_response.py

Necessary direct imports and focused existing-test additions are included. No new module,
Store orchestration changes, endpoint renaming, request/response format change, new config,
new ConfigDict, shared HttpRequestLogRecord change, pasted-model change or task edits.
Commit/run-outcome/pull/push behavior stays unchanged. /validate remains a synthetic,
request-only durable record, NOT a served endpoint; no ValidationResponse model is added.

### 1. Corresponding architectural protocols

Under BackendComponent in protected/src/architecture.py (JsonValue is a normal Pydantic
import; retain existing Mapping/UUID/Literal/Self imports):

```python
class ValidationRequestBodyProperty(
    ComponentProtocol.PropertyProtocol,
    Protocol,
):
    @property
    def commit_id(self) -> UUID: ...

    @property
    def post_commit_validation(
        self,
    ) -> BackendComponent.PostCommitValidationProperty: ...

    @property
    def submission_type(
        self,
    ) -> Literal["Submission", "StandardizedSubmission"] | None: ...

    @property
    def submission(self) -> Mapping[str, JsonValue] | None: ...

    @property
    def http_record_ids(self) -> tuple[UUID, ...]: ...

    def validate_body(self) -> Self: ...


class ValidationRecordProperty(
    HttpRequestLogRecordProtocol,
    ComponentProtocol.PropertyProtocol,
    Protocol,
):
    @property
    def http_request_log_record(self) -> HttpRequestLogRecord: ...

    @property
    def validation_request_body(
        self,
    ) -> BackendComponent.ValidationRequestBodyProperty: ...

    def validate_record(self) -> Self: ...

    @classmethod
    def from_http_request_log_record(
        cls,
        record: HttpRequestLogRecord,
    ) -> Self: ...
```

The existing body gains only its conformance decorator; fields/body validation stay:

```python
@implements[BackendComponent.ValidationRequestBodyProperty]()
class ValidationRequestBody(FrozenStrictModel):
    # Existing fields and body validation unchanged.
```

### 2. Typed record in the existing validation_event.py

Reuse existing schema/method/synthetic-host/header constants through direct imports.
Follow BackendCommitRecord's excluded parsed-body pattern; no second serialized body:

```python
@implements[BackendComponent.ValidationRecordProperty]()
class BackendValidationRecord(HttpRequestLogRecord):
    validation_request_body: ValidationRequestBody = Field(exclude=True)

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord:
        return self

    def validate_record(self) -> Self:
        if (
            self.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            or self.record_id.version != 7
            or self.method != HTTP_POST_METHOD
            or self.scheme != SYNTHETIC_SCHEME
            or self.host != SYNTHETIC_HOST
            or self.port is not None
            or self.path != VALIDATE_PATH
            or self.query
            or set(self.request_headers) != {SOURCE_KEY_HEADER, NAME_KEY_HEADER}
            or self.request_body is None
            or self.response_code is not None
            or self.response_headers is not None
            or self.response_body is not None
            or self.received_at_unix_usec is not None
            or self.ready_to_respond_at_unix_usec is not None
            or self.duration_usec is not None
        ):
            raise ValueError("validation HTTP record has an invalid contour")

        parsed = ValidationRequestBody.model_validate_json(self.request_body)
        if parsed != self.validation_request_body:
            raise ValueError("validation request body does not match its record")
        return self

    @model_validator(mode="after")
    def _validate_record(self) -> Self:
        return self.validate_record()

    @classmethod
    def from_http_request_log_record(
        cls,
        record: HttpRequestLogRecord,
    ) -> Self:
        if record.request_body is None:
            raise ValueError("validation request body is missing")
        return cls(
            **record.model_dump(),
            validation_request_body=ValidationRequestBody.model_validate_json(
                record.request_body,
            ),
        )
```

Existing ValidationRequestBody.http_record changes only return type/constructor and adds
the excluded typed body; its commit-ID guard and all envelope arguments remain unchanged:

```diff
- def http_record(self, commit: BackendCommitRecord) -> HttpRequestLogRecord:
+ def http_record(self, commit: BackendCommitRecord) -> BackendValidationRecord:
```

```diff
- return HttpRequestLogRecord(
+ return BackendValidationRecord(
+     validation_request_body=self,
      schema_version="1.1",
```

### 3. Existing consumer wiring

api._validated_http_record delegates /validate before its commit-only branch, preserving
the current generic return and error translation:

```python
if route == (HTTP_POST_METHOD, VALIDATE_PATH):
    try:
        BackendValidationRecord.from_http_request_log_record(validated)
    except ValueError as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_INVALID) from exc
    return validated
```

Remove /validate from the subsequent commit-specific branch; retain commit checks.
api._apply_validation_record obtains the typed body at its existing entry:

```python
validation_record = BackendValidationRecord.from_http_request_log_record(record)
body = validation_record.validation_request_body
```

KEEP all Store-dependent checks in that applicator: preceding commit/provider records,
matching commit headers, exact re-evaluated verdict/submission/consumed-provider-ID
agreement. Models must not acquire Store/DB access. Its existing result update becomes:

```python
return evaluated.model_copy(update={
    "http_records": tuple(inputs),
    "validation_record": validation_record,
}), commit_database
```

In query_response.py, change only the domain AgentRuntimeAttemptRecord field:

```python
validation_record: BackendValidationRecord | None = None
```

KEEP _AgentRuntimeAttemptRecordJson.validation_record as HttpRequestLogRecord | None
for the unchanged serialized shape. Its rehydration now constructs:

```python
validation_record = (
    None
    if serialized.validation_record is None
    else BackendValidationRecord.from_http_request_log_record(
        serialized.validation_record,
    )
)

if validation_record is not None:
    body = validation_record.validation_request_body
    # Existing body/result/reference consistency checks remain.
```

Pass validation_record to the returned domain object. Add the corresponding getter to
BackendComponent.AgentRuntimePort.AttemptRecordProperty:

```python
@property
def validation_record(
    self,
) -> BackendComponent.ValidationRecordProperty | None: ...
```

Store's append/apply/readback orchestration is untouched, including:

```python
self.append_authoritative_record(body.http_record(commit))
```

### Verification and explicit tightening

One intentional tightening IS approved: QueryResponse rehydration now validates the entire
/validate envelope, not only its body/linked values. Preserve optional None for existing
DTOs; no new compatibility fallback or migration. No valid-record wire/schema/UUID change.
Extend focused existing test_api/test_http_interceptor coverage as appropriate for exact
serialized JSON/UUID preservation, typed live/replay/query readback, malformed-envelope
rejection and typed-body mismatch rejection. Preserve existing linkage/replay-agreement
checks. Run applicable Ruff/strict mypy and these meaningful regressions; this model-only
scope does not require a live Codex/operator run.

P20 implementation is present in the four pinned production files and existing
test_http_interceptor.py. Initial focused checks:21 passed,171 deselected (27.77s),
Ruff and diff whitespace checks passed. Strict mypy identified Pydantic's decorated
validator descriptor as incompatible with protocol callable methods. Kept both public
validation methods and their rules unchanged, using the existing commit-record pattern:
private @model_validator wrappers call validate_body()/validate_record(). No protocol
weakening or type suppression. The snippet above reflects this typing-only wiring;
ValidationRequestBody similarly has _validate_body calling validate_body. Final check:
21 passed,171 deselected (29.25s); strict mypy passed54files. The two test-only header
imports were corrected to their defining modules, without re-export assumptions.

## P21 — Completed: RunOutcomeRecord naming consolidation

Operator approved the exact immediately preceding proposal and requested recording it with
exact snippets. Implementation and focused verification are complete. Unlike /validate, run outcomes
already have a specialized full-exchange model: rename that existing model; do NOT introduce
another wrapper. This scope does not authorize the separate operator-review corrections.

### Exact rename scope

| Current | Approved replacement |
|---|---|
| RunOutcomeResponse | RunOutcomeRecord |
| RunOutcomeResponseProperty | RunOutcomeRecordProperty |
| validate_run_outcome_response() | validate_record() |
| _validate_run_outcome_response() | _validate_run_outcome_record() |
| src/backend/helpers/data_models/run_outcome_response.py | src/backend/helpers/data_models/run_outcome_record.py |
| _RunCommitView.run_outcome_response | _RunCommitView.run_outcome_record |

Keep RunOutcomeRequest, RunOutcomeResponseBody, their protocols, and the field
run_outcome_response_body unchanged: those names correctly describe their contents.
The module move is a straight rename, with necessary import updates; no duplicate module,
compatibility alias, new ConfigDict or unrelated renaming/test-file moves.

### 1. Rename the existing record protocol

Keep it under BackendComponent.ControlCentrePort in protected/src/architecture.py:

```python
class RunOutcomeRecordProperty(
    HttpRequestLogRecordProtocol,
    ComponentProtocol.PortProtocol.PropertyProtocol,
    Protocol,
):
    @property
    def run_outcome_request(
        self,
    ) -> ControlCentreComponent.BackendPort.RunOutcomeRequestProperty: ...

    @property
    def http_request_log_record(self) -> HttpRequestLogRecord: ...

    @property
    def run_outcome_response_body(
        self,
    ) -> BackendComponent.ControlCentrePort.RunOutcomeResponseBodyProperty: ...

    @property
    def run_outcome(
        self,
    ) -> ControlCentreComponent.LifecycleProperty: ...

    def validate_record(self) -> Self: ...

    @classmethod
    def from_http_request_log_record(
        cls,
        record: HttpRequestLogRecord,
    ) -> Self: ...
```

Update existing references in QueryResponseProperty.run_outcome_records and
RunProperty.run_outcome_record. Do not move the protocol to another architectural port.

### 2. Rename the existing model and validator methods

In the renamed module:

```diff
- @implements[BackendComponent.ControlCentrePort.RunOutcomeResponseProperty]()
- class RunOutcomeResponse(HttpRequestLogRecord):
+ @implements[BackendComponent.ControlCentrePort.RunOutcomeRecordProperty]()
+ class RunOutcomeRecord(HttpRequestLogRecord):
      run_outcome_request: RunOutcomeRequest = Field(exclude=True)
      run_outcome_response_body: RunOutcomeResponseBody = Field(exclude=True)
```

```diff
- def validate_run_outcome_response(self) -> Self:
+ def validate_record(self) -> Self:
```

The entire validation body remains unchanged. Its existing wrapper becomes:

```python
@model_validator(mode="after")
def _validate_run_outcome_record(self) -> Self:
    return self.validate_record()
```

Keep both existing constructor implementations unchanged, using the renamed class:

```python
RunOutcomeRecord.from_run_outcome_request(...)
RunOutcomeRecord.from_http_request_log_record(...)
```

### 3. Preserve the persistence contour

The existing IPC handler changes by naming substitution only:

```python
record = RunOutcomeRecord.from_run_outcome_request(
    ipc_request,
    response_code=response_code,
    response_headers=response_headers,
    response_body=snapshot,
    ready_to_respond_at_unix_usec=ready_at_unix_usec,
)

# Existing try/except and fatal persistence-error handling remain.
stored = runtime.pipeline_config.backend_store.append_authoritative_record(
    record.http_request_log_record,
)
return RunOutcomeRecord.from_http_request_log_record(stored)
```

Keep the actual existing try/except around append; the excerpt above does not remove it.
Flask continues sending the returned DB-readback record's response fields. Do not send
the response before persistence/readback or change Store ownership/transaction ordering.

### 4. Update typed consumers, preserving serialized keys

```python
# QueryResponse
run_outcome_records: tuple[RunOutcomeRecord, ...] = ()

# Run — field name already correct
run_outcome_record: RunOutcomeRecord | None = None

# _RunCommitView — rename the misleading field and its consumers
run_outcome_record: RunOutcomeRecord | None
```

Query's serialized DTO remains:

```python
run_outcome_records: tuple[HttpRequestLogRecord, ...]
```

Rehydration uses the renamed class:

```python
run_outcome_records=tuple(
    RunOutcomeRecord.from_http_request_log_record(record)
    for record in serialized.run_outcome_records
)
```

Update imports, annotations and direct call sites in api.py, protected/src/backend/ipc.py,
Store query, query_response.py, Dashboard dashboard_query_snapshot.py/run_event.py/ui.py,
and corresponding existing tests/helpers. Include the _RunCommitView constructor keyword,
property consumers and associated test-helper naming. Do not rename genuine response-body
or HTTP-response concepts. No unrelated renames or test-file moves.

### Unchanged boundaries and verification

- /completed, /failed, /cancelled; request headers and empty request body.
- Response body, HTTP codes, UUIDs, timestamps and ALL existing validation rules.
- Replay-log/DB/NiceGUI serialized shapes and storage keys.
- Store ownership, append/apply/readback ordering, queue and finalization behavior.

Verify with existing run-outcome IPC, replay, query-roundtrip and Dashboard tests plus
Ruff/strict mypy. No new testing framework, live Codex run, production-data access, task
edit or permission change. P21 applied exactly as a naming-only change. No old full-record names/imports remain;
response-body names are unchanged. Renamed record module compared against HEAD: exact
text match after only the four approved identifier substitutions. IPC still persists,
reads back and only then responds; its fatal error path remains unchanged.
Verification:21 focused IPC/replay/query/UI cases passed,361 deselected (14.00s).
Ruff PASS; strict mypy PASS54files; diff whitespace PASS. No task edits or live services.

## P22 — Completed historical scope: display-only IDs on researcher cards

Operator requested this surgical addition: in the researcher card, immediately after the
existing commit record ID, show the validation record ID and then the run outcome record
ID. Feasible using the existing NiceGUI wholesale query snapshot; no new Backend query,
record, persisted field or DB column was needed for that former display-only scope.
Its implementation/checks are historical. P24 is the separately approved replacement for
this display-only approach; P22 is not reopened or relabeled pending.

### Narrow contour

- Add the two metadata lines to EACH committed section already rendered in the researcher
  card, in this exact order: commit record ID, validation record ID, run outcome record ID.
  No new rows/columns in either Dashboard table and no change to which cards are available.
- Resolve validation by the displayed section's commit ID in the snapshot's existing
  attempt records. Resolve the run outcome through the existing outcomes_by_session lookup
  with BOTH that researcher's NameKey and that commit's Codex session ID. Do not use the
  researcher's latest unrelated run/commit, fabricate IDs, or consult the run journal/DB.
- Missing optional validation/outcome records display an em dash; do not infer that an
  unqueried record does not exist in Backend. No committed section means no added ID block.
- Build the extra fields ONLY in the transient deep-copied InnerDict data returned by the
  existing selected_card_outer_dict. Insert them into dictionary order immediately after
  KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL, then call the unchanged shared build_cards renderer.
  Never mutate the stored query snapshot, source researcher, committed innerdicts or DB.
- Keep a single Markdown source: displayed card, Download Markdown/TXT, Download DOCX and
  publish completed naturally include the same metadata through their existing contour.
  No independent export metadata path, Markdown string-replacement hack or new exporter.

Limit production edits to src/control_centre/dashboard/ui.py and its existing protected
helpers/locale.py, plus necessary existing test_ui helper/callpoint updates. No shared
cards.py, Backend/API/Store, schema, query protocol, task, storage-slot or new-model changes.
Uses P20/P21's typed records; no duplicated model work.

### Historical implemented shape (superseded by P24)

Display-only labels in Control Centre Locale, matching the existing commit label style;
these are NOT new database-column constants:

```python
CARD_VALIDATION_RECORD_ID_LABEL: Final = "ktp.ai_augment_validation_record_id"
CARD_RUN_OUTCOME_RECORD_ID_LABEL: Final = "ktp.ai_augment_run_outcome_record_id"
CARD_RECORD_ID_UNAVAILABLE: Final = "—"
```

Pass the same captured in-memory snapshot through the existing render callback, without
adding a service or granting a query capability:

```python
# _ControlCentreController.__init__ callback annotation
render_card: Callable[[_Researcher, DashboardQuerySnapshot], str]

# researcher_card: capture once and use this snapshot for researcher and metadata.
snapshot = self._snapshot
researcher = snapshot.researchers_by_namekey.get(namekey.to_json_key())
# Preserve the existing unknown-namekey check.
markdown = await asyncio.to_thread(self._render_card, researcher, snapshot)

# Existing pure _BackendDatabaseClient.card callback
def card(self, researcher: _Researcher, snapshot: DashboardQuerySnapshot) -> str:
    selected = selected_card_outer_dict(researcher)
    # Add ordered display-only metadata to selected's copied rows, as below.
    # Existing build_cards call uses selected; remaining arguments/result checks stay.
```

The metadata lookup/insertion stays local to that existing card method. For each selected
copied innerdict with a commit-ID field:

```python
attempts_by_commit = {
    record.attempt.commit_record.record_id: record
    for record in snapshot.attempts_by_namekey.get(researcher.namekey.to_json_key(), ())
}

# Inside the local iteration over selected's copied rows, after finding a commit-ID field:
attempt_record = attempts_by_commit[UUID(str(inner.data[KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL]))]
validation_record = attempt_record.validation_record
session_id = attempt_record.attempt.commit_record.commit_request_body.codex_session_record.session_id
run_outcome_record = (
    None if session_id is None
    else snapshot.outcomes_by_session.get((researcher.namekey.to_json_key(), session_id))
)
metadata = {
    Locale.CARD_VALIDATION_RECORD_ID_LABEL: (
        Locale.CARD_RECORD_ID_UNAVAILABLE
        if validation_record is None else str(validation_record.record_id)
    ),
    Locale.CARD_RUN_OUTCOME_RECORD_ID_LABEL: (
        Locale.CARD_RECORD_ID_UNAVAILABLE
        if run_outcome_record is None else str(run_outcome_record.record_id)
    ),
}
data: dict[str, Any] = {}
for column, value in inner.data.items():
    data[column] = value
    if column == KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL:
        data.update(metadata)
inner.data = data
```

No fallback for inconsistent commit linkage: the existing snapshot already requires each
committed innerdict to have its matching accepted attempt. Preserve that invariant.
The missing-record placeholder is only for genuinely optional validation/outcome fields.

Verification: focused existing card/UI tests for exact adjacent ordering, correct IDs with
multiple commits/sessions, absent optional records, unchanged cards without commits, and
unchanged snapshot/source dictionaries. Reuse existing export tests for the shared Markdown
contour; no live Backend/Codex/browser run required just to verify these metadata lines.
Implemented exactly in ui.py/Locale and existing test_ui helpers/tests. The real renderer
regression first failed at the missing metadata assertion before implementation. Afterward:
11 focused card/offline/download/publish cases passed,191 deselected (3.67s), plus the
new no-commit exact shared-renderer comparison:1 passed,202 deselected (8.98s).
Coverage includes three commits over two sessions (two commits sharing one outcome), all
four present/absent validation/outcome combinations, a different researcher's same-session
outcome and a newer unrelated session. Metadata order and UUIDs are exact. Original query,
rehydrated snapshot and NiceGUI storage remain unchanged; no query is sent while rendering.
Existing TXT/DOCX and completed-publishing tests confirm the shared Markdown callback path.
No shared renderer/exporter edits or actual browser/Codex execution. Final Ruff PASS;
strict mypy PASS54files; all callback/import callpoints reviewed. Only the approved card
callback gains the captured snapshot argument; no new query capability or service.

## Completed immediate correction — prefix/suffix verification logging

Operator authorized ONLY the surgical log wording/placement correction in Store's existing
_verify_log_projection. Emit one prefix size/line-count summary and a prefix-match message
after successful verification (including the empty anchor). Emit per-line messages ONLY
for suffix lines whose individual hashes are compared. Make the final ordinal/byte coverage
message explicit. No hash reuse/optimization, verification skips, replay/application changes,
new schema/flags, or edits to the separate operator-review findings. Implemented only log
calls/wording and logging-only guards in ai_augment_backend_store.py. For a fully anchored
three-line log the progress messages now read:

```text
Verifying prefix: 3 lines, 58054 bytes
Prefix hash matches stored anchor
DB/log ordinal and byte coverage verified: 3 lines, 58054 bytes
```

The existing stored/config hash summary remains, now explicitly called "Verifying replay
log". Only suffix lines emit "Verifying suffix line N". Ruff PASS;12 existing Store
integrity/anchor/replay-refusal cases passed,14 deselected (33.53s), including corrupt
prefix/suffix rejection. No test assertions, hash calculations or DB behavior changed.
The preceding manual /push500 was explained by the operator forgetting to
supply the session ID; that investigation remains paused, not a newly authorized redesign.

## Latest production review — 2026-09-17 14:55–14:59 (-04:00)

Inputs: logs/from_operator/pre-commit.log and pre-commit-extra.log (updated by operator).
Reviewed against current HEAD f56fb8a. This is a review, not approval to alter ordinary
Pixi tasks, browser selection, root permissions, queue semantics or timeouts.

### Actual outcomes

- Normal guest phase14:55:29–14:57:54: Ruff PASS; mypy68/53files PASS. Main tests174 passed,
  5 skipped,6 xfailed,1 xpassed in4.91s. Both real configured DuckDB binary checks now PASS.
  Step4 synthetic4passed/1skip; explicit slow case SKIPPED because five real parquet inputs
  are unavailable. Mode3 all6passed (including the previously regressed notice test).
  Mode0 all4passed,11 existing Plotly/Kaleido deprecation warnings.
- AI normal selection:9failed,517passed,1skipped,3deselected,1warning in110.02s.
  ONE failure is test_main_ipc_only_runs_only_the_dashboard_query_server: server.py's new
  INFO call accesses runtime.pipeline_config.backend_store.detour_db_path, absent on that
  test's minimal BackendStore double. Real Store has it and real IPC startup succeeded in
  the same run. This is an agent-introduced log/test integration regression, not proof the
  production Store lacks the attribute. Reproduced locally with the unchanged exact node:
  1failed in2.92s. Earlier22-test verification missed this node after correcting the similar
  writable-lifecycle logging issue. Narrow proposed correction: retain the IPC opening log
  without this unnecessary path lookup; preserve the existing lifecycle test/assertions.
- The other EIGHT failures are all test_ui_e2e browser launches, before browser assertions:
  installed Google Chrome not found at /opt/google/chrome/chrome. Normal task does not pass
  --playwright-chromium; elevate does. Setting PLAYWRIGHT_BROWSERS_PATH does not select a
  channel. The passing elevate is not verification of normal task browser provisioning.
  Proposed: explicitly select/provision the agreed browser in that guest task, not a silent
  fallback/skip. Non-elevate task edit requires approval and was NOT made.
  The normal task's subsequent real_api institution round-trip was not reached (&&).
- Extra guest14:57:54–14:57:58: main OpenAlex3passed/1expectedxfail (3.25s); privileged
  appendwatch3FAILED/70deselected (0.26s), still before watcher monitoring assertions.
  New diagnostics establish /home/anonymous.linux is0750 uid501/gid1000; nobody receives
  its own uid/gid and empty supplementary groups. This blocks traversal to the configured
  cached Python; its leaf/resolved executable and later directories have executable modes.
  The script's /Volumes path components are readable/traversable. Correctly selected AI
  environment now has dependencies; this is not the earlier missing-Pydantic/FastAPI error.
  Needed: an actually accessible runtime path or separately approved precise access change,
  with real drop-before-exec retained. No chmod/ACL/cache move/preload or root execution made.
  Four safe actual-Pixi unset/stale-parent activation regressions passed on this guest too;
  the original pixi-shell report is not reproduced, and variables are not this failure.
- Host operator14:57:58–14:59:39: preflight, private initialization, initial real Query IPC,
 307-person wholesale storage replacement, clean IPC stop, Queue and Start all succeeded.
  Then NO full Backend start, Codex start or HTTP record appeared. Harness printed0records
  at10s intervals through60s; operator Ctrl+C. Active case INTERRUPTED, not passed;
  2 intentional skips,88.42s, exit2. Dashboard/descendant shutdown was clean.
  Guard now covers BOTH production data trees AND .nicegui: all unchanged. Private storage
  path is visible in the log. This verifies this run's isolation; old contamination was
  neither inspected nor cleaned.

### Hang: established boundary versus unproven cause

This is NOT the former post-Codex completion-guard hang and is not a long model inference.
Queue event/processing-start logs are present; full Backend start log is absent. In code,
_worker dequeues, _process_queued_run removes the persisted queue entry, then waits in
_wait_until_codex_idle BEFORE _backend.start. That gate repeatedly calls is_busy, whose
real SSH command is `pgrep -u "$(id -u)" -x codex` and returns literal busy when any same-user
Codex process exists. The remote command's communicate has no total timeout; successful
busy checks can also wait indefinitely by design. Neither busy-check entry/result nor
dequeue/wait progress currently emits a log. Actual external Codex occupancy/blocked SSH
is NOT captured in these logs, so do not assert either as the proven cause or kill/adopt
an external process. Worker scheduling/task failure is not directly observed either.

Preflight uses limactl shell for reachability/authentication, whereas the runtime gate uses
the configured ProxyJump SSH path. Preflight success therefore does not prove that exact
runtime check completed. The harness closes the browser, then only watches replay records
and top-level Dashboard process exit; "workflow is still running" is misleading when no
full Backend has started, and its1800s deadline hides pre-start stalls.

Proposed surgical follow-up: log existing dequeue/busy-check/wait/Backend-handoff boundaries,
including outcomes/errors; diagnose the actual runtime SSH/occupancy through the same path.
Only then propose any bounded-check/failure policy needed. Do not silently bypass busy,
auto-query, start a second Codex, change cancellation/queue semantics or extend timeouts.
Secure upstream tests for waiting-busy then idle, failed/blocked checks and browser-close
independence; the existing queue-gate test substitutes _process_queued_run and so does not
cover the real pre-start gate. The successful F4 synthetic regression deliberately has no
queued run and consequently could not catch this. No new helper/test changes made yet.

### Other evidence / lessons / next verification

- Audit-read test passes but emits Python3.14's multithreaded-fork deprecation warning;
  it is a separate risk, not evidence that it caused the operator hang. Mode0's11 warnings
  are deprecations, not current hard failures. No new cleanup traceback after this Ctrl+C.
- Normal logs include expected error/warning logs from PASSING negative-path tests; do not
  count these as extra failures. Initial absent IPC-socket polling precedes successful200.
- Approval-rejected pre-commit wrapper structure/grep remains unchanged. Read per-stage
  failures and the active case's interrupted status, not the green "2 skipped" footer.
- Missed homework: run all existing tests at the changed entrypoint, and verify the actual
  normal task's browser channel/prerequisites, not only a differently configured elevate.
  Full UI logging review also missed the silent pre-start gate. These are specific gaps in
  prior completion claims. Start with the failing IPC test, browser-task prerequisite check,
  original3root cases after an approved access correction, and a cheap pre-start-gate test;
  no reason to spend another live-Codex run before these are resolved.

WORK status: prior approved code is present but verified completion/production acceptance
remain OPEN. Proposed corrective work here is review output, not newly approved scope.

## Approved follow-up implementation — code present; latest regression noted above

Operator authorized strictly the immediately preceding proposal/snippets:

1. F3: preserve RunningWatcher's original Popen/preexec_fn and all three permission-test
   bodies. On PermissionError only, add interpreter/resolved path/script/privilege-drop
   details and owner/group/mode for interpreter/script path components (including symlink
   targets). A small test-only watcher_runtime_path_details helper may report these.
   Diagnostic failures must not replace the original exception. No preload, alternate
   runtime, permission changes, skip or timeout change. This diagnoses EACCES; it does NOT
   fix the unknown denied path/mount. Any actual runtime correction needs evidence/approval.

   ```python
   try:
       self.process = subprocess.Popen(
           command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
           stderr=subprocess.PIPE, text=True, preexec_fn=preexec_fn,
       )
   except PermissionError as exc:
       exc.add_note(
           f"Watcher interpreter: {WATCHER_PYTHON!r}; "
           f"resolved: {Path(WATCHER_PYTHON).resolve()}; script: {SCRIPT}; "
           f"privilege drop requested: {preexec_fn is not None}"
       )
       exc.add_note(watcher_runtime_path_details())
       raise
   ```

2. F4: one focused test_ui_e2e regression, with named subprocess support in the EXISTING
   shared plugin. Reuse synthetic source/config/Store setup; take initial real Store query,
   append synthetic HTTP records through append_authoritative_record, then seed PRIVATE
   NiceGUI storage with the earlier snapshot and completed run journal. Launch real
   Dashboard with stopped queue; use real owned IPC-only startup/query/clean stop/storage
   replacement. Isolate configuration inputs only; no substitute controller/query/helper,
   fake success notification, pre-populated saved result, live Codex/SSH workflow, direct
   derived-table SQL, new production hooks or timeout increase. Assert actual uppercase
   innerText vs semantic Rerun and invoke existing wait_for_completed_grid_row, which must
   call unchanged query_snapshot_in_browser. Verify expected commit, saved/OK fields,
   exactly one request/replacement log and removed owned IPC socket. Snippet core:

   ```python
   assert execute.inner_text().strip() == "RERUN"
   assert (execute.text_content() or "").strip() == "Rerun"
   expect(history).not_to_contain_text(Locale.RUN_OUTCOME_SNAPSHOT_SAVED)
   output_start = len(dashboard.output)
   _, commit_id = wait_for_completed_grid_row(
       page, dashboard, runtime, queued_at_monotonic=time.monotonic(),
   )
   assert commit_id == str(expected_commit_id)
   expect(history).to_contain_text(Locale.RUN_OUTCOME_SNAPSHOT_SAVED)
   expect(history).to_contain_text(Locale.SESSION_STATUS_OK)
   output = "".join(dashboard.output[output_start:])
   assert output.count("Requesting wholesale Backend query snapshot") == 1
   assert output.count("Dashboard snapshot replaced:") == 1
   assert not runtime.dashboard_socket_path.exists()
   ```

   Use existing ACTION_LABEL_BY_VALUE/RERUN mapping (proposal explicitly allowed this;
   no new ACTION_RERUN locale constant). Parent fixture/assertions remain in test_ui_e2e;
   child bodies are named helpers in pytest_plugin, following P19.

3. F7: add sys.executable and ONLY PIXI_PROJECT_ROOT/CONDA_PREFIX/APPENDWATCH_PYTHON/
   APPENDWATCH_SCRIPT prints with flush=True to existing watcher_import_process before its
   unchanged check=True real watcher --help execution. Keep actual unset/stale-parent Pixi
   regression and original15s bound. No speculative ordinary task rewrite. Operator-host
   activation issue remains unresolved until host evidence identifies it.

4. Verify applicable local Ruff/mypy/retained regressions first, then prepare bounded
   Assistant-owned elevate selection for real browser/query, activation checks and original
   privileged tests where root is available. Preserve its status aggregation/FAILED grep.
   Do not claim prepared/delegated tests passed before returned logs. No production storage,
   DuckDB prerequisite assertions, pre-commit wrapper or Backend/Store contract changes.

5. F8 — added by operator during implementation: investigate missing Backend terminal
   output and surgically emit missing logs. Operator clarified DIRECT terminal startup,
   not Dashboard forwarding; then further clarified MISSING RUNTIME /pull and /push detail,
   not merely startup. Review the existing HTTP middleware, pull/push lifecycle decisions,
   commit/validation handoff and success/failure logs, plus CLI/IPC emission. Add detailed
   operation/result/error logs at existing boundaries only. No business/lifecycle/permission changes, new
   logging framework, production payload dumps, task rewrite or broad refactor. Existing
   stdout/stderr forwarding, clean-close token and failure propagation must be preserved.
   Fresh server import + existing basicConfig emits INFO correctly before/after Uvicorn
   Config construction; no global suppression reproduced. Recent api.py revisions retain
   evidence/result/error logging, but lack routine request/pull/push decision/progress logs.
   Do not claim this proves why older detailed output stopped on the operator host.
   Dashboard forwarding already emits every child line and stays unchanged.
   Diagnose the actual suppression/gap before claiming a cause. Local logging regressions
   and the approved real browser/IPC case should cover the changed emission boundaries.

The pinned diagnostics, real-browser fixture/regression, and F8 log additions are now
implemented. F3/F7 environmental blockers are not claimed fixed by diagnostic additions.
The operator authorized this contour, not another permission/provisioning mechanism.

Earlier verification failures (not current pending implementation): operator ran elevate while the F4
fixture was being implemented. logs/from_operator/elevate.log (5008 bytes,18:24:56–18:25:10UTC)
shows a NEW agent-introduced collection failure: test_ui_e2e imports test_ui.startup_files,
but test_ui imported test_ui_e2e at module load. Pytest reported1 collection error in5.09s,
exit1; none of the four activation cases or browser body executed. The local setup-only
check independently caught the same cycle. Corrected by moving test_ui's sole browser
module import into its consuming test (no test removal/skip). Local mypy also identified
new helper import/constant callpoint errors; those were corrected.
After correction, collection succeeds; the initial real fixture setup child exceeded its
unchanged30s bound (64.15s total pytest, mypy running concurrently). Cause not established;
fixture phase diagnostics added, with no timeout increase. The next local setup-only check
exposed a synthetic-host fixture mismatch; using the existing model constants corrected it.
The subsequent setup-only check passed (17.68s); it is not browser/IPC serving coverage.

Earlier delegated elevate (18:31:59–18:34:32UTC,2026-09-17):1 FAILED,5 PASSED in139.38s;
exit1. Existing browser contract passed; four real-Pixi unset/stale-parent launcher cases
passed and printed correct interpreter/project/script variables. Root dispatch in those
cases remains a sentinel, NOT real privileged monitoring or proof on the operator's Lima.
The new real-query fixture setup succeeded (23.54s). Dashboard started/restored private
storage and received the exact JSON NameKey search. Browser still saw24 rendered grid rows
instead of1 at the unchanged5s assertion deadline; test failed BEFORE selection/completion
helper/Query IPC. Dashboard and its child resource tracker stopped cleanly. No Ctrl+C,
Backend startup, query or storage replacement occurred in this failed case. Browser call
52.62s, contract47.66s; stage-specific timing was not captured, so no precise cause for
those durations is established. This is not evidence of a Backend/IPC failure, nor proof
that production filtering is correct. The fixture now additionally constructs real services,
loads its private snapshot/journal, and checks real controller snapshots:307 unfiltered,
exactly1 for the same JSON NameKey, completed/Rerun with no commit yet. No services start
and no controller/query helper is substituted. The existing named child retains its30s
limit. Local setup-only verification passed in17.26s; this proves fixture/filter behavior,
NOT browser rendering or query IPC. Browser warnings/errors and assertion-failure input,
rendered rows/page errors/server output now appear in diagnostics without replacing the
original exception. Failure cause remains unestablished; no timeout/assertion relaxation
or production filtering behavior change. Targeted elevate selected only this case.

Next run (18:44:13–18:45:53UTC) FAILED:1 failure in83.50s. Filtering and completed/Rerun
checks passed; the REAL completion helper clicked Query IPC. Owned IPC-only Backend missed
its unchanged30s readiness deadline after config/source loading and entry into Store open.
Dashboard stopped it with SIGTERM (return_code=-15, no clean-close acknowledgement), and
the query helper failed promptly rather than waiting1800s. Deleted-slot notification
exceptions followed browser teardown. No query response/storage replacement occurred;
no Ctrl+C. Setup17.17s, browser call57.92s. No code/timeout change was made for this failure.

LATEST rerun (18:47:59–18:48:56UTC) PASSED:1 passed in47.19s, exit0; setup11.89s,
browser call32.26s. Actual rendered RERUN/semantic Rerun checks, real completion helper,
owned IPC-only Backend, OPTIONS200/GET-query200,5-line replay/DB verification, wholesale
307-person snapshot with1 accepted commit/1 outcome, saved/OK display, single replacement,
clean-close acknowledgement/exit0/socket removal and source/replay/DB byte-preservation
assertions all passed. Dashboard also stopped cleanly. No warning/error/traceback in this
successful log; repeated absent-socket availability lines precede successful readiness and
are expected polling, not another failure. Existing browser contract and four activation
cases already passed in the earlier batch; they were not repeated.

Operator notes this is a weak machine and accepts timing flakiness. Read-only host checks
after the failed run showed ~961MiB RAM, ~787MiB swap in use and recent memory/CPU pressure;
these support resource contention as plausible, not proof of its exact causal contribution.
No timeout increases, retries, assertion weakening, skipped prerequisites or production
filter/startup changes. No further diagnostic startup helper/test or performance refactor
was added before the operator stopped investigation and reran. No further repeat requested.

Current local checks:
- F8 API/middleware/pull decisions, IPC query and Store cleanup selection:22 passed,
  162 deselected (9.39s). Initial20pass/2fail exposed an unnecessary new log attribute
  access in minimal cleanup fixtures; removed the attribute read, tests unchanged.
- F3 failure-only EACCES diagnostics plus F7 actual task activation and standalone import:
  7 passed,43 deselected (22.29s); original15s bound retained. Original nobody/root cases
  unchanged and still require actual privileged execution.
- Operator preflight full non-operator selection:23 passed (71.89s).
- Final Ruff PASS; strict mypy PASS54files (detour plus shared HttpRequestLogRecord);
  git diff HEAD --check PASS. TOML parsing and elevate Bash syntax PASS; task-map comparison
  confirms ONLY elevate differs from HEAD, ordinary tasks unchanged.
- After narrowing elevate, its real-shell failure/FAILED-reporting cases and existing
  browser-fixture callback consumer:4 passed,217 deselected (16.31s). This also exercises
  the corrected local browser-module import; no browser serving claim.
No production payload dumps, response/schema/state changes, logging reconfiguration or
ordinary task changes. No local checks remain running. The requested targeted browser
verification is now complete; root monitoring and final production acceptance remain.

Verification mistake disclosed to operator: a direct Python importlib.find_spec lookup of
nicegui.persistence.file_persistent_dict imported parent NiceGUI outside the early test
isolation hook while inspecting installed source. Default storage may have been accessed;
no assertion of preservation can be made for that command. No default/production storage
inspection or cleanup followed. Subsequent NiceGUI execution must use the isolated pytest
hook/private child environment, and installed-source reads must not import the package.

## Completed scope index

| ID | Implemented scope | Main locations |
|---|---|---|
| P1 | Exact JSONL hashes, typed table-comment anchor, independent prefix/suffix verification, safe transactional promotion | Store + replay_log.py |
| P2 | Full --new empty baseline or separately confirmed nonempty replay; strict resume never heals | server.py + Store |
| P3 | Real append-open/close preflight without writing, writable mode only | replay_log.py + Store |
| P4 | Historical verdict substitution removed; failed full-child cycle blocks unattended retry/reset | api.py + Dashboard context |
| P5 | Four Backend/IPC lifecycle corrections below | server.py, api.py, ui.py, context, launcher help |
| P6 | Non-locking IPC signal flag; unchanged clean-close token in protected Backend vars | ipc.py + vars.py + import points |
| P7 | Empty parameterless QueryRequestProperty; concrete outbound_http retained | protected/src/architecture.py |
| P8 | Single Start/Stop queue-processing switch, stopped at Dashboard startup | Dashboard controller/page |
| P9 | No Backend card/ZIP publishing; explicit Dashboard publish completed shares DOCX renderer | Store, api.py, ui.py |
| P10 | Dashboard background-startup failure requests normal shutdown and unsuccessful process exit | ui.py application lifecycle |
| P11 | All25 in-scope remaining detour dataclasses converted, with standalone dependency/constructor integration | Inventory below |
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

P24 is implemented and locally verified. Its exact scope and verification boundary
are pinned above; unrelated production-review corrections remain unapproved.

## Previous production incident — baseline for F1-F7 corrections

CRITICAL operator finding, confirmed by source tracing and isolated reproduction: tests
write into PRODUCTION NiceGUI storage. A subsequent normal Dashboard launch displays test
snapshot/run data although the isolated test replay log no longer exists. This violates
test isolation; Dashboard's intentional snapshot autonomy does not excuse contamination.
F1 prevention is now approved; do not read, delete, reset or
repair production NiceGUI storage or production data. Surgical approved scope is pinned below;
F1 prevention is now implemented; local isolation checks pass. Real browser/root verification
remains below. Existing contaminated production storage has not been touched.

The incident descriptions below refer to the failed-run baseline, not a claim that the now-
corrected code remains unchanged. Current F1-F7 implementation/check status follows them.

Operator reran pixi run pre-commit-operator and supplied logs/from_operator/pre-commit.log
(88385 bytes) and pre-commit-extra.log (1277562 bytes). Reviewed stages, timestamps,
heartbeats, exceptions and current callpoints; no production/test/task changes or live
execution were made during this review. This supersedes the previous "next: acceptance"
recommendation. Do not request another expensive complete run before addressing these
findings with approved scope and upstream regressions.

### Critical NiceGUI isolation failure — incident baseline and implemented correction

NiceGUI's Storage.path is fixed DURING IMPORT from NICEGUI_STORAGE_PATH, defaulting to
cwd/.nicegui. Its global app constructs FilePersistentDict for storage-general.json, and
nicegui.py calls general.initialize_sync DURING IMPORT. That reads existing contents and
updates the persistent mapping; its on-change backup can rewrite the file. A late ordinary
pytest fixture, a different --config, browser session, port, or storage_secret does NOT isolate
this general storage. If NICEGUI_REDIS_URL is inherited, Redis takes precedence over the
file path; tests must unset it before import rather than touching the operator's Redis.

| Existing test contour | Finding |
|---|---|
| Operator running_dashboard | Copies environment, cwd=repository_root, no storage override. Temporary config/DB/replay/CAS paths do not affect NiceGUI. Actual test query overwrites the production snapshot and queue/run events use the same production file. |
| test_ui_e2e browser launches, both context-manager and standalone contract path | Also copy environment and run from repository root with no override. Stub controller avoids domain writes, but real NiceGUI import still accesses production persistence. |
| test_ui in-process tests | isolated_general_storage replaces app.storage._general with a dict only at fixture setup, AFTER test module import has loaded NiceGUI. It protects test-body writes, not import-time access. |
| Shared socketless_dashboard_lifecycle and operator-fixture bootstrap children | Fresh Dashboard/NiceGUI imports inherit default storage settings. Substituting serving/services or stopping before serving does not isolate framework persistence. |
| Collection/other detour imports of Dashboard | Can initialize NiceGUI before any per-test fixture. Shared pytest plugin currently provides no early storage isolation. |
| Blanket isolated_lima_configuration autouse fixture | Imports Dashboard for every non-operator test, including standalone appendwatch tests. This unnecessarily exposes unrelated tests to Dashboard dependencies and, when imports succeed, NiceGUI persistence. Narrow fixture applicability is proposed below. |

AiAugmentDashboardStorage has three persisted slots: detour_ai_augment_backend_database,
detour_ai_augment_run_events, detour_ai_augment_queue. Normal Dashboard startup reloads all
three; it intentionally does not consult the replay log to decide whether they should exist.
The leak works both ways: an operator test can also inherit real snapshot/journal/queue and
run normal startup handling of stored unfinished runs. No claim is made that such remote
cleanup actually occurred in this log; actual production storage was not inspected.

The production_data_unchanged fixture hashes only repository data/ and detour data/. The
"production data is unchanged" message therefore did NOT establish NiceGUI preservation.
That limited check passed while unguarded .nicegui could be modified.

Safe diagnostic performed with real installed NiceGUI in fresh subprocesses, each cwd
inside one temporary directory containing a SYNTHETIC .nicegui sentinel (no repository
storage, production data, server, browser, sockets, network or privilege escalation):
- Default launch read the synthetic operator sentinel and wrote test state into that file.
- Changing NICEGUI_STORAGE_PATH AFTER import did not redirect Storage.path or existing dict.
- Setting it BEFORE import wrote only the isolated directory; same-directory restart
  retained test state; a second test directory began empty. Synthetic default sentinel
  stayed byte-for-byte identical across all isolated launches. All five subprocesses exited0.

Approved test-only scope (F1): existing protected/tests/pytest_plugin.py,
protected/tests/operator/test_operator_e2e.py, tests/control_centre/test_ui_e2e.py,
relevant existing test_ui.py/operator-preflight regressions, and WORK. No production
storage model/UI/config/schema/CLI changes and NO pyproject task changes.

1. In the EXISTING shared plugin's pytest_configure, BEFORE test-module collection/import,
   allocate a private session temporary directory and force NiceGUI to local storage there.
   Capture the original configured/default file-storage path for preservation checks.
   Fail closed if NiceGUI was already imported (do not pretend late monkeypatching undoes
   earlier access). Restore environment/remove only this owned temp directory at pytest
   config cleanup, after test children stop. Preserve existing in-memory unit-test fixture.
   Representative hook addition, before existing marker/operator configuration:

   ```python
   if "nicegui" in sys.modules:
       raise pytest.UsageError("NiceGUI imported before test storage isolation")
   directory = tempfile.TemporaryDirectory(prefix="ai-augment-pytest-nicegui-")
   environment = pytest.MonkeyPatch()
   environment.setenv("NICEGUI_STORAGE_PATH", directory.name)
   environment.delenv("NICEGUI_REDIS_URL", raising=False)
   config.add_cleanup(environment.undo)
   config.add_cleanup(directory.cleanup)
   ```

   Capture the original resolved path BEFORE the setenv in a typed pytest.Config stash entry;
   the existing operator preservation fixture receives it explicitly. Do not import NiceGUI
   to discover that path. This setup is not a normal autouse fixture: that would be too late.

2. One shared test-only environment helper and explicit per-test path fixture:

   ```python
   def nicegui_test_environment(storage_path: Path) -> dict[str, str]:
       environment = os.environ.copy()
       environment["NICEGUI_STORAGE_PATH"] = str(storage_path.resolve())
       environment.pop("NICEGUI_REDIS_URL", None)
       return environment

   @pytest.fixture
   def nicegui_storage_path(tmp_path: Path) -> Path:
       return tmp_path / "nicegui"
   ```

   Operator running_dashboard replaces only its os.environ.copy with:

   ```python
   environment = nicegui_test_environment(runtime.config_path.parent / "nicegui")
   # Existing PYTEST_CURRENT_TEST removal, socket/unbuffered settings and launch stay.
   ```

   Both browser launch paths explicitly use the nicegui_storage_path fixture through that
   helper; socketless_dashboard_lifecycle and the named operator-fixture bootstrap pass their
   fixture path/environment to the existing PythonProcess runner. Same operator runtime may
   restart using the same isolated storage;
   separate tests get different roots. Do not alter repository cwd/import resolution to
   solve a storage path issue, reset HOME, clear general storage, or copy/restore prod data.

3. Extend existing operator file-tree preservation coverage to the originally configured
   file-based NiceGUI directory (including absent-before/created-after detection), and make
   its log describe exactly the protected paths. Unset Redis in tests; never connect to a
   production Redis service for a preservation check. Use existing hashing, not a backup/
   restore mechanism that could conceal writes. Record isolated storage path in existing
   operator startup diagnostics. No production-storage deletion/repair is included.
4. Meaningful upstream coverage BEFORE another operator run: real NiceGUI import and
   persistence against synthetic default-storage sentinel; early pytest collection isolation;
   actual caller environment wiring, file writes under per-test path, same-test restart,
   separate-test empty state, overridden inherited NICEGUI_STORAGE_PATH/Redis settings, and
   cleanup after child exit/failure. Reuse P19 named helpers/runner; no embedded Python strings,
   no mocked persistence and no live Codex. Existing real browser checks remain the serving
   boundary; they must consume the same isolated environment rather than another substitute.

Existing contaminated operator storage is not automatically distinguishable from legitimate
data by presence/absence of a replay file. It has NOT been examined or cleared. Any cleanup
requires separate explicit instructions; no blanket deletion or silent fallback is proposed.

### Mode-3 follow-up — completed, NOT pending scope

Operator reported a real failure of test_detour_contract_and_mode3_stats_readonly and
required causal investigation before any change to unrelated-detour assertions. Baseline
for that investigation is aicode/staging (ef5ddef898b4dd5fcd1846acd24f6904f8a37c64), NOT
this task's dc951fe implementation checkpoint. Do not infer a historical test failure
from old-source execution with current dependencies; the operator reports previous passes.

Cause was isolated with real pytest/synthetic DBs and actual temporary PTYs, COLUMNS/LINES
unset, no renderer mocks. Before the correction:

| Source / invocation (same current installed dependencies) | 80-column PTY | 92-column PTY |
|---|---|---|
| Current code, default FD capture (-q) | PASS | PASS |
| Current code, actual task flags (-vv -srA) | PASS | FAIL at the phrase assertion |
| Isolated staging source, original flags (-vv -s) | PASS | FAIL at the same assertion |

Rich's default Console reads terminal geometry; with -s, capsys still leaves the underlying
terminal FDs available. At92 columns, the methodology phrase wraps between "full" and
"normalized string first"; the contiguous substring assertion fails. Default pytest FD
capture hid the geometry and produced the80-column fallback in the local checks. This was
a verification gap: use the real task invocation, not just a passing captured run.

The renderer, console construction, methodology notices and run_detour are identical to
staging; the Rich14.3.4 wheel lock record/hash is identical too. No introducing AI-augment
production-code change was identified. The complete old runtime was not recreated; these
results explain coexistence of passes/failures, not the exact historical terminal width.

Operator explicitly approved ONLY injecting a deterministic REAL80-column Rich console
into this particular test. Whitespace normalization, changed assertions, 80/92 test
parametrization, global COLUMNS, shared pytest-console configuration, dependency pins,
production-code changes and task-flag changes were NOT approved and were not applied.

Approved implementation in repository-root tests/test_detours/test_detour_mode3_pgf_stats.py:

```python
from rich.console import Console
from src.detours import detour_mode3_pgf_stats as mode3

# Existing test gains only the monkeypatch: pytest.MonkeyPatch parameter and this line:
monkeypatch.setattr(mode3, "console", Console(width=80))
# Every original assertion is unchanged, including:
assert "full normalized string first" in plain
```

Exactly four source-line additions, plus WORK. Pytest restores the module binding afterward;
normal production rendering remains terminal-responsive. Verification after the change:
- Entire synthetic Mode-3 module/default capture:6 passed in16.67s.
- Modified test with actual -vv -srA and real PTYs:80 columns1 passed in10.36s;
  92 columns1 passed in5.73s. These overlap the six above; counts are not additive.
- Ruff PASS; default-environment mypy PASS (1 source file); git diff HEAD --check PASS.
The operator committed this as ab8d761; agent Git use remained read-only. This closes the
narrow Mode-3 fix, not the unrelated acceptance failures below.

### Additional privileged invocation — separate setup failure, still unresolved

**New sudo run: default environment plus unnecessarily broad fixture dependencies.** The
pytest header explicitly identifies .../envs/default/bin/python, not detour-ai-augment.
The supplied CONDA_PREFIX expansion therefore selects an environment without FastAPI and
pydantic-extra-types; both belong to the AI-augment dependency group in pyproject.toml.
This is not sudo losing packages from an otherwise correctly selected interpreter. The
three selected cases ERROR at autouse fixture setup, before watcher launch/privilege drop.
The pydantic-extra-types collection skip is consistent with the same environment mismatch.
The existing explicitly selected task is:

```bash
pixi run -e detour-ai-augment test-detour-ai-augment-root
```

This identifies the intended invocation, NOT a request to rerun now: NiceGUI isolation and
the earlier post-drop interpreter EACCES remain unresolved. No task rewrite or installing
Dashboard packages into default is proposed.

The shared plugin's isolated_lima_configuration is autouse for all non-operator tests and
imports dashboard.ui at577; ui imports FastAPI at26. Standalone appendwatch tests need no
Lima/Dashboard setup. Merely replacing the UI import with ai_augment_context is insufficient
to remove the dependency: that context imports Backend api (FastAPI) and pasted models
(pydantic-extra-types). The now-implemented F2 correction makes this fixture
explicitly applicable to its actual consumers, preserving their isolation and the existing
mock-free startup-class override, while standalone watcher tests do not request it. Audit
consumers during implementation; do not special-case test filenames, skip real cases, or substitute
the fixture's whole production dependency graph. Keep this separate from early NiceGUI
storage isolation, which is still required for legitimate Dashboard consumers.

Even with the correct AI environment and fixture scoping, the earlier production failure
remains: exec of the cached AI interpreter after dropping to nobody failed with EACCES. These reports failed at
different boundaries; neither exercised permission-monitoring assertions. The proposed
load-before-drop bootstrap F3 was subsequently rejected and removed; no replacement
mechanism is approved yet. Do not chmod the operator's home/cache or run the watcher
as root to make permission tests pass.

Upstream lesson: selected tests include their entire fixture/import graph, not only their
test bodies. Prior green checks at one width/in a dependency-rich parent environment are
insufficient. Explaining a failing assertion is not identifying the regression's origin;
do not shift a newly introduced defect onto unrelated-detour tests without that analysis.

### Actual results

- Normal guest phase11:52:09–11:52:35 (-04:00): Ruff and both mypy leaves PASS (68/53files).
  Main pytest:172 passed,1 failed,6 skipped,6 xfailed,1 xpassed in5.14s. Config-path DuckDB
  fallback test fails on missing /Volumes/home/aicode/.duckdb/extensions/v1.5.1/linux_arm64/
  splink_udfs.duckdb_extension. No normal detour-suite execution appears after this failure.
- Extra guest phase11:52:35–11:52:40: real OpenAlex3 passed,1 expected xfail in3.09s.
  Root was available this time: all3 needs_sudo tests FAILED in0.81s, before watcher startup.
  After drop_privileges(nobody), exec of the Pixi interpreter under the operator's
  /home/anonymous.linux/.cache/rattler/... directory raises PermissionError13. This is no
  longer the missing-Pydantic error, but interpreter-path access remains unresolved. The
  exact nontraversable/denied component is not identifiable from this log alone. Monitoring
  assertions did not run; do not call this a watcher-behavior failure or a sudo absence.
- Host operator phase11:52:40–12:01:25: preflight/isolated Store initialization/first wholesale
  Query IPC/explicit queue Start all succeeded. Three submissions were durably accepted202;
  two returned retry200; the third reached pull410. Codex exited; Dashboard's one final pull
  returned410; completed IPC returned200 at11:59:03; journal showed completed. Backend
  emitted clean-close acknowledgement and stopped. Harness nonetheless kept waiting,
  operator pressed Ctrl+C twice, and pytest ended interrupted:2 intentionally skipped,
  active case NOT passed, elapsed500.97s, command status2. Card display/artifact assertions
  were never reached. Dashboard/child shutdown and the two guarded data-tree preservation
  checks passed; NiceGUI storage was not covered by those checks.

### Long wait and concrete code findings

The initial live run took about330s from queue11:53:18 to pull410 at11:58:48. First push was
about216s after queue; two retries added about114s. Logs show web research, payload building,
first-round evidence corrections and second-round retry-identity corrections, not an idle
Backend deadlock during that interval. Codex reported152456 tokens; this is an expensive
acceptance run. The final useless wait persisted for over2min AFTER completion; heartbeats
continued from352s through462s before Ctrl+C. Existing overall deadline is1800s, so it would
not have failed promptly on its own.

wait_for_completed_grid_row (protected/tests/operator/test_operator_e2e.py) gates its
post-completion Query IPC on completed status, execute.inner_text().strip() == "Rerun", and
View card enabled. Quasar's real .q-btn CSS applies text-transform:uppercase; UI has no
no-caps override. inner_text() is rendered innerText, unlike Playwright's default textContent
assertions elsewhere. Thus rendered "RERUN" fails the mixed-case comparison. This is a
strong code-backed diagnosis; the supplied log does NOT record the actual button DOM text
or enabledness, so do not claim that those values were captured or a browser reproduction
was performed. No second Query IPC appears in the log. A previously voiced snapshot/card
circular-wait hypothesis was corrected during review: View card is gated by active_run_id,
not query-snapshot availability (ui.py:sync_selected_action).

The completion heartbeat always says "waiting for Codex to exit" even after reporting
completed. It omits the particular guard still false (action text, View card enabledness,
post-query snapshot status), explaining why operator output offered no useful diagnosis.

Main tests/test_duckdb_extensions.py uses _FakeConn to force BOTH repository attempts to
fail, hardcodes linux_arm64, then reads the real config/default binary path without supplying
a temporary binary. This is a nonhermetic test setup defect, not evidence that normal
community loading is broken: other tests log successful community loads. The temporary config/binary proposal was withdrawn by the operator; the existing check
must continue to expose the configured binary absence. No replacement fix is approved.

### Other log inconsistencies/noise

- Eight IPC FileNotFoundError messages precede successful owned IPC startup/OPTIONS200.
  Socket absence is expected during startup polling; labeling every poll as an IPC error
  with no socket path/phase is misleading. Preserve meaningful explicit Probe diagnostics.
- /commit and /validate "no response" means deliberately null response fields on synthetic
  durable request records, not a network hang. Their log wording should make that distinction.
- Backend return_code=-15 follows explicit SIGTERM plus the clean-close token; code accepts
  that combination as successful shutdown. It is not evidence of a crash in this run.
- Most of the1.28MB extra log is evidence candidate diagnostics (~0.83MB of stripped text)
  and repeated payload diffs (~0.18MB). Repeated evidence analysis can come from live
  speculative validation and persisted readback; repetition alone does not prove duplicate
  durable commits. Phase/summary diagnostics could improve readability, but no suppression
  or logging redesign is authorized by this review.
- The "avoid503 errors" phrase is Codex commentary, not an observed HTTP503; actual response
  records here are200/202/410. Do not misclassify quoted model code/errors as server failures.
- Pending-task/TargetClosedError warnings follow the double Ctrl+C and browser teardown.
  They are cleanup symptoms, not the initiating hang. The two guarded data trees remained
  unchanged; this does not establish NiceGUI storage preservation.
- Existing xfail/xpass descriptions document previously reviewed name-matching exceptions;
  they are not new hard failures. Unchanged wrapper grep/status limitations remain; no new
  permission to change pre-commit tasks. Read the per-stage results rather than wrapper status.

### Current corrective scope F1-F7 — reconciled with operator rollbacks

P1-P19 and the Mode-3 console correction remain implemented. F1-F6 were originally approved,
then the operator withdrew F3's preload solution and F5's synthetic binary/config fixture,
and requested removal of the substituted-query browser test and timeout increase. These
latest instructions supersede their prior approval; do not resurrect the removed changes.
Backend/Store/replay, queue/final-pull/outcome and wholesale-query contracts are unchanged.

| ID | Scope | Current status |
|---|---|---|
| F1 | Early NiceGUI test storage isolation, per-child paths, production-storage preservation guard | Implemented; local real-persistence/wiring and isolated real browser/query checks passed; full production operator rerun pending; contaminated storage untouched |
| F2 | Explicit Lima fixture for Dashboard consumers only | Implemented; independent watcher import and existing UI checks passed |
| F3 | Diagnose privileged watcher launch failure | Diagnostics implemented; latest PROD identifies0750 /home/anonymous.linux traversal barrier; runtime/access correction and real monitoring pending |
| F4 | Completion text comparison, wait diagnostics and synthetic-record wording | Implemented; real completion/helper/owned-query/wholesale replacement browser regression PASSED; earlier timing failures retained in evidence |
| F5 | Configured DuckDB fallback binary absence | Latest PROD real binary/config fallback checks PASS; no replacement fixture or assertion weakening |
| F6 | IPC availability diagnostic wording/path | Implemented; focused checks passed |
| F7 | Investigate/fix operator task-variable availability | Not reproduced locally; safe activation regressions retained with original15s bound; operator-host issue unresolved |
| F8 | Restore detailed direct-terminal Backend operation logs | Logs present; IPC-only opening-log correction implemented and unchanged regression passes; full production serving acceptance remains open |

#### F1 — NiceGUI test storage (implemented; local checks passed)

Use the exact early-isolation/environment-helper shape pinned in the critical-storage
section above. No new pytest plugin or production setting. Configure an owned private
session NICEGUI_STORAGE_PATH before collection imports; unset NICEGUI_REDIS_URL. Fail
if NiceGUI already imported rather than pretending isolation was early enough. Save only
the original resolved file-storage PATH in typed Config stash for the operator guard.

Every real Dashboard/browser child gets a per-test private path through the ONE shared
nicegui_test_environment helper. Includes both browser Popen sites, running_dashboard,
socketless_dashboard_lifecycle, and the named operator-fixture bootstrap child which imports
operator workflow/Dashboard. Same-test restarts reuse their private path; different tests
must not inherit each other's state. Keep the existing per-test in-memory UI fixture.

Extend the existing operator production_data_unchanged file-tree guard to the ORIGINAL
file-based NiceGUI path, detecting absent-before/created-after too; log exact protected
paths and the test storage path. Local regression uses only a synthetic operator-storage
sentinel. Do not inspect/clean production NiceGUI here, copy it into tests, clear it, reset
HOME/cwd, or connect to production Redis. This prevents future contamination; existing
operator storage cleanup needs separate instructions.

Coverage: real framework import/persistence, early collection, child environment wiring,
same-test restart, separate-test emptiness, inherited env overrides, preservation sentinel
and owned-directory cleanup after child shutdown. P19 named helpers/runner, no inline
Python bodies or mocked persistence. No browser/operator run before this isolation is in place.

#### F2 — Narrow Lima fixture applicability (implemented; local checks passed)

Remove autouse=True from isolated_lima_configuration; request it explicitly for the existing
Dashboard test consumers, preserving their previous isolated configuration. The test_ui.py
module can select it with usefixtures; its TestBackendStartupConditions override still
resolves to the existing no-op. Other actual consumers, if any, must request it explicitly;
no filename/marker heuristics and no new skip/fallback. Standalone watcher/API/audit tests
must not import Dashboard merely to initialize an irrelevant fixture.

```python
@pytest.fixture  # no longer global autouse
def isolated_lima_configuration(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ...  # Existing body, except the import/constant change described below.

# Explicit selection at the Dashboard test consumer; preserve any existing marks:
pytestmark = pytest.mark.usefixtures("isolated_lima_configuration")
```

Within that fixture remove its UI import and use the already-imported context module's
LIMA_APPENDWATCH_REPORT_PARAM. Context itself still imports FastAPI/pasted models, so this
import simplification alone is NOT the fix; narrowing applicability is essential. Do not
install Dashboard dependencies into default to conceal the coupling. The existing root
Pixi task already selects the AI environment; the pasted manual default-env command was a
separate wrong-environment invocation, not permission to rewrite tasks.

Coverage: isolated appendwatch collection/setup imports no Dashboard/NiceGUI; Dashboard
consumers retain isolation; the real startup class remains free of the Lima substitution.
Use isolated child checks without executing privileged or socket operations here.

#### F3 — Privileged watcher startup: unresolved, rejected workaround removed

Original preexec_fn/drop_privileges launcher and all three original permission-test bodies
are restored exactly. No watcher_permission_process helper or private-interpreter preload
case remains. The cached interpreter EACCES reported on PROD remains an actual blocker;
F2 only removes the unrelated Dashboard dependency during fixture setup. Do not claim root
monitoring was verified or replace real non-root startup with preloaded dependencies.
A different corrective mechanism needs a narrow proposal and explicit approval first.
Failure-only path/interpreter diagnostics were subsequently approved and implemented as
pinned above. Path resolution/stat failures are guarded so they cannot replace EACCES.
The two added real nonexecutable-interpreter cases verify diagnostics, not nobody execution.

#### F4 — Operator completion wait and harness messages (implemented; real browser check passed)

In wait_for_completed_grid_row, keep the completed-status/action/View-card guard and the
single explicit post-completion wholesale Query IPC. Replace only presentation-dependent
button inner_text with semantic text_content:

```python
action_text = (execute.text_content() or "").strip()
# Existing guard uses action_text == ACTION_LABEL_BY_VALUE[...RERUN...].
```

Quasar uppercases rendered innerText; it does not uppercase textContent. The diagnosis is
source-backed; actual DOM values were not captured in the failed operator log. Secure it
with an upstream REAL browser regression invoking this existing helper against a real
NiceGUI button/stale-then-refreshed synthetic snapshot, without live Codex. Do not accept
arbitrary button text or alter production button styling to satisfy the harness.

Existing heartbeat/timeout logs must identify the actual phase and unmet conditions:
run status, semantic action text, View-card enabledness, whether the one query was sent,
commit ID presence, savedness and session status when applicable. Keep the10s heartbeat and
1800s overall deadline; no timeout increase or new watchdog. Ensure the existing
savedness-wait branch cannot bypass the common heartbeat via an early continue. Preserve
failure/cancellation handling and outcome/Backend shutdown ordering.

In wait_for_gone_pull ONLY, describe synthetic POST /commit and /validate records with null
response fields as "request-only record; response fields intentionally null", not "no
response". Leave genuinely absent provider responses distinguishable. This wording lives
in the operator harness, NOT the Backend/Store, so no production HTTP-record changes.

Coverage: real rendered-uppercase/semantic-Rerun behavior, one query only, success after
snapshot refresh, existing failure handling, and informative waiting/timeout diagnostics.
No automatic production query, card gating, Backend finalization or timeout changes.

#### F5 — DuckDB fallback prerequisite: latest PROD checks pass

Repository-root tests/test_duckdb_extensions.py was not changed by this review. The latest
PROD log shows both real configured-binary and config-path fallback tests passing with the
actual linux_arm64 extension. The existing config-path test must still expose absence if
that prerequisite disappears; the neighboring real-binary skip is not replacement coverage.
Do not reintroduce a temporary config or b"fixture" binary into the existing config-path
check. No replacement code/config/install change is currently approved for this finding.

#### F6 — Accurate IPC availability logs (implemented and verified)

Only _BackendDatabaseClient.available in ui.py: distinguish FileNotFoundError and include
the socket path; retain detailed error logging for every other failure. Every explicit
Probe action/outcome remains emitted. Same requests, timeouts, return values and retries:

```python
except FileNotFoundError as exc:
    emit_log(Locale.CONTROL_CENTRE_LOG_PREFIX,
             f"IPC unavailable; socket not present: {self._socket_path}; {exc!r}")
    return False
```

The existing general OSError/HTTPException branch retains error reporting, adding the path.
No quiet/log flags, new logging interface, per-poll suppression or readiness orchestration.
Do not label absence as startup-only: this method also serves explicit Probe and borrowing.

#### F7 — Task environment-variable availability (reported issue unresolved on operator host)

Operator reports test-detour-ai-augment-root required pixi shell first. Trace actual Pixi
activation, command expansion and shell boundaries with a sanitized parent environment and
safe command sentinels (no sudo/network/live workflow). Correct the proven defect in that
task and any other task with the same problem, without broad task restructuring, new flags,
changing task selections or dropping grep. Record precise finding and test actual task
commands under unset and stale parent CONDA_PREFIX/PIXI_PROJECT_ROOT. Elevate may be adjusted
for delegated verification as already authorized. No pixi shell prerequisite is acceptable.

Verification checkpoint (2026-09-17): evidence below has distinct retained/reverted boundaries.

| Check | Result / boundary |
|---|---|
| Real NiceGUI import/persistence and collection isolation | Initial4 passed; real file writes, restart/separation, inherited storage/Redis override and success/failure cleanup |
| Actual operator/browser launcher environment wiring | 3 passed; stopped at process-launch seam, separate real persistence coverage above |
| Original-storage preservation guard | 2 passed against synthetic absent/existing storage; actual fixture detects new/modified files |
| Independent watcher fixture/import graph + real hash checks | 3 passed; no Dashboard/NiceGUI/FastAPI imported |
| Completion-helper conditions | 4 passed: success, pending-savedness timeout, failed, cancelled; semantic action, one query, heartbeat diagnostics |
| Withdrawn F5 fixture | Its prior2 passes are NOT evidence for current code; operator restored the original prerequisite check |
| UI/lifecycle/bootstrap selection | 8 passed,190 deselected (51.51s); includes both IPC failures, existing client, four socketless lifecycles and real isolated operator Store bootstrap |
| Existing UI after explicit Lima fixture selection | 82 passed,116 deselected (31.81s); excludes startup matrix/socketless checks already covered separately |
| Existing nonprivileged watcher CLI | 3 passed,46 deselected (11.41s): default debounce, FIFO shutdown and append/shrink |
| Elevate status/FAILED reporting | 3 passed,20 deselected (18.47s); actual PTY logger/shell with controlled leaf outcomes |
| Full preflight selection excluding elevate | 19 passed,1 timed out,3 deselected (72.79s); see qualification below |

Qualification: collection-failure isolation child printed COLLECTION_STORAGE_CLEANED but
exceeded its30s process-exit limit while other local checks ran. No timeout/runtime change
was made. After those checks ended, both collection cases plus preservation guard cases
passed together:4 passed,19 deselected (19.55s). The first selection was NOT wholly green;
concurrency is not established as the cause. No changed assertions or ignored failures.

F3 has its original three root cases; they have not passed on the corrected operator setup.
The rejected browser regression substituting the query helper was removed. Its real-query
replacement passed in the latest elevate after the two qualified timing failures above.
This verifies the real completion/query contour, not a new live-Codex acceptance run.
F1's helper retains an optional copied base environment to preserve startup TMPDIR/namekey.

Current elevate selects ONLY test_completed_grid_row_uses_real_query_ipc with its added
fixture/filter checks and failure diagnostics; it has now passed. The other five cases
passed in the earlier batch and are not repeated. No live Codex or privileged monitoring; installer/status/FAILED
grep remain unchanged. The four actual-Pixi activation cases passed locally and delegated
under their original15s bound. Their sentinels do not prove root monitoring or the separate
operator-host activation report. Latest static/local results are recorded above.
Agent did not alter Git index; operator staged files concurrently.

F7: no task-variable defect reproduced. Actual pixi run --locked launches, both explicit
-e detour-ai-augment and implicit environment selection, supply correct variables with
parent CONDA_PREFIX/PIXI_PROJECT_ROOT unset or stale. Updated existing task-launch regression
now tests actual Pixi activation rather than manually supplying those variables:4 passed.
Only sudo/pytest dispatch are safe sentinels; real configured watcher --help executes.
No task fix made without a reproduced defect. Operator clarified they entered Lima and only saw variables after pixi shell, then explicitly
corrected the Assistant: their pixi run invocation DID fail before pixi shell. Do not infer
an omitted pixi run or dismiss the report. No further clarification requested. Finding remains
UNRESOLVED on operator host. Local checks now also strip ALL parent CONDA_/PIXI_ variables
and the active environment bin from PATH before testing unset/stale prefixes. Include these
safe launcher checks in elevate; no actual sudo/pytest suites are dispatched by their sentinels.
Ordinary task definitions unchanged until a concrete correction can be justified.

#### Verification and exclusions for retained follow-up scope

TASK's requirement is upstream coverage BEFORE another expensive human live-Codex run.
Run the changed synthetic/import/process/fixture/helper checks locally where permitted,
including actual consumer paths, and relevant Ruff/mypy. Root and real browser/Unix-socket
checks must be prepared as the smallest targeted elevate batch after isolation is fixed;
operator execution is requested only when ready. Reuse existing graph-leaf evidence; update
its exact coverage/status rather than claiming a green subset proves pre-commit-operator.
A successful full production acceptance run is still required afterward, not claimed here.

Only retained scope is authorized; F3/F5 approaches above are withdrawn. F7 permits task-variable
expansion fixes in affected tasks; preserve pre-commit wrappers and grep. Elevate remains
authorized for bounded delegated verification. No sample_deploy, paused BDD, TASK/HUMANS/README,
shared schemas, Backend/Store/replay logic, production cleanup or unapproved data access.
No general logging cleanup, evidence-log suppression, timeout increases or service redesign.

## Store integrity and startup — implemented

Primary files:
- src/backend/helpers/data_models/ai_augment_backend_store.py
- protected/src/backend/helpers/data_models/replay_log.py
- src/backend/server.py; domain SQL/algorithms stay in src/backend/api.py.

The EXISTING detour_http_records table now has raw_line_sha256, written in the SAME
application transaction as its typed HTTP row. It hashes exact durable bytes including
LF, not reserialized JSON. Store writes a JSON _ReplayAnchor in the DuckDB TABLE COMMENT
on that table: sha256, ordinal, byte_offset. Metadata is written by _write_anchor using
COMMENT ON TABLE and read by _verify_log_projection from duckdb_tables().comment,
restricted to the current DB and main schema. No checkpoint table or authoritative-
projection crutch was added. Main pipeline metadata examples are Parquet KV_METADATA,
not this table comment.

Every resume/continue/read-only opening verifies the saved prefix independently, checks
ordered DB coverage through exact EOF and each suffix line's raw SHA256, and validates
anchor/line boundaries. Missing/extra/gapped rows, truncated prefix, invalid tail, absent
anchor or missing required hash column FAIL. Same config/anchor hash does not skip coverage
checks. Resume/IPC never insert missing history, repair tails, migrate old DBs, or silently
rebuild. The failure latch and explicit --new remain the reconstruction boundary.

Dashboard children deliberately retain --danger-no-verify-hash. An unchanged configured
hash remains anchored at its OLD verified boundary after live appends. A changed hash is
verified by RegisteredResource.verify_hash(), not accepted from stale parent booleans.
Only a fully verified writable opening can promote it, AFTER append-open preflight succeeds
and inside a transaction. Read-only IPC never promotes. Failed preflight/anchor transaction
leaves the previous comment intact. --new also verifies through RegisteredResource before
accepting the log. No config auto-repin or new hash-validation framework exists; the human
operator maintains config. Independent prefix hashing is the separately approved check.

_replay_log._lines streams exact LF-delimited bytes. Log size does not require loading all
HTTP payloads into memory during integrity verification. Operator logs show hashes,
boundaries, replay totals/line progress and acceptance/failure.

Writable startup obtains a real O_WRONLY|O_APPEND descriptor, with no CREATE/TRUNC, no-follow,
and same-inode checks. It closes without writing and restores0400. The same private opening
mechanism is used by real appends. IPC-only never acquires a writer. The retained locked
FD stays read-only; Store alone opens short detour-DB write transactions. API domain code
has no raw detour connection; the two source-DB consumers remain explicitly read-only.

Full --new/reset and resume/continue require the existing default-No confirmation. --yes
bypasses confirmations; there is no new replay/noninteractive flag. A registered empty log
initializes the standard hardcoded SHA256(empty), ordinal0, byte0 anchor. Nonempty --new
asks a SECOND default-No replay question before deleting the old detour DB/WAL; --yes accepts
both. Refusal preserves the old DB. Replay seeds the empty anchor, applies line1 onward
through the common live applicator, and promotes only after complete success. First invalid
framing/schema/linkage/domain/dependency line stops startup. No reappend, provider HTTP,
Backend archive publishing or repair. Existing source/replay-path deletion guards remain.
The historical INNERDICT_AND_CARD verdict substitution is gone: re-evaluation disagreement
fails. Persisted validation-stage values/schema are unchanged.

## 1. Remove Backend’s knowledge of its launcher

Implemented: _watch_control_parent, its task setup/cancellation, PID environment variable,
polling constant and dead locale/imports are removed. Dashboard no longer injects the PID.
API startup still initializes workflow/preflights/stdin; shutdown still gathers authoritative
background tasks and raises their failures before Store closes.

Dashboard SIGKILL may leave a Backend alive. Restart intentionally treats that process as
external through explicit Probe/Query; borrow it but never adopt/reset/stop it. No guardian,
parent-death hook, durable ownership registry, orphan cleanup or automatic startup probe.

## 2. Make initialization flags irrelevant to IPC-only

Implemented: --new and --resume/--continue are independent parser booleans. Full Backend
requires exactly one. IPC-only normalizes both False, including supplied/conflicting modes.
--config remains required. IPC-only only serves wholesale /query and cheap OPTIONS: no
startup/reset/replay prompts, run-outcome routes, DB creation, catch-up, append or promotion.
The literal DASHBOARD_QUERY_PATH = "/query" is preserved.

## 3. Physically bypass initialization in IPC-only

Implemented: main uses confirmed=False for IPC-only, preserves common process lock/config/
runtime setup, directly enters backend_store.read_only(), serves query-only IPC, and emits
the clean-close acknowledgement only after successful context exit. Missing/invalid
DB fails without initialization. backend_store_lifecycle is full-only, with Store.writable;
explicit --new invokes the Store replay-confirmation callback. No read_only selector remains.

## 4. Exclude IPC-only from Dashboard initialization bookkeeping

Implemented: _BackendSupervisor._start supplies () initialization args for IPC-only, and
_stop calls finish_backend_stop only for full children. IPC uses the ordinary readiness
timeout, not the rebuild timeout. First owned full start is --new --yes; only a successful
full start AND clean stop enables later --resume --yes. A failed cycle, including the first,
blocks further full starts for operator intervention rather than rearming destructive new.
The policy is private per Dashboard context, not global/class/persisted storage. Query and
borrowed/external lifetimes do not alter it. Codex launches use the same full-start policy.
Repository-root pyproject.toml serve usage text changed; argument forwarding is untouched.

## IPC/protocol details — implemented

- serve_dashboard_query_only uses local stopped=False; SIGINT/SIGTERM handler only assigns
  it True, and the loop checks worker liveness then time.sleep(0.1). Cleanup and prior signal-
  handler restoration remain. No threading.Event lock in the signal handler.
- BACKEND_STORE_CLOSED_CLEANLY retains its exact value and now lives in
  protected/src/backend/helpers/vars.py. Server and Dashboard import from there; not locale.
  Acceptable exit + acknowledgement + no forced kill still define clean owned shutdown.
- QueryRequestProperty is an empty documented parameterless Protocol. Concrete QueryRequest
  keeps outbound_http; send_query_request(QueryRequest()) remains typed. No filters/body/
  by-namekey query or transport redesign.

## Dashboard queue, publishing, lifecycle and logging — implemented

ui.py remains the composition/page/controller location; no separate exporter/services added.

Queue processing is a controller-wide runtime switch, always stopped for a new Dashboard
process. Stored queues restore but do not dequeue until Start. One worker/event is retained;
permission check and get_nowait have no intervening await. Enqueue/Start wake it. Stop only
gates the NEXT dequeue, never cancels the current run, changes its outcome or stops Backend.
Browser refresh reflects the switch. Cancel remains separate and actually stops the current
run; queued cancellation remains, and neither changes the switch nor re-enqueues a run.

Backend no longer publishes card ZIPs on live validation, repeated validation, writable
startup or explicit replay. _publish_stored_cards, publish_card_zip, _same_zip_contents,
publication-only imports/constants/preflight checks are removed. DB validation/materialization,
CAS/evidence and shared card utilities remain. Existing archives are never deleted/repaired.

Explicit command:

```bash
pixi run -e detour-ai-augment python -m src.detours.detour_ai_augment.src.control_centre.dashboard.ui publish completed --config config_ai_augment.json
```

The command uses normal NiceGUI config/storage/services startup, the stored wholesale
Dashboard snapshot and journal, existing unfiltered displayed lifecycle, and normal shutdown.
It publishes only non-INELIGIBLE, CURRENTLY COMPLETED researchers with download_available.
No implicit query, Backend launch, source-DB load, queue processing, abandoned remote-run
cleanup or journal mutation. _ResearcherCardView owns download_available, filename_stem,
docx_filename and render_docx; the button and batch share them. Button sends browser bytes; batch writes DOCX
to configured output_dir, overwriting same names on explicit rerun. No ZIP/browser automation.
Count/progress/path/final logs include zero-file no-op. First render/write error stops the batch,
keeps prior files, requests normal shutdown and returns a failing exit status.

Dashboard startup config/hash/storage exceptions now log and request app.shutdown(), with
APPLICATION_EXIT_CODE=1. Failed partially started services are cleaned up before publication;
normal shutdown hooks remain and cleanup failures also mark the exit unsuccessful. This was
tested through real NiceGUI background dispatch/shutdown flag/hooks and a subprocess exit,
with only its socket-serving loop substituted. No live server was bound.

P12 reviewed all of ui.py, including existing callbacks, controller/process/HTTP boundaries,
pure views and refresh helpers. Missing emit_log calls were added for probe actions/statuses/
detailed errors, Backend start/readiness/session supply/borrowing, non-failed run transitions,
final pull/outcome requests/responses, explicit query, card rendering, DOCX render/send/failure,
user selection filters, publishing progress/no-op/failure, and startup/shutdown errors.
Existing adequate logs were retained. No new probes/refresher/orchestration behavior or broad
logging framework. Pure formatting/view helpers and timer-driven repaint remain silent.

## Dataclass conversion inventory — implemented

All25 in-scope remaining declarations were converted; no dataclasses remain outside
sample_deploy. Its PriceQuote, LogEvent and _DummyQuote remain dataclasses intentionally.
Dashboard's earlier approved view names/aliases remain unchanged.

FrozenStrictModel, without config overrides:
- api.py: _PushConfiguration, _ArchivedFile, _RolloutRecord, _SessionMetadata, _CodexFcRow,
  _CodexFcoRow, _CodexTurnRefRow, _RolloutIndex, _EvidenceMatch, _EvidenceCandidate,
  _EvidenceItemAssessment, _EvidenceAssessment.
- protected Backend CiteSection; ModelHttpInterceptor (record_get callable, PrivateAttr caches).
- AuditReadConfiguration.
- Test helpers BackendTestPaths, ExpectedEvidence, FakeResponse, OperatorRuntime and
  WorkflowCheckpoint.

Explicit BaseModel/ConfigDict where a different contract is needed:
- _DashboardIpcServer, DashboardProcess, OperatorProcessSnapshot retain frozen/strict/extra-forbid
  with local arbitrary-types support for live opaque handles. DashboardProcess validates its
  shared output list without copying, preserving collector-thread identity.
- Appendwatch Record and paused-BDD LifecycleState remain mutable, strict, extra-forbid with
  assignment validation. Record's two shallow copies use model_copy; constructors are keyworded.
  BDD change is model/import-only; its suite was NOT reactivated, repaired or run.
- FakeResponse.json intentionally implements requests.Response's dict-returning stub contract,
  with a local override annotation for Pydantic's unrelated deprecated JSON-string method.
  Pasted production pydantic_to_paste/StrictModel are untouched.

Standalone integration (part of the approved conversion, not provisioning redesign):
- deploy.sh ships the unchanged canonical repository-root src/helpers/architecture.py.
- provision.sh requires Python3.12+ for its syntax, provisions python3-venv if needed, and
  creates/reuses root-owned AIVM_AUDIT_ENV=/usr/local/libexec/aivm-audit-env (operator rename).
  It installs Pydantic>=2,<3 there if absent; it does not rely on distro Pydantic being v2.
- The canonical module is installed at /usr/local/libexec/src/helpers/architecture.py; audit
  executable shebang and appendwatch systemd command use that venv. Shared import preflight
  and the controlled module search path are local to existing provisioning. Audit permissions,
  watcher logic and remote process behavior are unchanged. No fork of FrozenStrictModel.
- Deployed-layout imports were tested away from the repository; Python3.12 syntax parsed;
  actual guest installation/PyPI access/deployment was NOT performed here.

## Retained architecture/contracts

- API keeps domain/evidence algorithms and SQL; Store owns all detour DB/replay I/O and
  transactions. Main source DuckDB is read-only. execute().fetchone()/fetchall() return
  detached consuming rows; no escaped connection/cursor. Modes are writable/read_only.
- Live HTTP remains capture -> append/fsync -> common projection -> typed DB readback ->
  downstream. Speculative missing-input validation rolls back before live capture; no replay
  network fallback. Transactional Codex IDs consume no IDs on rollback.
- /validate keeps commit_id, serialized PostCommitValidation and Submission/StandardizedSubmission,
  discriminator, provider HTTP UUIDs, commit-shaped headers and null response fields.
  HttpRequestLogRecord.from_response/to_response remain the conversion boundary.
- CAS fails on missing/corrupt evidence; no redownload. No automatic config repin, DB catch-up,
  tail repair or publication recovery. Derived-table discipline is not a shadow-rebuild proof.
- NiceGUI storage adapter owns immutable wholesale query snapshot and separate run journal/queue.
  Controller has no query client; explicit composition callback owns Query IPC. No startup,
  repaint or card query/source-DB reads. Snapshot replacement follows successful child cleanup.
- Finalization: CODEX_EXITED -> one ordinary /pull;410 completed, anything else including503
  failed -> outcome IPC -> owned Backend shutdown. Cancellation independent. Snapshot updates
  never mutate the run journal. Explicit four-stage cheap Probe remains independent.
- Existing remote interrupted-run cleanup remains for interactive startup, skipped for publishing.
  It is not local orphan-Backend cleanup. Owned stop still SIGTERM, bounded wait then SIGKILL;
  borrowed/external Backend is never stopped or reset.
- Human-owned README/HUMANS/TASK and signed-off comments preserved. HUMANS' historical proposals
  do not revive superseded scope. Agent test selections exclude historical captures and
  prohibited production artifacts. The discovered NiceGUI persistence leak violates the
  intended test-isolation contract; F1 now prevents that leak, with local real-persistence
  checks passed and real browser/production acceptance still outstanding.

## Verification evidence

Completed P1-P12 implementation checks (not historical handoff totals; not P13 evidence):
- Broad hermetic API/IPC/HTTP-loop/Store/UI/framework/model-deployment/shared-HTTP suite:
  306 passed,1 skipped,3 deselected (110.83s).
- After final Store ordering correction: strict-integrity matrix, atomic promotion/preflight
  failure, unexpected IPC worker death and provisioning syntax checks:28 passed (37.93s).
  This overlaps the broad suite; totals are NOT additive.
- Audit/appendwatch selected isolated checks:12 passed,41 deselected.
- Pasted-model fake-response suite:22 passed,1 real-provider case deselected.
- Dataclass inventory:zero outside excluded sample_deploy. Retained deploy.sh/provision.sh
  edits passed bash -n; reverted proxy launcher checks are not scope evidence.
- Final Ruff and strict mypy passed after the last edits (56 files).
- git diff HEAD --check passed. No staging/unstaging; operator index remains intact.

Main check commands, from repository root:

```bash
pixi run -e detour-ai-augment env ruff check src/detours/detour_ai_augment src/helpers/data_models/http_request_log.py
pixi run -e detour-ai-augment env mypy --config-file src/detours/detour_ai_augment/mypy.ini src/detours/detour_ai_augment src/helpers/data_models/http_request_log.py
```

Core pytest selection: tests/backend/{test_api,test_ipc,test_http_interceptor,test_backend_store}.py,
tests/control_centre/{test_ui,test_audit_read}.py (detour-relative; operator consolidated
startup-exit/model-deployment checks into these modules),
plus repository-root tests/test_http_request_log.py. Exclude captured_operator_push,
historical_haanen_retry and real_mode_0600_unix_socket; exclude real_api/operator/needs_sudo.
No test_ui_e2e, real socket/HTTP providers, guest deployment or paused BDD execution.

## P17 — Completed: Dashboard layout only

2026-09-17: operator requested recording these two surgical formatting changes in WORK.
Approved methods applied after P13. Ruff/strict mypy passed; only grouping/order changed.
No new layout tests were added. The existing real-browser layout contract subsequently
passed in P18's targeted elevate rerun, recorded below.

Limit production changes to _ControlCentrePage.build_header and build_card_panel in
src/control_centre/dashboard/ui.py, plus WORK status/evidence. Reuse existing NiceGUI
containers/styles; only adjust grouping/order/indentation of existing elements.

Operator steering during implementation: immediately move both Start/Stop queue-processing
labels into Control Centre Locale.ACTION_START_QUEUE_PROCESSING and
Locale.ACTION_STOP_QUEUE_PROCESSING. Done in locale.py and both ui.py construction/refresh
uses; no behavior change. This explicitly extends P17's file boundary to the existing locale
module; the snippets below reflect the authorized label move.

### Header: two distinct rows, in this exact order

Operator corrected the layout: buttons share the title row, immediately to its right.

1. Left-to-right: "AI augmentation Control Centre" (existing Locale.PAGE_TITLE), then
   the existing Probe, Query IPC and Start queue processing buttons.
   Preserve the existing dynamic Stop queue processing label when processing is enabled.
2. Existing status labels, left-to-right: Backend API; IPC; Lima/SSH; Codex; Probed.
   Preserve current label text, status values and refresh logic; these names specify order,
   not a request to relabel statuses.

Use a vertical header container retaining PAGE_HEADER_TEST_ID with these two rows.
Keep existing child handles, callbacks, test IDs and responsive styling.

### Card download buttons: one horizontal row

Wrap the existing download_card_button_docx and download_card_button_txt construction in
one ui.row, in that order: Download DOCX on the left, Download Markdown on the right.
Keep the card Markdown below/outside the button row. Preserve existing button labels,
styles, handles, test IDs, handlers, enable/disable rules, download content and logging.

### Exact code snippets

These are the complete replacement methods on _ControlCentrePage in ui.py.
Only existing element grouping/order changes plus the explicitly authorized Locale labels;
no new imports, callbacks or helpers. Applied to production code as recorded; no additional behavior changes.

```python
def build_header(self) -> None:
    with (
        ui.column().style(FULL_WIDTH_STYLE)
        .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_HEADER_TEST_ID))
    ):
        with ui.row().style(RESPONSIVE_ROW_STYLE):
            ui.label(Locale.PAGE_TITLE)
            self._handles.probe_button = ui.button(Locale.ACTION_PROBE, on_click=self.probe_all)
            self._handles.backend_refresh_button = ui.button(
                Locale.ACTION_QUERY_IPC, on_click=self.refresh_from_ipc,
            ).props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=BACKEND_REFRESH_TEST_ID))
            self._handles.queue_processing_button = ui.button(
                Locale.ACTION_STOP_QUEUE_PROCESSING if self._controller.queue_processing
                else Locale.ACTION_START_QUEUE_PROCESSING,
                on_click=self.toggle_queue_processing,
            )
        with ui.row().style(RESPONSIVE_ROW_STYLE):
            self._handles.backend_status_label = ui.label()
            self._handles.backend_ipc_status_label = ui.label().props(
                _NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=BACKEND_IPC_STATUS_TEST_ID)
            )
            self._handles.ssh_status_label = ui.label()
            self._handles.codex_status_label = ui.label()
            self._handles.probe_time_label = ui.label()
```

```python
def build_card_panel(self) -> None:
    self._handles.card_container = (
        ui
        .card()
        .style(CARD_CONTAINER_STYLE)
        .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=PAGE_FOOTER_TEST_ID))
    )
    with self._handles.card_container:
        with ui.row().style(RESPONSIVE_ROW_STYLE):
            self._handles.download_card_button_docx = (
                ui
                .button(
                    Locale.ACTION_DOWNLOAD_DOCX,
                    on_click=self.download_displayed_card,
                )
                .style(ACTION_BUTTON_STYLE)
                .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=DOWNLOAD_CARD_DOCX_TEST_ID))
            )
            self._handles.download_card_button_docx.disable()
            self._handles.download_card_button_txt = (
                ui
                .button(
                    Locale.ACTION_DOWNLOAD_TXT,
                    on_click=lambda: self.download_displayed_card(output_format="txt"),
                )
                .style(ACTION_BUTTON_STYLE)
                .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=DOWNLOAD_CARD_TXT_TEST_ID))
            )
            self._handles.download_card_button_txt.disable()
        self._handles.card_markdown = (
            ui
            .markdown("")
            .style(CARD_MARKDOWN_STYLE)
            .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(test_id=CARD_MARKDOWN_TEST_ID))
        )
```

### Boundaries

Everything else stays unchanged: no behavioral changes to Probe, Query IPC, queue control,
statuses, cards/downloads, storage or Backend; no helper/classes/refactoring, renames,
configuration changes, or changes to other page sections. This does not authorize fixes
tracked separately in P18 and does not alter P13.
At implementation, run applicable static checks; no new test framework, business-logic
tests or operator E2E run is needed for this container-only formatting edit.

## P16 — Completed: Dashboard Markdown/TXT download

2026-09-17: operator approved the proposed shared download contour and requested
implementation, with two corrections: button label is "Download Markdown" (no .txt
parenthetical); formerly unqualified DOCX-only button objects must be explicitly named
with symmetric _docx / _txt suffixes. TASK/WORK reread before implementation.

Narrow scope: ui.py, existing protected Dashboard locale.py, existing download regression
in tests/control_centre/test_ui.py, naming-only update to the existing DOCX selector in
test_ui_e2e.py, and WORK. Main pipeline TXT mode was reviewed: unchanged Markdown, UTF-8,
shared card_filename basename plus .txt; no separate TXT renderer. Reuse the displayed
card and existing shared download handler, not a new exporter/helper hierarchy.
No shared pipeline edits, Backend/IPC/DB/storage changes, ZIPs, CLI/config changes, or
changes to publish completed (still DOCX-only). P16 did not change CAS; P13 is tracked separately.

### Approved snippets, incorporating the operator's naming corrections

_ResearcherCardView: extract the existing basename, preserve existing DOCX callers:

```python
@property
def filename_stem(self) -> str:
    return card_filename(
        draw_label=self.researcher.draw_number,
        first_name=self.researcher.namekey.first_name,
        last_name=self.researcher.namekey.last_name,
    )

@property
def docx_filename(self) -> str:
    return f"{self.filename_stem}.docx"
```

Add Literal to ui.py's typing import. UI constants and handles:

```python
TXT_MEDIA_TYPE: Final = "text/plain; charset=utf-8"
DOWNLOAD_CARD_DOCX_TEST_ID: Final = "download-researcher-card-docx"
DOWNLOAD_CARD_TXT_TEST_ID: Final = "download-researcher-card-txt"

# _UiHandles: replace the old download_card_button, update all consumers.
download_card_button_docx: Any | None = None
download_card_button_txt: Any | None = None

# Existing Locale:
ACTION_DOWNLOAD_TXT: Final = "Download Markdown"
TXT_DOWNLOAD_FAILED: Final = "Researcher card TXT download failed"
```

Keep the DOCX button/default handler, rename its handle/selector explicitly; add beside it:

```python
self._handles.download_card_button_txt = (
    ui.button(
        Locale.ACTION_DOWNLOAD_TXT,
        on_click=lambda: self.download_displayed_card(output_format="txt"),
    )
    .style(ACTION_BUTTON_STYLE)
    .props(_NiceGui.TEST_ID_PROP_TEMPLATE.format(
        test_id=DOWNLOAD_CARD_TXT_TEST_ID,
    ))
)
self._handles.download_card_button_txt.disable()
```

Replace the single-button availability/clear sections with:

```python
# _show_card:
for button in (
    self._handles.download_card_button_docx,
    self._handles.download_card_button_txt,
):
    if button is not None:
        if card.download_available:
            button.enable()
        else:
            button.disable()

# _clear_displayed_card:
for button in (
    self._handles.download_card_button_docx,
    self._handles.download_card_button_txt,
):
    if button is not None:
        button.disable()
```

Shared handler (no DOCX suffix: it now serves both formats):

```python
async def download_displayed_card(
    self,
    *,
    output_format: Literal["docx", "txt"] = "docx",
) -> None:
    label = output_format.upper()
    card = self._displayed_card
    if card is None or not card.download_available:
        emit_log(
            Locale.CONTROL_CENTRE_LOG_PREFIX,
            f"{label} download skipped: no available card",
        )
        return

    button = (
        self._handles.download_card_button_docx
        if output_format == "docx"
        else self._handles.download_card_button_txt
    )
    filename = f"{card.filename_stem}.{output_format}"
    if button is not None:
        button.disable()

    emit_log(
        Locale.CONTROL_CENTRE_LOG_PREFIX,
        f"Rendering {label} download: {filename}",
    )
    try:
        if output_format == "docx":
            content = await asyncio.to_thread(
                card.render_docx, self._reference_docx,
            )
            media_type = DOCX_MEDIA_TYPE
        else:
            content = card.card_markdown.encode(TEXT_ENCODING)
            media_type = TXT_MEDIA_TYPE

        ui.download(content, filename=filename, media_type=media_type)
        emit_log(
            Locale.CONTROL_CENTRE_LOG_PREFIX,
            f"{label} sent to browser: {filename}; {len(content)} bytes",
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        emit_log(
            Locale.CONTROL_CENTRE_LOG_PREFIX,
            f"{label} download failed: {filename}; {exc!r}",
        )
        ui.notify(
            Locale.DOCX_DOWNLOAD_FAILED
            if output_format == "docx"
            else Locale.TXT_DOWNLOAD_FAILED,
            type="negative",
        )
    finally:
        if button is not None and self._displayed_card is card:
            button.enable()
```

Implemented the pinned shape. The existing card display log now reports DOCX/TXT
availability. Existing DOCX-only browser-test selector/local names were updated; the browser
suite was not run at P16 implementation. The real browser DOCX-download test subsequently
passed in P18's targeted elevate rerun; this is not browser TXT-download coverage.
No generic old download-card handle/selector references remain.
Verification: 7 focused UI cases passed (184 deselected, 11.11s), covering both download
formats with exact Unicode bytes/filename/MIME, button clearing/skipped download, logs,
snapshot invalidation, unchanged completed DOCX publishing, publication failure/no-op and
existing detailed DOCX error logging. Ruff and strict mypy passed the four touched Python
files; git diff --check passed. No real browser/operator/server/network execution.

Focused command:

```bash
pixi run -e detour-ai-augment env pytest -q src/detours/detour_ai_augment/tests/control_centre/test_ui.py -k 'displayed_card_download or snapshot_replacement_clears or publish_completed or publish_one_shot or probe_and_docx_failures' -m 'not real_api and not operator and not needs_sudo'
```

## P13 — Completed: extensionless, sharded CAS layout

Approved 2026-09-16: the operator approved the exact narrow proposal and snippets below
and initially requested recording them in WORK. The later in-order implementation request
authorized implementation; it is now complete.

### Exact scope

Former AiAugmentCAS layout was flat <cas-root>/<full-sha256>.jsonl. The suffix describes
Codex rollout content but is unnecessary for content addressing; the README requires
content addressing, not that suffix or a flat layout. Implemented replacement:

```text
<cas-root>/ab/cd/abcdef…<full-64-character-digest>
```

The first two digest characters form the first shard, the next two the second; the leaf
is the FULL digest, with no extension. Keep rollout content and metadata unchanged.

Limit implementation to:

- src/backend/helpers/data_models/ai_augment_cas.py: canonical digest validation in
  _blob_path, the extensionless two-level layout, shard-directory creation/symlink checks,
  replacing the existing flat-parent validation guard, and publication durability below.
- Necessary path expectations/fixtures and corresponding focused checks in
  tests/backend/test_api.py, tests/backend/test_http_interceptor.py and
  protected/tests/operator/test_operator_e2e.py. Update/remove the old filename-template
  constant and its imports only as required by the new path shape.

### Exact approved code snippets

Core path change (add the import at module level; method remains on AiAugmentCAS):

```python
import re

def _blob_path(self, sha256: str) -> Path:
    if re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise ValueError(Locale.ROLLOUT_CAS_BLOB_INVALID)
    return self.path / sha256[:2] / sha256[2:4] / sha256
```

Digest validation matters because CodexRolloutRecord.sha256 currently accepts any strict
string. Do not extend this into a separate model/schema redesign.

Before publishing, in copy_rollout:

```python
destination = self._blob_path(archived.sha256)
for directory in (destination.parent.parent, destination.parent):
    directory.mkdir(exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(Locale.ROLLOUT_CAS_BLOB_INVALID)
```

Replace the existing flat-directory validation guard in validated_rollout:

```python
path = self._blob_path(reference.sha256)
if (
    any(p.is_symlink() for p in (path.parent.parent, path.parent, path))
    or not path.is_file()
):
    raise ValueError(Locale.ROLLOUT_CAS_BLOB_INVALID)
# Existing digest/size/line-count verification remains.
```

Publication must also fsync BOTH shard directories and the CAS root, so newly created
directory entries are durable. Preserve existing blob fsync and publication mechanics;
no additional code snippet was proposed for this explicitly approved requirement.

### Boundaries and existing blobs

- Keep existing digest, byte-size and line-count verification and missing/corrupt-blob
  failure behavior. No automatic recovery or redownload.
- No DB/replay schema or reference changes: references already contain digests, not CAS
  storage paths. Original rollout filenames in SourceKey remain unchanged, including their
  .jsonl suffixes; only CAS blob filenames become extensionless.
- Existing blobs require an explicit layout move, otherwise old references fail lookup.
  No automatic migration or fallback is approved. No production-data move or migration
  utility is included in this code-only scope; TASK's artifact restrictions still apply.
- No CAS generalization/refactor, new service hierarchy or unrelated changes.
  sample_deploy remains explicitly out of scope.
- Verify this localized change with focused hermetic CAS/path checks and applicable
  Ruff/mypy checks; do not run the real operator suite in this restricted environment.

P13 verification: the existing audit-copy regression first failed against the old flat
layout, then passed after implementation. Sharded readback, corruption/size/line-count,
missing/unsharded paths, shard/leaf symlinks, live-copy shard rejection, duplicate copy and
real fsync of blob/both shards/root were verified. 18 selected CAS/audit/HTTP-interceptor
cases passed; 6 malformed-digest cases passed after correcting their test fixture's unrelated
minimum line_count (24 cases total). Ruff and strict mypy passed the four touched modules.
Operator fixture path expectations updated, but no live operator tests or blob migration ran.

## P14 — Completed: current Backend table and mock-free startup-condition tests

2026-09-17 operator requested the updated IPC-only/full-Backend lifecycle comparison and
pytest.mark.parametrize coverage using real code, no mocks. Operator clarified this is a
matrix of STARTING CONDITIONS, not an end-to-end serving-lifespan test. No AIVM is needed:
tests stop after real argument parsing, confirmations, config/context/resource construction,
process locking and Store initialization/verification. They do NOT claim coverage of real
HTTP/socket serving, SSH preflights or signal-driven shutdown. No such behavior is mocked.
The table itself was checked directly against server.py, api.py, ipc.py and Dashboard supervisor.

New TestBackendStartupConditions in tests/control_centre/test_ui.py (moved there wholesale
by the operator) uses real subprocess stdin for prompts, real
file locks, a synthetic 307-person source DB satisfying the real cohort invariants, and real
DuckDB/replay files. The startup test class locally overrides the surrounding UI/Lima mocking fixtures with
empty fixtures; existing UI tests keep their original fixtures. No production object/function
is patched for the startup matrix.
Modes: IPC-only/new/resume/continue. Conditions: ready/read-only source, missing/malformed/
invalid config, missing/corrupt source, missing replay, hash mismatch, missing/corrupt/
unanchored detour DB, unprojected valid log record, {} with/without LF, missing/unknown/
ineligible namekey, and held Backend lock. Additional parametrizations cover full-mode
confirmation No/EOF/Yes/--yes, second nonempty-replay confirmation, required --config and
all combinations of initialization flags with/without IPC-only. Assertions include source/
log content preservation, no implicit DB change for resume/IPC, and DB preservation on
replay refusal. Local installed splink_udfs is a prerequisite for real Store opening.

This is tests/WORK only: no production behavior changes, no P13 implementation,
no guest provisioning, sockets, browser/Codex runs or sample_deploy changes.
Verification: 111 passed (538.68s) in TestBackendStartupConditions: 72 mode/condition
cases, 15 full-start confirmation cases, 4 nonempty replay-confirmation cases, 16 mode-parser
cases and 4 required-config cases. No mocks, guest, sockets or production data used by this
matrix. The independently passing 123 existing/moved tests are recorded under P15.

Current lifecycle comparison, checked against production code:

| Concern | IPC-only | Full Backend |
|---|---|---|
| CLI initialization mode | Flags ignored/normalized off, even conflicting ones; no confirmation | Exactly one of new or resume/continue; default-No confirmation unless --yes |
| Selected researcher | Not required | Required and eligible |
| Initialization | Existing valid detour DB required; no rebuild/replay | New resets/replays after confirmations; resume verifies, never heals |
| Store | Read-only content access; no append preflight or anchor promotion | Short write windows, actual append-open preflight, verified transactional anchor promotion |
| Servers/routes | Unix IPC wholesale /query + OPTIONS | Uvicorn HTTP plus Unix IPC /query and completed/failed/cancelled |
| Workflow startup | None | Real SSH/audit readability checks and session-ID stdin reader |
| Parent watcher | Absent | Absent |
| Dashboard readiness | OPTIONS /query | /openapi.json then ordinary /pull must return 200 |

Both require --config, acquire the exclusive Backend process lock, construct resources/
Store/context, verify configured hashes unless delegated/bypassed, and load source researchers
from the read-only main DB. Store independently checks the saved replay prefix, suffix hashes
and exact DB/log coverage. IPC may enforce 0400 permissions but never writes DB/log contents.
New nonempty replay has a second default-No prompt before DB deletion; --yes accepts both.

IPC wind-down: SIGINT/SIGTERM sets a plain boolean; loop checks worker liveness, then stops/
joins/closes IPC, unlinks socket, restores handlers and exits Store. Full wind-down: Uvicorn
drains HTTP, stops IPC, awaits authoritative background commit/validation work, exits Store.
Successful Store closure emits the clean-close token; main finally releases the process lock.
Neither mode publishes Backend card archives or has a Dashboard-parent watcher.

Dashboard sends SIGTERM to an owned child, waits 10s, then SIGKILL if needed. Clean means the
acknowledgement, an acceptable exit and no forced kill. Borrowed Backends are never stopped.
IPC children do not change full-child initialization bookkeeping; first owned full cycle uses
--new --yes, later cycles use --resume --yes only after successful startup AND clean shutdown.
A failed full cycle latches failure rather than authorizing unattended destructive retry.

## P15 — Completed: operator-staged test renames/consolidations review

2026-09-17: operator requested review/ack of already-completed test renames and whole-file
moves, authorizing only surgical import/Ruff/mypy fixes. Preserve chosen module names and
organization; never restore deleted modules or stage edits. test_http_loop became
test_http_interceptor; Store checks live in test_backend_store; model-deployment checks moved
into test_audit_read and framework-startup checks into test_ui. Operator also moved P14's
new startup-condition file wholesale into test_ui during work.

Found/fixed: duplicate/mid-file imports and repeated __future__ imports in both consolidated
Control Centre modules; stale test_http_loop fixture import in test_backend_store; appended
NAMEKEY collision (renamed only the startup fixture identity to STARTUP_NAMEKEY). The moved
empty module-wide Lima autouse fixture would disable existing UI test isolation. Scoped the
new mock-free startup tests/three no-op fixture overrides inside TestBackendStartupConditions
so existing UI fixtures keep their behavior. No production changes or module renames.
Verification: Ruff passed; strict mypy passed all14 active detour test files; collection
passed across active detour/Backend/operator test directories (no test execution at collection).
Moved/consolidated UI, audit, Store and interceptor checks passed: 123 passed, 111 new startup
cases deselected (144.40s). These checks include the existing UI fixture behavior after the
class-scoped correction. Paused BDD and sample_deploy remain unexecuted. P14 is verified
separately; no additional broad regression rerun is needed for this import/name cleanup.

## P18 — Pinned corrections implemented; production verification failed; follow-up review above

2026-09-17: operator approved recording the identified integration gaps as a new P item,
including the broader homework the Assistant missed before handing work to the human.
TASK was reread IN FULL, especially its testing philosophy. Approved corrections are now
implemented after verified P13/P17; earlier upstream checks and delegated results are
recorded below. The latest production run FAILED root launchers and was interrupted during
operator completion; the additional storage-contamination finding is critical. Follow-up
current corrective status is recorded in F1-F7 above, including the later withdrawals. The separate Mode-3 follow-up is
already approved, implemented and verified.
P13/P17 are complete, with their exact scope unchanged.

### Final task boundary: wrappers rejected; Conda interpreter approved

Operator clarified: pre-commit task SHAPE changes are REJECTED, but the previously proposed
APPENDWATCH_PYTHON="$CONDA_PREFIX/bin/python" substitution is APPROVED in the existing
test-detour-ai-augment and test-detour-ai-augment-root tasks. Both substitutions are applied;
no other changes to those tasks are authorized. Verify the selected interpreter and actual
privilege-drop accessibility; no permission changes are approved.

Keep pre-commit-operator and pre-commit-extra-operator unchanged, including their existing
grep functionality. The residual agent extra-wrapper patch was removed from the WORKING
TREE only; Git index/staging was not altered. Wrapper aggregation/grep reformulation is not
pending approval or implementation. Any special verification status aggregation/reporting
belongs ONLY in agent-owned elevate. All other task edits still need explicit approval.

The agent briefly over-applied the rejection to the two approved interpreter lines, then
restored them on this clarification. Effective diff: the two approved launcher interpreter
substitutions plus elevate; NO pre-commit wrapper changes. Preserve concurrent user edits.

Unchanged pre-commit wrappers retain the reviewed status/reporting limitations. elevate can
aggregate its own verification results, but success there does not prove those wrappers have
been corrected. Local leaf-graph review and P19 checks are recorded below. The initial
delegated batch failed at browser startup; all five failures passed in the targeted rerun
without startup-code/timeout changes. Root tests later ran on prod and failed before watcher
startup; the operator workflow also stalled. See the latest review, not the older readiness
recommendation.

### Implemented corrections and checks (not rollout acceptance)

- Shared architecture.py Ruff-only whitespace/import correction applied; human comments preserved.
- Operator fixture now invokes real server parsing/configuration/full Store initialization
  (--new --yes) and clean closure before first Query IPC. It does not start Uvicorn or perform
  remote workflow preflights. Synthetic fresh-fixture regression passed (1 test, 15.11s):
  actual helper creates DB, then real read-only Store/query produces the 307-person snapshot;
  replay remains empty and source bytes unchanged. No production artifacts or sockets used.
- Operator browser helpers now request Start explicitly and observe fresh query/failure logs
  within ordinary readiness/stop bounds. Headless helper/callback/controller checks passed as
  recorded below; these do not prove real browser serving. Delegated browser results remain
  initially failed in five cases at startup; those five passed in the targeted rerun,
  alongside the two browser cases that passed in the initial batch.
- Pre-commit wrapper edits are rejected; approved regular/root Conda interpreter lines are
  applied. The initial elevate batch retained its browser/Unix-IPC/socket-substitution checks
  and invoked the existing privileged appendwatch task and the mode0 synthetic module (its
  Kaleido child requires socket operations unavailable here). Its own shell runs all these checks,
  aggregates failures, and prints grep -n FAILED matches (or explicit no-match/read-error)
  against elevate.log without masking any earlier failure. GNU script -e remains the Linux
  log/status boundary. TOML parse and bash -n passed, and a before/after task-map comparison
  confirmed only elevate changed in this step. This initial delegated batch completed with
  exit1; its results and the narrowly targeted follow-up batch are recorded below.
- Query-helper regression updated for immediate startup/query/process failure and stale success
  notifications. Browser fixture now supports publishing startup and the queue-processing
  property/setter; its old header geometry assertion was aligned with P17. New headless
  harness/controller-gate and browser-fixture interface regressions passed with the query
  failure/stale-success cases: 7 passed, 195 deselected (5.34s). Browser transport is substituted;
  actual operator helper, page callbacks and controller gate/worker execute. An initial threaded
  test driver stalled; it was stopped and replaced by bounded synchronous asyncio.Runner
  dispatch with the existing inline-I/O seam, not production changes.
- Actual regular/root task-shell smoke tests passed: 2 passed,43 deselected (49.78s).
  Only pytest dispatch and sudo dispatch are sentinels; each actual configured watcher
  interpreter imports/executes the real appendwatch --help. No real root/privilege-drop claim.
- Full repository Ruff passed in the default environment; default full mypy passed (68 files).
  Ruff and detour strict mypy (53 files) also passed after P19's named-helper migration.
- Existing step4 synthetic leaf: 4 passed,1 slow case deselected (55.35s). Mode3 synthetic leaf:
  6 passed (28.23s). Mode0: 2 passed,2 failed (69.97s); failures are Kaleido's forbidden
  socket shutdown operation in this sandbox, not assertions in detour logic. Added that
  synthetic module to elevate for real execution outside this restriction; no mode0 code edits.
- Nonprivileged/nonsocket appendwatch leaf: 38 passed,7 deselected (30.51s).
- elevate's actual shell/PTY logger regression: 5 passed,8 deselected (5.71s). Controlled
  external-command outcomes cover all-pass, install/browser/root/mode0 failures; every stage
  still runs, exit status retains failure and matching FAILED lines are shown. An initial
  sentinel matched --playwright-chromium as the installer; corrected to inspect argv[2].
- Default main-suite feasible selection: 138 passed,3 skipped,3 deselected,3 failed (48.75s).
  Failures are environment/fixture prerequisites: config lacks linux_amd64 extension mapping;
  configured /Volumes/home/aicode extension binary unavailable; reviewed XLSX fixture at the
  operator path absent. No unrelated fixes/config changes made. Two DOCX-review tests that
  write data/test_data were excluded; the real_api case was excluded. Initial misspelled
  exclusion run was stopped before emitting test results, then corrected before this run.
  Slow step4 real-config and live-provider leaves remain unrun under TASK resource restrictions.

### Governing lesson from TASK

Human operator-run production E2E remains the acceptance cornerstone, not a substitute for
Assistant verification. TASK requires catching failures upstream wherever possible and,
when an operator discovers one, wiring appropriate upstream regression coverage without
another reminder. Operator time must not be used to discover missing imports, stale test
setup or inconsistent lifecycle assumptions that cheap checks/code review can expose.
This is bounded verification of the changed contour and its consumers, not permission for
an unrelated repo-wide rewrite or a new testing framework.

### Original P18 evidence and implemented corrective scope (historical, not pending)

Source: logs/from_operator/pre-commit.log and pre-commit-extra.log, supplied by the operator.
This subsection records the FIRST failed operator run that motivated the now-implemented
P18 corrections, not the latest logs currently occupying those paths. During that original
review only the shared-module Ruff error was reproduced locally. Ordinary checks stopped at Ruff. Root appendwatch tests: 3 failed
before watcher startup. Active operator case failed first Query IPC, then was interrupted;
2 other cases were intentionally excluded/skipped. None of that is an operator E2E pass.
Main real_api checks: 3 passed, 1 expected xfail. AIVM/auth/service preflight, Dashboard
cleanup and production-data pre/post hash preservation succeeded. Post-interruption
Playwright TargetClosed/pending-task warnings are not the initiating failure.

| Gap | Narrow correction | Required upstream evidence |
|---|---|---|
| Shared architecture module omitted from focused lint | Whitespace/import-spacing only in repository-root src/helpers/architecture.py (I001, E302); preserve human-signed comments | Actual lint covers affected shared dependencies as well as the detour; no new test for whitespace |
| Converted appendwatch imports Pydantic2 but task subprocess uses /usr/bin/python3 | APPROVED: set APPENDWATCH_PYTHON to the existing Pixi interpreter in regular/root tasks (and elevate). Interpreter/packages must remain accessible after dropping privileges to nobody | Real selected-interpreter subprocess imports/starts the watcher; do not substitute pytest's interpreter or mock the import. Retain existing real privilege-drop tests and check executable/dependency accessibility |
| Fresh operator fixture has empty replay/config, no DB, then immediately queries IPC | In protected/tests/operator/test_operator_e2e.py, initialize the isolated DB through the established full Backend --new/--yes lifecycle and clean shutdown before the first Query IPC | Synthetic fresh setup exercises real config/Store initialization, then succeeds at the query prerequisite; IPC-only against an uninitialized DB must STILL fail. Exercise the harness setup path, not a second manually prepared DB that bypasses it |
| Harness queues but never enables processing | queue_in_browser explicitly clicks existing Start queue processing as part of its normal browser sequence | Exercise that sequence against the real queue-control behavior: initially stopped, Queue alone does not dequeue, explicit Start permits processing. Existing controller-only tests are insufficient evidence that the harness performs Start |
| Query helper waits for success up to stale rebuild timeout600s after child failure | Observe query failure/process failure promptly in the existing operator helper, using ordinary IPC readiness bounds, not rebuild bounds | Known startup/query failure exits the helper promptly with useful diagnostics; success still proceeds normally. Do not merely lower the timeout and leave failure unobserved |
| Pre-commit wrappers can mask earlier failures; inverted grep message and wrong extra-log target | Pre-commit edits REJECTED. Keep those wrappers unchanged; put aggregate verification status and visible FAILED grep diagnostics only in elevate | Verify elevate shell syntax and status/FAILED reporting with controlled outcomes; inspect unchanged pre-commit limitations, but do not add tests claiming those rejected fixes exist |

Keep tests in existing relevant modules aligned with production naming: test_appendwatch,
test_ui (including TestBackendStartupConditions), test_audit_read/deployed-layout coverage
where appropriate, and existing operator/preflight checks. Update only directly affected
fixtures/launchers; no gratuitous module moves, new service layers or duplicate test harness.
Use existing hermetic seams for unavailable external systems, but never replace the very
boundary being tested (interpreter selection/import, Store initialization, queue permission,
query-failure observation or shell exit-status propagation). Extend meaningful existing
coverage instead of testing source-code strings or mirroring the implementation.

### Assistant homework before the next operator handoff

1. Trace each changed contract through its actual consumers and entrypoints. For these
   changes: dependency -> standalone executable -> regular/root test launchers -> deployed
   service; full/IPC startup contract -> fresh operator fixture -> first query; default-stopped
   queue -> browser harness -> dequeue; subprocess failure -> helper -> wrapper exit status.
   Read the callers and configuration, not only the changed functions.
2. Audit fixture/mocking assumptions. Identify prerequisite setup supplied by fixtures that
   the real operator sequence does not perform. P14's 111 real startup cases correctly prove
   individual modes, including rejection of missing DBs; they do not prove the operator
   harness initializes a DB before querying. Pydantic importing in the parent proves nothing
   about /usr/bin/python3 in its child. A passing deployed-service import does not cover the
   separate test-task interpreter. Record and close these specific integration holes.
3. Add regressions at the earliest realistic, cheap layer, then fix the issue. Capture the
   failure first where feasible; exercise normal and failing compositions, not only isolated
   green components. Preserve real filesystem/Store/process boundaries for the relevant
   assertions. No live model calls are needed to discover these setup/dependency gaps.
4. Run applicable available lint/type/import/subprocess/configuration/integration checks
   before requesting operator time. Use the full pre-commit-operator leaf inventory below,
   including shared modules and launchers, not merely the changed detour. Review selections,
   exclusions, interpreter/environment/permission differences and shell propagation; do not
   blindly invoke the root command in this environment.
5. Record exactly what passed, what was not exercised, and why. Test counts and mocked
   successes are not readiness evidence for an unexercised boundary. Distinguish code
   implemented, upstream integration verified, and real operator acceptance. If an execution
   prerequisite is unavailable, continue useful static/hermetic review and state the remaining
   runtime gap explicitly; do not silently substitute a different interpreter/lifecycle.

### Verification entrypoint: the full pre-commit-operator graph

Operator clarification: their acceptance entrypoint is exactly `pixi run pre-commit-operator`.
Assistant preparation must therefore inspect its FULL execution graph and run every leaf
that can be run within the available environment/TASK constraints, not just selected AI
augment checks. Trace both Pixi dependencies/aliases and shell-invoked tasks/commands,
including feature-specific task definitions, environment selection, pytest default/explicit
markers, platform/privilege requirements, short-circuit edges and exit-code propagation.

Current graph outline, checked against pyproject.toml (re-read actual definitions before use):

```text
pre-commit-operator
  Lima aicode: pre-commit
    lint
      ruff: src tests (default environment)
      mypy: src tests (default environment)
      mypy-detour-ai-augment (detour-ai-augment environment)
    test-repl
      test . (default environment; configured pytest defaults)
    test-detours
      step4-breakdown: normal selection + explicit slow selection (default)
      mode3-pgf-stats: its test module (default)
      mode0-econ-stats: its test module (detour-mode0-econ-stats)
      ai-augment (detour-ai-augment)
        regular detour/backend/operator-preflight selection, not needs_sudo
        explicit real_api institution round-trip, conditional on preceding success
  pre-commit-extra-operator
    Lima aicode
      test-repl-extra -> test . -m real_api (default)
      test-detour-ai-augment-root -> needs_sudo backend tests (conditional on preceding success)
    host
      test-detour-ai-augment-operator -> real operator workflow selection
```

This outline is not proof of execution and is not permission to skip nested shell leaves.
Before the next handoff, record a concise per-leaf inventory: actual command/environment,
selection, passed/failed/not-run status, evidence/log location, and reason/next action for
anything unavailable. An early root-task failure does not excuse ignoring later independently
runnable leaves. Reuse valid existing evidence where applicable; do not rerun equivalent
checks pointlessly. Broader verification does not authorize unrelated code changes; report
out-of-scope findings and obtain approval before extending the implementation scope.

### Current P18 leaf evidence (local/delegated, not production acceptance)

Commands below use the existing installed environment executables, always through the
required outer pixi run -e detour-ai-augment. Ruff/mypy/pytest use env dispatch or the
explicit installed executable of the graph leaf's required environment. All test data
created by the selected detour tests are synthetic/temporary.

| Leaf / environment | Selection and evidence | Remaining boundary |
|---|---|---|
| Ruff / default | ruff check src tests: PASS; also passed after P19 | None for current code |
| Mypy / default | mypy src tests: PASS,68 files | P19 touches only detour tests, excluded from this leaf |
| Mypy / AI augment | strict detour config: PASS,53 files after P19 | None for current code |
| Main tests / default | Latest PROD174 pass,5 skip,6 xfail,1 xpass (4.91s) | Both actual configured-binary tests now pass; no synthetic replacement |
| Step4 normal / default | explicit module, not slow/real_api: 4 pass,1 deselect | None for synthetic selection |
| Step4 slow / default | Latest PROD1 skipped/4 deselected | Five referenced real parquet inputs unavailable; not accepted as a pass |
| Mode3 / default | Approved test-console injection: full module6 pass; actual -s case passes at80/92-column PTYs; Ruff/mypy pass | This narrow fix is complete; assertions/production/tasks unchanged; broader acceptance failures remain separate |
| Mode0 / mode0 env | Local2 pass/2 socket-restricted failures; delegated complete module4 pass,11 deprecation warnings (18.03s) | Closed for synthetic selection; no mode0 implementation edits |
| AI augment normal / AI env | Latest PROD517 pass,9 fail,1 skip,3 deselect (110.02s) | IPC-only logging/test regression subsequently fixed and locally verified;8 missing-Chrome launch failures unresolved; earlier Chromium elevate not equivalent provisioning |
| Appendwatch normal / AI env | not needs_sudo, not socket/task-launcher: 38 pass; actual task-interpreter smoke2 pass | P19 sentinel uses named shared helper, rechecked with P19 |
| Pasted-model provider / AI env | Earlier fake-response22 pass; latest PROD real_api stage not reached | Normal task && stopped after9 failures |
| Main extra real_api / default | Latest supplied production run3 pass,1 expected xfail (3.09s) | No new Assistant live run |
| Appendwatch privileged / AI env | Latest PROD3failed/70deselected (0.26s) | Cached Python unreachable through0750 home after dropping privileges; dependency/fixture issue no longer the blocker |
| Operator workflow / host | Latest Query IPC/queue/Start succeeded, then0records/no full Backend start; Ctrl+C,88.42s | Active case interrupted; silent pre-start gate needs diagnosis; production data and NiceGUI guard PASS |
| Pre-commit wrappers | Inspected, UNCHANGED by explicit rejection | Existing failure/reporting quirks remain; no claim fixed |
| elevate / AI env | Earlier shell/browser/IPC/mode0 evidence below remains recorded | Those checks did not establish storage isolation; fix isolation before further browser/operator execution |

### Completed delegated run and targeted follow-up

Initial P18 delegated verification completed on2026-09-17 at15:38:32UTC, with exit1, reviewed
from logs/from_operator/elevate.log (then37791 bytes; the rerun replaced that file). Real Unix IPC and both socket-substitution cases
passed; browser2 passed/5 failed at the existing10s startup deadline (combined group5 passed,
5 failed in156.30s). These failures occurred before their UI assertions, including DOCX export
and the header contract. Some failed children emitted no output; others logged ready then
normal shutdown after the harness timed out. Sudo requested a password and exited before
the root tests ran. Root was unavailable in that delegated environment, so all three
needs_sudo appendwatch tests were left for PROD through the existing root task (also part
of pre-commit-operator). The subsequent production run did exercise that launcher and
failed before watcher startup, as reviewed above; it is no longer an unperformed check.
No privilege or permission workaround was made. Mode0 then completed:4 passed,11 deprecation
warnings in18.03s. This batch contained no live Codex workflow.

After local heavy checks finished, a socket-free fresh browser-module import/fixture profile
took4.01s +0.04s construction (5.00s process total). This does not establish why real HTTP
startup missed10s. Review confirms the failed cases stop in wait_for_server before browser
launch; no child traceback or HTTP error is reported. Earlier local heavy tests overlapped
the batch, so load is a possible contributor, not a proven cause. No timeouts changed.

The targeted P18 follow-up batch was prepared within existing Assistant-owned elevate authorization:
elevate selects ONLY the FIVE initially failed test_ui_e2e cases, retaining its cached Chromium setup,
PTY log, nonzero status preservation and FAILED grep. Pytest --durations=0 records timings.
Already-passed IPC/socket/mode0 leaves and the unavailable sudo invocation are removed from
this temporary batch; their regular tasks/tests are untouched. The existing elevate shell
regression now matches its two remaining stages (install/browser):3 passed,8 deselected
(6.35s), covering success and each stage failing without losing diagnostics/status. Ruff,
strict mypy and TOML/bash syntax passed. Task-map comparison confirms no additional task
edits beyond elevate and the two previously approved interpreter substitutions.

The operator completed this targeted rerun at15:46:13UTC on2026-09-17:
5 passed in97.60s, COMMAND_EXIT_CODE=0. Reviewed logs/from_operator/elevate.log was5548 bytes
at that time; the latest operator upload contains only the new pre-commit logs.
Passing cases cover compact line spacing, idempotent researcher/history selection, completed
metadata/history, actual DOCX browser download, and the overall browser/layout contract.
No production/test-startup code or timeout was changed between the failed run and this
rerun, and no heavy local suites overlapped it. The rerun closes the outstanding browser
verification, but does NOT prove contention caused the earlier timeouts or establish load
robustness. No further repeat run or timeout change is proposed. P19 remains complete.

That production pre-commit-operator run has now occurred and failed as reviewed at the top.
Do NOT request a blind repeat. Resolve the remaining approved-scope gaps and verify the
retained corrections before another expensive live-Codex acceptance run.
The unchanged wrapper status is not a substitute for inspecting individual leaves.

### Assistant-owned elevate task: targeted delegated verification

The operator explicitly permits the Assistant to maintain/mutate the existing `elevate`
task in pyproject.toml as needed for its verification work. It is the Assistant's command;
there is no need for separate permission just to update that task within this test scope.
When required leaves cannot run here (e.g. browser/socket/privilege/host prerequisites),
prepare the concrete targeted checks in `elevate`, then ask the user to execute
`pixi run elevate` on the Assistant's behalf. State what it exercises and any prerequisites;
retain useful detailed output in logs/from_operator/elevate.log and meaningful nonzero
failure status. Read the returned log, fix approved-scope issues and secure upstream
regressions before recommending the complete operator acceptance run.

Do not silently leave feasible delegated verification outstanding merely because this
sandbox cannot execute it. Conversely, do not offload checks that the Assistant can run
itself or use elevate as a disguised repeat of the whole expensive live-Codex acceptance
workflow. Use the smallest meaningful batch of outstanding checks. User execution is
explicitly requested when needed; writing the task or asking for a run is not evidence it
ran/passed and does not grant the agent extra runtime permissions. Update elevate as needed during P18 and request delegated execution only when its checks
are concrete and ready.

### Completion criteria and boundaries

P18 is NOT complete merely because these notes were written or individual fixes landed.
Before another operator handoff, record each correction's relevant check/result and its
coverage boundary, plus the full command-graph leaf inventory and any elevate results, in WORK. Known locally detectable blockers within approved scope must be resolved; rejected task repairs remain explicitly documented, not claimed fixed; real
privilege/guest/platform/provider checks that cannot run here stay explicitly outstanding,
not reported as passed. Avoid unrelated/repeated broad testing after appropriate checks pass.
The operator remains responsible for final real-environment acceptance, not basic discovery.

Preserve all approved production contracts: no IPC DB creation/replay/append, no automatic
queue start, no raw detour DB writes outside Store, no recovery/tail repair/hash bypass/new
flags, no new Backend launcher knowledge, and no change to the final pull/outcome contour.
The isolated operator fixture may initialize only its own resources through existing Backend
lifecycle; never production data or direct fixture SQL/schema fabrication. Do not redesign
provisioning, security permissions or process supervision to conceal a launcher/test problem.
If the bounded correction requires changing a production contract or adding another mechanism,
pause and request explicit approval. P18 does not authorize running guest/network/operator
commands in this restricted environment. Keep sample_deploy, paused BDD and human-owned
TASK/HUMANS/README untouched; Git remains read-only.

## P19 — Implemented and locally verified: explicit, centralized Python-subprocess tests

2026-09-17: operator requested review of inline Python snippets launched from detour tests,
and authorized centralizing their shared mechanics through appropriate pytest fixtures/
markers, explicitly requested/applied by the affected tests. Implementation and local checks
are complete after P18 local corrections. Those earlier checks passed, but latest production
verification exposed the additional defects documented above. This does NOT authorize the rejected pre-commit wrapper edits in P18.

Implemented: PythonProcess run/popen fixture and explicit marker registrations
now live in the EXISTING protected/tests/pytest_plugin.py; the socketless NiceGUI harness is
centralized there behind its explicit fixture. Operator clarified that embedded Python bodies must go too, not just launch boilerplate.
All five existing bodies, the fixture cleanup children, and P18's watcher-import sentinel
have now become named ordinary Python functions in the same plugin. PythonProcess accepts
only a zero-argument callable, serializes that function's source centrally, and launches it
without importing the plugin/parent globals in the child (essential for deployed import
isolation). The task sentinel uses the same source serializer. No script-string bodies remain
in affected tests; setup/parent assertions remain module-aligned. Static checks and affected
regression evidence are recorded below; final marker collection selects102 subprocess cases, with the
4 socketless lifecycle cases separately selectable. The first regression run was stopped for this clarification, not passed. Operator briefly requested moving the plugin,
then explicitly withdrew that instruction: KEEP it in protected; no move was made.

### Findings: these are not subprocess escapes from socket restrictions

Pre-change review of active tests/shared plugin found these five inline-Python launch sites
(now migrated to named helpers and explicit fixtures):

| Test family / location | Actual reason for subprocess / coverage boundary |
|---|---|
| test_ui.test_startup_failure_exits_through_framework_shutdown | Fresh NiceGUI globals and actual process exit status. Centralized harness substitutes ONLY ui.run's socket-serving loop; real framework callback dispatch, shutdown signalling/hooks and application exit code execute. This is the socketless lifecycle substitute, not real serving coverage. |
| test_ui.start / TestBackendStartupConditions | Real CLI stdin/default-No confirmations, process lock, configuration and Store initialization in a fresh process. Stops before serving; no server/socket substitution. Only startup conditions/confirmation methods use this launcher; parser-only methods run in-process. |
| test_ui.TestBackendStartupConditions.test_operator_fixture_initializes_before_query | Actual isolated operator fixture initialization plus read-only query, in a fresh process/environment; no socket server or mocked Store. |
| test_audit_read.test_deployed_guest_imports_unchanged_shared_model_outside_repository | Fresh sys.modules/import path and cwd outside the repository prove deployed-layout dependencies resolve; unrelated to socket restrictions. |
| test_api.test_backend_singleton_lock_is_independent_of_replay_log | Concurrent real process holds flock while the parent checks contention/release; unrelated to sockets. Uses Popen rather than run. |

Real browser servers use python -m and actually bind sockets. Appendwatch launches the
real script; operator tests launch actual applications/external commands. Those are not the
inline-snippet pattern and must not be converted into socketless substitutes. A child process
has no greater socket permission than the parent; none of these subprocesses bypasses a
sandbox. The NiceGUI case avoids serving by explicitly substituting that boundary.

### Narrow implementation scope / chosen pytest mechanics

Use the EXISTING protected/tests/pytest_plugin.py as the one shared support location:
both tests/conftest.py and protected/tests/conftest.py already load it. Do not introduce a
second plugin or duplicate fixtures across these trees.

1. Add one explicit python_process fixture for the inline-Python execution mechanics.
   Its small test-only runner exposes run (CompletedProcess[str]) and popen (Popen[str])
   for the existing blocking and lock-holder cases. Centralize interpreter selection,
   callable-source serialization, python -c construction, text/captured I/O and bounded child
   cleanup here. Helpers are normal typed Python functions, checked by Ruff/mypy, not strings.
   Preserve each caller's explicit argv, stdin, cwd, environment and timeout. Do not inject
   repository PYTHONPATH into the deployed-layout test or hide errors/turn failures into skips.
   Preserve live lock-holder stdin/stdout coordination and always reap it, including on failed
   assertions. No shell=True, transport fallback or permission changes.
2. Register python_subprocess in the plugin's existing pytest_configure, and explicitly
   decorate each affected test (or only a wholly subprocess-based class). Marker registration
   belongs here, NOT in pyproject.toml. Tests request python_process directly or through an
   explicitly named scenario fixture; helpers receive it explicitly. No autouse subprocess
   substitution or source scanning to infer which tests to mark. Do not mark the startup class wholesale:
   its parser-only methods are not subprocess tests.
3. Move the reusable socketless NiceGUI driver out of the test's embedded harness into
   shared support, exposed by an explicit socketless_dashboard_lifecycle fixture using the
   common runner. Register/apply socketless_lifecycle ONLY to the framework-substitution
   tests, in addition to python_subprocess. Preserve its existing substitution boundary;
   never imply that this exercises Uvicorn/socket serving. Real startup initialization tests
   retain their real production boundaries and must not acquire this fixture/marker.
4. Replace the five inline-launch sites' duplicated process construction with the shared
   runner/fixtures. Move ALL embedded child bodies into named helpers in this shared plugin;
   keep parent-process assertions and fixture data next to their tests;
   preserve test names and module-aligned placement. The startup helper may still assemble
   its domain-specific arguments; it delegates process execution. Do not collect unrelated
   assertions into a giant scenario switch or create a new test framework.

Implemented usage (annotations abbreviated in these call-shape examples):

```python
@pytest.mark.python_subprocess
def test_deployed_guest_imports_unchanged_shared_model_outside_repository(
    tmp_path, python_process,
):
    # Existing isolated files, parent assertions and environment setup remain;
    # child assertions live in the named statically checked helper.
    result = python_process.run(
        deployed_guest_imports_process, cwd=tmp_path, env=environment, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "DEPLOYED_MODELS_OK" in result.stdout


@pytest.mark.python_subprocess
@pytest.mark.socketless_lifecycle
@pytest.mark.parametrize("publish", (False, True))
@pytest.mark.parametrize("failure", ("config", "storage"))
def test_startup_failure_exits_through_framework_shutdown(
    publish, failure, socketless_dashboard_lifecycle,
):
    result = socketless_dashboard_lifecycle(publish=publish, failure=failure)
    # Existing exit/shutdown/cleanup assertions remain here.
```

Selection becomes explicit without a new CLI flag or task edit:

```bash
pixi run -e detour-ai-augment env pytest <existing-test-paths> -m python_subprocess
pixi run -e detour-ai-augment env pytest <existing-test-paths> -m 'not python_subprocess'
pixi run -e detour-ai-augment env pytest <existing-test-paths> -m socketless_lifecycle
```

These are marker-selection examples, not permission to execute unrelated socket/operator/
provider tests. Retain other required marker exclusions and TASK restrictions. No change to
which tests run by default; markers make intentional inclusion/exclusion and collection
listing possible. No new blanket socket probing/skipping or real-server test redesign.

### Verification / boundaries

P19 evidence: Ruff src/tests passed; strict detour mypy passed all53 files after
named-helper migration. 11 focused subprocess cases passed (63.56s): framework shutdown4,
operator fixture bootstrap1, deployed import1, real process lock1, cleanup/timeout2 and
actual task-launcher sentinels2. The remaining feasible AI-augment suite passed: 320 passed,1 skipped,103 deselected
(193.38s), excluding subprocess/browser/real-provider/privileged/historical-capture cases.
The full91 startup/confirmation run finished: 90 passed,1 failed,105 deselected (717.18s).
Failure was missing_source-resume hitting its unchanged20s child-process timeout with
empty stdout/stderr, not a contract assertion. The identical case passed alone in7.65s without
changing code/timeouts. The initial full matrix was not wholly green; the cause of its one
timeout is not established. Socketless marker collection selects exactly4 cases;
parser-only startup checks remain unmarked. Full active-tree python_subprocess collection:
102 selected,410 deselected (512 total); no marker registration or test-task changes were
needed. No Python script = triple-quote / STARTUP
body remains in active tests; only the shared runner constructs python -c. Shell -c in
actual-task smoke tests is intentionally unchanged, not embedded Python.

At P19 completion, task-map comparison against its then-HEAD confirmed ordinary pre-commit
wrappers unchanged, with precisely the two approved interpreter substitutions plus elevate
different. The operator has since committed those changes; this is historical check evidence.
No sample_deploy/main CLI changes; git diff --check passed.


Use collection-only marker selections to demonstrate the exact marked set and ensure
in-process parser tests are not mislabeled. Run the affected existing subprocess regressions
through the common fixture, retaining real stdin, exit statuses, isolated imports, Store and
lock contention. Check timeout/failing-assertion cleanup where applicable, and Ruff/strict
mypy for touched modules. No new broad suite, live guest/operator/browser run or new fixture
that mocks the behavior under assertion. P18 verification may reuse these results.

Files: shared pytest_plugin.py, tests/control_centre/test_ui.py, test_audit_read.py,
tests/backend/test_api.py, protected/tests/backend/test_appendwatch.py (the new P18
watcher-import sentinel body), and WORK. Existing conftest imports need no change unless needed
for this wiring. Exclude sample_deploy, paused BDD, production code and all Pixi task edits.
Preserve the rest of P18 and its task boundary: two approved interpreter substitutions, no pre-commit wrapper changes; special verification in elevate only.

## Remaining rollout acceptance — separate from latest protocol/innerdict review

P20/P21/P22 are complete within their historical approved scopes. P24's revised scope
for outcome-triggered materialization/persisted IDs/HTTP-IPC ordering is implemented
and locally verified after operator restore; its explicit IPC-timeout docstring is included.
P23 shared HTTP-record protocol addition is COMPLETE and verified. These items do not fix
or authorizes the separate production-review corrections below. P1-P19's implementation/
evidence and production-acceptance limitations remain distinct.

P1-P19 and earlier follow-up code are present. The F8 IPC-only log/test regression is now
fixed and locally verified; pre-start diagnostic/verification gaps remain. F4's Chromium
real-query test passed earlier; normal PROD browser task instead fails on missing Chrome.
Remaining: explicitly agreed browser provisioning/selection, root runtime
access correction and actual monitoring, diagnosis of the silent pre-start wait, full HTTP
log/workflow/card acceptance. F5 binary prerequisite now PASS; four F7 activation checks
also pass on PROD (earlier pixi-shell report not reproduced). Proposed corrections at the
top are NOT newly authorized. Do not revive rejected workarounds or change ordinary tasks
without approval.
Do not call removed tests passing coverage or claim production acceptance has passed.
Earlier transient test failures remain qualified, not relabeled as first-run passes.

Actual guest/browser/provider/privileged execution and production config/log maintenance
remain operator-side boundaries. Latest delegated and local evidence is at the top; no
production-data cleanup occurred. The disclosed NiceGUI lookup mistake is also recorded
there; do not imply untouched storage was proven for that command.

## Mandatory constraints for continuation

- After compaction reread TASK and WORK IN FULL. Keep WORK current, remove stale pending claims.
- Only the current detour contract exists: no historical-schema special cases, shape-based
  migration or alternate parser. No special output-schema guard. This retry changes
  ONLY P24; no audit, DTO-default removal or card-format tightening is authorized.
- Operator forbids cast: proposed/implemented changes must use genuinely compatible types,
  not cast or substitute type suppressions. P24's needless runtime argument/cast is removed.
  This constraint does not authorize an unrelated codebase-wide refactor; P24 is narrowly approved.
- All commands via pixi run -e detour-ai-augment; Ruff/mypy/pytest via env. Git read-only.
- Task edits: prior interpreter substitutions, agent-owned elevate, and newly approved F7 fixes for proven environment-variable expansion defects only. Pre-commit structure/grep changes remain rejected.
- Never run/import src.repl, edit src/cli.py, import another detour or edit TASK/HUMANS.
- Only allowed production data is data/scisci_process.duckdb READ ONLY. No other data/,
  .aicode/ or historical captures. Isolated temporary test fixtures are permitted.
- No network/socket probes/escalation. Paused BDD permits only its completed model conversion.
- Preserve operator edits/staging, human-signed comments and narrowly approved boundaries.
- sample_deploy is excluded from edits, conversion inventories and test execution.
