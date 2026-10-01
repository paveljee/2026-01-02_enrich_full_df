# AI augment production — current workbook (2026-10-01)

## Governing boundaries
Read tasks/tasks-20260911-ai-augment-prod/src/TASK.md and this entire file after compaction. Do not consult former WORK or HUMANS. Use pixi run -e detour-ai-augment for Python/checks; never run src.repl or modify the main DB. Git is read-only for this agent: do not stage/unstage. Do not edit architecture.py without targeted approval, excluded BDD, or human-signed-off comments. Source and existing-test edits must be surgical; no old-record fallbacks, unauthorized wrappers, new/redundant tests, wholesale replacements, or unrelated cleanup. The operator has now authorized implementation of the exact settled WORK contour. SQL/method wiring is implementation work, not a new operator decision. Preserve exact model shapes and docstrings, particularly CASCodexRolloutRecord. Stop and ask if a deviation from the reviewed boundary is needed.

Architecture.py governs models; README lifecycle is somewhat stale. Replay log is principal and detour DB is fully reconstructible from log/CAS; DOCX renders DB innerdicts. Store alone owns detour SQL and authoritative lifecycle records. Current replay contour: append/fsync, log readback, project in one DB transaction, reconstruct typed object from DB, compare value and byref links, then advance the one current_replayed_record cursor if applicable. BUSY 503 exchanges are logged but do not advance that cursor. On validation replay the cursor must be a BackendCommitRequestRecord; intervening provider HTTP or BUSY 503 log lines are permitted. Assert identity with is only for the same byref object, not across a fresh reconstruction. Post-commit validation gets a byref commit and Store-supplied inputs/reads; it does no SQL. Existing LazyResultFactory callbacks for validation are truly deferred and use (value, error) results; immediate HTTP-record lookup is instead Callable[[UUID], HttpRequestLogRecord].

## Current source and verification status
The working tree contains the approved push-admission implementation (exclusive HTTP gate, inlined API push decision, immediately reconstructed PushResponseRecord plus eventual promise, BUSY 503, narrow cursor invariant), the ID-based run-outcome response-body cleanup, and the secondary run-outcome/query readback codec. Preserve the operator's names current_replayed_record, session_id, captured_push_request_http_record, the_coroutine, stores_push_promise, and PUSH_PROCESSING_DESCRIPTION. The card's exact response-body JSON follows `ktp.last_name`; the unused commit-body staging field is removed. Serialization changes and surgical updates to existing tests are verified by the checks below.

The **final full Linux-feasible detour run after all approved rename/import edits** passed **751 tests, 5 skipped, 4 deselected in 1278.50s** (`tmp/ai-augment-rename-verification-20261001/final-feasible-detour.log/xml`). Full dashboard `test_ui.py` passed **206/206**, operator preflight **72/72**, and the separately feasible subprocess-only query fixture plus Store recovery integration passed **2/2** after the exact name/import edits; these are overlapping focused checks, not additional distinct detour tests except the subprocess-only fixture. After the operator's targeted direction, the two unused `StandardizedSubmission` and `Submission` imports in `protected/src/architecture.py` were moved verbatim into comments inside the unused `AttemptRecordProperty` block; no protocol code or existing comment was changed. Whole-source Ruff, detour mypy (**63 source files**), and unstaged `git diff --check` now pass. **Staged** `git diff --cached --check` separately reports two trailing-space lines in the human-staged detour README (lines 102, 125); this agent did not alter that unrelated file. The Pixi `pre-commit-operator` task does not itself call `git diff --check`, but the staged diff is not whitespace-clean. An additional repository-wide `mypy src tests` run in the detour environment reports 20 errors in seven unchanged main-pipeline files; this is not the operator task's default-environment mypy invocation and is outside the approved edit contour. The operator explicitly approved the targeted one-blank-line Ruff E305 fix in `src/helpers/architecture.py:108`; that exact formatting edit is applied. The corrected operator E2E assertion requires surname → exact run-outcome response body → session metadata and restores a rendered-body content check. Full pre-commit-operator requires Darwin/Lima/Chrome and cannot run here; do not call it passed.

Unrun here: one real-API and three authenticated/operator E2E tests; eight `test_ui_e2e.py` cases after the subprocess-only fixture case passed separately (one of the eight was attempted and failed at denied local socket creation); three sudo-marked appendwatch tests; and the deliberately excluded BDD module. The full operator test of completed-card rendering remains unexecuted. Current per-test evidence and the separately encountered optional-other-detour dependency failure are recorded below. Source files and WORK have preexisting staged edits; some existing tests and current WORK updates are unstaged. This agent did not stage or unstage anything, as TASK forbids that.

## Operator decisions on the three review points
1. `codex_innerdicts` contains only flat card innerdict JSONL, including the existing session metadata/rollout summary **and the run-outcome HTTP response body** as a JSON string. The response-body card field must immediately follow `ktp.last_name`. The obsolete commit-request-body staging/card field is removed: no remaining consumer needs it. Store the distinct full query-ready outcome snapshot once in `codex_run_outcome_records(run_outcome_record_id PRIMARY KEY, serialized_json)`; duplicate keys fail loudly, with no upsert or fallback. `codex_output_rows` remains the accepted-card staging table and links its one card row to the outcome ID.
2. Pull/push response JSON decoders accept optional predecessor references. Omitted and explicit `None` mean `None`; a supplied record is used by reference. No sentinel or omission check.
3. Purge the old `RunOutcomeResponseRecord` attempt-array serializer/deserializer, `seen` guard, and `SERIALIZED_ATTEMPT_LINEAGE_KEY` when the separate-table codec replaces that path. No legacy or fallback support, and no `seen` in the new codec.

## Approved card restoration, 2026-10-01 — implemented and verified
The operator corrected the placement: the response-body field follows **`KTP_LAST_NAME_COL`**, not the SourceKey columns, and precedes session metadata. The card contains the exact `RunOutcomeResponseRecord.response_body` string sent over HTTP, not `outcome.serialize()` (the full HTTP envelope) or the separate full query snapshot. The obsolete commit-request-body column has no consumer and is removed from the staging schema and accepted-output row, not merely hidden in the card. No new response-body class is authorized.

~~~python
# protected/src/backend/helpers/vars.py
KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}run_outcome_response_body"
)

# In CODEX_OUTPUT_SCHEMA, immediately after the surname:
(KTP_LAST_NAME_COL, "VARCHAR NOT NULL"),
(KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL, "VARCHAR"),
(KTP_AI_AUGMENT_COMMIT_REQUEST_RECORD_ID_COL, "VARCHAR NOT NULL UNIQUE"),
~~~

~~~python
# ai_augment_backend_store.py, existing completed-outcome UPDATE:
f"{duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL)} = ?, "
f"{duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL)} = ? "
# corresponding values:
str(outcome.record_id),
outcome.response_body,
~~~

`_replace_codex_output_view` already carries every non-internal schema column in order; `build_cards` renders that flat field without a new renderer. Retain the independent `codex_run_outcome_records` full graph snapshot for query. Remove `KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL` from globals/schema, the accepted-output row, and the view's now-obsolete exclusion. Preserve commit request body in the authoritative record/replay log; only its redundant staging copy goes. Surgically adapt existing affected assertions; no new tests or fallback.

## Settled change contour — ID-only validation replay body
IMPLEMENTED AND VERIFIED. The existing _ValidationRequestBodyJson owns the JSON schema and parsing. No parallel validation-body JSON-key globals, manual json.loads/key-set checks, or LazyResultFactory for immediate UUID resolution. If a JSON-key constant proves unavoidable elsewhere, name it with _JSON_KEY. No detour architecture.py edit was made.

### 1. validation_request.py: wire representation and inverse
Keep ValidationRequestBody's architecture-defined Python fields as typed objects. The private JSON model is the exact wire schema for serialization and parsing.

~~~python
class _ValidationRequestBodyJson(FrozenStrictModel):
    commit_request_record_id: UUID
    post_commit_validation: PostCommitValidation
    initial_validation_request_record_id: UUID | None
    openalex_ror_records_ids: tuple[UUID, ...]
~~~

Replace only ValidationRequestBody.serialize's body; retain @model_serializer and its existing http_record creation.

~~~python
@model_serializer
def serialize(self) -> dict[str, object]:
    return _ValidationRequestBodyJson(
        commit_request_record_id=self.commit_request_record.record_id,
        post_commit_validation=self.post_commit_validation,
        initial_validation_request_record_id=(
            None if self.initial_validation_request_record is None
            else self.initial_validation_request_record.record_id
        ),
        openalex_ror_records_ids=tuple(
            record.record_id for record in self.openalex_ror_records
        ),
    ).model_dump(mode="json")
~~~

Add the inverse on ValidationRequestBody; Store passes exactly its commit/initial references and its existing projected-DB HTTP-record reader. Pydantic parses UUIDs, fields, and post_commit_validation. The method checks only semantic links and constructs architecture-defined objects; it does not import Store or run SQL.

~~~python
@classmethod
def from_serialized_json(
    cls,
    value: str,
    *,
    commit_request_record: BackendCommitRequestRecord,
    initial_validation_request_record: BackendValidationRequestRecord | None,
    resolve_http_record: Callable[[UUID], HttpRequestLogRecord],
) -> Self:
    parsed = _ValidationRequestBodyJson.model_validate_json(value)
    if parsed.commit_request_record_id != commit_request_record.record_id:
        raise ValueError(Locale.VALIDATION_COMMIT_LINK_INVALID)
    if parsed.initial_validation_request_record_id != (
        None if initial_validation_request_record is None
        else initial_validation_request_record.record_id
    ):
        raise ValueError(Locale.VALIDATION_INITIAL_LINK_INVALID)
    return cls(
        commit_request_record=commit_request_record,
        post_commit_validation=parsed.post_commit_validation,
        initial_validation_request_record=initial_validation_request_record,
        openalex_ror_records=tuple(
            resolve_http_record(record_id)
            for record_id in parsed.openalex_ror_records_ids
        ),
    )
~~~

Existing ValidationRequestBody.validate_body still checks retry lineage and duplicate/non-v7 provider IDs. BackendValidationRequestRecord.validate_record retains its HTTP-contour checks and compares the Pydantic-parsed request body with the typed body's serialized view; it no longer parses full embedded HTTP envelopes.

~~~python
parsed = _ValidationRequestBodyJson.model_validate_json(self.request_body)
initial = self.validation_request_body.initial_validation_request_record
if (
    parsed.model_dump(mode="json") != self.validation_request_body.serialize()
    or self.request_headers
    != self.validation_request_body.commit_request_record.request_headers
    or (initial is not None and initial.record_id == self.record_id)
):
    raise ValueError(Locale.VALIDATION_BODY_MISMATCH)
~~~

### 2. ai_augment_backend_store.py: replay and checks
In _apply_durable_record's /validate branch, retain the hard typed-cursor requirement, log-readback/DB projection, and attempt insertion. Replace its manual JSON decoding and body construction with:

~~~python
commit_ref = self._current_replayed_record
if not isinstance(commit_ref, BackendCommitRequestRecord):
    raise ValueError(Locale.REPLAY_VALIDATION_COMMIT_MISMATCH)
if record.request_body is None:
    raise ValueError(Locale.VALIDATION_BODY_MISSING)
initial_ref = self._initial_validation_for_commit(commit_ref)
body = ValidationRequestBody.from_serialized_json(
    record.request_body,
    commit_request_record=commit_ref,
    initial_validation_request_record=initial_ref,
    resolve_http_record=self._http_record,
)
self._apply_validation_record(
    record,
    body=body,
    commit_ref=commit_ref,
    initial_ref=initial_ref,
)
validation = BackendValidationRequestRecord.from_http_request_log_record(
    record,
    validation_request_body=body,
)
assert validation.validation_request_body is body
self._insert_validation_request_record_id(validation)
reconstructed = validation
~~~

The operator identified the immediate post-construction `body` identity assertions as redundant: `ValidationRequestBody` had just been given those exact references. Remove the two analogous live-construction assertions too. Keep `_apply_validation_record`'s argument-boundary checks and Store's `_assert_lifecycle_links` checks after reconstruction; those verify boundaries rather than restating constructor arguments.

In _apply_validation_record, remove the parsed argument and only checks of now-absent embedded commit/pull/push/initial HTTP envelopes. Keep its cursor-is-commit assertion, projected commit/initial UUID and ordinal checks, request-header checks, the existing provider _http_record_with_ordinal check (earlier than validation, complete, equals the body-resolved record), ModelHttpInterceptor.from_records, evaluate_commit call, observed-vs-recomputed validation and provider-ID comparisons, and _project_validation. Do not change failure ordering unnecessarily. Provider records are separate earlier replay-log lines and are fetched from the projected detour DB via Store._http_record, not copied inside /validate. Store's shared append/readback/project/reconstruct/compare/cursor contour remains unchanged.

### 3. Other consumers of the old embedded validation envelopes
RunOutcomeResponseRecord.from_serialized_json now handles only its replay-log HTTP record and a caller-provided attempt byref; it no longer walks embedded validation envelopes. Store's cursor holds only the latest lifecycle record, **not every historical outcome's refs**. For query, Store._codex_innerdicts gets each historical outcome's complete secondary snapshot from projected detour DB, constructs typed CodexInnerDict and AiAugmentSingularOuterDict, and serializes a **fully self-contained query payload**. The dashboard parses it using _QueryResponseBodyJson → _AiAugmentSingularOuterDictJson → _CodexInnerDictJson and reconstructs its typed graph from that payload, with no Store/DB access. The query-only payload includes full pull, push, commit, validation, and provider HTTP envelopes; the principal /validate and /completed replay-log lines remain ID-based/lean. The query-only serialized-record schema lives at the existing CodexInnerDict JSON handoff, not inside RunOutcomeResponseRecord.serialize (whose record-level semantics are the replay-log HTTP line). Section 7 specifies the private JSON fields; no competing architecture class.

Current query call path: Store.query_response_record calls QueryResponseRecord.from_query_request with Store.ai_augment_singular_outerdicts(); that reads the projected codex_innerdicts table. IPC reconstructs QueryResponseRecord from its HTTP envelope. The dashboard receives the query response body and calls DashboardQuerySnapshot.from_serialized_json → QueryResponseRecord.outerdicts_from_response_body. QueryResponseRecord.from_serialized_json is **not currently the dashboard body parser**. Store's live append and full log rebuild project/read back each record, so DB is the proper historical source; no full replay-log replay per query. But projected HTTP rows/secondary rows do not automatically preserve typed Python refs for all earlier outcomes. Store must reconstruct historical objects from DB before serializing a complete query payload; the dashboard cannot receive Store's Python object identities across the socket. Avoid the invented name lineage in any proposed model/class: describe existing validation/pull/push/commit objects and their query-only serialized HTTP envelopes directly. Any proposal to pass Store refs into QueryResponseRecord.from_serialized_json must distinguish a Store-side construction call from the dashboard's independent body deserialization and must not make the latter depend on Store.

Read-only code audit: _http_record_with_ordinal(UUID) returns a projected **base** HttpRequestLogRecord; _backend_commit_request_record(record) only verifies/returns the **current cursor** commit, not an arbitrary historical one. _replay_durable_record invokes the projection transaction and must not be rerun by a read-only query. Store does not have an existing arbitrary-ID typed readback function to invoke as-is; the secondary snapshot design below avoids needing one. QueryResponseRecord.from_query_request constructs the backend response; its from_serialized_json is a decoder, not a serializer. The dashboard can only reconstruct from the fully serialized query response body, not receive Store's Python references.

Query reconstruction boundary: at _apply_run_outcome_record, Store already has the reconstructed RunOutcomeResponseRecord and its attempt→commit→push→pull→prior-validation graph. A complete secondary JSON snapshot of that graph must be projected once into **codex_run_outcome_records**, with exactly two columns: run_outcome_record_id (primary key) and serialized_json. Insert plainly: any key conflict fails the projection transaction and the detour loudly; no upsert, ignore, overwrite, or fallback. The **full graph snapshot** must not be in codex_output_rows or codex_innerdicts; the separate compact HTTP response body **does** belong in the flat card innerdict. Rebuilding from log must regenerate both. Section 7 defines the private JSON-only graph codec; its former same-column storage/readback proposal is withdrawn. Store combines card rows and snapshot records when constructing CodexInnerDict for query; the dashboard reconstructs from the complete query body without Store. Record-level serialize/from_serialized_json retain their distinct replay-log meanings.

### 4. Four-method AiAugmentHttpRequestLogRecord audit
Explicitly declare http_request_log_record, from_http_request_log_record, serialize, and from_serialized_json on every subclass, including RequestRecord, ResponseRecord, PullRequestRecord, PullResponseRecord, PushRequestRecord, PushResponseRecord, BackendCommitRequestRecord, BackendValidationRequestRecord, RunOutcomeRequestRecord, RunOutcomeResponseRecord, QueryRequestRecord, and QueryResponseRecord. AgentRuntimeAttempt is an alias of BackendValidationRequestRecord, not another class. A method body containing only pass is invalid; plain subclasses use explicit super() delegation where it truly works, e.g.:

~~~python
@property
def http_request_log_record(self) -> HttpRequestLogRecord:
    return super().http_request_log_record

@classmethod
def from_serialized_json(cls, *, value: str) -> Self:
    return super().from_serialized_json(value=value)

def serialize(self) -> dict[str, object]:
    return super().serialize()
~~~

The complete plain-record delegation pattern also includes:

~~~python
@classmethod
def from_http_request_log_record(
    cls, *, http_request_log_record: HttpRequestLogRecord,
) -> Self:
    return super().from_http_request_log_record(
        http_request_log_record=http_request_log_record,
    )
~~~

Use this only when no excluded byref field must be supplied. Pull/push response, commit, validation, run outcome response, and query response use child-specific reconstruction. serialize/from_serialized_json represent the replay-log serialized HTTP record, not a secondary graph; the separate JSON-only outcome codec carries the query graph. QueryRequestRecord/QueryResponseRecord are ephemeral, but still participate in the method audit.

The operator's exact decisions for the response codecs and old-path removal are summarized above. Store still supplies its owned references on authoritative replay; accepted pushes still require a valid pull.

### 5. Record-class audit and implementation requirements
The operator authorizes **redefining the existing four AiAugmentHttpRequestLogRecord methods in a subclass whenever justified**, visibly and specifically; do not add a separate thin adapter method. A bogus super() forwarding override on a reference-bearing record is not acceptable. Optional pull/push decoder references default to `None` per the settled decision above; the approved item-3 methods supply the concrete commit/validation/outcome decoder signatures. Store's authoritative DB-readback path uses `from_http_request_log_record` with its owned references, not an unnecessary serialize/decode round trip. The Store branch in section 2 is a body-first contour; BackendValidationRequestRecord.from_serialized_json is separately usable with supplied references. The secondary JSON codec and separate-table SQL are implemented as described in section 7.

AgentRuntimeAttempt is **an alias** of BackendValidationRequestRecord, not another Record class. Excluded byref fields are reconstructed from Store-supplied references for replay; full historical graphs use the separate JSON-only query codec. There is no attempt default_factory.

### 6. Verification
Existing tests/fixtures were adapted surgically to ID-only validation JSON and the restored card field; no tests were wholesale removed, excluded BDD was untouched, and there is no old-record fallback. The one later operator-requested recovery integration test is documented below. The final full feasible detour suite, operator preflight, Ruff, and mypy pass as recorded above. The human operator's full pre-commit-operator task remains to run on Darwin/Lima/Chrome.

### 7. Secondary query JSON codec — separate two-column storage settled
Store already has the fully linked outcome object while projecting `/completed`. The two private JSON-only models below encode and decode it. Their storage is **codex_run_outcome_records(run_outcome_record_id PRIMARY KEY, serialized_json)**, one snapshot per outcome record ID; a duplicate key is a fatal detour projection error, never an upsert/ignore. The former proposal to put the snapshot in codex_output_rows and materialize it into codex_innerdicts is withdrawn. Store serializes its DB-readback reconstructed RunOutcomeResponseRecord with its byref attempt graph through `_RunOutcomeResponseRecordJson.from_run_outcome_response_record(outcome).model_dump_json()`, not through the lean record-level `outcome.serialize()`. Rebuilding DuckDB from the replay log must regenerate the table using that same projection. The existing outcome ID in codex_output_rows links card rows to the snapshot for query.

**Implemented and verified pieces:** Store's outcome projection and `_codex_innerdicts`, the concrete pull/push/commit/validation/outcome constructors, the CodexInnerDict JSON handoff, `QueryResponseRecord.from_query_request`, and the complete typed secondary JSON representation of the referenced validation records. No full commit/provider envelopes are embedded in the principal validation body.

Two private **JSON-only** models in `codex_innerdict.py`—not new lifecycle records:

~~~python
class _CodexInnerDictValidationJson(FrozenStrictModel):
    pull_response_http_record: HttpRequestLogRecord
    push_response_http_record: HttpRequestLogRecord
    commit_request_http_record: HttpRequestLogRecord
    validation_request_http_record: HttpRequestLogRecord
    openalex_ror_records: tuple[HttpRequestLogRecord, ...]

    @classmethod
    def from_validation_request_record(
        cls, validation: BackendValidationRequestRecord,
    ) -> Self:
        body = validation.validation_request_body
        commit = body.commit_request_record
        pull = commit.commit_request_body.pull_response_record
        push = commit.commit_request_body.push_response_record
        return cls(
            pull_response_http_record=pull.http_request_log_record,
            push_response_http_record=push.http_request_log_record,
            commit_request_http_record=commit.http_request_log_record,
            validation_request_http_record=validation.http_request_log_record,
            openalex_ror_records=body.openalex_ror_records,
        )

    def to_validation_request_record(
        self,
        *,
        prior_validation_request_record: BackendValidationRequestRecord | None,
        initial_validation_request_record: BackendValidationRequestRecord | None,
    ) -> BackendValidationRequestRecord:
        pull = PullResponseRecord.from_http_request_log_record(
            http_request_log_record=self.pull_response_http_record,
            validation_request_record=prior_validation_request_record,
        )
        push = PushResponseRecord.from_http_request_log_record(
            http_request_log_record=self.push_response_http_record,
            pull_response_record=pull,
        )
        commit_refs: dict[UUID, PullResponseRecord | PushResponseRecord] = {
            pull.record_id: pull,
            push.record_id: push,
        }
        commit = BackendCommitRequestRecord.from_http_request_log_record(
            self.commit_request_http_record,
            resolve_http_record=commit_refs.__getitem__,
        )

        request_body = self.validation_request_http_record.request_body
        assert request_body is not None
        provider_records = {
            record.record_id: record for record in self.openalex_ror_records
        }
        body = ValidationRequestBody.from_serialized_json(
            request_body,
            commit_request_record=commit,
            initial_validation_request_record=initial_validation_request_record,
            resolve_http_record=provider_records.__getitem__,
        )
        validation = BackendValidationRequestRecord.from_http_request_log_record(
            self.validation_request_http_record,
            validation_request_body=body,
        )
        assert pull.validation_request_record is prior_validation_request_record
        assert push.pull_response_record is pull
        assert commit.commit_request_body.pull_response_record is pull
        assert commit.commit_request_body.push_response_record is push
        assert body.commit_request_record is commit
        assert body.initial_validation_request_record is initial_validation_request_record
        return validation
~~~

The other JSON model holds the completed outcome envelope and those validations in chronological order:

~~~python
class _RunOutcomeResponseRecordJson(FrozenStrictModel):
    run_outcome_response_http_record: HttpRequestLogRecord
    validation_requests: tuple[_CodexInnerDictValidationJson, ...]

    @classmethod
    def from_run_outcome_response_record(
        cls, outcome: RunOutcomeResponseRecord,
    ) -> Self:
        validations: list[_CodexInnerDictValidationJson] = []
        validation = outcome.attempt
        while validation is not None:
            validations.append(
                _CodexInnerDictValidationJson.from_validation_request_record(
                    validation
                )
            )
            pull = (
                validation.validation_request_body.commit_request_record
                .commit_request_body.pull_response_record
            )
            validation = pull.validation_request_record
        return cls(
            run_outcome_response_http_record=outcome.http_request_log_record,
            validation_requests=tuple(reversed(validations)),
        )

    def to_run_outcome_response_record(self) -> RunOutcomeResponseRecord:
        prior: BackendValidationRequestRecord | None = None
        initial: BackendValidationRequestRecord | None = None
        for serialized in self.validation_requests:
            validation = serialized.to_validation_request_record(
                prior_validation_request_record=prior,
                initial_validation_request_record=initial,
            )
            if initial is None:
                initial = validation
            prior = validation
        outcome = RunOutcomeResponseRecord.from_http_request_log_record(
            self.run_outcome_response_http_record,
            attempt=prior,
        )
        if outcome._body().validation_record_id != (
            None if prior is None else prior.record_id
        ):
            raise ValueError(Locale.RUN_OUTCOME_ATTEMPT_LINK_INVALID)
        assert outcome.attempt is prior
        return outcome
~~~

The two-column table shape and codec source are settled; exact SQL write/read wiring is mechanical implementation work. Current `CODEX_OUTPUT_SCHEMA` makes commit_request_record_id unique, and `/completed` selects by that ID, so a completed outcome can match **at most one** staged output row and produce at most one card innerdict. The existing `fetchall()`/loop does not imply multiple rows; the agent's earlier claim that one outcome could produce multiple card rows was incorrect. Insert one snapshot for the matched completed outcome. The old same-column write/read snippets are withdrawn. Decode `serialized_json` from the new table with `_RunOutcomeResponseRecordJson.model_validate_json(run_outcome_json).to_run_outcome_response_record()`.

The CodexInnerDict JSON handoff changes **only the outcome snapshot field**. Do not introduce another procedure-restoration validator, serializer, or JSON format: `CodexInnerDict.innerdict` is already an `InnerDict` object; its existing `from_serialized` uses `InnerDict.from_mapping(serialized.innerdict, _CodexInnerDictProcedure())`, and its existing `_CodexInnerDictJson.from_codex_innerdict` takes `value.innerdict.data` for the JSON wire. The private JSON-only field's mapping is a wire value, not the authoritative innerdict object. This existing conversion is already implemented and must be preserved.

~~~python
# In the existing _CodexInnerDictJson, retain its innerdict field and
# value.innerdict.data constructor argument. Replace only its outcome field:
run_outcome_response_record_json: _RunOutcomeResponseRecordJson

# Replace only the outcome constructor argument:
run_outcome_response_record_json=(
    _RunOutcomeResponseRecordJson.from_run_outcome_response_record(
        value.run_outcome_response_record
    )
)

# In CodexInnerDict.from_serialized:
run_outcome_response_record = (
    serialized.run_outcome_response_record_json.to_run_outcome_response_record()
)
innerdict = InnerDict.from_mapping(
    serialized.innerdict, _CodexInnerDictProcedure(),
)  # existing typed reconstruction, unchanged
~~~

`_AiAugmentSingularOuterDictJson` and `_QueryResponseBodyJson` then carry that complete nested representation using their existing path. **No new `QueryResponseRecord` factory is needed on the backend**: `from_query_request(...)` already accepts Store's fully reconstructed outerdicts and serializes the response. The dashboard's existing body parser reconstructs the same graph from JSON without Store access.

Full graph copies belong only in the **separate secondary DuckDB table and query representation**, while `/validate` and `/completed` replay-log lines stay lean. `codex_innerdicts` remains card-only, including its session metadata summary and the new compact run-outcome response-body JSON field. `RunOutcomeResponseRecord.serialize/from_serialized_json` must mean the record's replay-log JSON. No old-record fallback or dual-format handling.


## Operator-retained exact items 1–3

The operator directed that items 1 and 2 be recorded exactly, and explicitly approved item 3 within the exact supplied shape. These snippets supersede the corresponding gaps above. Source implementation and feasible local verification are complete.

**1. Outcome link.**

```python
if outcome._body().validation_record_id != (
    None if prior is None else prior.record_id
):
    raise ValueError(Locale.RUN_OUTCOME_ATTEMPT_LINK_INVALID)
```

**2. Validation self-reference.**

```python
or (initial is not None and initial.record_id == self.record_id)
```



**3. Record methods.**

```python
# BackendCommitRequestRecord
@classmethod
def from_serialized_json(
    cls,
    *,
    value: str,
    resolve_http_record: Callable[
        [UUID], PullResponseRecord | PushResponseRecord
    ] | None = None,
) -> Self:
    if resolve_http_record is None:
        raise ValueError(Locale.COMMIT_REFERENCES_REQUIRED)
    return cls.from_http_request_log_record(
        HttpRequestLogRecord.model_validate_json(value),
        resolve_http_record=resolve_http_record,
    )

def serialize(self) -> dict[str, object]:
    return self.http_request_log_record.model_dump(mode="json")
```

```python
# BackendValidationRequestRecord
@classmethod
def from_serialized_json(
    cls,
    *,
    value: str,
    commit_request_record: BackendCommitRequestRecord | None = None,
    initial_validation_request_record: BackendValidationRequestRecord | None = None,
    resolve_http_record: Callable[[UUID], HttpRequestLogRecord] | None = None,
) -> Self:
    if commit_request_record is None:
        raise ValueError(Locale.VALIDATION_COMMIT_LINK_INVALID)
    if resolve_http_record is None:
        raise ValueError(Locale.VALIDATION_HTTP_REFERENCES_INVALID)
    record = HttpRequestLogRecord.model_validate_json(value)
    if record.request_body is None:
        raise ValueError(Locale.VALIDATION_BODY_MISSING)
    body = ValidationRequestBody.from_serialized_json(
        record.request_body,
        commit_request_record=commit_request_record,
        initial_validation_request_record=initial_validation_request_record,
        resolve_http_record=resolve_http_record,
    )
    return cls.from_http_request_log_record(
        record, validation_request_body=body,
    )

def serialize(self) -> dict[str, object]:
    return self.http_request_log_record.model_dump(mode="json")
```

```python
# RunOutcomeResponseRecord
@classmethod
def from_serialized_json(
    cls, *, value: str, attempt: AgentRuntimeAttempt | None = None,
) -> Self:
    outcome = cls.from_http_request_log_record(
        HttpRequestLogRecord.model_validate_json(value),
        attempt=attempt,
    )
    if outcome._body().validation_record_id != (
        None if attempt is None else attempt.record_id
    ):
        raise ValueError(Locale.RUN_OUTCOME_ATTEMPT_LINK_INVALID)
    return outcome

def serialize(self) -> dict[str, object]:
    return self.http_request_log_record.model_dump(mode="json")
```

## Settled items 4–5 — implemented and verified

### 4. Keep the persisted researcher-card innerdict plain and card-only

Operator clarification: `CODEX_INNERDICT_TABLE` has the same plain-innerdict meaning as XLSX/DOCX innerdict tables: its JSONL contains flat researcher-card key/value data, the existing `KTP_AI_AUGMENT_SESSION_METADATA_COL`, and the compact `KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL` JSON string. The full run-outcome graph snapshot needed for query construction belongs in **codex_run_outcome_records(run_outcome_record_id PRIMARY KEY, serialized_json)**, not in the innerdict table or repeated in each output row. Store joins that separate table for query. XLSX/DOCX and Codex innerdict tables share the two-column `(KTP_NAMEKEY_COL, KTP_INNERDICT_JSONLINES_COL)` schema. Section 7's same-column graph-storage snippets and the previous filter-on-read item 4 are withdrawn. Points 2 and 3 are settled above; no copied legacy cycle guard.

### 5. Preserve the architecture's two-field CodexInnerDict

`CodexInnerDict` remains exactly `innerdict: InnerDict` plus `run_outcome_response_record: RunOutcomeResponseRecord`. In the private JSON-only wire model, the corresponding field is `run_outcome_response_record_json: _RunOutcomeResponseRecordJson`; `run_outcome_json` names the stored/read snapshot value. Its `innerdict` mapping is only the serialized image of `InnerDict.data`; the authoritative model and existing procedure-restoration path stay typed. No `attempt` field is added to CodexInnerDict, QueryResponseRecord, or any outerdict: only RunOutcomeResponseRecord owns `attempt` beside `run_outcome_request_record`.

~~~python
class _CodexInnerDictJson(FrozenStrictModel):
    innerdict: dict[str, Any]
    run_outcome_response_record_json: _RunOutcomeResponseRecordJson

    @classmethod
    def from_codex_innerdict(cls, value: CodexInnerDict) -> Self:
        return cls(
            innerdict=value.innerdict.data,
            run_outcome_response_record_json=(
                _RunOutcomeResponseRecordJson.from_run_outcome_response_record(
                    value.run_outcome_response_record
                )
            ),
        )

# In CodexInnerDict.from_serialized:
return cls(
    innerdict=InnerDict.from_mapping(
        serialized.innerdict, _CodexInnerDictProcedure(),
    ),
    run_outcome_response_record=(
        serialized.run_outcome_response_record_json.to_run_outcome_response_record()
    ),
)
~~~

The existing session metadata summary **remains card data**, and the run-outcome response body is restored as card data. `CodexInnerDict.validate_codex_innerdict` must continue to check its `KTP_AI_AUGMENT_SESSION_METADATA_COL` against the outcome session ID. Store additionally reads staging metadata from `codex_output_rows` and the outcome snapshot from `codex_run_outcome_records`, verifying the same session link. Exact readback SQL is implementation detail:

~~~python
session_id = outcome._codex_session_record().session_id
if session_id is None or session_id != outcome.run_outcome_request_record.session_id:
    raise ValueError(Locale.INNERDICT_OUTCOME_MISMATCH)
summary = CodexRolloutRecord.parse_summary_json(
    self._required_text(KTP_AI_AUGMENT_SESSION_METADATA_COL)
)
if UUID(summary[CODEX_SESSION_ID_JSON_KEY]) != session_id:
    raise ValueError(Locale.INNERDICT_OUTCOME_MISMATCH)
~~~

Items 4–5 are implemented and verified by the local checks above. Section 7's JSON-only snapshot construction/reconstruction and separate-table boundary govern the implementation.

## Implemented surgical rename: commit/validation-request index

Operator selected `commit_validation_request_record_index` for the existing secondary commit→validation ID lookup. Its rows are not `AttemptProperty` objects: `AgentRuntimeAttempt` aliases `BackendValidationRequestRecord`, while the table holds only IDs. The implemented two-plain-column shape is:

```sql
CREATE TABLE commit_validation_request_record_index (
    commit_request_record_id VARCHAR PRIMARY KEY,
    validation_request_record_id VARCHAR NOT NULL
);
```

Confine edits to the table/column/DDL constants in `protected/src/backend/helpers/vars.py`, Store's insert and reads/check (including direct ID select in completed outcome), affected API constant reexports, and existing tests that inspect the table or monkeypatch the insert. Remove the one-field `attempt_record` JSON and its JSON key; no old-schema fallback or implicit migration. Keep the `/validate` replay line, typed attempt, replay order, other detour tables, and architecture.py unchanged. Existing DBs require the established explicit replay-log/CAS rebuild. No new tests; verify surgically adapted tests, Ruff, mypy, diff check.

Implemented. Operator clarified that `attempt_record` is not an implementation concept; use `validation_request_record_id`, not `attempt_id` (retry audit already uses `attempt_id` for commit ID). Backend-focused tests: 14 passed; detour mypy and targeted Ruff passed. The operator preflight had 71 passed and one 30-second subprocess timeout while run concurrently with backend tests; the timed-out case passed alone in 16 seconds. The full feasible detour suite then passed serially without concurrent load: 750 passed, 5 skipped, 4 deselected. Query review finding, not part of this rename: `codex_innerdicts` already carries session metadata; `_codex_innerdicts` redundantly reads it from `codex_output_rows` as a cross-projection check. No edit to that path without separate review.

## Current read-only detour DB audit

The operator requested an atom-by-atom verification of their table-flow narrative and a complete count/audit of every detour DB table. Static source inventory: **11 persistent user tables** when all lifecycle stages have occurred (`replayed_http_request_log_records`, `commit_validation_request_record_index`, `codex_fc`, `codex_fco`, `codex_calls`, `codex_turn_ref`, `codex_retry_baselines`, `codex_evidence_attempts`, `codex_output_rows`, `codex_run_outcome_records`, `codex_innerdicts`). There are **two views** (`codex_output`, plus `codex_turn_ref_normalized` only for match version 2); the normalized view is created but has no production reader in the detour source. The shared materializer briefly creates and drops `codex_innerdicts_frame`, which is not a persistent table. Relation creation is lazy: empty rebuild has two tables, first accepted push makes ten, first completed accepted outcome makes eleven. The separate sample inference proxy's `pricing_daily` and `requests` are SQLite tables in another DB and are excluded. This is a code-defined inventory, not a physical DB-file introspection. Audit findings: startup log projection verifies ordinal/row-count/hash coverage, not every projected UUID/JSON envelope; `codex_output_rows` is populated for accepted validations, keyed by commit ID plus unique filename/fragment, not every accepted HTTP push/validation; `codex_innerdicts` contains only completed-card flat data, grouped by namekey; `codex_run_outcome_records` stores a full typed outcome/attempt graph projection for historical query readback, not a copy of the flat output or a replay input. All are secondary to log/CAS, though operationally used. Rebuild also constructs Context from current config and a read-only main source DB, so log+CAS alone have not been shown sufficient under source/config drift. Do not change schema/query/verification paths without separate approval; this request is review only.

Implemented rename: `detour_http_records` → `replayed_http_request_log_records`. The operator directly instructed implementation on 2026-10-01; schema and replay behavior were unchanged. Source check: both live append and rebuild parse the log line as `HttpRequestLogRecord` before DB insert; `_apply_durable_record` inserts and reads it back inside a transaction, so a failure there rolls that transaction back. But `_replay_durable_record`'s envelope-value comparison runs **after** that transaction commits; live append's stronger same-type/original-object comparison also runs after commit, whereas rebuild has no original typed object to compare. Any failure poisons that Store instance; it does not necessarily terminate the OS process or undo the durable log, and a post-commit comparison failure need not remove the DB row. The new name is descriptive of successfully projected rows, but it does not imply atomic certification by the postcommit check.

Recovery RCA: the agent's earlier categorical statement that explicit `--new` is always required after a failed live append was too strong. Manual backend CLI requires either `--new` or `--resume` and asks for confirmation unless `--yes`; `--new` additionally prompts for nonempty-log replay unless `--yes`. These are selected-mode confirmations, not a failure-triggered rebuild prompt. `--resume` constructs a fresh Store and verifies log/DB ordinal coverage and hashes, not the previous instance's `_failure` or every projected UUID/payload. If an appended line lacked a committed DB row, resume fails coverage verification and `--new` is needed. If failure occurred after a row committed and log/DB coverage and downstream query checks pass, Store `--resume` may succeed despite the prior Store failure. **Normal manual CLI startup first checks the configured full-file replay-log SHA; the unchanged pin rejects an appended log before Store opens.** After repinning the config hash (or using the explicit `--danger-no-verify-hash` CLI option), Store resume can accept the postcommit-failed row. Dashboard checks resources at its own startup, passes `--danger-no-verify-hash` to child processes, starts its first child with `--new --yes`, uses `--resume --yes` only after a clean cycle, and refuses restart in the same context after a failed cycle; a new Dashboard context starts with `--new --yes`. No production recovery-policy edit made.

Current authorized work: keep **one** real recovery test in the operator-specified **new file** `src/detours/detour_ai_augment/protected/tests/backend/test_backend_store_integration.py`, using the shared function-scoped `startup_files` fixture's `tmp_path` dummy config/source population/replay log/CAS/detour DB and production `server.configure_runtime` plus `initialize_backend_store`. No monkeypatching production. Force a failure at Store's *post-commit typed-record comparison* using an existing typed `ResponseRecord` on a non-public provider route; check the durable JSONL line, committed DB row, raw-line hash, old anchor, poisoned same Store, **actual manual `server.main` CLI `--resume --yes` subprocess refusal on the stale pin**, Dashboard-style hash-bypass Store resume, and repinned-hash Store resume. The subprocess receives the fixture's TMPDIR/NameKey environment and asserts its process-lock file exists inside `tmp_path`, not the shared system temp path. This test is the direct empirical answer to the operator's recovery question and complements the existing pre-commit readback-failure test. No production recovery-policy or schema changes in this experiment. The operator will explicitly declare when the integration test is done.

Integration test remains under operator review. The operator separately and explicitly instructed the table rename, so the earlier wait requirement no longer applies to that rename. A generic typed provider `ResponseRecord` triggers Store's real postcommit type-mismatch failure; durable log and projected row remain, row hash matches, and DuckDB anchor is still the empty prefix. The revised test explicitly verifies same-Store reads fail, the actual manual CLI subprocess refuses the changed log with an unchanged pin before Store opens, a new config-loaded Store with hash-on-init disabled resumes and appends `/pull`, and normal hash-verifying Store startup resumes after repinning **only the temporary config**. This type-mismatch trigger is intentionally artificial (production provider capture passes a base `HttpRequestLogRecord`); the test demonstrates the structural recovery gap, not a claimed ordinary provider incident. The fixture originally bootstrapped via `backend_store_lifecycle`, which transiently opened/created a shared system-temp process-lock file; operator directed removing that cross-test side effect for all consumers. Its initial empty-log rebuild now uses production `initialize_backend_store` directly, leaving subprocess startup tests' real lock behavior intact. The actual CLI proof and temp lock-path assertion pass in focused pytest (1 passed, 14.07s); focused Ruff, mypy and diff check pass. No production recovery-policy or schema edits during this investigation.

Operator moved `startup_files`, `StartupFiles`, and `source_population` into `protected/tests/fixtures/pytest_fixtures.py`. The moved fixture module is now self-contained (including its own `ROOT` and `STARTUP_NAMEKEY`) and registered from both detour test-tree `conftest.py` files. Consumers in `test_ui.py`, `test_ui_e2e.py`, `test_api.py`, `test_operator_e2e_preflight.py`, and the new integration test point to the shared fixture/helper. The new integration test explicitly checks that the **same Store** refuses a second read after the postcommit failure. Affected-file Ruff and mypy pass after the move. Full post-move run of **all 119 fixture/helper consumers** finished in 476.37s: **118 passed, 1 failed**. The sole failure was `test_completed_grid_row_uses_real_query_ipc`, after successful completed-query fixture setup, at `operator.running_dashboard -> _assert_ports_available -> socket.socket(AF_INET, SOCK_STREAM)`: this execution environment returned `PermissionError(1, Operation not permitted)`. No production or fixture assertion failed in that case; browser/ports cannot be exercised here. A pre-move run was interrupted when the operator moved the fixture; its 36 passes are superseded by the post-move run. The integration test remains under review; the operator's direct rename instruction supersedes the old rename deferral.

**Rename verification and operator readiness:** The physical table name was changed from `detour_http_records` to `replayed_http_request_log_records` in Store DDL/queries/anchor handling and affected existing tests/fixture; schema, replay behavior, and `AUTHORITATIVE_RECORDS_TABLE` constant name are unchanged. The rename-focused run passed **101 tests, 64 deselected** in 364.71s; the final full feasible run below supersedes it. Collection files in `tmp/ai-augment-rename-verification-20261001/` show **919** tests in configured main/detour/backend/operator suites plus **15** optional `tests/test_detours` tests excluded from ordinary discovery (total **934** within these sources; paused BDD and sample deploy are excluded). The first repository-main run used `pytest -q -x -m 'not real_api and not slow' tests` with per-test JUnit XML and stopped after **20 passed, 1 skipped, 1 deselected, 1 unexpected failure**. Failed node: `tests/test_duckdb_extensions.py::test_config_accepts_duckdb_extension_repo_and_platform_bins`; this Linux AMD64 environment reports platform key `linux_amd64`, whereas the configured `splink_udfs` binaries list only `linux_arm64` and `osx_arm64`. Evidence: `main.log` and `main.xml`. A second run with that test deselected stopped after **21 passed, 2 skipped, 2 deselected, 1 failure** at `tests/test_duckdb_extensions.py::test_load_duckdb_extension_from_config_path_uses_repo_or_binary`: it monkeypatches platform to `linux_arm64` but the configured absolute binary path `/Volumes/home/aicode/.duckdb/extensions/v1.5.1/linux_arm64/splink_udfs.duckdb_extension` does not exist here. Evidence: `main-after-skip.log` and `main-after-skip.xml`. The operator explicitly authorized skipping both named tests; the third platform-bound failure and authorizations are below. The final per-test inventory follows the completed checks. BDD remains excluded wholesale.

Third run with those two tests deselected stopped at `tests/test_sciscinet_name_matching.py::test_manual_best_reviewed_fixture_expectation_coverage`: its hard-coded `/Volumes/home/aicode/2026-01-02_enrich_full_df/data/test_data/sciscinet_name_matching/duckdb_ui_20260601T1750Z_export_edit_done_namekey_edit.xlsx` path is absent here. Outcome **86 passed, 2 skipped, 3 deselected, 1 failed**. Evidence: `tmp/ai-augment-rename-verification-20261001/main-after-two-skips.log` and `main-after-two-skips.xml`. The operator authorized skipping this exact test; resume with all three named tests deselected.

Fourth main-suite run with those three exact exclusions passed **140, 3 runtime-skipped, 4 deselected** (the fourth deselection is the real-API marker); evidence `main-after-three-skips.log/xml`. Full feasible detour backend/dashboard/preflight run was started with JUnit evidence `detour-feasible.xml` and `-x`. The operator explicitly waived attempts for the configured **operator, sudo, real-API, and macOS-browser** categories; these still require a per-test not-run listing, but no attempt is needed for each. Other excluded tests still need individual evidence/reason. Any unexpected failure stops the run before a fix.

The feasible detour run stopped at an unexpected failure after **655 passed, 5 runtime-skipped, 4 deselected, 1 failed** in 1045.05s. Failed node: `src/detours/detour_ai_augment/protected/tests/backend/test_appendwatch.py::test_standalone_watcher_fixtures_do_not_import_dashboard`. Its `watcher_fixture_process` child pytest run failed the `ImportAudit.pytest_runtest_call` assertion at `protected/tests/pytest_plugin.py:570-578`; the traceback does not identify which of the three import-audit assertions failed. Evidence: `tmp/ai-augment-rename-verification-20261001/detour-feasible.log` and `detour-feasible.xml`. Initially stopped without a fix or exclusion; the subsequent isolated rerun and diagnosis are recorded below.

Operator authorized a read-only investigation of that particular failure, and separately requested use of `AUTHORITATIVE_RECORDS_TABLE` from vars instead of a literal in `backend_startup_process`; that exact function-local import/query edit is made, Ruff passes, and it does **not** address the import audit. Isolated rerun reproduced the failure (`watcher-isolated.log/xml`). Read-only child diagnostic (`watcher-import-diagnostic.log`) found `isolated_lima_configuration=False`, no NiceGUI modules, and `fastapi_loaded=True`. Cause: `protected/tests/conftest.py` now registers `fixtures.pytest_fixtures`; importing that fixture module eagerly imports both backend `server` and `ai_augment_backend_store`, each of which loads FastAPI. Importing only backend vars does not. Therefore the child pytest process has FastAPI in `sys.modules` before watcher test execution, violating the deliberate no-FastAPI assertion. This is a deterministic test-fixture import-isolation regression, not a Linux platform/resource failure or appendwatch functional failure. The operator subsequently approved the narrow import move, recorded below.

The operator approved moving those two backend imports from module top-level into `startup_files()` in `protected/tests/fixtures/pytest_fixtures.py`, with no other fixture change. Applied exactly. The isolated watcher test now passes **1/1 in 5.42s**; evidence `tmp/ai-augment-rename-verification-20261001/watcher-after-fix.log/xml`. The 95 previously unexecuted feasible detour nodes passed **95/95 in 57.57s** (`detour-remaining.log/xml`). A separate fixture-closure inventory found **97** tests using `startup_files`: **95 locally feasible**, **2 in exempted macOS-browser `test_ui_e2e.py`**. The focused run of all 95 locally feasible fixture users passed **95/95 in 444.19s** (`startup-fixture-focused.log/xml`); node lists are `startup-fixture-all-nodes.txt` and `startup-fixture-feasible-nodes.txt` in the same evidence directory. Thus all selected feasible detour nodes are accounted for across the original and continuation runs: **751 passed, 5 runtime-skipped, 4 marker-deselected**; the fixture-focused run separately verifies every locally feasible user after the import move.

**Optional-detour inventory, 2026-10-01:** A separately collected `tests/test_detours` run stopped at `tests/test_detours/test_detour_mode0_econ_stats.py::test_detour_contract_and_mode0_econ_stats_readonly`: `src/detours/detour_mode0_econ_stats.py:689` requires Plotly/Kaleido from the optional `detour-mode0-econ-stats` environment, unavailable in the required detour-ai-augment environment (`optional-detours.log/xml`). After the operator authorized skipping that exact test, `test_detour_module_entrypoint` failed at the same child-process import (`optional-detours-after-skip.log/xml`); the operator authorized skipping that specific test too. With those two and the TASK-excluded slow main-pipeline test deselected, **12/12 passed, 3 deselected in 20.78s** (`optional-detours-after-two-skips.log/xml`). Ten renamed-table SQL E501 errors were corrected with `AUTHORITATIVE_RECORDS_TABLE` and line wrapping; full Ruff now passes (`ruff-after-fix.log`). The 11 fixture-move mypy import errors found at that time (`mypy-detour.log`) were later resolved by the four approved direct imports; mypy now passes 63 source files. The final post-edit detour run and per-test inventory are below. Do not modify the other detour's code.

## Current authorized attempt-naming audit (2026-10-01)
Operator first directed `codex_retry_baselines.attempt_id` → `commit_record_id`, then explicitly directed a grep of all `attempt` uses against architecture's narrow `AttemptProperty` (`AgentRuntimeAttempt` aliases `BackendValidationRequestRecord`) and appropriate renames wherever the referent is not that object. Initial grep inventory: `tmp/ai-augment-rename-verification-20261001/attempt-audit.txt` (409 matches, including tests/prose). The only authoritative `attempt` objects are validation request records and the `RunOutcomeResponseRecord.attempt` reference to one; those refs are preserved. No architecture.py edit or legacy migration/fallback.

Implemented and verified: both `codex_retry_baselines` and the evidence-assessment audit table now call their commit-ID column `commit_record_id`; the audit table is named `codex_evidence_audits` (existing global `CODEX_EVIDENCE_AUDIT_TABLE`), since it did not contain `AttemptProperty` objects. `CODEX_RETRY_COMMIT_RECORD_ID_COL` is the single column global; the inaccurate `CODEX_RETRY_ATTEMPT_ID_COL` is gone. Store DDL/insert/read and test SQL use the new names. Baseline DTO/reads, `_EvidenceAssessmentAudit`, commit-derived `commit_request_timestamp`, retry evaluation/projection helper names, and synthetic test-helper seed names follow their actual referents. The appendwatch temp filename's placeholder now names the commit ID; its emitted filename value is unchanged. Dashboard CodexInnerDict footnote args no longer say `attempt`. The UI history panel is **“Runs and outcomes”** with `RUN_OUTCOME_HISTORY_*` names per the exact approved contour below; it includes dashboard Runs, some without a commit. Natural-language verbs and the negative check for an absent legacy `attempts` JSON key remain; they are not model references. Active `attempt` refs in outcome/query/UI remain typed `AgentRuntimeAttempt`/`BackendValidationRequestRecord`. The operator separately instructed the remaining `test_ui.py` hardcoded `COMMENT ON TABLE replayed_http_request_log_records IS NULL` use the existing table global; done.

The historical focused retry run passed **7, 1 skipped, 273 deselected** (`tmp/ai-augment-rename-verification-20261001/attempt-rename-retry.log/xml`); the final full feasible run supersedes it for current test status. The 11 fixture-import mypy errors were resolved by the four approved direct imports; detour mypy passes. Stop and report any *new* unexpected test failure before fixing it, per operator instruction. The operator flagged two misleading phrases: `RUN_OUTCOME_PROJECTION_INCONSISTENT` now says “Run-outcome projection is inconsistent” (dropping only “validation”), and unused `ACCEPTED_SESSION_DUPLICATE` was removed rather than reworded to an invented “session outcomes” concept. Source search found no consumer of that constant.

Operator approved renaming the test-only `commit_record_seed` to `synthetic_record_id_seed`: the helper hashes this synthetic input into both push and commit-request IDs; it does not come from pipeline config. Also approved backend-side local `_validate_commit(...)` result `attempt` → `validation_request_record`, preserving architecture-defined `RunOutcomeResponseRecord.attempt` and `AgentRuntimeAttempt`. Both exact renames are applied. The dashboard `test_ui.py` file passed **206/206 in 529.60s** immediately before these two separate renames (`attempt-rename-ui.log/xml`). The focused backend/HTTP-interceptor/operator-preflight selection after them passed **171, 1 skipped, 225 deselected in 404.60s** (`approved-seed-and-validation-name.log/xml`). Ruff and `git diff --check` pass.

Audit correction: `Locale.ATTEMPT_DATABASE_INCONSISTENT` is live, used by `DashboardQuerySnapshot.validate_records()` and `_ResearcherView.from_snapshot`/`_RunCommitView.backend_lifecycle`; an earlier commentary incorrectly called it unused after searching the wrong term. It was not removed or renamed. Its message “validated attempt database state is inconsistent” conflates several query/run checks and remains pending review.

The operator approved and the agent applied exactly these direct-import corrections: `StartupFiles`/`STARTUP_NAMEKEY` from `protected.tests.fixtures.pytest_fixtures` in `test_ui_e2e.py` and operator preflight; `STARTUP_NAMEKEY` from there in `pytest_plugin.py`; direct protected backend `api` import for the lock-path constant in `test_backend_store_integration.py`. `pixi run -e detour-ai-augment mypy-detour-ai-augment` now passes all 63 source files.

Collection after the first naming edits found **919** configured main/detour test nodes (`collection-after-naming.txt`); separate optional detour collection has 15, for 934 across those sources. Later approved UI renames changed two node names but not the count; the current names are recorded in the inventory below. The 772 detour nodes comprise 756 in the feasible selection plus 16 outside it (three sudo appendwatch, one real-API, three operator E2E, nine `test_ui_e2e.py` browser-module nodes). The nine browser-module nodes include the subprocess-only fixture check that passed separately and one real-query IPC case attempted earlier but blocked by denied local socket creation. The 143 main selected nodes are evidenced by `main-after-three-skips.xml`; optional 12/15 by `optional-detours-after-two-skips.xml`.
The subprocess-only `test_completed_query_fixture_has_current_queryable_history` within the browser module was separately rerun after naming and passed **1/1 in 15.19s** (`completed-query-fixture-after-naming.log/xml`); it does not require a browser. Thus the browser-module exclusion is eight remaining nodes, one of which was attempted earlier and failed at denied local socket creation.
The real recovery integration test `test_resume_after_committed_row_and_postcommit_failure` was also rerun after naming and passed **1/1 in 7.91s** (`backend-store-integration-after-naming.log/xml`).

The operator approved the exact `_RunCommit*` naming-only contour below. `_RunCommitView` combines an optional dashboard Run and optional query-derived AgentRuntimeAttempt/accepted CodexInnerDict/RunOutcomeResponseRecord, keyed by session where possible; commit ID is only a display/join key. `_RunCommitVarView` is the per-researcher-variable flattened UI state and also supports a no-run READY placeholder. The history merges query-completed records and dashboard runs, deduplicates matched sessions, and its current state feeds the main grid. Preserve real commit ID, attempt, run, outcome field names, and test fake's actual run-ID collection. No model behavior or query/replay representation change is authorized.

| Current | Approved replacement |
|---|---|
| `_RunCommitView` | `_RunAttemptView` |
| `validate_run_or_commit` | `validate_run_or_attempt` |
| `_RunCommitVarView` | `_ResearcherVarRowView` |
| `run_commit_views` / `latest_run_commit_view` | `run_attempt_views` / `latest_run_attempt_view` |
| `run_commit_var_views` / `latest_run_commit_var_view` | `researcher_var_row_views` / `current_researcher_var_row_view` |
| `run_commit_view` / `run_commit_var_view` locals | `run_attempt_view` / `researcher_var_row_view` |
| `to_var_view` | `to_researcher_var_row_view` |
| `accepted: CodexInnerDict | None` | `codex_innerdict: CodexInnerDict | None` |
| `GRID_RUN_COMMIT_TIMESTAMP_FIELD = "run_commit_timestamp"` | `GRID_TIMESTAMP_FIELD = "timestamp"` |
| `RUN_COMMIT_VIEW_EMPTY` | `RUN_ATTEMPT_VIEW_EMPTY`, saying `Run` or `AgentRuntimeAttempt` is required |

Panel: label **“Runs and outcomes”**; `RUN_HISTORY_*`/`run_history_*` → `RUN_OUTCOME_HISTORY_*`/`run_outcome_history_*`; `run_commit_detail_rows` → `run_outcome_history_rows`; HTML test IDs → `run-outcome-history-*`. Only directly affected tests adapt. The approved four direct-import corrections for mypy were applied before this naming change and verified afterward.

Implementation of this exact naming contour is complete. The only remaining `run_history` identifier in detour Python is the browser test fake's genuine collection of Run IDs. The approved four direct-import corrections are also complete. Detour mypy passes **63/63 source files**; whole-source Ruff and unstaged `git diff --check` pass after the targeted architecture-import move recorded in current status. Post-edit focused runs passed: dashboard `test_ui.py` **206/206 in 467.29s** (`approved-run-outcome-names-ui.log/xml`), operator preflight **72/72 in 55.25s** (`approved-run-outcome-names-preflight.log/xml`), Store recovery integration plus subprocess-only completed-query fixture **2/2 in 21.67s** (`approved-imports-feasible.log/xml`). The final full feasible detour run then passed **751, 5 runtime-skipped, 4 marker-deselected in 1278.50s** (`final-feasible-detour.log/xml`). No operator/browser/sudo/real-API case is claimed as passed.

## Final per-test evidence and operator handoff

Scope counted: configured main/detour/backend/operator collection **919** (`collection-after-naming.txt`) plus optional other-detour collection **15** (`collection-optional-detours.txt`), total **934**. Paused BDD and sample deploy modules are excluded by repository/task configuration and are not part of this denominator. Across those 934: **904 distinct passed** (751 final feasible detour + one browser-module subprocess-only fixture in `approved-imports-feasible.xml` + 140 repository-main + 12 optional other-detour), **8 runtime-skipped** in final JUnit, **22 without a passing run here**. Of the 22, **6 were attempted and blocked by environment/platform requirements** and **16 were not attempted** under operator instructions or TASK. Focused overlapping reruns are not double-counted. No test failed in the final feasible run. `pre-commit-operator` itself requires Darwin/Lima/Chrome (`pyproject.toml:347-378`) and was not run on this Linux host.

All evidence paths below are relative to `tmp/ai-augment-rename-verification-20261001/`. The JUnit XML files identify individual executed testcases; collection files establish the individually excluded nodes. Group prefixes save repetition: `D=src/detours/detour_ai_augment`, `R=tests`. The three operator E2E and seven remaining macOS-browser nodes were not attempted here by the operator's explicit waiver. The real-query IPC browser case *was* attempted during fixture verification and stopped at `socket.socket(AF_INET, SOCK_STREAM)` with `PermissionError(1)`; no assertion of production behavior was reached.

**Five runtime skips in `final-feasible-detour.xml` (individual `<testcase><skipped>` reasons):**

| Test node relative to D | Reason |
|---|---|
| `tests/backend/test_api.py::test_historical_haanen_retry_preserves_verified_evidence_roundtrip` | Optional historical rollout fixtures absent. |
| `tests/backend/test_api.py::test_multiple_sql_matches_report_the_exact_excerpt` | Multiple evidence matches currently allowed. |
| `tests/backend/test_ipc.py::test_dashboard_client_queries_real_mode_0600_unix_socket` | Unix sockets denied (`Operation not permitted`). |
| `protected/tests/backend/test_appendwatch.py::test_inspect_flags_nonregular_substitution_without_blocking[socket-path was replaced by a non-regular file]` | Unix sockets denied. |
| `protected/tests/backend/test_appendwatch.py::test_cli_detects_delayed_directory_fifo_symlink_and_socket_substitutions` | Unix sockets denied. |

**Three runtime skips in `main-after-three-skips.xml`:**

| Test node relative to R | Reason |
|---|---|
| `test_csv_sample_validation.py::test_csv_rows_match_samples` | Sample data absent. |
| `test_duckdb_extensions.py::test_configured_duckdb_extension_binary_loads_unaccent` | Platform-specific splink_udfs binary absent. |
| `test_sciscinet_name_matching.py::test_manual_best_reviewed_fixture_outputs_select_expected_author_ids[manual_best_reviewed_fixture_missing]` | Hard-coded macOS author-review fixture files absent. |

**22 not passed here; each node is present in the collection evidence named above:**

| Test node | Reason / attempted evidence |
|---|---|
| `R/test_duckdb_extensions.py::test_config_accepts_duckdb_extension_repo_and_platform_bins` | Attempted; Linux AMD64 not in configured splink_udfs platforms (`main.xml`, `main.log`); specific skip approved. |
| `R/test_duckdb_extensions.py::test_load_duckdb_extension_from_config_path_uses_repo_or_binary` | Attempted; configured `/Volumes/.../linux_arm64` binary absent (`main-after-skip.xml/log`); specific skip approved. |
| `R/test_sciscinet_name_matching.py::test_manual_best_reviewed_fixture_expectation_coverage` | Attempted; hard-coded macOS XLSX fixture absent (`main-after-two-skips.xml/log`); specific skip approved. |
| `R/test_sciscinet_name_matching.py::test_real_api_openalex_identifies_known_false_confident_ssn_picks[NOTSET]` | Real-API marker; operator waived attempt. |
| `R/test_detours/test_detour_mode0_econ_stats.py::test_detour_contract_and_mode0_econ_stats_readonly` | Attempted; optional Plotly/Kaleido env absent (`optional-detours.xml/log`); specific skip approved. |
| `R/test_detours/test_detour_mode0_econ_stats.py::test_detour_module_entrypoint` | Attempted; child process needs same optional env (`optional-detours-after-skip.xml/log`); specific skip approved. |
| `R/test_detours/test_detour_step4_breakdown.py::test_slow_real_config_pre_deviation_full_equivalence` | Real main-pipeline resources prohibited by TASK; not attempted. |
| `D/protected/tests/backend/test_appendwatch.py::test_cli_static_eacces_is_scoped_and_recovered_files_fail_closed` | needs_sudo; operator waived attempt. |
| `D/protected/tests/backend/test_appendwatch.py::test_cli_dynamic_eacces_existing_watch_is_detected_and_scoped` | needs_sudo; operator waived attempt. |
| `D/protected/tests/backend/test_appendwatch.py::test_cli_shutdown_reconcile_marks_files_from_unwatched_root_interval` | needs_sudo; operator waived attempt. |
| `D/protected/tests/backend/test_pydantic_to_paste.py::test_academic_institution_round_trips_against_real_apis` | real_api marker; operator waived attempt. |
| `D/protected/tests/operator/test_operator_e2e.py::test_existing_aivm_exposes_the_persisted_appendwatch_topology` | Human/operator E2E; operator waived attempt here. |
| `D/protected/tests/operator/test_operator_e2e.py::test_complete_dashboard_backend_codex_commit_and_replay_workflow` | Human/operator E2E; operator waived attempt here. |
| `D/protected/tests/operator/test_operator_e2e.py::test_completed_dashboard_backend_codex_workflow_renders_researcher_card` | Human/operator E2E; operator waived attempt here. |
| `D/tests/control_centre/test_ui_e2e.py::test_completed_grid_row_uses_real_query_ipc` | Attempted during fixture-user run; local `AF_INET` socket creation raised `PermissionError(1)` before production assertion; browser/Lima required. |
| `D/tests/control_centre/test_ui_e2e.py::test_underscore_field_labels_render_literally_in_researcher_card` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_main_grid_and_researcher_card_use_compact_line_spacing` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_selected_researcher_row_is_highlighted` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_researcher_selection_and_run_outcome_history_are_idempotent` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_completed_researcher_metadata_is_available_in_visible_run_outcome_history` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_displayed_researcher_card_downloads_as_docx` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_control_centre_browser_contract` | macOS browser; waived. |

The separately executed `D/tests/control_centre/test_ui_e2e.py::test_completed_query_fixture_has_current_queryable_history` **passed** (`approved-imports-feasible.xml`) and is already counted among the 904, not among the 22. The recovery integration test also passed there but is already included in the final 751. Operator handoff: run `pixi run pre-commit-operator` on Darwin with configured Lima and Chrome. The staged README has two unrelated trailing-space lines (`README.md:102,125`); `git diff --cached --check` fails, though this is not a step in the Pixi operator task. No edit to that human-staged README was authorized within the strict rename scope.
