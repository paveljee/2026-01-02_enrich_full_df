# AI augment production preparation

## Status and authorization

2026-09-16: Previously approved implementation scope P1-P12 is implemented.
Newly approved P13 (extensionless, sharded CAS layout) is PENDING; its exact narrow
scope and approved snippets are pinned below. That approval requested recording,
not implementation. No CAS code or stored blobs have been changed.
2026-09-17: P14 startup-condition tests and P15 staged-test consolidation review are
complete: 111 mock-free startup cases and 123 moved/existing tests passed; Ruff/mypy passed.
P16 Markdown/TXT download is implemented and verified; approved snippets below.
P13 remains the only pending approved implementation scope and was not part of P16.
The full hermetic regression run passed (306 passed,1 skipped,3 excluded); subsequent
Store/IPC/provisioning checks passed (28, overlapping the broad suite). Final Ruff and strict mypy
passed after the last edits. No production/operator/guest/network
rollout was performed. That acceptance remains separate from implementation completion.

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
| P14 | Current lifecycle review and 111 mock-free parametrized startup-condition cases | tests/control_centre/test_ui.py |
| P15 | Operator test moves preserved; import, constant and fixture collisions corrected | test_ui.py, test_audit_read.py, test_backend_store.py |
| P16 | Markdown/TXT button shares DOCX download contour; symmetric format-specific handles/selectors | ui.py, locale.py, existing UI tests |

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
changes to publish completed (still DOCX-only). P13 remains pending and untouched.

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
suite was not run. No generic old download-card handle/selector references remain.
Verification: 7 focused UI cases passed (184 deselected, 11.11s), covering both download
formats with exact Unicode bytes/filename/MIME, button clearing/skipped download, logs,
snapshot invalidation, unchanged completed DOCX publishing, publication failure/no-op and
existing detailed DOCX error logging. Ruff and strict mypy passed the four touched Python
files; git diff --check passed. No real browser/operator/server/network execution.

Focused command:

```bash
pixi run -e detour-ai-augment env pytest -q src/detours/detour_ai_augment/tests/control_centre/test_ui.py -k 'displayed_card_download or snapshot_replacement_clears or publish_completed or publish_one_shot or probe_and_docx_failures' -m 'not real_api and not operator and not needs_sudo'
```

## P13 — Pending approved scope: extensionless, sharded CAS layout

Approved 2026-09-16: the operator approved the exact narrow proposal and snippets below
and requested recording them in pending WORK. Implementation has NOT started.

### Exact scope

Current AiAugmentCAS layout is flat <cas-root>/<full-sha256>.jsonl. The suffix describes
Codex rollout content but is unnecessary for content addressing; the README requires
content addressing, not that suffix or a flat layout. Replace it with:

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

## Remaining acceptance, NOT unimplemented approved scope

For completed P1-P12, only human/operator rollout acceptance in the real environment
remains; P13 is separately pending implementation. P14/P15 test/review and P16 download
scope are complete.
Rollout acceptance covers actual guest
provisioning/dependency install, interactive Dashboard/server/browser/provider E2E and the
operator-maintained production config/log hashes. No such activity was authorized for this
restricted execution environment and none is claimed. All code changes remain reviewable
in the working tree/operator-staged index; no commits were made by the agent.

## Mandatory constraints for continuation

- After compaction reread TASK and WORK IN FULL. Keep WORK current, remove stale pending claims.
- All commands via pixi run -e detour-ai-augment; Ruff/mypy/pytest via env. Git read-only.
- Never run/import src.repl, edit src/cli.py, import another detour or edit TASK/HUMANS.
- Only allowed production data is data/scisci_process.duckdb READ ONLY. No other data/,
  .aicode/ or historical captures. Isolated temporary test fixtures are permitted.
- No network/socket probes/escalation. Paused BDD permits only its completed model conversion.
- Preserve operator edits/staging, human-signed comments and narrowly approved boundaries.
- sample_deploy is excluded from edits, conversion inventories and test execution.
