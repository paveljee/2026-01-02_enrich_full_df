## human written - ai never touches this
### prerequisites and setup
See prerequisites and setup in
`tasks/tasks-20260519-review-231/SPEC.md`

Use `./WORK.md` as
your own workbook for
recording actions you have in mind and
recording in progress and completed, or
any other notes you feel you need.
Write as if for a
busy tech lead and
also to be helpful for the executor, so
lean concise text that 
contains all relevant info inplace but is
focused and very well organized.

### actual task
build a new detour.
review existing ones to see how they work.
the most important bit is that
they are inspired by some components of the main pipeline
yet are completely standalone in operation.

the detour will spin up a fastapi server.
the server is intended for api-only use,
by an executor (AI agent) who will be filling in missing data.

the executor's intended workflow
(that is, equipped with the detour's server endpoints):

**first, the executor will be receiving payloads
for which we do not have any missing data -
that is, subset 1 namekeys. this is for evals.
once the executor is happy with results, it requests
supervisor's review before the executor is
allowed to proceed with any records with missing data.
and so, the eval part goes as follows:**

- request a new payload.
(the payload contains all non-missing fields
for the record, and the list of missing fields;
the record being a single namekey).
- conduct web searches to
fill in all missing data.
- submit work to a structured endpoint
(endpoint is very principled and
will not accept any badly formatted work;
it accepts only a valid json payload).
- endpoint returns ground truth results
for executor's review.
the executor must submit
(on a special endpoint)
confirmation that review of ground truth results is
complete, executor's own assessment of pass/fail, and
takeaways from the review.
the executor must also update their workbook, 
which is limited in size, 
by recording only the most important learnings there.
all changes are made as git commits.
the commit hash is always submitted in the payload.
- the endpoint verifies the submitted json and
the hash, as well the endpoint has direct access
to an automated JSONL rollout of the agent's work
and relevant events are auto verified against it.
- once endpoint is happy, it prompts the executor
whether they would like a new payload or
they would like to submit whole work for supervisor's review.
if not happy, it returns specific feedback to address.

payload production is randomized, seed is set
within the fastapi code as top level env var.

once executor says submit all work for supervisor review,
fastapi collates all tasks into a single report
which must be reviewed by supervisor (i.e., human).
supervisor review is not available via fastapi,
rather it must be supplied separately to the server env.
until it's supplied, server does not return new payloads.
once it's supplied, the server start returning payloads again
but this time with genuinely missing data.
in this iteration, the executor is not obviously offered
ground truth which is nonexistent, but rather is
simply shown its own submitted work and prompted to confirm.
once confirmed and endpoint is happy with validation,
new payload is offered, and this continues until
all missing data are filled.

executor should also be explicitly offered an
endpoint for modifying a previous submission.
the endpoint will operate identically to
namekey submission confirmation operation
for missing-data namekeys:
endpoint returns inputted data and prompts to confirm.
once all missing-data-payloads are processed,
the executor gets a final opportunity to review and
change any previously submitted work before
the executor confirms that all is sent to supervisor.

so, now that the whole workflow is described,
the goal is build a detour that spins up this server.
namekeys for review (i.e., with missing data)
should be partition 4 of subset 2.
records for evals are subset 1.
the amount of information show to exectutor
is same as in the final cards.

submitted results of work are **not** stored in 
the main database which is read.
note that it's  always read as read-only.
instead, a separate db is created for the detour.

now, another important aspect of how server accepts work.
the executor, when submitting a data item
(missing data filled in - for evals or for real assignments)
must also submit direct URLs which 
the executor claims contain confirmation.
the executor also must supply a XML DOM (xpath) or
regex to use to actually find this on the page.
the server then, upon receipt of this payload,
uses playwright to actually download the page as HTML +
takes a screenshot (for archival/auditability +
to be linked in report for supervisor review) and
applies executor-supplied xpath or regex to the
text of the page and algorithmically thus validates
if the claimed text is truly present there.
**the report to supervisor must contain a snippet,
against each datapoint, that is produced ALGORITHMICALLY
from the downloaded local copy** and accordingly a message
whether the server-side verification failed or passed.

## useful implementation details
- detour must have this:
`parser.add_argument("--config", type=Path, required=True, help="Path to JSON config file.")`
and derive db path (for input, readonly db) from there,
same as prior detours.
the db for the detour is though separate, yes;
in detour step4 breakdown there is a neat "detourizer"
that creates a standalone db file based on passed input file name.
- **note that repository root** and
overall work dir for the **executor** will be
**completely different** than this repo from which
the fastapi server is served.
the executor will not have access to this dir at all.
so assume they are working from a completely separate,
**completely empty** workdir where they initialize what needed.
**all interaction** with the server is done **through HTTP**,
so the executor is only given the URL on which the server is running and
will use swagger or other api specific means to figure
what are the available endpoints and how to work with it.
**the api is the only way of communication** for the executor.
- there must be a (single) pytest test file for this detour,
like for the other detours.
the test file will contain **per endpoint** unit tests,
so all endpoints must be tested separately, and
any unit tests for functions within
(so the detour module must be written explicitly with
the ease of unit testing in mind).
- also, there must be a **test** in this test module
that confirms that the detour can correctly read info
from the database across all of subset1 and subset2 namekeys,
and so to prove this the test must print summary stats about this
and this must be asserted to be equal to known values.
this includes both counts of namekeys, 
as well as availability/missingness of datapoints within.
as such this test proves that coverage of the supplied
database file (that is, as derived from supplied config file) is
fully aligning with the file that we expect to see in this detour.
of course ground truth values for the test
must be obtained using direct database inspection at dev time.
- **in case multiple docx rows are available per namekey,
all of them must be shown/used at all times, no exceptions.**
- all logic decisions used by the fastapi server,
for example the logic for sampling payloads, or
any other business logic,
must be exposed conveniently in the detour module and
be covered with a straightforward unit test.
no logic is allowed to be buried within module code unexposed or
uncovered with a visible unit test.
a great example of this approach is expected input-output tests from
`tests/test_xlsx_name_matching.py`.
- make sure that all env vars that affect detour logic are
exposed as top level vars in the modules.
no hardcoded values are allowed to be buried within module.
- Requesting supervisor review requires
at least two completed evals.
if the number of completed evals is below
"set in detour env var, default 10", then
prompt the executor to confirm that they are
truly confident with eval results because the 
number of completed evals is low.
- supervisor should be able to submit one field of
free text feedback to the executor, which
the fastapi server will relay as guidance for
resubmission or upcoming missing-data filling.
- supervisor must also be able to return the
final submission for rework, with a text feedback field.

## how ai understood the spec

### delivery target

Build a new API-only detour with a stable module entry point such as
`python -m src.detours.detour_fastapi`. Its CLI must take the main
config/source DB, separate detour DB, repository root, executor
workspace/workbook, report directory, host, and port explicitly, with
environment variables reserved for the seed, bearer token, rollout,
and out-of-band supervisor review. The entry point starts a
FastAPI/Uvicorn server; it does not run any main pipeline step.

This detour has two data connections with deliberately different roles:

1. `data/scisci_process.duckdb` is the source database and is always
   opened with DuckDB `read_only=True`.
2. A distinct detour DuckDB is writable and owns all campaign,
   assignment, submission, review, audit, and report state.

Resolve and compare both paths before opening either database. Reject
the configuration if they are equal, if either resolves to the other
through a symlink, or if they identify the same inode. Never attach the
source database with write access and never create, replace, update, or
drop an object in it. Submitted values are not patched back into the
main pipeline database.

The server may reuse pure constants, data models, JSONL parsing, and
card-display conventions from `src/helpers`, but its operation must be
standalone. In particular, it must not import or invoke `src.repl`,
`src.steps`, pipeline initialization, the step registry, or REPL
runtime/state helpers. It must also not call another detour. Starting
the server must require only the already-persisted source DB, the
detour DB, the repository, the executor rollout, and detour-specific
configuration.

This task is an implementation task for the detour, its tests,
dependency/lock-file updates, and concise README usage. It must not
alter the main matching or card-building behavior.

### current source-of-truth audit

The counts in the May prerequisite spec are historical. They must not
be copied into this detour. Direct read-only inspection of the current
database gives:

| current item | namekeys |
|---|---:|
| all `outerdict_name_keys` | 307 |
| subset 1 | 181 |
| subset 2 | 126 |
| subset-2 partition 1 | 17 |
| subset-2 partition 2 | 9 |
| subset-2 partition 4 | 100 |

`card_partitions` currently contains exactly 126 unique
`ktp.source_key` values with `card_subset_mode = 2`, all of which exist
in `outerdict_name_keys`. For this detour:

- subset 2 is the persisted mode-2 key set in `card_partitions`;
- subset 1 is the anti-join of `outerdict_name_keys` against that
  persisted mode-2 key set;
- the real missing-data cohort is the subset-2 rows where
  `ktp.partition = KTP_PARTITION_DOCX_VALUE`, currently the numeric
  value `4`.

Do not infer that `card_subset_mode = 4` means partition 4. Mode and
partition are separate concepts. Do not recompute an older subset rule
from the May spec: the persisted current classification reflects the
current XLSX v2 and SSN v2 work. The implementation should validate
uniqueness, membership, subset disjointness, and cohort coverage at
startup. Current-data integration tests should assert the counts above,
but cohort logic itself should be relational rather than a hard-coded
list of names.

At first initialization, store a deterministic source fingerprint in
the detour DB. It should cover the ordered source-key/cohort assignment,
the schemas of the three innerdict relations, and the source DB file
identity. On resume, refuse to continue if that fingerprint, the
configured seed, or the repository base commit differs. This prevents
an in-progress campaign from silently changing populations.

### records, target fields, and ground truth

Reconstruct each namekey's card input directly from the persisted
`xlsx_innerdicts`, `docx_innerdicts`, and `ssn_innerdicts` relations,
using the same source order and stable draw/filename/fragment ordering
as final cards. Do not read generated DOCX, TXT, ZIP, CSV, diagnostics,
or other data artifacts as an alternate source.

The executor-facing record is structured JSON, not rendered Markdown.
It must expose the same source information available in a final card:

- the name, draw information, and ordered innerdicts;
- `ktp.filename` as the innerdict heading/provenance;
- every other card-visible, non-null field with a JSON-safe value;
- the same technical exclusions as card building:
  `ktp.source_key`, `ktp.csv_row_index`, `ktp.docx_table_index`,
  `ktp.docx_row_index`, and `ktp.docx_fragment`; and
- workflow metadata such as assignment ID, phase, and missing-field
  list separately from source data.

Do not add source-derived columns that final cards do not expose. Empty
required target fields move to the explicit `missing_fields` list
rather than being presented as usable values.

The fill target is the required `ktp.table_1_*` field family used by
the current subset-1 DOCX rule. Derive requiredness from the persisted
DOCX schema plus `KTP_DOCX_TABLE_1_PREFIX`,
`KTP_DOCX_OPTIONAL_EMPTY_COLS`, and
`KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS`; do not maintain a second
hand-written required-column rule. The current source resolves to eight
required fields:

| required field |
|---|
| `ktp.table_1_academic_position_s_` |
| `ktp.table_1_age_first_publication_according_to_openalex_profile` |
| `ktp.table_1_education` |
| `ktp.table_1_gender` |
| `ktp.table_1_links_` |
| `ktp.table_1_place_of_residence` |
| `ktp.table_1_researcher_author` |
| `ktp.table_1_social_capital` |

The current 100 partition-4 records each have exactly one DOCX
innerdict. Every one has `docx_any = true` and
`docx_table_1_required_all = false`. Their current per-field missing
counts are:

| missing field | namekeys |
|---|---:|
| education | 71 |
| age at first publication | 53 |
| academic position(s) | 41 |
| gender | 38 |
| links | 27 |
| social capital | 25 |
| place of residence | 20 |
| researcher/author | 0 |

Counts overlap because a record can miss multiple fields. Optional-empty
table-1 fields are context, not required fill targets.

For future-compatible handling of multiple DOCX rows, choose the
canonical row by fewest missing required fields and then by the shared
stable draw/filename/fragment order. If no DOCX row exists, synthesize
an empty target row and treat every required field as missing. For the
real cohort, preserve every existing canonical-row value and request
answers for exactly its missing required fields.

All 181 current subset-1 namekeys have at least one complete DOCX row:
178 have one complete row, two have two, and one has four. Choose the
canonical complete row by the same stable order. This row supplies
evaluation ground truth.

Evaluation payloads must simulate the real task. Build the set of
missing-field masks from the 100 real partition-4 records, shuffle that
mask set deterministically, and assign/cycle those masks across the
seeded subset-1 queue. Before returning an eval payload, assert that the
canonical complete row contains a non-empty ground-truth value for
every masked field. Redact every masked field from every DOCX
innerdict representation in that payload, not only from the canonical
row. Independent XLSX/SSN context remains available as research
evidence. No endpoint, log entry, error, OpenAPI example, or list
response may reveal an eval record's hidden values before its first
valid submission is accepted.

### deterministic assignment production

Read the integer seed from the top-level environment variable
`FASTAPI_DETOUR_SEED`. It is required; malformed or missing values
fail startup. Persist the seed in the detour DB.

Generate independent deterministic orders for the eval source keys,
real source keys, and eval masks. Prefer sorting by a SHA-256 key over
`seed`, phase, and stable identity rather than relying on DuckDB
`random()` or mutable process-global RNG state. Materialize the
resulting ordinal queues in the detour DB at campaign creation. A
restart must resume the stored order exactly; changing the seed must
not reshuffle an existing campaign.

Assignments are without replacement. There is only one active
assignment for the executor at a time. Repeating the next-assignment
request while one is active returns the same assignment; it never
consumes another queue row. Each assignment carries an immutable ID,
phase, ordinal, source key, payload version, and source fingerprint.

### campaign state machine

The server must enforce the workflow as persisted state, not as hints
in response prose:

1. A new campaign starts in `eval_open`.
2. `next` issues one seeded subset-1 eval assignment.
3. A valid eval submission is stored immutably and only then returns
   that assignment's ground truth side-by-side with the submitted
   values. Factual disagreement must not be rejected before reveal;
   the purpose is evaluation.
4. The assignment remains blocked until the executor uses the special
   ground-truth-review endpoint. That request confirms review is
   complete, records the executor's `pass`/`fail` assessment,
   field-level assessments, and concise takeaways, and proves the
   workbook update/commit.
5. A successful review response explicitly offers the allowed actions:
   request another eval or submit the completed eval work for
   supervisor review.
6. Requesting supervisor review requires at least one completed eval
   and no unreviewed/awaiting-confirmation assignment. It creates a
   canonical JSON report plus a concise Markdown report, records their
   SHA-256 digests, and moves the campaign to
   `supervisor_review_pending`.
7. While pending, no endpoint returns a new payload. `next` returns a
   locked response that identifies the pending report, without leaking
   unavailable supervisor content.
8. Supervisor review is never submitted through FastAPI. It is
   supplied out of band through the server environment and imported
   only when bound to the exact pending report ID and SHA-256.
9. An approved review moves the campaign to `real_open`. A
   `changes_requested` review preserves the feedback, reopens
   `eval_open`, and permits more evals or revisions followed by a new
   report. A stale, malformed, or replayed review does nothing.
10. In `real_open`, `next` issues seeded partition-4 assignments. A
    valid submission returns only the executor's own normalized input
    and asks for confirmation; there is no ground truth.
11. The real submission becomes active only after the explicit
    confirmation endpoint succeeds. The executor may then request the
    next payload or revise any previously confirmed submission when no
    other submission/revision is awaiting confirmation.
12. After all real assignments have an active confirmed submission,
    `next` returns `final_review_available` instead of a payload.
    Listing/detail endpoints expose all active submissions and their
    revision history so the executor can review and revise them.
13. Finalization is allowed only when all 100 current real assignments
    are confirmed, no draft revision is pending, and validation is
    clean. It emits canonical JSON and Markdown supervisor reports,
    records their digests, locks the campaign in
    `final_supervisor_pending`, and confirms that the complete work has
    been made available for out-of-band supervisor review.

No automatic timer advances a gate. Exhausting the eval queue forces
supervisor review; it does not bypass it. Exhausting the real queue
forces final review; it does not auto-finalize.

### out-of-band supervisor review

Use a top-level environment value such as
`FASTAPI_DETOUR_SUPERVISOR_REVIEW_JSON`. Because process environment is
immutable, setting or changing it may require a server restart; the
detour DB must resume cleanly. The JSON is a strict, versioned envelope:

```json
{
  "schema_version": 1,
  "review_id": "globally-unique-id",
  "report_id": "pending-report-id",
  "report_sha256": "64-lowercase-hex",
  "decision": "approved",
  "reviewer": "human identifier",
  "reviewed_at": "RFC3339 timestamp",
  "feedback": "review text"
}
```

`decision` is exactly `approved` or `changes_requested`. Extra keys,
blank reviewer/feedback, invalid timestamps, the wrong report digest,
and reused review IDs are rejected. Persist the imported envelope and
its digest once. Do not expose an endpoint that can create, modify, or
approve supervisor review.

### HTTP contract

Version the API under `/v1`. `GET /openapi.json` is the machine-readable
contract. Apart from a minimal health endpoint, require bearer
authentication on every route.

| method and path | contract |
|---|---|
| `GET /health` | Liveness only; no cohort, token, path, or ground-truth details. |
| `GET /v1/session` | Campaign phase, source fingerprint, queue counts, active assignment, pending report, and allowed actions. |
| `POST /v1/assignments/next` | Return the current active assignment or atomically allocate the next allowed one. |
| `GET /v1/assignments/{assignment_id}` | Return only information permitted by that assignment's current reveal state. |
| `POST /v1/assignments/{assignment_id}/submissions` | Strict initial work submission. Eval returns ground truth after acceptance; real work returns an echo and confirmation prompt. |
| `POST /v1/eval-submissions/{submission_id}/ground-truth-review` | Special eval-only review confirmation with assessment and takeaways. |
| `POST /v1/work-submissions/{submission_id}/confirm` | Confirm an echoed real initial submission. |
| `POST /v1/submissions/{submission_id}/revisions` | Submit a complete replacement revision; never use an ambiguous partial JSON Patch. Return the revised input and prompt to confirm. |
| `POST /v1/revisions/{revision_id}/confirm` | Atomically promote the confirmed revision to active. |
| `GET /v1/submissions` | Paginated phase/status summary for final review; no premature eval ground truth. |
| `GET /v1/submissions/{submission_id}` | Active value and immutable revision/audit history allowed by reveal state. |
| `POST /v1/reports/evaluation` | Collate completed eval work and enter the supervisor gate. |
| `GET /v1/reports/{report_id}` | Report metadata/digest and, when authorized by state, its structured content. |
| `GET /v1/final-review` | Completeness matrix for every real assignment and any draft revision. |
| `POST /v1/reports/final` | Confirm all work is ready, emit final reports, and lock the campaign. |

Every success response includes `state`, `allowed_actions`, and
link-like endpoint paths. This is the API form of prompting the executor
to choose a new payload or supervisor review. State-changing endpoints
require an `Idempotency-Key` header. Persist the key, authenticated
principal, request digest, response status, and response body in the
same transaction. An exact replay returns the original response; reuse
with a different body returns `409`.

Use transactional compare-and-set on assignment/revision versions.
Stale versions and concurrent promotions return `409`; they must not
create duplicate assignments or active revisions.

Submission, ground-truth review, confirmation, revision, evaluation
report, and final-report requests are work-bearing and must carry the
git transport envelope. The empty `{}` body used to request `next` and
read-only GET requests do not represent executor work and do not
require a new commit.

### strict submission models

All request bodies must use `Content-Type: application/json`. Reject
empty bodies, form data, JSON strings/lists where an object is expected,
duplicate object keys, non-finite numbers, invalid UTF-8, and bodies
above a documented limit. Pydantic request models use strict types and
`extra = "forbid"` at every nested level; do not rely on coercion such
as `"true"` to `true`.

A work submission transport envelope has this shape:

```json
{
  "schema_version": 1,
  "assignment_version": 1,
  "git_commit": "full commit object id",
  "artifact_path": "configured/executor/workspace/submission.json",
  "work": {
    "assignment_id": "immutable assignment id",
    "answers": {
      "exact.missing.field": {
        "value": "non-empty researched value",
        "sources": [
          {
            "url": "https://source.example/item",
            "title": "source title",
            "accessed_at": "RFC3339 timestamp",
            "support": "short explanation of what the source supports"
          }
        ],
        "rationale": "concise synthesis"
      }
    },
    "research_summary": "concise cross-field summary"
  }
}
```

The `answers` key set must equal the assignment's `missing_fields`
exactly: no omissions and no extras. Every value is a bounded,
non-empty string and may not be one of the pipeline's empty
placeholders. Every field has at least one unique HTTP(S) citation with
bounded title/support text. Validate timestamps, URL scheme, string
lengths, collection sizes, and total body size. Store both the submitted
representation and a canonical normalized representation.

The eval ground-truth-review body contains:

- `review_complete: true`;
- overall `assessment`, exactly `pass` or `fail`;
- one field assessment for every missing field, exactly
  `pass`, `partial`, or `fail`, with a short explanation;
- one or more bounded takeaways;
- the git transport fields described below.

The endpoint returns the submitted and ground-truth values; the
executor, not the server, supplies the assessment. Exact string
disagreement is not itself a schema failure.

A real confirmation or revision confirmation contains
`confirmed: true`, the relevant optimistic version, an optional bounded
note, and git transport fields. The response repeats the now-active
normalized work. A revision is a full new `work` object and parent
submission/version reference. Preserve every revision; never overwrite
the historical row.

If an eval submission is revised after ground truth was revealed, keep
the original pre-reveal submission as the evaluation baseline. Mark the
revision `post_reveal` and include it in the audit/report, but never
credit it as an unassisted eval result.

Use one stable error envelope:

```json
{
  "error": {
    "code": "stable_machine_code",
    "message": "actionable summary",
    "field_errors": [],
    "retryable": false,
    "state": "current_campaign_state",
    "allowed_actions": []
  }
}
```

Use `401` for authentication, `404` for unknown IDs, `409` for
state/version/idempotency conflicts, `413` for size limits, `415` for
content type, `422` for well-formed JSON that violates the model or
assignment, and `423` for the supervisor gate. Validation feedback
should identify exact JSON paths without returning hidden ground truth.

### git-backed work contract

The API payload carries a commit hash, but a file cannot contain the
hash of the commit that contains that same file. Therefore keep
`git_commit` and `artifact_path` in the transport envelope, outside the
`work`/review/confirmation object. At the submitted commit, the
artifact file must equal the canonical JSON serialization of that inner
object, not the whole transport envelope.

Configure and persist:

- the repository root and campaign base commit;
- an executor artifact directory confined beneath that root;
- the executor workbook path, defaulting for this task to
  `tasks/tasks-20260720-fastapi-detour/WORK.md`; and
- a workbook maximum of 16,384 UTF-8 bytes unless deliberately
  overridden by a detour-specific setting before campaign creation.

For every work-bearing mutation, verify with read-only git commands
that:

- the hash is a full commit object ID;
- it exists in this repository and descends from the campaign base and
  the previously accepted executor commit;
- the artifact path is relative, normalized, non-symlinked, below the
  configured executor directory, and exists in that commit;
- its bytes are the canonical JSON for the submitted inner object; and
- the relevant artifact/workbook blobs in the working tree still match
  the submitted commit.

The server never stages, commits, checks out, resets, or otherwise
mutates git.

For each eval ground-truth review, the submitted commit must also
contain a changed executor workbook. Enforce the byte limit at the
commit, verify that it differs from the preceding accepted workbook
blob, and store its blob hash. The executor may edit/prune earlier
notes to stay within the limit. The API cannot judge prose quality, but
the spec expectation is that only durable, high-value learnings are
kept. Work/result artifacts remain the full audit trail; the workbook
is not one.

### rollout JSONL verification

Read the live rollout path from required
`FASTAPI_DETOUR_ROLLOUT_JSONL`. Treat it as read-only. Parse complete
JSONL records incrementally, tolerate only one incomplete trailing
line, and fail closed on malformed completed records or an unsupported
schema. Identify stored evidence by line number plus SHA-256 rather
than trusting mutable offsets alone.

Support the current Codex rollout families used by the bundled timeline
viewer, including `response_item` payloads of type `function_call`,
`function_call_output`, `custom_tool_call`, and
`custom_tool_call_output`, linked through call IDs where available.
Keep schema-specific adapters isolated and test them with sanitized
fixtures.

Between assignment issuance and initial submission, automatically
verify:

- one or more recognized web search/open/fetch events occurred;
- every cited URL, or its canonical URL, appears in a recognized
  research result rather than only in arbitrary shell output;
- the committed submission artifact was written/edited; and
- a git commit-producing event and output agree with `git_commit`.

Before accepting an eval ground-truth review, additionally verify that
the earlier API response containing that submission's ground-truth
reveal appears in the rollout, that the workbook was edited after the
reveal, and that the review commit event agrees with the submitted
hash. Before accepting a real confirmation or revision confirmation,
verify the corresponding echo response occurred before confirmation.

The current API call may not yet have been flushed to the rollout while
the server is handling it, so validate prior required events and record
the current request itself in the detour audit log. Never return raw
rollout content through the API. Return only check names, pass/fail
status, and actionable missing-evidence feedback.

### detour database and reports

Use schema-versioned migrations owned by this detour. At minimum,
persist:

- campaign metadata, source fingerprint, seed, base/last commit, and
  current state;
- frozen cohort rows, queue ordinals, eval masks, and canonical target
  row identity;
- assignments and reveal state;
- immutable submission/revision bodies plus normalized answers;
- eval reviews, work confirmations, and active-revision pointers;
- git and rollout evidence records;
- idempotency records;
- supervisor reports and imported out-of-band reviews; and
- an append-only audit event stream with timestamp, actor, transition,
  request/response digests, and a hash chain.

Use explicit DuckDB transactions for every state transition. FastAPI
handlers must not share an unprotected DuckDB connection across
threads. A single-process writer lock or short connection-per-transaction
store is acceptable; multiple Uvicorn workers are not. The supported
server configuration is one worker. Tests must prove that concurrent
`next`, submit, and confirm calls cannot double-allocate or
double-promote.

Reports are first-class immutable snapshots. Persist canonical JSON in
the detour DB and write atomic JSON and Markdown copies under a
detour-specific report directory. Record SHA-256, source fingerprint,
seed, generation time, and report ID. Do not include bearer tokens,
environment secrets, or raw rollout events.

The evaluation report contains every completed eval assignment,
pre-reveal answers/citations, ground truth, executor/field assessment,
takeaways, post-reveal revisions, commits, and evidence-check results.
The final report contains every real assignment, original missing
fields, preserved existing values, active filled values/citations,
revision history, confirmations, commits, and validation status, plus
completeness summaries. It must be possible for a supervisor to recover
the complete submitted result from the report/detour DB without the
main DB being modified.

### runtime and security

Add compatible direct dependencies for FastAPI and Uvicorn to
`pyproject.toml`, `requirements.txt`, and `pixi.lock`; add HTTP test
support if it is not already transitively available. Provide a
detour-specific Pixi task or a documented module command. Do not put
detour knobs or secrets into `PipelineConfig` merely to reuse the main
REPL configuration path.

Required environment/config values include:

- `FASTAPI_DETOUR_SEED`;
- `FASTAPI_DETOUR_API_TOKEN`;
- `FASTAPI_DETOUR_ROLLOUT_JSONL`;
- source DB, detour DB, repository root, executor directory, workbook,
  and report directory settings; and
- `FASTAPI_DETOUR_SUPERVISOR_REVIEW_JSON` only when an out-of-band
  review is being imported.

Bind to `127.0.0.1` by default. Require an explicit option to bind
elsewhere. Compare bearer tokens in constant time, do not enable CORS
by default, do not accept filesystem paths or SQL from API callers, and
do not serve repository/report files directly. Redact secrets and
ground truth from access/error logs. Validate configured paths before
startup and set a bounded request size.

Expose an app factory for tests and a lifespan that opens/validates
state, imports any matching supervisor review, and closes connections
cleanly. Startup should be idempotent: a fresh state DB freezes the
campaign; an existing one resumes it without regenerating assignments.

### tests and acceptance checks

Add focused tests under `tests/test_detours/` using temporary source,
state, repository, workbook, report, and rollout fixtures. Cover:

- import isolation from `src.repl`, `src.steps`, initialization/runtime
  helpers, and other detours;
- source/detour path alias rejection and proof that source schema,
  row counts, and file bytes do not change;
- startup cohort validation, disjointness, partition-value selection,
  source fingerprinting, and resume mismatch refusal;
- deterministic seeded eval/real order and mask assignment, with
  different seeds producing different orders;
- exact card-equivalent field projection, stable ordering, technical
  exclusions, JSON-safe values, and redaction of every hidden eval
  occurrence;
- current-data read-only integration counts of `181/126`, subset-2
  partitions `17/9/100`, and real cohort `100`;
- current required-field discovery and the missing-count audit above;
- strict JSON/media-type/duplicate-key/extra-key/type/body-size
  rejection and stable error envelopes;
- exact answer-key enforcement, non-empty values, citations, and no
  ground-truth disclosure through validation differences;
- eval submit-then-reveal ordering, special review confirmation,
  assessment/takeaways, workbook update and size limit;
- supervisor report generation, digest-bound environment import,
  pending-gate `423`, approval, changes requested, stale/replayed review,
  and restart behavior;
- real submission echo, explicit confirmation, next assignment, and
  absence of any ground-truth field;
- complete-replacement revisions, confirmation/promotion,
  post-reveal eval tagging, and immutable history;
- final-review completeness, blocking on drafts/missing confirmations,
  final report contents/digests, and final lock;
- commit existence/ancestry/path/canonical-artifact/workbook checks
  using a temporary git repository, while proving the server performs
  no git mutation;
- sanitized rollout fixtures for recognized search, citation URL,
  edit, commit, reveal/echo, malformed/truncated, and unsupported-schema
  cases;
- idempotent replay, conflicting reuse, stale optimistic versions, and
  concurrent `next`/confirm calls; and
- bearer authentication, local binding defaults, secret redaction, and
  clean lifespan shutdown.

Use FastAPI's test client for endpoint/state-machine tests and direct
DuckDB assertions for storage invariants. Keep real-database tests
read-only and marked slow if appropriate. Do not run `src.repl` in any
test or verification path. Run the focused detour tests, lint/type
checks, and the repository's detour test suite after implementation.
