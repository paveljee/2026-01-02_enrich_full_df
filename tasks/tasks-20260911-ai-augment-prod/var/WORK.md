# AI augment production — current workbook (2026-09-30)

## Governing boundaries
Read tasks/tasks-20260911-ai-augment-prod/src/TASK.md and this entire file after compaction. Do not consult former WORK or HUMANS. Use pixi run -e detour-ai-augment for Python/checks; never run src.repl or modify the main DB. Git is read-only for this agent: do not stage/unstage. Do not edit architecture.py without targeted approval, excluded BDD, or human-signed-off comments. Source and existing-test edits must be surgical; no old-record fallbacks, unauthorized wrappers, new/redundant tests, wholesale replacements, or unrelated cleanup. The operator's earlier "don't implement yet" direction still pauses source edits; the design decisions below are settled, with remaining SQL/method wiring being implementation work rather than new operator decisions. Preserve exact model shapes and docstrings, particularly CASCodexRolloutRecord. Do not change a reviewed boundary while implementing it without returning for review.

Architecture.py governs models; README lifecycle is somewhat stale. Replay log is principal and detour DB is fully reconstructible from log/CAS; DOCX renders DB innerdicts. Store alone owns detour SQL and authoritative lifecycle records. Current replay contour: append/fsync, log readback, project in one DB transaction, reconstruct typed object from DB, compare value and byref links, then advance the one current_replayed_record cursor if applicable. BUSY 503 exchanges are logged but do not advance that cursor. On validation replay the cursor must be a BackendCommitRequestRecord; intervening provider HTTP or BUSY 503 log lines are permitted. Assert identity with is only for the same byref object, not across a fresh reconstruction. Post-commit validation gets a byref commit and Store-supplied inputs/reads; it does no SQL. Existing LazyResultFactory callbacks for validation are truly deferred and use (value, error) results; immediate HTTP-record lookup is instead Callable[[UUID], HttpRequestLogRecord].

## Current source and verification status
The working/index tree already contains the approved push-admission implementation (exclusive HTTP gate, inlined API push decision, immediately reconstructed PushResponseRecord plus eventual promise, BUSY 503, narrow cursor invariant), the ID-free run-outcome response-body cleanup, and a secondary run-outcome/query readback codec. Preserve the operator's names current_replayed_record, session_id, captured_push_request_http_record, the_coroutine, stores_push_promise, and PUSH_PROCESSING_DESCRIPTION. No further source edits have been made during the current serialization design discussion.

The last full Linux-feasible detour suite: 749 passed, 5 skipped, 4 deselected, 1 failed (operator preflight test_operator_artifact_validator_accepts_completed_store_history, raising Locale.COMMIT_BODY_RECORDS_MISMATCH from BackendCommitRequestRecord.from_http_request_log_record). Source Ruff and targeted mypy had passed before that run. pre-commit-operator requires Darwin/Lima/Chrome and cannot run here. Do not claim operator readiness; after approved implementation, run relevant existing tests and all feasible checks, investigate the remaining failure without disguising a production defect as a test defect.

## Operator decisions on the three review points
1. `codex_innerdicts` must contain only flat card innerdict JSONL. Store the full query-ready outcome snapshot once in `codex_run_outcome_records(run_outcome_record_id PRIMARY KEY, serialized_json)`; duplicate keys fail the detour loudly, with no upsert or fallback. `codex_output_rows` remains the accepted-card staging table and links its one card row to the outcome ID.
2. Pull/push response JSON decoders accept optional predecessor references. Omitted and explicit `None` mean `None`; a supplied record is used by reference. No sentinel or omission check.
3. Purge the old `RunOutcomeResponseRecord` attempt-array serializer/deserializer, `seen` guard, and `SERIALIZED_ATTEMPT_LINEAGE_KEY` when the separate-table codec replaces that path. No legacy or fallback support, and no `seen` in the new codec.

## Settled change contour — ID-only validation replay body
NO SOURCE EDITS YET. The existing _ValidationRequestBodyJson owns the JSON schema and parsing. No parallel validation-body JSON-key globals, manual json.loads/key-set checks, or LazyResultFactory for immediate UUID resolution. If a JSON-key constant proves unavoidable elsewhere, name it with _JSON_KEY. No architecture.py edit is proposed.

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
assert body.commit_request_record is commit_ref
assert body.initial_validation_request_record is initial_ref
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
self._insert_attempt_record(validation)
reconstructed = validation
~~~

In _apply_validation_record, remove the parsed argument and only checks of now-absent embedded commit/pull/push/initial HTTP envelopes. Keep its cursor-is-commit assertion, projected commit/initial UUID and ordinal checks, request-header checks, the existing provider _http_record_with_ordinal check (earlier than validation, complete, equals the body-resolved record), ModelHttpInterceptor.from_records, evaluate_commit call, observed-vs-recomputed validation and provider-ID comparisons, and _project_validation. Do not change failure ordering unnecessarily. Provider records are separate earlier replay-log lines and are fetched from the projected detour DB via Store._http_record, not copied inside /validate. Store's shared append/readback/project/reconstruct/compare/cursor contour remains unchanged.

### 3. Other consumers of the old embedded validation envelopes
run_outcome_event.py's current RunOutcomeResponseRecord.from_serialized_json secondary readback walks validation lines and assumes each contains full commit/pull/push/provider HTTP objects. That assumption becomes false. Store's cursor holds only the latest lifecycle record, **not every historical outcome's refs**. For query, Store._codex_innerdicts must get each historical outcome and its validation/pull/push/commit/provider records from projected detour DB (or a secondary DB representation derived from the same log/CAS), construct the typed CodexInnerDict and AiAugmentSingularOuterDict, and serialize a **fully self-contained query payload**. The dashboard then parses it using _QueryResponseBodyJson → _AiAugmentSingularOuterDictJson → _CodexInnerDictJson and reconstructs its own typed byref graph from that payload, with no Store/DB access. The query-only payload includes the full pull, push, commit, validation, and provider HTTP envelopes needed for each attempt; the principal /validate and /completed replay-log lines remain ID-based/lean. Place the query-only serialized-record schema at the existing CodexInnerDict JSON handoff, not inside RunOutcomeResponseRecord.serialize (whose record-level semantics are the replay-log HTTP line). Section 7 specifies the private JSON fields; do not add a competing architecture class.

Current query call path: Store.query_response_record calls QueryResponseRecord.from_query_request with Store.ai_augment_singular_outerdicts(); that reads the projected codex_innerdicts table. IPC reconstructs QueryResponseRecord from its HTTP envelope. The dashboard receives the query response body and calls DashboardQuerySnapshot.from_serialized_json → QueryResponseRecord.outerdicts_from_response_body. QueryResponseRecord.from_serialized_json is **not currently the dashboard body parser**. Store's live append and full log rebuild project/read back each record, so DB is the proper historical source; no full replay-log replay per query. But projected HTTP rows/secondary rows do not automatically preserve typed Python refs for all earlier outcomes. Store must reconstruct historical objects from DB before serializing a complete query payload; the dashboard cannot receive Store's Python object identities across the socket. Avoid the invented name lineage in any proposed model/class: describe existing validation/pull/push/commit objects and their query-only serialized HTTP envelopes directly. Any proposal to pass Store refs into QueryResponseRecord.from_serialized_json must distinguish a Store-side construction call from the dashboard's independent body deserialization and must not make the latter depend on Store.

Read-only code audit: _http_record_with_ordinal(UUID) returns a projected **base** HttpRequestLogRecord; _backend_commit_request_record(record) only verifies/returns the **current cursor** commit, not an arbitrary historical one. _replay_durable_record invokes the projection transaction and must not be rerun by a read-only query. Store does not have an existing arbitrary-ID typed readback function to invoke as-is; the secondary snapshot design below avoids needing one. QueryResponseRecord.from_query_request constructs the backend response; its from_serialized_json is a decoder, not a serializer. The dashboard can only reconstruct from the fully serialized query response body, not receive Store's Python references.

Query reconstruction boundary: at _apply_run_outcome_record, Store already has the reconstructed RunOutcomeResponseRecord and its attempt→commit→push→pull→prior-validation graph. A complete secondary JSON snapshot of that graph must be projected once into **codex_run_outcome_records**, with exactly two columns: run_outcome_record_id (primary key) and serialized_json. Insert plainly: any key conflict fails the projection transaction and the detour loudly; no upsert, ignore, overwrite, or fallback. It must not be in codex_output_rows or codex_innerdicts. Rebuilding from log must regenerate it. Section 7 defines the private JSON-only codec; its former same-column storage/readback proposal is withdrawn. Codex_innerdicts must be plain card innerdicts, like XLSX/DOCX innerdicts. Store combines card rows and snapshot records when constructing CodexInnerDict for query; the dashboard reconstructs from the complete query body without Store. Record-level serialize/from_serialized_json retain their distinct replay-log meanings.

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

Use this only when no excluded byref field must be supplied. Pull/push response, commit, validation, run outcome response, and query response need their real child-specific reconstruction. serialize/from_serialized_json represent the replay-log serialized HTTP record, not a secondary graph. BackendCommitRequestRecord and RunOutcomeResponseRecord currently use serialize for secondary graphs; separate that handoff without losing query/attempt data. QueryRequestRecord/QueryResponseRecord are ephemeral, but still participate in the method audit.

The operator's exact decisions for the response codecs and old-path removal are summarized above. Store still supplies its owned references on authoritative replay; accepted pushes still require a valid pull.

### 5. Record-class audit and implementation requirements
The operator authorizes **redefining the existing four AiAugmentHttpRequestLogRecord methods in a subclass whenever justified**, visibly and specifically; do not add a separate thin adapter method. A bogus super() forwarding override on a reference-bearing record is not acceptable. Optional pull/push decoder references default to `None` per the settled decision above; the approved item-3 methods supply the concrete commit/validation/outcome decoder signatures. Store's authoritative DB-readback path deliberately uses `from_http_request_log_record` with its owned references, not an unnecessary serialize/decode round trip. The Store branch in section 2 is a body-first contour and must not leave BackendValidationRequestRecord.from_serialized_json unusable. The secondary JSON codec design is in section 7; its separate-table SQL wiring is still missing.

Current excluded-field audit (all are AiAugmentHttpRequestLogRecord descendants):

| Class | Current excluded fields | Current serialize/from_serialized_json concern |
| --- | --- | --- |
| RequestRecord, ResponseRecord, PullRequestRecord, PushRequestRecord, RunOutcomeRequestRecord, QueryRequestRecord | None | Inherited base round-trip is structurally plausible; four members are not explicitly declared on each class as required. |
| PullResponseRecord | optional validation_request_record=None | Base JSON round-trip silently loses the retry validation byref; child from_http_request_log_record works only when Store supplies it. |
| PushResponseRecord | optional pull_response_record=None | Base JSON round-trip fails validation for accepted 202 (pull required); rejected responses can silently lose an available pull byref. |
| BackendCommitRequestRecord | required commit_request_body | Has custom serialize/from_serialized_json, but these use _BackendCommitRequestRecordJson's copied secondary graph rather than the replay-log HTTP line. from_http_request_log_record needs Store-supplied pull/push refs. |
| BackendValidationRequestRecord | required validation_request_body | Inherited value-only from_serialized_json fails because Field(exclude=True) omits the body. Must explicitly redefine the existing method(s) so body decoding uses the Store's exact commit/initial refs and projected provider records. |
| RunOutcomeResponseRecord | required run_outcome_request_record; optional attempt=None | Custom serialize/from_serialized_json use a secondary attempt-lineage graph, not the plain replay-log line; from_http_request_log_record derives request but defaults attempt to None. A completed outcome can therefore lose its attempt without the model itself rejecting it. |
| QueryResponseRecord | required ai_augment_singular_outerdicts | Custom from_http_request_log_record/from_serialized_json rehydrate the excluded field from response_body; current round-trip is structurally sound, subject to the nested CodexInnerDict/run-outcome codec. |

AgentRuntimeAttempt is **an alias** of BackendValidationRequestRecord, not another Record class. The remembered attempt/exclude issue is the same general failure mode: Pydantic omits excluded fields from JSON, so a defaulted field silently resets and a required field fails construction. In current code RunOutcomeResponseRecord.attempt uses default=None, **not default_factory**; BackendValidationRequestRecord.validation_request_body has no default. Do not describe an active attempt default_factory that is not present.

### 6. Verification after source implementation
Surgically adapt existing tests/fixtures asserting embedded validation envelopes to ID-only JSON; do not remove or wholesale replace tests, add duplicate tests, touch excluded BDD, or add old-record fallback. Check live vs replay equivalence, provider ordinal/missing-ID failures, retry initial-reference identity, complete query/attempt readback, and the prior failing operator artifact preflight. Then run Ruff, mypy, and the full feasible detour suite before claiming readiness.

### 7. Secondary query JSON codec — separate two-column storage settled; no source edits
Store already has the fully linked outcome object while projecting `/completed`. The two private JSON-only models below encode and decode it. Their storage is **codex_run_outcome_records(run_outcome_record_id PRIMARY KEY, serialized_json)**, one snapshot per outcome record ID; a duplicate key is a fatal detour projection error, never an upsert/ignore. The former proposal to put the snapshot in codex_output_rows and materialize it into codex_innerdicts is withdrawn. Store serializes its DB-readback reconstructed RunOutcomeResponseRecord with its byref attempt graph through `_RunOutcomeResponseRecordJson.from_run_outcome_response_record(outcome).model_dump_json()`, not through the lean record-level `outcome.serialize()`. Rebuilding DuckDB from the replay log must regenerate the table using that same projection. The existing outcome ID in codex_output_rows links card rows to the snapshot for query.

**Existing pieces to reuse:** Store's outcome projection and `_codex_innerdicts`, the concrete pull/push/commit/validation/outcome constructors, the CodexInnerDict JSON handoff, and `QueryResponseRecord.from_query_request`. What is missing is a **complete, typed secondary JSON representation** of the outcome's referenced validation records. The current stored snapshot contains validation envelopes but relies on full commit/provider envelopes currently embedded inside them.

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

Full copies belong only in the **separate secondary DuckDB table and query representation**, while `/validate` and `/completed` replay-log lines stay lean and codex_innerdicts remains card-only. `RunOutcomeResponseRecord.serialize/from_serialized_json` must mean the record's replay-log JSON. No old-record fallback or dual-format handling. Source edits remain paused by the operator's earlier direction.


## Operator-retained exact items 1–3

The operator directed that items 1 and 2 be recorded exactly, and explicitly approved item 3 within the exact supplied shape. These snippets supersede the corresponding open gaps above. No source edits have yet been made for this serialization review.

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

## Settled items 4–5 — not yet implemented

### 4. Keep the persisted researcher-card innerdict plain and card-only

Operator clarification: `CODEX_INNERDICT_TABLE` must have the same plain-innerdict meaning as XLSX/DOCX innerdict tables: its JSONL contains only flat researcher-card key/value data. The full run-outcome response snapshot needed for query construction belongs in **codex_run_outcome_records(run_outcome_record_id PRIMARY KEY, serialized_json)**, not in the innerdict table or repeated in each output row. Current source does **not** satisfy this: `_apply_run_outcome_record` writes `outcome.serialize()` to `KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_RECORD_COL` in `CODEX_OUTPUT_ROWS_TABLE`; `_replace_codex_output_view` includes that column (and session metadata); the common materializer copies both into `CODEX_INNERDICT_TABLE` JSONL; `_codex_innerdicts` reads the snapshot from that JSONL. XLSX/DOCX and Codex innerdict tables share the two-column `(KTP_NAMEKEY_COL, KTP_INNERDICT_JSONLINES_COL)` schema, but the Codex JSONL payload is presently polluted. Section 7's same-column storage snippets and the previous filter-on-read item 4 are withdrawn. Points 2 and 3 are settled above; no copied legacy cycle guard. No source edits authorized yet.

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

Because session metadata no longer belongs to card data, replace only that portion of `CodexInnerDict.validate_codex_innerdict`. Store must read session metadata from its `codex_output_rows` staging row and the outcome snapshot from `codex_run_outcome_records`, then verify the metadata against the outcome request; exact readback SQL remains to be specified:

~~~python
session_id = outcome._codex_session_record().session_id
if session_id is None or session_id != outcome.run_outcome_request_record.session_id:
    raise ValueError(Locale.INNERDICT_OUTCOME_MISMATCH)
~~~

Items 4–5 reflect settled design, not completed source changes. Section 7's JSON-only snapshot construction/reconstruction and separate-table boundary govern the implementation; exact SQL wiring is mechanical. Source edits remain paused by the operator's earlier direction.
