# Tighten API — current handoff

## Required operating rules

- Read this file and `tasks/tasks-20260731-tighten-api/src/TASK.md` in full
  immediately after every compaction. Together they are the complete context;
  make only focused code lookups afterward.
- Keep this file current and standalone throughout the work. Replace superseded
  content; do not preserve a progress diary.
- `src/TASK.md` is human-owned and immutable. Do not edit the frozen legacy
  SPEC, README, `.env.example`, sample runs, historical submissions/rollouts, or
  ground-truth data.
- Run every command through `pixi run`. Git is read-only. Apply edits only with
  a complete reviewable `pixi run apply_patch <<'PATCH' ... PATCH` command.
- Use only `pixi run pre-commit 2>&1` for verification; do not run lint or
  component test contours separately. Operator tests remain a separate explicit
  contour on the operator machine.
- Keep changes surgical. Human-facing backend wording belongs in
  `backend/helpers/locale.py`; tests belong in
  `src/detours/detour_ai_augment/tests`.

## Current objective

Replace the loose `ControlRunEvent`/run-journal/per-attempt-manifest/archive-dir
design with rigorously modelled real HTTP exchanges and content-addressed
rollout storage. This is currently an approved architectural direction under
discussion, not yet an instruction to implement.

## Canonical persistence direction

- `HttpRequestLogRecord` remains the exact, vetted JSONL envelope. Its field set
  must not acquire run IDs, attempt IDs, artifact metadata, or other internal
  fields. Endpoint-specific information belongs only in the actual HTTP request
  and response bodies, validated by dedicated Pydantic models.
- Preserve three separate append-only JSONL resources for clarity:
  1. dashboard -> backend sanction exchanges;
  2. client -> backend `/push` exchanges, whether valid, invalid, or failed;
  3. backend -> dashboard submission-processing-result exchanges, regardless of
     whether dashboard is listening.
- Each attempted exchange is logged as a complete `HttpRequestLogRecord` with
  the actual request and observed response. An unreachable recipient is
  represented honestly by the model's absent response values rather than by a
  synthetic successful response.
- The three logs are canonical inputs. DuckDB remains a disposable projection
  reconstructed from these logs plus the read-only main source database.
- Replace attempt directories with a content-addressed store containing only
  cumulative rollout snapshots. Snapshot bytes are addressed and verified by
  SHA-256. Small private processing inputs/results currently spread across
  manifests and run events belong in the actual processing-result request body.
- Restoration must not discover attempts by scanning directories. It parses the
  three logs, validates endpoint bodies, correlates exchanges, verifies the
  referenced rollout snapshot, and feeds the same deterministic projection
  pathway used after live processing.
- URL/path identifies the exchange category but cannot correlate repeated
  exchanges. Actual payloads need stable correlation: run identity and hashes of
  the corresponding sanction exchange, push exchange, and rollout snapshot.
  JSONL line ordering is storage order only; cross-log timestamps/order may tie
  or race and must not be treated as causality.
- `ControlRunEvent`, `RunJournal`, custom per-attempt manifests, archive
  directory scanning, and the associated symlink policy should disappear once
  the replacement is complete. Do not try to strengthen the current optional-
  field event bag as an end state.

## Open design points to resolve before implementation

- The three mutable append-only logs should be registered with hashes in
  `config_ai_augment.json`, per the operator's direction. A static configured
  whole-file hash becomes stale after every append, so the lifecycle must be
  made explicit: e.g. active versus sealed logs, immutable segments, or another
  strict scheme that never silently rewrites expected hashes. Do not invent a
  mutable manifest as a workaround.
- The three listed exchanges do not by themselves close a run that dies before
  `/push`, is canceled, or is interrupted during launch/discovery. Preserving
  the prior requirement that every dashboard-visible run reconstruct exactly
  requires a real dashboard -> backend termination/control exchange (possibly a
  second typed operation on the same control endpoint), unless the operator
  explicitly narrows history to sanctioned/pushed runs.
- Exact asynchronous delivery semantics need definition. A completed HTTP log
  records an attempted cycle, but a recipient may be absent or a sender may die
  between remote side effect and durable append. Correlation and idempotent
  replay are required; clarify whether an undelivered request record is merely
  audit evidence or a durable command consumers must apply later.
- The result-notification Pydantic body must contain enough private, small data
  to rebuild the current detour DB/card exactly without rerunning historical
  web-evidence validation. It must not expose those private details through the
  public `/push` response.

## `HttpRequestLogRecord.host` correction

- Current API logging uses `request.url.hostname`, which drops an explicit port.
  Fix this without changing the `HttpRequestLogRecord` field set or invalidating
  historical OpenAlex records such as `host="api.openalex.org"`.
- The compatible direction is to define `host` as HTTP authority: hostname for
  ordinary/default-port records and host plus explicit/non-default port for
  local control exchanges. Preserve valid old values and add regressions for an
  old OpenAlex line and local 8611/8612 records. Handle IPv6 authority correctly.
- Unique endpoint paths should remain the primary exchange classifier; do not
  rely solely on port identity.

## Pending Lima lifecycle work

- Revisit separately after the HTTP-ledger design. `deploy.sh` currently starts,
  verifies, and leaves `aivm` running. Desired direction: after successful deploy,
  stop the Lima instance, perhaps after an operator prompt.
- Operator tests should own availability: detect whether `aivm` exists/runs;
  when stopped, prompt to start it (with noninteractive flags for automation),
  then probe SSH and appendwatch. They may prompt after the contour whether to
  stop it, but must never delete it except through the already explicit redeploy
  flow.
- Current autouse operator fixture merely invokes `limactl shell ... true` with
  `check=True`; absent/unavailable AIVM therefore raises
  `subprocess.CalledProcessError` during fixture setup. Replace this with explicit
  lifecycle handling and human-readable failures when this work resumes.

## Current code/verification state

- The tree still contains the recently implemented run-event DuckDB projection,
  private event endpoint, attempt manifests/directories, archive restoration,
  appendwatch topology, sanctioned `/pull` probe, shutdown recovery, and six
  operator E2E extensions. The new three-log/CAS architecture has not yet been
  implemented and will supersede substantial parts of that persistence work.
- `archive_http_request_log`, `record_attempt`, and `safely_record_attempt` now
  have explanatory docstrings only; function names and behavior are unchanged.
- A repository-wide pre-commit contour was green before a later macOS failure
  exposed a stale subprocess test double. The fake now accepts and verifies
  `start_new_session=True`, but the full contour has not been rerun since that
  fix and the docstring-only edits because the attempted rerun was declined.

## Immediate next action

Finish the concrete three-log schemas, correlation and delivery semantics,
configured-hash lifecycle, pre-push termination representation, and deterministic
reducer contract with the operator. Do not implement the architecture until the
operator approves that contract. Keep the Lima lifecycle as a recorded separate
follow-up.
