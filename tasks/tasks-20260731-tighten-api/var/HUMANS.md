## human written - ai never touches this
hi humans. this file will be used for any notes or other important things as we move forward with this. it's sort of like AI's `WORK.md` but for us.

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
