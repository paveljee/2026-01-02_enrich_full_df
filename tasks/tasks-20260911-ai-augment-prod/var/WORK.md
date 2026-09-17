# AI augment production preparation

## Status and authorization

2026-09-16: Previously approved implementation scope P1-P12 is implemented.
P13 (extensionless, sharded CAS layout) is implemented and verified; exact scope/snippets below.
Only code/synthetic test fixtures may change; no stored production blobs will be moved.
2026-09-17: P14 startup-condition tests and P15 staged-test consolidation review are
complete: 111 mock-free startup cases and 123 moved/existing tests passed; Ruff/mypy passed.
P16 Markdown/TXT download is implemented and verified; approved snippets below.
P13 (CAS layout), P17 (Dashboard layout) and P18 (operator failures/upstream verification)
are authorized for implementation IN ORDER by the latest operator request. P13 is complete;
P17 is complete; P18 implementation and available upstream verification are complete, with
root-only/production verification outstanding; P19 is implemented and locally verified (test
subprocess centralization/selection, with one initial startup timeout and a passing isolated
rerun). All approved P1-P19 code changes are implemented; no approved implementation item
remains pending. This is NOT full production acceptance. Non-elevate Pixi task edits require explicit
per-change approval; see P18 authorization correction. P18 records integration work, not mere rollout acceptance.
The full hermetic regression run passed (306 passed,1 skipped,3 excluded); subsequent
Store/IPC/provisioning checks passed (28, overlapping the broad suite). Final Ruff and strict mypy
passed after the last edits. The agent performed no production/operator/guest/network
rollout. The operator subsequently supplied an unsuccessful acceptance run; findings below.
Acceptance remains separate from implementation completion.

The operator authorized implementation of all pending WORK, strictly narrowly as pinned.
During implementation they added P12: first probe logs, then a whole-ui.py missing-emit_log
review including DOCX download. No new service hierarchy, recovery contour or extra flags
were introduced. Any future deviation/scope extension requires explicit operator approval.
TASK + this WORK stand alone; HUMANS is a human-owned historical record, not another
verbatim backlog. The prior handoff/conversation reconciliation is complete. No hidden
pending approved implementation items remain from that reconciliation.

Git remains READ ONLY for the agent. The operator has staged some edits concurrently;
none was staged/unstaged/reverted by the agent. Baseline at implementation start: dc951fe.
Paths below are detour-relative unless explicitly marked repository-root-relative.

Scope correction (2026-09-16): protected/src/llm_inference_api/sample_deploy is
OUT OF SCOPE, as pyproject.toml's pytest/Ruff exclusions and detour mypy.ini already
specified. Its optional illustrative proxy is not production detour code. The operator
reverted the mistakenly included proxy/models/tests/launcher changes; review confirms no
remaining staged or unstaged changes there and no in-scope dependency on those changes.
Do not edit or run its tests. The conversion inventory below excludes it.

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
| P18 | Operator fixture/query/queue corrections, watcher interpreter, shared lint, full check-graph review and targeted elevate verification | Operator helpers/tests, architecture.py, two approved task substitutions + elevate; root/production verification pending |
| P19 | Named subprocess helpers, shared explicit fixture and selectable markers; preserved isolation/timeouts | protected/tests/pytest_plugin.py + existing test callpoints |

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
anchor or legacy hash-column schema FAIL. Same config/anchor hash does not skip coverage
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
the clean-close acknowledgement only after successful context exit. Missing/invalid/legacy
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
  do not revive superseded scope. No tests touch historical captures or production artifacts.

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
missing/legacy paths, shard/leaf symlinks, live-copy shard rejection, duplicate copy and
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

## P18 — Implemented; available upstream checks complete; production verification pending

2026-09-17: operator approved recording the identified integration gaps as a new P item,
including the broader homework the Assistant missed before handing work to the human.
TASK was reread IN FULL, especially its testing philosophy. Approved corrections are now
implemented after verified P13/P17; available upstream checks and delegated results are
recorded below. Root-only and production acceptance remain outstanding, not additional
approved code changes. This supersedes the former unapproved operator-log-review follow-up.
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
without startup-code/timeout changes. Production root-test execution remains outstanding.

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

### Evidence and exact corrective scope

Source: logs/from_operator/pre-commit.log and pre-commit-extra.log, supplied by the operator.
No production/test code changed during review; only the shared-module Ruff error was
reproduced locally. Ordinary checks stopped at Ruff. Root appendwatch tests: 3 failed
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
| Main tests / default | tests, not slow/real_api, excluding both DOCX-review data-writing cases: 138 pass,3 skip,3 deselect,3 fail | Platform mapping/operator extension path/reviewed XLSX unavailable; do not mutate unrelated config/data |
| Step4 normal / default | explicit module, not slow/real_api: 4 pass,1 deselect | None for synthetic selection |
| Step4 slow / default | NOT RUN | Real config references forbidden/unavailable source artifacts; not a synthetic substitute |
| Mode3 / default | explicit module: 6 pass | None |
| Mode0 / mode0 env | Local2 pass/2 socket-restricted failures; delegated complete module4 pass,11 deprecation warnings (18.03s) | Closed for synthetic selection; no mode0 implementation edits |
| AI augment normal / AI env | Non-subprocess320 pass,1 skip,103 deselect; focused subprocess11 pass; startup90 pass/1 timeout, then the failed case passed alone; all7 browser cases passed across initial/targeted runs | Initial runs were not wholly green; timeout cause unproven; historical captures excluded |
| Appendwatch normal / AI env | not needs_sudo, not socket/task-launcher: 38 pass; actual task-interpreter smoke2 pass | P19 sentinel uses named shared helper, rechecked with P19 |
| Pasted-model provider / AI env | Current fake-response22 pass,1 real_api deselected (21.76s) | Live provider not run locally |
| Main extra real_api / default | NOT RUN locally; supplied operator log3 pass,1 expected xfail retained | Existing evidence, not a new live run |
| Appendwatch privileged / AI env | NOT RUN: delegated sudo stopped before pytest because a password was unavailable | Operator confirms root unavailable here; run existing root task on prod to verify nobody interpreter/dependency accessibility |
| Operator workflow / host | NOT RUN | Expensive real acceptance, after upstream preparation; never hidden inside elevate |
| Pre-commit wrappers | Inspected, UNCHANGED by explicit rejection | Existing failure/reporting quirks remain; no claim fixed |
| elevate / AI env | Initial shell orchestration5 pass; first real batch exit1: IPC/socket substitutions3 pass, browser2 pass/5 startup timeouts, mode0 all4 pass; narrowed shell regression3 pass; targeted real browser rerun5 pass, exit0 | No further elevate run needed for these checks; root execution deferred to prod |

### Completed delegated run and targeted follow-up

Initial P18 delegated verification completed on2026-09-17 at15:38:32UTC, with exit1, reviewed
from logs/from_operator/elevate.log (then37791 bytes; the rerun replaced that file). Real Unix IPC and both socket-substitution cases
passed; browser2 passed/5 failed at the existing10s startup deadline (combined group5 passed,
5 failed in156.30s). These failures occurred before their UI assertions, including DOCX export
and the header contract. Some failed children emitted no output; others logged ready then
normal shutdown after the harness timed out. Sudo requested a password and exited before
the root tests ran. Operator confirms root is unavailable in this environment: all three
needs_sudo appendwatch tests remain explicitly pending on PROD through the existing
pixi run test-detour-ai-augment-root task (also part of pre-commit-operator). No privilege or
permission workaround is authorized/needed. Mode0 then completed:4 passed,11 deprecation
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
5 passed in97.60s, COMMAND_EXIT_CODE=0. Current logs/from_operator/elevate.log is5548 bytes.
Passing cases cover compact line spacing, idempotent researcher/history selection, completed
metadata/history, actual DOCX browser download, and the overall browser/layout contract.
No production/test-startup code or timeout was changed between the failed run and this
rerun, and no heavy local suites overlapped it. The rerun closes the outstanding browser
verification, but does NOT prove contention caused the earlier timeouts or establish load
robustness. No further repeat run or timeout change is proposed. P19 remains complete.

Next operator step: run the established pixi run pre-commit-operator in the usual
production/operator setup, with sudo available for the three root-only appendwatch cases.
That is the acceptance entrypoint, not another implementation task. Inspect its leaf results
and logs rather than trusting the unchanged wrapper's status alone. If an earlier command
prevents the root leaf running, it remains unverified; the existing
pixi run test-detour-ai-augment-root is its standalone entrypoint. Real provider/workflow,
guest provisioning and production-resource checks remain acceptance boundaries. Local
main-suite platform/extension/XLSX prerequisite failures above are not claimed fixed.

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
are complete after P18 local corrections; its available delegated checks have passed, while
root/production verification remains outstanding. This does NOT authorize the rejected pre-commit wrapper edits in P18.

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

Final task-map comparison against HEAD confirmed all ordinary pre-commit definitions
unchanged, with precisely the two approved interpreter substitutions plus elevate different.
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

## Remaining rollout acceptance — separate from pending implementation

All approved P1-P19 implementation is complete within the pinned scope; no approved code
change remains pending. P18's available local/delegated verification is complete, including
the five-case browser rerun, but root-only and production verification are NOT complete.
The earlier transient startup failures remain recorded, not relabeled as first-run passes.
Rollout acceptance covers actual guest
provisioning/dependency install, interactive Dashboard/server/browser/provider E2E and the
operator-maintained production config/log hashes. No such activity was authorized for this
restricted execution environment and none is claimed. All code changes remain reviewable
in the working tree/operator-staged index; no commits were made by the agent.

## Mandatory constraints for continuation

- After compaction reread TASK and WORK IN FULL. Keep WORK current, remove stale pending claims.
- All commands via pixi run -e detour-ai-augment; Ruff/mypy/pytest via env. Git read-only.
- No task edits except the two explicitly approved APPENDWATCH_PYTHON substitutions and agent-owned elevate; pre-commit wrapper changes are rejected.
- Never run/import src.repl, edit src/cli.py, import another detour or edit TASK/HUMANS.
- Only allowed production data is data/scisci_process.duckdb READ ONLY. No other data/,
  .aicode/ or historical captures. Isolated temporary test fixtures are permitted.
- No network/socket probes/escalation. Paused BDD permits only its completed model conversion.
- Preserve operator edits/staging, human-signed comments and narrowly approved boundaries.
- sample_deploy is excluded from edits, conversion inventories and test execution.
