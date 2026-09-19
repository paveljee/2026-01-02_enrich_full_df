> I copy and paste into here
> from chat if there is some bits
> I would like to persist, for a while.
> The text below may be AI-generated;
> this file is just called `HUMANS.md`
> because I maintain it vs. agents.
> signed off: Pavel

# Pre-commit-operator acceptance gate before P26

**Current priority: obtain a failure-free `pixi run pre-commit-operator` run before starting P26.**
The completed `find`/evidence-eligibility fix is not full operator acceptance. P26–P30 remain
approved but pending; they must not be used to obscure failures in the current implementation.

Updated on 2026-09-18 with the operator's permission. Status and implementation evidence are
also recorded in [WORK.md](WORK.md). Remaining snippets below retain their proposed scope;
this document update does not authorize their implementation.

| Item | Status | Remaining acceptance concern |
|---|---|---|
| 1. Web-action eligibility | Implemented; locally verified | Confirm in the eventual full operator workflow |
| 2. IPC test callpoints | Proposed; awaiting approval | Five ordinary-suite failures |
| 3. Elevate wrapper tests | Proposed; awaiting approval | Three ordinary-suite failures |
| 4. Card spacing test | Proposed; awaiting approval | Host Chrome failure; render readiness versus CSS cause not yet established |
| 5. Cancellation-safe Backend stop | Proposed; awaiting approval | Missing full-Backend clean-close evidence and a confirmed cancellation window |
| 6. Operator failure diagnostics | Proposed; awaiting approval | Preserve the actual Backend reason in the final test failure |
| 7. Audit probe subprocess | Proposed; awaiting approval | Avoid the test's multithreaded-fork warning without suppressing it |

Item 5 is the remaining proposed production correction. Items 2–4 and 6–7 concern tests and
diagnostics. The provider test was not reached after the ordinary-suite failures; it is still
a verification gap, not a pass or a demonstrated provider defect.

## 1. Completed: `find` and supported-subset evidence eligibility

In `api.py`, alongside the existing action constants:

```python
WEB_FIND_ACTION = "find"
WEB_RESPONSE_LENGTH_ARGUMENT = "response_length"

ELIGIBLE_WEB_ACTIONS = frozenset({
    WEB_SEARCH_QUERY_ACTION,
    WEB_OPEN_ACTION,
    WEB_CLICK_ACTION,
    WEB_FIND_ACTION,
})
```

The final approved implementation also excludes unsupported arguments instead of failing
the entire rollout. In `_web_arguments`, after the existing JSON-object decoding:

```python
if (
    decoded.keys() - ELIGIBLE_WEB_ACTIONS - {WEB_RESPONSE_LENGTH_ARGUMENT}
    or not any(decoded.get(action) for action in ELIGIBLE_WEB_ACTIONS)
):
    logger.info(Locale.WEB_CALL_EVIDENCE_INELIGIBLE_LOG, call_id, sorted(decoded))
    return None
return decoded
```

Multiple supported action keys can coexist, as confirmed by `SearchCommands` in the
operator-supplied `protected/src/agent_runtime/docs/search.rs` and message 25 of the schema
chat. `response_length` remains allowed. A call containing any unsupported argument is
excluded, even if it also contains a supported action.

Exclusion happens before strict citation-output parsing and before indexing, so both exact
and near-match candidate pools exclude that call. The existing seeded `choice()` remains
unchanged. If no eligible evidence matches, the existing assessment/retry mechanism produces
`/pull` 200 Markdown correction instructions, not 500. Malformed JSON and broken supported
chains still fail closed; no generic exception swallowing or evidence-check relaxation.

Verified coverage:

- Explicitly cover all four actions, rather than derive coverage from the whitelist.
- Combined supported actions and `response_length`.
- Sanitized four-target `find`: two URL-backed results indexed, two URL-less errors excluded.
- Unsupported and mixed calls, alternative eligible provenance, exact/near-match filtering.
- Rejection of malformed/ambiguous chains.
- Real persisted validation, retry obligations and `/pull` status; identical DB/query state
  after replay, with unchanged replay-log bytes.

**Local result: 246 passed, 1 existing skip, 3 deliberate exclusions; Ruff and strict mypy
passed.** The exclusions were the process-lock subprocess and two historical-capture cases;
the existing skip concerns multiple-match rejection when multiple matches are intentionally
allowed. No full production/operator rerun is claimed.

No recovered files are modified. Changing this validation rule can cause the recovered rejected `/validate` record to fail replay consistency; no historical-verdict substitution or fallback.

## 2. Correct the five stale IPC test callpoints

In `test_operator_e2e_preflight.py`:

```python
monkeypatch.setattr(
    backend_server,
    "start_dashboard_query_server",
    Mock(side_effect=AssertionError),
)
```

Remove the unused `backend_ipc` import. Preserve all five cases and assertions. No compatibility alias.

## 3. Decouple elevate tests from its temporary batch contents

Keep `elevate` at **“Nothing to elevate”**, unchanged.

Test its actual shell/log/exit/grep wrapper with controlled batch outcomes instead of assuming install/browser commands exist:

```python
@pytest.mark.parametrize(
    ("batch", "expected_status", "has_failed_line"),
    (
        ("printf 'passed controlled\\n'; exit 0", 0, False),
        ("printf 'FAILED controlled\\n'; exit 7", 7, True),
        ("printf 'FAILED controlled\\n'; exit 0", 0, True),
    ),
)
```

A test-only executable shim replaces **only** the batch argument, then executes real GNU `script`:

```sh
#!/bin/sh
if [ "$#" -ne 5 ] || [ "$1" != -q ] || [ "$2" != -e ] || [ "$3" != -c ]; then
    echo "Unexpected elevate script invocation" >&2
    exit 98
fi
exec "$REAL_SCRIPT" "$1" "$2" "$3" "$ELEVATE_TEST_BATCH" "$5"
```

Assert actual exit status, log contents, FAILED reporting and log path. All files remain under `tmp_path`; no real batch executes. **No ordinary task changes.**

## 4. Make the spacing test measure a ready card

Test-only changes in `test_ui_e2e.py`:

```python
card = page.get_by_test_id(control_ui.CARD_MARKDOWN_TEST_ID)

expect(
    card.locator("code", has_text=E2E_CARD_FILENAME)
).to_have_text(E2E_CARD_FILENAME)

expect(
    page.get_by_test_id(control_ui.DOWNLOAD_CARD_DOCX_TEST_ID)
).to_be_enabled()

card_paragraphs = card.locator("p")
```

Replace the uninformative bare ratio calculation with:

```python
def _line_height_ratio(locator: Locator) -> float:
    expect(locator).to_be_visible()
    measurement = locator.evaluate("""element => {
        const style = getComputedStyle(element);
        return {
            connected: element.isConnected,
            lineHeight: style.lineHeight,
            fontSize: style.fontSize,
            ratio: parseFloat(style.lineHeight) / parseFloat(style.fontSize),
        };
    }""")
    assert measurement["connected"], measurement
    ratio = float(measurement["ratio"])
    assert math.isfinite(ratio), measurement
    return ratio
```

Keep **every spacing/bounding-box assertion and timeout unchanged**. No CSS change, arbitrary sleep, NaN replacement or retry-until-spacing-passes. If a genuine CSS defect remains, return with that evidence before changing production styling.

## 5. Finish Backend shutdown before propagating cancellation

In `_BackendSupervisor`, move the existing `_stop` body unchanged into `_stop_owned_process`, then wrap it:

```python
async def _stop(self) -> None:
    stop_task = asyncio.create_task(self._stop_owned_process())
    try:
        await asyncio.shield(stop_task)
    except asyncio.CancelledError:
        await stop_task
        raise

async def _stop_owned_process(self) -> None:
    # Existing _stop body:
    # terminate/wait, drain logs, check acknowledgement,
    # finish_backend_stop, then clear ownership.
    ...
```

Existing callers retain the lifecycle lock until this finishes. Preserve the existing SIGTERM/10-second/SIGKILL policy and clean-close requirements.

Extend the **existing** Locale-backed stop log:

```python
BACKEND_STOPPED_LOG_TEMPLATE: Final = (
    "Backend process stopped: pid={pid} return_code={return_code}; "
    "clean_close_ack={clean_close_ack}; forced_kill={forced_kill}; "
    "shutdown_succeeded={shutdown_succeeded}"
)
```

Pass the already-computed booleans.

Tests exercise actual supervisor cancellation during child exit and log draining. Operator teardown additionally verifies a successful stop **for each owned Backend PID**, after completing cleanup—an earlier IPC-only acknowledgement must not satisfy full-Backend shutdown.

No Backend/server/Store changes or borrowed-process handling changes.

## 6. Include the actual Backend error in operator-test failures

Change only `raise_for_dashboard_failure`:

```python
if failed_run_lines:
    backend_error_prefixes = tuple(
        f"{Locale.BACKEND_LOG_PREFIX} {level}:"
        for level in ("WARNING", "ERROR", "CRITICAL")
    )
    diagnostics = [
        line for line in dashboard.output
        if line.startswith(backend_error_prefixes)
    ]
    raise RuntimeError(
        "workflow failed:\n"
        + "".join((*failed_run_lines, *diagnostics))
    )
```

Add a cheap regression proving the exception includes both the failed-run summary and captured rollout-index error.

Dashboard remains dumb: no additional query, Backend-state inspection or inferred validation reason.

## 7. Run the audit probe outside multithreaded pytest

Move only the test’s in-process probe invocation into the existing shared subprocess mechanism.

Named helper in the protected pytest plugin:

```python
def audit_probe_process() -> None:
    import sys
    from src.detours.detour_ai_augment.src.control_centre.appendwatch import audit_read

    configured = audit_read.AuditReadConfiguration.model_validate_json(sys.argv[1])
    audit_read.execute(
        configured,
        audit_read.PROBE_COMMAND,
        output=sys.stdout.buffer,
    )
```

Existing test, explicitly marked `python_subprocess`:

```python
result = python_process.run(
    audit_probe_process,
    configured.model_dump_json(),
    timeout=10,
)
assert result.returncode == 0, result.stdout + result.stderr
assert result.stdout == result.stderr == ""
```

Production audit behavior remains unchanged. No warning suppression or new privilege requirement.

## Verification and exclusions

After approval and implementation of the remaining corrections, before another expensive
operator run:

- Examine the entire `pre-commit-operator` task graph and run every feasible leaf locally,
  including the corrected preflight cases, affected API/replay/UI/audit tests and Ruff/mypy.
  Selected passing tests are not proof that the ordinary suite passes.
- Put necessary host-Chrome checks and the previously unreached real-provider test into
  `elevate`, with embedded machine checks and the correct existing environment. Chrome tests
  belong on the macOS production Dashboard host; Linux tests belong on `aicode`, not `aivm`.
- Retain isolated NiceGUI storage and production-data preservation checks. No password/key
  logging, prerequisite masking, substituted tested boundaries or new skips.
- Preserve existing timeouts, assertions and storage isolation.
- Only after cheap/local and necessary delegated checks pass, request the full operator run.
  Review every leaf's result and actual execution, not wrapper exit/grep summaries alone.

**P26 is blocked until that full run completes without test/check failures, hangs or operator
interruptions.** Previously unreached leaves must actually run; an interrupted or partially
executed workflow is not acceptance. Review warnings, long waits, cleanup and preservation
evidence as well. Existing intentional skips/xfails are not new failures or permission to
hide a failed prerequisite. Unexpected new defects need their own narrow proposal/approval.

No changes proposed for normal readiness polling, cached NiceGUI data, duplicate live/replay warnings, the unreproduced old hang, documented XPASS, or out-of-scope Mode0 dependency deprecations. Previously rejected pre-commit wrapper restructuring remains excluded.

Item 1 is implemented. Items 2–7 remain **proposed, not approved**. The operator acceptance
gate remains unmet; no P26 implementation should begin yet.
