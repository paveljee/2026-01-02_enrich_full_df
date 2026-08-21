## human written - ai never touches this
hi humans. this file will be used for any notes or other important things as we move forward with this. it's sort of like AI's `WORK.md` but for us.

### 2026-08-21 - pytest-bdd proposal
from codex, after a conversation -
copied and pasted from the task rollout.

<!---begin ai slop--->
The stronger design is a traceability graph with several pytest touchpoints:

1. The tag identifies the complete pytest node:

   ```gherkin
   @test_e2e_operator::test_accepted_run
   ```

2. Each interface-owned `Scenario` is one phase of that test.

3. Each `Given` consumes named state established by earlier phases.

4. Each `When` performs one interaction across the current interface.

5. Each `Then` produces a named state consumed by later phases.

6. A custom pytest-bdd parser resolves symbolic references such as:

   - `<AiAugmentDetourConfig.db_file>` → typed config-field reference
   - `<ktp.namekey>` → typed column reference
   - `<selected_researcher>` → phase output/fixture
   - `<active_sanction>` → phase output/fixture

That makes the scenario chain executable and inspectable at step level:

```gherkin
@test_e2e_operator::test_accepted_run
Scenario: Control Centre selects an eligible researcher from the Main DB
  Given the Backend has no active sanction
  And the Agent Runtime is idle
  When the Control Centre reads <AiAugmentDetourConfig.db_file>
  Then <selected_researcher> contains one eligible <ktp.namekey> and source context
```

```gherkin
@test_e2e_operator::test_accepted_run
Scenario: Backend sanctions the Control Centre’s selected researcher
  Given the Control Centre has produced <selected_researcher>
  And the Agent Runtime remains idle
  When the Control Centre sends authenticated `POST /_control/push`
  Then the Backend durably establishes <active_sanction>
```

```gherkin
@test_e2e_operator::test_accepted_run
Scenario: Control Centre starts the Agent Runtime for the active sanction
  Given the Backend has established <active_sanction>
  And the Human Operator has requested execution
  When the Control Centre starts Codex through SSH
  Then <agent_run> is running for <active_sanction>
```

```gherkin
@test_e2e_operator::test_accepted_run
Scenario: Backend accepts the Agent Runtime’s sanctioned submission
  Given the Control Centre has started <agent_run>
  And the Backend exposes <active_sanction>
  When the Agent Runtime calls `GET /pull`
  And submits exactly validated evidence to `POST /push`
  Then the Backend produces <accepted_attempt>
  And consumes <active_sanction>
```

The pytest-bdd implementation can expose the phase boundaries through `target_fixture`:

```python
@then(
    phase_parser("<selected_researcher> contains one eligible "
                 "<ktp.namekey> and source context"),
    target_fixture="selected_researcher",
)
def selected_researcher_phase(...) -> SelectedResearcher:
    ...
```

The next phase consumes `selected_researcher`, so the handoff is enforced rather than merely described.

A custom parser can return typed references instead of loose strings:

```python
PhaseReference("selected_researcher")
ConfigFieldReference(AiAugmentDetourConfig, "db_file")
ColumnReference("ktp.namekey")
```

pytest-bdd hooks can then report:

```text
test_e2e_operator.py::test_accepted_run
  phase: selected_researcher
  interface: I002.03
  step: Control Centre reads AiAugmentDetourConfig.db_file
```

One technical boundary remains important: custom step parsers do not themselves combine multiple Gherkin `Scenario`s into one pytest test. We would need a small deterministic composition layer that:

1. Groups scenarios by `@module::test_name`.
2. Connects produced and consumed phase references.
3. Rejects missing, duplicate, or cyclic phases.
4. Emits one ordered pytest-bdd scenario per test address.

That composition is preferable to arbitrary `@phase_01` tags because the state handoffs determine the order structurally. A failed or missing phase becomes detectable at collection/validation time, and pytest reports still identify the precise interface step that failed.
<!---end ai slop--->

### 2026-08-20 - Pending Lima lifecycle work
ai written from `WORK` but so we don't forget:

```markdown
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
```

### 2026-08-19 - some coverage gaps
re: `src/detours/detour_ai_augment/tests/test_e2e_operator.py`,
so at some point i asked ai,

> what exactly does it prove? what it doesnt prove?  apart from of course not being run on fresh aivm, but that's ok.
> what workflows of our detour ai augment remain uncovered by e2e?

and below it added some thoughts after reflection.

I'm not claiming it's accurate for sure, but
just keeping it for future reference or
it will get lost in the codex rollout.

```markdown
The three tests now form a solid real startup/read-side E2E contour. They do not yet exercise the detour’s write/execution workflow.

### What the passing tests prove

- A missing detour DuckDB is created from the real read-only source DB and production attempt archive.
- Every archived attempt directory is counted and classified through the production reconciliation pathway.
- Reconciliation emits exactly one aggregate summary.
- Restored manifests and accepted counts agree with DuckDB contents.
- Invalid plus restored attempts equal all discovered attempt directories.
- The real dashboard supervises the real backend and becomes reachable on the production ports.
- The actual installed Google Chrome loads the real NiceGUI application without console or page errors.
- The UI reports 307 researchers.
- A real sourcekey can be searched, selected, and reduced to exactly one displayed row.
- Attempt history is displayed for the selected researcher.
- A real source-backed researcher card renders and includes the expected first and last name.
- Repeated restarts produce byte-equivalent logical contents across every DuckDB table and sequence.
- Reconciliation is idempotent on subsequent starts.
- Browser-visible history and card text remain identical across restarts.
- The existing AIVM is reachable.
- Each test leaves the complete repository and detour production data trees unchanged.

### Important limitations inside those claims

- The test does not inspect all 307 rows in Chrome. It checks the reported total and one real searchable row.
- The production archive currently contains no accepted attempt satisfying today’s HTTP-log contract. Therefore the positive accepted-attempt restoration/history branch did not execute.
- The reconstruction test consequently proves correct invalid-archive handling and base DB reconstruction, but not successful replay of a current-contract accepted attempt.
- AIVM is only probed for reachability. No Codex process is started inside it.
- The host OpenAlex key reaches dashboard startup, but this run does not prove that a real agent process inside AIVM receives or uses it.
- Chrome runs headlessly. It is the real Chrome binary, but headed-window behavior, extensions, and the operator’s profile are outside the test.

### Workflows still lacking real operator E2E coverage

1. **Successful attempt execution**

   Dashboard action → SSH/AIVM → Codex → `/pull` → rollout/web tools → `/push` → archived HTTP request/response → DuckDB materialization → history/card/TXT/DOCX.

2. **Positive archive restoration**

   Rebuilding a deleted DuckDB from at least one valid, accepted, current-contract attempt and proving all accepted values, evidence, standardized values, history, and card output are restored.

3. **Evidence rejection and retry**

   Initial evidence rejection, exhaustive per-excerpt diagnostics, standardized retry schema, immutable baseline enforcement, corrected retry, withdrawal, and eventual acceptance.

4. **External execution synchronization**

   A Codex run started outside the dashboard, detection that Codex is busy, Queue-only behavior, importing the resulting external attempt, and starting the queued dashboard attempt afterward.

5. **Execution controls**

   Real queueing, serial dequeue, rerun with a new attempt ID, cancellation, and proof that both remote Codex and local supervising processes exit.

6. **Multiple runs in one rollout**

   Several pull/push cycles for different—or repeated—researchers in one cumulative rollout, with correct sanction, attempt, line-count, and retry-baseline isolation.

7. **Failure and recovery paths**

   Malformed or missing rollout, appendwatch rejection, backend interruption, failed push, restart during execution, and recovery without duplicate materialization.

8. **Real OpenAlex use from AIVM**

   The key being available to the actual agent process and an institution validation request succeeding from inside the guest.

9. **Full real-stack browser interactions**

   Sorting, responsive layout, text selection, stable filters, row highlighting, card caching, action transitions, and attempt expansion have simulated Playwright coverage, but not real backend/AIVM operator coverage.

The highest-value next test would be one successful dashboard-initiated attempt. It would connect most currently separate components and expose failures that startup/read-only tests cannot detect.
```
