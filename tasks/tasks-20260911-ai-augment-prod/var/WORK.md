## 1. Timing rules

| Object | `received_at_unix_usec` | `ready_to_respond_at_unix_usec` | `duration_usec` |
|---|---|---|---|
| Pull/Push/Query/RunOutcome **RequestRecord** | Request receipt | `None` | `0` |
| Corresponding **ResponseRecord** | `None` | Response ready | Response ready − request receipt |
| Init/Commit/Validation | `None` | Construction time | `0` |
| Outgoing OpenAlex/ROR request | `None` | Dispatch time | `0` |
| Received OpenAlex/ROR response | Arrival time, captured immediately after `send()` returns | `None` | `response.elapsed` in microseconds |


## My understanding

- Construct inbound request records **in the actual `server.py` routes**, before downstream business logic.
- Keep each `requests.PreparedRequest` local to its FastAPI/Flask route. API/IPC business logic selects a reply without receiving that prepared request; `requests.Response` composition needs only status, headers and body.
- Construct pull/push/run-outcome response records **in those same routes**, independently from the local prepared request and selected `requests.Response`. Do not copy request-record fields or dump them into a response constructor; reuse only receipt time for duration, plus deliberate run-outcome semantic links. Query is the explicit read-only Store exception below.
- Pull/push duration ends before storage and background commit/validation.
- Store receives completed pull/push/run-outcome **response records**.
- **Query persists neither record**; Store returns an ephemeral typed query response through the unchanged query port.
- Init/commit/validate are persisted request-only records.

## 1. Request construction at the route

In [server.py](/home/moshi/2026-01-02_enrich_full_df/src/detours/detour_ai_augment/protected/src/backend/server.py:241), the pull route starts like this. Existing fatal-error handling remains around the body:

```python
async def pull(request: Request) -> Response:
    received = time.time_ns() // NANOSECONDS_PER_MICROSECOND
    prepared = await _prepared_http_request(request)
    target = urlsplit(prepared.url or "")

    request_record = PullRequestRecord(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        method=prepared.method or "",
        scheme=target.scheme,
        host=target.hostname or "",
        port=target.port,
        path=target.path,
        query=target.query,
        request_headers=dict(prepared.headers),
        request_body=api._request_body_for_authoritative_log(
            api._prepared_request_body(prepared)
        ),
        response_code=None,
        response_headers=None,
        response_body=None,
        received_at_unix_usec=received,
        ready_to_respond_at_unix_usec=None,
        duration_usec=0,
    )

    # Select the reply and construct the separate response record here; see §2.
```

Repeat that **explicit construction**, with the appropriate class, at:

| Route | Class |
|---|---|
| `push` | `PushRequestRecord` |
| `dashboard_query` | `QueryRequestRecord` |
| `run_outcome_request` | `RunOutcomeRequestRecord` |

IPC business logic may consume the already-constructed run-outcome request record for its parsed NameKey/session/ETag/outcome properties, but never the prepared request; no request record is passed into Store. Those properties are not a template for response transport fields.

## 2. Independent response construction at the route

Make `api._response` and `api._error_response` compose a `requests.Response` from status, headers and body **without** a `PreparedRequest`; remove that parameter from `_pull_response` too. In the pull route, immediately after reply selection and before Store:

```python
store = request.app.state.store
try:
    reply = api._pull_response(store)
except Exception:
    reply = api._error_response(HTTPStatus.INTERNAL_SERVER_ERROR)
ready = time.time_ns() // NANOSECONDS_PER_MICROSECOND
current = store.current_replayed_record
linked_validation = None
if (
    reply.status_code == HTTPStatus.OK
    and reply.headers.get(HTTP_CONTENT_TYPE_HEADER) == ContentType.MARKDOWN_UTF8
):
    if isinstance(current, BackendValidationRequestRecord):
        linked_validation = current
    elif isinstance(current, PullResponseRecord):
        linked_validation = current.validation_request_record

response_record = PullResponseRecord(
    schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
    method=prepared.method or "",
    scheme=target.scheme,
    host=target.hostname or "",
    port=target.port,
    path=target.path,
    query=target.query,
    request_headers=dict(prepared.headers),
    request_body=api._request_body_for_authoritative_log(
        api._prepared_request_body(prepared)
    ),
    response_code=reply.status_code,
    response_headers=dict(reply.headers),
    response_body=reply.content.decode(TEXT_ENCODING),
    received_at_unix_usec=None,
    ready_to_respond_at_unix_usec=ready,
    duration_usec=ready - received,
    validation_request_record=linked_validation,
)

promise = await asyncio.to_thread(
    store.promise_pull_response_record, response_record,
)
# Keep existing ACK/error handling; return the stored record's to_response().
```

`linked_validation` remains the existing rejected validation for a successful Markdown retry pull; otherwise `None`. Capture `ready` before Store persistence/background work. The response UUID is independently generated.

Keep the existing push lifecycle/lock/decision block in the `server.push` route, immediately after constructing `PushRequestRecord`; it sets local `provisional_reply`, `session_id`, and `pull_response_record` without a tuple-returning operation. In the same route, build `PushResponseRecord` with the same explicit `prepared`/reply field mapping as pull and the intentional business link:

```python
pull_response_record=(
    pull_response_record
    if provisional_reply.status_code == HTTPStatus.ACCEPTED
    else None
),
```

Then:

```python
immediate_response, promise = await asyncio.to_thread(
    store.promise_push_response_record,
    push_response_record,
    session_id=session_id,
)
```

No request-record UUID or transport fields are copied. Each response constructor gets its own default UUIDv7. Store's existing push continuation uses the persisted `PushResponseRecord`.

## 3. IPC: query stays entirely unpersisted

Keep the existing `QueryOnlyStoreProperty.query_response_record` contract unchanged. The Flask route constructs `QueryRequestRecord` immediately and passes it to Store **for reading, not storage**:

```python
promise = store.query_response_record(request_record)
assert promise.acknowledgment is BackendStoreAcknowledgment.NAK
response_record, error = await promise.response_record_promise()
```

Store reads the snapshot and constructs `QueryResponseRecord` in place with its own UUID, separately from the query request record:

```python
cards = self.ai_augment_singular_outerdicts()
body = _QueryResponseBodyJson(
    ai_augment_singular_outerdicts=tuple(
        _AiAugmentSingularOuterDictJson.from_ai_augment_singular_outerdict(card)
        for card in cards
    ),
).model_dump_json()
ready = time.time_ns() // NANOSECONDS_PER_MICROSECOND
query_response_record = QueryResponseRecord(
    schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
    method=request_record.method,
    scheme=request_record.scheme,
    host=request_record.host,
    port=request_record.port,
    path=request_record.path,
    query=request_record.query,
    request_headers=request_record.request_headers,
    request_body=request_record.request_body,
    response_code=HTTPStatus.OK,
    response_headers={
        HTTP_CONTENT_TYPE_HEADER: ContentType.JSON,
        HTTP_CONTENT_LENGTH_HEADER: str(len(body.encode(TEXT_ENCODING))),
    },
    response_body=body,
    received_at_unix_usec=None,
    ready_to_respond_at_unix_usec=ready,
    duration_usec=ready - request_record.received_at_unix_usec,
    ai_augment_singular_outerdicts=cards,
)
```

The route returns that record’s response. **Neither query record is persisted.** Query is the operator-approved exception to route-owned response construction because this Store operation reads rather than writes; no architecture port replacement.

For run-outcome, keep the existing snapshot/decision logic directly in the Flask route, with the local `RunOutcomeRequestRecord` as input. No `RunOutcomeReply` tuple, selection callback, or prepared request passed downstream. The same route builds the reply body with a new response UUID, constructs `RunOutcomeResponseRecord` from its local `prepared` and reply, then:

```python
promise = await asyncio.to_thread(
    store.run_outcome_response_record, run_outcome_response_record,
)
```

Keep the deliberate `run_outcome_request_record` and `attempt` semantic links; do not derive HTTP fields or the response UUID from the request record.

## 4. Init/commit/validate: frozen once, complete before storage

Init already has the correct timing. Inline commit construction in `_capture_push_commit`, and validation construction in `_validate_commit`.

Their constructors use:

```python
received_at_unix_usec=None,
ready_to_respond_at_unix_usec=(
    time.time_ns() // NANOSECONDS_PER_MICROSECOND
),
duration_usec=0,
```

Remove `_synthetic_commit_request_record` and `ValidationRequestBody.http_record`; construct the typed records where their bodies become available.

## 5. OpenAlex/ROR: capture immediately after receiving HTTP

In `_capture_model_http`, put capture **inside the session context, immediately after `send()`**, before response validation or storage:

```python
response = session.send(
    request, **required.send_kwargs, allow_redirects=False,
)
received = time.time_ns() // NANOSECONDS_PER_MICROSECOND
actual_request = response.request
target = urlsplit(actual_request.url or "")

record = AiAugmentHttpRequestLogRecord(
    schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
    method=actual_request.method or "",
    scheme=target.scheme,
    host=target.hostname or "",
    port=target.port,
    path=target.path,
    query=redact_http_request_log_query(target.query),
    request_headers=dict(actual_request.headers),
    request_body=request_body(actual_request),
    response_code=response.status_code,
    response_headers=dict(response.headers),
    response_body=response.text,
    received_at_unix_usec=received,
    ready_to_respond_at_unix_usec=None,
    duration_usec=response.elapsed // timedelta(microseconds=1),
)
```

Construct the outgoing record inline before dispatch with dispatch-ready time and duration `0`. On transport failure, persist that request-only record; do not invent response timing.

## Necessary supporting changes

Remove live-construction factories:

```text
_authoritative_http_record
RunOutcomeRequestRecord.from_http_request
QueryResponseRecord.from_query_request
RunOutcomeResponseRecord.from_run_outcome_request_record
_construct_run_outcome_response_record
```

Store’s pull/push/run-outcome entry points accept **response** properties. Push background work receives the persisted `PushResponseRecord`, not a reconstructed `PushRequestRecord`.

Also remove this live conversion from `_append_authoritative_record`:

```diff
- record = self._response_record_for_http(record)
```

Keep replay reconstruction, but update validators for the timing table. Run-outcome replay recovers request receipt with:

```python
received_at_unix_usec=ready_to_respond_at_unix_usec - duration_usec
```

Its transient request UUID must not be compared with the response UUID. Compare persisted envelopes and retain existing semantic-link checks.

## Execution status

- Replay failure diagnostics: `store.py` now adds the failed contour field, commit-body validation location/type, lifecycle link, validation/recomputed-input mismatch, run-outcome link/status, or projection field/row count to the existing replay error prefix. `_ReplayLogLineInvalidError` carries the underlying reason and the rebuild logger includes it in the line-numbered log entry; single-line validation now uses the actual durable ordinal, rather than misleadingly reporting every failure as inner line 1. All new user-facing text is in `Locale`; exception classes, accept/reject checks, and durable records are unchanged. Added focused assertions for malformed commit body, missing public ready time, and replayed init/commit NameKey mismatch. The initial diagnostic tests hit a strict-model fixture construction error (`record_id` was serialized to a string); switching only those two fixture dumps to Python mode fixed it without changing assertions. Broad replay subset: 102 passed; run-outcome replay selection: 72 passed; final six focused cases passed. Focused strict mypy, Ruff and whitespace checks passed. Operator E2E has not been rerun after these diagnostics.
- Latest surgical startup fix: Full Backend `server.main()` now parses the configured NameKey and resolves `context.blueprint_for_namekey(startup_namekey)` immediately after read-only runtime configuration, **before** `confirm_startup(args)` and process-lock acquisition; IPC-only acquisition/configuration order is unchanged. The subprocess `backend_startup_process()` fixture mirrors this order. Added a no-prompt/no-lock regression test for unknown and ineligible NameKeys, with exact errors. Per operator approvals, the new ineligible expectation now checks the exact category-specific error; the existing refusal test uses a valid startup fixture but retains its confirmation and no-lock assertions. Focused API checks: 4 + 10 passed. Focused full-mode subprocess checks: 9 invalid-namekey cases and 5 valid confirmation cases passed. One IPC-only subprocess run timed out after `STARTUP_READY` amid concurrent checks, then passed alone in 12.16s; no assertion or timeout was changed. Focused Ruff and strict mypy (3 source files) passed.
- Latest accepted-initial-submission fix: `_standardized_initial_submission()` now sets `NOT_AVAILABLE_OR_APPLICABLE_VALUE` (`NA`) for all nine standardized fields and every nested component, rather than `NOT_REPORTED_VALUE` (`NR`); raw values, evidence, comments, retry submissions, and Store behavior are unchanged. The existing conversion test now independently asserts actual `NA` values and retains all prior assertions; it and both placeholder-rendering cases passed (3 total). Focused Ruff, strict mypy (2 source files), and `git diff HEAD --check` passed. Existing operator replay artifacts are historical and not rewritten by this change.
- Local Linux verification / handoff baseline: `pre-commit-operator` collects 954 unique tests, BDD excluded by `pyproject.toml`. All 931 executable here had been exercised: 923 passed, 8 skipped. The other 23 were 3 sudo/root, 9 macOS Chrome UI, 3 operator/AIVM-socket, 2 real API, 2 root DuckDB platform-bin tests (`linux_amd64` config key absent; configured `linux_arm64` binary absent), 1 root reviewed-workbook absolute-path test (`/Volumes/...` absent), 2 mode-0 Kaleido/Chromium sandbox tests (`Operation not permitted`), and 1 slow step-4 real-config case barred by TASK data constraints. User confirmed missing platform bins, workbook, and sandbox behavior are expected in this env; tests/assertions/config unchanged. The user installed `splink_udfs` from DuckDB community in detour Pixi env; formerly failing run-outcome case passed in subsequent API run. `pre-commit-operator` wrapper itself is macOS-only and cannot execute here.
- Detour tests: all 776 detour-local non-host cases exercised (771 passed, 5 skipped). API file 280 cases split after one pre-assert fixture failure: initial full run 245 passed/2 skipped, then `test_dashboard_query_uses_scoped_store_reads` generic `HttpRequestLogRecord` caused Store reconstruction type mismatch. Changed only constructor to `PullResponseRecord(...)` with fields/assertions unchanged; focused test passed, 32-case suffix passed, totaling 278 passed/2 skipped. UI unit full 210 passed before final rollout-model file move; nine relevant UI smoke cases passed after move. Other detour full suites: backend Store+interceptor 93, IPC 22+1 skip, protected appendwatch/pydantic 67+6 skips (four excluded marker cases), operator preflight 74, protected Store integration 15, audit-read 12; protected UI integration 1 outside configured task passed. Root hermetic cases 143 exercised (140 passed, 3 skipped); other detours 12 exercised (12 passed), with declared Pixi environments. No failing assertion was weakened.
- Import correction: `ui.py` imports `AiAugmentDetourConfig` directly from its source; `test_audit_read.py` imports `AiAugmentBackendContext` directly from its source; no `server` reexports. Operator moved rollout models to `protected/src/backend/helpers/data_models/codex_rollout_record.py`; completed its imports and pointed CAS, documented `commit_request.py` mid-module import, Store, post-commit validation, and direct test consumers at that source. This breaks `config -> cas -> commit -> validation -> cas` without `model_rebuild` or Store-local import. Fresh imports pass. Final `pixi run` static checks: repo Ruff (`src tests`) passed, default mypy passed 68 source files, detour strict mypy passed 65 source files, `git diff HEAD --check` on detour/WORK/pyproject passed. Repo-wide whitespace check reports unrelated trailing whitespace in `chats/.../README.md`; left untouched. Do not stage/unstage.
- Operator logs reviewed (`logs/from_operator/pre-commit.log`, `pre-commit-extra.log`, 2026-10-06; counts below are **per task**, not additive unique-test counts): guest `pre-commit` exited 0: Ruff and both mypy checks passed; default suite 174 passed/5 skipped/6 xfailed/1 xpassed; step-4 ordinary 4 passed/1 skipped and slow real-config 1 skipped; mode-3 6 passed; mode-0 4 passed; detour 776 passed/1 skipped/3 deselected; detour real-API 1 passed. Extra guest checks exited 0: default real-API 3 passed/1 xfailed; privileged appendwatch 3 passed. Mac Chrome UI: 8 passed/1 failed; `test_completed_grid_row_uses_real_query_ipc` was stopped **before launching dashboard/query assertions** by `_assert_ports_available()` because local port 8611 was occupied. Preserve this guard and assertions; operator should identify/free the port, then rerun that one test. Final operator AIVM E2E never collected: `test-detour-ai-augment-operator` stopped at `Redeploy AIVM before each operator test? [y/N]` with exit 2. Run it interactively with a deliberate redeploy/reuse choice after the port issue. No code/test assertion fix justified by these logs; no test was weakened.
- Operator follow-up: user reports the occupying process was killed and the entire pre-commit suite and final operator E2E now pass. The randomized workflow candidate log listed five ground-truth records but omitted the extra draw-146 Sheikh candidate. Added only an `_operator_log` line in `target_namekey()` immediately before `Random().choice(...)`: `added {namekey.last_name} to workflow candidates: {namekey.model_dump_json(by_alias=True)}`. `model_dump_json(by_alias=True)` is compact; `to_json_key()` would insert spaces. Candidate selection and assertions are unchanged. Verified exact compact Sheikh output, focused Ruff, focused mypy (1 source file), and `git diff --check`; all passed. The E2E run already in progress when this source edit was made did not include that logging change.
- Read-only operator artifact audit: new `tmp/test.pf957tzt` (David N Spergel) versus pre-timestamp-fix `tmp/test.m3b9l8lg` (A. Sheikh). Both completed with 7 UI lifecycle events, one final output row with all 30 fields non-null, correctly linked outcome IDs, valid per-line replay hashes, SHA256-addressed CAS files, and accepted final evidence. New replay: 8 records, one push/commit/validation accepted first try; old replay: 13 records, including an existing Beatriz Roldan Cuenya `/init` prefix (the old config hash equals precisely the first JSONL line), then one rejected and one accepted Sheikh validation. New config hash equals empty replay prefix. New JSONL Table 1 check: all 8 `received_at=None`; all 8 `ready` present; init/commit/validate duration 0; pull durations 2256, 1990, 885 µs; push 956 µs; completed 608648 µs. Event times increase with no reconstructed interval overlap; final pull follows Codex exit by 2.643 ms, `/completed` starts 82.167 ms later, and UI completion is 65.015 ms after its response-ready time. Old commit/validate timing was null and old `/completed` had both receipt and ready timestamps; new representation fixes both. No provider HTTP records in either replay, so `response.elapsed` timing is not assessed here. Pull/push `ready` is captured at reply selection, before typed-record construction/persistence, as specified; UUIDv7 creation can follow it by a few ms (7 ms max observed), so recorded durations are not end-to-end network latencies. The session-discovered UI event is backdated to `result.session_timestamp` and may appear after a later remote-PID event in storage; present in both runs, not a regression. No source/test changes made for the audit.
