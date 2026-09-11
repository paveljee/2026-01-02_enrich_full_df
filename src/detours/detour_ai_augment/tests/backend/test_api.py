from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path, PurePosixPath
from threading import Barrier
from types import SimpleNamespace
from typing import Any, cast, get_args
from uuid import UUID
from zipfile import ZipFile

import duckdb
import pytest
import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import ValidationError

from src.detours.detour_ai_augment.protected.src.backend.helpers import codex_parse
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models import (
    pydantic_to_paste,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (  # noqa: E501
    RESOURCE_DESCRIPTION_KEY,
    RESOURCE_PATH_KEY,
    RESOURCE_SHA256_KEY,
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.pydantic_to_paste import (  # noqa: E501
    EvidenceWithdrawal,
    FieldSubmission,
    StandardizedFieldSubmission,
    StandardizedSubmission,
    WebSearchExcerpt,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_fixture import (  # noqa: E501
    L_FEI_FEI_INITIAL_FIXTURE,
    L_FEI_FEI_RETRY_FIXTURE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_init import (  # noqa: E501
    Submission,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AI_AUGMENT_COLUMNS,
    AI_AUGMENT_EVIDENCE_COLUMNS,
    DOCX_COLUMNS,
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    KTP_AI_AUGMENT_COMMENTS_COL,
    KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL,
    KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL,
    KTP_AI_AUGMENT_EDUCATION_COL,
    KTP_AI_AUGMENT_GENDER_COL,
    KTP_AI_AUGMENT_LINKS_COL,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
    KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
    MAP_SUBSET_0_TO_BATCH_KEY,
    PYDANTIC_TO_PASTE_SOURCE,
    REPLAY_LOG_KEY,
    TEXT_ENCODING,
    AiAugmentCohort,
    AiAugmentIneligibilityCategory,
)
from src.detours.detour_ai_augment.src.backend import api, ipc, server
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (
    AiAugmentBackendContext,
    _source_innerdicts_by_namekey,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_outer_dict import (
    AiAugmentOuterDict,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_event import (
    SOURCE_KEY_HEADER,
    AppendwatchReportEncoding,
    AppendwatchReportRecord,
    BackendCommitRecord,
    BackendLifecycle,
    CodexRolloutRecord,
    CodexSessionRecord,
    CommitRequestBody,
    PostCommitValidation,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.query_response import (
    AgentRuntimeAttempt,
    AgentRuntimeAttemptRecord,
    QueryResponse,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.run_outcome_response import (
    RunOutcomeResponse,
    RunOutcomeResponseBody,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    run_outcome as run_outcome_models,
)
from src.helpers.cards import build_cards, write_cards_zip
from src.helpers.config import PipelineConfig
from src.helpers.data_models import (
    InnerDict,
    NameKey,
)
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
)
from src.helpers.duckdb_extensions import load_duckdb_extension_from_config_path
from src.helpers.duckdb_utils import duckdb_quote_identifier
from src.helpers.procedures import (
    DocxMatchProcedure,
    ParquetMatchProcedure,
    XlsxMatchProcedure,
)
from src.helpers.schema import (
    DOCX_INNERDICT_TABLE,
    PARQUET_INNERDICT_TABLE,
    XLSX_INNERDICT_TABLE,
)
from src.helpers.vars import (
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_INNERDICT_JSONLINES_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
)


@dataclass(frozen=True, slots=True)
class BackendTestPaths:
    config: Path
    ai_augment_config: Path
    source_database: Path
    reference_docx: Path
    pydantic_to_paste: Path
    july_rollout: Path
    haanen_rejected_rollout: Path
    haanen_accepted_rollout: Path


JULY_ROLLOUT_RELATIVE_PATH = PurePosixPath(
    "2026/07/27/rollout-2026-07-27T12-10-36-019fa457-aac5-7652-8669-9d571206e7cb.jsonl"
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
TEST_SESSION_ID = UUID("019d0000-0000-7000-8000-000000000001")
TEST_SESSION_TIMESTAMP = "2026-07-31T16:10:36.000Z"
TEST_ROLLOUT_FILENAME = f"rollout-2026-07-31T12-10-36-{TEST_SESSION_ID}.jsonl"
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
TEST_NAMEKEY_MODEL = NameKey.from_json_key(TEST_NAMEKEY)
TEST_RUN_ID = UUID("019fa457-aac5-7652-8669-9d571206e7cb")
TEST_SECOND_RUN_ID = UUID("019fa457-aac5-7652-8669-9d571206e7cc")
TEST_ATTEMPT_TIMESTAMP = datetime(2026, 8, 14, tzinfo=timezone.utc)
TEST_AUTHORITATIVE_REQUEST_BODY = b'{"probe":true}'
TEST_AUTHORITATIVE_RESPONSE_BODY = {"accepted": True}
TEST_AUTHORITATIVE_RESPONSE_HEADER = "X-Authoritative-Probe"
TEST_AUTHORITATIVE_RESPONSE_HEADER_VALUE = "preserved"
TEST_AUTHORITATIVE_LOG_FILENAME = "authoritative.jsonl"
TEST_DETOUR_DB_FILENAME = "detour.duckdb"
TEST_ROLLOUT_CAS_DIRECTORY = "rollout-cas"
OPERATOR_ACCEPTED_PUSH_FIXTURE = "operator_accepted_aziz_sheikh_push.json"
OPERATOR_CAPTURED_SESSION_ID = "01a068a7-1179-7d62-8dde-4720457e3808"
OPERATOR_CAPTURED_SESSION_TIMESTAMP = "2026-09-03T19:16:00.000Z"


def persisted_http_record(
    *,
    record_id: UUID,
    method: str,
    path: str,
    response_code: int,
    request_body: str | None = None,
    response_body: str = "",
    response_headers: dict[str, str] | None = None,
) -> HttpRequestLogRecord:
    return HttpRequestLogRecord(
        schema_version="1.1",
        record_id=record_id,
        method=method,
        scheme="http",
        host="testserver",
        port=None,
        ready_to_respond_at_unix_usec=2,
        path=path,
        query="",
        request_headers={},
        request_body=request_body,
        response_code=response_code,
        response_headers=response_headers or {},
        response_body=response_body,
        received_at_unix_usec=1,
        duration_usec=1,
    )


def deterministic_uuid7(value: str) -> UUID:
    return UUID(
        bytes=hashlib.sha256(value.encode(TEXT_ENCODING)).digest()[:16],
        version=7,
    )


def retry_attempt_records(
    *,
    run_id: UUID,
    session_id: UUID,
    attempt_id: str,
) -> tuple[HttpRequestLogRecord, BackendCommitRecord]:
    pull_record = persisted_http_record(
        record_id=run_id,
        method=api.HTTP_GET_METHOD,
        path=api.PULL_PATH,
        response_code=status.HTTP_200_OK,
    )
    push_record = persisted_http_record(
        record_id=deterministic_uuid7(attempt_id + "-push"),
        method=api.HTTP_POST_METHOD,
        path=api.PUSH_PATH,
        response_code=status.HTTP_202_ACCEPTED,
        request_body="{}",
    )
    commit_record = api._synthetic_commit_record(
        pull_record=pull_record,
        push_record=push_record,
        session_id=session_id,
        rollout_archive=api._ArchivedFile(
            path=Path("unused-test-rollout.jsonl"),
            size=3,
            sha256=hashlib.sha256(b"{}\n").hexdigest(),
            line_count=1,
        ),
        rollout_filename=f"rollout-{session_id}.jsonl",
        appendwatch_report=b".\n",
        namekey=TEST_NAMEKEY_MODEL,
    ).model_copy(update={"record_id": deterministic_uuid7(attempt_id)})
    return pull_record, commit_record


def process_retry_attempt_for_test(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: UUID,
    namekey: NameKey,
    session_id: UUID,
    attempt_id: str,
    attempt_timestamp: datetime,
    submission_payload: Submission | StandardizedSubmission,
    assessment: api._EvidenceAssessment,
) -> tuple[str, ...]:
    original_pull, commit_record = retry_attempt_records(
        run_id=run_id,
        session_id=session_id,
        attempt_id=attempt_id,
    )
    return api._process_retry_attempt(
        conn,
        original_pull=original_pull,
        commit_record=commit_record,
        namekey=namekey,
        attempt_timestamp=attempt_timestamp,
        submission_payload=submission_payload,
        assessment=assessment,
    )


HAANEN_REJECTED_ATTEMPT_ID = "20260813T141344_678596Z_8ef1f6372b4a48d9a3b1279736356363"
HAANEN_ACCEPTED_ATTEMPT_ID = "20260813T141450_027429Z_044215aac8c44200882531b10a2acfa6"
HAANEN_ROLLOUT_FILENAME = "rollout-2026-08-13T10-08-12-019ffb73-b72c-7812-9fc4-d56fdf3ea1a2.jsonl"
HAANEN_SESSION_ID = UUID("019ffb73-b72c-7812-9fc4-d56fdf3ea1a2")
HAANEN_RUN_ID = UUID("019ffb73-b72c-7812-9fc4-d56fdf3ea1a3")
HAANEN_NAMEKEY = '{"ktp.first_name": "J. B.", "ktp.last_name": "Haanen"}'
HAANEN_NAMEKEY_MODEL = NameKey.from_json_key(HAANEN_NAMEKEY)
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
    for column in AI_AUGMENT_EVIDENCE_COLUMNS
    if column != KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL
)
HAANEN_JSON_DECODER = json.JSONDecoder()
TEST_STANDARDIZED_VALUES = {
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL: {
        "first_name": "NR",
        "last_name": "NR",
        "orcid": "NR",
        "openalex_id": "NR",
    },
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL: {
        "place": "NR",
        "location": "NR",
    },
    KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL: {
        "race": "NA",
        "ethnicity": "NA",
        "language": "NR",
        "culture": "NA",
    },
    KTP_AI_AUGMENT_GENDER_COL: "NR",
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL: "NR",
    KTP_AI_AUGMENT_EDUCATION_COL: "NR",
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL: "NR",
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL: "NR",
    KTP_AI_AUGMENT_LINKS_COL: "NR",
}


@pytest.fixture(scope="session")
def backend_test_paths(
    pytestconfig: pytest.Config,
) -> BackendTestPaths:
    repository_root = pytestconfig.rootpath
    detour_root = repository_root / "src" / "detours" / "detour_ai_augment"
    haanen_rejected_attempt = repository_root / "tmp" / HAANEN_REJECTED_ATTEMPT_ID
    haanen_accepted_attempt = repository_root / "tmp" / HAANEN_ACCEPTED_ATTEMPT_ID
    return BackendTestPaths(
        config=repository_root / "config.repl.json",
        ai_augment_config=repository_root / "config_ai_augment.json",
        source_database=repository_root / "data" / "scisci_process.duckdb",
        reference_docx=repository_root / "resources" / "pandoc-custom-reference.docx",
        pydantic_to_paste=(
            detour_root
            / "protected"
            / "src"
            / "backend"
            / "helpers"
            / "data_models"
            / "pydantic_to_paste.py"
        ),
        july_rollout=(
            detour_root
            / "data"
            / "sample_run"
            / ".codex"
            / "sessions"
            / Path(*JULY_ROLLOUT_RELATIVE_PATH.parts)
        ),
        haanen_rejected_rollout=(
            haanen_rejected_attempt / f"rollout.{HAANEN_REJECTED_ATTEMPT_ID}.jsonl"
        ),
        haanen_accepted_rollout=(
            haanen_accepted_attempt / f"rollout.{HAANEN_ACCEPTED_ATTEMPT_ID}.jsonl"
        ),
    )


@pytest.fixture(autouse=True)
def isolated_backend_detour_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    monkeypatch.setattr(api, "BACKEND_PROCESS_LOCK_PATH", tmp_path / "backend.lock")
    api._release_backend_process_lock()
    api.close_backend_detour_database()
    yield
    api.close_backend_detour_database()
    api._release_backend_process_lock()


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
        KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
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
        KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
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
        KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
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
        KTP_AI_AUGMENT_GENDER_COL,
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
        KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
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
        KTP_AI_AUGMENT_EDUCATION_COL,
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
        KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
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
        KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
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
        KTP_AI_AUGMENT_LINKS_COL,
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
                        f"SELECT * FROM {duckdb_quote_identifier(str(name))} ORDER BY ALL"
                    ).fetchall()
                ),
            )
            for name, relation_type in relations
        }
    finally:
        connection.close()


def rollout_record(value: dict[str, object], line_number: int) -> api._RolloutRecord:
    raw_line = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    return api._RolloutRecord(
        line_number=line_number,
        line_sha256=hashlib.sha256(raw_line).hexdigest(),
        value=value,
    )


def minimal_rollout_records(action: str = "search_query") -> tuple[api._RolloutRecord, ...]:
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
                "session_id": str(TEST_SESSION_ID),
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


def build_test_index(action: str = "search_query") -> api._RolloutIndex:
    return api.build_rollout_index(
        minimal_rollout_records(action),
        timezone_name=TEST_TIMEZONE,
        configured_rollout_basename=TEST_ROLLOUT_FILENAME,
    )


def build_duplicate_evidence_index() -> api._RolloutIndex:
    index = build_test_index()
    return api._RolloutIndex(
        session=index.session,
        fc_rows=index.fc_rows
        + (
            api._CodexFcRow(
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
            api._CodexFcoRow(
                timestamp=index.fco_rows[0].timestamp,
                fco_id=TEST_VIEW_FCO_ID,
                call_id=TEST_VIEW_CALL_ID,
            ),
        ),
        turn_ref_rows=index.turn_ref_rows
        + (
            api._CodexTurnRefRow(
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
) -> api._RolloutIndex:
    index = build_test_index()
    return api._RolloutIndex(
        session=index.session,
        fc_rows=index.fc_rows,
        fco_rows=index.fco_rows,
        turn_ref_rows=tuple(
            api._CodexTurnRefRow(
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
        for column in AI_AUGMENT_EVIDENCE_COLUMNS
    }


def standardized_submission_body(
    plain_body: dict[str, object],
) -> dict[str, object]:
    standardized_body = deepcopy(plain_body)
    for column in AI_AUGMENT_EVIDENCE_COLUMNS:
        field_submission = standardized_body[column]
        assert isinstance(field_submission, dict)
        field_submission[FIELD_STANDARDIZED_VALUE_FIELD] = deepcopy(
            TEST_STANDARDIZED_VALUES[column]
        )
    return standardized_body


def connect_v2_index(
    index: api._RolloutIndex,
    *,
    config_path: Path,
    database_path: Path | None = None,
) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(database_path) if database_path is not None else ":memory:")
    try:
        load_duckdb_extension_from_config_path(
            connection,
            api.CODEX_TOKEN_EXTENSION,
            config_path,
            log=None,
        )
    except RuntimeError as exc:
        connection.close()
        pytest.skip(f"configured DuckDB token extension is unavailable: {exc}")
    api.persist_rollout_index(
        connection,
        index,
        codex_match_version=2,
    )
    return connection


def historical_haanen_submissions(
    paths: BackendTestPaths,
) -> tuple[dict[str, object], dict[str, object]]:
    if not paths.haanen_rejected_rollout.is_file() or not paths.haanen_accepted_rollout.is_file():
        pytest.skip("optional historical Haanen rollout fixtures are unavailable")
    rejected_stream = paths.haanen_rejected_rollout.open("r", encoding="utf-8")
    accepted_stream = paths.haanen_accepted_rollout.open("r", encoding="utf-8")
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
    race_evidence_source = KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL
    rejected_submission[KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL] = {
        FIELD_VALUE_FIELD: "Not present in the archived pre-field submission.",
        FIELD_EVIDENCE_FIELD: deepcopy(
            rejected_submission[race_evidence_source][FIELD_EVIDENCE_FIELD][:1]
        ),
    }
    accepted_submission[KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL] = deepcopy(
        rejected_submission[KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL]
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
        body[KTP_AI_AUGMENT_COMMENTS_COL] = {"value": EXPECTED_COMMENT}
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
    paths: BackendTestPaths,
    *,
    output_format: str = "txt",
    source_database: Path | None = None,
    namekey: str | None = None,
    codex_match_version: int | None = None,
) -> AiAugmentBackendContext:
    output_dir = tmp_path / "output"
    replay_log_path = tmp_path / "authoritative.jsonl"
    rollout_cas_dir = tmp_path / "rollout-cas"
    output_dir.mkdir(exist_ok=True)
    replay_log_path.write_text("", encoding=TEXT_ENCODING)
    config_data = json.loads(paths.ai_augment_config.read_text(encoding=TEXT_ENCODING))
    config_data["files_config"][REPLAY_LOG_KEY] = {
        "path": str(replay_log_path),
        "sha256": hashlib.sha256(b"").hexdigest(),
        "desc": "isolated Backend test replay log",
    }
    configured_pipeline = AiAugmentDetourConfig.model_validate(
        config_data,
        context={"verify_hash_on_init": False},
    )
    pipeline = configured_pipeline.model_copy(
        update={
            "db_file": source_database or paths.source_database,
            "output_dir": output_dir,
            "output_format": output_format,
            "pandoc_reference_docx": paths.reference_docx,
            "detour_db_path": tmp_path / "detour_ai_augment.duckdb",
            "rollout_cas_dir": rollout_cas_dir,
            "match_rule_version": (
                configured_pipeline.match_rule_version
                if codex_match_version is None
                else configured_pipeline.match_rule_version.model_copy(
                    update={"codex_match": codex_match_version}
                )
            ),
        }
    )
    ai_augment_outerdicts: tuple[AiAugmentOuterDict, ...] = ()
    configured_namekey: NameKey | None = None
    if namekey is not None:
        configured_namekey = NameKey.from_json_key(namekey)
        source_connection = duckdb.connect(str(pipeline.db_file), read_only=True)
        try:
            xlsx = _source_innerdicts_by_namekey(
                source_connection,
                table_name=XLSX_INNERDICT_TABLE,
                procedure=XlsxMatchProcedure(),
            )
            ssn = _source_innerdicts_by_namekey(
                source_connection,
                table_name=PARQUET_INNERDICT_TABLE,
                procedure=ParquetMatchProcedure(),
            )
            docx = _source_innerdicts_by_namekey(
                source_connection,
                table_name=DOCX_INNERDICT_TABLE,
                procedure=DocxMatchProcedure(),
            )
            ai_augment_outerdicts = (
                AiAugmentOuterDict(
                    namekey=configured_namekey,
                    xlsx_innerdicts=xlsx[namekey],
                    ssn_innerdicts=ssn.get(namekey, ()),
                    docx_innerdicts=docx.get(namekey, ()),
                    ai_augment_rnd=1,
                    ai_augment_cohort=AiAugmentCohort.GROUND_TRUTH,
                ),
            )
        finally:
            source_connection.close()
    return AiAugmentBackendContext(
        pipeline_config=pipeline,
        configured_namekey=configured_namekey,
        cached_ai_augment_outerdicts=ai_augment_outerdicts,
    )


def prepare_real_sample_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    paths: BackendTestPaths,
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

    runtime = runtime_for_test(tmp_path, paths, output_format=output_format)
    rendered_cards: list[str] = []
    configuration = api._PushConfiguration(
        rollout_guest_path=JULY_ROLLOUT_GUEST_PATH,
        rollout_relative_path=JULY_ROLLOUT_RELATIVE_PATH,
        appendwatch_report=PurePosixPath("/mounted/appendwatch-tree.txt"),
        lima_ssh_config=lima_config_path,
        identity_file=identity_path,
        known_hosts_file=known_hosts_path,
        ssh_user="aivm-audit",
        ssh_target="aivm-aivm-audit",
        host_key_alias="lima-aivm-aivm-audit",
    )
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    monkeypatch.setattr(api, "load_duckdb_extension", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api, "push_configuration", lambda _rollout=None: configuration)
    monkeypatch.setattr(api, "AUTHORITATIVE_BACKEND_HEALTHY", False)
    monkeypatch.setattr(api, "AUTHORITATIVE_LOG_DESCRIPTOR", None)
    monkeypatch.setattr(api, "AUTHORITATIVE_LOG_OFFSET", api.AUTHORITATIVE_EMPTY_OFFSET)
    monkeypatch.setattr(api, "AUTHORITATIVE_NEXT_LINE_NUMBER", api.AUTHORITATIVE_FIRST_LINE)

    def fake_subprocess(
        command: list[str],
        **kwargs: object,
    ) -> SimpleNamespace:
        if command[0] == api.SSH_EXECUTABLE:
            assert command[-2] == configuration.ssh_target
            if command[-1] == (f"{api.AUDIT_READ_ROLLOUT_COMMAND} {JULY_ROLLOUT_RELATIVE_PATH}"):
                cast(Any, kwargs["stdout"]).write(read_bytes(paths.july_rollout))
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            assert command[-1] == (
                f"{api.AUDIT_READ_APPENDWATCH_REPORT_COMMAND} {configuration.appendwatch_report}"
            )
            return SimpleNamespace(
                returncode=0,
                stdout=read_bytes(report_path),
                stderr=b"",
            )
        assert command[0] == "pandoc"
        output_path = Path(command[command.index("-o") + 1])
        write_bytes(output_path, b"test DOCX renderer output")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_subprocess)

    original_write_cards_zip = write_cards_zip

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


def operator_capture_fixture(detour_root: Path, filename: str) -> Path:
    return detour_root / "protected" / "tests" / "fixtures" / filename


def operator_retry_baseline(
    accepted_push: dict[str, object],
) -> dict[str, object]:
    baseline = deepcopy(accepted_push)
    for column in AI_AUGMENT_EVIDENCE_COLUMNS:
        field = baseline[column]
        assert isinstance(field, dict)
        field.pop(FIELD_STANDARDIZED_VALUE_FIELD)

    education = baseline[KTP_AI_AUGMENT_EDUCATION_COL]
    assert isinstance(education, dict)
    education[FIELD_VALUE_FIELD] = (
        "BSc Physiology, University College London (1990); MBBS Medicine, "
        "University College London (1993); three additional unverified credentials."
    )
    evidence = education[FIELD_EVIDENCE_FIELD]
    assert isinstance(evidence, list)
    evidence[1:] = [
        {
            EVIDENCE_EXCERPT_FIELD: f"Unverified captured credential {index}",
            EVIDENCE_URL_FIELD: f"https://unverified.invalid/credential-{index}",
        }
        for index in range(1, 4)
    ]
    return baseline


def operator_capture_rollout(accepted_push: dict[str, object]) -> bytes:
    records: list[dict[str, object]] = [
        {
            "timestamp": OPERATOR_CAPTURED_SESSION_TIMESTAMP,
            "type": "session_meta",
            "payload": {
                "session_id": OPERATOR_CAPTURED_SESSION_ID,
                "timestamp": OPERATOR_CAPTURED_SESSION_TIMESTAMP,
                "originator": "codex_cli_rs",
                "source": "exec",
                "cli_version": "0.146.0-alpha.3.1",
                "model_provider": "openai",
            },
        },
        {
            "timestamp": OPERATOR_CAPTURED_SESSION_TIMESTAMP,
            "type": "turn_context",
            "payload": {"model": "gpt-5.6-sol", "effort": "xhigh"},
        },
    ]
    evidence_index = 0
    for column in AI_AUGMENT_EVIDENCE_COLUMNS:
        field = accepted_push[column]
        assert isinstance(field, dict)
        evidence = field[FIELD_EVIDENCE_FIELD]
        assert isinstance(evidence, list)
        for item in evidence:
            assert isinstance(item, dict)
            if EVIDENCE_WITHDRAWAL_ACTION_FIELD in item:
                continue
            excerpt = item[EVIDENCE_EXCERPT_FIELD]
            url = item[EVIDENCE_URL_FIELD]
            assert isinstance(excerpt, str)
            assert isinstance(url, str)
            call_id = f"call_operator_{evidence_index}"
            ref_id = f"turn0search{evidence_index}"
            timestamp = f"2026-09-03T19:16:{evidence_index + 1:02d}.000Z"
            arguments = {
                "search_query": [{"q": f"captured operator evidence {evidence_index}"}],
                "response_length": "long",
            }
            records.extend((
                {
                    "timestamp": timestamp,
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "id": f"fc_operator_{evidence_index}",
                        "name": "run",
                        "namespace": "web",
                        "arguments": json.dumps(arguments, separators=(",", ":")),
                        "call_id": call_id,
                    },
                },
                {
                    "timestamp": timestamp,
                    "type": "event_msg",
                    "payload": {
                        "type": "web_search_end",
                        "call_id": call_id,
                        "results": [
                            {
                                "type": "text_result",
                                "domain": "captured.operator.test",
                                "ref_id": ref_id,
                                "snippet": excerpt,
                                "thumbnail_url": None,
                                "title": f"Captured operator evidence {evidence_index}",
                                "url": url,
                            }
                        ],
                    },
                },
                {
                    "timestamp": timestamp,
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "id": f"fco_operator_{evidence_index}",
                        "call_id": call_id,
                        "output": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Captured result\n"
                                    f"{api.CODEX_CITE_MARKER_PREFIX}{ref_id}"
                                    f"{api.CODEX_CITE_MARKER_SUFFIX}\n{excerpt}"
                                ),
                            }
                        ],
                    },
                },
            ))
            evidence_index += 1
    return b"".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        for record in records
    )


def create_operator_capture_source_database(
    path: Path,
    ground_truth: Mapping[str, object],
) -> None:
    xlsx_row = {
        KTP_NAMEKEY_COL: TEST_NAMEKEY,
        KTP_FILENAME_COL: "operator-capture.xlsx",
        KTP_FRAGMENT_COL: 148,
        KTP_FRAGMENT_TYPE_COL: "csv_row",
        DRAW_LABEL: "146",
        KTP_FIRST_NAME_COL: "A.",
        KTP_LAST_NAME_COL: "Sheikh",
    }
    docx_row = {
        KTP_NAMEKEY_COL: TEST_NAMEKEY,
        KTP_FILENAME_COL: "operator-capture.docx",
        KTP_FRAGMENT_COL: 1,
        KTP_FRAGMENT_TYPE_COL: "docx_table",
        DRAW_LABEL: "146",
        **ground_truth,
    }
    connection = duckdb.connect(str(path))
    try:
        for table_name in (
            XLSX_INNERDICT_TABLE,
            DOCX_INNERDICT_TABLE,
            PARQUET_INNERDICT_TABLE,
        ):
            connection.execute(
                f"CREATE TABLE {duckdb_quote_identifier(table_name)} ("
                f"{duckdb_quote_identifier(KTP_NAMEKEY_COL)} VARCHAR PRIMARY KEY, "
                f"{duckdb_quote_identifier(KTP_INNERDICT_JSONLINES_COL)} VARCHAR NOT NULL)"
            )
        connection.execute(
            f"INSERT INTO {duckdb_quote_identifier(XLSX_INNERDICT_TABLE)} VALUES (?, ?)",
            [TEST_NAMEKEY, api.json_line(xlsx_row)],
        )
        connection.execute(
            f"INSERT INTO {duckdb_quote_identifier(DOCX_INNERDICT_TABLE)} VALUES (?, ?)",
            [TEST_NAMEKEY, api.json_line(docx_row)],
        )
    finally:
        connection.close()


async def authoritative_api_exchange(
    method: str,
    path: str,
    body: bytes = b"",
) -> tuple[int, bytes]:
    async def public_endpoint(
        scope: dict[str, object],
        receive: Any,
        send: Any,
    ) -> None:
        request = Request(cast(Any, scope), receive=receive)
        response = (
            api.authoritative_pull()
            if method == api.HTTP_GET_METHOD
            else await api.authoritative_push(request)
        )
        await response(cast(Any, scope), receive, send)

    request_pending = True
    never_disconnect = asyncio.Event()
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        nonlocal request_pending
        if request_pending:
            request_pending = False
            return {
                api.ASGI_TYPE_KEY: api.ASGI_HTTP_REQUEST_MESSAGE_TYPE,
                api.ASGI_BODY_KEY: body,
                api.ASGI_MORE_BODY_KEY: False,
            }
        await never_disconnect.wait()
        return {api.ASGI_TYPE_KEY: api.ASGI_HTTP_DISCONNECT_MESSAGE_TYPE}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    headers = [(b"content-type", b"application/json")]
    if body:
        headers.append((b"content-length", str(len(body)).encode()))
    scope = {
        api.ASGI_TYPE_KEY: api.ASGI_HTTP_SCOPE_TYPE,
        api.ASGI_METHOD_KEY: method,
        api.ASGI_PATH_KEY: path,
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "http_version": "1.1",
        "root_path": "",
    }
    await asyncio.wait_for(
        api._AuthoritativeHttpMiddleware(cast(Any, public_endpoint))(
            cast(Any, scope),
            receive,
            cast(Any, send),
        ),
        timeout=5,
    )
    response_start = next(
        message
        for message in sent
        if message[api.ASGI_TYPE_KEY] == api.ASGI_HTTP_RESPONSE_START_MESSAGE_TYPE
    )
    response_body = b"".join(
        cast(bytes, message.get(api.ASGI_BODY_KEY, b""))
        for message in sent
        if message[api.ASGI_TYPE_KEY] == api.ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE
    )
    return cast(int, response_start[api.ASGI_STATUS_KEY]), response_body


def assert_captured_operator_push_contour(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_test_paths: BackendTestPaths,
    detour_root: Path,
) -> None:
    accepted_push_path = operator_capture_fixture(
        detour_root,
        OPERATOR_ACCEPTED_PUSH_FIXTURE,
    )
    accepted_push = read_json(accepted_push_path)
    accepted_values: dict[str, object] = {}
    for column in AI_AUGMENT_COLUMNS:
        field = accepted_push[column]
        assert isinstance(field, dict)
        accepted_values[column] = field[FIELD_VALUE_FIELD]
    ground_truth = {
        column: f"synthetic operator ground truth {index}"
        for index, column in enumerate(DOCX_COLUMNS, start=1)
    }
    gone_response_text = api.json_line(accepted_values) + api.json_line(ground_truth)

    source_database = tmp_path / "operator-capture-source.duckdb"
    create_operator_capture_source_database(source_database, ground_truth)
    runtime = runtime_for_test(
        tmp_path,
        backend_test_paths,
        source_database=source_database,
        namekey=TEST_NAMEKEY,
        codex_match_version=1,
    )
    rollout_relative_path = PurePosixPath(
        f"2026/09/03/rollout-2026-09-03T15-16-00-{OPERATOR_CAPTURED_SESSION_ID}.jsonl"
    )
    rollout_path = tmp_path / rollout_relative_path.name
    write_bytes(rollout_path, operator_capture_rollout(accepted_push))
    deployment_dir = tmp_path / "operator-capture-deployment"
    deployment_dir.mkdir()
    report_path = deployment_dir / "appendwatch-tree.txt"
    write_text(report_path, report_for_rollout(rollout_relative_path))
    identity_path = deployment_dir / "id_ed25519"
    known_hosts_path = deployment_dir / "known_hosts"
    lima_config_path = deployment_dir / "ssh.config"
    for path in (identity_path, known_hosts_path, lima_config_path):
        write_text(path, "fixture\n")
    configuration = api._PushConfiguration(
        rollout_guest_path=f"{api.CODEX_SESSIONS_ROOT}/{rollout_relative_path}",
        rollout_relative_path=rollout_relative_path,
        appendwatch_report=PurePosixPath("/mounted/appendwatch-tree.txt"),
        lima_ssh_config=lima_config_path,
        identity_file=identity_path,
        known_hosts_file=known_hosts_path,
        ssh_user="aivm-audit",
        ssh_target="aivm-aivm-audit",
        host_key_alias="lima-aivm-aivm-audit",
    )

    institution_names = {
        "I45129253": ("University College London", "https://ror.org/02jx3x895"),
        "I40120149": ("University of Oxford", "https://ror.org/052gg0110"),
        "I98677209": ("University of Edinburgh", "https://ror.org/01nrxwf90"),
    }
    ror_names = {
        "02jx3x895": "University College London",
        "052gg0110": "University of Oxford",
        "01nrxwf90": "University of Edinburgh",
    }

    def fake_institution_get(url: str, **_kwargs: object) -> SimpleNamespace:
        identifier = url.rstrip("/").rsplit("/", 1)[-1]
        if url.startswith("https://api.openalex.org/"):
            organization_name, ror = institution_names[identifier]
            payload: dict[str, object] = {"display_name": organization_name, "ror": ror}
        else:
            payload = {"names": [{"value": ror_names[identifier], "types": ["ror_display"]}]}
        return SimpleNamespace(
            status_code=200,
            json=lambda: payload,
            raise_for_status=lambda: None,
        )

    def fake_subprocess_run(
        command: list[str],
        **kwargs: object,
    ) -> SimpleNamespace:
        assert command[0] == api.SSH_EXECUTABLE
        assert command[-2] == configuration.ssh_target
        if command[-1] == (
            f"{api.AUDIT_READ_ROLLOUT_COMMAND} {configuration.rollout_relative_path}"
        ):
            cast(Any, kwargs["stdout"]).write(read_bytes(rollout_path))
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        assert command[-1] == (
            f"{api.AUDIT_READ_APPENDWATCH_REPORT_COMMAND} {configuration.appendwatch_report}"
        )
        return SimpleNamespace(
            returncode=0,
            stdout=read_bytes(report_path),
            stderr=b"",
        )

    original_after_authoritative_record = api._after_authoritative_public_record

    async def commit_inline_after_authoritative_record(
        record: HttpRequestLogRecord,
    ) -> None:
        if (record.method, record.path) == (api.HTTP_POST_METHOD, api.PUSH_PATH):
            assert record.response_code == status.HTTP_202_ACCEPTED
            api._commit_accepted_push(record)
            return
        await original_after_authoritative_record(record)

    monkeypatch.setenv(pydantic_to_paste.EXPORT_OPENALEX_API_KEY, "operator-fixture-key")
    monkeypatch.setattr(requests, "get", fake_institution_get)
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    monkeypatch.setattr(
        api,
        "StreamingResponse",
        lambda content, *, media_type: Response(
            content="".join(content),
            media_type=media_type,
        ),
    )
    monkeypatch.setattr(
        api,
        "push_configuration_for_session",
        lambda session_id: (
            configuration
            if session_id == UUID(OPERATOR_CAPTURED_SESSION_ID)
            else pytest.fail()
        ),
    )
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(
        api,
        "_after_authoritative_public_record",
        commit_inline_after_authoritative_record,
    )
    monkeypatch.setattr(api, "BACKEND_CURRENT_PULL_RECORD", None)
    monkeypatch.setattr(api, "BACKEND_PENDING_PULL_RECORD", None)
    monkeypatch.setattr(api, "BACKEND_LATEST_PUSH_RECORD", None)
    monkeypatch.setattr(api, "BACKEND_SESSION_ID", UUID(OPERATOR_CAPTURED_SESSION_ID))
    monkeypatch.setattr(api, "BACKEND_ATTEMPT_RECORD", None)
    monkeypatch.setattr(api, "BACKEND_LIFECYCLE", BackendLifecycle.READY)
    api._acquire_authoritative_process_lock(runtime)
    try:
        api.synchronize_authoritative_projection(runtime)

        async def run_captured_contour() -> tuple[
            tuple[int, bytes],
            tuple[int, bytes],
            tuple[int, bytes],
            tuple[int, bytes],
            tuple[int, bytes],
        ]:
            initial_pull = await authoritative_api_exchange(
                api.HTTP_GET_METHOD,
                api.PULL_PATH,
            )
            baseline_push = await authoritative_api_exchange(
                api.HTTP_POST_METHOD,
                api.PUSH_PATH,
                json.dumps(operator_retry_baseline(accepted_push)).encode(),
            )
            retry_pull = await authoritative_api_exchange(
                api.HTTP_GET_METHOD,
                api.PULL_PATH,
            )
            accepted = await authoritative_api_exchange(
                api.HTTP_POST_METHOD,
                api.PUSH_PATH,
                read_bytes(accepted_push_path),
            )
            gone_pull = await authoritative_api_exchange(
                api.HTTP_GET_METHOD,
                api.PULL_PATH,
            )
            return initial_pull, baseline_push, retry_pull, accepted, gone_pull

        initial_pull, baseline_push, retry_pull, accepted, gone_pull = asyncio.run(
            run_captured_contour()
        )
        assert initial_pull[0] == status.HTTP_200_OK
        assert baseline_push[0] == status.HTTP_202_ACCEPTED
        assert retry_pull[0] == status.HTTP_200_OK
        assert accepted[0] == status.HTTP_202_ACCEPTED
        assert gone_pull == (status.HTTP_410_GONE, gone_response_text.encode())

        authoritative_records = tuple(
            record
            for record, _byte_offset, _line_sha256 in api._authoritative_log_records(
                Path(runtime.pipeline_config.resources.replay_log)
            )
        )
        pushes = tuple(
            record
            for record in authoritative_records
            if (record.method, record.path) == (api.HTTP_POST_METHOD, api.PUSH_PATH)
        )
        commits = tuple(
            record
            for record in authoritative_records
            if (record.method, record.path) == api.AUTHORITATIVE_COMMIT_ROUTE
        )
        assert len(pushes) == len(commits) == 2
        assert isinstance(pushes[-1].request_body, str)
        assert pushes[-1].request_body == read_text(accepted_push_path)
        records_by_id = {record.record_id: record for record in authoritative_records}
        assert commits[-1].request_body is not None
        accepted_commit = CommitRequestBody.from_serialized_json(
            commits[-1].request_body,
            resolve_http_record=records_by_id.__getitem__,
        )
        assert accepted_commit.push_record.record_id == pushes[-1].record_id
        assert accepted_commit.pull_record.record_id == next(
            record.record_id
            for record in reversed(authoritative_records)
            if (record.method, record.path) == (api.HTTP_GET_METHOD, api.PULL_PATH)
            and record.response_code == status.HTTP_200_OK
        )

        query = QueryResponse.from_serialized_json(
            ipc.dashboard_query_payload(TEST_NAMEKEY_MODEL)
        )
        assert len(query.attempts) == 2
        assert (
            query.attempts[-1].attempt.post_commit_validation.result
            is BackendLifecycle.ACCEPTED
        )
        assert (
            query.attempts[-1].attempt.commit_record.record_id
            == commits[-1].record_id
        )
        assert (
            query.attempts[-1]
            .attempt.commit_record.commit_request_body.push_record.record_id
            == pushes[-1].record_id
        )
        assert len(query.ai_augment_outerdicts) == 1
        selected_outerdict = query.ai_augment_outerdicts[0]
        assert len(selected_outerdict.committed_innerdicts) == 1
        committed = selected_outerdict.committed_innerdicts[0]
        assert committed.commit_record.record_id == commits[-1].record_id
        assert committed.text(
            KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL
        ) == (
            accepted_commit.model_dump_json()
        )
        cards = build_cards(
            api.selected_card_outer_dict(selected_outerdict),
            total_draws=runtime.pipeline_config.total_draws,
            intro="",
            excluded_cols=api.CARD_EXCLUDED_COLUMNS,
        )
        assert len(cards) == 1
        card_markdown = next(iter(cards.values()))
        assert "Professor Sir Aziz Sheikh OBE" in card_markdown
        commit_record_id_position = card_markdown.index(KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL)
        commit_request_body_position = card_markdown.index(
            KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL
        )
        assert commit_record_id_position < commit_request_body_position
        assert str(commits[-1].record_id) in card_markdown
        assert accepted_commit.model_dump_json() in card_markdown
    finally:
        api.close_backend_detour_database()
        api._release_authoritative_process_lock()


def test_captured_operator_push_generates_commit_and_exact_410_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_test_paths: BackendTestPaths,
    pytestconfig: pytest.Config,
) -> None:
    detour_root = pytestconfig.rootpath / "src" / "detours" / "detour_ai_augment"
    assert_captured_operator_push_contour(
        tmp_path,
        monkeypatch,
        backend_test_paths,
        detour_root,
    )


def test_pure_asgi_middleware_records_every_public_exchange_before_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, UUID]] = []
    response_body = json.dumps(TEST_AUTHORITATIVE_RESPONSE_BODY).encode()

    async def finite_app(
        scope: dict[str, object],
        receive: Any,
        send: Any,
    ) -> None:
        del receive
        response_code = (
            status.HTTP_200_OK
            if scope[api.ASGI_METHOD_KEY] == api.HTTP_GET_METHOD
            else status.HTTP_202_ACCEPTED
        )
        await send({
            api.ASGI_TYPE_KEY: api.ASGI_HTTP_RESPONSE_START_MESSAGE_TYPE,
            api.ASGI_STATUS_KEY: response_code,
            api.ASGI_HEADERS_KEY: [(b"content-type", b"application/json")],
        })
        await send({
            api.ASGI_TYPE_KEY: api.ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE,
            api.ASGI_BODY_KEY: response_body,
        })

    def append(record: HttpRequestLogRecord) -> None:
        events.append(("append", record.record_id))

    async def after(record: HttpRequestLogRecord) -> None:
        events.append(("after", record.record_id))

    monkeypatch.setattr(api, "AUTHORITATIVE_BACKEND_HEALTHY", True)
    monkeypatch.setattr(api, "append_authoritative_record", append)
    monkeypatch.setattr(api, "_after_authoritative_public_record", after)

    async def exchange(method: str, path: str, body: bytes) -> list[dict[str, object]]:
        request_pending = True
        sent: list[dict[str, object]] = []

        async def receive() -> dict[str, object]:
            nonlocal request_pending
            if request_pending:
                request_pending = False
                return {
                    api.ASGI_TYPE_KEY: api.ASGI_HTTP_REQUEST_MESSAGE_TYPE,
                    api.ASGI_BODY_KEY: body,
                    api.ASGI_MORE_BODY_KEY: False,
                }
            return {api.ASGI_TYPE_KEY: api.ASGI_HTTP_DISCONNECT_MESSAGE_TYPE}

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        scope = {
            api.ASGI_TYPE_KEY: api.ASGI_HTTP_SCOPE_TYPE,
            api.ASGI_METHOD_KEY: method,
            api.ASGI_PATH_KEY: path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "http_version": "1.1",
            "root_path": "",
        }
        await api._AuthoritativeHttpMiddleware(cast(Any, finite_app))(
            cast(Any, scope),
            receive,
            cast(Any, send),
        )
        return sent

    pull_messages = asyncio.run(exchange(api.HTTP_GET_METHOD, api.PULL_PATH, b""))
    push_messages = asyncio.run(
        exchange(api.HTTP_POST_METHOD, api.PUSH_PATH, TEST_AUTHORITATIVE_REQUEST_BODY)
    )

    assert pull_messages[0][api.ASGI_STATUS_KEY] == status.HTTP_200_OK
    assert push_messages[0][api.ASGI_STATUS_KEY] == status.HTTP_202_ACCEPTED
    assert [kind for kind, _record_id in events] == ["append", "after"] * 2
    record_ids = [record_id for kind, record_id in events if kind == "append"]
    assert len(set(record_ids)) == 2
    assert all(record_id.version == 7 for record_id in record_ids)


def test_authoritative_middleware_preserves_streaming_response_until_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = b'{"task":"streamed"}\n'
    records: list[HttpRequestLogRecord] = []

    async def body() -> AsyncIterator[bytes]:
        yield response_body

    async def streaming_app(
        scope: dict[str, object],
        receive: Any,
        send: Any,
    ) -> None:
        await StreamingResponse(
            body(),
            media_type=api.MEDIA_TYPE,
        )(cast(Any, scope), receive, send)

    async def after(_record: HttpRequestLogRecord) -> None:
        return None

    monkeypatch.setattr(api, "AUTHORITATIVE_BACKEND_HEALTHY", True)
    monkeypatch.setattr(api, "append_authoritative_record", records.append)
    monkeypatch.setattr(api, "_after_authoritative_public_record", after)

    async def exchange() -> list[dict[str, object]]:
        request_pending = True
        disconnected = asyncio.Event()
        sent: list[dict[str, object]] = []

        async def receive() -> dict[str, object]:
            nonlocal request_pending
            if request_pending:
                request_pending = False
                return {
                    api.ASGI_TYPE_KEY: api.ASGI_HTTP_REQUEST_MESSAGE_TYPE,
                    api.ASGI_BODY_KEY: b"",
                    api.ASGI_MORE_BODY_KEY: False,
                }
            await disconnected.wait()
            return {api.ASGI_TYPE_KEY: api.ASGI_HTTP_DISCONNECT_MESSAGE_TYPE}

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        scope = {
            api.ASGI_TYPE_KEY: api.ASGI_HTTP_SCOPE_TYPE,
            api.ASGI_METHOD_KEY: api.HTTP_GET_METHOD,
            api.ASGI_PATH_KEY: api.PULL_PATH,
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "raw_path": api.PULL_PATH.encode(),
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "http_version": "1.1",
            "root_path": "",
        }
        await asyncio.wait_for(
            api._AuthoritativeHttpMiddleware(cast(Any, streaming_app))(
                cast(Any, scope),
                receive,
                cast(Any, send),
            ),
            timeout=1,
        )
        return sent

    messages = asyncio.run(exchange())
    response_chunks = [
        message
        for message in messages
        if message[api.ASGI_TYPE_KEY] == api.ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE
    ]

    assert messages[0][api.ASGI_STATUS_KEY] == status.HTTP_200_OK
    assert response_chunks[-1].get(api.ASGI_MORE_BODY_KEY, False) is False
    assert (
        b"".join(cast(bytes, message.get(api.ASGI_BODY_KEY, b"")) for message in response_chunks)
        == response_body
    )
    assert len(records) == 1
    assert records[0].response_code == status.HTTP_200_OK
    assert records[0].response_body == response_body.decode()


def test_private_metadata_headers_are_canonical_structured_fields() -> None:
    namekey = NameKey(first_name='A. "Ada"', last_name=r"Back\slash")
    name_key_header = api.name_key_header(namekey)
    source_key_header = api._source_key_header("rollout-2xxxx.jsonl", 82)

    assert name_key_header == (
        r'ktp.first_name="A. \"Ada\"", ktp.last_name="Back\\slash"'
    )
    assert api.parse_name_key_header(name_key_header) == namekey
    assert source_key_header == (
        'ktp.filename="rollout-2xxxx.jsonl", '
        'ktp.fragment;type="line_number";line_number="82"'
    )
    assert api.parse_source_key_header(source_key_header) == (
        "rollout-2xxxx.jsonl",
        82,
    )


@pytest.mark.parametrize(
    "value",
    (
        (
            'ktp.filename="rollout.jsonl", '
            'ktp.fragment;type="line_number";line_number=82'
        ),
        (
            'ktp.filename="rollout.jsonl", '
            'ktp.fragment;line_number="82";type="line_number"'
        ),
        (
            'ktp.filename="rollout.jsonl", '
            'ktp.fragment;type="line_number";line_number="082"'
        ),
        (
            'ktp.filename="rollout.jsonl", '
            'ktp.fragment;type="line_number";line_number="0"'
        ),
        (
            'ktp.filename="nested/rollout.jsonl", '
            'ktp.fragment;type="line_number";line_number="82"'
        ),
        (
            'ktp.filename="rollout.jsonl", '
            'ktp.fragment;type="line_number";line_number="82", extra'
        ),
    ),
)
def test_source_key_header_parser_requires_the_canonical_dictionary(value: str) -> None:
    with pytest.raises(
        api._PushValidationError,
        match=Locale.REPLAY_COMMIT_SOURCE_KEY_INVALID,
    ):
        api.parse_source_key_header(value)


@pytest.mark.parametrize(
    "value",
    (
        'ktp.first_name="A.",ktp.last_name="Sheikh"',
        'ktp.last_name="Sheikh", ktp.first_name="A."',
        'ktp.first_name="A.", ktp.last_name="Sheikh", extra',
    ),
)
def test_name_key_header_parser_requires_the_canonical_dictionary(value: str) -> None:
    with pytest.raises(
        api._PushValidationError,
        match=Locale.REPLAY_COMMIT_NAME_KEY_INVALID,
    ):
        api.parse_name_key_header(value)


def test_synthetic_commit_matches_the_readme_contour_exactly(tmp_path: Path) -> None:
    rollout_path = tmp_path / TEST_ROLLOUT_FILENAME
    rollout_path.write_bytes(b'{"one":1}\n{"two":2}\n')
    rollout = api._archived_file(rollout_path)
    pull_record_id = UUID("019d0000-0000-7000-8000-000000000001")
    push_record_id = UUID("019d0000-0000-7000-8000-000000000002")
    session_id = UUID("019d0000-0000-7000-8000-000000000003")
    pull_record = persisted_http_record(
        record_id=pull_record_id,
        method=api.HTTP_GET_METHOD,
        path=api.PULL_PATH,
        response_code=status.HTTP_200_OK,
    )
    push_record = persisted_http_record(
        record_id=push_record_id,
        method=api.HTTP_POST_METHOD,
        path=api.PUSH_PATH,
        response_code=status.HTTP_202_ACCEPTED,
        request_body="{}",
    )
    report = (
        b".\n\xe2\x94\x94\xe2\x94\x80\xe2\x94\x80 OK          "
        + (TEST_ROLLOUT_FILENAME.encode())
        + b"\n"
    )

    record = api._synthetic_commit_record(
        pull_record=pull_record,
        push_record=push_record,
        session_id=session_id,
        rollout_archive=rollout,
        rollout_filename=TEST_ROLLOUT_FILENAME,
        appendwatch_report=report,
        namekey=TEST_NAMEKEY_MODEL,
    )

    assert api._validated_readme_record(record).model_dump() == record.model_dump()
    assert record.record_id.version == 7
    serialized_record = record.model_dump(mode="json", exclude={"record_id"})
    assert serialized_record == {
        "schema_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "host": "invalid",
        "port": None,
        "ready_to_respond_at_unix_usec": None,
        "path": "/commit",
        "query": "",
        "request_headers": {
            "SourceKey": (
                f'ktp.filename="{TEST_ROLLOUT_FILENAME}", '
                'ktp.fragment;type="line_number";line_number="2"'
            ),
            "NameKey": 'ktp.first_name="A.", ktp.last_name="Sheikh"',
        },
        "request_body": record.request_body,
        "response_code": None,
        "response_headers": None,
        "response_body": None,
        "received_at_unix_usec": None,
        "duration_usec": None,
    }
    assert record.request_body is not None
    assert json.loads(record.request_body) == {
        "pull_record_id": str(pull_record_id),
        "push_record_id": str(push_record_id),
        "codex_session_record": {
            "codex_session_id": str(session_id),
            "codex_rollout_record": {
                "sha256": rollout.sha256,
                "size": rollout.size,
                "line_count": rollout.line_count,
            },
            "appendwatch_report_record": {
                "encoding": "base64",
                "data": base64.b64encode(report).decode("ascii"),
            },
        },
    }
    assert record.commit_request_body.pull_record is pull_record
    assert record.commit_request_body.push_record is push_record
    assert record.commit_request_body.codex_session_record.session_id == session_id


def test_commit_request_body_contract_is_strict_canonical_and_losslessly_resolved() -> None:
    pull_record_id = UUID("019d0000-0000-7000-8000-000000000001")
    push_record_id = UUID("019d0000-0000-7000-8000-000000000002")
    session_id = UUID("019d0000-0000-7000-8000-000000000003")
    pull_record = persisted_http_record(
        record_id=pull_record_id,
        method=api.HTTP_GET_METHOD,
        path=api.PULL_PATH,
        response_code=status.HTTP_200_OK,
    )
    push_record = persisted_http_record(
        record_id=push_record_id,
        method=api.HTTP_POST_METHOD,
        path=api.PUSH_PATH,
        response_code=status.HTTP_202_ACCEPTED,
        request_body="{}",
    )
    body: dict[str, Any] = {
        "pull_record_id": str(pull_record_id),
        "push_record_id": str(push_record_id),
        "codex_session_record": {
            "codex_session_id": str(session_id),
            "codex_rollout_record": {
                "sha256": "0" * 64,
                "size": 2,
                "line_count": 1,
            },
            "appendwatch_report_record": {
                "encoding": "base64",
                "data": base64.b64encode(b".\n").decode("ascii"),
            },
        },
    }
    serialized = json.dumps(body, separators=(",", ":"))
    resolved = CommitRequestBody.from_serialized_json(
        serialized,
        resolve_http_record={
            pull_record_id: pull_record,
            push_record_id: push_record,
        }.__getitem__,
    )

    assert json.loads(resolved.model_dump_json()) == body
    assert resolved.pull_record is pull_record
    assert resolved.push_record is push_record
    assert resolved.codex_session_record.session_id == session_id
    for field in ("pull_record_id", "push_record_id", "codex_session_record"):
        invalid = {key: value for key, value in body.items() if key != field}
        with pytest.raises(ValidationError):
            CommitRequestBody.validate_serialized_json(json.dumps(invalid))
    for field in (
        "codex_session_id",
        "codex_rollout_record",
        "appendwatch_report_record",
    ):
        invalid_session = {
            key: value for key, value in body["codex_session_record"].items() if key != field
        }
        with pytest.raises(ValidationError):
            CommitRequestBody.validate_serialized_json(
                json.dumps({**body, "codex_session_record": invalid_session})
            )
        with pytest.raises(ValidationError):
            CommitRequestBody.validate_serialized_json(
                json.dumps({
                    **body,
                    "codex_session_record": {
                        **body["codex_session_record"],
                        field: None,
                    },
                })
            )
    with pytest.raises(ValidationError):
        CommitRequestBody.validate_serialized_json(json.dumps({**body, "schema_version": "1.1"}))


def test_run_outcome_snapshot_captures_fresh_rollout_and_appendwatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_id = UUID("019d0000-0000-7000-8000-000000000011")
    pull_record_id = UUID("019d0000-0000-7000-8000-000000000012")
    push_record_id = UUID("019d0000-0000-7000-8000-000000000013")
    rollout_filename = f"{api.ROLLOUT_FILENAME_PREFIX}{session_id}.jsonl"
    configuration = cast(
        api._PushConfiguration,
        SimpleNamespace(rollout_relative_path=PurePosixPath(rollout_filename)),
    )
    archive = api._ArchivedFile(
        path=tmp_path / "cas.jsonl",
        size=12,
        sha256="a" * 64,
        line_count=3,
    )
    calls: list[object] = []

    def read_appendwatch(_configuration: api._PushConfiguration) -> bytes:
        calls.append("appendwatch")
        return b".\n"

    def select_rollout(selected_session_id: UUID) -> api._PushConfiguration:
        calls.append(("rollout", selected_session_id))
        return configuration

    def copy_rollout(
        selected_configuration: api._PushConfiguration,
        _runtime: AiAugmentBackendContext,
    ) -> api._ArchivedFile:
        calls.append(("copy", selected_configuration))
        return archive

    monkeypatch.setattr(api, "BACKEND_SESSION_ID", session_id)
    pull_record = persisted_http_record(
        record_id=pull_record_id,
        method=api.HTTP_GET_METHOD,
        path=api.PULL_PATH,
        response_code=status.HTTP_200_OK,
    )
    push_record = persisted_http_record(
        record_id=push_record_id,
        method=api.HTTP_POST_METHOD,
        path=api.PUSH_PATH,
        response_code=status.HTTP_202_ACCEPTED,
        request_body="{}",
    )
    monkeypatch.setattr(api, "BACKEND_CURRENT_PULL_RECORD", pull_record)
    monkeypatch.setattr(api, "BACKEND_PENDING_PULL_RECORD", None)
    monkeypatch.setattr(api, "BACKEND_LATEST_PUSH_RECORD", push_record)
    monkeypatch.setattr(
        api,
        "_run_outcome_snapshot_configuration",
        lambda _session_id: configuration,
    )
    monkeypatch.setattr(api, "_read_appendwatch_bytes", read_appendwatch)
    monkeypatch.setattr(api, "push_configuration_for_session", select_rollout)
    monkeypatch.setattr(api, "copy_rollout_to_cas", copy_rollout)

    snapshot, filename, failures = api.capture_run_outcome_snapshot(
        cast(AiAugmentBackendContext, SimpleNamespace())
    )

    assert failures == ()
    assert filename == rollout_filename
    assert snapshot == RunOutcomeResponseBody(
        pull_record_id=pull_record_id,
        push_record_id=push_record_id,
        codex_session_record=CodexSessionRecord(
            session_id=session_id,
            codex_rollout_record=CodexRolloutRecord(
                sha256=archive.sha256,
                size=archive.size,
                line_count=archive.line_count,
            ),
            appendwatch_report_record=AppendwatchReportRecord(
                encoding=AppendwatchReportEncoding.BASE64,
                data=base64.b64encode(b".\n").decode("ascii"),
            ),
        ),
    )
    assert calls == [
        ("rollout", session_id),
        ("copy", configuration),
        "appendwatch",
    ]


@pytest.mark.parametrize(
    ("path", "snapshot", "rollout_filename", "failures", "expected_status"),
    (
        (
            run_outcome_models.COMPLETED_PATH,
            RunOutcomeResponseBody(
                pull_record_id=UUID("019d0000-0000-7000-8000-000000000022"),
                push_record_id=UUID("019d0000-0000-7000-8000-000000000023"),
                codex_session_record=CodexSessionRecord(
                    session_id=UUID("019d0000-0000-7000-8000-000000000021"),
                    codex_rollout_record=CodexRolloutRecord(
                        sha256="b" * 64,
                        size=10,
                        line_count=2,
                    ),
                    appendwatch_report_record=AppendwatchReportRecord(
                        encoding=AppendwatchReportEncoding.BASE64,
                        data=base64.b64encode(b".\n").decode("ascii"),
                    ),
                ),
            ),
            ("rollout-2026-09-07T00-00-00-019d0000-0000-7000-8000-000000000021.jsonl"),
            (),
            status.HTTP_200_OK,
        ),
        (
            run_outcome_models.FAILED_PATH,
            RunOutcomeResponseBody(
                pull_record_id=None,
                push_record_id=None,
                codex_session_record=CodexSessionRecord(
                    session_id=None,
                    codex_rollout_record=None,
                    appendwatch_report_record=None,
                ),
            ),
            None,
            (OSError("rollout unavailable"),),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ),
    ),
)
def test_run_outcome_http_exchange_is_logged_and_replays_as_raw_history(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    snapshot: RunOutcomeResponseBody,
    rollout_filename: str | None,
    failures: tuple[Exception, ...],
    expected_status: int,
) -> None:
    runtime = cast(
        AiAugmentBackendContext,
        SimpleNamespace(configured_namekey=NameKey.from_json_key(TEST_NAMEKEY)),
    )
    appended: list[HttpRequestLogRecord] = []
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    monkeypatch.setattr(
        api,
        "capture_run_outcome_snapshot",
        lambda _runtime: (snapshot, rollout_filename, failures),
    )
    monkeypatch.setattr(api, "append_authoritative_record", appended.append)
    received_at = 1_789_000_000_000_000
    request = HttpRequestLogRecord(
        schema_version="1.1",
        received_at_unix_usec=received_at,
        method=api.HTTP_POST_METHOD,
        scheme=ipc.DASHBOARD_IPC_SCHEME,
        host=ipc.DASHBOARD_IPC_HOST,
        port=None,
        path=path,
        query="",
        ready_to_respond_at_unix_usec=None,
        request_headers={
            run_outcome_models.NAME_KEY_HEADER: api.name_key_header(
                TEST_NAMEKEY_MODEL
            )
        },
        request_body=None,
        response_code=None,
        response_headers=None,
        response_body=None,
        duration_usec=None,
    )

    outcome_request = run_outcome_models.RunOutcomeRequest.from_http_request_log_record(
        request
    )
    response_record = ipc.handle_dashboard_run_outcome_request(outcome_request)

    assert response_record.response_code == expected_status
    assert response_record.response_body == snapshot.model_dump_json()
    if rollout_filename is None:
        expected_response_headers = None
    else:
        rollout = snapshot.codex_session_record.codex_rollout_record
        assert rollout is not None
        expected_response_headers = {
            SOURCE_KEY_HEADER: api._source_key_header(
                rollout_filename,
                rollout.line_count,
            )
        }
    assert response_record.response_headers == expected_response_headers
    assert len(appended) == 1
    record = appended[0]
    assert record == response_record.http_request_log_record
    validated = RunOutcomeResponse.from_http_request_log_record(record)
    assert validated.run_outcome_response_body == snapshot
    assert record.record_id.version == 7
    assert record.path == path
    assert record.request_headers == outcome_request.request_headers
    assert record.request_body is None
    assert record.response_code == expected_status
    assert record.response_body == snapshot.model_dump_json()
    assert record.received_at_unix_usec == received_at
    assert record.duration_usec is not None
    assert (record.response_headers is not None) == (rollout_filename is not None)

    connection = duckdb.connect(":memory:")
    try:
        api._initialize_readme_authoritative_schema(connection)
        api._project_readme_record(
            connection,
            runtime,
            record,
            line_number=1,
            byte_offset=100,
            line_sha256="c" * 64,
            materialize_files=False,
        )
        replayed_responses = ipc._run_outcome_records(connection)
        assert tuple(
            response.http_request_log_record for response in replayed_responses
        ) == (record,)
        assert replayed_responses[0].run_outcome_request == outcome_request
        assert replayed_responses[0].run_outcome_response_body == snapshot
        assert connection.execute(
            f"SELECT count(*) FROM {api.AUTHORITATIVE_RECORDS_TABLE}"
        ).fetchone() == (1,)
    finally:
        connection.close()


def test_failed_post_commit_work_projects_atomically_without_domain_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rollout_path = tmp_path / TEST_ROLLOUT_FILENAME
    rollout_path.write_text("{}\n", encoding=TEXT_ENCODING)
    pull_record_id = UUID("019d0000-0000-7000-8000-000000000061")
    push_record_id = UUID("019d0000-0000-7000-8000-000000000062")
    pull_record = persisted_http_record(
        record_id=pull_record_id,
        method=api.HTTP_GET_METHOD,
        path=api.PULL_PATH,
        response_code=status.HTTP_200_OK,
    )
    push_record = persisted_http_record(
        record_id=push_record_id,
        method=api.HTTP_POST_METHOD,
        path=api.PUSH_PATH,
        response_code=status.HTTP_202_ACCEPTED,
        request_body="{}",
    )
    record = api._synthetic_commit_record(
        pull_record=pull_record,
        push_record=push_record,
        session_id=UUID("019d0000-0000-7000-8000-000000000063"),
        rollout_archive=api._archived_file(rollout_path),
        rollout_filename=TEST_ROLLOUT_FILENAME,
        appendwatch_report=b".\n",
        namekey=TEST_NAMEKEY_MODEL,
    )
    failed_attempt_record = api._failed_attempt_record(
        commit_record=record,
        stage=BackendLifecycle.APPENDWATCH_REPORT_VALIDATION,
        error=RuntimeError("post-commit validation failed"),
    )
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE domain_probe (value INTEGER)")
    api._initialize_readme_authoritative_schema(connection)

    def fail_after_domain_write(
        conn: duckdb.DuckDBPyConnection,
        _runtime: AiAugmentBackendContext,
        _record: HttpRequestLogRecord,
        *,
        materialize_files: bool,
    ) -> tuple[AgentRuntimeAttemptRecord, bool]:
        assert materialize_files is True
        conn.execute("INSERT INTO domain_probe VALUES (1)")
        return failed_attempt_record, False

    monkeypatch.setattr(api, "_validate_projected_commit", fail_after_domain_write)
    try:
        api._project_readme_record(
            connection,
            cast(
                AiAugmentBackendContext,
                SimpleNamespace(
                    configured_namekey=NameKey.from_json_key(TEST_NAMEKEY)
                ),
            ),
            record,
            line_number=1,
            byte_offset=123,
            line_sha256="a" * 64,
            materialize_files=True,
        )

        assert connection.execute("SELECT * FROM domain_probe").fetchall() == []
        assert connection.execute(
            f"SELECT count(*) FROM {api.AUTHORITATIVE_RECORDS_TABLE}"
        ).fetchone() == (1,)
        assert api._projection_checkpoint(connection) == (1, 123, "a" * 64)
    finally:
        connection.close()


@pytest.mark.parametrize("action", sorted(api.ELIGIBLE_WEB_ACTIONS))
def test_direct_search_open_and_click_build_complete_ref_rows(action: str) -> None:
    index = build_test_index(action)

    assert len(index.fc_rows) == len(index.fco_rows) == len(index.turn_ref_rows) == 1
    assert index.fc_rows[0].call_id == TEST_CALL_ID
    assert set(json.loads(index.fc_rows[0].arguments_json)) & api.ELIGIBLE_WEB_ACTIONS == {action}
    assert index.fco_rows[0].fco_id == TEST_FCO_ID
    assert index.turn_ref_rows[0] == api._CodexTurnRefRow(
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
        api._CodexTurnRefRow(
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

    with pytest.raises(api._PushValidationError, match="one function call and one"):
        api.build_rollout_index(
            without_event,
            timezone_name=TEST_TIMEZONE,
            configured_rollout_basename=TEST_ROLLOUT_FILENAME,
        )

    malformed_output = list(records)
    output_value = json.loads(json.dumps(malformed_output[-1].value))
    output_value["payload"]["output"].append({"type": "input_text", "text": TEST_EXCERPT})
    malformed_output[-1] = rollout_record(output_value, malformed_output[-1].line_number)
    with pytest.raises(api._PushValidationError, match="exactly one input_text"):
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
    with pytest.raises(api._PushValidationError, match="line 2"):
        api.parse_rollout(rollout_path)


def test_submission_contract_has_nine_evidence_fields_and_optional_comments() -> None:
    without_comments = valid_submission_body(include_comments=False)
    parsed = Submission.model_validate(without_comments)

    assert tuple(column for column, _field in parsed.evidence_items()) == (
        AI_AUGMENT_EVIDENCE_COLUMNS
    )
    assert parsed.comments is None
    assert KTP_AI_AUGMENT_COMMENTS_COL not in parsed.normalized_values()

    with_comments = Submission.model_validate(valid_submission_body())
    assert with_comments.comments is not None
    assert with_comments.comments.value == EXPECTED_COMMENT

    missing = valid_submission_body()
    missing.pop(AI_AUGMENT_EVIDENCE_COLUMNS[0])
    with pytest.raises(ValidationError):
        Submission.model_validate(missing)

    absent_evidence = valid_submission_body()
    absent_evidence[AI_AUGMENT_EVIDENCE_COLUMNS[0]]["web_search_excerpts"] = []  # type: ignore[index]
    with pytest.raises(ValidationError):
        Submission.model_validate(absent_evidence)

    duplicate_evidence = valid_submission_body()
    first_field = duplicate_evidence[AI_AUGMENT_EVIDENCE_COLUMNS[0]]
    first_field["web_search_excerpts"] *= 2  # type: ignore[index]
    with pytest.raises(ValidationError):
        Submission.model_validate(duplicate_evidence)

    comments_with_evidence = valid_submission_body()
    comments_with_evidence[KTP_AI_AUGMENT_COMMENTS_COL][  # type: ignore[index]
        "web_search_excerpts"
    ] = []
    with pytest.raises(ValidationError):
        Submission.model_validate(comments_with_evidence)


def test_successful_initial_submission_converts_to_retry_model_with_placeholders() -> None:
    initial = Submission.model_validate(api.EVIDENCE_SUBMISSION_EXAMPLE)

    converted = api._standardized_initial_submission(initial)

    assert isinstance(converted, StandardizedSubmission)
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


def test_openapi_example_is_a_complete_pydantic_valid_submission(
    backend_test_paths: BackendTestPaths,
) -> None:
    assert isinstance(
        L_FEI_FEI_INITIAL_FIXTURE.submission,
        Submission,
    )
    assert (
        Submission.model_validate_json(json.dumps(api.EVIDENCE_SUBMISSION_EXAMPLE))
        == L_FEI_FEI_INITIAL_FIXTURE.submission
    )
    assert set(api.EVIDENCE_SUBMISSION_EXAMPLE) == set(AI_AUGMENT_COLUMNS)
    assert L_FEI_FEI_INITIAL_FIXTURE.identity == ("L.", "Fei-Fei")
    assert isinstance(
        L_FEI_FEI_RETRY_FIXTURE.submission,
        StandardizedSubmission,
    )
    assert api.RETRY_EVIDENCE_SUBMISSION_EXAMPLE == (
        L_FEI_FEI_RETRY_FIXTURE.submission.model_dump(by_alias=True, mode="json")
    )
    assert all(
        FIELD_STANDARDIZED_VALUE_FIELD not in field
        for column, field in api.EVIDENCE_SUBMISSION_EXAMPLE.items()
        if column in AI_AUGMENT_EVIDENCE_COLUMNS and isinstance(field, dict)
    )
    assert all(
        FIELD_STANDARDIZED_VALUE_FIELD in field
        for column, field in api.RETRY_EVIDENCE_SUBMISSION_EXAMPLE.items()
        if column in AI_AUGMENT_EVIDENCE_COLUMNS and isinstance(field, dict)
    )
    source = backend_test_paths.pydantic_to_paste.read_text(encoding="utf-8").rstrip()
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
    body[AI_AUGMENT_EVIDENCE_COLUMNS[0]] = rejected_value

    with pytest.raises(ValidationError) as raised:
        Submission.model_validate(body)

    field, reason, failed_input = api.pydantic_failure(raised.value)
    assert field == AI_AUGMENT_EVIDENCE_COLUMNS[0]
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
            for column in AI_AUGMENT_EVIDENCE_COLUMNS
        }
        submission = Submission.model_validate(body)
        validated = api.validate_submission_evidence(
            connection,
            submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
        )
        assert [
            match.evidence_number for matches in validated.values() for match in matches
        ] == list(range(1, len(AI_AUGMENT_EVIDENCE_COLUMNS) + 1))

        changed_excerpt = json.loads(json.dumps(body))
        changed_excerpt[AI_AUGMENT_EVIDENCE_COLUMNS[0]]["web_search_excerpts"][0]["excerpt"] = (
            TEST_EXCERPT[:-1] + "X"
        )
        with pytest.raises(api._PushValidationError, match="no indexed match"):
            api.validate_submission_evidence(
                connection,
                Submission.model_validate(changed_excerpt),
                rollout_filename=TEST_ROLLOUT_FILENAME,
            )

        changed_url = json.loads(json.dumps(body))
        changed_url[AI_AUGMENT_EVIDENCE_COLUMNS[0]]["web_search_excerpts"][0]["url"] = (
            TEST_URL + "/"
        )
        with pytest.raises(api._PushValidationError, match="URL does not match"):
            api.validate_submission_evidence(
                connection,
                Submission.model_validate(changed_url),
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
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, V2_CITE_TEXT),)),
        config_path=backend_test_paths.config,
    )
    try:
        assessment = api.assess_submission_evidence(
            connection,
            Submission.model_validate(submission_body_for_evidence(excerpt)),
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
    finally:
        connection.close()

    assert {item.outcome for item in assessment.items} == {expected_outcome}
    assert assessment.accepted is (expected_outcome == api.EVIDENCE_OUTCOME_V1_EXACT)
    assert sum(len(matches) for matches in assessment.validated.values()) == (
        len(AI_AUGMENT_EVIDENCE_COLUMNS) if expected_outcome == api.EVIDENCE_OUTCOME_V1_EXACT else 0
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
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, value),)),
        config_path=backend_test_paths.config,
    )
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
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, cite_text),)),
        config_path=backend_test_paths.config,
    )
    try:
        assessment = api.assess_submission_evidence(
            connection,
            Submission.model_validate(submission_body_for_evidence(excerpt)),
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
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, "Alpha Beta Gamma Delta"),)),
        config_path=backend_test_paths.config,
    )
    try:
        assessment = api.assess_submission_evidence(
            connection,
            Submission.model_validate(submission_body_for_evidence(excerpt)),
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
    finally:
        connection.close()

    assert {item.outcome for item in assessment.items} == {api.EVIDENCE_OUTCOME_UNMATCHED}
    assert assessment.accepted is False


def test_codex_v2_cannot_join_tokens_across_citation_sections(
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index((
            (TEST_URL, "Alpha Beta"),
            (TEST_URL, "Gamma Delta"),
        )),
        config_path=backend_test_paths.config,
    )
    try:
        assessment = api.assess_submission_evidence(
            connection,
            Submission.model_validate(submission_body_for_evidence("Alpha Beta Gamma Delta")),
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
    finally:
        connection.close()

    assert {item.outcome for item in assessment.items} == {api.EVIDENCE_OUTCOME_UNMATCHED}


def test_codex_v2_requires_the_exact_candidate_url(
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, V2_CITE_TEXT),)),
        config_path=backend_test_paths.config,
    )
    try:
        assessment = api.assess_submission_evidence(
            connection,
            Submission.model_validate(
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
        Submission.model_validate(submission_body_for_evidence(""))


def test_evidence_assessment_is_exhaustive_and_public_guidance_is_nonrevealing(
    backend_test_paths: BackendTestPaths,
) -> None:
    body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    failed_field = AI_AUGMENT_EVIDENCE_COLUMNS[0]
    body[failed_field]["web_search_excerpts"][0]["excerpt"] = (  # type: ignore[index]
        "Jose Garcia Senior Researcher"
    )
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, V2_CITE_TEXT),)),
        config_path=backend_test_paths.config,
    )
    try:
        assessment = api.assess_submission_evidence(
            connection,
            Submission.model_validate(body),
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        detail = api._assessment_public_detail(assessment)
    finally:
        connection.close()

    assert len(assessment.items) == len(AI_AUGMENT_EVIDENCE_COLUMNS)
    assert assessment.exact_count == len(AI_AUGMENT_EVIDENCE_COLUMNS) - 1
    assert assessment.items[0].outcome == api.EVIDENCE_OUTCOME_V2_NEAR
    assert assessment.items[-1].outcome == api.EVIDENCE_OUTCOME_V1_EXACT
    assert assessment.accepted is False
    assert f"{failed_field}.web_search_excerpts[0]" in detail
    assert TEST_CALL_ID not in detail
    assert TEST_REF_ID not in detail
    assert V2_CITE_TEXT not in detail


def test_retry_guidance_separates_exact_progress_from_blocking_contract_violations() -> None:
    submission = StandardizedSubmission.model_validate(
        standardized_submission_body(submission_body_for_evidence(V2_EXACT_EXCERPT))
    )
    assessment = api._EvidenceAssessment(
        items=tuple(
            api._EvidenceItemAssessment(
                field=field,
                index=0,
                evidence_number=evidence_number,
                submission=field_submission.web_search_excerpts[0],
                outcome=api.EVIDENCE_OUTCOME_V1_EXACT,
                match=None,
            )
            for evidence_number, (field, field_submission) in enumerate(
                submission.evidence_items(),
                start=1,
            )
        )
    )
    total = len(AI_AUGMENT_EVIDENCE_COLUMNS)
    location = f"{AI_AUGMENT_EVIDENCE_COLUMNS[0]}.web_search_excerpts[0]"
    violation = Locale.EVIDENCE_MINOR_CHANGE_ONLY_TEMPLATE.format(location=location)
    detail = api._assessment_public_detail(assessment, violations=(violation,))

    assert assessment.exact_count == total
    assert assessment.accepted is True
    assert detail.splitlines()[0] == (
        f"{total} of {total} current evidence items exactly match our records."
    )
    assert "archived rollout" not in detail
    assert Locale.EVIDENCE_REVIEW_HEADER not in detail
    assert Locale.EVIDENCE_RETRY_VIOLATION_HEADER in detail
    assert f"- {violation}" in detail


def test_v2_retry_baseline_replays_and_accepts_only_the_exact_correction(
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, V2_CITE_TEXT),)),
        config_path=backend_test_paths.config,
    )
    near_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    near_body[AI_AUGMENT_EVIDENCE_COLUMNS[0]][  # type: ignore[index]
        "web_search_excerpts"
    ][0]["excerpt"] = "Jose Garcia Senior Researcher"
    near_submission = Submission.model_validate(near_body)
    exact_submission = StandardizedSubmission.model_validate(
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
            process_retry_attempt_for_test(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY_MODEL,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-near",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission_payload=near_submission,
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
            process_retry_attempt_for_test(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY_MODEL,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-exact",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission_payload=exact_submission,
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


def test_v2_retry_rejects_changed_tokens_and_repeats_near_guidance(
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, V2_CITE_TEXT),)),
        config_path=backend_test_paths.config,
    )
    near_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    failed_field = AI_AUGMENT_EVIDENCE_COLUMNS[0]
    near_body[failed_field]["web_search_excerpts"][0]["excerpt"] = (  # type: ignore[index]
        "Jose Garcia Senior Researcher"
    )
    changed_body = json.loads(json.dumps(near_body))
    changed_body[failed_field]["web_search_excerpts"][0]["excerpt"] = "Jose Garcia Lead Researcher"
    try:
        near_submission = Submission.model_validate(near_body)
        near_assessment = api.assess_submission_evidence(
            connection,
            near_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert (
            process_retry_attempt_for_test(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY_MODEL,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-near",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission_payload=near_submission,
                assessment=near_assessment,
            )
            == ()
        )

        changed_submission = StandardizedSubmission.model_validate(
            standardized_submission_body(changed_body)
        )
        changed_assessment = api.assess_submission_evidence(
            connection,
            changed_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        changed_violations = process_retry_attempt_for_test(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY_MODEL,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-changed",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission_payload=changed_submission,
            assessment=changed_assessment,
        )
        near_retry_submission = StandardizedSubmission.model_validate(
            standardized_submission_body(near_body)
        )
        repeated_violations = process_retry_attempt_for_test(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY_MODEL,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-near-again",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission_payload=near_retry_submission,
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


def test_retry_preserves_exact_items_inside_a_rejected_field(
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, V2_CITE_TEXT),)),
        config_path=backend_test_paths.config,
    )
    field = AI_AUGMENT_EVIDENCE_COLUMNS[0]
    baseline_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    baseline_body[field]["web_search_excerpts"] = [  # type: ignore[index]
        {"excerpt": "José García", "url": TEST_URL},
        {"excerpt": "Jose Garcia Senior Researcher", "url": TEST_URL},
    ]
    changed_body = json.loads(json.dumps(baseline_body))
    changed_body[field]["web_search_excerpts"][0]["excerpt"] = "García"
    try:
        baseline_submission = Submission.model_validate(baseline_body)
        baseline_assessment = api.assess_submission_evidence(
            connection,
            baseline_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert (
            process_retry_attempt_for_test(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY_MODEL,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-baseline",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission_payload=baseline_submission,
                assessment=baseline_assessment,
            )
            == ()
        )

        changed_submission = StandardizedSubmission.model_validate(
            standardized_submission_body(changed_body)
        )
        changed_assessment = api.assess_submission_evidence(
            connection,
            changed_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        violations = process_retry_attempt_for_test(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY_MODEL,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-changed",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission_payload=changed_submission,
            assessment=changed_assessment,
        )
    finally:
        connection.close()

    assert violations == (
        Locale.EVIDENCE_EXACT_IMMUTABLE_TEMPLATE.format(
            immutable=f"{field}.web_search_excerpts[0]"
        ),
    )


def test_retry_preserves_fully_verified_fields_and_complete_evidence_counts(
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, V2_CITE_TEXT),)),
        config_path=backend_test_paths.config,
    )
    failed_field = AI_AUGMENT_EVIDENCE_COLUMNS[0]
    accepted_field = AI_AUGMENT_EVIDENCE_COLUMNS[1]
    baseline_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    baseline_body[failed_field]["web_search_excerpts"] = [  # type: ignore[index]
        {"excerpt": "José García", "url": TEST_URL},
        {"excerpt": "Jose Garcia Senior Researcher", "url": TEST_URL},
    ]
    changed_body = json.loads(json.dumps(baseline_body))
    changed_body[accepted_field]["value"] = "changed"
    changed_body[failed_field]["web_search_excerpts"].pop(0)
    try:
        baseline_submission = Submission.model_validate(baseline_body)
        baseline_assessment = api.assess_submission_evidence(
            connection,
            baseline_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert (
            process_retry_attempt_for_test(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY_MODEL,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-baseline",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission_payload=baseline_submission,
                assessment=baseline_assessment,
            )
            == ()
        )

        changed_submission = StandardizedSubmission.model_validate(
            standardized_submission_body(changed_body)
        )
        changed_assessment = api.assess_submission_evidence(
            connection,
            changed_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        violations = process_retry_attempt_for_test(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY_MODEL,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-changed",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission_payload=changed_submission,
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
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, V2_CITE_TEXT),)),
        config_path=backend_test_paths.config,
    )
    field = AI_AUGMENT_EVIDENCE_COLUMNS[0]
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
        baseline_submission = Submission.model_validate(baseline_body)
        baseline_assessment = api.assess_submission_evidence(
            connection,
            baseline_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert (
            process_retry_attempt_for_test(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY_MODEL,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-baseline",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission_payload=baseline_submission,
                assessment=baseline_assessment,
            )
            == ()
        )

        retry_submission = StandardizedSubmission.model_validate(
            standardized_submission_body(retry_body)
        )
        retry_assessment = api.assess_submission_evidence(
            connection,
            retry_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        violations = process_retry_attempt_for_test(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY_MODEL,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-retry",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission_payload=retry_submission,
            assessment=retry_assessment,
        )
    finally:
        connection.close()

    field_items = tuple(item for item in retry_assessment.items if item.field == field)
    assert field_items[1].outcome == expected_outcome
    assert retry_assessment.accepted is True
    assert violations == ()


def test_v2_near_evidence_cannot_be_withdrawn(
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, V2_CITE_TEXT),)),
        config_path=backend_test_paths.config,
    )
    field = AI_AUGMENT_EVIDENCE_COLUMNS[0]
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
        baseline_submission = Submission.model_validate(baseline_body)
        baseline_assessment = api.assess_submission_evidence(
            connection,
            baseline_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        assert (
            process_retry_attempt_for_test(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY_MODEL,
                session_id=TEST_SESSION_ID,
                attempt_id="attempt-baseline",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission_payload=baseline_submission,
                assessment=baseline_assessment,
            )
            == ()
        )

        withdrawal_submission = StandardizedSubmission.model_validate(
            standardized_submission_body(withdrawal_body)
        )
        withdrawal_assessment = api.assess_submission_evidence(
            connection,
            withdrawal_submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        violations = process_retry_attempt_for_test(
            connection,
            run_id=TEST_RUN_ID,
            namekey=TEST_NAMEKEY_MODEL,
            session_id=TEST_SESSION_ID,
            attempt_id="attempt-withdrawal",
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission_payload=withdrawal_submission,
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
    backend_test_paths: BackendTestPaths,
) -> None:
    database_path = tmp_path / "retry.duckdb"
    index = build_citation_index(((TEST_URL, V2_CITE_TEXT),))
    near_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    near_body[AI_AUGMENT_EVIDENCE_COLUMNS[0]][  # type: ignore[index]
        "web_search_excerpts"
    ][0]["excerpt"] = "Jose Garcia Senior Researcher"
    unmatched_body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    unmatched_body[AI_AUGMENT_EVIDENCE_COLUMNS[0]][  # type: ignore[index]
        "web_search_excerpts"
    ][0]["excerpt"] = "Invented evidence"

    first_connection = connect_v2_index(
        index,
        config_path=backend_test_paths.config,
        database_path=database_path,
    )
    try:
        for run_id, attempt_id, body in (
            (TEST_RUN_ID, "run-one-baseline", near_body),
            (TEST_SECOND_RUN_ID, "run-two-baseline", unmatched_body),
        ):
            submission = Submission.model_validate(body)
            assessment = api.assess_submission_evidence(
                first_connection,
                submission,
                rollout_filename=TEST_ROLLOUT_FILENAME,
                codex_match_version=2,
            )
            assert (
                process_retry_attempt_for_test(
                    first_connection,
                    run_id=run_id,
                    namekey=TEST_NAMEKEY_MODEL,
                    session_id=TEST_SESSION_ID,
                    attempt_id=attempt_id,
                    attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                    submission_payload=submission,
                    assessment=assessment,
                )
                == ()
            )
    finally:
        first_connection.close()

    second_connection = connect_v2_index(
        index,
        config_path=backend_test_paths.config,
        database_path=database_path,
    )
    try:
        exact_submission = StandardizedSubmission.model_validate(
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
                process_retry_attempt_for_test(
                    second_connection,
                    run_id=run_id,
                    namekey=TEST_NAMEKEY_MODEL,
                    session_id=TEST_SESSION_ID,
                    attempt_id=attempt_id,
                    attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                    submission_payload=exact_submission,
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
    backend_test_paths: BackendTestPaths,
) -> None:
    database_path = tmp_path / "concurrent.duckdb"
    index = build_citation_index(((TEST_URL, V2_CITE_TEXT),))
    setup_connection = connect_v2_index(
        index,
        config_path=backend_test_paths.config,
        database_path=database_path,
    )
    setup_connection.close()
    barrier = Barrier(2)

    def submit(attempt_id: str, excerpt: str) -> None:
        connection = duckdb.connect(str(database_path))
        load_duckdb_extension_from_config_path(
            connection,
            api.CODEX_TOKEN_EXTENSION,
            backend_test_paths.config,
            log=None,
        )
        try:
            plain_body = submission_body_for_evidence(excerpt)
            barrier.wait()
            with api.DETOUR_DB_LOCK:
                original_pull, _commit_record = retry_attempt_records(
                    run_id=TEST_RUN_ID,
                    session_id=TEST_SESSION_ID,
                    attempt_id=attempt_id,
                )
                retry_expected = api._retry_baseline_exists(
                    connection,
                    original_pull=original_pull,
                    namekey=TEST_NAMEKEY_MODEL,
                    session_id=TEST_SESSION_ID,
                )
                submission: Submission | StandardizedSubmission = (
                    StandardizedSubmission.model_validate(standardized_submission_body(plain_body))
                    if retry_expected
                    else Submission.model_validate(plain_body)
                )
                assessment = api.assess_submission_evidence(
                    connection,
                    submission,
                    rollout_filename=TEST_ROLLOUT_FILENAME,
                    codex_match_version=2,
                )
                assert (
                    process_retry_attempt_for_test(
                        connection,
                        run_id=TEST_RUN_ID,
                        namekey=TEST_NAMEKEY_MODEL,
                        session_id=TEST_SESSION_ID,
                        attempt_id=attempt_id,
                        attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                        submission_payload=submission,
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


def test_corrupt_applied_audit_fails_as_configuration_error(
    backend_test_paths: BackendTestPaths,
) -> None:
    connection = connect_v2_index(
        build_citation_index(((TEST_URL, V2_CITE_TEXT),)),
        config_path=backend_test_paths.config,
    )
    body = submission_body_for_evidence(V2_EXACT_EXCERPT)
    body[AI_AUGMENT_EVIDENCE_COLUMNS[0]][  # type: ignore[index]
        "web_search_excerpts"
    ][0]["excerpt"] = "Jose Garcia Senior Researcher"
    submission = Submission.model_validate(body)
    try:
        api.assess_submission_evidence(
            connection,
            submission,
            rollout_filename=TEST_ROLLOUT_FILENAME,
            codex_match_version=2,
        )
        retry_submission = StandardizedSubmission.model_validate(standardized_submission_body(body))
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
                process_retry_attempt_for_test(
                    connection,
                    run_id=TEST_RUN_ID,
                    namekey=TEST_NAMEKEY_MODEL,
                    session_id=TEST_SESSION_ID,
                    attempt_id=attempt_id,
                    attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                    submission_payload=attempted_submission,
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
            ["{}", str(deterministic_uuid7("audit-second"))],
        )

        with pytest.raises(
            api._PushConfigurationError,
            match=Locale.EVIDENCE_AUDIT_REPLAY_FAILED,
        ):
            process_retry_attempt_for_test(
                connection,
                run_id=TEST_RUN_ID,
                namekey=TEST_NAMEKEY_MODEL,
                session_id=TEST_SESSION_ID,
                attempt_id="audit-third",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission_payload=retry_submission,
                assessment=attempted_assessment,
            )
    finally:
        connection.close()


def test_historical_haanen_retry_preserves_verified_evidence_roundtrip(
    backend_test_paths: BackendTestPaths,
) -> None:
    original_body_value, archived_retry_body_value = historical_haanen_submissions(
        backend_test_paths
    )
    original_body = cast(dict[str, Any], original_body_value)
    archived_retry_body = cast(dict[str, Any], archived_retry_body_value)
    rollout_index = api.build_rollout_index(
        api.parse_rollout(backend_test_paths.haanen_accepted_rollout),
        timezone_name=TEST_TIMEZONE,
        configured_rollout_basename=HAANEN_ROLLOUT_FILENAME,
    )
    connection = connect_v2_index(
        rollout_index,
        config_path=backend_test_paths.config,
    )
    try:
        original_submission = Submission.model_validate(original_body)
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
            (KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL, 1),
        )
        assert (
            process_retry_attempt_for_test(
                connection,
                run_id=HAANEN_RUN_ID,
                namekey=HAANEN_NAMEKEY_MODEL,
                session_id=HAANEN_SESSION_ID,
                attempt_id=HAANEN_REJECTED_ATTEMPT_ID,
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission_payload=original_submission,
                assessment=original_assessment,
            )
            == ()
        )

        archived_retry = StandardizedSubmission.model_validate(archived_retry_body)
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
        archived_retry_violations = process_retry_attempt_for_test(
            connection,
            run_id=HAANEN_RUN_ID,
            namekey=HAANEN_NAMEKEY_MODEL,
            session_id=HAANEN_SESSION_ID,
            attempt_id=HAANEN_ACCEPTED_ATTEMPT_ID,
            attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
            submission_payload=archived_retry,
            assessment=archived_retry_assessment,
        )
        assert archived_retry_violations
        assert (
            Locale.EVIDENCE_COUNT_DECREASED_TEMPLATE.format(field=KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL)
            in archived_retry_violations
        )
        assert (
            Locale.EVIDENCE_ACCEPTED_FIELD_IMMUTABLE_TEMPLATE.format(
                immutable=KTP_AI_AUGMENT_GENDER_COL
            )
            in archived_retry_violations
        )
        assert (
            original_body[KTP_AI_AUGMENT_GENDER_COL][FIELD_EVIDENCE_FIELD][0][
                EVIDENCE_EXCERPT_FIELD
            ]
            == HAANEN_ORIGINAL_GENDER_EXCERPT
        )
        assert (
            archived_retry_body[KTP_AI_AUGMENT_GENDER_COL][FIELD_EVIDENCE_FIELD][0][
                EVIDENCE_EXCERPT_FIELD
            ]
            == HAANEN_RETRY_GENDER_EXCERPT
        )

        ideal_retry_body = json.loads(json.dumps(original_body, ensure_ascii=False))
        ideal_retry_body[KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL][FIELD_EVIDENCE_FIELD][1][
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
        assert changed_items == ((KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL, 1),)

        ideal_retry = StandardizedSubmission.model_validate(
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
            process_retry_attempt_for_test(
                connection,
                run_id=HAANEN_RUN_ID,
                namekey=HAANEN_NAMEKEY_MODEL,
                session_id=HAANEN_SESSION_ID,
                attempt_id=f"{HAANEN_ACCEPTED_ATTEMPT_ID}-ideal",
                attempt_timestamp=TEST_ATTEMPT_TIMESTAMP,
                submission_payload=ideal_retry,
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
        (str(deterministic_uuid7(HAANEN_REJECTED_ATTEMPT_ID)), True, False),
        (str(deterministic_uuid7(HAANEN_ACCEPTED_ATTEMPT_ID)), False, False),
        (
            str(deterministic_uuid7(f"{HAANEN_ACCEPTED_ATTEMPT_ID}-ideal")),
            True,
            True,
        ),
    ]


@pytest.mark.skip(reason="multiple evidence matches are currently allowed")
def test_multiple_sql_matches_report_the_exact_excerpt() -> None:
    connection = duckdb.connect(":memory:")
    try:
        index = build_test_index()
        duplicate_call_id = "call_duplicate"
        duplicate_index = api._RolloutIndex(
            session=index.session,
            fc_rows=index.fc_rows
            + (
                api._CodexFcRow(
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
                api._CodexFcoRow(
                    timestamp=index.fco_rows[0].timestamp,
                    fco_id="fco_duplicate",
                    call_id=duplicate_call_id,
                ),
            ),
            turn_ref_rows=index.turn_ref_rows
            + (
                api._CodexTurnRefRow(
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
            for column in AI_AUGMENT_EVIDENCE_COLUMNS
        }

        with pytest.raises(api._MultipleEvidenceMatches) as raised:
            api.validate_submission_evidence(
                connection,
                Submission.model_validate(body),
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

        def choose_search(candidates: tuple[api._EvidenceCandidate, ...]) -> api._EvidenceCandidate:
            offered_ref_ids.append(tuple(candidate.ref_id for candidate in candidates))
            return next(candidate for candidate in candidates if candidate.ref_id == TEST_REF_ID)

        monkeypatch.setattr(api, "EVIDENCE_RANDOM", SimpleNamespace(choice=choose_search))
        body = {
            column: {
                "value": column,
                "web_search_excerpts": [{"excerpt": TEST_EXCERPT, "url": TEST_URL}],
            }
            for column in AI_AUGMENT_EVIDENCE_COLUMNS
        }

        validated = api.validate_submission_evidence(
            connection,
            Submission.model_validate(body),
            rollout_filename=TEST_ROLLOUT_FILENAME,
        )

        matches = [match for field_matches in validated.values() for match in field_matches]
        assert {match.ref_id for match in matches} == {TEST_REF_ID}
        assert offered_ref_ids == [(TEST_REF_ID, TEST_VIEW_REF_ID)] * len(
            AI_AUGMENT_EVIDENCE_COLUMNS
        )
    finally:
        connection.close()


def test_seeded_evidence_selection_round_trips_deterministically(
    tmp_path: Path,
    backend_test_paths: BackendTestPaths,
) -> None:
    database_path = tmp_path / "evidence.duckdb"
    index = build_duplicate_evidence_index()
    submission = Submission.model_validate({
        column: {
            "value": column,
            "web_search_excerpts": [{"excerpt": TEST_EXCERPT, "url": TEST_URL}],
        }
        for column in AI_AUGMENT_EVIDENCE_COLUMNS
    })
    sample_seed = PipelineConfig.from_json(backend_test_paths.config).sample_seed
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
    assert len(selections[0]) == len(AI_AUGMENT_EVIDENCE_COLUMNS)
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
    with pytest.raises(api._PushValidationError):
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

    with pytest.raises(api._PushValidationError):
        api.parse_appendwatch_report(report_path, TEST_ROLLOUT_RELATIVE_PATH)


def test_configured_replay_log_hash_is_enforced_on_each_backend_start(
    tmp_path: Path,
    backend_test_paths: BackendTestPaths,
) -> None:
    release_map = tmp_path / "release-map.csv"
    replay_log = tmp_path / "replay.jsonl"
    release_map.write_text("draw,batch\n1,1\n", encoding=TEXT_ENCODING)
    replay_log.write_text('{"first":true}\n', encoding=TEXT_ENCODING)
    config_data = json.loads(
        backend_test_paths.ai_augment_config.read_text(encoding=TEXT_ENCODING)
    )
    config_data["files_config"][MAP_SUBSET_0_TO_BATCH_KEY] = {
        RESOURCE_PATH_KEY: str(release_map),
        RESOURCE_SHA256_KEY: hashlib.sha256(release_map.read_bytes()).hexdigest(),
        RESOURCE_DESCRIPTION_KEY: "isolated release map",
    }
    config_data["files_config"][REPLAY_LOG_KEY] = {
        RESOURCE_PATH_KEY: str(replay_log),
        RESOURCE_SHA256_KEY: hashlib.sha256(replay_log.read_bytes()).hexdigest(),
        RESOURCE_DESCRIPTION_KEY: "isolated authoritative log",
    }

    configured = AiAugmentDetourConfig.model_validate(config_data)

    assert all(
        resource.verify_hash_on_init
        for resource in configured.resources.registered_resources
    )
    replay_log.write_text('{"changed":true}\n', encoding=TEXT_ENCODING)
    with pytest.raises(ValidationError):
        AiAugmentDetourConfig.model_validate(config_data)


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
    with pytest.raises(api._PushConfigurationError):
        api.push_configuration()


def test_aivm_identity_file_must_be_configured_explicitly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lima_config = tmp_path / "ssh.config"
    write_text(lima_config, "fixture\n")
    monkeypatch.setattr(api, "APPENDWATCH_REPORT", "/mounted/appendwatch-tree.txt")
    monkeypatch.setattr(api, "LIMA_SSH_CONFIG_PATH", lima_config)
    monkeypatch.setattr(api, "AIVM_IDENTITY_FILE", None)

    with pytest.raises(
        api._PushConfigurationError,
        match=api.AIVM_IDENTITY_FILE_ENV_NAME,
    ):
        api.push_configuration(TEST_ROLLOUT_GUEST_PATH)


def test_session_rollout_discovery_uses_restricted_audit_principal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = UUID("019fa457-aac5-7652-8669-9d571206e7cb")
    rollout = api.CODEX_SESSIONS_ROOT / JULY_ROLLOUT_RELATIVE_PATH
    deployment_files = [
        tmp_path / "identity",
        tmp_path / "known-hosts",
        tmp_path / "ssh.config",
    ]
    for path in deployment_files:
        write_text(path, "fixture\n")
    monkeypatch.setattr(api, "APPENDWATCH_REPORT", "/mounted/appendwatch-tree.txt")
    monkeypatch.setattr(api, "AIVM_IDENTITY_FILE", deployment_files[0])
    monkeypatch.setattr(api, "AIVM_KNOWN_HOSTS_FILE", deployment_files[1])
    monkeypatch.setattr(api, "LIMA_SSH_CONFIG_PATH", deployment_files[2])
    observed: list[str] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        observed.extend(command)
        assert kwargs["check"] is True
        return SimpleNamespace(stdout=f"{rollout}\n", stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", run)

    configured = api.push_configuration_for_session(session_id)

    assert configured.ssh_user == api.AIVM_AUDIT_USER
    assert configured.ssh_target == f"{api.AIVM_INSTANCE}-{api.AIVM_AUDIT_USER}"
    assert f"User={api.AIVM_AUDIT_USER}" in observed
    assert observed[-1] == f"{api.AUDIT_FIND_ROLLOUT_COMMAND} {session_id}"
    assert configured.rollout_guest_path == str(rollout)


def test_audit_ssh_uses_pinned_identity_and_counts_physical_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_test_paths: BackendTestPaths,
) -> None:
    report_path = tmp_path / "report.txt"
    identity_path = tmp_path / "identity"
    known_hosts_path = tmp_path / "known_hosts"
    lima_config_path = tmp_path / "ssh.config"
    for path in (report_path, identity_path, known_hosts_path, lima_config_path):
        write_text(path, "fixture\n")
    configuration = api._PushConfiguration(
        rollout_guest_path=TEST_ROLLOUT_GUEST_PATH,
        rollout_relative_path=TEST_ROLLOUT_RELATIVE_PATH,
        appendwatch_report=PurePosixPath("/mounted/appendwatch-tree.txt"),
        lima_ssh_config=lima_config_path,
        identity_file=identity_path,
        known_hosts_file=known_hosts_path,
        ssh_user="aivm-audit",
        ssh_target="aivm-aivm-audit",
        host_key_alias="lima-aivm-aivm-audit",
    )
    runtime = runtime_for_test(tmp_path, backend_test_paths)
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: object) -> None:
        captured["command"] = command
        captured["kwargs"] = kwargs
        cast(Any, kwargs["stdout"]).write(b"first\nsecond")

    monkeypatch.setattr(subprocess, "run", fake_run)
    archived = api.copy_rollout_to_cas(configuration, runtime)

    command = captured["command"]
    assert command[0] == api.SSH_EXECUTABLE
    assert f"IdentityFile={identity_path}" in command
    assert f"UserKnownHostsFile={known_hosts_path}" in command
    assert f"User={configuration.ssh_user}" in command
    assert f"HostKeyAlias={configuration.host_key_alias}" in command
    assert "StrictHostKeyChecking=accept-new" in command
    assert command[-2] == configuration.ssh_target
    assert command[-1] == (f"{api.AUDIT_READ_ROLLOUT_COMMAND} {TEST_ROLLOUT_RELATIVE_PATH}")
    assert "shell" not in captured["kwargs"]
    assert archived.line_count == 2
    assert archived.path == (
        runtime.pipeline_config.rollout_cas_dir
        / api.ROLLOUT_CAS_FILENAME_TEMPLATE.format(sha256=archived.sha256)
    )


@pytest.mark.parametrize(
    "raw_namekey",
    (
        TEST_NAMEKEY,
        '{"ktp.first_name":"A.","ktp.last_name":"Sheikh"}',
        '{"ktp.last_name":"Sheikh","ktp.first_name":"A."}',
        '{  "ktp.first_name" : "A." ,  "ktp.last_name" : "Sheikh"  }',
    ),
)
def test_configured_namekey_normalizes_equivalent_json(
    monkeypatch: pytest.MonkeyPatch,
    raw_namekey: str,
) -> None:
    monkeypatch.setenv(api.NAMEKEY_ENV_NAME, raw_namekey)

    assert api._configured_namekey() == NameKey.from_json_key(TEST_NAMEKEY)


@pytest.mark.parametrize(
    "raw_namekey",
    (
        "not-json",
        '{"ktp.first_name":"A."}',
    ),
)
def test_configured_namekey_rejects_malformed_or_incomplete_json(
    monkeypatch: pytest.MonkeyPatch,
    raw_namekey: str,
) -> None:
    monkeypatch.setenv(api.NAMEKEY_ENV_NAME, raw_namekey)

    with pytest.raises(
        api._PushConfigurationError,
        match=Locale.CONFIGURED_NAMEKEY_MALFORMED,
    ):
        api._configured_namekey()


def ai_augment_outerdict(
    first_name: str,
    last_name: str,
    *,
    cohort: AiAugmentCohort = AiAugmentCohort.GROUND_TRUTH,
    ineligibility_category: AiAugmentIneligibilityCategory | None = None,
) -> AiAugmentOuterDict:
    namekey = NameKey(first_name=first_name, last_name=last_name)
    xlsx_innerdict = InnerDict.from_mapping(
        {
            KTP_NAMEKEY_COL: namekey.to_json_key(),
            KTP_FIRST_NAME_COL: first_name,
            KTP_LAST_NAME_COL: last_name,
            DRAW_LABEL: "1",
        },
        XlsxMatchProcedure(),
    )
    return AiAugmentOuterDict(
        namekey=namekey,
        xlsx_innerdicts=(xlsx_innerdict,),
        ssn_innerdicts=(),
        docx_innerdicts=(),
        ai_augment_rnd=1,
        ai_augment_cohort=cohort,
        ai_augment_ineligibility_category=ineligibility_category,
    )


def test_backend_singleton_lock_is_independent_of_replay_log(
    tmp_path: Path,
) -> None:
    lock_path = api.BACKEND_PROCESS_LOCK_PATH
    holder = subprocess.Popen(
        (
            sys.executable,
            "-c",
            (
                "import fcntl, os, sys; "
                "descriptor = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600); "
                "fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB); "
                "print('locked', flush=True); sys.stdin.read(1)"
            ),
            str(lock_path),
        ),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "locked"
    try:
        with pytest.raises(
            api._PushConfigurationError,
            match=Locale.BACKEND_ALREADY_RUNNING,
        ):
            api._acquire_backend_process_lock()
    finally:
        assert holder.stdin is not None
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=5)

    api._acquire_backend_process_lock()
    assert api.BACKEND_PROCESS_LOCK_DESCRIPTOR is not None
    api._release_backend_process_lock()
    assert api.BACKEND_PROCESS_LOCK_DESCRIPTOR is None


def test_backend_startup_prepares_source_rows_for_initial_pull(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_test_paths: BackendTestPaths,
) -> None:
    base_runtime = runtime_for_test(tmp_path, backend_test_paths)
    outerdict = ai_augment_outerdict("A.", "Sheikh")
    factory_calls: list[AiAugmentBackendContext] = []

    def outerdicts_factory(
        context: AiAugmentBackendContext,
    ) -> tuple[AiAugmentOuterDict, ...]:
        factory_calls.append(context)
        return (outerdict,)

    monkeypatch.setenv(api.NAMEKEY_ENV_NAME, TEST_NAMEKEY)
    monkeypatch.setattr(
        AiAugmentDetourConfig,
        "from_json",
        lambda _path, *, verify_hash_on_init=True: base_runtime.pipeline_config,
    )
    monkeypatch.setattr(
        AiAugmentBackendContext,
        "ai_augment_outerdicts_factory",
        outerdicts_factory,
    )

    runtime = api.configure_runtime(backend_test_paths.ai_augment_config)

    assert factory_calls == [runtime]
    assert runtime.configured_ai_augment_outerdict() is outerdict

    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    monkeypatch.setattr(
        api,
        "StreamingResponse",
        lambda content, *, media_type: Response(
            content="".join(content),
            media_type=media_type,
        ),
    )
    monkeypatch.setattr(api, "BACKEND_LIFECYCLE", BackendLifecycle.READY)
    response = api.authoritative_pull()

    assert factory_calls == [runtime]
    assert response.status_code == status.HTTP_200_OK
    assert response.body == "".join(api.configured_pull_lines(outerdict)).encode()


def test_ipc_only_runtime_prepares_projection_without_a_namekey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_test_paths: BackendTestPaths,
) -> None:
    base_runtime = runtime_for_test(tmp_path, backend_test_paths)
    outerdict = ai_augment_outerdict("A.", "Sheikh")
    monkeypatch.delenv(api.NAMEKEY_ENV_NAME, raising=False)
    monkeypatch.setattr(
        AiAugmentDetourConfig,
        "from_json",
        lambda _path, *, verify_hash_on_init=True: base_runtime.pipeline_config,
    )
    monkeypatch.setattr(
        AiAugmentBackendContext,
        "ai_augment_outerdicts_factory",
        lambda *_args, **_kwargs: (outerdict,),
    )

    runtime = api.configure_runtime(
        backend_test_paths.ai_augment_config,
        require_namekey=False,
    )

    assert runtime.configured_namekey is None
    assert runtime.configured_ai_augment_outerdict() is None
    assert runtime.ai_augment_outerdicts == (outerdict,)


def test_ipc_only_query_defers_configuration_and_uses_read_only_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_test_paths: BackendTestPaths,
) -> None:
    config_path = tmp_path / "config.json"
    outerdict = ai_augment_outerdict("A.", "Sheikh")
    runtime = runtime_for_test(tmp_path, backend_test_paths).model_copy(
        update={"cached_ai_augment_outerdicts": (outerdict,)}
    )
    calls: list[object] = []

    class ReadOnlyConnection:
        def close(self) -> None:
            calls.append("close")

    connection = cast(duckdb.DuckDBPyConnection, ReadOnlyConnection())

    def configure(
        selected_path: Path,
        *,
        require_namekey: bool,
        verify_hash_on_init: bool,
    ) -> None:
        calls.append(
            ("configure", selected_path, require_namekey, verify_hash_on_init)
        )

    def open_database(
        selected_runtime: AiAugmentBackendContext,
        *,
        read_only: bool = False,
    ) -> duckdb.DuckDBPyConnection:
        assert selected_runtime is runtime
        calls.append(("open", read_only))
        return connection

    def configured_runtime() -> AiAugmentBackendContext:
        calls.append("runtime")
        return runtime

    def attempts(
        selected_runtime: AiAugmentBackendContext,
        selected_connection: duckdb.DuckDBPyConnection,
        *,
        namekey: NameKey | None,
    ) -> tuple[AgentRuntimeAttemptRecord, ...]:
        assert selected_runtime is runtime
        assert namekey is None or namekey == TEST_NAMEKEY_MODEL
        calls.append(("attempts", selected_connection))
        return ()

    def committed_innerdicts(
        selected_connection: duckdb.DuckDBPyConnection,
    ) -> tuple[object, ...]:
        calls.append(("committed", selected_connection))
        return ()

    monkeypatch.setattr(api, "configure_runtime", configure)
    monkeypatch.setattr(api, "runtime_configuration", configured_runtime)
    monkeypatch.setattr(api, "open_detour_database", open_database)
    monkeypatch.setattr(api, "_attempt_records", attempts)
    monkeypatch.setattr(api, "_committed_innerdicts", committed_innerdicts)
    monkeypatch.setattr(ipc, "_run_outcome_records", lambda _connection: ())

    query = ipc.build_ipc_only_dashboard_query_payload_callback(config_path)

    assert calls == []
    first = QueryResponse.from_serialized_json(query(None))
    second = QueryResponse.from_serialized_json(query(TEST_NAMEKEY_MODEL))
    assert tuple(
        value.serialize() for value in first.ai_augment_outerdicts
    ) == (outerdict.serialize(),)
    assert tuple(
        value.serialize() for value in second.ai_augment_outerdicts
    ) == (outerdict.serialize(),)
    assert calls == [
        ("configure", config_path, False, True),
        "runtime",
        ("open", True),
        ("committed", connection),
        ("attempts", connection),
        "close",
        "runtime",
        ("open", True),
        ("committed", connection),
        ("attempts", connection),
        "close",
    ]


def test_detour_database_open_modes_are_explicit_and_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_test_paths: BackendTestPaths,
) -> None:
    runtime = runtime_for_test(tmp_path, backend_test_paths)
    connection = cast(
        duckdb.DuckDBPyConnection,
        SimpleNamespace(close=lambda: None),
    )
    calls: list[tuple[str, bool]] = []
    extension_calls: list[tuple[duckdb.DuckDBPyConnection, str, object, object]] = []

    def connect(path: str, *, read_only: bool) -> duckdb.DuckDBPyConnection:
        calls.append((path, read_only))
        if not read_only:
            raise duckdb.IOException("permission denied")
        return connection

    def load_extension(
        selected_connection: duckdb.DuckDBPyConnection,
        extension: str,
        config: object,
        *,
        log: object,
    ) -> None:
        extension_calls.append((selected_connection, extension, config, log))

    monkeypatch.setattr(duckdb, "connect", connect)
    monkeypatch.setattr(api, "load_duckdb_extension", load_extension)

    assert api.open_detour_database(runtime, read_only=True) is connection
    with pytest.raises(api._PushValidationError) as exc_info:
        api.open_detour_database(runtime)

    assert calls == [
        (str(runtime.pipeline_config.detour_db_path), True),
        (str(runtime.pipeline_config.detour_db_path), False),
    ]
    assert extension_calls == [
        (
            connection,
            api.CODEX_TOKEN_EXTENSION,
            runtime.pipeline_config.duckdb_extensions.get(api.CODEX_TOKEN_EXTENSION),
            None,
        )
    ]
    assert str(exc_info.value) == Locale.DETOUR_DUCKDB_OPEN_FAILED
    assert "read/write mode" in str(exc_info.value)

    def denied_connect(*_args: object, **_kwargs: object) -> None:
        raise duckdb.IOException("permission denied")

    monkeypatch.setattr(duckdb, "connect", denied_connect)
    with pytest.raises(api._PushValidationError) as read_only_exc_info:
        api.open_detour_database(runtime, read_only=True)
    assert str(read_only_exc_info.value) == Locale.DETOUR_DUCKDB_READ_ONLY_OPEN_FAILED


def test_configured_namekey_population_accepts_exact_eligible_match() -> None:
    outerdict = ai_augment_outerdict("Gaoquan ", "Shi")

    assert api._configured_ai_augment_outerdict(
        outerdict.namekey,
        (outerdict,),
    ) is outerdict


def test_configured_namekey_population_reports_exact_ineligibility_category() -> None:
    category = AiAugmentIneligibilityCategory.STAGING_PARTITION_2
    outerdict = ai_augment_outerdict(
        "Gaoquan ",
        "Shi",
        cohort=AiAugmentCohort.INELIGIBLE,
        ineligibility_category=category,
    )

    with pytest.raises(api._PushConfigurationError) as exc_info:
        api._configured_ai_augment_outerdict(
            outerdict.namekey,
            (outerdict,),
        )

    assert str(exc_info.value) == Locale.CONFIGURED_NAMEKEY_INELIGIBLE_TEMPLATE.format(
        category=category.value
    )


def test_configured_namekey_population_suggests_exact_trailing_space_match() -> None:
    outerdict = ai_augment_outerdict("Gaoquan ", "Shi")
    configured_namekey = ai_augment_outerdict("Gaoquan", "Shi").namekey

    with pytest.raises(api._PushConfigurationError) as exc_info:
        api._configured_ai_augment_outerdict(configured_namekey, (outerdict,))

    assert str(exc_info.value) == Locale.CONFIGURED_NAMEKEY_NOT_FOUND_SUGGESTIONS_TEMPLATE.format(
        suggestions=outerdict.namekey.to_json_key()
    )


def test_configured_namekey_population_sorts_multiple_whitespace_suggestions() -> None:
    outerdicts = (
        ai_augment_outerdict("Gaoquan ", "Shi"),
        ai_augment_outerdict(" Gaoquan", "Shi"),
    )
    configured_namekey = ai_augment_outerdict("Gaoquan", "Shi").namekey
    suggestions = " or ".join(
        sorted(outerdict.namekey.to_json_key() for outerdict in outerdicts)
    )

    with pytest.raises(api._PushConfigurationError) as exc_info:
        api._configured_ai_augment_outerdict(configured_namekey, outerdicts)

    assert str(exc_info.value) == Locale.CONFIGURED_NAMEKEY_NOT_FOUND_SUGGESTIONS_TEMPLATE.format(
        suggestions=suggestions
    )


def test_configured_namekey_population_reports_unrelated_unknown_without_suggestion() -> None:
    outerdict = ai_augment_outerdict("Gaoquan ", "Shi")
    configured_namekey = ai_augment_outerdict("Gaoquan", "Shih").namekey

    with pytest.raises(api._PushConfigurationError) as exc_info:
        api._configured_ai_augment_outerdict(configured_namekey, (outerdict,))

    assert str(exc_info.value) == Locale.CONFIGURED_NAMEKEY_NOT_FOUND


def test_required_config_and_source_database_are_read_only(
    tmp_path: Path,
    backend_test_paths: BackendTestPaths,
) -> None:
    with pytest.raises(SystemExit):
        server.parse_args([])
    arguments = server.parse_args(["--config", str(backend_test_paths.config)])
    assert arguments.config == backend_test_paths.config
    assert arguments.ipc_only is False
    assert (
        server.parse_args([
            "--config",
            str(backend_test_paths.config),
            server.IPC_ONLY_OPTION,
        ]).ipc_only
        is True
    )
    replay_log = tmp_path / "configured-replay.jsonl"
    replay_log.write_text("", encoding=TEXT_ENCODING)
    config_data = json.loads(
        backend_test_paths.ai_augment_config.read_text(encoding=TEXT_ENCODING)
    )
    config_data["db_file"] = str(backend_test_paths.source_database)
    config_data["files_config"][REPLAY_LOG_KEY] = {
        RESOURCE_PATH_KEY: str(replay_log),
        RESOURCE_SHA256_KEY: hashlib.sha256(b"").hexdigest(),
        RESOURCE_DESCRIPTION_KEY: "isolated authoritative log",
    }
    configured = AiAugmentDetourConfig.model_validate(
        config_data,
        context={"verify_hash_on_init": False},
    )
    assert configured.detour_db_path == backend_test_paths.source_database.with_name(
        "scisci_process__detour_ai-augment.duckdb"
    )

    runtime = runtime_for_test(tmp_path, backend_test_paths)
    before = file_signature(backend_test_paths.source_database)
    connection = api.open_source_database(runtime)
    try:
        with pytest.raises(duckdb.Error):
            connection.execute("CREATE TABLE forbidden_write (id INTEGER)")
    finally:
        connection.close()
    assert file_signature(backend_test_paths.source_database) == before


def test_main_ipc_only_runs_only_the_dashboard_query_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    calls: list[object] = []

    monkeypatch.setattr(api, "_acquire_backend_process_lock", lambda: calls.append("acquire"))
    monkeypatch.setattr(api, "_release_backend_process_lock", lambda: calls.append("release"))
    monkeypatch.setattr(
        ipc,
        "serve_dashboard_query_only",
        lambda selected_path, *, verify_hash_on_init: calls.append(
            ("ipc", selected_path, verify_hash_on_init)
        ),
    )
    monkeypatch.setattr(
        api,
        "configure_runtime",
        lambda *_args, **_kwargs: pytest.fail("full Backend configuration must not start"),
    )
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Uvicorn must not start in IPC-only mode"),
    )

    server.main(["--config", str(config_path), server.IPC_ONLY_OPTION])

    assert calls == ["acquire", ("ipc", config_path, True), "release"]


def test_main_full_mode_configures_and_runs_composed_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    calls: list[object] = []

    def compose() -> FastAPI:
        calls.append("compose")
        return api.app

    monkeypatch.setattr(api, "_acquire_backend_process_lock", lambda: calls.append("acquire"))
    monkeypatch.setattr(api, "_release_backend_process_lock", lambda: calls.append("release"))
    monkeypatch.setattr(
        api,
        "configure_runtime",
        lambda selected_path, *, verify_hash_on_init: calls.append(
            ("configure", selected_path, verify_hash_on_init)
        ),
    )
    monkeypatch.setattr(
        server,
        "full_backend_application",
        compose,
    )
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda application, *, host, port: calls.append(("serve", application, host, port)),
    )

    server.main(["--config", str(config_path)])

    assert calls == [
        "acquire",
        ("configure", config_path, True),
        "compose",
        ("serve", api.app, api.SERVER_HOST, api.SERVER_PORT),
        "release",
    ]


def test_ipc_only_ctrl_c_stops_server_and_closes_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    calls: list[object] = []

    class InterruptibleThread:
        @staticmethod
        def join() -> None:
            calls.append("wait")
            raise KeyboardInterrupt

    ipc_server = SimpleNamespace(thread=InterruptibleThread())
    monkeypatch.setattr(
        ipc,
        "start_dashboard_query_server",
        lambda *_args, **_kwargs: ipc_server,
    )
    monkeypatch.setattr(
        ipc,
        "stop_dashboard_query_server",
        lambda handle: calls.append(("stop", handle)),
    )
    monkeypatch.setattr(
        api,
        "close_backend_detour_database",
        lambda: calls.append("close-database"),
    )

    ipc.serve_dashboard_query_only(config_path)

    assert calls == ["wait", ("stop", ipc_server), "close-database"]


def test_repeated_researcher_rows_materialize_as_distinct_innerdicts() -> None:
    connection = duckdb.connect(":memory:")
    try:

        def output_row(fragment: int, attempt_id: str) -> dict[str, object]:
            values: dict[str, object] = {
                column: f"value for {column}" for column, _data_type in api.CODEX_OUTPUT_SCHEMA
            }
            values.update({
                KTP_NAMEKEY_COL: TEST_NAMEKEY,
                KTP_FILENAME_COL: TEST_ROLLOUT_FILENAME,
                KTP_FRAGMENT_COL: fragment,
                KTP_FRAGMENT_TYPE_COL: api.ROLLOUT_LINE_FRAGMENT_TYPE,
                DRAW_LABEL: api.TARGET_DRAW_NUMBER,
                KTP_FIRST_NAME_COL: "A.",
                KTP_LAST_NAME_COL: "Sheikh",
                KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL: attempt_id,
                KTP_AI_AUGMENT_COMMENTS_COL: None,
            })
            return values

        api.append_codex_output(connection, output_row(100, "attempt-1"))
        api.append_codex_output(connection, output_row(101, "attempt-2"))
        innerdicts_row = connection.execute(
            f"SELECT {duckdb_quote_identifier(KTP_INNERDICT_JSONLINES_COL)} "
            f"FROM {api.CODEX_INNERDICT_TABLE}"
        ).fetchone()
        assert innerdicts_row is not None
        innerdicts_text = innerdicts_row[0]
        innerdicts = tuple(json.loads(line) for line in innerdicts_text.splitlines())
        assert [row[KTP_FRAGMENT_COL] for row in innerdicts] == [100, 101]
        assert [row[KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL] for row in innerdicts] == [
            "attempt-1",
            "attempt-2",
        ]

        with pytest.raises(api._PushValidationError, match="already accepted"):
            api.append_codex_output(connection, output_row(101, "attempt-3"))
    finally:
        connection.close()


def test_push_acceptance_changes_state_before_post_commit_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pull_record_id = UUID("019d0000-0000-7000-8000-000000000010")
    pull_record = persisted_http_record(
        record_id=pull_record_id,
        method=api.HTTP_GET_METHOD,
        path=api.PULL_PATH,
        response_code=status.HTTP_200_OK,
    )
    session_id = UUID("019d0000-0000-7000-8000-000000000011")
    monkeypatch.setattr(api, "BACKEND_LIFECYCLE", BackendLifecycle.READY)
    monkeypatch.setattr(api, "BACKEND_CURRENT_PULL_RECORD", pull_record)
    monkeypatch.setattr(api, "BACKEND_PENDING_PULL_RECORD", None)
    monkeypatch.setattr(api, "BACKEND_ATTEMPT_RECORD", None)
    monkeypatch.setattr(api, "BACKEND_SESSION_ID", session_id)

    response = asyncio.run(api.authoritative_push(cast(Any, None)))

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.headers[api.LOCATION_HEADER] == api.PULL_PATH
    assert api.BACKEND_LIFECYCLE is BackendLifecycle.BUSY
    assert api.BACKEND_PENDING_PULL_RECORD is pull_record
    assert api.BACKEND_CURRENT_PULL_RECORD is None

    duplicate = asyncio.run(api.authoritative_push(cast(Any, None)))

    assert duplicate.status_code == status.HTTP_409_CONFLICT
    assert duplicate.headers[api.LOCATION_HEADER] == api.PULL_PATH


def test_retry_push_requires_a_persisted_current_pull_before_acceptance(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    prior_pending_pull_record_id = UUID("019d0000-0000-7000-8000-000000000030")
    current_pull_record_id = UUID("019d0000-0000-7000-8000-000000000031")
    session_id = UUID("019d0000-0000-7000-8000-000000000032")
    prior_pending_pull, prior_commit = retry_attempt_records(
        run_id=prior_pending_pull_record_id,
        session_id=session_id,
        attempt_id="prior-retry",
    )
    prior_attempt_record = AgentRuntimeAttemptRecord(
        attempt=AgentRuntimeAttempt(
            pull_record=prior_pending_pull,
            commit_record=prior_commit,
            post_commit_validation=PostCommitValidation(
                stage=BackendLifecycle.PYDANTIC_VALIDATION,
                result=BackendLifecycle.REJECTED,
                detail="retry",
            ),
        ),
        submission=None,
        ground_truth_innerdict=None,
    )
    monkeypatch.setattr(api, "BACKEND_LIFECYCLE", BackendLifecycle.RETRY)
    monkeypatch.setattr(api, "BACKEND_CURRENT_PULL_RECORD", None)
    monkeypatch.setattr(
        api,
        "BACKEND_PENDING_PULL_RECORD",
        prior_pending_pull,
    )
    monkeypatch.setattr(api, "BACKEND_ATTEMPT_RECORD", prior_attempt_record)
    monkeypatch.setattr(api, "BACKEND_SESSION_ID", session_id)
    request = cast(Any, object())

    premature = asyncio.run(api.authoritative_push(request))

    assert premature.status_code == status.HTTP_409_CONFLICT
    assert premature.headers[api.LOCATION_HEADER] == api.PULL_PATH
    assert json.loads(bytes(premature.body)) == {"detail": Locale.CONFIGURATION_ERROR_DETAIL}
    assert api.BACKEND_LIFECYCLE is BackendLifecycle.RETRY
    assert api.BACKEND_CURRENT_PULL_RECORD is None
    assert api.BACKEND_PENDING_PULL_RECORD is prior_pending_pull
    assert api.BACKEND_ATTEMPT_RECORD is prior_attempt_record
    assert Locale.PUSH_CURRENT_PULL_REQUIRED_LOG in caplog.messages

    persisted_pull = HttpRequestLogRecord(
        schema_version="1.1",
        record_id=current_pull_record_id,
        method=api.HTTP_GET_METHOD,
        scheme="http",
        host="testserver",
        path=api.PULL_PATH,
        query="",
        request_headers={},
        request_body="",
        response_code=status.HTTP_200_OK,
        response_headers={"content-type": api.MARKDOWN_MEDIA_TYPE},
        response_body="retry\n",
        received_at_unix_usec=1,
        ready_to_respond_at_unix_usec=2,
        duration_usec=1,
    )
    asyncio.run(api._after_authoritative_public_record(persisted_pull))

    assert api.BACKEND_CURRENT_PULL_RECORD is persisted_pull
    accepted = asyncio.run(api.authoritative_push(request))
    assert accepted.status_code == status.HTTP_202_ACCEPTED
    assert accepted.headers[api.LOCATION_HEADER] == api.PULL_PATH
    assert api.BACKEND_LIFECYCLE is BackendLifecycle.BUSY
    assert api.BACKEND_CURRENT_PULL_RECORD is None
    assert api.BACKEND_PENDING_PULL_RECORD is persisted_pull
    assert api.BACKEND_ATTEMPT_RECORD is None


@pytest.mark.parametrize(
    ("workflow_status", "session_id"),
    (
        (BackendLifecycle.READY, None),
        (BackendLifecycle.FAILED, TEST_SESSION_ID),
    ),
)
def test_push_configuration_failures_remain_internal_errors(
    monkeypatch: pytest.MonkeyPatch,
    workflow_status: BackendLifecycle,
    session_id: UUID | None,
) -> None:
    pull_record_id = UUID("019d0000-0000-7000-8000-000000000040")
    pull_record = persisted_http_record(
        record_id=pull_record_id,
        method=api.HTTP_GET_METHOD,
        path=api.PULL_PATH,
        response_code=status.HTTP_200_OK,
    )
    monkeypatch.setattr(api, "BACKEND_LIFECYCLE", workflow_status)
    monkeypatch.setattr(api, "BACKEND_CURRENT_PULL_RECORD", pull_record)
    monkeypatch.setattr(api, "BACKEND_PENDING_PULL_RECORD", None)
    monkeypatch.setattr(api, "BACKEND_ATTEMPT_RECORD", None)
    monkeypatch.setattr(api, "BACKEND_SESSION_ID", session_id)

    response = asyncio.run(api.authoritative_push(cast(Any, None)))

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert api.LOCATION_HEADER not in response.headers
    assert api.BACKEND_LIFECYCLE is workflow_status
    assert api.BACKEND_CURRENT_PULL_RECORD is pull_record
    assert api.BACKEND_PENDING_PULL_RECORD is None


def test_accepted_push_is_committed_only_after_its_public_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = UUID("019d0000-0000-7000-8000-000000000021")
    pull_record_id = UUID("019d0000-0000-7000-8000-000000000020")
    pull_record = persisted_http_record(
        record_id=pull_record_id,
        method=api.HTTP_GET_METHOD,
        path=api.PULL_PATH,
        response_code=status.HTTP_200_OK,
    )
    push_record = HttpRequestLogRecord(
        schema_version="1.1",
        method="POST",
        scheme="http",
        host="testserver",
        path="/push",
        query="",
        request_headers={},
        request_body="{}",
        response_code=202,
        response_headers={"location": "/pull"},
        response_body="",
        received_at_unix_usec=None,
        ready_to_respond_at_unix_usec=1,
        duration_usec=1,
    )
    rollout_path = tmp_path / f"rollout-2026-08-31T00-00-00-{session_id}.jsonl"
    rollout_path.write_text("{}\n", encoding=TEXT_ENCODING)
    rollout = api._archived_file(rollout_path)
    configuration = SimpleNamespace(
        rollout_relative_path=PurePosixPath(rollout_path.name),
    )
    runtime = cast(
        AiAugmentBackendContext,
        SimpleNamespace(configured_namekey=NameKey.from_json_key(TEST_NAMEKEY)),
    )
    appended: list[BackendCommitRecord] = []
    api.BACKEND_PENDING_PULL_RECORD = pull_record
    api.BACKEND_SESSION_ID = session_id
    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    monkeypatch.setattr(
        api,
        "push_configuration_for_session",
        lambda supplied: configuration if supplied == session_id else pytest.fail(),
    )
    monkeypatch.setattr(api, "copy_rollout_to_cas", lambda *_args: rollout)
    monkeypatch.setattr(api, "_read_appendwatch_bytes", lambda *_args: b".\n")

    def append_commit(record: HttpRequestLogRecord) -> AgentRuntimeAttemptRecord:
        assert isinstance(record, BackendCommitRecord)
        appended.append(record)
        return AgentRuntimeAttemptRecord(
            attempt=AgentRuntimeAttempt(
                pull_record=pull_record,
                commit_record=record,
                post_commit_validation=PostCommitValidation(
                    stage=BackendLifecycle.PYDANTIC_VALIDATION,
                    result=BackendLifecycle.REJECTED,
                    detail="retry",
                ),
            ),
            submission=None,
            ground_truth_innerdict=None,
        )

    monkeypatch.setattr(api, "append_authoritative_record", append_commit)

    api._commit_accepted_push(push_record)

    assert len(appended) == 1
    commit_record = appended[0]
    assert commit_record.request_body is not None
    commit = CommitRequestBody.from_serialized_json(
        commit_record.request_body,
        resolve_http_record={
            pull_record_id: pull_record,
            push_record.record_id: push_record,
        }.__getitem__,
    )
    assert commit.pull_record is pull_record
    assert commit.push_record is push_record
    assert commit.codex_session_record.codex_rollout_record is not None
    assert commit.codex_session_record.codex_rollout_record.sha256 == rollout.sha256
    assert api.BACKEND_LIFECYCLE is BackendLifecycle.RETRY


@pytest.mark.anyio
async def test_persisted_push_becomes_latest_run_outcome_snapshot_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    push_record = HttpRequestLogRecord(
        schema_version="1.1",
        method=api.HTTP_POST_METHOD,
        scheme="http",
        host="testserver",
        path=api.PUSH_PATH,
        query="",
        request_headers={},
        request_body="{}",
        response_code=status.HTTP_202_ACCEPTED,
        response_headers={api.LOCATION_HEADER: api.PULL_PATH},
        response_body="",
        received_at_unix_usec=1,
        ready_to_respond_at_unix_usec=2,
        duration_usec=1,
    )
    monkeypatch.setattr(api, "BACKEND_LATEST_PUSH_RECORD", None)
    monkeypatch.setattr(api, "AUTHORITATIVE_BACKGROUND_TASKS", set())
    monkeypatch.setattr(api, "_commit_accepted_push", lambda _record: None)

    async def run_inline(function: Any, /, *args: object) -> Any:
        return function(*args)

    monkeypatch.setattr(asyncio, "to_thread", run_inline)
    await api._after_authoritative_public_record(push_record)
    background_tasks = tuple(api.AUTHORITATIVE_BACKGROUND_TASKS)
    await asyncio.gather(*background_tasks)

    assert api.BACKEND_LATEST_PUSH_RECORD is push_record


@pytest.mark.parametrize(
    ("result", "stage", "expected_code", "expected_media_type"),
    (
        (
            BackendLifecycle.ACCEPTED,
            BackendLifecycle.ACCEPTED,
            410,
            api.MEDIA_TYPE_WITH_CHARSET,
        ),
        (
            BackendLifecycle.REJECTED,
            BackendLifecycle.PYDANTIC_VALIDATION,
            200,
            api.MARKDOWN_MEDIA_TYPE,
        ),
        (
            BackendLifecycle.REJECTED,
            BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION,
            200,
            api.MARKDOWN_MEDIA_TYPE,
        ),
        (
            BackendLifecycle.REJECTED,
            BackendLifecycle.ROLLOUT_INDEX,
            500,
            api.JSON_MEDIA_TYPE,
        ),
        (
            BackendLifecycle.REJECTED,
            BackendLifecycle.APPENDWATCH_REPORT_VALIDATION,
            500,
            api.JSON_MEDIA_TYPE,
        ),
    ),
)
def test_post_commit_result_is_exposed_only_by_follow_up_pull(
    monkeypatch: pytest.MonkeyPatch,
    result: BackendLifecycle,
    stage: BackendLifecycle,
    expected_code: int,
    expected_media_type: str,
) -> None:
    monkeypatch.setattr(
        api,
        "runtime_configuration",
        lambda: cast(AiAugmentBackendContext, SimpleNamespace()),
    )
    pull_record, commit_record = retry_attempt_records(
        run_id=UUID("019d0000-0000-7000-8000-000000000050"),
        session_id=UUID("019d0000-0000-7000-8000-000000000051"),
        attempt_id=f"{result.value}-{stage.value}",
    )
    submission = (
        StandardizedSubmission.model_validate(
            standardized_submission_body(valid_submission_body())
        )
        if result is BackendLifecycle.ACCEPTED
        else None
    )
    api.BACKEND_ATTEMPT_RECORD = AgentRuntimeAttemptRecord(
        attempt=AgentRuntimeAttempt(
            pull_record=pull_record,
            commit_record=commit_record,
            post_commit_validation=PostCommitValidation(
                stage=stage,
                result=result,
                detail="retry details",
            ),
        ),
        submission=submission,
        ground_truth_innerdict=None,
    )
    if result is BackendLifecycle.ACCEPTED:
        api.BACKEND_LIFECYCLE = BackendLifecycle.COMPLETE
    elif stage in {
        BackendLifecycle.PYDANTIC_VALIDATION,
        BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION,
    }:
        api.BACKEND_LIFECYCLE = BackendLifecycle.RETRY
    else:
        api.BACKEND_LIFECYCLE = BackendLifecycle.FAILED

    if api.BACKEND_LIFECYCLE is BackendLifecycle.FAILED:
        with pytest.raises(HTTPException) as exc_info:
            api.authoritative_pull()
        assert exc_info.value.status_code == expected_code
        return

    response = api.authoritative_pull()
    assert response.status_code == expected_code
    assert response.headers["content-type"].startswith(expected_media_type)


def test_backend_stdin_accepts_one_canonical_session_id() -> None:
    api.BACKEND_SESSION_ID = None
    session_id = "019d0000-0000-7000-8000-000000000040"

    api.read_backend_session_id(StringIO(session_id + "\n"))

    assert api.BACKEND_SESSION_ID == UUID(session_id)
    with pytest.raises(api._PushConfigurationError):
        api.read_backend_session_id(
            StringIO("019d0000-0000-7000-8000-000000000041\n")
        )


def test_startup_proves_report_and_remote_sessions_readable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "appendwatch.txt"
    report_path.write_bytes(b"appendwatch\n")
    configuration = SimpleNamespace(
        appendwatch_report=PurePosixPath("/mounted/appendwatch.txt"),
        lima_ssh_config=tmp_path / "ssh.conf",
        identity_file=tmp_path / "identity",
        known_hosts_file=tmp_path / "known-hosts",
        ssh_user="aivm-audit",
        host_key_alias="alias",
        ssh_target="guest",
    )
    observed: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        assert kwargs["check"] is True
        observed.append(command)
        stdout = (
            b"appendwatch\n"
            if command[-1].startswith(api.AUDIT_READ_APPENDWATCH_REPORT_COMMAND)
            else ""
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(api, "push_configuration", lambda _path: configuration)
    monkeypatch.setattr(subprocess, "run", run)

    api.prove_workflow_inputs_readable()

    assert len(observed) == 2
    assert all(command[-2] == configuration.ssh_target for command in observed)
    assert observed[0][-1] == (
        f"{api.AUDIT_READ_APPENDWATCH_REPORT_COMMAND} {configuration.appendwatch_report}"
    )
    assert observed[1][-1] == api.AUDIT_PROBE_COMMAND


def test_background_commit_failure_exits_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exits: list[int] = []

    class FailedTask:
        @staticmethod
        def cancelled() -> bool:
            return False

        @staticmethod
        def exception() -> RuntimeError:
            return RuntimeError("commit failed")

    task = cast(asyncio.Task[None], FailedTask())
    monkeypatch.setattr(os, "_exit", exits.append)

    api._authoritative_background_finished(task)

    assert exits == [1]


def test_appendwatch_commit_lookup_requires_one_exact_filename(
    tmp_path: Path,
) -> None:
    filename = "rollout-2026-08-31T00-00-00-019d0000-0000-7000-8000-000000000050.jsonl"
    report_path = tmp_path / "appendwatch.txt"
    report_path.write_text(
        f".\n└── 2026/\n    └── 08/\n        └── {api.APPENDWATCH_OK_PREFIX}{filename}\n",
        encoding=TEXT_ENCODING,
    )

    api.parse_appendwatch_report(report_path, PurePosixPath(filename))

    report_path.write_text(
        report_path.read_text(encoding=TEXT_ENCODING)
        + f"└── {api.APPENDWATCH_OK_PREFIX}{filename}\n",
        encoding=TEXT_ENCODING,
    )
    with pytest.raises(api._PushValidationError):
        api.parse_appendwatch_report(report_path, PurePosixPath(filename))


def test_openapi_does_not_disclose_integrity_internals() -> None:
    schema = api.app.openapi()
    assert set(schema["paths"]) == {api.PULL_PATH, api.PUSH_PATH}
    push_schema = schema["paths"]["/push"]["post"]
    serialized = json.dumps(push_schema).lower()

    assert push_schema["description"] == Locale.PUSH_DESCRIPTION
    assert "appendwatch" not in serialized
    assert "rollout" not in serialized
    assert api.ROLLOUT_ENV_NAME.lower() not in serialized
    assert set(push_schema["responses"]) == {"202", "409", "500"}
    conflict_schema = push_schema["responses"]["409"]
    assert "current pull must be retrieved" in conflict_schema["description"]
    assert set(conflict_schema["headers"]) == {api.LOCATION_HEADER}
    assert set(schema["paths"]["/pull"]["get"]["responses"]) == {
        "200",
        "410",
        "500",
        "503",
    }


def test_dashboard_query_uses_one_backend_owned_connection_and_synchronizes_each_use(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_test_paths: BackendTestPaths,
) -> None:
    runtime = runtime_for_test(tmp_path, backend_test_paths)
    synchronized_connections: list[duckdb.DuckDBPyConnection] = []
    original_synchronize = api._synchronize_authoritative_projection_locked
    monkeypatch.setattr(api, "load_duckdb_extension", lambda *_args, **_kwargs: None)

    def tracked_synchronize(
        selected_runtime: AiAugmentBackendContext,
        connection: duckdb.DuckDBPyConnection,
    ) -> None:
        synchronized_connections.append(connection)
        original_synchronize(selected_runtime, connection)

    monkeypatch.setattr(api, "runtime_configuration", lambda: runtime)
    monkeypatch.setattr(
        api,
        "_synchronize_authoritative_projection_locked",
        tracked_synchronize,
    )

    first = QueryResponse.from_serialized_json(ipc.dashboard_query_payload(None))
    replayed_pull = HttpRequestLogRecord(
        schema_version="1.1",
        method=api.HTTP_GET_METHOD,
        scheme="http",
        host="127.0.0.1",
        port=api.SERVER_PORT,
        ready_to_respond_at_unix_usec=1,
        path=api.PULL_PATH,
        query="",
        request_headers={},
        request_body=None,
        response_code=status.HTTP_200_OK,
        response_headers={"content-type": api.MEDIA_TYPE},
        response_body="{}\n",
        received_at_unix_usec=None,
        duration_usec=1,
    )
    Path(runtime.pipeline_config.resources.replay_log).write_text(
        replayed_pull.model_dump_json() + "\n",
        encoding=TEXT_ENCODING,
    )
    second = QueryResponse.from_serialized_json(ipc.dashboard_query_payload(None))

    assert (
        first
        == second
        == QueryResponse(
            attempts=(),
            ai_augment_outerdicts=(),
            run_outcome_records=(),
        )
    )
    assert len(synchronized_connections) == 2
    assert synchronized_connections[0] is synchronized_connections[1]
    assert synchronized_connections[0] is api.DETOUR_DB_CONNECTION
    assert synchronized_connections[0].execute(
        f"SELECT count(*) FROM {api.AUTHORITATIVE_RECORDS_TABLE}"
    ).fetchone() == (1,)


def test_dashboard_query_has_no_route_on_the_public_fastapi_application() -> None:
    route_paths = {getattr(route, "path", None) for route in api.app.routes}

    assert ipc.DASHBOARD_QUERY_PATH not in route_paths
    assert not any(isinstance(path, str) and path.startswith("/_control/") for path in route_paths)
