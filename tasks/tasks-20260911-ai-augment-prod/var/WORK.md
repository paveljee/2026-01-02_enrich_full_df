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

- Latest verification / handoff counts: `pre-commit-operator` collects 954 unique tests, BDD excluded by `pyproject.toml`. All 931 executable here have been exercised: 923 passed, 8 skipped. The other 23 are 3 sudo/root, 9 macOS Chrome UI, 3 operator/AIVM-socket, 2 real API, 2 root DuckDB platform-bin tests (`linux_amd64` config key absent; configured `linux_arm64` binary absent), 1 root reviewed-workbook absolute-path test (`/Volumes/...` absent), 2 mode-0 Kaleido/Chromium sandbox tests (`Operation not permitted`), and 1 slow step-4 real-config case barred by TASK data constraints. User confirmed missing platform bins, workbook, and sandbox behavior are expected in this env; tests/assertions/config unchanged. The user installed `splink_udfs` from DuckDB community in detour Pixi env; formerly failing run-outcome case passed in subsequent API run. `pre-commit-operator` wrapper itself is macOS-only and cannot execute here.
- Detour tests: all 776 detour-local non-host cases exercised (771 passed, 5 skipped). API file 280 cases split after one pre-assert fixture failure: initial full run 245 passed/2 skipped, then `test_dashboard_query_uses_scoped_store_reads` generic `HttpRequestLogRecord` caused Store reconstruction type mismatch. Changed only constructor to `PullResponseRecord(...)` with fields/assertions unchanged; focused test passed, 32-case suffix passed, totaling 278 passed/2 skipped. UI unit full 210 passed before final rollout-model file move; nine relevant UI smoke cases passed after move. Other detour full suites: backend Store+interceptor 93, IPC 22+1 skip, protected appendwatch/pydantic 67+6 skips (four excluded marker cases), operator preflight 74, protected Store integration 15, audit-read 12; protected UI integration 1 outside configured task passed. Root hermetic cases 143 exercised (140 passed, 3 skipped); other detours 12 exercised (12 passed), with declared Pixi environments. No failing assertion was weakened.
- Import correction: `ui.py` imports `AiAugmentDetourConfig` directly from its source; `test_audit_read.py` imports `AiAugmentBackendContext` directly from its source; no `server` reexports. Operator moved rollout models to `protected/src/backend/helpers/data_models/codex_rollout_record.py`; completed its imports and pointed CAS, documented `commit_request.py` mid-module import, Store, post-commit validation, and direct test consumers at that source. This breaks `config -> cas -> commit -> validation -> cas` without `model_rebuild` or Store-local import. Fresh imports pass. Final `pixi run` static checks: repo Ruff (`src tests`) passed, default mypy passed 68 source files, detour strict mypy passed 65 source files, `git diff HEAD --check` on detour/WORK/pyproject passed. Repo-wide whitespace check reports unrelated trailing whitespace in `chats/.../README.md`; left untouched. Do not stage/unstage. Handoff ready for user to run `pre-commit-operator` on macOS/Lima, subject to host-dependent cases above.
