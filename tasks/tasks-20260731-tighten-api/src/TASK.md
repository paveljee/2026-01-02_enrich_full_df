## human written - ai never touches this
### environment
```bash
([ "$PWD" = "/Volumes/home/aicode/2026-01-02_enrich_full_df" ] || exit 1)
TASK_DIR="$PWD/tasks/tasks-20260731-tighten-api"
TASK="$TASK_DIR/src/TASK.md"
WORK="$TASK_DIR/var/WORK.md"
SPECS="$TASK_DIR/build/SPECS.ipynb"
```

## after each compaction
> [!IMPORTANT]
> Immediately after compaction, refresh TASK/WORK in full.

## always
> [!IMPORTANT]
> Remember to keep WORK current at all times - compaction can happen anytime.
> WORK should contain sufficient context for what we're currently doing.
> The TASK/WORK combo should stand alone at all times.
> WORK should never carry any stale baggage.

### prerequisites and setup
AI must interpret how it understood this TASK
as prescribed in `$TASK_DIR/Makefile`,
whose `make validate` will be used to verify AI's work.

> [!IMPORTANT]
> When writing SPECS, AI should know:
> - The procedure is called atomic requirement-to-evidence mapping.
> - One Markdown cell represents one requirement unit:
>   - A requirement unit is the smallest contiguous set of TASK lines expressing one independently verifiable behavior.
>   - A unit may span multiple contiguous TASK lines.
> - An evidence (code) cell must prove only its preceding requirement unit:
>   - Exactly one evidence cell must immediately follow each Markdown cell.
>   - Its task_lines must exactly match that Markdown cell’s source lines.
>   - A code cell must not define paths, test IDs, setup, or assertions for other units.
>   - No shared “miscellaneous evidence” code cells or consecutive code cells.

### actual task

```yaml
feature:
  description:
    name: "KTP HCR Detour: AI Augmentation"
    pixi: detour-ai-augment
  background:  # human-curated
    readme: src/detours/detour_ai_augment/README.md
    rdf:   src/detours/detour_ai_augment/assets/hcr_augment_agent_architecture.drawrdf.ttl
    # plus, see below
# scenarios: []
```

#### background
As given in `readme`,
the feature's infrastructure
consists of five main nodes:

- Human Operator
- Control Centre
- Inference API
- Agent Runtime
- Backend

Useful-to-know
aliases and examples:

- Human Operator,
  e.g., **the user**
- Control Centre
  is operationally synonymous with
  **Host Machine**,
  e.g., a Mac16,12
  (macOS arm64)
- Agent Runtime
  is operationally synonymous with
  **Guest Machine**,
  e.g., a Lima AIVM
  (Ubuntu arm64)
- Inference API,
  e.g., via OpenAI ChatGPT login
- Backend,
  e.g., FastAPI

As given in `readme`,

- Human Operator
  has 4 connections
- Control Centre
  has 3 connections
- Inference API
  has 2 connections
- Agent Runtime
  has 4 connections
- Backend
  has 3 connections

As given in `readme`,
these connections reuse
the following 8 interfaces:

- Human Operator <-> Control Centre
- Human Operator <-> Inference API
- Human Operator <-> Agent Runtime
- Human Operator <-> Backend
- Control Centre <-> Agent Runtime
- Control Centre <-> Backend
- Inference API <-> Agent Runtime
- Agent Runtime <-> Backend

Therefore,
the number of connections is
twice the number of interfaces.

It is helpful to note that:
- Human Operator
  has connections with all 4 remaining nodes,
  reusing 4 of 8 interfaces
- Agent Runtime
  has connections with all 4 remaining nodes,
  reusing 4 of 8 interfaces
- Control Centre
  has connections with 3 nodes,
  except Inference API,
  reusing 3 of 8 interfaces
- Backend
  has connections with 3 nodes,
  except Inference API,
  reusing 3 of 8 interfaces
- Inference API
  has connections with 2 nodes,
  namely Agent Runtime and
  (optionally) Human Operator,
  reusing 2 of 8 interfaces.

We proceed to describing
the feature lifecycle
from two perspectives:

1. Describe each interface
1. Describe how each node uses each interface

But prior to proceeding,
there is room to reduce complexity:

- Human Operator may be omitted as a node
  because we do not prescribe the behaviour
  of the human operator in this description
  of the feature behaviour.
- Inference API, in this set-up,
  only interfaces with Agent Runtime, and
  therefore it may be omitted as a node;
  it will be sufficient to describe the
  Inference API – Agent Runtime interface
  and how Agent Runtime uses it, as
  Inference API is not controlled or
  described in this feature description.
- Note that interfaces are two-way,
  so they may as well be grouped
  under the dominating node, or the
  node "owning" the interface may
  be designated.

Therefore, this is tentatively reduced
to, ordered from higher to lower priority
in the feature's lifecycle:

- Part 1: Backend-owned Interfaces
  - 1.1. Backend <-> Control Centre
  - 1.2. Backend <-> Agent Runtime
  - 1.3. Backend <-> Human Operator
- Part 2: Control Centre-owned Interfaces
  - 2.1. Control Centre <-> Human Operator
  - 2.2. Control Centre <-> Agent Runtime
- Part 3: Agent Runtime-owned Interfaces
  - 3.1. Agent Runtime <-> Inference API
  - 3.2. Agent Runtime <-> Human Operator
- Omitted:
  - Human Operator <-> Inference API

As this is insufficient to
fully describe the feature's lifecycle,
several lower-level nodes need to be noted
and the interfaces prescribed:

- config file\* (`PipelineConfig`, `AiAugmentDetourConfig`). interfaces with human (omitted), with backend (read-only, owned by backend), with control centre (read-only, owned by control centre).
- main db (`PipelineConfig.db_file`). interfaces with human (omitted), with config file (read-only, owned by config file), with control centre (read-only, owned by control centre).
- output dir (`PipelineConfig.output_dir`). interfaces with config file (read-only, owned by config file), with backend (write, owned by backend).
- rollout CAS (`AiAugmentDetourConfig.rollout_cas_dir`). interfaces with config file (read-only, owned by config file), with backend (write, owned by backend).
- detour db (`AiAugmentBackendContext.detour_db_path`). interfaces with human (omitted), with config file (read-only, owned by config file), with backend (owned by backend).
- http replay jsonl (`AiAugmentBackendContext.replay_log`). interfaces with config (read-only, owned by config), with backend (write, owned by backend).

\* Note that for this detour,
the main pipeline machinery
(`src/helpers/config.py::PipelineConfig`)
is supported with custom fields in `config_ai_augment.json`
and supporting code, owned by the detour
(`src/detours/detour_ai_augment/src/backend/helpers/data_models/ai_augment_config.py::AiAugmentDetourConfig`).
This is reflective of
the **Architectural Rule** in this repo
that **sets** that detour logic is owned by the detour
and must not spill over onto the main pipeline.
For the purpose of this breakdown,
it is helpful to separate the fields offered
in the main pipeline machinery vs. fields
the detour introduces for itself.

Further,
it is important to mention internal interfacing
that happens between inner components of
the detour-owned nodes:

- Backend <-> Backend
- Control Centre <-> Control Centre
- Agent Runtime <-> Agent Runtime

It is therefore helpful to revise and extend the above breakdown:

- Part 1: Backend-owned Interfaces
  - I001.01. Backend <-> `PipelineConfig` (read-only)
  - I001.02. Backend <-> `AiAugmentDetourConfig` (read-only)
  - I001.03. Backend <-> Detour DB
  - I001.04. Backend <-> Detour output directory
  - I001.05. Backend <-> Detour replay JSONL
  - I001.06. Backend <-> Rollout CAS
  - I001.07. Backend <-> Control Centre
  - I001.08. Backend <-> Agent Runtime
  - I001.09. Backend <-> Human Operator
  - I001.10. Backend <-> Backend
- Part 2: Control Centre-owned Interfaces
  - I002.01. Control Centre <-> `PipelineConfig` (read-only)
  - I002.02. Control Centre <-> `AiAugmentDetourConfig` (read-only)
  - I002.03. Control Centre <-> Main DB (read-only)
  - I002.04. Control Centre <-> Human Operator
  - I002.05. Control Centre <-> Agent Runtime
  - I002.06. Control Centre <-> Control Centre
- Part 3: Agent Runtime-owned Interfaces
  - I003.01. Agent Runtime <-> Human Operator
  - I003.02. Agent Runtime <-> Inference API
  - I003.03. Agent Runtime <-> Agent Runtime
- Omitted:
  - Most Human Operator's interfaces
  - `PipelineConfig` <-> Main DB
    (outside of detour scope,
    as this is prescribed in the main pipeline)
  - `PipelineConfig` <-> Detour output directory
    (outside of detour scope,
    as this is prescribed in the main pipeline)
  - Interfaces between
    lower-level detour-owned nodes
    (as all of them are fully prescribed
    as part of the above-listed interfaces)

Total:
  19 prescribed interfaces

It is also helpful to
illustrate the **communication methods**
that may be employed by the interfaces:

- HTTP protocol
- SSH protocol
- Non-interactive CLI
- REPL CLI/chat
- GUI
- SDK
- Config/env vars
- Disk I/O
- Unix shell

#### scenarios
##### I001.01. Backend <-> `PipelineConfig` (read-only)
Human Operator — interfaces with Control Centre via CLI/HTTP: `pixi run dashboard`; `http://127.0.0.1:8611`

##### I001.02. Backend <-> `AiAugmentDetourConfig` (read-only)

##### I001.03. Backend <-> Detour DB
Backend — interfaces with detour DB via SQL/DuckDB API: derived detour `.duckdb` opened read/write

##### I001.04. Backend <-> Detour output directory
Backend — interfaces with filesystem via POSIX: configured `output_dir`

##### I001.05. Backend <-> Detour replay JSONL
Backend — interfaces with filesystem via POSIX: authoritative `detour_ai_augment_backend_api_replay_log`

##### I001.06. Backend <-> Rollout CAS
Backend — interfaces with filesystem via POSIX: configured `rollout_cas_dir`

##### I001.07. Backend <-> Control Centre
Control Centre — interfaces with Backend via HTTP: `POST /_control/push`; `GET /_control/pull`

##### I001.08. Backend <-> Agent Runtime
Agent Runtime — interfaces with Backend via HTTP: `GET /openapi.json`; `GET /pull`; `POST /push`

##### I001.09. Backend <-> Human Operator

##### I001.10. Backend <-> Backend
Backend — interfaces with itself via in-process HTTP/ASGI: `PUT /_control/commit` 

##### I002.01. Control Centre <-> `PipelineConfig` (read-only)

##### I002.02. Control Centre <-> `AiAugmentDetourConfig` (read-only)

##### I002.03. Control Centre <-> Main DB (read-only)
Control Centre — interfaces with main DB via SQL/DuckDB API: configured `db_file`, `read_only=True`

##### I002.04. Control Centre <-> Human Operator

##### I002.05. Control Centre <-> Agent Runtime
Control Centre — interfaces with Agent Runtime via SSH: `ssh -F ~/.lima/aivm/ssh.config … aivm-ai`

##### I002.06. Control Centre <-> Control Centre

##### I003.01. Agent Runtime <-> Human Operator
Agent Runtime — interfaces with guest OS via POSIX: `/home/ai/workdir`; `/home/ai/.codex/sessions`

##### I003.02. Agent Runtime <-> Inference API

##### I003.03. Agent Runtime <-> Agent Runtime

<!--- aislop for review; initially in response to mine, "for a minute, explain me how do you understand currently detour ai augment feature *should* work? in given-when-then scenarios pls. in whole scope."

1. Source population

Given the configured read-only main database and release-map configuration,  
When the dashboard starts,  
Then it reads `ktp.innerdicts`, groups researchers by `ktp.namekey`, and derives exactly 307 researcher rows, deterministic `rnd` values 1–307, draw numbers, cohorts, and ineligibility categories.

1. Dashboard source reads

Given the dashboard needs to construct the 307-row researcher population or sanction a researcher,  
When it loads source information,  
Then the dashboard reads the main database and Lima/deploy configuration read-only. It does not access the detour DuckDB or authoritative JSONL.

1. Backend durable storage

Given detour state must be stored, queried, or reconstructed,  
When any detour-DB or authoritative-log operation occurs,  
Then only `api.py` reads or writes the detour DuckDB and only `api.py` writes the authoritative JSONL.

1. Dashboard–backend communication

Given the dashboard needs to sanction a run or observe durable run state,  
When it communicates with `api.py`,  
Then it sends source/run context through authenticated control push and obtains sanctions, attempts, results, history, and cards through authenticated control pull. It never communicates by opening backend-owned storage directly.

1. Dashboard startup

Given no run has been selected,  
When the dashboard starts,  
Then all 307 researchers appear, including ineligible researchers. Ineligible rows show their category and cannot be executed; eligible rows are ready.

1. Sanctioning a researcher

Given the operator queues an eligible researcher,  
When the dashboard discovers the Codex session and rollout,  
Then it sends an idempotent authenticated control push containing the run identity, `ktp.namekey`, relevant source context, session/rollout metadata, and required Lima-derived information.

1. Public pull before sanction

Given there is no active sanction,  
When an agent calls `GET /pull`,  
Then it receives the generic 503 `CONFIGURATION_ERROR_DETAIL`. No internal reason is disclosed.

1. Public pull after sanction

Given a valid sanction has committed,  
When the agent calls `GET /pull`,  
Then it receives that researcher’s source JSONL and one annotation row with all AI-augmentation fields null. Ground truth is omitted.

1. Stable pull

Given the sanctioned researcher has not yet been accepted,  
When `/pull` is called repeatedly,  
Then it returns the same researcher and, after a rejected push, the applicable retry guidance.

1. Multiple researchers in one rollout

Given one cumulative Codex rollout,  
When one researcher is accepted and the operator sanctions another,  
Then another pull/push cycle may occur in the same rollout. Each run and attempt remains distinct by run ID, attempt ID, researcher `ktp.namekey`, session, and rollout line count.

1. First submission contract

Given this is the first Pydantic-valid submission for a run,  
When the agent calls `POST /push`,  
Then the simple legacy submission model is used: plain values plus evidence, language included like every other field, comments optional, and no standardized values requested.

1. Successful first submission

Given every required excerpt and URL passes exact validation,  
When the first submission is accepted,  
Then standardized fields are explicitly initialized to appropriate `NR` values, and the full standardized model is what ultimately gets stored.

1. Rollout evidence eligibility

Given a submitted excerpt,  
When validation begins,  
Then the backend first finds it as plain text within a rollout `function_call_output`, parses that event, requires a valid turn-reference marker, and follows the complete call chain using `call_id`.

1. Web-tool chain

Given a candidate turn reference,  
When its provenance is reconstructed,  
Then the original call must be `name="run", namespace="web"`, its queries and `web_search_end` results must agree, and open/click references are resolved within the same `call_id`.

1. Evidence record construction

Given a fully valid chain,  
When an evidence item is indexed,  
Then the backend constructs a de novo structured record containing response timestamp, call identity, query text, result URL/ref ID/domain/snippet/thumbnail where present, and the actual cited text.

1. Exact acceptance rule

Given a submitted evidence item,  
When its excerpt is a case-sensitive, character-for-character contiguous span and its URL exactly equals the indexed URL,  
Then it is `v1_exact`. Only this rule can accept evidence.

1. Diagnostic near matching

Given exact matching fails and `codex_match=2`,  
When the normalized submitted token sequence occurs contiguously in one valid citation section under the same URL,  
Then it is `v2_near`. The XLSX-v2 Unicode-aware tokenization primitive is reused exactly, but this never accepts the evidence.

1. Unmatched evidence

Given neither exact nor diagnostic matching succeeds,  
When assessment completes,  
Then the item is `unmatched` and remains rejected.

1. Exhaustive assessment

Given several submitted evidence items,  
When one fails,  
Then validation continues through every item. The response reports aggregate verified counts and every failed field/index without revealing candidate text, call IDs, ref IDs, SQL, or internal matching mechanics.

1. Retry baseline

Given the first Pydantic-valid submission is evidence-invalid,  
When assessment completes,  
Then an immutable retry baseline is committed for that run. It preserves every value, evidence item, URL, outcome, session, researcher namekey, and attempt audit.

1. Standardized retry contract

Given a retry baseline exists,  
When the agent retries,  
Then it must submit the complete `StandardizedSubmission`; the response explains that standardized values are now required and includes the copyable Pydantic schema and full example.

1. Retry immutability

Given baseline items were exact,  
When a retry arrives,  
Then exact fields/items, values, excerpts, URLs, and evidence counts must remain unchanged.

1. Near-match retry

Given an item was `v2_near`,  
When it is retried,  
Then its URL and normalized token sequence must remain unchanged. Only formatting differences normalized away may be corrected, and the corrected raw excerpt must still pass exact v1 matching before acceptance.

1. Unmatched retry and withdrawal

Given an item was unmatched,  
When retried,  
Then it may be replaced freely and reclassified. It may instead be explicitly withdrawn using the structured attestation model, but only if it remains unmatched; near matches cannot be withdrawn, and the field must retain at least one exact supporting item.

1. Private commit

Given public push processing has produced its complete outcome,  
When backend state is committed,  
Then the backend invokes its unmounted in-process `PUT /_control/commit`. That body contains the public request, response outcome, appendwatch snapshot, workbook snapshot, rollout CAS reference, retry/audit metadata, and everything necessary for replay.

1. Authoritative ordering

Given one public push transaction,  
When it completes,  
Then the private PUT record is durably appended and projected first; the public POST record is appended afterwards. The external push record therefore always follows its corresponding commit record.

1. Authoritative storage

Given any dashboard control push, public push, or private commit,  
When the backend has completed the response,  
Then it appends one literal schema-v2 `HttpRequestLogRecord`, flushes and fsyncs it before sending the response. Pulls are read-only and are not logged.

1. Log fields

Given a backend-generated HTTP log record,  
When serialized,  
Then it includes schema-v2 `port` and `ready_to_respond_at_unix_usec`, sets `received_at_unix_usec` to null, and otherwise follows the exact shared `HttpRequestLogRecord` contract.

1. Rollout CAS

Given a rollout snapshot is needed,  
When it is archived,  
Then only that rollout enters the configured SHA-256 content-addressed store. `rollout_cas_dir` must come from `config_ai_augment.json`; it is never guessed.

1. Detour database projection

Given committed authoritative records,  
When processing succeeds,  
Then `api.py` projects them into the ephemeral detour DuckDB. Accepted output, retry state, attempts, sanctions, cards, and control history are all derived from this projection.

1. Accepted submission

Given every required field has only exact evidence and all retry obligations are satisfied,  
When the private commit succeeds,  
Then accepted values and standardized values are materialized, a researcher card becomes available, a `PUSH_ACCEPTED` event is recorded, and the sanction is consumed.

1. Post-acceptance pull

Given acceptance consumed the sanction,  
When `/pull` is called again before another sanction,  
Then it returns the same generic no-sanction 503 response.

1. Researcher cards

Given accepted attempts exist,  
When the dashboard requests a card through control pull,  
Then `api.py` renders it from the source context and detour projection. The dashboard loads cards lazily and caches them; large cards are not transferred until clicked.

1. Card presentation

Given card content is rendered as text, DOCX, or NiceGUI Markdown,  
When field names or filenames contain underscores,  
Then literal labels are enclosed in backticks. Plain and standardized values are adjacent, empty `NA`/`NR` standardized values are hidden, comments appear immediately after links, and footnotes/arguments are rendered safely and compactly.

1. Dashboard truth

Given the dashboard is running or restarted,  
When it refreshes,  
Then attempts, sanctions, accepted results, and run events come from authenticated control pull—not a local journal, attempt directory, or UI memory.

1. Persistent attempt history

Given any queued, running, failed, canceled, configuration-failed, rejected, or accepted attempt was shown,  
When the dashboard restarts or the detour DB is rebuilt,  
Then the same history is reconstructed from the authoritative log and remains visible.

1. External activity

Given a run was initiated outside the dashboard through the same control API,  
When the dashboard polls control pull,  
Then it discovers that run. If Codex is already busy, dashboard actions offer queueing rather than starting another process.

1. Concurrency and idempotency

Given one control/public push is active,  
When another push arrives,  
Then the shared non-waiting gate immediately returns and logs BUSY. Repeating an already committed idempotency key observes the prior result without duplicating state.

1. Crash recovery

Given the backend crashes before append,  
When restarted,  
Then nothing was committed. Given it crashes after fsync but before projection/response, replay applies the committed record exactly once.

1. Replay integrity

Given backend startup,  
When the configured authoritative log and detour projection are inspected,  
Then a behind projection catches up in line order. A conflicting prefix, invalid CAS reference, edited log, or corrupt projected state fails startup loudly.

1. Incomplete tail repair

Given the JSONL ends with an incomplete final line,  
When startup detects it,  
Then the operator is explicitly prompted before truncation. Refusal or failed repair leaves the log untouched and startup fails.

1. Single writer

Given one backend already owns the authoritative log,  
When a second backend starts against it,  
Then process locking makes the second backend fail.

1. Public error privacy

Given any internal backend/configuration failure,  
When responding to the public agent,  
Then only `CONFIGURATION_ERROR_DETAIL` is exposed. Operator logs instead show the concrete route, stage, line/gate, failing value, and underlying cause.

1. Cancellation and shutdown

Given Codex or dashboard work is in progress,  
When the operator cancels, presses Ctrl-C, kills the process, or the control parent disappears,  
Then processes are terminated as safely as the signal permits, committed history remains valid, and restart reconciliation accurately represents interrupted work.

1. NiceGUI behavior

Given a researcher row is selected,  
When it is clicked again or refreshed,  
Then it remains selected and its attempt history remains expanded. Selecting another row changes selection. Filters/search/sort/selection are preserved across action clicks, cell text is selectable, and clearing search resets it.

1. NiceGUI responsiveness

Given different viewport widths,  
When the dashboard renders,  
Then header, filters, table, action area, card, and footer share the same responsive width; columns remain usable without zero-width prostheses; cards wrap text with compact line spacing.

1. Sorting

Given pilot and numeric draw numbers,  
When rows are sorted,  
Then pilot-prefixed draws come first and all draws use human/natural ordering. First name appears left of last name and original database column labels are preserved.

1. Operator E2E

Given the explicit operator test command on the control-centre machine,  
When the real contour runs,  
Then it uses actual backend, dashboard, browser, configured main DB, authoritative log/CAS, and reachable AIVM. Every test hashes both production data trees before and after and proves they are unchanged; Lima is explicitly treated as ephemeral.

1. Test/spec evidence

Given any independently verifiable TASK requirement,  
When implementation is complete,  
Then it has a dedicated roundtrip test and one atomic Markdown requirement cell followed immediately by one evidence cell in `SPECS.ipynb`. The sample DOCX is generated for human rendering review, and `make validate` passes.
--->

<!---stale
```bash
sed -n '8,212p' "$TASK_DIR/legacy/SPEC.md"
```

### other issues that need addressing:
- review docx and txt renderers and identify where markdown is being produced - and enclose any  underscore containing items into backticks. so basically field names etc. otherwise in nicegui they are incorrectly rendered as markdown.
- in main nicegui table and in researcher card, somehow the line spacing is too large. in the attempt history table it's perfect.
- in main nicegui table the row clicked on doesn't get highlighted which is confusing.
- when nicegui table row is selected/unselected multiple times, this expands and collapses attempts table which is not intuitive. what should happen is that once it's selected, the attempt history should be expanded, and any future clicks will be idempotent.
when clicking on a different row, the selection will change.
therefore when for the first time a row has been selected, rows never get unselected
and therefore attempt history persists.
- in the search box when i remove the value, the search doesn't get reset. **already addressed in commit: `eeeaeacd8aef6d425c27935d2b00cd8777c196fa`. only remains to wire in spec.**
- a spec that uses the docx card building functionality to build a sample researcher's card from db. the card includes full featured output identical to that on a nicegui card. the spec saves it under `$TASK_DIR/data/sample.docx` for future review of rendering.
every case above must have a dedicated roundtrip test.

### revamped evidence matching
- it became known that submitter (agent runtime) tends to discard a large portion of evidence - without necessary changing the submitted variable values themselves. we need to address this by encapsulating current exact-matching behaviour as `match_rule_version.codex_match` in `config_ai_augment.json` (already added). v1 always remains authoritative for actual evidence acceptance but v2 is used to further explore the reasons for non-match and selecting what message to return to submitted and how to validate the resubmission.
- The detour configuration now has `match_rule_version.codex_match` with allowed versions 1 and 2.
- `match_rule_version.codex_match` is 1 by default if unspecified. Codex match rule v1 is the current case-sensitive exact contiguous excerpt match. Codex match rule v1 also requires the submitted URL to equal the indexed result URL. Codex match rule v1 remains the only rule capable of accepting evidence. When codex_match is 1, only v1 matching is performed.
- Codex match rule v2 is diagnostic only and must never accept evidence. When codex_match is 2, v1 matching is attempted first and v2 is attempted only after v1 fails.
- An excerpt satisfying v1 must always be classified as v1 even when it would also satisfy v2.
- The actual per-evidence outcome must be preserved as v1_exact, v2_near, unmatched, or withdrawn. These values are defined as top globals in `src/detours/detour_ai_augment/src/backend/api.py` and any labels intended for humans go into `src/detours/detour_ai_augment/src/backend/helpers/locale.py`.
- Codex v2 should reuse exactly the normalization/tokenization primitive currently used by XLSX v2. Yes, it's a DuckDB-based processing - we use it for codex_parse also, and we .leverage existing `codex_*` tables and views. Only the generic XLSX v2 tokenization primitive may be reused; XLSX initial expansion, compact-initial matching, source/target asymmetry, name-key generation, and candidate priority are irrelevant to Codex evidence. The XLSX v2 tokenization primitive must be extracted into a domain-neutral shared helper without changing its generated SQL or main-pipeline behavior. xlsx_v2_tokens_sql must remain available as a compatibility wrapper around the extracted helper. Normalized values are persisted in a new view at `persist_rollout_index` for easier use downstream. Codex v2 must compare normalized token sequences rather than normalized complete strings. The complete normalized submitted-excerpt token sequence must occur contiguously and in order within one normalized citation section. Otherwise currect exact match logic can be reused. Codex v2 must still only use citation sections produced by a fully valid web-tool chain. Codex v2 must still require the submitted URL to equal the candidate citation result URL. V2 matching must be used only to classify and coach a rejected item; it must never modify the submitted excerpt automatically.
- An empty or punctuation-only submitted excerpt must not satisfy v2. 
- Every submitted evidence item must be evaluated independently before the API constructs its submission response. Evidence validation must not stop at the first failed item
- Compromised `appendwatch` rollout provenance still fails the rollout-index stage before per-evidence assessment begins.
- A field is provisionally accepted only when every submitted excerpt for that field satisfies v1.
- A v2-near excerpt is not accepted and therefore prevents provisional acceptance of its field.
- An unmatched excerpt is not accepted and therefore prevents provisional acceptance of its field.
- The complete push remains rejected until every required evidence-bearing field is provisionally accepted. The submitter must therefore resubmit the complete payload rather than submitting only failed fields or failed excerpts.
- The optional comments field remains independent of evidence validation and requires no web excerpts.
- The first Pydantic-valid but evidence-invalid submission for a sanctioned run must establish an immutable retry baseline. Plain `src.detours.detour_ai_augment.src.backend.helpers.data_models.submission.Submission` is used to validate the first submission. The retry baseline must be keyed by sanctioned run_id rather than session_id or rollout filename. The retry baseline must also bind sourcekey and session_id so mismatched retry state fails closed.
- `src.detours.detour_ai_augment.src.backend.helpers.data_models.pydantic_to_paste.StandardizedSubmission` is used to validate every retry submission. The message to the resubmitter must include a note that standardized values are now required and the Pydantic schema is provided (e.g., `src.detours.detour_ai_augment.src.backend.helpers.locale.Locale.EVIDENCE_RETRY_STANDARDIZED_VALUES`). The API should not let the resubmitter know anything about the plain `Submission` or even its existence; `StandardizedSubmission` is the only schema the resubmitter sees.
- OpenAPI `/push` example is shown accordingly to the schema used.
- All standardized values are saved into DuckDB along with plain ones; a separate `ktp.ai_augment_*_standardized` field is provisioned in the db schema for each variable and it contains JSON-serialized `standardized_value`.
- All standardized values are shown in the final produced card; every standardized field immediately follows its plain version; if the standardized value is None/NA/NR, use routine logic for card display that hides `KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS` (extend this var for this detour - no touching the main pipeline); no footnotes are attached or shown for standardized values as all footnotes will already have been shown at the plain value.
- The retry baseline must be created atomically, persist across API restarts, and never be replaced by a later retry.
- A Pydantic-invalid submission must not establish a retry baseline.
- Different pull/push runs in the same cumulative Codex rollout must have independent retry baselines. 
- The retry baseline must preserve every submitted evidence item and its v1, v2, or unmatched outcome.
- A v1-exact baseline evidence item must be immutable on all retries. A v1-exact baseline evidence item must retain its exact excerpt and exact URL.
- A fully provisionally accepted field must retain its exact field value and complete evidence list on retries. Provisionally accepted fields are therefore carried forward unchanged in the complete payload and are not invitations for further editing.
- Within a rejected field, every v1-exact evidence item must still be retained unchanged.
- A v2-near response should praise the overall progress only when exhaustive assessment proves that the submission is largely v1-valid (without saying internal words like v1 or v2 of course).
- A v2-near response should say that the identified evidence item appears close to the recorded result and probably needs a minor correction involving case, accents, punctuation, whitespace, or line breaks.
- A v2-near response must instruct the submitter to preserve all verified values and evidence unchanged.
- An unmatched response should say that the identified evidence item does not appear to match its cited web result.
- An unmatched response must instruct the submitter to verify both the excerpt and URL against the original web-tool output.
- The API response must identify each failed evidence item by field and array index, e.g.:
    
    > 21 of 22 evidence items were verified. Preserve all verified values and evidence unchanged. Review the following flagged excerpts:
    >
    > - ktp.ai_augment_social_capital.web_search_excerpts[1]; its wording appears close to the recorded result but may differ in case, punctuation, whitespace, or line breaks.
    > - ktp.ai_augment_social_capital.web_search_excerpts[2]; does not appear to match its cited web result. Preserve all verified values and evidence unchanged, then verify this excerpt and URL against the original web-tool output.
    > - ..etc, one line per rejected excerpt
    >
    > Compare the above evidence items character-for-character with the original web-tool output and resubmit the complete payload after correcting only the flagged items.
- The API response must not return the server’s candidate text or a corrected excerpt. The API response must not disclose call_id, ref_id, match positions, SQL, or other internal validation details.
- Exact candidate text and detailed diffs should remain available in private server logs or a human-only Control Centre view.
- A v2-near baseline item must preserve its original URL on retry.
- A v2-near baseline item must preserve its original normalized v2 token sequence on retry. The resubmitted v2-near excerpt must normalize to exactly the same token sequence as the original submitted excerpt. Of course, a v2-near retry whose normalized tokens remain equal must still satisfy v1 before it can be accepted.
- A v2-near retry with a different normalized token sequence must be rejected with a message that only a minor textual correction was permitted.
- If a v2-near retry retains the normalized tokens but still fails v1, it must remain rejected and receive the minor-correction instruction again.
- The v2 retry restriction must prevent shortening Geslacht followed by a line break and Man to only Man (feel free to copy real-world examples from `tmp/20260813T141344_678596Z_8ef1f6372b4a48d9a3b1279736356363` and `tmp/20260813T141450_027429Z_044215aac8c44200882531b10a2acfa6`).
- An initially unmatched evidence item may be replaced with any excerpt and any URL because no credible source identity or wording was established.
- An initially unmatched evidence item must be classified afresh on every retry.
- An unmatched replacement that satisfies v1 becomes provisionally accepted and immutable.
- An unmatched replacement that satisfies only v2 becomes v2-near and establishes a normalized-token and URL lock for subsequent retries.
- An unmatched replacement that still satisfies neither rule remains freely replaceable.
- Evidence counts must not decrease by silently deleting v1-exact or v2-near baseline items. An unmatched evidence item may be removed only through an explicit audited withdrawal mechanism. The withdrawal mechanism must be represented by a structured Pydantic model and a withdrawal should contain a machine-readable unsupported-evidence reason and an explicit attestation, e.g.: `{"action": "withdraw_unverified_evidence", "reason": "not_present_in_web_results", "attested": true}`. The submitter identity for a withdrawal must come from the sanctioned run, session, and attempt metadata.
- A withdrawal must never count as validated evidence.
- A withdrawal must remain visible in the immutable attempt audit.
- Automatic withdrawal must be available only for evidence that satisfies neither v1 nor v2.
- A v2-near item must never be withdrawable because the backend already has evidence that its wording is present after conservative normalization.
- Withdrawing an unmatched item must release only that unaccepted item’s retry obligation. Withdrawing an unmatched item must not permit deletion or modification of any v1-exact or v2-near item.
- The field value associated with a withdrawn item must be resubmitted so the unsupported claim can be corrected.
- A field containing a withdrawal must still retain at least one v1-exact evidence item before the field can be accepted.
- The backend must continue to use rigorous v1 matching after every v2 diagnostic or withdrawal operation. V2 classification, retry guidance, and withdrawal must not weaken the final exact-match acceptance boundary.
- Detailed per-item outcomes, submitted excerpts, submitted URLs, and candidate diagnostics must be logged privately.
- Public retry responses must expose only the failed item locations, aggregate counts, permitted correction category, and remediation instructions.
- The implementation must preserve current deterministic evidence candidate ordering and sampling behavior.
- The implementation must preserve source database read-only behavior.
- Rejected and provisionally accepted retry state must not materialize accepted output rows or researcher cards.
- Only a fully accepted push may append Codex output, materialize a researcher card, acknowledge acceptance, and consume the sanction.
- Unit tests must follow the existing XLSX and SSN name-matching style by using parametrized cases and explicit expected matched-rule sets.
- Tests must prove that exact text is classified as v1 when codex_match is 2.
- Tests must prove that case-only differences are classified as v2 and remain rejected.
- Tests must prove that accent-only differences are classified as v2 and remain rejected if XLSX normalization is reused exactly.
- Tests must prove that punctuation-only differences are classified as v2 and remain rejected.
- Tests must prove that whitespace and line-break differences - including with several such characters in a row - are classified as v2 and remain rejected.
- Tests must prove that reordered tokens fail v2.
- Tests must prove that missing or added internal tokens fail v2.
- Tests must prove that tokens split across citation sections cannot satisfy v2.
- Tests must prove that an otherwise matching token sequence under a different URL cannot satisfy v2.
- Tests must prove that punctuation-only and empty excerpts cannot satisfy v2.
- Tests must prove that enabling codex_match version 2 never causes v2 evidence to be accepted.
- Tests must prove that all evidence items are assessed even when an earlier item fails.
- Tests must prove that a field is accepted only when all its evidence items satisfy v1.
- Tests must prove that a complete submission is rejected when any field remains unaccepted.
- Tests must prove that v1-exact fields and evidence cannot be changed or removed on retry.
- Tests must prove that a v2-near retry may change only formatting represented away by v2 normalization.
- Tests must prove that a v2-near retry with changed normalized tokens is rejected.
- Tests must prove that a v2-near retry is accepted only after its corrected raw excerpt satisfies v1.
- Tests must prove that an unmatched item may be replaced freely and is reclassified after replacement.
- Tests must prove that an unmatched item may be explicitly withdrawn without removing accepted evidence.
- Tests must prove that a v2-near item cannot use submitter-initiated withdrawal.
- Tests must prove that retry baselines survive API restart.
- Tests must prove that concurrent first rejected submissions cannot replace the immutable baseline.
- Tests must prove that retry state does not cross run_id boundaries within the same Codex session and rollout.
- A historical Haanen regression fixture (from `tmp/20260813T141344_678596Z_8ef1f6372b4a48d9a3b1279736356363` and `tmp/20260813T141450_027429Z_044215aac8c44200882531b10a2acfa6` paths) must demonstrate that exhaustive validation classifies 21 original evidence items as v1 and one item as v2-near.
- The historical Haanen regression must demonstrate that the ideal retry preserves all 21 v1 items unchanged and corrects only the one newline-mismatched item.
- The historical Haanen regression must demonstrate that the retry cannot reduce 22 evidence items to 9.
- The historical Haanen regression must demonstrate that the retry cannot shorten already-valid excerpts such as Geslacht followed by a line break and Man to Man.
- All existing tests, including XLSX name matching, must remain green after extracting the shared tokenization primitive.
- A focused equivalence test must prove that the extracted shared tokenization produces exactly the same XLSX v2 tokens as the pre-extraction implementation for all the normalizations applied.
- The main pipeline remains completely independent of any `src/detours/detour_ai_augment` code.

### revamped logging and db
- detour's db is considered ephemeral for easy access. it may be deleted any time and should be reconstructible exactly from stored data.
- stored data consist of a single jsonl append-only log which documents http request/response events (see below) and content-addressable storage that stores _only_ rollout snapshots. everything else is fairly small and goes directly into appropriate http request logs.
- corrolary of this is that http request/responses (see below) should be architected in such a way that they are _all encompassing for all info needed for replay_ (except for rollout snapshot that is stored in cas). for this to work for appendwatch and other backend private metadata, we introduce internal control commit endpoint that uses PUT to commit final state; only then public pull give error feedback (if unsuccessful submission) and otherwise will give busy response. so external push and internal commit are a single transaction.
- `HttpRequestLogRecord` (with `schema_version = 2`) is the canonical way to store request/response contours. of which we have several:
- the main component remains backend api which serves /pull and /push. to be able to serve those, it must be sanctioned by someone (usually dashboard, but in principle can be sanctioned by human operator manually - through using same http machinery as dashboard). so /pull in that sense is fully deterministic to the upstream (i.e., sanctioning) http request that backend received. therefore, on backend side we need to store _all_ pushes it _responds_ to.
- backend api also serves internal push and pull endpoints for dashboard/human operator to sanction researchers (push for sanctioning, pull for polling outcome). a successful internal push endpoint directly and idempotently enables public pull. if server is shut down halfway through the internal push, no worries because the logging boundary here is push requests that backend served. 
- note that we keep the entire contour strictly sync-only and idempotent in the sense that only one sanctioned record may exist and be served by public pull at a time. backend api is strictly sync therefore and this forces dashboard and agent runtime to be sync (and therefore must be idempotent) too. 
- so here is how it all works:
- backend api owns the duckdb connection including any reads and writes to duckdb or to jsonl file. neither duckdb nor jsonl file are never exposed to or used by dashboard or (god forbid) agent runtime client. upon start of backend it does replay its append-only jsonl file, simply in line order, and confirms whether db conflicts with it - what we currently have as a replay logic there. if it finds conflicts it just exits loudly with an informative server log message. and so if all ok, at start of backend api it has duckdb open and synchronized with jsonl files without any conflicts. at first starts it's empty jsonl files and so it's just empty tables. at this point both public pull and public push will return errors because no sanctioning HttpRequestLogRecord will be found in duckdb. note that because backend fully owns both db and jsonl file, it only needs to do the db/jsonl sync check once - at start, and then it trusts db until restart.
- backend api only always processes one http request at a time (from any client) and all others get denials.
- though denials do get noticed by asgi middleware tha wraps entire backend api and mechanically dumps the internal/public push ones in the single jsonl (pulls are not logged); the jsonl writer is therefore tightly wired into the middleware and listens to all requests at once and its job is to dump them all to jsonl as fast as possible and so other api.py logic deals with this later and so that only scenario where any response from backend api would be lost would be a very unusual case where it returned but between the lines of return response and dump to jsonl computer shut down or disk broke, so very unusual.
- dashboard (or human operator manually curl'ing for that matter) can send a sanctioning (i.e., internal push) request. dashboard also owns the readonly connection to main db and reading of lima/deploy stuff, which it then communicates through control push to backend. if backend is not ready it'll respond with error (though its middleware will still capture the request/response into jsonl). if it's ready it will serve it. serve it means serve, _write to jsonl succesfully_ and only then actually send it. it's fully transactional - either whole contour from receive request to log succeeds or fails. sending of response to push is out of transaction really because how it's made is that push sender never cares about response to push - it will then poll pull.
- in line with this, we must ensure the external/public push and pull are designed in same way. agentic runtime sends push and should not rely on response; rather the openapi.json it reads at the beginning should be clear about that after sending it it should poll pull for response to its push. and so how it will look from agent runtime's end is it sends push then polls pull, if push was successful it gets a success confirmation and then upon next pull agent runtime will observe it's been disabled until human sanctions next one.  so public pull either returns as 200 and payload or an error and error message. 

here is about same thing in other words:

1. Ownership and source of truth
The backend owns all durable state:
Dashboard ───────┐
                 │
External client ─┼──► Backend ──► authoritative.jsonl
                 │                    │
                 │                    ▼
                 └───────────────► DuckDB projection
authoritative.jsonl is the canonical append-only history. DuckDB is never authoritative; it is a materialized/queryable projection that can be reconstructed from JSONL.
On startup:
open/validate JSONL
      ↓
compare DuckDB projection checkpoint
      ↓
JSONL has new entries → apply them to DuckDB
      ↓
mismatch with already-projected prefix → FAIL LOUDLY
If DuckDB is corrupt or fundamentally disagrees with JSONL, the safe recovery is ultimately to rebuild DuckDB from JSONL rather than modify JSONL to match DuckDB.
I would store a small projection checkpoint in DuckDB such as the last applied JSONL byte offset/line plus a hash of that last line. That lets you distinguish simply being behind from actual divergence.
2. Four endpoints
Conceptually:
Internal push   Dashboard → Backend
Internal pull   Dashboard ← Backend

External push   Client → Backend
External pull   Client ← Backend
Only the two push endpoints go into the authoritative event log.
Pulls are queries. They don’t change state, so they don’t need to participate in replay.
3. Backend state machine
Something approximately like:
IDLE
 │
 │ internal push / sanction accepted
 ▼
SANCTION ACTIVE
 │
 │ external pulls may repeatedly observe same sanctioned value
 │
 │ correct external push accepted
 ▼
IDLE
The internal push therefore establishes the sanctioned state. That state remains stable until the corresponding valid external push completes it.
Both pushes should be idempotent. This becomes especially important because an HTTP caller may not know whether a request succeeded.
I’d give an internal dashboard command an idempotency key, probably in a header. Ideally the external transaction also has a natural transaction/job/sanction identifier.
4. Serialization
Use one FastAPI/Uvicorn worker process and one global non-waiting command gate covering the two pushes:
internal push ─┐
               ├──► command gate, capacity 1
external push ─┘
If another push arrives while one is being processed:
push arrives
   ↓
gate occupied
   ↓
immediate BUSY response
   ↓
log that response
   ↓
send it
No waiting queue.
Pulls don’t necessarily need this gate. In fact, keeping internal status/pull readable while a command executes is useful. You just need their read semantics to tolerate seeing either the pre-commit or post-commit state.
5. Middleware owns logging
I agree with using middleware now because your rule is structural rather than endpoint-specific:
Every response produced for either push endpoint must go through the log before leaving the backend.
For those two routes:
request
   ↓
middleware captures request
   ↓
gate / endpoint processing
   ↓
complete response produced
   ↓
middleware captures complete response
   ↓
append one JSONL record
   ↓
flush + fsync
   ↓
only now send response
The middleware should therefore buffer the response rather than immediately forwarding http.response.start to the client. For small JSON API responses, that’s perfectly reasonable.
Use a separate JSONL append lock because a rejected busy request could be getting logged while the active push is still executing.
6. What gets logged
Your stated rule now is:
Every response to an internal or external push is logged.
So the log contains both successful transactions and rejected attempts:
{"request": {...}, "response": {"status": 200, ...}, ...}
{"request": {...}, "response": {"status": 503, ...}, ...}
{"request": {...}, "response": {"status": 409, ...}, ...}
That’s fine. DuckDB’s state projection simply applies the entries that actually represent committed state transitions. The others can still exist as audit/history records.
And because there is now one writer and one file, file order is your canonical order:
line 1
line 2
line 3
...
No k-way merge, UUID ordering, monotonic tie-breaking, or sorting is needed.
7. The crucial commit boundary
This deserves to be extremely explicit.
For a successful state-changing request, ideally:
validate request
      ↓
calculate next state + response
      ↓
append response/event to JSONL
      ↓
fsync                         ← COMMIT
      ↓
apply new state / DuckDB projection
      ↓
send HTTP response
Avoid mutating authoritative application state before the JSONL commit if possible.
Therefore:
JSONL succeeded
backend died before HTTP response
means the transaction happened.
The caller merely failed to learn about it through that HTTP connection.
That’s exactly why your dashboard’s new behavior works well.
8. Dashboard semantics
The dashboard shouldn’t use the command’s HTTP response as ground truth.
Instead:
Dashboard
   │
   ├── POST internal push
   │
   │      doesn't rely on response for correctness
   │
   └── periodically GET internal pull/status
                 ↓
             Backend
                 ↓
              DuckDB
If it doesn’t observe the expected result, it can retry the same idempotency key.
I wouldn’t literally fire the HTTP request and immediately destroy/cancel the connection. Send it normally; simply don’t make receipt of its response part of your correctness model.
 
⸻
 
Failure modes I would explicitly design/test
There are several important ones.
Crash before JSONL append. No transaction was committed. On restart there is nothing to replay. Good.
Crash midway through JSONL append. You can have a partial final line. On startup, validate the tail and truncate an incomplete final record back to the previous newline. This should be an explicit recovery routine.
Crash after JSONL fsync, before DuckDB update. Transaction is committed. Startup replay discovers JSONL is ahead and applies it to DuckDB. This is one of the main reasons the architecture works.
Crash after JSONL and DuckDB update, before HTTP response. Transaction is committed. Caller may time out. Dashboard discovers it through status; a retry must be idempotent.
Disk full / permission error / I/O error during JSONL append. Do not send a successful response. More importantly, don’t let the domain state have already irreversibly changed before this point.
DuckDB update fails after JSONL committed. This one is subtle: the transaction is already real, because JSONL is authoritative. You cannot pretend it was rolled back. I’d mark the backend unhealthy/fail closed for subsequent state-changing pushes until the projection is repaired, and report the projection error loudly.
Backend receives a request, but client times out while it is executing. The request can still commit. Client timeout never means “the operation did not happen.” Idempotency + polling handles this.
Duplicate/retried pushes. Explicitly design idempotency. This is one of the most likely real-world failure cases.
Framework-generated errors. If you want “every response for these push paths,” test malformed JSON, validation 422, authentication failures, handler exceptions/500, and busy rejection. Make sure your middleware is positioned so the responses you intend to capture actually pass through it.
Request never reaches your application. Connection failure, port unavailable, server not listening, malformed traffic rejected below your application, etc. cannot appear in your application-owned JSONL. That’s okay; document the boundary as “push requests that reached the backend application and produced a response.”
Streaming responses. Your design assumes ordinary finite JSON responses. Don’t use streaming for these push endpoints, because “log complete response before sending it” becomes incompatible with true streaming.
Log manually edited/truncated. Backend can see this because `config_ai_augment.json` contains `detour_ai_augment_backend_api_replay_log` which human operator manually sets at control centre/backend termination/whenever operator wants and so at start of backend this is always verified (using conventional `RegisteredResource` logic) and if it mismatches backend fails to start loudly. If hash matches, backend trusts the log and replays it; any mismatches in duckdb are interpreted as corrupted db and backend api fails loudly with an informative server message that human operator should investigate.
Two backend processes accidentally start. This is worth guarding against. Your entire single-writer model assumes exactly one backend instance owns that JSONL.
Consider a process-level lock on startup so a second backend refuses to start against the same data directory.
Note that in `HttpRequestLogRecord` (with `schema_version = 2`) we use `ready_to_respond_at_unix_usec` rather than `response_received_at` for the obvious reason - we are logging responses we are sending ourselves here rather than ones we receive.
Overall, the strongest invariant I would write into the design is:
A push transaction becomes authoritative when its complete request/response entry has been durably appended to JSONL. DuckDB and all other state are projections of that committed log; successful HTTP delivery is notification, not the commit mechanism.
That one sentence resolves most of the crash and retry questions.
--->
