from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from random import Random
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import duckdb
import pytest

from src.detours.detour_ai_augment.src.backend import api
from src.detours.detour_ai_augment.src.control_centre.dashboard import ui as control_ui
from src.helpers.cards import write_cards_zip
from src.helpers.vars import KTP_FILENAME_COL

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPOSITORY_ROOT / "config_ai_augment.json"
TASK_DATA_DIR = REPOSITORY_ROOT / "tasks" / "tasks-20260731-tighten-api" / "data"
SAMPLE_DOCX_PATH = TASK_DATA_DIR / "sample.docx"
SAMPLE_MARKDOWN_PATH_NAME = "sample.md"
SAMPLE_ZIP_PATH_NAME = "sample.zip"
SAMPLE_CARD_ARCHIVE_NAME = "sample.docx"
SAMPLE_CARD_DRAW_NUMBER = "146"
SAMPLE_CARD_ROLLOUT_FILENAME = "sample-rollout.jsonl"
SAMPLE_CARD_ATTEMPT_ID = "sample-attempt"
SAMPLE_CARD_FRAGMENT = 1
PANDOC_PLAIN_COMMAND = ("pandoc", "--to", "plain")
FULL_CARD_PROCEDURE_NAMES = frozenset({
    "CodexMatchProcedure",
    "DocxMatchProcedure",
    "ParquetMatchProcedure",
    "XlsxMatchProcedure",
})
SESSION_TIMESTAMP = datetime(2026, 8, 7, tzinfo=timezone.utc)
SESSION_ID = control_ui.SessionId("019fb000-0000-7000-8000-000000000001")
TERMINATE_RETURN_CODE = -15
KILL_RETURN_CODE = -9
REMOTE_TEST_PID = control_ui.RemotePid(4321)
ROLLOUT_PATH = PurePosixPath(
    "/home/ai/.codex/sessions/2026/08/07/"
    "rollout-2026-08-07T00-00-00-019fb000-0000-7000-8000-000000000001.jsonl"
)
CONTROL_TIMEZONE = ZoneInfo("UTC")
TEST_OPENALEX_API_KEY = "test-openalex-api-key"
TEST_ASYNC_TIMEOUT_SECONDS = 1
TEST_BUSY_POLL_SECONDS = 0.01
TEST_SESSION_METADATA_VALUE = "test"
EARLIER_ARCHIVED_ATTEMPT_ID = "20260813T141450_027429Z_044215aac8c44200882531b10a2acfa6"
LATER_ARCHIVED_ATTEMPT_ID = "20260813T143347_182523Z_733e33fbf8e74c0aaf0aa0139d6a6f45"
TEST_ARCHIVE_FILENAME = "test.jsonl"
TEST_ARCHIVE_SHA256 = "0" * 64
TEST_ROLLOUT_RELATIVE_PATH = "2026/08/test.jsonl"
TEST_CONTROL_RUN_EVENTS_TOKEN = "test-control-run-events-token"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def researcher(
    number: int,
    *,
    cohort: control_ui.ResearcherCohort = (control_ui.ResearcherCohort.NO_GROUND_TRUTH),
    ineligibility_category: control_ui.IneligibilityCategory | None = None,
) -> control_ui.Researcher:
    return control_ui.Researcher(
        source_key=control_ui.SourceKey(f'{{"researcher": {number}}}'),
        rnd=number,
        draw_numbers=(str(number),),
        first_name=f"First {number}",
        last_name=f"Last {number}",
        cohort=cohort,
        ineligibility_category=ineligibility_category,
    )


def archived_attempt_manifest(
    *,
    researcher_item: control_ui.Researcher,
    attempt_id: str,
    run_id: UUID | None = None,
) -> api.ArchivedAttemptManifest:
    artifact = api.ArchivedArtifact(
        filename=TEST_ARCHIVE_FILENAME,
        size=0,
        sha256=TEST_ARCHIVE_SHA256,
    )
    return api.ArchivedAttemptManifest(
        attempt_id=attempt_id,
        stage=api.ATTEMPT_STAGE_ACCEPTED,
        result=api.ATTEMPT_RESULT_ACCEPTED,
        updated_at=SESSION_TIMESTAMP.isoformat(),
        artifacts=api.ArchivedAttemptArtifacts(
            rollout=api.ArchivedRolloutArtifact(
                filename=TEST_ARCHIVE_FILENAME,
                size=0,
                sha256=TEST_ARCHIVE_SHA256,
                line_count=1,
            ),
            appendwatch_report=artifact,
            http_request_log=artifact,
        ),
        rollout_relative_path=TEST_ROLLOUT_RELATIVE_PATH,
        run_id=run_id,
        source_key=researcher_item.source_key,
        session_id=SESSION_ID,
    )


def test_variable_specs_cover_every_ai_augment_column() -> None:
    assert (
        tuple(variable.ai_column for variable in control_ui.VARIABLE_SPECS)
        == api.AI_AUGMENT_COLUMNS
    )


def test_archived_attempt_reconciliation_delegates_and_reports_all_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    attempts_dir = tmp_path / "attempts"
    backend_runtime = cast(api.RuntimeConfiguration, object())
    expected = api.ArchivedAttemptRecovery(
        discovered=4,
        invalid=1,
        restored_attempt_ids=(
            EARLIER_ARCHIVED_ATTEMPT_ID,
            LATER_ARCHIVED_ATTEMPT_ID,
        ),
        restored_accepted_attempt_ids=(LATER_ARCHIVED_ATTEMPT_ID,),
        skipped_attempt_ids=("20260813T150000_000000Z_00000000000000000000000000000000",),
    )
    observed: list[tuple[api.RuntimeConfiguration, Path]] = []

    def fake_restore(
        runtime: api.RuntimeConfiguration,
        *,
        attempts_dir: Path,
    ) -> api.ArchivedAttemptRecovery:
        observed.append((runtime, attempts_dir))
        return expected

    monkeypatch.setattr(control_ui, "restore_archived_attempts", fake_restore)
    configuration = cast(
        control_ui.RuntimeConfiguration,
        SimpleNamespace(
            backend_runtime=backend_runtime,
        ),
    )
    repository = control_ui.DetourRepository(configuration=configuration)

    assert repository.reconcile_archived_attempts(attempts_dir=attempts_dir) == expected
    assert observed == [(backend_runtime, attempts_dir)]
    log_output = capsys.readouterr().out
    assert "restored 2" in log_output
    assert "accepted 1" in log_output
    assert "already present and skipped 1" in log_output
    assert "invalid 1" in log_output
    assert "discovered 4" in log_output


def test_validated_attempt_manifest_round_trips_from_detour_database(
    tmp_path: Path,
) -> None:
    detour_db_path = tmp_path / "detour.duckdb"
    researcher_item = researcher(1)
    manifest = archived_attempt_manifest(
        researcher_item=researcher_item,
        attempt_id=LATER_ARCHIVED_ATTEMPT_ID,
    )
    connection = duckdb.connect(str(detour_db_path))
    try:
        connection.execute(api.CREATE_ARCHIVED_ATTEMPTS_TABLE_SQL)
        connection.execute(
            api.INSERT_ARCHIVED_ATTEMPT_SQL,
            [manifest.attempt_id, manifest.model_dump_json()],
        )
    finally:
        connection.close()
    configuration = cast(
        control_ui.RuntimeConfiguration,
        SimpleNamespace(
            database_paths=control_ui.DatabasePaths(
                source_db=tmp_path / "source.duckdb",
                detour_db=detour_db_path,
            ),
        ),
    )

    loaded = control_ui.DetourRepository(
        configuration=configuration,
    ).load_attempt_manifests()

    assert loaded == {researcher_item.source_key: (manifest,)}


def test_real_config_derives_exact_innerdict_owned_cohorts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(control_ui.EXPORT_OPENALEX_API_KEY, TEST_OPENALEX_API_KEY)
    configuration = control_ui.RuntimeConfiguration(config_path=CONFIG_PATH)
    repository = control_ui.SourceRepository(configuration=configuration)

    researchers = repository.load_researchers()
    repeated_researchers = control_ui.SourceRepository(
        configuration=control_ui.RuntimeConfiguration(config_path=CONFIG_PATH)
    ).load_researchers()

    assert Counter(item.cohort for item in researchers) == {
        control_ui.ResearcherCohort.GROUND_TRUTH: api.EXPECTED_GROUND_TRUTH_RESEARCHERS,
        control_ui.ResearcherCohort.NO_GROUND_TRUTH: (api.EXPECTED_NO_GROUND_TRUTH_RESEARCHERS),
        control_ui.ResearcherCohort.INELIGIBLE: api.EXPECTED_INELIGIBLE_RESEARCHERS,
    }
    assert (
        Counter(
            item.ineligibility_category
            for item in researchers
            if item.ineligibility_category is not None
        )
        == api.EXPECTED_INELIGIBILITY_COUNTS
    )
    assert len(researchers) == api.EXPECTED_SOURCE_RESEARCHERS
    assert [(item.source_key, item.rnd) for item in researchers] == [
        (item.source_key, item.rnd) for item in repeated_researchers
    ]
    expected_rnd = list(
        range(
            api.RND_START,
            api.EXPECTED_SOURCE_RESEARCHERS + api.RND_START,
        )
    )
    Random(configuration.pipeline_config.sample_seed).shuffle(expected_rnd)
    assert {item.source_key: item.rnd for item in researchers} == dict(
        zip(
            sorted(item.source_key for item in researchers),
            expected_rnd,
            strict=True,
        )
    )
    assert researchers[0].draw_numbers == ("pilot.1",)
    excluded = next(item for item in researchers if item.source_key == api.EXCLUDED_SOURCE_KEY)
    assert excluded.cohort is control_ui.ResearcherCohort.INELIGIBLE
    assert (
        excluded.ineligibility_category
        is control_ui.IneligibilityCategory.EXCLUDED_DUPLICATE_SOURCE_KEY
    )
    assert (
        sum(len(item.draw_numbers) > 1 for item in researchers)
        == api.EXPECTED_MULTIDRAW_SOURCE_RESEARCHERS
    )
    assert all(item.draw_numbers for item in researchers)


def test_lima_appendwatch_topology_is_passed_exactly_to_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(control_ui.EXPORT_OPENALEX_API_KEY, TEST_OPENALEX_API_KEY)
    configuration = control_ui.RuntimeConfiguration(config_path=CONFIG_PATH)
    backend = control_ui.BackendSupervisor(
        repository_root=REPOSITORY_ROOT,
        config_path=CONFIG_PATH,
        control_url=control_ui.CONTROL_CENTRE_BASE_URL,
        openalex_api_key=TEST_OPENALEX_API_KEY,
        appendwatch_report=configuration.appendwatch_report,
        control_run_events_token=TEST_CONTROL_RUN_EVENTS_TOKEN,
    )

    environment = backend.environment()

    assert configuration.appendwatch_report.is_file()
    assert environment[api.APPENDWATCH_REPORT_ENV_NAME] == str(
        configuration.appendwatch_report
    )
    assert (
        environment[api.CONTROL_RUN_EVENTS_TOKEN_ENV_NAME]
        == TEST_CONTROL_RUN_EVENTS_TOKEN
    )


def test_config_registers_verified_release_map_without_writing_source_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(control_ui.EXPORT_OPENALEX_API_KEY, TEST_OPENALEX_API_KEY)
    source_db_path = control_ui.PipelineConfig.from_json(CONFIG_PATH).db_file
    source_hash_before = hashlib.sha256(source_db_path.read_bytes()).hexdigest()

    configuration = control_ui.RuntimeConfiguration(config_path=CONFIG_PATH)

    resource = configuration.backend_runtime.release_map
    assert resource is not None
    assert resource.group.value == "ktp_pipeline_artifact"
    assert resource.fragment_type.value == "csv_row"
    assert api.load_release_batches(resource)["125"] == "subset 7"
    assert hashlib.sha256(source_db_path.read_bytes()).hexdigest() == source_hash_before


def test_real_database_card_round_trips_identically_through_docx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(control_ui.EXPORT_OPENALEX_API_KEY, TEST_OPENALEX_API_KEY)
    real_configuration = control_ui.RuntimeConfiguration(config_path=CONFIG_PATH)
    detour_db_path = tmp_path / "card.duckdb"
    configuration = cast(
        control_ui.RuntimeConfiguration,
        SimpleNamespace(
            pipeline_config=real_configuration.pipeline_config,
            timezone=real_configuration.timezone,
            database_paths=control_ui.DatabasePaths(
                source_db=real_configuration.database_paths.source_db,
                detour_db=detour_db_path,
            ),
            backend_runtime=replace(
                real_configuration.backend_runtime,
                detour_db_path=detour_db_path,
            ),
        ),
    )
    source_repository = control_ui.SourceRepository(configuration=configuration)
    detour_repository = control_ui.DetourRepository(configuration=configuration)
    researcher = next(
        item
        for item in source_repository.load_researchers()
        if SAMPLE_CARD_DRAW_NUMBER in item.draw_numbers
    )
    source_inner_dicts = source_repository.load_source_card_innerdicts(
        researcher.source_key
    ).get_inner_by_key(researcher.source_key)
    assert {
        type(inner_dict.procedure).__name__ for inner_dict in source_inner_dicts
    } == FULL_CARD_PROCEDURE_NAMES - {"CodexMatchProcedure"}
    metadata = api.CompactSessionMetadata(
        originator=TEST_SESSION_METADATA_VALUE,
        source=TEST_SESSION_METADATA_VALUE,
        cli_version=TEST_SESSION_METADATA_VALUE,
        model_provider=TEST_SESSION_METADATA_VALUE,
        model=TEST_SESSION_METADATA_VALUE,
        reasoning_effort=TEST_SESSION_METADATA_VALUE,
        session_id=str(SESSION_ID),
        timestamp=SESSION_TIMESTAMP.isoformat(),
    )
    output_row: dict[str, object] = {
        column: TEST_SESSION_METADATA_VALUE for column, _data_type in api.CODEX_OUTPUT_SCHEMA
    }
    output_row.update({
        api.KTP_NAMEKEY_COL: researcher.source_key,
        api.KTP_FILENAME_COL: SAMPLE_CARD_ROLLOUT_FILENAME,
        api.KTP_FRAGMENT_COL: SAMPLE_CARD_FRAGMENT,
        api.KTP_FRAGMENT_TYPE_COL: api.ROLLOUT_LINE_FRAGMENT_TYPE,
        api.DRAW_LABEL: researcher.draw_number,
        api.KTP_FIRST_NAME_COL: researcher.first_name,
        api.KTP_LAST_NAME_COL: researcher.last_name,
        api.KTP_AI_AUGMENT_ATTEMPT_ID_COL: SAMPLE_CARD_ATTEMPT_ID,
        api.KTP_AI_AUGMENT_SESSION_METADATA_COL: metadata.model_dump_json(),
    })
    connection = duckdb.connect(str(detour_db_path))
    try:
        api.append_codex_output(connection, output_row)
    finally:
        connection.close()
    renderer = control_ui.ResearcherCardRenderer(
        source_repository=source_repository,
        detour_repository=detour_repository,
        configuration=configuration,
    )
    accepted_attempts = detour_repository.load_accepted_attempts()
    assert tuple(accepted_attempts) == (researcher.source_key,)
    source_key = researcher.source_key
    inner_dicts = renderer.build_outer_dict(source_key).get_inner_by_key(source_key)
    assert {
        type(inner_dict.procedure).__name__ for inner_dict in inner_dicts
    } == FULL_CARD_PROCEDURE_NAMES

    card = renderer.render(source_key)
    assert all(
        str(inner_dict.data[KTP_FILENAME_COL]) in card.markdown for inner_dict in inner_dicts
    )
    zip_path = write_cards_zip(
        {SAMPLE_DOCX_PATH.stem: card.markdown},
        tmp_path,
        SAMPLE_ZIP_PATH_NAME,
        output_format="docx",
        reference_docx=real_configuration.pipeline_config.pandoc_reference_docx,
        docx_workers=1,
    )
    with ZipFile(zip_path) as archive:
        assert archive.namelist() == [SAMPLE_CARD_ARCHIVE_NAME]
        sample_docx = archive.read(SAMPLE_CARD_ARCHIVE_NAME)
    SAMPLE_DOCX_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_DOCX_PATH.write_bytes(sample_docx)

    markdown_path = tmp_path / SAMPLE_MARKDOWN_PATH_NAME
    markdown_path.write_text(card.markdown, encoding="utf-8")
    expected_plain_text = subprocess.run(
        [*PANDOC_PLAIN_COMMAND, str(markdown_path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    docx_plain_text = subprocess.run(
        [*PANDOC_PLAIN_COMMAND, str(SAMPLE_DOCX_PATH)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    assert docx_plain_text == expected_plain_text


@pytest.mark.parametrize("mutation", ["missing", "bad_hash"])
def test_config_rejects_missing_or_hash_mismatched_release_map(
    tmp_path: Path,
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(control_ui.EXPORT_OPENALEX_API_KEY, TEST_OPENALEX_API_KEY)
    config_value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    map_metadata = config_value["files_config"][api.MAP_SUBSET_0_TO_BATCH_KEY]
    if mutation == "missing":
        del config_value["files_config"][api.MAP_SUBSET_0_TO_BATCH_KEY]
    else:
        map_metadata["sha256"] = "0" * 64
    config_path = tmp_path / "config_ai_augment.json"
    config_path.write_text(json.dumps(config_value), encoding="utf-8")

    with pytest.raises(api.PushConfigurationError):
        control_ui.RuntimeConfiguration(config_path=config_path)


def test_run_journal_replays_process_and_acceptance_state(tmp_path: Path) -> None:
    journal_path = tmp_path / "runs.jsonl"
    journal = control_ui.RunJournal(path=journal_path)
    run_id = uuid4()
    source_key = control_ui.SourceKey('{"researcher": 1}')
    attempt_id = "20260807T000000_000000Z_attempt"

    for event in (
        control_ui.RunEvent(
            run_id=run_id,
            source_key=source_key,
            at=SESSION_TIMESTAMP,
            kind=control_ui.RunEventKind.QUEUED,
        ),
        control_ui.RunEvent(
            run_id=run_id,
            source_key=source_key,
            at=SESSION_TIMESTAMP,
            kind=control_ui.RunEventKind.STARTED,
            remote_pid=321,
        ),
        control_ui.RunEvent(
            run_id=run_id,
            source_key=source_key,
            at=SESSION_TIMESTAMP,
            kind=control_ui.RunEventKind.SESSION_DISCOVERED,
            session_id=SESSION_ID,
        ),
        control_ui.RunEvent(
            run_id=run_id,
            source_key=source_key,
            at=SESSION_TIMESTAMP,
            kind=control_ui.RunEventKind.PUSH_ACCEPTED,
            accepted_attempt_id=attempt_id,
        ),
        control_ui.RunEvent(
            run_id=run_id,
            source_key=source_key,
            at=SESSION_TIMESTAMP,
            kind=control_ui.RunEventKind.CODEX_EXITED,
            codex_exit_code=0,
        ),
        control_ui.RunEvent(
            run_id=run_id,
            source_key=source_key,
            at=SESSION_TIMESTAMP,
            kind=control_ui.RunEventKind.COMPLETE,
        ),
    ):
        journal.append(event)

    loaded = journal.load_runs()[run_id]

    assert loaded.status is control_ui.RunStatus.COMPLETE
    assert loaded.remote_pid == 321
    assert loaded.session_id == SESSION_ID
    assert loaded.accepted_attempt_id == attempt_id
    assert loaded.codex_exit_code == 0
    assert len(journal.load_events()) == 6


@pytest.mark.anyio
async def test_control_plane_exposes_and_revokes_one_exact_sanction() -> None:
    plane = control_ui.ControlPlane()
    run = control_ui.SanctionedRun(
        run_id=uuid4(),
        source_key=control_ui.SourceKey('{"researcher": 1}'),
        session_id=SESSION_ID,
        rollout_jsonl=ROLLOUT_PATH,
        sanctioned_at=SESSION_TIMESTAMP,
    )

    await plane.sanction(run)
    snapshot = await plane.snapshot()

    assert snapshot.sanctioned_run is not None
    assert snapshot.sanctioned_run.run_id == run.run_id
    assert snapshot.sanctioned_run.source_key == run.source_key
    assert snapshot.sanctioned_run.session_id == run.session_id
    assert snapshot.sanctioned_run.rollout_jsonl == str(run.rollout_jsonl)
    with pytest.raises(RuntimeError, match="already sanctioned"):
        await plane.sanction(run)
    await plane.revoke(run_id=uuid4())
    assert await plane.current() == run
    await plane.revoke(run_id=run.run_id)
    assert (await plane.snapshot()).sanctioned_run is None


class FakeSourceRepository:
    def __init__(self, researchers: tuple[control_ui.Researcher, ...]) -> None:
        self.researchers = researchers

    def load_researchers(self) -> tuple[control_ui.Researcher, ...]:
        return self.researchers

    def load_ground_truth_by_source_key(
        self,
    ) -> dict[control_ui.SourceKey, control_ui.GroundTruthRecord]:
        return {}


class FakeDetourRepository:
    def __init__(self) -> None:
        self.archived_attempts: dict[
            control_ui.SourceKey,
            tuple[control_ui.AcceptedAttempt, ...],
        ] = {}
        self.archived_manifests: dict[
            control_ui.SourceKey,
            tuple[api.ArchivedAttemptManifest, ...],
        ] = {}
        self.accepted_attempts: dict[
            control_ui.SourceKey,
            tuple[control_ui.AcceptedAttempt, ...],
        ] = {}
        self.attempt_manifests: dict[
            control_ui.SourceKey,
            tuple[api.ArchivedAttemptManifest, ...],
        ] = {}
        self.control_run_events: tuple[control_ui.RunEvent, ...] = ()
        self.reconcile_calls = 0

    def reconcile_archived_attempts(self) -> api.ArchivedAttemptRecovery:
        self.reconcile_calls += 1
        self.accepted_attempts = dict(self.archived_attempts)
        self.attempt_manifests = dict(self.archived_manifests)
        restored_attempt_ids = tuple(
            manifest.attempt_id
            for manifests in self.archived_manifests.values()
            for manifest in manifests
        )
        restored_accepted_attempt_ids = tuple(
            manifest.attempt_id
            for manifests in self.archived_manifests.values()
            for manifest in manifests
            if manifest.result == api.ATTEMPT_RESULT_ACCEPTED
        )
        return api.ArchivedAttemptRecovery(
            discovered=len(restored_attempt_ids),
            invalid=0,
            restored_attempt_ids=restored_attempt_ids,
            restored_accepted_attempt_ids=restored_accepted_attempt_ids,
            skipped_attempt_ids=(),
        )

    def load_attempt_manifests(
        self,
    ) -> dict[control_ui.SourceKey, tuple[api.ArchivedAttemptManifest, ...]]:
        return dict(self.attempt_manifests)

    def load_accepted_attempts(
        self,
    ) -> dict[control_ui.SourceKey, tuple[control_ui.AcceptedAttempt, ...]]:
        return dict(self.accepted_attempts)

    def load_accepted_attempts_for_source_key(
        self,
        source_key: control_ui.SourceKey,
    ) -> tuple[control_ui.AcceptedAttempt, ...]:
        return self.accepted_attempts.get(source_key, ())

    def persist_control_run_events(
        self,
        events: tuple[control_ui.RunEvent, ...],
    ) -> int:
        if self.control_run_events != events[: len(self.control_run_events)]:
            raise RuntimeError(control_ui.Locale.CONTROL_RUN_EVENTS_PERSIST_FAILED)
        persisted = len(events) - len(self.control_run_events)
        self.control_run_events = tuple(events)
        return persisted

    def load_control_run_events(self) -> tuple[control_ui.RunEvent, ...]:
        return self.control_run_events


class CountingCardRenderer:
    def __init__(self) -> None:
        self.calls: list[control_ui.SourceKey] = []

    def render(
        self,
        source_key: control_ui.SourceKey,
    ) -> control_ui.ResearcherCardView:
        self.calls.append(source_key)
        return control_ui.ResearcherCardView(
            source_key=source_key,
            draw_number="1",
            first_name="First",
            last_name="Last",
            markdown=f"render {len(self.calls)}",
        )


class FakeButton:
    def __init__(self) -> None:
        self.text = ""
        self.disabled = False

    def set_text(self, value: str) -> None:
        self.text = value

    def disable(self) -> None:
        self.disabled = True

    def enable(self) -> None:
        self.disabled = False


class FakeProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminate_calls = 0
        self.kill_calls = 0

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.returncode = TERMINATE_RETURN_CODE

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = KILL_RETURN_CODE

    async def wait(self) -> int:
        return 0 if self.returncode is None else self.returncode


class StartingCancelableCodex:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.canceled = asyncio.Event()
        self.handle: control_ui.CodexProcessHandle | None = None

    async def start(
        self,
        *,
        run_id: UUID,
        on_handle: (Callable[[control_ui.CodexProcessHandle], Awaitable[None]] | None) = None,
    ) -> control_ui.CodexStartResult:
        self.handle = control_ui.CodexProcessHandle(
            run_id=run_id,
            process=cast(asyncio.subprocess.Process, FakeProcess()),
        )
        if on_handle is not None:
            await on_handle(self.handle)
        self.started.set()
        await self.canceled.wait()
        raise RuntimeError("Codex exited before rollout discovery")

    async def is_busy(self) -> bool:
        return False

    async def cancel(self, handle: control_ui.CodexProcessHandle) -> None:
        assert handle is self.handle
        handle.process.terminate()
        await handle.process.wait()
        self.canceled.set()

    async def wait(self, _handle: control_ui.CodexProcessHandle) -> int:
        raise AssertionError("a cancelled startup must not reach Codex wait")


class FakeBackend:
    def __init__(self) -> None:
        self.status = control_ui.BackendStatus.STOPPED
        self.pull_probes = 0
        self.persisted_events: tuple[control_ui.RunEvent, ...] = ()

    async def start(self) -> None:
        self.status = control_ui.BackendStatus.RUNNING

    async def stop(self) -> None:
        self.status = control_ui.BackendStatus.STOPPED

    async def probe_pull(self) -> None:
        self.pull_probes += 1

    def persist_run_events(self, events: tuple[control_ui.RunEvent, ...]) -> int:
        if self.persisted_events != events[: len(self.persisted_events)]:
            raise RuntimeError(control_ui.Locale.CONTROL_RUN_EVENTS_PERSIST_FAILED)
        persisted = len(events) - len(self.persisted_events)
        self.persisted_events = tuple(events)
        return persisted


class FailingPullBackend(FakeBackend):
    async def probe_pull(self) -> None:
        await super().probe_pull()
        raise RuntimeError(control_ui.Locale.BACKEND_PULL_NOT_READY)


class SerialFakeCodex:
    def __init__(self) -> None:
        self.started: asyncio.Queue[UUID] = asyncio.Queue()
        self.release: asyncio.Queue[UUID] = asyncio.Queue()
        self.external_busy = False
        self.canceled: list[UUID] = []

    async def is_busy(self) -> bool:
        return self.external_busy

    async def start(
        self,
        *,
        run_id: UUID,
        on_handle: (Callable[[control_ui.CodexProcessHandle], Awaitable[None]] | None) = None,
    ) -> control_ui.CodexStartResult:
        await self.started.put(run_id)
        handle = control_ui.CodexProcessHandle(
            run_id=run_id,
            process=cast(
                asyncio.subprocess.Process,
                SimpleNamespace(returncode=None),
            ),
            remote_pid=control_ui.RemotePid(123),
        )
        if on_handle is not None:
            await on_handle(handle)
        return control_ui.CodexStartResult(
            handle=handle,
            session_id=control_ui.SessionId(str(run_id)),
            session_timestamp=SESSION_TIMESTAMP,
            rollout_jsonl=ROLLOUT_PATH.with_name(f"rollout-{run_id}.jsonl"),
        )

    async def wait(self, handle: control_ui.CodexProcessHandle) -> int:
        assert await self.release.get() == handle.run_id
        return 0

    async def cancel(self, handle: control_ui.CodexProcessHandle) -> None:
        self.canceled.append(handle.run_id)

    async def terminate_abandoned_run(self, _run_id: UUID) -> None:
        return None


def make_test_controller(
    *,
    configuration: object,
    source_repository: object,
    detour_repository: object,
    journal: control_ui.RunJournal,
    card_renderer: object,
    backend: object,
    codex: object,
    control_plane: control_ui.ControlPlane,
    reconciler: control_ui.AttemptReconciler,
    projector: control_ui.VariableProjector,
) -> control_ui.ControlCentreController:
    return control_ui.ControlCentreController(
        configuration=cast(control_ui.RuntimeConfiguration, configuration),
        source_repository=cast(control_ui.SourceRepository, source_repository),
        detour_repository=cast(control_ui.DetourRepository, detour_repository),
        journal=journal,
        card_renderer=cast(control_ui.ResearcherCardRenderer, card_renderer),
        backend=cast(control_ui.BackendSupervisor, backend),
        codex=cast(control_ui.CodexRunner, codex),
        control_plane=control_plane,
        reconciler=reconciler,
        projector=projector,
    )


@pytest.mark.anyio
async def test_researchers_without_runs_are_shown_as_ready_placeholders(
    tmp_path: Path,
) -> None:
    researchers = (researcher(1), researcher(2))
    controller = make_test_controller(
        configuration=SimpleNamespace(),
        source_repository=FakeSourceRepository(researchers),
        detour_repository=FakeDetourRepository(),
        journal=control_ui.RunJournal(path=tmp_path / "runs.jsonl"),
        card_renderer=SimpleNamespace(),
        backend=FakeBackend(),
        codex=SerialFakeCodex(),
        control_plane=control_ui.ControlPlane(),
        reconciler=control_ui.AttemptReconciler(),
        projector=control_ui.VariableProjector(),
    )
    await controller.start()
    try:
        snapshot = await controller.snapshot(
            selection=control_ui.UiSelection(
                variable_key=control_ui.VARIABLE_SPECS[0].key,
            ),
        )
        page = control_ui.ControlCentrePage(controller=controller)
        grid_rows = page.grid_rows(snapshot=snapshot)
        grid_options = page.grid_options(
            snapshot=snapshot,
            variable=control_ui.VARIABLE_SPECS[0],
        )
        grid_updates: list[None] = []
        page._handles.grid = SimpleNamespace(
            options={"theme": "quartz"},
            update=lambda: grid_updates.append(None),
        )
        await page.refresh_grid(snapshot=snapshot)
        await page.refresh_grid(snapshot=snapshot)
    finally:
        await controller.shutdown()

    assert [row.source_key for row in snapshot.rows] == [item.source_key for item in researchers]
    assert all(not row.attempts for row in snapshot.rows)
    assert [row["status"] for row in grid_rows] == [
        control_ui.RunStatus.READY.value,
        control_ui.RunStatus.READY.value,
    ]
    assert [row["action"] for row in grid_rows] == [
        control_ui.RunAction.QUEUE.value,
        control_ui.RunAction.QUEUE.value,
    ]
    assert all(row["run_id"] is None for row in grid_rows)
    assert all(row["attempt_id"] is None for row in grid_rows)
    assert all(row["row_id"] == row["source_key"] for row in grid_rows)
    assert grid_options["rowData"] == grid_rows
    assert grid_options[":getRowId"] == control_ui.AgGrid.GET_ROW_ID_TEMPLATE.format(
        row_id_field=control_ui.GRID_ROW_ID_FIELD
    )
    assert "getRowId" not in grid_options
    assert page._handles.grid.options["theme"] == "quartz"
    assert grid_updates == [None]


@pytest.mark.anyio
async def test_external_codex_busy_queues_then_reconciles_unjournaled_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external_researcher = researcher(1)
    queued_researcher = researcher(2)
    detour_repository = FakeDetourRepository()
    codex = SerialFakeCodex()
    codex.external_busy = True
    controller = make_test_controller(
        configuration=SimpleNamespace(),
        source_repository=FakeSourceRepository((external_researcher, queued_researcher)),
        detour_repository=detour_repository,
        journal=control_ui.RunJournal(path=tmp_path / "runs.jsonl"),
        card_renderer=SimpleNamespace(),
        backend=FakeBackend(),
        codex=codex,
        control_plane=control_ui.ControlPlane(),
        reconciler=control_ui.AttemptReconciler(),
        projector=control_ui.VariableProjector(),
    )
    external_attempt = control_ui.AcceptedAttempt(
        source_key=external_researcher.source_key,
        attempt_id=control_ui.AttemptId(LATER_ARCHIVED_ATTEMPT_ID),
        session_metadata=control_ui.SessionMetadata(
            originator=TEST_SESSION_METADATA_VALUE,
            source=TEST_SESSION_METADATA_VALUE,
            cli_version=TEST_SESSION_METADATA_VALUE,
            model_provider=TEST_SESSION_METADATA_VALUE,
            model=TEST_SESSION_METADATA_VALUE,
            reasoning_effort=TEST_SESSION_METADATA_VALUE,
            session_id=SESSION_ID,
            timestamp=SESSION_TIMESTAMP,
        ),
        values={
            control_ui.VARIABLE_SPECS[0].ai_column: TEST_SESSION_METADATA_VALUE,
        },
        footnotes=None,
        footnote_arguments=None,
    )
    monkeypatch.setattr(
        control_ui,
        "UI_REFRESH_SECONDS",
        TEST_BUSY_POLL_SECONDS,
    )

    await controller.start()
    try:
        busy_snapshot = await controller.snapshot(
            selection=control_ui.UiSelection(
                variable_key=control_ui.VARIABLE_SPECS[0].key,
            ),
        )
        queued_run_id = await controller.queue(source_key=queued_researcher.source_key)
        await asyncio.sleep(TEST_BUSY_POLL_SECONDS)

        assert controller.codex_busy
        assert [row.latest.action for row in busy_snapshot.rows] == [
            control_ui.RunAction.QUEUE,
            control_ui.RunAction.QUEUE,
        ]
        assert codex.started.empty()

        detour_repository.archived_attempts = {
            external_researcher.source_key: (external_attempt,),
        }
        detour_repository.archived_manifests = {
            external_researcher.source_key: (
                archived_attempt_manifest(
                    researcher_item=external_researcher,
                    attempt_id=LATER_ARCHIVED_ATTEMPT_ID,
                ),
            ),
        }
        codex.external_busy = False
        assert (
            await asyncio.wait_for(
                codex.started.get(),
                timeout=TEST_ASYNC_TIMEOUT_SECONDS,
            )
            == queued_run_id
        )

        imported_snapshot = await controller.snapshot(
            selection=control_ui.UiSelection(
                variable_key=control_ui.VARIABLE_SPECS[0].key,
            ),
        )
        imported_row = imported_snapshot.rows[0]
        assert detour_repository.reconcile_calls == 2
        assert imported_row.latest.attempt_id == external_attempt.attempt_id
        assert imported_row.latest.attempt_status is control_ui.RunStatus.COMPLETE
        assert imported_row.latest.action is control_ui.RunAction.QUEUE
        assert all(
            run.source_key != external_researcher.source_key
            for run in controller._journal.load_runs().values()
        )

        await codex.release.put(queued_run_id)
        await asyncio.wait_for(
            controller._queue.join(),
            timeout=TEST_ASYNC_TIMEOUT_SECONDS,
        )
    finally:
        await controller.shutdown()


@pytest.mark.anyio
async def test_cleared_search_stays_empty_during_timer_refresh(
    tmp_path: Path,
) -> None:
    controller = make_test_controller(
        configuration=SimpleNamespace(),
        source_repository=FakeSourceRepository((researcher(1),)),
        detour_repository=FakeDetourRepository(),
        journal=control_ui.RunJournal(path=tmp_path / "runs.jsonl"),
        card_renderer=SimpleNamespace(),
        backend=FakeBackend(),
        codex=SerialFakeCodex(),
        control_plane=control_ui.ControlPlane(),
        reconciler=control_ui.AttemptReconciler(),
        projector=control_ui.VariableProjector(),
    )
    await controller.start()
    try:
        page = control_ui.ControlCentrePage(controller=controller)
        grid_updates: list[None] = []
        page._handles.grid = SimpleNamespace(
            options={},
            update=lambda: grid_updates.append(None),
        )

        await page.on_search_changed(None)
        await page.refresh()
    finally:
        await controller.shutdown()

    assert page.selection.search_text == ""
    assert grid_updates == [None]


@pytest.mark.anyio
async def test_ineligible_action_is_disabled_and_cards_are_click_cached(
    tmp_path: Path,
) -> None:
    eligible = researcher(1)
    ineligible = researcher(
        2,
        cohort=control_ui.ResearcherCohort.INELIGIBLE,
        ineligibility_category=(control_ui.IneligibilityCategory.STAGING_PARTITION_4_MULTIPLE_SSN),
    )
    card_renderer = CountingCardRenderer()
    controller = make_test_controller(
        configuration=SimpleNamespace(),
        source_repository=FakeSourceRepository((eligible, ineligible)),
        detour_repository=FakeDetourRepository(),
        journal=control_ui.RunJournal(path=tmp_path / "runs.jsonl"),
        card_renderer=card_renderer,
        backend=FakeBackend(),
        codex=SerialFakeCodex(),
        control_plane=control_ui.ControlPlane(),
        reconciler=control_ui.AttemptReconciler(),
        projector=control_ui.VariableProjector(),
    )
    await controller.start()
    try:
        selection = control_ui.UiSelection(
            variable_key=control_ui.VARIABLE_SPECS[0].key,
            selected_source_key=eligible.source_key,
        )
        snapshot = await controller.snapshot(selection=selection)
        page = control_ui.ControlCentrePage(controller=controller)
        rows = page.grid_rows(snapshot=snapshot)
        button = FakeButton()
        page._handles.execute_button = button

        assert card_renderer.calls == []
        assert snapshot.counts.total == 2
        assert snapshot.counts.no_ground_truth == 1
        assert snapshot.counts.ineligible == 1
        assert snapshot.counts.ready == 1
        assert [row.latest.action for row in snapshot.rows] == [
            control_ui.RunAction.QUEUE,
            control_ui.RunAction.DISABLED,
        ]
        assert (
            page.grid_column_definitions(variable=control_ui.VARIABLE_SPECS[0])[0]["field"]
            == control_ui.GRID_RND_FIELD
        )

        page.selection.selected_source_key = ineligible.source_key
        page.sync_selected_action(rows)
        assert button.text == control_ui.ACTION_LABEL_BY_VALUE[control_ui.RunAction.DISABLED.value]
        assert button.disabled
        with pytest.raises(ValueError, match="ineligible"):
            await controller.queue(source_key=ineligible.source_key)

        page.selection.selected_source_key = eligible.source_key
        page.sync_selected_action(rows)
        assert button.text == control_ui.ACTION_LABEL_BY_VALUE[control_ui.RunAction.QUEUE.value]
        assert not button.disabled
        await page.refresh_card()
        await page.refresh_card()
        assert card_renderer.calls == [eligible.source_key]
    finally:
        await controller.shutdown()


@pytest.mark.anyio
async def test_controller_runs_queue_serially_and_reruns_get_new_ids(
    tmp_path: Path,
) -> None:
    researchers = (researcher(1), researcher(2))
    backend = FakeBackend()
    codex = SerialFakeCodex()
    controller = make_test_controller(
        configuration=SimpleNamespace(),
        source_repository=FakeSourceRepository(researchers),
        detour_repository=FakeDetourRepository(),
        journal=control_ui.RunJournal(path=tmp_path / "runs.jsonl"),
        card_renderer=SimpleNamespace(),
        backend=backend,
        codex=codex,
        control_plane=control_ui.ControlPlane(),
        reconciler=control_ui.AttemptReconciler(),
        projector=control_ui.VariableProjector(),
    )
    await controller.start()
    try:
        first_id = await controller.queue(source_key=researchers[0].source_key)
        second_id = await controller.queue(source_key=researchers[1].source_key)
        assert first_id != second_id
        assert await asyncio.wait_for(codex.started.get(), timeout=1) == first_id
        assert codex.started.empty()

        await codex.release.put(first_id)
        assert await asyncio.wait_for(codex.started.get(), timeout=1) == second_id
        await codex.release.put(second_id)
        await asyncio.wait_for(controller._queue.join(), timeout=1)

        rerun_id = await controller.rerun(source_key=researchers[0].source_key)
        assert rerun_id not in {first_id, second_id}
        assert await asyncio.wait_for(codex.started.get(), timeout=1) == rerun_id
        await codex.release.put(rerun_id)
        await asyncio.wait_for(controller._queue.join(), timeout=1)
    finally:
        await controller.shutdown()

    runs = controller._journal.load_runs()
    assert [runs[run_id].status for run_id in (first_id, second_id, rerun_id)] == [
        control_ui.RunStatus.FAILED,
        control_ui.RunStatus.FAILED,
        control_ui.RunStatus.FAILED,
    ]


@pytest.mark.anyio
async def test_failed_sanctioned_pull_is_canceled_and_rebuilt_as_terminal_history(
    tmp_path: Path,
) -> None:
    item = researcher(1)
    repository = FakeDetourRepository()
    journal = control_ui.RunJournal(path=tmp_path / "runs.jsonl")
    backend = FailingPullBackend()
    codex = SerialFakeCodex()
    controller = make_test_controller(
        configuration=SimpleNamespace(),
        source_repository=FakeSourceRepository((item,)),
        detour_repository=repository,
        journal=journal,
        card_renderer=SimpleNamespace(),
        backend=backend,
        codex=codex,
        control_plane=control_ui.ControlPlane(),
        reconciler=control_ui.AttemptReconciler(),
        projector=control_ui.VariableProjector(),
    )
    await controller.start()
    run_id = await controller.queue(source_key=item.source_key)
    await asyncio.wait_for(controller._queue.join(), timeout=TEST_ASYNC_TIMEOUT_SECONDS)
    await controller.shutdown()

    assert backend.pull_probes == 1
    assert codex.canceled == [run_id]
    assert journal.load_runs()[run_id].status is control_ui.RunStatus.FAILED

    restarted = make_test_controller(
        configuration=SimpleNamespace(),
        source_repository=FakeSourceRepository((item,)),
        detour_repository=repository,
        journal=journal,
        card_renderer=SimpleNamespace(),
        backend=FakeBackend(),
        codex=SerialFakeCodex(),
        control_plane=control_ui.ControlPlane(),
        reconciler=control_ui.AttemptReconciler(),
        projector=control_ui.VariableProjector(),
    )
    await restarted.start()
    try:
        snapshot = await restarted.snapshot(
            selection=control_ui.UiSelection(
                variable_key=control_ui.VARIABLE_SPECS[0].key,
            )
        )
    finally:
        await restarted.shutdown()

    assert repository.control_run_events == journal.load_events()
    assert snapshot.rows[0].attempts[-1].run_id == run_id
    assert snapshot.rows[0].attempts[-1].attempt_status is control_ui.RunStatus.FAILED


@pytest.mark.anyio
async def test_shutdown_during_codex_startup_terminates_and_persists_the_run(
    tmp_path: Path,
) -> None:
    item = researcher(1)
    codex = StartingCancelableCodex()
    journal = control_ui.RunJournal(path=tmp_path / "runs.jsonl")
    controller = make_test_controller(
        configuration=SimpleNamespace(),
        source_repository=FakeSourceRepository((item,)),
        detour_repository=FakeDetourRepository(),
        journal=journal,
        card_renderer=SimpleNamespace(),
        backend=FakeBackend(),
        codex=codex,
        control_plane=control_ui.ControlPlane(),
        reconciler=control_ui.AttemptReconciler(),
        projector=control_ui.VariableProjector(),
    )
    await controller.start()
    run_id = await controller.queue(source_key=item.source_key)
    await asyncio.wait_for(codex.started.wait(), timeout=TEST_ASYNC_TIMEOUT_SECONDS)

    await controller.shutdown()

    assert codex.canceled.is_set()
    assert codex.handle is not None
    assert codex.handle.process.returncode == TERMINATE_RETURN_CODE
    assert journal.load_runs()[run_id].status is control_ui.RunStatus.FAILED


@pytest.mark.anyio
async def test_cancel_during_codex_startup_stops_the_visible_process(
    tmp_path: Path,
) -> None:
    item = researcher(1)
    codex = StartingCancelableCodex()
    controller = make_test_controller(
        configuration=SimpleNamespace(),
        source_repository=FakeSourceRepository((item,)),
        detour_repository=FakeDetourRepository(),
        journal=control_ui.RunJournal(path=tmp_path / "runs.jsonl"),
        card_renderer=SimpleNamespace(),
        backend=FakeBackend(),
        codex=codex,
        control_plane=control_ui.ControlPlane(),
        reconciler=control_ui.AttemptReconciler(),
        projector=control_ui.VariableProjector(),
    )
    await controller.start()
    try:
        run_id = await controller.queue(source_key=item.source_key)
        await asyncio.wait_for(codex.started.wait(), timeout=1)

        await controller.cancel(run_id=run_id)
        await asyncio.wait_for(controller._queue.join(), timeout=1)
    finally:
        await controller.shutdown()

    assert codex.handle is not None
    assert codex.handle.process.returncode == TERMINATE_RETURN_CODE
    assert codex.canceled.is_set()
    assert controller._journal.load_runs()[run_id].status is control_ui.RunStatus.CANCELED


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        (control_ui.CODEX_REMOTE_BUSY_MARKER.encode(), True),
        (b"", False),
    ),
)
@pytest.mark.anyio
async def test_codex_busy_uses_the_guest_process_table(
    output: bytes,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = control_ui.CodexRunner(
        timezone=CONTROL_TIMEZONE,
        openalex_api_key=TEST_OPENALEX_API_KEY,
    )
    commands: list[str] = []

    async def remote_command(
        command: str,
        *,
        input_bytes: bytes | None = None,
        check: bool = True,
    ) -> bytes:
        assert input_bytes is None
        assert check
        commands.append(command)
        return output

    monkeypatch.setattr(runner, "_remote_command", remote_command)

    assert await runner.is_busy() is expected
    assert commands == [control_ui.CODEX_REMOTE_BUSY_COMMAND]


@pytest.mark.anyio
async def test_codex_cancel_verifies_remote_and_local_process_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = control_ui.CodexRunner(
        timezone=CONTROL_TIMEZONE,
        openalex_api_key=TEST_OPENALEX_API_KEY,
    )
    process = FakeProcess()
    handle = control_ui.CodexProcessHandle(
        run_id=uuid4(),
        process=cast(asyncio.subprocess.Process, process),
        remote_pid=REMOTE_TEST_PID,
    )
    remote_alive = True
    commands: list[str] = []

    async def remote_command(
        command: str,
        *,
        input_bytes: bytes | None = None,
        check: bool = True,
    ) -> bytes:
        nonlocal remote_alive
        assert input_bytes is None
        assert not check
        commands.append(command)
        if command == control_ui.CODEX_REMOTE_SIGNAL_COMMAND_TEMPLATE.format(
            signal=control_ui.CODEX_REMOTE_KILL_SIGNAL,
            remote_pid=int(REMOTE_TEST_PID),
        ):
            remote_alive = False
        if command == control_ui.CODEX_REMOTE_PROCESS_ALIVE_COMMAND_TEMPLATE.format(
            remote_pid=int(REMOTE_TEST_PID),
            alive_marker=control_ui.CODEX_REMOTE_PROCESS_ALIVE_MARKER,
        ):
            return control_ui.CODEX_REMOTE_PROCESS_ALIVE_MARKER.encode() if remote_alive else b""
        return b""

    monkeypatch.setattr(control_ui, "CODEX_CANCEL_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(runner, "_remote_command", remote_command)

    await runner.cancel(handle)

    assert not remote_alive
    assert process.returncode == KILL_RETURN_CODE
    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert commands == [
        control_ui.CODEX_REMOTE_SIGNAL_COMMAND_TEMPLATE.format(
            signal=control_ui.CODEX_REMOTE_TERMINATE_SIGNAL,
            remote_pid=int(REMOTE_TEST_PID),
        ),
        control_ui.CODEX_REMOTE_PROCESS_ALIVE_COMMAND_TEMPLATE.format(
            remote_pid=int(REMOTE_TEST_PID),
            alive_marker=control_ui.CODEX_REMOTE_PROCESS_ALIVE_MARKER,
        ),
        control_ui.CODEX_REMOTE_SIGNAL_COMMAND_TEMPLATE.format(
            signal=control_ui.CODEX_REMOTE_KILL_SIGNAL,
            remote_pid=int(REMOTE_TEST_PID),
        ),
        control_ui.CODEX_REMOTE_PROCESS_ALIVE_COMMAND_TEMPLATE.format(
            remote_pid=int(REMOTE_TEST_PID),
            alive_marker=control_ui.CODEX_REMOTE_PROCESS_ALIVE_MARKER,
        ),
    ]


def test_codex_ssh_command_has_only_the_approved_reverse_forward() -> None:
    runner = control_ui.CodexRunner(
        timezone=CONTROL_TIMEZONE,
        openalex_api_key=TEST_OPENALEX_API_KEY,
    )

    command = runner.ssh_base_command()

    assert command.count("-R") == 1
    assert command[command.index("-R") + 1] == control_ui.CODEX_REMOTE_FORWARD
    assert control_ui.CODEX_EXEC_COMMAND[0] == str(control_ui.CODEX_CLI_BIN_PATH)
    assert "127.0.0.1:8611" not in command
    assert "ExitOnForwardFailure=yes" in command
    assert "ClearAllForwardings=no" in command
    assert "ClearAllForwardings=yes" not in command


@pytest.mark.anyio
async def test_codex_start_uses_the_same_full_workbook_bytes_in_file_and_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = tmp_path / "workbook.md"
    workbook_bytes = "First learning.\nUnicode: ’\n".encode()
    workbook_path.write_bytes(workbook_bytes)
    runner = control_ui.CodexRunner(
        timezone=CONTROL_TIMEZONE,
        openalex_api_key=TEST_OPENALEX_API_KEY,
    )
    remote_writes: list[tuple[PurePosixPath, bytes]] = []
    launched_commands: list[tuple[str, ...]] = []
    launched_new_sessions: list[bool] = []

    async def write_remote(path: PurePosixPath, content: bytes) -> None:
        remote_writes.append((path, content))

    async def remote_command(
        _command: str,
        *,
        input_bytes: bytes | None = None,
        check: bool = True,
    ) -> bytes:
        assert input_bytes is None
        assert check
        return b""

    async def create_process(
        *command: str,
        start_new_session: bool,
    ) -> SimpleNamespace:
        launched_commands.append(command)
        launched_new_sessions.append(start_new_session)
        return SimpleNamespace(returncode=None)

    async def discover_session(
        _handle: control_ui.CodexProcessHandle,
    ) -> tuple[control_ui.SessionId, datetime]:
        return SESSION_ID, SESSION_TIMESTAMP

    async def discover_rollout_path(
        *,
        session_id: control_ui.SessionId,
        session_timestamp: datetime,
    ) -> PurePosixPath:
        assert session_id == SESSION_ID
        assert session_timestamp == SESSION_TIMESTAMP
        return ROLLOUT_PATH

    monkeypatch.setattr(control_ui, "HOST_WORKBOOK_PATH", workbook_path)
    monkeypatch.setattr(runner, "_write_remote_file", write_remote)
    monkeypatch.setattr(runner, "_remote_command", remote_command)
    monkeypatch.setattr(runner, "discover_session", discover_session)
    monkeypatch.setattr(runner, "discover_rollout_path", discover_rollout_path)
    monkeypatch.setattr(control_ui.asyncio, "create_subprocess_exec", create_process)

    result = await runner.start(run_id=uuid4())

    prompt_bytes = control_ui.CODEX_PROMPT_TEMPLATE.format(
        openapi_url=control_ui.BACKEND_OPENAPI_URL,
        workbook=workbook_bytes.decode(),
    ).encode()
    assert result.session_id == SESSION_ID
    assert remote_writes == [
        (
            control_ui.CODEX_ENV_PATH,
            control_ui.CODEX_ENV_EXPORT_TEMPLATE.format(
                name=control_ui.EXPORT_OPENALEX_API_KEY,
                value=TEST_OPENALEX_API_KEY,
            ).encode(),
        ),
        (control_ui.CODEX_WORKBOOK_PATH, workbook_bytes),
        (control_ui.CODEX_PROMPT_PATH, prompt_bytes),
    ]
    assert len(launched_commands) == 1
    assert launched_new_sessions == [True]
    remote_launch = launched_commands[0][-1]
    assert " ".join(control_ui.CODEX_EXEC_COMMAND) in remote_launch
    assert str(control_ui.CODEX_ENV_PATH) in remote_launch
    assert TEST_OPENALEX_API_KEY not in remote_launch
    assert str(control_ui.CODEX_PROMPT_PATH) in remote_launch


def test_backend_environment_includes_openalex_api_key() -> None:
    backend = control_ui.BackendSupervisor(
        repository_root=REPOSITORY_ROOT,
        config_path=CONFIG_PATH,
        control_url=control_ui.CONTROL_CENTRE_BASE_URL,
        openalex_api_key=TEST_OPENALEX_API_KEY,
        appendwatch_report=CONFIG_PATH,
        control_run_events_token=TEST_CONTROL_RUN_EVENTS_TOKEN,
    )

    assert backend.environment()[control_ui.EXPORT_OPENALEX_API_KEY] == (TEST_OPENALEX_API_KEY)
