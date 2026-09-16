> I copy and paste into here
> from chat if there is some bits
> I would like to persist, for a while.
> The text below may be AI-generated;
> this file is just called `HUMANS.md`
> because I maintain it vs. agents.
> signed off: Pavel

# food for thought - like we wrapped duckdb and replay log on backend, we could wrap hermetically nicegui  storage apps into a class, putting all adjacent logic in there, and in a different class wrap query   response. perhaps even put nicegui logic inside the query response class - to ensure all responses are   accepted and translate properly into storage updates. although this is not necessarily the best solution.  think

> context for this: prior there was some work
> related to refactoring backend from what 
> codex called "anemic/procedural" pattern 
> towards a more  beefy classes that own
> their procedures - codex analyzed the
> codebase and specifically said itself
> that the codebase lends itself to the 
> latter .
>
> so, i invited codex to also analyze
> ui.py from this perspective.
> it produced some response which 
> i don't capture because it wasn't
> very interesting, but then i followed up
> with this and the following bits are
> useful to shape the refactor.
>
> signed off: Pavel


• I think the analogy is strong, with one important separation:

- NiceGUI storage wrapper owns persistence.
- Query-response wrapper owns interpretation and indexing.
- The Backend’s QueryResponse itself should remain unaware of NiceGUI.

Putting NiceGUI access directly into QueryResponse would couple a Backend connector DTO to one UI framework
and make model operations side-effectful. It would also let Backend-facing code acquire a UI-storage
dependency.

## Suggested shape

### AiAugmentDashboardStorage

The sole class allowed to access app.storage.general.

It would own:

- storage keys;
- strict load/store of the query snapshot;
- strict load/store of the run journal;
- persisted queue membership;
- canonical serialization;
- translation of validation failures into granular dashboard-storage errors.

It does not need a context manager: NiceGUI owns the underlying resource lifetime. Hermeticity comes from
there being no direct app.storage.general access anywhere else.

### DashboardQuerySnapshot

A frozen Control Centre model wrapping one QueryResponse.

It would own:

- dashboard-specific consistency validation;
- unique outerdict/namekey indexing;
- attempts by namekey;
- run outcomes by namekey;
- committed innerdicts directly from each returned outerdict;
- ground truth directly from each returned outerdict;
- researcher/card lookup;
- canonical storage serialization and restoration.

It should construct everything locally and become valid only after the entire response translates
successfully. No mutation of pre-existing source outerdicts.

## One-door acceptance flow

IPC bytes
→ QueryResponse.from_serialized_json()
→ DashboardQuerySnapshot.from_query_response()
→ AiAugmentDashboardStorage.replace_query_snapshot()
→ controller swaps its current snapshot

Therefore, if parsing or dashboard-specific translation fails:

- no partial outerdict mutation occurs;
- NiceGUI storage remains unchanged;
- the controller’s current snapshot remains unchanged.

Restoration uses the same gate in reverse:

NiceGUI stored value
→ AiAugmentDashboardStorage.load_query_snapshot()
→ DashboardQuerySnapshot.from_stored_value()

The storage wrapper could expose this particularly useful operation:

def accept_query_response(
    self,
    response: QueryResponse,
) -> DashboardQuerySnapshot:
    snapshot = DashboardQuerySnapshot.from_query_response(response)
    self._general[QUERY_SNAPSHOT_STORAGE_KEY] = snapshot.serialize()
    return snapshot

The controller then assigns the returned snapshot only after successful storage.

## Why this is better

It mirrors the Backend refactor without conflating responsibilities:

- ReplayLogRegisteredResource owns replay-log persistence.
- AiAugmentDetourDB owns DuckDB access.
- AiAugmentDashboardStorage owns NiceGUI persistence.
- DashboardQuerySnapshot owns the meaning of persisted query data.
- QueryResponse remains the framework-independent Backend/Control Centre connector model.

The same storage wrapper can later work with RunJournal, but each model should validate its own data rather
than turning the storage class into another large procedural coordinator.

This would also provide a very clear final invariant: a literal search for app.storage.general in active
production code should find only AiAugmentDashboardStorage. No code changes made.

# sounds good and i think we should also remove any implicit /query requests including at startup. dashboard  should always only load from AiAugmentDashboardStorage and therefore will have no physical means of making  a query. at first startup just show an empty table. user will click the new "query ipc" button and the old  refresh button can be replaced with literal "poll backend" which updates both of backend statuses at once  and i think also "poll ai agent runtime" or something which will simply check codex auth status while  simultaneously checking health of lima connection and roundtrip, so ai agent runtime can also show two  statuses simultatneously - one for lima/ssh and other for codex proper. and then query ipc will always  return query resopnse which is wrapped into dashboardquerysnapshot and then it tries to supersede the  aiaugmentdashboardstorage and user should see a notification that this happened or failed, and server log  should show detailed info . thoughts?

> my immediate follow-up to the above, and
> codex's response is below
> signed off: Pavel


• I agree. This produces a much clearer command/query architecture.

## Proposed UI contract

### Startup and repaint

- Restore state only through AiAugmentDashboardStorage.
- If no DashboardQuerySnapshot is stored, show an empty table.
- Backend and AI Agent Runtime statuses initially show not probed.
- Page construction and the periodic UI repaint perform no HTTP, IPC, SSH, source-database, or Codex
operations.

- Probe results remain volatile; persisting them would present stale health information after restart.

### Probe Backend

Explicitly and concurrently checks:

- Backend API: /openapi.json
- Backend IPC: OPTIONS /query

It replaces one BackendProbeResult atomically and never calls /query or changes dashboard data.

### Probe AI Agent Runtime

Explicitly checks:

- AIVM/SSH: a byte-for-byte roundtrip through the exact production SSH/ProxyJump route.
- Codex: /home/ai/.local/bin/codex login status over that same SSH route.

The authentication command already exists in the operator preflight. If SSH fails, Codex should show not
checked, not unauthenticated. The existing is_busy() only checks for a running Codex process; it is not an
authentication probe. Run startup should retain its immediate busy check as a safety invariant.

### Query IPC

This should be the sole capability that can retrieve a full QueryResponse:

explicit click
→ IPC query
→ strict QueryResponse parsing
→ DashboardQuerySnapshot construction
→ AiAugmentDashboardStorage replacement
→ UI repaint from storage

The replacement is wholesale—never merged with existing data. Construction and validation complete before
storage mutation. On any failure:

- the previous stored snapshot remains unchanged;
- the current UI remains on that snapshot;
- the user sees a concise negative notification;
- the server log identifies the failed stage and includes the complete exception traceback.

On success, the user should see something concrete such as:

> Dashboard snapshot replaced: 307 researchers, 14 attempts, 3 run outcomes.

This action can retain the previously discussed hermetic behavior: use an existing IPC server when
appropriate, or start an owned IPC-only Backend, query once, and stop it in finally.

I would not disable Query IPC merely because a previous probe reported IPC unavailable—the probe may be
stale, and the action may be capable of starting IPC-only mode itself.

## Physical capability separation

The ordinary storage-backed controller should not receive a query client at all. Composition would provide
three narrow operations:

- ProbeBackend
- ProbeAiAgentRuntime
- QueryIpc

Only QueryIpc receives both the IPC query capability and AiAugmentDashboardStorage. That makes “no
accidental query” structural rather than conventional.

This removes the current implicit full /query calls from:

- Backend readiness;
- periodic refresh;
- researcher-card loading;
- post-run-outcome refresh.

Cards consequently render only from the stored snapshot.

## One material lifecycle issue

Current _finalize_run() calls /query by session ID to determine whether the exited Codex run produced an
accepted commit. Without that information, it cannot preserve the existing distinction between COMPLETED
and FAILED.

If only explicit Query IPC may access the full /query, I recommend a separate narrow Backend IPC operation
returning only something like:

SessionCompletion(
    session_id=...,
    accepted_commit_record_id=... | None,
)

The run controller would receive that narrow capability but never a QueryResponse. It would not hydrate or
mutate dashboard data.

If the requirement is stronger—no automatic projected-DB read of any kind—then run completion needs a new
Backend-to-controller result channel. That would be a larger lifecycle redesign.

So overall: yes to the proposal, with the narrow session-completion dependency treated as an explicit
connector decision. No code changed.

# for _finalize_run i think this should stop at codex exited. user will do their query ipc button whenever  they see fit and this will fill in missing info. so the dashboard's cycle will be from query to codex  exited and it's completely hermetic from backend response. would it though? pls go over the whole ui  lifecycle again (now we have helpful comments of yours there that mark lifecycle changes - use them) and  verify if that would work . also attempt reconciler and variable projector look confusing to me, don't you think? anyway we could get   rid of them? what's their purpose anyway? think as if our refactor we're devising was applied alreaday.  pls finish your current work you're doing and then think about this

> this is my next two followups
> put together as codex responded
> to both at once - below is.
> signed off: Pavel

• ## Lifecycle verdict

Yes, the normal Control Centre lifecycle can end at CODEX_EXITED, but simply removing _finalize_run() would
not work.

Current flow:

QUEUED
→ STARTED
→ REMOTE_PID_DISCOVERED (optional)
→ SESSION_DISCOVERED
→ ROLLOUT_DISCOVERED
→ CODEX_EXITED
→ PUSH_ACCEPTED (if found through implicit /query)
→ COMPLETED | FAILED | CANCELLED

The post-exit portion starts at 2026-01-02_enrich_full_df/src/detours/detour_ai_augment/src/control_centre/
dashboard/ui.py:2669. _finalize_run() queries Backend state and translates it into Dashboard lifecycle.

The proposed normal flow should be:

stored DashboardQuerySnapshot
→ QUEUED
→ STARTED
→ REMOTE_PID_DISCOVERED (optional)
→ SESSION_DISCOVERED
→ ROLLOUT_DISCOVERED
→ CODEX_EXITED
→ Backend shuts down and settles outstanding commits

Later, explicitly:
Query IPC
→ new DashboardQuerySnapshot
→ displayed Backend results update

### Required consequences

1. CODEX_EXITED must mean “no longer running.”

    Currently 2026-01-02_enrich_full_df/src/detours/detour_ai_augment/src/control_centre/dashboard/helpers/
    data_models/run_event.py:55 returns true for anything except QUEUED without a run_outcome. Therefore,
    merely removing finalization would leave the run:
    - displayed as RUNNING;
    - cancellable;
    - treated as abandoned on restart;
    - eventually changed to FAILED.

    CODEX_EXITED must instead be a locally finished Control Centre state, while run_outcome remains absent
    because that is Backend-derived information.

2. A later query must not mutate the Run journal.

    The Run should remain historically and truthfully at CODEX_EXITED. The newly queried snapshot supplies a
    separate displayed Backend result:
    - accepted attempt → completed Backend result;
    - rejected attempt → failed Backend result;
    - no attempt → “Codex exited; no Backend attempt in this snapshot.”

3. Matching must use Codex session_id.

    Without _finalize_run, accepted_commit_record_id is never written. The existing reconciler therefore
    cannot connect the exited run to the later Backend attempt. The durable shared identity is already
    session_id.

    One session may produce multiple commit attempts, so the relationship is:

    Dashboard Run (one session_id)
        └── zero or more Backend attempt records

4. The query must happen after owned Backend shutdown finishes.

    This is safe because Backend shutdown waits for authoritative commit tasks before closing the replay log
    and DuckDB, and the supervisor waits for process exit. Therefore, once cleanup has completed, an IPC-
    only query sees the settled projection.

5. One audit issue remains.

    _record_run_outcome() currently does more than classify the run: it captures final rollout/appendwatch
    evidence after Codex exits. Removing it outright can lose the final rollout tail—or all final evidence
    when Codex never pushed.

    To preserve the bulletproof immutable contour, I would separate that responsibility into a neutral
    durable Codex-exited evidence capture. Its acknowledgement would never determine or mutate Dashboard
    lifecycle. That is a replay/connector-format change requiring separate approval.

So the lifecycle can be hermetic from Backend outcome classification. It cannot literally consume no
Backend responses at all: Backend readiness and Codex pull/push still require responses. The current
readiness path also performs an implicit /query, which the proposed refactor must remove.

## _AttemptReconciler

Your impression is justified. It currently combines:

- response consistency validation;
- attempts ↔ committed-innerdict joining;
- run-outcome association;
- Backend attempt + local Run concatenation;
- duplicate suppression;
- ordering;
- current-lifecycle selection.

Most revealingly, 2026-01-02_enrich_full_df/src/detours/detour_ai_augment/src/control_centre/dashboard/
ui.py:531 requires either a Backend attempt or a Dashboard Run. It cannot represent their actual
association. Thus _AttemptReconciler mostly interleaves two histories and suppresses selected duplicates
rather than properly reconciling them.

It also contains a positional fallback for sessionless outcomes, which is inference rather than a strict
identity-based relationship.

The standalone class can be removed in the proposed architecture. Its essential responsibilities should
become:

- DashboardQuerySnapshot: validate the complete QueryResponse and build immutable indexes by namekey,
commit ID, and session ID.

- AiAugmentDashboardStorage: own the snapshot and run journal, and expose researcher state by joining them
strictly through session_id.

- No guessed sessionless associations.
- No mutation of Runs when a snapshot arrives.

## _VariableProjector

Its purpose is legitimate but the class is unnecessary. It is a stateless transformer that:

- chooses the selected AI field and ground-truth field;
- extracts footnotes;
- adds attempt/session metadata;
- computes the action;
- synthesizes a READY row;
- produces _ResearcherGridRow.

Because it owns no state, _VariableProjector is effectively a namespace around transformation functions.

It can be removed by giving the immutable view objects their own behavior:

AiAugmentDashboardStorage
    → DashboardResearcherState
        → DashboardAttemptState.project(variable, runtime_state)
        → DashboardResearcherState.project(variable, runtime_state)

NiceGUI widget construction should remain outside those objects. The resulting path becomes direct:

stored QueryResponse + Run journal
→ researcher/session state
→ selected-variable row
→ NiceGUI rendering

So, under the proposed refactor, both _AttemptReconciler and _VariableProjector can disappear as
coordinator/service classes. Their necessary behavior should move onto the objects that actually own and
represent the data. No product or test code was changed.


# well  detour_authoritative_projection should definitely be ditched. i just wonder how to best do this  considering we now have:  - config ai augment json that must contain a current full file hash of replay log and if it doesn't match  on backend start (or on dasbboard start), program exits. correct - does this logic work rigght now?  - backend store that supposedly (but does it in practice?? review) encapsulates and owns completely*  (does it??) _both_ the replay log and detour db. owning means here it sets readonly rights on them and  only makes them writable for the period of transaction . yes or no?  yeah, and we have the replay logic that should (does it??) basically be exactly the same in live and  replay contour - except that in live contour there is also (taken separately! right??) persisting of live  transactions into replay log (with their further projection into detour db) plus live http calls. right??  what am i missing?  so with this in mind, what should be our mechanism for ensuring both-ways equivalence between deotur db  and replay log? we don't want either to ever go stale.

• The intended architecture is reasonable, but the current implementation does not fully enforce it.

### 1. Startup hash verification: not consistently

- Standalone Backend: checks the full replay-log hash when Store opens it, unless --danger-no-verify-hash
is supplied. However, writable opening currently repairs an incomplete tail before checking the hash.

- Dashboard: currently does not check replay-log contents. Moving verification from model construction to
Store entry left this path uncovered.

- Dashboard-started Backend: the supervisor (src/detours/detour_ai_augment/src/control_centre/dashboard/
ui.py:1080) unconditionally supplies --danger-no-verify-hash. Its preceding check merely checks
configuration booleans—not whether verification happened.

So your mandatory startup rule is currently broken.

### 2. Store ownership and transaction-only writability: no

Production DB/log I/O is now concentrated in Store, but:

- DB stays 0600, with a writable connection, for the entire Backend lifetime.
- Log becomes 0400, but its writable descriptor remains open throughout that lifetime.
- Store’s execute() permits SQL outside an explicit transaction.
- Resource handles remain publicly accessible.

chmod does not revoke an already-open writable descriptor. Literal transaction-only writability requires
short-lived writable handles, not merely toggling permissions around a persistent writable connection.

### 3. Shared live/replay application: yes, for DB application

Both paths use the same application sequence:

durable log bytes
→ insert HTTP record into DB
→ validated DB readback
→ apply derived changes
→ commit DB transaction

Live HTTP capture happens separately, outside the DB transaction. Replay validation uses recorded HTTP
inputs without network.

There are still live-only effects: speculative validation and card-ZIP creation. Replay does not recreate
those files.

### What is missing

First: hash maintenance. Every legitimate append changes the full-file hash. Nothing currently updates the
configured hash. Therefore, enforcing your rule means subsequent startup fails until that hash is updated.
Whether this remains operator-maintained or becomes Store-maintained needs to be explicit.

Second: cross-file atomicity. Log fsync and DuckDB commit cannot be one atomic transaction with the current
storage arrangement. A crash can leave the log ahead. Updating a separate config file introduces another
such boundary.

The achievable guarantee is “never serve stale state,” not “these separate files are identical at every
instant.”

### Recommended mechanism, without the checkpoint table

1. Before serving: Store verifies the configured hash against untouched log bytes.
2. Verify correspondence: ordered detour_http_records must exactly match a contiguous log prefix—ordinals,
    UUIDs, payloads, and indexed metadata. Extra or conflicting DB records fail.

3. Catch up: apply the remaining suffix through the common applicator. Each HTTP row and its derived
    changes commit together.

4. During live operations: serialize append → fsync → apply → readback against queries. On failure, block
    reads until recovery succeeds; never return the old snapshot as current.

5. Enforce write windows: only Store’s application transaction gets writable DB access; only its append
    operation gets writable log access.

One qualification to my earlier recommendation: matching HTTP rows does not prove the derived tables are
correct. For rigorous whole-DB verification, replay into a fresh DB and compare logical contents—not DuckDB
file hashes. Replay also needs the same hash-validated rollout CAS and source/configuration inputs.

“Both ways” should mean verifying correspondence, never copying unexplained DB changes back into the
authoritative log.

# could you also pls go over our entire conversation and compare it to WORK - specifically we need all instances where i authorized/approved any change scope, and whether it's reflected in WORK. ideally if after your review you returned in this chat a table of all scope changes (just a short description of the approved scope) that happened in this session and the status: done, rejected, superseded, pending in WORK, pending but NOT in WORK

> closing loopholes one by one
> but still wanted this another check
> signed off: Pavel

**One omission found:** “replace all dataclasses” was completed in `ui.py`, but **19 production dataclasses and one test helper remain elsewhere**. WORK hadn’t disclosed that narrower implementation. It now records the discrepancy and remaining locations.

Repeated confirmations are grouped below. **Done** means implemented/reviewed—not production acceptance. Rejected and superseded proposals are not backlog.

| # | Scope change | Status |
|---|---|---|
| 1 | Additional `AiAugmentSourceContext` redesign | rejected |
| 2 | Shared-context protocol and Dashboard inheritance from Backend context | superseded |
| 3 | Repurpose Backend Store as Dashboard’s in-memory collection | superseded |
| 4 | Use `FrozenStrictModel` where justified; explicit `BaseModel` configs otherwise; pasted models untouched | done |
| 5 | Independent Dashboard; wholesale snapshots from NiceGUI storage; no partial/namekey queries | done |
| 6 | Remove stale `project_record` / `_project_readme_record` machinery | done |
| 7 | Remove attempt/validation data and restrict records to pull/push/commit/outcome | superseded |
| 8 | Keep attempts; add `/validate` containing validation, commit ID and full submission | done |
| 9 | Record provider HTTP exchanges, reference UUIDs, validate through submission mixin | done |
| 10 | Shared live/replay path: persist log → project DB → typed readback → downstream | done |
| 11 | Generic model HTTP interceptor, not institution-specific | done |
| 12 | Keep/restore domain and Codex evidence algorithms in `api.py` | done |
| 13 | Store owns detour DB/log and write windows; remove raw detour connections from callers | done |
| 14 | `HttpRequestLogRecord.from_response()` / `to_response()` | done |
| 15 | Remove `TYPE_CHECKING` import guards | done |
| 16 | Only writable/read-only Store modes | done |
| 17 | Detached `execute().fetchone()` / `fetchall()` interface | done |
| 18 | Remove `detour_authoritative_projection` | done |
| 19 | Remove tail repair; use registered-resource configured-hash verification | done |
| 20 | Separate validation from Backend ZIP publication/republication | superseded |
| 21 | Operator-maintained hash; Dashboard verifies and delegates hash bypass to children | done |
| 22 | Terminal `CODEX_EXITED`-only lifecycle / alternative completion endpoint | superseded |
| 23 | One post-exit `/pull`: 410 completed, otherwise failed—including 503—then outcome and shutdown | done |
| 24 | One cheap four-stage Probe button | done |
| 25 | Separate probe buttons/services | superseded |
| 26 | Storage/snapshot ownership; remove `_AttemptReconciler` and `_VariableProjector` | done |
| 27 | Convert `ui.py` dataclasses to Pydantic | done |
| 28 | Unqualified “all dataclasses” beyond `ui.py` | **pending but NOT in WORK*** |
| 29 | Intermediate `RunDisplayRow`, `SingularOuterDictWith*`, `AiTable1ColsPerVariable`, `KeyValueGroundTruth`, `_Var` names | superseded |
| 30 | Final Researcher/RunCommit view names; `_Researcher` alias; `_ResearcherVar`, docstring, `varname`, lookup naming | done |
| 31 | Rollback must not consume Codex DB row IDs | done |
| 32 | Full Backend `--new` versus `--resume`/`--continue`; default-No confirmations; `--yes` | done |
| 33 | Shared full/IPC first-child initialization policy, rearmed after failure | superseded |
| 34 | Controller receives no query client; separate Query IPC closure in `create_services` | done |
| 35 | Typed `QueryRequest` and `send_query_request()` instead of client `pull()` | done |
| 36 | Startup-failure, WORK/HUMANS/handoff and restoration-behavior reviews | done |
| 37 | Dashboard startup failure actually shuts down the process with unsuccessful exit | pending in WORK |
| 38 | Actual append-descriptor startup preflight, only when appends are authorized | pending in WORK |
| 39 | Trust saved prefix without independently hashing it | superseded |
| 40 | DuckDB table-comment anchor; raw-line hashes; prefix/suffix verification; safe anchor promotion | pending in WORK |
| 41 | Require an empty replay log for every `--new` | superseded |
| 42 | Empty baseline plus optional nonempty-log replay during `--new`; second default-No prompt; `--yes` accepts both | pending in WORK |
| 43 | No resume recovery, failure-triggered reset or historical validation-verdict substitution | pending in WORK |
| 44 | Remove all Backend card/ZIP publication and republishing | pending in WORK |
| 45 | Dashboard `publish completed` command reusing DOCX download logic | pending in WORK |
| 46 | Start/Stop dequeue button; stopped at startup; active run unaffected; cancellation separate | pending in WORK |
| 47 | Empty `QueryRequestProperty`; keep `outbound_http` concrete-only | pending in WORK |
| 48 | Restore literal `DASHBOARD_QUERY_PATH = "/query"` | done |
| 49 | IPC signal handler: replace Event with approved boolean/polling shape | pending in WORK |
| 50 | Remove Backend parent watcher and Dashboard PID injection | pending in WORK |
| 51 | IPC-only ignores initialization flags | pending in WORK |
| 52 | IPC-only directly opens Store read-only, bypassing initialization | pending in WORK |
| 53 | Exclude IPC children from Dashboard first-full-start bookkeeping | pending in WORK |
| 54 | Guardian/ownership registry for orphan cleanup; instead surviving Backend is external | rejected |
| 55 | Move unchanged clean-close token to protected Backend vars | pending in WORK |
| 56 | Preserve exact approved snippets, clean stale WORK, explicitly document TABLE COMMENT | done |

\* **Missing before this audit; now recorded.** The wording was “all,” although the surrounding discussion concerned UI models; WORK now preserves that distinction rather than claiming complete conversion.

Only WORK changed. All 16 pinned snippets and four exact numbered headings were preserved. No implementation tests were rerun.
