from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

import duckdb
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.detours.detour_ai_augment.src.backend import api
from src.detours.detour_ai_augment.src.backend.helpers import codex_parse
from src.helpers.config import PipelineConfig

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPOSITORY_ROOT / "config.repl.json"
AI_AUGMENT_CONFIG_PATH = REPOSITORY_ROOT / "config_ai_augment.json"
SOURCE_DB_PATH = REPOSITORY_ROOT / "data" / "scisci_process.duckdb"
SOURCE_JSONL_PATH = REPOSITORY_ROOT / "tmp" / "sheikh.jsonl"
REFERENCE_DOCX_PATH = REPOSITORY_ROOT / "resources" / "pandoc-custom-reference.docx"
JULY_ROLLOUT_RELATIVE_PATH = PurePosixPath(
    "2026/07/27/rollout-2026-07-27T12-10-36-019fa457-aac5-7652-8669-9d571206e7cb.jsonl"
)
JULY_ROLLOUT_PATH = (
    REPOSITORY_ROOT
    / "src"
    / "detours"
    / "detour_ai_augment"
    / "data"
    / "sample_run"
    / ".codex"
    / "sessions"
    / Path(*JULY_ROLLOUT_RELATIVE_PATH.parts)
)
JULY_ROLLOUT_GUEST_PATH = f"{api.CODEX_SESSIONS_ROOT}/{JULY_ROLLOUT_RELATIVE_PATH}"
JULY_ROLLOUT_FILENAME = JULY_ROLLOUT_RELATIVE_PATH.name
JULY_ROLLOUT_LINE_COUNT = 107
JULY_SESSION_ID = "019fa457-aac5-7652-8669-9d571206e7cb"
JULY_FC_COUNT = 9
JULY_FCO_COUNT = 9
JULY_CALL_COUNT = 9
JULY_REF_COUNT = 155
JULY_THUMBNAIL_REF_IDS = (
    "turn0search3",
    "turn0search17",
    "turn0search18",
    "turn0search20",
    "turn0search24",
)

TEST_ROLLOUT_GUEST_PATH = "/home/ai/.codex/sessions/2026/07/31/rollout-chat.jsonl"
TEST_ROLLOUT_RELATIVE_PATH = PurePosixPath("2026/07/31/rollout-chat.jsonl")
TEST_TIMEZONE = "America/Toronto"
TEST_SESSION_ID = "session-test"
TEST_SESSION_TIMESTAMP = "2026-07-31T16:10:36.000Z"
TEST_ROLLOUT_FILENAME = "rollout-2026-07-31T12-10-36-session-test.jsonl"
TEST_CALL_ID = "call_test"
TEST_FC_ID = "fc_test"
TEST_FCO_ID = "fco_test"
TEST_REF_ID = "turn0search0"
TEST_VIEW_CALL_ID = "call_view"
TEST_VIEW_FC_ID = "fc_view"
TEST_VIEW_FCO_ID = "fco_view"
TEST_VIEW_REF_ID = "turn1view0"
TEST_VIEW_ARGUMENTS = '{"open":[{"ref_id":"turn0search0"}]}'
TEST_NO_URL_REF_ID = "turn0view1"
TEST_EXCERPT = "Professor Example holds the Example Chair."
TEST_URL = "https://example.test/profile"
TEST_SOURCE_KEY = '{"ktp.first_name": "A.", "ktp.last_name": "Sheikh"}'

OFFICERS_URL = (
    "https://find-and-update.company-information.service.gov.uk/company/SC621293/officers"
)
COMPANY_URL = "https://find-and-update.company-information.service.gov.uk/company/SC621293"
COMMONWEALTH_URL = "https://www.commonwealthfund.org/person/aziz-sheikh"
OXFORD_BDI_URL = "https://www.bdi.ox.ac.uk/Team/aziz-sheikh"
NIHR_URL = (
    "https://www.spcr.nihr.ac.uk/news/congratulations-to-the-new-nihr-senior-investigators-2026"
)

CALL_ARGUMENTS_TURN_2 = (
    '{"search_query":[{"q":"\\"Aziz Sheikh\\" \\"born\\" professor Edinburgh"},'
    '{"q":"\\"Aziz Sheikh\\" \\"1968\\" professor"},'
    '{"q":"\\"Aziz Sheikh\\" \\"1967\\" Edinburgh professor"},'
    '{"q":"\\"Aziz Sheikh\\" age professor Oxford"}],"response_length":"long"}'
)
CALL_ARGUMENTS_TURN_4 = (
    '{"search_query":[{"q":"\\"Aziz Sheikh\\" \\"Master\'s in Epidemiology\\""},'
    '{"q":"\\"Aziz Sheikh\\" \\"Masters in Epidemiology\\""},'
    '{"q":"\\"Aziz Sheikh\\" \\"University College London\\" '
    '\\"London School of Hygiene\\" MD"},'
    '{"q":"\\"Aziz Sheikh\\" BSc MBBS MSc MD education"}],'
    '"response_length":"long"}'
)
CALL_ARGUMENTS_TURN_6 = '{"open":[{"ref_id":"turn5search0"}],"response_length":"long"}'
CALL_ARGUMENTS_TURN_7 = '{"click":[{"ref_id":"turn6view0","id":10}],"response_length":"long"}'
DISPLAY_ARGUMENTS_TURN_6 = (
    f'{{"open":[{{"ref_id":"turn5search0","url":"{COMPANY_URL}"}}],'
    '"response_length":"long"}'
)
DISPLAY_ARGUMENTS_TURN_7 = (
    f'{{"click":[{{"ref_id":"turn6view0","url":"{COMPANY_URL}","id":10}}],'
    '"response_length":"long"}'
)
CALL_ARGUMENTS_TURN_8 = (
    '{"search_query":[{"q":"site:nam.edu \\"Aziz Sheikh\\" elected National '
    'Academy of Medicine 2024"},{"q":"site:ed.ac.uk \\"Aziz Sheikh\\" '
    'National Academy of Medicine 2024"},{"q":"site:nihr.ac.uk '
    '\\"Aziz Sheikh\\" Senior Investigator"},{"q":"site:hdr.uk '
    '\\"Aziz Sheikh\\" Strategic Adviser Health Care Policy"}],'
    '"response_length":"long"}'
)


@dataclass(frozen=True)
class ExpectedEvidence:
    column: str
    value: str
    excerpt: str
    url: str
    ref_id: str
    call_id: str
    fc_id: str
    fco_id: str
    fco_timestamp: str
    arguments_json: str
    display_arguments_json: str


EXPECTED_EVIDENCE = (
    ExpectedEvidence(
        api.KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
        "Aziz Sheikh",
        "SHEIKH, Aziz Ul Haque",
        OFFICERS_URL,
        "turn7view0",
        "call_SzOsv4AVuruWWBbM0oy5i4M0",
        "fc_03938c1e0667a7cc016a6783752e2481959e7e365e71c60b20",
        "fco_019fa459-883b-7480-b82c-b775520d1401",
        "2026-07-27T16:12:38.843Z",
        CALL_ARGUMENTS_TURN_7,
        DISPLAY_ARGUMENTS_TURN_7,
    ),
    ExpectedEvidence(
        api.KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
        "Scotland",
        "Country of residence\nL75:      Scotland",
        OFFICERS_URL,
        "turn7view0",
        "call_SzOsv4AVuruWWBbM0oy5i4M0",
        "fc_03938c1e0667a7cc016a6783752e2481959e7e365e71c60b20",
        "fco_019fa459-883b-7480-b82c-b775520d1401",
        "2026-07-27T16:12:38.843Z",
        CALL_ARGUMENTS_TURN_7,
        DISPLAY_ARGUMENTS_TURN_7,
    ),
    ExpectedEvidence(
        api.KTP_AI_AUGMENT_GENDER_COL,
        "Male",
        "Nationality\nL72:      British",
        OFFICERS_URL,
        "turn7view0",
        "call_SzOsv4AVuruWWBbM0oy5i4M0",
        "fc_03938c1e0667a7cc016a6783752e2481959e7e365e71c60b20",
        "fco_019fa459-883b-7480-b82c-b775520d1401",
        "2026-07-27T16:12:38.843Z",
        CALL_ARGUMENTS_TURN_7,
        DISPLAY_ARGUMENTS_TURN_7,
    ),
    ExpectedEvidence(
        api.KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
        "Age derived from a December 1968 birth date",
        "Date of birth\nL66:      December 1968",
        OFFICERS_URL,
        "turn7view0",
        "call_SzOsv4AVuruWWBbM0oy5i4M0",
        "fc_03938c1e0667a7cc016a6783752e2481959e7e365e71c60b20",
        "fco_019fa459-883b-7480-b82c-b775520d1401",
        "2026-07-27T16:12:38.843Z",
        CALL_ARGUMENTS_TURN_7,
        DISPLAY_ARGUMENTS_TURN_7,
    ),
    ExpectedEvidence(
        api.KTP_AI_AUGMENT_EDUCATION_COL,
        "MSc epidemiology and MD",
        (
            "Sheikh holds a master's of science in epidemiology from the London "
            "School of Hygiene & Tropical Medicine, and a M.D. from the University "
            "of London."
        ),
        COMMONWEALTH_URL,
        "turn4search0",
        "call_S7SrLlbSPHIujjScm4LXYt2X",
        "fc_03938c1e0667a7cc016a67836064b081958a409fea02229e26",
        "fco_019fa459-3dda-7ea0-8d5c-2351036f67f5",
        "2026-07-27T16:12:19.802Z",
        CALL_ARGUMENTS_TURN_4,
        CALL_ARGUMENTS_TURN_4,
    ),
    ExpectedEvidence(
        api.KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
        "Oxford Big Data Institute",
        "Aziz Sheikh — Oxford Big Data Institute (https://www.bdi.ox.ac.uk/Team/aziz-sheikh)",
        OXFORD_BDI_URL,
        "turn2search0",
        "call_Tv7D3tbhKCOUBdz2xfruMIIY",
        "fc_03938c1e0667a7cc016a678326af18819587231df3dd08c37d",
        "fco_019fa458-5973-77a1-93a4-0c27355f8eb8",
        "2026-07-27T16:11:21.331Z",
        CALL_ARGUMENTS_TURN_2,
        CALL_ARGUMENTS_TURN_2,
    ),
    ExpectedEvidence(
        api.KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
        "NIHR Senior Investigator",
        (
            "The NIHR has announced its 2026 cohort of Senior Investigators, "
            "recognising outstanding leaders in health and care research."
        ),
        NIHR_URL,
        "turn8search0",
        "call_KLTzFeZeazG7AjjhDp42wUtj",
        "fc_03938c1e0667a7cc016a67837ae26881958bb5e280a116e970",
        "fco_019fa459-b0f8-79e1-88f4-535744154d8e",
        "2026-07-27T16:12:49.272Z",
        CALL_ARGUMENTS_TURN_8,
        CALL_ARGUMENTS_TURN_8,
    ),
    ExpectedEvidence(
        api.KTP_AI_AUGMENT_LINKS_COL,
        COMPANY_URL,
        'Source: open({"ref_id":"turn5search0","lineno":null}); Total lines: 92',
        COMPANY_URL,
        "turn6view0",
        "call_dWCc1wam5TvIfxwvI1o6RPEL",
        "fc_03938c1e0667a7cc016a678370815881958bcee4380dc8ed61",
        "fco_019fa459-750e-7920-b0cf-ef211333113f",
        "2026-07-27T16:12:33.934Z",
        CALL_ARGUMENTS_TURN_6,
        DISPLAY_ARGUMENTS_TURN_6,
    ),
)
EXPECTED_COMMENT = "OpenAlex records may contain identity conflation."

EXPECTED_CALL_LINKS = (
    (
        "call_JrCO9EEdFFwnncEyo0Tky0N3",
        "fc_03938c1e0667a7cc016a67831675848195b35c40d330cd04b2",
        "fco_019fa458-1fef-7a43-9f53-7d987861ad64",
    ),
    (
        "call_C9nCCxE2YU5zrv9kI6ewtswG",
        "fc_03938c1e0667a7cc016a67831c12b08195ae364f3f129f750c",
        "fco_019fa458-3b72-7a83-8874-2b9e174b5aed",
    ),
    (
        "call_Tv7D3tbhKCOUBdz2xfruMIIY",
        "fc_03938c1e0667a7cc016a678326af18819587231df3dd08c37d",
        "fco_019fa458-5973-77a1-93a4-0c27355f8eb8",
    ),
    (
        "call_YxDU7O0lAHezJU2HMRaJAd0O",
        "fc_03938c1e0667a7cc016a678352e1c88195bee04fa6259f5b3c",
        "fco_019fa459-06a6-7a73-9cb5-9e75d35f47c0",
    ),
    (
        "call_S7SrLlbSPHIujjScm4LXYt2X",
        "fc_03938c1e0667a7cc016a67836064b081958a409fea02229e26",
        "fco_019fa459-3dda-7ea0-8d5c-2351036f67f5",
    ),
    (
        "call_3OgJqG5RIvAQxxZZmTZc7puu",
        "fc_03938c1e0667a7cc016a67836ab04081958d8880d3cb1990a0",
        "fco_019fa459-6641-7d53-9347-4c7d663d5003",
    ),
    (
        "call_dWCc1wam5TvIfxwvI1o6RPEL",
        "fc_03938c1e0667a7cc016a678370815881958bcee4380dc8ed61",
        "fco_019fa459-750e-7920-b0cf-ef211333113f",
    ),
    (
        "call_SzOsv4AVuruWWBbM0oy5i4M0",
        "fc_03938c1e0667a7cc016a6783752e2481959e7e365e71c60b20",
        "fco_019fa459-883b-7480-b82c-b775520d1401",
    ),
    (
        "call_KLTzFeZeazG7AjjhDp42wUtj",
        "fc_03938c1e0667a7cc016a67837ae26881958bb5e280a116e970",
        "fco_019fa459-b0f8-79e1-88f4-535744154d8e",
    ),
)

EXPECTED_TABLE_COLUMNS = {
    api.CODEX_FC_TABLE: (
        "id",
        "codex.fc_timestamp",
        "codex.fc_id",
        "codex.fc_name",
        "codex.fc_namespace",
        "codex.fc_arguments",
    ),
    api.CODEX_FCO_TABLE: ("id", "codex.fco_timestamp", "codex.fco_id"),
    api.CODEX_CALLS_TABLE: (
        "id",
        "codex.call_id",
        "codex.fc_id",
        "codex.fco_id",
        "codex.rollout_filename",
    ),
    api.CODEX_TURN_REF_TABLE: (
        "id",
        "codex.ref_id",
        "codex.call_id",
        "codex.ref_domain",
        "codex.ref_snippet",
        "codex.ref_thumbnail_url",
        "codex.ref_title",
        "codex.ref_url",
        "codex.cite_text",
    ),
}
OPTIONAL_REF_METADATA_COLUMNS = (
    api.CODEX_REF_DOMAIN_COL,
    api.CODEX_REF_SNIPPET_COL,
    api.CODEX_REF_THUMBNAIL_URL_COL,
    api.CODEX_REF_TITLE_COL,
)


# File access helpers are intentionally centralized for fixture auditability.
def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_bytes(path: Path, value: bytes) -> None:
    path.write_bytes(value)


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(read_text(path))
    assert isinstance(value, dict)
    return value


def file_signature(path: Path) -> tuple[int, int, str]:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(api.ARCHIVE_HASH_CHUNK_BYTES):
            digest.update(chunk)
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, digest.hexdigest()


def read_zip_text(path: Path) -> str:
    with ZipFile(path) as archive:
        names = archive.namelist()
        assert names
        return "\n".join(archive.read(name).decode("utf-8") for name in names)


def zip_member_names(path: Path) -> tuple[str, ...]:
    with ZipFile(path) as archive:
        return tuple(archive.namelist())


def open_readonly_database(path: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path), read_only=True)


def rollout_record(value: dict[str, object], line_number: int) -> api.RolloutRecord:
    raw_line = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    return api.RolloutRecord(
        line_number=line_number,
        line_sha256=hashlib.sha256(raw_line).hexdigest(),
        value=value,
    )


def minimal_rollout_records(action: str = "search_query") -> tuple[api.RolloutRecord, ...]:
    arguments = {
        "search_query": [{"q": "example"}],
        "open": [{"ref_id": TEST_REF_ID}],
        "click": [{"ref_id": TEST_REF_ID, "id": 1}],
    }[action]
    cite_text = (
        f"Result\n{api.CODEX_CITE_MARKER_PREFIX}{TEST_REF_ID}"
        f"{api.CODEX_CITE_MARKER_SUFFIX}\n{TEST_EXCERPT}"
    )
    values: tuple[dict[str, object], ...] = (
        {
            "timestamp": TEST_SESSION_TIMESTAMP,
            "type": "session_meta",
            "payload": {
                "session_id": TEST_SESSION_ID,
                "timestamp": TEST_SESSION_TIMESTAMP,
                "originator": "codex_vscode",
                "source": "vscode",
                "cli_version": "test",
                "model_provider": "openai",
            },
        },
        {
            "timestamp": TEST_SESSION_TIMESTAMP,
            "type": "turn_context",
            "payload": {"model": "test-model", "effort": "high"},
        },
        {
            "timestamp": "2026-07-31T16:11:00.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "id": TEST_FC_ID,
                "name": "run",
                "namespace": "web",
                "arguments": json.dumps(
                    {action: arguments, "response_length": "long"},
                    separators=(",", ":"),
                ),
                "call_id": TEST_CALL_ID,
            },
        },
        {
            "timestamp": "2026-07-31T16:11:01.000Z",
            "type": "event_msg",
            "payload": {
                "type": "web_search_end",
                "call_id": TEST_CALL_ID,
                "results": [
                    {
                        "type": "text_result",
                        "domain": "example.test",
                        "ref_id": TEST_REF_ID,
                        "snippet": "Example snippet",
                        "thumbnail_url": "https://example.test/thumbnail.png",
                        "title": "Example title",
                        "url": TEST_URL,
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-31T16:11:02.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "id": TEST_FCO_ID,
                "call_id": TEST_CALL_ID,
                "output": [{"type": "input_text", "text": cite_text}],
            },
        },
    )
    return tuple(
        rollout_record(value, line_number) for line_number, value in enumerate(values, start=1)
    )


def build_test_index(action: str = "search_query") -> api.RolloutIndex:
    return api.build_rollout_index(
        minimal_rollout_records(action),
        timezone_name=TEST_TIMEZONE,
        configured_rollout_basename=TEST_ROLLOUT_FILENAME,
    )


def build_duplicate_evidence_index() -> api.RolloutIndex:
    index = build_test_index()
    return api.RolloutIndex(
        session=index.session,
        fc_rows=index.fc_rows
        + (
            api.CodexFcRow(
                timestamp=index.fc_rows[0].timestamp,
                fc_id=TEST_VIEW_FC_ID,
                call_id=TEST_VIEW_CALL_ID,
                name="run",
                namespace="web",
                arguments_json=TEST_VIEW_ARGUMENTS,
            ),
        ),
        fco_rows=index.fco_rows
        + (
            api.CodexFcoRow(
                timestamp=index.fco_rows[0].timestamp,
                fco_id=TEST_VIEW_FCO_ID,
                call_id=TEST_VIEW_CALL_ID,
            ),
        ),
        turn_ref_rows=index.turn_ref_rows
        + (
            api.CodexTurnRefRow(
                ref_id=TEST_VIEW_REF_ID,
                call_id=TEST_VIEW_CALL_ID,
                domain="example.test",
                snippet="Opened result",
                thumbnail_url=None,
                title="Opened title",
                url=TEST_URL,
                cite_text=f"Opened result: {TEST_EXCERPT}",
            ),
        ),
    )


def valid_submission_body(*, include_comments: bool = True) -> dict[str, object]:
    body: dict[str, object] = {
        expected.column: {
            "value": expected.value,
            "web_search_excerpts": [{"excerpt": expected.excerpt, "url": expected.url}],
        }
        for expected in EXPECTED_EVIDENCE
    }
    if include_comments:
        body[api.KTP_AI_AUGMENT_COMMENTS_COL] = {"value": EXPECTED_COMMENT}
    return body


def report_for_rollout(relative_path: PurePosixPath) -> str:
    lines = ["."]
    for depth, part in enumerate(relative_path.parts):
        prefix = "    " * depth + "└── "
        lines.append(
            prefix
            + (f"{api.APPENDWATCH_OK_PREFIX}{part}" if part == relative_path.name else f"{part}/")
        )
    return "\n".join(lines) + "\n"


def runtime_for_test(
    tmp_path: Path,
    *,
    output_format: str = "txt",
) -> api.RuntimeConfiguration:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    pipeline = PipelineConfig.from_json(CONFIG_PATH).model_copy(
        update={
            "db_file": SOURCE_DB_PATH,
            "output_dir": output_dir,
            "output_format": output_format,
            "pandoc_reference_docx": REFERENCE_DOCX_PATH,
        }
    )
    return api.RuntimeConfiguration(
        pipeline=pipeline,
        detour_db_path=tmp_path / "detour_ai_augment.duckdb",
    )


def prepare_real_sample_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    output_format: str = "txt",
) -> SimpleNamespace:
    deployment_dir = tmp_path / "deployment"
    attempts_dir = tmp_path / "attempts"
    deployment_dir.mkdir()
    report_path = deployment_dir / "appendwatch-tree.txt"
    identity_path = deployment_dir / "id_ed25519"
    known_hosts_path = deployment_dir / "known_hosts"
    lima_config_path = deployment_dir / "ssh.config"
    write_text(report_path, report_for_rollout(JULY_ROLLOUT_RELATIVE_PATH))
    for path in (identity_path, known_hosts_path, lima_config_path):
        write_text(path, "fixture\n")

    runtime = runtime_for_test(tmp_path, output_format=output_format)
    events: list[str] = []
    rendered_cards: list[str] = []
    monkeypatch.setattr(api, "ROLLOUT_JSONL", JULY_ROLLOUT_GUEST_PATH)
    monkeypatch.setattr(api, "APPENDWATCH_REPORT", report_path)
    monkeypatch.setattr(api, "AIVM_IDENTITY_FILE", identity_path)
    monkeypatch.setattr(api, "AIVM_KNOWN_HOSTS_FILE", known_hosts_path)
    monkeypatch.setattr(api, "LIMA_SSH_CONFIG_PATH", lima_config_path)
    monkeypatch.setattr(api, "AIVM_INSTANCE", "aivm")
    monkeypatch.setattr(api, "AIVM_USER", "ai")
    monkeypatch.setattr(api, "AIVM_SSH_PORT", "22022")
    monkeypatch.setattr(api, "ATTEMPTS_DIR", attempts_dir)
    monkeypatch.setattr(api, "SOURCE_FILE", SOURCE_JSONL_PATH)
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)

    def fake_subprocess(command: list[str], **_kwargs: object) -> None:
        if command[0] == "scp":
            events.append("scp")
            assert command[-2] == f"aivm-ai:{JULY_ROLLOUT_GUEST_PATH}"
            write_bytes(Path(command[-1]), read_bytes(JULY_ROLLOUT_PATH))
            return
        assert command[0] == "pandoc"
        output_path = Path(command[command.index("-o") + 1])
        write_bytes(output_path, b"test DOCX renderer output")

    monkeypatch.setattr(api.subprocess, "run", fake_subprocess)

    original_copy_report = api.copy_appendwatch_report
    original_status_check = api.parse_appendwatch_report
    original_persist = api.persist_rollout_index
    original_model_validate_json = api.Submission.model_validate_json
    original_validate_evidence = api.validate_submission_evidence
    original_append_output = api.append_codex_output
    original_ground_truth = api.ground_truth
    original_write_cards_zip = api.write_cards_zip

    def tracked_copy_report(*args: object, **kwargs: object) -> api.ArchivedFile:
        events.append("status_copy")
        return original_copy_report(*args, **kwargs)  # type: ignore[arg-type]

    def tracked_status_check(*args: object, **kwargs: object) -> None:
        events.append("status_check")
        original_status_check(*args, **kwargs)  # type: ignore[arg-type]

    def tracked_persist(*args: object, **kwargs: object) -> None:
        events.append("rollout_index")
        original_persist(*args, **kwargs)  # type: ignore[arg-type]

    def tracked_model_validate_json(
        _cls: type[api.Submission],
        value: str | bytes | bytearray,
    ) -> api.Submission:
        events.append("pydantic")
        return original_model_validate_json(value)

    def tracked_validate_evidence(*args: object, **kwargs: object) -> api.ValidatedEvidence:
        events.append("evidence")
        return original_validate_evidence(*args, **kwargs)  # type: ignore[arg-type]

    def tracked_append_output(*args: object, **kwargs: object) -> None:
        events.append("output")
        original_append_output(*args, **kwargs)  # type: ignore[arg-type]

    def tracked_ground_truth() -> dict[str, object]:
        events.append("ground_truth")
        return original_ground_truth()

    def tracked_write_cards_zip(*args: object, **kwargs: object) -> None:
        events.append("card")
        cards = args[0]
        assert isinstance(cards, dict)
        rendered_cards.extend(cards.values())
        original_write_cards_zip(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(api, "copy_appendwatch_report", tracked_copy_report)
    monkeypatch.setattr(api, "parse_appendwatch_report", tracked_status_check)
    monkeypatch.setattr(api, "persist_rollout_index", tracked_persist)
    monkeypatch.setattr(
        api.Submission,
        "model_validate_json",
        classmethod(tracked_model_validate_json),
    )
    monkeypatch.setattr(api, "validate_submission_evidence", tracked_validate_evidence)
    monkeypatch.setattr(api, "append_codex_output", tracked_append_output)
    monkeypatch.setattr(api, "ground_truth", tracked_ground_truth)
    monkeypatch.setattr(api, "write_cards_zip", tracked_write_cards_zip)

    return SimpleNamespace(
        client=TestClient(api.app),
        payload=valid_submission_body(),
        runtime=runtime,
        attempts_dir=attempts_dir,
        report_path=report_path,
        events=events,
        rendered_cards=rendered_cards,
    )


@pytest.mark.parametrize("action", sorted(api.ELIGIBLE_WEB_ACTIONS))
def test_direct_search_open_and_click_build_complete_ref_rows(action: str) -> None:
    index = build_test_index(action)

    assert len(index.fc_rows) == len(index.fco_rows) == len(index.turn_ref_rows) == 1
    assert index.fc_rows[0].call_id == TEST_CALL_ID
    assert set(json.loads(index.fc_rows[0].arguments_json)) & api.ELIGIBLE_WEB_ACTIONS == {action}
    assert index.fco_rows[0].fco_id == TEST_FCO_ID
    assert index.turn_ref_rows[0] == api.CodexTurnRefRow(
        ref_id=TEST_REF_ID,
        call_id=TEST_CALL_ID,
        domain="example.test",
        snippet="Example snippet",
        thumbnail_url="https://example.test/thumbnail.png",
        title="Example title",
        url=TEST_URL,
        cite_text=index.turn_ref_rows[0].cite_text,
    )
    assert TEST_EXCERPT in index.turn_ref_rows[0].cite_text


def test_optional_result_metadata_is_nullable_and_no_url_ref_is_skipped() -> None:
    records = list(minimal_rollout_records())
    event_value = json.loads(json.dumps(records[3].value))
    event_results = event_value["payload"]["results"]
    valid_result = event_results[0]
    for optional_field in ("domain", "snippet", "thumbnail_url", "title"):
        valid_result.pop(optional_field, None)
    event_results.append({
        "type": "text_result",
        "ref_id": TEST_NO_URL_REF_ID,
        "snippet": "Total lines: 1",
        "title": "Internal Error",
    })
    records[3] = rollout_record(event_value, records[3].line_number)

    output_value = json.loads(json.dumps(records[4].value))
    output_text = output_value["payload"]["output"][0]["text"]
    output_value["payload"]["output"][0]["text"] = (
        f"{output_text}\n{api.CODEX_RESULT_SEPARATOR}\nInternal Error ()\n"
        f"{api.CODEX_CITE_MARKER_PREFIX}{TEST_NO_URL_REF_ID}"
        f"{api.CODEX_CITE_MARKER_SUFFIX} Source: open; Total lines: 1"
    )
    records[4] = rollout_record(output_value, records[4].line_number)

    index = api.build_rollout_index(
        tuple(records),
        timezone_name=TEST_TIMEZONE,
        configured_rollout_basename=TEST_ROLLOUT_FILENAME,
    )

    assert index.turn_ref_rows == (
        api.CodexTurnRefRow(
            ref_id=TEST_REF_ID,
            call_id=TEST_CALL_ID,
            domain=None,
            snippet=None,
            thumbnail_url=None,
            title=None,
            url=TEST_URL,
            cite_text=index.turn_ref_rows[0].cite_text,
        ),
    )
    connection = duckdb.connect(":memory:")
    try:
        api._create_codex_schema(connection)
        not_null = {
            row[1]: bool(row[3])
            for row in connection.execute(
                f"PRAGMA table_info('{api.CODEX_TURN_REF_TABLE}')"
            ).fetchall()
        }
        assert all(not not_null[column] for column in OPTIONAL_REF_METADATA_COLUMNS)

        api.persist_rollout_index(connection, index)
        stored = connection.execute(
            f'SELECT "{api.CODEX_REF_DOMAIN_COL}", '
            f'"{api.CODEX_REF_SNIPPET_COL}", '
            f'"{api.CODEX_REF_THUMBNAIL_URL_COL}", '
            f'"{api.CODEX_REF_TITLE_COL}", '
            f'"{api.CODEX_REF_URL_COL}" '
            f"FROM {api.CODEX_TURN_REF_TABLE}"
        ).fetchone()
        assert stored == (None, None, None, None, TEST_URL)
    finally:
        connection.close()


def test_rollout_index_fails_closed_on_broken_direct_chain() -> None:
    records = minimal_rollout_records()
    without_event = records[:3] + records[4:]

    with pytest.raises(api.PushValidationError, match="one function call and one"):
        api.build_rollout_index(
            without_event,
            timezone_name=TEST_TIMEZONE,
            configured_rollout_basename=TEST_ROLLOUT_FILENAME,
        )

    malformed_output = list(records)
    output_value = json.loads(json.dumps(malformed_output[-1].value))
    output_value["payload"]["output"].append(
        {"type": "input_text", "text": TEST_EXCERPT}
    )
    malformed_output[-1] = rollout_record(output_value, malformed_output[-1].line_number)
    with pytest.raises(api.PushValidationError, match="exactly one input_text"):
        api.build_rollout_index(
            tuple(malformed_output),
            timezone_name=TEST_TIMEZONE,
            configured_rollout_basename=TEST_ROLLOUT_FILENAME,
        )


def test_rollout_parser_rejects_completed_malformed_json_but_ignores_live_tail(
    tmp_path: Path,
) -> None:
    rollout_path = tmp_path / "rollout.jsonl"
    write_bytes(rollout_path, b'{"type":"event_msg"}\n{"incomplete"')
    assert len(api.parse_rollout(rollout_path)) == 1

    write_bytes(rollout_path, b'{"type":"event_msg"}\nnot-json\n')
    with pytest.raises(api.PushValidationError, match="line 2"):
        api.parse_rollout(rollout_path)


def test_submission_contract_has_eight_evidence_fields_and_optional_comments() -> None:
    without_comments = valid_submission_body(include_comments=False)
    parsed = api.Submission.model_validate(without_comments)

    assert tuple(column for column, _field in parsed.evidence_items()) == (
        api.AI_AUGMENT_EVIDENCE_COLUMNS
    )
    assert parsed.comments is None
    assert api.KTP_AI_AUGMENT_COMMENTS_COL not in parsed.normalized_values()

    with_comments = api.Submission.model_validate(valid_submission_body())
    assert with_comments.comments is not None
    assert with_comments.comments.value == EXPECTED_COMMENT

    missing = valid_submission_body()
    missing.pop(api.AI_AUGMENT_EVIDENCE_COLUMNS[0])
    with pytest.raises(ValidationError):
        api.Submission.model_validate(missing)

    absent_evidence = valid_submission_body()
    absent_evidence[api.AI_AUGMENT_EVIDENCE_COLUMNS[0]]["web_search_excerpts"] = []  # type: ignore[index]
    with pytest.raises(ValidationError):
        api.Submission.model_validate(absent_evidence)

    duplicate_evidence = valid_submission_body()
    first_field = duplicate_evidence[api.AI_AUGMENT_EVIDENCE_COLUMNS[0]]
    first_field["web_search_excerpts"] *= 2  # type: ignore[index]
    with pytest.raises(ValidationError):
        api.Submission.model_validate(duplicate_evidence)

    comments_with_evidence = valid_submission_body()
    comments_with_evidence[api.KTP_AI_AUGMENT_COMMENTS_COL][  # type: ignore[index]
        "web_search_excerpts"
    ] = []
    with pytest.raises(ValidationError):
        api.Submission.model_validate(comments_with_evidence)


def test_pydantic_failure_reports_exact_rejected_input() -> None:
    body = valid_submission_body()
    rejected_value = ["not", "an", "object"]
    body[api.AI_AUGMENT_EVIDENCE_COLUMNS[0]] = rejected_value

    with pytest.raises(ValidationError) as raised:
        api.Submission.model_validate(body)

    field, reason, failed_input = api.pydantic_failure(raised.value)
    assert field == api.AI_AUGMENT_EVIDENCE_COLUMNS[0]
    assert reason == "Input should be a valid dictionary or instance of FieldSubmission"
    assert failed_input is rejected_value


def test_persisted_index_is_idempotent_and_evidence_lookup_is_exact() -> None:
    connection = duckdb.connect(":memory:")
    try:
        index = build_test_index()
        api.persist_rollout_index(connection, index)
        api.persist_rollout_index(connection, index)
        body = {
            column: {
                "value": column,
                "web_search_excerpts": [{"excerpt": TEST_EXCERPT, "url": TEST_URL}],
            }
            for column in api.AI_AUGMENT_EVIDENCE_COLUMNS
        }
        submission = api.Submission.model_validate(body)
        validated = api.validate_submission_evidence(
            connection,
            submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
        )
        assert [
            match.evidence_number for matches in validated.values() for match in matches
        ] == list(range(1, len(api.AI_AUGMENT_EVIDENCE_COLUMNS) + 1))

        changed_excerpt = json.loads(json.dumps(body))
        changed_excerpt[api.AI_AUGMENT_EVIDENCE_COLUMNS[0]]["web_search_excerpts"][0]["excerpt"] = (
            TEST_EXCERPT[:-1] + "X"
        )
        with pytest.raises(api.PushValidationError, match="no indexed match"):
            api.validate_submission_evidence(
                connection,
                api.Submission.model_validate(changed_excerpt),
                rollout_filename=TEST_ROLLOUT_FILENAME,
            )

        changed_url = json.loads(json.dumps(body))
        changed_url[api.AI_AUGMENT_EVIDENCE_COLUMNS[0]]["web_search_excerpts"][0]["url"] = (
            TEST_URL + "/"
        )
        with pytest.raises(api.PushValidationError, match="URL does not match"):
            api.validate_submission_evidence(
                connection,
                api.Submission.model_validate(changed_url),
                rollout_filename=TEST_ROLLOUT_FILENAME,
            )
    finally:
        connection.close()


@pytest.mark.skip(reason="multiple evidence matches are currently allowed")
def test_multiple_sql_matches_report_the_exact_excerpt() -> None:
    connection = duckdb.connect(":memory:")
    try:
        index = build_test_index()
        duplicate_call_id = "call_duplicate"
        duplicate_index = api.RolloutIndex(
            session=index.session,
            fc_rows=index.fc_rows
            + (
                api.CodexFcRow(
                    timestamp=index.fc_rows[0].timestamp,
                    fc_id="fc_duplicate",
                    call_id=duplicate_call_id,
                    name="run",
                    namespace="web",
                    arguments_json=index.fc_rows[0].arguments_json,
                ),
            ),
            fco_rows=index.fco_rows
            + (
                api.CodexFcoRow(
                    timestamp=index.fco_rows[0].timestamp,
                    fco_id="fco_duplicate",
                    call_id=duplicate_call_id,
                ),
            ),
            turn_ref_rows=index.turn_ref_rows
            + (
                api.CodexTurnRefRow(
                    ref_id="turn1search0",
                    call_id=duplicate_call_id,
                    domain="duplicate.example.test",
                    snippet="Duplicate snippet",
                    thumbnail_url=None,
                    title="Duplicate title",
                    url=TEST_URL,
                    cite_text=f"Duplicate result: {TEST_EXCERPT}",
                ),
            ),
        )
        api.persist_rollout_index(connection, duplicate_index)
        body = {
            column: {
                "value": column,
                "web_search_excerpts": [{"excerpt": TEST_EXCERPT, "url": TEST_URL}],
            }
            for column in api.AI_AUGMENT_EVIDENCE_COLUMNS
        }

        with pytest.raises(api.MultipleEvidenceMatches) as raised:
            api.validate_submission_evidence(
                connection,
                api.Submission.model_validate(body),
                rollout_filename=TEST_ROLLOUT_FILENAME,
            )
        assert raised.value.excerpt == TEST_EXCERPT
        assert TEST_EXCERPT in api.MULTIPLE_MATCH_DETAIL.format(excerpt=raised.value.excerpt)
    finally:
        connection.close()


def test_multiple_exact_excerpt_and_url_matches_use_random_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert api.ALLOW_MULTIPLE_EVIDENCE_MATCHES is True
    connection = duckdb.connect(":memory:")
    try:
        api.persist_rollout_index(connection, build_duplicate_evidence_index())
        offered_ref_ids: list[tuple[str, ...]] = []

        def choose_search(candidates: tuple[api.EvidenceCandidate, ...]) -> api.EvidenceCandidate:
            offered_ref_ids.append(tuple(candidate.ref_id for candidate in candidates))
            return next(candidate for candidate in candidates if candidate.ref_id == TEST_REF_ID)

        monkeypatch.setattr(api, "EVIDENCE_RANDOM", SimpleNamespace(choice=choose_search))
        body = {
            column: {
                "value": column,
                "web_search_excerpts": [{"excerpt": TEST_EXCERPT, "url": TEST_URL}],
            }
            for column in api.AI_AUGMENT_EVIDENCE_COLUMNS
        }

        validated = api.validate_submission_evidence(
            connection,
            api.Submission.model_validate(body),
            rollout_filename=TEST_ROLLOUT_FILENAME,
        )

        matches = [match for field_matches in validated.values() for match in field_matches]
        assert {match.ref_id for match in matches} == {TEST_REF_ID}
        assert offered_ref_ids == [(TEST_REF_ID, TEST_VIEW_REF_ID)] * len(
            api.AI_AUGMENT_EVIDENCE_COLUMNS
        )
    finally:
        connection.close()


def test_seeded_evidence_selection_round_trips_deterministically(tmp_path: Path) -> None:
    database_path = tmp_path / "evidence.duckdb"
    index = build_duplicate_evidence_index()
    submission = api.Submission.model_validate({
        column: {
            "value": column,
            "web_search_excerpts": [{"excerpt": TEST_EXCERPT, "url": TEST_URL}],
        }
        for column in api.AI_AUGMENT_EVIDENCE_COLUMNS
    })
    sample_seed = PipelineConfig.from_json(CONFIG_PATH).sample_seed
    selections: list[tuple[tuple[str, int, str, str], ...]] = []

    for _roundtrip in range(2):
        connection = duckdb.connect(str(database_path))
        try:
            api.persist_rollout_index(connection, index)
            api._seed_evidence_random(sample_seed)
            validated = api.validate_submission_evidence(
                connection,
                submission,
                rollout_filename=TEST_ROLLOUT_FILENAME,
            )
            selections.append(tuple(
                (match.field, match.evidence_number, match.ref_id, match.call_id)
                for field_matches in validated.values()
                for match in field_matches
            ))
        finally:
            connection.close()

    assert selections[0] == selections[1]
    assert len(selections[0]) == len(api.AI_AUGMENT_EVIDENCE_COLUMNS)
    assert {
        (ref_id, call_id) for _field, _number, ref_id, call_id in selections[0]
    }.issubset({
        (TEST_REF_ID, TEST_CALL_ID),
        (TEST_VIEW_REF_ID, TEST_VIEW_CALL_ID),
    })


def test_renderer_uses_generic_arguments_wording() -> None:
    citation_marker = f"{api.CODEX_CITE_MARKER_PREFIX}{TEST_REF_ID}{api.CODEX_CITE_MARKER_SUFFIX}"
    cite_prefix = (
        f"Neighbor header turn9search9\n{citation_marker}\n"
        "# Heading\n- [source](https://example.test) `before` "
        f"{api.CODEX_CITE_MARKER_PREFIX}13\u2020"
    )
    cite_suffix = (
        f"{codex_parse.INLINE_CITATION_SEPARATOR}example.test"
        f"{api.CODEX_CITE_MARKER_SUFFIX} after\n> quoted"
    )
    footnote = codex_parse.render_footnote(
        number=1,
        cite_text=f"{cite_prefix}{TEST_EXCERPT}{cite_suffix}",
        citation_marker=citation_marker,
        marker_prefix=api.CODEX_CITE_MARKER_PREFIX,
        marker_suffix=api.CODEX_CITE_MARKER_SUFFIX,
        excerpt=TEST_EXCERPT,
        excerpt_position=len(cite_prefix),
        context_characters=api.FOOTNOTE_CONTEXT_CHARACTERS,
        fco_timestamp="2026-07-31T16:11:02.000Z",
        url=TEST_URL,
    )

    assert f"**{codex_parse.escape_markdown_text(TEST_EXCERPT)}**" in footnote
    assert r"\# Heading \- \[source\]\(https\:\/\/example\.test\) \`before\`" in footnote
    assert r"after \> quoted" in footnote
    assert "\n" not in footnote
    assert TEST_REF_ID not in footnote
    assert "turn9search9" not in footnote
    assert api.CODEX_CITE_MARKER_PREFIX not in footnote
    assert api.CODEX_CITE_MARKER_SUFFIX not in footnote
    assert codex_parse.INLINE_CITATION_SEPARATOR not in footnote
    assert "using arguments^1^" in footnote
    assert "search query" not in footnote
    assert codex_parse.render_footnote_argument(
        1,
        CALL_ARGUMENTS_TURN_6,
        {"turn5search0": COMPANY_URL},
        ref_id_pattern=api.CODEX_REF_ID_PATTERN,
    ) == (
        f"1. {DISPLAY_ARGUMENTS_TURN_6}"
    )
    assert codex_parse.render_footnote_argument(
        1,
        CALL_ARGUMENTS_TURN_7,
        {"turn6view0": COMPANY_URL},
        ref_id_pattern=api.CODEX_REF_ID_PATTERN,
    ) == (
        f"1. {DISPLAY_ARGUMENTS_TURN_7}"
    )
    multi_open = (
        '{"open":[{"ref_id":"turn1search0"},{"ref_id":"turn1search1"}],'
        '"response_length":"long"}'
    )
    assert codex_parse.render_footnote_argument(
        1,
        multi_open,
        {"turn1search0": COMPANY_URL, "turn1search1": OFFICERS_URL},
        ref_id_pattern=api.CODEX_REF_ID_PATTERN,
    ) == (
        f'1. {{"open":[{{"ref_id":"turn1search0","url":"{COMPANY_URL}"}},'
        f'{{"ref_id":"turn1search1","url":"{OFFICERS_URL}"}}],'
        '"response_length":"long"}'
    )
    assert codex_parse.render_footnote_argument(
        1,
        CALL_ARGUMENTS_TURN_6,
        {},
        ref_id_pattern=api.CODEX_REF_ID_PATTERN,
    ) == (f"1. {CALL_ARGUMENTS_TURN_6}")
    direct_url_open = (
        f'{{"open":[{{"ref_id":"{COMPANY_URL}"}}],"response_length":"long"}}'
    )
    assert codex_parse.render_footnote_argument(
        1,
        direct_url_open,
        {},
        ref_id_pattern=api.CODEX_REF_ID_PATTERN,
    ) == (f"1. {direct_url_open}")
    assert codex_parse.render_footnote_argument(
        1,
        CALL_ARGUMENTS_TURN_2,
        {},
        ref_id_pattern=api.CODEX_REF_ID_PATTERN,
    ) == (
        f"1. {CALL_ARGUMENTS_TURN_2}"
    )


def test_copied_report_requires_one_exact_nested_ok_path(tmp_path: Path) -> None:
    report_path = tmp_path / "snapshot.txt"
    write_text(report_path, report_for_rollout(TEST_ROLLOUT_RELATIVE_PATH))
    api.parse_appendwatch_report(report_path, TEST_ROLLOUT_RELATIVE_PATH)

    write_text(
        report_path,
        report_for_rollout(TEST_ROLLOUT_RELATIVE_PATH).replace(
            api.APPENDWATCH_OK_PREFIX,
            api.APPENDWATCH_COMPROMISED_PREFIX,
        ),
    )
    with pytest.raises(api.PushValidationError):
        api.parse_appendwatch_report(report_path, TEST_ROLLOUT_RELATIVE_PATH)


@pytest.mark.parametrize(
    "report_text",
    (
        ".  [COMPROMISED: monitoring gap]\n",
        ".\n",
        ".\n└── malformed status rollout-chat.jsonl\n",
        (
            ".\n"
            "└── 2026/\n"
            "    └── 07/\n"
            "        └── 31/\n"
            f"            ├── {api.APPENDWATCH_OK_PREFIX}rollout-chat.jsonl\n"
            f"            └── {api.APPENDWATCH_OK_PREFIX}rollout-chat.jsonl\n"
        ),
    ),
)
def test_copied_report_missing_malformed_or_ambiguous_fails_closed(
    report_text: str,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "snapshot.txt"
    write_text(report_path, report_text)

    with pytest.raises(api.PushValidationError):
        api.parse_appendwatch_report(report_path, TEST_ROLLOUT_RELATIVE_PATH)


@pytest.mark.parametrize(
    "rollout_path",
    (
        "",
        "relative/rollout-chat.jsonl",
        "/home/ai/.codex/sessions/../rollout-chat.jsonl",
        "/home/ai/rollout-chat.jsonl",
        "/home/ai/.codex/sessions/2026/07/31/not-a-rollout.txt",
        "/home/ai/.codex/sessions/2026/07/31/rollout-chat.jsonl\n",
    ),
)
def test_rollout_configuration_is_confined(
    rollout_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "ROLLOUT_JSONL", rollout_path)
    with pytest.raises(api.PushConfigurationError):
        api.push_configuration()


def test_scp_uses_pinned_identity_and_counts_physical_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "report.txt"
    identity_path = tmp_path / "identity"
    known_hosts_path = tmp_path / "known_hosts"
    lima_config_path = tmp_path / "ssh.config"
    for path in (report_path, identity_path, known_hosts_path, lima_config_path):
        write_text(path, "fixture\n")
    configuration = api.PushConfiguration(
        rollout_guest_path=TEST_ROLLOUT_GUEST_PATH,
        rollout_relative_path=TEST_ROLLOUT_RELATIVE_PATH,
        appendwatch_report=report_path,
        lima_ssh_config=lima_config_path,
        identity_file=identity_path,
        known_hosts_file=known_hosts_path,
        ssh_target="aivm-ai",
        host_key_alias="lima-aivm-ai",
    )
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: object) -> None:
        captured["command"] = command
        captured["kwargs"] = kwargs
        write_bytes(Path(command[-1]), b"first\nsecond")

    monkeypatch.setattr(api.subprocess, "run", fake_run)
    archived = api.copy_rollout(configuration, attempt_dir, "attempt-id")

    command = captured["command"]
    assert command[0] == "scp"
    assert f"IdentityFile={identity_path}" in command
    assert f"UserKnownHostsFile={known_hosts_path}" in command
    assert f"HostKeyAlias={configuration.host_key_alias}" in command
    assert "StrictHostKeyChecking=accept-new" in command
    assert command[-2] == f"aivm-ai:{TEST_ROLLOUT_GUEST_PATH}"
    assert "shell" not in captured["kwargs"]
    assert archived.line_count == 2
    assert archived.path.name == "rollout.attempt-id.jsonl"


def test_required_config_and_source_database_are_read_only(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        api.parse_args([])
    assert api.parse_args(["--config", str(CONFIG_PATH)]).config == CONFIG_PATH
    assert api._detour_db_path(SOURCE_DB_PATH) == SOURCE_DB_PATH.with_name(
        "scisci_process__detour_ai-augment.duckdb"
    )

    runtime = runtime_for_test(tmp_path)
    before = file_signature(SOURCE_DB_PATH)
    connection = api.open_source_database(runtime)
    try:
        with pytest.raises(duckdb.Error):
            connection.execute("CREATE TABLE forbidden_write (id INTEGER)")
    finally:
        connection.close()
    assert file_signature(SOURCE_DB_PATH) == before


def test_repeated_researcher_rows_materialize_as_distinct_innerdicts() -> None:
    connection = duckdb.connect(":memory:")
    try:

        def output_row(fragment: int, attempt_id: str) -> dict[str, object]:
            values: dict[str, object] = {
                column: f"value for {column}" for column, _data_type in api.CODEX_OUTPUT_SCHEMA
            }
            values.update({
                api.KTP_NAMEKEY_COL: TEST_SOURCE_KEY,
                api.KTP_FILENAME_COL: TEST_ROLLOUT_FILENAME,
                api.KTP_FRAGMENT_COL: fragment,
                api.KTP_FRAGMENT_TYPE_COL: api.ROLLOUT_LINE_FRAGMENT_TYPE,
                api.DRAW_LABEL: api.TARGET_DRAW_NUMBER,
                api.KTP_FIRST_NAME_COL: "A.",
                api.KTP_LAST_NAME_COL: "Sheikh",
                api.KTP_AI_AUGMENT_ATTEMPT_ID_COL: attempt_id,
                api.KTP_AI_AUGMENT_COMMENTS_COL: None,
            })
            return values

        api.append_codex_output(connection, output_row(100, "attempt-1"))
        api.append_codex_output(connection, output_row(101, "attempt-2"))
        innerdicts_row = connection.execute(
            f"SELECT {api.duckdb_quote_identifier(api.KTP_INNERDICT_JSONLINES_COL)} "
            f"FROM {api.CODEX_INNERDICT_TABLE}"
        ).fetchone()
        assert innerdicts_row is not None
        innerdicts_text = innerdicts_row[0]
        innerdicts = tuple(json.loads(line) for line in innerdicts_text.splitlines())
        assert [row[api.KTP_FRAGMENT_COL] for row in innerdicts] == [100, 101]
        assert [row[api.KTP_AI_AUGMENT_ATTEMPT_ID_COL] for row in innerdicts] == [
            "attempt-1",
            "attempt-2",
        ]

        with pytest.raises(api.PushValidationError, match="already accepted"):
            api.append_codex_output(connection, output_row(101, "attempt-3"))
    finally:
        connection.close()


@pytest.mark.parametrize("output_format", ("txt", "docx"))
def test_real_july_push_matches_exact_objects_and_renders_card_end_to_end(
    output_format: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = prepare_real_sample_push(
        tmp_path,
        monkeypatch,
        output_format=output_format,
    )
    source_signature = file_signature(SOURCE_DB_PATH)

    response = context.client.post("/push", json=context.payload)

    assert response.status_code == 200, response.text
    assert context.events == [
        "scp",
        "status_copy",
        "status_check",
        "rollout_index",
        "pydantic",
        "evidence",
        "output",
        "ground_truth",
        "card",
    ]
    assert file_signature(SOURCE_DB_PATH) == source_signature
    response_lines = response.text.splitlines()
    assert len(response_lines) == 2
    assert json.loads(response_lines[0]) == {
        **{expected.column: expected.value for expected in EXPECTED_EVIDENCE},
        api.KTP_AI_AUGMENT_COMMENTS_COL: EXPECTED_COMMENT,
    }
    truth = json.loads(response_lines[1])
    assert tuple(truth) == api.DOCX_COLUMNS

    attempt_dir = next(context.attempts_dir.iterdir())
    manifest = read_json(attempt_dir / "attempt.json")
    assert manifest["result"] == "accepted"
    assert manifest["artifacts"]["rollout"]["line_count"] == JULY_ROLLOUT_LINE_COUNT
    archived_rollout = attempt_dir / manifest["artifacts"]["rollout"]["filename"]
    archived_report = attempt_dir / manifest["artifacts"]["appendwatch_report"]["filename"]
    assert read_bytes(archived_rollout) == read_bytes(JULY_ROLLOUT_PATH)
    assert read_bytes(archived_report) == read_bytes(context.report_path)
    assert read_text(attempt_dir / "response.jsonl") == response.text

    connection = open_readonly_database(context.runtime.detour_db_path)
    try:
        for table_name, expected_columns in EXPECTED_TABLE_COLUMNS.items():
            columns = tuple(
                row[1]
                for row in connection.execute(f"PRAGMA table_info('{table_name}')").fetchall()
            )
            assert columns == expected_columns
        counts = {}
        for table_name in EXPECTED_TABLE_COLUMNS:
            count_row = connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()
            assert count_row is not None
            counts[table_name] = count_row[0]
        assert counts == {
            api.CODEX_FC_TABLE: JULY_FC_COUNT,
            api.CODEX_FCO_TABLE: JULY_FCO_COUNT,
            api.CODEX_CALLS_TABLE: JULY_CALL_COUNT,
            api.CODEX_TURN_REF_TABLE: JULY_REF_COUNT,
        }
        call_links = tuple(
            row[:3]
            for row in connection.execute(
                f'SELECT "{api.CODEX_CALL_ID_COL}", "{api.CODEX_FC_ID_COL}", '
                f'"{api.CODEX_FCO_ID_COL}", "{api.CODEX_ROLLOUT_FILENAME_COL}" '
                f"FROM {api.CODEX_CALLS_TABLE} ORDER BY id"
            ).fetchall()
        )
        assert set(call_links) == set(EXPECTED_CALL_LINKS)
        assert {
            row[0]
            for row in connection.execute(
                f'SELECT "{api.CODEX_REF_ID_COL}" FROM {api.CODEX_TURN_REF_TABLE} '
                f'WHERE "{api.CODEX_REF_THUMBNAIL_URL_COL}" IS NOT NULL'
            ).fetchall()
        } == set(JULY_THUMBNAIL_REF_IDS)

        for expected in EXPECTED_EVIDENCE:
            rows = connection.execute(
                f"""
                SELECT refs."{api.CODEX_REF_ID_COL}", refs."{api.CODEX_CALL_ID_COL}",
                       calls."{api.CODEX_FC_ID_COL}", calls."{api.CODEX_FCO_ID_COL}",
                       fco."{api.CODEX_FCO_TIMESTAMP_COL}",
                       fc."{api.CODEX_FC_ARGUMENTS_COL}",
                       refs."{api.CODEX_REF_URL_COL}", refs."{api.CODEX_CITE_TEXT_COL}"
                FROM {api.CODEX_TURN_REF_TABLE} refs
                JOIN {api.CODEX_CALLS_TABLE} calls
                  ON calls."{api.CODEX_CALL_ID_COL}" = refs."{api.CODEX_CALL_ID_COL}"
                JOIN {api.CODEX_FCO_TABLE} fco
                  ON fco."{api.CODEX_FCO_ID_COL}" = calls."{api.CODEX_FCO_ID_COL}"
                JOIN {api.CODEX_FC_TABLE} fc
                  ON fc."{api.CODEX_FC_ID_COL}" = calls."{api.CODEX_FC_ID_COL}"
                WHERE strpos(refs."{api.CODEX_CITE_TEXT_COL}", ?) > 0
                """,
                [expected.excerpt],
            ).fetchall()
            assert len(rows) == 1
            row = rows[0]
            assert row[:4] == (
                expected.ref_id,
                expected.call_id,
                expected.fc_id,
                expected.fco_id,
            )
            assert api._render_fco_timestamp(row[4]) == expected.fco_timestamp
            assert row[5] == expected.arguments_json
            assert row[6] == expected.url
            assert expected.excerpt in row[7]

        output_columns = tuple(column for column, _type in api.CODEX_OUTPUT_SCHEMA)
        output_values = connection.execute(f"SELECT * FROM {api.CODEX_OUTPUT_VIEW}").fetchone()
        assert output_values is not None
        output = dict(zip(output_columns, output_values, strict=True))
        assert output[api.KTP_NAMEKEY_COL] == (
            '{"ktp.first_name": "A.", "ktp.last_name": "Sheikh"}'
        )
        assert output[api.KTP_FILENAME_COL] == JULY_ROLLOUT_FILENAME
        assert output[api.KTP_FRAGMENT_COL] == JULY_ROLLOUT_LINE_COUNT
        assert output[api.KTP_FRAGMENT_TYPE_COL] == api.ROLLOUT_LINE_FRAGMENT_TYPE
        assert output[api.DRAW_LABEL] == api.TARGET_DRAW_NUMBER
        metadata = json.loads(output[api.KTP_AI_AUGMENT_SESSION_METADATA_COL])
        assert metadata["session_id"] == JULY_SESSION_ID
        assert output[api.KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL] == "\n".join(
            f"{number}. {expected.display_arguments_json}"
            for number, expected in enumerate(EXPECTED_EVIDENCE, start=1)
        )
        footnotes = output[api.KTP_AI_AUGMENT_FOOTNOTES_COL]
        footnote_lines = footnotes.splitlines()
        assert len(footnote_lines) == len(EXPECTED_EVIDENCE)
        assert api.CODEX_CITE_MARKER_PREFIX not in footnotes
        assert api.CODEX_CITE_MARKER_SUFFIX not in footnotes
        for number, (expected, footnote) in enumerate(
            zip(EXPECTED_EVIDENCE, footnote_lines, strict=True),
            start=1,
        ):
            assert f"**{codex_parse.escape_markdown_text(expected.excerpt)}**" in footnote
            assert f'arguments^{number}^ on "{expected.fco_timestamp}", {expected.url}' in footnote
            assert output[expected.column] == (
                f'**AI-generated text**: "{expected.value}"^{number}^'
            )
        assert re.fullmatch(
            rf'- \*\*AI-generated text\*\*: "{re.escape(EXPECTED_COMMENT)}" '
            r"\(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\)",
            output[api.KTP_AI_AUGMENT_COMMENTS_COL],
        )

        innerdicts_row = connection.execute(
            f"SELECT {api.duckdb_quote_identifier(api.KTP_NAMEKEY_COL)}, "
            f"{api.duckdb_quote_identifier(api.KTP_INNERDICT_JSONLINES_COL)} "
            f"FROM {api.CODEX_INNERDICT_TABLE}"
        ).fetchone()
        assert innerdicts_row is not None
        name_key, innerdicts_text = innerdicts_row
        assert name_key == TEST_SOURCE_KEY
        innerdicts = tuple(json.loads(line) for line in innerdicts_text.splitlines())
        assert len(innerdicts) == 1
        assert innerdicts[0][api.KTP_FILENAME_COL] == JULY_ROLLOUT_FILENAME
        assert innerdicts[0][api.KTP_FRAGMENT_COL] == JULY_ROLLOUT_LINE_COUNT
        assert innerdicts[0][api.KTP_AI_AUGMENT_ATTEMPT_ID_COL] == manifest["attempt_id"]
    finally:
        connection.close()

    card_path = context.runtime.pipeline.output_dir / manifest["artifacts"]["card_zip"]["filename"]
    card_text = "\n".join(context.rendered_cards)
    assert f"#### {api.KTP_FILENAME_COL}: {JULY_ROLLOUT_FILENAME}" in card_text
    assert f"**{api.KTP_FRAGMENT_COL}**: {JULY_ROLLOUT_LINE_COUNT}" in card_text
    assert f"**{api.KTP_AI_AUGMENT_ATTEMPT_ID_COL}**: {manifest['attempt_id']}" in card_text
    assert f"**{api.KTP_AI_AUGMENT_FOOTNOTES_COL}**:" in card_text
    assert f"**{api.KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL}**:" in card_text
    assert (
        card_text.index(f"**{api.KTP_AI_AUGMENT_LINKS_COL}**:")
        < card_text.index(f"**{api.KTP_AI_AUGMENT_COMMENTS_COL}**:")
        < card_text.index(f"**{api.KTP_AI_AUGMENT_FOOTNOTES_COL}**:")
    )
    assert "using arguments^1^" in card_text
    assert "<details>" not in card_text
    if output_format == "txt":
        assert read_zip_text(card_path) == card_text
    else:
        assert all(name.endswith(".docx") for name in zip_member_names(card_path))


@pytest.mark.parametrize("mutation", ("excerpt", "url"))
def test_real_july_push_rejects_changed_evidence_before_ground_truth(
    mutation: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    context = prepare_real_sample_push(tmp_path, monkeypatch)
    payload = json.loads(json.dumps(context.payload))
    first_column = EXPECTED_EVIDENCE[0].column
    evidence = payload[first_column]["web_search_excerpts"][0]
    if mutation == "excerpt":
        evidence["excerpt"] = evidence["excerpt"][:-1] + "X"
    else:
        evidence["url"] += "/"
    monkeypatch.setattr(
        api,
        "open_source_database",
        lambda *_args, **_kwargs: pytest.fail(
            "source database must not open after evidence rejection"
        ),
    )
    monkeypatch.setattr(
        api,
        "ground_truth",
        lambda: pytest.fail("ground truth must not load after evidence rejection"),
    )

    response = context.client.post("/push", json=payload)

    assert response.status_code == 422
    assert response.json() == {"detail": api.VALIDATION_ERROR_DETAIL}
    assert f"excerpt={evidence['excerpt']!r}" in caplog.text
    assert f"url={evidence['url']!r}" in caplog.text
    assert context.events == [
        "scp",
        "status_copy",
        "status_check",
        "rollout_index",
        "pydantic",
        "evidence",
    ]
    attempt_dir = next(context.attempts_dir.iterdir())
    manifest = read_json(attempt_dir / "attempt.json")
    assert manifest["result"] == "rejected"
    assert manifest["stage"] == "duckdb_evidence_validation"
    assert not (attempt_dir / "response.jsonl").exists()
    assert not tuple(context.runtime.pipeline.output_dir.iterdir())

    connection = open_readonly_database(context.runtime.detour_db_path)
    try:
        count_row = connection.execute(
            f"SELECT COUNT(*) FROM {api.CODEX_TURN_REF_TABLE}"
        ).fetchone()
        assert count_row is not None
        assert count_row[0] == JULY_REF_COUNT
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        assert api.CODEX_OUTPUT_ROWS_TABLE not in tables
        assert api.CODEX_INNERDICT_TABLE not in tables
    finally:
        connection.close()


def test_missing_rollout_is_generic_503_and_pull_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_path = tmp_path / "source.jsonl"
    write_text(
        source_path,
        json.dumps({
            api.DRAW_NUMBER_COLUMN: api.TARGET_DRAW_NUMBER,
            api.FRAGMENT_TYPE_COLUMN: api.DOCX_ROW_FRAGMENT_TYPE,
            api.KTP_FIRST_NAME_COL: "A.",
            api.KTP_LAST_NAME_COL: "Sheikh",
            **dict.fromkeys(api.DOCX_COLUMNS),
        })
        + "\n",
    )
    runtime = runtime_for_test(tmp_path)
    monkeypatch.setattr(api, "SOURCE_FILE", source_path)
    monkeypatch.setattr(api, "ROLLOUT_JSONL", "")
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    client = TestClient(api.app)

    push_response = client.post("/push", json={})
    pull_response = client.get("/pull")

    assert push_response.status_code == 503
    assert push_response.json() == {"detail": api.CONFIGURATION_ERROR_DETAIL}
    assert api.ROLLOUT_ENV_NAME in caplog.text
    assert pull_response.status_code == 503
    assert pull_response.json() == {"detail": api.CONFIGURATION_ERROR_DETAIL}


def test_sanctioned_pull_is_dynamic_retryable_and_omits_ground_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = api.configure_runtime(AI_AUGMENT_CONFIG_PATH)
    assert runtime.eligible_cohorts is not None
    source_key = next(
        key
        for key, cohort in runtime.eligible_cohorts.items()
        if cohort == api.GROUND_TRUTH_COHORT
    )
    snapshot = api.SanctionSnapshot(
        run_id=api.UUID("019fb000-0000-7000-8000-000000000001"),
        source_key=source_key,
        session_id="019fb000-0000-7000-8000-000000000002",
        rollout_guest_path=(
            "/home/ai/.codex/sessions/2026/08/07/"
            "rollout-2026-08-07T00-00-00-019fb000-0000-7000-8000-000000000002.jsonl"
        ),
        control_base_url="http://127.0.0.1:8611",
    )
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    monkeypatch.setattr(api, "sanctioned_snapshot", lambda: snapshot)
    monkeypatch.setattr(api, "push_configuration", lambda _rollout: SimpleNamespace())
    monkeypatch.setattr(api, "WORKBOOK_INITIALIZED", True)
    client = TestClient(api.app)

    first_response = client.get("/pull")
    retry_response = client.get("/pull")

    assert first_response.status_code == 200
    assert retry_response.status_code == 200
    assert retry_response.content == first_response.content
    rows = [json.loads(line) for line in first_response.text.splitlines()]
    task = rows[-1]
    name_key = api.NameKey.from_json_key(source_key)
    assert task == {
        api.KTP_FIRST_NAME_COL: name_key.first_name,
        api.KTP_LAST_NAME_COL: name_key.last_name,
        **dict.fromkeys(api.AI_AUGMENT_COLUMNS),
    }
    assert all(
        row.get(api.KTP_FRAGMENT_TYPE_COL) != api.DOCX_ROW_FRAGMENT_TYPE
        for row in rows[:-1]
    )
    assert not any(
        column in row
        for row in rows[:-1]
        for column in api.DOCX_COLUMNS
    )


def test_control_mode_without_sanction_fails_both_routes_without_env_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = runtime_for_test(tmp_path)
    monkeypatch.setattr(api, "CONTROL_BASE_URL", "http://127.0.0.1:8611")
    monkeypatch.setattr(api, "ROLLOUT_JSONL", JULY_ROLLOUT_GUEST_PATH)
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    monkeypatch.setattr(
        api,
        "_control_request",
        lambda _base_url, _path, *, method, body=None: b'{"sanctioned_run":null}',
    )
    client = TestClient(api.app)

    pull_response = client.get("/pull")
    push_response = client.post("/push", json={})

    assert pull_response.status_code == 503
    assert push_response.status_code == 503
    assert pull_response.json() == {"detail": api.CONFIGURATION_ERROR_DETAIL}
    assert push_response.json() == {"detail": api.CONFIGURATION_ERROR_DETAIL}


def test_openapi_does_not_disclose_integrity_internals() -> None:
    schema = TestClient(api.app).get("/openapi.json").json()
    push_schema = schema["paths"]["/push"]["post"]
    serialized = json.dumps(push_schema).lower()

    assert push_schema["description"] == "Validates and stores the completed submission."
    assert "appendwatch" not in serialized
    assert "rollout" not in serialized
    assert api.ROLLOUT_ENV_NAME.lower() not in serialized
