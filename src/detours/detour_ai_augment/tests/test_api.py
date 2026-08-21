from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from threading import Barrier
from types import SimpleNamespace
from typing import Any, cast, get_args
from uuid import UUID
from zipfile import ZipFile

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.detours.detour_ai_augment.src.backend import api
from src.detours.detour_ai_augment.src.backend.helpers import codex_parse
from src.detours.detour_ai_augment.src.backend.helpers.data_models.pydantic_to_paste import (
    EvidenceWithdrawal,
    FieldSubmission,
    StandardizedFieldSubmission,
    WebSearchExcerpt,
)
from src.detours.detour_ai_augment.src.backend.helpers.locale import (
    PYDANTIC_TO_PASTE_SOURCE,
    Locale,
)
from src.helpers.config import PipelineConfig
from src.helpers.data_models.http_request_log import (
    HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY,
    HTTP_REQUEST_LOG_PORT_KEY,
    HttpRequestLogRecord,
)
from src.helpers.duckdb_extensions import load_duckdb_extension_from_config_path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPOSITORY_ROOT / "config.repl.json"
AI_AUGMENT_CONFIG_PATH = REPOSITORY_ROOT / "config_ai_augment.json"
SOURCE_DB_PATH = REPOSITORY_ROOT / "data" / "scisci_process.duckdb"
SOURCE_JSONL_PATH = REPOSITORY_ROOT / "tmp" / "sheikh.jsonl"
REFERENCE_DOCX_PATH = REPOSITORY_ROOT / "resources" / "pandoc-custom-reference.docx"
PYDANTIC_TO_PASTE_PATH = (
    REPOSITORY_ROOT
    / "src"
    / "detours"
    / "detour_ai_augment"
    / "src"
    / "backend"
    / "helpers"
    / "data_models"
    / "pydantic_to_paste.py"
)
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
MARKDOWN_LITERAL_FIELD_TEMPLATE = "**`{field}`**"
FIELD_VALUE_FIELD, FIELD_EVIDENCE_FIELD = FieldSubmission.model_fields
(FIELD_STANDARDIZED_VALUE_FIELD,) = (
    StandardizedFieldSubmission.model_fields.keys() - FieldSubmission.model_fields.keys()
)
EVIDENCE_EXCERPT_FIELD, EVIDENCE_URL_FIELD = WebSearchExcerpt.model_fields
(
    EVIDENCE_WITHDRAWAL_ACTION_FIELD,
    EVIDENCE_WITHDRAWAL_REASON_FIELD,
    EVIDENCE_WITHDRAWAL_ATTESTED_FIELD,
) = EvidenceWithdrawal.model_fields
EVIDENCE_WITHDRAWAL_ACTION = get_args(
    EvidenceWithdrawal.model_fields[EVIDENCE_WITHDRAWAL_ACTION_FIELD].annotation
)[0]
EVIDENCE_WITHDRAWAL_REASON = get_args(
    EvidenceWithdrawal.model_fields[EVIDENCE_WITHDRAWAL_REASON_FIELD].annotation
)[0]

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
V2_CITE_TEXT = "Profile: José García — Senior\nResearcher"
V2_EXACT_EXCERPT = "José García — Senior\nResearcher"
TEST_NAMEKEY = '{"ktp.first_name": "A.", "ktp.last_name": "Sheikh"}'
TEST_RUN_ID = UUID("019fa457-aac5-7652-8669-9d571206e7cb")
TEST_SECOND_RUN_ID = UUID("019fa457-aac5-7652-8669-9d571206e7cc")
TEST_ATTEMPT_TIMESTAMP = datetime(2026, 8, 14, tzinfo=timezone.utc)
TEST_CONTROL_RUN_EVENTS_TOKEN = "test-control-run-events-token"
TEST_AUTHORITATIVE_REQUEST_BODY = b'{"probe":true}'
TEST_AUTHORITATIVE_RESPONSE_BODY = {"accepted": True}
TEST_AUTHORITATIVE_RESPONSE_HEADER = "X-Authoritative-Probe"
TEST_AUTHORITATIVE_RESPONSE_HEADER_VALUE = "preserved"
TEST_CONTROL_IDEMPOTENCY_KEY = "test-control-idempotency-key"
TEST_AUTHORITATIVE_LOG_FILENAME = "authoritative.jsonl"
TEST_DETOUR_DB_FILENAME = "detour.duckdb"
TEST_ROLLOUT_CAS_DIRECTORY = "rollout-cas"

HAANEN_REJECTED_ATTEMPT_ID = "20260813T141344_678596Z_8ef1f6372b4a48d9a3b1279736356363"
HAANEN_ACCEPTED_ATTEMPT_ID = "20260813T141450_027429Z_044215aac8c44200882531b10a2acfa6"
HAANEN_REJECTED_ATTEMPT_DIR = REPOSITORY_ROOT / "tmp" / HAANEN_REJECTED_ATTEMPT_ID
HAANEN_ACCEPTED_ATTEMPT_DIR = REPOSITORY_ROOT / "tmp" / HAANEN_ACCEPTED_ATTEMPT_ID
HAANEN_REJECTED_ROLLOUT_PATH = (
    HAANEN_REJECTED_ATTEMPT_DIR / f"rollout.{HAANEN_REJECTED_ATTEMPT_ID}.jsonl"
)
HAANEN_ACCEPTED_ROLLOUT_PATH = (
    HAANEN_ACCEPTED_ATTEMPT_DIR / f"rollout.{HAANEN_ACCEPTED_ATTEMPT_ID}.jsonl"
)
HAANEN_ROLLOUT_FILENAME = "rollout-2026-08-13T10-08-12-019ffb73-b72c-7812-9fc4-d56fdf3ea1a2.jsonl"
HAANEN_SESSION_ID = "019ffb73-b72c-7812-9fc4-d56fdf3ea1a2"
HAANEN_RUN_ID = UUID("019ffb73-b72c-7812-9fc4-d56fdf3ea1a3")
HAANEN_NAMEKEY = '{"ktp.first_name": "J. B.", "ktp.last_name": "Haanen"}'
HAANEN_TOOL_CALL_TYPE = "custom_tool_call"
HAANEN_TOOL_INPUT_KEY = "input"
HAANEN_COMMAND_START = "{cmd:"
HAANEN_HEREDOC_START = "--data-binary @- <<'JSON'\n"
HAANEN_HEREDOC_END = "\nJSON"
HAANEN_PATCH_ASSIGNMENT_START = "const patch = "
HAANEN_PATCH_FILE_START = "*** Add File: haanen_submission.json\n"
HAANEN_PATCH_END = "*** End Patch"
HAANEN_CORRECTED_NEAR_EXCERPT = (
    "He co-authored over 500 peer-reviewed articles, is currently \nEditor-in-Chief of ESMO IOTECH."
)
HAANEN_ORIGINAL_GENDER_EXCERPT = "Geslacht\n\nMan"
HAANEN_RETRY_GENDER_EXCERPT = "Man"
HAANEN_ORIGINAL_EVIDENCE_COUNT = 22
HAANEN_RETRY_EVIDENCE_COUNT = 9
HAANEN_ARCHIVED_EVIDENCE_COLUMNS = tuple(
    column
    for column in api.AI_AUGMENT_EVIDENCE_COLUMNS
    if column != api.KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL
)
HAANEN_JSON_DECODER = json.JSONDecoder()
TEST_STANDARDIZED_VALUES = {
    api.KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL: {
        "first_name": "NR",
        "last_name": "NR",
        "orcid": "NR",
        "openalex_id": "NR",
    },
    api.KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL: {
        "place": "NR",
        "location": "NR",
    },
    api.KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL: {
        "race": "NA",
        "ethnicity": "NA",
        "language": "NR",
        "culture": "NA",
    },
    api.KTP_AI_AUGMENT_GENDER_COL: "NR",
    api.KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL: "NR",
    api.KTP_AI_AUGMENT_EDUCATION_COL: "NR",
    api.KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL: "NR",
    api.KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL: "NR",
    api.KTP_AI_AUGMENT_LINKS_COL: "NR",
}

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
    f'{{"open":[{{"ref_id":"turn5search0","url":"{COMPANY_URL}"}}],"response_length":"long"}}'
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
        api.KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
        "British nationality; race, ethnicity, language, and culture not reported",
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


def logical_database_snapshot(
    path: Path,
) -> dict[str, tuple[str, tuple[tuple[object, ...], ...], tuple[tuple[object, ...], ...]]]:
    connection = open_readonly_database(path)
    try:
        relations = tuple(
            connection.execute(
                "SELECT table_name, table_type FROM information_schema.tables "
                "WHERE table_schema = 'main' ORDER BY table_name"
            ).fetchall()
        )
        return {
            str(name): (
                str(relation_type),
                tuple(
                    tuple(row)
                    for row in connection.execute(
                        "SELECT column_name, data_type, is_nullable "
                        "FROM information_schema.columns "
                        "WHERE table_schema = 'main' AND table_name = ? "
                        "ORDER BY ordinal_position",
                        [name],
                    ).fetchall()
                ),
                tuple(
                    tuple(row)
                    for row in connection.execute(
                        f"SELECT * FROM {api.duckdb_quote_identifier(str(name))} ORDER BY ALL"
                    ).fetchall()
                ),
            )
            for name, relation_type in relations
        }
    finally:
        connection.close()


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


def build_citation_index(
    sections: tuple[tuple[str, str], ...],
) -> api.RolloutIndex:
    index = build_test_index()
    return api.RolloutIndex(
        session=index.session,
        fc_rows=index.fc_rows,
        fco_rows=index.fco_rows,
        turn_ref_rows=tuple(
            api.CodexTurnRefRow(
                ref_id=f"turn0search{section_index}",
                call_id=TEST_CALL_ID,
                domain="example.test",
                snippet="Example snippet",
                thumbnail_url=None,
                title="Example title",
                url=url,
                cite_text=cite_text,
            )
            for section_index, (url, cite_text) in enumerate(sections)
        ),
    )


def submission_body_for_evidence(
    excerpt: str,
    *,
    url: str = TEST_URL,
) -> dict[str, object]:
    return {
        column: {
            "value": column,
            "web_search_excerpts": [{"excerpt": excerpt, "url": url}],
        }
        for column in api.AI_AUGMENT_EVIDENCE_COLUMNS
    }


def standardized_submission_body(
    plain_body: dict[str, object],
) -> dict[str, object]:
    standardized_body = deepcopy(plain_body)
    for column in api.AI_AUGMENT_EVIDENCE_COLUMNS:
        field_submission = standardized_body[column]
        assert isinstance(field_submission, dict)
        field_submission[FIELD_STANDARDIZED_VALUE_FIELD] = deepcopy(
            TEST_STANDARDIZED_VALUES[column]
        )
    return standardized_body


def connect_v2_index(
    index: api.RolloutIndex,
    *,
    database_path: Path | None = None,
) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(database_path) if database_path is not None else ":memory:")
    load_duckdb_extension_from_config_path(
        connection,
        api.CODEX_TOKEN_EXTENSION,
        CONFIG_PATH,
        log=None,
    )
    api.persist_rollout_index(
        connection,
        index,
        codex_match_version=2,
    )
    return connection


def historical_haanen_submissions() -> tuple[dict[str, object], dict[str, object]]:
    rejected_stream = HAANEN_REJECTED_ROLLOUT_PATH.open("r", encoding="utf-8")
    accepted_stream = HAANEN_ACCEPTED_ROLLOUT_PATH.open("r", encoding="utf-8")
    tool_inputs: list[list[str]] = []
    for stream in (rejected_stream, accepted_stream):
        inputs: list[str] = []
        with stream:
            for line in stream:
                value = json.loads(line)
                payload = value.get(api.CODEX_PAYLOAD_KEY)
                if (
                    isinstance(payload, dict)
                    and payload.get(api.CODEX_TYPE_KEY) == HAANEN_TOOL_CALL_TYPE
                    and isinstance(payload.get(HAANEN_TOOL_INPUT_KEY), str)
                ):
                    inputs.append(payload[HAANEN_TOOL_INPUT_KEY])
        tool_inputs.append(inputs)

    rejected_input = next(
        value for value in tool_inputs[0] if HAANEN_HEREDOC_START.replace("\n", "\\n") in value
    )
    rejected_command, _end = HAANEN_JSON_DECODER.raw_decode(
        rejected_input.split(HAANEN_COMMAND_START, 1)[1]
    )
    rejected_document = rejected_command.split(HAANEN_HEREDOC_START, 1)[1].split(
        HAANEN_HEREDOC_END,
        1,
    )[0]

    accepted_input = next(
        value for value in tool_inputs[1] if HAANEN_PATCH_FILE_START.replace("\n", "\\n") in value
    )
    accepted_patch, _end = HAANEN_JSON_DECODER.raw_decode(
        accepted_input.split(HAANEN_PATCH_ASSIGNMENT_START, 1)[1]
    )
    accepted_lines = accepted_patch.split(HAANEN_PATCH_FILE_START, 1)[1].split(
        HAANEN_PATCH_END,
        1,
    )[0]
    accepted_document = "\n".join(
        line[1:] for line in accepted_lines.splitlines() if line.startswith("+")
    )

    rejected_submission = json.loads(rejected_document)
    accepted_submission = json.loads(accepted_document)
    assert isinstance(rejected_submission, dict)
    assert isinstance(accepted_submission, dict)
    race_evidence_source = api.KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL
    rejected_submission[api.KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL] = {
        FIELD_VALUE_FIELD: "Not present in the archived pre-field submission.",
        FIELD_EVIDENCE_FIELD: deepcopy(
            rejected_submission[race_evidence_source][FIELD_EVIDENCE_FIELD][:1]
        ),
    }
    accepted_submission[api.KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL] = deepcopy(
        rejected_submission[api.KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL]
    )
    accepted_submission = standardized_submission_body(accepted_submission)
    return rejected_submission, accepted_submission


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
    replay_log_path = tmp_path / "authoritative.jsonl"
    rollout_cas_dir = tmp_path / "rollout-cas"
    output_dir.mkdir(exist_ok=True)
    replay_log_path.write_text("", encoding=api.TEXT_ENCODING)
    pipeline = api.AiAugmentPipelineConfig.from_json(AI_AUGMENT_CONFIG_PATH).model_copy(
        update={
            "db_file": SOURCE_DB_PATH,
            "output_dir": output_dir,
            "output_format": output_format,
            "pandoc_reference_docx": REFERENCE_DOCX_PATH,
            "rollout_cas_dir": rollout_cas_dir,
        }
    )
    replay_log = api.RegisteredResource(
        name=replay_log_path.name,
        hash=hashlib.sha256(b"").hexdigest(),
        group=api.ResourceGroup.KTP_PIPELINE_ARTIFACT,
        fragment_type=api.FragmentType.LINE_NUMBER,
        url=replay_log_path.as_uri(),
    )
    return api.RuntimeConfiguration(
        pipeline=pipeline,
        detour_db_path=tmp_path / "detour_ai_augment.duckdb",
        replay_log=replay_log,
        rollout_cas_dir=rollout_cas_dir,
        eligible_cohorts={TEST_NAMEKEY: api.GROUND_TRUTH_COHORT},
    )


def prepare_real_sample_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    output_format: str = "txt",
) -> SimpleNamespace:
    deployment_dir = tmp_path / "deployment"
    deployment_dir.mkdir()
    report_path = deployment_dir / "appendwatch-tree.txt"
    identity_path = deployment_dir / "id_ed25519"
    known_hosts_path = deployment_dir / "known_hosts"
    lima_config_path = deployment_dir / "ssh.config"
    write_text(report_path, report_for_rollout(JULY_ROLLOUT_RELATIVE_PATH))
    for path in (identity_path, known_hosts_path, lima_config_path):
        write_text(path, "fixture\n")

    runtime = runtime_for_test(tmp_path, output_format=output_format)
    rendered_cards: list[str] = []
    configuration = api.PushConfiguration(
        rollout_guest_path=JULY_ROLLOUT_GUEST_PATH,
        rollout_relative_path=JULY_ROLLOUT_RELATIVE_PATH,
        appendwatch_report=report_path,
        lima_ssh_config=lima_config_path,
        identity_file=identity_path,
        known_hosts_file=known_hosts_path,
        ssh_target="aivm-ai",
        host_key_alias="lima-aivm-ai",
    )
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    monkeypatch.setattr(api, "push_configuration", lambda _rollout=None: configuration)
    monkeypatch.setattr(api, "CONTROL_RUN_EVENTS_TOKEN", TEST_CONTROL_RUN_EVENTS_TOKEN)
    monkeypatch.setattr(api, "AUTHORITATIVE_BACKEND_HEALTHY", False)
    monkeypatch.setattr(api, "AUTHORITATIVE_LOG_DESCRIPTOR", None)
    monkeypatch.setattr(api, "AUTHORITATIVE_LOG_OFFSET", api.AUTHORITATIVE_EMPTY_OFFSET)
    monkeypatch.setattr(api, "AUTHORITATIVE_NEXT_LINE_NUMBER", api.AUTHORITATIVE_FIRST_LINE)

    def fake_subprocess(command: list[str], **_kwargs: object) -> None:
        if command[0] == api.SCP_EXECUTABLE:
            destination = Path(command[-1])
            assert command[-2] == f"aivm-ai:{JULY_ROLLOUT_GUEST_PATH}"
            write_bytes(destination, read_bytes(JULY_ROLLOUT_PATH))
            return
        assert command[0] == "pandoc"
        output_path = Path(command[command.index("-o") + 1])
        write_bytes(output_path, b"test DOCX renderer output")

    monkeypatch.setattr(api.subprocess, "run", fake_subprocess)

    original_write_cards_zip = api.write_cards_zip

    def tracked_write_cards_zip(*args: object, **kwargs: object) -> None:
        cards = args[0]
        assert isinstance(cards, dict)
        rendered_cards.extend(cards.values())
        original_write_cards_zip(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(api, "write_cards_zip", tracked_write_cards_zip)

    return SimpleNamespace(
        payload=valid_submission_body(),
        runtime=runtime,
        report_path=report_path,
        configuration=configuration,
        rendered_cards=rendered_cards,
    )


def test_pure_asgi_middleware_buffers_and_records_finite_control_push(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[HttpRequestLogRecord] = []
    probe_app = FastAPI()
    probe_app.add_middleware(api.AuthoritativeHttpMiddleware)

    @probe_app.post(api.CONTROL_PUSH_PATH)
    async def probe_control_push() -> JSONResponse:
        return JSONResponse(
            content=TEST_AUTHORITATIVE_RESPONSE_BODY,
            headers={
                TEST_AUTHORITATIVE_RESPONSE_HEADER: (
                    TEST_AUTHORITATIVE_RESPONSE_HEADER_VALUE
                )
            },
        )

    monkeypatch.setattr(api, "AUTHORITATIVE_BACKEND_HEALTHY", True)
    monkeypatch.setattr(api, "AUTHORITATIVE_COMMAND_ACTIVE", False)
    monkeypatch.setattr(api, "_append_authoritative_record", records.append)

    with TestClient(probe_app) as client:
        response = client.post(
            api.CONTROL_PUSH_PATH,
            content=TEST_AUTHORITATIVE_REQUEST_BODY,
            headers={api.HTTP_CONTENT_TYPE_HEADER: api.JSON_MEDIA_TYPE},
        )

    assert any(
        middleware.cls is api.AuthoritativeHttpMiddleware
        for middleware in api.app.user_middleware
    )
    assert any(
        middleware.cls is api.AuthoritativeHttpMiddleware
        for middleware in api.commit_app.user_middleware
    )
    assert response.status_code == api.status.HTTP_200_OK
    assert response.json() == TEST_AUTHORITATIVE_RESPONSE_BODY
    assert (
        response.headers[TEST_AUTHORITATIVE_RESPONSE_HEADER]
        == TEST_AUTHORITATIVE_RESPONSE_HEADER_VALUE
    )
    assert len(records) == 1
    record = records[0]
    assert record.method == api.HTTP_POST_METHOD
    assert record.path == api.CONTROL_PUSH_PATH
    assert record.request_body == TEST_AUTHORITATIVE_REQUEST_BODY.decode(api.TEXT_ENCODING)
    assert record.response_code == response.status_code
    assert record.response_body == response.text
    assert (
        record.response_headers[TEST_AUTHORITATIVE_RESPONSE_HEADER.lower()]
        == TEST_AUTHORITATIVE_RESPONSE_HEADER_VALUE
    )
    assert record.received_at_unix_usec is None
    assert record.ready_to_respond_at_unix_usec is not None
    assert api.AUTHORITATIVE_COMMAND_ACTIVE is False


def test_control_push_is_logged_projected_and_replayed_through_real_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_log_path = tmp_path / TEST_AUTHORITATIVE_LOG_FILENAME
    detour_db_path = tmp_path / TEST_DETOUR_DB_FILENAME
    rollout_cas_dir = tmp_path / TEST_ROLLOUT_CAS_DIRECTORY
    replay_log_path.write_bytes(b"")
    replay_log = api.RegisteredResource(
        name=replay_log_path.name,
        hash=hashlib.sha256(b"").hexdigest(),
        group=api.ResourceGroup.KTP_PIPELINE_ARTIFACT,
        fragment_type=api.FragmentType.LINE_NUMBER,
        url=replay_log_path.as_uri(),
    )
    pipeline = cast(
        api.AiAugmentDetourConfig,
        SimpleNamespace(match_rule_version=SimpleNamespace(codex_match=1)),
    )
    runtime = api.AiAugmentBackendContext(
        pipeline=pipeline,
        detour_db_path=detour_db_path,
        replay_log=replay_log,
        rollout_cas_dir=rollout_cas_dir,
        eligible_cohorts={},
    )
    event = api.ControlRunEvent(
        run_id=TEST_RUN_ID,
        namekey=TEST_NAMEKEY,
        at=TEST_ATTEMPT_TIMESTAMP,
        kind=api.ControlRunEventKind.QUEUED,
    )
    body = api.ControlPushRequest(event=event).model_dump_json().encode(api.TEXT_ENCODING)
    headers = {
        api.CONTROL_RUN_EVENTS_TOKEN_HEADER: TEST_CONTROL_RUN_EVENTS_TOKEN,
        api.HTTP_CONTENT_TYPE_HEADER: api.JSON_MEDIA_TYPE,
        api.HTTP_IDEMPOTENCY_KEY_HEADER: TEST_CONTROL_IDEMPOTENCY_KEY,
    }
    monkeypatch.setattr(api, "RUNTIME_CONFIGURATION", runtime)
    monkeypatch.setattr(api, "CONTROL_RUN_EVENTS_TOKEN", TEST_CONTROL_RUN_EVENTS_TOKEN)
    monkeypatch.setattr(api, "AUTHORITATIVE_LOG_DESCRIPTOR", None)
    monkeypatch.setattr(api, "AUTHORITATIVE_COMMAND_ACTIVE", False)

    with TestClient(api.app) as client:
        push_response = client.post(api.CONTROL_PUSH_PATH, content=body, headers=headers)
        first_pull = api.ControlPullResponse.model_validate_json(
            client.get(
                api.CONTROL_PULL_PATH,
                headers={
                    api.CONTROL_RUN_EVENTS_TOKEN_HEADER: TEST_CONTROL_RUN_EVENTS_TOKEN,
                },
            ).content
        )

    assert push_response.status_code == api.status.HTTP_200_OK
    assert api.ControlPushResponse.model_validate_json(push_response.content) == (
        api.ControlPushResponse(accepted=True, duplicate=False)
    )
    assert first_pull.events == (event,)
    records = tuple(
        HttpRequestLogRecord.model_validate_json(line)
        for line in replay_log_path.read_text(encoding=api.TEXT_ENCODING).splitlines()
    )
    assert len(records) == 1
    assert records[0].path == api.CONTROL_PUSH_PATH
    assert records[0].request_body == body.decode(api.TEXT_ENCODING)

    detour_db_path.unlink()
    with TestClient(api.app) as client:
        replayed_pull = api.ControlPullResponse.model_validate_json(
            client.get(
                api.CONTROL_PULL_PATH,
                headers={
                    api.CONTROL_RUN_EVENTS_TOKEN_HEADER: TEST_CONTROL_RUN_EVENTS_TOKEN,
                },
            ).content
        )

    assert replayed_pull == first_pull


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
    output_value["payload"]["output"].append({"type": "input_text", "text": TEST_EXCERPT})
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


def test_submission_contract_has_nine_evidence_fields_and_optional_comments() -> None:
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


def test_successful_initial_submission_converts_to_retry_model_with_placeholders() -> None:
    initial = api.Submission.model_validate(api.EVIDENCE_SUBMISSION_EXAMPLE)

    converted = api._standardized_initial_submission(initial)

    assert isinstance(converted, api.StandardizedSubmission)
    assert converted.normalized_values() == initial.normalized_values()
    assert converted.comments == initial.comments
    for (initial_column, initial_field), (converted_column, converted_field) in zip(
        initial.evidence_items(),
        converted.evidence_items(),
        strict=True,
    ):
        assert converted_column == initial_column
        assert converted_field.value == initial_field.value
        assert converted_field.web_search_excerpts == initial_field.web_search_excerpts
        assert (
            getattr(converted_field, FIELD_STANDARDIZED_VALUE_FIELD)
            == (api.INITIAL_STANDARDIZED_VALUES[initial_column])
        )


def test_openapi_example_is_a_complete_pydantic_valid_submission() -> None:
    assert isinstance(
        api.L_FEI_FEI_INITIAL_FIXTURE.submission,
        api.Submission,
    )
    assert (
        api.Submission.model_validate_json(json.dumps(api.EVIDENCE_SUBMISSION_EXAMPLE))
        == api.L_FEI_FEI_INITIAL_FIXTURE.submission
    )
    assert set(api.EVIDENCE_SUBMISSION_EXAMPLE) == set(api.AI_AUGMENT_COLUMNS)
    assert api.L_FEI_FEI_INITIAL_FIXTURE.identity == ("L.", "Fei-Fei")
    assert isinstance(
        api.L_FEI_FEI_RETRY_FIXTURE.submission,
        api.StandardizedSubmission,
    )
    assert api.RETRY_EVIDENCE_SUBMISSION_EXAMPLE == (
        api.L_FEI_FEI_RETRY_FIXTURE.submission.model_dump(by_alias=True, mode="json")
    )
    assert all(
        FIELD_STANDARDIZED_VALUE_FIELD not in field
        for column, field in api.EVIDENCE_SUBMISSION_EXAMPLE.items()
        if column in api.AI_AUGMENT_EVIDENCE_COLUMNS and isinstance(field, dict)
    )
    assert all(
        FIELD_STANDARDIZED_VALUE_FIELD in field
        for column, field in api.RETRY_EVIDENCE_SUBMISSION_EXAMPLE.items()
        if column in api.AI_AUGMENT_EVIDENCE_COLUMNS and isinstance(field, dict)
    )
    source = PYDANTIC_TO_PASTE_PATH.read_text(encoding="utf-8").rstrip()
    assert PYDANTIC_TO_PASTE_SOURCE == source
    assert source in api.RETRY_SUBMISSION_PUBLIC_GUIDANCE
    assert (
        json.dumps(
            api.RETRY_EVIDENCE_SUBMISSION_EXAMPLE,
            ensure_ascii=False,
            indent=2,
        )
        in api.RETRY_SUBMISSION_PUBLIC_GUIDANCE
    )
    assert "CurrentAge: TypeAlias" in source
    assert "YearOfBirth: TypeAlias" in source
    assert "DateOfBirth: TypeAlias" in source
    assert "YearOfFirstPublication: TypeAlias" in source
    assert "DateOfFirstPublication: TypeAlias" in source
    assert 'NotReported: TypeAlias = Literal["NR"]' in source
    assert 'NotAvailableOrApplicable: TypeAlias = Literal["NA"]' in source


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


@pytest.mark.parametrize(
    ("excerpt", "expected_outcome"),
    (
        (V2_EXACT_EXCERPT, api.EVIDENCE_OUTCOME_V1_EXACT),
        ("josé garcía — senior\nresearcher", api.EVIDENCE_OUTCOME_V2_NEAR),
        ("Jose Garcia — Senior\nResearcher", api.EVIDENCE_OUTCOME_V2_NEAR),
        ("José García Senior Researcher", api.EVIDENCE_OUTCOME_V2_NEAR),
        ("José   García\n\n—\tSenior   Researcher", api.EVIDENCE_OUTCOME_V2_NEAR),
    ),
    ids=("exact", "case", "accent", "punctuation", "whitespace"),
)
def test_codex_v2_classifies_normalized_variants_without_accepting_them(
    excerpt: str,
    expected_outcome: str,
) -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, V2_CITE_TEXT),)))
    try:
        assessment = api.assess_submission_evidence(
            connection,
            api.Submission.model_validate(submission_body_for_evidence(excerpt)),
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
    finally:
        connection.close()

    assert {item.outcome for item in assessment.items} == {expected_outcome}
    assert assessment.accepted is (expected_outcome == api.EVIDENCE_OUTCOME_V1_EXACT)
    assert sum(len(matches) for matches in assessment.validated.values()) == (
        len(api.AI_AUGMENT_EVIDENCE_COLUMNS)
        if expected_outcome == api.EVIDENCE_OUTCOME_V1_EXACT
        else 0
    )


@pytest.mark.parametrize(
    ("value", "expected_tokens"),
    (
        ("Иван Петров", ("иван", "петров")),
        ("ИВАН—ПЕТРОВ", ("иван", "петров")),
        ("张伟", ("张伟",)),
        ("张 伟", ("张", "伟")),
        ("张，伟", ("张", "伟")),
        ("أحمد حسن", ("احمد", "حسن")),
        ("Αλέξανδρος Παπαδόπουλος", ("αλεξανδρος", "παπαδοπουλος")),
    ),
    ids=(
        "cyrillic",
        "cyrillic-punctuation",
        "han-unseparated",
        "han-space",
        "han-fullwidth-punctuation",
        "arabic",
        "greek",
    ),
)
def test_codex_v2_normalizer_preserves_non_latin_scripts(
    value: str,
    expected_tokens: tuple[str, ...],
) -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, value),)))
    try:
        assert api._normalized_evidence_tokens(connection, value) == expected_tokens
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("cite_text", "excerpt", "expected_outcome"),
    (
        ("ИВАН—ПЕТРОВ", "иван петров", api.EVIDENCE_OUTCOME_V2_NEAR),
        ("张，伟", "张 伟", api.EVIDENCE_OUTCOME_V2_NEAR),
        ("张伟", "张 伟", api.EVIDENCE_OUTCOME_UNMATCHED),
        ("أحمد حسن", "احمد—حسن", api.EVIDENCE_OUTCOME_V2_NEAR),
        (
            "Αλέξανδρος Παπαδόπουλος",
            "αλεξανδρος παπαδοπουλος",
            api.EVIDENCE_OUTCOME_V2_NEAR,
        ),
    ),
    ids=(
        "cyrillic",
        "han-equivalent-boundaries",
        "han-different-boundaries",
        "arabic",
        "greek",
    ),
)
def test_codex_v2_matches_non_latin_token_sequences_conservatively(
    cite_text: str,
    excerpt: str,
    expected_outcome: str,
) -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, cite_text),)))
    try:
        assessment = api.assess_submission_evidence(
            connection,
            api.Submission.model_validate(submission_body_for_evidence(excerpt)),
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
    finally:
        connection.close()

    assert {item.outcome for item in assessment.items} == {expected_outcome}
    assert assessment.accepted is False


@pytest.mark.parametrize(
    "excerpt",
    (
        "Alpha Gamma Beta Delta",
        "Alpha Beta Delta",
        "Alpha Beta Extra Gamma Delta",
        "!!!",
    ),
    ids=("reordered", "missing", "added", "punctuation-only"),
)
def test_codex_v2_rejects_noncontiguous_or_empty_token_sequences(
    excerpt: str,
) -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, "Alpha Beta Gamma Delta"),)))
    try:
        assessment = api.assess_submission_evidence(
            connection,
            api.Submission.model_validate(submission_body_for_evidence(excerpt)),
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
    finally:
        connection.close()

    assert {item.outcome for item in assessment.items} == {api.EVIDENCE_OUTCOME_UNMATCHED}
    assert assessment.accepted is False


def test_codex_v2_cannot_join_tokens_across_citation_sections() -> None:
    connection = connect_v2_index(
        build_citation_index((
            (TEST_URL, "Alpha Beta"),
            (TEST_URL, "Gamma Delta"),
        ))
    )
    try:
        assessment = api.assess_submission_evidence(
            connection,
            api.Submission.model_validate(submission_body_for_evidence("Alpha Beta Gamma Delta")),
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
    finally:
        connection.close()

    assert {item.outcome for item in assessment.items} == {api.EVIDENCE_OUTCOME_UNMATCHED}


def test_codex_v2_requires_the_exact_candidate_url() -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, V2_CITE_TEXT),)))
    try:
        assessment = api.assess_submission_evidence(
            connection,
            api.Submission.model_validate(
                submission_body_for_evidence(
                    "Jose Garcia Senior Researcher",
                    url=f"{TEST_URL}/other",
                )
            ),
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
    finally:
        connection.close()

    assert {item.outcome for item in assessment.items} == {api.EVIDENCE_OUTCOME_UNMATCHED}


def test_empty_excerpt_is_rejected_before_codex_v2_matching() -> None:
    with pytest.raises(ValidationError):
        api.Submission.model_validate(submission_body_for_evidence(""))


def test_evidence_assessment_is_exhaustive_and_public_guidance_is_nonrevealing() -> None:
    body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    failed_field = api.AI_AUGMENT_EVIDENCE_COLUMNS[0]
    body[failed_field]["web_search_excerpts"][0]["excerpt"] = (  # type: ignore[index]
        "Jose Garcia Senior Researcher"
    )
    connection = connect_v2_index(build_citation_index(((TEST_URL, V2_CITE_TEXT),)))
    try:
        assessment = api.assess_submission_evidence(
            connection,
            api.Submission.model_validate(body),
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        detail = api._assessment_public_detail(assessment)
    finally:
        connection.close()

    assert len(assessment.items) == len(api.AI_AUGMENT_EVIDENCE_COLUMNS)
    assert assessment.exact_count == len(api.AI_AUGMENT_EVIDENCE_COLUMNS) - 1
    assert assessment.items[0].outcome == api.EVIDENCE_OUTCOME_V2_NEAR
    assert assessment.items[-1].outcome == api.EVIDENCE_OUTCOME_V1_EXACT
    assert assessment.accepted is False
    assert f"{failed_field}.web_search_excerpts[0]" in detail
    assert TEST_CALL_ID not in detail
    assert TEST_REF_ID not in detail
    assert V2_CITE_TEXT not in detail


def test_v2_retry_baseline_replays_and_accepts_only_the_exact_correction() -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, V2_CITE_TEXT),)))
    near_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    near_body[api.AI_AUGMENT_EVIDENCE_COLUMNS[0]][  # type: ignore[index]
        "web_search_excerpts"
    ][0]["excerpt"] = "Jose Garcia Senior Researcher"
    near_submission = api.Submission.model_validate(near_body)
    exact_submission = api.StandardizedSubmission.model_validate(
        standardized_submission_body(submission_body_for_evidence(V2_EXACT_EXCERPT))
    )
    try:
        near_assessment = api.assess_submission_evidence(
            connection,
            near_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert near_assessment.accepted is False
        assert (
            api._process_retry_attempt(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-near",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission=near_submission,
                assessment=near_assessment,
            )
            == ()
        )

        exact_assessment = api.assess_submission_evidence(
            connection,
            exact_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert exact_assessment.accepted is True
        assert (
            api._process_retry_attempt(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-exact",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission=exact_submission,
                assessment=exact_assessment,
            )
            == ()
        )

        baseline_count = connection.execute(
            f"SELECT count(*) FROM {api.CODEX_RETRY_BASELINE_TABLE}"
        ).fetchone()
        audit_rows = connection.execute(
            f"""
            SELECT
                {api.CODEX_EVIDENCE_APPLIED_COL},
                {api.CODEX_EVIDENCE_ACCEPTED_COL}
            FROM {api.CODEX_EVIDENCE_AUDIT_TABLE}
            ORDER BY {api.CODEX_EVIDENCE_AUDIT_ID_COL}
            """
        ).fetchall()
    finally:
        connection.close()

    assert baseline_count == (1,)
    assert audit_rows == [(True, False), (True, True)]


def test_v2_retry_rejects_changed_tokens_and_repeats_near_guidance() -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, V2_CITE_TEXT),)))
    near_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    failed_field = api.AI_AUGMENT_EVIDENCE_COLUMNS[0]
    near_body[failed_field]["web_search_excerpts"][0]["excerpt"] = (  # type: ignore[index]
        "Jose Garcia Senior Researcher"
    )
    changed_body = json.loads(json.dumps(near_body))
    changed_body[failed_field]["web_search_excerpts"][0]["excerpt"] = "Jose Garcia Lead Researcher"
    try:
        near_submission = api.Submission.model_validate(near_body)
        near_assessment = api.assess_submission_evidence(
            connection,
            near_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert (
            api._process_retry_attempt(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-near",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission=near_submission,
                assessment=near_assessment,
            )
            == ()
        )

        changed_submission = api.StandardizedSubmission.model_validate(
            standardized_submission_body(changed_body)
        )
        changed_assessment = api.assess_submission_evidence(
            connection,
            changed_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        changed_violations = api._process_retry_attempt(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-changed",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission=changed_submission,
            assessment=changed_assessment,
        )
        near_retry_submission = api.StandardizedSubmission.model_validate(
            standardized_submission_body(near_body)
        )
        repeated_violations = api._process_retry_attempt(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-near-again",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission=near_retry_submission,
            assessment=near_assessment,
        )
        applied_rows = connection.execute(
            f"""
            SELECT {api.CODEX_EVIDENCE_APPLIED_COL}
            FROM {api.CODEX_EVIDENCE_AUDIT_TABLE}
            ORDER BY {api.CODEX_EVIDENCE_AUDIT_ID_COL}
            """
        ).fetchall()
    finally:
        connection.close()

    location = f"{failed_field}.web_search_excerpts[0]"
    assert changed_assessment.items[0].outcome == api.EVIDENCE_OUTCOME_UNMATCHED
    assert changed_violations == (
        Locale.EVIDENCE_MINOR_CHANGE_ONLY_TEMPLATE.format(location=location),
    )
    assert repeated_violations == ()
    assert near_assessment.accepted is False
    assert applied_rows == [(True,), (False,), (True,)]


def test_retry_preserves_exact_items_inside_a_rejected_field() -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, V2_CITE_TEXT),)))
    field = api.AI_AUGMENT_EVIDENCE_COLUMNS[0]
    baseline_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    baseline_body[field]["web_search_excerpts"] = [  # type: ignore[index]
        {"excerpt": "José García", "url": TEST_URL},
        {"excerpt": "Jose Garcia Senior Researcher", "url": TEST_URL},
    ]
    changed_body = json.loads(json.dumps(baseline_body))
    changed_body[field]["web_search_excerpts"][0]["excerpt"] = "García"
    try:
        baseline_submission = api.Submission.model_validate(baseline_body)
        baseline_assessment = api.assess_submission_evidence(
            connection,
            baseline_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert (
            api._process_retry_attempt(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-baseline",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission=baseline_submission,
                assessment=baseline_assessment,
            )
            == ()
        )

        changed_submission = api.StandardizedSubmission.model_validate(
            standardized_submission_body(changed_body)
        )
        changed_assessment = api.assess_submission_evidence(
            connection,
            changed_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        violations = api._process_retry_attempt(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-changed",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission=changed_submission,
            assessment=changed_assessment,
        )
    finally:
        connection.close()

    assert violations == (
        Locale.EVIDENCE_EXACT_IMMUTABLE_TEMPLATE.format(
            immutable=f"{field}.web_search_excerpts[0]"
        ),
    )


def test_retry_preserves_fully_verified_fields_and_complete_evidence_counts() -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, V2_CITE_TEXT),)))
    failed_field = api.AI_AUGMENT_EVIDENCE_COLUMNS[0]
    accepted_field = api.AI_AUGMENT_EVIDENCE_COLUMNS[1]
    baseline_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    baseline_body[failed_field]["web_search_excerpts"] = [  # type: ignore[index]
        {"excerpt": "José García", "url": TEST_URL},
        {"excerpt": "Jose Garcia Senior Researcher", "url": TEST_URL},
    ]
    changed_body = json.loads(json.dumps(baseline_body))
    changed_body[accepted_field]["value"] = "changed"
    changed_body[failed_field]["web_search_excerpts"].pop(0)
    try:
        baseline_submission = api.Submission.model_validate(baseline_body)
        baseline_assessment = api.assess_submission_evidence(
            connection,
            baseline_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert (
            api._process_retry_attempt(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-baseline",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission=baseline_submission,
                assessment=baseline_assessment,
            )
            == ()
        )

        changed_submission = api.StandardizedSubmission.model_validate(
            standardized_submission_body(changed_body)
        )
        changed_assessment = api.assess_submission_evidence(
            connection,
            changed_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        violations = api._process_retry_attempt(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-changed",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission=changed_submission,
            assessment=changed_assessment,
        )
    finally:
        connection.close()

    assert Locale.EVIDENCE_COUNT_DECREASED_TEMPLATE.format(field=failed_field) in violations
    assert (
        Locale.EVIDENCE_ACCEPTED_FIELD_IMMUTABLE_TEMPLATE.format(immutable=accepted_field)
        in violations
    )


@pytest.mark.parametrize(
    ("replacement", "changed_value", "expected_outcome"),
    (
        (
            {"excerpt": "Profile:", "url": TEST_URL},
            False,
            api.EVIDENCE_OUTCOME_V1_EXACT,
        ),
        (
            {
                EVIDENCE_WITHDRAWAL_ACTION_FIELD: EVIDENCE_WITHDRAWAL_ACTION,
                EVIDENCE_WITHDRAWAL_REASON_FIELD: EVIDENCE_WITHDRAWAL_REASON,
                EVIDENCE_WITHDRAWAL_ATTESTED_FIELD: True,
            },
            True,
            api.EVIDENCE_OUTCOME_WITHDRAWN,
        ),
    ),
    ids=("replace", "withdraw"),
)
def test_unmatched_evidence_can_be_replaced_or_explicitly_withdrawn(
    replacement: dict[str, object],
    changed_value: bool,
    expected_outcome: str,
) -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, V2_CITE_TEXT),)))
    field = api.AI_AUGMENT_EVIDENCE_COLUMNS[0]
    baseline_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    baseline_body[field]["web_search_excerpts"] = [  # type: ignore[index]
        {"excerpt": V2_EXACT_EXCERPT, "url": TEST_URL},
        {"excerpt": "Invented evidence", "url": TEST_URL},
    ]
    retry_body = json.loads(json.dumps(baseline_body))
    retry_body[field]["web_search_excerpts"][1] = replacement
    if changed_value:
        retry_body[field]["value"] = "corrected value"
    try:
        baseline_submission = api.Submission.model_validate(baseline_body)
        baseline_assessment = api.assess_submission_evidence(
            connection,
            baseline_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert (
            api._process_retry_attempt(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-baseline",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission=baseline_submission,
                assessment=baseline_assessment,
            )
            == ()
        )

        retry_submission = api.StandardizedSubmission.model_validate(
            standardized_submission_body(retry_body)
        )
        retry_assessment = api.assess_submission_evidence(
            connection,
            retry_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        violations = api._process_retry_attempt(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-retry",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission=retry_submission,
            assessment=retry_assessment,
        )
    finally:
        connection.close()

    field_items = tuple(item for item in retry_assessment.items if item.field == field)
    assert field_items[1].outcome == expected_outcome
    assert retry_assessment.accepted is True
    assert violations == ()


def test_v2_near_evidence_cannot_be_withdrawn() -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, V2_CITE_TEXT),)))
    field = api.AI_AUGMENT_EVIDENCE_COLUMNS[0]
    baseline_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    baseline_body[field]["web_search_excerpts"][0]["excerpt"] = (  # type: ignore[index]
        "Jose Garcia Senior Researcher"
    )
    withdrawal_body = json.loads(json.dumps(baseline_body))
    withdrawal_body[field]["value"] = "corrected value"
    withdrawal_body[field]["web_search_excerpts"][0] = {
        EVIDENCE_WITHDRAWAL_ACTION_FIELD: EVIDENCE_WITHDRAWAL_ACTION,
        EVIDENCE_WITHDRAWAL_REASON_FIELD: EVIDENCE_WITHDRAWAL_REASON,
        EVIDENCE_WITHDRAWAL_ATTESTED_FIELD: True,
    }
    try:
        baseline_submission = api.Submission.model_validate(baseline_body)
        baseline_assessment = api.assess_submission_evidence(
            connection,
            baseline_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert (
            api._process_retry_attempt(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-baseline",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission=baseline_submission,
                assessment=baseline_assessment,
            )
            == ()
        )

        withdrawal_submission = api.StandardizedSubmission.model_validate(
            standardized_submission_body(withdrawal_body)
        )
        withdrawal_assessment = api.assess_submission_evidence(
            connection,
            withdrawal_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        violations = api._process_retry_attempt(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-withdrawal",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission=withdrawal_submission,
            assessment=withdrawal_assessment,
        )
    finally:
        connection.close()

    assert violations == (
        Locale.EVIDENCE_WITHDRAWAL_NOT_ALLOWED_TEMPLATE.format(
            location=f"{field}.web_search_excerpts[0]"
        ),
    )


def test_retry_baselines_survive_restart_and_remain_isolated_by_run(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "retry.duckdb"
    index = build_citation_index(((TEST_URL, V2_CITE_TEXT),))
    near_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    near_body[api.AI_AUGMENT_EVIDENCE_COLUMNS[0]][  # type: ignore[index]
        "web_search_excerpts"
    ][0]["excerpt"] = "Jose Garcia Senior Researcher"
    unmatched_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    unmatched_body[api.AI_AUGMENT_EVIDENCE_COLUMNS[0]][  # type: ignore[index]
        "web_search_excerpts"
    ][0]["excerpt"] = "Invented evidence"

    first_connection = connect_v2_index(index, database_path=database_path)
    try:
        for run_id, attempt_id, body in (
            (TEST_RUN_ID, "run-one-baseline", near_body),
            (TEST_SECOND_RUN_ID, "run-two-baseline", unmatched_body),
        ):
            submission = api.Submission.model_validate(body)
            assessment = api.assess_submission_evidence(
                first_connection,
                submission,
                rollout_filename=TEST_ROLLOUT_FILENAME,
                codex_match_version=2,
            )
            assert (
                api._process_retry_attempt(
                    first_connection,
                    run_id=run_id,
                    namekey=TEST_NAMEKEY,
                    session_id=TEST_SESSION_ID,
                    attempt_id=attempt_id,
                    attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                    submission=submission,
                    assessment=assessment,
                )
                == ()
            )
    finally:
        first_connection.close()

    second_connection = connect_v2_index(index, database_path=database_path)
    try:
        exact_submission = api.StandardizedSubmission.model_validate(
            standardized_submission_body(submission_body_for_evidence(V2_EXACT_EXCERPT))
        )
        exact_assessment = api.assess_submission_evidence(
            second_connection,
            exact_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        for run_id, attempt_id in (
            (TEST_RUN_ID, "run-one-exact"),
            (TEST_SECOND_RUN_ID, "run-two-exact"),
        ):
            assert (
                api._process_retry_attempt(
                    second_connection,
                    run_id=run_id,
                    namekey=TEST_NAMEKEY,
                    session_id=TEST_SESSION_ID,
                    attempt_id=attempt_id,
                    attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                    submission=exact_submission,
                    assessment=exact_assessment,
                )
                == ()
            )
        baseline_rows = second_connection.execute(
            f"""
            SELECT {api.CODEX_RETRY_RUN_ID_COL}
            FROM {api.CODEX_RETRY_BASELINE_TABLE}
            ORDER BY {api.CODEX_RETRY_RUN_ID_COL}
            """
        ).fetchall()
        accepted_rows = second_connection.execute(
            f"""
            SELECT count(*)
            FROM {api.CODEX_EVIDENCE_AUDIT_TABLE}
            WHERE {api.CODEX_EVIDENCE_ACCEPTED_COL}
            """
        ).fetchone()
    finally:
        second_connection.close()

    assert baseline_rows == sorted([(str(TEST_RUN_ID),), (str(TEST_SECOND_RUN_ID),)])
    assert accepted_rows == (2,)


def test_concurrent_first_rejections_cannot_replace_the_baseline(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "concurrent.duckdb"
    index = build_citation_index(((TEST_URL, V2_CITE_TEXT),))
    setup_connection = connect_v2_index(index, database_path=database_path)
    setup_connection.close()
    barrier = Barrier(2)

    def submit(attempt_id: str, excerpt: str) -> None:
        connection = duckdb.connect(str(database_path))
        load_duckdb_extension_from_config_path(
            connection,
            api.CODEX_TOKEN_EXTENSION,
            CONFIG_PATH,
            log=None,
        )
        try:
            plain_body = submission_body_for_evidence(excerpt)
            barrier.wait()
            with api.DETOUR_DB_LOCK:
                retry_expected = api._retry_baseline_exists(
                    connection,
                    run_id=TEST_RUN_ID,
                    namekey=TEST_NAMEKEY,
                    session_id=TEST_SESSION_ID,
                )
                submission: api.SubmissionPayload = (
                    api.StandardizedSubmission.model_validate(
                        standardized_submission_body(plain_body)
                    )
                    if retry_expected
                    else api.Submission.model_validate(plain_body)
                )
                assessment = api.assess_submission_evidence(
                    connection,
                    submission,
                    rollout_filename=TEST_ROLLOUT_FILENAME,
                    codex_match_version=2,
                )
                assert (
                    api._process_retry_attempt(
                        connection,
                        run_id=TEST_RUN_ID,
                        namekey=TEST_NAMEKEY,
                        session_id=TEST_SESSION_ID,
                        attempt_id=attempt_id,
                        attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                        submission=submission,
                        assessment=assessment,
                    )
                    == ()
                )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(
                submit,
                "concurrent-lower",
                "Jose Garcia Senior Researcher",
            ),
            executor.submit(
                submit,
                "concurrent-upper",
                "JOSE GARCIA SENIOR RESEARCHER",
            ),
        )
        for future in futures:
            future.result()

    verification_connection = duckdb.connect(str(database_path))
    try:
        baseline_attempt = verification_connection.execute(
            f"""
            SELECT {api.CODEX_RETRY_ATTEMPT_ID_COL}
            FROM {api.CODEX_RETRY_BASELINE_TABLE}
            """
        ).fetchone()
        audit_attempts = verification_connection.execute(
            f"""
            SELECT {api.CODEX_RETRY_ATTEMPT_ID_COL}
            FROM {api.CODEX_EVIDENCE_AUDIT_TABLE}
            ORDER BY {api.CODEX_EVIDENCE_AUDIT_ID_COL}
            """
        ).fetchall()
    finally:
        verification_connection.close()

    assert len(audit_attempts) == 2
    assert baseline_attempt == audit_attempts[0]


def test_corrupt_applied_audit_fails_as_configuration_error() -> None:
    connection = connect_v2_index(build_citation_index(((TEST_URL, V2_CITE_TEXT),)))
    body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    body[api.AI_AUGMENT_EVIDENCE_COLUMNS[0]][  # type: ignore[index]
        "web_search_excerpts"
    ][0]["excerpt"] = "Jose Garcia Senior Researcher"
    submission = api.Submission.model_validate(body)
    try:
        api.assess_submission_evidence(
            connection,
            submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        retry_submission = api.StandardizedSubmission.model_validate(
            standardized_submission_body(body)
        )
        for attempt_id, attempted_submission in (
            ("audit-baseline", submission),
            ("audit-second", retry_submission),
        ):
            attempted_assessment = api.assess_submission_evidence(
                connection,
                attempted_submission,
                rollout_filename=TEST_ROLLOUT_FILENAME,
                codex_match_version=2,
            )
            assert (
                api._process_retry_attempt(
                    connection,
                    run_id=TEST_RUN_ID,
                    namekey=TEST_NAMEKEY,
                    session_id=TEST_SESSION_ID,
                    attempt_id=attempt_id,
                    attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                    submission=attempted_submission,
                    assessment=attempted_assessment,
                )
                == ()
            )
        connection.execute(
            f"""
            UPDATE {api.CODEX_EVIDENCE_AUDIT_TABLE}
            SET {api.CODEX_EVIDENCE_ASSESSMENT_COL} = ?
            WHERE {api.CODEX_RETRY_ATTEMPT_ID_COL} = ?
            """,
            ["{}", "audit-second"],
        )

        with pytest.raises(
            api.PushConfigurationError,
            match=Locale.EVIDENCE_AUDIT_REPLAY_FAILED,
        ):
            api._process_retry_attempt(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY,
                session_id=TEST_SESSION_ID,
                attempt_id="audit-third",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission=retry_submission,
                assessment=attempted_assessment,
            )
    finally:
        connection.close()


def test_historical_haanen_retry_preserves_verified_evidence_roundtrip() -> None:
    original_body_value, archived_retry_body_value = historical_haanen_submissions()
    original_body = cast(dict[str, Any], original_body_value)
    archived_retry_body = cast(dict[str, Any], archived_retry_body_value)
    rollout_index = api.build_rollout_index(
        api.parse_rollout(HAANEN_ACCEPTED_ROLLOUT_PATH),
        timezone_name=TEST_TIMEZONE,
        configured_rollout_basename=HAANEN_ROLLOUT_FILENAME,
    )
    connection = connect_v2_index(rollout_index)
    try:
        original_submission = api.Submission.model_validate(original_body)
        original_assessment = api.assess_submission_evidence(
            connection,
            original_submission,
            rollout_filename=HAANEN_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        original_archived_items = tuple(
            item
            for item in original_assessment.items
            if item.field in HAANEN_ARCHIVED_EVIDENCE_COLUMNS
        )
        assert len(original_archived_items) == HAANEN_ORIGINAL_EVIDENCE_COUNT
        assert sum(
            item.outcome == api.EVIDENCE_OUTCOME_V1_EXACT for item in original_archived_items
        ) == (HAANEN_ORIGINAL_EVIDENCE_COUNT - 1)
        near_items = tuple(
            item
            for item in original_assessment.items
            if item.outcome == api.EVIDENCE_OUTCOME_V2_NEAR
        )
        assert tuple((item.field, item.index) for item in near_items) == (
            (api.KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL, 1),
        )
        assert (
            api._process_retry_attempt(
                connection,
                run_id=HAANEN_RUN_ID,
                namekey=HAANEN_NAMEKEY,
                session_id=HAANEN_SESSION_ID,
                attempt_id=HAANEN_REJECTED_ATTEMPT_ID,
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission=original_submission,
                assessment=original_assessment,
            )
            == ()
        )

        archived_retry = api.StandardizedSubmission.model_validate(archived_retry_body)
        archived_retry_assessment = api.assess_submission_evidence(
            connection,
            archived_retry,
            rollout_filename=HAANEN_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert (
            len(
                tuple(
                    item
                    for item in archived_retry_assessment.items
                    if item.field in HAANEN_ARCHIVED_EVIDENCE_COLUMNS
                )
            )
            == HAANEN_RETRY_EVIDENCE_COUNT
        )
        archived_retry_violations = api._process_retry_attempt(
            connection,
            run_id=HAANEN_RUN_ID,
            namekey=HAANEN_NAMEKEY,
            session_id=HAANEN_SESSION_ID,
            attempt_id=HAANEN_ACCEPTED_ATTEMPT_ID,
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission=archived_retry,
            assessment=archived_retry_assessment,
        )
        assert archived_retry_violations
        assert (
            Locale.EVIDENCE_COUNT_DECREASED_TEMPLATE.format(
                field=api.KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL
            )
            in archived_retry_violations
        )
        assert (
            Locale.EVIDENCE_ACCEPTED_FIELD_IMMUTABLE_TEMPLATE.format(
                immutable=api.KTP_AI_AUGMENT_GENDER_COL
            )
            in archived_retry_violations
        )
        assert (
            original_body[api.KTP_AI_AUGMENT_GENDER_COL][FIELD_EVIDENCE_FIELD][0][
                EVIDENCE_EXCERPT_FIELD
            ]
            == HAANEN_ORIGINAL_GENDER_EXCERPT
        )
        assert (
            archived_retry_body[api.KTP_AI_AUGMENT_GENDER_COL][FIELD_EVIDENCE_FIELD][0][
                EVIDENCE_EXCERPT_FIELD
            ]
            == HAANEN_RETRY_GENDER_EXCERPT
        )

        ideal_retry_body = json.loads(json.dumps(original_body, ensure_ascii=False))
        ideal_retry_body[api.KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL][FIELD_EVIDENCE_FIELD][1][
            EVIDENCE_EXCERPT_FIELD
        ] = HAANEN_CORRECTED_NEAR_EXCERPT
        changed_items = tuple(
            (field, index)
            for field in HAANEN_ARCHIVED_EVIDENCE_COLUMNS
            for index, (original, corrected) in enumerate(
                zip(
                    original_body[field][FIELD_EVIDENCE_FIELD],
                    ideal_retry_body[field][FIELD_EVIDENCE_FIELD],
                    strict=True,
                )
            )
            if original != corrected
        )
        assert changed_items == ((api.KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL, 1),)

        ideal_retry = api.StandardizedSubmission.model_validate(
            standardized_submission_body(ideal_retry_body)
        )
        ideal_assessment = api.assess_submission_evidence(
            connection,
            ideal_retry,
            rollout_filename=HAANEN_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        ideal_archived_items = tuple(
            item
            for item in ideal_assessment.items
            if item.field in HAANEN_ARCHIVED_EVIDENCE_COLUMNS
        )
        assert len(ideal_archived_items) == HAANEN_ORIGINAL_EVIDENCE_COUNT
        assert all(item.outcome == api.EVIDENCE_OUTCOME_V1_EXACT for item in ideal_archived_items)
        assert ideal_assessment.accepted is True
        assert (
            api._process_retry_attempt(
                connection,
                run_id=HAANEN_RUN_ID,
                namekey=HAANEN_NAMEKEY,
                session_id=HAANEN_SESSION_ID,
                attempt_id=f"{HAANEN_ACCEPTED_ATTEMPT_ID}-ideal",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission=ideal_retry,
                assessment=ideal_assessment,
            )
            == ()
        )

        audit_rows = connection.execute(
            f"""
            SELECT
                {api.CODEX_RETRY_ATTEMPT_ID_COL},
                {api.CODEX_EVIDENCE_APPLIED_COL},
                {api.CODEX_EVIDENCE_ACCEPTED_COL}
            FROM {api.CODEX_EVIDENCE_AUDIT_TABLE}
            ORDER BY {api.CODEX_EVIDENCE_AUDIT_ID_COL}
            """
        ).fetchall()
    finally:
        connection.close()

    assert audit_rows == [
        (HAANEN_REJECTED_ATTEMPT_ID, True, False),
        (HAANEN_ACCEPTED_ATTEMPT_ID, False, False),
        (f"{HAANEN_ACCEPTED_ATTEMPT_ID}-ideal", True, True),
    ]


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
        assert TEST_EXCERPT in Locale.MULTIPLE_MATCH_DETAIL_TEMPLATE.format(
            excerpt=raised.value.excerpt
        )
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
            selections.append(
                tuple(
                    (match.field, match.evidence_number, match.ref_id, match.call_id)
                    for field_matches in validated.values()
                    for match in field_matches
                )
            )
        finally:
            connection.close()

    assert selections[0] == selections[1]
    assert len(selections[0]) == len(api.AI_AUGMENT_EVIDENCE_COLUMNS)
    assert {(ref_id, call_id) for _field, _number, ref_id, call_id in selections[0]}.issubset({
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
    ) == (f"1. {DISPLAY_ARGUMENTS_TURN_6}")
    assert codex_parse.render_footnote_argument(
        1,
        CALL_ARGUMENTS_TURN_7,
        {"turn6view0": COMPANY_URL},
        ref_id_pattern=api.CODEX_REF_ID_PATTERN,
    ) == (f"1. {DISPLAY_ARGUMENTS_TURN_7}")
    multi_open = (
        '{"open":[{"ref_id":"turn1search0"},{"ref_id":"turn1search1"}],"response_length":"long"}'
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
    direct_url_open = f'{{"open":[{{"ref_id":"{COMPANY_URL}"}}],"response_length":"long"}}'
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
    ) == (f"1. {CALL_ARGUMENTS_TURN_2}")


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
    runtime = runtime_for_test(tmp_path)
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: object) -> None:
        captured["command"] = command
        captured["kwargs"] = kwargs
        write_bytes(Path(command[-1]), b"first\nsecond")

    monkeypatch.setattr(api.subprocess, "run", fake_run)
    archived = api.copy_rollout_to_cas(configuration, runtime)

    command = captured["command"]
    assert command[0] == "scp"
    assert f"IdentityFile={identity_path}" in command
    assert f"UserKnownHostsFile={known_hosts_path}" in command
    assert f"HostKeyAlias={configuration.host_key_alias}" in command
    assert "StrictHostKeyChecking=accept-new" in command
    assert command[-2] == f"aivm-ai:{TEST_ROLLOUT_GUEST_PATH}"
    assert "shell" not in captured["kwargs"]
    assert archived.line_count == 2
    assert archived.path == runtime.rollout_cas_dir / api.ROLLOUT_CAS_FILENAME_TEMPLATE.format(
        sha256=archived.sha256
    )


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
                api.KTP_NAMEKEY_COL: TEST_NAMEKEY,
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
    accepted_submission = api._standardized_initial_submission(
        api.Submission.model_validate(context.payload)
    )
    accepted_fields = dict(accepted_submission.evidence_items())
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
            count_row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
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
        for plain_column, standardized_column in api.AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS:
            assert output_columns.index(standardized_column) == (
                output_columns.index(plain_column) + 1
            )
            assert (
                json.loads(output[standardized_column])
                == (
                    accepted_fields[plain_column].model_dump(mode="json")[
                        FIELD_STANDARDIZED_VALUE_FIELD
                    ]
                )
            )
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
        assert name_key == TEST_NAMEKEY
        innerdicts = tuple(json.loads(line) for line in innerdicts_text.splitlines())
        assert len(innerdicts) == 1
        assert tuple(innerdicts[0]) == tuple(
            column for column in output_columns if column != api.KTP_NAMEKEY_COL
        )
        assert innerdicts[0][api.KTP_FILENAME_COL] == JULY_ROLLOUT_FILENAME
        assert innerdicts[0][api.KTP_FRAGMENT_COL] == JULY_ROLLOUT_LINE_COUNT
        assert innerdicts[0][api.KTP_AI_AUGMENT_ATTEMPT_ID_COL] == manifest["attempt_id"]
    finally:
        connection.close()

    card_path = context.runtime.pipeline.output_dir / manifest["artifacts"]["card_zip"]["filename"]
    card_text = "\n".join(context.rendered_cards)
    assert f"#### {api.KTP_FILENAME_COL}: {JULY_ROLLOUT_FILENAME}" in card_text
    assert f"**{api.KTP_FRAGMENT_COL}**: {JULY_ROLLOUT_LINE_COUNT}" in card_text
    assert (
        f"{MARKDOWN_LITERAL_FIELD_TEMPLATE.format(field=api.KTP_AI_AUGMENT_ATTEMPT_ID_COL)}: "
        f"{manifest['attempt_id']}"
    ) in card_text
    assert (
        f"{MARKDOWN_LITERAL_FIELD_TEMPLATE.format(field=api.KTP_AI_AUGMENT_FOOTNOTES_COL)}:"
        in card_text
    )
    assert (
        f"{MARKDOWN_LITERAL_FIELD_TEMPLATE.format(field=api.KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL)}:"
        in card_text
    )
    assert (
        card_text.index(
            f"{MARKDOWN_LITERAL_FIELD_TEMPLATE.format(field=api.KTP_AI_AUGMENT_LINKS_COL)}:"
        )
        < card_text.index(
            f"{MARKDOWN_LITERAL_FIELD_TEMPLATE.format(field=api.KTP_AI_AUGMENT_COMMENTS_COL)}:"
        )
        < card_text.index(
            f"{MARKDOWN_LITERAL_FIELD_TEMPLATE.format(field=api.KTP_AI_AUGMENT_FOOTNOTES_COL)}:"
        )
    )
    assert "using arguments^1^" in card_text
    assert "<details>" not in card_text
    for plain_column, standardized_column in api.AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS:
        standardized_value = json.loads(output[standardized_column])
        standardized_label = MARKDOWN_LITERAL_FIELD_TEMPLATE.format(field=standardized_column)
        if standardized_value == api.NOT_REPORTED_VALUE:
            assert standardized_label not in card_text
            continue
        plain_label = MARKDOWN_LITERAL_FIELD_TEMPLATE.format(field=plain_column)
        expected_pair = (
            f"{plain_label}: {output[plain_column]}\n\n"
            f"{standardized_label}: {output[standardized_column]}\n\n"
        )
        assert expected_pair in card_text
        assert "^" not in f"{standardized_label}: {output[standardized_column]}"
    if output_format == "txt":
        assert read_zip_text(card_path) == card_text
    else:
        assert all(name.endswith(".docx") for name in zip_member_names(card_path))


def test_archived_attempts_rebuild_database_from_exact_http_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = prepare_real_sample_push(tmp_path, monkeypatch)
    attempts_dir = context.attempts_dir
    detour_db_path = context.runtime.detour_db_path
    output_dir = context.runtime.pipeline.output_dir
    runtime = api.RuntimeConfiguration(
        pipeline=context.runtime.pipeline,
        detour_db_path=detour_db_path,
        eligible_cohorts={TEST_NAMEKEY: api.GROUND_TRUTH_COHORT},
    )
    snapshot = api.SanctionSnapshot(
        run_id=TEST_RUN_ID,
        source_key=TEST_NAMEKEY,
        session_id=JULY_SESSION_ID,
        rollout_guest_path=JULY_ROLLOUT_GUEST_PATH,
        control_base_url=None,
    )
    rejected_payload = deepcopy(context.payload)
    rejected_evidence = rejected_payload[EXPECTED_EVIDENCE[0].column][FIELD_EVIDENCE_FIELD][0]
    rejected_evidence[EVIDENCE_EXCERPT_FIELD] += "X"
    accepted_payload = standardized_submission_body(context.payload)
    rejected_body = json.dumps(
        rejected_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    accepted_body = json.dumps(
        accepted_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    old_attempt_dir = attempts_dir / HAANEN_REJECTED_ATTEMPT_ID
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    monkeypatch.setattr(api, "sanctioned_snapshot", lambda: snapshot)

    rejected_response = context.client.post(
        api.PUSH_PATH,
        content=rejected_body,
        headers={api.HTTP_CONTENT_TYPE_HEADER: api.JSON_MEDIA_TYPE},
    )
    accepted_response = context.client.post(
        api.PUSH_PATH,
        content=accepted_body,
        headers={api.HTTP_CONTENT_TYPE_HEADER: api.JSON_MEDIA_TYPE},
    )
    attempt_dirs = tuple(sorted(attempts_dir.iterdir(), key=lambda path: path.name))
    rejected_attempt_dir, accepted_attempt_dir = attempt_dirs
    rejected_manifest = read_json(rejected_attempt_dir / api.ATTEMPT_MANIFEST_FILENAME)
    accepted_manifest = read_json(accepted_attempt_dir / api.ATTEMPT_MANIFEST_FILENAME)
    rejected_http_path = (
        rejected_attempt_dir
        / rejected_manifest[api.ATTEMPT_ARTIFACTS_KEY][api.ARTIFACT_HTTP_REQUEST_LOG_KEY][
            api.ARTIFACT_FILENAME_KEY
        ]
    )
    accepted_http_path = (
        accepted_attempt_dir
        / accepted_manifest[api.ATTEMPT_ARTIFACTS_KEY][api.ARTIFACT_HTTP_REQUEST_LOG_KEY][
            api.ARTIFACT_FILENAME_KEY
        ]
    )
    rejected_http = api.HttpRequestLogRecord.model_validate_json(read_text(rejected_http_path))
    accepted_http = api.HttpRequestLogRecord.model_validate_json(read_text(accepted_http_path))

    assert rejected_response.status_code == 422
    assert accepted_response.status_code == 200
    assert rejected_http.schema_version == api.KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V2
    assert accepted_http.schema_version == api.KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V2
    assert rejected_http.port is None
    assert accepted_http.port is None
    assert rejected_http.coerce_schema_v1 is False
    assert accepted_http.coerce_schema_v1 is False
    assert HTTP_REQUEST_LOG_PORT_KEY in json.loads(read_text(rejected_http_path))
    assert HTTP_REQUEST_LOG_PORT_KEY in json.loads(read_text(accepted_http_path))
    assert HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY in json.loads(
        read_text(rejected_http_path)
    )
    assert HTTP_REQUEST_LOG_COERCE_SCHEMA_V1_KEY in json.loads(
        read_text(accepted_http_path)
    )
    assert rejected_http.request_body == rejected_body
    assert rejected_http.response_code == rejected_response.status_code
    assert rejected_http.response_body == rejected_response.text
    assert accepted_http.request_body == accepted_body
    assert accepted_http.response_code == accepted_response.status_code
    assert accepted_http.response_body == accepted_response.text
    assert rejected_manifest[api.ATTEMPT_RUN_ID_KEY] == str(TEST_RUN_ID)
    assert accepted_manifest[api.ATTEMPT_SOURCE_KEY] == TEST_NAMEKEY
    assert accepted_manifest[api.ATTEMPT_SESSION_ID_KEY] == JULY_SESSION_ID
    assert accepted_manifest[api.ATTEMPT_ROLLOUT_RELATIVE_PATH_KEY] == str(
        JULY_ROLLOUT_RELATIVE_PATH
    )

    before = logical_database_snapshot(detour_db_path)
    accepted_card_path = (
        output_dir
        / accepted_manifest[api.ATTEMPT_ARTIFACTS_KEY][api.ARTIFACT_CARD_ZIP_KEY][
            api.ARTIFACT_FILENAME_KEY
        ]
    )
    accepted_response_path = accepted_attempt_dir / api.RESPONSE_FILENAME
    accepted_card_path.unlink()
    accepted_response_path.unlink()
    detour_db_path.unlink()
    old_attempt_dir.mkdir()
    write_text(
        old_attempt_dir / api.ATTEMPT_MANIFEST_FILENAME,
        json.dumps({
            api.ATTEMPT_ID_KEY: HAANEN_REJECTED_ATTEMPT_ID,
            api.ATTEMPT_STAGE_KEY: api.ATTEMPT_STAGE_EVIDENCE_VALIDATION,
            api.ATTEMPT_RESULT_KEY: api.ATTEMPT_RESULT_REJECTED,
            api.ATTEMPT_UPDATED_AT_KEY: TEST_ATTEMPT_TIMESTAMP.isoformat(),
            api.ATTEMPT_ARTIFACTS_KEY: {},
        }),
    )

    archive_source_dir = tmp_path / "archive_source"
    attempts_dir.rename(archive_source_dir)
    attempts_dir.mkdir(parents=True)
    for source_attempt in sorted(archive_source_dir.iterdir(), key=lambda path: path.name):
        (attempts_dir / source_attempt.name).symlink_to(
            source_attempt,
            target_is_directory=source_attempt.is_dir(),
        )

    recovery = api.restore_archived_attempts(runtime, attempts_dir=attempts_dir)
    after = logical_database_snapshot(detour_db_path)
    repeated = api.restore_archived_attempts(runtime, attempts_dir=attempts_dir)

    restored_attempt_ids = tuple(path.name for path in attempt_dirs)
    assert recovery == api.ArchivedAttemptRecovery(
        discovered=3,
        invalid=1,
        restored_attempt_ids=restored_attempt_ids,
        restored_accepted_attempt_ids=(accepted_attempt_dir.name,),
        skipped_attempt_ids=(),
    )
    assert after == before
    assert repeated == api.ArchivedAttemptRecovery(
        discovered=3,
        invalid=1,
        restored_attempt_ids=(),
        restored_accepted_attempt_ids=(),
        skipped_attempt_ids=restored_attempt_ids,
    )
    assert not accepted_card_path.exists()
    assert not accepted_response_path.exists()

    connection = open_readonly_database(detour_db_path)
    try:
        relation_names = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
        assert {
            api.ARCHIVED_ATTEMPTS_TABLE,
            api.CODEX_RETRY_BASELINE_TABLE,
            api.CODEX_EVIDENCE_AUDIT_TABLE,
            api.CODEX_FC_TABLE,
            api.CODEX_FCO_TABLE,
            api.CODEX_CALLS_TABLE,
            api.CODEX_TURN_REF_TABLE,
            api.CODEX_OUTPUT_ROWS_TABLE,
            api.CODEX_OUTPUT_VIEW,
            api.CODEX_INNERDICT_TABLE,
        } <= relation_names
        archived_rows = connection.execute(
            f"SELECT {api.ATTEMPT_ID_KEY}, {api.ARCHIVED_ATTEMPT_MANIFEST_COLUMN} "
            f"FROM {api.ARCHIVED_ATTEMPTS_TABLE} ORDER BY {api.ATTEMPT_ID_KEY}"
        ).fetchall()
        assert tuple(row[0] for row in archived_rows) == restored_attempt_ids
        assert tuple(json.loads(row[1]) for row in archived_rows) == (
            rejected_manifest,
            accepted_manifest,
        )
        assert connection.execute(
            f"SELECT {api.CODEX_RETRY_RUN_ID_COL}, "
            f"{api.CODEX_RETRY_SOURCEKEY_COL}, "
            f"{api.CODEX_RETRY_SESSION_ID_COL}, "
            f"{api.CODEX_RETRY_ATTEMPT_ID_COL} "
            f"FROM {api.CODEX_RETRY_BASELINE_TABLE}"
        ).fetchall() == [
            (
                str(TEST_RUN_ID),
                TEST_NAMEKEY,
                JULY_SESSION_ID,
                rejected_attempt_dir.name,
            )
        ]
        assert connection.execute(
            f"SELECT {api.CODEX_RETRY_ATTEMPT_ID_COL}, "
            f"{api.CODEX_EVIDENCE_APPLIED_COL}, "
            f"{api.CODEX_EVIDENCE_ACCEPTED_COL} "
            f"FROM {api.CODEX_EVIDENCE_AUDIT_TABLE} "
            f"ORDER BY {api.CODEX_EVIDENCE_AUDIT_ID_COL}"
        ).fetchall() == [
            (rejected_attempt_dir.name, True, False),
            (accepted_attempt_dir.name, True, True),
        ]
        index_counts: dict[str, int] = {}
        for table_name in (
            api.CODEX_FC_TABLE,
            api.CODEX_FCO_TABLE,
            api.CODEX_CALLS_TABLE,
            api.CODEX_TURN_REF_TABLE,
        ):
            count_row = connection.execute(f"SELECT count(*) FROM {table_name}").fetchone()
            assert count_row is not None
            index_counts[table_name] = count_row[0]
        assert index_counts == {
            api.CODEX_FC_TABLE: JULY_FC_COUNT,
            api.CODEX_FCO_TABLE: JULY_FCO_COUNT,
            api.CODEX_CALLS_TABLE: JULY_CALL_COUNT,
            api.CODEX_TURN_REF_TABLE: JULY_REF_COUNT,
        }
        assert connection.execute(
            f"SELECT {api.duckdb_quote_identifier(api.KTP_NAMEKEY_COL)}, "
            f"{api.duckdb_quote_identifier(api.KTP_FILENAME_COL)}, "
            f"{api.duckdb_quote_identifier(api.KTP_FRAGMENT_COL)}, "
            f"{api.duckdb_quote_identifier(api.KTP_FRAGMENT_TYPE_COL)}, "
            f"{api.duckdb_quote_identifier(api.KTP_AI_AUGMENT_ATTEMPT_ID_COL)} "
            f"FROM {api.CODEX_OUTPUT_VIEW}"
        ).fetchall() == [
            (
                TEST_NAMEKEY,
                JULY_ROLLOUT_FILENAME,
                JULY_ROLLOUT_LINE_COUNT,
                api.ROLLOUT_LINE_FRAGMENT_TYPE,
                accepted_attempt_dir.name,
            )
        ]
        innerdict_rows = connection.execute(
            f"SELECT {api.duckdb_quote_identifier(api.KTP_NAMEKEY_COL)}, "
            f"{api.duckdb_quote_identifier(api.KTP_INNERDICT_JSONLINES_COL)} "
            f"FROM {api.CODEX_INNERDICT_TABLE}"
        ).fetchall()
        assert len(innerdict_rows) == 1
        assert innerdict_rows[0][0] == TEST_NAMEKEY
        assert (
            json.loads(innerdict_rows[0][1])[api.KTP_AI_AUGMENT_ATTEMPT_ID_COL]
            == accepted_attempt_dir.name
        )
    finally:
        connection.close()


@pytest.mark.parametrize("mutation", ("excerpt", "url"))
def test_real_july_push_rejects_changed_evidence_before_ground_truth(
    mutation: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger=api.__name__)
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
    detail = response.json()["detail"]
    assert "8 of 9 evidence items were verified" in detail
    assert f"{first_column}.web_search_excerpts[0]" in detail
    assert TEST_CALL_ID not in detail
    assert TEST_REF_ID not in detail
    assert evidence["excerpt"] not in detail
    assert evidence["url"] not in detail
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


def test_real_july_rejection_requires_standardized_retry_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = prepare_real_sample_push(tmp_path, monkeypatch)
    snapshot = api.SanctionSnapshot(
        run_id=TEST_RUN_ID,
        source_key=TEST_NAMEKEY,
        session_id=JULY_SESSION_ID,
        rollout_guest_path=JULY_ROLLOUT_GUEST_PATH,
        control_base_url=None,
    )
    rejected_payload = deepcopy(context.payload)
    first_column = EXPECTED_EVIDENCE[0].column
    rejected_evidence = rejected_payload[first_column][FIELD_EVIDENCE_FIELD][0]
    rejected_evidence[EVIDENCE_EXCERPT_FIELD] += "X"
    monkeypatch.setattr(api, "sanctioned_snapshot", lambda: snapshot)

    rejected_response = context.client.post("/push", json=rejected_payload)
    plain_retry_response = context.client.post("/push", json=context.payload)

    assert rejected_response.status_code == 422
    rejected_detail = rejected_response.json()["detail"]
    assert f"{first_column}.{FIELD_EVIDENCE_FIELD}[0]" in rejected_detail
    assert api.RETRY_SUBMISSION_PUBLIC_GUIDANCE in rejected_detail
    assert plain_retry_response.status_code == 422
    assert plain_retry_response.json()["detail"] == (
        f"{Locale.VALIDATION_ERROR_DETAIL}\n{api.RETRY_SUBMISSION_PUBLIC_GUIDANCE}"
    )
    assert not tuple(context.runtime.pipeline.output_dir.iterdir())
    attempt_dirs = tuple(context.attempts_dir.iterdir())
    assert len(attempt_dirs) == 2
    assert all(read_json(path / "attempt.json")["result"] == "rejected" for path in attempt_dirs)
    assert all(not (path / "response.jsonl").exists() for path in attempt_dirs)

    connection = open_readonly_database(context.runtime.detour_db_path)
    try:
        baseline_count = connection.execute(
            f"SELECT COUNT(*) FROM {api.CODEX_RETRY_BASELINE_TABLE}"
        ).fetchone()
        audit_count = connection.execute(
            f"SELECT COUNT(*) FROM {api.CODEX_EVIDENCE_AUDIT_TABLE}"
        ).fetchone()
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    finally:
        connection.close()

    assert baseline_count == (1,)
    assert audit_count == (1,)
    assert api.CODEX_OUTPUT_ROWS_TABLE not in tables
    assert api.CODEX_INNERDICT_TABLE not in tables


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
    assert push_response.json() == {"detail": Locale.CONFIGURATION_ERROR_DETAIL}
    assert api.ROLLOUT_ENV_NAME in caplog.text
    assert pull_response.status_code == 503
    assert pull_response.json() == {"detail": Locale.CONFIGURATION_ERROR_DETAIL}


def test_sanctioned_pull_is_dynamic_retryable_and_omits_ground_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = api.configure_runtime(AI_AUGMENT_CONFIG_PATH)
    assert runtime.eligible_cohorts is not None
    source_key = next(
        key for key, cohort in runtime.eligible_cohorts.items() if cohort == api.GROUND_TRUTH_COHORT
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
        row.get(api.KTP_FRAGMENT_TYPE_COL) != api.DOCX_ROW_FRAGMENT_TYPE for row in rows[:-1]
    )
    assert not any(column in row for row in rows[:-1] for column in api.DOCX_COLUMNS)


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
    assert pull_response.json() == {"detail": Locale.CONFIGURATION_ERROR_DETAIL}
    assert push_response.json() == {"detail": Locale.CONFIGURATION_ERROR_DETAIL}


def test_control_run_events_are_authenticated_and_rebuild_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = runtime_for_test(tmp_path)
    events = (
        api.ControlRunEvent(
            run_id=TEST_RUN_ID,
            source_key=TEST_NAMEKEY,
            at=TEST_ATTEMPT_TIMESTAMP,
            kind=api.ControlRunEventKind.QUEUED,
        ),
        api.ControlRunEvent(
            run_id=TEST_RUN_ID,
            source_key=TEST_NAMEKEY,
            at=TEST_ATTEMPT_TIMESTAMP,
            kind=api.ControlRunEventKind.FAILED,
            detail="pre-push configuration failure",
        ),
    )
    payload = api.ControlRunEventsRequest(events=events).model_dump(mode="json")
    monkeypatch.setattr(api, "CONTROL_RUN_EVENTS_TOKEN", TEST_CONTROL_RUN_EVENTS_TOKEN)
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    client = TestClient(api.app)

    forbidden = client.put(api.CONTROL_RUN_EVENTS_PATH, json=payload)
    first = client.put(
        api.CONTROL_RUN_EVENTS_PATH,
        json=payload,
        headers={api.CONTROL_RUN_EVENTS_TOKEN_HEADER: TEST_CONTROL_RUN_EVENTS_TOKEN},
    )
    repeated = client.put(
        api.CONTROL_RUN_EVENTS_PATH,
        json=payload,
        headers={api.CONTROL_RUN_EVENTS_TOKEN_HEADER: TEST_CONTROL_RUN_EVENTS_TOKEN},
    )

    assert forbidden.status_code == 403
    assert first.json() == {"persisted": len(events)}
    assert repeated.json() == {"persisted": 0}
    assert api.load_control_run_events(runtime) == events
    assert api.CONTROL_RUN_EVENTS_PATH not in client.get("/openapi.json").json()["paths"]

    runtime.detour_db_path.unlink()
    rebuilt = client.put(
        api.CONTROL_RUN_EVENTS_PATH,
        json=payload,
        headers={api.CONTROL_RUN_EVENTS_TOKEN_HEADER: TEST_CONTROL_RUN_EVENTS_TOKEN},
    )

    assert rebuilt.json() == {"persisted": len(events)}
    assert api.load_control_run_events(runtime) == events


def test_openapi_does_not_disclose_integrity_internals() -> None:
    schema = TestClient(api.app).get("/openapi.json").json()
    push_schema = schema["paths"]["/push"]["post"]
    serialized = json.dumps(push_schema).lower()

    assert push_schema["description"] == Locale.PUSH_DESCRIPTION
    assert "appendwatch" not in serialized
    assert "rollout" not in serialized
    assert api.ROLLOUT_ENV_NAME.lower() not in serialized
