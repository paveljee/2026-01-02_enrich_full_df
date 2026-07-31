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
- api validator currently does not make use of appendwatch. how it should work: api must not accept pushes until human operator manually sets the path to the codex rollout associated with the chat. how it should be seen on agent runtime's end: there should be some generic error that says that api not properly configured and human operator must be contacted. then runtime will flag this to the user. the runtime does not need to know what the error is. but backend api logs should be informative, human operator goes to check them and sees that this var is not set in .env file for api, so operator checks what the rollout path is and sets it there, restarts api and goes back to runtime. now, backend knows what file to compare against. backend can scp the rollout file from vm (using provisioned ssh key from deploy.sh), then create a versioned copy of the appendwatch log from mounted protected dir, and only then  check if status is ok (i.e., not compromised) in that copy of the log. so copying of rollout should precede copying the log, and copying the log should precede checking the log - in this case if log is ok then we're certain that our copy of rollout is still ok. then backend can finally pydantic validate the submission. i think to be able to do this, we're going to have to extend /push contract and require agent runtime to provide a full list of exact excerpt(s) from its web search results that justify its response - per json key in the push payload. what the pydantic validation does it attempts to find an exact match in the rollout (there is an example rollout for you to review how web searches and responses are structured under "src/detours/detour_ai_augment/data/sample_run/.codex/sessions") and if found, validates that it truly comes from an eligible tool output (like websearch and click, open - those web tools), then takes the whole json object (or rather, at least two objects - object with tool output and with the tool call with this id) and puts it directly into the markdown report (we can use details/summary tag to hide; we may also reformat it as not a table but as a doc with sections where ai output plus validated match and ground truth output are just paragraphs within subsection for var). the human reviewer will then see not only ai output but also validated result from web search. if fails to validate, the api should fail to accept submission and briefly, without details advise that this did not pass validation and they are encouraged to verify all the details of the submission.

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
