from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import threading
from collections.abc import AsyncGenerator, Iterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from random import Random
from typing import Annotated, Any, Literal, Self, cast
from uuid import uuid4
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
from src.helpers.data_models import FragmentType, NameKey, OuterDict
from src.helpers.duckdb_utils import (
    append_innerdicts_from_jsonlines_table,
    duckdb_quote_identifier,
    materialize_innerdicts_from_rows_table,
)
from src.helpers.procedures import DocxMatchProcedure, ParquetMatchProcedure, XlsxMatchProcedure
from src.helpers.schema import (
    DOCX_INNERDICT_TABLE,
    OUTERDICT_NAME_VIEW,
    PARQUET_INNERDICT_TABLE,
    SAMPLES_WITH_NAMES_VIEW,
    XLSX_INNERDICT_TABLE,
)
from src.helpers.vars import (
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
    KTP_LAST_NAME_COL,
    KTP_SOURCE_KEY_COL,
)

from . import codex_parse

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
load_dotenv(REPOSITORY_ROOT / ".env")

logger = logging.getLogger(__name__)

SUBMISSIONS_DIR = Path(__file__).resolve().parents[2] / "data" / "submissions"
ATTEMPTS_DIR = SUBMISSIONS_DIR / "attempts"
SOURCE_FILE = Path("tmp/sheikh.jsonl")

ROLLOUT_ENV_NAME = "FASTAPI_DETOUR_ROLLOUT_JSONL"
ROLLOUT_JSONL = os.environ.get(ROLLOUT_ENV_NAME, "")
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
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8612

DETOUR_ID = "ai-augment"
DETOUR_DB_LOCK = threading.Lock()
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

KTP_AI_AUGMENT_ATTEMPT_ID_COL = "ktp.ai_augment_attempt_id"
KTP_AI_AUGMENT_SESSION_METADATA_COL = "ktp.ai_augment_session_metadata"
KTP_AI_AUGMENT_FOOTNOTES_COL = "ktp.ai_augment_footnotes"
KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL = "ktp.ai_augment_footnote_arguments"
KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL = "ktp.ai_augment_researcher_author"
KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL = "ktp.ai_augment_place_of_residence"
KTP_AI_AUGMENT_GENDER_COL = "ktp.ai_augment_gender"
KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL = (
    "ktp.ai_augment_age_first_publication_according_to_openalex_profile"
)
KTP_AI_AUGMENT_EDUCATION_COL = "ktp.ai_augment_education"
KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL = "ktp.ai_augment_academic_position_s_"
KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL = "ktp.ai_augment_social_capital"
KTP_AI_AUGMENT_LINKS_COL = "ktp.ai_augment_links_"
KTP_AI_AUGMENT_COMMENTS_COL = "ktp.ai_augment_comments"

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
    (KTP_SOURCE_KEY_COL, "VARCHAR NOT NULL"),
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
    KTP_SOURCE_KEY_COL,
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
        push_configuration()
    except PushConfigurationError as exc:
        logger.error("push is disabled: %s", exc)
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


class CodexMatchProcedure:
    dataset_id_field = KTP_SOURCE_KEY_COL


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

    detour_db_path = _detour_db_path(pipeline.db_file)
    if detour_db_path == pipeline.db_file:
        raise PushConfigurationError("detour DuckDB path must differ from source DuckDB")
    RUNTIME_CONFIGURATION = RuntimeConfiguration(
        pipeline=pipeline,
        detour_db_path=detour_db_path,
    )
    return RUNTIME_CONFIGURATION


def runtime_configuration() -> RuntimeConfiguration:
    if RUNTIME_CONFIGURATION is None:
        raise PushConfigurationError("API was not started with required --config config.json")
    return RUNTIME_CONFIGURATION


def push_configuration() -> PushConfiguration:
    raw_rollout = ROLLOUT_JSONL
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
        "ClearAllForwardings=yes",
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
        for row in rollout_index.fc_rows:
            _insert_or_validate(
                conn,
                table_name=CODEX_FC_TABLE,
                key_column=CODEX_FC_ID_COL,
                key_value=row.fc_id,
                columns=(
                    CODEX_FC_TIMESTAMP_COL,
                    CODEX_FC_ID_COL,
                    CODEX_FC_NAME_COL,
                    CODEX_FC_NAMESPACE_COL,
                    CODEX_FC_ARGUMENTS_COL,
                ),
                values=(
                    _datetime_value(row.timestamp),
                    row.fc_id,
                    row.name,
                    row.namespace,
                    row.arguments_json,
                ),
            )
        for row in rollout_index.fco_rows:
            _insert_or_validate(
                conn,
                table_name=CODEX_FCO_TABLE,
                key_column=CODEX_FCO_ID_COL,
                key_value=row.fco_id,
                columns=(CODEX_FCO_TIMESTAMP_COL, CODEX_FCO_ID_COL),
                values=(_datetime_value(row.timestamp), row.fco_id),
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
        for row in rollout_index.turn_ref_rows:
            key_value = f"{row.call_id}\0{row.ref_id}"
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
                [row.call_id, row.ref_id],
            ).fetchall()
            values = (
                row.ref_id,
                row.call_id,
                row.domain,
                row.snippet,
                row.thumbnail_url,
                row.title,
                row.url,
                row.cite_text,
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
            total, distinct = conn.execute(
                f"SELECT COUNT(*), COUNT(DISTINCT {distinct_expression}) FROM {table_name}"
            ).fetchone()
            if total != distinct:
                raise PushValidationError(
                    f"normalized provenance uniqueness failed for {table_name}"
                )

        missing_fc_links, missing_fco_links, missing_call_links = conn.execute(
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
    report_archive: ArchivedFile | None = None,
    card_archive: ArchivedFile | None = None,
) -> None:
    artifacts = {}
    for name, artifact in (
        ("rollout", rollout_archive),
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


def resolve_researcher(
    source_conn: duckdb.DuckDBPyConnection,
    *,
    first_name: str,
    last_name: str,
) -> ResearcherContext:
    rows = source_conn.execute(
        f"""
        SELECT DISTINCT
            names.{duckdb_quote_identifier(KTP_SOURCE_KEY_COL)},
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
) -> tuple[tuple[str, str], ArchivedFile]:
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
        KTP_SOURCE_KEY_COL: researcher.source_key,
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
        truth = ground_truth()
        submitted_line = json_line(normalized_submission)
        truth_line = json_line(truth)
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
        _atomic_write_text(response_path, submitted_line + truth_line)
        detour_conn.execute("COMMIT")
    except Exception:
        detour_conn.execute("ROLLBACK")
        response_path.unlink(missing_ok=True)
        zip_path.unlink(missing_ok=True)
        raise
    return (submitted_line, truth_line), _archived_file(zip_path)


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
    return StreamingResponse(
        pull_lines(),
        media_type=MEDIA_TYPE,
    )


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
    report_archive: ArchivedFile | None = None
    card_archive: ArchivedFile | None = None
    stage = "transport"

    try:
        validate_transport(request)
        stage = "configuration"
        runtime = runtime_configuration()
        configuration = push_configuration()
        attempt_dir = create_attempt(attempt_id)
        record_attempt(attempt_dir, attempt_id, stage, "pending")

        stage = "rollout_copy"
        record_attempt(attempt_dir, attempt_id, stage, "pending")
        rollout_archive = copy_rollout(configuration, attempt_dir, attempt_id)

        stage = "appendwatch_report_copy"
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "pending",
            rollout_archive=rollout_archive,
        )
        report_archive = copy_appendwatch_report(configuration, attempt_dir, attempt_id)

        stage = "appendwatch_report_validation"
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "pending",
            rollout_archive=rollout_archive,
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
                first_name, last_name = selected_task_identity()
                source_conn = open_source_database(runtime)
                researcher = resolve_researcher(
                    source_conn,
                    first_name=first_name,
                    last_name=last_name,
                )

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
            report_archive=report_archive,
            card_archive=card_archive,
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
