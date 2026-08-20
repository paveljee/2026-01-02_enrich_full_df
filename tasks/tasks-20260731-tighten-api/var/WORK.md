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

- The three append-only logs follow the established OpenAlex-log checkpoint
  contract. They may remain mutable while work is active. When the operator is
  ready to checkpoint, hand off, or publish them, the operator manually records
  their current SHA-256 values in `config_ai_augment.json`. Runtime code must not
  rewrite configured hashes or treat them as live synchronization state.
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
  Add version-2 wire behavior with an explicit `port` field while preserving the
  version-1 contract and historical OpenAlex records.
- Keep `KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION = 1` for all main-pipeline producers
  and domain checks. The active simpler proposal is one versioned
  `HttpRequestLogRecord` with `schema_version: Literal[1, 2]` and
  `port: int | None = None`, plus differential wire validation and serialization.
  Before validation, version 1 rejects the presence of the `port` key even when
  null. Native version 2 accepts omitted `port` input and defaults it to `None`;
  `port` remains a declared version-2 schema property and version-2 serialization
  always includes it, including as null. Version 1 serialization omits `port`, so
  version 1 remains the exact original 13-field JSON contract.
- `coerce_schema_v1: bool = False` is an ordinary model field, not a custom
  `model_validate_json` argument. Like `port`, the field is absent and forbidden
  in schema version 1; schema version 2 initializes and serializes it. For version
  2 with coercion true, validation first removes only the two version-2 fields,
  changes the projected schema version to 1, and fully validates that projection
  under strict version 1 before completing ordinary version-2 validation. Native
  version 2 with coercion false skips this projection and still permits
  `port=None`. The detour API is native version 2 and does not opt into coercion;
  coercion remains an explicit fallback for a future painless migration.
  `model_validate_json` remains Pydantic's unmodified routine validator.
- Version 2 additionally declares
  `ready_to_respond_at_unix_usec: int | None = None`. Version 1 rejects the field
  on input and omits it on serialization. A migrated version-1 payload omits the
  unsupported field, so opt-in version-1 coercion receives the ordinary null
  default without special mutation. Native version 2 preserves a supplied
  timestamp and otherwise defaults it to null. No producer, including the detour
  API, explicitly populates the field yet. Main-pipeline/OpenAlex version-1
  timing and wire records remain unchanged.
- Within the Python object, a parsed version-1 instance necessarily has the
  statically declared `port=None` and `coerce_schema_v1=False` defaults;
  “undefined” applies to the version-1 wire representation. If the attributes
  themselves must not exist, two models are required. The one-model JSON Schema
  will also need explicit
  conditional/`oneOf` customization if consumers must see the version-dependent
  required/forbidden rule rather than relying only on runtime validation.
- Add regressions for an old OpenAlex version-1 line, version-1 serialization,
  local version-2 8611/8612 records, explicit default ports, no-port URLs, and
  IPv6 host/port separation.
- Unique endpoint paths should remain the primary exchange classifier; do not
  rely solely on port identity.
- A read-only full audit found that all 135 records in
  `data/openalex_author_search_log.jsonl` and all 167 records in
  `data/openalex_paper_title_log.jsonl` validate against the strict current
  model. Every record has the exact 13-field schema-version-1 envelope and uses
  `host="api.openalex.org"` with no port. The OpenAlex producer and validator use
  the same `OPENALEX_HOST` constant directly, so authority-aware URL extraction
  for detour records does not change historical or future OpenAlex records.
- Keep existing version-1 OpenAlex producers, validators, matching helper, and
  construction helper on version 1. Their explicit schema-version checks remain
  unchanged. New detour HTTP ledgers intentionally construct version 2 and
  populate `host=request.url.hostname` and `port=request.url.port`; Starlette
  preserves explicitly supplied ports and returns `None` when absent. Any new
  version-2 matching/reduction compares the port and cannot conflate otherwise
  identical endpoints on different ports.

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

- The shared `HttpRequestLogRecord` now supports version 1 and version 2 through
  one strict model. Differential validation forbids all three version-2 fields in
  version 1; version 2 declares and serializes port, coercion, and response-ready
  fields while permitting null/defaulted values. With coercion true, the common
  payload is fully validated under version 1 before version-2 validation
  completes; a migrated payload defaults its absent response-ready field to null.
  Differential serialization preserves the exact 13-field version-1 wire format. The main
  OpenAlex constant and producers remain on version 1. Detour push HTTP archives
  intentionally write native version 2 with host and optional port; the new
  response-ready field remains at its null default. Archive replay likewise
  requires and validates native version-2 records directly. The shared model's
  opt-in coercion path is not consumed by the detour API.
- The tree still contains the recently implemented run-event DuckDB projection,
  private event endpoint, attempt manifests/directories, archive restoration,
  appendwatch topology, sanctioned `/pull` probe, shutdown recovery, and six
  operator E2E extensions. The new three-log/CAS architecture has not yet been
  implemented and will supersede substantial parts of that persistence work.
- `archive_http_request_log`, `record_attempt`, and `safely_record_attempt` now
  have explanatory docstrings only; function names and behavior are unchanged.
- The latest `pixi run pre-commit 2>&1` passed Ruff, mypy, all shared HTTP-log
  regressions (including the V2 response-ready JSON roundtrip), and 162 detour
  tests. The contour failed seven tests because the current human-edited
  `config_ai_augment.json` is invalid JSON at line 40, column 79. No config edit
  was made. Operator-marked tests remain an explicit separate contour on the
  operator machine.

## Immediate next action

After the operator resolves the current invalid JSON in
`config_ai_augment.json`, rerun `pixi run pre-commit 2>&1`. Then finish the
three-log body schemas, correlation and delivery semantics, pre-push termination
representation, and deterministic reducer contract with the operator. Do not
implement the wider architecture until the operator approves that contract.
Keep the Lima lifecycle as a recorded separate follow-up.
