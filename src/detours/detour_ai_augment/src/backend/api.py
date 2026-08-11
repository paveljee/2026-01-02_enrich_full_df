from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import threading
from collections import Counter
from collections.abc import AsyncGenerator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path, PurePosixPath
from random import Random
from typing import Annotated, Any, Literal, Self, cast
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import duckdb
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    StringConstraints,
    ValidationError,
    model_validator,
)

from src.helpers.cards import build_cards, write_cards_zip
from src.helpers.config import PipelineConfig
from src.helpers.data_models import (
    FragmentType,
    NameKey,
    OuterDict,
    RegisteredResource,
    ResourceGroup,
)
from src.helpers.duckdb_utils import (
    append_innerdicts_from_jsonlines_table,
    duckdb_quote_identifier,
    materialize_innerdicts_from_rows_table,
)
from src.helpers.procedures import DocxMatchProcedure, ParquetMatchProcedure, XlsxMatchProcedure
from src.helpers.resources import register_resource
from src.helpers.schema import (
    CARD_PARTITION_TABLE,
    DOCX_INNERDICT_TABLE,
    OUTERDICT_NAME_VIEW,
    PARQUET_INNERDICT_TABLE,
    SAMPLES_WITH_NAMES_VIEW,
    XLSX_INNERDICT_TABLE,
)
from src.helpers.vars import (
    BATCH_LABEL,
    CARD_INTRODUCTION,
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_INNERDICT_JSONLINES_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
    KTP_PARTITION_COL,
    KTP_PARTITION_DOCX_VALUE,
    KTP_PARTITION_FLAG_SSN_COUNT_COL,
    KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
    KTP_PARTITION_SSN_VALUE,
)

from . import codex_parse

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
load_dotenv(REPOSITORY_ROOT / ".env")

logger = logging.getLogger(__name__)


class SourceCohort(StrEnum):
    GROUND_TRUTH = "ground_truth"
    NO_GROUND_TRUTH = "no_ground_truth"
    INELIGIBLE = "ineligible"


class IneligibilityCategory(StrEnum):
    EXCLUDED_DUPLICATE_SOURCE_KEY = "excluded_duplicate_source_key"
    RELEASE_BATCH_SUBSET_8 = "release_batch_subset_8"
    STAGING_PARTITION_2 = "staging_partition_2"
    STAGING_PARTITION_4_XLSX_NON_EXACT = "staging_partition_4_xlsx_non_exact"
    STAGING_PARTITION_4_MULTIPLE_SSN = "staging_partition_4_multiple_ssn"


SUBMISSIONS_DIR = Path(__file__).resolve().parents[2] / "data" / "submissions"
ATTEMPTS_DIR = SUBMISSIONS_DIR / "attempts"
SOURCE_FILE = Path("tmp/sheikh.jsonl")
HOST_WORKBOOK_PATH = Path(__file__).resolve().parents[2] / "data" / "workbook.md"
AIVM_WORKDIR = PurePosixPath("/home/ai/workdir")
AIVM_WORKBOOK_PATH = AIVM_WORKDIR / "WORKBOOK.md"

ROLLOUT_ENV_NAME = "FASTAPI_DETOUR_ROLLOUT_JSONL"
ROLLOUT_JSONL = os.environ.get(ROLLOUT_ENV_NAME, "")
CONTROL_URL_ENV_NAME = "FASTAPI_DETOUR_CONTROL_URL"
CONTROL_BASE_URL = os.environ.get(CONTROL_URL_ENV_NAME, "")
CONTROL_CURRENT_PATH = "/_control/current"
CONTROL_ACCEPTED_PATH_TEMPLATE = "/_control/runs/{run_id}/accepted"
CONTROL_HTTP_TIMEOUT_SECONDS = 10
CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 8611
CODEX_SESSIONS_ROOT = PurePosixPath("/home/ai/.codex/sessions")
APPENDWATCH_REPORT = Path(
    os.environ.get(
        "FASTAPI_DETOUR_APPENDWATCH_REPORT",
        "/Volumes/home/aicode/aivm/home/ai/.aivm-control/appendwatch/appendwatch-tree.txt",
    )
).expanduser()

AIVM_INSTANCE = os.environ.get("FASTAPI_DETOUR_AIVM_INSTANCE", "aivm")
AIVM_USER = os.environ.get("FASTAPI_DETOUR_AIVM_USER", "ai")
AIVM_SSH_PORT = os.environ.get("FASTAPI_DETOUR_AIVM_SSH_PORT", "22022")
AIVM_KEY_DIR = Path.home() / ".local" / "share" / "aivm" / ".ssh"
AIVM_IDENTITY_FILE = Path(
    os.environ.get("FASTAPI_DETOUR_AIVM_IDENTITY_FILE", AIVM_KEY_DIR / "id_ed25519")
).expanduser()
AIVM_KNOWN_HOSTS_FILE = Path(
    os.environ.get("FASTAPI_DETOUR_AIVM_KNOWN_HOSTS_FILE", AIVM_KEY_DIR / "known_hosts")
).expanduser()
LIMA_SSH_CONFIG_PATH = Path(
    os.environ.get(
        "FASTAPI_DETOUR_LIMA_SSH_CONFIG",
        Path.home() / ".lima" / AIVM_INSTANCE / "ssh.config",
    )
).expanduser()
AIVM_SSH_TARGET = f"{AIVM_INSTANCE}-{AIVM_USER}"
AIVM_HOST_KEY_ALIAS = f"lima-{AIVM_INSTANCE}-{AIVM_USER}"

MAX_PUSH_BODY_BYTES = 2 * 1024 * 1024
MAX_VALUE_CHARACTERS = MAX_PUSH_BODY_BYTES
MAX_EXCERPT_CHARACTERS = MAX_PUSH_BODY_BYTES
MAX_URL_CHARACTERS = MAX_PUSH_BODY_BYTES
MAX_EXCERPTS_PER_FIELD = MAX_PUSH_BODY_BYTES
ARCHIVE_HASH_CHUNK_BYTES = 1024 * 1024
SCP_TIMEOUT_SECONDS = 60
SSH_TIMEOUT_SECONDS = 60
MIN_TCP_PORT = 1
MAX_TCP_PORT = 65_535
CONTROL_CHARACTER_CEILING = 32
DELETE_CHARACTER_CODEPOINT = 127
APPENDWATCH_STATUS_WIDTH = 11
TREE_INDENT_WIDTH = len("│   ")
APPENDWATCH_OK_PREFIX = f"{'OK':<{APPENDWATCH_STATUS_WIDTH}} "
APPENDWATCH_COMPROMISED_PREFIX = f"{'COMPROMISED':<{APPENDWATCH_STATUS_WIDTH}} "
CONFIGURATION_ERROR_DETAIL = "API is not properly configured. Contact the human operator."
# VALIDATION_ERROR_DETAIL = "Submission did not pass validation. Verify all details and try again."
VALIDATION_ERROR_DETAIL = (
    "Submission did not pass validation. Recheck every evidence excerpt and URL before "
    "retrying. Copy each excerpt verbatim as one contiguous span from the cited web-tool "
    "output, preserving every character—including repeated spaces, line breaks, punctuation, "
    "capitalization, and Unicode typography—and copy its associated URL exactly. Do not "
    "paraphrase, normalize, retype, or join separated text."
)
PYDANTIC_MISSING_INPUT = "<missing>"
MULTIPLE_MATCH_DETAIL = (
    "Excerpt matched multiple entries. Resubmit with an excerpt unique across "
    "the searched web pages: {excerpt}"
)
ALLOW_MULTIPLE_EVIDENCE_MATCHES = True
ELIGIBLE_WEB_ACTIONS = frozenset({"search_query", "open", "click"})
TREE_LINE = re.compile(r"^(?P<indent>(?:(?:│   )|(?:    ))*)(?:├── |└── )(?P<body>.*)$")
CODEX_CITE_MARKER_PREFIX = "\ue200cite\ue202"
CODEX_CITE_MARKER_SUFFIX = "\ue201"
CODEX_REF_ID_PATTERN = r"turn[0-9]+[A-Za-z_]+[0-9]+"
CODEX_RESULT_SEPARATOR = "-" * 80
FOOTNOTE_CONTEXT_CHARACTERS = 160
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8612

CONFIG_FILENAME = "config_ai_augment.json"
MAP_SUBSET_0_TO_BATCH_KEY = "map_subset_0_to_batch"
MAP_COLUMNS = (DRAW_LABEL, BATCH_LABEL)
GROUND_TRUTH_RELEASE_BATCHES = frozenset({"subset 1", "subset 5", "subset 6", "subset 7"})
GROUND_TRUTH_COHORT = SourceCohort.GROUND_TRUTH
NO_GROUND_TRUTH_COHORT = SourceCohort.NO_GROUND_TRUTH
EXPECTED_GROUND_TRUTH_RESEARCHERS = 196
EXPECTED_NO_GROUND_TRUTH_RESEARCHERS = 78
EXPECTED_ELIGIBLE_RESEARCHERS = 274
EXPECTED_INELIGIBLE_RESEARCHERS = 33
EXPECTED_SOURCE_RESEARCHERS = EXPECTED_ELIGIBLE_RESEARCHERS + EXPECTED_INELIGIBLE_RESEARCHERS
EXPECTED_MULTIDRAW_SOURCE_RESEARCHERS = 5
RND_START = 1
NO_GROUND_TRUTH_PARTITION = 4
NO_GROUND_TRUTH_SSN_COUNT = 1
INELIGIBLE_COHORT = SourceCohort.INELIGIBLE
INELIGIBLE_RELEASE_BATCH = "subset 8"
EXPECTED_INELIGIBILITY_COUNTS = {
    IneligibilityCategory.EXCLUDED_DUPLICATE_SOURCE_KEY: 1,
    IneligibilityCategory.RELEASE_BATCH_SUBSET_8: 3,
    IneligibilityCategory.STAGING_PARTITION_2: 7,
    IneligibilityCategory.STAGING_PARTITION_4_XLSX_NON_EXACT: 6,
    IneligibilityCategory.STAGING_PARTITION_4_MULTIPLE_SSN: 16,
}
EXCLUDED_SOURCE_KEY = json.dumps(
    {KTP_FIRST_NAME_COL: "Mercouri G.", KTP_LAST_NAME_COL: "Kanatzidis"},
    sort_keys=True,
)
DRAW_VALUE_SEPARATOR = ", "
DRAW_PILOT_PREFIX = "pilot."
DRAW_SORT_PART = re.compile(r"\d+|\D+")

DETOUR_ID = "ai-augment"
DETOUR_DB_LOCK = threading.Lock()
CONSUMED_RUN_LOCK = threading.Lock()
CONSUMED_RUN_IDS: set[UUID] = set()
WORKBOOK_STATE_LOCK = threading.Lock()
WORKBOOK_INITIALIZED = False
EVIDENCE_RANDOM = Random()
CODEX_FC_TABLE = "codex_fc"
CODEX_FCO_TABLE = "codex_fco"
CODEX_CALLS_TABLE = "codex_calls"
CODEX_TURN_REF_TABLE = "codex_turn_ref"
CODEX_OUTPUT_ROWS_TABLE = "codex_output_rows"
CODEX_OUTPUT_VIEW = "codex_output"
CODEX_INNERDICT_TABLE = "codex_innerdicts"
CODEX_FC_ID_SEQUENCE = "codex_fc_id_sequence"
CODEX_FCO_ID_SEQUENCE = "codex_fco_id_sequence"
CODEX_CALLS_ID_SEQUENCE = "codex_calls_id_sequence"
CODEX_TURN_REF_ID_SEQUENCE = "codex_turn_ref_id_sequence"

CODEX_ID_COL = "id"
CODEX_FC_TIMESTAMP_COL = "codex.fc_timestamp"
CODEX_FC_ID_COL = "codex.fc_id"
CODEX_FC_NAME_COL = "codex.fc_name"
CODEX_FC_NAMESPACE_COL = "codex.fc_namespace"
CODEX_FC_ARGUMENTS_COL = "codex.fc_arguments"
CODEX_FCO_TIMESTAMP_COL = "codex.fco_timestamp"
CODEX_FCO_ID_COL = "codex.fco_id"
CODEX_CALL_ID_COL = "codex.call_id"
CODEX_ROLLOUT_FILENAME_COL = "codex.rollout_filename"
CODEX_REF_ID_COL = "codex.ref_id"
CODEX_REF_DOMAIN_COL = "codex.ref_domain"
CODEX_REF_SNIPPET_COL = "codex.ref_snippet"
CODEX_REF_THUMBNAIL_URL_COL = "codex.ref_thumbnail_url"
CODEX_REF_TITLE_COL = "codex.ref_title"
CODEX_REF_URL_COL = "codex.ref_url"
CODEX_CITE_TEXT_COL = "codex.cite_text"

AI_AUGMENT_COLUMN_PREFIX = "ktp.ai_augment_"
KTP_AI_AUGMENT_ATTEMPT_ID_COL = f"{AI_AUGMENT_COLUMN_PREFIX}attempt_id"
KTP_AI_AUGMENT_SESSION_METADATA_COL = f"{AI_AUGMENT_COLUMN_PREFIX}session_metadata"
KTP_AI_AUGMENT_FOOTNOTES_COL = f"{AI_AUGMENT_COLUMN_PREFIX}footnotes"
KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}footnote_arguments"
KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL = f"{AI_AUGMENT_COLUMN_PREFIX}researcher_author"
KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL = f"{AI_AUGMENT_COLUMN_PREFIX}place_of_residence"
KTP_AI_AUGMENT_GENDER_COL = f"{AI_AUGMENT_COLUMN_PREFIX}gender"
KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}age_first_publication_according_to_openalex_profile"
)
KTP_AI_AUGMENT_EDUCATION_COL = f"{AI_AUGMENT_COLUMN_PREFIX}education"
KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}academic_position_s_"
KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL = f"{AI_AUGMENT_COLUMN_PREFIX}social_capital"
KTP_AI_AUGMENT_LINKS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}links_"
KTP_AI_AUGMENT_COMMENTS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}comments"

DRAW_NUMBER_COLUMN = DRAW_LABEL
TARGET_DRAW_NUMBER = "146"
FRAGMENT_TYPE_COLUMN = KTP_FRAGMENT_TYPE_COL
DOCX_ROW_FRAGMENT_TYPE = FragmentType.DOCX_ROW.value
ROLLOUT_LINE_FRAGMENT_TYPE = FragmentType.LINE_NUMBER.value
DOCX_TO_AI_AUGMENT_COLUMNS = (
    ("ktp.table_1_researcher_author", KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL),
    ("ktp.table_1_place_of_residence", KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL),
    ("ktp.table_1_gender", KTP_AI_AUGMENT_GENDER_COL),
    (
        "ktp.table_1_age_first_publication_according_to_openalex_profile",
        KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    ),
    ("ktp.table_1_education", KTP_AI_AUGMENT_EDUCATION_COL),
    ("ktp.table_1_academic_position_s_", KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL),
    ("ktp.table_1_social_capital", KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL),
    ("ktp.table_1_links_", KTP_AI_AUGMENT_LINKS_COL),
    ("ktp.table_1_comments", KTP_AI_AUGMENT_COMMENTS_COL),
)
DOCX_COLUMNS = tuple(docx_column for docx_column, _ai_column in DOCX_TO_AI_AUGMENT_COLUMNS)
AI_AUGMENT_EVIDENCE_COLUMNS = (
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
    KTP_AI_AUGMENT_GENDER_COL,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    KTP_AI_AUGMENT_EDUCATION_COL,
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
    KTP_AI_AUGMENT_LINKS_COL,
)
AI_AUGMENT_COLUMNS = AI_AUGMENT_EVIDENCE_COLUMNS + (KTP_AI_AUGMENT_COMMENTS_COL,)
CODEX_OUTPUT_SCHEMA = (
    (KTP_NAMEKEY_COL, "VARCHAR NOT NULL"),
    (KTP_FILENAME_COL, "VARCHAR NOT NULL"),
    (KTP_FRAGMENT_COL, "BIGINT NOT NULL"),
    (KTP_FRAGMENT_TYPE_COL, "VARCHAR NOT NULL"),
    (DRAW_LABEL, "VARCHAR NOT NULL"),
    (KTP_FIRST_NAME_COL, "VARCHAR NOT NULL"),
    (KTP_LAST_NAME_COL, "VARCHAR NOT NULL"),
    (KTP_AI_AUGMENT_ATTEMPT_ID_COL, "VARCHAR NOT NULL UNIQUE"),
    (KTP_AI_AUGMENT_SESSION_METADATA_COL, "VARCHAR NOT NULL"),
    *((column, "VARCHAR NOT NULL") for column in AI_AUGMENT_EVIDENCE_COLUMNS),
    (KTP_AI_AUGMENT_COMMENTS_COL, "VARCHAR"),
    (KTP_AI_AUGMENT_FOOTNOTES_COL, "VARCHAR NOT NULL"),
    (KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL, "VARCHAR NOT NULL"),
)

CARD_EXCLUDED_COLUMNS = {
    KTP_FILENAME_COL,
    KTP_NAMEKEY_COL,
    CSV_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
}
CARD_ZIP_PREFIX = "ai_augment_cards"

MEDIA_TYPE = "application/x-ndjson"

# Note: generated via chatgpt.com on 2026-07-27 UTC,
# using GPT-5.6-Sol-High with tools (context lost)
SUBMISSION_EXAMPLE: dict[str, object] = {
    AI_AUGMENT_COLUMNS[0]: "Fei-Fei Li; publishes as L. Fei-Fei.",
    AI_AUGMENT_COLUMNS[1]: "Stanford campus, Stanford, California.",
    AI_AUGMENT_COLUMNS[2]: "Female.",
    AI_AUGMENT_COLUMNS[3]: (
        "28–29; born in 1976, with the earliest visible work on the OpenAlex profile dated 2005."
    ),
    AI_AUGMENT_COLUMNS[4]: (
        "B.A. Physics, Princeton University, 1999; M.S. Electrical "
        "Engineering, Caltech, 2001; Ph.D. Electrical Engineering, "
        "Caltech, 2005."
    ),
    AI_AUGMENT_COLUMNS[5]: (
        "Sequoia Capital Professor of Computer Science, Stanford; Senior "
        "Fellow, Stanford HAI; Professor by courtesy, Stanford Graduate "
        "School of Business; former Director, Stanford AI Lab, 2013–2018; "
        "former Vice President and Chief Scientist of AI/ML, Google Cloud, "
        "2017–2018; Co-founder and CEO, World Labs."
    ),
    AI_AUGMENT_COLUMNS[6]: (
        "Founding Co-Director, Stanford HAI; Co-founder and Chair, AI4ALL; "
        "member of the National Academy of Engineering, National Academy "
        "of Medicine, American Academy of Arts and Sciences, and Council "
        "on Foreign Relations; ACM Fellow; UN special adviser."
    ),
    AI_AUGMENT_COLUMNS[7]: (
        "Stanford profile: https://profiles.stanford.edu/fei-fei-li; "
        "OpenAlex: https://openalex.org/A5100450462; "
        "AI4ALL: https://ai-4-all.org/our-people/fei-fei-li/"
    ),
    AI_AUGMENT_COLUMNS[8]: (
        "OpenAlex appears to conflate this author with unrelated researchers "
        "and institutions; age at first publication is therefore provisional."
    ),
}

NULL_SUBMISSION_EXAMPLE = {
    KTP_FIRST_NAME_COL: "L.",
    KTP_LAST_NAME_COL: "Fei-Fei",
    **dict.fromkeys(AI_AUGMENT_COLUMNS),
}
EVIDENCE_SUBMISSION_EXAMPLE = {
    column: {
        "value": value,
        "web_search_excerpts": [
            {
                "excerpt": "Exact contiguous excerpt from a cited web result.",
                "url": "https://example.test/result",
            }
        ],
    }
    for column, value in SUBMISSION_EXAMPLE.items()
    if column in AI_AUGMENT_EVIDENCE_COLUMNS
}
EVIDENCE_SUBMISSION_EXAMPLE[KTP_AI_AUGMENT_COMMENTS_COL] = {
    "value": SUBMISSION_EXAMPLE[KTP_AI_AUGMENT_COMMENTS_COL]
}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    try:
        runtime_configuration()
    except PushConfigurationError as exc:
        logger.error("API startup failed: %s", exc)
        raise
    try:
        if _control_base_url() is None:
            push_configuration()
        else:
            initialize_guest_workbook()
    except PushConfigurationError as exc:
        logger.error("pull and push are disabled: %s", exc)
    yield


APP_CONFIG: dict[str, Any] = {
    "title": "Highly-Cited Researcher Annotation API",
    "description": (
        "Pull a JSONL annotation task, submit completed values, "
        "and compare the submission with ground truth."
    ),
    "version": "1.0.0",
    "lifespan": lifespan,
}

PULL_ROUTE: dict[str, Any] = {
    "path": "/pull",
    "response_class": StreamingResponse,
    "summary": "Pull the annotation task",
    "description": (
        "Streams the source JSONL through the selected row. "
        "The selected row contains only the annotation columns "
        "with all values replaced by null."
    ),
    "responses": {
        200: {
            "description": "JSON Lines annotation task",
            "content": {
                MEDIA_TYPE: {
                    "example": (json.dumps(NULL_SUBMISSION_EXAMPLE, ensure_ascii=False) + "\n"),
                },
            },
        },
    },
}

PUSH_ROUTE: dict[str, Any] = {
    "path": "/push",
    "response_class": StreamingResponse,
    "summary": "Submit completed annotations",
    "description": "Validates and stores the completed submission.",
    "responses": {
        200: {
            "description": "Submission followed by ground truth",
            "content": {
                MEDIA_TYPE: {
                    "example": (
                        json.dumps(SUBMISSION_EXAMPLE, ensure_ascii=False)
                        + "\n"
                        + json.dumps(SUBMISSION_EXAMPLE, ensure_ascii=False)
                        + "\n"
                    ),
                },
            },
        },
        422: {"description": VALIDATION_ERROR_DETAIL},
        503: {"description": CONFIGURATION_ERROR_DETAIL},
    },
    "openapi_extra": {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": EVIDENCE_SUBMISSION_EXAMPLE}},
        }
    },
}

app = FastAPI(**APP_CONFIG)

SubmissionText = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=MAX_VALUE_CHARACTERS),
]
ExcerptText = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=MAX_EXCERPT_CHARACTERS),
]
UrlText = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=MAX_URL_CHARACTERS),
]


class WebSearchExcerpt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    excerpt: ExcerptText
    url: UrlText

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if not self.excerpt.strip() or not self.url.strip():
            raise ValueError("excerpt and url must be non-blank")
        return self


class FieldSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: SubmissionText
    web_search_excerpts: list[WebSearchExcerpt] = Field(
        min_length=1,
        max_length=MAX_EXCERPTS_PER_FIELD,
    )

    @model_validator(mode="after")
    def validate_field(self) -> Self:
        if not self.value.strip():
            raise ValueError("value must be non-blank")
        evidence_pairs = [(evidence.excerpt, evidence.url) for evidence in self.web_search_excerpts]
        if len(set(evidence_pairs)) != len(evidence_pairs):
            raise ValueError("web_search_excerpts must not contain duplicate pairs")
        return self


class CommentSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: SubmissionText

    @model_validator(mode="after")
    def validate_comment(self) -> Self:
        if not self.value.strip():
            raise ValueError("value must be non-blank")
        return self


class CompactSessionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    originator: StrictStr
    source: StrictStr
    cli_version: StrictStr
    model_provider: StrictStr
    model: StrictStr
    reasoning_effort: StrictStr
    session_id: StrictStr
    timestamp: StrictStr

    @model_validator(mode="after")
    def validate_metadata(self) -> Self:
        if any(not value.strip() for value in self.model_dump().values()):
            raise ValueError("session metadata fields must be non-blank")
        return self


class ControlRun(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    run_id: UUID
    source_key: StrictStr
    session_id: StrictStr
    rollout_jsonl: StrictStr

    @model_validator(mode="after")
    def validate_control_run(self) -> Self:
        if any(
            not _valid_nonblank(value)
            for value in (self.source_key, self.session_id, self.rollout_jsonl)
        ):
            raise ValueError("control run fields must be non-blank and normalized")
        return self


class ControlSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    sanctioned_run: ControlRun | None


class ControlAcceptedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source_key: StrictStr
    session_id: StrictStr
    attempt_id: StrictStr


class ControlAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    acknowledged: bool


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    researcher_author: FieldSubmission = Field(alias=KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL)
    place_of_residence: FieldSubmission = Field(alias=KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL)
    gender: FieldSubmission = Field(alias=KTP_AI_AUGMENT_GENDER_COL)
    age_first_publication: FieldSubmission = Field(alias=KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL)
    education: FieldSubmission = Field(alias=KTP_AI_AUGMENT_EDUCATION_COL)
    academic_positions: FieldSubmission = Field(alias=KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL)
    social_capital: FieldSubmission = Field(alias=KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL)
    links: FieldSubmission = Field(alias=KTP_AI_AUGMENT_LINKS_COL)
    comments: CommentSubmission | None = Field(
        default=None,
        alias=KTP_AI_AUGMENT_COMMENTS_COL,
    )

    def evidence_items(self) -> tuple[tuple[str, FieldSubmission], ...]:
        return (
            (KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL, self.researcher_author),
            (KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL, self.place_of_residence),
            (KTP_AI_AUGMENT_GENDER_COL, self.gender),
            (KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL, self.age_first_publication),
            (KTP_AI_AUGMENT_EDUCATION_COL, self.education),
            (KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL, self.academic_positions),
            (KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL, self.social_capital),
            (KTP_AI_AUGMENT_LINKS_COL, self.links),
        )

    def normalized_values(self) -> dict[str, str]:
        values = {column: field.value for column, field in self.evidence_items()}
        if self.comments is not None:
            values[KTP_AI_AUGMENT_COMMENTS_COL] = self.comments.value
        return values


class CodexTextResult(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    type: Literal["text_result"]
    domain: StrictStr | None = None
    ref_id: StrictStr
    snippet: StrictStr | None = None
    thumbnail_url: StrictStr | None = None
    title: StrictStr | None = None
    url: StrictStr | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if not self.ref_id.strip():
            raise ValueError("web result ref_id must be non-blank")
        return self


class PushConfigurationError(RuntimeError):
    pass


class PushValidationError(RuntimeError):
    pass


class MultipleEvidenceMatches(PushValidationError):
    def __init__(self, excerpt: str) -> None:
        self.excerpt = excerpt
        super().__init__(f"excerpt matched multiple indexed results: {excerpt}")


@dataclass(frozen=True)
class PushConfiguration:
    rollout_guest_path: str
    rollout_relative_path: PurePosixPath
    appendwatch_report: Path
    lima_ssh_config: Path
    identity_file: Path
    known_hosts_file: Path
    ssh_target: str
    host_key_alias: str


@dataclass(frozen=True)
class RuntimeConfiguration:
    pipeline: PipelineConfig
    detour_db_path: Path
    release_map: RegisteredResource | None = None
    source_population: tuple[SourcePopulationRow, ...] = ()
    eligible_cohorts: Mapping[str, str] | None = None


@dataclass(frozen=True)
class SanctionSnapshot:
    run_id: UUID | None
    source_key: str | None
    session_id: str | None
    rollout_guest_path: str
    control_base_url: str | None


@dataclass(frozen=True)
class SourceResearcher:
    source_key: str
    first_name: str
    last_name: str
    draw_numbers: tuple[str, ...]
    xlsx_rows: tuple[dict[str, object], ...]
    docx_rows: tuple[dict[str, object], ...]
    ssn_rows: tuple[dict[str, object], ...]
    cohort: str


@dataclass(frozen=True)
class SourcePopulationRow:
    source_key: str
    rnd: int
    first_name: str
    last_name: str
    draw_numbers: tuple[str, ...]
    cohort: SourceCohort
    ineligibility_category: IneligibilityCategory | None


@dataclass(frozen=True)
class ArchivedFile:
    path: Path
    size: int
    sha256: str
    line_count: int


@dataclass(frozen=True)
class RolloutRecord:
    line_number: int
    line_sha256: str
    value: dict[str, object]


@dataclass(frozen=True)
class SessionMetadata:
    session_id: str
    timestamp: str
    rollout_filename: str
    compact: CompactSessionMetadata

    @property
    def compact_json(self) -> str:
        return json.dumps(
            self.compact.model_dump(),
            ensure_ascii=False,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class CodexFcRow:
    timestamp: str
    fc_id: str
    call_id: str
    name: str
    namespace: str
    arguments_json: str


@dataclass(frozen=True)
class CodexFcoRow:
    timestamp: str
    fco_id: str
    call_id: str


@dataclass(frozen=True)
class CodexTurnRefRow:
    ref_id: str
    call_id: str
    domain: str | None
    snippet: str | None
    thumbnail_url: str | None
    title: str | None
    url: str
    cite_text: str


@dataclass(frozen=True)
class RolloutIndex:
    session: SessionMetadata
    fc_rows: tuple[CodexFcRow, ...]
    fco_rows: tuple[CodexFcoRow, ...]
    turn_ref_rows: tuple[CodexTurnRefRow, ...]


@dataclass(frozen=True)
class EvidenceMatch:
    field: str
    evidence_number: int
    excerpt: str
    url: str
    ref_id: str
    call_id: str
    cite_text: str
    excerpt_position: int
    fco_timestamp: str
    arguments_json: str


@dataclass(frozen=True)
class EvidenceCandidate:
    ref_id: str
    call_id: str
    cite_text: str
    excerpt_position: int
    url: str
    fco_timestamp: datetime
    arguments_json: object


@dataclass(frozen=True)
class ResearcherContext:
    source_key: str
    draw_number: str
    first_name: str
    last_name: str
    cohort: str = GROUND_TRUTH_COHORT
    draw_numbers: tuple[str, ...] = ()


class CodexMatchProcedure:
    dataset_id_field = KTP_NAMEKEY_COL


ValidatedEvidence = dict[str, list[EvidenceMatch]]
RUNTIME_CONFIGURATION: RuntimeConfiguration | None = None


def _has_control_character(value: str) -> bool:
    return any(
        ord(character) < CONTROL_CHARACTER_CEILING or ord(character) == DELETE_CHARACTER_CODEPOINT
        for character in value
    )


def _valid_nonblank(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value == value.strip()
        and not _has_control_character(value)
    )


def _configuration_file(path: Path, setting: str) -> Path:
    if not path.is_absolute():
        raise PushConfigurationError(f"{setting} must be an absolute path")
    if path.is_symlink() or not path.is_file() or not os.access(path, os.R_OK):
        raise PushConfigurationError(
            f"{setting} is not a readable regular file; rerun deploy.sh or correct .env"
        )
    return path


def _detour_db_path(path: Path) -> Path:
    suffix = path.suffix or ".duckdb"
    stem = path.stem if path.suffix else path.name
    return path.with_name(f"{stem}__detour_{DETOUR_ID}{suffix}")


def _seed_evidence_random(sample_seed: int) -> None:
    EVIDENCE_RANDOM.seed(sample_seed)


def registered_release_map(config: PipelineConfig) -> RegisteredResource:
    meta = config.files_config.get(MAP_SUBSET_0_TO_BATCH_KEY)
    if meta is None:
        raise PushConfigurationError(
            f"files_config is missing required detour resource {MAP_SUBSET_0_TO_BATCH_KEY!r}"
        )
    try:
        return register_resource(
            Path(meta["path"]),
            group=ResourceGroup.KTP_PIPELINE_ARTIFACT,
            fragment_type=FragmentType.CSV_ROW,
            description=meta["desc"],
            expected_hash=meta["sha256"],
        )
    except (KeyError, OSError, ValueError) as exc:
        raise PushConfigurationError(
            f"configured {MAP_SUBSET_0_TO_BATCH_KEY} resource is invalid"
        ) from exc


def load_release_batches(resource: RegisteredResource) -> dict[str, str]:
    path = Path(resource)
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != MAP_COLUMNS:
                raise PushConfigurationError(
                    f"{MAP_SUBSET_0_TO_BATCH_KEY} must have exactly columns {MAP_COLUMNS!r}"
                )
            batches: dict[str, str] = {}
            for row_number, row in enumerate(reader, start=2):
                draw_number = row.get(DRAW_LABEL)
                release_batch = row.get(BATCH_LABEL)
                if not _valid_nonblank(draw_number) or not _valid_nonblank(release_batch):
                    raise PushConfigurationError(
                        f"{MAP_SUBSET_0_TO_BATCH_KEY} row {row_number} has blank values"
                    )
                assert isinstance(draw_number, str)
                assert isinstance(release_batch, str)
                if draw_number in batches and batches[draw_number] != release_batch:
                    raise PushConfigurationError(
                        f"{MAP_SUBSET_0_TO_BATCH_KEY} has conflicting draw {draw_number!r}"
                    )
                batches[draw_number] = release_batch
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PushConfigurationError(
            f"configured {MAP_SUBSET_0_TO_BATCH_KEY} CSV is unreadable or malformed"
        ) from exc
    if not batches:
        raise PushConfigurationError(f"configured {MAP_SUBSET_0_TO_BATCH_KEY} CSV is empty")
    return batches


def _innerdict_json_rows(
    value: object,
    *,
    table_name: str,
    source_key: str,
) -> tuple[dict[str, object], ...]:
    if not isinstance(value, str):
        raise PushConfigurationError(f"{table_name} has non-text innerdicts for {source_key}")
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(value.splitlines(), start=1):
        try:
            row: object = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PushConfigurationError(
                f"{table_name} has malformed JSONL for {source_key} at line {line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise PushConfigurationError(
                f"{table_name} has a non-object row for {source_key} at line {line_number}"
            )
        rows.append(cast(dict[str, object], row))
    return tuple(rows)


def _draw_sort_key(
    value: str,
) -> tuple[int, tuple[tuple[int, int | str], ...], str]:
    raw = value.strip()
    normalized = raw.casefold()
    if normalized.startswith(DRAW_PILOT_PREFIX):
        group = 0
        sortable = normalized.removeprefix(DRAW_PILOT_PREFIX)
    elif raw.isdecimal():
        group = 1
        sortable = normalized
    elif raw:
        group = 2
        sortable = normalized
    else:
        group = 3
        sortable = normalized
    tokens = tuple(
        (0, int(part)) if part.isdecimal() else (1, part)
        for part in DRAW_SORT_PART.findall(sortable)
    )
    return (group, tokens, normalized)


def _source_identity_and_draws(
    conn: duckdb.DuckDBPyConnection,
) -> dict[str, tuple[NameKey, tuple[str, ...]]]:
    draws_by_source_key: dict[str, set[str]] = {}
    names_by_source_key: dict[str, NameKey] = {}
    for table_name in (XLSX_INNERDICT_TABLE, DOCX_INNERDICT_TABLE, PARQUET_INNERDICT_TABLE):
        try:
            table_rows = conn.execute(
                f"SELECT {duckdb_quote_identifier(KTP_NAMEKEY_COL)}, "
                f"{duckdb_quote_identifier(KTP_INNERDICT_JSONLINES_COL)} "
                f"FROM {table_name} "
                f"ORDER BY {duckdb_quote_identifier(KTP_NAMEKEY_COL)}"
            ).fetchall()
        except duckdb.Error as exc:
            raise PushConfigurationError(f"configured source DuckDB lacks {table_name}") from exc
        for raw_source_key, jsonlines in table_rows:
            if not isinstance(raw_source_key, str):
                raise PushConfigurationError(f"{table_name} contains a non-text name_key")
            try:
                name_key = NameKey.from_json_key(raw_source_key)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise PushConfigurationError(f"{table_name} contains an invalid name_key") from exc
            source_key = name_key.to_json_key()
            names_by_source_key[source_key] = name_key
            source_draws = draws_by_source_key.setdefault(source_key, set())
            for row in _innerdict_json_rows(
                jsonlines,
                table_name=table_name,
                source_key=source_key,
            ):
                draw_number = row.get(DRAW_LABEL)
                if draw_number is not None:
                    draw_text = str(draw_number).strip()
                    if draw_text:
                        source_draws.add(draw_text)
    return {
        source_key: (
            name_key,
            tuple(sorted(draws_by_source_key[source_key], key=_draw_sort_key)),
        )
        for source_key, name_key in names_by_source_key.items()
    }


def derive_source_population(
    conn: duckdb.DuckDBPyConnection,
    release_batches: Mapping[str, str],
    *,
    sample_seed: int,
) -> tuple[SourcePopulationRow, ...]:
    source_researchers = _source_identity_and_draws(conn)
    rnd_values = list(
        range(RND_START, len(source_researchers) + RND_START)
    )
    Random(sample_seed).shuffle(rnd_values)
    rnd_by_source_key = dict(
        zip(sorted(source_researchers), rnd_values, strict=True)
    )
    ground_truth = {
        source_key
        for source_key, (_name_key, draws) in source_researchers.items()
        if source_key != EXCLUDED_SOURCE_KEY
        and any(release_batches.get(draw) in GROUND_TRUTH_RELEASE_BATCHES for draw in draws)
    }
    try:
        partition_rows = conn.execute(
                f"""
            SELECT
                {duckdb_quote_identifier(KTP_NAMEKEY_COL)},
                {duckdb_quote_identifier(KTP_PARTITION_COL)},
                {duckdb_quote_identifier(KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL)},
                {duckdb_quote_identifier(KTP_PARTITION_FLAG_SSN_COUNT_COL)}
            FROM {CARD_PARTITION_TABLE}
            ORDER BY {duckdb_quote_identifier(KTP_NAMEKEY_COL)}
            """
        ).fetchall()
    except duckdb.Error as exc:
        raise PushConfigurationError(
            f"configured source DuckDB lacks usable {CARD_PARTITION_TABLE} eligibility flags"
        ) from exc
    partition_flags: dict[str, tuple[int, bool, int]] = {}
    for source_key, partition, xlsx_non_exact, ssn_count in partition_rows:
        if (
            not isinstance(source_key, str)
            or not isinstance(partition, int)
            or not isinstance(xlsx_non_exact, bool)
            or not isinstance(ssn_count, int)
            or source_key in partition_flags
        ):
            raise PushConfigurationError(
                f"configured {CARD_PARTITION_TABLE} contains invalid source classifications"
            )
        partition_flags[source_key] = (partition, xlsx_non_exact, ssn_count)
    no_ground_truth = {
        source_key
        for source_key, (partition, xlsx_non_exact, ssn_count) in partition_flags.items()
        if partition == NO_GROUND_TRUTH_PARTITION
        and not xlsx_non_exact
        and ssn_count == NO_GROUND_TRUTH_SSN_COUNT
    }
    missing_source_keys = no_ground_truth - source_researchers.keys()
    overlap = ground_truth & no_ground_truth
    if missing_source_keys:
        raise PushConfigurationError("card-partition eligibility contains unknown source keys")
    if overlap:
        raise PushConfigurationError("ground-truth and no-ground-truth cohorts overlap")
    if len(ground_truth) != EXPECTED_GROUND_TRUTH_RESEARCHERS:
        raise PushConfigurationError(
            "ground-truth cohort cardinality is invalid: "
            f"expected {EXPECTED_GROUND_TRUTH_RESEARCHERS}, got {len(ground_truth)}"
        )
    if len(no_ground_truth) != EXPECTED_NO_GROUND_TRUTH_RESEARCHERS:
        raise PushConfigurationError(
            "no-ground-truth cohort cardinality is invalid: "
            f"expected {EXPECTED_NO_GROUND_TRUTH_RESEARCHERS}, got {len(no_ground_truth)}"
        )
    if len(ground_truth | no_ground_truth) != EXPECTED_ELIGIBLE_RESEARCHERS:
        raise PushConfigurationError("eligible cohort union cardinality is invalid")
    if set(partition_flags) != set(source_researchers):
        raise PushConfigurationError(
            "card-partition source keys do not match innerdict-owned source keys"
        )

    population: list[SourcePopulationRow] = []
    for source_key, (name_key, draws) in source_researchers.items():
        ineligibility_category: IneligibilityCategory | None = None
        if source_key in ground_truth:
            cohort = GROUND_TRUTH_COHORT
        elif source_key in no_ground_truth:
            cohort = NO_GROUND_TRUTH_COHORT
        else:
            cohort = INELIGIBLE_COHORT
            partition, xlsx_non_exact, ssn_count = partition_flags[source_key]
            if source_key == EXCLUDED_SOURCE_KEY:
                ineligibility_category = (
                    IneligibilityCategory.EXCLUDED_DUPLICATE_SOURCE_KEY
                )
            elif any(
                release_batches.get(draw) == INELIGIBLE_RELEASE_BATCH
                for draw in draws
            ):
                ineligibility_category = (
                    IneligibilityCategory.RELEASE_BATCH_SUBSET_8
                )
            elif partition == KTP_PARTITION_SSN_VALUE:
                ineligibility_category = IneligibilityCategory.STAGING_PARTITION_2
            elif partition == KTP_PARTITION_DOCX_VALUE and xlsx_non_exact:
                ineligibility_category = (
                    IneligibilityCategory.STAGING_PARTITION_4_XLSX_NON_EXACT
                )
            elif (
                partition == KTP_PARTITION_DOCX_VALUE
                and ssn_count > NO_GROUND_TRUTH_SSN_COUNT
            ):
                ineligibility_category = (
                    IneligibilityCategory.STAGING_PARTITION_4_MULTIPLE_SSN
                )
            else:
                raise PushConfigurationError(
                    "an ineligible source key has no recognized category"
                )
        population.append(SourcePopulationRow(
            source_key=source_key,
            rnd=rnd_by_source_key[source_key],
            first_name=name_key.first_name,
            last_name=name_key.last_name,
            draw_numbers=tuple(sorted(draws, key=_draw_sort_key)),
            cohort=cohort,
            ineligibility_category=ineligibility_category,
        ))

    population.sort(key=lambda row: (
        tuple(_draw_sort_key(draw) for draw in row.draw_numbers),
        row.first_name.casefold(),
        row.last_name.casefold(),
        row.source_key,
    ))
    cohort_counts = Counter(row.cohort for row in population)
    ineligibility_counts = Counter(
        row.ineligibility_category
        for row in population
        if row.ineligibility_category is not None
    )
    if cohort_counts != {
        GROUND_TRUTH_COHORT: EXPECTED_GROUND_TRUTH_RESEARCHERS,
        NO_GROUND_TRUTH_COHORT: EXPECTED_NO_GROUND_TRUTH_RESEARCHERS,
        INELIGIBLE_COHORT: EXPECTED_INELIGIBLE_RESEARCHERS,
    }:
        raise PushConfigurationError("source population cohort cardinalities are invalid")
    if ineligibility_counts != EXPECTED_INELIGIBILITY_COUNTS:
        raise PushConfigurationError("source population ineligibility categories are invalid")
    if len(population) != EXPECTED_SOURCE_RESEARCHERS:
        raise PushConfigurationError("source population cardinality is invalid")
    if {row.rnd for row in population} != set(
        range(RND_START, EXPECTED_SOURCE_RESEARCHERS + RND_START)
    ):
        raise PushConfigurationError("source population rnd values are invalid")
    if (
        sum(len(row.draw_numbers) > 1 for row in population)
        != EXPECTED_MULTIDRAW_SOURCE_RESEARCHERS
    ):
        raise PushConfigurationError("source population contracted-draw count is invalid")
    return tuple(population)


def eligible_cohorts(
    source_population: Sequence[SourcePopulationRow],
) -> dict[str, str]:
    return {
        row.source_key: row.cohort
        for row in source_population
        if row.cohort != INELIGIBLE_COHORT
    }


def _control_base_url() -> str | None:
    raw = CONTROL_BASE_URL
    if not raw:
        return None
    if raw != raw.strip() or _has_control_character(raw):
        raise PushConfigurationError(f"{CONTROL_URL_ENV_NAME} is invalid")
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "http"
        or parsed.hostname != CONTROL_HOST
        or parsed.port != CONTROL_PORT
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise PushConfigurationError(
            f"{CONTROL_URL_ENV_NAME} must be http://{CONTROL_HOST}:{CONTROL_PORT}"
        )
    return raw.rstrip("/")


def _control_request(
    base_url: str,
    path: str,
    *,
    method: str,
    body: bytes | None = None,
) -> bytes:
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib_request.Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib_request.urlopen(request, timeout=CONTROL_HTTP_TIMEOUT_SECONDS) as response:
            return response.read()
    except (OSError, urllib_error.URLError, urllib_error.HTTPError) as exc:
        raise PushConfigurationError("Control Centre endpoint is unavailable") from exc


def sanctioned_snapshot() -> SanctionSnapshot:
    base_url = _control_base_url()
    if base_url is None:
        return SanctionSnapshot(
            run_id=None,
            source_key=None,
            session_id=None,
            rollout_guest_path=ROLLOUT_JSONL,
            control_base_url=None,
        )
    try:
        snapshot = ControlSnapshot.model_validate_json(
            _control_request(base_url, CONTROL_CURRENT_PATH, method="GET")
        )
    except ValidationError as exc:
        raise PushConfigurationError("Control Centre returned malformed sanction state") from exc
    if snapshot.sanctioned_run is None:
        raise PushConfigurationError("Control Centre has no sanctioned run")
    run = snapshot.sanctioned_run
    with CONSUMED_RUN_LOCK:
        if run.run_id in CONSUMED_RUN_IDS:
            raise PushConfigurationError("Control Centre run sanction has already been consumed")
    return SanctionSnapshot(
        run_id=run.run_id,
        source_key=run.source_key,
        session_id=run.session_id,
        rollout_guest_path=run.rollout_jsonl,
        control_base_url=base_url,
    )


def consume_sanction(snapshot: SanctionSnapshot) -> None:
    if snapshot.run_id is None:
        return
    with CONSUMED_RUN_LOCK:
        CONSUMED_RUN_IDS.add(snapshot.run_id)


def acknowledge_sanction(snapshot: SanctionSnapshot, attempt_id: str) -> None:
    if snapshot.run_id is None or snapshot.control_base_url is None:
        return
    assert snapshot.source_key is not None
    assert snapshot.session_id is not None
    body = ControlAcceptedRequest(
        source_key=snapshot.source_key,
        session_id=snapshot.session_id,
        attempt_id=attempt_id,
    ).model_dump_json().encode("utf-8")
    path = CONTROL_ACCEPTED_PATH_TEMPLATE.format(run_id=snapshot.run_id)
    try:
        response = ControlAcceptedResponse.model_validate_json(
            _control_request(snapshot.control_base_url, path, method="POST", body=body)
        )
    except ValidationError as exc:
        raise PushConfigurationError("Control Centre returned malformed acknowledgement") from exc
    if not response.acknowledged:
        raise PushConfigurationError("Control Centre refused accepted-run acknowledgement")


def configure_runtime(config_path: Path) -> RuntimeConfiguration:
    global RUNTIME_CONFIGURATION

    try:
        pipeline = PipelineConfig.from_json(config_path)
    except (OSError, ValueError) as exc:
        raise PushConfigurationError(f"--config is invalid or unreadable: {config_path}") from exc
    if pipeline.output_format not in {"txt", "docx"}:
        raise PushConfigurationError("config output_format must be txt or docx")
    if not pipeline.db_file.is_file() or not os.access(pipeline.db_file, os.R_OK):
        raise PushConfigurationError(
            f"configured source DuckDB is not readable: {pipeline.db_file}"
        )
    if pipeline.output_format == "docx" and (
        not pipeline.pandoc_reference_docx.is_file()
        or not os.access(pipeline.pandoc_reference_docx, os.R_OK)
    ):
        raise PushConfigurationError(
            "configured DOCX output requires a readable pandoc_reference_docx"
        )
    try:
        ZoneInfo(pipeline.timezone)
    except (KeyError, ValueError) as exc:
        raise PushConfigurationError(
            f"configured timezone is invalid: {pipeline.timezone}"
        ) from exc

    release_map = registered_release_map(pipeline)
    release_batches = load_release_batches(release_map)
    source_conn: duckdb.DuckDBPyConnection | None = None
    try:
        source_conn = duckdb.connect(str(pipeline.db_file), read_only=True)
        source_population = derive_source_population(
            source_conn,
            release_batches,
            sample_seed=pipeline.sample_seed,
        )
    except duckdb.Error as exc:
        raise PushConfigurationError("configured source DuckDB could not be validated") from exc
    finally:
        if source_conn is not None:
            source_conn.close()

    detour_db_path = _detour_db_path(pipeline.db_file)
    if detour_db_path == pipeline.db_file:
        raise PushConfigurationError("detour DuckDB path must differ from source DuckDB")
    RUNTIME_CONFIGURATION = RuntimeConfiguration(
        pipeline=pipeline,
        detour_db_path=detour_db_path,
        release_map=release_map,
        source_population=source_population,
        eligible_cohorts=eligible_cohorts(source_population),
    )
    return RUNTIME_CONFIGURATION


def runtime_configuration() -> RuntimeConfiguration:
    if RUNTIME_CONFIGURATION is None:
        raise PushConfigurationError(
            f"API was not started with required --config {CONFIG_FILENAME}"
        )
    return RUNTIME_CONFIGURATION


def push_configuration(rollout_jsonl: str | None = None) -> PushConfiguration:
    raw_rollout = ROLLOUT_JSONL if rollout_jsonl is None else rollout_jsonl
    if not raw_rollout.strip():
        raise PushConfigurationError(
            f"{ROLLOUT_ENV_NAME} is not set; add the active chat rollout path "
            "to the repository-root .env and restart the API"
        )
    if raw_rollout != raw_rollout.strip() or _has_control_character(raw_rollout):
        raise PushConfigurationError(
            f"{ROLLOUT_ENV_NAME} contains whitespace or control characters; "
            "correct .env and restart the API"
        )

    rollout_path = PurePosixPath(raw_rollout)
    if str(rollout_path) != raw_rollout or any(
        part in {"", ".", ".."} for part in rollout_path.parts
    ):
        raise PushConfigurationError(
            f"{ROLLOUT_ENV_NAME} must be normalized without traversal; "
            "correct .env and restart the API"
        )
    try:
        relative_path = rollout_path.relative_to(CODEX_SESSIONS_ROOT)
    except ValueError as exc:
        raise PushConfigurationError(
            f"{ROLLOUT_ENV_NAME} must be below {CODEX_SESSIONS_ROOT}; "
            "correct .env and restart the API"
        ) from exc
    if (
        relative_path == PurePosixPath(".")
        or not relative_path.name.startswith("rollout-")
        or relative_path.suffix != ".jsonl"
    ):
        raise PushConfigurationError(
            f"{ROLLOUT_ENV_NAME} must name a rollout-*.jsonl file; correct .env and restart the API"
        )

    if not _valid_nonblank(AIVM_INSTANCE):
        raise PushConfigurationError(
            "FASTAPI_DETOUR_AIVM_INSTANCE is invalid; correct .env and restart the API"
        )
    if not _valid_nonblank(AIVM_USER):
        raise PushConfigurationError(
            "FASTAPI_DETOUR_AIVM_USER is invalid; correct .env and restart the API"
        )
    if not AIVM_SSH_PORT.isdecimal() or not MIN_TCP_PORT <= int(AIVM_SSH_PORT) <= MAX_TCP_PORT:
        raise PushConfigurationError(
            "FASTAPI_DETOUR_AIVM_SSH_PORT is invalid; correct .env and restart the API"
        )

    return PushConfiguration(
        rollout_guest_path=raw_rollout,
        rollout_relative_path=relative_path,
        appendwatch_report=_configuration_file(
            APPENDWATCH_REPORT,
            "FASTAPI_DETOUR_APPENDWATCH_REPORT",
        ),
        lima_ssh_config=_configuration_file(
            LIMA_SSH_CONFIG_PATH,
            "FASTAPI_DETOUR_LIMA_SSH_CONFIG",
        ),
        identity_file=_configuration_file(
            AIVM_IDENTITY_FILE,
            "FASTAPI_DETOUR_AIVM_IDENTITY_FILE",
        ),
        known_hosts_file=_configuration_file(
            AIVM_KNOWN_HOSTS_FILE,
            "FASTAPI_DETOUR_AIVM_KNOWN_HOSTS_FILE",
        ),
        ssh_target=f"{AIVM_INSTANCE}-{AIVM_USER}",
        host_key_alias=f"lima-{AIVM_INSTANCE}-{AIVM_USER}",
    )


def new_attempt_id(attempt_timestamp: datetime | None = None) -> str:
    current_timestamp = attempt_timestamp or datetime.now(timezone.utc)
    timestamp_text = current_timestamp.strftime("%Y%m%dT%H%M%S_%fZ")
    return f"{timestamp_text}_{uuid4().hex}"


def create_attempt(attempt_id: str) -> Path:
    attempt_dir = ATTEMPTS_DIR / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=False)
    return attempt_dir


def _fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _archived_file(path: Path) -> ArchivedFile:
    digest = hashlib.sha256()
    size = 0
    line_count = 0
    final_byte = b""
    with path.open("rb") as stream:
        while chunk := stream.read(ARCHIVE_HASH_CHUNK_BYTES):
            size += len(chunk)
            digest.update(chunk)
            line_count += chunk.count(b"\n")
            final_byte = chunk[-1:]
    if size and final_byte != b"\n":
        line_count += 1
    return ArchivedFile(
        path=path,
        size=size,
        sha256=digest.hexdigest(),
        line_count=line_count,
    )


def _publish_archive(temporary: Path, destination: Path) -> ArchivedFile:
    _fsync_file(temporary)
    os.replace(temporary, destination)
    _fsync_directory(destination.parent)
    return _archived_file(destination)


def _aivm_connection_options(
    *,
    lima_ssh_config: Path,
    identity_file: Path,
    known_hosts_file: Path,
    host_key_alias: str,
) -> list[str]:
    return [
        "-F",
        str(lima_ssh_config),
        "-o",
        f"ProxyJump=lima-{AIVM_INSTANCE}",
        "-o",
        "HostName=127.0.0.1",
        "-o",
        f"Port={AIVM_SSH_PORT}",
        "-o",
        f"User={AIVM_USER}",
        "-o",
        f"IdentityFile={identity_file}",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ClearAllForwardings=no",
        "-o",
        f"UserKnownHostsFile={known_hosts_file}",
        "-o",
        f"HostKeyAlias={host_key_alias}",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]


def _host_workbook() -> Path:
    HOST_WORKBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not HOST_WORKBOOK_PATH.exists():
        _atomic_write_text(HOST_WORKBOOK_PATH, "")
    if (
        HOST_WORKBOOK_PATH.is_symlink()
        or not HOST_WORKBOOK_PATH.is_file()
        or not os.access(HOST_WORKBOOK_PATH, os.R_OK | os.W_OK)
    ):
        raise PushConfigurationError("host workbook is not a readable writable regular file")
    return HOST_WORKBOOK_PATH


def initialize_guest_workbook() -> None:
    global WORKBOOK_INITIALIZED

    host_workbook = _host_workbook()
    lima_ssh_config = _configuration_file(
        LIMA_SSH_CONFIG_PATH,
        "FASTAPI_DETOUR_LIMA_SSH_CONFIG",
    )
    identity_file = _configuration_file(
        AIVM_IDENTITY_FILE,
        "FASTAPI_DETOUR_AIVM_IDENTITY_FILE",
    )
    known_hosts_file = _configuration_file(
        AIVM_KNOWN_HOSTS_FILE,
        "FASTAPI_DETOUR_AIVM_KNOWN_HOSTS_FILE",
    )
    options = _aivm_connection_options(
        lima_ssh_config=lima_ssh_config,
        identity_file=identity_file,
        known_hosts_file=known_hosts_file,
        host_key_alias=AIVM_HOST_KEY_ALIAS,
    )
    try:
        subprocess.run(
            ["ssh", *options, AIVM_SSH_TARGET, "mkdir", "-p", "--", str(AIVM_WORKDIR)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SSH_TIMEOUT_SECONDS,
        )
        subprocess.run(
            [
                "scp",
                *options,
                "--",
                str(host_workbook),
                f"{AIVM_SSH_TARGET}:{AIVM_WORKBOOK_PATH}",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SCP_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PushConfigurationError(
            "host workbook could not be initialized in the AIVM workdir"
        ) from exc
    with WORKBOOK_STATE_LOCK:
        WORKBOOK_INITIALIZED = True


def copy_guest_workbook(
    configuration: PushConfiguration,
    attempt_dir: Path,
    attempt_id: str,
) -> ArchivedFile:
    temporary = attempt_dir / ".workbook.tmp"
    destination = attempt_dir / f"workbook.{attempt_id}.md"
    options = _aivm_connection_options(
        lima_ssh_config=configuration.lima_ssh_config,
        identity_file=configuration.identity_file,
        known_hosts_file=configuration.known_hosts_file,
        host_key_alias=configuration.host_key_alias,
    )
    try:
        subprocess.run(
            [
                "scp",
                *options,
                "--",
                f"{configuration.ssh_target}:{AIVM_WORKBOOK_PATH}",
                str(temporary),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SCP_TIMEOUT_SECONDS,
        )
        if not temporary.is_file() or temporary.is_symlink():
            raise PushConfigurationError("SCP did not produce a regular workbook archive")
        archive = _publish_archive(temporary, destination)
        host_temporary = HOST_WORKBOOK_PATH.with_name(f".{HOST_WORKBOOK_PATH.name}.tmp")
        try:
            shutil.copyfile(archive.path, host_temporary)
            _fsync_file(host_temporary)
            os.replace(host_temporary, _host_workbook())
            _fsync_directory(HOST_WORKBOOK_PATH.parent)
        finally:
            host_temporary.unlink(missing_ok=True)
        return archive
    except (OSError, subprocess.SubprocessError) as exc:
        raise PushConfigurationError("guest workbook could not be archived") from exc
    finally:
        temporary.unlink(missing_ok=True)


def copy_rollout(
    configuration: PushConfiguration,
    attempt_dir: Path,
    attempt_id: str,
) -> ArchivedFile:
    temporary = attempt_dir / ".rollout.tmp"
    destination = attempt_dir / f"rollout.{attempt_id}.jsonl"
    command = [
        "scp",
        "-F",
        str(configuration.lima_ssh_config),
        "-o",
        f"ProxyJump=lima-{AIVM_INSTANCE}",
        "-o",
        "HostName=127.0.0.1",
        "-o",
        f"Port={AIVM_SSH_PORT}",
        "-o",
        f"User={AIVM_USER}",
        "-o",
        f"IdentityFile={configuration.identity_file}",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ClearAllForwardings=no",
        "-o",
        f"UserKnownHostsFile={configuration.known_hosts_file}",
        "-o",
        f"HostKeyAlias={configuration.host_key_alias}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "--",
        f"{configuration.ssh_target}:{configuration.rollout_guest_path}",
        str(temporary),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SCP_TIMEOUT_SECONDS,
        )
        if not temporary.is_file() or temporary.is_symlink():
            raise PushConfigurationError(
                "SCP did not produce a regular rollout archive; verify AIVM deployment"
            )
        return _publish_archive(temporary, destination)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PushConfigurationError(
            "rollout SCP failed; verify the configured rollout and AIVM SSH deployment"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def copy_appendwatch_report(
    configuration: PushConfiguration,
    attempt_dir: Path,
    attempt_id: str,
) -> ArchivedFile:
    temporary = attempt_dir / ".appendwatch-tree.tmp"
    destination = attempt_dir / f"appendwatch-tree.{attempt_id}.txt"
    try:
        shutil.copyfile(configuration.appendwatch_report, temporary)
        return _publish_archive(temporary, destination)
    except OSError as exc:
        raise PushConfigurationError(
            "appendwatch status could not be archived; verify deployment and mounted report"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def parse_appendwatch_report(
    report_path: Path,
    rollout_relative_path: PurePosixPath,
) -> None:
    try:
        report = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PushValidationError("archived appendwatch report is unreadable") from exc
    if not report.endswith("\n"):
        raise PushValidationError("archived appendwatch report is incomplete")

    lines = report.splitlines()
    if not lines or lines[0] != ".":
        if lines and lines[0].startswith(".  [COMPROMISED:"):
            raise PushValidationError("appendwatch reports global monitoring degradation")
        raise PushValidationError("archived appendwatch report has a malformed root")

    target = rollout_relative_path.parts
    directories: list[tuple[str, bool]] = []
    seen_paths: set[tuple[str, ...]] = set()
    target_entries: list[tuple[str, bool]] = []
    line_index = 1

    while line_index < len(lines) and lines[line_index] != "":
        match = TREE_LINE.fullmatch(lines[line_index])
        if match is None:
            raise PushValidationError("archived appendwatch report contains a malformed tree line")
        indent = match.group("indent")
        depth = len(indent) // TREE_INDENT_WIDTH
        if depth > len(directories):
            raise PushValidationError("archived appendwatch report contains invalid nesting")
        directories = directories[:depth]
        parent_parts = tuple(name for name, _compromised in directories)
        parent_compromised = any(compromised for _name, compromised in directories)
        body = match.group("body")

        compromised_directory = re.fullmatch(
            rf"{re.escape(APPENDWATCH_COMPROMISED_PREFIX)}(?P<name>[^/]+)/  \[.+\]",
            body,
        )
        if compromised_directory is not None:
            name = compromised_directory.group("name")
            path = (*parent_parts, name)
            if path in seen_paths:
                raise PushValidationError("archived appendwatch report contains a duplicate path")
            seen_paths.add(path)
            directories.append((name, True))
            line_index += 1
            continue

        if body.endswith("/") and not body.startswith(("OK ", "COMPROMISED ")):
            name = body[:-1]
            if not name or "/" in name:
                raise PushValidationError(
                    "archived appendwatch report contains a malformed directory"
                )
            path = (*parent_parts, name)
            if path in seen_paths:
                raise PushValidationError("archived appendwatch report contains a duplicate path")
            seen_paths.add(path)
            directories.append((name, parent_compromised))
            line_index += 1
            continue

        ok_file = re.fullmatch(
            rf"{re.escape(APPENDWATCH_OK_PREFIX)}(?P<name>[^/]+)",
            body,
        )
        compromised_file = re.fullmatch(
            rf"{re.escape(APPENDWATCH_COMPROMISED_PREFIX)}"
            r"(?P<name>[^/]+?)(?:  \[.*\])?",
            body,
        )
        if ok_file is None and compromised_file is None:
            raise PushValidationError("archived appendwatch report contains a malformed file entry")
        name = (ok_file or compromised_file).group("name")  # type: ignore[union-attr]
        path = (*parent_parts, name)
        if path in seen_paths:
            raise PushValidationError("archived appendwatch report contains a duplicate path")
        seen_paths.add(path)
        if path == target:
            target_entries.append((
                "OK" if ok_file is not None else "COMPROMISED",
                parent_compromised,
            ))
        line_index += 1

    if line_index < len(lines):
        if lines[line_index:] == [""]:
            raise PushValidationError("archived appendwatch report has a stray blank line")
        if lines[line_index : line_index + 2] != [
            "",
            "removed or replaced (no longer a regular file):",
        ]:
            raise PushValidationError("archived appendwatch report has a malformed removed section")
        for removed_line in lines[line_index + 2 :]:
            removed = re.fullmatch(
                rf"    {re.escape(APPENDWATCH_COMPROMISED_PREFIX)}"
                r"(?P<path>.+?)(?:  \[.*\])?",
                removed_line,
            )
            if removed is None:
                raise PushValidationError(
                    "archived appendwatch report has a malformed removed entry"
                )
            if PurePosixPath(removed.group("path")).parts == target:
                raise PushValidationError("configured rollout was removed or replaced")

    if len(target_entries) != 1:
        reason = "missing" if not target_entries else "ambiguous"
        raise PushValidationError(f"configured rollout status is {reason} in archived report")
    status, compromised_ancestor = target_entries[0]
    if status != "OK" or compromised_ancestor:
        raise PushValidationError("configured rollout is not OK beneath monitored ancestors")


def parse_rollout(rollout_path: Path) -> tuple[RolloutRecord, ...]:
    try:
        raw_lines = rollout_path.read_bytes().splitlines(keepends=True)
    except OSError as exc:
        raise PushValidationError("archived rollout is unreadable") from exc

    records: list[RolloutRecord] = []
    for line_number, raw_line in enumerate(raw_lines, start=1):
        completed = raw_line.endswith(b"\n")
        encoded = raw_line[:-1] if completed else raw_line
        if encoded.endswith(b"\r"):
            encoded = encoded[:-1]
        try:
            value: object = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if line_number == len(raw_lines) and not completed:
                break
            raise PushValidationError(
                f"archived rollout contains malformed JSONL at line {line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise PushValidationError(f"archived rollout line {line_number} is not a JSON object")
        records.append(
            RolloutRecord(
                line_number=line_number,
                line_sha256=hashlib.sha256(raw_line).hexdigest(),
                value=cast(dict[str, object], value),
            )
        )
    return tuple(records)


def _timestamp(value: object, *, label: str) -> str:
    if not _valid_nonblank(value):
        raise PushValidationError(f"{label} has an invalid timestamp")
    raw = cast(str, value)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PushValidationError(f"{label} has an invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise PushValidationError(f"{label} timestamp must include a timezone")
    return raw


def _web_arguments(payload: Mapping[str, object], line_number: int) -> dict[str, object]:
    call_id = payload.get("call_id")
    if not _valid_nonblank(call_id):
        raise PushValidationError(f"web call at rollout line {line_number} has an invalid call_id")
    arguments = payload.get("arguments")
    if not isinstance(arguments, str):
        raise PushValidationError(f"web call {call_id} has unsupported arguments")
    try:
        decoded: object = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise PushValidationError(f"web call {call_id} has malformed arguments") from exc
    if not isinstance(decoded, dict):
        raise PushValidationError(f"web call {call_id} arguments are not a JSON object")
    eligible_actions = [action for action in ELIGIBLE_WEB_ACTIONS if decoded.get(action)]
    if len(eligible_actions) != 1:
        raise PushValidationError(
            f"web call {call_id} must contain exactly one eligible web action"
        )
    return cast(dict[str, object], decoded)


def _session_metadata(
    records: tuple[RolloutRecord, ...],
    *,
    timezone_name: str,
    configured_rollout_basename: str,
) -> SessionMetadata:
    session_records = [record for record in records if record.value.get("type") == "session_meta"]
    if len(session_records) != 1:
        raise PushValidationError("rollout must contain exactly one session_meta record")
    session_record = session_records[0]
    payload = session_record.value.get("payload")
    if not isinstance(payload, dict):
        raise PushValidationError("session_meta payload is malformed")
    session_id = payload.get("session_id")
    if not _valid_nonblank(session_id):
        raise PushValidationError("session_meta session_id is invalid")
    session_id = cast(str, session_id)
    payload_timestamp = _timestamp(payload.get("timestamp"), label="session_meta payload")
    response_timestamp = _timestamp(
        session_record.value.get("timestamp"),
        label="session_meta response",
    )
    local_timestamp = datetime.fromisoformat(payload_timestamp.replace("Z", "+00:00")).astimezone(
        ZoneInfo(timezone_name)
    )
    rollout_filename = f"rollout-{local_timestamp:%Y-%m-%dT%H-%M-%S}-{session_id}.jsonl"
    if rollout_filename != configured_rollout_basename:
        raise PushValidationError("session metadata does not match the configured rollout basename")

    turn_context_payload = next(
        (
            cast(dict[str, object], record.value["payload"])
            for record in records
            if record.value.get("type") == "turn_context"
            and isinstance(record.value.get("payload"), dict)
        ),
        None,
    )
    if turn_context_payload is None:
        raise PushValidationError("rollout has no valid turn_context metadata")
    model = turn_context_payload.get("model")
    reasoning_effort = turn_context_payload.get("effort")
    try:
        compact = CompactSessionMetadata.model_validate({
            "originator": payload.get("originator"),
            "source": payload.get("source"),
            "cli_version": payload.get("cli_version"),
            "model_provider": payload.get("model_provider"),
            "model": model,
            "reasoning_effort": reasoning_effort,
            "session_id": session_id,
            "timestamp": response_timestamp,
        })
    except ValidationError as exc:
        raise PushValidationError("rollout session metadata fields are incomplete") from exc
    return SessionMetadata(
        session_id=session_id,
        timestamp=response_timestamp,
        rollout_filename=rollout_filename,
        compact=compact,
    )


def _eligible_fco_text(record: RolloutRecord, payload: Mapping[str, object]) -> str | None:
    output = payload.get("output")
    marker_start = f"{CODEX_CITE_MARKER_PREFIX}turn"
    if isinstance(output, list):
        contains_marker = any(
            isinstance(block, dict)
            and isinstance(block.get("text"), str)
            and marker_start in cast(str, block["text"])
            for block in output
        )
    else:
        contains_marker = isinstance(output, str) and marker_start in output
    if not contains_marker:
        return None
    if (
        not isinstance(output, list)
        or len(output) != 1
        or not isinstance(output[0], dict)
        or output[0].get("type") != "input_text"
        or not isinstance(output[0].get("text"), str)
    ):
        raise PushValidationError(
            f"cited function output at rollout line {record.line_number} "
            "must contain exactly one input_text block"
        )
    return cast(str, output[0]["text"])


def build_rollout_index(
    records: tuple[RolloutRecord, ...],
    *,
    timezone_name: str,
    configured_rollout_basename: str,
) -> RolloutIndex:
    session = _session_metadata(
        records,
        timezone_name=timezone_name,
        configured_rollout_basename=configured_rollout_basename,
    )
    calls: dict[str, list[RolloutRecord]] = {}
    events: dict[str, list[RolloutRecord]] = {}
    cited_outputs: list[tuple[RolloutRecord, dict[str, object], str]] = []

    for record in records:
        value = record.value
        payload = value.get("payload")
        if not isinstance(payload, dict):
            continue
        payload_type = payload.get("type")
        if (
            value.get("type") == "response_item"
            and payload_type == "function_call"
            and payload.get("namespace") == "web"
            and payload.get("name") == "run"
        ):
            call_id = payload.get("call_id")
            if not _valid_nonblank(call_id):
                raise PushValidationError(
                    f"web call at rollout line {record.line_number} has an invalid call_id"
                )
            calls.setdefault(cast(str, call_id), []).append(record)
        elif value.get("type") == "event_msg" and payload_type == "web_search_end":
            call_id = payload.get("call_id")
            if not _valid_nonblank(call_id):
                raise PushValidationError(
                    f"web event at rollout line {record.line_number} has an invalid call_id"
                )
            events.setdefault(cast(str, call_id), []).append(record)
        elif value.get("type") == "response_item" and payload_type == "function_call_output":
            text = _eligible_fco_text(record, payload)
            if text is not None:
                cited_outputs.append((record, payload, text))

    fc_rows: list[CodexFcRow] = []
    fco_rows: list[CodexFcoRow] = []
    turn_ref_rows: list[CodexTurnRefRow] = []
    seen_fc_ids: set[str] = set()
    seen_fco_ids: set[str] = set()
    seen_call_ids: set[str] = set()
    for output_record, output_payload, output_text in cited_outputs:
        call_id = output_payload.get("call_id")
        fco_id = output_payload.get("id")
        if not _valid_nonblank(call_id) or not _valid_nonblank(fco_id):
            raise PushValidationError(
                f"cited function output at rollout line {output_record.line_number} has invalid IDs"
            )
        call_id = cast(str, call_id)
        fco_id = cast(str, fco_id)
        if call_id in seen_call_ids or fco_id in seen_fco_ids:
            raise PushValidationError("cited function output IDs are duplicated")
        seen_call_ids.add(call_id)
        seen_fco_ids.add(fco_id)
        fco_timestamp = _timestamp(
            output_record.value.get("timestamp"),
            label=f"function output {fco_id}",
        )

        matching_calls = calls.get(call_id, [])
        matching_events = events.get(call_id, [])
        if len(matching_calls) != 1 or len(matching_events) != 1:
            raise PushValidationError(
                f"cited web chain {call_id} must have one function call and one web_search_end"
            )
        call_record = matching_calls[0]
        event_record = matching_events[0]
        if not (call_record.line_number < event_record.line_number < output_record.line_number):
            raise PushValidationError(f"cited web chain {call_id} is out of order")
        call_payload = cast(dict[str, object], call_record.value["payload"])
        fc_id = call_payload.get("id")
        if not _valid_nonblank(fc_id) or cast(str, fc_id) in seen_fc_ids:
            raise PushValidationError(f"web call {call_id} has an invalid or duplicate fc_id")
        fc_id = cast(str, fc_id)
        seen_fc_ids.add(fc_id)
        arguments = _web_arguments(call_payload, call_record.line_number)
        arguments_json = json.dumps(
            arguments,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        fc_rows.append(
            CodexFcRow(
                timestamp=_timestamp(
                    call_record.value.get("timestamp"),
                    label=f"function call {fc_id}",
                ),
                fc_id=fc_id,
                call_id=call_id,
                name="run",
                namespace="web",
                arguments_json=arguments_json,
            )
        )
        fco_rows.append(
            CodexFcoRow(
                timestamp=fco_timestamp,
                fco_id=fco_id,
                call_id=call_id,
            )
        )

        try:
            sections = codex_parse.extract_cite_sections(
                output_text,
                marker_prefix=CODEX_CITE_MARKER_PREFIX,
                marker_suffix=CODEX_CITE_MARKER_SUFFIX,
                ref_id_pattern=CODEX_REF_ID_PATTERN,
                result_separator=CODEX_RESULT_SEPARATOR,
            )
        except ValueError as exc:
            raise PushValidationError(str(exc)) from exc
        event_payload = cast(dict[str, object], event_record.value["payload"])
        results = event_payload.get("results")
        if not isinstance(results, list):
            raise PushValidationError(f"web event {call_id} has unsupported results")
        for section in sections:
            matching_results = [
                result
                for result in results
                if isinstance(result, dict)
                and result.get("type") == "text_result"
                and result.get("ref_id") == section.ref_id
            ]
            if len(matching_results) != 1:
                raise PushValidationError(
                    f"citation {section.ref_id} does not resolve to one event result"
                )
            try:
                result = CodexTextResult.model_validate(matching_results[0])
            except ValidationError as exc:
                raise PushValidationError(
                    f"citation {section.ref_id} has unsupported result metadata"
                ) from exc
            if not _valid_nonblank(result.url):
                continue
            turn_ref_rows.append(
                CodexTurnRefRow(
                    ref_id=section.ref_id,
                    call_id=call_id,
                    domain=result.domain,
                    snippet=result.snippet,
                    thumbnail_url=result.thumbnail_url,
                    title=result.title,
                    url=cast(str, result.url),
                    cite_text=section.text,
                )
            )

    return RolloutIndex(
        session=session,
        fc_rows=tuple(fc_rows),
        fco_rows=tuple(fco_rows),
        turn_ref_rows=tuple(turn_ref_rows),
    )


def _create_codex_schema(conn: duckdb.DuckDBPyConnection) -> None:
    for sequence in (
        CODEX_FC_ID_SEQUENCE,
        CODEX_FCO_ID_SEQUENCE,
        CODEX_CALLS_ID_SEQUENCE,
        CODEX_TURN_REF_ID_SEQUENCE,
    ):
        conn.execute(f"CREATE SEQUENCE IF NOT EXISTS {sequence}")

    id_col = duckdb_quote_identifier(CODEX_ID_COL)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CODEX_FC_TABLE} (
            {id_col} BIGINT PRIMARY KEY DEFAULT nextval('{CODEX_FC_ID_SEQUENCE}'),
            {duckdb_quote_identifier(CODEX_FC_TIMESTAMP_COL)} TIMESTAMPTZ NOT NULL,
            {duckdb_quote_identifier(CODEX_FC_ID_COL)} VARCHAR NOT NULL UNIQUE,
            {duckdb_quote_identifier(CODEX_FC_NAME_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_FC_NAMESPACE_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_FC_ARGUMENTS_COL)} JSON NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CODEX_FCO_TABLE} (
            {id_col} BIGINT PRIMARY KEY DEFAULT nextval('{CODEX_FCO_ID_SEQUENCE}'),
            {duckdb_quote_identifier(CODEX_FCO_TIMESTAMP_COL)} TIMESTAMPTZ NOT NULL,
            {duckdb_quote_identifier(CODEX_FCO_ID_COL)} VARCHAR NOT NULL UNIQUE
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CODEX_CALLS_TABLE} (
            {id_col} BIGINT PRIMARY KEY DEFAULT nextval('{CODEX_CALLS_ID_SEQUENCE}'),
            {duckdb_quote_identifier(CODEX_CALL_ID_COL)} VARCHAR NOT NULL UNIQUE,
            {duckdb_quote_identifier(CODEX_FC_ID_COL)} VARCHAR NOT NULL UNIQUE,
            {duckdb_quote_identifier(CODEX_FCO_ID_COL)} VARCHAR NOT NULL UNIQUE,
            {duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} VARCHAR NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CODEX_TURN_REF_TABLE} (
            {id_col} BIGINT PRIMARY KEY DEFAULT nextval('{CODEX_TURN_REF_ID_SEQUENCE}'),
            {duckdb_quote_identifier(CODEX_REF_ID_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_CALL_ID_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_REF_DOMAIN_COL)} VARCHAR,
            {duckdb_quote_identifier(CODEX_REF_SNIPPET_COL)} VARCHAR,
            {duckdb_quote_identifier(CODEX_REF_THUMBNAIL_URL_COL)} VARCHAR,
            {duckdb_quote_identifier(CODEX_REF_TITLE_COL)} VARCHAR,
            {duckdb_quote_identifier(CODEX_REF_URL_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_CITE_TEXT_COL)} VARCHAR NOT NULL,
            UNIQUE (
                {duckdb_quote_identifier(CODEX_CALL_ID_COL)},
                {duckdb_quote_identifier(CODEX_REF_ID_COL)}
            )
        )
        """
    )


def _insert_or_validate(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    key_column: str,
    key_value: str,
    columns: tuple[str, ...],
    values: tuple[object, ...],
) -> None:
    projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
    existing = conn.execute(
        f"SELECT {projection} FROM {table_name} WHERE {duckdb_quote_identifier(key_column)} = ?",
        [key_value],
    ).fetchall()
    if existing:
        if len(existing) != 1 or existing[0] != values:
            raise PushValidationError(
                f"conflicting cumulative rollout row in {table_name} for {key_value}"
            )
        return
    placeholders = ", ".join("?" for _column in columns)
    conn.execute(
        f"INSERT INTO {table_name} ({projection}) VALUES ({placeholders})",
        list(values),
    )


def _datetime_value(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def persist_rollout_index(
    conn: duckdb.DuckDBPyConnection,
    rollout_index: RolloutIndex,
) -> None:
    conn.execute("BEGIN TRANSACTION")
    try:
        _create_codex_schema(conn)
        current_call_ids = {row.call_id for row in rollout_index.fc_rows}
        existing_call_ids = {
            cast(str, row[0])
            for row in conn.execute(
                f"SELECT {duckdb_quote_identifier(CODEX_CALL_ID_COL)} "
                f"FROM {CODEX_CALLS_TABLE} WHERE "
                f"{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?",
                [rollout_index.session.rollout_filename],
            ).fetchall()
        }
        if not existing_call_ids.issubset(current_call_ids):
            raise PushValidationError(
                "archived rollout prefix is older than its persisted provenance index"
            )
        current_turn_keys = {(row.call_id, row.ref_id) for row in rollout_index.turn_ref_rows}
        existing_turn_keys = {
            (cast(str, row[0]), cast(str, row[1]))
            for row in conn.execute(
                f"SELECT "
                f"ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)}, "
                f"ts.{duckdb_quote_identifier(CODEX_REF_ID_COL)} "
                f"FROM {CODEX_TURN_REF_TABLE} ts "
                f"JOIN {CODEX_CALLS_TABLE} calls ON "
                f"calls.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} = "
                f"ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} "
                f"WHERE calls.{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?",
                [rollout_index.session.rollout_filename],
            ).fetchall()
        }
        if not existing_turn_keys.issubset(current_turn_keys):
            raise PushValidationError(
                "archived rollout prefix is older than its persisted citation index"
            )

        fc_by_call = {row.call_id: row for row in rollout_index.fc_rows}
        fco_by_call = {row.call_id: row for row in rollout_index.fco_rows}
        if set(fc_by_call) != current_call_ids or set(fco_by_call) != current_call_ids:
            raise PushValidationError("normalized rollout call linkages are incomplete")
        for function_call_row in rollout_index.fc_rows:
            _insert_or_validate(
                conn,
                table_name=CODEX_FC_TABLE,
                key_column=CODEX_FC_ID_COL,
                key_value=function_call_row.fc_id,
                columns=(
                    CODEX_FC_TIMESTAMP_COL,
                    CODEX_FC_ID_COL,
                    CODEX_FC_NAME_COL,
                    CODEX_FC_NAMESPACE_COL,
                    CODEX_FC_ARGUMENTS_COL,
                ),
                values=(
                    _datetime_value(function_call_row.timestamp),
                    function_call_row.fc_id,
                    function_call_row.name,
                    function_call_row.namespace,
                    function_call_row.arguments_json,
                ),
            )
        for function_output_row in rollout_index.fco_rows:
            _insert_or_validate(
                conn,
                table_name=CODEX_FCO_TABLE,
                key_column=CODEX_FCO_ID_COL,
                key_value=function_output_row.fco_id,
                columns=(CODEX_FCO_TIMESTAMP_COL, CODEX_FCO_ID_COL),
                values=(
                    _datetime_value(function_output_row.timestamp),
                    function_output_row.fco_id,
                ),
            )
        for call_id in sorted(current_call_ids):
            fc_row = fc_by_call[call_id]
            fco_row = fco_by_call[call_id]
            _insert_or_validate(
                conn,
                table_name=CODEX_CALLS_TABLE,
                key_column=CODEX_CALL_ID_COL,
                key_value=call_id,
                columns=(
                    CODEX_CALL_ID_COL,
                    CODEX_FC_ID_COL,
                    CODEX_FCO_ID_COL,
                    CODEX_ROLLOUT_FILENAME_COL,
                ),
                values=(
                    call_id,
                    fc_row.fc_id,
                    fco_row.fco_id,
                    rollout_index.session.rollout_filename,
                ),
            )
        for turn_ref_row in rollout_index.turn_ref_rows:
            key_value = f"{turn_ref_row.call_id}\0{turn_ref_row.ref_id}"
            columns = (
                CODEX_REF_ID_COL,
                CODEX_CALL_ID_COL,
                CODEX_REF_DOMAIN_COL,
                CODEX_REF_SNIPPET_COL,
                CODEX_REF_THUMBNAIL_URL_COL,
                CODEX_REF_TITLE_COL,
                CODEX_REF_URL_COL,
                CODEX_CITE_TEXT_COL,
            )
            projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
            existing = conn.execute(
                f"SELECT {projection} FROM {CODEX_TURN_REF_TABLE} WHERE "
                f"{duckdb_quote_identifier(CODEX_CALL_ID_COL)} = ? AND "
                f"{duckdb_quote_identifier(CODEX_REF_ID_COL)} = ?",
                [turn_ref_row.call_id, turn_ref_row.ref_id],
            ).fetchall()
            values = (
                turn_ref_row.ref_id,
                turn_ref_row.call_id,
                turn_ref_row.domain,
                turn_ref_row.snippet,
                turn_ref_row.thumbnail_url,
                turn_ref_row.title,
                turn_ref_row.url,
                turn_ref_row.cite_text,
            )
            if existing:
                if len(existing) != 1 or existing[0] != values:
                    raise PushValidationError(
                        "conflicting cumulative rollout row in "
                        f"{CODEX_TURN_REF_TABLE} for {key_value}"
                    )
            else:
                placeholders = ", ".join("?" for _column in columns)
                conn.execute(
                    f"INSERT INTO {CODEX_TURN_REF_TABLE} ({projection}) VALUES ({placeholders})",
                    list(values),
                )

        integrity_checks = (
            (
                CODEX_FC_TABLE,
                duckdb_quote_identifier(CODEX_FC_ID_COL),
            ),
            (
                CODEX_FCO_TABLE,
                duckdb_quote_identifier(CODEX_FCO_ID_COL),
            ),
            (
                CODEX_CALLS_TABLE,
                duckdb_quote_identifier(CODEX_CALL_ID_COL),
            ),
            (
                CODEX_TURN_REF_TABLE,
                "("
                + duckdb_quote_identifier(CODEX_CALL_ID_COL)
                + ", "
                + duckdb_quote_identifier(CODEX_REF_ID_COL)
                + ")",
            ),
        )
        for table_name, distinct_expression in integrity_checks:
            integrity_row = conn.execute(
                f"SELECT COUNT(*), COUNT(DISTINCT {distinct_expression}) FROM {table_name}"
            ).fetchone()
            if integrity_row is None:
                raise PushValidationError(
                    f"normalized provenance integrity query failed for {table_name}"
                )
            total, distinct = integrity_row
            if total != distinct:
                raise PushValidationError(
                    f"normalized provenance uniqueness failed for {table_name}"
                )

        linkage_row = conn.execute(
            f"""
            SELECT
                (
                    SELECT COUNT(*)
                    FROM {CODEX_CALLS_TABLE} calls
                    LEFT JOIN {CODEX_FC_TABLE} fc
                      ON fc.{duckdb_quote_identifier(CODEX_FC_ID_COL)} =
                         calls.{duckdb_quote_identifier(CODEX_FC_ID_COL)}
                    WHERE fc.{duckdb_quote_identifier(CODEX_ID_COL)} IS NULL
                ),
                (
                    SELECT COUNT(*)
                    FROM {CODEX_CALLS_TABLE} calls
                    LEFT JOIN {CODEX_FCO_TABLE} fco
                      ON fco.{duckdb_quote_identifier(CODEX_FCO_ID_COL)} =
                         calls.{duckdb_quote_identifier(CODEX_FCO_ID_COL)}
                    WHERE fco.{duckdb_quote_identifier(CODEX_ID_COL)} IS NULL
                ),
                (
                    SELECT COUNT(*)
                    FROM {CODEX_TURN_REF_TABLE} ts
                    LEFT JOIN {CODEX_CALLS_TABLE} calls
                      ON calls.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} =
                         ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)}
                    WHERE calls.{duckdb_quote_identifier(CODEX_ID_COL)} IS NULL
                )
            """
        ).fetchone()
        if linkage_row is None:
            raise PushValidationError("normalized provenance linkage query failed")
        missing_fc_links, missing_fco_links, missing_call_links = linkage_row
        if missing_fc_links or missing_fco_links or missing_call_links:
            raise PushValidationError("normalized provenance relationships are incomplete")

        persisted_call_ids = {
            cast(str, row[0])
            for row in conn.execute(
                f"SELECT {duckdb_quote_identifier(CODEX_CALL_ID_COL)} "
                f"FROM {CODEX_CALLS_TABLE} WHERE "
                f"{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?",
                [rollout_index.session.rollout_filename],
            ).fetchall()
        }
        persisted_turn_keys = {
            (cast(str, row[0]), cast(str, row[1]))
            for row in conn.execute(
                f"SELECT "
                f"ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)}, "
                f"ts.{duckdb_quote_identifier(CODEX_REF_ID_COL)} "
                f"FROM {CODEX_TURN_REF_TABLE} ts "
                f"JOIN {CODEX_CALLS_TABLE} calls ON "
                f"calls.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} = "
                f"ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} "
                f"WHERE calls.{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?",
                [rollout_index.session.rollout_filename],
            ).fetchall()
        }
        if persisted_call_ids != current_call_ids or persisted_turn_keys != current_turn_keys:
            raise PushValidationError(
                "persisted provenance does not match the current archived rollout prefix"
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _render_fco_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _evidence_candidates(rows: list[tuple[Any, ...]]) -> tuple[EvidenceCandidate, ...]:
    candidates: list[EvidenceCandidate] = []
    for row in rows:
        (
            ref_id,
            call_id,
            cite_text,
            excerpt_position,
            url,
            fco_timestamp,
            arguments_json,
        ) = row
        candidates.append(
            EvidenceCandidate(
                ref_id=cast(str, ref_id),
                call_id=cast(str, call_id),
                cite_text=cast(str, cite_text),
                excerpt_position=cast(int, excerpt_position),
                url=cast(str, url),
                fco_timestamp=cast(datetime, fco_timestamp),
                arguments_json=arguments_json,
            )
        )
    return tuple(candidates)


def _rollout_ref_urls(
    conn: duckdb.DuckDBPyConnection,
    *,
    rollout_filename: str,
) -> dict[str, str]:
    rows = conn.execute(
        f"""
        SELECT
            ts.{duckdb_quote_identifier(CODEX_REF_ID_COL)},
            ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)},
            ts.{duckdb_quote_identifier(CODEX_REF_URL_COL)}
        FROM {CODEX_TURN_REF_TABLE} ts
        JOIN {CODEX_CALLS_TABLE} calls
          ON calls.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} =
             ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)}
        WHERE calls.{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?
        ORDER BY ts.{duckdb_quote_identifier(CODEX_ID_COL)}
        """,
        [rollout_filename],
    ).fetchall()
    rows_by_ref: dict[str, set[tuple[str, str]]] = {}
    for ref_id, call_id, url in rows:
        rows_by_ref.setdefault(cast(str, ref_id), set()).add(
            (cast(str, call_id), cast(str, url))
        )
    return {
        ref_id: next(iter(ref_rows))[1]
        for ref_id, ref_rows in rows_by_ref.items()
        if len(ref_rows) == 1
    }


def validate_submission_evidence(
    conn: duckdb.DuckDBPyConnection,
    submission: Submission,
    *,
    rollout_filename: str,
) -> ValidatedEvidence:
    validated: ValidatedEvidence = {}
    evidence_number = 0
    for field, field_submission in submission.evidence_items():
        field_matches: list[EvidenceMatch] = []
        for evidence in field_submission.web_search_excerpts:
            evidence_number += 1
            rows = conn.execute(
                f"""
                SELECT
                    ts.{duckdb_quote_identifier(CODEX_REF_ID_COL)},
                    ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)},
                    ts.{duckdb_quote_identifier(CODEX_CITE_TEXT_COL)},
                    strpos(ts.{duckdb_quote_identifier(CODEX_CITE_TEXT_COL)}, ?),
                    ts.{duckdb_quote_identifier(CODEX_REF_URL_COL)},
                    fco.{duckdb_quote_identifier(CODEX_FCO_TIMESTAMP_COL)},
                    fc.{duckdb_quote_identifier(CODEX_FC_ARGUMENTS_COL)}
                FROM {CODEX_TURN_REF_TABLE} ts
                JOIN {CODEX_CALLS_TABLE} calls
                  ON calls.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} =
                     ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)}
                JOIN {CODEX_FCO_TABLE} fco
                  ON fco.{duckdb_quote_identifier(CODEX_FCO_ID_COL)} =
                     calls.{duckdb_quote_identifier(CODEX_FCO_ID_COL)}
                JOIN {CODEX_FC_TABLE} fc
                  ON fc.{duckdb_quote_identifier(CODEX_FC_ID_COL)} =
                     calls.{duckdb_quote_identifier(CODEX_FC_ID_COL)}
                WHERE calls.{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?
                  AND strpos(
                      ts.{duckdb_quote_identifier(CODEX_CITE_TEXT_COL)}, ?
                  ) > 0
                ORDER BY ts.{duckdb_quote_identifier(CODEX_ID_COL)}
                """,
                [evidence.excerpt, rollout_filename, evidence.excerpt],
            ).fetchall()
            if not rows:
                raise PushValidationError(
                    f"{field}: excerpt has no indexed match; "
                    f"excerpt={evidence.excerpt!r} url={evidence.url!r}"
                )
            candidates = tuple(
                candidate
                for candidate in _evidence_candidates(rows)
                if candidate.url == evidence.url
            )
            if not candidates:
                raise PushValidationError(
                    f"{field}: submitted URL does not match; "
                    f"excerpt={evidence.excerpt!r} url={evidence.url!r}"
                )
            if len(candidates) > 1 and not ALLOW_MULTIPLE_EVIDENCE_MATCHES:
                raise MultipleEvidenceMatches(evidence.excerpt)
            candidate = (
                EVIDENCE_RANDOM.choice(candidates) if len(candidates) > 1 else candidates[0]
            )
            arguments_json = candidate.arguments_json
            if not isinstance(arguments_json, str):
                arguments_json = json.dumps(
                    arguments_json,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            field_matches.append(
                EvidenceMatch(
                    field=field,
                    evidence_number=evidence_number,
                    excerpt=evidence.excerpt,
                    url=evidence.url,
                    ref_id=candidate.ref_id,
                    call_id=candidate.call_id,
                    cite_text=candidate.cite_text,
                    excerpt_position=candidate.excerpt_position - 1,
                    fco_timestamp=_render_fco_timestamp(candidate.fco_timestamp),
                    arguments_json=arguments_json,
                )
            )
        validated[field] = field_matches
    return validated


def source_rows() -> Iterator[dict[str, object]]:
    try:
        source = SOURCE_FILE.open(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot open {SOURCE_FILE}: {exc}") from exc

    with source:
        for line_number, line in enumerate(source, start=1):
            try:
                value: object = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"invalid JSON in {SOURCE_FILE} at line {line_number}") from exc

            if not isinstance(value, dict):
                raise RuntimeError(f"expected an object in {SOURCE_FILE} at line {line_number}")

            yield cast(dict[str, object], value)


def select_columns(row: Mapping[str, object]) -> dict[str, object]:
    missing = [column for column in DOCX_COLUMNS if column not in row]

    if missing:
        raise RuntimeError(f"target row is missing keys: {', '.join(missing)}")

    return {column: row[column] for column in DOCX_COLUMNS}


def json_line(row: Mapping[str, object]) -> str:
    return (
        json.dumps(
            row,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )


def pull_lines() -> Iterator[str]:
    for row in source_rows():
        if (row.get(DRAW_NUMBER_COLUMN) == TARGET_DRAW_NUMBER) and (
            row.get(FRAGMENT_TYPE_COLUMN) == DOCX_ROW_FRAGMENT_TYPE
        ):
            select_columns(row)
            first_name = row.get(KTP_FIRST_NAME_COL)
            last_name = row.get(KTP_LAST_NAME_COL)
            if not _valid_nonblank(first_name) or not _valid_nonblank(last_name):
                raise RuntimeError("target row is missing researcher identity")
            yield json_line({
                KTP_FIRST_NAME_COL: first_name,
                KTP_LAST_NAME_COL: last_name,
                **dict.fromkeys(AI_AUGMENT_COLUMNS),
            })
            return

        yield json_line(row)


def ground_truth() -> dict[str, object]:
    for row in source_rows():
        if (row.get(DRAW_NUMBER_COLUMN) == TARGET_DRAW_NUMBER) and (
            row.get(FRAGMENT_TYPE_COLUMN) == DOCX_ROW_FRAGMENT_TYPE
        ):
            return select_columns(row)

    raise PushValidationError("target draw ground truth was not found")


def selected_task_identity() -> tuple[str, str]:
    for row in source_rows():
        if (
            row.get(DRAW_NUMBER_COLUMN) == TARGET_DRAW_NUMBER
            and row.get(FRAGMENT_TYPE_COLUMN) == DOCX_ROW_FRAGMENT_TYPE
        ):
            first_name = row.get(KTP_FIRST_NAME_COL)
            last_name = row.get(KTP_LAST_NAME_COL)
            if not _valid_nonblank(first_name) or not _valid_nonblank(last_name):
                raise PushValidationError("selected task identity is incomplete")
            return cast(str, first_name), cast(str, last_name)
    raise PushValidationError("selected task identity was not found")


def _atomic_write_text(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def record_attempt(
    attempt_dir: Path,
    attempt_id: str,
    stage: str,
    result: str,
    *,
    rollout_archive: ArchivedFile | None = None,
    workbook_archive: ArchivedFile | None = None,
    report_archive: ArchivedFile | None = None,
    card_archive: ArchivedFile | None = None,
) -> None:
    artifacts = {}
    for name, artifact in (
        ("rollout", rollout_archive),
        ("workbook", workbook_archive),
        ("appendwatch_report", report_archive),
        ("card_zip", card_archive),
    ):
        if artifact is not None:
            artifacts[name] = {
                "filename": artifact.path.name,
                "size": artifact.size,
                "sha256": artifact.sha256,
            }
            if name == "rollout":
                artifacts[name]["line_count"] = artifact.line_count
    value = {
        "attempt_id": attempt_id,
        "stage": stage,
        "result": result,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": artifacts,
    }
    _atomic_write_text(
        attempt_dir / "attempt.json",
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def open_source_database(
    runtime: RuntimeConfiguration,
) -> duckdb.DuckDBPyConnection:
    try:
        return duckdb.connect(str(runtime.pipeline.db_file), read_only=True)
    except duckdb.Error as exc:
        raise PushValidationError("configured source DuckDB could not be opened read-only") from exc


def open_detour_database(
    runtime: RuntimeConfiguration,
) -> duckdb.DuckDBPyConnection:
    try:
        runtime.detour_db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(runtime.detour_db_path))
    except (OSError, duckdb.Error) as exc:
        raise PushValidationError("detour DuckDB could not be opened") from exc


def _source_table_rows(
    source_conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    source_key: str,
) -> tuple[dict[str, object], ...]:
    try:
        rows = source_conn.execute(
            f"SELECT {duckdb_quote_identifier(KTP_INNERDICT_JSONLINES_COL)} "
            f"FROM {table_name} "
            f"WHERE {duckdb_quote_identifier(KTP_NAMEKEY_COL)} = ?",
            [source_key],
        ).fetchall()
    except duckdb.Error as exc:
        raise PushValidationError(f"configured source DuckDB lacks {table_name}") from exc
    if len(rows) > 1:
        raise PushValidationError(f"{table_name} contains duplicate rows for sanctioned source key")
    if not rows:
        return ()
    try:
        return _innerdict_json_rows(
            rows[0][0],
            table_name=table_name,
            source_key=source_key,
        )
    except PushConfigurationError as exc:
        raise PushValidationError(str(exc)) from exc


def load_source_researcher(
    source_conn: duckdb.DuckDBPyConnection,
    runtime: RuntimeConfiguration,
    *,
    source_key: str,
) -> SourceResearcher:
    cohorts = runtime.eligible_cohorts
    if cohorts is None or source_key not in cohorts:
        raise PushValidationError("sanctioned source key is not eligible for this detour")
    try:
        name_key = NameKey.from_json_key(source_key)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise PushValidationError("sanctioned source key is malformed") from exc
    if name_key.to_json_key() != source_key:
        raise PushValidationError("sanctioned source key is not canonical")

    xlsx_rows = _source_table_rows(
        source_conn,
        table_name=XLSX_INNERDICT_TABLE,
        source_key=source_key,
    )
    docx_rows = _source_table_rows(
        source_conn,
        table_name=DOCX_INNERDICT_TABLE,
        source_key=source_key,
    )
    ssn_rows = _source_table_rows(
        source_conn,
        table_name=PARQUET_INNERDICT_TABLE,
        source_key=source_key,
    )
    if not xlsx_rows:
        raise PushValidationError("sanctioned source key has no xlsx innerdict context")
    draw_numbers = tuple(sorted({
        str(row[DRAW_LABEL]).strip()
        for row in (*xlsx_rows, *docx_rows, *ssn_rows)
        if row.get(DRAW_LABEL) is not None and str(row[DRAW_LABEL]).strip()
    }, key=_draw_sort_key))
    if not draw_numbers:
        raise PushValidationError("sanctioned source key has no innerdict-owned draw")
    return SourceResearcher(
        source_key=source_key,
        first_name=name_key.first_name,
        last_name=name_key.last_name,
        draw_numbers=draw_numbers,
        xlsx_rows=xlsx_rows,
        docx_rows=docx_rows,
        ssn_rows=ssn_rows,
        cohort=cohorts[source_key],
    )


def researcher_context(researcher: SourceResearcher) -> ResearcherContext:
    return ResearcherContext(
        source_key=researcher.source_key,
        draw_number=DRAW_VALUE_SEPARATOR.join(researcher.draw_numbers),
        first_name=researcher.first_name,
        last_name=researcher.last_name,
        cohort=researcher.cohort,
        draw_numbers=researcher.draw_numbers,
    )


def sanctioned_pull_lines(researcher: SourceResearcher) -> Iterator[str]:
    for row in (*researcher.xlsx_rows, *researcher.ssn_rows):
        yield json_line(row)
    yield json_line({
        KTP_FIRST_NAME_COL: researcher.first_name,
        KTP_LAST_NAME_COL: researcher.last_name,
        **dict.fromkeys(AI_AUGMENT_COLUMNS),
    })


def ground_truth_for_researcher(researcher: SourceResearcher) -> dict[str, object] | None:
    if researcher.cohort == NO_GROUND_TRUTH_COHORT:
        return None
    required_columns = DOCX_COLUMNS[:-1]
    complete_rows = [
        row
        for row in researcher.docx_rows
        if all(column in row and bool(str(row[column]).strip()) for column in required_columns)
    ]
    if not complete_rows:
        raise PushValidationError("ground-truth researcher has no complete docx innerdict")
    return select_columns(complete_rows[0])


def resolve_researcher(
    source_conn: duckdb.DuckDBPyConnection,
    *,
    first_name: str,
    last_name: str,
) -> ResearcherContext:
    rows = source_conn.execute(
        f"""
        SELECT DISTINCT
            names.{duckdb_quote_identifier(KTP_NAMEKEY_COL)},
            samples.{duckdb_quote_identifier(DRAW_LABEL)},
            names.{duckdb_quote_identifier(KTP_FIRST_NAME_COL)},
            names.{duckdb_quote_identifier(KTP_LAST_NAME_COL)}
        FROM {OUTERDICT_NAME_VIEW} names
        JOIN {SAMPLES_WITH_NAMES_VIEW} samples
          ON names.{duckdb_quote_identifier(KTP_FIRST_NAME_COL)} =
             samples.{duckdb_quote_identifier(KTP_FIRST_NAME_COL)}
         AND names.{duckdb_quote_identifier(KTP_LAST_NAME_COL)} =
             samples.{duckdb_quote_identifier(KTP_LAST_NAME_COL)}
        WHERE names.{duckdb_quote_identifier(KTP_FIRST_NAME_COL)} = ?
          AND names.{duckdb_quote_identifier(KTP_LAST_NAME_COL)} = ?
          AND CAST(samples.{duckdb_quote_identifier(DRAW_LABEL)} AS VARCHAR) = ?
        """,
        [first_name, last_name, TARGET_DRAW_NUMBER],
    ).fetchall()
    if len(rows) != 1:
        raise PushValidationError("selected researcher did not resolve uniquely")
    return ResearcherContext(
        source_key=cast(str, rows[0][0]),
        draw_number=str(rows[0][1]),
        first_name=cast(str, rows[0][2]),
        last_name=cast(str, rows[0][3]),
    )


def render_codex_values(
    submission: Submission,
    evidence: ValidatedEvidence,
    *,
    attempt_timestamp: datetime,
    argument_ref_urls: Mapping[str, str],
) -> dict[str, str | None]:
    rendered: dict[str, str | None] = {}
    ordered_matches: list[EvidenceMatch] = []
    for column, field_submission in submission.evidence_items():
        matches = evidence[column]
        ordered_matches.extend(matches)
        rendered[column] = codex_parse.render_ai_value(
            field_submission.value,
            tuple(match.evidence_number for match in matches),
        )
    rendered[KTP_AI_AUGMENT_FOOTNOTES_COL] = "\n".join(
        codex_parse.render_footnote(
            number=match.evidence_number,
            cite_text=match.cite_text,
            citation_marker=(f"{CODEX_CITE_MARKER_PREFIX}{match.ref_id}{CODEX_CITE_MARKER_SUFFIX}"),
            marker_prefix=CODEX_CITE_MARKER_PREFIX,
            marker_suffix=CODEX_CITE_MARKER_SUFFIX,
            excerpt=match.excerpt,
            excerpt_position=match.excerpt_position,
            context_characters=FOOTNOTE_CONTEXT_CHARACTERS,
            fco_timestamp=match.fco_timestamp,
            url=match.url,
        )
        for match in ordered_matches
    )
    rendered[KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL] = "\n".join(
        codex_parse.render_footnote_argument(
            match.evidence_number,
            match.arguments_json,
            argument_ref_urls,
            ref_id_pattern=CODEX_REF_ID_PATTERN,
        )
        for match in ordered_matches
    )
    rendered[KTP_AI_AUGMENT_COMMENTS_COL] = (
        None
        if submission.comments is None
        else codex_parse.render_comment(
            submission.comments.value,
            _render_fco_timestamp(attempt_timestamp),
        )
    )
    return rendered


def _create_codex_output_schema(conn: duckdb.DuckDBPyConnection) -> None:
    definitions = ", ".join(
        f"{duckdb_quote_identifier(column)} {data_type}"
        for column, data_type in CODEX_OUTPUT_SCHEMA
    )
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {CODEX_OUTPUT_ROWS_TABLE} ("
        f"{definitions}, UNIQUE ("
        f"{duckdb_quote_identifier(KTP_FILENAME_COL)}, "
        f"{duckdb_quote_identifier(KTP_FRAGMENT_COL)}))"
    )


def append_codex_output(
    conn: duckdb.DuckDBPyConnection,
    row: Mapping[str, object],
) -> None:
    _create_codex_output_schema(conn)
    columns = tuple(column for column, _data_type in CODEX_OUTPUT_SCHEMA)
    projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _column in columns)
    try:
        conn.execute(
            f"INSERT INTO {CODEX_OUTPUT_ROWS_TABLE} ({projection}) VALUES ({placeholders})",
            [row[column] for column in columns],
        )
    except duckdb.ConstraintException as exc:
        raise PushValidationError(
            "attempt ID or rollout filename/line-count fragment is already accepted"
        ) from exc
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {CODEX_OUTPUT_VIEW} AS
        SELECT {projection}
        FROM {CODEX_OUTPUT_ROWS_TABLE}
        ORDER BY
            {duckdb_quote_identifier(KTP_FILENAME_COL)},
            {duckdb_quote_identifier(KTP_FRAGMENT_COL)},
            {duckdb_quote_identifier(KTP_AI_AUGMENT_ATTEMPT_ID_COL)}
        """
    )
    materialize_innerdicts_from_rows_table(
        conn,
        source_relation=CODEX_OUTPUT_VIEW,
        table_name=CODEX_INNERDICT_TABLE,
    )


def selected_card_outer_dict(
    source_conn: duckdb.DuckDBPyConnection,
    detour_conn: duckdb.DuckDBPyConnection,
    researcher: ResearcherContext,
) -> OuterDict:
    name_key = NameKey(**{
        KTP_FIRST_NAME_COL: researcher.first_name,
        KTP_LAST_NAME_COL: researcher.last_name,
    })
    outer_dict = OuterDict.from_name_keys([name_key])
    append_innerdicts_from_jsonlines_table(
        source_conn,
        table_name=XLSX_INNERDICT_TABLE,
        outer_dict=outer_dict,
        procedure=XlsxMatchProcedure(),
    )
    append_innerdicts_from_jsonlines_table(
        detour_conn,
        table_name=CODEX_INNERDICT_TABLE,
        outer_dict=outer_dict,
        procedure=CodexMatchProcedure(),
        required_columns={KTP_FILENAME_COL, KTP_FRAGMENT_COL},
    )
    append_innerdicts_from_jsonlines_table(
        source_conn,
        table_name=DOCX_INNERDICT_TABLE,
        outer_dict=outer_dict,
        procedure=DocxMatchProcedure(),
    )
    append_innerdicts_from_jsonlines_table(
        source_conn,
        table_name=PARQUET_INNERDICT_TABLE,
        outer_dict=outer_dict,
        procedure=ParquetMatchProcedure(),
    )
    return OuterDict(
        data={name_key.to_json_key(): list(outer_dict.get_inner_by_key(name_key.to_json_key()))}
    )


def write_accepted_submission(
    detour_conn: duckdb.DuckDBPyConnection,
    source_conn: duckdb.DuckDBPyConnection,
    runtime: RuntimeConfiguration,
    *,
    submission: Submission,
    evidence: ValidatedEvidence,
    researcher: ResearcherContext,
    rollout_index: RolloutIndex,
    rollout_archive: ArchivedFile,
    attempt_dir: Path,
    attempt_id: str,
    attempt_timestamp: datetime,
    source_researcher: SourceResearcher | None = None,
) -> tuple[tuple[str, ...], ArchivedFile]:
    normalized_submission = submission.normalized_values()
    response_path = attempt_dir / "response.jsonl"
    zip_name = f"{CARD_ZIP_PREFIX}_{attempt_id}.zip"
    zip_path = runtime.pipeline.output_dir / zip_name
    if zip_path.exists():
        raise PushValidationError("attempt card ZIP already exists")

    rendered = render_codex_values(
        submission,
        evidence,
        attempt_timestamp=attempt_timestamp,
        argument_ref_urls=_rollout_ref_urls(
            detour_conn,
            rollout_filename=rollout_index.session.rollout_filename,
        ),
    )
    output_row: dict[str, object] = {
        KTP_NAMEKEY_COL: researcher.source_key,
        KTP_FILENAME_COL: rollout_index.session.rollout_filename,
        KTP_FRAGMENT_COL: rollout_archive.line_count,
        KTP_FRAGMENT_TYPE_COL: ROLLOUT_LINE_FRAGMENT_TYPE,
        DRAW_LABEL: researcher.draw_number,
        KTP_FIRST_NAME_COL: researcher.first_name,
        KTP_LAST_NAME_COL: researcher.last_name,
        KTP_AI_AUGMENT_ATTEMPT_ID_COL: attempt_id,
        KTP_AI_AUGMENT_SESSION_METADATA_COL: rollout_index.session.compact_json,
        **rendered,
    }

    detour_conn.execute("BEGIN TRANSACTION")
    try:
        append_codex_output(detour_conn, output_row)
        submitted_line = json_line(normalized_submission)
        truth = (
            ground_truth()
            if source_researcher is None
            else ground_truth_for_researcher(source_researcher)
        )
        response_lines = (
            (submitted_line,)
            if truth is None
            else (submitted_line, json_line(truth))
        )
        outer_dict = selected_card_outer_dict(source_conn, detour_conn, researcher)
        intro_date = attempt_timestamp.astimezone(ZoneInfo(runtime.pipeline.timezone)).strftime(
            "%B %d, %Y"
        )
        cards = build_cards(
            outer_dict,
            total_draws=runtime.pipeline.total_draws,
            intro=CARD_INTRODUCTION.format(intro_date),
            excluded_cols=CARD_EXCLUDED_COLUMNS,
        )
        if len(cards) != 1:
            raise PushValidationError("selected researcher did not produce exactly one card")
        write_cards_zip(
            cards,
            runtime.pipeline.output_dir,
            zip_name,
            output_format=runtime.pipeline.output_format,
            reference_docx=runtime.pipeline.pandoc_reference_docx,
        )
        _atomic_write_text(response_path, "".join(response_lines))
        detour_conn.execute("COMMIT")
    except Exception:
        detour_conn.execute("ROLLBACK")
        response_path.unlink(missing_ok=True)
        zip_path.unlink(missing_ok=True)
        raise
    return response_lines, _archived_file(zip_path)


def validate_transport(request: Request) -> None:
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/json":
        raise PushValidationError("request Content-Type must be application/json")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise PushValidationError("request Content-Length is invalid") from exc
        if declared_length < 0 or declared_length > MAX_PUSH_BODY_BYTES:
            raise PushValidationError("request body exceeds the configured size limit")


async def bounded_request_body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_PUSH_BODY_BYTES:
            raise PushValidationError("request body exceeds the configured size limit")
    return bytes(body)


def pydantic_failure(exc: ValidationError) -> tuple[str | None, str, object]:
    errors = exc.errors(
        include_url=False,
        include_context=False,
        include_input=True,
    )
    if not errors:
        return None, "submission failed Pydantic validation", PYDANTIC_MISSING_INPUT
    error = errors[0]
    reason = str(error.get("msg", "submission failed Pydantic validation"))
    field = next(
        (
            item
            for item in error.get("loc", ())
            if isinstance(item, str) and item in AI_AUGMENT_COLUMNS
        ),
        None,
    )
    if field is None:
        field = next(
            (column for column in AI_AUGMENT_COLUMNS if column in reason),
            None,
        )
    failed_input = (
        PYDANTIC_MISSING_INPUT
        if error.get("type") == "missing"
        else error.get("input", PYDANTIC_MISSING_INPUT)
    )
    return field, reason, failed_input


def safely_record_attempt(
    attempt_dir: Path | None,
    attempt_id: str,
    stage: str,
    result: str,
    *,
    rollout_archive: ArchivedFile | None,
    workbook_archive: ArchivedFile | None = None,
    report_archive: ArchivedFile | None,
    card_archive: ArchivedFile | None,
) -> None:
    if attempt_dir is None:
        return
    try:
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            result,
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
        )
    except OSError:
        logger.exception(
            "push attempt=%s could not record stage=%s result=%s",
            attempt_id,
            stage,
            result,
        )


# curl -N http://127.0.0.1:8000/pull
@app.get(**PULL_ROUTE)
def pull() -> StreamingResponse:
    try:
        runtime = runtime_configuration()
        snapshot = sanctioned_snapshot()
        push_configuration(snapshot.rollout_guest_path)
        if snapshot.control_base_url is None:
            lines = tuple(pull_lines())
        else:
            with WORKBOOK_STATE_LOCK:
                if not WORKBOOK_INITIALIZED:
                    raise PushConfigurationError(
                        "guest workbook was not initialized at backend startup"
                    )
            assert snapshot.source_key is not None
            source_conn = open_source_database(runtime)
            try:
                researcher = load_source_researcher(
                    source_conn,
                    runtime,
                    source_key=snapshot.source_key,
                )
                lines = tuple(sanctioned_pull_lines(researcher))
            finally:
                source_conn.close()
        return StreamingResponse(iter(lines), media_type=MEDIA_TYPE)
    except (PushConfigurationError, PushValidationError, OSError, duckdb.Error) as exc:
        logger.error("pull failed configuration/sanction validation: %s", exc)
        raise HTTPException(status_code=503, detail=CONFIGURATION_ERROR_DETAIL) from None


# curl -N \
#  -H 'Content-Type: application/json' \
#  --data @submission.json \
#  http://127.0.0.1:8000/push
@app.post(**PUSH_ROUTE)
async def push(request: Request) -> StreamingResponse:
    attempt_timestamp = datetime.now(timezone.utc)
    attempt_id = new_attempt_id(attempt_timestamp)
    attempt_dir: Path | None = None
    rollout_archive: ArchivedFile | None = None
    workbook_archive: ArchivedFile | None = None
    report_archive: ArchivedFile | None = None
    card_archive: ArchivedFile | None = None
    snapshot: SanctionSnapshot | None = None
    stage = "transport"

    try:
        validate_transport(request)
        stage = "configuration"
        runtime = runtime_configuration()
        snapshot = sanctioned_snapshot()
        configuration = push_configuration(snapshot.rollout_guest_path)
        if snapshot.control_base_url is not None:
            with WORKBOOK_STATE_LOCK:
                if not WORKBOOK_INITIALIZED:
                    raise PushConfigurationError(
                        "guest workbook was not initialized at backend startup"
                    )
        attempt_dir = create_attempt(attempt_id)
        record_attempt(attempt_dir, attempt_id, stage, "pending")

        stage = "rollout_copy"
        record_attempt(attempt_dir, attempt_id, stage, "pending")
        rollout_archive = copy_rollout(configuration, attempt_dir, attempt_id)

        if snapshot.control_base_url is not None:
            stage = "workbook_copy"
            record_attempt(
                attempt_dir,
                attempt_id,
                stage,
                "pending",
                rollout_archive=rollout_archive,
            )
            workbook_archive = copy_guest_workbook(configuration, attempt_dir, attempt_id)

        stage = "appendwatch_report_copy"
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "pending",
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
        )
        report_archive = copy_appendwatch_report(configuration, attempt_dir, attempt_id)

        stage = "appendwatch_report_validation"
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "pending",
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
        )
        parse_appendwatch_report(
            report_archive.path,
            configuration.rollout_relative_path,
        )

        stage = "rollout_index"
        records = parse_rollout(rollout_archive.path)
        rollout_index = build_rollout_index(
            records,
            timezone_name=runtime.pipeline.timezone,
            configured_rollout_basename=configuration.rollout_relative_path.name,
        )
        if (
            snapshot.session_id is not None
            and rollout_index.session.session_id != snapshot.session_id
        ):
            raise PushValidationError("sanctioned session does not match archived rollout")
        with DETOUR_DB_LOCK:
            detour_conn = open_detour_database(runtime)
            source_conn: duckdb.DuckDBPyConnection | None = None
            try:
                persist_rollout_index(detour_conn, rollout_index)

                stage = "pydantic_validation"
                body = await bounded_request_body(request)
                submission = Submission.model_validate_json(body)

                stage = "duckdb_evidence_validation"
                _seed_evidence_random(runtime.pipeline.sample_seed)
                validated_evidence = validate_submission_evidence(
                    detour_conn,
                    submission,
                    rollout_filename=rollout_index.session.rollout_filename,
                )

                stage = "researcher_resolution"
                source_conn = open_source_database(runtime)
                source_researcher: SourceResearcher | None = None
                if snapshot.source_key is None:
                    first_name, last_name = selected_task_identity()
                    researcher = resolve_researcher(
                        source_conn,
                        first_name=first_name,
                        last_name=last_name,
                    )
                else:
                    source_researcher = load_source_researcher(
                        source_conn,
                        runtime,
                        source_key=snapshot.source_key,
                    )
                    researcher = researcher_context(source_researcher)

                stage = "innerdict_and_card"
                lines, card_archive = write_accepted_submission(
                    detour_conn,
                    source_conn,
                    runtime,
                    submission=submission,
                    evidence=validated_evidence,
                    researcher=researcher,
                    rollout_index=rollout_index,
                    rollout_archive=rollout_archive,
                    attempt_dir=attempt_dir,
                    attempt_id=attempt_id,
                    attempt_timestamp=attempt_timestamp,
                    source_researcher=source_researcher,
                )
            finally:
                if source_conn is not None:
                    source_conn.close()
                detour_conn.close()
        record_attempt(
            attempt_dir,
            attempt_id,
            "accepted",
            "accepted",
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
        )
        assert snapshot is not None
        consume_sanction(snapshot)
        try:
            acknowledge_sanction(snapshot, attempt_id)
        except PushConfigurationError as exc:
            logger.error(
                "push attempt=%s accepted but Control Centre acknowledgement failed: %s",
                attempt_id,
                exc,
            )
        logger.info("push attempt=%s accepted", attempt_id)
        return StreamingResponse(iter(lines), media_type=MEDIA_TYPE)
    except PushConfigurationError as exc:
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "configuration_error",
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
        )
        logger.error(
            "push attempt=%s failed stage=%s: %s",
            attempt_id,
            stage,
            exc,
        )
        raise HTTPException(status_code=503, detail=CONFIGURATION_ERROR_DETAIL) from None
    except MultipleEvidenceMatches as exc:
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "rejected",
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
        )
        logger.warning(
            "push attempt=%s failed stage=%s: excerpt matched multiple rows excerpt=%r",
            attempt_id,
            stage,
            exc.excerpt,
        )
        raise HTTPException(
            status_code=422,
            detail=MULTIPLE_MATCH_DETAIL.format(excerpt=exc.excerpt),
        ) from None
    except PushValidationError as exc:
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "rejected",
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
        )
        logger.warning(
            "push attempt=%s failed stage=%s: %s",
            attempt_id,
            stage,
            exc,
        )
        raise HTTPException(status_code=422, detail=VALIDATION_ERROR_DETAIL) from None
    except ValidationError as exc:
        field, reason, failed_input = pydantic_failure(exc)
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "rejected",
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
        )
        logger.warning(
            "push attempt=%s failed stage=%s field=%s value=%r: %s",
            attempt_id,
            stage,
            field or "unknown",
            failed_input,
            reason,
        )
        raise HTTPException(status_code=422, detail=VALIDATION_ERROR_DETAIL) from None
    except (OSError, ValueError, duckdb.Error, subprocess.SubprocessError) as exc:
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "rejected",
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
        )
        logger.warning(
            "push attempt=%s failed stage=%s: %s",
            attempt_id,
            stage,
            exc,
        )
        raise HTTPException(status_code=422, detail=VALIDATION_ERROR_DETAIL) from None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the AI augmentation detour API.")
    parser.add_argument("--config", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_runtime(args.config)
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)


if __name__ == "__main__":
    main()
