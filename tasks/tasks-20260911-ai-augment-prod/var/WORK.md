# AI augment production preparation

## Status and authorization

2026-09-22: REVIEW ONLY. Operator rejects the foundation-only G1 proposal because it
leaves compensatory representations intact. Latest request: select ONE data-model purge
contour and argue the concrete changes from current architecture.py. No implementation
approved. G1 is withdrawn; its patch/snippets are removed from active WORK. The combined
two-commit inventory remains reference, not an approved implementation plan. Preserve
operator staging/edits and signed comments. Do not restore earlier rejected broad proposals.

TASK reread. Comparison is 1824770^ (fe9cd31) -> a17256a, architecture.py only, treating
1824770 and a17256a as ONE change. Operator establishes pre-change implementation as the
working/test-passing baseline. Do not introduce unrelated repairs or reinterpret omitted
nonessential protocol members as orders to delete concrete methods/fields. Entire combined
diff read (356 insertions/500 deletions), current architecture already read end to end.
No source implementation or fresh test result; only source/history reads and WORK maintenance.

## P37 — architecture review; commit reconstruction purge proposed, NOT APPROVED

Abbreviations below: B=BackendComponent, A=AgentRuntimeComponent, C=ControlCentreComponent.
The inventory describes the combined architectural diff, not proposed extra behavior.

### Complete combined change inventory

1. B.AiAugmentHttpRequestLogRecordProperty added with http_request_log_record, keyword-only
   from_http_request_log_record(*, http_request_log_record), from_serialized_json(*, value:str),
   serialize()->dict[str,object]. B.RequestRecordProperty/ResponseRecordProperty inherit it.
2. PullResponseRecordProperty no longer specifies pull_response_body; PullRequest remains
   empty-specific. Both still inherit their common record contracts.
3. PushRequestRecordProperty no longer specifies pull_record_id/session_id.
4. PushResponseRecordProperty no longer specifies commit_record/validation_record.
5. CommitRecordProperty becomes CommitRequestRecordProperty; commit_request_body remains,
   common interface inherited; specialized validate_commit_record/resolver-taking factory
   no longer declared.
6. CommitRequestBodyProperty keeps pull/push/session objects but omits validate_complete_commit,
   validate_serialized_json, resolver-taking from_serialized_json and serialize.
7. ValidationRecordProperty becomes ValidationRequestRecordProperty, inheriting common record
   interface. Specialized validation_request_body/validate_record/factory declarations omitted;
   docstring specifies lossless whole-attempt meaning and no Agent wire exposure.
8. PostCommitValidationProperty omits validate_lifecycle; its five data properties unchanged.
9. ValidationRequestBodyProperty omits validate_body, retargets commit/initial validation to
   request-record names, adds body docstring; captured-input members otherwise unchanged.
10. Backend Lifecycle omits is_post_commit_validation_stage/result; value literals unchanged.
11. CodexRolloutRecordProperty, AppendwatchReportEncodingProperty, AppendwatchReportRecordProperty
    move from B.AgentRuntimePort directly to B. Session/encoding references follow. Report
    contract omits validate_canonical_base64/decoded_bytes; other members/bases unchanged.
12. B.ControlCentrePort.CommittedInnerDictProperty becomes B.CodexInnerDictProperty; documents
    completed outcome+InnerDict; omits independent commit_record; outcome type is C.BackendPort;
    validator is validate_codex_innerdict. Marker base is component-property rather than
    port-property. Text/innerdict/serialization remain.
13. AiAugmentSingularOuterDictProperty moves from B.ControlCentrePort to B;
    committed_innerdicts becomes codex_innerdicts typed with CodexInnerDictProperty; adds
    ultimate augmented-card docstring; marker base becomes component-property. Other
    data/methods unchanged.
14. A.AttemptProperty becomes A.BackendPort.AttemptProperty, inheriting B.ValidationRequestRecordProperty
    instead of declaring separate pull/commit/post-commit-result members.
15. B.AgentRuntimePort.AttemptRecordProperty becomes A.BackendPort.AttemptRecordProperty and
    inherits AttemptProperty. Keeps attempt/submission/ground_truth_innerdict. Separate nullable
    validation_record and procedure-taking deserializer declarations disappear; common
    conversion/serialization inherited. Added docstring explains richer view of validation.
16. Backend QueryRequestProperty (empty client request) and QueryRequestRecordProperty give
    way to one C.BackendPort.QueryRequestRecordProperty inheriting B.RequestRecordProperty.
17. Backend QueryResponseProperty (attempts/researchers/outcomes body) and QueryResponseRecordProperty
    (query_response_body accessor) give way to one C.BackendPort.QueryResponseRecordProperty:
    inherited response-record contract plus direct researcher collection only. Custom body
    deserializer/serializer no longer declared separately.
18. Backend RunOutcomeRequestProperty/client and RunOutcomeRequestRecordProperty/captured-input
    contracts give way to C.BackendPort.RunOutcomeRequestRecordProperty. Essential members:
    namekey,session_id,backend_validation_record(nullable FULL validation),run_outcome(narrow
    port outcome). Inherits request-record contract. No separate pull/push IDs/final session
    capture/rollout filename; validation UUID property is replaced by full-record property.
    Custom transport factories/validator/path narrowing no longer declared separately.
19. RunOutcomeResponseRecordProperty belongs to C.BackendPort, inherits common response record;
    run_outcome_request_record replaces run_outcome_request, direct attempt is added; requested
    run_outcome stays C.LifecycleProperty. Body accessor and specialized validator/factory
    declarations absent; common conversion applies.
20. RunOutcomeResponseBodyProperty is absent: its independent pull/push/commit/validation/self
    IDs, session snapshot and body serialization are not the essential outcome contract.
21. Store query and outcome signatures use C.BackendPort request/response protocols directly;
    current commit/current validation/initial validation use new request-record names. Pull,
    push, current raw pull/push, four-operation shape, ACK/NAK and result tuple unchanged.
22. Backend Context adds backend_store:FullStore|QueryOnlyStore. Its source-researcher factory,
    collection and configured-researcher method are omitted; config/configured_namekey remain.
23. C.BackendPort.RunOutcomePathProperty becomes RunOutcomeProperty with values
    completed/failed/cancelled, from_url_path(Literal paths), to_url_path PROPERTY returning
    those paths. Semantic value separated from URL representation.
24. C.Lifecycle to_run_outcome_path/from_run_outcome_path(str) become to_run_outcome and
    from_run_outcome(port outcome). is_run_outcome and lifecycle literals unchanged.
25. RunEvent essential members are run_id,time,lifecycle,detail; namekey,session_id,
    rollout_jsonl,remote_pid,accepted_commit_record_id,codex_exit_code,occurred_at omitted.
26. Run adds essential session_id/remote_pid; events changes property->method; run_outcome/
    attempts omitted; run_outcome_record references C.BackendPort response. Other essentials stay.
27. B.AgentRuntimePort and B.ControlCentrePort are descriptive empty counterparts; A.BackendPort
    is introduced. Ownership/connector docstrings explain nested-Python placement and trusted
    Control Centre versus non-authoritative Agent Runtime.
28. Sections/comments/formatting reorganized; unused Callable/datetime/PurePosixPath/
    MatchingProcedure imports absent. Exception/acknowledgment protocols gain docstrings only;
    promise behavior/signatures/result alias not changed independently of inherited record base.

### Logical groups, in implementation-review order

G1 Common record-conversion foundation:1; downstream promise-bound implication from21/28.
G2 Backend concrete records and lower-level inputs:2-11.
G3 Validation-based Agent port views:14-15.
G4 Single IPC record family and semantic outcomes:16-20,23-24, related21/27 ownership.
G5 Researcher/innerdict handoff:12-13.
G6 Runtime capability and local Run/events:22,25-26, remaining21 consumers.
G7 Documentation/import-only bookkeeping:28 and explanatory parts of27.

Groups express dependencies, not permission to implement them. Omitted essentials may remain
as useful concrete members; they must not bypass/duplicate declared authoritative transitions.

### Selected purge contour — self-contained commit reconstruction; REVIEW ONLY

Operator asks for one concrete model-file purge argued from the current architecture.
Selected commit_event.py plus its DIRECT representation consumers, not a common-superclass
rollout or a full outcome/Attempt/Dashboard redesign. No implementation authorization inferred.
Test code can be omitted from review snippets but remains required during any implementation.

Architectural reason: CommitRequestRecordProperty inherits the common factory accepting ONLY
http_request_log_record; its commit_request_body exposes actual pull_record/push_record/session.
Current commit HTTP body serializes only pull/push UUIDs; its factory needs resolve_http_record.
Therefore those bytes cannot independently reconstruct the declared object. A signature rename
cannot fix the missing information. Proposed concrete current-format change: commit request_body
contains the full existing CommitRequestBody's typed pull/push/session data, not UUID substitutes.
This changes the commit-body format, not shared HTTP-log v1.1 or synthetic null response fields.
README162 still specifies UUID-only commit body; it must be explicitly aligned if this scope
is approved. No old parser, fallback or migration. Exact serialized session spelling must be
pinned in the eventual patch; do not silently change the distinct outcome snapshot codec.

Purge:
- _CommitRequestBodyJson's separate ID-only representation; its validation-only pass and
  resolver-taking deserializer/serializer round trip. Keep CommitRequestBody and its actual
  completeness validation; standard model serialization can carry the already typed inputs.
- BackendCommitRecord.commit_request_body Field(exclude=True) as an independently supplied
  second copy. Make it a derived typed property parsed from request_body. Existing envelope
  validator additionally validates that body; remove only the equality check whose purpose
  was comparing two independently supplied copies and its temporary UUID->record resolver.
- Remove required resolve_http_record from record reconstruction; implement exact keyword-only
  factory/common conversion signatures under BackendComponent.CommitRequestRecordProperty.
- Delete _BackendCommitRecordJson in committed_innerdict.py (http_record plus independent
  pull/push/session copies). In committed_innerdict/query_response/validation_event codecs,
  carry the self-contained commit record directly and remove from_commit_record/to_commit_record
  wrapping. Do NOT redesign the remaining outer codecs or AgentRuntimeAttempt in this contour.
- _commit_request_body in api.py has NO caller anywhere in active detour Python; delete it.
  _backend_commit_record currently supplies a Store resolver; replace its callers with the
  single authoritative model factory, retaining necessary ReplayInputMissing/_PushValidationError
  translation at actual replay boundaries. No compatibility alias or duplicate reconstruction path.
- _synthetic_commit_record no longer passes commit_request_body separately: the serialized
  request_body is sufficient. Update direct constructors/factories/annotations and test fixtures.

Preserve:
- CodexSessionRecord, rollout summary, appendwatch canonical-base64 validation/decoded_bytes,
  lifecycle stage/result helpers: these still have semantic consumers despite omission from
  essential protocols. _CodexSessionRecordJson is also used by outcome serialization; do not
  delete/change it globally merely because commit no longer needs a parallel ID-only codec.
- Synthetic commit method/path/headers/null-response contract, actual UUIDs, full pull/push
  exchanges, snapshot/CAS capture, append/fsync/project/readback, ACK202 timing and retry rules.
- Store-owned persisted-input verification. _validate_projected_commit already loads _pull/_push
  and checks ordinal/routes/status. With embedded inputs, ALSO compare the embedded envelopes
  to those DB-readback records. Previously equality was implicit because the resolver supplied
  the DB objects. Removing resolution must not remove that guarantee. DB reads verify already
  reconstructed objects; they no longer provide otherwise missing construction data.
- Full tests remain implementation work: offline reconstruction/JSON equality, rejection of
  malformed body, real log/DB equality/order checks for tampered embedded pull/push, unchanged
  grouped durability/replay and dependent validation/query/innerdict round trips.

Current compensating layout verified in source:
  commit_event.py225: _CommitRequestBodyJson(pull_record_id,push_record_id,session codec)
  commit_event.py243: CommitRequestBody(actual pull,push,session)
  commit_event.py308: BackendCommitRecord(raw request_body + required excluded typed body)
  committed_innerdict.py49: _BackendCommitRecordJson(raw commit + pull,push,session copies)
  validation_event.py56/query_response.py52/committed_innerdict.py78 use that extra wrapper.

Initial outcome trace was useful but not selected for implementation: RunOutcomeResponseBody's
independent ancestry IDs are candidates for the subsequent record-chain purge, but its final
codex_session_record is FRESH rollout/report evidence and is not the commit snapshot. It must
not be deleted as supposedly duplicate data merely because the new essential protocol omits it.
Outcome request full-validation vs current empty-body/ETag transport also needs a concrete later
proposal; no implicit permission for wire changes from this commit-focused discussion.

Review only: complete commit/outcome modules and direct API/Store/IPC/codec consumers read;
no production/test/task/index edits or runtime tests. G1 proposal artifact is removed because
it is withdrawn; historical syntax/style/applicability checks do not establish implementation.
Await review of this contour, then an exact patch if requested; no claim this section is an
approved executable snippet set or that all architecture differences are resolved.

### Commit serialization ownership — proposal refinement, NOT APPROVED

Latest operator asks how ALL serialization/deserialization is owned by model methods in the
selected commit contour. Proposed ownership:
1. CommitRequestBody keeps its three existing typed fields and completeness validator. Remove
   _CommitRequestBodyJson, ID-only serialize mapping, resolver-taking decoder and _serialize
   @model_serializer. from_serialized_json(*, value) calls cls.model_validate_json(value);
   serialize() calls model_dump(mode="json"). Inherited model_dump_json emits the JSON string
   needed by the HTTP request_body. Do not decorate the model_dump-backed serialize method:
   that would recurse. Nested HTTP/session/rollout/report models own their own serialization.
2. BackendCommitRecord implements the new CommitRequestRecordProperty. Raw request_body is
   authoritative; commit_request_body becomes a property calling the body model's decoder.
   from_http_request_log_record(*, http_request_log_record) delegates to from_serialized_json
   with the shared record's model_dump_json; from_serialized_json(*, value) runs its own
   model_validate_json. Existing after-validator retains envelope checks and validates the
   derived body, without the removed independently supplied body's equality/resolver check.
   serialize() is existing HTTP envelope model_dump(mode="json"); http_request_log_record
   returns self. No derived-body @computed_field, excluded input, external resolver or DB I/O.
3. Live producer serializes CommitRequestBody with its model_dump_json; supplies that string
   to the existing synthetic envelope constructor and NO commit_request_body argument.
   This does not require a new creator service or extra factory. Raw external capture and
   header selection remain in their existing producer; data encoding belongs to models.
4. Direct consumers of _BackendCommitRecordJson instead use BackendCommitRecord typed fields;
   their enclosing models serialize/validate those nested records using the record's actual
   Pydantic schema/validators. No separate DTO reconstructs missing record contents. All named
   factory callpoints use the exact keyword-only signature; malformed data is not defaulted.

Core proposed method shapes (existing class fields/validators otherwise as described):

```python
# CommitRequestBody; remove its custom @model_serializer and ID-only codec.
@classmethod
def from_serialized_json(cls, *, value: str) -> Self:
    return cls.model_validate_json(value)

def serialize(self) -> dict[str, object]:
    return self.model_dump(mode="json")

# BackendCommitRecord; replace the excluded commit_request_body field.
@property
def commit_request_body(self) -> CommitRequestBody:
    if self.request_body is None:
        raise ValueError(Locale.COMMIT_REQUEST_BODY_MISSING)
    return CommitRequestBody.from_serialized_json(value=self.request_body)

@property
def http_request_log_record(self) -> HttpRequestLogRecord:
    return self

@classmethod
def from_http_request_log_record(
    cls, *, http_request_log_record: HttpRequestLogRecord,
) -> Self:
    return cls.from_serialized_json(value=http_request_log_record.model_dump_json())

@classmethod
def from_serialized_json(cls, *, value: str) -> Self:
    return cls.model_validate_json(value)

def serialize(self) -> dict[str, object]:
    return self.model_dump(mode="json")
```

Locale.COMMIT_REQUEST_BODY_MISSING is a proposed existing-Backend-Locale constant with the
current exact message "commit request body is missing" (not an existing constant claimed
available). Keep existing commit-envelope/completeness errors, centralized there if touched.
The existing envelope after-validator MUST parse/validate the derived body on construction;
lazy getter validation alone would be insufficient. Only the two-copy comparison disappears.

Proposed new commit body uses actual field names pull_record/push_record/codex_session_record;
nested CodexSessionRecord therefore uses session_id under normal model serialization. This
explicitly resolves the earlier unpinned session spelling for the NEW commit body. Existing
outcome body's codex_session_id codec remains untouched pending its own proposal. No alias,
legacy decoder, shared HTTP-log schema change, new transport or renamed lower-level fields.
The operator has not approved this commit-body schema or implementation yet. WORK records a
reviewable method-ownership proposal, not a completed or authorized patch. No source changes.

### Historical completion status before operator architecture/timestamp edits

2026-09-21 latest instruction: item1's EXACT two header-test/fixture edits are IMPLEMENTED
and verified:72preflight cases, Ruff and strict mypy PASS. Item2's outcome-ancestry proposal is REJECTED;
change neither production outcome selection/replay nor its existing fixture/UUID assertions.
Item3 is explicitly NO CHANGE to authentication. Earlier approved implementation through
P36 is complete except P32 global retention superseded by P35/P36 and withdrawn P33.
Latest full operator acceptance FAILED at KeyError('location'); the correction now passes
the actual upstream artifact validator. No full operator rerun or new elevate payload; no
full-run success claim. No approved implementation remains from these three items. Generic503 and
original missing-socket diagnostics remain as elected. No production/task/index changes.
TASK reread; preserve all scope constraints and operator staging.

P36's exact marker/fixture is implemented: only use_rootpath_tmp-marked tests retain their
tmp_path-derived files under rootpath/tmp; unmarked tests use pytest/system scratch. The
operator module has independent operator and use_rootpath_tmp markers. Local evidence:
72preflight +677ordinary tests, Ruff/mypy/root discovery. The latest production run now
confirms ordinary FIFO/socket/root/browser checks pass and the actual operator runtime uses
a unique retained tmp/test.v4dkxxmy directory. Original NiceGUI preservation checks pass.
P34 artifact-discovery exclusions and P35 sudo -k remain implemented. The root log shows
sudo -k and3passes but does not print a password prompt; do not claim prompt visibility.

### RunEvent / Run audit — COMPLETE; review only, no implementation approved

Historical pre-fe9cd31 source-use audit. Later removal of RunEvent and revised essential
protocols are separately reviewed above; do not read this baseline as current conformance
or authorization to remove members omitted from the new architecture.

2026-09-21 operator requests used/unused fields and redundancy, including possible reuse of
existing typed objects. Read concrete models, architecture protocols, complete reducer and
all production event constructors, storage, controller, views, Codex handles/results and
relevant tests. rg across src/tests plus AST attribute/constructor inventory distinguishes
same-named fields on other types. No production resources/model imports, source edits or
runtime tests: findings are source-use analysis, not new execution coverage. Header correction
remains complete; rejected outcome-ancestry and no-change auth decisions remain untouched.

Roles/ownership: run_event.py defines20Run fields and10RunEvent fields plus occurred_at.
RunEvent is an immutable Dashboard fact, serialized to the NiceGUI journal by
AiAugmentDashboardStorage.save_run_events. Run is a mutable reducer result reconstructed by
replay_run_events; it is NOT separately persisted. Controller._events owns the journal,
Controller._runs its per-run state. Backend query data stays in DashboardQuerySnapshot and is
joined to Run at _ResearcherView.from_snapshot by session_id. These are distinct roles; do not
merge/inherit them merely because they repeat identity/current-state values.

| Run field(s) | Actual use / finding |
|---|---|
| run_id | Active: journal/queue/map key, cancellation, owned remote paths and outcome deduplication. |
| namekey | Active: reducer identity check, grouping, Backend startup and outcome headers. Already a NameKey object. |
| lifecycle | Active: queue/running/display classification and latest-event state. |
| run_outcome | Active: terminal checks, cancellation/dequeue and displayed final state; overlap with lifecycle discussed below. |
| events | Reducer only appends; no production consumer. One test asserts tuple contents (test_ui1480). Duplicates Controller._events references, not a necessary second persisted journal. |
| attempts | Never populated/read in production; always default (). Query/view path owns actual attempts. Protocol declaration is not a consumer. |
| run_outcome_record | Never populated/read in production; always default None. _RunCommitView's separate same-named field IS used and comes from Query snapshot. |
| queued_at | Active: display ordering/timestamp when start is absent. |
| started_at | Active: display ordering/timestamp and prevents repeated STARTED event in handle callback. |
| session_id | Active: query-snapshot join and run-outcome identity header. Dashboard run_id and Codex session_id are distinct; cannot merge. |
| session_timestamp | Assigned from SESSION_DISCOVERED event; never read on Run. |
| rollout_jsonl | Assigned from ROLLOUT_DISCOVERED event; never read on Run. Remote operations use other objects/paths. |
| remote_pid | Read to avoid duplicate REMOTE_PID_DISCOVERED events; cancellation uses active handle, restart uses run-specific PID file. Not entirely unused. |
| accepted_commit_record_id | Only populated by PUSH_ACCEPTED reducer branch; current production NEVER emits that event. Nominal read in _RunCommitView.commit_record_id therefore yields None for current Dashboard-only runs; actual commit IDs come from snapshot attempts. |
| accepted_at | Only assigned in that unproduced PUSH_ACCEPTED branch; never read. |
| cancel_requested_at | Active as a non-None flag at three decisions; its timestamp value is never inspected. Journal already retains the occurrence time. |
| codex_exit_code | Assigned at CODEX_EXITED; no production reader on Run. One test asserts it (test_ui1596). Local exit variable/event journal still carry the actual value. |
| exited_at | Assigned at CODEX_EXITED; no production reader. |
| failure_detail | Syntactically read in cancellation classification, but redundant under current reducer invariants: its only setter also makes the run finished, and classification is consumed only for unfinished runs. _RunCommitView.failure_detail has no consumer. Event detail remains useful diagnostic/history data. |
| dashboard_owned | Read by restart/shutdown guards, but every production Run is constructed True; no False construction/assignment. Backend-only history creates views with run=None, not external Run objects. |

Thus8fields have no useful production read: events, attempts, run_outcome_record,
session_timestamp, rollout_jsonl, accepted_at, codex_exit_code, exited_at. Separately,
accepted_commit_record_id is dormant and dashboard_owned is constant. The other10fields have
read sites, but failure_detail's apparent control-flow use is redundant as established below.
This is not permission to remove fields/tests/protocol members automatically.

| RunEvent field/property | Actual use / finding |
|---|---|
| run_id | Journal routing/grouping, Run construction and log identity. |
| namekey | Run identity construction/check on every event and logs; repetition provides a real consistency check. |
| occurred_at_unix_usec / occurred_at | Stored scalar and computed timezone-aware datetime conversion, respectively; not duplicate persisted values. Supplies Run milestone times. |
| lifecycle | Dispatch, journal history and visible progress; CODEX_EXITED remains meaningful independently of its optional exit code. |
| session_id | Produced/consumed at SESSION_DISCOVERED. Repeated on ROLLOUT_DISCOVERED, but ignored by that reducer branch. |
| rollout_jsonl | Produced, persisted, required by rollout branch and copied to the unused Run field; currently audit data, not an operational lookup. |
| remote_pid | Produced at handle callbacks, projected and used for callback deduplication. |
| accepted_commit_record_id | No current producer. Only stale PUSH_ACCEPTED branch requires it; explicit test_ui2466 asserts no PUSH_ACCEPTED is emitted during completion. |
| codex_exit_code | Produced on CODEX_EXITED and repeated terminal event; reducer uses it ONLY on CODEX_EXITED. Persisted audit fact; duplicate terminal copy has no current reader. |
| detail | Produced for errors, persisted in the journal and logged on append; FAILED copies it to Run, whose apparent cancellation/error distinction is redundant (follow-up below). |

Redundancy/design assessment (recommendations only):
1. Clearest narrow cleanup is removing unused Run copies and never-populated Backend fields,
   not reviving reconciliation. Keep meaningful journal facts such as exit code/rollout path;
   no production read of their Run copies does not make persisted audit data worthless.
2. Remove dormant accepted fields/PUSH_ACCEPTED branch/member only as an explicitly approved
   connected cleanup (RunEvent, Run, enum, protocol, reducer and view fallback). No legacy
   reader, migration or alternative query is proposed. Actual snapshot-derived commit data stays.
3. Run.events duplicates the same journal objects already retained globally. Keep one journal
   owner. Alternatively make Run a view over its event tuple and derive fields, but that is
   a broader design choice: controller queues/active handles rely on Run object identity and
   current mutable updates. Do not silently switch to rebuilding immutable Run instances.
4. Existing RunEvent instances already contain phase-related bundles: session event has ID/
   timestamp, exit event has exit code/timestamp, FAILED event has outcome/detail/time. Keeping
   selected event references plus computed accessors can remove parallel scalars without a
   new DTO. A SINGLE latest event cannot replace all state: sparse events do not carry earlier
   session/start/cancellation data. After dead-field removal, much of the apparent grouping
   opportunity disappears, so extra containers may be unnecessary.
5. lifecycle/run_outcome overlap but are not constrained equal. Reducer unconditionally writes
   lifecycle, writes run_outcome only for terminal events, and permits nonterminal events after
   a terminal one. A computed outcome based solely on current lifecycle would change that
   behavior. Reusing a retained terminal RunEvent (outcome/detail/time) is possible, but a
   precise transition/retention policy is needed first; failure_detail is also not cleared by
   non-FAILED events. No state-machine redesign is authorized by this audit.
6. Shared RunLifecycle includes view-only READY/RUNNING plus event kinds and terminal outcomes.
   Run.run_outcome accepts the whole enum despite consumers expecting only completed/failed/
   cancelled. This is a real overly broad type; narrow terminal typing could use those enum
   members. RunEvent's optional bag permits phase-irrelevant payloads; current reducer checks
   required PID/session/path/commit values, not a discriminated payload type. Separate typed
   event payloads would be a larger proposal, not a necessary first cleanup.
7. Adjacent duplication: _CodexStartResult repeats session_id/session_timestamp/rollout_jsonl
   already assigned on its handle, then projected into Run. Handle session_id IS read for
   cancellation logging; handle timestamp/path have no readers. Its successful result's
   non-null fields are useful and used. Pruning unused handle/Run copies is simpler than
   blindly returning a still-nullable handle. A shared immutable session descriptor is an
   option only if remaining consumers justify it; Backend CodexSessionRecord is NOT that
   descriptor (CAS/appendwatch snapshot, not remote session discovery). Do not put a live
   subprocess-bearing _CodexStartResult into the persistent journal.

Model-config note: mutable Run's validate_assignment is consistent with actual reducer use.
RunEvent is already frozen, but its non-strict Python-mode validation currently rehydrates
UUID/enum/path strings from NiceGUI's JSON dictionaries. FrozenStrictModel is not a drop-in
without changing that loader boundary. No blanket BaseModel/config replacement proposed.

Potential cleanup must update the exact affected component protocol members and direct tests;
no casts, compatibility aliases, storage migration, Backend query/schema change or revival of
rejected outcome-reference work. Audit complete; wait for a concrete implementation approval.

### Detail follow-up — COMPLETE; review only

Operator asks about keeping events inside Run versus dropping them and persisting mutable Run,
then requests all detail uses/necessity/optimization. Direct Run persistence was discussed as
an option, NOT approved: it would replace journal replay and lose intermediate history, while
the Backend query snapshot remains separate. No model/storage/controller change authorized.

Static trace of RunEvent.detail and Run.failure_detail (not Backend validation detail):

| Producer in ui.py | Recorded text |
|---|---|
| start:1980 | Locale.RESTART_INTERRUPTED_RUN for an interrupted owned run on restart. |
| shutdown:2012 | Locale.SHUTDOWN_INTERRUPTED_RUN for an unfinished run at shutdown. |
| cancel:2087 | Locale.CODEX_CANCEL_FAILED_TEMPLATE with cancellation exception text. |
| _process_queued_run:2325 | str(exc) for an unfinished, noncancelled failure; None for cancellation. |
| Same method:2343 | Locale.RUN_PROCESS_CLEANUP_FAILED_TEMPLATE with cleanup exception text. |

All five populated paths produce FAILED events. Other current events leave detail=None;
ordinary final-pull classification at2456 also leaves it None even when FAILED.

Complete consumers/retention:
1. Storage.save_run_events serializes detail in each event; load_run_events rehydrates it.
   Controller._events and Run.events retain event references; Run is not separately saved.
2. apply_run_event:1125 copies it to Run.failure_detail ONLY for FAILED, in the same
   synchronous branch that sets run_outcome=FAILED. Replay uses this same reducer.
3. _append_run_event:2559/2566 emits it in operator logs: nonfailure empty text versus
   failure 'unspecified' when absent/empty. Operator raise_for_dashboard_failure includes
   the whole failed-run line in its exception; it does not parse the detail value.
4. _process_queued_run:2310 checks failure_detail is None when computing cancelled, but
   uses that result only inside if not run.is_finished(). Only reducer constructs production
   Run; failure_detail starts None; its only setter first sets a terminal run_outcome, which
   no production code clears. Therefore every unfinished run already has failure_detail=None.
   No await separates this check and guard. This corrects the earlier audit's assertion that
   the presence check actually distinguishes reachable cancellation/failure states.
5. _RunCommitView.failure_detail:531 exposes Backend validation detail or the Run copy,
   but has NO caller, computed-field serializer or table binding. Not shown in UI/cards and
   not sent in outcome IPC. Backend PostCommitValidation.detail and session-status error
   formatting are distinct fields/uses, not consumers of Dashboard event detail.
6. test_failed_run_events_are_logged checks its exact emitted text; operator preflight's
   test_operator_failure_includes_captured_backend_reason checks summary-plus-Backend logs.
   Generic journal roundtrip retains it, not an additional business decision.

Recommendation only: preserve diagnostic text; remove the dead view getter and redundant
cancellation operand if separately authorized. Then Run.failure_detail's derived copy has
no functional reader while journal remains. If the operator instead chooses persisted Run
without events, one stored failure_detail would retain the latest reason (not full history).
Text must not encode control state. No new flag/type, Backend query or schema change proposed.
Review performed by rg/full relevant source reads, without imports/runtime tests/source edits.

### Latest full operator review — 2026-09-21; workflow complete, harness FAILED

User initially requested only pre-commit.log, then explicitly added pre-commit-extra.log
and tmp/test.v4dkxxmy. Reviewed only those current logs/bundle plus source; no unrelated
captures or original host resources. Raw LF line references below (not universal-newline
conversion, which adds lines for terminal CRs). Files: pre-commit.log485213bytes/3689LF;
pre-commit-extra.log836120bytes/4970LF. No Ctrl+C/KeyboardInterrupt/test timeout in either.

| Leaf | Actual result |
|---|---|
| Ruff/default mypy/AI strict mypy | PASS;68/55source files |
| Main |174passed5skipped6xfailed1documented XPASS4.35s |
| Step4 |4passed1skip2.33s; slow leaf1skip4deselected0.24s (configured parquet resources unavailable) |
| Mode3 |6passed1.14s |
| Mode0 |4passed11existing Plotly/Kaleido deprecation warnings2.46s |
| AI ordinary + preflight, aicode |755passed1existing skip3root deselected147.27s; previously failing FIFO/socket cases and root-discovery regressions pass |
| Real OpenAlex/ROR institution model |1passed0.80s; ordinary task's && reached this leaf |
| Host Chrome module |9passed34.70s, including real query/card/synthetic DOCX; guest and host script status0 |
| Main real API |3passed182deselected1expected xfail2.75s |
| Privileged appendwatch |3passed70deselected3.64s; guest script status0 |
| Live operator |1failed2intentional excluded-case skips273.26s; host status1 |

Severity-message investigation:
- pre-commit.log has133ERROR,28WARNING,1CRITICAL log entries, ALL under passing tests'
  captured-log sections. Existing -srA includes -rA, which displays these even for passes;
  stdout capture and pytest logging capture are separate. No severity suppression proposed.
-104errors are the explicit outcome matrix (LF2198–2441): deliberately missing/wrong
  NameKey/Session-ID/ETag, body/query/SourceKey rejection and injected unavailable rollout.
  Tests verify durable error history and live/replay equality, not success for invalid input.
-Remaining errors exercise injected validation/projection/fsync/completion failures, invalid
  replay lines, invalid workflow states/ETags, failed IPC/startup/cleanup/snapshot replacement
  and DOCX rendering failure. Traces point into deliberate test raises/fixtures. Sole CRITICAL
  LF2497 is test_background_commit_failure_exits_backend: its FailedTask returns
  RuntimeError('commit failed'), and the test verifies fatal exit1 without killing pytest.
-28warnings exercise rejected evidence/retry baseline, missing initial pull, malformed
  submission and duplicate already-accepted fragments. Repeated live evaluation, authoritative
  validation application and explicit replay re-log those rejections. Tests of first/current
  validation state intentionally reuse the same fragment. No new persistence failure inferred.
-Mode0's11DeprecationWarnings are separate: legacy Kaleido defaults/old Kaleido API/setDaemon.
  Existing dependency warnings, all Mode0 tests pass; outside this detour's correction scope.
-Extra log has6REAL Codex-client ERRORs at LF169–192: expired authentication token causes
  two model-list401s, two MCP transport401s and two Responses-WebSocket401s. Not test injections
  or Backend HTTP errors. Preflight only checks codex login status exit0 (plugin185–203),
  which cannot establish live endpoint authorization. Codex subsequently performs research,
  submits twice and exits0. Log does NOT establish whether refresh/retry/transport selection
  resolved the authorization; do not invent that mechanism or claim all MCP tools recovered.
-Extra log's2Backend WARNINGs (LF1523,1543, interleaved into long evidence lines) are the SAME
  first rejected push, logged at evaluation and persisted-input application. Actual mismatch:
  social_capital.web_search_excerpts[0] says 'he is a highly cited author, ...'; captured HMC
  sentence instead has '... in excess of £200M, is a highly cited author, ...'. Exact contiguous
  match fails:26/27. Retry fixes it and all27match. One rejected validation, not two failures.
  Long full-candidate log output interleaves prefixes; a genuine readability issue, not a new
  validation/persistence failure. No logging refactor approved by this review.

Actual failure, current producer and missed upstream boundary:
-At the failed run, extra LF4947 / test_operator_e2e.py:1138 indexed a plain stored dict with ['location'].
  BOTH real accepted push records have {'Location': '/pull', 'Content-Length': '0'}.
  Backend api._response uses LOCATION_HEADER='Location'; _authoritative_http_record captures
  dict(response.headers) BEFORE ASGI transport. Curl's lowercased wire header at LF1096/3565
  does not imply the persisted Requests-side envelope has lowercase keys. HTTP header names
  are case-insensitive; the test's dictionary assumption is wrong, not a missing Location.
-At the failed run, P31's synthetic completed-query fixture used LOCATION_HEADER.lower() (plugin803).
  Therefore both upstream artifact-validator and Chrome helper tests passed with the same
  lowercase assumption. This is a missed Assistant test-fidelity defect, not a required
  production header/serialization change or an unavailable-browser explanation.
-Header diagnostic executed actual api._response/_authoritative_http_record plus typed copies
  of both supplied live pushes, through isolated pytest/pre-import NiceGUI protection; no
  network/serving/Store writes. Reproduces KeyError and proves existing _http_header_value
  handles Location/location/LOCATION:4passed0.88s. Initial diagnostic had1pass/3fail because
  Python-mode strict UUID validation was mistakenly used for JSON dict input; corrected to
  model_validate_json, no model relaxation or production edit. Temporary module removed.
  This is NOT a full artifact-validator pass or acceptance run.

Lifecycle, timing and retained files:
-Guest normal run11:18:40–11:21:42; Chrome finishes11:22:18; extra guest completes11:22:25.
  Host operator wrapper11:22:25–12:06:56, but pytest reports273.26s (~4m33), and actual
  Dashboard run queued12:02:35.746 -> completed12:06:45.924 (~250s). Approximately40minutes
  occur outside the timed pytest session. The redeploy prompt is before session start;
  untimestamped prompt/preflight output cannot prove where that interval was spent. Do NOT
  label it a40minute Backend/Codex hang or assume the operator caused it.
-Research accounts for heartbeats with2records through171s, first push around180s, second
  around239s; no500pull. Final pull410 and completed200 materialize1section (LF4755–4771).
  Full Backend42631: clean token, exit-15, clean_close_ack=True, forced_kill=False,
  shutdown_succeeded=True. IPC-only42609/43503 both clean exit0. Post-run query307researchers/
  2attempts/1outcome; actual card displayed/captured; Dashboard42583 and resource tracker42588
  exit normally. Artifact assertion fails AFTER cleanup. No Playwright teardown warnings.
-Expected absent-socket polls and one transient ConnectionRefused at LF116 resolve to readiness.
  They are not failed Query requests; unchanged operator-approved startup behavior.
-Run directory retained/logged as tmp/test.v4dkxxmy, including replay/DB/CAS/config/private
  NiceGUI. No global basetemp retention. Host ordinary browser data instead uses native
  pytest scratch with short /tmp/q.* sockets. Original data/NiceGUI preservation guard passes.

Read-only audit of supplied tmp/test.v4dkxxmy:
-12LF-terminated valid typed HTTP records,342140bytes, replay SHA256
  c4d5d009b355bf8438bdb215932784760150e9135ef75e549c6567071525bf7b.
  Every DB ordinal/UUID/method/path/full JSON envelope/LF-inclusive hash matches exactly.
  Readonly DuckDB; whole-file hash unchanged after each read. No source symlink followed,
  no saved-config resource construction, replay/network/provider call or artifact mutation.
-Sequence:pull200,pull200,push202,commit,validate(rejected),pull200,push202,commit,
  validate(accepted),pull410,pull410,completed200.2attempts,1materialized innerdict. Embedded
  commit/pull/push/initial-validation inputs match prior records in order; final outcome
  references final410/current push/accepted commit+validation/self, with matching Session-ID/
  ETag. That final410 reference matches the current implementation but is INCORRECT under the
  ancestry expectation raised in review. The proposed correction was subsequently REJECTED;
  this observation is not an implementation instruction. Initial-validation ancestry
  correctly points to the rejected first validation.
-All3extensionless CAS blobs match SHA256/shards/size; each is referenced. No missing or
  orphan blob. Both validations have no provider captures; accepted submission has7institution
  objects, all OpenAlex/ROR IDs NR/NR, consistent with no provider HTTP inputs. Table-comment
  anchor remains empty prefix0/0, consistent with
  a fresh --new lifetime; subsequent readonly verification does not promote it.
-NiceGUI has307researchers,2attempts,1outcome,7events ending Codex exit0/completed, empty queue.
  Stored committed innerdict matches DB plus its separate namekey, its complete outcome
  matches the replay envelope, and its commit DTO matches the actual persisted records.
  This supplies substantial independent consistency evidence, not proof of checks never
  reached by the failed validator. Its later CAS/outcome/full rendered-card assertions did
  NOT execute; no raw captured card-text file is included in this bundle.

### Follow-up assertion audit — 2026-09-21

Operator asks whether replacing location with Location passes and whether similar assertions
were missed. Yes for BOTH saved real push records, but merely changing that literal would
break the lowercase synthetic fixture. Existing case-insensitive lookup plus producer-cased
fixture are now explicitly approved below. Reviewed all direct header accesses/assertions in the operator module
and its preflight helper: this is the ONLY direct header-dictionary subscript. NameKey,
SourceKey and ETag already use _http_header_value; no second equivalent casing defect found.
Reviewed the remaining ordering/identity/CAS/outcome/card and browser/cleanup/preservation
checks against producers and current captured evidence.

Executed the EXACT original statement block following the bad assertion up to (excluding)
the browser card_text block against the supplied saved records/CAS, with real parsed typed
records and accepted-commit selection from readonly DB:1passed3.91s. Temporary isolated
pytest loaded that unchanged AST block; it did NOT invoke Store/config initialization,
mock persistence, alter an assertion or change artifacts. DB hash unchanged, temporary module
removed. All remaining nonbrowser artifact assertions pass for this run, including CAS
size/hash/line count, outcome UUID/session/ETag/SourceKey, ordering and appendwatch parsing.
Those unchanged assertions explicitly expect the latest pull; their pass does NOT establish
correct commit ancestry. The user's concern remains recorded, but the proposed ancestry
correction is rejected and the existing UUID assertions are outside the approved change.
This is deliberately a tail-block forensic check, not a full operator invocation or live
replay. Exact captured browser inner_text was not retained, so its final complete rendered-
card comparison remains unverified against this run. Earlier browser capture assertions and
cleanup/preservation passed in the actual run; no new production/test/task changes.

### Approved narrow header-test correction — COMPLETE, locally verified

Only existing operator artifact test, its completed-query fixture and corresponding preflight
coverage; no production, HttpRequestLogRecord, task, timeout, casing normalization or fallback.
Reuse the case-insensitive helper already used by the rest of the artifact validator:

```python
# test_operator_e2e.py; replace ONLY the faulty header assertion:
assert backend_api._http_header_value(
    push_record.response_headers, backend_api.LOCATION_HEADER,
) == PULL_PATH

# pytest_plugin.py completed-query fixture; match actual producer casing:
response_headers={LOCATION_HEADER: PULL_PATH},
```

Latest operator approval is ONLY the exact two edits above. No additional permanent test
body/helper/refactor is authorized. The existing full synthetic artifact-validator test now
provides upstream coverage with producer-cased headers. Verification sequence: change fixture
first to reproduce KeyError through that actual validator, then apply the exact assertion
and run the affected preflight module plus Ruff/strict mypy. The prior four-case diagnostic
already covers actual response capture and header case variants; no fresh live Codex/browser
run is needed to reproduce this dictionary lookup. Preserve every other assertion/timeout.

Reproduction: after changing ONLY fixture header spelling, the unchanged actual artifact
validator fails exactly at ['location']:1failed18.94s. Real synthetic Store/replay/DB/CAS,
isolated NiceGUI and normal fixture startup; no socket/provider/live-Codex call. Applied the
exact approved helper assertion next. The full affected preflight module then passed:
72passed85.83s, no skips or warnings. This includes the actual synthetic Store/log/DB/CAS
artifact validator and retained header/UUID/order/CAS assertions, not a replacement validator.
Ruff PASS and configured strict mypy PASS2changed files; diff whitespace PASS. The prior
four-case header diagnostic is separate evidence, not a rerun in this implementation.

Final code diff is exactly the approved assertion replacement (one line -> three) and removal
of .lower() in the fixture (one line). No other existing test, permanent test addition,
production source, HTTP schema, outcome reference/assertion, auth, task, dependency or index
change. WORK records completion and rejection/no-change decisions. Browser/live-Codex/root/
provider checks were not rerun; this test-only correction is locally complete, not a new full
operator acceptance result. Existing real browser fixture consumes the same corrected data.

### Outcome ancestry proposal — REJECTED; no implementation

The user rejected item2 in full. Removed its proposed implementation/test snippets so they
cannot be mistaken for pending approved work. Do NOT derive outcome pull/push from commit,
add the proposed replay equality check, alter the fixture's final410 reference, or replace
P31's latest-record assertions. No API/IPC/Store/protocol/saved-artifact change is authorized.

Retain the read-only finding for discussion, not as a pending correction: outcome
01a0c4b8-42a3-75f4-abd2-49639cca13c3 references pull01a0c4b8-426a-73bd-b0e9-c1202a5b5c8b
(line11, Dashboard410), whereas its commit01a0c4b8-1cec-77cb-8449-0b03b1d0ec7f references
pull01a0c4b7-42dc-73f6-b3d8-298111a6a2d7 (line6, retry200). Store advances the current pull
on each projected exchange; IPC captures it and the outcome copies it. The existing verifier
and operator assertions accept that latest-record relationship. Rejection of the proposed
patch does not itself resolve the operator's semantic concern or authorize an alternative.

### Authentication follow-up — operator confirmed NO CHANGE

Confirmed operator contour: active completed test has requires_codex_auth; its autouse
production_data_unchanged depends on operator_aivm, which calls _ensure_codex_is_authenticated
before the test body/Dashboard/Codex session. Actual command is limactl shell --workdir=/ aivm
sudo --user ai --set-home /home/ai/.local/bin/codex login status. Plugin185–203 checks exit0,
discards stdout/stderr and enforces the existing probe timeout. Extra log LF70–72 records
successful auth preflight before actual session startup and LF169+ expired-token401 errors.
The run subsequently completes; the exact recovery/refresh mechanism is NOT established.
An exit0 login-status probe is not proof every later remote endpoint will authorize a call.
No credential reset, forced login, added network probe, retry policy or log suppression proposed
for this recovered incident.

Important production distinction: Dashboard._CodexRunner.probe_auth runs login status only
from explicit probe_all (ui2159). _wait_until_codex_idle checks busy state; _execute_run starts
Backend then _CodexRunner.start directly. That start prepares remote paths and executes Codex;
its shell template contains no login-status check. Thus operator preflight DOES precede this
session, but ordinary Dashboard does NOT automatically recheck authentication before every
queued session. No auth-gate implementation authorization inferred from this question.

### Latest elevate review — 2026-09-21; P32 PASS, retained artifacts verified

Operator supplied the complete logs/from_operator/elevate.lBbiaK bundle. Read its195-line,
22178-byte elevate.log in full plus status0 and relevant retained synthetic files. No original
host paths followed or production resources constructed; supplied detour DB opened READ ONLY,
whole-file bytes checked unchanged afterward. No artifact or symlink edits.

- Exact two intended nodes and --test-artifacts-root are visible in captured argv (lines1–5).
  macOS Python3.14.2/pytest9.1.1 runs the real Chrome completed-query/card/artifact case and
  real retained-operator-directory case:2passed9.83s (lines167–170), Pytest exit0; saved status
  also0. No test failure, warning summary, traceback, command-not-found, timeout or Ctrl+C.
  Captured log does not contain the OUTER wrapper exit code/grep output; do not invent it.
- Both explicit Query phases succeed: IPC-only Backend PIDs34804/34821 return307researchers,
  1attempt/1outcome; each closes Store cleanly, exits0, clean_close_ack=True, forced_kill=False,
  shutdown_succeeded=True before the Dashboard snapshot replacement. Dashboard34773 exits0;
  resource-tracker descendant34774 exits gracefully. No abnormal wait or forced fallback kill.
  Two queries are intentional: original grid assertion, then the separate approved real card
  capture helper. There is no hidden automatic query introduced by these tests.
- Fifteen missing-socket diagnostics (8 then7) resolve into OPTIONS200 readiness. These are
  the existing discovery/startup polling messages the operator elected to retain, not a new
  missing-file failure. Repeated six-line suffix verification is expected: IPC-only verifies
  against the empty anchor without promoting it. No incorrect prefix-line logging/recovery.
- Retention is now proven, not merely claimed: all24 files in the captured final inventory
  exist in the supplied bundle, plus its log/status (26regular files). Reserved nicegui/t/pytest
  and q.14e7kje1 directories remain. Two distinct operator-test.chugb10j/q2l53o8y directories
  retain config/initialized DB/empty replay; synthetic repository/source remain under pytest.
  Socket files are absent after normal unlink, as intended. Copied absolute source/current
  symlinks still name the original macOS run root; inspected link text only, no following or
  relocation/migration. They are not evidence of missing original fixture data.
- Browser fixture retains config/source/detour DB/replay/CAS/private NiceGUI and7293-byte
  card-rendered.txt, not just footer buttons. Actual browser helper's full card/workflow
  validator passed before shutdown. Independent read-only review: six LF records
  pull200 -> push202 -> commit -> validate -> pull410 -> completed200 exactly match DB
  UUIDs/envelopes/ordinals and LF-inclusive line hashes; one finalized innerdict carries the
  outcome envelope. Replay SHA256 matches the hash shown by startup verification. The sole
  extensionless CAS blob's SHA256/shards match. Private NiceGUI retains307researchers,
  1attempt/1outcome and an empty queue; card contains linked commit/validation/outcome IDs.

Rechecked current pre-commit-operator graph: aicode nonbrowser/default/provider/root leaves,
host Chrome then live operator; routing/commands untouched. P33 independently passed its
changed HTTP-message boundary locally before the operator withdrew that change. That review supported the then-issued full-run recommendation, which is NOW WITHDRAWN
after the operator exposed P34 below. The two passing targeted tests did not cover retained
fixture rediscovery by a subsequent repository-wide run. No further elevate requested yet. Full live-Codex/provider/root acceptance was NOT rerun in this two-test batch.
At that review elevate held the approved P32 batch. Current read-only inspection finds it
restored to the idle "Nothing to elevate" scaffolding; P34 leaves every task unchanged.

### Prior elevate review — 2026-09-20; invocation/retention defects corrected by P32

Operator supplied logs/from_operator/elevate.log (127108bytes,mtime13:42UTC). Read this log
and current code only; operator reports no recovered test data. Do not search unrelated
system/production directories for it. At this log review the checked-in elevate was the idle task,
and the supplied log does not contain the executed command, wrapper status or retained-root
banner. Therefore do not claim the exact proposed two-node wrapper was what actually ran.

- macOS Python3.14:227passed110.32s, consisting of audit_read12, UI206 and UI-E2E9.
  The real completed-query/card helper and full artifact validator pass, including both
  IPC-only children32187/32204 clean Store closure/exit0, no forced kill; Dashboard32167
  exits0 and its resource-tracker descendant exits gracefully. No timeout/interruption or
  warning summary. Other logged ERROR tracebacks are passing negative-path tests, not failures.
- Final two log lines are shell errors: test_ui_e2e.py::test_completed_grid_row_uses_real_query_ipc
  and test_operator_e2e_preflight.py::test_operator_run_directories_are_unique_retained_and_contained
  were executed as standalone commands and are not found. The browser node passed within the
  broader suite; the retained-directory preflight node was NOT collected/executed. The log
  shows argument/command separation, but cannot identify the exact shell edit that caused it.
  At that checkpoint there was no aggregate success claim or full-run recommendation.
- Browser DB/log/CAS/config/NiceGUI fixtures live under the logged system pytest-78/
  test_completed_grid_row_uses_r0 directory, not an elevate directory. This is separate from
  production NiceGUI storage; no production-contamination finding is established by this log.
  Source/config paths and isolated NiceGUI path are logged, but no retained artifact root.
- Assistant proposal defect: ELEVATE_RUN_DIR owned only the status file. Pytest received no
  --basetemp, so its actual durable test files remained in system temp; the root banner was
  printed BEFORE script started recording. Retention and discoverability were not wired in.
  The earlier claim about retained temporary files applied only to wrapper status, not data.
- Separate deliberate cleanup: the browser socket uses /tmp/query-browser-* TemporaryDirectory
  (socket removed normally), and the directory self-test uses repo/tmp/p.* TemporaryDirectory
  around its synthetic repository. It asserts retention across operator-fixture closure but
  then deletes its own outer fixture. --basetemp does not preserve either of these explicit
  TemporaryDirectory trees, nor collection-only NiceGUI scratch. Do NOT promise otherwise.
  The completed browser fixture's durable config/DB/log/CAS/child-NiceGUI data DO derive from
  tmp_path and can be retained with --basetemp alone, without changing tests or production.

P31 approved implementation remains COMPLETE. This historical review led to P32's shared
retained root and delegated two-case pass. P35 now explicitly supersedes that global policy:
only actual operator runtime artifacts are retained in repo/tmp; ordinary pytest scratch and
collection storage use normal native temporary storage/cleanup. Do not restore P32's global
overrides from this historical review. No production or cleanup fallback is authorized.

### Prior full operator run — 2026-09-19; failed acceptance; live workflow completed

Files: logs/from_operator/pre-commit.log (392568bytes,mtime2026-09-19T13:49:24UTC) and
pre-commit-extra.log (1141265bytes,mtime13:54:57UTC). Execution09:46:16–09:54:57(-04).
Log references below use raw LF line numbers; CR/ANSI-normalized views differ.

| Leaf | Result |
|---|---|
| Ruff/default mypy/AI mypy | PASS;68/55 source files |
| Main |174passed5skipped6xfailed1documented XPASS5.38s |
| Step4 |4passed1skipped2.31s; separate slow selection1skipped4deselected0.24s (configured external resources unavailable) |
| Mode3 |6passed1.11s |
| Mode0 |4passed11existing Plotly/Kaleido deprecation warnings3.46s |
| AI ordinary (aicode) |629passed1existing skip3deselected118.00s; no audit fork warning |
| Real OpenAlex/ROR model |1passed0.97s; reached after ordinary suite |
| macOS Chrome |9passed31.77s, including spacing, real query and synthetic DOCX export |
| Main real API |3passed182deselected1expected xfail3.86s |
| Privileged watcher |3passed70deselected3.56s |
| Live operator |1failed2intentional excluded-case skips320.80s; command exit1 |

No Ctrl+C, timeout or hanging wait in this run. Research/retries explain the duration:
first push about190s after queueing, second about261s, third about284s. Two evidence
validations reject into normal retry, then third is accepted. First was30/31 exact; final
31/31. No rollout-index failure or /pull500 observed. Repeated warnings correspond to
live/replay verification of the rejected attempts, not duplicate /validate records. Some
long evidence output interleaves warning prefixes; diagnostic formatting is noisy, not proof
of additional validation failure. Normal-suite ERROR/traceback output belongs to passing
negative-path tests; do not confuse pytest -srA capture with fresh failures.

Fresh verified progress: /completed200 materializes1section. Full Backend pid25607 closes
Store cleanly, Uvicorn completes shutdown; Dashboard records exit-15, clean_close_ack=True,
forced_kill=False, shutdown_succeeded=True. IPC-only pids25587 and26160 likewise close cleanly
and exit0. Post-run query returns307researchers/3attempts/1outcome; storage replacement is
after clean stop. Dashboard25569 exits0; resource-tracker descendant exits gracefully; no
forced fallback kill or Playwright teardown warning. Explicit private NiceGUI path and
production-data/original-NiceGUI preservation checks pass. IPC missing-socket polling stays
unchanged as operator elected below. IPC 'waiting for0' is immediately followed by admission,
not evidence of a stall. Full artifact validation/card-content verification did NOT pass.

Confirmed harness issues in that run (now corrected by P31 below):

1. validate_workflow_artifacts, protected/tests/operator/test_operator_e2e.py:1001, permits
   only /pull,/push,/commit and outcome paths. It rejects legitimate synthetic POST /validate.
   The traceback explicitly lists this sole extra route. Do not remove validation records,
   loosen production validation, or drop the allowlist assertion. Proposed test correction
   must use current /validate definition and also account strictly for linked provider HTTP
   inputs when present (none in this recovered run), not blanket-allow arbitrary external rows.
2. capture_completed_researcher_card selects PAGE_FOOTER_TEST_ID and waits only for nonempty
   text. Footer buttons already meet that condition. Actual captured card_text in extra.log
   LF7266 is exactly 'DOWNLOAD DOCX\nDOWNLOAD MARKDOWN'; no Markdown was captured. Its success
   log is therefore false evidence. Production 'Researcher card displayed' follows capture.
   Approved P31 correction: select existing CARD_MARKDOWN_TEST_ID, wait for the linked
   commit UUID/actual content and enabled DOCX button, then capture Markdown element text;
   replace stale commit-body assertions with current outcome-record content checks; retain timeouts. No UI/CSS change.

The first assertion prevented all later artifact checks; after it is corrected, the recorded
button-only capture would also fail card assertions. No claim that all remaining checks have
already passed. Ordinary/synthetic Chrome cases did not exercise these actual end-of-workflow
helpers. Before requesting another live run, proposed upstream coverage must invoke the actual
artifact validator against a real synthetic completed Store/log/CAS fixture and exercise the
actual card-capture helper in the existing host browser contour (not merely parallel helpers).
That review alone authorized no implementation; the exact P31 proposal below was subsequently approved.
No new elevate batch prepared or run; idle task unchanged.

### Recovered current run — read-only audit and requested artifact-directory change

Operator explicitly supplied tmp/run_h5f6hp6j_2 and reports conflation during recovery with a
previous run. Inspected ONLY this supplied bundle; no original production paths/config
construction, live/replay execution, provider/SSH calls or artifact edits. Current config
paths identify pytest-77/test_completed_dashboard_backe0. Findings:

-16LF-terminated JSON records; all16 DB HTTP rows exactly match IDs, ordinal sequence,
 method/path, JSON envelopes and LF-inclusive SHA256. DuckDB opened read_only=True;
 whole-file hash unchanged after reads. Initial empty table-comment anchor is expected.
-3push/commit/validate groups:2rejected evidence retries,1accepted; final /completed200.
 DB has3attempts and1materialized innerdict. Final outcome's commit/validation/self IDs match
 the innerdict. Accepted StandardizedSubmission has11institution objects, all provider IDs
 NR/NR: empty provider-record lists are consistent, not unexplained missing captures.
-All4CAS blobs match hash/size/line-count and are referenced by this run's3commits/final
 outcome; no unreferenced old blob. One Codex session01a0b9ee-3d90-7dc0-b437-55741ea22a18.
-NiceGUI has one Dashboard run01a0b9ee-2ff7-7213-8e62-3e58865dbcac,7events ending completed,
 empty queue and refreshed307/3/1 snapshot. Its sole committed innerdict matches the DB
 payload plus the separate namekey column; nested commit DTO's http_record/pull/push and
 outcome envelope match the exact replay records. Initial diagnostic comparisons mistakenly
 compared DTO wrappers/omitted separate namekey; corrected to the actual serialized shapes,
 not evidence of a data mismatch. No implementation/test assertion was changed.
-Queued→started interval1.572342s includes launch/readiness bookkeeping (not an isolated
 startup stopwatch); queued→completed297.656583s. No old Dashboard run in supplied storage.
 These files show no cross-run contamination; that does not refute operator's reported
 ambiguity/conflation while recovering files from the shared system-temp hierarchy.

Before P31, the fixture used pytest's per-test tmp_path for config/DB/replay/CAS/storage and a
separate /tmp/detour-operator-* TemporaryDirectory for socket path length. It does NOT
intentionally reuse one data directory across invocations. Nonetheless generated artifacts
should be easier to locate and preserve together, as operator requests. Proposed exact narrow
P31 fixture change (now implemented): unique retained repository tmp/operator-test.XXXXXXXX/
per operator test, logged before initialization, containing config/source-readonly-symlink,
DB/replay/CAS/NiceGUI/output and socket. No ordinary task or global pytest basetemp change,
no production storage cleanup, no change to production Dashboard/Store and no deletion on
success/failure. Existing process/socket cleanup and production preservation guards remain.
Collection-time NiceGUI isolation in the shared plugin is distinct from child run storage;
no unrelated all-suite tempdir redesign is proposed.

```python
@pytest.fixture
def operator_runtime(repository_root: Path) -> Iterator[OperatorRuntime]:
    artifacts_root = repository_root / "tmp"
    artifacts_root.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="operator-test.", dir=artifacts_root))
    _operator_log(f"Operator run directory (preserved): {run_dir}")
    dashboard_socket_path = run_dir / "dashboard.sock"
    if len(os.fsencode(dashboard_socket_path)) >= DARWIN_AF_UNIX_PATH_CAPACITY_BYTES:
        raise RuntimeError("operator dashboard socket path exceeds Darwin AF_UNIX capacity")
    yield _operator_runtime(
        run_dir,
        repository_root=repository_root,
        dashboard_socket_path=dashboard_socket_path,
    )
```

Configured production checkout yields88bytes for the proposed socket path, below the
existing104-byte Darwin limit; retain the explicit guard for other checkout locations, no
system-directory fallback. Necessary fixture/isolation tests should establish uniqueness,
retention and child storage/config/socket paths inside the run directory. This requested
direction and exact snippet were subsequently approved and implemented as P31.

### Local/delegated verification preceding this full run

Current verification:
- Item2: reproduced all five stale IPC-target failures (4.04s); corrected only target/import;
  unchanged preflight module then20passed25.15s.
- Item4: exact ready-card checks and finite measurement diagnostics; every existing spacing/
  bounding-box assertion and timeout retained. Host Chrome spacing verification now passes (3.28s); see delegated results below.
- Item5: real-child cancellation regressions reproduce early ownership release (2failed7.40s).
  Exact wrapper/log implementation plus per-owned-PID operator teardown check now in place;
  focused supervisor/shutdown/teardown selection8passed7.79s. Named child helper lives in the
  existing plugin; test explicitly marked python_subprocess. Initial test harness loop wakeup
  issue interrupted48.56s; reused existing threaded_loop fixture. An initial child-exit wait also timed out; replaced signal-handler
  printing with explicit sigwait to eliminate that race opportunity (initial cause unproven); synchronized log-drain phase with actual child exit. No production
  timing/timeout change or skipped assertion. These harness-development failures are not passes.
- Item6: new diagnostic regression reproduced missing Backend reason (1failed3.16s), then
  exact approved error-prefix filtering applied.
- Item7: exact named audit subprocess helper/explicit marker, unchanged production audit.
  First combined preflight/audit run36passed1failed80.96s: new child exceeded approved10s
  bound during concurrent verification. No timeout increase/suppression. The unchanged test
  passed within the full feasible suite below; unchanged isolated recheck plus three nonsocket
  substitution cases passed4tests2.67s. Cause of the initial timeout remains unproven.
- Full ordinary AI feasible suite:620passed1existing skip12deselected818.49s. Includes all
  startup cases, API/replay/index/Store, UI/supervisor, audit and full operator preflight.
  Excluded real-provider/root, two historical captures, Unix IPC/socket-substitution and
  four nonregular substitution params; the three nonsocket params passed separately above.
  Host browser module explicitly ignored, not reported passed. Existing skip is the
  deliberately disabled multiple-evidence-match rejection test. No warnings in this run.
  Strict detour mypy PASS55files; full src/tests
  Ruff PASS after correcting only the approved helper snippet's import-spacing blank line.
  AST audit confirms old _stop body unchanged except approved extra log fields; every original
  compact-spacing/bounding-box assertion is unchanged.
  Main/default mypy PASS68files. Main suite on this x86 host is NOT wholly green:
  initial maxfail run20passed1skipped1deselected1failed12.43s (configuration lists only ARM
  extension binaries, not linux_amd64). Remaining main selection140passed3skipped2deselected
  2failed16.42s: configured ARM binary absent, reviewed workbook absent at production path.
  No fixture/config substitution, new skip, data search or test weakening. Those
  existing prerequisite checks now pass on aicode through elevate; no out-of-scope implementation.
  Step4/Mode3:10passed1slow deselected17.80s (default environment). Mode0 import/isolation
  and normalization helpers:2passed2plot cases deselected2.60s (Mode0 environment). Plotting
  requires Kaleido sockets unavailable here; existing operator Mode0/root passes remain the
  retained evidence for unchanged boundaries, not newly executed checks. No full acceptance claim.

The prior failure-free FULL pre-commit-operator prerequisite is lifted by the latest explicit instruction. P26–P30 are now authorized for sequential implementation despite the deferred harness failures. Correction1 (find/supported-subset eligibility) remains implemented and
locally verified246passed1existing skip3deselected; seeded choice/retry behavior unchanged.
Correction3 deleted all elevate-triggering tests and preserved the then-idle task. The
Assistant-owned elevate completed the delegated checks described below and is restored to
its historical idle script/log/status/FAILED-grep scaffolding; no tests invoke it. Any further deviation/new defect requires explicit approval.

### Delegated verification preceding the latest full operator run

Previously reviewed logs/from_operator/elevate.log (mtime2026-09-19T12:19:57UTC,23837bytes,
231lines). All20 targeted cases PASS, none skipped, no warnings/errors, timeout, Ctrl+C or
forced process kill. Log ends at the final pytest summary; outer wrapper exit status is not
included, so do not invent one. Each of the five intended leaf commands visibly completed:

| Machine/leaf | Result |
|---|---|
| macOS, actual Chrome UI module |9passed31.09s; compact spacing3.28s, DOCX export3.38s, real owned query4.45s; longest case7.25s |
| aicode, real OpenAlex/ROR model validation |1passed1.11s (previously unreached provider leaf) |
| aicode, real0600 Unix IPC and isolated audit probe |2passed0.82s; audit0.31s, no multithreaded-fork warning |
| aicode, nonprivileged watcher socket substitutions |2passed48deselected4.72s; real CLI case4.65s |
| aicode, default-env extension/reviewed-workbook prerequisites |6passed0.61s; real configured ARM binary loads and workbook exists |

Owned IPC Backend pid23475 logs clean-close acknowledgment, exit0, clean_close_ack=True,
forced_kill=False, shutdown_succeeded=True before the snapshot replacement. Dashboard
pid23457 then stops normally, exits0; resource-tracker descendant exits without fallback
termination. Private NiceGUI storage path is explicit. The full-Backend/live-Codex contour
was not part of this batch; its final proof remains the full pre-commit-operator run.

Eight identical missing-socket messages precede normal IPC readiness, accounting for the
operator's noise complaint, not an actual failed start. The suffix verification from an
empty anchor is expected for this fixture. "after earlier load attempts failed" in the
main extension tests is their intentional exercised fallback, not a new failure or masking.
No abnormal wait or inconsistent machine/environment routing was found.

Operator removed the elevate EXIT trap to retain its temporary files. Preserve that choice:
no preserved script/status/log file was deleted, and no trap was restored. There are no
copied tmp/elevate.*/status files locally; do not search unrelated artifacts for one.
With this batch complete, restored only elevate's historical "Nothing to elevate"
script/log/status/FAILED-grep scaffolding. TOML, shell syntax and equality of all other
settings/tasks checked; no task executed during restoration. No new delegated batch is
needed for that handoff. The subsequently executed full run is reviewed above; its new
harness failures were addressed by P31; its approved UUID amendment is implemented and locally verified. The operator had separately lifted the gate for P26–P30 implementation.

### IPC readiness logging — keep current behavior; discussion closed

Operator explicitly rolled back the ui.py/test_ui.py suppression patch, then said
"ok. let's keep it" after the causal review. Preserve original FileNotFoundError diagnostic,
0.1s readiness polling and30s deadline (600s full rebuild). No suppression flag, initial
sleep, timeout change or SSE implementation is pending/authorized. The prior patch's8test/
Ruff/mypy pass is historical evidence only, not a current implementation.
The real Query button checks for an external Backend, starts its own if absent, waits for
OPTIONS readiness, THEN sends GET/query. Initial discovery plus startup polls explain the
messages; Backend creates socket only after config/source loading and Store verification.
The earlier elevate case had7child readiness misses, whole test call4.45s; neither that nor
slower prior test durations is an isolated startup benchmark. Query is not sent prematurely.

P30 is COMPLETE. Implemented operator clarification: persistence must not depend on
application validity. Missing/mismatching session/identity/linkage/ETag cannot suppress the
HTTP history. This supersedes the prior session-less outcome exception question; no special
permission to persist it is needed. Current implementation and verification are recorded below.

P29 is COMPLETE: Backend retry bookkeeping uses original_pull_record_id throughout, including
DDL/SQL and direct tests. Dashboard run IDs are unchanged; P30 linkage work is now complete.

P28 is COMPLETE: direct BackendComponent ownership, common record inheritance and downstream
RunOutcomeResponseRecord rename. Wire fields/module locations remain unchanged.

P27 is COMPLETE: full P25 literal audit, authoritative definitions and retained-literal
justification recorded below, with fresh passing checks.

P26 is COMPLETE: explicit typed record constructors, authoritative Backend ContentType/header
wiring and query receipt-time validation. Fresh verification is below.

P25's exact proposed four-operation Store contract,
implementation boundary and code snippets are APPROVED, with two operator corrections:
use BackendStoreAcknowledgment.ACK/NAK (values "ack"/"nak") everywhere;
operator explicitly requires enum-member checks, never acknowledgment.value vs raw strings; reserve publishing
terminology for DOCX/TXT and use update_pull_state for the runtime pull-state update.
P25 baseline implementation is COMPLETE and locally verified (2026-09-18). TASK and WORK
were reread in full; verification results and corrected development failures are below.
The full approved contour/snippets below stand alone.
Any deviation or extension requires explicit approval before implementation.

P24 is implemented and locally verified after the operator's restore/reimplementation
instruction; its fresh evidence is below. P20/P21/P23 remain implemented. P22 is historical,
superseded by P24's persisted-ID/pure-renderer contour. P25 retains that contour while
changing Store/adapter boundaries and grouped processing only as explicitly pinned below.
P25 production wiring is implemented and its selected integration/startup checks pass.
The last full operator run exposed five missed preflight callpoints and three stale elevate
test expectations; both are corrected now, but fresh full acceptance remains pending. The
separate web-action correction1 is implemented. The additions' current statuses are above; P26–P30 are complete, including the persistence-first and initial-validation clarifications. P30 supersedes only the state ownership,
outcome reference selection and innerdict metadata decisions identified below. Preserve
operator edits/staging. Production acceptance and unrelated browser/root/pre-start findings
remain separate; these additions do not authorize their corrections.

## P25 — Implemented and locally verified: four-operation Store contract

Operator approved the exact preceding proposal and snippets, subject only to the naming
corrections incorporated below. This section consolidates the discussion into that approved
contour; it is not a further proposal or an implementation claim. This is a bounded structural
change, not merely a server gate cleanup. Preserve durable record linkage, pure innerdict
rendering, no recovery and common live/replay rules. P30 replaces the former metadata fields
with a full persisted outcome envelope. Unrelated browser/root/pre-start findings are excluded.

### Responsibility and persistence contract

Server owns ASGI/WSGI transport conversion, lifecycle and admission. API/IPC helpers exchange
Requests PreparedRequest/Response objects with server, app RequestRecord/ResponseRecordPromise
objects with Store. Requests is used as an in-process representation, never internal HTTP.
API retains existing transport/workflow response timing, including busy503, push409 and early202,
and updates pull state from final push results. It does not append/project/validate itself.
Existing evidence/SQL algorithms may remain private helpers invoked by Store; no wholesale
move of API algorithms into the Store module. Only Store owns DB/log operations/transactions.

BackendStoreAcknowledgment has exactly ACK/NAK and refers ONLY to request persistence.
ResponseRecordPromiseResult[R] is exactly (R, None) or (None, StoreExceptionProperty), with
concrete BackendStoreException implementing that protocol. Result errors are raised by the
adapter; they do not silently become HTTP409. Request persistence failure for API returns NAK
plus an already-resolved error result. IPC always expects NAK. ACK followed by a later error
remains ACK plus an error result. Invalid result tuples are contract failures, never fallbacks.
Normal Store failures resolve the tuple; they are not thrown directly from the completion
awaitable. API/IPC raise its returned real exception. Never return both tuple values or both
None. A failed append/fsync can leave bytes despite NAK: fail closed, no repair/retry or claim
of zero bytes written. Successful run-outcome409 is NAK plus (response_record, None) after
its response exchange is durably persisted/projected; HTTP status is independent of the gate.

| Operation | Gate | Operation/result boundary |
|---|---|---|
| pull | ACK after append/fsync; NAK on failure | project/read back exchange before result; preserve all existing HTTP statuses/bodies |
| push | ACK after append/fsync; NAK on failure | accepted202 may be sent before processing finishes; final result follows grouped commit/validation projection |
| run_outcome | NAK by policy | persist complete response exchange, including409, project/materialize eligible rows, then return successful result |
| query | NAK by policy | read-only wholesale snapshot, no log or DB content writes |

Approved record format: retain existing v1.1 COMPLETE pull/push HTTP exchange envelopes in
log. The app RequestRecord can contain the already-selected public response (202/409/etc.)
because it is an application input, not an alias for raw HTTP request. Do not introduce a
second request-only pull/push log entry, repeated record UUIDs, mutation of old JSONL lines,
or request/response pairing schema. Commit/validate retain their current synthetic shapes;
outcome logs its full response exchange only; query logs nothing. This is explicitly part
of the approved scope, not a new compatibility contour. Early202 establishes log durability,
NOT completion of grouped DB projection. Final result objects still come through Store
projection/readback. Extra application model fields are excluded from HTTP-log serialization.

Timing wording to make explicit in the promise protocol: Store performs required response
persistence before returning a SUCCESSFUL completed promise result. The initial handle and
its request gate are distinct from that final result. A response persistence failure yields
(None, exc), never a usable response. For push its public202 exchange is already persisted
at ACK; its added commit/validation properties become available only at completion. A literal
requirement to finish all final application-response work before returning the initial handle
would contradict early push acceptance; do not silently change that timing.

### Exact approved protocol and exception snippets

Architecture property definitions below live under BackendComponent in
protected/src/architecture.py (existing component bases retained). The latest operator
correction explicitly places StoreAcknowledgmentProperty and
ResponseRecordPromiseResultProperty there; concrete BackendStoreAcknowledgment and
ResponseRecordPromiseResult remain downstream in response_record_promise.py. The result
property is a tuple-union type alias, preserving the approved exact tuple contract; it is
not a new result wrapper model.
The structural exception includes raise_exception so protocol-typed consumers can raise the
real exception without casts or pretending a Protocol inherits Exception.

```python
# Nested under BackendComponent:
class StoreAcknowledgmentProperty(Protocol):
    @property
    def value(self) -> Literal["ack", "nak"]: ...

type ResponseRecordPromiseResultProperty[R] = (
    tuple[R, None]
    | tuple[None, BackendComponent.StoreExceptionProperty]
)

class RequestRecordProperty(HttpRequestLogRecordProtocol, Protocol):
    pass

class ResponseRecordProperty(HttpRequestLogRecordProtocol, Protocol):
    pass

class StoreExceptionProperty(Protocol):
    def raise_exception(self) -> NoReturn: ...

class ResponseRecordPromiseProperty[
    R: BackendComponent.ResponseRecordProperty,
](Protocol):
    """A request-persistence acknowledgment and an eventual application result.

    ACK means the request record was appended and fsynced in the replay log.
    NAK means it was not. IPC deliberately does not persist request records.
    Neither value describes response persistence or application success.

    Backend Store performs response persistence where required before returning
    the successful completed result. Response-persistence failure returns
    (None, exc); success returns (response_record, None).

    Returning the initial promise handle does not imply processing completion.
    """
    @property
    def acknowledgment(self) -> BackendComponent.StoreAcknowledgmentProperty: ...

    async def response_record(self) -> BackendComponent.ResponseRecordPromiseResultProperty[R]: ...
```

Concrete implementations in the new response_record_promise.py helper:

```python
@implements[BackendComponent.StoreAcknowledgmentProperty]()
class BackendStoreAcknowledgment(StrEnum):
    ACK = "ack"
    NAK = "nak"


@implements[BackendComponent.StoreExceptionProperty]()
class BackendStoreException(RuntimeError):
    def raise_exception(self) -> NoReturn:
        raise self


type ResponseRecordPromiseResult[R] = (
    tuple[R, None] | tuple[None, BackendStoreException]
)
```

Preserve the original cause when converting internal exceptions; log detailed errors, retain
existing fail-closed Store state, and never stringify away the cause or retry. The concrete
ResponseRecordPromise is a FrozenStrictModel: acknowledgment is its public field, task/result
state is PrivateAttr. Awaiters shield the Store-owned completion. No arbitrary_types_allowed,
new executor service, cast, type suppression or serialized Task/Future. Reuse existing thread
offload and tracked background work; no threaded IPC. Keep completion tracked through the
pull-state update and shutdown, including client disconnect and failed response sends.

### Route-specific records and Store surface

Add route-specific RequestRecordProperty/ResponseRecordProperty protocols under BackendComponent.
Their common base is the corresponding HTTP-record protocol. Concrete pull/push/query records
inherit HttpRequestLogRecord; reuse the existing outcome response model, renamed to
RunOutcomeResponseRecord by the later explicit P28 correction. Keep outbound Dashboard QueryRequest and
RunOutcomeRequest as existing client-facing types; add server-side record adapters, not duplicate
client protocols. Existing QueryResponse remains the wholesale response BODY, not the envelope.

Representative concrete shapes (constructors/validators preserve current wire fields):

```python
class PullRequestRecord(HttpRequestLogRecord):
    pass

class PullResponseRecord(HttpRequestLogRecord):
    @property
    def pull_response_body(self) -> str:
        if self.response_body is None:
            raise ValueError(Locale.PULL_RESPONSE_BODY_MISSING)
        return self.response_body

class PushResponseRecord(HttpRequestLogRecord):
    commit_record: BackendCommitRecord | None = Field(exclude=True)
    validation_record: BackendValidationRecord | None = Field(exclude=True)
```

Use existing @implements decorators and record validators; both extra push fields are explicit
at construction, not old-data fallbacks. Nonaccepted pushes have neither; accepted pushes return
matching typed records after completion. Preserve external session/pull linkage on PushRequestRecord
and captured outcome inputs on its server-side request model as excluded typed fields. API/IPC
helpers assemble/capture those external inputs at their existing lifecycle points; do not delay202
for rollout capture or duplicate that I/O. Store orchestrates the existing capture helpers when
processing needs them. QueryResponseRecord exposes typed query_response_body. No raw DB handle
or transport object in serialized records. Preserve intentional nullable outcome headers when
converting to Requests responses; do not change the shared v1/v1.1 converter or add old-schema code.

Public operations, abbreviated concrete names (P30 additionally exposes four read-only
current-record properties and the initial-validation reference on the full Store only;
query-only capability stays unchanged):

```python
class QueryOnlyStoreProperty(Protocol):
    def query(self, request: QueryRequestRecord) -> ResponseRecordPromise[QueryResponseRecord]: ...

class FullStoreProperty(QueryOnlyStoreProperty, Protocol):
    def pull(self, request: PullRequestRecord) -> ResponseRecordPromise[PullResponseRecord]: ...
    def push(self, request: PushRequestRecord) -> ResponseRecordPromise[PushResponseRecord]: ...
    def run_outcome(self, request: RunOutcomeRequestRecord) -> ResponseRecordPromise[RunOutcomeResponseRecord]: ...
```

The real architecture protocols use the corresponding component record/promise protocols.
Private constructors/lifecycle/SQL/append/readback/validation/materialization helpers remain
private; public Store operations are exactly these four, plus P30's read-only current/initial properties.
Query-only object actually has only
query, not a cast or full object hidden solely behind a narrower annotation.

Initialization overloads in the EXISTING Store module, preserving confirmation/hash/lock rules:

```python
@overload
def initialize_backend_store(
    runtime: AiAugmentBackendContext, *, ipc_only: Literal[True],
) -> AbstractContextManager[AiAugmentQueryBackendStore]: ...

@overload
def initialize_backend_store(
    runtime: AiAugmentBackendContext, *, ipc_only: Literal[False],
    new: bool, confirmed: bool, confirm_replay: Callable[[], bool],
) -> AbstractContextManager[AiAugmentBackendStore]: ...
```

One actual query-only wrapper, with its engine reference private, suffices; no hierarchy of
services. Config still registers/verifies resources but no longer exposes a full Store instance
before mode selection. Construct the owned Store at server lifecycle entry from those resources;
pass only selected capability to adapters. This requires the local ai_augment_config.py field/
construction removal and necessary runtime callpoint wiring. No JSON config/CLI change.
IPC-only still ignores new/resume flags, does not initialize DB, append-preflight or promote hashes.
Full new/resume/continue prompts, optional nonempty replay confirmation, permissions, process
lock and clean-close acknowledgment stay unchanged. No public Store open/execute/etc. loophole.
Construct config/source runtime once per server lifetime; mode-selected Store lives inside
the corresponding server context. No duplicate context/resource construction.

### Adapter/server snippets and boundary

API preserves current response selection/timing. It creates app RequestRecords from Requests
objects. Schematic accepted-push branch (new helper names are reviewable wiring, not extra Store
methods):

```python
promise = await asyncio.to_thread(store.push, request_record)
if promise.acknowledgment is BackendStoreAcknowledgment.NAK:
    response_record, error = await promise.response_record()
    if error is not None:
        error.raise_exception()
    raise BackendStoreException(Locale.PUSH_NAK_ERROR_MISSING)

# Register before serving 202; task updates pull state before leaving the gate.
register_processing(finish_push(promise))
return accepted_response
```

The candidate202 exchange in request_record is what was durably logged; ACK does not select
202 for a request whose existing API response decision was409/500. Later Store errors are
raised by the tracked completion task and retain existing fatal handling, never dropped.

```python
async def finish_push(promise: ResponseRecordPromise[PushResponseRecord]) -> None:
    response_record, error = await promise.response_record()
    if error is not None:
        error.raise_exception()
    if response_record is None:
        raise BackendStoreException(Locale.PUSH_RESPONSE_RECORD_MISSING)
    update_pull_state(response_record)
```

IPC requires NAK and resolves the same tuple before transport conversion:

```python
if promise.acknowledgment is not BackendStoreAcknowledgment.NAK:
    raise BackendStoreException(Locale.IPC_REQUEST_UNEXPECTEDLY_PERSISTED)
response_record, error = await promise.response_record()
if error is not None:
    error.raise_exception()
if response_record is None:
    raise BackendStoreException(Locale.IPC_RESPONSE_MISSING)
return response_record.to_response()
```

Move ONLY actual transport glue to server.py: FastAPI app/route registration and raw
ASGI request/response conversion; Flask app/route registration, _DashboardQueryApp and
Unix-socket start/stop/serve wrappers formerly in protected IPC. Preserve route metadata,
OpenAPI output, socket permissions, signals and clean shutdown. Update direct test/import
callpoints rather than leaving compatibility aliases. API workflow input/session startup
remains its helper, called by server; evidence/validation algorithms are not part of this
transport move. Eliminate _AuthoritativeHttpMiddleware's independent persistence path once
Store operations own it, not a second append on top of the new flow.

Server receives Requests Response and serves status/headers/body unchanged. Retain separate
FastAPI and single-threaded Flask; gate ALL IPC including OPTIONS before Store work, through
response. Existing server-owned gate/bridge/shutdown offload can remain narrowly adapted:
wait for active HTTP exchanges plus registered API completion/pull-state-update tasks, prevent a
new HTTP request slipping through IPC admission, release on failures. No priority queue or
threaded Flask. Client timeout is explicitly allowed and never cancels durable work. No
need to reimplement the gate merely to make it shorter.
Keep the explicit IPC docstring: clients may time out while IPC waits for FastAPI and its
tracked processing to finish; their timeout does not cancel durable Backend work. Single-threaded
IPC naturally serializes outcome/query; no outcome-over-query overtaking policy. Shutdown drains
tracked processing through the pull-state update and responses, stops/joins transports without
blocking the server event loop, closes Store, then emits the existing clean-close acknowledgment
and releases the process lock. No public Store finish/poll operation or client-owned task lifetime.

### Grouped replay and outcome changes — not hidden in a protocol-only patch

Keep private append/fsync separate from common application; separate durable append
position from committed projection
position so an ACK can precede group completion. Keep exact raw bytes, SHA256, ordinals and
anchor coverage. Group an accepted202 push through its matching commit/provider/validate
records, preserving interleaved /pull503 and rejected /push409 records in append order.
Domain invalidity is a completed recorded validation, not a missing validation record.
Incomplete group on explicit replay fails at the originating push; no recovery/network.

Common group application uses ONE outer DB transaction; per-record applicators no longer
independently commit it. Provider rows may be provisionally inserted/read inside this
transaction before model validation, then all group rows become committed together. Do not
hold the append/DB mutex across external provider wait in a way that prevents current busy503
responses. An interleaved public exchange can enlist in the active group; it must not open
a competing/nested transaction or independently commit it. Query/outcome remain gated out.
This concurrency/cursor wiring is implemented and covered by the P25 checks below.

Rejected validation discards its rejected derived effects. Grouped rollback must
retain/reinsert ALL group raw HTTP rows/hashes/ordinals,
not only /validate, plus the recorded attempt, without retaining rejected derived output.
Preserve existing evidence/retry algorithms and which domain effects are retained. Final
accepted innerdicts still wait for outcome, as P24 specifies.

P30 supersedes historical latest-by-session reference searches here: outcome uses the
Store-owned current records and explicit session/ETag checks. It still checks persisted
reference consistency without reapplying side effects, and constructs response with
commit_record_id, validation_record_id and run_outcome_record_id, appends/fsyncs, then
projects outcome/materializes in the same
transaction before exposing success. Exact self ID is the exchange UUID, not a second UUID.
The exact additions to the existing RunOutcomeResponseBody are:

```python
commit_record_id: UUID | None
validation_record_id: UUID | None
run_outcome_record_id: UUID
```

These are required current fields (nullable references where genuinely absent), not defaults
or old-schema fallbacks. Update the corresponding protocol/DTO/readback consumers together.
Rejected409 is logged/history only: no finalization and no late-validation fence. Update P24
applicator/snapshot invariants accordingly, retaining all accepted rows/multiple commit links
and not choosing a different researcher's/session's latest commit. No synthetic missing data.

Approved outcome/record decisions (included in the accepted exact scope):

1. Preserve complete pull/push exchange envelopes as above, rather than add request-only logs.
2. With P30's current-record/session selection and completed ETag check replacing historical
   selection: /completed200 only for a replay-consistent ACCEPTED validation; /failed200 when
   that current matching result is absent/not accepted
   (including replay-consistent rejected validation),
   otherwise409. Missing evidence is distinct from corrupt persisted evidence/DB, which
   remains a Store error. /cancelled requires no commit/validation. Existing capture failures
   remain separate from domain409; do not silently drop their500/history behavior.
3. P30 replaces latest-matching scans with Store-owned current commit/validation references
   and their exact link; its full outcome-envelope field replaces commit-centric innerdict
   metadata. Do not overwrite earlier finalized data or silently broaden/narrow acceptance
   eligibility. All body/DTO/protocol validators and query consumers must agree; no fallback
   for missing current fields. See P30 for the precise metadata/state boundary.
4. Dashboard's one-pull503=>failed policy is unchanged: if Store finishes successfully while
   outcome waits, /failed may then409. No automatic reclassification/retry/extra query is authorized.

### File boundary and upstream verification

Latest narrow operator corrections (2026-09-18): within P25 only, HTTP status decisions,
parameters/return annotations and newly changed comparisons must use HTTPStatus, not plain
int/numeric literals. Preserve the shared v1/v1.1 serialized numeric field contract; convert
at the typed boundary rather than change that shared schema. Move P25's hardcoded exception
and operator-facing log messages to the appropriate existing locale.py, preserving wording
and behavior. No unrelated codebase-wide status/localization refactor is authorized.

Existing production files: protected architecture.py, backend API/server/Store and config,
protected IPC, run_outcome_record.py, query_response.py; necessary concrete context typing/
initialization callpoints; Dashboard snapshot/run-outcome DTO consumers ONLY as needed to
understand outcome IDs/409 without treating rejection as finalization. No UI layout/queue/
render/export redesign or extra query. Apply P28's explicit outcome response rename and
P30's narrowly authorized outcome-envelope metadata and ETag/sender wiring; retain dump-only
rendering rather than the superseded separate card-ID presentation.
New small modules only: response_record_promise.py and request_response_records.py under
existing Backend helpers/data_models. Keep private Store lifecycle/query-only implementation
in its current module. Necessary imports/calls/tests only; no broad module reorganization.

Existing relevant tests: test_api, test_ipc, test_backend_store, test_http_interceptor,
startup cases in test_ui and isolated browser/operator fixture callpoints affected by Store
construction. Test real synthetic Store/log/DB and transport adapters, not source-string tests.
Cover all ACK/NAK/result combinations; fsync/request/response/projection failures; early202
and later pull update; callback failure/shutdown/client disconnect; read-only no-write query;
actual query-only capability; grouped exact-byte live/replay equivalence including interleaved
503/409 and rejected validation; truncated groups; outcome200/409/cancellation; finalization
IDs and pure cards. Test existing IPC gate with real in-process ASGI/WSGI and background tasks.
Run applicable Ruff/strict mypy without casts/suppressions and existing meaningful regressions.
Real socket/browser/operator verification is a separate boundary; no live Codex needed to
catch these contract errors. Do not alter ordinary tasks or touch production artifacts.

Excluded: shared HttpRequestLogRecord v1/v1.1 implementation, pasted models/StrictModel,
main pipeline/other detours, sample_deploy, TASK/HUMANS/README, CAS layout, hash/config auto-
updates, compatibility/migration/fallbacks, recovery, wrapper tasks, unrelated operator fixes.
Grouped persistence and the request/response API are implemented; P26–P30 additions are complete.
P30 and P31 are also complete and locally verified. Proposed delegated host verification and full production acceptance remain.

### Latest approved P25 test-helper correction

Operator approved exactly these separate ownership entry points, not a Path | Store union:

```python
def logical_database_snapshot(path: Path) -> DatabaseSnapshot:
    # Own a read-only connection; close it before returning.
    ...

def store_database_snapshot(store: AiAugmentBackendStore) -> DatabaseSnapshot:
    # Read through Store; do not open or close a connection.
    ...
```

DatabaseSnapshot only names the existing return type. Both delegate to one private snapshot
builder receiving a row-fetching callable. No isinstance dispatch, new model, changed SQL/
assertion or production API. Update only the corresponding test callpoints. Implemented;
existing snapshot/replay checks passed2 in25.84s.

## P25 execution checkpoint

- Completed instruction: P25 only, including the approved snapshot helper split.
  P26–P30 were separately pending at that historical checkpoint. Their current statuses
  are above. Do not reintroduce
  their superseded historical selection/card rules as the final design. Operator has staged
  in-progress files; preserve the index and signed human comments.
- Production wiring is implemented: four Store operations/private lifecycle/SQL; actual
  query-only capability; ACK/NAK promises and grouped push projection; Requests adapter and
  server transport/admission; outcome IDs/409 handling; necessary config/consumer wiring.
  Evidence/retry algorithms stay in API helpers called by Store. No shared HTTP-schema,
  CAS, ordinary-task, pasted-model or unrelated operator correction.
- Architecture owns StoreAcknowledgmentProperty and ResponseRecordPromiseResultProperty;
  concrete implementations remain downstream. The result alias's human-signed Annotated
  comment/import is preserved. Explicit promise @implements checks the tuple return through
  method compatibility. New record/capability/exception/enum protocols have downstream
  @implements; P28 separately removes the redundant Pull common-base decorators.
- Enum comparisons use BackendStoreAcknowledgment.ACK/NAK, not raw .value strings. P25
  status decisions/constructor annotations use HTTPStatus; shared numeric wire fields stay.
  P26/P27 subsequently completed typed construction/content types and the full literal audit.
- Actual fsync -> readback failure now preserves ACK plus error (never NAK). Grouped raw
  records/hashes/ordinals survive rejected-derived-effects rollback. Busy503 and rejected409
  can enlist during provider capture; IPC waits through HTTP and tracked pull-state update.
- Existing tests now call actual Request/Response/Store boundaries, not removed middleware,
  config.backend_store or _apply_log_record. Snapshot helpers have separate Path/read-only
  and Store-owned entry points, sharing unchanged SQL/assertions (2passed25.84s).
- test_run_outcome_http_exchange_is_logged_and_replays_as_raw_history remains. Its obsolete
  fake-Store/two-case parametrization became all three paths x complete/incomplete capture,
  exercising real IPC/Store/log/DB/replay (6passed48.24s). No accepted validation means
  completed409, not200. Separate materialization matrix covers accepted completed200.
  Exact canonical headers, full serialized envelope, typed body, live/replay query JSON,
  logical DB and unchanged replay bytes are checked. Initial header/base-subclass equality
  test errors were corrected without weakening the stored-record assertions.
- Real early202/durable push/interleaved503/final commit-validation and captured provenance
  checks passed2 in35.52s. The adapter-before-send test exposed a missing nonaccepted-push
  record-UUID log; restored one message via Backend Locale, retaining assertions (2passed).
- Latest additional boundary selection:17passed45.49s. Covers outcome NAK with response fsync/
  projection failure and no usable result; Store-owned completion surviving waiter cancellation;
  incomplete groups ending after push/commit failing at originating replay line2 without
  projection/recovery; provider capture allowing interleaved503/409; actual accepted-push
  completion after client cancellation/response-send failure; successful public outcome200,
  linked IDs and materialization. No real provider/SSH/network calls.
- Fresh static checks: Ruff PASS, full strict mypy PASS56files, git diff whitespace PASS.
  Initial mypy182/105/37/7/1-error migration checkpoints are superseded by this pass.
  Initial broad API check167pass/1skip/2fail/1error: one adjacent action parametrization was
  accidentally lost during migration (restored exactly); closed Store now raises the typed
  runtime-unavailable error under mode-specific construction; provenance test used the wrong
  fixture object's session member (fixed). All five affected cases then passed10.60s.
-410 hang: bounded45s diagnostic showed only main-thread selector polling during Runner
  cleanup, not a Store-lock worker. Moved existing explicit threaded_loop fixture from
  test_ipc to protected pytest plugin and reused it for new async/offloaded test callpoints;
  unchanged410 timeout/assertions now pass1 in4.99s. Timer drives cross-thread callbacks
  through executor cleanup; no production timing/locking change, fallback or skip.
- Final diff audit: current API/IPC adapters no longer reference config.backend_store,
  removed middleware or _apply_log_record; direct detour-DB handles remain inside Store/
  its resource, with source-DB reads explicitly readonly. No new cast/type suppression or
  acknowledgment.value comparison. AST comparison found only the two obsolete middleware
  tests replaced by the actual adapter test; other parametrizations retained except the
  documented outcome matrix and HTTPStatus enum migration. The accidentally lost unrelated
  action parametrization is restored. Human-signed promise alias comment remains unchanged.
  Paused/excluded protected BDD still references api.app and the removed middleware; it is
  outside this implementation/test scope and was not changed or run. No compatibility alias.
- Earlier focused P25 evidence: Store integrity/startup26passed33.83s; initial public
  operations7passed7.87s; interceptor/group33passed71.75s; IPC22passed2.99s; Store/IPC56passed
 69.74s (overlapping selections, not additive). Real socket/historical capture exclusions
  remain; historical callpoints updated statically, never executed/accessed.
- Combined feasible API/Store/interceptor/IPC/UI regression:379passed,1existing skip,
 102deselected in273.33s. Deselections cover subprocess/browser/socket/historical boundaries.
  Startup subprocess batch stopped after5 failures: two migrated named child helpers used
  relative imports despite being executed standalone. Corrected to absolute imports; focused
  bootstrap then reached clean Store closure but timed out in the async query check. Reused
  the existing test-only ticking Runner through a shared context helper for standalone child
  callers as well as the explicit fixture; unchanged timeouts, real adapters/offload retained.
  Bootstrap, all four ready modes and completed-query fixture recheck:6passed46.08s.
  Remaining startup-condition/confirmation matrix:87passed,25deselected443.65s. Also moved the completed-
  query helper's HTTPStatus import inside its standalone body and added a browser-free test
  executing that actual fixture and checking its queryable linked history. P25 baseline is
  implemented and locally verified. Browser/root/live-Codex/operator acceptance is not claimed; remaining
  independent production findings are recorded below.
- Delegated check completed (2026-09-18): reviewed elevate.log; both existing tests PASS,
  2passed43.48s, command exit0: real0600 Unix-socket query/cleanup and real browser/owned
  IPC wholesale-query. Browser setup10.56s/call30.24s; repeated missing-socket readiness
  polls eventually succeed, no timeout/interruption. Snapshot307researchers/1attempt/1outcome
  replaces storage only after Backend clean-close acknowledgment/exit0; Dashboard exits0.
  Uses explicitly selected Playwright Chromium (installs only its headless shell), isolated
  test storage, existing timeouts/assertions and detailed elevate.log/FAILED grep/status.
  No live Codex, provider or sudo tests; ordinary tasks unchanged.
  P25's targeted real-transport check now passes, but does not resolve browser-test placement,
  root watcher access or the live-operator pre-start hang. That checkpoint did not establish full acceptance readiness. The subsequent routing/root
  corrections and targeted checks below now permit a full operator run; acceptance itself
  is still pending. P26–P30 were pending at that checkpoint; see current statuses above. Local preparation:
  TOML/shell syntax PASS, both exact nodes collected (2tests3.42s), diff whitespace PASS;
  collection is not an execution pass.

## P26 — COMPLETE: typed record construction and Backend content types

Operator approved the explicit QueryResponseRecord constructor/factory shown in chat,
including rejection of a missing receipt timestamp instead of inventing zero duration.
Operator then approved a narrow addition: represent the content types used by these
request/response paths with a StrEnum in protected/src/backend/helpers/vars.py and wire it
through all P25 RequestRecord/ResponseRecord construction/consumer paths. This supersedes
the proposed standalone JSON_MEDIA_TYPE constant, not P25's persistence/lifecycle contract.

Scope:

- Explicit typed model construction with named arguments, not model_dump dictionary merges
  or string-key overrides, for the request/response records introduced/rewired by P25.
  Keep route-owned envelope decisions in the corresponding record constructor/factory;
  Store orchestrates operations and passes typed inputs. No generic builder/service layer,
  model_construct validation bypass, cast, compatibility alias or schema fallback.
- Explicit operator-flagged instance, covered by P26/P27 rather than a new scope item:
  RunOutcomeRecord.to_response (RunOutcomeResponseRecord after P28) previously reconstructed
  an HTTP record via self.model_dump() | {"response_headers": ...}, then sets literal
  "Content-Type"/"application/json" on the converted response. Replace this shape with
  explicit typed construction and the authoritative header constant/ContentType.JSON;
  keep the response-specific header decision owned by the response model. Any temporary
  transport-envelope adaptation must leave the durable record and its intentional nullable
  headers unchanged. Reuse the existing shared HTTP converter; no shared-schema change.
- One ContentType StrEnum and authoritative Content-Type header-name constant in existing
  Backend vars.py. Wire relevant API/IPC/server/record constants, comparisons and helper
  annotations to enum members; update their direct test/import callpoints. No raw-string
  enum comparisons or duplicated application media-type definitions in these paths.
- Preserve actual wire values and charset behavior, including NDJSON/Markdown UTF8 responses
  and existing JSON/plain-text responses. Do not add headers to synthetic /commit or
  /validate or change intentional nullable outcome headers in durable records. Do not
  coerce/restrict captured external-provider headers to this application enum.
- Existing protected Backend locale.py owns the missing-timestamp error. Preserve HTTPStatus,
  request ACK/NAK, complete-exchange serialization, response timing and query's no-write rule.
- Only necessary record/helper/callpoint/test changes within P25 plus Backend vars/locale;
  no shared HttpRequestLogRecord/Protocol v1/v1.1 schema change, unrelated media-type cleanup,
  Dashboard redesign, new module or new endpoint.

Exact enum/constant shape for the currently used application content types:

```python
# protected/src/backend/helpers/vars.py
from enum import StrEnum
from typing import Final

HTTP_CONTENT_TYPE_HEADER: Final = "Content-Type"


class ContentType(StrEnum):
    JSON = "application/json"
    NDJSON = "application/x-ndjson"
    MARKDOWN = "text/markdown"
    PLAIN_TEXT = "text/plain"
    NDJSON_UTF8 = "application/x-ndjson; charset=utf-8"
    MARKDOWN_UTF8 = "text/markdown; charset=utf-8"
```

The UTF8 members retain the existing complete header values; base members are used where
the existing code checks the media type without parameters. These are not new response formats.

Approved query factory, retaining existing fields and validators on QueryResponseRecord:

```python
@classmethod
def from_query_request(
    cls,
    request: QueryRequestRecord,
    *,
    body: QueryResponse,
    ready_to_respond_at_unix_usec: int,
) -> Self:
    received = request.received_at_unix_usec
    if received is None:
        raise ValueError(Locale.QUERY_REQUEST_RECEIPT_TIME_MISSING)

    return cls(
        schema_version=request.schema_version,
        record_id=request.record_id,
        method=request.method,
        scheme=request.scheme,
        host=request.host,
        port=request.port,
        path=request.path,
        query=request.query,
        request_headers=request.request_headers,
        request_body=request.request_body,
        response_code=HTTPStatus.OK,
        response_headers={HTTP_CONTENT_TYPE_HEADER: ContentType.JSON},
        response_body=body.model_dump_json(),
        received_at_unix_usec=received,
        ready_to_respond_at_unix_usec=ready_to_respond_at_unix_usec,
        duration_usec=ready_to_respond_at_unix_usec - received,
        query_response_body=body,
    )
```

```python
# Existing Backend Locale:
QUERY_REQUEST_RECEIPT_TIME_MISSING: Final = (
    "Query request receipt time is missing"
)

# Store query operation; existing promise/error handling remains:
selected = QueryRequestRecord.model_validate(request, from_attributes=True)
snapshot = self._query_snapshot()
response = QueryResponseRecord.from_query_request(
    selected,
    body=snapshot,
    ready_to_respond_at_unix_usec=time.time_ns() // NANOSECONDS_PER_MICROSECOND,
)
```

Wire the same enum into P25's response helper, retaining all other arguments and behavior:

```python
def _response(
    request: requests.PreparedRequest,
    code: HTTPStatus,
    body: str = "",
    *,
    content_type: ContentType | None = None,
    headers: Mapping[str, str] | None = None,
) -> requests.Response:
    # Existing response assembly remains; its header assignment uses:
    # response.headers[HTTP_CONTENT_TYPE_HEADER] = content_type
    ...
```

Verification: existing real record/adapter/Store tests must retain the same wire codes,
headers, bodies and persistence behavior; cover query receipt time0 (valid) versus None
(error), exact response duration and continued read-only query behavior. Ruff/strict mypy
for affected paths. No source-string tests or relaxed assertions/prerequisites.

### P26 completion — 2026-09-19

Explicit named-field construction replaces P25 record dictionary merging in API/IPC/Store
and commit/validation/outcome readback. Query factory exactly follows the approved snippet;
receipt0 is valid, None returns the error promise. One ContentType enum/header constant
owns app headers; captured provider headers and synthetic/null durable headers unchanged.
Removed unused duplicate JSON media constant; only necessary direct test/helper imports
changed. No protocol rename, Store-state or retry-algorithm change.

Verification: feasible Backend API/Store/IPC/interceptor batch314passed,1existing skip,
4deselected183.80s; includes real persistence/replay/wire checks and query0/None duration
cases. Exclusions: subprocess lock, real Unix socket, two historical captures. Full configured
strict mypy PASS56files; changed-file Ruff PASS. An earlier identical test invocation's
terminal output was lost across compaction; its result is not claimed, so this batch was
rerun after that process exited. No browser/root/provider/live-Codex acceptance claim.

## P27 — COMPLETE: P25 literal audit and authoritative definitions

Exact narrow operator instruction:

> "1.1" literal has an authoritative global in vars. you must add, as another approved
> narrow scope addition, grep of all changes introduced in P25 for literal quot marks
> single and double and each must be really justified if inline. there needs to be balance:
> if this already exists in vars or locale, ofc use it. if it's truly globabl/reusable, put
> in vars or locale as appropriate. all text messages should ofc go to lcoale. this must
> be enforced.

Execution and acceptance, limited to that instruction:

- Grep/rg all changes introduced by P25 for both single- and double-quoted literals,
  including multiline/f-string forms; inspect both staged and unstaged changes and the
  affected surrounding code. Do not audit only exception messages or only the unstaged diff.
- For every occurrence, first check existing authoritative vars/locale definitions and
  reuse them when available. No duplicate constant or raw literal in their place.
- If a value is genuinely global/reusable and lacks an authoritative definition, place it
  in the appropriate existing vars.py or locale.py and wire the in-scope consumers to it.
  All text messages go to the appropriate locale.py. Preserve text and runtime behavior.
- Retain inline literals only with a concrete justification. Exercise balance: do not
  mechanically extract every quote into a global. Record audit coverage and the rationale
  for retained inline occurrences in WORK; identical uses may share a rationale only when
  it genuinely covers each occurrence. P27 is not complete until every occurrence is covered.
- Integrate with P26's ContentType enum, not a parallel media-type constant scheme. Preserve
  P25's HTTPStatus/ACK/NAK typing and all existing shared HTTP-record wire/schema contracts.
- Scope is P25-introduced changes and necessary definitions/imports/direct callpoints only;
  no unrelated repository-wide literal cleanup, behavioral redesign, compatibility fallback,
  new lint framework or source-string tests. Preserve operator staging/human-signed comments.

Confirmed authoritative definition: src/helpers/vars.py already declares
KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1. Import/use it in the affected construction and
validation paths; do not redefine it or change shared HttpRequestLogRecord behavior:

```python
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

# Named HTTP-record construction argument:
schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,

# Existing schema validation condition:
record.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
```

Recheck the changed literals after corrections and run affected Ruff/strict mypy and
existing relevant behavior tests. This is an enforced completion review, not a claim that
the earlier partial Locale migration already satisfied it.

### P27 audit checkpoint — scope and retained-literal rationale

Audited the entire P25 commit c4ef193 against its parent608f561 (the parent changes only
WORK/rollout capture), then both index and working-tree diffs. Index was empty. rg scanned
both quote forms (including f-string/multiline lines); AST string-span inspection additionally
mapped every P25-introduced occurrence to current code so moved/removed strings were not
missed. Broad current-diff inspection also identified later find/operator changes; those are
not a new P27 cleanup scope. No audit framework or source-string test was added.

P26 already removed dictionary-key construction/media duplicates. P27 reuses shared
KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1; common Backend vars now own GET/POST, pull/push
paths and Content-Length alongside P26's Content-Type. Direct consumers import those
constants from vars, including operator fixture callpoints (imports only; P31 unchanged).
Query record validation delegates to the existing QueryRequest.outbound_http route pair,
not a duplicate /query definition or circular IPC import. StandardizedSubmission discriminator
comparison has an authoritative Backend constant; its existing Literal schema stays literal.
Existing literal error/log messages introduced by P25 are already centralized in Backend
Locale (73 AST string occurrences); no translated/runtime wording changes were needed.

Retained production occurrences, exhaustively grouped by identical purpose:

| Location | Retained inline literals and justification |
|---|---|
| architecture.py | ACK/NAK Literal type members: Python typing requires literal values, not runtime constants. Promise docstring documents its contract. |
| IPC handlers | Eight empty-string operands are Requests/urlsplit absent-value normalization into existing validators, not fallback schema or operator text. |
| api.py new response/pull/reference helpers | Empty body/join identities and newline delimiters preserve transport framing; `detail` is the public error JSON key; `value` is the existing submission field key. SQL fragments SELECT/FROM/WHERE/ORDER/DESC/operators/separators and `$.request_body` are local query syntax with existing table/column constants, not new global identifiers. |
| Store | BEGIN TRANSACTION/COMMIT/ROLLBACK are the three literal DuckDB commands at the owning boundary; extracting SQL verbs does not add an application authority. `read_only` is the existing StoreMode value at its entry point (typed Literal remains authoritative). Query-only docstring documents capability. |
| request_response_records.py | Six `mode="after"` Pydantic decorator settings are third-party Literal API options. Empty request-body sentinel is protocol emptiness, not a message. |
| response_record_promise.py | ACK/NAK enum definitions are the authority; docstring and human-signed Annotated compatibility text stay attached to the contract. No `.value`/raw-string consumer comparison. |
| run_outcome_record.py | Three added serializer keys commit_record_id/validation_record_id/run_outcome_record_id are exact model/wire field names, intentionally inline in the authoritative serializer. |
| server.py | `app` is the ASGI scope key; `forbid` a Pydantic Literal config option; Flask app/thread identifiers are single-owner registration names; endpoint `run-outcome-` and slash-removal compose local route identifiers; `unix://` is Werkzeug's transport-address syntax; lifecycle docstring stays local. |

Test occurrences are independent synthetic inputs, boundary expectations, fixture/monkeypatch
symbol names and pytest parameter names—not operator-facing application messages. They remain
inline to avoid expected values being derived from the implementation under test. Specifically:
plugin10 occurrences (standalone /query request, pull/push fixture headers/routes, row-count SQL);
test_api P25's229 occurrences (ASGI schema/HTTP-version1.1—not HTTP-log schema—message fields,
controlled request/response payloads and URLs, fixture file paths, explicit monkeypatch names,
error/log expectations, domain-probe/snapshot SQL and disconnect/send-failure case labels);
test_backend_store66 (schema/header/status/route expectations, damaged-log and fsync/projection
injections, promise cancellation, read-only SQL/capability assertions); interceptor29 (provider
capture exclusion timing, exact route/validation/replay checks, SQL probes and error expectations);
IPC11 (Flask/OpenAPI route and request expectations, named lifecycle substitutions); browser2
(fixture docstring and CAS config key). The counts refer to the original P25 diff, not later
find/spacing/cleanup changes. Test strings that are schema keys/hooks are required library/
model names; injected errors and exact expected diagnostics deliberately do not become Locale
entries used by production. Necessary moved-constant imports were updated without changing
any assertion. P25 config/context/Dashboard snapshot/UI changes introduced no string literals.

Development corrections: the first targeted run83passed/2failed exposed an accidental import
list insertion in _http_header_value arguments; restored its exact two-argument call. Strict
mypy identified implicit reexports and an overbroad removal of the Dashboard request method;
fixed direct imports and restored the unchanged HTTP request call, without aliases/ignores.
These initial runs are failures, not completion evidence; fresh checks follow.

### P27 completion — 2026-09-19

Fresh Store/IPC/interceptor106passed,1real-socket deselected175.75s. Dashboard exact outcome
sender/query replacement4passed202deselected11.20s. Full Ruff PASS, strict mypy PASS56files,
diff whitespace PASS. No index edits. Test bytes (ASGI wire bodies/headers) were included in
the quote scan and remain independently pinned boundary payloads, like the test strings
above. No ACK/NAK raw-string comparison, shared HTTP schema change or compatibility alias.
At the P27 checkpoint only direct constant imports changed in operator helpers; P31 was
separate. Its subsequent implementation/verification is recorded below.
P27 is complete; move to P28 ownership/inheritance/rename only.

## P28 — COMPLETE: centralized request/response/body protocols

Exact narrow operator direction: specific request record properties inherit
BackendComponent.RequestRecordProperty and Protocol; apply the corresponding rule to
response records. Do not duplicate the common-base @implements on downstream classes.
All specific request/response properties and existing body properties belong directly
under BackendComponent for consistent ownership. Latest explicit operator correction:
RunOutcomeRecordProperty becomes RunOutcomeResponseRecordProperty and its concrete model
RunOutcomeRecord becomes RunOutcomeResponseRecord. This supersedes the earlier instruction
to retain P21's name; the existing model/contract is renamed, not duplicated.

Pre-P28 finding (corrected): Pull/Push/Query/RunOutcomeRequest protocols already inherited
the common base. P28 removed redundant Pull decorators, changed Commit/Validation bases
and moved the outcome protocol out of the port, as authorized below.

Approved implementation boundary:

- Keep common RequestRecordProperty/ResponseRecordProperty under BackendComponent, retaining
  their HttpRequestLogRecordProtocol and component-property bases.
- Every specific request record protocol inherits RequestRecordProperty plus Protocol;
  every specific response record protocol inherits ResponseRecordProperty plus Protocol.
  This includes existing synthetic CommitRecordProperty and ValidationRecordProperty as
  request records, and RunOutcomeResponseRecordProperty as the outcome response record.
  Preserve members/signatures and all other names; no duplicate response-record model.
- Keep only the specific record @implements on each concrete downstream model. Its protocol
  inheritance supplies the common contract. Retain required decorators on body implementations
  and other unrelated protocols; this is not removal of structural conformance checking.
- Centralize existing request/response/body protocols directly in BackendComponent. Apart
  from the explicit outcome response rename, keep existing names; update annotations,
  references/imports and downstream @implements together.
  No old-path aliases or duplicate definitions. In particular, move:

| Existing property location | Authoritative location |
|---|---|
| BackendComponent.ControlCentrePort.RunOutcomeRecordProperty | BackendComponent.RunOutcomeResponseRecordProperty |
| BackendComponent.ControlCentrePort.RunOutcomeResponseBodyProperty | BackendComponent.RunOutcomeResponseBodyProperty |
| BackendComponent.ControlCentrePort.QueryResponseProperty | BackendComponent.QueryResponseProperty |
| ControlCentreComponent.BackendPort.QueryRequestProperty | BackendComponent.QueryRequestProperty |
| ControlCentreComponent.BackendPort.RunOutcomeRequestProperty | BackendComponent.RunOutcomeRequestProperty |

- CommitRequestBodyProperty and ValidationRequestBodyProperty already reside directly under
  BackendComponent; retain that ownership. Existing body/client-request properties remain
  their existing contracts, not HTTP-record envelopes: do not invent HTTP fields or force
  a body/parameterless outbound QueryRequest to inherit a record protocol. Use the existing
  component-property base plus Protocol when moving a property out of a port.
- Rename the concrete model to RunOutcomeResponseRecord and update every direct producer,
  consumer, annotation, promise specialization, import, decorator and affected test. Do not
  retain aliases for either old name. Keep current module location and serialized field
  names (including run_outcome_records); this is a Python model/protocol naming correction,
  not a wire-format or lifecycle change.
- No unrelated port/domain-property relocation, concrete-model module move, protocol rename,
  wire/schema/default change, new abstraction or behavior change. This explicitly authorizes
  only the listed ownership/inheritance corrections, explicit outcome response rename and
  necessary direct callpoints/tests.

Representative approved shape (existing members omitted here remain unchanged):

```python
class BackendComponent(ComponentProtocol, Protocol):
    class RequestRecordProperty(
        HttpRequestLogRecordProtocol, ComponentProtocol.PropertyProtocol, Protocol,
    ):
        pass

    class ResponseRecordProperty(
        HttpRequestLogRecordProtocol, ComponentProtocol.PropertyProtocol, Protocol,
    ):
        pass

    class PullRequestRecordProperty(RequestRecordProperty, Protocol):
        pass

    class PullResponseRecordProperty(ResponseRecordProperty, Protocol):
        @property
        def pull_response_body(self) -> str: ...

    class CommitRecordProperty(RequestRecordProperty, Protocol):
        ...  # Retain all existing members.

    class ValidationRecordProperty(RequestRecordProperty, Protocol):
        ...  # Retain all existing members.

    class RunOutcomeResponseBodyProperty(ComponentProtocol.PropertyProtocol, Protocol):
        ...  # Retain all existing members.

    class RunOutcomeResponseRecordProperty(ResponseRecordProperty, Protocol):
        @property
        def run_outcome_request(self) -> BackendComponent.RunOutcomeRequestProperty: ...

        @property
        def run_outcome_response_body(
            self,
        ) -> BackendComponent.RunOutcomeResponseBodyProperty: ...

        ...  # Retain the other existing members.
```

Within the BackendComponent class body, unqualified nested base names above refer to the
same component-owned protocols. Downstream declarations become:

```python
@implements[BackendComponent.PullRequestRecordProperty]()
class PullRequestRecord(HttpRequestLogRecord):
    ...  # Existing implementation unchanged.

@implements[BackendComponent.PullResponseRecordProperty]()
class PullResponseRecord(HttpRequestLogRecord):
    ...  # Existing implementation unchanged.

@implements[BackendComponent.RunOutcomeResponseRecordProperty]()
class RunOutcomeResponseRecord(HttpRequestLogRecord):
    ...  # Existing implementation unchanged.

@implements[BackendComponent.RunOutcomeResponseBodyProperty]()
class RunOutcomeResponseBody(FrozenStrictModel):
    ...  # Existing implementation unchanged.
```

Apply the same ownership to QueryResponse/QueryRequest/RunOutcomeRequest conformance checks
and update Store promise/query-body annotations to the direct BackendComponent paths.
Verify with strict mypy/Ruff and existing affected record/adapter tests; no casts, type
suppressions, source-string tests or weakening of member signatures.

### P28 completion — 2026-09-19

Moved exactly the five approved protocols directly into BackendComponent, preserving their
members; commit/validation inherit RequestRecordProperty and outcome inherits
ResponseRecordProperty. Removed only redundant common Pull decorators; concrete bodies/client
requests/records retain specific @implements. All direct active producers/consumers/tests now
use RunOutcomeResponseRecord, no alias or module move; serialized run_outcome_records unchanged.
No old protocol path/name remains in active scoped Python. Human-signed promise comment preserved.

Strict mypy PASS56files; Ruff PASS; selected outcome/query/card contract tests18passed,
423deselected37.84s. Static review confirms every moved protocol has its downstream decorator
and correct inherited members. No runtime/lifecycle/persistence/default changes. P28 complete;
P29 follows as the rename-only step before P30 linkage changes.

## P29 — COMPLETE: original pull record ID naming

Operator authorized the narrow rename of Backend retry bookkeeping's run_id to
original_pull_record_id. This is the existing original_pull.record_id, NOT Dashboard's
UUIDv7 run ID or the Codex session ID. No new identifier or linkage contract is introduced.

Meaning verified in api.py: _original_pull_record starts with the commit's linked pull.
For a Markdown retry pull it follows the latest preceding projected commit's linked pull
recursively; _namekey_from_original_pull then requires the resolved initial-task record to
be HTTP200, NDJSON and nonempty, and checks its researcher identity at the caller. Retry
Markdown pulls are also HTTP200: status200 alone does not identify the original. Nor does
original mean the first-ever200 in the log: repeated initial-task pulls have distinct UUIDs,
and the commit's linked pull determines which is used. This describes the current code,
not the desired P30 contour: P29 itself is only a rename, but the later P30 explicitly
supersedes retaining this heuristic and authorizes re-hooking its related machinery.

Exact narrow change boundary:

- In src/backend/api.py rename CODEX_RETRY_RUN_ID_COL to
  CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL and its column value from run_id to
  original_pull_record_id in both CODEX_RETRY_BASELINE_TABLE and CODEX_EVIDENCE_AUDIT_TABLE.
  Update all direct DDL/insert/select/returning/filter references through the constant.
  Preserve types, constraints, values and retry grouping/evidence behavior.
- Rename run_id_text to original_pull_record_id_text in _process_retry_attempt.
  Rename corresponding Backend test helper arguments, fixture constants/locals and direct
  assertions/import references where they denote this pull UUID. Leave unrelated run IDs
  untouched. Existing original_pull record-object arguments already describe their content.
- No Dashboard run-event/queue/storage/protocol changes, new backend-disclosed Dashboard ID,
  replay-log wire change, runtime identifier generation change or broader naming cleanup.
- Current schema only: no old-column alias, migration, fallback or automatic DB repair.
  Existing explicit --new/replay machinery remains the way to build the current schema.

Approved rename shape (existing surrounding logic remains):

```python
CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL = "original_pull_record_id"

# In _process_retry_attempt:
original_pull_record_id_text = str(original_pull.record_id)
```

Wire the renamed column constant and local through their existing SQL/parameter callpoints;
no SQL algorithm rewrite under P29 alone (P30's explicit linkage rewiring is additional).
Verify existing synthetic retry-baseline/evidence tests and affected
Ruff/strict mypy checks. Historical capture fixtures remain unexecuted/inaccessible. Check
that Backend retry references no longer use the misleading name, without renaming legitimate
Dashboard run_id fields. Status: implemented and verified; evidence below.

### P29 completion — 2026-09-19

Renamed the column constant/value in both retry tables, every SQL callpoint and local
original_pull_record_id_text. Backend test helper parameters/fixture constants (including
historical fixture names, not execution) and the baseline-isolation test name now describe
the actual original pull UUID. Values, constraints, grouping and evidence rules unchanged.
No Backend retry run_id/CODEX_RETRY_RUN_ID_COL reference remains; Dashboard run_id untouched.
No alias/migration/recovery. Nine synthetic retry/baseline checks passed,203deselected11.32s;
configured mypy PASS2changedfiles; Ruff PASS. P29 complete before P30 boundary review.

## P30 — COMPLETE: Store-owned records, initial validation, session outcome linkage and persistence independent of validity

Approval sequence: operator specified explicit pull -> commit -> validation linkage, a
session-scoped outcome with Session-ID confirmation and a completed-only ETag handshake,
and outcome-response-record innerdict metadata. Operator then corrected ownership: current
records belong to Backend Store, not API globals; expose actual model instances, not just
UUIDs, by reference without deepcopy. Assistant restated persist/fsync -> DB projection ->
typed DB readback before exposure; operator approved recording this shape. Latest explicit
addition: original_pull_record_id and its related machinery must be re-hooked to this model
in this same P. Status: implemented and locally verified, including the approved addition below.

### Current record ownership and access

- Full Store owns current_pull_record, current_push_record, current_commit_record and
  current_validation_record. Each is a read-only property returning the actual typed record
  instance or None when absent; no detached/deep-copied object and no parallel API globals.
- Store replaces the corresponding state as records pass through the common live/replay
  processing path. Preserve the approved ordering: persist/fsync, project, construct the
  typed DB-readback record, then expose that instance. Never expose an unpersisted input
  as authoritative, or leave an aborted projection exposed as successfully applied state.
  Replay does not append/fsync again; it consumes the existing durable log into the same
  projection/readback/state-update logic. No extra replay/recovery contour.
- API/IPC consume references; they do not own/update these four slots. Existing four Store
  operations remain; these four read-only properties are the explicit narrow extension to
  P25's full-Store surface. Query-only wrapper still exposes only query.
- Initial absence is None, not a fabricated record. The approved addition below also maintains
  the distinct first-validation reference. Preserve current initialized session
  identity: old-session records must not silently become a new session's commit/validation.
  No duplicate context/service, mutable public setter or new record-ID generation scheme.
- Preserve the accepted push's captured pull reference and the actual accepted push while
  processing it. Later/interleaved pulls or rejected pushes must not silently change that
  commit's inputs merely because a current-record slot was subsequently updated.

The preceding chat named these four properties and their behavior but contained no fenced
Python block. Do not claim an earlier verbatim code approval that did not occur. The snippet
below spells out that agreed reference-returning shape using existing persisted-record types;
pull/push are HTTP-log envelopes, not a fabricated completed PushResponseRecord requiring
commit/validation before those exist. Necessary FullStoreProperty annotations mirror these
through existing HTTP/commit/validation protocols; use @implements and no cast/type weakening.

```python
# Additions inside AiAugmentBackendStore; existing lifecycle/operations remain.
_current_pull_record: HttpRequestLogRecord | None = PrivateAttr(default=None)
_current_push_record: HttpRequestLogRecord | None = PrivateAttr(default=None)
_current_commit_record: BackendCommitRecord | None = PrivateAttr(default=None)
_current_validation_record: BackendValidationRecord | None = PrivateAttr(default=None)

@property
def current_pull_record(self) -> HttpRequestLogRecord | None:
    return self._current_pull_record

@property
def current_push_record(self) -> HttpRequestLogRecord | None:
    return self._current_push_record

@property
def current_commit_record(self) -> BackendCommitRecord | None:
    return self._current_commit_record

@property
def current_validation_record(self) -> BackendValidationRecord | None:
    return self._current_validation_record
```

This is the accessor/storage shape, not permission to bypass the existing lock, transaction,
mode or readback rules. Wire assignments into the owned common processing path, not into
these getters or the adapters; no catch-up projection from a getter.

### Explicit session, commit/validation and completed handshake

- Commit contains the latest served pull selected for the accepted push and that accepted
  push; validation identifies that exact commit UUID. Outcome concerns the current Codex
  session, not Dashboard's local run UUID and not an independently guessed retry group.
- RunOutcomeRequest retains its outcome path and NameKey header; add Session-ID, and check
  both supplied identities against the running Backend session/researcher. Dashboard passes
  its known Codex session ID, not its Dashboard run ID; manual callers must confirm likewise.
- Simplify/remove _run_outcome_references' historical scans: use Store's current commit and
  validation instances, verify their persisted counterparts and the exact validation.commit_id
  == commit.record_id linkage. No latest-by-name/session SQL guessing or replaying side effects
  merely to choose records. Replay checks the recorded explicit links in ordered Store state.
- For /completed, require ETag in RunOutcomeRequest. /pull410 alone supplies ETag equal to the
  UUID of the persisted validation on which that410 is based; no ETag on200/503/other pulls.
  Dashboard's existing single ordinary post-exit pull captures this ETag and forwards it in
  /completed. Backend compares it with current_validation_record.record_id and requires the
  matching accepted validation/commit. Preserve actual HTTP header encoding consistently;
  compare parsed UUIDs, not loose string/enum coercions.
- Latest required-header/persistence clarification supersedes the earlier pre-persistence
  exception direction: invalid/missing client identity or completed ETag selects an actual
  BAD_REQUEST exchange, which is persisted and returned without materialization. NAK remains
  the IPC request-persistence policy, not its HTTP outcome. The response is not an accepted
  domain result. Genuine storage/projection/reference-verification failures still resolve
  (None, BackendStoreException). No fabricated IDs, guessed references or silent fallback;
  retain existing ResponseRecordPromiseResult, not a parallel result class.
- /failed and /cancelled still support legitimately absent commit/validation records;
  present-but-inconsistent references are errors. Cancellation does not require accepted
  validation or the completed ETag. Preserve the separately approved domain200/409 and
  evidence-capture500 behavior except where these explicit identity/linkage checks apply.
  Missing session data must remain honestly missing in the persisted record. The latest
  operator clarification below removes the proposed permission gate on persistence; no
  fabricated ID or omission of an invalid/partial outcome from the log.
- Retain NAK for outcome request persistence; required outcome response persistence precedes
  successful completion. Server gate/client-timeout tolerance and Dashboard one-pull503=>failed
  behavior stay unchanged. No extra pull/query, retry or automatic outcome reclassification.

The earlier approved link check below pins the inconsistency condition, not a surviving
pre-persistence raise. Under the latest clarification, response selection records an error
exchange first; full DB-reference verification follows append/fsync. Storage/projection
errors use (None, exc), while recorded client rejection is an actual error response:

```python
commit = store.current_commit_record
validation = store.current_validation_record
if validation is not None and (
    commit is None
    or validation.validation_request_body.commit_id != commit.record_id
):
    raise BackendStoreException(Locale.RUN_OUTCOME_VALIDATION_LINKAGE_CORRUPT)
```

This check does not replace the separately required session/NameKey, completed acceptance
and ETag checks, or the durable DB-readback requirement above.

### Innerdict metadata and original-pull/retry rewiring

- Replace commit-ID/commit-request-body-centric innerdict metadata with
  ktp.ai_augment_run_outcome_response_record containing the FULL serialized
  RunOutcomeResponseRecord: envelope, request headers, response body, record UUID and other
  current HTTP-log fields, not just the body or a second hand-assembled summary.
- Store persists/projects the outcome and materializes this field in the outcome transaction.
  Update only the necessary innerdict model/protocol, query snapshot validation/serialization,
  record consumers and card field wiring. Keep other researcher/evidence/result data intact.
  DOCX/TXT/card remains a dumb innerdict renderer, with no transient enrichment or extra IPC.
  No old metadata/schema alias, alternate parser, migration or fallback.
- Full outcome serialization identifies its exact commit/validation/pull/push/session and
  log/CAS evidence; it is not an embedded copy of every earlier retry/provider response.
  Do not silently imply that a reference-only outcome embeds the full evidence archive.
- Explicit latest addition: re-hook original_pull_record_id and dependent retry baseline/
  obligation/evidence bookkeeping to this Store-owned record/session model and explicit links.
  P29's rename remains; P30 supersedes preserving _original_pull_record's Markdown detection
  plus latest-preceding-commit scan. Do not retain that heuristic as a fallback or introduce
  a second parallel run identifier. Keep existing retry evidence rules and actual record
  UUIDs, and preserve live/replay agreement through the same Store processing path.
- The root link must follow authoritative captured relationships, not another researcher's
  or session's nearest record. Current record pointers alone must not erase ancestry needed
  by retry checks. Any further wire field, new root-selection policy or change in innerdict
  cardinality not specified here requires a concrete proposal/approval before implementation;
  do not invent it while implementing the required rewiring.

Exact agreed new innerdict key, defined once alongside existing Backend column constants:

```python
KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_RECORD_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}run_outcome_response_record"
)

# Value stored through the existing innerdict projection is the whole record:
outcome.model_dump_json()
```

Reuse P26 content types, P27 authoritative header/schema constants and Locale text, and P28's
RunOutcomeResponseRecord/Property names. Preserve P25 grouped durability/ACK timing and raw
HTTP history. This item does not authorize removing attempts/audit tables, replay-log records,
provider captures, existing evidence validation or unrelated UI/storage/queue behavior.

### Narrow implementation boundary and verification

Files: Store, API, IPC/server direct transport/ETag callpoints; protected architecture/Backend
vars/Locale; existing run-outcome request/response and innerdict/query/snapshot models; Dashboard
single-pull/outcome sender and pure-card metadata consumers; corresponding existing tests only.
No new public Store operation, unrelated context refactor or ordinary task changes.

Use real synthetic Store/log/DB and in-process adapters to verify: reference-returning getters
and None state; durable/readback timing and failed processing; live/replay agreement; captured
pull/push stable across interleaved requests; matching and mismatched session/NameKey/linkage;
ETag only on410, forwarded on completed, missing/wrong ETag failure; failed/cancelled legitimate
absence; full outcome envelope roundtrip in query/innerdict and unchanged dump-only export;
retry chains with repeated pulls and other-session records, no historical-nearest inference.
Update affected direct callpoints and run Ruff/strict mypy. No source-string assertions,
mocked replacement of the tested persistence boundary, skipped prerequisites or network calls.

P30 supersedes only the earlier API-global current-record ownership, historical outcome/root
selection and commit-centric innerdict metadata instructions. P25–P29 are complete. Unresolved operator acceptance boundaries remain separate, with
P31 including its approved UUID amendment is complete and locally verified below.

### P30 clarification — persistence is independent of application validity

Latest operator instruction (supersedes the prior missing-session question/proposal):

> persistence of run outcome should in no way depend on its validity. it should persist
> in log at all times. this also goes for pull an push and validate and commit. they must
> be persist whenever at all possible. so we must never gate the persistence.

Further explicit clarification: clients MUST submit both NameKey and Session-ID. Missing,
malformed or mismatched identity headers affect the actual Backend response, not durable
capture. There is NO both-None identity acceptance exception. Resume P30 implementation
under this rule; retain the actual error exchange and no fabricated identity. A completed
outcome still additionally requires the validation ETag. The former persistence question
is resolved, not a remaining approval prerequisite.

The Assistant wrongly conflated domain acceptance/identity confirmation with eligibility
for durable capture. Withdraw the proposed missing-session persistence exception and its
approval request. No permission is needed to preserve an invalid/partial exchange; missing
or mismatching session information is data/error to record, not justification to omit it.
This does not mean accepting invalid input for derived output/materialization, inventing
missing IDs or returning a successful domain result. No special both-None authentication
exception was approved by this clarification; none is silently introduced.

Pre-P30 gaps now corrected: IPC rejected wrong NameKey before Store; outcome DB reference
verification preceded append; API Store inputs performed application validation before durable
capture. Current code captures nullable parsed identity while retaining raw invalid headers/
bodies, selects the actual error exchange, appends/fsyncs before reference verification, and
validates available base HTTP envelopes before route-specific application. Commit/validate
invalid-envelope regressions prove fsync precedes domain rejection. Structural impossibility
or real append failure remains an error, never invented data or a false persistence ACK.

Required interpretation for continuing the narrowly approved work:
- Capture and append/fsync each available HTTP-log envelope independently of domain validity,
  retaining the actual request, available data and failure/partial response where applicable.
- Domain rejection may prevent accepted projection/materialization and may return the existing
  error result, but must not prevent preserving the exchange whenever serialization/storage
  permit it. An append/fsync failure remains a real failure, never a fabricated persistence ACK.
- Preserve existing record contour: complete pull/push exchanges, synthetic commit/validate
  records and complete outcome response exchange; no duplicate request-only outcome record.
  Outcome request acknowledgment remains NAK; query remains read-only/unlogged.
- Keep shared HTTP-log v1.1 schema unchanged; application validators must not be confused
  with whether the actual available HTTP envelope can be durably serialized. No old schema,
  fallback/recovery, fabricated commit/validation/session or unrelated redesign.
- P30's existing identity/linkage/ETag checks still determine domain acceptance. Necessary
  ordering/capture changes must preserve failure history before reporting those errors.
  Add upstream checks for missing/mismatched identities and failed application validation:
  assert actual durable log bytes/fsync/history, separately from error/materialization.

P26–P30 are completed; the former persistence blocker is withdrawn,
not implemented via a nullable-session acceptance exception. P31 including its approved UUID amendment is complete and locally verified below.

### P30 approved addition — initial-validation ancestry and typed validation inputs

The proposed original_pull_record_id addition to CommitRequestBody/PushRequestRecord was
NOT approved or implemented and is superseded by the operator's2026-09-20 direction below.
Do not add that field. Existing retry baselines/audits use the initial pull UUID, but the
operator instead supplies explicit ancestry through the first validation's commit/push/pull.

Exact operator-provided model shape, including the subsequently approved nullable initial
validation reference:

```python
@implements[BackendComponent.ValidationRequestBodyProperty]()
class ValidationRequestBody(FrozenStrictModel):
    commit_record: BackendCommitRecord
    post_commit_validation: PostCommitValidation
    initial_validation_record: BackendValidationRecord | None
    openalex_ror_records: tuple[HttpRequestLogRecord, ...] = ()
```

Operator also directs moving submission_type into PostCommitValidation and post-commit
validation-related definitions into validation_event.py. Store retains the FIRST validation
record successfully persisted, projected and reconstructed from DB, never replacing it
during that Backend lifecycle. This is distinct from current_validation_record, which advances.
The shared live/replay application mechanism establishes it regardless of accepted/rejected
domain result, not from a speculative validation. Later validations explicitly reference it;
retry machinery can follow initial validation -> commit -> original push/pull without the
Markdown/nearest-commit heuristic or an extra original-pull field on commits.

Operator explicitly approved documenting this exact flow/scope/snippets and continuing
implementation to completion, stopping only for an unexpected scope blocker.
Operator explicitly confirmed the nullable type: BackendValidationRecord | None, with None
ONLY on the first validation record. Keep this a required field with an explicitly supplied
None, not a missing-field default, fabricated record or recursive self-reference. This settles
the initial-record construction detail. Do not invent further unspecified changes to the
shape. The full serialized submission remains captured alongside submission_type in
PostCommitValidation, as included in the approved flow:

```python
@implements[BackendComponent.PostCommitValidationProperty]()
class PostCommitValidation(FrozenStrictModel):
    stage: BackendLifecycle
    result: BackendLifecycle
    detail: StrictStr | None = None
    submission_type: Literal["Submission", "StandardizedSubmission"] | None
    submission: dict[str, JsonValue] | None
```

Move the existing validation model/validators and their necessary imports from commit_event.py
to validation_event.py. Update the existing component protocols and direct constructors/
consumers/tests together; no old import aliases, old-body parser or discriminator inference.
Typed commit/provider/initial-validation inputs must roundtrip through the current serialized
validation body and be checked against Store-owned persisted records. Reuse the existing
commit DTO serialization primitive for its HTTP envelope/pull/push/session; the initial
validation's HTTP envelope carries its complete body. No extra original-pull field on commits,
new record UUID or duplicate top-level replay entry. This is a self-contained typed validation
body, not an invented request transport or a change to shared HTTP-log v1.1.

Approved state rule, expressed with the existing Store model/readback convention:

```python
_initial_validation_record: BackendValidationRecord | None = PrivateAttr(default=None)

@property
def initial_validation_record(self) -> BackendValidationRecord | None:
    return self._initial_validation_record

# After successful common projection and typed DB readback:
if self._initial_validation_record is None:
    self._initial_validation_record = validation
self._current_validation_record = validation
```

The first stored validation has initial_validation_record=None; later validation construction
uses the retained initial instance. Failed projection must not leave an authoritative initial
slot populated. Full Store protocol mirrors the accessor; query-only capability is unchanged.
Explicit replay uses the serialized initial link/None boundary to reproduce each lifecycle;
the first validation of the entire multi-lifecycle log is not every lifecycle's root. No
nearest-record/session guessing. New live Backend lifetime starts with absent current/initial
state; mere resume verification does not restore a previous lifetime's active state.

Retry baseline/audit rules and stored pull UUIDs stay; replace heuristic root selection with
the directly linked pull of initial_validation_record.commit_record (or the current commit's
pull for the first validation). A rejected/configuration-error first validation still anchors
the lifecycle; do not silently choose the first accepted/evidence-rejected validation instead.
Necessary Store/API/DTO/protocol/query/fixture changes are part of this P30 addition, no P31
harness behavior or ordinary task edits. Verify initial None, immutable initial vs advancing
current state, failed projection, repeated pulls, live/replay multi-validation and lifecycle
boundaries, exact serialized inputs and unchanged retry obligations/materialization.

### P30 execution evidence and completion — 2026-09-20

Store current-record getters/common projection/rollback restoration, API-global removal,
IPC capture from Store, required-identity/ETag error responses, full outcome innerdict
metadata and Dashboard single-pull ETag forwarding are wired. Invalid identities produce
persisted BAD_REQUEST history and no materialization; query retains those raw histories
without treating them as accepted session outcomes. Error-response handling is not a nullable
identity acceptance exception. Explicit outcome links replace historical outcome scans.
Retry ancestry now uses the approved initial-validation link; the former Markdown/nearest-commit
heuristic is removed, with no new original-pull field on commits.

Affected synthetic fixtures/assertions have been migrated to actual Store state/new metadata;
no compatibility aliases. First focused batch stopped with8passed490deselected179.38s because
an accidentally nested workflow lock deadlocked accepted push; corrected by capturing state
under the existing lock and calling the separately locking response decision outside it,
without an intervening await. This is failed development evidence, not a pass. First strict
mypy check29errors then4errors were stale test callpoints/signatures plus one accidental
probe return replacement; corrected. Fresh focused rerun77passed490deselected128.76s: all three outcomes x complete/partial
capture x eight identity cases (matching, absent/malformed/wrong NameKey or Session-ID,
absent Backend session); exact durable log/DB/readback, query and independent replay equality,
no materialization for invalid identities. Includes API state/push/capture, Dashboard
single-pull/cancellation and pure-card cases. Strict mypy PASS56files and Ruff PASS. A broader pre-addition batch stopped at386passed/1existing skip/104deselected/5failed303.23s:
missed fixture/callpoint adaptations, not passes. Reused the initialized runtime fixture;
updated typed current-slot response-policy unit fixtures and tuple-returning Dashboard
finalizer doubles. Corrected/new capture selection42passed493deselected66.56s. The response-
policy unit test injects current slots; it is not claimed as real persistence coverage.

2026-09-20 initial-validation addition: moved PostCommitValidation to validation_event.py,
including submission discriminator/payload; body holds the approved typed records, serializes
through existing commit DTO and complete initial/provider HTTP envelopes, and checks these
against persisted DB counterparts. Store exposes an immutable initial reference separately
from latest; common projection/readback advances it only after a successful group. Explicit
None roots preserve recorded lifecycle boundaries during replay. Removed the original-pull
Markdown/nearest-commit heuristic; retry tables retain their actual pull UUID via the initial
validation's exact commit link. No new commit wire field or compatibility alias. Updated
necessary query/body/protocol/test callpoints; removed touched DTO's old discriminator guess.

Initial migration mypy77errors (including a missed StrictStr import and prior request-body
protocol annotation) corrected; intermediate mypy56files passed. Focused current validation/
response-policy/provenance selection46passed273deselected18.49s. Broader five-module feasible
regression completed491passed/1existing skip/104deselected/1failed397.37s. Includes all outcome
identity/ETag/raw-history, live/replay, grouped push, retry/provider, initial-validation and
pure-card checks. Sole failure: existing readiness-test response double lacked headers now
read for ETag. Added its empty typed header map; unchanged assertion/timeout passed in the
follow-up below. Do not represent the initial batch as wholly green.

Follow-up7case selection:5passed/2failed25.88s. Passed readiness correction, two actual Store
projection-failure cases and repeated multi-lifecycle replay; the two failures were incorrect
new test exception expectations (ReplayInputMissing, not ValueError). Corrected only those
expected exception classes; all3altered-initial/commit/provider-input cases then passed10.83s,
proving the actual envelope remains logged while bad inputs neither advance initial/current
state nor leave rejected projection rows. No weakened body/state/log assertions.
Standalone real completed-query/browser-fixture preparation passed1test22.63s, without
launching Chrome or sockets. The initial mypy snapshot-inference issue was fixed with an
explicit snapshots list; final strict mypy PASS56files, full detour/shared-record Ruff PASS
and diff whitespace PASS. Test batches overlap and are not an additive total.

P30 is COMPLETE. Current active API/IPC globals/root-guessing paths are removed; specific
protocols retain downstream @implements; enum/constants/Locale and explicit model construction
remain wired; no casts, new suppressions, schema aliases/fallbacks or ordinary task/index edits.
Historical fixture callpoints were updated for current outcome metadata but not executed or
accessed. Main/shared HTTP schema, pasted models, server admission, renderer and P31 harness
behavior are unchanged. P26–P30 are implemented in the approved order. Real provider/network,
Chrome, privileged watcher and production pre-commit-operator acceptance were not rerun here;
P31 including its approved UUID amendment is implemented; fresh verification is recorded separately below.

## P31 — COMPLETE: approved implementation and UUID amendment locally verified

2026-09-20: operator explicitly approved P31 within the EXACT documented shape below.
P26–P30 are complete. P31 code and the separately approved test-only UUID correction are applied.
The approved proposal replaced the earlier broad description; its snippets are preserved. Preserve the actual
failure/recovered-artifact evidence above. No production, task, timeout, CSS, cleanup-policy,
schema or ordinary-wrapper changes; no new harness service/module or compatibility path.

Files: protected/tests/operator/test_operator_e2e.py and its existing preflight module;
protected/tests/pytest_plugin.py only the completed-query fixture; existing
tests/control_centre/test_ui_e2e.py. Necessary imports only. No new casts/suppressions.

### 1. Strict current HTTP history and explicit links

Add one private assertion helper in test_operator_e2e.py, called by the EXISTING artifact
validator in place of its stale route-only assertion. Import BackendValidationRecord and
VALIDATE_PATH from validation_event; import the unchanged pasted model module as
submission_models for its authoritative endpoint constants; UUID from uuid.

```python
def _validate_workflow_http_records(
    records: Sequence[HttpRequestLogRecord],
) -> dict[UUID, BackendValidationRecord]:
    by_id = {record.record_id: record for record in records}
    assert len(by_id) == len(records), "Duplicate HTTP record UUID"
    ordinal = {record.record_id: index for index, record in enumerate(records)}
    validations: dict[UUID, BackendValidationRecord] = {}
    provider_ids: set[UUID] = set()
    provider_endpoints = {
        (HTTP_GET_METHOD, submission_models.OPENALEX_SCHEME,
         submission_models.OPENALEX_HOST, submission_models.OPENALEX_INSTITUTIONS_PATH),
        (HTTP_GET_METHOD, submission_models.ROR_SCHEME,
         submission_models.ROR_HOST, submission_models.ROR_ORGANIZATIONS_PATH),
    }
    for record in records:
        if (record.method, record.path) != (HTTP_POST_METHOD, VALIDATE_PATH):
            continue
        validation = BackendValidationRecord.from_http_request_log_record(record)
        validations[record.record_id] = validation
        body = validation.validation_request_body
        commit = body.commit_record
        references: tuple[HttpRequestLogRecord, ...] = (
            commit,
            commit.commit_request_body.pull_record,
            commit.commit_request_body.push_record,
            *body.openalex_ror_records,
        )
        if body.initial_validation_record is not None:
            references += (body.initial_validation_record,)
        for linked in references:
            assert linked.record_id in by_id, linked.record_id
            assert linked.model_dump() == by_id[linked.record_id].model_dump(), linked.record_id
            assert ordinal[linked.record_id] < ordinal[record.record_id], linked.record_id
        for provider in body.openalex_ror_records:
            parent, _, identifier = provider.path.rpartition("/")
            assert identifier and (
                provider.method, provider.scheme, provider.host, parent
            ) in provider_endpoints, provider.record_id
            provider_ids.add(provider.record_id)

    local_routes = backend_api.AUTHORITATIVE_FASTAPI_ROUTES | {
        backend_api.AUTHORITATIVE_COMMIT_ROUTE,
        (HTTP_POST_METHOD, VALIDATE_PATH),
        *((HTTP_POST_METHOD, path) for path in run_outcome_models.RUN_OUTCOME_PATHS),
    }
    unexpected = [
        (record.record_id, record.method, record.host, record.path)
        for record in records
        if (record.method, record.path) not in local_routes
        and record.record_id not in provider_ids
    ]
    assert not unexpected, unexpected
    return validations
```

In validate_workflow_artifacts, replace only the route assertion with
`validations = _validate_workflow_http_records(records)`. Existing schema/UUID, DB attempt,
single accepted commit, CAS/hash/appendwatch and response checks remain. After constructing
validated_run_outcome/run_outcome_snapshot, add the current-link assertions:

```python
outcome_ordinal = _record_ordinal(records, run_outcome_record.record_id)
preceding_records = records[:outcome_ordinal]
latest_pull = next(
    record for record in reversed(preceding_records)
    if (record.method, record.path) == (HTTP_GET_METHOD, PULL_PATH)
)
latest_push = next(
    record for record in reversed(preceding_records)
    if (record.method, record.path) == (HTTP_POST_METHOD, PUSH_PATH)
)
assert run_outcome_snapshot.pull_record_id == latest_pull.record_id
assert run_outcome_snapshot.push_record_id == latest_push.record_id
assert run_outcome_snapshot.commit_record_id == commit_record.record_id
assert run_outcome_snapshot.run_outcome_record_id == run_outcome_record.record_id
assert run_outcome_snapshot.validation_record_id is not None
assert run_outcome_snapshot.validation_record_id in validations
validation = validations[run_outcome_snapshot.validation_record_id]
assert validation.validation_request_body.commit_record == commit_record
assert validation.validation_request_body.post_commit_validation.result is BackendLifecycle.ACCEPTED
assert commit_ordinal < _record_ordinal(records, validation.record_id) < gone_pull_ordinal
assert backend_api._http_header_value(
    gone_pull.response_headers, ETAG_HEADER,
) == f'"{validation.record_id}"'
outcome_request = validated_run_outcome.run_outcome_request
assert outcome_request.session_id == session.session_id
if outcome_request.run_outcome is RunLifecycle.COMPLETED:
    assert outcome_request.validation_record_id == validation.record_id
```

All these checks apply to this existing completed-workflow validator, not to general failed/
cancelled histories. No accepted/rejected policy is changed. Provider responses need not be
HTTP200: preserve failure responses too; eligibility here is endpoint plus exact persisted link.

### 2. Capture actual ready card and inspect current outcome metadata

Replace the footer selector/nonempty wait inside capture_completed_researcher_card only:

```python
card = page.get_by_test_id(control_ui.CARD_MARKDOWN_TEST_ID)
expect(card).to_contain_text(commit_record_id)
expect(page.get_by_test_id(control_ui.DOWNLOAD_CARD_DOCX_TEST_ID)).to_be_enabled()
card_text = card.inner_text().strip()
```

Preserve its empty-card check, browser-error assertion, browser close/finally and timeouts.
In validate_workflow_artifacts replace only its old commit-request-body card block:

```python
# Imports: lxml.html.fromstring and nicegui.elements.markdown.prepare_content.
# Both dependencies are already installed/declared; existing pytest isolation precedes imports.
if card_text is not None:
    expected_html = prepare_content(
        validated_run_outcome.model_dump_json(), extras="fenced-code-blocks tables",
    )
    expected_text = fromstring(expected_html).text_content().strip()
    metadata_position = card_text.index(KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_RECORD_COL)
    outcome_position = card_text.index(expected_text)
    assert metadata_position < outcome_position
```

This requires the rendered counterpart of the FULL current serialized envelope, not merely
three matching UUID strings. Browser inner_text is not raw Markdown: a read-only markdown2
probe confirmed underscores in nested JSON keys can become emphasis, so direct raw-JSON
substring comparison would be invalid. Use NiceGUI's existing converter/default extras and
already-declared lxml only for HTML text extraction. This does not certify raw JSON survives
HTML rendering byte-for-byte or alter/repair production rendering. Source Markdown/TXT remains
unchanged. Use the existing Backend vars constant; no invented old fields or new dependency.

### 3. Retained unique operator run directory

This records the historical P31 approval. P36 now replaces this fixture's allocation with
the marker-selected tmp_path; do not restore the historical direct mkdtemp below.

Replace only the operator_runtime fixture (remove tmp_path argument and separate /tmp
TemporaryDirectory). Existing _operator_runtime, child launch/cleanup and preservation guard stay:

```python
@pytest.fixture
def operator_runtime(repository_root: Path) -> Iterator[OperatorRuntime]:
    artifacts_root = repository_root / "tmp"
    artifacts_root.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="operator-test.", dir=artifacts_root))
    _operator_log(f"Operator run directory (preserved): {run_dir}")
    dashboard_socket_path = run_dir / "dashboard.sock"
    if len(os.fsencode(dashboard_socket_path)) >= DARWIN_AF_UNIX_PATH_CAPACITY_BYTES:
        raise RuntimeError("operator dashboard socket path exceeds Darwin AF_UNIX capacity")
    yield _operator_runtime(
        run_dir,
        repository_root=repository_root,
        dashboard_socket_path=dashboard_socket_path,
    )
```

Existing constructors already derive config/DB/replay/CAS/output and NiceGUI child storage
from this run directory; source remains a symlink to the readonly source DB. Artifacts stay on
success/failure. Expected host socket path88bytes fits existing104byte guard. No alternate
system-temp location, global basetemp change, new cleanup or production storage access.

### 4. Exact upstream coverage boundary and fixture additions

The fixture snippet below includes the latest approved header-case correction; its originally
approved LOCATION_HEADER.lower() was the test-fidelity defect documented above. All other
P31 fixture behavior and outcome UUID assertions remain unchanged.

Reuse completed_query_files and the shared named completed_query_fixture_process. The fixture
already persists a real synthetic accepted commit/validation/outcome and CAS through Store,
but omits the push Location header and final410. Add only the following before outcome:

```python
# Existing persisted_http_record(...) construction of the accepted push:
response_headers={LOCATION_HEADER: PULL_PATH},

# Immediately after the fixture's existing successful _validate_commit assertions:
assert validated.submission is not None
lines = [api.json_line(validated.submission.normalized_values())]
if validated.ground_truth_innerdict is not None:
    lines.append(api.json_line(api.select_columns(validated.ground_truth_innerdict.data)))
gone_pull = store._append_authoritative_record(persisted_http_record(
    record_id=uuid7(),
    method=HTTP_GET_METHOD,
    path=PULL_PATH,
    response_code=HTTPStatus.GONE,
    response_headers={
        HTTP_CONTENT_TYPE_HEADER: ContentType.NDJSON_UTF8,
        ETAG_HEADER: f'"{validated.validation_record.record_id}"',
    },
    response_body="".join(lines),
))

# Existing RunOutcomeResponseBody construction uses the final persisted pull:
pull_record_id=gone_pull.record_id,
```

Use existing fixture helpers/constants (necessary local imports); no provider network call,
live Codex, inline subprocess script or mocked persistence. Existing repin/storage setup stays.

- Preflight: reuse existing completed_query_files/startup_files fixtures by import; construct
  OperatorRuntime exactly as the existing browser test does from its closed query-only
  Store engine/config/replay/CAS. Call real validate_workflow_artifacts with STARTUP_NAMEKEY
  and completed path. This is a nonbrowser python_subprocess-marked test. No Store mock.
- Parameterized cheap tests call the NEW assertion helper with real typed synthetic records:
  no providers, linked OpenAlex/ROR, later validation linked to initial; reject unknown route,
  unreferenced provider, missing/changed provider, wrong provider endpoint, missing/changed
  embedded commit/pull/push/initial, reversed reference order and duplicate UUID. These test
  the actual helper used by the full validator, not source strings or a replacement parser.
- Card: in existing test_completed_grid_row_uses_real_query_ipc, after its current Playwright
  context closes but before running_dashboard exits, call the ACTUAL existing capture helper:

```python
card_text = operator.capture_completed_researcher_card(
    dashboard, runtime, namekey=ui_tests.STARTUP_NAMEKEY,
    queued_at_monotonic=time.monotonic(),
)
operator.validate_workflow_artifacts(
    runtime, namekey=ui_tests.STARTUP_NAMEKEY,
    expected_run_outcome_path=RunLifecycle.COMPLETED.to_run_outcome_path(),
    card_text=card_text,
)
```

  Split that test's combined Dashboard/Playwright `with` into nesting solely to place these
  calls after Playwright closes. Keep all current assertions (including one-query assertion
  before this separate capture's own explicit Query), startup inputs, Chrome and timeouts.
  Existing post-test source/log/DB-byte preservation checks remain. No nested sync_playwright.
- Directory: exercise the real fixture using an isolated synthetic repository/config and
  existing startup fixture; two invocations must allocate distinct repo/tmp children, retain
  them after generator close, and contain config/DB/replay/CAS/output/storage/socket paths.
  Existing source remains readonly; path-length failure remains explicit. No new production
  data dependency and no source-string test.

Feasible preflight/record/fixture tests and Ruff/mypy first. Host Chrome is the only new
delegated boundary for this proposal; prepare it in elevate only AFTER approval/local checks.
No fresh privileged/provider/live-Codex run is needed for these test-only edits. P31 is
COMPLETE within the approved code scope, including the UUID correction below; fresh affected checks pass.

### P31 execution checkpoint — 2026-09-20

All four approved code changes are implemented in the four named test files only. The
private history helper and fixture replacement match the approved snippets; existing card
assertions/timeouts/cleanup and source/log/DB preservation assertions remain. Browser context
nesting changes only enable the approved actual capture/artifact calls after the initial
Playwright context exits. No production, ordinary-task, index or dependency edit.

New upstream full-artifact test first reproduced the actual /validate allowlist failure
(1failed17.92s). During fixture wiring, a wrong LOCATION_HEADER import failed setup
(1error8.27s); corrected to its existing authority in backend.api, not a new constant or
production move. The full preflight module then passed63tests50.85s, including real completed
Store/log/CAS validation, current typed reference checks and real unique/retained directory
fixtures. Positive provider tests cover absent/OpenAlex/ROR/both, initial ancestry and200/404;
negative tests reject missing/changed/reordered references, duplicate IDs, unknown routes,
unreferenced providers and unsupported endpoints. Directory test uses an owned synthetic
repository under repo/tmp (short p. prefix to keep the existing Darwin limit), not production
data or a system-temp fallback; fixture close retains artifacts before the test's own outer
temporary-repository cleanup. Overlong-path test fails before runtime construction.

Ruff initially found only import ordering/line wrapping; fixed without suppressions or
behavior changes. Fresh full-repository src/tests Ruff, detour strict mypy56files and default
mypy68files PASS. Read-only AST audit confirms exact approved helper/directory-fixture bodies,
no changed/deleted existing preflight tests, only the named plugin/browser function changes,
and every original browser assertion unchanged. Only four test files plus WORK differ; index
is unchanged/empty. Full feasible ordinary AI suite finished737passed,1existing skip,
12deselected1011.94s. This includes the full operator preflight module, real synthetic
Store/log/CAS, API/IPC/in-process transport, startup subprocess matrix, UI/controller and
nonprivileged watcher coverage. Exclusions: host browser module, operator/live-provider/root,
two historical captures, real Unix socket and socket-substitution selections. Existing skip
is the deliberately disabled multiple-evidence-match rejection test. No warnings reported.
This pre-amendment green batch did NOT establish correct outcome-reference checking. The
separately approved correction below fixes that fixture/assertion pair and fresh affected
checks pass. Host Chrome has not been executed locally.

Latest operator instruction: once P31 is implemented, explicitly report pre-commit-operator
readiness; if proposing elevate, give its EXACT edit shape and justification for review.
Leave elevate unchanged until that review. The new delegated result is recorded at the top;
it proves the Chrome helper but not the separate directory test or successful wrapper execution.

### P31 UUID amendment — APPROVED, implemented and locally verified

Historical approval/implementation evidence. The2026-09-21 review raised an outcome-ancestry
concern, but the operator explicitly REJECTED the proposed production/test correction.
This amendment remains implemented and untouched by the separately approved header fix.
No ancestry correction is pending implementation; preserve the review finding above.

Read-only producer review during handoff verification found an Assistant proposal error:
protected/src/backend/ipc.py:_capture_run_outcome_snapshot captures store.current_pull_record
and current_push_record. Store updates the pull slot after EVERY projected pull, including410;
api._run_outcome_record copies these captured IDs unchanged into the response body. Thus in
normal Dashboard completion, the outcome pull is the final410, not the earlier200 linked by
the commit. A later rejected push can likewise make the outcome push differ from the commit's
accepted push. The explicit commit/validation links separately preserve submission ancestry.

The original approved P31 assertions equated both pairs, while the synthetic fixture manually
constructed its outcome with the older pull. That passing upstream artifact test therefore
did NOT establish correct live outcome-input checking. Operator subsequently approved exactly
the test-only correction below, including the fixture UUID change. It is now applied; fresh
affected checks passed, as recorded below. No production/task changes are included in this approval.

Exact approved amendment, same two existing P31 files only:

```python
# validate_workflow_artifacts: replace ONLY the first two new equality assertions.
# Add PUSH_PATH to its existing Backend vars imports.
outcome_ordinal = _record_ordinal(records, run_outcome_record.record_id)
preceding_records = records[:outcome_ordinal]
latest_pull = next(
    record for record in reversed(preceding_records)
    if (record.method, record.path) == (HTTP_GET_METHOD, PULL_PATH)
)
latest_push = next(
    record for record in reversed(preceding_records)
    if (record.method, record.path) == (HTTP_POST_METHOD, PUSH_PATH)
)
assert run_outcome_snapshot.pull_record_id == latest_pull.record_id
assert run_outcome_snapshot.push_record_id == latest_push.record_id

# completed_query_fixture_process: retain the new410 record rather than discard its handle:
gone_pull = store._append_authoritative_record(persisted_http_record(
    # EXACT existing approved410 construction, unchanged.
))
# In the existing RunOutcomeResponseBody construction only:
pull_record_id=gone_pull.record_id,
```

Keep every other approved assertion, including commit/validation equality, ETag, ordering,
CAS, provider/initial links and full rendered outcome; no production change or weakened
reference requirement. Re-run the existing real completed-Store preflight case with the
corrected final-pull fixture. This check now passes; proposed host Chrome verification follows.

Completion evidence: full affected preflight module63passed98.40s with the corrected final410
fixture; full src/tests Ruff PASS and strict detour mypy PASS56files; diff whitespace PASS.
Read-only AST audit confirms the new assertion block exactly matches the approved snippet.
Only the two approved test files changed in this amendment, plus WORK; prior P31 changes
remain confined to the original four test files. Production, pyproject, dependencies and
index unchanged. The earlier737passed ordinary batch is retained evidence, not falsely
reported as rerun after this small correction. No remaining approved P31 implementation;
The subsequent P32 host batch now passes BOTH the Chrome helper and actual-macOS directory
test (see latest elevate review). Full production acceptance remains the next operator run.

## P32 — Historical implementation; global retention SUPERSEDED by P35

P32 introduced a shared retained test root, --test-artifacts-root, global basetemp/TMPDIR/
tempfile.tempdir redirection, retained collection NiceGUI scratch and browser/unit fixture
storage. This was implemented and locally passed70preflight cases; delegated macOS batch
passed2cases9.83s with preserved files (review above). Those boundaries did NOT exercise
subsequent root discovery or Linux shared-mount FIFO/socket constraints.

P34 corrected root discovery. The latest operator instruction now explicitly withdraws
all-suite repository retention: retain ONLY actual operator Dashboard/Backend/Codex data
under repo/tmp. P35 restores normal pytest/system scratch and pre-P32 isolated collection
cleanup. Obsolete P32 implementation snippets are removed so they cannot be reapplied as
pending/authoritative scope. Operator per-run retention, real card/artifact validation,
production NiceGUI protection and existing cleanup/timeout/assertion contracts remain.
Elevate is already idle; no task payload from historical P32 is pending or restored.

## P33 — WITHDRAWN / rolled back by operator: preserve generic busy-pull message

Operator decided the existing generic detail, HTTP503 and Retry-After:1 are sufficient and
explicitly rolled back P33. Current API again uses Locale.CONFIGURATION_ERROR_DETAIL for
this response; no PULL_PROCESSING_DETAIL, optional detail parameter or new busy-body assertions
remain. Verified read-only on2026-09-21, clean working tree before this WORK update. Preserve
that decision; no reapplication and no status200 change is authorized.

Historical evidence only: the reverted exact message/helper/OpenAPI patch and three assertion
additions passed11focused checks, Ruff and mypy56files. Those passes do not represent surviving
P33 code or a pending requirement. Obsolete implementation snippets are removed from WORK.

## P34 — COMPLETE: exclude retained artifacts from root discovery

### Confirmed failure and missed upstream boundary

Operator traceback reports three collection errors under
`tmp/tests.uxqd116_/pytest/test_nicegui_isolated_before_c{0,1,current}/test_collection.py`.
The generated modules import NiceGUI at collection time; default environment lacks it, so
collection aborts before real tests run. The current symlink names the second retained case,
not a third independent fixture. The182deselected summary does not make this a runtime test
failure; marker selection cannot protect against imports already performed in collection.

P32 moved/retained generated fixture modules under repository tmp. Existing main tasks
explicitly invoke pytest on `.`: test-repl -> test '.', test-repl-extra -> test '.' real_api.
Explicit `.` bypasses testpaths=['tests']. Existing norecursedirs excludes detour source/test
paths but not tmp or logs. Pytest does not use gitignore for discovery. The generated files
have no enclosing detour conftest, so its early NiceGUI isolation is not installed. Installing
NiceGUI would not correct the boundary; it could instead permit unintended fixture imports
outside their controlled child environment. No production storage access is asserted from
this particular ModuleNotFoundError report.

Assistant missed the next-run cross-suite effect of retaining generated Python modules.
The70-case local preflight and2-case macOS elevate used explicit detour node paths and could
not expose this. Prior graph review noted `test .` but failed to test it AFTER artifact
creation. This is an Assistant-introduced P32 regression, not operator/environment fault.
The full-run readiness recommendation is withdrawn.

### Exact approved correction

Add ONLY these two entries to the EXISTING global pytest norecursedirs list in pyproject.toml;
keep all current entries/markers/testpaths and every Pixi task byte-for-byte unchanged:

```diff
 [tool.pytest.ini_options]
 pythonpath = ["."]
 testpaths = ["tests"]
 norecursedirs = [
+    "tmp",  # retained runtime/test artifacts, not test sources
+    "logs",  # includes copied diagnostic/test artifact bundles
     "tests/test_detours",  # can run via `pixi run test tests/test_detours`
```

Both directories are artifact roots, not authoritative test suites; git ls-files reports
no tracked Python files beneath tmp/logs. Logs exclusion addresses the same generated files
when copied into from_operator for diagnosis, as the operator has repeatedly supplied bundles.
No deleting retained data, shortening its lifetime, renaming generated tests, dependency
addition, pytest skip/importorskip, collection-error suppression, command/marker rewrite,
new plugin or production behavior change. The excluded artifacts must remain deliberately
runnable as explicit child file targets with their existing isolated configuration.

Global pytest config was outside P32's boundary. The operator has now explicitly approved
this narrow P34 extension and its discovery regression. It changes CONFIGURATION, not any
ordinary task shape. Approval does not authorize dependency, fixture-lifetime or other edits.

### Reproduction and approved regression coverage

Read-only review plus a safe synthetic project at tmp/p34-discovery.sefdm6_m. Copied current
pyproject.toml; used the actual default-environment Python/pytest through the mandated Pixi
wrapper. No real main tests/CLI import, NiceGUI import, socket, provider or production artifact.
Synthetic archived modules deliberately raise on import, avoiding unintended storage access;
tree includes tmp retained case, its current symlink and a copied logs/from_operator bundle.
Legitimate control tests are under tests, one marked real_api and one ordinary.

- Unchanged config: `pytest -q .` -> exit2/3collection errors0.39s;
  `pytest -q -m real_api .` -> exit2/3errors/1deselected0.30s.
- Candidate applied ONLY to the copied config: ordinary ->2passed0.02s;
  marked ->1passed1deselected0.01s; both exit0. TOML comparison proves only norecursedirs differs.
- Real repository config was unchanged at that diagnostic stage. Diagnostic log/tree retained; no old artifacts
  were imported/removed, no main pipeline code executed and no production data inspected.

Approved permanent coverage belongs in the existing operator preflight/shared subprocess
mechanism, testing ACTUAL pytest discovery with a copied current repository configuration,
not source-string matching. Parameterize the ordinary and real_api root invocations. Place
controlled generated fixture modules under tmp and a copied logs tree, including a current
symlink; require legitimate tests to run and archived modules NEVER to be imported, with files
unchanged afterward. Reuse existing PythonProcess/named-helper mechanism and explicit
python_subprocess marker; no inline multi-line child scripts in individual tests. Preserve
existing direct child collection/retention tests to prove exclusion does not skip intended
isolated fixture execution. No elevate-triggering test or new dependency/module.

Implement only the config entries and corresponding discovery regression in
existing preflight/plugin files, run the new regression plus existing isolation/retention
cases and affected static checks; check root collection safely without executing retained
fixture code or importing src.repl. No further operator run requested before this passes.

Latest operator instruction reinforces the missing homework: exercise ALL locally feasible
test leaves before handoff, use elevate/necessary production checks for unavailable boundaries,
and explicitly flag uncertainty instead of giving an unqualified readiness claim. Test real
root discovery after retained files exist (including copied logs/current symlinks), not merely
the generating tests' explicit paths. Record actual passes/failures and environment/resource
constraints separately. No assertion weakening or speculative prerequisite substitution.

Latest operator constraint: no sweeping changes; justify every changed line. P34 remains
exactly two configuration entries, one two-case regression and three tiny named source
helpers in the existing plugin, plus WORK. No existing test body/fixture changed.

Execution checkpoint: permanent regression reproduced BOTH failures before the config fix
(2failed70deselected6.62s). Each actual child root invocation imported tmp, its current
symlink and logs archive, producing3collection errors. The two approved entries are now
applied. Full changed preflight PASS72tests158.95s, including both new root-discovery cases
and existing explicit child isolation/retention/conflict tests, no skips/deselections.
Actual default-environment repository-root collection AFTER retained artifacts exist passes:
ordinary147nodes25.55s; real_api1node/146deselected25.59s (production-only reviewed fixture
parameterization is unavailable here). Both exit0; every node belongs to tests/, no tmp/logs
imports. This is COLLECTION evidence, not live-API execution. Logs are retained under
tmp/p34-verify.h4s5vslu. Full Ruff PASS; strict detour mypy PASS56files. Parsed TOML comparison
proves only those two exclusion entries differ; every task and dependency is unchanged.
Remaining feasible graph verification is complete; results and exclusions follow.
The previous attempt's terminal receipt was lost at compaction; it is not claimed as a pass.

Fresh additional leaves: default mypy PASS68files; Step4/Mode3 PASS10tests71.63s (only
production-resource slow case excluded); Mode0 nonplot helpers PASS2tests9.67s (two Kaleido
socket-dependent cases excluded). Default root execution:138passed/3existing skips/4deselected/
2failed48.33s. The two unchanged extension prerequisite tests require a configured platform
binary; this x86 host has no config entry and the configured ARM path is absent. No binary/
config substitution, new skip or relaxed assertion. The four deselections are the two
reviewed-workbook cases and two DOCX cases that write data/test_data; TASK prohibits those
artifact operations here. No production data was read/written by these tests. Real Chrome/
provider/socket/root/live-Codex execution remains unavailable, not a pass or an inferred failure.

Line-level scope justification: the tmp entry blocks generated fixtures; the logs entry
blocks copied fixture bundles. The new test's decorators select both actual root command
shapes; setup copies authoritative config and constructs two legitimate controls plus three
archive paths (including current symlink); subprocess/receipt assertions prove discovery
and marker behavior; before/after hashes prove exclusion does not delete data. Three tiny
named plugin helpers provide those standalone source bodies through the existing mechanism,
avoiding inline child programs. AST comparison proves ALL previous test/plugin code unchanged.

### P34 completion evidence — 2026-09-21

- Full feasible ordinary AI batch:677passed/1existing skip/9deselected1006.83s, exit0,
  no warnings. Includes real synthetic Store/log/DB/replay, in-process transport, UI/controller,
  startup subprocess matrix, audit and nonprivileged watcher tests. The separately completed
  full72-case preflight is not included in this batch. Host browser module was explicitly
  excluded; its browser-free completed-query fixture separately passed1test42.76s. The
  existing skip is the deliberately disabled multiple-evidence-match rejection check.
  Nine deselections:3needs_sudo,1real provider,2historical captures,1real Unix IPC,
  1socket substitution parameter and1socket-substitution CLI case. Three nonsocket
  substitution parameters WERE executed, not discarded with the socket case.
- AFTER that artifact-generating batch, repeated both actual default-env root collections:
  ordinary147nodes; real_api1node/146deselected; both exit0 in6.92s. Node lists exactly
  match the earlier successful collection, all under tests/, no tmp/logs imports. This
  covers the previously missed subsequent-invocation boundary, not just a copied config.
- Every locally feasible operator-graph leaf was addressed: Ruff, both mypy environments,
  default root execution/collection, Step4/Mode3, Mode0 nonplot, AI ordinary/preflight and
  browser-free fixture. Resource/safety/network/browser/root exclusions and two genuine
  local extension-prerequisite failures remain explicit above; no hidden green claim.
- Diff: ONLY2pyproject configuration lines,45new preflight lines (one two-case test),17new
  plugin lines (three named source helpers), plus WORK. No existing test/assertion/timeout,
  fixture lifecycle, task, production source, dependency or index changes. TOML equality
  outside the two entries, unchanged existing test/plugin AST and diff whitespace all PASS.
  Verification logs remain in tmp/p34-verify.h4s5vslu; generated artifact roots are retained.

All approved P34 implementation is complete. No additional fix or elevate batch is proposed
for this discovery correction: its actual default-environment boundary is testable here and
now tested. Current elevate remains the existing idle scaffolding, unchanged. A full new
pre-commit-operator run is still production acceptance, not something these local results
can certify in advance. P33 remains withdrawn; no other pending approved code is revived.

## P35 — COMPLETE: restore interactive sudo and ordinary temporary storage

Historical P35 implementation/evidence below: P36 supersedes its direct operator-directory
allocation and prefix. All other P35 corrections remain. Do not reinstate the old allocation
snippet once the marker-based P36 wiring is applied.

Latest explicit operator instruction supersedes the unapproved native_fs_path proposal:
- Root task must ask for its sudo password; restore interactive authentication.
- Repository ./tmp retention is ONLY for operator-test Dashboard/Backend/Codex files.
- No sweeping changes; modify only necessary wiring and corresponding tests.

Implementation boundary:
1. Existing root task uses ordinary sudo already, not sudo -n. Add only -k to invalidate
   cached authentication for this invocation; preserve env/interpreter/selection and every
   other task. No password capture, sudo -S, root preload or credential-policy changes.
   Update its existing launcher sentinel to require/consume -k; that test proves argv and
   real interpreter activation, NOT actual sudo authentication/privilege dropping.
2. Remove P32's global test-artifacts-root option/stash, basetemp/TMPDIR/tempfile.tempdir
   overrides and all-suite retained directories. Restore the pre-P32 TemporaryDirectory
   NiceGUI collection isolation/cleanup; original-storage/Redis guards stay intact.
3. operator_runtime alone retains unique repo/tmp/operator-test.XXXXXXXX directories for
   its config/source link/DB/replay/CAS/NiceGUI/output/socket. No scratch redirected there.
4. Ordinary browser fixture uses its original short native temporary socket directory,
   with normal cleanup; data stays in ordinary tmp_path. Update only direct removed-fixture
   callpoints and retention tests. Keep browser/card assertions, helpers and timeouts.
5. Replace obsolete P32 global-retention rejection expectations with real checks that
   normal pytest scratch/configuration is not redirected. Keep P34 discovery exclusions/
   regression (old retained artifacts still exist). Never delete old artifacts or add skips.

Exact root command change: sudo env -> sudo -k env.
Exact collection isolation to restore (historical58e727e):
```python
directory = tempfile.TemporaryDirectory(prefix="ai-augment-pytest-nicegui-")
environment = pytest.MonkeyPatch()
environment.setenv("NICEGUI_STORAGE_PATH", directory.name)
environment.delenv("NICEGUI_REDIS_URL", raising=False)
config.add_cleanup(environment.undo)
config.add_cleanup(directory.cleanup)
```
Exact operator retention boundary:
```python
@pytest.fixture
def operator_runtime(repository_root: Path) -> Iterator[OperatorRuntime]:
    artifacts_root = repository_root / "tmp"
    artifacts_root.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="operator-test.", dir=artifacts_root))
    # Existing log, socket-length guard, runtime initialization/yield remain unchanged.
```

The five reported FIFO/socket failures are ordinary, NOT needs_sudo tests. Their path
correction is independent of root authentication. Shared-checkout FIFO semantics remain
unconfirmed without the full traceback/mount evidence, but returning ordinary scratch to
native temp also restores the previous filesystem boundary. No new native_fs_path fixture,
locator mechanism, broad skip removal or production patch from the superseded proposal.

Verify changed real preflight/collection/ordinary FIFO tests, launcher activation, static
checks and root discovery. Socket/browser/sudo execution remains an explicitly delegated
boundary; do not claim actual password-prompt verification from a sentinel. No new elevate
batch or pre-commit wrapper change is included in this correction.

### P35 execution checkpoint — 2026-09-21

Implementation is confined to six existing config/test files plus WORK:
- pyproject.toml: only sudo env -> sudo -k env in test-detour-ai-augment-root. Parsed TOML
  equality outside that exact change and bash -n PASS; every other task remains unchanged.
- test_appendwatch.py: its existing sudo sentinel requires/consumes -k, preserving real
  Pixi activation/watcher --help checks. Actual sudo authentication is not simulated evidence.
- pytest_plugin.py: remove global retention option/stash/fixture and path overrides; restore
  pre-P32 isolated NiceGUI cleanup. AST of pytest_configure matches58e727e exactly. Preserve
  original-storage/Redis guards and add one tiny named child source for normal tmp_path proof.
- operator fixture: restore repo/tmp/operator-test.* allocation, unchanged logging/length
  guard/runtime/yield and retained artifacts. Only this real runtime retains repo/tmp data.
- preflight: update removed-fixture callpoints and superseded retention expectations; replace
  obsolete seven global-retention conflicts with three real standard pytest policy cases.
  Preserve remaining assertions; synthetic-repository cleanup is ordinary test cleanup.
- browser test: restore short native socket TemporaryDirectory with finalizer, remove the
  obsolete global-root argument/assertion, correct misleading retained-data log. No browser
  assertion/helper/timeout/process-cleanup change; ordinary data still derives from tmp_path.

First preflight run:64passed/3failed/1error117.97s. New subprocess regression ran outside the
repository without an import path; fixed only its cwd to pytestconfig.rootpath, keeping its
explicit temporary pytest.ini/basetemp. Existing completed-history fixture exceeded unchanged
30s child timeout while other checks ran; no proven cause or timeout change. Fresh module run
alone:68passed52.74s, including that unchanged fixture and all three new policy cases.
Ruff initially caught import ordering for tempfile; corrected, full src/tests Ruff PASS.
Strict detour/shared-record mypy PASS56files. A prior ordinary watcher receipt was lost across
compaction; not claimed as a pass. Fresh full feasible ordinary AI results follow.
No production code, dependency, test skip/timeout or Git-index mutation. Elevate stays idle.

### P35 completion evidence — 2026-09-21

- Full feasible ordinary AI suite:677passed/1existing skip/9deselected893.08s, exit0. Includes
  unchanged three FIFO-only regressions, remaining nonsocket watcher cases, all four actual
  Pixi/interpreter launcher cases, Store/API/replay and startup matrix. Existing skip is the
  deliberately disabled multiple-evidence-match rejection test. Nine deselections:3root,
  1provider,2historical captures,1real Unix IPC,1socket substitution parameter,1mixed socket
  CLI case. Host browser module explicitly excluded. Separate changed preflight68passed52.74s.
- AFTER this suite: actual default-environment root collection147nodes; real_api collection
  1node; both exit0, all nodes under tests/, no retained tmp/logs test imports. Collection
  is not execution evidence for provider/main tests. P34 exclusions remain unchanged.
- Final Ruff PASS; strict mypy56files PASS plus the final preflight cwd correction checked
  separately1file PASS. Diff whitespace PASS. Parsed TOML proves root sudo -k is its sole
  change; bash -n PASS. AST checks prove every other watcher/browser/operator function
  unchanged; all original browser assertions remain except superseded global-root containment.
  pytest_configure exactly matches pre-P32, preserving early NiceGUI isolation/cleanup.
- Representative normal aicode socket paths are89/91bytes, below Linux107byte pathname
  maximum. This is arithmetic, not a real socket pass or proof of the guest mount's FIFO
  semantics. No root/sudo/socket/Chrome/provider/live-Codex execution here. Sudo uses normal
  terminal authentication with -k; no password input capture or modified sudoers policy.

Approved P35 implementation is complete. Only the six named config/test files and WORK
changed; no native_fs_path fixture, added skip, timeout, production edit or pre-commit/elevate
rewrite. Actual operator runtime data alone is retained under repo/tmp/operator-test.*;
ordinary scratch follows pytest/system policy. Old retained artifacts were not deleted.
No unqualified full pre-commit-operator success/readiness claim; production acceptance remains.

## P36 — COMPLETE: use_rootpath_tmp

Operator accepted the exact proposed snippets, renamed use_cwd_tmp -> use_workdir_tmp ->
use_rootpath_tmp with constant USE_ROOTPATH_TMP_MARKER. Root means request.config.rootpath,
not invocation cwd or later chdir. This supersedes only P35's operator-specific allocation:
marked tests may retain ALL tmp_path-derived files, not exclusively runtime files. Initially
mark only the existing operator module; do not opt other suites/browser tests in implicitly.

Exact additions in existing protected/tests/pytest_plugin.py:
```python
USE_ROOTPATH_TMP_MARKER = "use_rootpath_tmp"

# Inside existing pytest_configure:
config.addinivalue_line(
    "markers",
    f"{USE_ROOTPATH_TMP_MARKER}: retain tmp_path data under project-root/tmp",
)

@pytest.fixture
def tmp_path(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Path:
    if request.node.get_closest_marker(USE_ROOTPATH_TMP_MARKER) is None:
        return tmp_path

    root = request.config.rootpath / "tmp"
    root.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="test.", dir=root))
    print(
        f"[test-data] {request.node.nodeid}: retained {directory}",
        flush=True,
    )
    return directory
```

The same-name argument resolves pytest's original fixture by standard override semantics;
unmarked callers receive that unchanged Path. Marked directories are unique and retained
after success/failure. No override of basetemp, TMPDIR, tempfile or tmp_path_factory; no
collection-time NiceGUI storage change, new cleanup or change to ordinary fixture policies.

Exact operator module wiring:
```python
pytestmark = [
    pytest.mark.operator,
    pytest.mark.use_rootpath_tmp,
]

@pytest.fixture
def operator_runtime(
    repository_root: Path,
    tmp_path: Path,
) -> Iterator[OperatorRuntime]:
    run_dir = tmp_path
    # Existing logging, socket-length guard and runtime/yield unchanged.
```

Remove only the now-redundant directory allocation from operator_runtime. Keep existing
operator selection/authentication behavior; the new marker does NOT authorize AIVM work.
Necessary existing preflight callpoints/tests must consume the supplied directory and
preserve runtime containment, file/source preservation and socket-length assertions. Add
real isolated pytest coverage for marked/unmarked behavior, marker inheritance, unique
directories/retention on success and failure, dependent fixtures and project-root anchoring
when invoked from a subdirectory. Reuse existing named subprocess helpers, no inline child
programs in test functions. No test weakening, new skip or timeout change.

Boundary: three existing test files (plugin, operator module, operator preflight), plus WORK.
No task/production/dependency/browser modification, sudo rework or index mutation. P35's
fake-sudo adaptation was expressly accepted and stays unchanged. Keep P34 discovery guards.
Prototype before approval: actual pytest4cases passed0.80s with rootpath anchoring from a
subdirectory; this is mechanism proof, distinct from the repository verification below.

### P36 execution checkpoint

Exact approved marker constant/registration/fixture body and operator module markers/runtime
signature are implemented. Removed only operator_runtime's redundant allocation and its now
unused tempfile import; existing log, guard and yield unchanged. Necessary preflight changes:
runtime test supplies two distinct short owned directories and retains its complete byte/
source/path checks; overlong-path test supplies the actual overlong directory directly.
Allocation uniqueness is now exercised at its owner: four real child-pytest cases (function/
module marker x success/failure), each running two parameterized tests. They prove dependent
NiceGUI paths, project-root anchoring from a subdirectory, diagnostic paths and retained data
even with ordinary pytest retention disabled. Existing three unmarked policy cases remain.
One named test-source helper added to the existing plugin; no separate harness/module.

Focused actual checks:11passed61deselected53.81s, including those four cases, unmarked policies,
collection NiceGUI cleanup and runtime path checks. Ruff PASS; strict mypy PASS56files. Added
an explicit expected-failure-message assertion afterward; full affected module follows.
Full affected preflight:72passed60.24s, including that assertion and all existing artifact/
isolation/root-discovery checks. AST audit matches the approved fixture body, marker list,
operator signature and assignment exactly. No obsolete marker names/prefix consumers remain
in active tests. Operator staging changed during implementation; preserve it. No Git mutation
was performed. No tasks/production/browser files changed for P36. Full feasible ordinary AI
suite ran separately with the same explicit browser/socket/root/provider/history boundaries
as P35; final evidence follows.

### P36 completion evidence — 2026-09-21

- Full feasible ordinary AI suite:677passed/1existing skip/9deselected879.13s, exit0. Includes
  unchanged FIFO/watcher, interpreter launchers, real synthetic Store/log/DB/replay, UI and
  startup subprocess matrix. The existing multiple-evidence-match skip and nine explicit
  exclusions are exactly those listed for P35; browser module excluded, no new skip/timeout.
  Separate full preflight72passed60.24s; the focused11case run is a subset, not additive.
- Actual default-environment root discovery after those checks:147ordinary nodes and1real_api
  node, exit0, all under tests/. No tmp/logs import. This is collection, not provider execution.
- Ruff PASS; strict detour/shared-record mypy PASS56files; whitespace check PASS. AST verifies
  the exact approved fixture body, operator marker list/signature/assignment; operator
  log/guard/yield remain unchanged. pytest_configure matches the pre-P32 behavior exactly
  after removing ONLY the new marker-registration statement from the comparison.
- Operator asked whether old relocation code remained: inspected HEAD/index/working tree.
  All-suite option/stash/fixture, basetemp/TMPDIR/tempfile.tempdir overrides, policy guards and
  operator-specific allocation are removed (already staged). Native NiceGUI collection
  isolation, short socket directories and the existing browser-local child TMPDIR remain
  intentionally; none is the retired suite-wide repository relocation mechanism.

P36 is complete within the exact approved shape. Three existing test files plus WORK only;
no new module, production/task/dependency change or Git mutation. All operator staging is
preserved. Actual sudo/socket/Chrome/provider/live-Codex acceptance was not rerun; elevate
remains idle. Prior operator-prefix allocation snippets are historical, superseded by P36.

## Completed scope index

| ID | Implemented scope | Main locations |
|---|---|---|
| P1 | Exact JSONL hashes, typed table-comment anchor, independent prefix/suffix verification, safe transactional promotion | Store + replay_log.py |
| P2 | Full --new empty baseline or separately confirmed nonempty replay; strict resume never heals | server.py + Store |
| P3 | Real append-open/close preflight without writing, writable mode only | replay_log.py + Store |
| P4 | Historical verdict substitution removed; failed full-child cycle blocks unattended retry/reset | api.py + Dashboard context |
| P5 | Launcher independence; IPC-only ignores modes/bypasses initialization; full-only Dashboard bookkeeping | server.py, api.py, ui.py, context, launcher help |
| P6 | Non-locking IPC signal flag; unchanged clean-close token in protected Backend vars | ipc.py + vars.py + import points |
| P7 | Empty parameterless QueryRequestProperty; concrete outbound_http retained | protected/src/architecture.py |
| P8 | Single Start/Stop queue-processing switch, stopped at Dashboard startup | Dashboard controller/page |
| P9 | No Backend card/ZIP publishing; explicit Dashboard publish completed shares DOCX renderer | Store, api.py, ui.py |
| P10 | Dashboard background-startup failure requests normal shutdown and unsuccessful process exit | ui.py application lifecycle |
| P11 | All25 in-scope remaining detour dataclasses converted, with standalone dependency/constructor integration | Backend models, watcher/audit and corresponding test helpers |
| P12 | Missing operator-terminal logs for existing UI actions/results/errors, including probes/download/publishing | ui.py |
| P13 | Extensionless two-level SHA256 CAS shards, symlink guards and directory fsync | ai_augment_cas.py + corresponding test fixtures |
| P14 | Current lifecycle review and 111 mock-free parametrized startup-condition cases | tests/control_centre/test_ui.py |
| P15 | Operator test moves preserved; import, constant and fixture collisions corrected | test_ui.py, test_audit_read.py, test_backend_store.py |
| P16 | Markdown/TXT button shares DOCX download contour; symmetric format-specific handles/selectors | ui.py, locale.py, existing UI tests |
| P17 | Header grouping, horizontal DOCX/Markdown buttons, localized queue-processing labels | ui.py + protected Dashboard locale |
| P18 | Original operator fixture/query/queue corrections, watcher interpreter, shared lint and graph review | Approved code implemented; F4 real query/browser check passed; F3/F7 diagnostics implemented, runtime findings unresolved; F5 replacement withdrawn; production acceptance pending |
| P19 | Named subprocess helpers, shared explicit fixture and selectable markers; preserved isolation/timeouts | protected/tests/pytest_plugin.py + existing test callpoints |
| P20 | Typed /validate record/body protocols and readback, unchanged wire format | validation_event.py, architecture.py, api.py, query_response.py |
| P21 | Existing full run-outcome exchange renamed RunOutcomeRecord throughout | renamed run_outcome_record.py + direct protocol/consumer/test callpoints |
| P22 | Completed historical display-only card-ID scope; superseded by P24 | ui.py + Control Centre Locale + test_ui.py |
| P23 | Shared v1.1 HTTP-record structural protocol, model conformance and three record-protocol bases | shared http_request_log.py + protected architecture.py |
| P24 | Persisted validation/outcome IDs, outcome-triggered materialization, pure card renderer, server-owned HTTP/IPC admission | Backend API/Store/server/IPC/models; Dashboard snapshot/card callpoints |


All P1-P24 code changes are implemented (P22 superseded by P24); this is not production
acceptance or fresh P25 verification. No additional pending historical implementation is
revived. P25 is implemented; P26–P30 are complete; P31's approved shape and UUID amendment are complete and locally verified. F7 remains an unresolved report,
not a proven task defect to patch speculatively.

## Retained contracts — baseline and P25 boundaries

### Store, integrity and startup

- Backend Store exclusively owns detour DB/replay I/O, locks, permissions and transactions;
  domain SQL/evidence algorithms remain API private helpers. Main source DB is read-only.
  Low-level Store operations become private under P25, not DB handles exposed to adapters.
- Exact JSONL bytes including LF are SHA256-hashed into detour_http_records.raw_line_sha256
  in the projection transaction. _ReplayAnchor (sha256, ordinal, byte_offset) is JSON in that
  table's DuckDB TABLE COMMENT: _write_anchor uses COMMENT ON TABLE; _verify_log_projection
  reads duckdb_tables().comment for current DB/main schema. No separate anchor table or
  detour_authoritative_projection. P25 preserves this metadata/verification mechanism.
- Resume/continue/IPC independently hash the saved prefix, verify complete ordered DB/log
  coverage and per-line suffix hashes through EOF. Same config hash never skips coverage.
  Missing/extra/gapped rows, truncated/invalid tail or anchor fail. No tail repair, catch-up,
  migration, shadow rebuild, replay fallback, automatic config update or recovery.
- Config hashes use RegisteredResource mechanics; human recalculates/updates config between
  launches. Dashboard verifies resources and deliberately passes --danger-no-verify-hash to
  owned children. Changed anchor promotion requires verification and successful append-open
  preflight and transaction; readonly IPC never promotes. Failed preflight leaves anchor intact.
- Full --new or --resume/--continue required, with default-No confirmation unless --yes.
  Nonempty --new asks a second default-No replay question BEFORE deleting old DB/WAL;
  --yes accepts both. Empty baseline uses SHA256(empty), ordinal/byte0. Explicit replay must
  reproduce recorded results without network or fabricated missing records; fail at first
  invalid record/group. P25 adds the expressly approved grouped projection contour only.
- Writable startup checks actual O_WRONLY|O_APPEND open/close without create/truncate/write,
  no-follow/same-inode, then restores0400. Retained log FD is readonly. Store alone opens
  write windows. IPC-only ignores even conflicting initialization flags, has no prompts,
  requires an existing valid DB, serves only wholesale /query and OPTIONS, and never
  rebuilds/appends/append-preflights/promotes. --config remains required in both modes.
- Full mode requires an eligible selected researcher; IPC-only does not. Both retain exclusive
  process lock, config/source construction and verification. No Backend parent watcher or
  launcher knowledge. Orphan Backend after Dashboard SIGKILL is intentionally external on
  restart: it may be borrowed, never adopted/reset/stopped. No startup automatic probe/query.
- Store closes successfully before BACKEND_STORE_CLOSED_CLEANLY is emitted; constant lives
  in protected Backend vars.py. Signal handlers remain simple non-locking flags in IPC-only.
  Full shutdown must keep the event loop alive while draining/stopping IPC/background work.
- Dashboard first owned FULL cycle uses --new --yes; only successful start AND clean stop
  permits future --resume --yes. Failed full cycle blocks unattended retry/reset. IPC-only
  and borrowed lifetimes do not affect that private instance policy. Owned stop: SIGTERM,
 10s wait then SIGKILL; clean means accepted exit + token + no forced kill. Borrowed not stopped.

### Records, validation, innerdicts and Dashboard

- Shared HttpRequestLogRecord/Protocol v1/v1.1 fields/conversion remain untouched in P25.
  Its docstring already records Response.text/UTF8 limitations and desirable raw-byte v2.
  Current provider endpoints: main OpenAlex /authors(select=id), /works(select=id,title);
  detour OpenAlex /institutions/{id}, ROR /v2/organizations/{id}, all JSON. Local /push is
  application/json; /pull also returns Markdown/NDJSON. New endpoints need individual review.
  No tagged-base64 v1.1 or v2 implementation/migration approved.
- /commit and /validate remain synthetic request-only HTTP records with null response
  fields. Typed BackendValidationRecord/body stay; P28 explicitly renames the outcome model
  to RunOutcomeResponseRecord without changing its wire shape. Validation
  now contains typed commit/initial-validation/provider records and PostCommitValidation
  with submission/discriminator, following the approved P30 addition rather than the prior
  commit-ID/provider-ID-only body. Unchanged pasted model performs intercepted validation using persisted DB-readback
  responses; no replay provider calls or swallowed replay inconsistency.
- P24 baseline: accepted output rows initially have null validation/outcome IDs; /pull410
  uses durably persisted accepted validation/submission, not final innerdicts. Only matching
  outcome application sets final IDs and materializes codex_innerdicts in its transaction.
  Query reads that table, not unfinished flat output rows. P30 supersedes the baseline's
  separate commit/validation/outcome card metadata with the full stored outcome response
  record; pure innerdict rendering remains, with no transient UI enrichment. P25 changes
  grouped transaction/response409 eligibility exactly as specified above.
- Preserve exact researcher/session/commit/validation linkage, prior finalized IDs and multiple
  eligible commits. Missing/rejected data never becomes an accepted placeholder. Cancellation
  preserves durable data and fabricates nothing. No default/schema audit outside P25 fields.
- CAS layout is extensionless <root>/ab/cd/<full SHA256>; symlink guards and fsync cover blob,
  both shards/root. Missing/corrupt blobs fail, never redownload/migrate. No P25 CAS changes.
- NiceGUI owns wholesale query snapshot independently of run journal/queue. Explicit Query IPC
  composition callback owns query capability, not controller. QueryRequestProperty remains
  parameterless; concrete outbound_http stays. No filtered/per-person, startup, repaint or
  card queries; replacement follows successful owned-child cleanup.
- Dashboard CODEX_EXITED -> one ordinary /pull:410 completed, all others including503 failed
  -> outcome IPC -> owned Backend shutdown. Cancellation separate. P25 permits /failed409
  after waiting for successful processing; no automatic retry/reclassification/extra query.
- Queue switch starts stopped each Dashboard process; Stop affects next dequeue only. Cancel
  actually stops/removes the current run and does not alter the switch/re-enqueue. Existing
  remote interrupted-run cleanup remains interactive-start-only, skipped for publishing.
- No Backend card/ZIP publication or recovery. Display and DOCX/TXT downloads share Markdown
  renderer; TXT uses raw Markdown UTF8/.txt, main-pipeline basename, symmetric handles.
  Explicit Dashboard `publish completed --config ...` shares DOCX path, stored eligible
  completed snapshot, no automatic query/Backend/queue start, normal shutdown, detailed logs.
- Layout and localized queue labels unchanged; probe/query/start-stop alongside title,
  statuses next row; DOCX then Markdown together. P25 does not redesign UI/export/queue/logging.
- In-scope dataclasses already converted: FrozenStrictModel where feasible; explicit BaseModel
  ConfigDict for mutable/opaque handles. Do not change pasted StrictModel. Standalone deployment
  installs unchanged shared architecture plus Pydantic2 in the provisioned model environment;
  no deploy/provision change under P25. sample_deploy excluded.

## Verification baseline — before P25, not evidence for the new implementation

P24's fresh local checks (overlapping selections, not additive):

| Check | Result and boundary |
|---|---|
| Live/replay outcome matrix and negative ordering/history | 12 passed (70.86s): complete/partial snapshots across completed/failed/cancelled; exact query JSON/logical DB equality, unchanged log; no-validation/rejected/no-session/other-session; two accepted commits, finalized IDs not rewritten, late validation rejected |
| Existing Store/interceptor selection | 47 passed,13 deselected (103.71s); excludes the above outcome cases and410 integration |
| Real Store/ASGI410 integration plus four card cases | 5 passed (32.00s): validation durable before410, no early innerdict, IPC waits through actual response send, validate < pull410 < outcome in durable history; card/interim-state checks |
| Gate/WSGI/lifespan composition | 21 passed,1 real-socket case deselected (9.81s): response/background wait, new-HTTP exclusion, ordinary503 availability, exception cleanup, OPTIONS/errors and real threaded bridge/shutdown |
| Factory registration plus final card-ID checks | 5 passed (7.61s); subsequent type-safe factory assertion alone1 passed (6.20s). Covers one-time outer gate registration and missing/malformed/unlinked/cross-NameKey/cross-session ID rejection |
| Existing API feasible selection | 166 passed,1 existing skip,4 deselected (80.28s). Preserved skip for currently allowed multiple evidence matches. No historical capture execution |
| Existing UI feasible selection | 84 passed,1 new negative-fixture failure (11.10s), then all four card cases passed in the focused checks above. Existing download/publishing/queue/autonomy checks passed |
| Final static checks | Ruff PASS; strict detour/shared-record mypy PASS54files; diff whitespace PASS |


P24 test-development failures were corrected without weakening production checks: real UUIDv7
negative fixture, serialized readback comparisons and typed middleware-factory assertion.
Threaded gate tests use a test-only loop timer through Runner cleanup; actual gate/ASGI/WSGI/
thread bridge executes but not real network serving. The410 case uses real Store/middleware
with an async test route around the sync pull handler. Historical capture callpoints were
updated statically, not executed/accessed. P25 needs fresh boundary checks after its edits.

Additional baseline evidence:

- P20:21 focused validation/replay/query cases; P21:21 outcome/query/UI cases; P23:53 shared
  HTTP/model cases; Ruff and strict detour mypy54files passed. Main mypy68files passed using
  designated default executable; earlier AI-stub main check had20 unrelated errors, not a pass.
- F8 IPC-only opening log fixed exactly to logger.info("Opening read-only Backend Store");
  unchanged test_main_ipc_only_runs_only_the_dashboard_query_server passed1 in1.94s after
  reproducing AttributeError from unnecessary detour_db_path access on its minimal fixture.
- Prefix verification log-only fix: one prefix summary/match, per-line messages only for
  hashed suffix;12 Store integrity cases passed. No verification/hash behavior changed.
- P14:111 real startup/confirmation cases passed in538.68s; P19 migrated to shared subprocess
  helpers. Later91-case run had90pass/1timeout, identical case passed alone unchanged7.65s;
  initial run not wholly green and timeout cause unproven. These stop before real serving.
- P19:11 subprocess cases and320 feasible nonsubprocess cases passed;102 marked subprocess,
 4 socketless lifecycle cases at that checkpoint. Names/markers may change only as direct
  P25 callpoints require; preserve case intent and isolation, no inline child Python bodies.
- P13:24 focused CAS cases; P16:7 DOCX/TXT cases; existing DOCX browser/layout cases passed
  delegated after initial startup timeouts. These do not certify browser TXT downloading.
- F1/F2: real NiceGUI persistence, early collection/child wiring, preservation guard and
  standalone watcher isolation checked. F4 actual browser/completion-helper/owned-query
  regression eventually passed47.19s after filtering5s and IPC-readiness30s timeouts;
  no timeout/assertion changes. Weak-host contention plausible, not proven cause.
- F3/F7 diagnostics:7 local cases; operator preflight23pass. Four actual-Pixi unset/stale-parent
  activation cases pass locally and PROD with15s bounds; sudo/pytest dispatch are sentinels,
  real watcher --help executes. These are not proof of nobody/root monitoring or resolution
  of the operator's original pixi-shell report.
- Mode3 approved test-only fix injects real Console(width=80), all assertions unchanged.
  Entire module6pass and actual -vv -srA PTYs80/92 both pass; production/tasks unchanged.
  Baseline aicode/staging (ef5ddef), not dc951fe. Staging source with current dependencies
  reproduces92-column wrap but does not establish historical failure; operator reports passes.

## Previous full operator findings (2026-09-18) — corrections implemented

Historical reviewed pre-commit-operator run:2026-09-18 15:37:17–15:46:13(-04),
logs/from_operator/pre-commit.log and pre-commit-extra.log. Full acceptance FAILED.
Operator then requested findings independent of pending P26-P30; those items were still
unimplemented at that checkpoint (now complete). The initial review changed WORK only; correction1 was
subsequently approved and implemented below. Corrections2 and4–7 are implemented and locally verified; targeted delegated verification passed; full operator acceptance remains pending;
correction3's approved test deletion is complete, not its original redesign. Line references below count LF lines
in the raw logs (terminal CR/ANSI sequences may affect rendered editor numbering).

| Finding in the last operator run | Evidence and present correction boundary |
|---|---|
| Live workflow blocker | Extra log4623–4629: rollout capture succeeds (856518bytes/178lines), commit and validation are persisted, but rollout_index rejects call_YiI9YVKmuEiZtIrZu1FI3vl2: “must contain exactly one eligible web action”. Pull then returns500, never410. Dashboard's ordinary final pull500 -> /failed200 follows its current contract. Recovered evidence identifies a find-only call excluded by that run's pre-fix whitelist (details below). Correction1 below implements the fix; full production acceptance has not been rerun. |
| Five stale preflight callpoints | test_operator_e2e_preflight.py:303 patches backend_ipc.start_dashboard_query_server, moved to backend_server by P25. All five then failed before exercising their behavior. Item2 now corrects the direct target/import, preserving cases/assertions; the20-case preflight run passed. No compatibility alias or production rollback. |
| Three stale elevate expectations | Same test module:344 assumes elevate always runs install+browser stages. Operator-requested idle “Nothing to elevate” correctly runs neither. The three tests failed on missing stages or expected nonzero status. Item3 deleted that parametrized test entirely; no obsolete batch or redesigned wrapper tests remain. |
| Host browser layout | pre-commit.log3267: card line-height ratio is NaN, so the compact-spacing assertion fails. Host module8passed/1failed34.11s; real query and DOCX download pass. The pre-correction test evaluated computed lineHeight/fontSize immediately after card click without content/visibility readiness; item4 adds the exact approved readiness checks and diagnostics; fresh host Chrome verification passes (3.28s). Current CSS explicitly sets1.25; logs do not capture computed strings or element attachment, so a render/detachment race is plausible, NOT proven and not justification to relax the assertion or change production CSS blindly. |
| Full Backend shutdown evidence incomplete | Extra log5405–5415: test teardown signals Dashboard while its worker is already stopping Backend. All processes disappear, Dashboard exits0, no forced-kill report; however the full Backend clean-close token, final Uvicorn shutdown lines and Dashboard Backend-stopped log are absent. Query-only shutdown earlier has them. The prior code had a cancellation window: cancellation inside Backend._stop cleared self._process before a second stop could await it. Item5 now shields/awaits that cleanup and tests both cancellation points. The prior missing log was not proof of Store failure; full operator re-verification remains pending. |
| Normal AI suite | 578passed/8failed/1skip/3deselected/1warning116.24s. The eight failures above prevent the subsequent real OpenAlex/ROR institution test via task's &&. Do not report that provider leaf as tested. |
| Browser placement / root watcher | Routing now correctly runs Chrome tests on macOS; aicode privileged appendwatch3passed70deselected2.55s, unchanged real EACCES assertions. Earlier machine-placement/credential blockers are resolved, not reasons for this run's failures. |
| Timing / previous hang | Live case finishes1failed/2intentional skips332.21s, no Ctrl+C/KeyboardInterrupt/timeout. Full Backend starts, session supplied, Codex works for about280s before push; then failure/outcome within roughly30s. Repeated 2-record heartbeats during research are expected, not proof of a stuck Backend. The old pre-start hang did not recur; its historical cause remains unknown. |
| Preservation / prerequisite checks | Isolated NiceGUI path logged; production-data and original-NiceGUI preservation guard passes. Configured DuckDB checks pass. Actual root task starts correctly this run; the older F7 pixi-shell report remains unreproduced, not dismissed. |

Recovered-record follow-up (operator supplied tmp/run_h5f6hp6j20s6x8737ypcwxj40000gn,
explicitly authorizing read-only inspection of this recovered test run): the failing call is
now identified precisely. In BOTH captured CAS blobs, rollout lines74–76 are the function
call, web_search_end and single input_text function output for
call_YiI9YVKmuEiZtIrZu1FI3vl2. Its arguments are:

```json
{"find":[{"ref_id":"turn6search2","pattern":"Aziz Sheikh"},{"ref_id":"turn3search0","pattern":"NIHR Senior Investigator"},{"ref_id":"turn6search0","pattern":"Professorial Fellow"},{"ref_id":"turn4search3","pattern":"Languages"}],"response_length":"long"}
```

This is one find action with four searches, NOT mixed eligible actions. Before correction1,
_web_arguments counted zero because ELIGIBLE_WEB_ACTIONS contained only search_query/open/click. Event action is
find_in_page; the output has ordinary citation sections. Two result refs have valid URLs
(turn7view0/turn7view2); two are Internal Error entries with no URL (turn7view1/turn7view3),
which the existing downstream indexing logic already excludes. The entire cited rollout is
indexed before submission validation, so this action blocked the run regardless of whether
its particular excerpts are ultimately submitted. P26-P30 do not change this whitelist.

Read-only diagnostic through actual parse_rollout/build_rollout_index, using an ephemeral
pytest module and the existing isolation plugin: both captured snapshots reproduce the exact
pre-fix exception; a test-only monkeypatch adding find to ELIGIBLE_WEB_ACTIONS allowed BOTH
complete indexes:14calls/14outputs/254URL-backed refs, with exactly the two valid find refs.
4cases passed1.50s; no production file/fixture/test/task edit, provider request or writable
Store/replay operation. Temporary test module removed on completion. This verifies the narrow
candidate correction, NOT full submission acceptance or replay under changed validation rules.
The initial find-only whitelist proposal is superseded by the operator's subsequent
discussion below: unsupported actions should make evidence ineligible, not fail the whole
rollout. The diagnostic above establishes find support only, not that revised behavior.
Operator subsequently authorized correction1 below, then corrections2 and4–7 on2026-09-19,
and finally deletion of the elevate-triggering tests instead of the proposed correction3.
The existing rejected /validate record remains unchanged; changing the indexing rule can
change recomputed validation on explicit replay, so no compatibility/success claim is made.

Recovered persistence evidence:

- All10 JSONL lines are LF-terminated and validate as actual HttpRequestLogRecord v1.1.
  Read-only DuckDB has the same10 contiguous ordinals, IDs, methods, paths, full JSON payloads
  and exact LF-inclusive SHA256 hashes. Database bytes unchanged after inspection.
- Sequence:2pull200, push202, commit, validate,4pull500, failed200. One stored attempt;
  validation stage=rollout_index/result=rejected, null submission and empty provider-ID list.
  No accepted innerdict table: rejection predates derived schema/output, not lost acceptance.
- Outcome references exactly the committed pull/push/commit/validation and its own UUID.
  Both CAS blobs match their recorded hash/size/line count (856518bytes/178lines and
  879529bytes/204lines); final blob extends the exact commit snapshot. Both embedded
  appendwatch reports mark the session OK. No evidence of log/DB/CAS mismatch in this run.
- DuckDB TABLE COMMENT remains the expected initial empty-file anchor (ordinal0/byte0);
  per-line hashes cover all appended records. This is normal for a fresh --new lifetime,
  not an unpromoted-resume failure. No hash/config/anchor was modified.
- NiceGUI has7run events ending codex_exited(exit0) -> failed, an empty queue, and the
  original307-researcher snapshot with0attempts/0outcomes. This is expected autonomy: no
  post-run Query IPC occurred. Codex exit0 does not mean Backend validation passed.
- Matching persisted artifacts resolve the concern about missing projection for this run;
  they do not establish the missing clean-close acknowledgement or remove the cancellation
  window identified above. No other historical captures or original production paths opened.

Duplicate Backend warning lines occur during validation and authoritative replay verification,
not duplicate persisted /validate records (the recovered log confirms exactly one).

Diagnostics: Dashboard's failed-run summary says detail=unspecified despite the preceding
final pull500; its final exception alone loses the Backend's useful earlier rollout_index
reason. The Backend warning does report that reason, whereas generic client500 is intentional.
Initial missing-socket messages resolve through normal IPC startup/query/clean closure; no
new missing-file defect. No Playwright teardown warning in this run. Existing Mode0 Plotly/
Kaleido deprecations (11) and audit_read multithreaded fork warning (1) remain; neither is shown
to cause these failures. Main-pipeline XPASS is its explicitly documented stale reviewed note.

Fresh upstream reproduction: the exact eight failed preflight cases reproduce locally,
8failed/15deselected4.01s, through the isolated pytest plugin, no network/root/production data.
They should have been caught BEFORE another human acceptance run. Earlier selected P25 and
browser/root passes did not cover the full ordinary graph, despite the handoff claim. Next
correction must retain the five lifecycle cases and meaningful log/exit-failure coverage, run
these cheap leaves locally, and only then request another expensive live workflow. Do not
mask this with P26-P30 implementation, relaxed assertions/skips, old aliases or task rewrites.

Other fresh leaves: Ruff + default mypy68files + AI strict mypy55files PASS; main174passed,
5skipped,6xfailed,1documented XPASS; step4 normal4passed1skip, slow1skip4deselected; Mode3 all6
PASS; Mode0 all4PASS; main real API3passed1expected xfail. Live completion/card/export/replay
acceptance is NOT reached; host synthetic DOCX export passing is a distinct boundary.
Wrapper status/grep quirks are unchanged and previously rejected for modification; actual
leaf summaries/exit statuses, not “grep: no FAILED”, determine the result.

### Operator-log corrections — implemented and targeted checks passed; full gate pending

Scope is separate from P26-P30. All seven corrections are implemented; verification status is below. On2026-09-19 the operator approved
exactly HUMANS sections2 and4–7; their complete bodies and fenced code snippets are copied
verbatim below, with headings reflecting current implementation/verification status. This is the implementation
boundary, not permission for broader refactoring. Item3 is explicitly superseded by deletion
of elevate-triggering tests. Preserve existing assertions/timeouts in retained tests and all
isolation/ownership constraints; any deviation needs explicit approval before implementation.

1. **Web-action evidence eligibility — IMPLEMENTED, locally verified:** add find alongside
   search_query/open/click. Operator proposes unsupported arguments make the affected
   evidence ineligible rather than fail the whole rollout with pull500. Latest explicit
   refinement: KEEP the existing choice() and exclude unsupported calls from eligible
   candidates; no without-replacement loop. An exhausted eligible pool enters the existing
   evidence-retry handling. This supersedes the earlier proposal to retain fatal action-count
   enforcement and the briefly discussed resampling loop. Implementation is now explicitly
   authorized for this correction only, not the other operator-log findings.

```python
WEB_FIND_ACTION = "find"
ELIGIBLE_WEB_ACTIONS = frozenset({
    WEB_SEARCH_QUERY_ACTION,
    WEB_OPEN_ACTION,
    WEB_CLICK_ACTION,
    WEB_FIND_ACTION,
})
```

   Schema evidence: operator supplied
   chats/chats-20260911-ai-augment-prod/ChatGPT-Discover_Web_Run_Schema.md, specifically
   operator-designated message "## 25 - ChatGPT" (lines2206–2294), read in full. The tagged
   rust-v0.146.0-alpha.3.1 SearchCommands source reproduced there (encoded source at line486)
   has ten independent optional operation arrays: search_query, image_query, open, click,
   find, screenshot, finance, weather, sports, time; plus response_length. FindOperation
   requires ref_id/pattern. Multiple action arrays are allowed, not an exactly-one union;
   tool.rs command_action is only a lossy summary. Optional nulls/empty command input are
   accepted by the upstream deserializer; that does not make them eligible evidence here.
   calculator/product_query are not declared in this tagged schema. Source was inspected in the supplied
   export, not independently fetched. Treat our supported subset as evidence policy,
   not a claim that other valid web.run commands are malformed. response_length and known
   nested action parameters are not unsupported actions. Check all argument keys against
   the four supported actions plus response_length, with at least one nonempty supported
   action. Multiple supported actions are not an upstream schema error; any unsupported
   argument excludes the call, even when another key is supported. No full tool-schema
   model, support for the other six actions, event-summary inference or catch-all fallback.
   Operator additionally supplied protected/src/agent_runtime/docs/search.rs. Read in full;
   SearchCommands/FindOperation/response_length confirm this rule. File left untouched.
   Operator's follow-up explicitly supports combinations because upstream is authoritative.
   No additional Rust source needed for this change.

   Implementation: _web_arguments returns None for unsupported/no-active arguments, with
   one Locale-owned info log; JSON/non-object corruption still raises. _has_cite_marker
   separates output discovery from strict _cited_fco_text validation, which runs only after
   arguments qualify. Ineligible calls produce no indexed rows, so both exact and near
   candidate SQL naturally excludes them; no SQL, choice(), assessment or retry rewrite.
   Keep malformed supported chains, duplicate IDs, citation/result ambiguity, session/CAS/
   appendwatch corruption fail-closed; no generic catch-and-continue.
   _exact_evidence_candidates finds occurrences of the submitted excerpt; assessment then
   matches its exact URL and uses one seeded EVIDENCE_RANDOM.choice, not an existing
   without-replacement loop. The proposed alternatives are provenance for THAT submitted
   excerpt/URL, not unrelated evidence or automatic submission rewriting. Operator explicitly
   chose prefiltering unsupported candidates and retaining the existing seeded choice;
   no sampling-loop change is authorized or needed. Apply the same eligibility to
   near-match candidates so they
   cannot resurrect unsupported evidence. No cross-item/global non-reuse rule is proposed.
   Existing unmatched assessment -> _process_retry_attempt -> _assessment_public_detail ->
   DUCKDB_EVIDENCE_VALIDATION rejection already yields RETRY and pull200 Markdown guidance,
   not500. Preserve codex-match-v2 near-match distinction and all existing retry obligations.
   An unused unsupported call must not force an otherwise valid submission to retry.

   Update the existing minimal_rollout_records arguments map with find targets including
   ref_id and pattern; make the existing action-test parameters explicitly cover all four
   wire actions (not only derive expected coverage from the implementation's whitelist).
   Add a small sanitized four-target find chain with find_in_page event, two URL-backed
   results and two URL-less errors. Verify the existing index produces exactly the valid
   refs. Include coverage for unsupported-only and supported/unsupported mixed calls,
   alternate same-excerpt/URL provenance, exhausted candidates and existing retry guidance,
   ordinary response_length, plus unreferenced unsupported calls. Preserve negative
   missing/ambiguous/malformed supported-chain checks and verify current-rule live/replay
   behavior with synthetic records. Never modify supplied artifacts or substitute
   a saved historical verdict: the recovered rejected validation is not promised replayable
   under a rule that changes its recomputed result. No migration/fallback/version shortcut.

   Completion evidence (2026-09-18):
   - Production diff confined to api.py and Backend locale.py: find/response_length peer
     constants, supported-subset eligibility, early exclusion before strict output parsing,
     and one informative exclusion log. choice(), SQL, retry logic, Store, server, Dashboard,
     tasks and P26-P30 are unchanged. Original CAS/replay/DB artifacts were not modified.
   - Added focused tests to existing test_api.py/test_http_interceptor.py: each supported
     action and their combination; six upstream unsupported actions, unknown keys and mixed
     supported/unsupported calls; multi-block unsupported output; exact/near candidate pools;
     four-target find with two URL-less errors; malformed JSON/non-object/duplicate/order/
     citation-integrity failures; real persisted validation and pull410 versus retry200 with
     baseline/audit persistence; identical query/logical DB after explicit replay, unchanged log.
     Existing random-choice/seeded-selection and retry assertions remain.
   - Before fix: focused reproduction3failed/3passed at maxfail3 (find, supported combination,
     unsupported image action). After fix:32focused passed3.29s,7additional find/integrity
     passed2.48s,4real validation/replay passed19.45s. These overlap the final batch below.
   - Final feasible API + HTTP-interceptor regression:246passed,1existing skip,3deselected
     in212.19s. Command: pixi run -e detour-ai-augment env python -m pytest -q
     src/detours/detour_ai_augment/tests/backend/test_api.py
     src/detours/detour_ai_augment/tests/backend/test_http_interceptor.py
     -m 'not python_subprocess'
     -k 'not captured_operator_push and not historical_haanen_retry'.
     Exclusions: process-lock subprocess and two historical capture cases. Existing skip:
     multiple-match rejection test, because multiple matches are intentionally allowed.
   - Ruff PASS; configured strict mypy PASS4changed Python files; full diff whitespace PASS.
     Initial mypy caught heterogeneous empty-tuple chained comparisons and indirect Locale
     import in new tests; corrected to separate assertions/direct import, no casts/ignores.
   - No network/browser/root/live-Codex acceptance run. Current correction is complete, not
     a full pre-commit-operator acceptance claim. Corrections2 and4–7 are implemented and locally verified; targeted delegated verification passed; full operator acceptance remains pending;
     correction3's authorized deletion is complete. P26–P30 are now complete; P31 including its approved UUID amendment is complete and locally verified below.

2. **IMPLEMENTED — Correct the five stale IPC test callpoints**

In `test_operator_e2e_preflight.py`:

```python
monkeypatch.setattr(
    backend_server,
    "start_dashboard_query_server",
    Mock(side_effect=AssertionError),
)
```

Remove the unused `backend_ipc` import. Preserve all five cases and assertions. No compatibility alias.

3. **IMPLEMENTED — Remove elevate-triggering tests entirely**

   Operator explicitly rejected the replacement-wrapper-test direction: "purge elevate
   triggering tests altogether". Remove test_elevate_retains_failures_and_reports_failed_lines
   and its none/install/browser parametrization from protected/tests/operator/
   test_operator_e2e_preflight.py, plus the now-unused tomllib import. Search the active detour
   tests for any other elevate-triggering tests and remove only those if present. Do not
   replace them with a shim, source-string assertion, skip or a different elevate invocation.
   Actual elevate command, log/status/FAILED-grep scaffolding and ordinary tasks stay untouched.
   Preserve the unrelated preflight tests. This supersedes the former unapproved item3 code
   snippets; they are deliberately removed from WORK, not retained as pending implementation.

   Provenance: git blame/show identifies introduction in commit
   2eeb7c4c0f754d483e975cb75376ec238fa91af7 (2026-09-17, "ai augment task: address test failures").
   Its historical WORK records P18 tests of the real GNU script/PTY logger, run-all behavior,
   retained failure status and FAILED reporting. The temporary verification batch was narrowed
   from five controlled cases to the committed three install/browser cases. The permanent
   preflight test reads current pyproject.toml's elevate command and runs the actual shell
   in tmp_path while replacing Python leaves with sentinel outcomes. It enters the ordinary
   suite because test-detour-ai-augment explicitly includes this preflight module; there is
   no recursive pixi run elevate. Binding those tests to the mutable install/browser payload
   was the mistake: correct restoration to "Nothing to elevate" broke all three. The operator
   now authorizes deleting that dependency entirely, not redesigning its coverage.

   Completion2026-09-19: removed the one parametrized test (all three cases) and unused
   tomllib import. No elevate references remain in the detour's tests. AST comparison to
   HEAD confirms every retained function/class is unchanged; only that test definition was
   removed. At item3 completion, the actual elevate task and all other pyproject tasks were unchanged. Ruff PASS;
   configured strict mypy PASS1file; pytest collection succeeded with20 remaining cases
   (6.11s), none targeting elevate. This is collection evidence, not a claim those20 tests
   pass; item2 was subsequently corrected and its full20-case preflight run passed above.

4. **IMPLEMENTED; HOST CHROME PASSED — Make the spacing test measure a ready card**

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

5. **IMPLEMENTED; LOCAL VERIFICATION PASSED — Finish Backend shutdown before propagating cancellation**

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

6. **IMPLEMENTED; LOCAL VERIFICATION PASSED — Include the actual Backend error in operator-test failures**

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

7. **IMPLEMENTED; LOCAL VERIFICATION PASSED — Run the audit probe outside multithreaded pytest**

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

**No correction in these seven items for normal/unchanged observations:**
unchanged NiceGUI snapshot, duplicate live/replay warning, old unreproduced pre-start hang,
F7 report, documented main-pipeline XPASS. Mode0 dependency deprecations are outside this
isolated detour scope: no main-pipeline/other-detour/environment/lockfile changes. Existing
ordinary-wrapper status/grep restructuring remains rejected; no pyproject task edit proposed.
The previously skipped provider leaf now passes in elevate, without changing && or tasks.
The later missing-socket patch was rolled back; operator elected to keep existing
readiness polling/diagnostics. No follow-up logging implementation is pending.

**Pre-handoff verification for approved corrections:** reproduce regressions before each fix; run all
feasible normal-suite leaves including operator preflight, changed API/index/replay and UI/
audit tests, Ruff and strict mypy. List environment-blocked leaves explicitly. Then prepare
only necessary delegated host-Chrome/layout/cleanup and previously blocked real-provider
checks in elevate, with machine checks, safe logging and preserved failure status/FAILED grep.
No password capture or SSH verbosity, no altered browser, no repeated root tests unless the
new diff touches their boundary. Full pre-commit-operator/live Codex only after those checks.
These corrections are separate from P26–P30. The operator subsequently lifted the full
pre-commit-operator prerequisite for implementing P26–P30 and deferred new harness issues
to P31 (subsequently implemented, including its separately approved UUID amendment). Full acceptance still requires reviewing every actual leaf, intentional
skip/xfail, warning, wait, cleanup and preservation result; it is not claimed here. Corrections2 and4–7 are implemented and locally verified; targeted delegated verification passed; full operator acceptance remains pending; correction3's
authorized deletion is complete. New defects or scope deviations still need a narrow
proposal/approval rather than broadening implementation silently.

Latest operator-assisted diagnostics (2026-09-18): operator authorized putting the proposed
checks in elevate with embedded machine checks, rather than separate commands or instructions
about where to run them. The completed batch required macOS before diagnostics/log replacement,
ran test_ui_e2e with default Chrome and the exact Dashboard ProxyJump busy command
(15s diagnostic timeout), and automatically dispatched interpreter/appendwatch --help to
the named aicode guest via limactl. Guest verifies Linux ARM64; non-interactive sudo -n and
setpriv run the actual selected interpreter/watcher as nobody with no supplementary groups.
No interactive sudo authentication or script/PTY wrapper; guest dispatch has stdin closed.
Unavailable privileges fail explicitly without requesting a password. namei prints interpreter
traversal permissions. No browser install, permission change,
live Codex run or remote process killing. A timed-out diagnostic kills only its own local
SSH process group. Combined stdout/stderr goes to elevate.log; all three checks run despite
earlier failure, aggregate status and FAILED grep retained. Only elevate and WORK changed;
no ordinary task edits. TOML/outer+batch+guest shell syntax, embedded SSH Python compilation,
wrong-machine guard and comparison proving other TOML settings unchanged all PASS locally.
First reviewed delegated log: host module9passed29.53s (eight real Chrome browser tests plus one
browser-free fixture check); slowest call7.08s, real owned query4.43s, clean child/host shutdown,
no timeout/Ctrl+C. SSH probe to aivm:exit0,0.33s,empty stdout (idle). The root diagnostic DID
NOT RUN: limactl reports the explicitly targeted aicode instance is stopped. Combined status1
is therefore correct, not a browser/SSH failure or a new watcher result.
Machine roles: macOS is the production Dashboard/browser-test host; aicode is the Linux
ARM64 development/test guest; aivm is the remote agent runtime and only the SSH busy-check
target. Log platform/path confirms macOS execution; no test batch was dispatched to aivm.
Operator redacted SSH key details from the log. The added -v unnecessarily printed public-key
fingerprints/identity paths; removed it and clarified the SSH phase label. Preserve ordinary
SSH errors/status/timing, do not request unredacted key material. Existing optional known-host
file/security-key-provider debug messages were not connection failures (actual exchange exits0).
Operator also flagged the sudo password prompt in recorded execution. Removed sudo -v and
the guest script/PTY wrapper entirely, rather than try to transfer sudo authentication between
different TTYs. Only sudo -n remains and guest stdin is /dev/null. No password input is requested
or collected by this diagnostic. Do not read/request an unredacted credential-bearing log;
previous log files were not modified.
Latest rerun (log modified2026-09-18 19:00UTC): host9passed29.72s; slowest call7.11s,
real query4.26s; SSH to aivm exits0 in0.32s, idle. aicode now runs the noninteractive check:
Python starts but cannot locate its platform-independent/dependent libraries, then fatally
fails importing encodings. Watcher code never starts; no monitoring pass. Combined status1.
The follow-up below establishes the actual path/access failure rather than treating this as
a missing Pydantic package or changing Python environment variables.

Focused elevate batch completed: only the aicode runtime-access diagnosis; no repeated Chrome/
SSH checks. Retains macOS guard, named aicode dispatch, Linux ARM64 check, closed stdin and sudo -n.
Normal-user interpreter identifies its actual prefix/stdlib/encodings paths, then the batch
prints nobody identity, namei chains and actual read/traverse checks under that identity before
executing the unchanged watcher --help with the same interpreter. Every subprocess is bounded.
This launches a fresh nobody Python; no privileged import preload, PYTHONHOME/PYTHONPATH override,
package install, permission change or test weakening. TOML/outer+guest shell syntax, embedded
Python compilation, wrong-machine guard and unchanged-other-TOML comparison PASS locally.
Reviewed result: uid65534(nobody),gid65534(nogroup), no supplementary groups. Every tested runtime
path is unreadable to nobody; prefix/stdlib/encodings directories also fail traversal. Normal
user resolves those paths successfully. namei identifies /home/anonymous.linux as0750, while
the listed descendant directories are0775 and encodings/__init__.py is0664. The watcher source
outside that home is readable (access exit0). Fresh nobody Python fails encodings import,
watcher startup exit1 and combined status1. No monitoring tests ran. Enough evidence for a
test-runtime/credential mismatch; no further diagnostic rerun requested. Operator correctly
challenged granting nobody home access when the caller already owns the runtime. ACL proposal
withdrawn; the narrower proposed harness correction is recorded below.
All future operator execution requests must be prepared in elevate with embedded machine
checks, not pasted as separate manual commands.
Operator requested reverting idle elevate to the original "Nothing to elevate" shape:
restored that exact placeholder with script/log/FAILED-grep/exit-status scaffolding. No
further diagnostic run is pending; do not execute a permission change before approval.

Latest browser-routing correction is APPROVED and IMPLEMENTED, including the operator's
additional one-line comment directly above PYTEST_ADDOPTS. It supersedes the earlier
marker/new-task proposal: change ONLY pre-commit-operator, not test modules/plugin or other
tasks. Scoped PYTEST_ADDOPTS in the existing aicode shell excludes the entire test_ui_e2e
module from that guest invocation only. Existing macOS BSD script logging runs the entire
nine-test module on the host before pre-commit-extra-operator. Keep existing PYTEST_ADDOPTS,
Chrome selection, test bodies and all grep/status/run-all behavior. No new marker/task or
browser fallback. TOML and outer/guest/host shell syntax plus actual parsed routing checked;
comparison confirms other task/settings unchanged (elevate separately restored to its idle
placeholder as requested). No operator commands executed locally or full acceptance claimed.

```diff
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -341,12 +341,14 @@
 [tool.pixi.tasks.pre-commit-operator]
 cwd = "."
-# run all in lima except operator tests.
+# run non-browser tests in lima; browser and operator tests on macOS.
 # using bash -c so that pixi does not
 # exit on first failed command.
 cmd = """
 bash -c '
   limactl shell aicode -- bash -c '"'"'
     export PATH="$HOME/.pixi/bin:$PATH"
+    # Exclude browser tests in this guest invocation; run them with host Chrome below.
+    export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:+$PYTEST_ADDOPTS }--ignore=src/detours/detour_ai_augment/tests/control_centre/test_ui_e2e.py"
     script -e -c "
       {
         pixi run pre-commit
@@ -355,6 +357,10 @@
     grep -q "FAILED" logs/pre-commit.log &&
     echo "grep: no FAILED"
   '"'"'
+  script -a \
+    logs/pre-commit.log \
+    bash -c '"'"'pixi run -e detour-ai-augment python -m pytest -vv -srA \
+      src/detours/detour_ai_augment/tests/control_centre/test_ui_e2e.py 2>&1'"'"'
   pixi run pre-commit-extra-operator
 '
 """
```

Root test harness is a SEPARATE APPROVED and IMPLEMENTED correction, not part of the browser-routing patch.
The ACL proposal is withdrawn. Tests intentionally run pytest as root and launch the watcher
unprivileged via nobody_credentials/drop_privileges; moving its interpreter into the invoking
user's private Pixi environment made that identity incompatible with runtime access.
Approved exact fix: select the original non-root sudo invoker via SUDO_UID/SUDO_GID,
not nobody, for the existing privilege-drop helper and temporary-tree ownership. Fail clearly
if invoker credentials are missing/invalid or root; no invented account/fallback/new skip.
Keep supplementary-group clearing, root-owned0700 denial fixtures, real watcher subprocesses,
permission transitions and every EACCES assertion unchanged. Update only helper naming and
direct explanatory text/callpoints. No home ACL/chmod, package/runtime relocation or preload.
The three existing privileged tests were verified through elevate using sudo -n; ordinary root
task unchanged. That verification used the macOS guard, explicit aicode dispatch and Linux ARM64
guard, same root-test environment/selection, closed stdin and sudo -n. No authentication prompt,
SSH verbosity, ACL edit or repeated Chrome/busy-probe checks. After the passing run, restored
elevate to the requested "Nothing to elevate" placeholder with script/log/status/grep scaffolding.

Exact approved helper replacement, in protected/tests/backend/
test_appendwatch.py; remove now-unused pwd import and update the introductory explanation:

```python
def sudo_invoker_credentials() -> tuple[int, int] | None:
    if os.geteuid() != 0:
        return None
    try:
        uid = int(os.environ["SUDO_UID"])
        gid = int(os.environ["SUDO_GID"])
    except (KeyError, ValueError) as exc:
        pytest.fail(
            f"Permission tests require valid SUDO_UID/SUDO_GID: {exc}",
            pytrace=False,
        )
    if uid <= 0 or gid < 0:
        pytest.fail("Permission tests require a non-root sudo invoker", pytrace=False)
    return uid, gid


def _permission_test_tree() -> tuple[Path, Path, Path, int, int]:
    credentials = sudo_invoker_credentials()
    if credentials is None:
        pytest.skip("requires root for real EACCES integration")
    uid, gid = credentials
    # Existing temporary-tree creation/chown/chmod and return remain unchanged.
```

Existing drop_privileges continues clearing supplementary groups, setting gid then uid.
Only non-root pytest retains its existing skip; missing/bad invoker under root fails rather
than skips. No existing permission-denial assertion or root-owned0700 fixture changes.
Implementation audit confirms only the approved helper/callpoint, unused pwd import and
introductory docstring changed. Local evidence:42passed,8deselected18.43s for test_appendwatch
with -m "not needs_sudo" -k "not socket and not nonregular_substitution"; exclusions respect
the no-root/no-socket execution boundary, not a pass for those cases. Ruff PASS; configured
strict mypy PASS1file. Exact delegated selection collects3/73tests (70deselected) in0.36s.
elevate TOML/shell syntax and wrong-machine guard PASS; no privileged commands executed here.
First delegated root rerun failed3before startup using the pre-fix test file: all three
traceback callsites match the old revision,12lines before the corrected version. Operator
confirmed forgetting to pull, then updated and reran. Latest reviewed elevate.log confirms
3passed,70deselected1.54s, root test status0. No additional implementation change or proposed
source-hash guard was applied between runs. Root verification is complete.
That targeted result supported the subsequent full operator run, now reviewed above.
Chrome placement/root credentials are resolved; the subsequent full run exposed
independent findings, including cheap preflight cases missed before handoff. Those corrections
are now implemented and targeted checks pass; fresh full acceptance remains pending.
That earlier review required no further batch. The completed post-correction elevate batch
is recorded at the top; current P26–P30 statuses are recorded separately above.

Rejected changes MUST NOT return: root preload-before-drop, synthetic DuckDB config/binary
that conceals prerequisites, substituted-query browser test, raised launcher timeout,
pre-commit wrapper restructuring/status/grep corrections. No production storage cleanup.
A prior direct importlib.find_spec on a NiceGUI submodule imported NiceGUI outside isolation;
default storage may have been accessed. No preservation claim for that command and no cleanup
followed. Never repeat ad-hoc NiceGUI imports; use installed-source reads or isolated tests.

## Verification discipline and operator command graph

TASK requires cheap upstream coverage before costly human production E2E. Review changed
callers AND fixtures/imports/launchers: passing unit models or startup conditions do not prove
real interpreter selection, queue Start, query helper or browser channel. Never replace the
boundary under assertion, silently skip prerequisites or weaken assertions/timeouts. Record
initial failures separately from eventual passes. Reuse valid evidence; broad unrelated edits
are not authorized by testing requirements.

Operator runs exactly pixi run pre-commit-operator. Recheck actual pyproject definitions before
handoff; inspect every independently runnable leaf and shell short-circuit/environment:

```text
pre-commit-operator
  Lima aicode: pre-commit
    lint -> default Ruff + default mypy + AI strict mypy
    test-repl -> default test .
    test-detours
      step4 normal + slow (default)
      mode3 (default)
      mode0 (mode0 env)
      AI normal/backend/operator-preflight, then real_api institution if success
  macOS host: test_ui_e2e (Chrome), appended to pre-commit.log
  pre-commit-extra-operator
    Lima aicode: default real_api then AI needs_sudo backend tests
    host: real AI operator workflow
```

Fresh per-leaf results and skipped downstream leaves are in the operator findings above.
Unchanged wrappers retain known status/grep quirks; inspect actual leaves. The operator review
exposed incomplete upstream graph coverage; selected passing batches must not be presented
as full ordinary-suite coverage.

Only Assistant-owned elevate can be freely adjusted for targeted delegated verification,
with detailed logs/from_operator/elevate.log, failure status and FAILED grep retained. Prepare
small concrete batches AFTER feasible local checks, then request operator execution; no
assumed pass or hidden live-Codex run. Ordinary task edits need explicit approval except the
already approved interpreter substitutions, narrowly approved pre-commit-operator macOS
browser routing, and F7 fixes for a proven variable defect.

Tests: existing protected/tests/pytest_plugin.py isolates NICEGUI_STORAGE_PATH before import,
unsets NICEGUI_REDIS_URL, fails if NiceGUI imported too early. Children use per-test
nicegui_test_environment; original-storage preservation checks remain. Explicit Lima fixture
only for real consumers. Named python_process helpers and python_subprocess/socketless_lifecycle
markers stay in protected plugin; sockets are not bypassed by subprocesses. Do not run
browser/operator/network/privileged/historical-capture tests here. Use real synthetic Store,
DB/log, in-process ASGI/WSGI, startup CLI and meaningful error paths for P25.

Relevant modules: tests/backend/{test_api,test_ipc,test_backend_store,test_http_interceptor}.py,
tests/control_centre/test_ui.py (includes startup conditions), protected test/plugin/operator
fixture callpoints and repository-root tests/test_http_request_log.py. Exclude real_api,
operator, needs_sudo, captured_operator_push, historical_haanen_retry, real_mode_0600_unix_socket.
Do not execute main CLI, inaccessible artifact fixtures, paused BDD or sample_deploy.

```bash
pixi run -e detour-ai-augment env ruff check src/detours/detour_ai_augment src/helpers/data_models/http_request_log.py
pixi run -e detour-ai-augment env mypy --config-file src/detours/detour_ai_augment/mypy.ini src/detours/detour_ai_augment src/helpers/data_models/http_request_log.py
```

## Mandatory constraints for continuation

- After compaction reread TASK and WORK IN FULL. Keep WORK current, remove stale pending claims.
- Only the current detour contract exists: no historical-schema special cases, shape-based
  migration or alternate parser. No special output-schema guard. P24 is complete; current
  implementation is ONLY P25's exact approved contour/snippets above, with ACK/NAK and
  update_pull_state, plus the approved P26 typed-construction/content-type, P27 literal-audit,
  P28 protocol-ownership/inheritance, P29 original-pull-ID rename and P30 Store-owned
  current-record/session/outcome-metadata/linkage additions.
  Current state: P26–P30 complete in order, including P30's explicit
  persistence-first clarification and initial-validation addition. The prior missing-session persistence question is withdrawn.
  Operator explicitly lifted the earlier full-acceptance gate. Harness/artifact-directory
  corrections are P31, complete and locally verified including its approved reference-check amendment. Earlier corrections2–7 are implemented;
  item3 deleted elevate-triggering tests. No unrelated audit, DTO-default removal or
  card-format tightening.
- Operator forbids cast: changes must use genuinely compatible types, not cast or substitute
  type suppressions. No unrelated codebase-wide refactor. Store persistence and pull-state
  updates must not be named publishing; that term is reserved for DOCX/TXT in the new scope.
- All commands via pixi run -e detour-ai-augment; Ruff/mypy/pytest via env. Git read-only.
- Task edits: prior interpreter substitutions, agent-owned elevate, approved pre-commit-operator host-browser routing, F7 fixes for proven environment-variable expansion defects, and P35's exact sudo -k addition only. Other pre-commit structure/status/grep changes remain rejected.
- Never run/import src.repl, edit src/cli.py, import another detour or edit TASK. HUMANS is
  human-maintained; the operator explicitly authorized only this 2026-09-18 post-find
  proposal/status update. No broader HUMANS editing permission is inferred.
- Only allowed production data is data/scisci_process.duckdb READ ONLY. No other data/,
  .aicode/ or historical captures. Isolated temporary test fixtures are permitted.
- No network/socket probes/escalation. Paused BDD permits only its completed model conversion.
- Preserve operator edits/staging, human-signed comments and narrowly approved boundaries.
- sample_deploy is excluded from edits, conversion inventories and test execution.
