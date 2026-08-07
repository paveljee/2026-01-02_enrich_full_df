from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from src.detours.detour_ai_augment.src.backend import api
from src.detours.detour_ai_augment.src.control_centre import ui as control_ui

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPOSITORY_ROOT / "config_ai_augment.json"
SESSION_TIMESTAMP = datetime(2026, 8, 7, tzinfo=timezone.utc)
SESSION_ID = control_ui.SessionId("019fb000-0000-7000-8000-000000000001")
ROLLOUT_PATH = PurePosixPath(
    "/home/ai/.codex/sessions/2026/08/07/"
    "rollout-2026-08-07T00-00-00-019fb000-0000-7000-8000-000000000001.jsonl"
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def researcher(number: int) -> control_ui.Researcher:
    return control_ui.Researcher(
        source_key=control_ui.SourceKey(f'{{"researcher": {number}}}'),
        draw_numbers=(str(number),),
        first_name=f"First {number}",
        last_name=f"Last {number}",
        cohort=control_ui.ResearcherCohort.NO_GROUND_TRUTH,
    )


def test_real_config_derives_exact_innerdict_owned_cohorts() -> None:
    configuration = control_ui.RuntimeConfiguration(config_path=CONFIG_PATH)
    repository = control_ui.SourceRepository(configuration=configuration)

    researchers = repository.load_eligible_researchers()

    assert Counter(item.cohort for item in researchers) == {
        control_ui.ResearcherCohort.GROUND_TRUTH: api.EXPECTED_GROUND_TRUTH_RESEARCHERS,
        control_ui.ResearcherCohort.NO_GROUND_TRUTH: (
            api.EXPECTED_NO_GROUND_TRUTH_RESEARCHERS
        ),
    }
    assert len(researchers) == api.EXPECTED_ELIGIBLE_RESEARCHERS
    assert api.EXCLUDED_SOURCE_KEY not in {item.source_key for item in researchers}
    assert sum(len(item.draw_numbers) > 1 for item in researchers) == 4
    assert all(item.draw_numbers for item in researchers)


def test_config_registers_verified_release_map_without_writing_source_db() -> None:
    source_db_path = control_ui.PipelineConfig.from_json(CONFIG_PATH).db_file
    source_hash_before = hashlib.sha256(source_db_path.read_bytes()).hexdigest()

    configuration = control_ui.RuntimeConfiguration(config_path=CONFIG_PATH)

    resource = configuration.backend_runtime.release_map
    assert resource is not None
    assert resource.group.value == "ktp_pipeline_artifact"
    assert resource.fragment_type.value == "csv_row"
    assert api.load_release_batches(resource)["125"] == "subset 7"
    assert hashlib.sha256(source_db_path.read_bytes()).hexdigest() == source_hash_before


@pytest.mark.parametrize("mutation", ["missing", "bad_hash"])
def test_config_rejects_missing_or_hash_mismatched_release_map(
    tmp_path: Path,
    mutation: str,
) -> None:
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

    def load_eligible_researchers(self) -> tuple[control_ui.Researcher, ...]:
        return self.researchers

    def load_ground_truth_by_source_key(
        self,
    ) -> dict[control_ui.SourceKey, control_ui.GroundTruthRecord]:
        return {}


class FakeDetourRepository:
    def load_accepted_attempts(
        self,
    ) -> dict[control_ui.SourceKey, tuple[control_ui.AcceptedAttempt, ...]]:
        return {}

    def load_accepted_attempts_for_source_key(
        self,
        _source_key: control_ui.SourceKey,
    ) -> tuple[control_ui.AcceptedAttempt, ...]:
        return ()


class FakeBackend:
    def __init__(self) -> None:
        self.status = control_ui.BackendStatus.STOPPED

    async def start(self) -> None:
        self.status = control_ui.BackendStatus.RUNNING

    async def stop(self) -> None:
        self.status = control_ui.BackendStatus.STOPPED


class SerialFakeCodex:
    def __init__(self) -> None:
        self.started: asyncio.Queue[UUID] = asyncio.Queue()
        self.release: asyncio.Queue[UUID] = asyncio.Queue()

    async def start(self, *, run_id: UUID) -> control_ui.CodexStartResult:
        await self.started.put(run_id)
        handle = control_ui.CodexProcessHandle(
            run_id=run_id,
            process=SimpleNamespace(returncode=None),
            remote_pid=control_ui.RemotePid(123),
        )
        return control_ui.CodexStartResult(
            handle=handle,
            session_id=control_ui.SessionId(str(run_id)),
            session_timestamp=SESSION_TIMESTAMP,
            rollout_jsonl=ROLLOUT_PATH.with_name(f"rollout-{run_id}.jsonl"),
        )

    async def wait(self, handle: control_ui.CodexProcessHandle) -> int:
        assert await self.release.get() == handle.run_id
        return 0

    async def cancel(self, _handle: control_ui.CodexProcessHandle) -> None:
        return None


@pytest.mark.anyio
async def test_controller_runs_queue_serially_and_reruns_get_new_ids(
    tmp_path: Path,
) -> None:
    researchers = (researcher(1), researcher(2))
    backend = FakeBackend()
    codex = SerialFakeCodex()
    controller = control_ui.ControlCentreController(
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


def test_codex_ssh_command_has_only_the_approved_reverse_forward() -> None:
    runner = control_ui.CodexRunner(timezone=timezone.utc)

    command = runner.ssh_base_command()

    assert command.count("-R") == 1
    assert command[command.index("-R") + 1] == control_ui.CODEX_REMOTE_FORWARD
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
    runner = control_ui.CodexRunner(timezone=timezone.utc)
    remote_writes: list[tuple[PurePosixPath, bytes]] = []
    launched_commands: list[tuple[str, ...]] = []

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

    async def create_process(*command: str) -> SimpleNamespace:
        launched_commands.append(command)
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
        (control_ui.CODEX_WORKBOOK_PATH, workbook_bytes),
        (control_ui.CODEX_PROMPT_PATH, prompt_bytes),
    ]
    assert len(launched_commands) == 1
    remote_launch = launched_commands[0][-1]
    assert " ".join(control_ui.CODEX_EXEC_COMMAND) in remote_launch
    assert str(control_ui.CODEX_PROMPT_PATH) in remote_launch
