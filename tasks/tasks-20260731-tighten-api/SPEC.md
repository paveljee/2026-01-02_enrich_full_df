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
        * codex_turn_search table, 8 cols: pkey, codex.ref_id (from event_msg corresponding turn-search), codex.call_id (establishes linkage to both fc and fco through codex_calls), codex.ref_domain, codex.ref_snippet, codex.ref_title, codex.ref_url (all from event_msg), codex.cite_text (raw text value from fco jsonline for parsed out related ref id)
        * finally, there is a codex_innerdicts table that follows same strict procedures as currently xlsx, docx, and ssn an serializes everything there properly with all proper columns and contract. this innerdicts table will be authoritative downstream.
    * also, in duckdb we establish a view (note that step 08 is overall closest in workflow, try to follow it as close as possible) where:
        * every row is a unique KTP_SOURCE_KEY_COL
        * KTP_SOURCE_KEY_COL (see vars.py) here is the total number of lines as in `nl -ba`  in the _archived under attempts_ copy of codex. you should modify api.py so that in addition to size and sha256 it also calculated nl -ba. this is helpful because archived attempts are by our design always append only and so this will differ necessarily for different attemtps, and therefore it's a nice file-based identifier for an attempt allowing the overarching approach in this repo where unique data identification is based on filename and fragment within it. this line number will always be usable regardless of what archived copy we deal with. it's of fragment type LINE_NUMBER.  also, notably it's always possible to trim the original codex jsonl at this line number properly, recalc hash and this should match hash inside attempt json. 
        * the KTP_FILENAME_COL for each row will be corresponding codex.rollout_filename
        * now, how do other columns get filled in? other columns include ALL as in ktp.table_1_* but are called ktp.ai_augment_* instead. the list is currently in api.py as COLUMNS but you must rename this to DOCX_COLUMNS and create new one with codex prefixes and fill out these (including in api).
            * the value of these codex-prefixed fields comes obviously from the /push submission. just raw text values.
            * in addition to those, we will construct KTP_AI_AUGMENT_FOOTNOTES_COL (this label must be in globals at top of api.py; note that this is a detour and so main repl pipeline should never be affected or edited). this will be assempled from values of new codex tables above and how exactly this will look like - is shown in an output sample below. just like we have docx_parse we will also create (within detour) codex_parse module helper where we will follow that parser and implement the textual values that will go into footnotes. no need to drag machine readable stuff there - just follow the looks of sample output below and overall of docx_parse architecture. note that footnote numbers at end of each ktp.ai_augment_* value are added programmatically.
            * value of KTP_SOURCE_KEY_COL and ktp draw number is taken from  existing data based on what ktp first and last name was given in the /pull payload (later on we will implement that the api now draws a random source key from duckdb, but for now we are still using the hardcoded sample jsonl).
    * so that view is precreated from an appendwatch-accepted jsonl and further used for look up.
* then look up is simple - see if any row contains an exact match within their codex.cite_text, and if yes grab the necessary data. if multiple rows, fail this and say in error status code to /push client that this particular excerpt (cite it as as submitted) matched multiple entries on validation and they are encouraged to resubmit ensuring that each value is supported by a distinct excerpt unique across searched web pages.
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

**ktp.ai_augment_researcher_author**: Professor Sir Aziz Sheikh OBE; publishes as Aziz Sheikh and A. Sheikh; ORCID 0000-0001-7022-3056.^1,2^

**ktp.ai_augment_place_of_residence**: Scotland, United Kingdom (Companies House country of residence); professionally based at the University of Oxford, England.^3^

**ktp.ai_augment_gender**: Male.^4,5^

**ktp.ai_augment_age_first_publication_according_to_openalex_profile**: 28-29; born in December 1968, with the earliest credible work on the OpenAlex profile dated 13 December 1997. Earlier records on the profile are identity-conflation errors.^6^

**ktp.ai_augment_education**: BSc Physiology and MBBS, University College London; MSc, London School of Hygiene and Tropical Medicine; MD, Imperial College London.^7^

**ktp.ai_augment_academic_position_s_**: University of Oxford: Pro-Vice-Chancellor, Head of the Nuffield Department of Primary Care Health Sciences, and Nuffield Professor of Primary Care Health Sciences. Previously Chair of Primary Care Research and Development, Director of the Usher Institute, and Dean of Data at the University of Edinburgh.^8^

**ktp.ai_augment_social_capital**: Officer of the Order of the British Empire (2014) and Knight Bachelor (2022); adviser to governments, the World Bank, World Health Organization, and World Innovation Summit for Health; committee service for the Academy of Medical Sciences and Royal Society.^7^

**ktp.ai_augment_links_**: Oxford profile: https://www.phc.ox.ac.uk/team/aziz-sheikh; ORCID: https://orcid.org/0000-0001-7022-3056; OpenAlex: https://openalex.org/A5026215303.^8^

**ktp.ai_augment_footnotes**: 

1. "...excerpt from codex.cite_text with some chars before and some chars after **web_search_excerpt number 1** in the list submitted with this value for ktp.ai_augment_researcher_author at /pull, where the raw submitted web search excerpt is boldened within the context...", accessed "fco timestamp", url://from-codex.ref_url
2. "...excerpt from codex.cite_text with some chars before and some chars after **web_search_excerpt number 2** in the list submitted with this value for ktp.ai_augment_researcher_author at /pull, where the raw submitted web search excerpt is boldened within the context...", accessed "fco timestamp", url://from-codex.ref_url
3. "...excerpt from codex.cite_text with some chars before and some chars after **web_search_excerpt number 1** in the list submitted with this value for ktp.ai_augment_place_of_residence at /pull, where the raw submitted web search excerpt is boldened within the context...", accessed "fco timestamp", url://from-codex.ref_url
4. ..etc

**ktp.ai_augment_search_queries**: 

1. raw codex.fc_arguments value corresponding to fco from footnote 1 above
2. raw codex.fc_arguments value corresponding to fco from footnote 2 above
3. raw codex.fc_arguments value corresponding to fco from footnote 3 above
4. ..etc

**ktp.ai_augment_comments**:

- **AI** commented: OpenAlex author A5026215303 appears conflated: it includes a 1962 A. Sheikh paper that predates Aziz Sheikh's documented December 1968 birth. Treat the literal earliest-work age and profile bibliometrics as unreliable; ORCID and the verified 1997 BMJ publication are safer identity anchors. (2026-08-04T20:32:21Z)
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
must wire the existing appendwatch, Lima deployment, SSH identity, Codex
rollout, `/push` validator, and submission report into one fail-closed
chain. It must preserve the current `/pull` task and the current nine
annotation fields. It must not invoke `src.repl`, alter the main pipeline,
or write to a pipeline database.

The trust chain for an accepted push is:

1. appendwatch ran as root before the `ai` account could start Codex and
   continuously monitored `/home/ai/.codex/sessions`;
2. the operator configured the absolute guest path of this chat's rollout;
3. the backend copied that rollout over the dedicated AIVM SSH connection;
4. only after the rollout copy completed, the backend made an immutable,
   versioned copy of appendwatch's protected status log;
5. only after the status-log copy completed, the backend checked that copy
   and proved the archived rollout was the exact rollout version marked OK;
6. only then did Pydantic validate the submitted values and their exact
   web-tool excerpts against the archived rollout; and
7. only a fully valid attempt produced the normal response and reviewer
   report.

No later step may run when an earlier step fails.

### surgical implementation boundary

The implementer must write surgical code: make only changes strictly required
by this spec and leave unrelated code, comments, formatting, and behavior
untouched. Do not perform incidental refactors or cleanup.

The expected production edits are narrowly confined to `deploy.sh`,
`provision.sh`, and `api.py`, plus focused tests and the minimum README/`.env`
example updates needed to operate those changes. `appendwatch.py` and its
existing regression tests should remain unchanged unless implementation
proves a specific change is indispensable for this exact flow. The manual
`run_appendwatch.sh`, architecture assets, sample data, main pipeline, and
unrelated project configuration are out of scope.

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

If the rollout setting or a required deployment/SSH/status setting is
missing, blank, invalid, or unreadable, the API may still start and `/pull`
may still work, but `/push` returns HTTP 503 with only:

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
   archived rollout, then record its size and SHA-256.
3. Copy the current atomic appendwatch tree report from the mounted protected
   host directory into the attempt directory. Fsync it, publish it under a
   unique versioned name, and record its SHA-256. Never inspect the live
   report and never check status before this copy exists.
4. Parse only that copied report. Reconstruct the configured rollout's exact
   relative tree path and require one unambiguous `OK` file entry beneath
   non-compromised ancestors. Missing, duplicated, malformed, degraded,
   unverified, deleted, or `COMPROMISED` status fails closed.
5. Parse the archived rollout as JSONL and build the eligible evidence
   index. Completed malformed records fail validation; at most one
   incomplete trailing record may be ignored because the chat is live.
6. Finally run the strict Pydantic submission and evidence validation using
   that immutable evidence index as validation context.
7. Only after success, load ground truth, write accepted response artifacts,
   and return the existing two-line NDJSON response (normalized AI values,
   then ground truth).

The order above is an invariant, not an optimization: rollout copy first,
report copy second, copied-report check third, payload validation last.

### extended submission contract

The outer key set remains exactly `COLUMNS`. Each field now carries its AI
value and the full list of literal web-result excerpts used to justify that
value:

```json
{
  "ktp.table_1_researcher_author": {
    "value": "Professor ...",
    "web_search_excerpts": [
      "exact contiguous text copied from an eligible web-tool output"
    ]
  }
}
```

The example is abbreviated; a real body must contain all nine current
outer keys and no others. Every inner object has exactly `value` and
`web_search_excerpts`; `value` retains the current non-null rule, and every
field has at least one non-blank, unique excerpt. Use strict types,
`extra="forbid"`, and documented collection/string/body bounds. The agent
must supply every excerpt it relied on; the API can prove presence and
provenance, while the human report remains responsible for judging whether
the excerpt substantively supports the answer.

Exact means a contiguous substring of one decoded text block in one
eligible output, with no case folding, whitespace collapsing, Unicode
normalization, fuzzy matching, or joining across blocks. An excerpt may be
reused across fields when it genuinely supports them.

### eligible Codex evidence

The bundled sample rollout establishes the current schema:

- the call is a complete top-level `response_item` whose payload is
  `type="function_call"`, `namespace="web"`, `name="run"`, with a non-empty
  `call_id` and JSON-object arguments;
- eligible arguments perform `search_query`, `open`, or `click` (with
  `response_length` and similar transport options allowed); and
- the result is a complete top-level `response_item` whose payload is
  `type="function_call_output"` with the same `call_id`. Current outputs are
  arrays of `input_text` blocks; isolate schema adapters so a documented
  string/text-block variant can be supported without broadening eligibility.

For each submitted excerpt, require at least one such eligible call/output
pair containing the exact text in the output. A matching assistant message,
reasoning item, web call arguments, `event_msg/web_search_end` summary alone,
shell/`exec_command` output, API response, submitted file, or orphan output
does not qualify. Search/open/click output may have a corresponding
`event_msg/web_search_end`; retain it as optional context, but it does not
replace the required pair.

Index records by rollout line number, line SHA-256, and `call_id`. Preserve
every distinct matching eligible pair in rollout order and deduplicate a
pair reused by multiple excerpts. Reject malformed IDs, ambiguous duplicate
call/output IDs, unsupported payload shapes, or an excerpt with no eligible
match.

### artifacts, report, and client-visible failures

Every accepted submission directory must contain the archived rollout, the
versioned appendwatch status copy used to authorize it, their hashes, the
normal `response.jsonl`, and `response.md`. Record an attempt ID and validation
stage/result so pre-validation archives cannot be mistaken for accepted
submissions. Never overwrite an earlier archive or status copy.

Replace the wide Markdown table with a field-oriented document. For each
annotation variable, show these subsections in order:

1. AI response;
2. validated web evidence, grouped by submitted excerpt; and
3. human/ground-truth response.

Under the evidence subsection, use collapsed `<details>/<summary>` blocks
and include the complete matched function-call JSON object and complete
function-call-output JSON object, plus optional matching web event metadata.
Do not truncate the objects. JSON/HTML-escape untrusted values so rollout
content cannot break the report structure or inject active HTML. Report
metadata must identify the archived rollout and appendwatch snapshot by
filename and SHA-256.

Any structural, appendwatch-integrity, rollout-parse, eligibility, or exact-
excerpt failure must reject the submission, must not return ground truth,
and must not create accepted response artifacts. Return one brief HTTP 422
message for all such cases:

```json
{
  "detail": "Submission did not pass validation. Verify all details and try again."
}
```

The backend log must include attempt ID, failed stage, field name where
applicable, and an actionable reason for the operator, without echoing an
entire excerpt or leaking secrets. Do not let FastAPI's default detailed
Pydantic error body bypass this policy.

### implementation tests and acceptance

Keep the existing appendwatch regression suite and add focused tests for:

- protected asset staging/self-install, systemd enable/start/restart,
  restrictive paths/modes, service verification before the `ai` shell, and
  negative source/report access probes as `ai`;
- missing rollout configuration producing only generic 503 while logs name
  `FASTAPI_DETOUR_ROLLOUT_JSONL`, with `/pull` remaining available;
- an instrumented assertion of the exact sequence SCP -> status copy ->
  copied-status check -> rollout parse -> Pydantic -> ground truth/dump;
- strict SCP argv/known-hosts/key use, path confinement, unique atomic
  archives, and custom-mount connection settings;
- copied-report parsing for nested exact paths, OK, compromised ancestors or
  rollout, global degradation, missing/duplicate paths, and malformed trees;
- strict nine-field/inner-object models, no evidence-free field, exact
  Unicode/whitespace behavior, absent excerpts, duplicate IDs, and stable
  generic 422 responses with no ground-truth leak;
- sanitized fixtures for search, open, and click call/output pairs, plus
  negative assistant, reasoning, `web_search_end`-only, shell-output, orphan,
  malformed JSONL, and unsupported-schema cases; and
- complete, deduplicated, escaped call/output objects in the field-oriented
  Markdown report, archive hashes, preserved two-line success NDJSON, and no
  accepted artifacts on rejection.

Use mocks/fakes for host SCP and the narrow provisioning checks, plus a small
sanitized rollout fixture shaped like the supplied sample. Keep existing
appendwatch tests as the monitoring regression proof rather than duplicating
them. This specification task itself changes only
`SPEC.md` and `WORK.md`; production code, tests, README/operator instructions,
and `.env.example` are for the later implementation task.
