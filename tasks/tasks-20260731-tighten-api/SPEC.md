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

If `apply_patch` does not work,
use the `env` workaround.

AI only uses git readonly.

### actual task
go to and review contents of `src/detours/detour_ai_augment/`.
There we have everything almost ready for production.
Some things need to be wired in:

- deploy/provision scripts must provision appendwatch from a root-only dir that cannot even be traversed into by a non-sudo user. we can use the already mounted macos dir to host it which is properly protected from nonsudoers, and this also gives easy access to these files for the host backend. we use systemd for persistence, and we also must ensure that the non-sudoer must have absolutely zero ways to view the python source code.
- api validator currently does not make use of appendwatch. how it should work: api must not accept pushes until human operator manually sets the path to the codex rollout associated with the chat. how it should be seen on agent runtime's end: there should be some generic error that says that api not properly configured and human operator must be contacted. then runtime will flag this to the user. the runtime does not need to know what the error is. but backend api logs should be informative, human operator goes to check them and sees that this var is not set in .env file for api, so operator checks what the rollout path is and sets it there, restarts api and goes back to runtime. now, backend knows what file to compare against. backend can scp the rollout file from vm (using provisioned ssh key from deploy.sh), then create a versioned copy of the appendwatch log from mounted protected dir, and only then  check if status is ok (i.e., not compromised) in that copy of the log. so copying of rollout should precede copying the log, and copying the log should precede checking the log - in this case if log is ok then we're certain that our copy of rollout is still ok. then backend can finally pydantic validate the submission. i think to be able to do this, we're going to have to extend /push contract and require agent runtime to provide a full list of exact excerpt(s) from its web search results that justify its response - per json key in the push payload. what the pydantic validation does it attempts to find an exact match in the rollout (there is some example rollouts for you to review how web searches and responses are structured under "src/detours/detour_ai_augment/data/sample_run/.codex/sessions") and if found, validates that it truly comes from an eligible tool output (like websearch and click, open - those web tools), then shows the matching piece plus a bit of context like some chars before and some chars after, plus the json lines event in which this is located, plus the original call with which this id is associated, plus etc. (see below for details). for rendering the report we should include all these fields as specified below. all in all we should reuse step 10 rendering logic and include everything as if it was a proper researcher card, again docx and txt must be supported and read from --config config.json passed to this detour. so essentially what the human reviewer will see is a familiar card, but there will be a new section (between xlsx and docx) one per each jsonl rollout-line count pair (see below). the human reviewer will then see not only ai output but also validated result from web search. if fails to validate, the api should fail to accept submission and briefly, without details advise that this did not pass validation and they are encouraged to verify all the details of the submission.

So to recap, the sequence of validation is:

* pre-index appendwatch-accepted jsonl which linenumbers are eligible for matching
    * that only includes only lines like,

      ```
      {
        "timestamp": "2026-07-27T16:11:06.607Z",
        "type": "response_item",
        "payload": {
          "type": "function_call_output",
          "id": "fco_019fa458-1fef-7a43-9f53-7d987861ad64",
          "call_id": "call_JrCO9EEdFFwnncEyo0Tky0N3",
          "output": [
            {
              "type": "input_text",
              "text": "a single text value containing citeturn0search0 symbolics; be sure to use valid unicode chars for delimiting these and put these chars as globals on top of api.py"
              }
          ],
          ...
        }
      }
      ```

      from this line we capture timestamp (as the canonical timestamp for evidence piece - because it's the last timestamp when actually this was received), also fco id, call id, and actual single-text-value output text (which we parse by ref_id like citeturn0search0 within).

      then, by looking up corresponding call_id event_msg/web_search_end line (must be unique - if not, raise error), we establish:

      ```
      {
        ...
        "type": "event_msg",
        "payload": {
          "type": "web_search_end",
          "call_id": "call_C9nCCxE2YU5zrv9kI6ewtswG",
          ...
          "results": [
            {
              "type": "text_result",
              "domain": "www.research.ed.ac.uk",
              "ref_id": "turn1search7",
              "snippet": "Image: No photo of Aziz Sheikh ... Professor ... & Sheikh, A., 21 May 2026, In: npj Primary Care Respiratory Medicine. 36, 3 p., 33.",
              "title": "Aziz Sheikh - University of Edinburgh Research Explorer",
              "url": "https://www.research.ed.ac.uk/en/persons/aziz-sheikh-2/"
            },
            ...
          ]
        }
      }
      ```

      from which we link domain, url, title, and snippet to each ref_id.

      and then finally, by same call_id we look up the originating query (must be unique, if not - raise):

      ```
      {
        ...
        "type": "response_item",
        "payload": {
          "type": "function_call",
          "id": "fc_03938c1e0667a7cc016a67831c12b08195ae364f3f129f750c",
          "name": "run",
          "namespace": "web",
          "arguments": "{\"search_query\":[{\"q\":\"\\\"Aziz Sheikh\\\" \\\"MBBS\\\" \\\"MSc\\\" \\\"MD\\\" biography education\"},{\"q\":\"\\\"Aziz Sheikh\\\" born 1968 professor medicine\"},{\"q\":\"\\\"Professor Aziz Sheikh\\\" education University College London MBBS\"},{\"q\":\"site:acmedsci.ac.uk \\\"Aziz Sheikh\\\" biography\"}],\"response_length\":\"long\"}",
          "call_id": "call_C9nCCxE2YU5zrv9kI6ewtswG",
          ...
        }
      }
      ```

      from this, we get fc_id and argument object which must be parsed as json and captured as the full dict.

      that is, it must have:

      - a valid timestamp (from fco),
      - valid call_id, which sets the scope for all further validation
      - all the other shape is as is shown above
      - the single text value is parsed by citeturn0search0 symbolics
      - fco id is the unique id for this function call output, use it to uniquely identify the source of this excerpt
      - we also store unique value of and fc id for each query.

    * and so, this dependency graph is preindexed, i think is even better to dump it into a duckdb table and use as the canonical representation of this rollout
* now we don't need to search in the jsonl - we can search in duckdb.
    * so the duckdb schema for as follows:
        * codex_fc table, 6 cols: pkey, codex.fc_timestamp (from fc json line), codex.fc_id, codex.fc_name (will always be "run" in this setup but no worries, just put the text value here - but always verify it's truly this in the rollout), codex.fc_namespace (same, will always be "web" - but need to verify in rollout) codex.fc_arguments which is a duckdb json object (put all these labels and table names as globals on top of api.py; don't touch vars.py and schema.py because this is a detour)
        * codex_fco table, 3 cols: pkey, codex.fco_timestamp (from fco jsonline), codex.fco_id
        * codex_calls table, 5 cols: pkey, codex.call_id, codex.fc_id, codex.fco_id, codex.rollout_filename (_original_ codex jsonl rollout filename including extension; can be reconstructed from session_id and timestamp from session_meta in the jsonl)
        * codex_turn_ref table, 9 cols: pkey, codex.ref_id (from event_msg corresponding turn-search), codex.call_id (establishes linkage to both fc and fco through codex_calls), codex.ref_domain, codex.ref_snippet, codex.ref_thumbnail_url, codex.ref_title, codex.ref_url (all from event_msg), codex.cite_text (raw text value from fco jsonline for parsed out related ref id)
        * finally, there is a codex_innerdicts table that follows same strict procedures as currently xlsx, docx, and ssn an serializes everything there properly with all proper columns and contract. this innerdicts table will be authoritative downstream.
    * also, in duckdb we establish a view (note that step 08 is overall closest in workflow, try to follow it as close as possible) where:
        * every row is a unique KTP_SOURCE_KEY_COL
        * KTP_FRAGMENT (see vars.py) here is the total number of lines as in `nl -ba`  in the _archived under attempts_ copy of codex. you should modify api.py so that in addition to size and sha256 it also calculated nl -ba. this is helpful because archived attempts are by our design always append only and so this will differ necessarily for different attemtps, and therefore it's a nice file-based identifier for an attempt allowing the overarching approach in this repo where unique data identification is based on filename and fragment within it. this line number will always be usable regardless of what archived copy we deal with. it's of fragment type LINE_NUMBER.  also, notably it's always possible to trim the original codex jsonl at this line number properly, recalc hash and this should match hash inside attempt json. 
        * the KTP_FILENAME_COL for each row will be corresponding codex.rollout_filename
        * now, how do other columns get filled in? other columns include ALL as in ktp.table_1_* but are called ktp.ai_augment_* instead. the list is currently in api.py as COLUMNS but you must rename this to DOCX_COLUMNS and create new one with codex prefixes and fill out these (including in api).
            * the value of these codex-prefixed fields comes obviously from the /push submission. just raw text values.
            * in addition to those, we will construct KTP_AI_AUGMENT_FOOTNOTES_COL (this label must be in globals at top of api.py; note that this is a detour and so main repl pipeline should never be affected or edited). this will be assempled from values of new codex tables above and how exactly this will look like - is shown in an output sample below. just like we have docx_parse we will also create (within detour) codex_parse module helper where we will follow that parser and implement the textual values that will go into footnotes. no need to drag machine readable stuff there - just follow the looks of sample output below and overall of docx_parse architecture. note that footnote numbers at end of each ktp.ai_augment_* value are added programmatically.
            * value of KTP_SOURCE_KEY_COL and ktp draw number is taken from  existing data based on what ktp first and last name was given in the /pull payload (later on we will implement that the api now draws a random source key from duckdb, but for now we are still using the hardcoded sample jsonl).
    * so that view is precreated from an appendwatch-accepted jsonl and further used for look up.
* then look up is simple - see if any row contains an exact match within their codex.cite_text, and if yes grab the necessary data. if multiple rows, select any random one. unused: if multiple rows, fail this and say in error status code to /push client that this particular excerpt (cite it as as submitted) matched multiple entries on validation and they are encouraged to resubmit ensuring that each value is supported by a distinct excerpt unique across searched web pages.
* let's extend the /push contract where together with each excerpt submitted must provide exact url as retrieved from search results. upon validation verify that both excerpt must be within codex.cite_text and also that submitted url must match corresponding codex.ref_url, otherwise fail submission.
* note that this is purely all implemented in duckdb queries, pls consult step 08 for inspiration.

here is what the output should look like:


```
#### ktp.filename: rollout-2026-07-27T12-10-36-019fa457-aac5-7652-8669-9d571206e7cb.jsonl
**ktp.fragment**: 416

**ktp.fragment_type**: line_number

**ktp.draw_number**: 146

**ktp.first_name**: A.

**ktp.last_name**: Sheikh

**ktp.ai_augment_attempt_id**: 20260804T203221_866237Z_6074203f9b8a453f9a2dac2b822bb62b

**ktp.ai_augment_session_metadata**: {"originator":"codex_vscode","source":"vscode","cli_version":"0.146.0-alpha.3.1","model_provider":"openai","model":"gpt-5.6-sol","reasoning_effort":"xhigh","session_id":"019fa457-aac5-7652-8669-9d571206e7cb","timestamp":"2026-07-27T16:10:36.764Z"}

**ktp.ai_augment_researcher_author**: **AI-generated text**: "Professor Sir Aziz Sheikh OBE; publishes as Aziz Sheikh and A. Sheikh; ORCID 0000-0001-7022-3056."^1,2^

**ktp.ai_augment_place_of_residence**: **AI-generated text**: "Scotland, United Kingdom (Companies House country of residence); professionally based at the University of Oxford, England."^3^

**ktp.ai_augment_gender**: **AI-generated text**: "Male."^4,5^

**ktp.ai_augment_age_first_publication_according_to_openalex_profile**: **AI-generated text**: "28-29; born in December 1968, with the earliest credible work on the OpenAlex profile dated 13 December 1997. Earlier records on the profile are identity-conflation errors."^6^

**ktp.ai_augment_education**: **AI-generated text**: "BSc Physiology and MBBS, University College London; MSc, London School of Hygiene and Tropical Medicine; MD, Imperial College London."^7^

**ktp.ai_augment_academic_position_s_**: **AI-generated text**: "University of Oxford: Pro-Vice-Chancellor, Head of the Nuffield Department of Primary Care Health Sciences, and Nuffield Professor of Primary Care Health Sciences. Previously Chair of Primary Care Research and Development, Director of the Usher Institute, and Dean of Data at the University of Edinburgh."^8^

**ktp.ai_augment_social_capital**: **AI-generated text**: "Officer of the Order of the British Empire (2014) and Knight Bachelor (2022); adviser to governments, the World Bank, World Health Organization, and World Innovation Summit for Health; committee service for the Academy of Medical Sciences and Royal Society."^7^

**ktp.ai_augment_links_**: **AI-generated text**: "Oxford profile: https://www.phc.ox.ac.uk/team/aziz-sheikh; ORCID: https://orcid.org/0000-0001-7022-3056; OpenAlex: https://openalex.org/A5026215303."^8^

**ktp.ai_augment_footnotes**: 

1. "...excerpt from codex.cite_text with some chars before and some chars after **web_search_excerpt number 1** in the list submitted with this value for ktp.ai_augment_researcher_author at /pull, where the raw submitted web search excerpt is boldened within the context...", retrieved from web run tool using arguments^1^ on "fco timestamp", url://from-codex.ref_url
2. "...excerpt from codex.cite_text with some chars before and some chars after **web_search_excerpt number 2** in the list submitted with this value for ktp.ai_augment_researcher_author at /pull, where the raw submitted web search excerpt is boldened within the context...", retrieved from web run tool using arguments^2^ on "fco timestamp", url://from-codex.ref_url
3. "...excerpt from codex.cite_text with some chars before and some chars after **web_search_excerpt number 1** in the list submitted with this value for ktp.ai_augment_place_of_residence at /pull, where the raw submitted web search excerpt is boldened within the context...", retrieved from web run tool using arguments^3^ on "fco timestamp", url://from-codex.ref_url
4. ..etc

**ktp.ai_augment_footnote_arguments**: 

1. raw codex.fc_arguments value corresponding to fco from footnote 1 above
2. raw codex.fc_arguments value corresponding to fco from footnote 2 above
3. raw codex.fc_arguments value corresponding to fco from footnote 3 above
4. ..etc

**ktp.ai_augment_comments**:

- **AI-generated text**: "OpenAlex author A5026215303 appears conflated: it includes a 1962 A. Sheikh paper that predates Aziz Sheikh's documented December 1968 birth. Treat the literal earliest-work age and profile bibliometrics as unreliable; ORCID and the verified 1997 BMJ publication are safer identity anchors." (2026-08-04T20:32:21Z)
```

**importantly:**

> [!ATTENTION]
> **and I cannot stress that enough!**

**all** implementation must be done _surgically_.
the code is only added when necessary and
existing code is not touched unless truly necessary
(e.g., no purposelessly stripping comments etc.).

## how ai understood the spec

### scope and required outcome

This is a production-hardening follow-up for the existing, deliberately
small detour under `src/detours/detour_ai_augment/`. The implementation
must wire the existing appendwatch, Lima deployment, SSH identity, archived
Codex rollout, DuckDB provenance index, `/push` validator, detour innerdict,
and researcher-card output into one fail-closed chain. It must not invoke
`src.repl`, alter the main pipeline, edit its `vars.py` or `schema.py`, or
write to the configured main-pipeline database.

One Codex rollout/session is expected eventually to contain many successive
`/pull` -> research -> `/push` cycles. Every push archives the then-current
cumulative rollout prefix. The rollout filename/session can therefore repeat
across attempts, while its physical line count advances and demarcates the
prefix used by each attempt. This task continues to serve the current
hardcoded task; advancing `/pull` to the next task after an accepted push is a
later change. A later task may concern a new researcher or the same researcher
again, so nothing implemented here may assume one rollout or one accepted
attempt per researcher.

The trust chain for an accepted push is:

1. appendwatch ran as root before the `ai` account could start Codex and
   continuously monitored `/home/ai/.codex/sessions`;
2. the operator configured the absolute guest path of this chat's rollout;
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
   DOCX researcher-card artifact.

No later step may run when an earlier step fails.

### surgical implementation boundary

The implementer must write surgical code: make only changes strictly required
by this spec and leave unrelated code, comments, formatting, and behavior
untouched. Do not perform incidental refactors or cleanup.

The expected production edits are narrowly confined to `api.py`, a new
detour-local `codex_parse.py`, focused tests, and the minimum serving-task
wiring needed to pass `--config config.json`. Touch `deploy.sh` or
`provision.sh` only if their already implemented appendwatch behavior is shown
not to satisfy this revised contract. `appendwatch.py`, its regression tests,
`README.md`, `.env.example`, the main pipeline, `src/helpers/vars.py`,
`src/helpers/schema.py`, architecture assets, and sample/ground-truth data
remain untouched.

All detour-owned table names, column labels, citation delimiters, paths,
collection/body bounds, context-length settings, and other repeated numeric
values belong in named globals at the top of `api.py`; do not scatter literals
through the implementation. Reuse existing main-pipeline constants by import
where the human section names them, without adding detour labels to the main
constants modules.

Reuse the existing codebase at its current seams rather than restating or
forking it: `PipelineConfig.from_json()` for config, the deterministic sibling
DB-path pattern in `detour_step4_breakdown.py`, step 08 and
`duckdb_utils.py` for flat relation -> output view -> common JSONL-innerdict
materialization, `docx_parse.py` for the parser/extraction/render separation,
and `cards.py`/step 10 for card assembly and TXT/DOCX ZIP output. Keep the
Codex-specific code detour-local and adapt only the data entering those seams.

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
Do not otherwise redesign the existing private SSH service. The current
manual `run_appendwatch.sh` is not the persistence mechanism.

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

Serving the detour requires `--config config.json`. Parse it once at startup
with the existing `PipelineConfig.from_json()` contract
and use its existing `db_file`, `output_dir`, `output_format`,
`pandoc_reference_docx`, `timezone`, and `total_draws` settings. Accept only
`txt` or `docx`; DOCX output also requires a readable reference DOCX. The
configured pipeline DuckDB is context only and must be opened read-only. Follow
the existing detour DB separation pattern: derive one deterministic sibling
DuckDB path from `config.db_file` using a named detour ID and the
`<source-stem>__detour_<detour-id><suffix>` convention. Open that separate
detour DB read/write for all Codex relations and preserve it across attempts;
do not copy or mutate the source DB. Serialize detour-DB write transactions. A
missing or invalid config prevents serving; do not silently fall back to
another path or format.

Use the repository-root `.env`, which is already ignored, with
`python-dotenv`'s normal rule that a real process environment value wins.
The per-chat setting is:

```dotenv
FASTAPI_DETOUR_ROLLOUT_JSONL=/home/ai/.codex/sessions/YYYY/MM/DD/rollout-....jsonl
```

It is intentionally unset until the operator identifies the rollout for
the active chat. It must be an absolute, normalized path below the watched
sessions root and must name a rollout JSONL file; reject traversal, control
characters, symlinks/unmonitored paths, and paths outside that root.

The backend must reuse the existing dedicated identity, known-hosts file,
Lima SSH config, target, and host-mounted appendwatch-report path already
defined by deployment. Expose only the few matching top-level API settings
needed to make those paths testable; do not add a new configuration system or
copy private-key material. Keep defaults aligned with `deploy.sh`, and ensure
a custom `--mount` can supply the corresponding host report path.

If the per-chat rollout setting or a required deployment/SSH/status setting
is missing, blank, invalid, or unreadable, the configured API may still start
and `/pull` may still work, but `/push` returns HTTP 503 with only:

```json
{"detail":"API is not properly configured. Contact the human operator."}
```

Startup and request logs must name the exact missing/invalid setting and
remediation for the operator. The client response, OpenAPI schema, and
access log must not reveal environment names, host/guest paths, SSH data,
appendwatch status, or compromise reasons. Restarting the API after editing
`.env` must pick up the new rollout.

### ordered `/push` integrity gate

FastAPI's automatic body-model validation would happen too early. Accept a
bounded raw JSON request in the route and call
`Submission.model_validate_json(...)` explicitly only after the integrity
gate below. Basic transport limits may run first, but no field/evidence
validation, ground-truth lookup, accepted-submission write, or detailed
validation response may precede the gate.

For each push attempt, use a unique backend-only attempt/version directory
and perform this exact order:

1. Validate operator/deployment configuration without inspecting the body.
2. SCP the configured rollout from the VM into a temporary file using the
   dedicated key and the same pinned SSH/known-hosts options as `deploy.sh`.
   Build an argv list without `shell=True`; fsync and atomically publish the
   archived rollout, then record its size, SHA-256, and physical line count
   equivalent to `nl -ba`. Count every physical JSONL line in the immutable
   archive, including a final non-newline-terminated line; do not invoke a
   shell command merely to calculate it.
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
7. After every evidence lookup succeeds, resolve the hardcoded current
   researcher against the configured pipeline DuckDB opened read-only; require
   one source key and its draw/name context. In the detour DuckDB, create the
   final Codex output view and materialize `codex_innerdicts` atomically.
8. Only after that transaction succeeds, load ground truth, write the accepted
   response and configured card artifact, mark the attempt accepted, and
   return the existing two-line NDJSON response.

The order above is an invariant, not an optimization: rollout copy first,
report copy second, copied-report check third, DuckDB provenance index fourth,
payload validation fifth, accepted innerdict/card writes last. A rejected
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

For the current hardcoded task, `/pull` must expose the selected researcher's
`ktp.first_name` and `ktp.last_name` and the nine AI-augment fields to fill.
The backend, not the client, retains the authoritative source key and draw
number used after acceptance. Queueing the next task is out of scope.

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

After validation, obtain the current researcher source key, draw number, first
name, and last name from existing data using the identity exposed by `/pull`.
The configured pipeline DuckDB remains read-only. In the detour DuckDB, append
one accepted flat row to a narrowly named backing table and expose it through
a `codex_output` view whose columns follow this order:

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
stage/result manifest, and `response.jsonl`. Preserve the two-line NDJSON
response: normalized AI-augment values first and mapped DOCX ground truth
second.

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
- missing rollout configuration producing only generic 503 while logs name
  `FASTAPI_DETOUR_ROLLOUT_JSONL`, with `/pull` remaining available;
- required `--config`, read-only access to its pipeline DuckDB, TXT/DOCX
  selection, reference-DOCX handling, deterministic sibling detour-DB path,
  and before/after proof of no writes to the configured source DB;
- an instrumented assertion of the exact sequence SCP -> status copy ->
  copied-status check -> rollout line count/index transaction -> Pydantic/SQL
  lookup -> output view/innerdict -> ground truth/card;
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
  TXT and DOCX ZIPs, archive hashes, two-line success NDJSON, and no accepted
  artifacts on rejection; and
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
