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
import time
from collections import Counter
from collections.abc import AsyncGenerator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path, PurePosixPath
from random import Random
from typing import Any, Callable, Literal, Self, TypeAlias, cast, get_args
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import duckdb
import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
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
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
    append_http_request_log_record,
)
from src.helpers.duckdb_extensions import load_duckdb_extension
from src.helpers.duckdb_utils import (
    append_innerdicts_from_jsonlines_table,
    duckdb_quote_identifier,
    materialize_innerdicts_from_rows_table,
)
from src.helpers.name_matching import normalized_tokens_sql
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
    KTP_DOCX_OPTIONAL_EMPTY_COLS,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
    KTP_INNERDICT_JSONLINES_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
    KTP_PARTITION_COL,
    KTP_PARTITION_DOCX_VALUE,
    KTP_PARTITION_FLAG_SSN_COUNT_COL,
    KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
    KTP_PARTITION_SSN_VALUE,
    KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS,
)

from .helpers import codex_parse
from .helpers.data_models.pydantic_to_paste import (
    MAX_PUSH_BODY_BYTES,
    EvidenceSubmission,
    EvidenceWithdrawal,
    FieldSubmission,
    NotAvailableOrApplicable,
    NotReported,
    PlaceOfResidenceStandardized,
    RaceEthnicityLanguageCultureStandardized,
    ResearcherAuthorStandardized,
    StandardizedFieldSubmission,
    StandardizedSubmission,
    StandardizedValue,
    WebSearchExcerpt,
)
from .helpers.data_models.submission import Submission
from .helpers.data_models.submission_fixture import (
    L_FEI_FEI_INITIAL_FIXTURE,
    L_FEI_FEI_RETRY_FIXTURE,
)
from .helpers.locale import Locale
from .helpers.vars import (
    AI_AUGMENT_COLUMNS,
    AI_AUGMENT_EVIDENCE_COLUMNS,
    AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS,
    AI_AUGMENT_STANDARDIZED_COLUMNS,
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    KTP_AI_AUGMENT_ATTEMPT_ID_COL,
    KTP_AI_AUGMENT_COMMENTS_COL,
    KTP_AI_AUGMENT_EDUCATION_COL,
    KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL,
    KTP_AI_AUGMENT_FOOTNOTES_COL,
    KTP_AI_AUGMENT_GENDER_COL,
    KTP_AI_AUGMENT_LINKS_COL,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
    KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
)

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
APPENDWATCH_REPORT_ENV_NAME = "FASTAPI_DETOUR_APPENDWATCH_REPORT"
AIVM_INSTANCE_ENV_NAME = "FASTAPI_DETOUR_AIVM_INSTANCE"
AIVM_USER_ENV_NAME = "FASTAPI_DETOUR_AIVM_USER"
AIVM_SSH_PORT_ENV_NAME = "FASTAPI_DETOUR_AIVM_SSH_PORT"
AIVM_IDENTITY_FILE_ENV_NAME = "FASTAPI_DETOUR_AIVM_IDENTITY_FILE"
AIVM_KNOWN_HOSTS_FILE_ENV_NAME = "FASTAPI_DETOUR_AIVM_KNOWN_HOSTS_FILE"
LIMA_SSH_CONFIG_ENV_NAME = "FASTAPI_DETOUR_LIMA_SSH_CONFIG"
CONTROL_CURRENT_PATH = "/_control/current"
CONTROL_ACCEPTED_PATH_TEMPLATE = "/_control/runs/{run_id}/accepted"
CONTROL_HTTP_TIMEOUT_SECONDS = 10
CONTROL_SCHEME = "http"
CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 8611
CONTROL_ROOT_PATHS = frozenset({"", "/"})
CODEX_SESSIONS_ROOT = PurePosixPath("/home/ai/.codex/sessions")
APPENDWATCH_REPORT = Path(
    os.environ.get(
        APPENDWATCH_REPORT_ENV_NAME,
        "/Volumes/home/aicode/aivm/home/ai/.aivm-control/appendwatch/appendwatch-tree.txt",
    )
).expanduser()

AIVM_INSTANCE = os.environ.get(AIVM_INSTANCE_ENV_NAME, "aivm")
AIVM_USER = os.environ.get(AIVM_USER_ENV_NAME, "ai")
AIVM_SSH_PORT = os.environ.get(AIVM_SSH_PORT_ENV_NAME, "22022")
AIVM_KEY_DIR = Path.home() / ".local" / "share" / "aivm" / ".ssh"
AIVM_IDENTITY_FILE = Path(
    os.environ.get(AIVM_IDENTITY_FILE_ENV_NAME, AIVM_KEY_DIR / "id_ed25519")
).expanduser()
AIVM_KNOWN_HOSTS_FILE = Path(
    os.environ.get(AIVM_KNOWN_HOSTS_FILE_ENV_NAME, AIVM_KEY_DIR / "known_hosts")
).expanduser()
LIMA_SSH_CONFIG_PATH = Path(
    os.environ.get(
        LIMA_SSH_CONFIG_ENV_NAME,
        Path.home() / ".lima" / AIVM_INSTANCE / "ssh.config",
    )
).expanduser()
AIVM_SSH_TARGET = f"{AIVM_INSTANCE}-{AIVM_USER}"
AIVM_HOST_KEY_ALIAS = f"lima-{AIVM_INSTANCE}-{AIVM_USER}"
CURRENT_DIRECTORY = PurePosixPath(".")
FORBIDDEN_NORMALIZED_PATH_PARTS = frozenset({"", ".", ".."})

COMPACT_JSON_SEPARATORS = (",", ":")
ARCHIVE_HASH_CHUNK_BYTES = 1024 * 1024
SCP_TIMEOUT_SECONDS = 60
SSH_TIMEOUT_SECONDS = 60
MIN_TCP_PORT = 1
MAX_TCP_PORT = 65_535
CONTROL_CHARACTER_CEILING = 32
DELETE_CHARACTER_CODEPOINT = 127
APPENDWATCH_STATUS_WIDTH = 11
TREE_INDENT_WIDTH = len("│   ")
APPENDWATCH_OK_STATUS = "OK"
APPENDWATCH_COMPROMISED_STATUS = "COMPROMISED"
APPENDWATCH_STATUS_SEPARATOR = " "
APPENDWATCH_OK_BODY_PREFIX = f"{APPENDWATCH_OK_STATUS}{APPENDWATCH_STATUS_SEPARATOR}"
APPENDWATCH_COMPROMISED_BODY_PREFIX = (
    f"{APPENDWATCH_COMPROMISED_STATUS}{APPENDWATCH_STATUS_SEPARATOR}"
)
APPENDWATCH_OK_PREFIX = f"{APPENDWATCH_OK_STATUS:<{APPENDWATCH_STATUS_WIDTH}} "
APPENDWATCH_COMPROMISED_PREFIX = f"{APPENDWATCH_COMPROMISED_STATUS:<{APPENDWATCH_STATUS_WIDTH}} "
APPENDWATCH_ROOT_ENTRY = "."
APPENDWATCH_DIRECTORY_SUFFIX = "/"
APPENDWATCH_BLANK_LINE = ""
APPENDWATCH_TREE_START_INDEX = 1
APPENDWATCH_REMOVED_SECTION_HEADER_LINES = 2
APPENDWATCH_EXPECTED_TARGET_ENTRIES = 1
APPENDWATCH_COMPROMISED_ROOT_PREFIX = (
    f"{APPENDWATCH_ROOT_ENTRY}  [{APPENDWATCH_COMPROMISED_STATUS}:"
)
APPENDWATCH_REMOVED_SECTION_HEADER = "removed or replaced (no longer a regular file):"
APPENDWATCH_ARCHIVE_TEMP_FILENAME = ".appendwatch-tree.tmp"
APPENDWATCH_ARCHIVE_FILENAME_TEMPLATE = "appendwatch-tree.{attempt_id}.txt"
TREE_INDENT_GROUP = "indent"
TREE_BODY_GROUP = "body"
APPENDWATCH_NAME_GROUP = "name"
APPENDWATCH_PATH_GROUP = "path"
APPENDWATCH_COMPROMISED_DIRECTORY_PATTERN = re.compile(
    rf"{re.escape(APPENDWATCH_COMPROMISED_PREFIX)}"
    rf"(?P<{APPENDWATCH_NAME_GROUP}>[^/]+)/  \[.+\]"
)
APPENDWATCH_OK_FILE_PATTERN = re.compile(
    rf"{re.escape(APPENDWATCH_OK_PREFIX)}(?P<{APPENDWATCH_NAME_GROUP}>[^/]+)"
)
APPENDWATCH_COMPROMISED_FILE_PATTERN = re.compile(
    rf"{re.escape(APPENDWATCH_COMPROMISED_PREFIX)}"
    rf"(?P<{APPENDWATCH_NAME_GROUP}>[^/]+?)(?:  \[.*\])?"
)
APPENDWATCH_REMOVED_ENTRY_PATTERN = re.compile(
    rf"    {re.escape(APPENDWATCH_COMPROMISED_PREFIX)}"
    rf"(?P<{APPENDWATCH_PATH_GROUP}>.+?)(?:  \[.*\])?"
)
ALLOW_MULTIPLE_EVIDENCE_MATCHES = True
WEB_SEARCH_QUERY_ACTION = "search_query"
WEB_OPEN_ACTION = "open"
WEB_CLICK_ACTION = "click"
ELIGIBLE_WEB_ACTIONS = frozenset({
    WEB_SEARCH_QUERY_ACTION,
    WEB_OPEN_ACTION,
    WEB_CLICK_ACTION,
})
CODEX_TYPE_KEY = "type"
CODEX_PAYLOAD_KEY = "payload"
CODEX_CALL_ID_KEY = "call_id"
CODEX_ARGUMENTS_KEY = "arguments"
CODEX_SESSION_ID_KEY = "session_id"
CODEX_TIMESTAMP_KEY = "timestamp"
CODEX_MODEL_KEY = "model"
CODEX_REASONING_EFFORT_KEY = "effort"
CODEX_ORIGINATOR_KEY = "originator"
CODEX_SOURCE_KEY = "source"
CODEX_CLI_VERSION_KEY = "cli_version"
CODEX_MODEL_PROVIDER_KEY = "model_provider"
CODEX_OUTPUT_KEY = "output"
CODEX_TEXT_KEY = "text"
CODEX_NAMESPACE_KEY = "namespace"
CODEX_NAME_KEY = "name"
CODEX_ID_KEY = "id"
CODEX_RESULTS_KEY = "results"
CODEX_REF_ID_KEY = "ref_id"
CODEX_SESSION_META_TYPE = "session_meta"
CODEX_TURN_CONTEXT_TYPE = "turn_context"
CODEX_INPUT_TEXT_TYPE = "input_text"
CODEX_RESPONSE_ITEM_TYPE = "response_item"
CODEX_EVENT_MESSAGE_TYPE = "event_msg"
CODEX_FUNCTION_CALL_TYPE = "function_call"
CODEX_FUNCTION_CALL_OUTPUT_TYPE = "function_call_output"
CODEX_WEB_SEARCH_END_TYPE = "web_search_end"
CODEX_WEB_NAMESPACE = "web"
CODEX_WEB_FUNCTION_NAME = "run"
CODEX_TEXT_RESULT_TYPE = "text_result"
CODEX_TURN_REF_PREFIX = "turn"
SESSION_REASONING_EFFORT_KEY = "reasoning_effort"
ATTEMPT_STAGE_TRANSPORT = "transport"
ATTEMPT_STAGE_CONFIGURATION = "configuration"
ATTEMPT_STAGE_ROLLOUT_COPY = "rollout_copy"
ATTEMPT_STAGE_WORKBOOK_COPY = "workbook_copy"
ATTEMPT_STAGE_APPENDWATCH_COPY = "appendwatch_report_copy"
ATTEMPT_STAGE_APPENDWATCH_VALIDATION = "appendwatch_report_validation"
ATTEMPT_STAGE_ROLLOUT_INDEX = "rollout_index"
ATTEMPT_STAGE_PYDANTIC_VALIDATION = "pydantic_validation"
ATTEMPT_STAGE_EVIDENCE_VALIDATION = "duckdb_evidence_validation"
ATTEMPT_STAGE_RESEARCHER_RESOLUTION = "researcher_resolution"
ATTEMPT_STAGE_CARD = "innerdict_and_card"
ATTEMPT_STAGE_ACCEPTED = "accepted"
ATTEMPT_RESULT_PENDING = "pending"
ATTEMPT_RESULT_ACCEPTED = "accepted"
ATTEMPT_RESULT_CONFIGURATION_ERROR = "configuration_error"
ATTEMPT_RESULT_REJECTED = "rejected"
ATTEMPT_RESULT_RESPONSE_CODE = {
    ATTEMPT_RESULT_ACCEPTED: status.HTTP_200_OK,
    ATTEMPT_RESULT_CONFIGURATION_ERROR: status.HTTP_503_SERVICE_UNAVAILABLE,
    ATTEMPT_RESULT_REJECTED: status.HTTP_422_UNPROCESSABLE_CONTENT,
}
SSH_EXECUTABLE = "ssh"
SCP_EXECUTABLE = "scp"
TEXT_ENCODING = "utf-8"
JSON_MEDIA_TYPE = "application/json"
HTTP_GET_METHOD = "GET"
HTTP_POST_METHOD = "POST"
HTTP_ACCEPT_HEADER = "Accept"
HTTP_CONTENT_TYPE_HEADER = "Content-Type"
HTTP_REQUEST_CONTENT_TYPE_HEADER = "content-type"
HTTP_REQUEST_CONTENT_LENGTH_HEADER = "content-length"
TEXT_OUTPUT_FORMAT = "txt"
DOCX_OUTPUT_FORMAT = "docx"
SUPPORTED_OUTPUT_FORMATS = frozenset({TEXT_OUTPUT_FORMAT, DOCX_OUTPUT_FORMAT})
ROLLOUT_FILENAME_PREFIX = "rollout-"
ROLLOUT_FILENAME_SUFFIX = ".jsonl"
DETOUR_DB_SUFFIX = ".duckdb"
DETOUR_DB_FILENAME_TEMPLATE = "{stem}__detour_{detour_id}{suffix}"
WORKBOOK_ARCHIVE_TEMP_FILENAME = ".workbook.tmp"
WORKBOOK_ARCHIVE_FILENAME_TEMPLATE = "workbook.{attempt_id}.md"
HOST_WORKBOOK_TEMP_FILENAME_TEMPLATE = ".{filename}.tmp"
ROLLOUT_ARCHIVE_TEMP_FILENAME = ".rollout.tmp"
ROLLOUT_ARCHIVE_FILENAME_TEMPLATE = f"rollout.{{attempt_id}}{ROLLOUT_FILENAME_SUFFIX}"
ATOMIC_TEMP_FILENAME_TEMPLATE = ".{filename}.{nonce}.tmp"
RESPONSE_FILENAME = f"response{ROLLOUT_FILENAME_SUFFIX}"
CARD_ZIP_FILENAME_TEMPLATE = "{prefix}_{attempt_id}.zip"
ATTEMPT_ID_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S_%fZ"
ATTEMPT_ID_SEPARATOR = "_"
ROLLOUT_TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%S"
CUMULATIVE_KEY_SEPARATOR = "\0"
FCO_TIMESTAMP_TIMESPEC = "milliseconds"
API_VERSION = "1.0.0"
PULL_PATH = "/pull"
PUSH_PATH = "/push"
CONFIG_OPTION = "--config"
RESOURCE_PATH_KEY = "path"
RESOURCE_DESCRIPTION_KEY = "desc"
RESOURCE_SHA256_KEY = "sha256"
PYDANTIC_ERROR_MESSAGE_KEY = "msg"
PYDANTIC_ERROR_LOCATION_KEY = "loc"
PYDANTIC_ERROR_TYPE_KEY = "type"
PYDANTIC_ERROR_INPUT_KEY = "input"
PYDANTIC_MISSING_ERROR_TYPE = "missing"
ARTIFACT_ROLLOUT_KEY = "rollout"
ARTIFACT_WORKBOOK_KEY = "workbook"
ARTIFACT_APPENDWATCH_REPORT_KEY = "appendwatch_report"
ARTIFACT_CARD_ZIP_KEY = "card_zip"
ARTIFACT_HTTP_REQUEST_LOG_KEY = "http_request_log"
ARTIFACT_FILENAME_KEY = "filename"
ARTIFACT_SIZE_KEY = "size"
ARTIFACT_SHA256_KEY = "sha256"
ARTIFACT_LINE_COUNT_KEY = "line_count"
ATTEMPT_ID_KEY = "attempt_id"
ATTEMPT_STAGE_KEY = "stage"
ATTEMPT_RESULT_KEY = "result"
ATTEMPT_UPDATED_AT_KEY = "updated_at"
ATTEMPT_ARTIFACTS_KEY = "artifacts"
ATTEMPT_RUN_ID_KEY = "run_id"
ATTEMPT_SOURCE_KEY = "source_key"
ATTEMPT_SESSION_ID_KEY = "session_id"
ATTEMPT_ROLLOUT_RELATIVE_PATH_KEY = "rollout_relative_path"
ATTEMPT_MANIFEST_FILENAME = "attempt.json"
HTTP_REQUEST_LOG_FILENAME_TEMPLATE = "push.{attempt_id}.http.jsonl"
EVIDENCE_OUTCOME_V1_EXACT = "v1_exact"
EVIDENCE_OUTCOME_V2_NEAR = "v2_near"
EVIDENCE_OUTCOME_UNMATCHED = "unmatched"
EVIDENCE_OUTCOME_WITHDRAWN = "withdrawn"
EvidenceOutcome = Literal[  # type: ignore[valid-type]
    EVIDENCE_OUTCOME_V1_EXACT,
    EVIDENCE_OUTCOME_V2_NEAR,
    EVIDENCE_OUTCOME_UNMATCHED,
    EVIDENCE_OUTCOME_WITHDRAWN,
]
EVIDENCE_ITEMS_ACCEPTED_DEF: Callable[[Sequence[str]], bool] = lambda outcomes: (
    EVIDENCE_OUTCOME_V1_EXACT in outcomes
    and all(
        outcome in {EVIDENCE_OUTCOME_V1_EXACT, EVIDENCE_OUTCOME_WITHDRAWN} for outcome in outcomes
    )
)
EVIDENCE_LOCATION_DEF: Callable[[str, int], str] = lambda field, index: (
    Locale.EVIDENCE_LOCATION_TEMPLATE.format(
        field=field,
        index=index,
    )
)
EVIDENCE_PROGRESS_PRAISE_DEF: Callable[[Sequence[str]], bool] = lambda outcomes: (
    EVIDENCE_OUTCOME_V2_NEAR in outcomes
    and outcomes.count(EVIDENCE_OUTCOME_V1_EXACT) > len(outcomes) // 2
)
TREE_LINE = re.compile(
    rf"^(?P<{TREE_INDENT_GROUP}>(?:(?:│   )|(?:    ))*)"
    rf"(?:├── |└── )(?P<{TREE_BODY_GROUP}>.*)$"
)
CODEX_CITE_MARKER_PREFIX = "\ue200cite\ue202"
CODEX_CITE_MARKER_SUFFIX = "\ue201"
CODEX_REF_ID_PATTERN = rf"{re.escape(CODEX_TURN_REF_PREFIX)}[0-9]+[A-Za-z_]+[0-9]+"
CODEX_RESULT_SEPARATOR = "-" * 80
FOOTNOTE_CONTEXT_CHARACTERS = 160
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8612

CONFIG_FILENAME = "config_ai_augment.json"
MAP_SUBSET_0_TO_BATCH_KEY = "map_subset_0_to_batch"
MAP_COLUMNS = (DRAW_LABEL, BATCH_LABEL)
# ground truth is defined explicitly by released batch, exclusive of dupe
GROUND_TRUTH_COHORT = SourceCohort.GROUND_TRUTH
GROUND_TRUTH_RELEASE_BATCHES = frozenset({"subset 1", "subset 5", "subset 6", "subset 7"})
EXCLUDED_SOURCE_KEY = json.dumps(
    {KTP_FIRST_NAME_COL: "Mercouri G.", KTP_LAST_NAME_COL: "Kanatzidis"},
    sort_keys=True,
)
GROUND_TRUTH_DEF: Callable[
    [str, Mapping[str, str], tuple[str, ...]],
    bool,
] = lambda source_key, release_batches, draws: (
    source_key != EXCLUDED_SOURCE_KEY
    and any(release_batches.get(draw) in GROUND_TRUTH_RELEASE_BATCHES for draw in draws)
)
NO_GROUND_TRUTH_COHORT = SourceCohort.NO_GROUND_TRUTH
# no ground truth is defined analytically from all unreleased except some
NO_GROUND_TRUTH_PARTITION = 4
NO_GROUND_TRUTH_SSN_COUNT = 1
NO_GROUND_TRUTH_DEF: Callable[
    [int, bool, int],
    bool,
] = lambda partition, xlsx_non_exact, ssn_count: (
    partition == NO_GROUND_TRUTH_PARTITION
    and not xlsx_non_exact
    and ssn_count == NO_GROUND_TRUTH_SSN_COUNT
)
EXPECTED_GROUND_TRUTH_RESEARCHERS = 196
EXPECTED_NO_GROUND_TRUTH_RESEARCHERS = 78
EXPECTED_ELIGIBLE_RESEARCHERS = 274
EXPECTED_INELIGIBLE_RESEARCHERS = 33
EXPECTED_SOURCE_RESEARCHERS = EXPECTED_ELIGIBLE_RESEARCHERS + EXPECTED_INELIGIBLE_RESEARCHERS
EXPECTED_MULTIDRAW_SOURCE_RESEARCHERS = 5
RND_START = 1
INELIGIBLE_COHORT = SourceCohort.INELIGIBLE
INELIGIBLE_RELEASE_BATCH = "subset 8"
EXPECTED_INELIGIBILITY_COUNTS = {
    IneligibilityCategory.EXCLUDED_DUPLICATE_SOURCE_KEY: 1,
    IneligibilityCategory.RELEASE_BATCH_SUBSET_8: 3,
    IneligibilityCategory.STAGING_PARTITION_2: 7,
    IneligibilityCategory.STAGING_PARTITION_4_XLSX_NON_EXACT: 6,
    IneligibilityCategory.STAGING_PARTITION_4_MULTIPLE_SSN: 16,
}
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
CODEX_TURN_REF_NORMALIZED_VIEW = "codex_turn_ref_normalized"
CODEX_RETRY_BASELINE_TABLE = "codex_retry_baselines"
CODEX_EVIDENCE_AUDIT_TABLE = "codex_evidence_attempts"
CODEX_OUTPUT_ROWS_TABLE = "codex_output_rows"
CODEX_OUTPUT_VIEW = "codex_output"
CODEX_INNERDICT_TABLE = "codex_innerdicts"
CODEX_FC_ID_SEQUENCE = "codex_fc_id_sequence"
CODEX_FCO_ID_SEQUENCE = "codex_fco_id_sequence"
CODEX_CALLS_ID_SEQUENCE = "codex_calls_id_sequence"
CODEX_TURN_REF_ID_SEQUENCE = "codex_turn_ref_id_sequence"
CODEX_EVIDENCE_AUDIT_ID_SEQUENCE = "codex_evidence_audit_id_sequence"
ARCHIVED_ATTEMPTS_TABLE = "control_centre_archived_attempts"
ARCHIVED_ATTEMPT_MANIFEST_COLUMN = "manifest"

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
CODEX_CITE_TOKENS_COL = "codex.cite_tokens"
CODEX_RETRY_RUN_ID_COL = "run_id"
CODEX_RETRY_SOURCEKEY_COL = "sourcekey"
CODEX_RETRY_SESSION_ID_COL = "session_id"
CODEX_RETRY_ATTEMPT_ID_COL = "attempt_id"
CODEX_RETRY_CREATED_AT_COL = "created_at"
CODEX_RETRY_BASELINE_COL = "baseline"
CODEX_EVIDENCE_SUBMISSION_COL = "submission"
CODEX_EVIDENCE_ASSESSMENT_COL = "assessment"
CODEX_EVIDENCE_APPLIED_COL = "applied"
CODEX_EVIDENCE_ACCEPTED_COL = "accepted"
CODEX_EVIDENCE_AUDIT_ID_COL = "id"
CODEX_TOKEN_EXTENSION = "splink_udfs"
CREATE_ARCHIVED_ATTEMPTS_TABLE_SQL = (
    f"CREATE TABLE IF NOT EXISTS {ARCHIVED_ATTEMPTS_TABLE} ("
    f"{ATTEMPT_ID_KEY} VARCHAR PRIMARY KEY, "
    f"{ARCHIVED_ATTEMPT_MANIFEST_COLUMN} JSON NOT NULL)"
)
SELECT_ARCHIVED_ATTEMPT_IDS_SQL = f"SELECT {ATTEMPT_ID_KEY} FROM {ARCHIVED_ATTEMPTS_TABLE}"
INSERT_ARCHIVED_ATTEMPT_SQL = (
    f"INSERT INTO {ARCHIVED_ATTEMPTS_TABLE} "
    f"({ATTEMPT_ID_KEY}, {ARCHIVED_ATTEMPT_MANIFEST_COLUMN}) VALUES (?, ?)"
)
HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_HEADER = "content-type"
HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_JSON = "application/json"
NANOSECONDS_PER_MICROSECOND = 1_000

NOT_REPORTED_VALUE = get_args(NotReported)[0]
NOT_AVAILABLE_OR_APPLICABLE_VALUE = get_args(NotAvailableOrApplicable)[0]
STANDARDIZED_VALUE_FIELD = next(
    field
    for field in StandardizedFieldSubmission.model_fields
    if field not in FieldSubmission.model_fields
)
INITIAL_STANDARDIZED_VALUES: Mapping[str, StandardizedValue] = {
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL: ResearcherAuthorStandardized(
        first_name=NOT_REPORTED_VALUE,
        last_name=NOT_REPORTED_VALUE,
        orcid=NOT_REPORTED_VALUE,
        openalex_id=NOT_REPORTED_VALUE,
    ),
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL: PlaceOfResidenceStandardized(
        place=NOT_REPORTED_VALUE,
        location=NOT_REPORTED_VALUE,
    ),
    KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL: (
        RaceEthnicityLanguageCultureStandardized(
            race=NOT_AVAILABLE_OR_APPLICABLE_VALUE,
            ethnicity=NOT_AVAILABLE_OR_APPLICABLE_VALUE,
            language=NOT_REPORTED_VALUE,
            culture=NOT_AVAILABLE_OR_APPLICABLE_VALUE,
        )
    ),
    KTP_AI_AUGMENT_GENDER_COL: NOT_REPORTED_VALUE,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL: NOT_REPORTED_VALUE,
    KTP_AI_AUGMENT_EDUCATION_COL: NOT_REPORTED_VALUE,
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL: NOT_REPORTED_VALUE,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL: NOT_REPORTED_VALUE,
    KTP_AI_AUGMENT_LINKS_COL: NOT_REPORTED_VALUE,
}
AI_AUGMENT_CARD_EMPTY_VALUE_PLACEHOLDERS = KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS | {
    NOT_AVAILABLE_OR_APPLICABLE_VALUE
}

DRAW_NUMBER_COLUMN = DRAW_LABEL
TARGET_DRAW_NUMBER = "146"
FRAGMENT_TYPE_COLUMN = KTP_FRAGMENT_TYPE_COL
DOCX_ROW_FRAGMENT_TYPE = FragmentType.DOCX_ROW.value
ROLLOUT_LINE_FRAGMENT_TYPE = FragmentType.LINE_NUMBER.value
DOCX_TO_AI_AUGMENT_COLUMNS = (
    ("ktp.table_1_researcher_author", KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL),
    ("ktp.table_1_place_of_residence", KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL),
    (
        "ktp.table_1_race_ethnicity_language_culture",
        KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
    ),
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
    *(
        definition
        for plain_column, standardized_column in AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS
        for definition in (
            (plain_column, "VARCHAR NOT NULL"),
            (standardized_column, "VARCHAR NOT NULL"),
        )
    ),
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
ATTEMPT_RESPONSE_CONTENT_TYPE = {
    status.HTTP_200_OK: MEDIA_TYPE,
    status.HTTP_422_UNPROCESSABLE_CONTENT: JSON_MEDIA_TYPE,
    status.HTTP_503_SERVICE_UNAVAILABLE: JSON_MEDIA_TYPE,
}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    try:
        runtime_configuration()
    except PushConfigurationError as exc:
        logger.error(Locale.API_STARTUP_FAILED_LOG, exc)
        raise
    try:
        if _control_base_url() is None:
            push_configuration()
        else:
            initialize_guest_workbook()
    except PushConfigurationError as exc:
        logger.error(Locale.ROUTES_DISABLED_LOG, exc)
    yield


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
            raise ValueError(Locale.SESSION_METADATA_NONBLANK)
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
            raise ValueError(Locale.CONTROL_RUN_NORMALIZED)
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


SubmissionPayload: TypeAlias = Submission | StandardizedSubmission

EVIDENCE_SUBMISSION_EXAMPLE = L_FEI_FEI_INITIAL_FIXTURE.submission.model_dump(
    by_alias=True,
    mode="json",
)
RETRY_EVIDENCE_SUBMISSION_EXAMPLE = L_FEI_FEI_RETRY_FIXTURE.submission.model_dump(
    by_alias=True,
    mode="json",
)
RETRY_SUBMISSION_PUBLIC_GUIDANCE = (
    Locale.EVIDENCE_RETRY_STANDARDIZED_VALUES
    + Locale.EVIDENCE_RETRY_EXAMPLE_TEMPLATE.format(
        example=json.dumps(
            RETRY_EVIDENCE_SUBMISSION_EXAMPLE,
            ensure_ascii=False,
            indent=2,
        )
    )
)
SUBMISSION_EXAMPLE: dict[str, object] = dict[str, object](
    L_FEI_FEI_INITIAL_FIXTURE.submission.normalized_values()
)
PULL_EXAMPLE_FIRST_NAME, PULL_EXAMPLE_LAST_NAME = L_FEI_FEI_INITIAL_FIXTURE.identity
NULL_SUBMISSION_EXAMPLE = {
    KTP_FIRST_NAME_COL: PULL_EXAMPLE_FIRST_NAME,
    KTP_LAST_NAME_COL: PULL_EXAMPLE_LAST_NAME,
    **dict.fromkeys(AI_AUGMENT_COLUMNS),
}

APP_CONFIG: dict[str, Any] = {
    "title": Locale.API_TITLE,
    "description": Locale.API_DESCRIPTION,
    "version": API_VERSION,
    "lifespan": lifespan,
}

PULL_ROUTE: dict[str, Any] = {
    "path": PULL_PATH,
    "response_class": StreamingResponse,
    "summary": Locale.PULL_SUMMARY,
    "description": Locale.PULL_DESCRIPTION,
    "responses": {
        status.HTTP_200_OK: {
            "description": Locale.PULL_RESPONSE_DESCRIPTION,
            "content": {
                MEDIA_TYPE: {
                    "example": (json.dumps(NULL_SUBMISSION_EXAMPLE, ensure_ascii=False) + "\n"),
                },
            },
        },
    },
}

PUSH_ROUTE: dict[str, Any] = {
    "path": PUSH_PATH,
    "response_class": StreamingResponse,
    "summary": Locale.PUSH_SUMMARY,
    "description": Locale.PUSH_DESCRIPTION,
    "responses": {
        status.HTTP_200_OK: {
            "description": Locale.PUSH_RESPONSE_DESCRIPTION,
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
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": Locale.VALIDATION_ERROR_DETAIL},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": Locale.CONFIGURATION_ERROR_DETAIL},
    },
    "openapi_extra": {
        "requestBody": {
            "required": True,
            "content": {JSON_MEDIA_TYPE: {"example": EVIDENCE_SUBMISSION_EXAMPLE}},
        }
    },
}

app = FastAPI(**APP_CONFIG)


class RetryEvidenceObligation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    outcome: EvidenceOutcome
    excerpt: StrictStr | None = None
    url: StrictStr | None = None
    normalized_tokens: list[StrictStr] = Field(default_factory=list)


class RetryFieldObligation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: StrictStr
    evidence: list[RetryEvidenceObligation]
    accepted: bool


class RetryObligations(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    fields: dict[StrictStr, RetryFieldObligation]


class EvidenceCandidateAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    ref_id: StrictStr
    call_id: StrictStr
    cite_text: StrictStr
    excerpt_position: int
    url: StrictStr


class EvidenceItemAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: StrictStr
    index: int
    outcome: EvidenceOutcome
    excerpt: StrictStr | None
    url: StrictStr | None
    normalized_tokens: list[StrictStr]
    candidates: list[EvidenceCandidateAudit]


class EvidenceAttemptAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[EvidenceItemAudit]


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
            raise ValueError(Locale.WEB_RESULT_REF_ID_NONBLANK)
        return self


class PushConfigurationError(RuntimeError):
    pass


class PushValidationError(RuntimeError):
    pass


class EvidenceAssessmentError(PushValidationError):
    def __init__(self, message: str, *, public_detail: str) -> None:
        self.public_detail = public_detail
        super().__init__(message)


class MultipleEvidenceMatches(PushValidationError):
    def __init__(self, excerpt: str) -> None:
        self.excerpt = excerpt
        super().__init__(Locale.MULTIPLE_EVIDENCE_MATCHES_TEMPLATE.format(excerpt=excerpt))


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


class ArchivedArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    filename: StrictStr
    size: int = Field(ge=0)
    sha256: StrictStr


class ArchivedRolloutArtifact(ArchivedArtifact):
    line_count: int = Field(ge=1)


class ArchivedAttemptArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    rollout: ArchivedRolloutArtifact
    appendwatch_report: ArchivedArtifact
    workbook: ArchivedArtifact | None = None
    card_zip: ArchivedArtifact | None = None
    http_request_log: ArchivedArtifact


class ArchivedAttemptManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    attempt_id: StrictStr
    stage: StrictStr
    result: StrictStr
    updated_at: StrictStr
    artifacts: ArchivedAttemptArtifacts
    rollout_relative_path: StrictStr
    run_id: UUID | None = None
    source_key: StrictStr | None = None
    session_id: StrictStr | None = None


@dataclass(frozen=True)
class ArchivedAttemptRecovery:
    discovered: int
    invalid: int
    restored_attempt_ids: tuple[str, ...]
    restored_accepted_attempt_ids: tuple[str, ...]
    skipped_attempt_ids: tuple[str, ...]


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
            separators=COMPACT_JSON_SEPARATORS,
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
class EvidenceItemAssessment:
    field: str
    index: int
    evidence_number: int
    submission: EvidenceSubmission
    outcome: EvidenceOutcome
    match: EvidenceMatch | None
    normalized_tokens: tuple[str, ...] = ()
    candidates: tuple[EvidenceCandidate, ...] = ()


@dataclass(frozen=True)
class EvidenceAssessment:
    items: tuple[EvidenceItemAssessment, ...]

    @property
    def validated(self) -> ValidatedEvidence:
        validated: ValidatedEvidence = {field: [] for field in AI_AUGMENT_EVIDENCE_COLUMNS}
        for item in self.items:
            if item.match is not None and item.outcome == EVIDENCE_OUTCOME_V1_EXACT:
                validated[item.field].append(item.match)
        return validated

    @property
    def exact_count(self) -> int:
        return sum(item.outcome == EVIDENCE_OUTCOME_V1_EXACT for item in self.items)

    @property
    def accepted(self) -> bool:
        return all(
            EVIDENCE_ITEMS_ACCEPTED_DEF(
                tuple(item.outcome for item in self.items if item.field == field)
            )
            for field in AI_AUGMENT_EVIDENCE_COLUMNS
        )


@dataclass(frozen=True)
class ResearcherContext:
    source_key: str
    draw_number: str
    first_name: str
    last_name: str
    cohort: str = GROUND_TRUTH_COHORT
    draw_numbers: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttemptReplayInput:
    attempt_dir: Path
    attempt_id: str
    attempt_timestamp: datetime
    rollout_archive: ArchivedFile
    report_archive: ArchivedFile
    rollout_relative_path: PurePosixPath
    request_body: bytes
    run_id: UUID | None
    source_key: str | None
    session_id: str | None
    materialize_files: bool


@dataclass(frozen=True)
class AttemptExecution:
    stage: str
    result: str
    response_code: int
    response_body: str
    response_detail: str | None
    response_lines: tuple[str, ...]
    retry_submission_expected: bool
    source_key: str | None
    session_id: str | None
    card_archive: ArchivedFile | None
    error: Exception | None
    commit_database: bool


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
        raise PushConfigurationError(Locale.SETTING_ABSOLUTE_TEMPLATE.format(setting=setting))
    if path.is_symlink() or not path.is_file() or not os.access(path, os.R_OK):
        raise PushConfigurationError(Locale.SETTING_READABLE_FILE_TEMPLATE.format(setting=setting))
    return path


def _detour_db_path(path: Path) -> Path:
    suffix = path.suffix or DETOUR_DB_SUFFIX
    stem = path.stem if path.suffix else path.name
    return path.with_name(
        DETOUR_DB_FILENAME_TEMPLATE.format(
            stem=stem,
            detour_id=DETOUR_ID,
            suffix=suffix,
        )
    )


def _seed_evidence_random(sample_seed: int) -> None:
    EVIDENCE_RANDOM.seed(sample_seed)


def registered_release_map(config: PipelineConfig) -> RegisteredResource:
    meta = config.files_config.get(MAP_SUBSET_0_TO_BATCH_KEY)
    if meta is None:
        raise PushConfigurationError(
            Locale.FILES_CONFIG_RESOURCE_MISSING_TEMPLATE.format(
                resource_key=MAP_SUBSET_0_TO_BATCH_KEY
            )
        )
    try:
        return register_resource(
            Path(meta[RESOURCE_PATH_KEY]),
            group=ResourceGroup.KTP_PIPELINE_ARTIFACT,
            fragment_type=FragmentType.CSV_ROW,
            description=meta[RESOURCE_DESCRIPTION_KEY],
            expected_hash=meta[RESOURCE_SHA256_KEY],
        )
    except (KeyError, OSError, ValueError) as exc:
        raise PushConfigurationError(
            Locale.CONFIGURED_RESOURCE_INVALID_TEMPLATE.format(
                resource_key=MAP_SUBSET_0_TO_BATCH_KEY
            )
        ) from exc


def load_release_batches(resource: RegisteredResource) -> dict[str, str]:
    path = Path(resource)
    try:
        with path.open(encoding=TEXT_ENCODING, newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != MAP_COLUMNS:
                raise PushConfigurationError(
                    Locale.MAP_COLUMNS_INVALID_TEMPLATE.format(
                        resource_key=MAP_SUBSET_0_TO_BATCH_KEY,
                        columns=MAP_COLUMNS,
                    )
                )
            batches: dict[str, str] = {}
            for row_number, row in enumerate(reader, start=2):
                draw_number = row.get(DRAW_LABEL)
                release_batch = row.get(BATCH_LABEL)
                if not _valid_nonblank(draw_number) or not _valid_nonblank(release_batch):
                    raise PushConfigurationError(
                        Locale.MAP_ROW_BLANK_TEMPLATE.format(
                            resource_key=MAP_SUBSET_0_TO_BATCH_KEY,
                            row_number=row_number,
                        )
                    )
                assert isinstance(draw_number, str)
                assert isinstance(release_batch, str)
                if draw_number in batches and batches[draw_number] != release_batch:
                    raise PushConfigurationError(
                        Locale.MAP_DRAW_CONFLICT_TEMPLATE.format(
                            resource_key=MAP_SUBSET_0_TO_BATCH_KEY,
                            draw_number=draw_number,
                        )
                    )
                batches[draw_number] = release_batch
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PushConfigurationError(
            Locale.MAP_CSV_UNREADABLE_TEMPLATE.format(resource_key=MAP_SUBSET_0_TO_BATCH_KEY)
        ) from exc
    if not batches:
        raise PushConfigurationError(
            Locale.MAP_CSV_EMPTY_TEMPLATE.format(resource_key=MAP_SUBSET_0_TO_BATCH_KEY)
        )
    return batches


def _innerdict_json_rows(
    value: object,
    *,
    table_name: str,
    source_key: str,
) -> tuple[dict[str, object], ...]:
    if not isinstance(value, str):
        raise PushConfigurationError(
            Locale.INNERDICTS_NON_TEXT_TEMPLATE.format(
                table_name=table_name,
                source_key=source_key,
            )
        )
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(value.splitlines(), start=1):
        try:
            row: object = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PushConfigurationError(
                Locale.INNERDICTS_MALFORMED_TEMPLATE.format(
                    table_name=table_name,
                    source_key=source_key,
                    line_number=line_number,
                )
            ) from exc
        if not isinstance(row, dict):
            raise PushConfigurationError(
                Locale.INNERDICTS_NON_OBJECT_TEMPLATE.format(
                    table_name=table_name,
                    source_key=source_key,
                    line_number=line_number,
                )
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
            raise PushConfigurationError(
                Locale.SOURCE_DUCKDB_TABLE_MISSING_TEMPLATE.format(table_name=table_name)
            ) from exc
        for raw_source_key, jsonlines in table_rows:
            if not isinstance(raw_source_key, str):
                raise PushConfigurationError(
                    Locale.TABLE_NAMEKEY_NON_TEXT_TEMPLATE.format(table_name=table_name)
                )
            try:
                name_key = NameKey.from_json_key(raw_source_key)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise PushConfigurationError(
                    Locale.TABLE_NAMEKEY_INVALID_TEMPLATE.format(table_name=table_name)
                ) from exc
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
    rnd_values = list(range(RND_START, len(source_researchers) + RND_START))
    Random(sample_seed).shuffle(rnd_values)
    rnd_by_source_key = dict(zip(sorted(source_researchers), rnd_values, strict=True))
    ground_truth = {
        source_key
        for source_key, (_name_key, draws) in source_researchers.items()
        if GROUND_TRUTH_DEF(source_key, release_batches, draws)
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
            Locale.ELIGIBILITY_FLAGS_MISSING_TEMPLATE.format(table_name=CARD_PARTITION_TABLE)
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
                Locale.SOURCE_CLASSIFICATIONS_INVALID_TEMPLATE.format(
                    table_name=CARD_PARTITION_TABLE
                )
            )
        partition_flags[source_key] = (partition, xlsx_non_exact, ssn_count)
    no_ground_truth = {
        source_key
        for source_key, (partition, xlsx_non_exact, ssn_count) in partition_flags.items()
        if NO_GROUND_TRUTH_DEF(partition, xlsx_non_exact, ssn_count)
    }
    missing_source_keys = no_ground_truth - source_researchers.keys()
    overlap = ground_truth & no_ground_truth
    if missing_source_keys:
        raise PushConfigurationError(Locale.CARD_PARTITION_UNKNOWN_SOURCE_KEYS)
    if overlap:
        raise PushConfigurationError(Locale.COHORTS_OVERLAP)
    if len(ground_truth) != EXPECTED_GROUND_TRUTH_RESEARCHERS:
        raise PushConfigurationError(
            Locale.GROUND_TRUTH_CARDINALITY_TEMPLATE.format(
                expected=EXPECTED_GROUND_TRUTH_RESEARCHERS,
                actual=len(ground_truth),
            )
        )
    if len(no_ground_truth) != EXPECTED_NO_GROUND_TRUTH_RESEARCHERS:
        raise PushConfigurationError(
            Locale.NO_GROUND_TRUTH_CARDINALITY_TEMPLATE.format(
                expected=EXPECTED_NO_GROUND_TRUTH_RESEARCHERS,
                actual=len(no_ground_truth),
            )
        )
    if len(ground_truth | no_ground_truth) != EXPECTED_ELIGIBLE_RESEARCHERS:
        raise PushConfigurationError(Locale.ELIGIBLE_COHORT_CARDINALITY_INVALID)
    if set(partition_flags) != set(source_researchers):
        raise PushConfigurationError(Locale.CARD_PARTITION_SOURCE_KEYS_MISMATCH)

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
                ineligibility_category = IneligibilityCategory.EXCLUDED_DUPLICATE_SOURCE_KEY
            elif any(release_batches.get(draw) == INELIGIBLE_RELEASE_BATCH for draw in draws):
                ineligibility_category = IneligibilityCategory.RELEASE_BATCH_SUBSET_8
            elif partition == KTP_PARTITION_SSN_VALUE:
                ineligibility_category = IneligibilityCategory.STAGING_PARTITION_2
            elif partition == KTP_PARTITION_DOCX_VALUE and xlsx_non_exact:
                ineligibility_category = IneligibilityCategory.STAGING_PARTITION_4_XLSX_NON_EXACT
            elif partition == KTP_PARTITION_DOCX_VALUE and ssn_count > NO_GROUND_TRUTH_SSN_COUNT:
                ineligibility_category = IneligibilityCategory.STAGING_PARTITION_4_MULTIPLE_SSN
            else:
                raise PushConfigurationError(Locale.INELIGIBILITY_CATEGORY_UNKNOWN)
        population.append(
            SourcePopulationRow(
                source_key=source_key,
                rnd=rnd_by_source_key[source_key],
                first_name=name_key.first_name,
                last_name=name_key.last_name,
                draw_numbers=tuple(sorted(draws, key=_draw_sort_key)),
                cohort=cohort,
                ineligibility_category=ineligibility_category,
            )
        )

    population.sort(
        key=lambda row: (
            tuple(_draw_sort_key(draw) for draw in row.draw_numbers),
            row.first_name.casefold(),
            row.last_name.casefold(),
            row.source_key,
        )
    )
    cohort_counts = Counter(row.cohort for row in population)
    ineligibility_counts = Counter(
        row.ineligibility_category for row in population if row.ineligibility_category is not None
    )
    if cohort_counts != {
        GROUND_TRUTH_COHORT: EXPECTED_GROUND_TRUTH_RESEARCHERS,
        NO_GROUND_TRUTH_COHORT: EXPECTED_NO_GROUND_TRUTH_RESEARCHERS,
        INELIGIBLE_COHORT: EXPECTED_INELIGIBLE_RESEARCHERS,
    }:
        raise PushConfigurationError(Locale.SOURCE_POPULATION_COHORTS_INVALID)
    if ineligibility_counts != EXPECTED_INELIGIBILITY_COUNTS:
        raise PushConfigurationError(Locale.SOURCE_POPULATION_INELIGIBILITY_INVALID)
    if len(population) != EXPECTED_SOURCE_RESEARCHERS:
        raise PushConfigurationError(Locale.SOURCE_POPULATION_CARDINALITY_INVALID)
    if {row.rnd for row in population} != set(
        range(RND_START, EXPECTED_SOURCE_RESEARCHERS + RND_START)
    ):
        raise PushConfigurationError(Locale.SOURCE_POPULATION_RND_INVALID)
    if (
        sum(len(row.draw_numbers) > 1 for row in population)
        != EXPECTED_MULTIDRAW_SOURCE_RESEARCHERS
    ):
        raise PushConfigurationError(Locale.SOURCE_POPULATION_MULTIDRAW_INVALID)
    return tuple(population)


def eligible_cohorts(
    source_population: Sequence[SourcePopulationRow],
) -> dict[str, str]:
    return {
        row.source_key: row.cohort for row in source_population if row.cohort != INELIGIBLE_COHORT
    }


def _control_base_url() -> str | None:
    raw = CONTROL_BASE_URL
    if not raw:
        return None
    if raw != raw.strip() or _has_control_character(raw):
        raise PushConfigurationError(
            Locale.CONTROL_URL_INVALID_TEMPLATE.format(environment_name=CONTROL_URL_ENV_NAME)
        )
    parsed = urlsplit(raw)
    if (
        parsed.scheme != CONTROL_SCHEME
        or parsed.hostname != CONTROL_HOST
        or parsed.port != CONTROL_PORT
        or parsed.path not in CONTROL_ROOT_PATHS
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise PushConfigurationError(
            Locale.CONTROL_URL_EXPECTED_TEMPLATE.format(
                environment_name=CONTROL_URL_ENV_NAME,
                host=CONTROL_HOST,
                port=CONTROL_PORT,
            )
        )
    return raw.rstrip("/")


def _control_request(
    base_url: str,
    path: str,
    *,
    method: str,
    body: bytes | None = None,
) -> bytes:
    headers = {HTTP_ACCEPT_HEADER: JSON_MEDIA_TYPE}
    if body is not None:
        headers[HTTP_CONTENT_TYPE_HEADER] = JSON_MEDIA_TYPE
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
        raise PushConfigurationError(Locale.CONTROL_ENDPOINT_UNAVAILABLE) from exc


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
            _control_request(
                base_url,
                CONTROL_CURRENT_PATH,
                method=HTTP_GET_METHOD,
            )
        )
    except ValidationError as exc:
        raise PushConfigurationError(Locale.CONTROL_SANCTION_MALFORMED) from exc
    if snapshot.sanctioned_run is None:
        raise PushConfigurationError(Locale.CONTROL_SANCTION_MISSING)
    run = snapshot.sanctioned_run
    with CONSUMED_RUN_LOCK:
        if run.run_id in CONSUMED_RUN_IDS:
            raise PushConfigurationError(Locale.CONTROL_SANCTION_CONSUMED)
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
    body = (
        ControlAcceptedRequest(
            source_key=snapshot.source_key,
            session_id=snapshot.session_id,
            attempt_id=attempt_id,
        )
        .model_dump_json()
        .encode(TEXT_ENCODING)
    )
    path = CONTROL_ACCEPTED_PATH_TEMPLATE.format(run_id=snapshot.run_id)
    try:
        response = ControlAcceptedResponse.model_validate_json(
            _control_request(
                snapshot.control_base_url,
                path,
                method=HTTP_POST_METHOD,
                body=body,
            )
        )
    except ValidationError as exc:
        raise PushConfigurationError(Locale.CONTROL_ACKNOWLEDGEMENT_MALFORMED) from exc
    if not response.acknowledged:
        raise PushConfigurationError(Locale.CONTROL_ACKNOWLEDGEMENT_REFUSED)


def configure_runtime(config_path: Path) -> RuntimeConfiguration:
    global RUNTIME_CONFIGURATION

    try:
        pipeline = PipelineConfig.from_json(config_path)
    except (OSError, ValueError) as exc:
        raise PushConfigurationError(
            Locale.CONFIG_INVALID_TEMPLATE.format(config_path=config_path)
        ) from exc
    if pipeline.output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise PushConfigurationError(Locale.OUTPUT_FORMAT_INVALID)
    if not pipeline.db_file.is_file() or not os.access(pipeline.db_file, os.R_OK):
        raise PushConfigurationError(
            Locale.SOURCE_DUCKDB_UNREADABLE_TEMPLATE.format(db_file=pipeline.db_file)
        )
    if pipeline.output_format == DOCX_OUTPUT_FORMAT and (
        not pipeline.pandoc_reference_docx.is_file()
        or not os.access(pipeline.pandoc_reference_docx, os.R_OK)
    ):
        raise PushConfigurationError(Locale.DOCX_REFERENCE_UNREADABLE)
    try:
        ZoneInfo(pipeline.timezone)
    except (KeyError, ValueError) as exc:
        raise PushConfigurationError(
            Locale.TIMEZONE_INVALID_TEMPLATE.format(timezone=pipeline.timezone)
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
        raise PushConfigurationError(Locale.SOURCE_DUCKDB_VALIDATION_FAILED) from exc
    finally:
        if source_conn is not None:
            source_conn.close()

    detour_db_path = _detour_db_path(pipeline.db_file)
    if detour_db_path == pipeline.db_file:
        raise PushConfigurationError(Locale.DETOUR_DB_EQUALS_SOURCE)
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
            Locale.API_CONFIG_REQUIRED_TEMPLATE.format(config_filename=CONFIG_FILENAME)
        )
    return RUNTIME_CONFIGURATION


def push_configuration(rollout_jsonl: str | None = None) -> PushConfiguration:
    raw_rollout = ROLLOUT_JSONL if rollout_jsonl is None else rollout_jsonl
    if not raw_rollout.strip():
        raise PushConfigurationError(
            Locale.ROLLOUT_NOT_SET_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
        )
    if raw_rollout != raw_rollout.strip() or _has_control_character(raw_rollout):
        raise PushConfigurationError(
            Locale.ROLLOUT_WHITESPACE_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
        )

    rollout_path = PurePosixPath(raw_rollout)
    if str(rollout_path) != raw_rollout or any(
        part in FORBIDDEN_NORMALIZED_PATH_PARTS for part in rollout_path.parts
    ):
        raise PushConfigurationError(
            Locale.ROLLOUT_NOT_NORMALIZED_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
        )
    try:
        relative_path = rollout_path.relative_to(CODEX_SESSIONS_ROOT)
    except ValueError as exc:
        raise PushConfigurationError(
            Locale.ROLLOUT_OUTSIDE_ROOT_TEMPLATE.format(
                environment_name=ROLLOUT_ENV_NAME,
                sessions_root=CODEX_SESSIONS_ROOT,
            )
        ) from exc
    if (
        relative_path == CURRENT_DIRECTORY
        or not relative_path.name.startswith(ROLLOUT_FILENAME_PREFIX)
        or relative_path.suffix != ROLLOUT_FILENAME_SUFFIX
    ):
        raise PushConfigurationError(
            Locale.ROLLOUT_FILENAME_INVALID_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
        )

    if not _valid_nonblank(AIVM_INSTANCE):
        raise PushConfigurationError(Locale.AIVM_INSTANCE_INVALID)
    if not _valid_nonblank(AIVM_USER):
        raise PushConfigurationError(Locale.AIVM_USER_INVALID)
    if not AIVM_SSH_PORT.isdecimal() or not MIN_TCP_PORT <= int(AIVM_SSH_PORT) <= MAX_TCP_PORT:
        raise PushConfigurationError(Locale.AIVM_SSH_PORT_INVALID)

    return PushConfiguration(
        rollout_guest_path=raw_rollout,
        rollout_relative_path=relative_path,
        appendwatch_report=_configuration_file(
            APPENDWATCH_REPORT,
            APPENDWATCH_REPORT_ENV_NAME,
        ),
        lima_ssh_config=_configuration_file(
            LIMA_SSH_CONFIG_PATH,
            LIMA_SSH_CONFIG_ENV_NAME,
        ),
        identity_file=_configuration_file(
            AIVM_IDENTITY_FILE,
            AIVM_IDENTITY_FILE_ENV_NAME,
        ),
        known_hosts_file=_configuration_file(
            AIVM_KNOWN_HOSTS_FILE,
            AIVM_KNOWN_HOSTS_FILE_ENV_NAME,
        ),
        ssh_target=f"{AIVM_INSTANCE}-{AIVM_USER}",
        host_key_alias=f"lima-{AIVM_INSTANCE}-{AIVM_USER}",
    )


def new_attempt_id(attempt_timestamp: datetime | None = None) -> str:
    current_timestamp = attempt_timestamp or datetime.now(timezone.utc)
    timestamp_text = current_timestamp.strftime(ATTEMPT_ID_TIMESTAMP_FORMAT)
    return f"{timestamp_text}{ATTEMPT_ID_SEPARATOR}{uuid4().hex}"


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
        raise PushConfigurationError(Locale.HOST_WORKBOOK_INVALID)
    return HOST_WORKBOOK_PATH


def initialize_guest_workbook() -> None:
    global WORKBOOK_INITIALIZED

    host_workbook = _host_workbook()
    lima_ssh_config = _configuration_file(
        LIMA_SSH_CONFIG_PATH,
        LIMA_SSH_CONFIG_ENV_NAME,
    )
    identity_file = _configuration_file(
        AIVM_IDENTITY_FILE,
        AIVM_IDENTITY_FILE_ENV_NAME,
    )
    known_hosts_file = _configuration_file(
        AIVM_KNOWN_HOSTS_FILE,
        AIVM_KNOWN_HOSTS_FILE_ENV_NAME,
    )
    options = _aivm_connection_options(
        lima_ssh_config=lima_ssh_config,
        identity_file=identity_file,
        known_hosts_file=known_hosts_file,
        host_key_alias=AIVM_HOST_KEY_ALIAS,
    )
    try:
        subprocess.run(
            [
                SSH_EXECUTABLE,
                *options,
                AIVM_SSH_TARGET,
                "mkdir",
                "-p",
                "--",
                str(AIVM_WORKDIR),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SSH_TIMEOUT_SECONDS,
        )
        subprocess.run(
            [
                SCP_EXECUTABLE,
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
        raise PushConfigurationError(Locale.HOST_WORKBOOK_INITIALIZATION_FAILED) from exc
    with WORKBOOK_STATE_LOCK:
        WORKBOOK_INITIALIZED = True


def copy_guest_workbook(
    configuration: PushConfiguration,
    attempt_dir: Path,
    attempt_id: str,
) -> ArchivedFile:
    temporary = attempt_dir / WORKBOOK_ARCHIVE_TEMP_FILENAME
    destination = attempt_dir / WORKBOOK_ARCHIVE_FILENAME_TEMPLATE.format(attempt_id=attempt_id)
    options = _aivm_connection_options(
        lima_ssh_config=configuration.lima_ssh_config,
        identity_file=configuration.identity_file,
        known_hosts_file=configuration.known_hosts_file,
        host_key_alias=configuration.host_key_alias,
    )
    try:
        subprocess.run(
            [
                SCP_EXECUTABLE,
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
            raise PushConfigurationError(Locale.SCP_WORKBOOK_ARCHIVE_INVALID)
        archive = _publish_archive(temporary, destination)
        host_temporary = HOST_WORKBOOK_PATH.with_name(
            HOST_WORKBOOK_TEMP_FILENAME_TEMPLATE.format(filename=HOST_WORKBOOK_PATH.name)
        )
        try:
            shutil.copyfile(archive.path, host_temporary)
            _fsync_file(host_temporary)
            os.replace(host_temporary, _host_workbook())
            _fsync_directory(HOST_WORKBOOK_PATH.parent)
        finally:
            host_temporary.unlink(missing_ok=True)
        return archive
    except (OSError, subprocess.SubprocessError) as exc:
        raise PushConfigurationError(Locale.GUEST_WORKBOOK_ARCHIVE_FAILED) from exc
    finally:
        temporary.unlink(missing_ok=True)


def copy_rollout(
    configuration: PushConfiguration,
    attempt_dir: Path,
    attempt_id: str,
) -> ArchivedFile:
    temporary = attempt_dir / ROLLOUT_ARCHIVE_TEMP_FILENAME
    destination = attempt_dir / ROLLOUT_ARCHIVE_FILENAME_TEMPLATE.format(attempt_id=attempt_id)
    options = _aivm_connection_options(
        lima_ssh_config=configuration.lima_ssh_config,
        identity_file=configuration.identity_file,
        known_hosts_file=configuration.known_hosts_file,
        host_key_alias=configuration.host_key_alias,
    )
    command = [
        SCP_EXECUTABLE,
        *options,
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
            raise PushConfigurationError(Locale.SCP_ROLLOUT_ARCHIVE_INVALID)
        return _publish_archive(temporary, destination)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PushConfigurationError(Locale.ROLLOUT_SCP_FAILED) from exc
    finally:
        temporary.unlink(missing_ok=True)


def copy_appendwatch_report(
    configuration: PushConfiguration,
    attempt_dir: Path,
    attempt_id: str,
) -> ArchivedFile:
    temporary = attempt_dir / APPENDWATCH_ARCHIVE_TEMP_FILENAME
    destination = attempt_dir / APPENDWATCH_ARCHIVE_FILENAME_TEMPLATE.format(attempt_id=attempt_id)
    try:
        shutil.copyfile(configuration.appendwatch_report, temporary)
        return _publish_archive(temporary, destination)
    except OSError as exc:
        raise PushConfigurationError(Locale.APPENDWATCH_ARCHIVE_FAILED) from exc
    finally:
        temporary.unlink(missing_ok=True)


def parse_appendwatch_report(
    report_path: Path,
    rollout_relative_path: PurePosixPath,
) -> None:
    try:
        report = report_path.read_text(encoding=TEXT_ENCODING)
    except (OSError, UnicodeError) as exc:
        raise PushValidationError(Locale.APPENDWATCH_REPORT_UNREADABLE) from exc
    if not report.endswith("\n"):
        raise PushValidationError(Locale.APPENDWATCH_REPORT_INCOMPLETE)

    lines = report.splitlines()
    if not lines or lines[0] != APPENDWATCH_ROOT_ENTRY:
        if lines and lines[0].startswith(APPENDWATCH_COMPROMISED_ROOT_PREFIX):
            raise PushValidationError(Locale.APPENDWATCH_GLOBAL_DEGRADATION)
        raise PushValidationError(Locale.APPENDWATCH_ROOT_MALFORMED)

    target = rollout_relative_path.parts
    directories: list[tuple[str, bool]] = []
    seen_paths: set[tuple[str, ...]] = set()
    target_entries: list[tuple[str, bool]] = []
    line_index = APPENDWATCH_TREE_START_INDEX

    while line_index < len(lines) and lines[line_index] != APPENDWATCH_BLANK_LINE:
        match = TREE_LINE.fullmatch(lines[line_index])
        if match is None:
            raise PushValidationError(Locale.APPENDWATCH_TREE_LINE_MALFORMED)
        indent = match.group(TREE_INDENT_GROUP)
        depth = len(indent) // TREE_INDENT_WIDTH
        if depth > len(directories):
            raise PushValidationError(Locale.APPENDWATCH_NESTING_INVALID)
        directories = directories[:depth]
        parent_parts = tuple(name for name, _compromised in directories)
        parent_compromised = any(compromised for _name, compromised in directories)
        body = match.group(TREE_BODY_GROUP)

        compromised_directory = APPENDWATCH_COMPROMISED_DIRECTORY_PATTERN.fullmatch(body)
        if compromised_directory is not None:
            name = compromised_directory.group(APPENDWATCH_NAME_GROUP)
            path = (*parent_parts, name)
            if path in seen_paths:
                raise PushValidationError(Locale.APPENDWATCH_PATH_DUPLICATE)
            seen_paths.add(path)
            directories.append((name, True))
            line_index += 1
            continue

        if body.endswith(APPENDWATCH_DIRECTORY_SUFFIX) and not body.startswith((
            APPENDWATCH_OK_BODY_PREFIX,
            APPENDWATCH_COMPROMISED_BODY_PREFIX,
        )):
            name = body.removesuffix(APPENDWATCH_DIRECTORY_SUFFIX)
            if not name or APPENDWATCH_DIRECTORY_SUFFIX in name:
                raise PushValidationError(Locale.APPENDWATCH_DIRECTORY_MALFORMED)
            path = (*parent_parts, name)
            if path in seen_paths:
                raise PushValidationError(Locale.APPENDWATCH_PATH_DUPLICATE)
            seen_paths.add(path)
            directories.append((name, parent_compromised))
            line_index += 1
            continue

        ok_file = APPENDWATCH_OK_FILE_PATTERN.fullmatch(body)
        compromised_file = APPENDWATCH_COMPROMISED_FILE_PATTERN.fullmatch(body)
        if ok_file is None and compromised_file is None:
            raise PushValidationError(Locale.APPENDWATCH_FILE_ENTRY_MALFORMED)
        name = (ok_file or compromised_file).group(  # type: ignore[union-attr]
            APPENDWATCH_NAME_GROUP
        )
        path = (*parent_parts, name)
        if path in seen_paths:
            raise PushValidationError(Locale.APPENDWATCH_PATH_DUPLICATE)
        seen_paths.add(path)
        if path == target:
            target_entries.append((
                (APPENDWATCH_OK_STATUS if ok_file is not None else APPENDWATCH_COMPROMISED_STATUS),
                parent_compromised,
            ))
        line_index += 1

    if line_index < len(lines):
        if lines[line_index:] == [APPENDWATCH_BLANK_LINE]:
            raise PushValidationError(Locale.APPENDWATCH_STRAY_BLANK_LINE)
        if lines[line_index : line_index + APPENDWATCH_REMOVED_SECTION_HEADER_LINES] != [
            APPENDWATCH_BLANK_LINE,
            APPENDWATCH_REMOVED_SECTION_HEADER,
        ]:
            raise PushValidationError(Locale.APPENDWATCH_REMOVED_SECTION_MALFORMED)
        for removed_line in lines[line_index + APPENDWATCH_REMOVED_SECTION_HEADER_LINES :]:
            removed = APPENDWATCH_REMOVED_ENTRY_PATTERN.fullmatch(removed_line)
            if removed is None:
                raise PushValidationError(Locale.APPENDWATCH_REMOVED_ENTRY_MALFORMED)
            if PurePosixPath(removed.group(APPENDWATCH_PATH_GROUP)).parts == target:
                raise PushValidationError(Locale.ROLLOUT_REMOVED_OR_REPLACED)

    if len(target_entries) != APPENDWATCH_EXPECTED_TARGET_ENTRIES:
        reason = (
            Locale.ROLLOUT_STATUS_MISSING if not target_entries else Locale.ROLLOUT_STATUS_AMBIGUOUS
        )
        raise PushValidationError(Locale.ROLLOUT_STATUS_INVALID_TEMPLATE.format(reason=reason))
    status, compromised_ancestor = target_entries[0]
    if status != APPENDWATCH_OK_STATUS or compromised_ancestor:
        raise PushValidationError(Locale.ROLLOUT_NOT_OK)


def parse_rollout(rollout_path: Path) -> tuple[RolloutRecord, ...]:
    try:
        raw_lines = rollout_path.read_bytes().splitlines(keepends=True)
    except OSError as exc:
        raise PushValidationError(Locale.ROLLOUT_UNREADABLE) from exc

    records: list[RolloutRecord] = []
    for line_number, raw_line in enumerate(raw_lines, start=1):
        completed = raw_line.endswith(b"\n")
        encoded = raw_line[:-1] if completed else raw_line
        if encoded.endswith(b"\r"):
            encoded = encoded[:-1]
        try:
            value: object = json.loads(encoded.decode(TEXT_ENCODING))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if line_number == len(raw_lines) and not completed:
                break
            raise PushValidationError(
                Locale.ROLLOUT_JSONL_MALFORMED_TEMPLATE.format(line_number=line_number)
            ) from exc
        if not isinstance(value, dict):
            raise PushValidationError(
                Locale.ROLLOUT_LINE_NON_OBJECT_TEMPLATE.format(line_number=line_number)
            )
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
        raise PushValidationError(Locale.TIMESTAMP_INVALID_TEMPLATE.format(label=label))
    raw = cast(str, value)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PushValidationError(Locale.TIMESTAMP_INVALID_TEMPLATE.format(label=label)) from exc
    if parsed.tzinfo is None:
        raise PushValidationError(Locale.TIMESTAMP_TIMEZONE_MISSING_TEMPLATE.format(label=label))
    return raw


def _web_arguments(payload: Mapping[str, object], line_number: int) -> dict[str, object]:
    call_id = payload.get(CODEX_CALL_ID_KEY)
    if not _valid_nonblank(call_id):
        raise PushValidationError(
            Locale.WEB_CALL_ID_INVALID_TEMPLATE.format(line_number=line_number)
        )
    arguments = payload.get(CODEX_ARGUMENTS_KEY)
    if not isinstance(arguments, str):
        raise PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_UNSUPPORTED_TEMPLATE.format(call_id=call_id)
        )
    try:
        decoded: object = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_MALFORMED_TEMPLATE.format(call_id=call_id)
        ) from exc
    if not isinstance(decoded, dict):
        raise PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_NON_OBJECT_TEMPLATE.format(call_id=call_id)
        )
    eligible_actions = [action for action in ELIGIBLE_WEB_ACTIONS if decoded.get(action)]
    if len(eligible_actions) != 1:
        raise PushValidationError(Locale.WEB_CALL_ACTION_COUNT_TEMPLATE.format(call_id=call_id))
    return cast(dict[str, object], decoded)


def _session_metadata(
    records: tuple[RolloutRecord, ...],
    *,
    timezone_name: str,
    configured_rollout_basename: str | None,
) -> SessionMetadata:
    session_records = [
        record for record in records if record.value.get(CODEX_TYPE_KEY) == CODEX_SESSION_META_TYPE
    ]
    if len(session_records) != 1:
        raise PushValidationError(Locale.SESSION_META_COUNT_INVALID)
    session_record = session_records[0]
    payload = session_record.value.get(CODEX_PAYLOAD_KEY)
    if not isinstance(payload, dict):
        raise PushValidationError(Locale.SESSION_META_PAYLOAD_MALFORMED)
    session_id = payload.get(CODEX_SESSION_ID_KEY)
    if not _valid_nonblank(session_id):
        raise PushValidationError(Locale.SESSION_META_SESSION_ID_INVALID)
    session_id = cast(str, session_id)
    payload_timestamp = _timestamp(
        payload.get(CODEX_TIMESTAMP_KEY),
        label=Locale.SESSION_META_PAYLOAD_LABEL,
    )
    response_timestamp = _timestamp(
        session_record.value.get(CODEX_TIMESTAMP_KEY),
        label=Locale.SESSION_META_RESPONSE_LABEL,
    )
    local_timestamp = datetime.fromisoformat(payload_timestamp.replace("Z", "+00:00")).astimezone(
        ZoneInfo(timezone_name)
    )
    rollout_timestamp = local_timestamp.strftime(ROLLOUT_TIMESTAMP_FORMAT)
    rollout_filename = (
        f"{ROLLOUT_FILENAME_PREFIX}{rollout_timestamp}-{session_id}{ROLLOUT_FILENAME_SUFFIX}"
    )
    if configured_rollout_basename is not None and rollout_filename != configured_rollout_basename:
        raise PushValidationError(Locale.SESSION_META_ROLLOUT_MISMATCH)

    turn_context_payload = next(
        (
            cast(dict[str, object], record.value[CODEX_PAYLOAD_KEY])
            for record in records
            if record.value.get(CODEX_TYPE_KEY) == CODEX_TURN_CONTEXT_TYPE
            and isinstance(record.value.get(CODEX_PAYLOAD_KEY), dict)
        ),
        None,
    )
    if turn_context_payload is None:
        raise PushValidationError(Locale.TURN_CONTEXT_MISSING)
    model = turn_context_payload.get(CODEX_MODEL_KEY)
    reasoning_effort = turn_context_payload.get(CODEX_REASONING_EFFORT_KEY)
    try:
        compact = CompactSessionMetadata.model_validate({
            CODEX_ORIGINATOR_KEY: payload.get(CODEX_ORIGINATOR_KEY),
            CODEX_SOURCE_KEY: payload.get(CODEX_SOURCE_KEY),
            CODEX_CLI_VERSION_KEY: payload.get(CODEX_CLI_VERSION_KEY),
            CODEX_MODEL_PROVIDER_KEY: payload.get(CODEX_MODEL_PROVIDER_KEY),
            CODEX_MODEL_KEY: model,
            SESSION_REASONING_EFFORT_KEY: reasoning_effort,
            CODEX_SESSION_ID_KEY: session_id,
            CODEX_TIMESTAMP_KEY: response_timestamp,
        })
    except ValidationError as exc:
        raise PushValidationError(Locale.SESSION_META_FIELDS_INCOMPLETE) from exc
    return SessionMetadata(
        session_id=session_id,
        timestamp=response_timestamp,
        rollout_filename=rollout_filename,
        compact=compact,
    )


def _eligible_fco_text(record: RolloutRecord, payload: Mapping[str, object]) -> str | None:
    output = payload.get(CODEX_OUTPUT_KEY)
    marker_start = f"{CODEX_CITE_MARKER_PREFIX}turn"
    if isinstance(output, list):
        contains_marker = any(
            isinstance(block, dict)
            and isinstance(block.get(CODEX_TEXT_KEY), str)
            and marker_start in cast(str, block[CODEX_TEXT_KEY])
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
        or output[0].get(CODEX_TYPE_KEY) != CODEX_INPUT_TEXT_TYPE
        or not isinstance(output[0].get(CODEX_TEXT_KEY), str)
    ):
        raise PushValidationError(
            Locale.CITED_OUTPUT_BLOCK_INVALID_TEMPLATE.format(line_number=record.line_number)
        )
    return cast(str, output[0][CODEX_TEXT_KEY])


def build_rollout_index(
    records: tuple[RolloutRecord, ...],
    *,
    timezone_name: str,
    configured_rollout_basename: str | None,
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
        payload = value.get(CODEX_PAYLOAD_KEY)
        if not isinstance(payload, dict):
            continue
        payload_type = payload.get(CODEX_TYPE_KEY)
        if (
            value.get(CODEX_TYPE_KEY) == CODEX_RESPONSE_ITEM_TYPE
            and payload_type == CODEX_FUNCTION_CALL_TYPE
            and payload.get(CODEX_NAMESPACE_KEY) == CODEX_WEB_NAMESPACE
            and payload.get(CODEX_NAME_KEY) == CODEX_WEB_FUNCTION_NAME
        ):
            call_id = payload.get(CODEX_CALL_ID_KEY)
            if not _valid_nonblank(call_id):
                raise PushValidationError(
                    Locale.WEB_CALL_ID_INVALID_TEMPLATE.format(line_number=record.line_number)
                )
            calls.setdefault(cast(str, call_id), []).append(record)
        elif (
            value.get(CODEX_TYPE_KEY) == CODEX_EVENT_MESSAGE_TYPE
            and payload_type == CODEX_WEB_SEARCH_END_TYPE
        ):
            call_id = payload.get(CODEX_CALL_ID_KEY)
            if not _valid_nonblank(call_id):
                raise PushValidationError(
                    Locale.WEB_EVENT_CALL_ID_INVALID_TEMPLATE.format(line_number=record.line_number)
                )
            events.setdefault(cast(str, call_id), []).append(record)
        elif (
            value.get(CODEX_TYPE_KEY) == CODEX_RESPONSE_ITEM_TYPE
            and payload_type == CODEX_FUNCTION_CALL_OUTPUT_TYPE
        ):
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
        call_id = output_payload.get(CODEX_CALL_ID_KEY)
        fco_id = output_payload.get(CODEX_ID_KEY)
        if not _valid_nonblank(call_id) or not _valid_nonblank(fco_id):
            raise PushValidationError(
                Locale.CITED_OUTPUT_IDS_INVALID_TEMPLATE.format(
                    line_number=output_record.line_number
                )
            )
        call_id = cast(str, call_id)
        fco_id = cast(str, fco_id)
        if call_id in seen_call_ids or fco_id in seen_fco_ids:
            raise PushValidationError(Locale.CITED_OUTPUT_IDS_DUPLICATE)
        seen_call_ids.add(call_id)
        seen_fco_ids.add(fco_id)
        fco_timestamp = _timestamp(
            output_record.value.get(CODEX_TIMESTAMP_KEY),
            label=Locale.FUNCTION_OUTPUT_LABEL_TEMPLATE.format(fco_id=fco_id),
        )

        matching_calls = calls.get(call_id, [])
        matching_events = events.get(call_id, [])
        if len(matching_calls) != 1 or len(matching_events) != 1:
            raise PushValidationError(Locale.CITED_WEB_CHAIN_COUNT_TEMPLATE.format(call_id=call_id))
        call_record = matching_calls[0]
        event_record = matching_events[0]
        if not (call_record.line_number < event_record.line_number < output_record.line_number):
            raise PushValidationError(Locale.CITED_WEB_CHAIN_ORDER_TEMPLATE.format(call_id=call_id))
        call_payload = cast(
            dict[str, object],
            call_record.value[CODEX_PAYLOAD_KEY],
        )
        fc_id = call_payload.get(CODEX_ID_KEY)
        if not _valid_nonblank(fc_id) or cast(str, fc_id) in seen_fc_ids:
            raise PushValidationError(
                Locale.WEB_CALL_FC_ID_INVALID_TEMPLATE.format(call_id=call_id)
            )
        fc_id = cast(str, fc_id)
        seen_fc_ids.add(fc_id)
        arguments = _web_arguments(call_payload, call_record.line_number)
        arguments_json = json.dumps(
            arguments,
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
        )
        fc_rows.append(
            CodexFcRow(
                timestamp=_timestamp(
                    call_record.value.get(CODEX_TIMESTAMP_KEY),
                    label=Locale.FUNCTION_CALL_LABEL_TEMPLATE.format(fc_id=fc_id),
                ),
                fc_id=fc_id,
                call_id=call_id,
                name=CODEX_WEB_FUNCTION_NAME,
                namespace=CODEX_WEB_NAMESPACE,
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
        event_payload = cast(
            dict[str, object],
            event_record.value[CODEX_PAYLOAD_KEY],
        )
        results = event_payload.get(CODEX_RESULTS_KEY)
        if not isinstance(results, list):
            raise PushValidationError(
                Locale.WEB_EVENT_RESULTS_UNSUPPORTED_TEMPLATE.format(call_id=call_id)
            )
        for section in sections:
            matching_results = [
                result
                for result in results
                if isinstance(result, dict)
                and result.get(CODEX_TYPE_KEY) == CODEX_TEXT_RESULT_TYPE
                and result.get(CODEX_REF_ID_KEY) == section.ref_id
            ]
            if len(matching_results) != 1:
                raise PushValidationError(
                    Locale.CITATION_RESULT_COUNT_TEMPLATE.format(ref_id=section.ref_id)
                )
            try:
                result = CodexTextResult.model_validate(matching_results[0])
            except ValidationError as exc:
                raise PushValidationError(
                    Locale.CITATION_RESULT_METADATA_UNSUPPORTED_TEMPLATE.format(
                        ref_id=section.ref_id
                    )
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


def _create_codex_schema(
    conn: duckdb.DuckDBPyConnection,
    *,
    codex_match_version: int = 1,
) -> None:
    for sequence in (
        CODEX_FC_ID_SEQUENCE,
        CODEX_FCO_ID_SEQUENCE,
        CODEX_CALLS_ID_SEQUENCE,
        CODEX_TURN_REF_ID_SEQUENCE,
        CODEX_EVIDENCE_AUDIT_ID_SEQUENCE,
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
        CREATE TABLE IF NOT EXISTS {CODEX_RETRY_BASELINE_TABLE} (
            {duckdb_quote_identifier(CODEX_RETRY_RUN_ID_COL)} VARCHAR PRIMARY KEY,
            {duckdb_quote_identifier(CODEX_RETRY_SOURCEKEY_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_RETRY_CREATED_AT_COL)} TIMESTAMPTZ NOT NULL,
            {duckdb_quote_identifier(CODEX_RETRY_BASELINE_COL)} JSON NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CODEX_EVIDENCE_AUDIT_TABLE} (
            {duckdb_quote_identifier(CODEX_EVIDENCE_AUDIT_ID_COL)}
                BIGINT PRIMARY KEY
                DEFAULT nextval('{CODEX_EVIDENCE_AUDIT_ID_SEQUENCE}'),
            {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)} VARCHAR NOT NULL UNIQUE,
            {duckdb_quote_identifier(CODEX_RETRY_RUN_ID_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_RETRY_SOURCEKEY_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_RETRY_CREATED_AT_COL)} TIMESTAMPTZ NOT NULL,
            {duckdb_quote_identifier(CODEX_EVIDENCE_SUBMISSION_COL)} JSON NOT NULL,
            {duckdb_quote_identifier(CODEX_EVIDENCE_ASSESSMENT_COL)} JSON NOT NULL,
            {duckdb_quote_identifier(CODEX_EVIDENCE_APPLIED_COL)} BOOLEAN NOT NULL,
            {duckdb_quote_identifier(CODEX_EVIDENCE_ACCEPTED_COL)} BOOLEAN NOT NULL
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
    if codex_match_version == 2:
        conn.execute(
            f"""
            CREATE OR REPLACE VIEW {CODEX_TURN_REF_NORMALIZED_VIEW} AS
            SELECT
                *,
                {normalized_tokens_sql(duckdb_quote_identifier(CODEX_CITE_TEXT_COL))}
                    AS {duckdb_quote_identifier(CODEX_CITE_TOKENS_COL)}
            FROM {CODEX_TURN_REF_TABLE}
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
                Locale.CUMULATIVE_ROW_CONFLICT_TEMPLATE.format(
                    table_name=table_name,
                    key_value=key_value,
                )
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
    *,
    codex_match_version: int = 1,
    manage_transaction: bool = True,
) -> None:
    if manage_transaction:
        conn.execute("BEGIN TRANSACTION")
    try:
        _create_codex_schema(
            conn,
            codex_match_version=codex_match_version,
        )
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
            raise PushValidationError(Locale.PROVENANCE_PREFIX_OLDER)
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
            raise PushValidationError(Locale.CITATION_PREFIX_OLDER)

        fc_by_call = {row.call_id: row for row in rollout_index.fc_rows}
        fco_by_call = {row.call_id: row for row in rollout_index.fco_rows}
        if set(fc_by_call) != current_call_ids or set(fco_by_call) != current_call_ids:
            raise PushValidationError(Locale.ROLLOUT_LINKAGES_INCOMPLETE)
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
            key_value = f"{turn_ref_row.call_id}{CUMULATIVE_KEY_SEPARATOR}{turn_ref_row.ref_id}"
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
                        Locale.CUMULATIVE_ROW_CONFLICT_TEMPLATE.format(
                            table_name=CODEX_TURN_REF_TABLE,
                            key_value=key_value,
                        )
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
                    Locale.PROVENANCE_INTEGRITY_QUERY_FAILED_TEMPLATE.format(table_name=table_name)
                )
            total, distinct = integrity_row
            if total != distinct:
                raise PushValidationError(
                    Locale.PROVENANCE_UNIQUENESS_FAILED_TEMPLATE.format(table_name=table_name)
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
            raise PushValidationError(Locale.PROVENANCE_LINKAGE_QUERY_FAILED)
        missing_fc_links, missing_fco_links, missing_call_links = linkage_row
        if missing_fc_links or missing_fco_links or missing_call_links:
            raise PushValidationError(Locale.PROVENANCE_RELATIONSHIPS_INCOMPLETE)

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
            raise PushValidationError(Locale.PROVENANCE_PREFIX_MISMATCH)
        if manage_transaction:
            conn.execute("COMMIT")
    except Exception:
        if manage_transaction:
            conn.execute("ROLLBACK")
        raise


def _render_fco_timestamp(value: datetime) -> str:
    return (
        value
        .astimezone(timezone.utc)
        .isoformat(timespec=FCO_TIMESTAMP_TIMESPEC)
        .replace("+00:00", "Z")
    )


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


def _exact_evidence_candidates(
    conn: duckdb.DuckDBPyConnection,
    *,
    rollout_filename: str,
    excerpt: str,
) -> tuple[EvidenceCandidate, ...]:
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
        [excerpt, rollout_filename, excerpt],
    ).fetchall()
    return _evidence_candidates(rows)


def _normalized_evidence_tokens(
    conn: duckdb.DuckDBPyConnection,
    excerpt: str,
) -> tuple[str, ...]:
    row = conn.execute(
        f"SELECT {normalized_tokens_sql('?')}",
        [excerpt],
    ).fetchone()
    if row is None or not isinstance(row[0], list):
        return ()
    return tuple(cast(list[str], row[0]))


def _near_evidence_candidates(
    conn: duckdb.DuckDBPyConnection,
    *,
    rollout_filename: str,
    url: str,
    submitted_tokens: tuple[str, ...],
) -> tuple[EvidenceCandidate, ...]:
    if not submitted_tokens:
        return ()
    rows = conn.execute(
        f"""
        WITH submitted(tokens) AS (VALUES (?)),
        candidate_rows AS (
            SELECT
                ts.{duckdb_quote_identifier(CODEX_ID_COL)},
                ts.{duckdb_quote_identifier(CODEX_REF_ID_COL)},
                ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)},
                ts.{duckdb_quote_identifier(CODEX_CITE_TEXT_COL)},
                list_position(
                    list_transform(
                        range(
                            1,
                            len(ts.{duckdb_quote_identifier(CODEX_CITE_TOKENS_COL)})
                                - len(submitted.tokens) + 2
                        ),
                        token_index -> list_slice(
                            ts.{duckdb_quote_identifier(CODEX_CITE_TOKENS_COL)},
                            token_index,
                            token_index + len(submitted.tokens) - 1
                        ) = submitted.tokens
                    ),
                    true
                ) AS excerpt_position,
                ts.{duckdb_quote_identifier(CODEX_REF_URL_COL)},
                fco.{duckdb_quote_identifier(CODEX_FCO_TIMESTAMP_COL)},
                fc.{duckdb_quote_identifier(CODEX_FC_ARGUMENTS_COL)}
            FROM {CODEX_TURN_REF_NORMALIZED_VIEW} ts
            CROSS JOIN submitted
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
              AND ts.{duckdb_quote_identifier(CODEX_REF_URL_COL)} = ?
        )
        SELECT
            {duckdb_quote_identifier(CODEX_REF_ID_COL)},
            {duckdb_quote_identifier(CODEX_CALL_ID_COL)},
            {duckdb_quote_identifier(CODEX_CITE_TEXT_COL)},
            excerpt_position,
            {duckdb_quote_identifier(CODEX_REF_URL_COL)},
            {duckdb_quote_identifier(CODEX_FCO_TIMESTAMP_COL)},
            {duckdb_quote_identifier(CODEX_FC_ARGUMENTS_COL)}
        FROM candidate_rows
        WHERE excerpt_position IS NOT NULL
        ORDER BY {duckdb_quote_identifier(CODEX_ID_COL)}
        """,
        [list(submitted_tokens), rollout_filename, url],
    ).fetchall()
    return _evidence_candidates(rows)


def _candidate_match(
    candidate: EvidenceCandidate,
    *,
    field: str,
    evidence_number: int,
    evidence: WebSearchExcerpt,
) -> EvidenceMatch:
    arguments_json = candidate.arguments_json
    if not isinstance(arguments_json, str):
        arguments_json = json.dumps(
            arguments_json,
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
        )
    return EvidenceMatch(
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


def assess_submission_evidence(
    conn: duckdb.DuckDBPyConnection,
    submission: SubmissionPayload,
    *,
    rollout_filename: str,
    codex_match_version: int,
) -> EvidenceAssessment:
    assessments: list[EvidenceItemAssessment] = []
    evidence_number = 0
    for field, field_submission in submission.evidence_items():
        for index, evidence in enumerate(field_submission.web_search_excerpts):
            evidence_number += 1
            if isinstance(evidence, EvidenceWithdrawal):
                assessments.append(
                    EvidenceItemAssessment(
                        field=field,
                        index=index,
                        evidence_number=evidence_number,
                        submission=evidence,
                        outcome=EVIDENCE_OUTCOME_WITHDRAWN,
                        match=None,
                    )
                )
                continue

            exact_candidates = _exact_evidence_candidates(
                conn,
                rollout_filename=rollout_filename,
                excerpt=evidence.excerpt,
            )
            exact_url_candidates = tuple(
                candidate for candidate in exact_candidates if candidate.url == evidence.url
            )
            if exact_url_candidates:
                if len(exact_url_candidates) > 1 and not ALLOW_MULTIPLE_EVIDENCE_MATCHES:
                    raise MultipleEvidenceMatches(evidence.excerpt)
                candidate = (
                    EVIDENCE_RANDOM.choice(exact_url_candidates)
                    if len(exact_url_candidates) > 1
                    else exact_url_candidates[0]
                )
                assessments.append(
                    EvidenceItemAssessment(
                        field=field,
                        index=index,
                        evidence_number=evidence_number,
                        submission=evidence,
                        outcome=EVIDENCE_OUTCOME_V1_EXACT,
                        match=_candidate_match(
                            candidate,
                            field=field,
                            evidence_number=evidence_number,
                            evidence=evidence,
                        ),
                        candidates=exact_url_candidates,
                    )
                )
                continue

            normalized_tokens: tuple[str, ...] = ()
            near_candidates: tuple[EvidenceCandidate, ...] = ()
            if codex_match_version == 2:
                normalized_tokens = _normalized_evidence_tokens(conn, evidence.excerpt)
                near_candidates = _near_evidence_candidates(
                    conn,
                    rollout_filename=rollout_filename,
                    url=evidence.url,
                    submitted_tokens=normalized_tokens,
                )
            assessments.append(
                EvidenceItemAssessment(
                    field=field,
                    index=index,
                    evidence_number=evidence_number,
                    submission=evidence,
                    outcome=(
                        EVIDENCE_OUTCOME_V2_NEAR if near_candidates else EVIDENCE_OUTCOME_UNMATCHED
                    ),
                    match=None,
                    normalized_tokens=normalized_tokens,
                    candidates=near_candidates or exact_candidates,
                )
            )
    return EvidenceAssessment(items=tuple(assessments))


def _retry_evidence_obligation(
    item: EvidenceItemAssessment,
) -> RetryEvidenceObligation:
    if isinstance(item.submission, WebSearchExcerpt):
        excerpt = item.submission.excerpt
        url = item.submission.url
    else:
        excerpt = None
        url = None
    return RetryEvidenceObligation(
        outcome=item.outcome,
        excerpt=excerpt,
        url=url,
        normalized_tokens=list(item.normalized_tokens),
    )


def _retry_obligations_from_assessment(
    submission: SubmissionPayload,
    assessment: EvidenceAssessment,
) -> RetryObligations:
    fields: dict[str, RetryFieldObligation] = {}
    for field, field_submission in submission.evidence_items():
        evidence = [
            _retry_evidence_obligation(item) for item in assessment.items if item.field == field
        ]
        fields[field] = RetryFieldObligation(
            value=field_submission.value,
            evidence=evidence,
            accepted=EVIDENCE_ITEMS_ACCEPTED_DEF(tuple(item.outcome for item in evidence)),
        )
    return RetryObligations(fields=fields)


def _assessment_audit(assessment: EvidenceAssessment) -> EvidenceAttemptAudit:
    items: list[EvidenceItemAudit] = []
    for item in assessment.items:
        if isinstance(item.submission, WebSearchExcerpt):
            excerpt = item.submission.excerpt
            url = item.submission.url
        else:
            excerpt = None
            url = None
        items.append(
            EvidenceItemAudit(
                field=item.field,
                index=item.index,
                outcome=item.outcome,
                excerpt=excerpt,
                url=url,
                normalized_tokens=list(item.normalized_tokens),
                candidates=[
                    EvidenceCandidateAudit(
                        ref_id=candidate.ref_id,
                        call_id=candidate.call_id,
                        cite_text=candidate.cite_text,
                        excerpt_position=candidate.excerpt_position,
                        url=candidate.url,
                    )
                    for candidate in item.candidates
                ],
            )
        )
    return EvidenceAttemptAudit(items=items)


def _log_evidence_assessment(
    assessment: EvidenceAssessment,
    *,
    attempt_id: str,
) -> None:
    for item in assessment.items:
        if isinstance(item.submission, WebSearchExcerpt):
            excerpt = item.submission.excerpt
            url = item.submission.url
        else:
            excerpt = None
            url = None
        candidate_diagnostics = tuple(
            (
                candidate.ref_id,
                candidate.call_id,
                candidate.cite_text,
                candidate.excerpt_position,
                candidate.url,
            )
            for candidate in item.candidates
        )
        logger.info(
            Locale.EVIDENCE_ITEM_ASSESSMENT_LOG,
            attempt_id,
            item.field,
            item.index,
            item.outcome,
            excerpt,
            url,
            candidate_diagnostics,
        )


def _assessment_public_detail(
    assessment: EvidenceAssessment,
    *,
    violations: Sequence[str] = (),
    include_retry_contract: bool = False,
) -> str:
    total = len(assessment.items)
    outcomes = tuple(item.outcome for item in assessment.items)
    progress_template = (
        Locale.EVIDENCE_GOOD_PROGRESS_TEMPLATE
        if EVIDENCE_PROGRESS_PRAISE_DEF(outcomes)
        else Locale.EVIDENCE_PROGRESS_TEMPLATE
    )
    lines = [
        progress_template.format(
            verified=assessment.exact_count,
            total=total,
        ),
        Locale.EVIDENCE_REVIEW_HEADER,
    ]
    for item in assessment.items:
        location = EVIDENCE_LOCATION_DEF(item.field, item.index)
        if item.outcome == EVIDENCE_OUTCOME_V2_NEAR:
            lines.append(Locale.EVIDENCE_NEAR_ITEM_TEMPLATE.format(location=location))
        elif item.outcome == EVIDENCE_OUTCOME_UNMATCHED:
            lines.append(Locale.EVIDENCE_UNMATCHED_ITEM_TEMPLATE.format(location=location))
        elif item.outcome == EVIDENCE_OUTCOME_WITHDRAWN:
            lines.append(Locale.EVIDENCE_WITHDRAWN_ITEM_TEMPLATE.format(location=location))
    lines.extend(violations)
    lines.append(Locale.EVIDENCE_RETRY_INSTRUCTION)
    if include_retry_contract:
        lines.append(RETRY_SUBMISSION_PUBLIC_GUIDANCE)
    return "\n".join(lines)


def _obligation_item_is_unchanged(
    previous: RetryEvidenceObligation,
    current: EvidenceSubmission,
) -> bool:
    if previous.outcome == EVIDENCE_OUTCOME_V1_EXACT:
        return (
            isinstance(current, WebSearchExcerpt)
            and current.excerpt == previous.excerpt
            and current.url == previous.url
        )
    return previous.outcome == EVIDENCE_OUTCOME_WITHDRAWN and isinstance(
        current, EvidenceWithdrawal
    )


def _apply_retry_obligations(
    conn: duckdb.DuckDBPyConnection,
    submission: StandardizedSubmission,
    assessment: EvidenceAssessment,
    previous: RetryObligations,
) -> tuple[RetryObligations, tuple[str, ...]]:
    next_fields: dict[str, RetryFieldObligation] = {}
    violations: list[str] = []
    assessed_items = {(item.field, item.index): item for item in assessment.items}
    for field, field_submission in submission.evidence_items():
        previous_field = previous.fields[field]
        current_evidence = field_submission.web_search_excerpts
        if previous_field.accepted:
            unchanged = (
                field_submission.value == previous_field.value
                and len(current_evidence) == len(previous_field.evidence)
                and all(
                    _obligation_item_is_unchanged(previous_item, current_item)
                    for previous_item, current_item in zip(
                        previous_field.evidence,
                        current_evidence,
                        strict=True,
                    )
                )
            )
            if not unchanged:
                violations.append(
                    Locale.EVIDENCE_ACCEPTED_FIELD_IMMUTABLE_TEMPLATE.format(immutable=field)
                )
            next_fields[field] = previous_field
            continue

        if len(current_evidence) < len(previous_field.evidence):
            violations.append(Locale.EVIDENCE_COUNT_DECREASED_TEMPLATE.format(field=field))

        next_evidence: list[RetryEvidenceObligation] = []
        withdrew_item = False
        for index, previous_item in enumerate(previous_field.evidence):
            if index >= len(current_evidence):
                next_evidence.append(previous_item)
                continue
            current_item = current_evidence[index]
            assessment_item = assessed_items[(field, index)]
            location = EVIDENCE_LOCATION_DEF(field, index)
            if previous_item.outcome == EVIDENCE_OUTCOME_V1_EXACT:
                if not _obligation_item_is_unchanged(previous_item, current_item):
                    violations.append(
                        Locale.EVIDENCE_EXACT_IMMUTABLE_TEMPLATE.format(immutable=location)
                    )
                next_evidence.append(previous_item)
                continue
            if previous_item.outcome == EVIDENCE_OUTCOME_V2_NEAR:
                if isinstance(current_item, EvidenceWithdrawal):
                    violations.append(
                        Locale.EVIDENCE_WITHDRAWAL_NOT_ALLOWED_TEMPLATE.format(location=location)
                    )
                    next_evidence.append(previous_item)
                    continue
                current_tokens = assessment_item.normalized_tokens
                if assessment_item.outcome == EVIDENCE_OUTCOME_V1_EXACT:
                    current_tokens = _normalized_evidence_tokens(
                        conn,
                        current_item.excerpt,
                    )
                if (
                    current_item.url != previous_item.url
                    or list(current_tokens) != previous_item.normalized_tokens
                ):
                    violations.append(
                        Locale.EVIDENCE_MINOR_CHANGE_ONLY_TEMPLATE.format(location=location)
                    )
                    next_evidence.append(previous_item)
                    continue
                if assessment_item.outcome not in {
                    EVIDENCE_OUTCOME_V1_EXACT,
                    EVIDENCE_OUTCOME_V2_NEAR,
                }:
                    violations.append(
                        Locale.EVIDENCE_MINOR_CHANGE_ONLY_TEMPLATE.format(location=location)
                    )
                    next_evidence.append(previous_item)
                    continue
                next_evidence.append(_retry_evidence_obligation(assessment_item))
                continue
            if previous_item.outcome == EVIDENCE_OUTCOME_UNMATCHED:
                if isinstance(current_item, EvidenceWithdrawal):
                    withdrew_item = True
                next_evidence.append(_retry_evidence_obligation(assessment_item))
                continue
            if not isinstance(current_item, EvidenceWithdrawal):
                violations.append(
                    Locale.EVIDENCE_WITHDRAWAL_NOT_ALLOWED_TEMPLATE.format(location=location)
                )
            next_evidence.append(previous_item)

        for index in range(len(previous_field.evidence), len(current_evidence)):
            assessment_item = assessed_items[(field, index)]
            if isinstance(assessment_item.submission, EvidenceWithdrawal):
                violations.append(Locale.EVIDENCE_WITHDRAWAL_WITHOUT_BASELINE)
            next_evidence.append(_retry_evidence_obligation(assessment_item))

        if withdrew_item and field_submission.value == previous_field.value:
            violations.append(
                Locale.EVIDENCE_WITHDRAWAL_VALUE_UNCHANGED_TEMPLATE.format(field=field)
            )
        next_fields[field] = RetryFieldObligation(
            value=field_submission.value,
            evidence=next_evidence,
            accepted=EVIDENCE_ITEMS_ACCEPTED_DEF(tuple(item.outcome for item in next_evidence)),
        )
    return RetryObligations(fields=next_fields), tuple(violations)


def _assessment_from_audit(
    submission: StandardizedSubmission,
    audit: EvidenceAttemptAudit,
) -> EvidenceAssessment:
    submission_fields = dict(submission.evidence_items())
    items: list[EvidenceItemAssessment] = []
    for evidence_number, audit_item in enumerate(audit.items, start=1):
        evidence = submission_fields[audit_item.field].web_search_excerpts[audit_item.index]
        items.append(
            EvidenceItemAssessment(
                field=audit_item.field,
                index=audit_item.index,
                evidence_number=evidence_number,
                submission=evidence,
                outcome=audit_item.outcome,
                match=None,
                normalized_tokens=tuple(audit_item.normalized_tokens),
            )
        )
    return EvidenceAssessment(items=tuple(items))


def _derive_retry_obligations(
    conn: duckdb.DuckDBPyConnection,
    *,
    baseline_json: str,
    baseline_attempt_id: str,
    run_id: str,
) -> RetryObligations:
    try:
        obligations = RetryObligations.model_validate_json(baseline_json)
        rows = conn.execute(
            f"""
            SELECT
                {duckdb_quote_identifier(CODEX_EVIDENCE_SUBMISSION_COL)},
                {duckdb_quote_identifier(CODEX_EVIDENCE_ASSESSMENT_COL)}
            FROM {CODEX_EVIDENCE_AUDIT_TABLE}
            WHERE {duckdb_quote_identifier(CODEX_RETRY_RUN_ID_COL)} = ?
              AND {duckdb_quote_identifier(CODEX_EVIDENCE_APPLIED_COL)}
              AND {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)} <> ?
            ORDER BY {duckdb_quote_identifier(CODEX_EVIDENCE_AUDIT_ID_COL)}
            """,
            [run_id, baseline_attempt_id],
        ).fetchall()
        for submission_json, assessment_json in rows:
            submission = StandardizedSubmission.model_validate_json(cast(str, submission_json))
            assessment = _assessment_from_audit(
                submission,
                EvidenceAttemptAudit.model_validate_json(cast(str, assessment_json)),
            )
            obligations, violations = _apply_retry_obligations(
                conn,
                submission,
                assessment,
                obligations,
            )
            if violations:
                raise PushConfigurationError(Locale.EVIDENCE_AUDIT_REPLAY_FAILED)
        return obligations
    except (IndexError, KeyError, ValidationError) as exc:
        raise PushConfigurationError(Locale.EVIDENCE_AUDIT_REPLAY_FAILED) from exc


def _process_retry_attempt(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: UUID,
    source_key: str,
    session_id: str,
    attempt_id: str,
    attempt_timestamp: datetime,
    submission: SubmissionPayload,
    assessment: EvidenceAssessment,
    manage_transaction: bool = True,
) -> tuple[str, ...]:
    run_id_text = str(run_id)
    initial_obligations = _retry_obligations_from_assessment(
        submission,
        assessment,
    )
    submission_json = submission.model_dump_json(by_alias=True)
    assessment_json = _assessment_audit(assessment).model_dump_json()
    if manage_transaction:
        conn.execute("BEGIN TRANSACTION")
    try:
        inserted_baseline = False
        if not assessment.accepted:
            inserted_baseline = (
                conn.execute(
                    f"""
                    INSERT INTO {CODEX_RETRY_BASELINE_TABLE} (
                        {duckdb_quote_identifier(CODEX_RETRY_RUN_ID_COL)},
                        {duckdb_quote_identifier(CODEX_RETRY_SOURCEKEY_COL)},
                        {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)},
                        {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)},
                        {duckdb_quote_identifier(CODEX_RETRY_CREATED_AT_COL)},
                        {duckdb_quote_identifier(CODEX_RETRY_BASELINE_COL)}
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    RETURNING {duckdb_quote_identifier(CODEX_RETRY_RUN_ID_COL)}
                    """,
                    [
                        run_id_text,
                        source_key,
                        session_id,
                        attempt_id,
                        attempt_timestamp,
                        initial_obligations.model_dump_json(),
                    ],
                ).fetchone()
                is not None
            )

        baseline_row = conn.execute(
            f"""
            SELECT
                {duckdb_quote_identifier(CODEX_RETRY_SOURCEKEY_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_BASELINE_COL)}
            FROM {CODEX_RETRY_BASELINE_TABLE}
            WHERE {duckdb_quote_identifier(CODEX_RETRY_RUN_ID_COL)} = ?
            """,
            [run_id_text],
        ).fetchone()

        violations: tuple[str, ...] = ()
        if baseline_row is not None:
            (
                baseline_source_key,
                baseline_session_id,
                baseline_attempt_id,
                baseline_json,
            ) = baseline_row
            if baseline_source_key != source_key or baseline_session_id != session_id:
                raise PushValidationError(Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH)
            if inserted_baseline:
                obligations = initial_obligations
                violations = tuple(
                    Locale.EVIDENCE_WITHDRAWAL_WITHOUT_BASELINE
                    for item in assessment.items
                    if item.outcome == EVIDENCE_OUTCOME_WITHDRAWN
                )
            else:
                obligations = _derive_retry_obligations(
                    conn,
                    baseline_json=cast(str, baseline_json),
                    baseline_attempt_id=cast(str, baseline_attempt_id),
                    run_id=run_id_text,
                )
                if not isinstance(submission, StandardizedSubmission):
                    raise PushConfigurationError(Locale.EVIDENCE_AUDIT_REPLAY_FAILED)
                _next_obligations, violations = _apply_retry_obligations(
                    conn,
                    submission,
                    assessment,
                    obligations,
                )

        applied = not violations
        accepted = assessment.accepted and applied
        conn.execute(
            f"""
            INSERT INTO {CODEX_EVIDENCE_AUDIT_TABLE} (
                {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_RUN_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_SOURCEKEY_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_CREATED_AT_COL)},
                {duckdb_quote_identifier(CODEX_EVIDENCE_SUBMISSION_COL)},
                {duckdb_quote_identifier(CODEX_EVIDENCE_ASSESSMENT_COL)},
                {duckdb_quote_identifier(CODEX_EVIDENCE_APPLIED_COL)},
                {duckdb_quote_identifier(CODEX_EVIDENCE_ACCEPTED_COL)}
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                attempt_id,
                run_id_text,
                source_key,
                session_id,
                attempt_timestamp,
                submission_json,
                assessment_json,
                applied,
                accepted,
            ],
        )
        if manage_transaction:
            conn.execute("COMMIT")
        return violations
    except Exception:
        if manage_transaction:
            conn.execute("ROLLBACK")
        raise


def _retry_baseline_exists(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: UUID,
    source_key: str,
    session_id: str,
) -> bool:
    row = conn.execute(
        f"""
        SELECT
            {duckdb_quote_identifier(CODEX_RETRY_SOURCEKEY_COL)},
            {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)}
        FROM {CODEX_RETRY_BASELINE_TABLE}
        WHERE {duckdb_quote_identifier(CODEX_RETRY_RUN_ID_COL)} = ?
        """,
        [str(run_id)],
    ).fetchone()
    if row is None:
        return False
    if row != (source_key, session_id):
        raise PushValidationError(Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH)
    return True


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
        rows_by_ref.setdefault(cast(str, ref_id), set()).add((cast(str, call_id), cast(str, url)))
    return {
        ref_id: next(iter(ref_rows))[1]
        for ref_id, ref_rows in rows_by_ref.items()
        if len(ref_rows) == 1
    }


def validate_submission_evidence(
    conn: duckdb.DuckDBPyConnection,
    submission: SubmissionPayload,
    *,
    rollout_filename: str,
    codex_match_version: int = 1,
) -> ValidatedEvidence:
    assessment = assess_submission_evidence(
        conn,
        submission,
        rollout_filename=rollout_filename,
        codex_match_version=codex_match_version,
    )
    if assessment.accepted:
        return assessment.validated
    failed = next(item for item in assessment.items if item.outcome != EVIDENCE_OUTCOME_V1_EXACT)
    if isinstance(failed.submission, EvidenceWithdrawal):
        raise PushValidationError(Locale.EVIDENCE_WITHDRAWAL_WITHOUT_BASELINE)
    detail_template = (
        Locale.EVIDENCE_URL_MISMATCH_TEMPLATE
        if failed.candidates
        else Locale.EVIDENCE_NO_MATCH_TEMPLATE
    )
    raise PushValidationError(
        detail_template.format(
            field=failed.field,
            excerpt=failed.submission.excerpt,
            url=failed.submission.url,
        )
    )


def source_rows() -> Iterator[dict[str, object]]:
    try:
        source = SOURCE_FILE.open(encoding=TEXT_ENCODING)
    except OSError as exc:
        raise RuntimeError(
            Locale.SOURCE_OPEN_FAILED_TEMPLATE.format(
                source_file=SOURCE_FILE,
                error=exc,
            )
        ) from exc

    with source:
        for line_number, line in enumerate(source, start=1):
            try:
                value: object = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    Locale.SOURCE_JSON_INVALID_TEMPLATE.format(
                        source_file=SOURCE_FILE,
                        line_number=line_number,
                    )
                ) from exc

            if not isinstance(value, dict):
                raise RuntimeError(
                    Locale.SOURCE_ROW_NON_OBJECT_TEMPLATE.format(
                        source_file=SOURCE_FILE,
                        line_number=line_number,
                    )
                )

            yield cast(dict[str, object], value)


def select_columns(row: Mapping[str, object]) -> dict[str, object]:
    missing = [column for column in DOCX_COLUMNS if column not in row]

    if missing:
        raise RuntimeError(Locale.TARGET_ROW_KEYS_MISSING_TEMPLATE.format(keys=", ".join(missing)))

    return {column: row[column] for column in DOCX_COLUMNS}


def json_line(row: Mapping[str, object]) -> str:
    return (
        json.dumps(
            row,
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
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
                raise RuntimeError(Locale.TARGET_ROW_IDENTITY_MISSING)
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

    raise PushValidationError(Locale.TARGET_GROUND_TRUTH_MISSING)


def selected_task_identity() -> tuple[str, str]:
    for row in source_rows():
        if (
            row.get(DRAW_NUMBER_COLUMN) == TARGET_DRAW_NUMBER
            and row.get(FRAGMENT_TYPE_COLUMN) == DOCX_ROW_FRAGMENT_TYPE
        ):
            first_name = row.get(KTP_FIRST_NAME_COL)
            last_name = row.get(KTP_LAST_NAME_COL)
            if not _valid_nonblank(first_name) or not _valid_nonblank(last_name):
                raise PushValidationError(Locale.TASK_IDENTITY_INCOMPLETE)
            return cast(str, first_name), cast(str, last_name)
    raise PushValidationError(Locale.TASK_IDENTITY_MISSING)


def _atomic_write_text(path: Path, value: str) -> None:
    temporary = path.with_name(
        ATOMIC_TEMP_FILENAME_TEMPLATE.format(
            filename=path.name,
            nonce=uuid4().hex,
        )
    )
    try:
        with temporary.open("x", encoding=TEXT_ENCODING) as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def archive_http_request_log(
    attempt_dir: Path,
    attempt_id: str,
    *,
    request: Request,
    request_body: bytes,
    response_code: int,
    response_headers: Mapping[str, str],
    response_body: str,
    started_ns: int,
) -> ArchivedFile:
    log_path = attempt_dir / HTTP_REQUEST_LOG_FILENAME_TEMPLATE.format(attempt_id=attempt_id)
    if log_path.exists():
        raise PushValidationError(Locale.ATTEMPT_HTTP_LOG_EXISTS)
    record = HttpRequestLogRecord(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
        method=HTTP_POST_METHOD,
        scheme=request.url.scheme,
        host=request.url.hostname or "",
        path=request.url.path,
        query=request.url.query,
        request_headers=dict(request.headers),
        request_body=request_body.decode(TEXT_ENCODING),
        response_code=response_code,
        response_headers=dict(response_headers),
        response_body=response_body,
        received_at_unix_usec=time.time_ns() // NANOSECONDS_PER_MICROSECOND,
        duration_usec=(time.monotonic_ns() - started_ns) // NANOSECONDS_PER_MICROSECOND,
    )
    append_http_request_log_record(log_path=log_path, record=record)
    _fsync_file(log_path)
    _fsync_directory(log_path.parent)
    return _archived_file(log_path)


def http_error_response_body(detail: str) -> str:
    return json.dumps(
        {"detail": detail},
        ensure_ascii=False,
        separators=COMPACT_JSON_SEPARATORS,
    )


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
    http_request_log_archive: ArchivedFile | None = None,
    run_id: UUID | None = None,
    source_key: str | None = None,
    session_id: str | None = None,
    rollout_relative_path: PurePosixPath | None = None,
) -> str:
    artifacts = {}
    for name, artifact in (
        (ARTIFACT_ROLLOUT_KEY, rollout_archive),
        (ARTIFACT_WORKBOOK_KEY, workbook_archive),
        (ARTIFACT_APPENDWATCH_REPORT_KEY, report_archive),
        (ARTIFACT_CARD_ZIP_KEY, card_archive),
        (ARTIFACT_HTTP_REQUEST_LOG_KEY, http_request_log_archive),
    ):
        if artifact is not None:
            artifacts[name] = {
                ARTIFACT_FILENAME_KEY: artifact.path.name,
                ARTIFACT_SIZE_KEY: artifact.size,
                ARTIFACT_SHA256_KEY: artifact.sha256,
            }
            if name == ARTIFACT_ROLLOUT_KEY:
                artifacts[name][ARTIFACT_LINE_COUNT_KEY] = artifact.line_count
    value = {
        ATTEMPT_ID_KEY: attempt_id,
        ATTEMPT_STAGE_KEY: stage,
        ATTEMPT_RESULT_KEY: result,
        ATTEMPT_UPDATED_AT_KEY: datetime.now(timezone.utc).isoformat(),
        ATTEMPT_ARTIFACTS_KEY: artifacts,
    }
    if run_id is not None:
        value[ATTEMPT_RUN_ID_KEY] = str(run_id)
    if source_key is not None:
        value[ATTEMPT_SOURCE_KEY] = source_key
    if session_id is not None:
        value[ATTEMPT_SESSION_ID_KEY] = session_id
    if rollout_relative_path is not None:
        value[ATTEMPT_ROLLOUT_RELATIVE_PATH_KEY] = str(rollout_relative_path)
    manifest_text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    _atomic_write_text(
        attempt_dir / ATTEMPT_MANIFEST_FILENAME,
        manifest_text,
    )
    return manifest_text


def open_source_database(
    runtime: RuntimeConfiguration,
) -> duckdb.DuckDBPyConnection:
    try:
        return duckdb.connect(str(runtime.pipeline.db_file), read_only=True)
    except duckdb.Error as exc:
        raise PushValidationError(Locale.SOURCE_DUCKDB_OPEN_FAILED) from exc


def open_detour_database(
    runtime: RuntimeConfiguration,
) -> duckdb.DuckDBPyConnection:
    conn: duckdb.DuckDBPyConnection | None = None
    try:
        runtime.detour_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(runtime.detour_db_path))
        if runtime.pipeline.match_rule_version.codex_match == 2:
            load_duckdb_extension(
                conn,
                CODEX_TOKEN_EXTENSION,
                runtime.pipeline.duckdb_extensions.get(CODEX_TOKEN_EXTENSION),
                log=None,
            )
        return conn
    except (OSError, RuntimeError, duckdb.Error) as exc:
        if conn is not None:
            conn.close()
        raise PushValidationError(Locale.DETOUR_DUCKDB_OPEN_FAILED) from exc


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
        raise PushValidationError(
            Locale.SOURCE_DUCKDB_TABLE_MISSING_TEMPLATE.format(table_name=table_name)
        ) from exc
    if len(rows) > 1:
        raise PushValidationError(
            Locale.SANCTIONED_ROWS_DUPLICATE_TEMPLATE.format(table_name=table_name)
        )
    if not rows:
        return ()
    (innerdict_jsonlines,) = rows[0]
    try:
        return _innerdict_json_rows(
            innerdict_jsonlines,
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
        raise PushValidationError(Locale.SANCTIONED_SOURCE_INELIGIBLE)
    try:
        name_key = NameKey.from_json_key(source_key)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise PushValidationError(Locale.SANCTIONED_SOURCE_MALFORMED) from exc
    if name_key.to_json_key() != source_key:
        raise PushValidationError(Locale.SANCTIONED_SOURCE_NONCANONICAL)

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
        raise PushValidationError(Locale.SANCTIONED_XLSX_CONTEXT_MISSING)
    draw_numbers = tuple(
        sorted(
            {
                str(row[DRAW_LABEL]).strip()
                for row in (*xlsx_rows, *docx_rows, *ssn_rows)
                if row.get(DRAW_LABEL) is not None and str(row[DRAW_LABEL]).strip()
            },
            key=_draw_sort_key,
        )
    )
    if not draw_numbers:
        raise PushValidationError(Locale.SANCTIONED_DRAW_MISSING)
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
    required_columns = tuple(
        column for column in DOCX_COLUMNS if column not in KTP_DOCX_OPTIONAL_EMPTY_COLS
    )
    complete_rows = [
        row
        for row in researcher.docx_rows
        if all(column in row and bool(str(row[column]).strip()) for column in required_columns)
    ]
    if not complete_rows:
        raise PushValidationError(Locale.GROUND_TRUTH_DOCX_INCOMPLETE)
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
        raise PushValidationError(Locale.RESEARCHER_NOT_UNIQUE)
    source_key, draw_number, first_name, last_name = rows[0]
    return ResearcherContext(
        source_key=cast(str, source_key),
        draw_number=str(draw_number),
        first_name=cast(str, first_name),
        last_name=cast(str, last_name),
    )


def render_codex_values(
    submission: StandardizedSubmission,
    evidence: ValidatedEvidence,
    *,
    attempt_timestamp: datetime,
    argument_ref_urls: Mapping[str, str],
) -> dict[str, str | None]:
    rendered: dict[str, str | None] = {}
    ordered_matches: list[EvidenceMatch] = []
    standardized_columns = dict(AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS)
    for column, field_submission in submission.evidence_items():
        matches = evidence[column]
        ordered_matches.extend(matches)
        rendered[column] = codex_parse.render_ai_value(
            field_submission.value,
            tuple(match.evidence_number for match in matches),
        )
        standardized_value = field_submission.model_dump(mode="json")[STANDARDIZED_VALUE_FIELD]
        rendered[standardized_columns[column]] = json.dumps(
            standardized_value,
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
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
        raise PushValidationError(Locale.ACCEPTED_IDENTITY_DUPLICATE) from exc
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
    selected = OuterDict(
        data={
            name_key.to_json_key(): [
                inner.model_copy(deep=True)
                for inner in outer_dict.get_inner_by_key(name_key.to_json_key())
            ]
        }
    )
    for inner_dicts in selected.values():
        for inner in inner_dicts:
            for column in AI_AUGMENT_STANDARDIZED_COLUMNS:
                value = inner.data.get(column)
                if not isinstance(value, str):
                    continue
                try:
                    decoded = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if decoded is None or (
                    isinstance(decoded, str) and decoded in AI_AUGMENT_CARD_EMPTY_VALUE_PLACEHOLDERS
                ):
                    inner.data[column] = None
    return selected


def _standardized_initial_submission(
    submission: Submission,
) -> StandardizedSubmission:
    payload = submission.model_dump(by_alias=True, mode="json")
    for column, standardized_value in INITIAL_STANDARDIZED_VALUES.items():
        field_payload = cast(dict[str, object], payload[column])
        field_payload[STANDARDIZED_VALUE_FIELD] = (
            standardized_value.model_dump(mode="json")
            if isinstance(standardized_value, BaseModel)
            else standardized_value
        )
    return StandardizedSubmission.model_validate(payload)


def write_accepted_submission(
    detour_conn: duckdb.DuckDBPyConnection,
    source_conn: duckdb.DuckDBPyConnection,
    runtime: RuntimeConfiguration,
    *,
    submission: StandardizedSubmission,
    evidence: ValidatedEvidence,
    researcher: ResearcherContext,
    rollout_index: RolloutIndex,
    rollout_archive: ArchivedFile,
    attempt_dir: Path,
    attempt_id: str,
    attempt_timestamp: datetime,
    source_researcher: SourceResearcher | None = None,
    manage_transaction: bool = True,
    materialize_files: bool = True,
) -> tuple[tuple[str, ...], ArchivedFile | None]:
    normalized_submission = submission.normalized_values()
    response_path = attempt_dir / RESPONSE_FILENAME
    zip_name = CARD_ZIP_FILENAME_TEMPLATE.format(
        prefix=CARD_ZIP_PREFIX,
        attempt_id=attempt_id,
    )
    zip_path = runtime.pipeline.output_dir / zip_name
    if materialize_files and zip_path.exists():
        raise PushValidationError(Locale.ATTEMPT_CARD_ZIP_EXISTS)

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

    if manage_transaction:
        detour_conn.execute("BEGIN TRANSACTION")
    try:
        append_codex_output(detour_conn, output_row)
        submitted_line = json_line(normalized_submission)
        truth = (
            ground_truth()
            if source_researcher is None
            else ground_truth_for_researcher(source_researcher)
        )
        response_lines = (submitted_line,) if truth is None else (submitted_line, json_line(truth))
        if materialize_files:
            outer_dict = selected_card_outer_dict(source_conn, detour_conn, researcher)
            intro_date = attempt_timestamp.astimezone(ZoneInfo(runtime.pipeline.timezone)).strftime(
                Locale.CARD_INTRO_DATE_FORMAT
            )
            cards = build_cards(
                outer_dict,
                total_draws=runtime.pipeline.total_draws,
                intro=CARD_INTRODUCTION.format(intro_date),
                excluded_cols=CARD_EXCLUDED_COLUMNS,
            )
            if len(cards) != 1:
                raise PushValidationError(Locale.RESEARCHER_CARD_COUNT_INVALID)
            write_cards_zip(
                cards,
                runtime.pipeline.output_dir,
                zip_name,
                output_format=runtime.pipeline.output_format,
                reference_docx=runtime.pipeline.pandoc_reference_docx,
            )
            _atomic_write_text(response_path, "".join(response_lines))
        if manage_transaction:
            detour_conn.execute("COMMIT")
    except Exception:
        if manage_transaction:
            detour_conn.execute("ROLLBACK")
        if materialize_files:
            response_path.unlink(missing_ok=True)
            zip_path.unlink(missing_ok=True)
        raise
    return response_lines, _archived_file(zip_path) if materialize_files else None


def execute_attempt(
    detour_conn: duckdb.DuckDBPyConnection,
    runtime: RuntimeConfiguration,
    replay: AttemptReplayInput,
) -> AttemptExecution:
    source_conn: duckdb.DuckDBPyConnection | None = None
    retry_submission_expected = False
    session_id = replay.session_id
    source_key = replay.source_key
    stage = ATTEMPT_STAGE_APPENDWATCH_VALIDATION
    try:
        parse_appendwatch_report(
            replay.report_archive.path,
            replay.rollout_relative_path,
        )
        stage = ATTEMPT_STAGE_ROLLOUT_INDEX
        rollout_index = build_rollout_index(
            parse_rollout(replay.rollout_archive.path),
            timezone_name=runtime.pipeline.timezone,
            configured_rollout_basename=replay.rollout_relative_path.name,
        )
        if session_id is not None and rollout_index.session.session_id != session_id:
            raise PushValidationError(Locale.SANCTIONED_SESSION_MISMATCH)
        session_id = rollout_index.session.session_id
        persist_rollout_index(
            detour_conn,
            rollout_index,
            codex_match_version=runtime.pipeline.match_rule_version.codex_match,
            manage_transaction=False,
        )

        stage = ATTEMPT_STAGE_PYDANTIC_VALIDATION
        if replay.run_id is not None:
            if source_key is None or replay.session_id is None:
                raise PushConfigurationError(Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH)
            retry_submission_expected = _retry_baseline_exists(
                detour_conn,
                run_id=replay.run_id,
                source_key=source_key,
                session_id=replay.session_id,
            )
        submission: SubmissionPayload = (
            StandardizedSubmission.model_validate_json(replay.request_body)
            if retry_submission_expected
            else Submission.model_validate_json(replay.request_body)
        )

        stage = ATTEMPT_STAGE_EVIDENCE_VALIDATION
        _seed_evidence_random(runtime.pipeline.sample_seed)
        evidence_assessment = assess_submission_evidence(
            detour_conn,
            submission,
            rollout_filename=rollout_index.session.rollout_filename,
            codex_match_version=runtime.pipeline.match_rule_version.codex_match,
        )
        _log_evidence_assessment(
            evidence_assessment,
            attempt_id=replay.attempt_id,
        )
        retry_violations: tuple[str, ...] = ()
        if replay.run_id is not None:
            assert source_key is not None
            assert replay.session_id is not None
            retry_violations = _process_retry_attempt(
                detour_conn,
                run_id=replay.run_id,
                source_key=source_key,
                session_id=replay.session_id,
                attempt_id=replay.attempt_id,
                attempt_timestamp=replay.attempt_timestamp,
                submission=submission,
                assessment=evidence_assessment,
                manage_transaction=False,
            )
        elif any(item.outcome == EVIDENCE_OUTCOME_WITHDRAWN for item in evidence_assessment.items):
            retry_violations = (Locale.EVIDENCE_WITHDRAWAL_WITHOUT_BASELINE,)
        if not evidence_assessment.accepted or retry_violations:
            raise EvidenceAssessmentError(
                Locale.EVIDENCE_SUBMISSION_REJECTED,
                public_detail=_assessment_public_detail(
                    evidence_assessment,
                    violations=retry_violations,
                    include_retry_contract=(replay.run_id is not None),
                ),
            )
        accepted_submission = (
            submission
            if isinstance(submission, StandardizedSubmission)
            else _standardized_initial_submission(submission)
        )

        stage = ATTEMPT_STAGE_RESEARCHER_RESOLUTION
        source_conn = open_source_database(runtime)
        source_researcher: SourceResearcher | None = None
        if source_key is None:
            first_name, last_name = selected_task_identity()
            researcher = resolve_researcher(
                source_conn,
                first_name=first_name,
                last_name=last_name,
            )
            source_key = researcher.source_key
        else:
            source_researcher = load_source_researcher(
                source_conn,
                runtime,
                source_key=source_key,
            )
            researcher = researcher_context(source_researcher)

        stage = ATTEMPT_STAGE_CARD
        response_lines, card_archive = write_accepted_submission(
            detour_conn,
            source_conn,
            runtime,
            submission=accepted_submission,
            evidence=evidence_assessment.validated,
            researcher=researcher,
            rollout_index=rollout_index,
            rollout_archive=replay.rollout_archive,
            attempt_dir=replay.attempt_dir,
            attempt_id=replay.attempt_id,
            attempt_timestamp=replay.attempt_timestamp,
            source_researcher=source_researcher,
            manage_transaction=False,
            materialize_files=replay.materialize_files,
        )
        response_body = "".join(response_lines)
        return AttemptExecution(
            stage=ATTEMPT_STAGE_ACCEPTED,
            result=ATTEMPT_RESULT_ACCEPTED,
            response_code=status.HTTP_200_OK,
            response_body=response_body,
            response_detail=None,
            response_lines=response_lines,
            retry_submission_expected=retry_submission_expected,
            source_key=source_key,
            session_id=session_id,
            card_archive=card_archive,
            error=None,
            commit_database=True,
        )
    except PushConfigurationError as exc:
        detail = Locale.CONFIGURATION_ERROR_DETAIL
        return AttemptExecution(
            stage=stage,
            result=ATTEMPT_RESULT_CONFIGURATION_ERROR,
            response_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            response_body=http_error_response_body(detail),
            response_detail=detail,
            response_lines=(),
            retry_submission_expected=retry_submission_expected,
            source_key=source_key,
            session_id=session_id,
            card_archive=None,
            error=exc,
            commit_database=False,
        )
    except MultipleEvidenceMatches as exc:
        detail = Locale.MULTIPLE_MATCH_DETAIL_TEMPLATE.format(excerpt=exc.excerpt)
        return AttemptExecution(
            stage=stage,
            result=ATTEMPT_RESULT_REJECTED,
            response_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            response_body=http_error_response_body(detail),
            response_detail=detail,
            response_lines=(),
            retry_submission_expected=retry_submission_expected,
            source_key=source_key,
            session_id=session_id,
            card_archive=None,
            error=exc,
            commit_database=(stage == ATTEMPT_STAGE_EVIDENCE_VALIDATION),
        )
    except PushValidationError as exc:
        detail = (
            exc.public_detail
            if isinstance(exc, EvidenceAssessmentError)
            else Locale.VALIDATION_ERROR_DETAIL
        )
        return AttemptExecution(
            stage=stage,
            result=ATTEMPT_RESULT_REJECTED,
            response_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            response_body=http_error_response_body(detail),
            response_detail=detail,
            response_lines=(),
            retry_submission_expected=retry_submission_expected,
            source_key=source_key,
            session_id=session_id,
            card_archive=None,
            error=exc,
            commit_database=(
                stage
                in {
                    ATTEMPT_STAGE_PYDANTIC_VALIDATION,
                    ATTEMPT_STAGE_EVIDENCE_VALIDATION,
                }
            ),
        )
    except ValidationError as exc:
        detail = Locale.VALIDATION_ERROR_DETAIL + (
            f"\n{RETRY_SUBMISSION_PUBLIC_GUIDANCE}" if retry_submission_expected else ""
        )
        return AttemptExecution(
            stage=stage,
            result=ATTEMPT_RESULT_REJECTED,
            response_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            response_body=http_error_response_body(detail),
            response_detail=detail,
            response_lines=(),
            retry_submission_expected=retry_submission_expected,
            source_key=source_key,
            session_id=session_id,
            card_archive=None,
            error=exc,
            commit_database=True,
        )
    except (OSError, ValueError, duckdb.Error, subprocess.SubprocessError) as exc:
        detail = Locale.VALIDATION_ERROR_DETAIL
        return AttemptExecution(
            stage=stage,
            result=ATTEMPT_RESULT_REJECTED,
            response_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            response_body=http_error_response_body(detail),
            response_detail=detail,
            response_lines=(),
            retry_submission_expected=retry_submission_expected,
            source_key=source_key,
            session_id=session_id,
            card_archive=None,
            error=exc,
            commit_database=False,
        )
    finally:
        if source_conn is not None:
            source_conn.close()


def _validated_archived_file(
    attempt_dir: Path,
    artifact: ArchivedArtifact,
    *,
    expected_filename: str,
) -> ArchivedFile:
    artifact_path = attempt_dir / artifact.filename
    if (
        artifact.filename != expected_filename
        or artifact_path.parent != attempt_dir
        or not artifact_path.is_file()
        or artifact_path.is_symlink()
    ):
        raise PushValidationError(
            Locale.ARCHIVED_ATTEMPT_ARTIFACT_INVALID_TEMPLATE.format(artifact=expected_filename)
        )
    archived_file = _archived_file(artifact_path)
    if archived_file.size != artifact.size or archived_file.sha256 != artifact.sha256:
        raise PushValidationError(
            Locale.ARCHIVED_ATTEMPT_ARTIFACT_INVALID_TEMPLATE.format(artifact=expected_filename)
        )
    if (
        isinstance(artifact, ArchivedRolloutArtifact)
        and archived_file.line_count != artifact.line_count
    ):
        raise PushValidationError(
            Locale.ARCHIVED_ATTEMPT_ARTIFACT_INVALID_TEMPLATE.format(artifact=expected_filename)
        )
    return archived_file


def _archived_attempt_replay(
    attempt_dir: Path,
) -> tuple[ArchivedAttemptManifest, str, AttemptReplayInput]:
    if not attempt_dir.is_dir() or attempt_dir.is_symlink():
        raise PushValidationError(Locale.ARCHIVED_ATTEMPT_PATH_INVALID)
    manifest_path = attempt_dir / ATTEMPT_MANIFEST_FILENAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise PushValidationError(Locale.ARCHIVED_ATTEMPT_MANIFEST_INVALID)
    try:
        manifest_text = manifest_path.read_text(encoding=TEXT_ENCODING)
        manifest = ArchivedAttemptManifest.model_validate_json(manifest_text)
        timestamp_text, uuid_text = manifest.attempt_id.rsplit(
            ATTEMPT_ID_SEPARATOR,
            maxsplit=1,
        )
        attempt_timestamp = datetime.strptime(
            timestamp_text,
            ATTEMPT_ID_TIMESTAMP_FORMAT,
        ).replace(tzinfo=timezone.utc)
        if UUID(hex=uuid_text).hex != uuid_text:
            raise ValueError(Locale.ARCHIVED_ATTEMPT_MANIFEST_INVALID)
        datetime.fromisoformat(manifest.updated_at)
    except (OSError, UnicodeError, ValueError, ValidationError) as exc:
        raise PushValidationError(Locale.ARCHIVED_ATTEMPT_MANIFEST_INVALID) from exc
    if manifest.attempt_id != attempt_dir.name:
        raise PushValidationError(Locale.ARCHIVED_ATTEMPT_MANIFEST_INVALID)
    expected_response_code = ATTEMPT_RESULT_RESPONSE_CODE.get(manifest.result)
    if expected_response_code is None:
        raise PushValidationError(Locale.ARCHIVED_ATTEMPT_MANIFEST_INVALID)
    if manifest.result == ATTEMPT_RESULT_ACCEPTED and manifest.stage != ATTEMPT_STAGE_ACCEPTED:
        raise PushValidationError(Locale.ARCHIVED_ATTEMPT_MANIFEST_INVALID)
    if manifest.run_id is not None and (manifest.source_key is None or manifest.session_id is None):
        raise PushValidationError(Locale.ARCHIVED_ATTEMPT_MANIFEST_INVALID)
    if manifest.result == ATTEMPT_RESULT_ACCEPTED and manifest.source_key is None:
        raise PushValidationError(Locale.ARCHIVED_ATTEMPT_MANIFEST_INVALID)

    rollout_relative_path = PurePosixPath(manifest.rollout_relative_path)
    if (
        str(rollout_relative_path) != manifest.rollout_relative_path
        or rollout_relative_path.is_absolute()
        or rollout_relative_path == CURRENT_DIRECTORY
        or any(part in FORBIDDEN_NORMALIZED_PATH_PARTS for part in rollout_relative_path.parts)
    ):
        raise PushValidationError(Locale.ARCHIVED_ATTEMPT_MANIFEST_INVALID)
    rollout_archive = _validated_archived_file(
        attempt_dir,
        manifest.artifacts.rollout,
        expected_filename=ROLLOUT_ARCHIVE_FILENAME_TEMPLATE.format(attempt_id=manifest.attempt_id),
    )
    report_archive = _validated_archived_file(
        attempt_dir,
        manifest.artifacts.appendwatch_report,
        expected_filename=APPENDWATCH_ARCHIVE_FILENAME_TEMPLATE.format(
            attempt_id=manifest.attempt_id
        ),
    )
    http_archive = _validated_archived_file(
        attempt_dir,
        manifest.artifacts.http_request_log,
        expected_filename=HTTP_REQUEST_LOG_FILENAME_TEMPLATE.format(attempt_id=manifest.attempt_id),
    )
    try:
        http_lines = http_archive.path.read_text(encoding=TEXT_ENCODING).splitlines()
        if len(http_lines) != 1 or http_archive.line_count != 1:
            raise ValueError(Locale.ARCHIVED_ATTEMPT_HTTP_INVALID)
        http_record = HttpRequestLogRecord.model_validate_json(http_lines[0])
        if (
            http_record.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION
            or http_record.method != HTTP_POST_METHOD
            or http_record.path != PUSH_PATH
            or http_record.query
            or http_record.response_code != expected_response_code
            or not isinstance(http_record.request_body, str)
        ):
            raise ValueError(Locale.ARCHIVED_ATTEMPT_HTTP_INVALID)
        request_body = http_record.request_body.encode(TEXT_ENCODING)
        if len(request_body) > MAX_PUSH_BODY_BYTES:
            raise ValueError(Locale.ARCHIVED_ATTEMPT_HTTP_INVALID)
    except (OSError, UnicodeError, ValueError, ValidationError) as exc:
        raise PushValidationError(Locale.ARCHIVED_ATTEMPT_HTTP_INVALID) from exc
    return (
        manifest,
        manifest_text,
        AttemptReplayInput(
            attempt_dir=attempt_dir,
            attempt_id=manifest.attempt_id,
            attempt_timestamp=attempt_timestamp,
            rollout_archive=rollout_archive,
            report_archive=report_archive,
            rollout_relative_path=rollout_relative_path,
            request_body=request_body,
            run_id=manifest.run_id,
            source_key=manifest.source_key,
            session_id=manifest.session_id,
            materialize_files=False,
        ),
    )


def restore_archived_attempts(
    runtime: RuntimeConfiguration,
    *,
    attempts_dir: Path = ATTEMPTS_DIR,
) -> ArchivedAttemptRecovery:
    attempts_dir.mkdir(parents=True, exist_ok=True)
    attempt_dirs = tuple(
        sorted(
            (path for path in attempts_dir.iterdir() if path.is_dir() or path.is_symlink()),
            key=lambda path: path.name,
        )
    )
    restored_attempt_ids: list[str] = []
    restored_accepted_attempt_ids: list[str] = []
    skipped_attempt_ids: list[str] = []
    invalid = 0
    with DETOUR_DB_LOCK:
        detour_conn = open_detour_database(runtime)
        try:
            detour_conn.execute(CREATE_ARCHIVED_ATTEMPTS_TABLE_SQL)
            existing_attempt_ids = {
                cast(str, row[0])
                for row in detour_conn.execute(SELECT_ARCHIVED_ATTEMPT_IDS_SQL).fetchall()
            }
            for attempt_dir in attempt_dirs:
                if attempt_dir.name in existing_attempt_ids:
                    skipped_attempt_ids.append(attempt_dir.name)
                    continue
                transaction_started = False
                try:
                    manifest, manifest_text, replay = _archived_attempt_replay(attempt_dir)
                    detour_conn.execute("BEGIN TRANSACTION")
                    transaction_started = True
                    execution = execute_attempt(detour_conn, runtime, replay)
                    if (
                        execution.stage != manifest.stage
                        or execution.result != manifest.result
                    ):
                        raise PushValidationError(Locale.ARCHIVED_ATTEMPT_OUTCOME_MISMATCH)
                    if not execution.commit_database:
                        detour_conn.execute("ROLLBACK")
                        transaction_started = False
                        detour_conn.execute("BEGIN TRANSACTION")
                        transaction_started = True
                    detour_conn.execute(
                        INSERT_ARCHIVED_ATTEMPT_SQL,
                        [manifest.attempt_id, manifest_text],
                    )
                    detour_conn.execute("COMMIT")
                    transaction_started = False
                    restored_attempt_ids.append(manifest.attempt_id)
                    if manifest.result == ATTEMPT_RESULT_ACCEPTED:
                        restored_accepted_attempt_ids.append(manifest.attempt_id)
                except Exception:
                    if transaction_started:
                        detour_conn.execute("ROLLBACK")
                    invalid += 1
        finally:
            detour_conn.close()
    return ArchivedAttemptRecovery(
        discovered=len(attempt_dirs),
        invalid=invalid,
        restored_attempt_ids=tuple(restored_attempt_ids),
        restored_accepted_attempt_ids=tuple(restored_accepted_attempt_ids),
        skipped_attempt_ids=tuple(skipped_attempt_ids),
    )


def validate_transport(request: Request) -> None:
    content_type = (
        request.headers.get(HTTP_REQUEST_CONTENT_TYPE_HEADER, "").partition(";")[0].strip().lower()
    )
    if content_type != JSON_MEDIA_TYPE:
        raise PushValidationError(Locale.REQUEST_CONTENT_TYPE_INVALID)
    content_length = request.headers.get(HTTP_REQUEST_CONTENT_LENGTH_HEADER)
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise PushValidationError(Locale.REQUEST_CONTENT_LENGTH_INVALID) from exc
        if declared_length < 0 or declared_length > MAX_PUSH_BODY_BYTES:
            raise PushValidationError(Locale.REQUEST_BODY_TOO_LARGE)


async def bounded_request_body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_PUSH_BODY_BYTES:
            raise PushValidationError(Locale.REQUEST_BODY_TOO_LARGE)
    return bytes(body)


def pydantic_failure(exc: ValidationError) -> tuple[str | None, str, object]:
    errors = exc.errors(
        include_url=False,
        include_context=False,
        include_input=True,
    )
    if not errors:
        return None, Locale.PYDANTIC_FAILURE, Locale.PYDANTIC_MISSING_INPUT
    error = errors[0]
    reason = str(error.get(PYDANTIC_ERROR_MESSAGE_KEY, Locale.PYDANTIC_FAILURE))
    error_location = error.get(PYDANTIC_ERROR_LOCATION_KEY)
    location_items = error_location if isinstance(error_location, tuple) else ()
    field = next(
        (item for item in location_items if isinstance(item, str) and item in AI_AUGMENT_COLUMNS),
        None,
    )
    if field is None:
        field = next(
            (column for column in AI_AUGMENT_COLUMNS if column in reason),
            None,
        )
    failed_input = (
        Locale.PYDANTIC_MISSING_INPUT
        if error.get(PYDANTIC_ERROR_TYPE_KEY) == PYDANTIC_MISSING_ERROR_TYPE
        else error.get(PYDANTIC_ERROR_INPUT_KEY, Locale.PYDANTIC_MISSING_INPUT)
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
    request: Request,
    request_body: bytes,
    response_code: int,
    response_body: str,
    started_ns: int,
    http_request_log_archive: ArchivedFile | None = None,
    run_id: UUID | None = None,
    source_key: str | None = None,
    session_id: str | None = None,
    rollout_relative_path: PurePosixPath | None = None,
) -> None:
    if attempt_dir is None:
        return
    try:
        if http_request_log_archive is None:
            http_request_log_archive = archive_http_request_log(
                attempt_dir,
                attempt_id,
                request=request,
                request_body=request_body,
                response_code=response_code,
                response_headers={
                    HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_HEADER: (
                        ATTEMPT_RESPONSE_CONTENT_TYPE[response_code]
                    )
                },
                response_body=response_body,
                started_ns=started_ns,
            )
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            result,
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
            http_request_log_archive=http_request_log_archive,
            run_id=run_id,
            source_key=source_key,
            session_id=session_id,
            rollout_relative_path=rollout_relative_path,
        )
    except OSError, PushValidationError:
        logger.exception(
            Locale.ATTEMPT_RECORD_FAILED_LOG,
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
                    raise PushConfigurationError(Locale.WORKBOOK_NOT_INITIALIZED)
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
        logger.error(Locale.PULL_FAILED_LOG, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=Locale.CONFIGURATION_ERROR_DETAIL,
        ) from None


# curl -N \
#  -H 'Content-Type: application/json' \
#  --data @submission.json \
#  http://127.0.0.1:8000/push
@app.post(**PUSH_ROUTE)
async def push(request: Request) -> StreamingResponse:
    started_ns = time.monotonic_ns()
    attempt_timestamp = datetime.now(timezone.utc)
    attempt_id = new_attempt_id(attempt_timestamp)
    attempt_dir: Path | None = None
    rollout_archive: ArchivedFile | None = None
    workbook_archive: ArchivedFile | None = None
    report_archive: ArchivedFile | None = None
    card_archive: ArchivedFile | None = None
    http_request_log_archive: ArchivedFile | None = None
    request_body = b""
    snapshot: SanctionSnapshot | None = None
    configuration: PushConfiguration | None = None
    stage = ATTEMPT_STAGE_TRANSPORT

    try:
        attempt_dir = create_attempt(attempt_id)
        record_attempt(attempt_dir, attempt_id, stage, ATTEMPT_RESULT_PENDING)
        request_body = await bounded_request_body(request)
        validate_transport(request)
        stage = ATTEMPT_STAGE_CONFIGURATION
        runtime = runtime_configuration()
        snapshot = sanctioned_snapshot()
        configuration = push_configuration(snapshot.rollout_guest_path)
        if snapshot.control_base_url is not None:
            with WORKBOOK_STATE_LOCK:
                if not WORKBOOK_INITIALIZED:
                    raise PushConfigurationError(Locale.WORKBOOK_NOT_INITIALIZED)
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            ATTEMPT_RESULT_PENDING,
            rollout_relative_path=configuration.rollout_relative_path,
        )

        stage = ATTEMPT_STAGE_ROLLOUT_COPY
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            ATTEMPT_RESULT_PENDING,
            rollout_relative_path=configuration.rollout_relative_path,
        )
        rollout_archive = copy_rollout(configuration, attempt_dir, attempt_id)

        if snapshot.control_base_url is not None:
            stage = ATTEMPT_STAGE_WORKBOOK_COPY
            record_attempt(
                attempt_dir,
                attempt_id,
                stage,
                ATTEMPT_RESULT_PENDING,
                rollout_archive=rollout_archive,
                rollout_relative_path=configuration.rollout_relative_path,
            )
            workbook_archive = copy_guest_workbook(configuration, attempt_dir, attempt_id)

        stage = ATTEMPT_STAGE_APPENDWATCH_COPY
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            ATTEMPT_RESULT_PENDING,
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            rollout_relative_path=configuration.rollout_relative_path,
        )
        report_archive = copy_appendwatch_report(configuration, attempt_dir, attempt_id)

        stage = ATTEMPT_STAGE_APPENDWATCH_VALIDATION
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            ATTEMPT_RESULT_PENDING,
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            rollout_relative_path=configuration.rollout_relative_path,
        )
        replay = AttemptReplayInput(
            attempt_dir=attempt_dir,
            attempt_id=attempt_id,
            attempt_timestamp=attempt_timestamp,
            rollout_archive=rollout_archive,
            report_archive=report_archive,
            rollout_relative_path=configuration.rollout_relative_path,
            request_body=request_body,
            run_id=snapshot.run_id,
            source_key=snapshot.source_key,
            session_id=snapshot.session_id,
            materialize_files=True,
        )
        with DETOUR_DB_LOCK:
            detour_conn = open_detour_database(runtime)
            transaction_started = False
            execution: AttemptExecution | None = None
            try:
                detour_conn.execute(CREATE_ARCHIVED_ATTEMPTS_TABLE_SQL)
                detour_conn.execute("BEGIN TRANSACTION")
                transaction_started = True
                execution = execute_attempt(detour_conn, runtime, replay)
                stage = execution.stage
                card_archive = execution.card_archive
                if not execution.commit_database:
                    detour_conn.execute("ROLLBACK")
                    transaction_started = False
                http_request_log_archive = archive_http_request_log(
                    attempt_dir,
                    attempt_id,
                    request=request,
                    request_body=request_body,
                    response_code=execution.response_code,
                    response_headers={
                        HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_HEADER: (
                            ATTEMPT_RESPONSE_CONTENT_TYPE[execution.response_code]
                        )
                    },
                    response_body=execution.response_body,
                    started_ns=started_ns,
                )
                manifest_text = record_attempt(
                    attempt_dir,
                    attempt_id,
                    execution.stage,
                    execution.result,
                    rollout_archive=rollout_archive,
                    workbook_archive=workbook_archive,
                    report_archive=report_archive,
                    card_archive=card_archive,
                    http_request_log_archive=http_request_log_archive,
                    run_id=snapshot.run_id,
                    source_key=execution.source_key,
                    session_id=execution.session_id,
                    rollout_relative_path=configuration.rollout_relative_path,
                )
                if not execution.commit_database:
                    detour_conn.execute("BEGIN TRANSACTION")
                    transaction_started = True
                detour_conn.execute(
                    INSERT_ARCHIVED_ATTEMPT_SQL,
                    [attempt_id, manifest_text],
                )
                detour_conn.execute("COMMIT")
                transaction_started = False
            except Exception:
                if transaction_started:
                    detour_conn.execute("ROLLBACK")
                if execution is not None and execution.card_archive is not None:
                    (attempt_dir / RESPONSE_FILENAME).unlink(missing_ok=True)
                    execution.card_archive.path.unlink(missing_ok=True)
                raise
            finally:
                detour_conn.close()

        assert execution is not None
        if execution.error is not None:
            if isinstance(execution.error, PushConfigurationError):
                logger.error(
                    Locale.PUSH_CONFIGURATION_FAILED_LOG,
                    attempt_id,
                    execution.stage,
                    execution.error,
                )
            elif isinstance(execution.error, MultipleEvidenceMatches):
                logger.warning(
                    Locale.PUSH_MULTIPLE_MATCHES_LOG,
                    attempt_id,
                    execution.stage,
                    execution.error.excerpt,
                )
            elif isinstance(execution.error, ValidationError):
                field, reason, failed_input = pydantic_failure(execution.error)
                logger.warning(
                    Locale.PUSH_PYDANTIC_FAILED_LOG,
                    attempt_id,
                    execution.stage,
                    field or Locale.UNKNOWN_FIELD,
                    failed_input,
                    reason,
                )
            elif isinstance(execution.error, PushValidationError):
                logger.warning(
                    Locale.PUSH_VALIDATION_FAILED_LOG,
                    attempt_id,
                    execution.stage,
                    execution.error,
                )
            else:
                logger.warning(
                    Locale.PUSH_UNEXPECTED_FAILED_LOG,
                    attempt_id,
                    execution.stage,
                    execution.error,
                )
            assert execution.response_detail is not None
            raise HTTPException(
                status_code=execution.response_code,
                detail=execution.response_detail,
            )

        consume_sanction(snapshot)
        try:
            acknowledge_sanction(snapshot, attempt_id)
        except PushConfigurationError as exc:
            logger.error(
                Locale.CONTROL_ACKNOWLEDGEMENT_FAILED_LOG,
                attempt_id,
                exc,
            )
        logger.info(Locale.PUSH_ACCEPTED_LOG, attempt_id)
        return StreamingResponse(iter(execution.response_lines), media_type=MEDIA_TYPE)
    except PushConfigurationError as exc:
        response_body = http_error_response_body(Locale.CONFIGURATION_ERROR_DETAIL)
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            ATTEMPT_RESULT_CONFIGURATION_ERROR,
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
            request=request,
            request_body=request_body,
            response_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            response_body=response_body,
            started_ns=started_ns,
            http_request_log_archive=http_request_log_archive,
            run_id=None if snapshot is None else snapshot.run_id,
            source_key=None if snapshot is None else snapshot.source_key,
            session_id=None if snapshot is None else snapshot.session_id,
            rollout_relative_path=(
                None if configuration is None else configuration.rollout_relative_path
            ),
        )
        logger.error(
            Locale.PUSH_CONFIGURATION_FAILED_LOG,
            attempt_id,
            stage,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=Locale.CONFIGURATION_ERROR_DETAIL,
        ) from None
    except MultipleEvidenceMatches as exc:
        detail = Locale.MULTIPLE_MATCH_DETAIL_TEMPLATE.format(excerpt=exc.excerpt)
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            ATTEMPT_RESULT_REJECTED,
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
            request=request,
            request_body=request_body,
            response_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            response_body=http_error_response_body(detail),
            started_ns=started_ns,
            http_request_log_archive=http_request_log_archive,
            run_id=None if snapshot is None else snapshot.run_id,
            source_key=None if snapshot is None else snapshot.source_key,
            session_id=None if snapshot is None else snapshot.session_id,
            rollout_relative_path=(
                None if configuration is None else configuration.rollout_relative_path
            ),
        )
        logger.warning(
            Locale.PUSH_MULTIPLE_MATCHES_LOG,
            attempt_id,
            stage,
            exc.excerpt,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        ) from None
    except PushValidationError as exc:
        detail = (
            exc.public_detail
            if isinstance(exc, EvidenceAssessmentError)
            else Locale.VALIDATION_ERROR_DETAIL
        )
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            ATTEMPT_RESULT_REJECTED,
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
            request=request,
            request_body=request_body,
            response_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            response_body=http_error_response_body(detail),
            started_ns=started_ns,
            http_request_log_archive=http_request_log_archive,
            run_id=None if snapshot is None else snapshot.run_id,
            source_key=None if snapshot is None else snapshot.source_key,
            session_id=None if snapshot is None else snapshot.session_id,
            rollout_relative_path=(
                None if configuration is None else configuration.rollout_relative_path
            ),
        )
        logger.warning(
            Locale.PUSH_VALIDATION_FAILED_LOG,
            attempt_id,
            stage,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        ) from None
    except ValidationError as exc:
        field, reason, failed_input = pydantic_failure(exc)
        detail = Locale.VALIDATION_ERROR_DETAIL
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            ATTEMPT_RESULT_REJECTED,
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
            request=request,
            request_body=request_body,
            response_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            response_body=http_error_response_body(detail),
            started_ns=started_ns,
            http_request_log_archive=http_request_log_archive,
            run_id=None if snapshot is None else snapshot.run_id,
            source_key=None if snapshot is None else snapshot.source_key,
            session_id=None if snapshot is None else snapshot.session_id,
            rollout_relative_path=(
                None if configuration is None else configuration.rollout_relative_path
            ),
        )
        logger.warning(
            Locale.PUSH_PYDANTIC_FAILED_LOG,
            attempt_id,
            stage,
            field or Locale.UNKNOWN_FIELD,
            failed_input,
            reason,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        ) from None
    except (OSError, ValueError, duckdb.Error, subprocess.SubprocessError) as exc:
        detail = Locale.VALIDATION_ERROR_DETAIL
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            ATTEMPT_RESULT_REJECTED,
            rollout_archive=rollout_archive,
            workbook_archive=workbook_archive,
            report_archive=report_archive,
            card_archive=card_archive,
            request=request,
            request_body=request_body,
            response_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            response_body=http_error_response_body(detail),
            started_ns=started_ns,
            http_request_log_archive=http_request_log_archive,
            run_id=None if snapshot is None else snapshot.run_id,
            source_key=None if snapshot is None else snapshot.source_key,
            session_id=None if snapshot is None else snapshot.session_id,
            rollout_relative_path=(
                None if configuration is None else configuration.rollout_relative_path
            ),
        )
        logger.warning(
            Locale.PUSH_UNEXPECTED_FAILED_LOG,
            attempt_id,
            stage,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        ) from None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=Locale.CLI_DESCRIPTION)
    parser.add_argument(CONFIG_OPTION, required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_runtime(args.config)
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)


if __name__ == "__main__":
    main()
