> I copy and paste into here
> from chat if there is some bits
> I would like to persist, for a while.
> The text below may be AI-generated;
> this file is just called `HUMANS.md`
> because I maintain it vs. agents.
> signed off: Pavel

# propose the exact shape for review with code snippets; as it's documented in P31 is currently too broad. i would like to see the exact shape you propose to change

I propose **four test-only changes**. No production code, task definitions, timeouts, or cleanup-policy changes. I’ve replaced the broad P31 description in [WORK](/home/moshi/2026-01-02_enrich_full_df/tasks/tasks-20260911-ai-augment-prod/var/WORK.md) with this proposal, still **unapproved**.

## 1. Correct the artifact validator without blanket-allowing external records

In `protected/tests/operator/test_operator_e2e.py`, add this private helper. `submission_models` imports the existing pasted model module’s endpoint constants; that module is not modified.

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
        (
            HTTP_GET_METHOD,
            submission_models.OPENALEX_SCHEME,
            submission_models.OPENALEX_HOST,
            submission_models.OPENALEX_INSTITUTIONS_PATH,
        ),
        (
            HTTP_GET_METHOD,
            submission_models.ROR_SCHEME,
            submission_models.ROR_HOST,
            submission_models.ROR_ORGANIZATIONS_PATH,
        ),
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
            assert (
                linked.model_dump() == by_id[linked.record_id].model_dump()
            ), linked.record_id
            assert (
                ordinal[linked.record_id] < ordinal[record.record_id]
            ), linked.record_id

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

Replace the existing route-only assertion in `validate_workflow_artifacts` with:

```python
validations = _validate_workflow_http_records(records)
```

After its existing outcome parsing, add explicit current-link checks:

```python
assert run_outcome_snapshot.pull_record_id == commit_request_body.pull_record.record_id
assert run_outcome_snapshot.push_record_id == commit_request_body.push_record.record_id
assert run_outcome_snapshot.commit_record_id == commit_record.record_id
assert run_outcome_snapshot.run_outcome_record_id == run_outcome_record.record_id

assert run_outcome_snapshot.validation_record_id is not None
assert run_outcome_snapshot.validation_record_id in validations
validation = validations[run_outcome_snapshot.validation_record_id]

assert validation.validation_request_body.commit_record == commit_record
assert (
    validation.validation_request_body.post_commit_validation.result
    is BackendLifecycle.ACCEPTED
)
assert (
    commit_ordinal
    < _record_ordinal(records, validation.record_id)
    < gone_pull_ordinal
)
assert backend_api._http_header_value(
    gone_pull.response_headers, ETAG_HEADER,
) == f'"{validation.record_id}"'

outcome_request = validated_run_outcome.run_outcome_request
assert outcome_request.session_id == session.session_id
if outcome_request.run_outcome is RunLifecycle.COMPLETED:
    assert outcome_request.validation_record_id == validation.record_id
```

Existing DB, CAS, hash, appendwatch, accepted-commit and response assertions remain.

## 2. Capture the actual card and check current metadata

In `capture_completed_researcher_card`, replace only the footer selector and nonempty wait:

```python
card = page.get_by_test_id(control_ui.CARD_MARKDOWN_TEST_ID)
expect(card).to_contain_text(commit_record_id)
expect(page.get_by_test_id(control_ui.DOWNLOAD_CARD_DOCX_TEST_ID)).to_be_enabled()
card_text = card.inner_text().strip()
```

Preserve its empty-card check, browser-error assertion, timeout and cleanup.

Replace the obsolete commit-request-body card assertion with:

```python
from lxml.html import fromstring
from nicegui.elements.markdown import prepare_content

# Inside validate_workflow_artifacts:
if card_text is not None:
    expected_html = prepare_content(
        validated_run_outcome.model_dump_json(),
        extras="fenced-code-blocks tables",
    )
    expected_text = fromstring(expected_html).text_content().strip()

    metadata_position = card_text.index(
        KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_RECORD_COL,
    )
    outcome_position = card_text.index(expected_text)
    assert metadata_position < outcome_position
```

This compares the **full record’s rendered text**, not merely its UUIDs. Rendering matters: browser `inner_text()` is not raw Markdown, and Markdown can interpret underscores in JSON keys. Both dependencies already exist; no renderer change is proposed.

## 3. Keep each operator run together in a unique retained directory

Replace only the `operator_runtime` fixture:

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

Existing constructors already derive the generated config, DB, replay, CAS, output and child NiceGUI storage from this directory. Source remains a read-only-source symlink. Process/socket cleanup stays; artifacts are retained.

## 4. Exercise these exact helpers upstream

Reuse the existing completed-query fixture. It currently omits two exchanges/details required by the artifact checker.

In `completed_query_fixture_process`, add to the existing accepted-push construction:

```python
response_headers={LOCATION_HEADER.lower(): PULL_PATH},
```

After successful validation, before outcome persistence:

```python
assert validated.submission is not None
lines = [api.json_line(validated.submission.normalized_values())]
if validated.ground_truth_innerdict is not None:
    lines.append(
        api.json_line(api.select_columns(validated.ground_truth_innerdict.data)),
    )

store._append_authoritative_record(persisted_http_record(
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
```

Then:

- **Existing preflight module:** invoke the full `validate_workflow_artifacts` against that real synthetic Store/log/CAS fixture, without a browser.
- **Parameterized helper tests:** valid linked providers/initial validation; unknown routes, unreferenced/missing/changed providers, incorrect endpoints, missing/changed embedded references, reversed ordering and duplicate UUIDs.
- **Directory fixture checks:** distinct retained directories and contained generated paths.
- **Existing host Chrome test:** after its current Playwright context closes, but while its Dashboard still runs, invoke the actual capture and artifact helpers:

```python
card_text = operator.capture_completed_researcher_card(
    dashboard,
    runtime,
    namekey=ui_tests.STARTUP_NAMEKEY,
    queued_at_monotonic=time.monotonic(),
)
operator.validate_workflow_artifacts(
    runtime,
    namekey=ui_tests.STARTUP_NAMEKEY,
    expected_run_outcome_path=RunLifecycle.COMPLETED.to_run_outcome_path(),
    card_text=card_text,
)
```

The existing assertions and file-preservation checks remain. No live Codex is needed for these upstream checks.

**Status:** P26–P30 complete. P31 proposal documented; no P31 implementation performed.
