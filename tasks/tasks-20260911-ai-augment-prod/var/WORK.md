# AI augment production preparation

## Status / current authorization

2026-09-16 HANDOFF: TASK and this WORK are the complete task context. No chat transcript,
historical workbook or HUMANS excerpts are needed to recover the approved pending scope.
The next implementor should implement the pending changes below, narrowly, preserving the
retained contracts and exact approved code shapes. This handoff-preparation turn changed
WORK only; it did NOT implement those changes or rerun the application suite.

Existing operator edits/staging must be preserved. Prior green checks cover earlier code,
not pending work or later operator edits. Production/operator acceptance is still outstanding.
Unless explicitly repository-root-relative, paths below are relative to
src/detours/detour_ai_augment. Read TASK, this entire WORK, and the authoritative detour
README before implementation. Keep WORK current as items are actually completed.

## Pending implementation index / execution boundary

All rows below are pending; the detailed sections supply the binding behavior and snippets.
This is an index, not additional scope. Ordinary local implementation choices needed to meet
these requirements do not require renewed approval. Do not restore superseded designs.

| ID | Approved work | Main edit points |
|---|---|---|
| P1 | Strict log/DB correspondence: table-comment anchor, exact raw-line hashes, independent prefix/suffix verification, read-only verification and safe promotion | Store + replay-log/detour-DB resource models |
| P2 | Full --new empty baseline and optional nonempty replay; second default-No prompt; --yes accepts both; strict resume never heals | server.py + Store common applicator |
| P3 | Actual no-write append-open preflight for writable startup only | ReplayLogRegisteredResource + Store startup |
| P4 | Remove historical validation-verdict substitution and all failure-triggered automatic --new resets | api._apply_validation_record + Dashboard context/supervisor |
| P5 | Four exact lifecycle changes: no parent watcher; IPC ignores modes; direct read-only IPC; IPC excluded from first-full-start policy | api.py, server.py, ui.py, Dashboard context; launcher help |
| P6 | Non-locking IPC signal flag and unchanged clean-close token moved to protected Backend vars | protected/src/backend/ipc.py, vars.py, server.py, ui.py |
| P7 | Parameterless QueryRequestProperty without outbound_http requirement; retain concrete helper and literal /query route | protected/src/architecture.py |
| P8 | Queue Start/Stop switch, initially stopped; stop only gates dequeue; preserve real cancellation | Dashboard controller/page |
| P9 | Remove ALL Backend card/ZIP publication; add explicit Dashboard publish completed using the same DOCX rendering as its button | Store, api.py, Dashboard card/page/application lifecycle |
| P10 | Real Dashboard startup-failure shutdown and unsuccessful exit, including publish mode | Dashboard application lifecycle |
| P11 | Remaining detour-wide dataclass conversions and necessary constructor/copy/dependency integration | Complete class inventory and exceptions in Dataclasses section |

Recommended order: P1-P5 together with hash-delegation checks; P6-P7; P8-P10 together;
then P11. This ordering is not a new architecture or permission gate. Verification belongs
with each change. Existing tests that expect superseded behavior must be adapted, not used
to justify reintroducing it. Do not claim all pending work complete while a listed integration
requirement is unfinished; explicitly distinguish code completion from operator rollout.

### Source navigation

- src/backend/server.py composes full and IPC-only lifetimes; src/backend/api.py keeps domain
  algorithms. src/backend/helpers/data_models/ai_augment_backend_store.py owns detour I/O,
  transactions, common record application and DB readback.
- protected/src/backend/helpers/data_models/{replay_log,ai_augment_detour_db,ai_augment_config}.py
  are the resource/config seams; src/backend/helpers/data_models/ai_augment_context.py loads
  source researchers from the MAIN pipeline DB READ ONLY. Do not move domain logic to Store.
- protected/src/backend/ipc.py implements IPC; protected/src/backend/helpers/{vars,locale}.py
  hold Backend constants/messages; protected/src/architecture.py declares QueryRequestProperty.
- src/control_centre/dashboard/ui.py owns UI/composition/supervisor/queue. Its
  helpers/data_models/{ai_augment_context,ai_augment_dashboard_storage,dashboard_query_snapshot,query_request}.py
  hold the private initialization policy, NiceGUI persistence, snapshot and request model.
- Repository-root pyproject.toml, [tool.pixi.feature.detour-ai-augment.tasks].serve, is the
  shell launcher whose usage text needs updating; do not rewrite its argument forwarding.
- Dataclass deployment seams: protected/src/agent_runtime/{deploy,provision}.sh and
  protected/src/llm_inference_api/sample_deploy/{run,usage}.sh. Conversion requires that the
  actual standalone interpreter can import its dependencies, not just the host Pixi Python.

## Approved Backend agnosticism / query-only IPC scope — pending implementation

The detour README was read IN FULL during the lifecycle review. Its Lifecycle corollary
makes Backend agnostic to who starts it; the existing parent watcher violates that boundary.
The operator now explicitly accepts that after Dashboard SIGKILL a surviving Backend
continues running and is treated by a restarted Dashboard as external, detected through
the existing explicit Probe / Query IPC flows (not a new automatic startup probe).
Query IPC may borrow it; Dashboard must not adopt it as owned or stop it afterward.
This latest instruction supersedes the earlier proposed owned-Backend restart cleanup:
NO guardian, parent-death hook, durable ownership DTO/storage slot, or orphan PID-targeting
mechanism is pending. Existing normal owned-process shutdown remains unchanged.

The following four headings and code snippets reproduce the operator-approved proposal
verbatim. The code shapes are pinned, not merely summarized; implementation is pending.

## 1. Remove Backend’s knowledge of its launcher

- api.py: delete _watch_control_parent, parent_watch setup/cancellation, the parent-PID
  environment constant/poll interval and now-unused signal/suppress imports. Preserve
  workflow initialization, preflights, stdin session input and authoritative-task settlement.
- ui.py stops injecting/importing that parent-PID constant; remove its dead Backend locale
  message. Ordinary SIGTERM/SIGINT shutdown remains independent of launcher identity.

Approved api.py lifespan snippet:

```python
# After existing workflow initialization, preflights and stdin reader:
try:
    yield
finally:
    if AUTHORITATIVE_BACKGROUND_TASKS:
        results = await asyncio.gather(
            *tuple(AUTHORITATIVE_BACKGROUND_TASKS),
            return_exceptions=True,
        )
        failures = [
            result for result in results
            if isinstance(result, BaseException)
        ]
        if failures:
            raise BaseExceptionGroup("Backend background work failed", failures)
```

Approved ui.py environment deletion:

```diff
- environment[CONTROL_PARENT_PID_ENV_NAME] = str(os.getpid())
```

## 2. Make initialization flags irrelevant to IPC-only

- server.parse_args: parse --new and --resume/--continue as independent booleans, then
  require exactly one ONLY for full mode. In IPC-only normalize both to False; supplied
  mode flags, including conflicting ones, are ignored. --config remains required.
- This supersedes all earlier first-IPC-child --new/rebuild rules. IPC-only serves only
  wholesale query and cheap OPTIONS, with existing DB/log read-only; no reset/replay
  prompts, DB creation, rebuild, catch-up, append or integrity-anchor promotion.

Approved server.py argument-parsing snippet:

```python
parser.add_argument("--new", action="store_true")
parser.add_argument("--resume", "--continue", action="store_true")
parser.add_argument("--yes", action="store_true")

args = parser.parse_args(argv)

if args.ipc_only:
    # Initialization flags have no effect in query-only mode.
    args.new = False
    args.resume = False
elif args.new == args.resume:
    parser.error(
        "Full Backend requires exactly one of --new or --resume/--continue"
    )

return args
```

## 3. Physically bypass initialization in IPC-only

- server.main uses `confirmed = False if args.ipc_only else confirm_startup(args)`;
  full-mode refusal still precedes resource opening. Keep common process lock/config/runtime
  construction. IPC-only directly enters runtime.pipeline_config.backend_store.read_only(),
  calls ipc.serve_dashboard_query_only(runtime), and prints the clean-close acknowledgement
  only after successful context exit. Existing finally releases the process lock.
- Full mode continues through full_backend_application. backend_store_lifecycle becomes
  full-only: remove read_only parameter/branch and always use Store.writable(runtime);
  retain explicit new/rebuild, confirmations and existing lock/ack behavior. The previously
  approved second replay confirmation remains part of pending full-mode initialization.
- Missing/invalid DB fails without initialization. Config/resource validation and Store
  read-only consistency checks remain. No new service/context/lifecycle abstraction.

Approved main() snippet:

```python
args = parse_args(argv)
confirmed = False if args.ipc_only else confirm_startup(args)

api._acquire_backend_process_lock()
try:
    runtime = configure_runtime(
        args.config,
        require_namekey=not args.ipc_only,
        verify_hash_on_init=not args.danger_no_verify_hash,
    )

    if args.ipc_only:
        with runtime.pipeline_config.backend_store.read_only():
            ipc.serve_dashboard_query_only(runtime)
        print(BACKEND_STORE_CLOSED_CLEANLY, flush=True)
    else:
        uvicorn.run(
            full_backend_application(
                runtime,
                new=args.new,
                confirmed=confirmed,
            ),
            host=api.SERVER_HOST,
            port=api.SERVER_PORT,
        )
finally:
    api._release_backend_process_lock()
```

Approved full-only backend_store_lifecycle snippet (existing confirmation, lock and
acknowledgement handling retained; read_only parameter/branch removed):

```python
if new:
    store.rebuild_from_log(runtime, reset_confirmed=confirmed)

with store.writable(runtime):
    yield store
```

## 4. Exclude IPC-only from Dashboard initialization bookkeeping

- _BackendSupervisor._start uses `() if ipc_only else self._context.begin_backend_start()`
  for initialization arguments. Existing --ipc-only/config/hash-delegation remain.
- _stop calls finish_backend_stop only when `not handle.ipc_only`. Thus query-child success
  or failure cannot consume/rearm the first-full-start policy, and uses the ordinary
  non-rebuild readiness timeout. Earlier approved no-failure-rebuild correction still
  applies to the full-child policy; no additional context redesign.
- Amend launcher usage text, not forwarding. Focused checks: IPC-only with no mode/each
  ignored mode/conflicting ignored modes never confirms/rebuilds/appends; missing DB fails
  without creation; full flags/confirmation stay mandatory; query child cannot mutate the
  initialization policy; acknowledgement follows successful cleanup; API lifespan no longer
  observes launcher PID and still settles authoritative work. External borrowing unchanged.

The policy is instance-private on AiAugmentControlCentreContext, not class/global or
persisted NiceGUI state. Its first owned FULL Backend starts with --new --yes; after that
full start AND clean stop succeed, later full starts use --resume --yes. All owned full
starts, including Codex launch, use the same policy. A failed cycle must never automatically
retry/reset through --new, including an unsuccessful first cycle: fail closed for operator
intervention rather than leaving a destructive retry armed. IPC starts/stops do not mutate
this policy; external borrowing never does. Missing/legacy DB makes Query IPC fail: do not
bootstrap it through an IPC child. Only an explicit full --new path can initialize it.

Approved _BackendSupervisor._start snippet:

```python
arguments = (
    () if ipc_only
    else self._context.begin_backend_start()
)
```

Approved _stop snippet:

```python
if not handle.ipc_only:
    self._context.finish_backend_stop(
        startup_succeeded=handle.startup_succeeded,
        shutdown_succeeded=shutdown_succeeded,
    )
```

## Approved narrow addition — IPC-only signal flag, pending implementation

In serve_dashboard_query_only, replace only its local stop Event/set/wait with this exact
shape. Retain SIGTERM/SIGINT registration, the existing finally server cleanup and previous
signal-handler restoration unchanged. No broader IPC/server lifecycle redesign.

```python
stopped = False

def request_stop(_signum: int, _frame: FrameType | None) -> None:
    nonlocal stopped
    stopped = True

# After installing handlers:
while not stopped:
    if not server.thread.is_alive():
        raise RuntimeError("Backend query server stopped unexpectedly")
    time.sleep(0.1)
```

The handler no longer acquires a threading.Event lock. Keep threading imports/usages
needed elsewhere. Adapt the directly affected signal tests to this polling shape;
verify both signals, unexpected worker death, cleanup and handler restoration without
server/network activity. Approved, not yet implemented.

## Approved narrow addition — clean-close constant move, pending implementation

Move the existing definition from src/backend/server.py to
protected/src/backend/helpers/vars.py (paths relative to the detour root), unchanged:

```python
BACKEND_STORE_CLOSED_CLEANLY = "AI_AUGMENT_BACKEND_STORE_CLOSED_CLEANLY"
```

Both server.py and Dashboard ui.py import it from that vars module:

```python
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    BACKEND_STORE_CLOSED_CLEANLY,
)
```

Remove only the old definition and Dashboard's old import of this constant from server.py;
retain unrelated imports. This is a machine-readable protocol token, so it does not go
in locale. No rename/value change, emission/parsing change, shutdown-policy change, or
broader constant relocation. Adjust only directly affected import references if needed.
Approved, not yet implemented; the existing approved lifecycle snippets remain unchanged.

## Approved narrow addition — QueryRequestProperty, pending implementation

Remove only the outbound_http requirement from QueryRequestProperty, leaving an empty
documented parameterless request contract. Retain outbound_http on concrete QueryRequest
as an implementation helper. Keep typed send_query_request(QueryRequest()) and existing
HTTP-boundary rejection of query parameters/request bodies. No model/client/transport
redesign or call-site change is authorized by this addition. Not yet implemented.

Exact approved protocol shape:

```python
class QueryRequestProperty(
    ComponentProtocol.PortProtocol.PropertyProtocol,
    Protocol,
):
    """Request the complete Backend snapshot; no parameters."""
```

The operator's separate restoration of `DASHBOARD_QUERY_PATH = "/query"` is already
present in protected/src/backend/ipc.py; retain it. It is not a pending implementation item.

## Approved narrow additions — queue control and publishing, pending implementation

- One Dashboard Start queue processing / Stop queue processing toggle.
  Processing always starts STOPPED on each Dashboard process startup; persisted queued
  runs are restored but not consumed until Start. This controller-wide runtime setting is
  not persisted; browser refresh reflects its current value rather than resetting it.
  Stop changes only permission to dequeue: the current _process_queued_run, including its
  run-outcome and Backend cleanup, continues normally. No cancellation, queue clearing,
  status rewrite, Backend stop or Query IPC triggered by the toggle. Enqueue/rerun while
  stopped still persist normally. Start wakes the existing single worker, never adds one.
  Cancel remains a separate action: actually terminate the current run, retain its normal
  cancellation/outcome/cleanup lifecycle, and leave it off the queue (never re-enqueue it).
  Cancellation does not change the queue-processing switch: if enabled, another run may
  dequeue after cleanup; if stopped, queued runs remain held. Preserve existing queued-run
  cancellation/removal as well; the new toggle must not weaken or replace cancellation.
  Gate the actual nonblocking dequeue with no await between the enabled check and dequeue;
  a wakeup event for enqueues/Start avoids the race from awaiting queue.get after a flag
  check (Stop while that get waits must not let a later enqueue slip through).
  Add the button/current-state refresh, concise operator logs, and focused startup/active-
  run/empty-queue-stop/restart tests. This supersedes automatic queue continuation, but
  does not by itself change the separate interrupted-run startup cleanup behavior.
- Remove Backend card/archive publication entirely: Store startup, explicit rebuild,
  existing-validation and first /validate application calls; _publish_stored_cards,
  api.publish_card_zip, _same_zip_contents and publication-only imports/constants/checks.
  Keep DB validation/materialization, HTTP records, CAS/evidence, card-rendering helpers
  needed by Dashboard, and shared main-pipeline card utilities. No deletion of old files
  or change to persisted validation-stage values solely for naming cleanup.
- Add `python -m src.detours.detour_ai_augment.src.control_centre.dashboard.ui publish completed --config config_ai_augment.json`;
  existing dashboard invocation unchanged.
  Start the normal NiceGUI server/config/storage/services lifecycle, publish once, request
  normal app.shutdown(), await existing shutdown hooks, and return a nonzero exit on failure.
- Reuse existing stored DashboardQuerySnapshot plus run journal and displayed lifecycle;
  no implicit Query IPC/Backend launch/source DB load. Select only non-INELIGIBLE researchers
  whose CURRENT displayed lifecycle is COMPLETED and whose card download is available.
  Do not substitute any historical accepted commit for the current displayed status.
- Extract the current button's DOCX byte rendering/filename and markdown-availability
  predicate onto the existing _ResearcherCardView; button and batch call that same code.
  Browser sink remains ui.download; CLI sink is pipeline_config.output_dir / same filename.
  No ZIP output, browser automation, fabricated UI client, second renderer or exporter service.
  Use the existing configured output_dir; explicit reruns overwrite matching filenames.
- Publishing must NOT resume queued Codex runs or perform abandoned-run cleanup/status
  mutations on startup/shutdown. Existing start() currently does both. Narrow mode gating
  must preserve storage loading and normal cleanup without activating run orchestration.
  The approved always-stopped queue toggle removes the need for a publish-specific queue
  enable flag; interrupted-run startup/shutdown mutation still needs separate handling
  for publishing. No new background refresh/probing.
- Log startup/config/storage readiness, total researchers, eligible+completed candidates,
  download availability among them, per-file name/progress/path, final count and shutdown.
  Stop/log/exit nonzero on first rendering/write error; already written files remain.
  Zero selected researchers is an explicit logged no-op, not a reason to query or recover.
- Focused future checks: no Backend archive writes in live/replay/start/repeated validation;
  unchanged DB validation outputs; batch/button share renderer and naming; exact eligibility/
  current-status/availability filtering; no queue/journal/IPC side effects from publishing;
  cancellation really terminates/removes the current run without changing the dequeue
  switch; normal shutdown and failing exit status. No production server/browser/provider
  run in this environment.

### Exact approved publishing snippets

Store application ends after the existing transaction; no first publication or recovery:

```diff
-        # Publication is outside the committed DB transaction in both live and replay.
-        # Failure leaves the durable validation intact for recovery, never a new verdict.
-        if (record.method, record.path) == (api.HTTP_POST_METHOD, VALIDATE_PATH):
-            api.publish_card_zip(self, cast(AiAugmentBackendContext, runtime), record.record_id)
         return applied
```

Shared card view and the existing button's rendering/download calls:

```python
class _ResearcherCardView(FrozenStrictModel):
    researcher: _Researcher
    card_markdown: str

    @property
    def download_available(self) -> bool:
        return bool(self.card_markdown)

    @property
    def docx_filename(self) -> str:
        return card_filename(
            draw_label=self.researcher.draw_number,
            first_name=self.researcher.namekey.first_name,
            last_name=self.researcher.namekey.last_name,
        ) + ".docx"

    def render_docx(self, reference_docx: Path) -> bytes:
        return render_docx_bytes(self.card_markdown, reference_docx)
```

```python
docx = await asyncio.to_thread(card.render_docx, self._reference_docx)
ui.download(docx, filename=card.docx_filename, media_type=DOCX_MEDIA_TYPE)
```

Retain the button's existing disable/error-handling wrapper; its availability and the
batch use the same download_available predicate. Only the output destination differs.

```python
async def publish_completed(services: _ApplicationServices) -> None:
    controller = services.controller
    config = services.configuration.pipeline_config

    # Existing unfiltered Dashboard view; no query or new classification logic.
    dashboard = await controller.snapshot(
        selection=_UiSelection(
            researcher_varname=RESEARCHER_VARS[0].varname,
        ),
    )
    candidates = [
        row for row in dashboard.researcher_var_views
        if row.researcher.ai_augment_cohort is not AiAugmentCohort.INELIGIBLE
        and row.latest_run_commit_var_view.lifecycle is RunLifecycle.COMPLETED
    ]

    cards = []
    for row in candidates:
        card = await controller.researcher_card(namekey=row.researcher.namekey)
        if card.download_available:
            cards.append(card)

    logger.info(
        "Publish completed: %d researchers; %d eligible and completed; "
        "%d DOCX downloads available",
        dashboard.counts.total, len(candidates), len(cards),
    )

    if cards:
        config.output_dir.mkdir(parents=True, exist_ok=True)

    for index, card in enumerate(cards, start=1):
        destination = config.output_dir / card.docx_filename
        logger.info("[%d/%d] Rendering %s", index, len(cards), destination)
        docx = await asyncio.to_thread(
            card.render_docx, config.pandoc_reference_docx,
        )
        await asyncio.to_thread(destination.write_bytes, docx)
        logger.info("[%d/%d] Written %s", index, len(cards), destination)

    logger.info("Publishing finished: %d DOCX files", len(cards))
```

The one-shot operation runs after server/services startup; normal shutdown hooks still run:

```python
async def publish_completed_and_shutdown() -> None:
    global APPLICATION_EXIT_CODE

    try:
        await publish_completed(require_services())
    except Exception:
        APPLICATION_EXIT_CODE = 1
        logger.exception("Publishing completed researchers failed")
    finally:
        app.shutdown()  # Existing shutdown hooks still run.
```

After ui.run() returns, main() returns that exit status. Startup failures likewise request
shutdown and exit unsuccessfully. Queue processing stays stopped by default in ALL modes;
only publishing skips interrupted-run startup/shutdown mutation, as approved above.

## Approved narrow change scope — pending implementation

### Strict startup verification and Store ownership

- Backend Store remains the exclusive owner of replay-log and detour-DB I/O/transactions.
  Main pipeline DB remains read-only. API keeps its domain/evidence algorithms.
- Persist an accepted-prefix anchor as JSON in a DuckDB table COMMENT on the EXISTING
  detour_http_records table:
  accepted config SHA256, covered record ordinal, byte offset. No new checkpoint table.
  A typed/FrozenStrictModel representation is appropriate; no new runtime/context hierarchy.
- Save SHA256 of each EXACT durable replay-log line, including LF, with its HTTP row in
  the same projection transaction. Hash durable bytes, not reserialized model JSON.
- On --resume/--continue, independently hash the saved prefix and compare against its
  anchor; compare each following raw line with the same-ordinal DB hash. Require exact
  ordered coverage through EOF: no missing/extra records, gaps, truncated prefix or
  invalid byte/line boundary. These invariants also matter when config/anchor hashes match.
- Only after complete verification may a newly verified config hash and current boundary
  replace the anchor transactionally. Never adopt a hash at an unrelated/newer EOF.
  Config whole-file verification remains RegisteredResource's responsibility; operator
  maintains the config hash. Additional prefix verification is now explicitly approved.
- Read-only IPC startup checks consistency but cannot promote/mutate the anchor. New-log
  bootstrap and anchor promotion belong only to an explicitly writable full-Backend path.
- An existing DB without the required anchor/raw-line-hash schema also fails resume/IPC
  verification; do not silently migrate, synthesize a baseline from current EOF, or fall
  back to MAX(record_ordinal). Explicit full --new is the reconstruction contour.
- Resume NEVER catches up, inserts missing historical rows, repairs/truncates a log,
  invents provider inputs, silently recreates DB state, or falls back to new on mismatch.
  Fail early. Human-directed removal/reset plus explicit --new is the only rebuild path.
- Before an append-authorized Backend reports ready, Store must actually open an append
  descriptor using the real append-opening mechanics, close it without writing, and
  restore0400. Temporary owner-write, O_WRONLY|O_APPEND, no O_CREAT/O_TRUNC, no-follow and
  same-inode checks. No os.access-only preflight. IPC-only requires no append capability.

Metadata pointer (pending facility, NOT current application code): write with
`COMMENT ON TABLE detour_http_records IS '<serialized anchor JSON>'`; read the `comment`
column of `duckdb_tables()` for that table/schema, only inside Backend Store. There is no
such access in the current detour implementation. Its current startup is
src/backend/helpers/data_models/ai_augment_backend_store.py::_restore_append_position,
which reads MAX(record_ordinal) and current log EOF instead. Existing repository examples
in src/helpers/openalex.py (parquet_kv_metadata reads around284/306, KV_METADATA write
around400) and src/helpers/resources.py (around133/172) concern PARQUET-file metadata,
not this DuckDB table-comment anchor. These two helper paths are repository-root-relative.

### Normal full-Backend --new behavior, with default-No confirmations

- For full Backend only, keep required --new vs --resume/--continue; --continue is an alias.
  No extra replay or non-interactive flag. Start/reset confirmation defaults No, including resume.
- --yes means yes to ALL confirmations. This includes Dashboard's first full --new --yes child,
  never an IPC-only query child (latest correction above).
- Normal fresh initialization uses an existing empty log with its standard hardcoded
  SHA256(empty); new DB metadata starts at empty hash, ordinal0, byte offset0.
- If registration instead verifies an existing NONEMPTY log and its nonempty config hash,
  normal --new asks a SECOND default-No question: replay this log before starting?
  Refusal aborts BEFORE destructive DB reset. --yes accepts this question too.
- This permission exists only during that --new initialization, not in persistent metadata
  or an independently selectable flag. Seed the same empty DB/empty-prefix anchor, then
  apply lines from1 via the SAME common projection used after a live durable append.
  Never append those lines to the log again; never issue live provider requests in replay.
- Stop at the first framing/schema/linkage/domain/dependency failure, identify its line,
  do not publish readiness/start appending/promote the anchor. Do not skip/fix records.
- Only full successful application establishes the registered hash + EOF ordinal/offset
  as the authoritative baseline for later strict resume. Empty anchor means empty
  projected prefix; it does not lie about the nonempty file's registered hash.
- Startup logs expose old/new hashes and boundaries, verification/replay totals, current
  line/progress, the first mismatch/failure, and final accepted hash.

### No alternative restoration contour

- Preserve intentional first-owned FULL Backend --new --yes and explicit bootstrap.
  Never turn a failed start/stop/resume into another unattended --new reset. IPC-only
  cannot consume or rearm initialization policy. Borrowed/external Backend is untouched.
- Remove the historical INNERDICT_AND_CARD verdict-substitution exception in
  api._apply_validation_record: re-evaluation disagreement must fail, not replace an
  accepted result with an old recorded failure. Preserve the persisted record schema.
- Remove ALL Backend card/archive publication per the explicit publishing scope above,
  not just startup/repeated-result recovery. No config auto-repin or resume catch-up.
- Preserve transaction rollback, descriptor/permission cleanup, ordinary submission
  correction retries, live provider capture-before-use and evidence/CAS checks. These
  are not data restoration. Do not extend scope to other components' caches/watchers.

## Dashboard startup fail-fast — pending implementation

On configuration/resource/hash or persisted-storage failure during startup, Dashboard must
log the failure, request normal shutdown/cleanup and exit unsuccessfully. Merely raising
inside NiceGUI's background startup handler is insufficient. Preserve the existing approved
startup/query separation. Verify the actual framework lifecycle and process exit, not only
an exception from a directly awaited coroutine. This requirement also applies to publishing.

## Integration constraint — operator hashes and Dashboard child lifetimes

Dashboard verifies the configured replay-log hash once, then deliberately launches children
with --danger-no-verify-hash. A live child can append; later children reread the SAME config
without an operator repin during that Dashboard lifetime. Never store that old hash at a
newer EOF. Keep its verified prefix boundary and verify following raw lines against DB rows;
promote only an actually verified new whole-file hash, in a writable full-Backend transaction.
IPC-only never promotes the anchor. A changed config on disk is not verified merely because
the parent's old verify_hash_on_init booleans are true. Preserve hash delegation and operator
repins; no silent config rewriting or recovery bypass. Resolve this within the approved
startup wiring, not by adding another runtime/context hierarchy.

## Current implementation audit — findings to correct, not target behavior

Reviewed source on 2026-09-16. Pending target behavior is specified ABOVE. These observations
explain the remaining edits; none grants permission to retain the conflicting behavior.

- server.py currently requires/acts on initialization modes for BOTH full and IPC-only.
  backend_store_lifecycle can rebuild even for IPC-only. api.lifespan still creates the
  Dashboard-parent watcher; ui.py still supplies its PID. These are the four-section edits.
- Store._restore_append_position reads DB MAX(record_ordinal), current log EOF and the last
  byte (LF required). It does not compare historical records/offsets/hashes. There is NO
  accepted anchor, HTTP raw-line hash column or table-comment access in active detour code.
- Store.rebuild_from_log currently pre-parses the complete log before deleting detour DB/WAL,
  recreates schemas and applies records. It has only the first confirmation, not the approved
  second nonempty replay question/empty anchor/progress. Keep explicit bootstrap, not resume
  catch-up. main source DB/log must remain protected from deletion by the existing guards.
- ReplayLogRegisteredResource._locked holds a read-only descriptor/lock and chmods0400.
  _append alone currently opens the temporary writer (0600, append-only, same-inode, fsync,
  finally0400); writable startup does not yet prove writer acquisition. No tail repair or
  missing-log creation exists. Empty log parses as zero records; malformed/blank/non-LF
  records fail parsing. Resume's current weak EOF check can miss malformed historical lines.
- Store._publish_stored_cards is called from ordinary writable opening and explicit rebuild;
  validate_commit republishes existing results; _apply_log_record publishes after commit.
  api.publish_card_zip/_same_zip_contents reconstruct/replace missing or different ZIPs.
  Delete ALL these effects, including first publication, under the approved export scope.
- api._apply_validation_record currently substitutes a historical INNERDICT_AND_CARD failure
  for a newly accepted evaluation before equality comparison. Remove that special case;
  mismatched re-evaluation must fail. Do not change persisted enum/record shapes for this.
- Dashboard context begin_backend_start/finish_backend_stop currently share one policy for
  both child modes and rearm --new on failures. Controller.start currently restores queued
  runs AND starts consuming them automatically. Both behaviors are approved for correction.
- application_startup is a NiceGUI background startup handler: exceptions currently prevent
  SERVICES publication but do not terminate the HTTP process. Fix the prior fail-fast gap;
  a test merely awaiting the coroutine does not establish real application shutdown.
- IPC-only still uses threading.Event.set in its signal handler. A signal during Event.wait's
  non-reentrant lock section can deadlock. The approved boolean/polling snippet fixes this.
- Clean-close token is still defined in server.py and imported therefrom by Dashboard;
  QueryRequestProperty still requires outbound_http. Both approved surgical moves are pending.
  The operator has already restored the literal DASHBOARD_QUERY_PATH = "/query"; retain it.

## Existing contracts to retain

- Prefer FrozenStrictModel where its frozen/strict/extra-forbid contract fits; otherwise
  use BaseModel with explicit ConfigDict, not overrides of FrozenStrictModel. The mutable
  singular outerdict retains assignment validation without arbitrary_types_allowed;
  mutable Run/UI handles and deliberately permissive external-input DTOs retain their
  distinct configs. The pasted StrictModel/pydantic_to_paste file is unchanged from handoff.
- ui.py dataclasses have been replaced with Pydantic models. Final approved names are
  the formal `_Researcher = AiAugmentSingularOuterDict` type alias, `_ResearcherVar`
  (varname/ai_column/table_1_column, with the approved explanatory docstring),
  RESEARCHER_VARS / RESEARCHER_VARS_BY_VARNAME, _RunCommitView, _RunCommitVarView,
  _ResearcherView, _ResearcherVarView and _ResearcherCardView. These final names are already
  implemented; no further UI rename is pending. Remaining detour-wide dataclasses are
  covered by the operator's latest clarification and the separate review below.
- Store exclusively owns detour DB/replay-log handles and transactions; API retains domain/
  evidence SQL. Main pipeline DB is read-only. Retained log FD is read-only; actual writer
  and writable DB handles have short Store-owned scopes. execute().fetchone()/fetchall()
  return detached results, never an escaped connection/cursor. Store modes: writable/read_only.
- Codex row IDs are allocated inside the Store transaction by api._next_codex_row_id,
  not nontransactional DuckDB sequences; speculative rollback must consume no IDs.
  Direct imports replace TYPE_CHECKING guards in the detour implementation.
- Live HTTP capture is separate from durable append/fsync -> projection -> DB readback ->
  downstream use. _consume_log_suffix runs immediately after LIVE append, not on startup
  to fill historical gaps. Failure latches prevent reuse in that Store instance; only an
  explicit rebuild clears the latch. New-process integrity is the pending startup check.
- /validate retains commit_id, PostCommitValidation, serialized Submission/StandardizedSubmission
  and discriminator, provider HTTP UUIDs, commit-shaped headers and null response fields.
  ModelHttpInterceptor replay rejects missing/ambiguous inputs without network fallback.
  Live capture/evaluate/rollback for missing inputs is ordinary execution, not recovery.
  HttpRequestLogRecord.from_response/to_response remain the response-conversion boundary.
  Pasted pydantic_to_paste and its StrictModel remain untouched.
- CAS checks hash/size/line-count and fails on missing/corrupt evidence; no redownload. Partial
  run-outcome capture is a recorded HTTP500, not fabricated/repaired evidence. Rollback,
  insert-or-validate, ordinary submission retries and temporary-file cleanup remain.
- NiceGUI access is exclusively AiAugmentDashboardStorage, with immutable validated wholesale
  DashboardQuerySnapshot and independent run journal/queue. The controller has no query
  client; create_services supplies a separate Query IPC callback plus probe/outcome/card
  capabilities. No startup/repaint/card implicit query or direct Dashboard source-DB read.
  Existing explicit Query IPC borrows an available Backend or owns a temporary query child,
  with serialized lifecycle and storage replacement only after successful child cleanup.
- Run finalization remains CODEX_EXITED -> one ordinary /pull -> 410 completed / everything
  else (including503) failed -> outcome IPC -> owned-process shutdown. Cancellation stays
  independent. The pending queue gate controls whether NEXT dequeue happens after cleanup.
  A later snapshot never mutates the run journal. One explicit cheap four-stage Probe stays.
  _AttemptReconciler/_VariableProjector are removed; keep approved final view/var names.
- Existing interactive restart handling may terminate abandoned REMOTE Codex runs and mark
  interrupted journal runs failed. This is not local orphan-Backend cleanup; do not extend
  it into such a mechanism. Publishing must skip those remote/journal mutations as approved.
- Owned Backend shutdown sends SIGTERM, waits10s, then SIGKILL if needed. Clean classification
  requires the Store-close acknowledgement, acceptable exit status and no forced kill.
  Preserve this protocol while relocating its constant. Borrowed/external Backend is never
  reset/stopped, including one surviving Dashboard SIGKILL. No automatic startup detection.
- Legacy QueryResponse discriminator inference is DTO compatibility only. The approved hash
  mechanism proves recorded-byte coverage, not independent equivalence of every derived
  domain table. _committed_innerdicts' absent-output-table case is not a DB repair mechanism;
  do not invent a shadow rebuild/comparison contour. Appendwatch and proxy caches are outside
  this scope.

## WORK / HUMANS / handoff reconciliation

HUMANS is a human-owned historical record, not an additional verbatim implementation
checklist. Latest operator decisions and the current pending scopes above control.
The handoff review against d9351ed is complete; retained implemented contracts are listed
above. Human/operator/browser/provider rollout acceptance remains outstanding separately.
Do not revive old proposals as extra backlog. The conversation audit was delivered in chat;
its superseded-proposal table and mistaken ambiguous-dataclass inventory are not retained
as current instructions here. The latest explicit dataclass clarification controls below.

## Dataclasses — detour-wide review complete; conversion pending

### Authorization and current status

Original operator instruction:
> replace all dataclasses with a pydantic model, preferrably FrozenStrictModel where feasible.

The accompanying assistant response scoped the work then performed:
> I’ll replace Dashboard dataclasses with Pydantic models, using `FrozenStrictModel` where immutable and explicit mutable configuration where needed.

Current authorization: the operator explicitly clarified that the instruction applies
to the entire AI-augment detour, reviewed the findings below and accepted them ("sounds
good"). Dashboard conversion is done; remaining conversions are pending implementation,
not a request to repeat the review. No models were changed in the review/handoff turns.
The latest whole-detour instruction covers all28 listed classes, including the mechanical
conversion of BDD LifecycleState. That narrowly updates the older paused-BDD edit exclusion:
do not reactivate, redesign or repair the paused BDD suite; change only its dataclass model
and directly necessary imports/call points. Its broader stale wiring remains outside scope.

### Complete current inventory and recommendation

Static rg + AST review covered every Python file under src/detours/detour_ai_augment,
including protected/unprotected source and tests. There are28 dataclasses remaining:
19 production classes and9 test helpers. No Dashboard dataclasses remain.

| File (detour-relative) | Classes/count | Recommendation |
|---|---|---|
| src/backend/api.py |12 frozen DTOs, listed below | FrozenStrictModel; existing fields/methods retained |
| protected/src/backend/helpers/codex_parse.py | CiteSection | FrozenStrictModel |
| src/backend/helpers/data_models/model_http_interceptor.py | ModelHttpInterceptor | FrozenStrictModel for resolver; _used/_requests become PrivateAttr caches |
| protected/src/backend/ipc.py | _DashboardIpcServer | BaseModel with explicit frozen/strict/extra-forbid/arbitrary-types config for WSGI server and Thread handles |
| src/control_centre/appendwatch/audit_read.py | AuditReadConfiguration | FrozenStrictModel fits its data, but standalone guest dependency/packaging must be addressed |
| protected/src/control_centre/appendwatch/appendwatch.py | Record | Mutable BaseModel with explicit strict/extra-forbid/assignment-validation config; guest dependency/packaging must be addressed |
| protected/src/llm_inference_api/sample_deploy/proxy.py | PriceQuote, LogEvent | FrozenStrictModel fits both; LogEvent is never reassigned after construction; standalone launcher dependencies must be addressed |
| tests/backend/test_api.py | BackendTestPaths, ExpectedEvidence | FrozenStrictModel |
| protected/tests/backend/test_pydantic_to_paste.py | FakeResponse | FrozenStrictModel; pasted production model stays untouched |
| protected/src/llm_inference_api/sample_deploy/test_proxy.py | _DummyQuote | FrozenStrictModel, subject to the sample deployment/test import arrangement |
| protected/tests/operator/test_operator_e2e.py | OperatorRuntime, WorkflowCheckpoint | FrozenStrictModel |
| protected/tests/operator/test_operator_e2e.py | DashboardProcess, OperatorProcessSnapshot | BaseModel with explicit handle config; preserve shared output-buffer identity |
| protected/tests/bdd/test_detour_ai_augment_bdd.py | LifecycleState | Mutable BaseModel; model-only conversion, without reactivating/refactoring the paused suite |

The12 API DTOs are _PushConfiguration, _ArchivedFile, _RolloutRecord, _SessionMetadata,
_CodexFcRow, _CodexFcoRow, _CodexTurnRefRow, _RolloutIndex, _EvidenceMatch,
_EvidenceCandidate, _EvidenceItemAssessment and _EvidenceAssessment. Their public fields
are already frozen, supported by Pydantic, and constructed with keywords. No arbitrary-
types exception is needed for them; nested evidence models remain unchanged.

### Necessary conversion details / limits

- Use FrozenStrictModel without overriding its config where it fits. Where a different
  config is genuinely needed, use BaseModel with explicit ConfigDict, per the earlier
  instruction. Do not weaken the shared base or change pydantic_to_paste/StrictModel.
- ModelHttpInterceptor only mutates internal lookup dictionaries, not its resolver.
  Callable is supported without arbitrary_types_allowed. PrivateAttr caches preserve
  its stateful behavior without making them serialized fields. Update positional calls
  in Store.validate_commit and test_http_loop to record_get=... .
- _DashboardIpcServer and the two operator process wrappers hold opaque live handles
  (WSGI server, Thread, Popen, psutil.Process). Explicit arbitrary_types_allowed is
  justified locally for instance checking; preserve the objects, do not serialize them.
  DashboardProcess.output is shared with _collect_output's running thread. An ordinary
  Pydantic list[str] field COPIES that list and breaks readiness/output collection;
  preserve shared-buffer identity explicitly instead of just swapping the class base.
- Appendwatch Record mutates status/reason/exists and inode/size/time/digest fields in place.
  Freezing it would force a larger algorithm rewrite and is not appropriate. Replace its
  two dataclasses.replace calls with equivalent shallow model copies (trusted bool updates),
  and its positional constructor in test_appendwatch with keyword arguments.
- ExpectedEvidence has nine positional fixture constructions; DashboardProcess has one.
  Adapt those to keyword calls. Do not change field meanings, ordering-dependent output,
  wire formats, live/replay logic or runtime ownership merely for model conversion.
- Standalone deployment is a real integration dependency, not just a typing choice:
  appendwatch.py explicitly requires no third-party packages; deploy.sh copies only it
  and audit_read.py; provision.sh uses /usr/bin/python3 and installs audit_read as a
  standalone executable. proxy run.sh/usage.sh invoke python3 directly. These paths do
  not provision Pydantic or the repository's shared FrozenStrictModel import. Making
  the classes Pydantic is feasible, but cannot honestly be called an isolated class-base
  edit without resolving dependency delivery/imports. The conversion must include the
  minimal dependency/import/launcher integration it needs; no distribution scheme is
  prescribed. Keep that wiring local to the existing scripts and verify the deployed-layout
  imports/interpreter compatibility hermetically. Do not copy/fork FrozenStrictModel, redesign
  provisioning, deploy to a real guest, or drop these classes silently to claim completion.
- Frozen means field assignment is blocked, not deep immutability of dict/list contents;
  that matches existing frozen dataclass data holders. Test helpers with mutable state
  or external object identity require their own explicit config/representation.

### Review verification

In-memory checks (no server/socket/thread start, no data files) confirmed: Callable plus
PrivateAttr caches works on FrozenStrictModel without arbitrary_types_allowed; a Thread
field needs explicit arbitrary-types support; that support preserves handle identity;
an ordinary list[str] field copies the operator's output buffer. These are feasibility
checks, not converted-code acceptance. No application/test source was changed.

## Verification evidence and focused checks still required

Earlier implementation evidence (not rerun for this WORK-only reconciliation and not proof
of pending behavior or subsequent operator edits):

- Ruff on detour plus shared HTTP-record module passed. Strict mypy using the detour config
  plus that module passed for53 files.
- Latest relevant hermetic UI/API/IPC/HTTP-loop run:240 passed,1 skipped,3 deselected (126.34s),
  excluding captured/Haanen data and real Unix-socket test. Three startup/probe cases passed
  afterward and overlap. Older overlapping totals are not additive acceptance evidence.
- Twelve mocked shell-launcher flag combinations passed before the IPC-only mode correction.
- Isolated DuckDB1.5.1 experiment: JSON in a table COMMENT persists across reopen; a rollback
  restores the old comment. No production DB touched. This validates a storage facility,
  not an implemented anchor. See the explicit metadata pointer in startup scope above.
- tmp/tmp.patch was explicitly supplied for review. Its IPC signal-handler deadlock was
  reproduced in an isolated socket-free/data-free child by delivering SIGTERM while
  Event.wait held its lock; a2s timeout killed/reaped the child. Existing signal tests mock
  Event.wait and miss this interaction. Do not restore the patch's obsolete namekey_parameter.
- Static recovery/I/O audit found no custom resume catch-up/tail repair or active API-owned
  detour DB connection. Main pipeline was reviewed statically; its metadata examples are
  Parquet KV_METADATA, not DuckDB table comments. HUMANS' existing EOF blank is human-owned.
- No actual browser/operator/provider E2E was run here.

With implementation, run focused hermetic checks plus appropriate Ruff/mypy:

- CLI: full-mode required exclusive new/resume/continue and default-No/--yes behavior;
  second nonempty-log prompt, refusal before reset, empty anchor, first failed-line progress.
  IPC-only accepts no mode/ignored single or conflicting modes without prompting/rebuilding;
  missing DB fails without creation. No parent-PID dependency. Launcher usage matches modes.
- Store: exact-byte prefix/suffix coverage, same-hash checks, invalid boundaries/truncation,
  missing/extra rows/ordinal gaps, atomic verified-anchor promotion and no resume mutation
  on failure. Dashboard stale-hash delegation must not advance the old hash to newer EOF.
  IPC-only verifies read-only without anchor promotion; bootstrap uses the common applicator
  offline, never appends to the replay log. Retain live/replay DB equality and explicit
  bootstrap/readback-failure coverage in test_http_loop.
- Append preflight: failed acquisition aborts readiness; success writes zero bytes and
  restores0400; IPC-only never acquires a writer. Historical verdict disagreement fails.
- Dashboard lifecycle: replace tests expecting failure-rearmed --new or IPC initialization;
  preserve first-full-new, later resume, external borrowing, serialized child lifecycle,
  bounded cleanup and acknowledgement ordering. Test both IPC signals/unexpected thread
  death/finally cleanup/handler restoration using the approved non-locking flag shape.
- Queue: startup always stopped, Start uses one worker, Stop leaves active run/finalization
  alone, stop-while-empty blocks a later enqueue, FIFO/persistence retained, cancellation
  actually terminates and leaves the run off queue without changing the processing switch.
- Publishing: no Backend archive writes on live/replay/start/repeated validation; DB results
  unchanged. Shared button/batch renderer/naming/availability; eligible+current-completed
  filtering; saved snapshot only; no query/queue/remote/journal side effects; per-file logs,
  zero-selection no-op, normal shutdown and nonzero failure status. Framework lifecycle
  coverage must establish shutdown on bad startup config/hash/storage, not just a raised
  directly awaited startup coroutine. Do not execute paused BDD or real sockets/network here.

### Verification entry points for the next implementor

Use explicit file/node selections, not broad Pixi operator/deploy/elevate tasks. All commands
run from repository root through pixi run -e detour-ai-augment. The following are commands
for the executor after edits, NOT new results from this handoff:

- `pixi run -e detour-ai-augment env ruff check src/detours/detour_ai_augment src/helpers/data_models/http_request_log.py`
- `pixi run -e detour-ai-augment env mypy --config-file src/detours/detour_ai_augment/mypy.ini src/detours/detour_ai_augment src/helpers/data_models/http_request_log.py`
- Primary regression files: tests/backend/{test_api,test_ipc,test_http_loop}.py and
  tests/control_centre/test_ui.py (detour-relative), plus repository-root
  tests/test_http_request_log.py. Invoke using `pixi run -e detour-ai-augment env pytest`
  and full repository-relative file paths with the following exclusions.
- Do not select real captured data/operator tests: specifically exclude
  test_captured_operator_push_generates_commit_and_exact_410_response and
  test_historical_haanen_retry_preserves_verified_evidence_roundtrip in test_api.py.
  Exclude test_dashboard_client_queries_real_mode_0600_unix_socket in test_ipc.py.
  Keep real_api/operator/needs_sudo cases out; do not run test_ui_e2e.py here.
- Adapt obsolete expectations in test_http_loop.py: publication/recovery tests become
  no-publication/explicit-export checks; durable readback failure must not imply resume
  catch-up. In test_ui.py replace shared-IPC-init/failure-rearm expectations. In test_ipc.py
  adapt signal tests for the boolean/poll loop; use hermetic mocks, not real socket servers.
- Model conversions: focused checks in tests/control_centre/test_audit_read.py,
  protected/tests/backend/{test_pydantic_to_paste,test_appendwatch}.py and
  protected/src/llm_inference_api/sample_deploy/test_proxy.py as applicable. Select only
  isolated cases after checking fixtures/markers; appendwatch tests can launch subprocesses
  and some require root, proxy tests can start socket servers. Do not run these entire
  suites blindly under the no-socket/no-root/no-network constraints.
- Strict mypy and default Ruff exclude sample_deploy and paused BDD. Therefore a green
  detour-wide invocation alone does not validate their converted classes; perform targeted
  syntax/model checks separately without unrelated lint cleanup or BDD collection/reactivation.
- Model-specific regressions: accepted nested types/validation, keyword constructor updates,
  mutable Record updates and shallow copies, opaque-handle identity, interceptor cache
  isolation, and shared operator output-buffer identity. Do not run operator processes to
  test those properties; use isolated objects. Check LifecycleState's model in isolation,
  without repairing or executing the paused BDD suite.
- Final review: `pixi run -e detour-ai-augment git diff --check` (read-only Git), review
  source/test changes without staging, update each pending section to actual status and
  report remaining operator-only acceptance separately. Do not reuse historical totals
  as evidence for the newly changed code.

## Mandatory constraints

- After compaction reread TASK and WORK IN FULL; keep WORK current and free of stale scope.
- All commands via pixi run -e detour-ai-augment; Ruff/mypy/pytest via env. Mypy config:
  src/detours/detour_ai_augment/mypy.ini.
- Git READ ONLY: never stage/unstage/reset/restore/stash. Operator stages concurrently.
- Never run/import src.repl, edit src/cli.py, or import another detour. Main pipeline was
  reviewed statically only. Only allowed source data: data/scisci_process.duckdb READ ONLY;
  do not inspect other data/, .aicode/ or historical production/tmp captures. Isolated
  test fixtures/temp files are allowed. No network/socket probes or escalation.
- Preserve human-signed comments; TASK/HUMANS human-owned and never edited by agent.
- Keep changes surgical within approved scope. No new scope inferred from a keyword hit.
  Paused BDD permits only the dataclass conversion required by the latest whole-detour
  instruction; no suite reactivation, broader repairs or execution. No unsolicited refactor
  or new service hierarchy.
