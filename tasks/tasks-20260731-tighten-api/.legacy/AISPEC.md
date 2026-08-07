## how ai understood the spec

### scope and required outcome

This is a production-hardening follow-up for the existing, deliberately
small detour under `src/detours/detour_ai_augment/`. The implementation
must wire the existing appendwatch, Lima deployment, SSH identity, archived
Codex rollout, DuckDB provenance index, `/push` validator, detour innerdict,
and researcher-card output into one fail-closed chain. It must not invoke
`src.repl`, alter the main pipeline, edit its `vars.py` or `schema.py`, or
write to the configured main-pipeline database.

The Control Centre now selects and sanctions each source-key run. A run starts
one noninteractive Codex execution, permits retries until one push is
accepted, and consumes its sanction after that acceptance so later pulls and
pushes remain disabled until the operator starts another run. The same source
key may be run repeatedly, and each run has its own UI run ID, Codex session,
and accepted attempt ID. Keep the backend's existing cumulative-rollout
support: every push archives the then-current prefix, and neither persistence
nor validation may assume one rollout, run, or accepted attempt per source
key.

The trust chain for an accepted push is:

1. appendwatch ran as root before the `ai` account could start Codex and
   continuously monitored `/home/ai/.codex/sessions`;
2. the Control Centre sanctioned one run with its source key, Codex session,
   and absolute guest rollout path;
3. the backend copied that rollout over the dedicated AIVM SSH connection;
4. only after the rollout copy completed, the backend made an immutable,
   versioned copy of appendwatch's protected status log;
5. only after the status-log copy completed, the backend checked that copy
   and proved the archived rollout was the exact rollout version marked OK;
6. only then did the backend count and parse that immutable rollout and update
   its normalized provenance tables in the detour-owned DuckDB;
7. only then did Pydantic validate the submitted AI values and excerpt/URL
   pairs through parameterized DuckDB lookups;
8. only a fully valid attempt materialized the Codex output view and common
   `codex_innerdicts` contract; and
9. only then did it produce the normal response and the configured TXT or
   DOCX researcher-card artifact and acknowledge that accepted run to the
   Control Centre.

No later step may run when an earlier step fails.

### surgical implementation boundary

The implementer must write surgical code: make only changes strictly required
by this spec and leave unrelated code, comments, formatting, and behavior
untouched. Do not perform incidental refactors or cleanup.

The expected production edits are narrowly confined to the existing
detour-local `api.py` and `codex_parse.py`, the supplied
`control_centre/ui.py` skeleton, focused tests, the minimum pinned
NiceGUI/Pixi task wiring, and the minimum `deploy.sh`/`provision.sh` changes
needed for the one approved API tunnel. `appendwatch.py`, its regression
tests, `README.md`, `.env.example`, the main pipeline,
`src/helpers/vars.py`, `src/helpers/schema.py`, architecture assets, and
sample/ground-truth data remain untouched.

All detour-owned table names, column labels, citation delimiters, paths,
ports, collection/body bounds, context-length settings, and other repeated
numeric values belong in named globals at the top of the file that owns them;
do not scatter literals through the implementation. Keep the existing API
schema labels at the top of `api.py`. Reuse existing main-pipeline constants
by import where they already exist, without adding detour labels to the main
constants modules or restating constants such as `CARD_PARTITION_TABLE`.

Reuse the existing codebase at its current seams rather than restating or
forking it: `PipelineConfig.from_json()` for config, the deterministic sibling
DB-path pattern in `detour_step4_breakdown.py`, step 08 and
`duckdb_utils.py` for flat relation -> output view -> common JSONL-innerdict
materialization, `docx_parse.py` for the parser/extraction/render separation,
and `cards.py`/step 10 for card assembly and TXT/DOCX ZIP output. Keep the
Codex-specific code detour-local and adapt only the data entering those seams.
Use the existing common innerdict loaders as the source of researcher identity,
draws, task context, ground truth, and rendered cards rather than querying or
reconstructing a parallel card representation.

The dedicated detour config is `config_ai_augment.json`. Require its
`files_config["map_subset_0_to_batch"]` entry in detour code and register that
CSV through the existing `register_resource()` helper as a
`RegisteredResource`, using `ResourceGroup.KTP_PIPELINE_ARTIFACT`,
`FragmentType.CSV_ROW`, and the configured description and SHA-256. Read the
map only through the verified registered-resource path, and import the
existing `DRAW_LABEL` and `BATCH_LABEL` constants for its two-column schema.
Require one non-blank release-batch classification per map draw and reject
missing columns or duplicate/conflicting draw rows. Do not add this detour-only
key to main-pipeline required-config constants, change `PipelineConfig`, or
otherwise affect main-pipeline config/resource loading.

### eligible source-key cohorts and innerdict ownership

The configured source DuckDB remains read-only. Its common innerdict tables
are authoritative for researcher membership and presentation. Obtain each
source key from the innerdict table's `name_key`, and obtain first/last names
and every non-null `ktp.draw_number` only from that source key's innerdict
JSONL records. Preserve every distinct draw carried by those records for a
contracted source key. Never source, replace, or choose a representative draw
from `card_partitions`, `samples_with_names`, another matching/view relation,
or the registered release-map CSV.

The SHA-256-verified `map_subset_0_to_batch` resource only classifies draw
values already found in innerdicts. Derive the cohorts by source key, not by
treating a draw as a unique researcher:

- The ground-truth cohort contains the distinct source keys whose
  innerdict-provided draws map to release batches `subset 1`, `subset 5`,
  `subset 6`, or `subset 7`, excluding the source key
  `{"ktp.first_name": "Mercouri G.", "ktp.last_name": "Kanatzidis"}`.
  Their one or more `docx_innerdicts` records supply the ground truth.
- The no-ground-truth cohort contains source keys selected by
  `card_partitions` only for its eligibility flags: partition 4,
  `ktp.partition_flag_xlsx_non_exact_any = false`, and
  `ktp.partition_flag_ssn_count = 1`. Join that result by source key to the
  innerdict-owned researcher data; do not take its draw/name columns.

Fail startup if the two sets overlap or if their exact cardinalities are not
196 and 78, respectively, with 274 distinct eligible source keys in total.
The remaining 33 source keys are not displayed as runnable work. Keep the
three release-batch-subset-8 source keys and the explicitly excluded
Kanatzidis source key out of the ground-truth cohort, and keep the remaining
29 staging source keys out of the augmentation cohort.

### Control Centre, run journal, and review UI

Implement the supplied `control_centre/ui.py` as one NiceGUI application with
AG Grid and one operator screen. It owns the queue, exactly one active Codex
process, source-key sanctions, cancel/rerun operations, and backend process
lifecycle. It starts the backend once for the UI lifetime. Queue and rerun
always create a new UUID run ID; repeated runs for one source key are valid.

The UI reads source context and ground truth from the configured source
DuckDB and accepted attempts from the one detour DuckDB. `api.py` remains the
only detour-DB writer. Suspend UI detour-DB reads while a sanctioned Codex run
could push; source-DB reads remain allowed. When idle, reopen the detour DB
read-only and reconcile accepted rows by source key, session metadata, and
attempt ID.

Accepted values and provenance remain authoritative only in DuckDB. Preserve
queued, running, failed, canceled, and process-exit history in the skeleton's
append-only, atomically appended UI run journal so failed/canceled runs survive
a UI restart without manufacturing accepted rows. A run becomes complete
only after its push is accepted and its Codex process exits; an exited run
without an accepted push is failed, and cancellation remains distinct.

The table is variable-at-a-time and includes source identity and all
innerdict-provided draws, the selected `ktp.ai_augment_*` value, its
`ktp.table_1_*` counterpart where this cohort has ground truth, matching
footnotes/arguments, attempt ID/time/status, and queue/cancel/rerun action.
Show the latest attempt in the researcher row and every older attempt in
chronological expandable history. Use a community-compatible custom expansion
rather than requiring AG Grid Enterprise. Filters cover text, cohort, status,
and variable. Below the table, render the selected researcher's full familiar
card through the existing common loaders and `build_cards()`, preserving xlsx
-> Codex -> docx -> ssn order.

### workbook lifecycle and Codex prompt

Keep one named host workbook path and one named AIVM workdir/workbook path as
top-level `ui.py`/API globals. Initialize an absent host workbook as an empty
text file. The host copy is the persistent operator-editable copy between
runs; workbook content is an untrusted learning artifact, not rollout
evidence or ground truth.

At backend initialization, copy the host workbook to its fixed AIVM workdir.
Because the backend stays alive across multiple runs, repeat that host-to-AIVM
copy immediately before every `codex exec`, after any operator edit. Read the
host workbook once for that launch: write those exact bytes to the AIVM file
and include the full same text in the Codex user prompt together with the
loopback OpenAPI URL. Do not truncate, summarize, or maintain a second prompt
version.

When the API copies a sanctioned rollout for a push attempt, also copy the
current AIVM workbook into that attempt directory and atomically publish it to
the host workbook path so it persists into the next execution. Keep the
per-attempt workbook copy for audit. Its transfer does not alter the required
rollout-copy -> appendwatch-report-copy -> copied-report-validation order and
must never make workbook text eligible evidence.

### protected appendwatch deployment

Use a stable control directory below the already mounted macOS path, for
example `$GUEST_MOUNTPOINT/.aivm-control/appendwatch/`. The same bytes are
available to the host backend at the corresponding path below
`$MOUNT_DIR`, while the existing ACL denial on the mount's parent prevents
the guest `ai` user from traversing to it at all.

`deploy.sh` must treat `appendwatch.py` as a required deployment asset.
Its self-install mode must retain that asset beside `provision.sh`, and a
normal deployment must stage a byte-for-byte copy in the protected mounted
directory. Do not place the Python source in the `ai` home or another guest
location the non-root account can inspect, and do not install a second
readable source or bytecode copy elsewhere. Run Python with bytecode
generation disabled.

`provision.sh` must create the Codex sessions directory, lock the mounted
control directory and its files to root in the guest, and install an
`aivm-appendwatch.service` unit which executes the protected source as
root. The unit must be enabled, start on boot, restart on failure, use a
restrictive umask, watch `/home/ai/.codex/sessions`, and atomically maintain
its existing tree report in the protected mounted directory. Provisioning
must start and verify the service before `deploy.sh` opens the `ai` shell.
Do not otherwise redesign the existing private SSH service beyond the
explicit, narrowly restricted API reverse-forwarding change below. The
current manual `run_appendwatch.sh` is not the persistence mechanism.

Deployment verification must prove all of the following before opening the
`ai` shell:

- appendwatch is enabled and active and has emitted a valid initial status;
- root can read the source and status, and the macOS backend user can read
  the status through the host path; and
- an SSH command as `ai` cannot traverse/list/stat/read/copy/execute the
  control directory, source, report, temporary files, or bytecode. The
  account must still have no passwordless sudo.

### appendwatch report contract

Use appendwatch's existing atomically replaced tree report and binary
`OK`/`COMPROMISED` semantics. This task does not require a second report
format, persistent watcher database, report schema migration, or changes to
its monitoring algorithm. The backend helper should parse the versioned copy
of that report, reconstruct the configured rollout's exact relative tree
path, and accept only one unambiguous `OK` file entry. A missing path,
duplicate/ambiguous match, malformed tree, compromised ancestor, global
degradation, or `COMPROMISED` rollout fails closed.

### backend configuration and SSH hand-off

Serving the detour requires `--config config_ai_augment.json`. Parse it once at
startup with the existing `PipelineConfig.from_json()` contract and use its
existing `db_file`, `output_dir`, `output_format`, `pandoc_reference_docx`,
`timezone`, `sample_seed`, and `total_draws` settings. Require and register the
`map_subset_0_to_batch` resource as specified above before deriving cohorts;
missing metadata, unreadable/non-regular CSV content, or a hash mismatch
prevents serving. Accept only `txt` or `docx`; DOCX output also requires a
readable reference DOCX. The configured pipeline DuckDB is context only and
must be opened read-only. Follow the existing detour DB separation pattern:
derive one deterministic sibling DuckDB path from `config.db_file` using a
named detour ID and the `<source-stem>__detour_<detour-id><suffix>` convention.
Open that separate detour DB read/write for all Codex relations and preserve it
across attempts; do not copy or mutate the source DB. Serialize detour-DB write
transactions. A missing or invalid config prevents serving; do not silently
fall back to another path or format.

In production, `ui.py` is the only owner of the current human sanction.
Expose these loopback-only NiceGUI/FastAPI control routes, excluded from its
OpenAPI schema:

- `GET /_control/current`, returning either no sanctioned run or one strict
  object containing `run_id`, `source_key`, `session_id`, and
  `rollout_jsonl`;
- `POST /_control/runs/{run_id}/accepted`, accepting the exact source key,
  session ID, and backend attempt ID and acknowledging only the matching
  current run.

The UI binds to `127.0.0.1:8611`; it is never forwarded to AIVM, so the
control routes require no token/header mechanism. `ui.py` starts the backend
with the control base URL in one named environment setting. When that setting
is present, the API must use the control endpoint exclusively and must never
fall back to `.env` if the UI is unavailable, returns malformed state, or has
no sanction.

At the start of each `/pull` or `/push`, fetch and validate one immutable
control snapshot. Pin it for the whole request; never reread midway and never
combine fields from different snapshots. Require its normalized absolute
rollout path to be below the watched sessions root and to name a rollout
JSONL file; reject traversal, control characters, symlinks/unmonitored paths,
and paths outside that root. Resolve and serve only its exact sanctioned
source key.

Retain the existing repository-root `.env` rollout setting only as an
isolated backend-unit-test override when no control URL is configured:

```dotenv
FASTAPI_DETOUR_ROLLOUT_JSONL=/home/ai/.codex/sessions/YYYY/MM/DD/rollout-....jsonl
```

The real process environment still wins over `.env`. This fallback is not a
production message bus and must not be consulted in control-endpoint mode.

The backend must reuse the existing dedicated identity, known-hosts file,
Lima SSH config, target, and host-mounted appendwatch-report path already
defined by deployment. Expose only the few matching top-level API settings
needed to make those paths testable; do not add a new configuration system or
copy private-key material. Keep defaults aligned with `deploy.sh`, and ensure
a custom `--mount` can supply the corresponding host report path.

Bind the backend to `127.0.0.1:8612`. `deploy.sh` passes one named backend
port into `provision.sh`; do not add a Lima YAML port forward. Preserve the
private SSH service's local forwarding required by VS Code, permit remote TCP
forwarding, and restrict remote listeners with
`PermitListen 127.0.0.1:8612` plus `GatewayPorts no`. The Codex SSH command
must require `ExitOnForwardFailure=yes` and create exactly
`-R 127.0.0.1:8612:127.0.0.1:8612`. Never forward/listen on 8611. Codex uses
`http://127.0.0.1:8612/openapi.json` inside AIVM.

If no run is sanctioned, the control endpoint is unavailable/invalid, or a
required rollout/deployment/SSH/status setting is missing, blank, invalid, or
unreadable, the configured API may still start but both `/pull` and `/push`
fail closed with HTTP 503 and only:

```json
{"detail":"API is not properly configured. Contact the human operator."}
```

Startup and request logs must name the exact missing/invalid setting or
control-state problem and remediation for the operator. The client response,
OpenAPI schema, and access log must not reveal environment names,
host/guest paths, SSH data, control state, appendwatch status, or compromise
reasons. Editing/restarting the `.env` override remains relevant only to
isolated backend tests.

### ordered `/push` integrity gate

FastAPI's automatic body-model validation would happen too early. Accept a
bounded raw JSON request in the route and call
`Submission.model_validate_json(...)` explicitly only after the integrity
gate below. Basic transport limits may run first, but no field/evidence
validation, ground-truth lookup, accepted-submission write, or detailed
validation response may precede the gate.

For each push attempt, use a unique backend-only attempt/version directory
and perform this exact order:

1. Validate and pin the one sanctioned control snapshot plus
   operator/deployment configuration without inspecting the body.
2. SCP the configured rollout from the VM into a temporary file using the
   dedicated key and the same pinned SSH/known-hosts options as `deploy.sh`.
   Build an argv list without `shell=True`; fsync and atomically publish the
   archived rollout, then record its size, SHA-256, and physical line count
   equivalent to `nl -ba`. Count every physical JSONL line in the immutable
   archive, including a final non-newline-terminated line; do not invoke a
   shell command merely to calculate it. After the rollout copy is published,
   copy and publish the current guest workbook as specified above.
3. Copy the current atomic appendwatch tree report from the mounted protected
   host directory into the attempt directory. Fsync it, publish it under a
   unique versioned name, and record its SHA-256. Never inspect the live
   report and never check status before this copy exists.
4. Parse only that copied report. Reconstruct the configured rollout's exact
   relative tree path and require one unambiguous `OK` file entry beneath
   non-compromised ancestors. Missing, duplicated, malformed, degraded,
   unverified, deleted, or `COMPROMISED` status fails closed.
5. Parse the immutable archive and, in one serialized transaction on the
   detour-owned DuckDB, pre-index only complete eligible web provenance into
   the normalized Codex tables specified below. Existing IDs from an earlier
   prefix must have byte-equivalent normalized values; insert only genuinely
   new rows and fail on conflicting reuse. Validate the unique session
   metadata and reconstructed original rollout filename at this stage. A
   completed malformed JSONL record fails closed; because the rollout is live,
   one incomplete final record may be excluded from the index while remaining
   part of the archived hash and physical line count.
6. Read the bounded body, run strict Pydantic validation, and validate every
   submitted excerpt/URL pair solely through parameterized DuckDB queries over
   that index. No ground-truth or configured-pipeline-DB lookup may precede
   this point.
7. After every evidence lookup succeeds, resolve the exact sanctioned source
   key against the configured pipeline DuckDB opened read-only. Require one
   innerdict-owned researcher identity and preserve all of its
   innerdict-provided draw context. In the detour DuckDB, create the final
   Codex output view and materialize `codex_innerdicts` atomically.
8. Only after that transaction succeeds, load ground truth for a
   ground-truth-cohort run, write the accepted response and configured card
   artifact, and mark the attempt accepted. Return normalized AI-augment
   values followed by mapped DOCX ground truth for the 196 cohort; return only
   the normalized accepted values for the 78 no-ground-truth cohort.
9. Consume this run's sanction, reject any further pull/push for it, and send
   the exact run/source/session/attempt acknowledgement to the Control Centre.
   A control-notification failure must not roll back accepted DuckDB output or
   silently re-enable the consumed run; the UI reconciles authoritative
   accepted output when it next becomes idle.

The order above is an invariant, not an optimization: rollout copy first,
guest-workbook archival/publication next, report copy after the rollout copy,
copied-report check after the report copy, then DuckDB provenance indexing,
payload validation, and accepted innerdict/card writes. Workbook transfer must
not move report copying or checking ahead of rollout publication. A rejected
attempt retains its immutable archives and failure-stage manifest, and the
shared database may retain appendwatch-approved normalized provenance, but a
rejected attempt must not add an authoritative accepted output row to
`codex_innerdicts` or create accepted response/card artifacts.

### `/pull`, column mapping, and extended submission contract

Rename the current `COLUMNS` tuple to `DOCX_COLUMNS`; those nine
`ktp.table_1_*` labels remain the ground-truth columns. Add a parallel
`AI_AUGMENT_COLUMNS` tuple in the same semantic order, replacing only the
`ktp.table_1_` prefix with `ktp.ai_augment_`. Keep an explicit ordered mapping
between the two tuples rather than deriving labels at request time.

For each sanctioned run, `/pull` resolves only that exact source key through
the configured source DuckDB's common innerdict tables. Reuse the existing
loaders to emit its xlsx and ssn context in the established JSONL shape, omit
all docx ground truth and prior Codex attempts, and append one synthetic task
record with the selected innerdict-owned first/last names and all nine
AI-augment fields set to null. The backend, not the client, retains the exact
sanctioned source key and every innerdict-provided draw used after acceptance.
The same sanction may retry `/pull` until accepted; after acceptance it is
consumed and no further pull or push is permitted for that run.

The `/push` outer key set requires the eight non-comment entries from
`AI_AUGMENT_COLUMNS` and permits the comments entry as the sole optional key.
Each required field carries its raw AI value and every literal web-result
excerpt used to justify it; every excerpt is paired with the exact URL reported
for its result:

```json
{
  "ktp.ai_augment_researcher_author": {
    "value": "Professor ...",
    "web_search_excerpts": [
      {
        "excerpt": "exact contiguous text copied from one cited result",
        "url": "https://exact.example/result"
      }
    ]
  }
}
```

The example is abbreviated; a real body must contain all eight non-comment
AI-augment keys and may contain `ktp.ai_augment_comments`, with no other keys.
Every required field object has exactly `value` and `web_search_excerpts`;
every evidence object has exactly `excerpt` and `url`. The optional comments
object has exactly one non-blank strict-text `value` and never requires or
accepts web evidence. Every required field has at least one
non-blank evidence item with no duplicate excerpt/URL pair in that field. Use strict types,
`extra="forbid"`, and named permissive bounds derived from the bounded request
body rather than invented web-tool limits. Treat URLs as literal strings for
comparison; URL parsing must not normalize or rewrite what the agent submits.
An excerpt may be reused across fields when it genuinely supports them, but it
must resolve to at least one indexed result with the submitted exact URL in
this attempt archive. When several rows match that exact pair, randomly select
one as the retained provenance row.

Exact means a contiguous substring of one `codex.cite_text`, with no case
folding, whitespace collapsing, Unicode normalization, fuzzy matching, URL
canonicalization, or joining across refs. The URL must then equal that same
row's `codex.ref_url` byte-for-byte as a decoded string.

### eligible Codex evidence and rollout pre-index

The archive must contain exactly one valid `session_meta` record for the
session. Retain the human-specified metadata fields as a compact JSON object.
Reconstruct Codex's original rollout basename from its session ID and payload
timestamp using the configured timezone and require it to equal the configured
guest rollout basename. The same reconstructed filename is expected to recur
across successive attempts in one rollout.

Only a complete direct web dependency chain is eligible. Start from each
top-level `response_item/function_call_output` whose payload has a valid,
globally unique `id` (`fco_id`), non-empty `call_id`, valid response timestamp,
and `output` containing exactly one `input_text` object with one string `text`
value. That output text must contain well-formed citation markers built from
named Unicode prefix/suffix globals such as `cite` and ``. The parser must
isolate each marker's `ref_id` and its complete associated result text into one
`codex.cite_text`, ending before the next result. Never combine refs or text
blocks.

For every such output, require exactly one corresponding
`event_msg/web_search_end` with the same `call_id`. Its `results` must be a
list, and each cited `ref_id` must resolve to exactly one `text_result`. An
eligible ref requires only its non-blank `ref_id`, exact non-blank URL, and the
isolated `codex.cite_text` from the FCO. Preserve domain, snippet, title, and
thumbnail URL when present; these are nullable provenance metadata and have no
downstream validation use. A uniquely linked result without a usable URL is
individually ineligible and skipped without invalidating other refs in the
same output. Then require exactly one earlier
top-level `response_item/function_call` with that `call_id`, a globally unique
`id` (`fc_id`), valid timestamp, `name="run"`, `namespace="web"`, and arguments
that decode to one JSON object containing an eligible `search_query`, `open`,
or `click` action. Store the entire decoded arguments object as DuckDB JSON.

The chain is fail-closed: malformed/duplicate IDs, a duplicate or missing
event/call, multiple text blocks, unsupported required result shape, malformed
arguments, a citation absent or duplicated in event results, or a ref section
that cannot be isolated unambiguously rejects indexing. Output records without
citation markers and unrelated records are simply ineligible. Assistant,
reasoning, `exec`/`custom_tool_call`, shell output, API response, submitted
file, rollout-scanning, orchestration-status, event-only, and orphan text never
become evidence, including an exec record that mentions `tools.web__run`.

Put the parsing/section-isolation helpers in detour-local `codex_parse.py`,
following `docx_parse.py`'s separation between source extraction and
human-readable Markdown rendering; do not copy that large parser or modify it.
`api.py` supplies structured rollout/evidence rows, while `codex_parse.py`
isolates cite sections and renders the Codex footnote/arguments/comment text shown
in the human sample. Validation lookups and accepted flat-row construction
remain parameterized DuckDB SQL.

### detour DuckDB schema

Define all table/column labels as top-level `api.py` globals and create these
exact normalized relations in the detour DuckDB. Follow the existing DuckDB
relation/materialization conventions. The human section's `pkey` entries mean
primary-key columns, not literal `pkey` labels; name each one `id` and make it
stable and unique. Use timestamp-capable values for timestamps, text for
IDs/text, and DuckDB `JSON` for `codex.fc_arguments`. Do not introduce a
parallel serialization convention:

- `codex_fc`, six columns: `id`, `codex.fc_timestamp`, `codex.fc_id`,
  `codex.fc_name`, `codex.fc_namespace`, `codex.fc_arguments`;
- `codex_fco`, three columns: `id`, `codex.fco_timestamp`, `codex.fco_id`;
- `codex_calls`, five columns: `id`, `codex.call_id`, `codex.fc_id`,
  `codex.fco_id`, `codex.rollout_filename`; and
- `codex_turn_ref`, nine columns: `id`, `codex.ref_id`,
  `codex.call_id`, `codex.ref_domain`, `codex.ref_snippet`,
  `codex.ref_thumbnail_url`, `codex.ref_title`, `codex.ref_url`,
  `codex.cite_text`.

In `codex_turn_ref`, `codex.ref_id`, `codex.call_id`, `codex.ref_url`, and
`codex.cite_text` are required. Domain, snippet, thumbnail URL, and title are
nullable because the web tool does not guarantee those metadata fields.

`codex.fc_id`, `codex.fco_id`, and `codex.call_id` are individually unique;
`codex_turn_ref` is unique on `(codex.call_id, codex.ref_id)`. Enforce the
relationships using the same SQL-first style as step 08, including explicit
validation where DuckDB does not enforce a desired cross-table relationship.
Insert all four relations in one transaction and query them back to prove row
counts and uniqueness before body validation.
The detour database is the cumulative canonical representation of the
appendwatch-approved rollout prefixes seen so far. Scope lookups to the current
reconstructed rollout filename and serialize pushes so no later prefix can
enter the database during validation of the current archive. Do not create
these relations in the configured pipeline database.

### DuckDB excerpt and URL validation

For each submitted evidence item, issue one parameterized DuckDB query that
searches `codex_turn_ref` for the exact excerpt as a contiguous substring of
`codex.cite_text`. Do not interpolate excerpts or URLs into SQL and do not
perform a second Python-side rollout scan.

- Zero matching rows produces the common generic validation failure.
- From all excerpt-matching rows, retain only rows whose `codex.ref_url`
  exactly equals the submitted URL; zero remaining rows produces the common
  generic validation failure.
- Keep a visibly named top-level `ALLOW_MULTIPLE_EVIDENCE_MATCHES` switch set
  to true. With that policy enabled, randomly select one row when multiple
  exact excerpt/URL rows remain using a dedicated RNG reseeded immediately
  before evidence validation from the required config's `sample_seed`; do not
  prefer search, view, open, or click provenance. A single remaining row is
  selected directly. Candidate ordering and submission traversal must remain
  explicit and stable so the same body against a hash-identical rollout
  selects the same provenance rows regardless of prior push history.

The lookup covers the full archived prefix for that attempt, including
evidence from earlier cycles in the same rollout. Retain the randomly selected
row, linked call arguments, FCO timestamp, and submitted field/item order for
accepted-row construction and footnote numbering.

### accepted Codex output view and innerdict contract

After validation, resolve the exact sanctioned source key and obtain its
first/last names and complete draw context only from the common innerdict JSONL
loaded for that key. Never accept these identity values from the push body or
source them from the release map or card-partition relation. The configured
pipeline DuckDB remains read-only. In the detour DuckDB, append one accepted
flat row to a narrowly named backing table and expose it through a
`codex_output` view whose columns follow this order:

1. `ktp.source_key`;
2. `ktp.filename`, containing the reconstructed original rollout basename;
3. `ktp.fragment`, containing this attempt archive's physical line count;
4. `ktp.fragment_type`, always the existing `line_number` enum value;
5. `ktp.draw_number`, `ktp.first_name`, and `ktp.last_name`;
6. `ktp.ai_augment_attempt_id` and `ktp.ai_augment_session_metadata`;
7. the eight non-comment `ktp.ai_augment_*` values in
   `AI_AUGMENT_EVIDENCE_COLUMNS` order, followed immediately by
   `ktp.ai_augment_comments` after `ktp.ai_augment_links_`; and
8. `ktp.ai_augment_footnotes` and `ktp.ai_augment_footnote_arguments`.

Define every detour-owned label and the backing-table/output-view names at the
top of `api.py`. One accepted push creates one output row. Enforce uniqueness
of attempt ID and of `(ktp.filename, ktp.fragment)`, but do not make
`ktp.source_key` unique: the same researcher may have multiple accepted rows,
including several sections with one rollout filename and different line-count
fragments.

Materialize `codex_innerdicts` from all accepted `codex_output` rows using the
same strict common two-column contract as xlsx/docx/ssn innerdicts:
`name_key VARCHAR` plus `innerdicts VARCHAR` containing ordered JSONL records.
Follow step 08's output-view/materialization sequence and use the existing
materialization helper plus a detour-local matching procedure whose dataset ID
field is `ktp.source_key`; do not modify the main schema, procedure, or
data-model modules. This cumulative table is authoritative for downstream
AI-augmentation rows. Rebuild it in the same transaction that adds an accepted
output row so a failure cannot expose a partial authoritative state.

### footnotes, arguments, and card rendering

Assign footnote numbers globally in the eight non-comment
`AI_AUGMENT_COLUMNS` entries' order and then in each field's submitted
evidence-list order. The submitted `value` remains raw text;
for each footnoted AI value, the detour-local parser/renderer constructs the
human sample's `**AI-generated text**: "<value>"` presentation and appends the
resulting superscript marker programmatically after the closing quote. The
parameterized lookup supplies the matched cite text and
exact position; the detour-local parser/renderer then
follows `docx_parse.py`'s Markdown conventions to show a named-global amount of
context before and after the match. Clamp that context to the excerpt's side
of the selected ref's citation marker so it never enters a neighboring ref or
the marker/header across that boundary. In rendered Markdown only, replace
every source line break with one space, remove Codex citation-marker markup
while retaining its visible label text, and escape all Markdown punctuation in
the context and excerpt before applying the renderer-owned bold wrapper to the
submitted excerpt. Preserve the exact raw `codex.cite_text` in DuckDB. Add the
FCO timestamp and result URL. Follow the human sample's footnote suffix exactly:
`retrieved from web run tool using arguments^N^ on ...`, where `N` is the
same global ordinal used by the corresponding argument-list item. Render the
comments value through the same helper in the sample's exact
`- **AI-generated text**: "<comment>" (<attempt timestamp>)` form, rather than
assembling value, footnote, or comment Markdown in the route. Its output column
and rendered card field appear immediately after `ktp.ai_augment_links_` and
before the footnotes fields.

`ktp.ai_augment_footnote_arguments` is a numbered list aligned one-to-one with
the footnotes and their `arguments^N^` references. Search-call items show the
raw decoded `codex.fc_arguments`. For `open` and `click`, inspect every action
object independently. When its string `ref_id` matches the existing Codex
turn-ref pattern and resolves to exactly one call-scoped `codex_turn_ref` row
in the current locked rollout prefix, render a full action object that
preserves that `ref_id`, adds its indexed `codex.ref_url` as `url`, and
preserves properties such as a click ID. Apply this independently to every
item in a multi-item action. If the turn-ref is absent or ambiguous, or the
`ref_id` is already a URL or any other non-turn value, leave that action
object unchanged. This is best-effort display enrichment, not an acceptance
condition; do not substitute the selected footnote output URL for an input
ref's own URL. Repetition is intentional when several footnotes come from one
call. Keep the raw arguments unchanged in normalized machine-readable
provenance; the footnotes and argument list are the human-readable rendering
shown in the sample.

For the selected namekey, load existing xlsx, docx, and ssn innerdicts from the
configured database read-only and load every accumulated Codex innerdict from
the detour database using the same common-innerdict loaders/procedures used by
pipeline initialization. Reuse `build_cards()` and `write_cards_zip()` rather
than forking step 10's renderer. Preserve the established innerdict order but
insert all Codex sections between xlsx and docx sections. Each Codex record
therefore renders through the existing generic card loop as its own
`#### ktp.filename` section, including its explicit attempt ID and line-count
fragment.

Read TXT versus DOCX and the DOCX reference path from the required config.
Pass those settings to the existing card ZIP writer and use the attempt ID in
the ZIP name so a previous report is never overwritten; record its filename
and SHA-256 in the attempt manifest. The accepted attempt contains
the archived rollout, copied appendwatch report, their hashes, line count,
stage/result manifest, archived workbook, and `response.jsonl`. For a
ground-truth-cohort run, write two NDJSON lines: normalized AI-augment values
first and mapped DOCX ground truth second. For a no-ground-truth-cohort run,
write only the normalized accepted AI-augment values; never manufacture an
empty ground-truth line.

### client-visible failures

Any structural, appendwatch-integrity, rollout/index, URL, eligibility, exact-
excerpt, output-view, innerdict, or render failure rejects the submission,
does not return ground truth, and creates no accepted response/card or Codex
innerdict row. With the current allow-multiple policy enabled, current
failures return only:

```json
{
  "detail": "Submission did not pass validation. Recheck every evidence excerpt and URL before retrying. Copy each excerpt verbatim as one contiguous span from the cited web-tool output, preserving every character—including repeated spaces, line breaks, punctuation, capitalization, and Unicode typography—and copy its associated URL exactly. Do not paraphrase, normalize, retype, or join separated text."
}
```

This universal guidance may explain the submission contract but must not name
the failed field or value, supply expected source text, or expose validation
order, rollout/index state, or persistence details.

Keep the existing `MultipleEvidenceMatches` exception, detailed message, and
HTTP handler in place. The named allow-multiple switch visibly disables that
rejection branch; setting it false makes the selector raise the retained
exception. Keep its original rejection test intact and mark it skipped with
the current multiple-match policy as the reason.

The backend log must include attempt ID, failed stage, field name where
applicable, and an actionable reason for the operator without leaking secrets.
Log the exact submitted excerpt and URL for evidence failures and the exact
rejected input (or an explicit missing marker) for Pydantic failures, using a
representation that escapes line breaks and control characters. Keep those
values out of the generic client response. Do not let FastAPI's default
detailed Pydantic error body bypass this policy.

### implementation tests and acceptance

Keep the existing appendwatch regression suite and add focused tests for:

- protected asset staging/self-install, systemd enable/start/restart,
  restrictive paths/modes, service verification before the `ai` shell, and
  negative source/report access probes as `ai`;
- absent/malformed/unavailable control sanction producing the same generic 503
  for both `/pull` and `/push`, exclusive control-endpoint mode, exact snapshot
  pinning, one acceptance acknowledgement, consumed-sanction behavior, and the
  isolated no-control-URL `.env` rollout fallback used only by backend tests;
- required `--config config_ai_augment.json`, `PipelineConfig.from_json()`,
  detour-local enforcement and repository-helper registration of
  `map_subset_0_to_batch`, configured SHA-256 verification, malformed/missing
  map rejection, read-only access to the pipeline DuckDB, TXT/DOCX selection,
  reference-DOCX handling, deterministic sibling detour-DB path, and
  before/after proof of no writes to the configured source DB;
- innerdict-only source-key/name/draw loading, preservation of all contracted
  draws, release-map classification of only those draws, source-key joins to
  card-partition flags, explicit Kanatzidis exclusion, disjoint exact cohort
  counts of 196 and 78/274 total, and startup failure on invariant drift;
- sanctioned dynamic `/pull` output containing only selected xlsx/ssn context
  plus one null-AI task record, with docx ground truth and prior Codex attempts
  absent and retries allowed only until the run is accepted;
- an instrumented assertion of the exact sequence SCP -> status copy ->
  copied-status check -> rollout line count/index transaction -> Pydantic/SQL
  lookup -> output view/innerdict -> ground truth/card, while separately
  proving the workbook is archived/published after rollout publication without
  moving report copying or validation ahead of the rollout;
- strict SCP argv/known-hosts/key use, path confinement, unique atomic
  archives, and custom-mount connection settings;
- copied-report parsing for nested exact paths, OK, compromised ancestors or
  rollout, global degradation, missing/duplicate paths, and malformed trees;
- `DOCX_COLUMNS`/`AI_AUGMENT_COLUMNS` mapping, `/pull` identity, strict eight-
  field value/evidence/URL models, the optional evidence-free comments model,
  absent or duplicate evidence, and exact Unicode/whitespace/URL behavior;
- unique session metadata and reconstructed basename, physical line counting,
  one tolerated incomplete trailing record, and conflicting cumulative-prefix
  rows failing closed;
- the exact four normalized table column contracts and transactionally linked
  direct search/open/click FCO -> event results -> FC records, including
  citation parsing and complete per-ref `codex.cite_text`;
- missing, duplicate, cross-ref, event-only, assistant, reasoning, custom-exec,
  shell-output, rollout-scanning, orphan, multi-block, malformed-ID/argument,
  and unsupported-result cases;
- parameterized SQL lookup, zero/exact/multiple substring matches, exact URL
  filtering before random candidate selection, generic failures, the retained
  but skipped multiple-match rejection test, and no ground-truth leak;
- cumulative accepted output rows where one namekey has multiple sections with
  the same rollout filename, distinct line-count fragments and attempt IDs,
  plus exact common-contract `codex_innerdicts` JSONL ordering;
- exact AI-generated value/comment wrappers, footnote numbering, one-line
  marker-bounded and Markdown-escaped context, bold excerpt, web-run
  wording/argument cross-reference/FCO time/URL, aligned raw argument lists,
  xlsx -> Codex -> docx -> ssn card order,
  TXT and DOCX ZIPs, archive hashes, two-line ground-truth success NDJSON,
  one-line no-ground-truth success NDJSON, and no accepted artifacts on
  rejection;
- focused Control Centre tests for serial queueing, cancel/rerun/new UUIDs,
  append-only journal replay, accepted-row reconciliation, detour-read
  suspension while a push is possible, workbook round trips/full prompt
  inclusion, backend lifetime, loopback-only ports, and the exact single API
  reverse tunnel without forwarding the control port; and
- an E2E in the existing `test_api.py` style using the real July direct-web
  rollout with fixed submitted excerpts, URLs, and expected FC/FCO/call/ref
  identities. Assert exact DuckDB rows and card sections, and prove a one-
  character excerpt change and an exact-URL change are rejected before ground
  truth or accepted artifacts. Do not derive the submitted fixture from the
  production parser under test.

Use mocks/fakes for host SCP and narrow provisioning checks, plus a small
sanitized direct-web rollout fixture. Reuse the current E2E helper/flow as much
as possible to reduce review fatigue. Keep existing appendwatch tests as the
monitoring regression proof rather than adding decorative source-text tests.
Implement production code and tests only within the surgical boundary above.
