from __future__ import annotations

import asyncio
import base64
import fcntl
import hashlib
import json
import logging
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import AsyncGenerator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager, contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path, PurePosixPath
from random import Random
from typing import Any, Callable, Literal, Self, TypeAlias, cast, get_args
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import duckdb
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    ValidationError,
    model_validator,
)
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.helpers.architecture import implements
from src.helpers.cards import build_cards, write_cards_zip
from src.helpers.config import PipelineConfig
from src.helpers.data_models import (
    FragmentType,
    InnerDict,
    NameKey,
    OuterDict,
    RegisteredResource,
    ResourceGroup,
)
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
)
from src.helpers.duckdb_extensions import load_duckdb_extension
from src.helpers.duckdb_utils import (
    duckdb_quote_identifier,
    materialize_innerdicts_from_rows_table,
)
from src.helpers.name_matching import normalized_tokens_sql
from src.helpers.resources import register_resource
from src.helpers.vars import (
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
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
    KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS,
)

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers import codex_parse
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.pydantic_to_paste import (
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
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_fixture import (
    L_FEI_FEI_INITIAL_FIXTURE,
    L_FEI_FEI_RETRY_FIXTURE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_init import (
    Submission,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AI_AUGMENT_COLUMNS,
    AI_AUGMENT_EVIDENCE_COLUMNS,
    AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS,
    AI_AUGMENT_STANDARDIZED_COLUMNS,
    CONFIG_FILENAME,
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    KTP_AI_AUGMENT_COMMENTS_COL,
    KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL,
    KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL,
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
    MAP_SUBSET_0_TO_BATCH_KEY,
    TEXT_ENCODING,
    AiAugmentCohort,
)

from ..control_centre.dashboard.helpers.data_models.run_outcome import (
    NAME_KEY_HEADER,
    name_key_from_header_value,
    name_key_header_value,
)
from .helpers.data_models.ai_augment_context import (
    AiAugmentBackendContext,
)
from .helpers.data_models.ai_augment_outer_dict import (
    AiAugmentOuterDict,
    CommittedInnerDict,
)
from .helpers.data_models.commit_event import (
    COMMIT_PATH,
    SOURCE_KEY_HEADER,
    AppendwatchReportEncoding,
    AppendwatchReportRecord,
    BackendCommitRecord,
    CodexRolloutRecord,
    CodexSessionRecord,
    CommitRequestBody,
    PostCommitValidation,
    PostCommitValidationResult,
    PostCommitValidationStage,
    source_key_from_header_value,
    source_key_header_value,
)
from .helpers.data_models.query_response import (
    AgentRuntimeAttempt,
    AgentRuntimeAttemptRecord,
    QueryResponse,
)
from .helpers.data_models.run_outcome_response import (
    RunOutcomeResponse,
    RunOutcomeResponseBody,
)

logger = logging.getLogger(__name__)


@implements[BackendComponent.WorkflowStatusProperty]()
class BackendWorkflowStatus(StrEnum):
    value: Literal[
        "ready",
        "busy",
        "retry",
        "complete",
        "failed",
    ]

    READY = "ready"
    BUSY = "busy"
    RETRY = "retry"
    COMPLETE = "complete"
    FAILED = "failed"


AIVM_WORKDIR = PurePosixPath("/home/ai/workdir")

ROLLOUT_ENV_NAME = "FASTAPI_DETOUR_ROLLOUT_JSONL"
ROLLOUT_JSONL = os.environ.get(ROLLOUT_ENV_NAME, "")
APPENDWATCH_REPORT_ENV_NAME = "FASTAPI_DETOUR_APPENDWATCH_REPORT"
NAMEKEY_ENV_NAME = "FASTAPI_DETOUR_NAMEKEY"
CODEX_SESSIONS_ROOT_ENV_NAME = "FASTAPI_DETOUR_CODEX_SESSIONS_DIR"
CONTROL_PARENT_PID_ENV_NAME = "FASTAPI_DETOUR_CONTROL_PARENT_PID"
AIVM_INSTANCE_ENV_NAME = "FASTAPI_DETOUR_AIVM_INSTANCE"
AIVM_AUDIT_USER_ENV_NAME = "FASTAPI_DETOUR_AIVM_AUDIT_USER"
AIVM_SSH_PORT_ENV_NAME = "FASTAPI_DETOUR_AIVM_SSH_PORT"
AIVM_IDENTITY_FILE_ENV_NAME = "FASTAPI_DETOUR_AIVM_IDENTITY_FILE"
AIVM_KNOWN_HOSTS_FILE_ENV_NAME = "FASTAPI_DETOUR_AIVM_KNOWN_HOSTS_FILE"
LIMA_SSH_CONFIG_ENV_NAME = "FASTAPI_DETOUR_LIMA_SSH_CONFIG"
CODEX_SESSIONS_ROOT = PurePosixPath(
    os.environ.get(CODEX_SESSIONS_ROOT_ENV_NAME, "/home/ai/.codex/sessions")
)
APPENDWATCH_REPORT = os.environ.get(APPENDWATCH_REPORT_ENV_NAME, "")
BACKEND_PROCESS_LOCK_PATH = Path(tempfile.gettempdir()) / "ktp-hcr-detour-ai-augment-backend.lock"

AIVM_INSTANCE = os.environ.get(AIVM_INSTANCE_ENV_NAME, "aivm")
AIVM_AUDIT_USER = os.environ.get(AIVM_AUDIT_USER_ENV_NAME, "aivm-audit")
AIVM_SSH_PORT = os.environ.get(AIVM_SSH_PORT_ENV_NAME, "22022")
AIVM_KEY_DIR = Path.home() / ".local" / "share" / "aivm" / ".ssh"
_AIVM_IDENTITY_FILE_VALUE = os.environ.get(AIVM_IDENTITY_FILE_ENV_NAME)
AIVM_IDENTITY_FILE = (
    None if not _AIVM_IDENTITY_FILE_VALUE else Path(_AIVM_IDENTITY_FILE_VALUE).expanduser()
)
AIVM_KNOWN_HOSTS_FILE = Path(
    os.environ.get(AIVM_KNOWN_HOSTS_FILE_ENV_NAME, AIVM_KEY_DIR / "known_hosts")
).expanduser()
LIMA_SSH_CONFIG_PATH = Path(
    os.environ.get(
        LIMA_SSH_CONFIG_ENV_NAME,
        Path.home() / ".lima" / AIVM_INSTANCE / "ssh.config",
    )
).expanduser()
CURRENT_DIRECTORY = PurePosixPath(".")
FORBIDDEN_NORMALIZED_PATH_PARTS = frozenset({"", ".", ".."})

COMPACT_JSON_SEPARATORS = (",", ":")
ARCHIVE_HASH_CHUNK_BYTES = 1024 * 1024
AUDIT_COPY_TIMEOUT_SECONDS = 60
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
CODEX_SOURCE_FIELD = "source"
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
SSH_EXECUTABLE = "ssh"
AUDIT_PROBE_COMMAND = "probe"
AUDIT_FIND_ROLLOUT_COMMAND = "find-rollout"
AUDIT_READ_ROLLOUT_COMMAND = "read-rollout"
AUDIT_READ_APPENDWATCH_REPORT_COMMAND = "read-appendwatch-report"
BASE64_TEXT_ENCODING = "ascii"
JSON_MEDIA_TYPE = "application/json"
HTTP_GET_METHOD = "GET"
HTTP_POST_METHOD = "POST"
HTTP_PUT_METHOD = "PUT"
HTTP_ACCEPT_HEADER = "Accept"
HTTP_CONTENT_TYPE_HEADER = "Content-Type"
HTTP_REQUEST_CONTENT_TYPE_HEADER = "content-type"
HTTP_REQUEST_CONTENT_LENGTH_HEADER = "content-length"
ASGI_TYPE_KEY = "type"
ASGI_METHOD_KEY = "method"
ASGI_PATH_KEY = "path"
ASGI_BODY_KEY = "body"
ASGI_MORE_BODY_KEY = "more_body"
ASGI_STATUS_KEY = "status"
ASGI_HEADERS_KEY = "headers"
ASGI_HTTP_SCOPE_TYPE = "http"
ASGI_HTTP_REQUEST_MESSAGE_TYPE = "http.request"
ASGI_HTTP_DISCONNECT_MESSAGE_TYPE = "http.disconnect"
ASGI_HTTP_RESPONSE_START_MESSAGE_TYPE = "http.response.start"
ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE = "http.response.body"
TEXT_OUTPUT_FORMAT = "txt"
DOCX_OUTPUT_FORMAT = "docx"
SUPPORTED_OUTPUT_FORMATS = frozenset({TEXT_OUTPUT_FORMAT, DOCX_OUTPUT_FORMAT})
ROLLOUT_FILENAME_PREFIX = "rollout-"
ROLLOUT_FILENAME_SUFFIX = ".jsonl"
DETOUR_DB_SUFFIX = ".duckdb"
DETOUR_DB_FILENAME_TEMPLATE = "{stem}__detour_{detour_id}{suffix}"
ATOMIC_TEMP_FILENAME_TEMPLATE = ".{filename}.{nonce}.tmp"
RESPONSE_FILENAME = f"response{ROLLOUT_FILENAME_SUFFIX}"
CARD_ZIP_FILENAME_TEMPLATE = "{prefix}_{attempt_id}.zip"
ROLLOUT_TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%S"
CUMULATIVE_KEY_SEPARATOR = "\0"
FCO_TIMESTAMP_TIMESPEC = "milliseconds"
API_VERSION = "1.0.0"
PULL_PATH = "/pull"
PUSH_PATH = "/push"
RESOURCE_PATH_KEY = "path"
RESOURCE_DESCRIPTION_KEY = "desc"
RESOURCE_SHA256_KEY = "sha256"
PYDANTIC_ERROR_MESSAGE_KEY = "msg"
PYDANTIC_ERROR_LOCATION_KEY = "loc"
PYDANTIC_ERROR_TYPE_KEY = "type"
PYDANTIC_ERROR_INPUT_KEY = "input"
PYDANTIC_MISSING_ERROR_TYPE = "missing"
REPLAY_LOG_RESOURCE_KEY = "detour_ai_augment_backend_api_replay_log"
ROLLOUT_CAS_TEMP_FILENAME_TEMPLATE = ".{nonce}.tmp"
ROLLOUT_CAS_FILENAME_TEMPLATE = "{sha256}.jsonl"
HTTP_ETAG_HEADER = "ETag"
HTTP_ETAG_SHA256_TEMPLATE = '"sha256:{sha256}"'
HTTP_ETAG_SHA256_PREFIX = '"sha256:'
HTTP_ETAG_SUFFIX = '"'
HTTP_INTERNAL_ERROR_RESPONSE = status.HTTP_500_INTERNAL_SERVER_ERROR
HTTP_BUSY_RESPONSE = status.HTTP_409_CONFLICT
AUTHORITATIVE_FASTAPI_ROUTES = frozenset({
    (HTTP_GET_METHOD, PULL_PATH),
    (HTTP_POST_METHOD, PUSH_PATH),
})
AUTHORITATIVE_COMMIT_ROUTE = (HTTP_POST_METHOD, COMMIT_PATH)
AUTHORITATIVE_CHECKPOINT_ID = 1
AUTHORITATIVE_FIRST_LINE = 1
AUTHORITATIVE_EMPTY_OFFSET = 0
AUTHORITATIVE_LOG_BASE64_ENCODING = "base64"
AUTHORITATIVE_LOG_ENCODING_KEY = "encoding"
AUTHORITATIVE_LOG_DATA_KEY = "data"
OPERATOR_CONFIRMATIONS = frozenset({"y", "yes"})
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
SYNTHETIC_COMMIT_SCHEME = "http"
SYNTHETIC_COMMIT_HOST = "invalid"
RETRY_AFTER_HEADER = "Retry-After"
LOCATION_HEADER = "Location"
RETRY_AFTER_SECONDS = "1"
MARKDOWN_MEDIA_TYPE = "text/markdown"

DRAW_VALUE_SEPARATOR = ", "

DETOUR_ID = "ai-augment"
DETOUR_DB_LOCK = threading.Lock()
DETOUR_DB_CONNECTION: duckdb.DuckDBPyConnection | None = None
DETOUR_DB_CONNECTION_PATH: Path | None = None
AUTHORITATIVE_APPEND_LOCK = threading.Lock()
AUTHORITATIVE_BACKEND_HEALTHY = True
BACKEND_PROCESS_LOCK_DESCRIPTOR: int | None = None
AUTHORITATIVE_LOG_DESCRIPTOR: int | None = None
AUTHORITATIVE_NEXT_LINE_NUMBER = 1
AUTHORITATIVE_LOG_OFFSET = 0
AUTHORITATIVE_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()
BACKEND_WORKFLOW_STATE_LOCK = threading.Lock()
BACKEND_WORKFLOW_STATUS = BackendWorkflowStatus.READY
BACKEND_ATTEMPT_RECORD: AgentRuntimeAttemptRecord | None = None
BACKEND_CURRENT_PULL_RECORD_ID: UUID | None = None
BACKEND_PENDING_PULL_RECORD_ID: UUID | None = None
BACKEND_LATEST_PUSH_RECORD_ID: UUID | None = None
BACKEND_SESSION_ID: str | None = None
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
AUTHORITATIVE_PROJECTION_TABLE = "detour_authoritative_projection"
AUTHORITATIVE_PROJECTION_ID_COLUMN = "id"
AUTHORITATIVE_PROJECTION_LINE_COLUMN = "line_number"
AUTHORITATIVE_PROJECTION_OFFSET_COLUMN = "byte_offset"
AUTHORITATIVE_PROJECTION_HASH_COLUMN = "line_sha256"
AUTHORITATIVE_RECORDS_TABLE = "detour_http_records"
AUTHORITATIVE_RECORD_ORDINAL_COLUMN = "record_ordinal"
AUTHORITATIVE_RECORD_ID_COLUMN = "record_id"
AUTHORITATIVE_RECORD_METHOD_COLUMN = "method"
AUTHORITATIVE_RECORD_PATH_COLUMN = "path"
AUTHORITATIVE_RECORD_PAYLOAD_COLUMN = "record"
AUTHORITATIVE_ATTEMPTS_TABLE = "detour_agent_runtime_attempt_records"
AUTHORITATIVE_ATTEMPT_COMMIT_ID_COLUMN = "commit_record_id"
AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN = "attempt_record"

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
CODEX_RETRY_NAMEKEY_COL = "namekey"
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
CREATE_AUTHORITATIVE_PROJECTION_TABLE_SQL = (
    f"CREATE TABLE IF NOT EXISTS {AUTHORITATIVE_PROJECTION_TABLE} ("
    f"{AUTHORITATIVE_PROJECTION_ID_COLUMN} INTEGER PRIMARY KEY, "
    f"{AUTHORITATIVE_PROJECTION_LINE_COLUMN} BIGINT NOT NULL, "
    f"{AUTHORITATIVE_PROJECTION_OFFSET_COLUMN} BIGINT NOT NULL, "
    f"{AUTHORITATIVE_PROJECTION_HASH_COLUMN} VARCHAR NOT NULL)"
)
CREATE_AUTHORITATIVE_RECORDS_TABLE_SQL = (
    f"CREATE TABLE IF NOT EXISTS {AUTHORITATIVE_RECORDS_TABLE} ("
    f"{AUTHORITATIVE_RECORD_ORDINAL_COLUMN} BIGINT PRIMARY KEY, "
    f"{AUTHORITATIVE_RECORD_ID_COLUMN} VARCHAR NOT NULL UNIQUE, "
    f"{AUTHORITATIVE_RECORD_METHOD_COLUMN} VARCHAR NOT NULL, "
    f"{AUTHORITATIVE_RECORD_PATH_COLUMN} VARCHAR NOT NULL, "
    f"{AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} JSON NOT NULL)"
)
CREATE_AUTHORITATIVE_ATTEMPTS_TABLE_SQL = (
    f"CREATE TABLE IF NOT EXISTS {AUTHORITATIVE_ATTEMPTS_TABLE} ("
    f"{AUTHORITATIVE_ATTEMPT_COMMIT_ID_COLUMN} VARCHAR PRIMARY KEY, "
    f"{AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN} JSON NOT NULL)"
)
HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_HEADER = "content-type"
HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_JSON = "application/json"
NANOSECONDS_PER_MICROSECOND = 1_000
CONTROL_PARENT_WATCH_SECONDS = 0.1

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
    (KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL, "VARCHAR NOT NULL UNIQUE"),
    (KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL, "VARCHAR NOT NULL"),
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
MEDIA_TYPE_WITH_CHARSET = f"{MEDIA_TYPE}; charset=utf-8"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    parent_watch: asyncio.Task[None] | None = None
    acquired_backend_process_lock = False
    try:
        runtime = runtime_configuration()
        with BACKEND_WORKFLOW_STATE_LOCK:
            global BACKEND_CURRENT_PULL_RECORD_ID
            global BACKEND_LATEST_PUSH_RECORD_ID
            global BACKEND_PENDING_PULL_RECORD_ID
            global BACKEND_SESSION_ID
            global BACKEND_ATTEMPT_RECORD
            global BACKEND_WORKFLOW_STATUS
            BACKEND_CURRENT_PULL_RECORD_ID = None
            BACKEND_PENDING_PULL_RECORD_ID = None
            BACKEND_LATEST_PUSH_RECORD_ID = None
            BACKEND_SESSION_ID = None
            BACKEND_ATTEMPT_RECORD = None
            BACKEND_WORKFLOW_STATUS = BackendWorkflowStatus.READY
        if BACKEND_PROCESS_LOCK_DESCRIPTOR is None:
            _acquire_backend_process_lock()
            acquired_backend_process_lock = True
        _acquire_authoritative_process_lock(runtime)
        prove_workflow_inputs_readable()
        synchronize_authoritative_projection(runtime)
        start_backend_session_reader()
        parent_pid = os.environ.get(CONTROL_PARENT_PID_ENV_NAME)
        if parent_pid is not None:
            if not parent_pid.isdecimal() or int(parent_pid) <= 0:
                raise _PushConfigurationError(Locale.CONTROL_PARENT_PID_INVALID)
            parent_watch = asyncio.create_task(_watch_control_parent(int(parent_pid)))
    except Exception as exc:
        logger.error(Locale.API_STARTUP_FAILED_LOG, exc)
        close_backend_detour_database()
        _release_authoritative_process_lock()
        if acquired_backend_process_lock:
            _release_backend_process_lock()
        raise
    try:
        yield
    finally:
        if AUTHORITATIVE_BACKGROUND_TASKS:
            await asyncio.gather(
                *tuple(AUTHORITATIVE_BACKGROUND_TASKS),
                return_exceptions=True,
            )
        if parent_watch is not None:
            parent_watch.cancel()
            with suppress(asyncio.CancelledError):
                await parent_watch
        close_backend_detour_database()
        _release_authoritative_process_lock()
        if acquired_backend_process_lock:
            _release_backend_process_lock()


async def _watch_control_parent(parent_pid: int) -> None:
    while True:
        if os.getppid() != parent_pid:
            os.kill(os.getpid(), signal.SIGTERM)
            return
        await asyncio.sleep(CONTROL_PARENT_WATCH_SECONDS)


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
    "response_class": Response,
    "summary": Locale.PULL_SUMMARY,
    "description": Locale.PULL_DESCRIPTION,
    "responses": {
        status.HTTP_200_OK: {
            "description": Locale.PULL_RESPONSE_DESCRIPTION,
            "content": {
                MEDIA_TYPE: {
                    "example": (json.dumps(NULL_SUBMISSION_EXAMPLE, ensure_ascii=False) + "\n"),
                },
                MARKDOWN_MEDIA_TYPE: {
                    "example": Locale.VALIDATION_ERROR_DETAIL + "\n",
                },
            },
        },
        status.HTTP_410_GONE: {
            "description": "Accepted submission, followed by ground truth if available.",
            "content": {
                MEDIA_TYPE: {
                    "example": json.dumps(SUBMISSION_EXAMPLE, ensure_ascii=False) + "\n",
                },
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": Locale.CONFIGURATION_ERROR_DETAIL,
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Accepted submission is still being processed; retry after one second.",
            "headers": {
                RETRY_AFTER_HEADER: {
                    "schema": {"type": "string", "example": RETRY_AFTER_SECONDS},
                },
            },
        },
    },
}

PUSH_ROUTE: dict[str, Any] = {
    "path": PUSH_PATH,
    "response_class": Response,
    "status_code": status.HTTP_202_ACCEPTED,
    "summary": Locale.PUSH_SUMMARY,
    "description": Locale.PUSH_DESCRIPTION,
    "responses": {
        status.HTTP_202_ACCEPTED: {
            "description": Locale.PUSH_RESPONSE_DESCRIPTION,
            "headers": {
                LOCATION_HEADER: {
                    "schema": {"type": "string", "example": PULL_PATH},
                },
            },
        },
        status.HTTP_409_CONFLICT: {
            "description": (
                "A submission is already being processed, or the current pull must be "
                "retrieved before submitting."
            ),
            "headers": {
                LOCATION_HEADER: {
                    "schema": {"type": "string", "example": PULL_PATH},
                },
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": Locale.CONFIGURATION_ERROR_DETAIL,
        },
    },
    "openapi_extra": {
        "requestBody": {
            "required": True,
            "content": {JSON_MEDIA_TYPE: {"example": EVIDENCE_SUBMISSION_EXAMPLE}},
        }
    },
}

app = FastAPI(**APP_CONFIG)


class _RetryEvidenceObligation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    outcome: EvidenceOutcome
    excerpt: StrictStr | None = None
    url: StrictStr | None = None
    normalized_tokens: list[StrictStr] = Field(default_factory=list)


class _RetryFieldObligation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: StrictStr
    evidence: list[_RetryEvidenceObligation]
    accepted: bool


class _RetryObligations(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    fields: dict[StrictStr, _RetryFieldObligation]


class _EvidenceCandidateAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    ref_id: StrictStr
    call_id: StrictStr
    cite_text: StrictStr
    excerpt_position: int
    url: StrictStr


class _EvidenceItemAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: StrictStr
    index: int
    outcome: EvidenceOutcome
    excerpt: StrictStr | None
    url: StrictStr | None
    normalized_tokens: list[StrictStr]
    candidates: list[_EvidenceCandidateAudit]


class _EvidenceAttemptAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[_EvidenceItemAudit]


class _CodexTextResult(BaseModel):
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


class _PushConfigurationError(RuntimeError):
    pass


class _PushValidationError(RuntimeError):
    pass


class _EvidenceAssessmentError(_PushValidationError):
    def __init__(self, message: str, *, public_detail: str) -> None:
        self.public_detail = public_detail
        super().__init__(message)


class _MultipleEvidenceMatches(_PushValidationError):
    def __init__(self, excerpt: str) -> None:
        self.excerpt = excerpt
        super().__init__(Locale.MULTIPLE_EVIDENCE_MATCHES_TEMPLATE.format(excerpt=excerpt))


@dataclass(frozen=True)
class _PushConfiguration:
    rollout_guest_path: str
    rollout_relative_path: PurePosixPath
    appendwatch_report: PurePosixPath
    lima_ssh_config: Path
    identity_file: Path
    known_hosts_file: Path
    ssh_user: str
    ssh_target: str
    host_key_alias: str


@dataclass(frozen=True)
class _ArchivedFile:
    path: Path
    size: int
    sha256: str
    line_count: int


@dataclass(frozen=True)
class _RolloutRecord:
    line_number: int
    line_sha256: str
    value: dict[str, object]


@dataclass(frozen=True)
class _SessionMetadata:
    session_id: str
    timestamp: str
    rollout_filename: str
    summary_json: str


@dataclass(frozen=True)
class _CodexFcRow:
    timestamp: str
    fc_id: str
    call_id: str
    name: str
    namespace: str
    arguments_json: str


@dataclass(frozen=True)
class _CodexFcoRow:
    timestamp: str
    fco_id: str
    call_id: str


@dataclass(frozen=True)
class _CodexTurnRefRow:
    ref_id: str
    call_id: str
    domain: str | None
    snippet: str | None
    thumbnail_url: str | None
    title: str | None
    url: str
    cite_text: str


@dataclass(frozen=True)
class _RolloutIndex:
    session: _SessionMetadata
    fc_rows: tuple[_CodexFcRow, ...]
    fco_rows: tuple[_CodexFcoRow, ...]
    turn_ref_rows: tuple[_CodexTurnRefRow, ...]


@dataclass(frozen=True)
class _EvidenceMatch:
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
class _EvidenceCandidate:
    ref_id: str
    call_id: str
    cite_text: str
    excerpt_position: int
    url: str
    fco_timestamp: datetime
    arguments_json: object


@dataclass(frozen=True)
class _EvidenceItemAssessment:
    field: str
    index: int
    evidence_number: int
    submission: EvidenceSubmission
    outcome: EvidenceOutcome
    match: _EvidenceMatch | None
    normalized_tokens: tuple[str, ...] = ()
    candidates: tuple[_EvidenceCandidate, ...] = ()


@dataclass(frozen=True)
class _EvidenceAssessment:
    items: tuple[_EvidenceItemAssessment, ...]

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


class _CodexMatchProcedure:
    dataset_id_field = KTP_NAMEKEY_COL


ValidatedEvidence = dict[str, list[_EvidenceMatch]]
RUNTIME_CONFIGURATION: AiAugmentBackendContext | None = None


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


def _configuration_file(path: Path | None, setting: str) -> Path:
    if path is None:
        raise _PushConfigurationError(Locale.SETTING_REQUIRED_TEMPLATE.format(setting=setting))
    if not path.is_absolute():
        raise _PushConfigurationError(Locale.SETTING_ABSOLUTE_TEMPLATE.format(setting=setting))
    if path.is_symlink() or not path.is_file() or not os.access(path, os.R_OK):
        raise _PushConfigurationError(Locale.SETTING_READABLE_FILE_TEMPLATE.format(setting=setting))
    return path


def _configuration_guest_path(value: str, setting: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or not path.is_absolute()
        or str(path) != value
        or any(part in FORBIDDEN_NORMALIZED_PATH_PARTS for part in path.parts)
        or _has_control_character(value)
    ):
        raise _PushConfigurationError(Locale.SETTING_GUEST_PATH_TEMPLATE.format(setting=setting))
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
        raise _PushConfigurationError(
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
        raise _PushConfigurationError(
            Locale.CONFIGURED_RESOURCE_INVALID_TEMPLATE.format(
                resource_key=MAP_SUBSET_0_TO_BATCH_KEY
            )
        ) from exc


def _repair_incomplete_replay_log_tail(path: Path) -> None:
    try:
        with path.open("rb") as stream:
            value = stream.read()
        if not value or value.endswith(b"\n"):
            return
        previous_newline = value.rfind(b"\n")
        truncate_at = previous_newline + 1
        discarded_bytes = len(value) - truncate_at
        reply = input(
            Locale.REPLAY_LOG_TAIL_REPAIR_PROMPT_TEMPLATE.format(
                path=path,
                discarded_bytes=discarded_bytes,
            )
        )
        if reply.strip().casefold() not in OPERATOR_CONFIRMATIONS:
            raise _PushConfigurationError(Locale.REPLAY_LOG_TAIL_REPAIR_DECLINED)
        with path.open("r+b") as stream:
            stream.seek(truncate_at)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(path.parent)
    except (EOFError, OSError) as exc:
        raise _PushConfigurationError(Locale.REPLAY_LOG_TAIL_REPAIR_FAILED) from exc


def registered_replay_log(config: PipelineConfig) -> RegisteredResource:
    meta = config.files_config.get(REPLAY_LOG_RESOURCE_KEY)
    if meta is None:
        raise _PushConfigurationError(
            Locale.FILES_CONFIG_RESOURCE_MISSING_TEMPLATE.format(
                resource_key=REPLAY_LOG_RESOURCE_KEY
            )
        )
    try:
        path = Path(meta[RESOURCE_PATH_KEY])
        if path.is_symlink() or not path.is_file() or not os.access(path, os.R_OK | os.W_OK):
            raise OSError(Locale.REPLAY_LOG_UNREADABLE)
        _repair_incomplete_replay_log_tail(path)
        return register_resource(
            path,
            group=ResourceGroup.KTP_PIPELINE_ARTIFACT,
            fragment_type=FragmentType.LINE_NUMBER,
            description=meta[RESOURCE_DESCRIPTION_KEY],
        )
    except (KeyError, OSError, ValueError) as exc:
        raise _PushConfigurationError(
            Locale.CONFIGURED_RESOURCE_INVALID_TEMPLATE.format(resource_key=REPLAY_LOG_RESOURCE_KEY)
        ) from exc


def _configured_ai_augment_outerdict(
    configured_namekey: NameKey,
    outerdicts: Sequence[AiAugmentOuterDict],
) -> AiAugmentOuterDict:
    configured = next(
        (outerdict for outerdict in outerdicts if outerdict.namekey == configured_namekey),
        None,
    )
    if configured is not None:
        if configured.ai_augment_cohort is not AiAugmentCohort.INELIGIBLE:
            return configured
        category = configured.ai_augment_ineligibility_category
        if category is None:
            raise _PushConfigurationError(Locale.INELIGIBILITY_CATEGORY_UNKNOWN)
        raise _PushConfigurationError(
            Locale.CONFIGURED_NAMEKEY_INELIGIBLE_TEMPLATE.format(category=category.value)
        )

    stripped_identity = (
        configured_namekey.first_name.strip(),
        configured_namekey.last_name.strip(),
    )
    suggestions = sorted({
        outerdict.namekey.to_json_key()
        for outerdict in outerdicts
        if (
            outerdict.namekey.first_name.strip(),
            outerdict.namekey.last_name.strip(),
        )
        == stripped_identity
    })
    if suggestions:
        raise _PushConfigurationError(
            Locale.CONFIGURED_NAMEKEY_NOT_FOUND_SUGGESTIONS_TEMPLATE.format(
                suggestions=" or ".join(suggestions)
            )
        )
    raise _PushConfigurationError(Locale.CONFIGURED_NAMEKEY_NOT_FOUND)


def _configured_namekey() -> NameKey:
    raw_namekey = os.environ.get(NAMEKEY_ENV_NAME, "")
    if not _valid_nonblank(raw_namekey):
        raise _PushConfigurationError(
            Locale.NAMEKEY_NOT_SET_TEMPLATE.format(environment_name=NAMEKEY_ENV_NAME)
        )
    try:
        return NameKey.from_json_key(raw_namekey)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise _PushConfigurationError(Locale.CONFIGURED_NAMEKEY_MALFORMED) from exc


def configure_runtime(
    config_path: Path,
    *,
    require_namekey: bool = True,
) -> AiAugmentBackendContext:
    global RUNTIME_CONFIGURATION

    try:
        pipeline = AiAugmentDetourConfig.from_json(config_path)
    except (OSError, ValueError) as exc:
        raise _PushConfigurationError(
            Locale.CONFIG_INVALID_TEMPLATE.format(config_path=config_path)
        ) from exc
    if pipeline.output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise _PushConfigurationError(Locale.OUTPUT_FORMAT_INVALID)
    if not pipeline.db_file.is_file() or not os.access(pipeline.db_file, os.R_OK):
        raise _PushConfigurationError(
            Locale.SOURCE_DUCKDB_UNREADABLE_TEMPLATE.format(db_file=pipeline.db_file)
        )
    if pipeline.output_format == DOCX_OUTPUT_FORMAT and (
        not pipeline.pandoc_reference_docx.is_file()
        or not os.access(pipeline.pandoc_reference_docx, os.R_OK)
    ):
        raise _PushConfigurationError(Locale.DOCX_REFERENCE_UNREADABLE)
    try:
        ZoneInfo(pipeline.timezone)
    except (KeyError, ValueError) as exc:
        raise _PushConfigurationError(
            Locale.TIMEZONE_INVALID_TEMPLATE.format(timezone=pipeline.timezone)
        ) from exc

    configured_namekey = _configured_namekey() if require_namekey else None

    registered_replay_log(pipeline)
    pipeline.release_map = registered_release_map(pipeline)
    runtime = AiAugmentBackendContext(
        pipeline_config=pipeline,
        configured_namekey=configured_namekey,
    )
    try:
        ai_augment_outerdicts = runtime.ai_augment_outerdicts
        if configured_namekey is not None:
            _configured_ai_augment_outerdict(
                configured_namekey,
                ai_augment_outerdicts,
            )
    except ValueError as exc:
        raise _PushConfigurationError(str(exc)) from exc

    if pipeline.detour_db_path == pipeline.db_file:
        raise _PushConfigurationError(Locale.DETOUR_DB_EQUALS_SOURCE)
    RUNTIME_CONFIGURATION = runtime
    return RUNTIME_CONFIGURATION


def runtime_configuration() -> AiAugmentBackendContext:
    if RUNTIME_CONFIGURATION is None:
        raise _PushConfigurationError(
            Locale.API_CONFIG_REQUIRED_TEMPLATE.format(config_filename=CONFIG_FILENAME)
        )
    return RUNTIME_CONFIGURATION


def push_configuration(rollout_jsonl: str | None = None) -> _PushConfiguration:
    raw_rollout = ROLLOUT_JSONL if rollout_jsonl is None else rollout_jsonl
    if not raw_rollout.strip():
        raise _PushConfigurationError(
            Locale.ROLLOUT_NOT_SET_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
        )
    if raw_rollout != raw_rollout.strip() or _has_control_character(raw_rollout):
        raise _PushConfigurationError(
            Locale.ROLLOUT_WHITESPACE_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
        )

    rollout_path = PurePosixPath(raw_rollout)
    if str(rollout_path) != raw_rollout or any(
        part in FORBIDDEN_NORMALIZED_PATH_PARTS for part in rollout_path.parts
    ):
        raise _PushConfigurationError(
            Locale.ROLLOUT_NOT_NORMALIZED_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
        )
    try:
        relative_path = rollout_path.relative_to(CODEX_SESSIONS_ROOT)
    except ValueError as exc:
        raise _PushConfigurationError(
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
        raise _PushConfigurationError(
            Locale.ROLLOUT_FILENAME_INVALID_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
        )

    if not _valid_nonblank(AIVM_INSTANCE):
        raise _PushConfigurationError(Locale.AIVM_INSTANCE_INVALID)
    if not _valid_nonblank(AIVM_AUDIT_USER):
        raise _PushConfigurationError(Locale.AIVM_AUDIT_USER_INVALID)
    if not AIVM_SSH_PORT.isdecimal() or not MIN_TCP_PORT <= int(AIVM_SSH_PORT) <= MAX_TCP_PORT:
        raise _PushConfigurationError(Locale.AIVM_SSH_PORT_INVALID)

    return _PushConfiguration(
        rollout_guest_path=raw_rollout,
        rollout_relative_path=relative_path,
        appendwatch_report=_configuration_guest_path(
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
        ssh_user=AIVM_AUDIT_USER,
        ssh_target=f"{AIVM_INSTANCE}-{AIVM_AUDIT_USER}",
        host_key_alias=f"lima-{AIVM_INSTANCE}-{AIVM_AUDIT_USER}",
    )


def set_backend_session_id(value: str) -> None:
    global BACKEND_SESSION_ID

    normalized = value.strip()
    try:
        session_id = UUID(normalized)
    except ValueError as exc:
        raise _PushConfigurationError(Locale.SESSION_ID_STDIN_INVALID) from exc
    if str(session_id) != normalized:
        raise _PushConfigurationError(Locale.SESSION_ID_STDIN_INVALID)
    with BACKEND_WORKFLOW_STATE_LOCK:
        if BACKEND_SESSION_ID is not None and BACKEND_SESSION_ID != normalized:
            raise _PushConfigurationError(Locale.SESSION_ID_STDIN_CONFLICT)
        BACKEND_SESSION_ID = normalized


def read_backend_session_id(stream: Any = None) -> None:
    input_stream = sys.stdin if stream is None else stream
    value = input_stream.readline()
    if not value:
        raise _PushConfigurationError(Locale.SESSION_ID_STDIN_MISSING)
    set_backend_session_id(value)
    logger.info(Locale.SESSION_ID_STDIN_ACCEPTED_LOG, value.strip())


def start_backend_session_reader() -> threading.Thread:
    def read_or_fail() -> None:
        try:
            read_backend_session_id()
        except Exception as exc:
            logger.exception(Locale.SESSION_ID_STDIN_FAILED_LOG, exc)
            _mark_workflow_failed(exc)

    reader = threading.Thread(
        target=read_or_fail,
        name="detour-ai-augment-session-reader",
        daemon=True,
    )
    reader.start()
    return reader


def push_configuration_for_session(session_id: str) -> _PushConfiguration:
    placeholder = (
        CODEX_SESSIONS_ROOT / f"{ROLLOUT_FILENAME_PREFIX}{session_id}{ROLLOUT_FILENAME_SUFFIX}"
    )
    base = push_configuration(str(placeholder))
    options = _aivm_connection_options(
        lima_ssh_config=base.lima_ssh_config,
        identity_file=base.identity_file,
        known_hosts_file=base.known_hosts_file,
        ssh_user=base.ssh_user,
        host_key_alias=base.host_key_alias,
    )
    try:
        completed = subprocess.run(
            [
                SSH_EXECUTABLE,
                *options,
                "--",
                base.ssh_target,
                shlex.join([AUDIT_FIND_ROLLOUT_COMMAND, session_id]),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=SSH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _PushConfigurationError(Locale.ROLLOUT_DISCOVERY_FAILED) from exc
    matches = tuple(line for line in completed.stdout.splitlines() if line)
    if len(matches) != 1:
        raise _PushConfigurationError(Locale.ROLLOUT_DISCOVERY_NOT_UNIQUE)
    return push_configuration(matches[0])


def prove_workflow_inputs_readable() -> None:
    probe_rollout = CODEX_SESSIONS_ROOT / (
        f"{ROLLOUT_FILENAME_PREFIX}startup-readability-probe{ROLLOUT_FILENAME_SUFFIX}"
    )
    configuration = push_configuration(str(probe_rollout))
    try:
        _read_appendwatch_bytes(configuration)
    except _PushConfigurationError as exc:
        raise _PushConfigurationError(Locale.APPENDWATCH_REPORT_UNREADABLE) from exc
    logger.info(Locale.APPENDWATCH_READABLE_LOG, configuration.appendwatch_report)
    options = _aivm_connection_options(
        lima_ssh_config=configuration.lima_ssh_config,
        identity_file=configuration.identity_file,
        known_hosts_file=configuration.known_hosts_file,
        ssh_user=configuration.ssh_user,
        host_key_alias=configuration.host_key_alias,
    )
    try:
        subprocess.run(
            [
                SSH_EXECUTABLE,
                *options,
                "--",
                configuration.ssh_target,
                AUDIT_PROBE_COMMAND,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=SSH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _PushConfigurationError(Locale.CODEX_SESSIONS_UNREADABLE) from exc
    logger.info(Locale.CODEX_SESSIONS_READABLE_LOG, CODEX_SESSIONS_ROOT)


def _fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _archived_file(path: Path) -> _ArchivedFile:
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
    return _ArchivedFile(
        path=path,
        size=size,
        sha256=digest.hexdigest(),
        line_count=line_count,
    )


def _publish_archive(temporary: Path, destination: Path) -> _ArchivedFile:
    _fsync_file(temporary)
    os.replace(temporary, destination)
    _fsync_directory(destination.parent)
    return _archived_file(destination)


def _aivm_connection_options(
    *,
    lima_ssh_config: Path,
    identity_file: Path,
    known_hosts_file: Path,
    ssh_user: str,
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
        f"User={ssh_user}",
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


def copy_rollout_to_cas(
    configuration: _PushConfiguration,
    runtime: AiAugmentBackendContext,
) -> _ArchivedFile:
    runtime.pipeline_config.rollout_cas_dir.mkdir(parents=True, exist_ok=True)
    temporary = runtime.pipeline_config.rollout_cas_dir / ROLLOUT_CAS_TEMP_FILENAME_TEMPLATE.format(
        nonce=uuid7().hex
    )
    options = _aivm_connection_options(
        lima_ssh_config=configuration.lima_ssh_config,
        identity_file=configuration.identity_file,
        known_hosts_file=configuration.known_hosts_file,
        ssh_user=configuration.ssh_user,
        host_key_alias=configuration.host_key_alias,
    )
    command = [
        SSH_EXECUTABLE,
        *options,
        "--",
        configuration.ssh_target,
        shlex.join([
            AUDIT_READ_ROLLOUT_COMMAND,
            str(configuration.rollout_relative_path),
        ]),
    ]
    try:
        with temporary.open("wb") as output:
            subprocess.run(
                command,
                check=True,
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=AUDIT_COPY_TIMEOUT_SECONDS,
            )
        if not temporary.is_file() or temporary.is_symlink():
            raise _PushConfigurationError(Locale.AUDIT_ROLLOUT_ARCHIVE_INVALID)
        archived = _archived_file(temporary)
        destination = runtime.pipeline_config.rollout_cas_dir / ROLLOUT_CAS_FILENAME_TEMPLATE.format(
            sha256=archived.sha256
        )
        if destination.exists():
            existing = _archived_file(destination)
            if existing.sha256 != archived.sha256 or existing.size != archived.size:
                raise _PushConfigurationError(Locale.ROLLOUT_CAS_CONFLICT)
            return existing
        return _publish_archive(temporary, destination)
    except (OSError, subprocess.SubprocessError) as exc:
        raise _PushConfigurationError(Locale.ROLLOUT_COPY_FAILED) from exc
    finally:
        temporary.unlink(missing_ok=True)


def parse_appendwatch_report(
    report_path: Path,
    rollout_relative_path: PurePosixPath,
) -> None:
    try:
        report = report_path.read_bytes()
    except OSError as exc:
        raise _PushValidationError(Locale.APPENDWATCH_REPORT_UNREADABLE) from exc
    parse_appendwatch_report_bytes(report, rollout_relative_path)


def parse_appendwatch_report_bytes(
    report_bytes: bytes,
    rollout_relative_path: PurePosixPath,
) -> None:
    try:
        report = report_bytes.decode(TEXT_ENCODING)
    except UnicodeError as exc:
        raise _PushValidationError(Locale.APPENDWATCH_REPORT_UNREADABLE) from exc
    if not report.endswith("\n"):
        raise _PushValidationError(Locale.APPENDWATCH_REPORT_INCOMPLETE)

    lines = report.splitlines()
    if not lines or lines[0] != APPENDWATCH_ROOT_ENTRY:
        if lines and lines[0].startswith(APPENDWATCH_COMPROMISED_ROOT_PREFIX):
            raise _PushValidationError(Locale.APPENDWATCH_GLOBAL_DEGRADATION)
        raise _PushValidationError(Locale.APPENDWATCH_ROOT_MALFORMED)

    target = rollout_relative_path.parts
    match_target_by_filename = len(target) == 1
    directories: list[tuple[str, bool]] = []
    seen_paths: set[tuple[str, ...]] = set()
    target_entries: list[tuple[str, bool]] = []
    line_index = APPENDWATCH_TREE_START_INDEX

    while line_index < len(lines) and lines[line_index] != APPENDWATCH_BLANK_LINE:
        match = TREE_LINE.fullmatch(lines[line_index])
        if match is None:
            raise _PushValidationError(Locale.APPENDWATCH_TREE_LINE_MALFORMED)
        indent = match.group(TREE_INDENT_GROUP)
        depth = len(indent) // TREE_INDENT_WIDTH
        if depth > len(directories):
            raise _PushValidationError(Locale.APPENDWATCH_NESTING_INVALID)
        directories = directories[:depth]
        parent_parts = tuple(name for name, _compromised in directories)
        parent_compromised = any(compromised for _name, compromised in directories)
        body = match.group(TREE_BODY_GROUP)

        compromised_directory = APPENDWATCH_COMPROMISED_DIRECTORY_PATTERN.fullmatch(body)
        if compromised_directory is not None:
            name = compromised_directory.group(APPENDWATCH_NAME_GROUP)
            path = (*parent_parts, name)
            if path in seen_paths:
                raise _PushValidationError(Locale.APPENDWATCH_PATH_DUPLICATE)
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
                raise _PushValidationError(Locale.APPENDWATCH_DIRECTORY_MALFORMED)
            path = (*parent_parts, name)
            if path in seen_paths:
                raise _PushValidationError(Locale.APPENDWATCH_PATH_DUPLICATE)
            seen_paths.add(path)
            directories.append((name, parent_compromised))
            line_index += 1
            continue

        ok_file = APPENDWATCH_OK_FILE_PATTERN.fullmatch(body)
        compromised_file = APPENDWATCH_COMPROMISED_FILE_PATTERN.fullmatch(body)
        if ok_file is None and compromised_file is None:
            raise _PushValidationError(Locale.APPENDWATCH_FILE_ENTRY_MALFORMED)
        name = (ok_file or compromised_file).group(  # type: ignore[union-attr]
            APPENDWATCH_NAME_GROUP
        )
        path = (*parent_parts, name)
        if path in seen_paths:
            raise _PushValidationError(Locale.APPENDWATCH_PATH_DUPLICATE)
        seen_paths.add(path)
        if path == target or (match_target_by_filename and path[-1:] == target):
            target_entries.append((
                (APPENDWATCH_OK_STATUS if ok_file is not None else APPENDWATCH_COMPROMISED_STATUS),
                parent_compromised,
            ))
        line_index += 1

    if line_index < len(lines):
        if lines[line_index:] == [APPENDWATCH_BLANK_LINE]:
            raise _PushValidationError(Locale.APPENDWATCH_STRAY_BLANK_LINE)
        if lines[line_index : line_index + APPENDWATCH_REMOVED_SECTION_HEADER_LINES] != [
            APPENDWATCH_BLANK_LINE,
            APPENDWATCH_REMOVED_SECTION_HEADER,
        ]:
            raise _PushValidationError(Locale.APPENDWATCH_REMOVED_SECTION_MALFORMED)
        for removed_line in lines[line_index + APPENDWATCH_REMOVED_SECTION_HEADER_LINES :]:
            removed = APPENDWATCH_REMOVED_ENTRY_PATTERN.fullmatch(removed_line)
            if removed is None:
                raise _PushValidationError(Locale.APPENDWATCH_REMOVED_ENTRY_MALFORMED)
            removed_parts = PurePosixPath(removed.group(APPENDWATCH_PATH_GROUP)).parts
            if removed_parts == target or (
                match_target_by_filename and removed_parts[-1:] == target
            ):
                raise _PushValidationError(Locale.ROLLOUT_REMOVED_OR_REPLACED)

    if len(target_entries) != APPENDWATCH_EXPECTED_TARGET_ENTRIES:
        reason = (
            Locale.ROLLOUT_STATUS_MISSING if not target_entries else Locale.ROLLOUT_STATUS_AMBIGUOUS
        )
        raise _PushValidationError(Locale.ROLLOUT_STATUS_INVALID_TEMPLATE.format(reason=reason))
    status, compromised_ancestor = target_entries[0]
    if status != APPENDWATCH_OK_STATUS or compromised_ancestor:
        raise _PushValidationError(Locale.ROLLOUT_NOT_OK)


def parse_rollout(rollout_path: Path) -> tuple[_RolloutRecord, ...]:
    try:
        raw_lines = rollout_path.read_bytes().splitlines(keepends=True)
    except OSError as exc:
        raise _PushValidationError(Locale.ROLLOUT_UNREADABLE) from exc

    records: list[_RolloutRecord] = []
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
            raise _PushValidationError(
                Locale.ROLLOUT_JSONL_MALFORMED_TEMPLATE.format(line_number=line_number)
            ) from exc
        if not isinstance(value, dict):
            raise _PushValidationError(
                Locale.ROLLOUT_LINE_NON_OBJECT_TEMPLATE.format(line_number=line_number)
            )
        records.append(
            _RolloutRecord(
                line_number=line_number,
                line_sha256=hashlib.sha256(raw_line).hexdigest(),
                value=cast(dict[str, object], value),
            )
        )
    return tuple(records)


def _timestamp(value: object, *, label: str) -> str:
    if not _valid_nonblank(value):
        raise _PushValidationError(Locale.TIMESTAMP_INVALID_TEMPLATE.format(label=label))
    raw = cast(str, value)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _PushValidationError(Locale.TIMESTAMP_INVALID_TEMPLATE.format(label=label)) from exc
    if parsed.tzinfo is None:
        raise _PushValidationError(Locale.TIMESTAMP_TIMEZONE_MISSING_TEMPLATE.format(label=label))
    return raw


def _web_arguments(payload: Mapping[str, object], line_number: int) -> dict[str, object]:
    call_id = payload.get(CODEX_CALL_ID_KEY)
    if not _valid_nonblank(call_id):
        raise _PushValidationError(
            Locale.WEB_CALL_ID_INVALID_TEMPLATE.format(line_number=line_number)
        )
    arguments = payload.get(CODEX_ARGUMENTS_KEY)
    if not isinstance(arguments, str):
        raise _PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_UNSUPPORTED_TEMPLATE.format(call_id=call_id)
        )
    try:
        decoded: object = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise _PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_MALFORMED_TEMPLATE.format(call_id=call_id)
        ) from exc
    if not isinstance(decoded, dict):
        raise _PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_NON_OBJECT_TEMPLATE.format(call_id=call_id)
        )
    eligible_actions = [action for action in ELIGIBLE_WEB_ACTIONS if decoded.get(action)]
    if len(eligible_actions) != 1:
        raise _PushValidationError(Locale.WEB_CALL_ACTION_COUNT_TEMPLATE.format(call_id=call_id))
    return cast(dict[str, object], decoded)


def _session_metadata(
    records: tuple[_RolloutRecord, ...],
    *,
    timezone_name: str,
    configured_rollout_basename: str | None,
) -> _SessionMetadata:
    session_records = [
        record for record in records if record.value.get(CODEX_TYPE_KEY) == CODEX_SESSION_META_TYPE
    ]
    if len(session_records) != 1:
        raise _PushValidationError(Locale.SESSION_META_COUNT_INVALID)
    session_record = session_records[0]
    payload = session_record.value.get(CODEX_PAYLOAD_KEY)
    if not isinstance(payload, dict):
        raise _PushValidationError(Locale.SESSION_META_PAYLOAD_MALFORMED)
    session_id = payload.get(CODEX_SESSION_ID_KEY)
    if not _valid_nonblank(session_id):
        raise _PushValidationError(Locale.SESSION_META_SESSION_ID_INVALID)
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
        raise _PushValidationError(Locale.SESSION_META_ROLLOUT_MISMATCH)

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
        raise _PushValidationError(Locale.TURN_CONTEXT_MISSING)
    model = turn_context_payload.get(CODEX_MODEL_KEY)
    reasoning_effort = turn_context_payload.get(CODEX_REASONING_EFFORT_KEY)
    try:
        summary_json = CodexRolloutRecord.build_summary_json({
            CODEX_ORIGINATOR_KEY: payload.get(CODEX_ORIGINATOR_KEY),
            CODEX_SOURCE_FIELD: payload.get(CODEX_SOURCE_FIELD),
            CODEX_CLI_VERSION_KEY: payload.get(CODEX_CLI_VERSION_KEY),
            CODEX_MODEL_PROVIDER_KEY: payload.get(CODEX_MODEL_PROVIDER_KEY),
            CODEX_MODEL_KEY: model,
            SESSION_REASONING_EFFORT_KEY: reasoning_effort,
            CODEX_SESSION_ID_KEY: session_id,
            CODEX_TIMESTAMP_KEY: response_timestamp,
        })
    except ValidationError as exc:
        raise _PushValidationError(Locale.SESSION_META_FIELDS_INCOMPLETE) from exc
    return _SessionMetadata(
        session_id=session_id,
        timestamp=response_timestamp,
        rollout_filename=rollout_filename,
        summary_json=summary_json,
    )


def _eligible_fco_text(record: _RolloutRecord, payload: Mapping[str, object]) -> str | None:
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
        raise _PushValidationError(
            Locale.CITED_OUTPUT_BLOCK_INVALID_TEMPLATE.format(line_number=record.line_number)
        )
    return cast(str, output[0][CODEX_TEXT_KEY])


def build_rollout_index(
    records: tuple[_RolloutRecord, ...],
    *,
    timezone_name: str,
    configured_rollout_basename: str | None,
) -> _RolloutIndex:
    session = _session_metadata(
        records,
        timezone_name=timezone_name,
        configured_rollout_basename=configured_rollout_basename,
    )
    calls: dict[str, list[_RolloutRecord]] = {}
    events: dict[str, list[_RolloutRecord]] = {}
    cited_outputs: list[tuple[_RolloutRecord, dict[str, object], str]] = []

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
                raise _PushValidationError(
                    Locale.WEB_CALL_ID_INVALID_TEMPLATE.format(line_number=record.line_number)
                )
            calls.setdefault(cast(str, call_id), []).append(record)
        elif (
            value.get(CODEX_TYPE_KEY) == CODEX_EVENT_MESSAGE_TYPE
            and payload_type == CODEX_WEB_SEARCH_END_TYPE
        ):
            call_id = payload.get(CODEX_CALL_ID_KEY)
            if not _valid_nonblank(call_id):
                raise _PushValidationError(
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

    fc_rows: list[_CodexFcRow] = []
    fco_rows: list[_CodexFcoRow] = []
    turn_ref_rows: list[_CodexTurnRefRow] = []
    seen_fc_ids: set[str] = set()
    seen_fco_ids: set[str] = set()
    seen_call_ids: set[str] = set()
    for output_record, output_payload, output_text in cited_outputs:
        call_id = output_payload.get(CODEX_CALL_ID_KEY)
        fco_id = output_payload.get(CODEX_ID_KEY)
        if not _valid_nonblank(call_id) or not _valid_nonblank(fco_id):
            raise _PushValidationError(
                Locale.CITED_OUTPUT_IDS_INVALID_TEMPLATE.format(
                    line_number=output_record.line_number
                )
            )
        call_id = cast(str, call_id)
        fco_id = cast(str, fco_id)
        if call_id in seen_call_ids or fco_id in seen_fco_ids:
            raise _PushValidationError(Locale.CITED_OUTPUT_IDS_DUPLICATE)
        seen_call_ids.add(call_id)
        seen_fco_ids.add(fco_id)
        fco_timestamp = _timestamp(
            output_record.value.get(CODEX_TIMESTAMP_KEY),
            label=Locale.FUNCTION_OUTPUT_LABEL_TEMPLATE.format(fco_id=fco_id),
        )

        matching_calls = calls.get(call_id, [])
        matching_events = events.get(call_id, [])
        if len(matching_calls) != 1 or len(matching_events) != 1:
            raise _PushValidationError(
                Locale.CITED_WEB_CHAIN_COUNT_TEMPLATE.format(call_id=call_id)
            )
        call_record = matching_calls[0]
        event_record = matching_events[0]
        if not (call_record.line_number < event_record.line_number < output_record.line_number):
            raise _PushValidationError(
                Locale.CITED_WEB_CHAIN_ORDER_TEMPLATE.format(call_id=call_id)
            )
        call_payload = cast(
            dict[str, object],
            call_record.value[CODEX_PAYLOAD_KEY],
        )
        fc_id = call_payload.get(CODEX_ID_KEY)
        if not _valid_nonblank(fc_id) or cast(str, fc_id) in seen_fc_ids:
            raise _PushValidationError(
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
            _CodexFcRow(
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
            _CodexFcoRow(
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
            raise _PushValidationError(str(exc)) from exc
        event_payload = cast(
            dict[str, object],
            event_record.value[CODEX_PAYLOAD_KEY],
        )
        results = event_payload.get(CODEX_RESULTS_KEY)
        if not isinstance(results, list):
            raise _PushValidationError(
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
                raise _PushValidationError(
                    Locale.CITATION_RESULT_COUNT_TEMPLATE.format(ref_id=section.ref_id)
                )
            try:
                result = _CodexTextResult.model_validate(matching_results[0])
            except ValidationError as exc:
                raise _PushValidationError(
                    Locale.CITATION_RESULT_METADATA_UNSUPPORTED_TEMPLATE.format(
                        ref_id=section.ref_id
                    )
                ) from exc
            if not _valid_nonblank(result.url):
                continue
            turn_ref_rows.append(
                _CodexTurnRefRow(
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

    return _RolloutIndex(
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
            {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)} VARCHAR NOT NULL,
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
            {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)} VARCHAR NOT NULL,
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
            raise _PushValidationError(
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
    rollout_index: _RolloutIndex,
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
            raise _PushValidationError(Locale.PROVENANCE_PREFIX_OLDER)
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
            raise _PushValidationError(Locale.CITATION_PREFIX_OLDER)

        fc_by_call = {row.call_id: row for row in rollout_index.fc_rows}
        fco_by_call = {row.call_id: row for row in rollout_index.fco_rows}
        if set(fc_by_call) != current_call_ids or set(fco_by_call) != current_call_ids:
            raise _PushValidationError(Locale.ROLLOUT_LINKAGES_INCOMPLETE)
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
                    raise _PushValidationError(
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
                raise _PushValidationError(
                    Locale.PROVENANCE_INTEGRITY_QUERY_FAILED_TEMPLATE.format(table_name=table_name)
                )
            total, distinct = integrity_row
            if total != distinct:
                raise _PushValidationError(
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
            raise _PushValidationError(Locale.PROVENANCE_LINKAGE_QUERY_FAILED)
        missing_fc_links, missing_fco_links, missing_call_links = linkage_row
        if missing_fc_links or missing_fco_links or missing_call_links:
            raise _PushValidationError(Locale.PROVENANCE_RELATIONSHIPS_INCOMPLETE)

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
            raise _PushValidationError(Locale.PROVENANCE_PREFIX_MISMATCH)
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


def _evidence_candidates(rows: list[tuple[Any, ...]]) -> tuple[_EvidenceCandidate, ...]:
    candidates: list[_EvidenceCandidate] = []
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
            _EvidenceCandidate(
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
) -> tuple[_EvidenceCandidate, ...]:
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
) -> tuple[_EvidenceCandidate, ...]:
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
    candidate: _EvidenceCandidate,
    *,
    field: str,
    evidence_number: int,
    evidence: WebSearchExcerpt,
) -> _EvidenceMatch:
    arguments_json = candidate.arguments_json
    if not isinstance(arguments_json, str):
        arguments_json = json.dumps(
            arguments_json,
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
        )
    return _EvidenceMatch(
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
) -> _EvidenceAssessment:
    assessments: list[_EvidenceItemAssessment] = []
    evidence_number = 0
    for field, field_submission in submission.evidence_items():
        for index, evidence in enumerate(field_submission.web_search_excerpts):
            evidence_number += 1
            if isinstance(evidence, EvidenceWithdrawal):
                assessments.append(
                    _EvidenceItemAssessment(
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
                    raise _MultipleEvidenceMatches(evidence.excerpt)
                candidate = (
                    EVIDENCE_RANDOM.choice(exact_url_candidates)
                    if len(exact_url_candidates) > 1
                    else exact_url_candidates[0]
                )
                assessments.append(
                    _EvidenceItemAssessment(
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
            near_candidates: tuple[_EvidenceCandidate, ...] = ()
            if codex_match_version == 2:
                normalized_tokens = _normalized_evidence_tokens(conn, evidence.excerpt)
                near_candidates = _near_evidence_candidates(
                    conn,
                    rollout_filename=rollout_filename,
                    url=evidence.url,
                    submitted_tokens=normalized_tokens,
                )
            assessments.append(
                _EvidenceItemAssessment(
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
    return _EvidenceAssessment(items=tuple(assessments))


def _retry_evidence_obligation(
    item: _EvidenceItemAssessment,
) -> _RetryEvidenceObligation:
    if isinstance(item.submission, WebSearchExcerpt):
        excerpt = item.submission.excerpt
        url = item.submission.url
    else:
        excerpt = None
        url = None
    return _RetryEvidenceObligation(
        outcome=item.outcome,
        excerpt=excerpt,
        url=url,
        normalized_tokens=list(item.normalized_tokens),
    )


def _retry_obligations_from_assessment(
    submission: SubmissionPayload,
    assessment: _EvidenceAssessment,
) -> _RetryObligations:
    fields: dict[str, _RetryFieldObligation] = {}
    for field, field_submission in submission.evidence_items():
        evidence = [
            _retry_evidence_obligation(item) for item in assessment.items if item.field == field
        ]
        fields[field] = _RetryFieldObligation(
            value=field_submission.value,
            evidence=evidence,
            accepted=EVIDENCE_ITEMS_ACCEPTED_DEF(tuple(item.outcome for item in evidence)),
        )
    return _RetryObligations(fields=fields)


def _assessment_audit(assessment: _EvidenceAssessment) -> _EvidenceAttemptAudit:
    items: list[_EvidenceItemAudit] = []
    for item in assessment.items:
        if isinstance(item.submission, WebSearchExcerpt):
            excerpt = item.submission.excerpt
            url = item.submission.url
        else:
            excerpt = None
            url = None
        items.append(
            _EvidenceItemAudit(
                field=item.field,
                index=item.index,
                outcome=item.outcome,
                excerpt=excerpt,
                url=url,
                normalized_tokens=list(item.normalized_tokens),
                candidates=[
                    _EvidenceCandidateAudit(
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
    return _EvidenceAttemptAudit(items=items)


def _log_evidence_assessment(
    assessment: _EvidenceAssessment,
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
    assessment: _EvidenceAssessment,
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
            exact=assessment.exact_count,
            total=total,
        )
    ]
    non_exact_items = tuple(
        item for item in assessment.items if item.outcome != EVIDENCE_OUTCOME_V1_EXACT
    )
    if non_exact_items:
        lines.append(Locale.EVIDENCE_REVIEW_HEADER)
    for item in non_exact_items:
        location = EVIDENCE_LOCATION_DEF(item.field, item.index)
        if item.outcome == EVIDENCE_OUTCOME_V2_NEAR:
            lines.append(Locale.EVIDENCE_NEAR_ITEM_TEMPLATE.format(location=location))
        elif item.outcome == EVIDENCE_OUTCOME_UNMATCHED:
            lines.append(Locale.EVIDENCE_UNMATCHED_ITEM_TEMPLATE.format(location=location))
        elif item.outcome == EVIDENCE_OUTCOME_WITHDRAWN:
            lines.append(Locale.EVIDENCE_WITHDRAWN_ITEM_TEMPLATE.format(location=location))
    if violations:
        lines.append(
            Locale.EVIDENCE_RETRY_VIOLATION_HEADER
            if len(violations) == 1
            else Locale.EVIDENCE_RETRY_VIOLATIONS_HEADER_TEMPLATE.format(count=len(violations))
        )
        lines.extend(f"- {violation}" for violation in violations)
    lines.append(Locale.EVIDENCE_RETRY_INSTRUCTION)
    if include_retry_contract:
        lines.append(RETRY_SUBMISSION_PUBLIC_GUIDANCE)
    return "\n".join(lines)


def _obligation_item_is_unchanged(
    previous: _RetryEvidenceObligation,
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
    assessment: _EvidenceAssessment,
    previous: _RetryObligations,
) -> tuple[_RetryObligations, tuple[str, ...]]:
    next_fields: dict[str, _RetryFieldObligation] = {}
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

        next_evidence: list[_RetryEvidenceObligation] = []
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
        next_fields[field] = _RetryFieldObligation(
            value=field_submission.value,
            evidence=next_evidence,
            accepted=EVIDENCE_ITEMS_ACCEPTED_DEF(tuple(item.outcome for item in next_evidence)),
        )
    return _RetryObligations(fields=next_fields), tuple(violations)


def _assessment_from_audit(
    submission: StandardizedSubmission,
    audit: _EvidenceAttemptAudit,
) -> _EvidenceAssessment:
    submission_fields = dict(submission.evidence_items())
    items: list[_EvidenceItemAssessment] = []
    for evidence_number, audit_item in enumerate(audit.items, start=1):
        evidence = submission_fields[audit_item.field].web_search_excerpts[audit_item.index]
        items.append(
            _EvidenceItemAssessment(
                field=audit_item.field,
                index=audit_item.index,
                evidence_number=evidence_number,
                submission=evidence,
                outcome=audit_item.outcome,
                match=None,
                normalized_tokens=tuple(audit_item.normalized_tokens),
            )
        )
    return _EvidenceAssessment(items=tuple(items))


def _derive_retry_obligations(
    conn: duckdb.DuckDBPyConnection,
    *,
    baseline_json: str,
    baseline_attempt_id: str,
    run_id: str,
) -> _RetryObligations:
    try:
        obligations = _RetryObligations.model_validate_json(baseline_json)
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
                _EvidenceAttemptAudit.model_validate_json(cast(str, assessment_json)),
            )
            obligations, violations = _apply_retry_obligations(
                conn,
                submission,
                assessment,
                obligations,
            )
            if violations:
                raise _PushConfigurationError(Locale.EVIDENCE_AUDIT_REPLAY_FAILED)
        return obligations
    except (IndexError, KeyError, ValidationError) as exc:
        raise _PushConfigurationError(Locale.EVIDENCE_AUDIT_REPLAY_FAILED) from exc


def _process_retry_attempt(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: UUID,
    namekey: str,
    session_id: str,
    attempt_id: str,
    attempt_timestamp: datetime,
    submission: SubmissionPayload,
    assessment: _EvidenceAssessment,
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
                        {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)},
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
                        namekey,
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
                {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)},
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
                baseline_namekey,
                baseline_session_id,
                baseline_attempt_id,
                baseline_json,
            ) = baseline_row
            if baseline_namekey != namekey or baseline_session_id != session_id:
                raise _PushValidationError(Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH)
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
                    raise _PushConfigurationError(Locale.EVIDENCE_AUDIT_REPLAY_FAILED)
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
                {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)},
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
                namekey,
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
    namekey: str,
    session_id: str,
) -> bool:
    row = conn.execute(
        f"""
        SELECT
            {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)},
            {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)}
        FROM {CODEX_RETRY_BASELINE_TABLE}
        WHERE {duckdb_quote_identifier(CODEX_RETRY_RUN_ID_COL)} = ?
        """,
        [str(run_id)],
    ).fetchone()
    if row is None:
        return False
    if row != (namekey, session_id):
        raise _PushValidationError(Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH)
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
        raise _PushValidationError(Locale.EVIDENCE_WITHDRAWAL_WITHOUT_BASELINE)
    detail_template = (
        Locale.EVIDENCE_URL_MISMATCH_TEMPLATE
        if failed.candidates
        else Locale.EVIDENCE_NO_MATCH_TEMPLATE
    )
    raise _PushValidationError(
        detail_template.format(
            field=failed.field,
            excerpt=failed.submission.excerpt,
            url=failed.submission.url,
        )
    )


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


def _atomic_write_text(path: Path, value: str) -> None:
    temporary = path.with_name(
        ATOMIC_TEMP_FILENAME_TEMPLATE.format(
            filename=path.name,
            nonce=uuid7().hex,
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


def http_error_response_body(detail: str) -> str:
    return json.dumps(
        {"detail": detail},
        ensure_ascii=False,
        separators=COMPACT_JSON_SEPARATORS,
    )


def open_source_database(
    runtime: AiAugmentBackendContext,
) -> duckdb.DuckDBPyConnection:
    try:
        return duckdb.connect(str(runtime.pipeline_config.db_file), read_only=True)
    except duckdb.Error as exc:
        raise _PushValidationError(Locale.SOURCE_DUCKDB_OPEN_FAILED) from exc


def open_detour_database(
    runtime: AiAugmentBackendContext,
    *,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    conn: duckdb.DuckDBPyConnection | None = None
    try:
        if not read_only:
            runtime.pipeline_config.detour_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(
            str(runtime.pipeline_config.detour_db_path),
            read_only=read_only,
        )
        if runtime.pipeline_config.match_rule_version.codex_match == 2:
            load_duckdb_extension(
                conn,
                CODEX_TOKEN_EXTENSION,
                runtime.pipeline_config.duckdb_extensions.get(CODEX_TOKEN_EXTENSION),
                log=None,
            )
        return conn
    except (OSError, RuntimeError, duckdb.Error) as exc:
        if conn is not None:
            conn.close()
        detail = (
            Locale.DETOUR_DUCKDB_READ_ONLY_OPEN_FAILED
            if read_only
            else Locale.DETOUR_DUCKDB_OPEN_FAILED
        )
        raise _PushValidationError(detail) from exc


def _backend_detour_database(
    runtime: AiAugmentBackendContext,
) -> duckdb.DuckDBPyConnection:
    global DETOUR_DB_CONNECTION
    global DETOUR_DB_CONNECTION_PATH

    if (
        DETOUR_DB_CONNECTION is not None
        and DETOUR_DB_CONNECTION_PATH == runtime.pipeline_config.detour_db_path
    ):
        return DETOUR_DB_CONNECTION
    if DETOUR_DB_CONNECTION is not None:
        DETOUR_DB_CONNECTION.close()
    DETOUR_DB_CONNECTION = open_detour_database(runtime)
    DETOUR_DB_CONNECTION_PATH = runtime.pipeline_config.detour_db_path
    return DETOUR_DB_CONNECTION


def close_backend_detour_database() -> None:
    global DETOUR_DB_CONNECTION
    global DETOUR_DB_CONNECTION_PATH

    with DETOUR_DB_LOCK:
        connection = DETOUR_DB_CONNECTION
        DETOUR_DB_CONNECTION = None
        DETOUR_DB_CONNECTION_PATH = None
        if connection is not None:
            connection.close()


def _acquire_backend_process_lock() -> None:
    global BACKEND_PROCESS_LOCK_DESCRIPTOR

    if BACKEND_PROCESS_LOCK_DESCRIPTOR is not None:
        raise _PushConfigurationError(Locale.BACKEND_ALREADY_RUNNING)
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(BACKEND_PROCESS_LOCK_PATH, flags, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise _PushConfigurationError(Locale.BACKEND_ALREADY_RUNNING) from exc
    BACKEND_PROCESS_LOCK_DESCRIPTOR = descriptor


def _release_backend_process_lock() -> None:
    global BACKEND_PROCESS_LOCK_DESCRIPTOR

    descriptor = BACKEND_PROCESS_LOCK_DESCRIPTOR
    BACKEND_PROCESS_LOCK_DESCRIPTOR = None
    if descriptor is None:
        return
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _acquire_authoritative_process_lock(runtime: AiAugmentBackendContext) -> None:
    global AUTHORITATIVE_LOG_DESCRIPTOR

    if AUTHORITATIVE_LOG_DESCRIPTOR is not None:
        raise _PushConfigurationError(Locale.REPLAY_LOG_ALREADY_LOCKED)
    descriptor = os.open(Path(runtime.pipeline_config.replay_log), os.O_RDWR)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(descriptor)
        raise _PushConfigurationError(Locale.REPLAY_LOG_ALREADY_LOCKED) from exc
    AUTHORITATIVE_LOG_DESCRIPTOR = descriptor


def _release_authoritative_process_lock() -> None:
    global AUTHORITATIVE_LOG_DESCRIPTOR

    descriptor = AUTHORITATIVE_LOG_DESCRIPTOR
    AUTHORITATIVE_LOG_DESCRIPTOR = None
    if descriptor is None:
        return
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _projection_checkpoint(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[int, int, str] | None:
    row = conn.execute(
        f"SELECT {AUTHORITATIVE_PROJECTION_LINE_COLUMN}, "
        f"{AUTHORITATIVE_PROJECTION_OFFSET_COLUMN}, {AUTHORITATIVE_PROJECTION_HASH_COLUMN} "
        f"FROM {AUTHORITATIVE_PROJECTION_TABLE} "
        f"WHERE {AUTHORITATIVE_PROJECTION_ID_COLUMN} = ?",
        [AUTHORITATIVE_CHECKPOINT_ID],
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), int(row[1]), str(row[2])


def _write_projection_checkpoint(
    conn: duckdb.DuckDBPyConnection,
    *,
    line_number: int,
    byte_offset: int,
    line_sha256: str,
) -> None:
    conn.execute(
        f"INSERT OR REPLACE INTO {AUTHORITATIVE_PROJECTION_TABLE} VALUES (?, ?, ?, ?)",
        [
            AUTHORITATIVE_CHECKPOINT_ID,
            line_number,
            byte_offset,
            line_sha256,
        ],
    )


def _http_header_value(
    headers: Mapping[str, object] | None,
    name: str,
) -> str | None:
    if headers is None:
        return None
    normalized_name = name.casefold()
    for key, value in headers.items():
        if key.casefold() == normalized_name and isinstance(value, str):
            return value
    return None


def _request_body_for_authoritative_log(body: bytes) -> str:
    try:
        return body.decode(TEXT_ENCODING)
    except UnicodeDecodeError:
        return json.dumps(
            {
                AUTHORITATIVE_LOG_ENCODING_KEY: AUTHORITATIVE_LOG_BASE64_ENCODING,
                AUTHORITATIVE_LOG_DATA_KEY: base64.b64encode(body).decode(BASE64_TEXT_ENCODING),
            },
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
        )


def _authoritative_http_record(
    request: Request,
    *,
    request_body: bytes,
    response_code: int,
    response_headers: Mapping[str, str],
    response_body: bytes,
    started_ns: int,
    ready_to_respond_at_unix_usec: int,
) -> HttpRequestLogRecord:
    try:
        response_text = response_body.decode(TEXT_ENCODING)
    except UnicodeDecodeError as exc:
        raise _PushConfigurationError(Locale.AUTHORITATIVE_RESPONSE_NOT_UTF8) from exc
    return HttpRequestLogRecord(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        method=request.method,
        scheme=request.url.scheme,
        host=request.url.hostname or "",
        port=request.url.port,
        ready_to_respond_at_unix_usec=ready_to_respond_at_unix_usec,
        path=request.url.path,
        query=request.url.query,
        request_headers=dict(request.headers),
        request_body=_request_body_for_authoritative_log(request_body),
        response_code=response_code,
        response_headers=dict(response_headers),
        response_body=response_text,
        received_at_unix_usec=None,
        duration_usec=(time.monotonic_ns() - started_ns) // NANOSECONDS_PER_MICROSECOND,
    )


class _AuthoritativeHttpMiddleware:
    """Durably record finite public exchanges before forwarding ASGI responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope[ASGI_TYPE_KEY] != ASGI_HTTP_SCOPE_TYPE:
            await self.app(scope, receive, send)
            return
        method = cast(str, scope[ASGI_METHOD_KEY])
        path = cast(str, scope[ASGI_PATH_KEY])
        route = (method, path)
        if route not in AUTHORITATIVE_FASTAPI_ROUTES:
            await self.app(scope, receive, send)
            return

        started_ns = time.monotonic_ns()
        request = Request(scope, receive=receive)
        request_body = await request.body()
        request_body_pending = True
        response_messages: list[Message] = []

        async def replay_request_body() -> Message:
            nonlocal request_body_pending
            if request_body_pending:
                request_body_pending = False
                return {
                    ASGI_TYPE_KEY: ASGI_HTTP_REQUEST_MESSAGE_TYPE,
                    ASGI_BODY_KEY: request_body,
                    ASGI_MORE_BODY_KEY: False,
                }
            return await receive()

        async def capture_response(message: Message) -> None:
            response_messages.append(message)

        async def replace_response(response: Response) -> None:
            response_messages.clear()
            await response(scope, replay_request_body, capture_response)

        try:
            if not AUTHORITATIVE_BACKEND_HEALTHY:
                logger.error(Locale.AUTHORITATIVE_BACKEND_UNHEALTHY_LOG, method, path)
                await replace_response(
                    JSONResponse(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        content={"detail": Locale.CONFIGURATION_ERROR_DETAIL},
                    )
                )
            else:
                await self.app(scope, replay_request_body, capture_response)
        except Exception:
            logger.exception(Locale.AUTHORITATIVE_HANDLER_FAILED_LOG, method, path)
            await replace_response(
                JSONResponse(
                    status_code=HTTP_INTERNAL_ERROR_RESPONSE,
                    content={"detail": Locale.CONFIGURATION_ERROR_DETAIL},
                )
            )

        response_start = tuple(
            message
            for message in response_messages
            if message[ASGI_TYPE_KEY] == ASGI_HTTP_RESPONSE_START_MESSAGE_TYPE
        )
        response_chunks = tuple(
            message
            for message in response_messages
            if message[ASGI_TYPE_KEY] == ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE
        )
        if (
            len(response_start) != 1
            or not response_chunks
            or response_chunks[-1].get(ASGI_MORE_BODY_KEY, False)
        ):
            logger.error(Locale.AUTHORITATIVE_RESPONSE_INCOMPLETE_LOG, method, path)
            await replace_response(
                JSONResponse(
                    status_code=HTTP_INTERNAL_ERROR_RESPONSE,
                    content={"detail": Locale.CONFIGURATION_ERROR_DETAIL},
                )
            )
            response_start = tuple(
                message
                for message in response_messages
                if message[ASGI_TYPE_KEY] == ASGI_HTTP_RESPONSE_START_MESSAGE_TYPE
            )
            response_chunks = tuple(
                message
                for message in response_messages
                if message[ASGI_TYPE_KEY] == ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE
            )

        start_message = response_start[0]
        response_body = b"".join(
            cast(bytes, message.get(ASGI_BODY_KEY, b"")) for message in response_chunks
        )
        response_headers = Headers(
            raw=cast(list[tuple[bytes, bytes]], start_message[ASGI_HEADERS_KEY])
        )
        ready_to_respond_at_unix_usec = time.time_ns() // NANOSECONDS_PER_MICROSECOND
        try:
            record = _authoritative_http_record(
                request,
                request_body=request_body,
                response_code=cast(int, start_message[ASGI_STATUS_KEY]),
                response_headers=dict(response_headers.items()),
                response_body=response_body,
                started_ns=started_ns,
                ready_to_respond_at_unix_usec=ready_to_respond_at_unix_usec,
            )
            append_authoritative_record(record)
            await _after_authoritative_public_record(record)
        except Exception as exc:
            logger.exception(Locale.AUTHORITATIVE_LOG_APPEND_FAILED_LOG, method, path, exc)
            raise SystemExit(1) from exc

        for message in response_messages:
            await send(message)


app.add_middleware(_AuthoritativeHttpMiddleware)


def _initialize_readme_authoritative_schema(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    conn.execute(CREATE_AUTHORITATIVE_RECORDS_TABLE_SQL)
    conn.execute(CREATE_AUTHORITATIVE_OUTCOMES_TABLE_SQL)
    conn.execute(CREATE_AUTHORITATIVE_PROJECTION_TABLE_SQL)


def _validated_readme_record(record: HttpRequestLogRecord) -> HttpRequestLogRecord:
    validated = HttpRequestLogRecord.model_validate_json(record.model_dump_json())
    if (
        validated.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
        or validated.record_id.version != 7
    ):
        raise _PushValidationError(Locale.REPLAY_RECORD_CONTOUR_INVALID)
    route = (validated.method, validated.path)
    if route != AUTHORITATIVE_COMMIT_ROUTE:
        if (
            validated.response_code is None
            or validated.response_headers is None
            or validated.response_body is None
            or validated.ready_to_respond_at_unix_usec is None
            or validated.duration_usec is None
        ):
            raise _PushValidationError(Locale.REPLAY_RECORD_CONTOUR_INVALID)
        return validated
    if (
        validated.scheme != SYNTHETIC_COMMIT_SCHEME
        or validated.host != SYNTHETIC_COMMIT_HOST
        or validated.port is not None
        or validated.ready_to_respond_at_unix_usec is not None
        or validated.query
        or set(validated.request_headers) != {SOURCE_KEY_HEADER, NAME_KEY_HEADER}
        or not isinstance(validated.request_body, str)
        or validated.response_code is not None
        or validated.response_headers is not None
        or validated.response_body is not None
        or validated.received_at_unix_usec is not None
        or validated.duration_usec is not None
    ):
        raise _PushValidationError(Locale.REPLAY_COMMIT_INVALID)
    try:
        CommitRequestBody.validate_serialized_json(validated.request_body)
    except (ValidationError, ValueError) as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_INVALID) from exc
    return validated


def _commit_request_body(
    conn: duckdb.DuckDBPyConnection,
    value: object,
) -> CommitRequestBody:
    if not isinstance(value, str):
        raise _PushValidationError(Locale.REPLAY_COMMIT_INVALID)
    try:
        return CommitRequestBody.from_serialized_json(
            value,
            resolve_http_record=lambda record_id: _projected_http_record(
                conn,
                record_id,
            )[1],
        )
    except (KeyError, ValidationError, ValueError) as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_INVALID) from exc


def _backend_commit_record(
    conn: duckdb.DuckDBPyConnection,
    record: HttpRequestLogRecord,
) -> BackendCommitRecord:
    try:
        return BackendCommitRecord.from_http_request_log_record(
            record,
            resolve_http_record=lambda record_id: _projected_http_record(
                conn,
                record_id,
            )[1],
        )
    except (KeyError, ValidationError, ValueError) as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_INVALID) from exc


def _authoritative_log_records(
    path: Path,
) -> tuple[tuple[HttpRequestLogRecord, int, str], ...]:
    records: list[tuple[HttpRequestLogRecord, int, str]] = []
    byte_offset = AUTHORITATIVE_EMPTY_OFFSET
    try:
        with path.open("rb") as stream:
            for line_number, line in enumerate(stream, start=AUTHORITATIVE_FIRST_LINE):
                if not line.endswith(b"\n") or not line.strip():
                    raise _PushValidationError(
                        Locale.REPLAY_LOG_LINE_INVALID_TEMPLATE.format(line_number=line_number)
                    )
                try:
                    record = _validated_readme_record(
                        HttpRequestLogRecord.model_validate_json(line)
                    )
                except (ValidationError, _PushValidationError) as exc:
                    raise _PushValidationError(
                        Locale.REPLAY_LOG_LINE_INVALID_TEMPLATE.format(line_number=line_number)
                    ) from exc
                byte_offset += len(line)
                records.append((record, byte_offset, hashlib.sha256(line).hexdigest()))
    except (OSError, UnicodeError) as exc:
        raise _PushConfigurationError(Locale.REPLAY_LOG_UNREADABLE) from exc
    return tuple(records)


def _projected_http_record(
    conn: duckdb.DuckDBPyConnection,
    record_id: UUID,
) -> tuple[int, HttpRequestLogRecord]:
    row = conn.execute(
        f"SELECT {AUTHORITATIVE_RECORD_ORDINAL_COLUMN}, "
        f"{AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
        f"FROM {AUTHORITATIVE_RECORDS_TABLE} "
        f"WHERE {AUTHORITATIVE_RECORD_ID_COLUMN} = ?",
        [str(record_id)],
    ).fetchone()
    if row is None:
        raise _PushValidationError(Locale.REPLAY_COMMIT_LINK_MISSING)
    try:
        return int(row[0]), HttpRequestLogRecord.model_validate_json(str(row[1]))
    except ValidationError as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_LINK_MISSING) from exc


def _source_key_header(filename: str, line_count: int) -> str:
    return source_key_header_value(filename, line_count)


def _parse_source_key_header(value: object) -> tuple[str, int]:
    try:
        return source_key_from_header_value(value)
    except ValueError as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_SOURCE_KEY_INVALID) from exc


def _name_key_header(namekey: str) -> str:
    return name_key_header_value(NameKey.from_json_key(namekey))


def name_key_header(namekey: str) -> str:
    return _name_key_header(namekey)


def _parse_name_key_header(value: object) -> str:
    try:
        return name_key_from_header_value(value).to_json_key()
    except ValueError as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_NAME_KEY_INVALID) from exc


def parse_name_key_header(value: object) -> str:
    return _parse_name_key_header(value)


def parse_source_key_header(value: object) -> tuple[str, int]:
    return _parse_source_key_header(value)


def _response_content_type(record: HttpRequestLogRecord) -> str:
    return (
        (
            _http_header_value(
                record.response_headers,
                HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_HEADER,
            )
            or ""
        )
        .partition(";")[0]
        .strip()
        .casefold()
    )


def _root_pull_record_id(
    conn: duckdb.DuckDBPyConnection,
    pull_record_id: UUID,
) -> UUID:
    pull_ordinal, pull = _projected_http_record(conn, pull_record_id)
    if (pull.method, pull.path) != (HTTP_GET_METHOD, PULL_PATH):
        raise _PushValidationError(Locale.REPLAY_COMMIT_PULL_INVALID)
    if _response_content_type(pull) != MARKDOWN_MEDIA_TYPE:
        return pull_record_id
    row = conn.execute(
        f"SELECT records.{AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
        f"FROM {AUTHORITATIVE_RECORDS_TABLE} AS records "
        f"JOIN {AUTHORITATIVE_OUTCOMES_TABLE} AS outcomes "
        f"ON records.{AUTHORITATIVE_RECORD_ID_COLUMN} = "
        f"outcomes.{AUTHORITATIVE_OUTCOME_COMMIT_ID_COLUMN} "
        f"WHERE records.{AUTHORITATIVE_RECORD_ORDINAL_COLUMN} < ? "
        f"ORDER BY records.{AUTHORITATIVE_RECORD_ORDINAL_COLUMN} DESC LIMIT 1",
        [pull_ordinal],
    ).fetchone()
    if row is None:
        raise _PushValidationError(Locale.REPLAY_COMMIT_PULL_INVALID)
    try:
        prior_record = HttpRequestLogRecord.model_validate_json(str(row[0]))
        if prior_record.request_body is None:
            raise _PushValidationError(Locale.REPLAY_COMMIT_PULL_INVALID)
        prior_pull_record_id, _prior_push_record_id = (
            CommitRequestBody.record_ids_from_serialized_json(prior_record.request_body)
        )
    except (ValidationError, ValueError) as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_PULL_INVALID) from exc
    return _root_pull_record_id(conn, prior_pull_record_id)


def _namekey_from_pull(
    conn: duckdb.DuckDBPyConnection,
    pull_record_id: UUID,
) -> str:
    root_record_id = _root_pull_record_id(conn, pull_record_id)
    _ordinal, pull = _projected_http_record(conn, root_record_id)
    if (
        pull.response_code != status.HTTP_200_OK
        or _response_content_type(pull) != MEDIA_TYPE
        or not pull.response_body
    ):
        raise _PushValidationError(Locale.REPLAY_COMMIT_PULL_INVALID)
    try:
        lines = tuple(json.loads(line) for line in pull.response_body.splitlines())
        identity = next(
            line
            for line in reversed(lines)
            if isinstance(line, dict) and KTP_FIRST_NAME_COL in line and KTP_LAST_NAME_COL in line
        )
        return NameKey(**{
            KTP_FIRST_NAME_COL: identity[KTP_FIRST_NAME_COL],
            KTP_LAST_NAME_COL: identity[KTP_LAST_NAME_COL],
        }).to_json_key()
    except (StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_PULL_INVALID) from exc


def _validated_replay_rollout(
    runtime: AiAugmentBackendContext,
    reference: CodexRolloutRecord,
) -> _ArchivedFile:
    path = runtime.pipeline_config.rollout_cas_dir / ROLLOUT_CAS_FILENAME_TEMPLATE.format(
        sha256=reference.sha256
    )
    if (
        path.parent != runtime.pipeline_config.rollout_cas_dir
        or path.is_symlink()
        or not path.is_file()
    ):
        raise _PushValidationError(Locale.ROLLOUT_CAS_BLOB_INVALID)
    archived = _archived_file(path)
    if (
        archived.sha256 != reference.sha256
        or archived.size != reference.size
        or archived.line_count != reference.line_count
    ):
        raise _PushValidationError(Locale.ROLLOUT_CAS_BLOB_INVALID)
    return archived


def _failed_prepared_pull_response(
    *,
    commit_record_id: UUID,
    stage: PostCommitValidationStage,
    error: Exception,
) -> PreparedPullResponse:
    logger.error(Locale.POST_COMMIT_VALIDATION_FAILED_LOG, commit_record_id, stage, error)
    detail = Locale.CONFIGURATION_ERROR_DETAIL
    return PreparedPullResponse(
        commit_record_id=commit_record_id,
        post_commit_validation=PostCommitValidation(
            stage=stage,
            result=PostCommitValidationResult.CONFIGURATION_ERROR,
            detail=detail,
        ),
        response_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        response_headers={
            HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_HEADER: JSON_MEDIA_TYPE,
        },
        response_body=http_error_response_body(detail),
    )


def _prepared_pull_response_from_validation(
    *,
    record: HttpRequestLogRecord,
    post_commit_validation: PostCommitValidation,
    accepted_response_body: str = "",
) -> PreparedPullResponse:
    if post_commit_validation.result is PostCommitValidationResult.ACCEPTED:
        response_code = status.HTTP_410_GONE
        response_headers = {
            HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_HEADER: MEDIA_TYPE_WITH_CHARSET,
        }
        response_body = accepted_response_body
    elif (
        post_commit_validation.result is PostCommitValidationResult.REJECTED
        and post_commit_validation.stage
        in {
            PostCommitValidationStage.PYDANTIC_VALIDATION,
            PostCommitValidationStage.DUCKDB_EVIDENCE_VALIDATION,
        }
    ):
        response_code = status.HTTP_200_OK
        response_headers = {
            HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_HEADER: MARKDOWN_MEDIA_TYPE,
        }
        response_body = (
            post_commit_validation.detail or Locale.VALIDATION_ERROR_DETAIL
        ).rstrip() + "\n"
    else:
        response_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        response_headers = {
            HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_HEADER: JSON_MEDIA_TYPE,
        }
        response_body = http_error_response_body(Locale.CONFIGURATION_ERROR_DETAIL)
    return PreparedPullResponse(
        commit_record_id=record.record_id,
        post_commit_validation=post_commit_validation,
        response_code=response_code,
        response_headers=response_headers,
        response_body=response_body,
    )


def _validate_projected_commit(
    conn: duckdb.DuckDBPyConnection,
    runtime: AiAugmentBackendContext,
    record: HttpRequestLogRecord,
    *,
    materialize_files: bool,
) -> tuple[PreparedPullResponse, bool]:
    stage = PostCommitValidationStage.CONFIGURATION
    try:
        commit_record = _backend_commit_record(conn, record)
        commit = commit_record.commit_request_body
        pull = commit.pull_record
        push = commit.push_record
        session_id = commit.codex_session_record.session_id
        rollout = commit.codex_session_record.codex_rollout_record
        appendwatch_report = commit.codex_session_record.appendwatch_report_record
        assert session_id is not None
        assert rollout is not None
        assert appendwatch_report is not None
        namekey = NameKey.from_json_key(
            _parse_name_key_header(record.request_headers.get(NAME_KEY_HEADER))
        )
        pull_ordinal, _pull = _projected_http_record(conn, pull.record_id)
        push_ordinal, _push = _projected_http_record(conn, push.record_id)
        commit_ordinal, _commit_record = _projected_http_record(conn, record.record_id)
        if not (
            pull_ordinal < push_ordinal < commit_ordinal
            and (pull.method, pull.path) == (HTTP_GET_METHOD, PULL_PATH)
            and pull.response_code == status.HTTP_200_OK
            and (push.method, push.path) == (HTTP_POST_METHOD, PUSH_PATH)
            and push.response_code == status.HTTP_202_ACCEPTED
            and isinstance(push.request_body, str)
        ):
            raise _PushValidationError(Locale.REPLAY_COMMIT_LINK_INVALID)
        if _namekey_from_pull(conn, pull.record_id) != namekey.to_json_key():
            raise _PushValidationError(Locale.REPLAY_COMMIT_NAME_KEY_INVALID)
        filename, source_line_count = _parse_source_key_header(
            record.request_headers.get(SOURCE_KEY_HEADER)
        )
        if source_line_count != rollout.line_count:
            raise _PushValidationError(Locale.REPLAY_COMMIT_SOURCE_KEY_INVALID)
        stage = PostCommitValidationStage.ROLLOUT_INDEX
        rollout_archive = _validated_replay_rollout(runtime, rollout)
        stage = PostCommitValidationStage.APPENDWATCH_REPORT_VALIDATION
        prepared_pull_response, commit_database = _execute_attempt(
            conn,
            runtime,
            commit_record=commit_record,
            rollout_archive=rollout_archive,
            appendwatch_report=appendwatch_report,
            rollout_relative_path=PurePosixPath(filename),
            run_id=_root_pull_record_id(conn, pull.record_id),
            namekey=namekey,
            materialize_files=materialize_files,
        )
        return prepared_pull_response, commit_database
    except Exception as exc:
        return (
            _failed_prepared_pull_response(
                commit_record_id=record.record_id,
                stage=stage,
                error=exc,
            ),
            False,
        )


def _insert_projected_http_record(
    conn: duckdb.DuckDBPyConnection,
    record: HttpRequestLogRecord,
    *,
    line_number: int,
) -> None:
    conn.execute(
        f"INSERT INTO {AUTHORITATIVE_RECORDS_TABLE} VALUES (?, ?, ?, ?, ?)",
        [
            line_number,
            str(record.record_id),
            record.method,
            record.path,
            record.model_dump_json(),
        ],
    )


def _insert_prepared_pull_response(
    conn: duckdb.DuckDBPyConnection,
    record: HttpRequestLogRecord,
    prepared_pull_response: PreparedPullResponse,
) -> None:
    conn.execute(
        f"INSERT INTO {AUTHORITATIVE_OUTCOMES_TABLE} VALUES (?, ?)",
        [str(record.record_id), prepared_pull_response.model_dump_json()],
    )


def _project_readme_record(
    conn: duckdb.DuckDBPyConnection,
    runtime: AiAugmentBackendContext,
    record: HttpRequestLogRecord,
    *,
    line_number: int,
    byte_offset: int,
    line_sha256: str,
    materialize_files: bool,
) -> None:
    conn.execute("BEGIN TRANSACTION")
    try:
        _insert_projected_http_record(
            conn,
            record,
            line_number=line_number,
        )
        if (record.method, record.path) == AUTHORITATIVE_COMMIT_ROUTE:
            prepared_pull_response, commit_database = _validate_projected_commit(
                conn,
                runtime,
                record,
                materialize_files=materialize_files,
            )
            if not commit_database:
                conn.execute("ROLLBACK")
                conn.execute("BEGIN TRANSACTION")
                _insert_projected_http_record(
                    conn,
                    record,
                    line_number=line_number,
                )
            _insert_prepared_pull_response(
                conn,
                record,
                prepared_pull_response,
            )
        _write_projection_checkpoint(
            conn,
            line_number=line_number,
            byte_offset=byte_offset,
            line_sha256=line_sha256,
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _synchronize_authoritative_projection_locked(
    runtime: AiAugmentBackendContext,
    conn: duckdb.DuckDBPyConnection,
) -> None:
    global AUTHORITATIVE_BACKEND_HEALTHY
    global AUTHORITATIVE_LOG_OFFSET
    global AUTHORITATIVE_NEXT_LINE_NUMBER

    try:
        records = _authoritative_log_records(Path(runtime.pipeline_config.replay_log))
        runtime.pipeline_config.rollout_cas_dir.mkdir(parents=True, exist_ok=True)
        _initialize_readme_authoritative_schema(conn)
        checkpoint = _projection_checkpoint(conn)
        projected_count_row = conn.execute(
            f"SELECT count(*) FROM {AUTHORITATIVE_RECORDS_TABLE}"
        ).fetchone()
        projected_count = 0 if projected_count_row is None else int(projected_count_row[0])
        if checkpoint is None:
            if projected_count:
                raise _PushConfigurationError(Locale.REPLAY_PROJECTION_CONFLICT)
            projected_line_count = 0
        else:
            projected_line_count, byte_offset, line_sha256 = checkpoint
            if projected_line_count != projected_count or projected_line_count > len(records):
                raise _PushConfigurationError(Locale.REPLAY_PROJECTION_CONFLICT)
            if projected_line_count:
                _, expected_offset, expected_hash = records[projected_line_count - 1]
                if byte_offset != expected_offset or line_sha256 != expected_hash:
                    raise _PushConfigurationError(Locale.REPLAY_PROJECTION_CONFLICT)
        for line_number, (record, byte_offset, line_sha256) in enumerate(
            records[projected_line_count:],
            start=projected_line_count + AUTHORITATIVE_FIRST_LINE,
        ):
            _project_readme_record(
                conn,
                runtime,
                record,
                line_number=line_number,
                byte_offset=byte_offset,
                line_sha256=line_sha256,
                materialize_files=False,
            )
        AUTHORITATIVE_NEXT_LINE_NUMBER = len(records) + AUTHORITATIVE_FIRST_LINE
        AUTHORITATIVE_LOG_OFFSET = records[-1][1] if records else AUTHORITATIVE_EMPTY_OFFSET
        AUTHORITATIVE_BACKEND_HEALTHY = True
    except Exception as exc:
        AUTHORITATIVE_BACKEND_HEALTHY = False
        raise _PushConfigurationError(Locale.REPLAY_PROJECTION_FAILED) from exc


def synchronize_authoritative_projection(runtime: AiAugmentBackendContext) -> None:
    with DETOUR_DB_LOCK:
        conn = _backend_detour_database(runtime)
        _synchronize_authoritative_projection_locked(runtime, conn)


@contextmanager
def synchronized_detour_database(
    runtime: AiAugmentBackendContext,
) -> Iterator[duckdb.DuckDBPyConnection]:
    with DETOUR_DB_LOCK:
        conn = _backend_detour_database(runtime)
        _synchronize_authoritative_projection_locked(runtime, conn)
        yield conn


def append_authoritative_record(record: HttpRequestLogRecord) -> None:
    global AUTHORITATIVE_BACKEND_HEALTHY
    global AUTHORITATIVE_LOG_OFFSET
    global AUTHORITATIVE_NEXT_LINE_NUMBER

    validated = _validated_readme_record(record)
    line = (validated.model_dump_json(ensure_ascii=True) + "\n").encode(TEXT_ENCODING)
    line_sha256 = hashlib.sha256(line).hexdigest()
    with AUTHORITATIVE_APPEND_LOCK:
        try:
            runtime = runtime_configuration()
            with DETOUR_DB_LOCK:
                conn = _backend_detour_database(runtime)
                _synchronize_authoritative_projection_locked(runtime, conn)
                descriptor = AUTHORITATIVE_LOG_DESCRIPTOR
                if descriptor is None:
                    raise _PushConfigurationError(Locale.AUTHORITATIVE_LOG_NOT_OPEN)
                end_offset = os.lseek(descriptor, AUTHORITATIVE_EMPTY_OFFSET, os.SEEK_END)
                if end_offset != AUTHORITATIVE_LOG_OFFSET:
                    raise _PushConfigurationError(Locale.REPLAY_PROJECTION_CONFLICT)
                written = 0
                while written < len(line):
                    count = os.write(descriptor, line[written:])
                    if count <= 0:
                        raise OSError(Locale.AUTHORITATIVE_LOG_APPEND_FAILED)
                    written += count
                os.fsync(descriptor)
                line_number = AUTHORITATIVE_NEXT_LINE_NUMBER
                AUTHORITATIVE_LOG_OFFSET += len(line)
                AUTHORITATIVE_NEXT_LINE_NUMBER += 1
                _project_readme_record(
                    conn,
                    runtime,
                    validated,
                    line_number=line_number,
                    byte_offset=AUTHORITATIVE_LOG_OFFSET,
                    line_sha256=line_sha256,
                    materialize_files=True,
                )
        except Exception:
            AUTHORITATIVE_BACKEND_HEALTHY = False
            raise


def _projected_prepared_pull_response(
    runtime: AiAugmentBackendContext,
    commit_record_id: UUID,
) -> PreparedPullResponse:
    with synchronized_detour_database(runtime) as conn:
        row = conn.execute(
            f"SELECT {AUTHORITATIVE_OUTCOME_PAYLOAD_COLUMN} "
            f"FROM {AUTHORITATIVE_OUTCOMES_TABLE} "
            f"WHERE {AUTHORITATIVE_OUTCOME_COMMIT_ID_COLUMN} = ?",
            [str(commit_record_id)],
        ).fetchone()
    if row is None:
        raise _PushConfigurationError(Locale.REPLAY_COMMIT_INVALID)
    try:
        return PreparedPullResponse.model_validate_json(str(row[0]))
    except ValidationError as exc:
        raise _PushConfigurationError(Locale.REPLAY_COMMIT_INVALID) from exc


def _read_appendwatch_bytes(configuration: _PushConfiguration) -> bytes:
    options = _aivm_connection_options(
        lima_ssh_config=configuration.lima_ssh_config,
        identity_file=configuration.identity_file,
        known_hosts_file=configuration.known_hosts_file,
        ssh_user=configuration.ssh_user,
        host_key_alias=configuration.host_key_alias,
    )
    try:
        completed = subprocess.run(
            [
                SSH_EXECUTABLE,
                *options,
                "--",
                configuration.ssh_target,
                shlex.join([
                    AUDIT_READ_APPENDWATCH_REPORT_COMMAND,
                    str(configuration.appendwatch_report),
                ]),
            ],
            check=True,
            capture_output=True,
            timeout=SSH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _PushConfigurationError(Locale.APPENDWATCH_ARCHIVE_FAILED) from exc
    return completed.stdout


def _synthetic_commit_record(
    *,
    pull_record: HttpRequestLogRecord,
    push_record: HttpRequestLogRecord,
    session_id: UUID,
    rollout_archive: _ArchivedFile,
    rollout_filename: str,
    appendwatch_report: bytes,
    namekey: str,
) -> BackendCommitRecord:
    codex_session_record = CodexSessionRecord(
        session_id=session_id,
        codex_rollout_record=CodexRolloutRecord(
            sha256=rollout_archive.sha256,
            size=rollout_archive.size,
            line_count=rollout_archive.line_count,
        ),
        appendwatch_report_record=AppendwatchReportRecord(
            encoding=AppendwatchReportEncoding.BASE64,
            data=base64.b64encode(appendwatch_report).decode(BASE64_TEXT_ENCODING),
        ),
    )
    commit = CommitRequestBody(
        pull_record=pull_record,
        push_record=push_record,
        codex_session_record=codex_session_record,
    )
    return BackendCommitRecord(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        method=HTTP_POST_METHOD,
        scheme=SYNTHETIC_COMMIT_SCHEME,
        host=SYNTHETIC_COMMIT_HOST,
        port=None,
        ready_to_respond_at_unix_usec=None,
        path=COMMIT_PATH,
        query="",
        request_headers={
            SOURCE_KEY_HEADER: _source_key_header(
                rollout_filename,
                rollout_archive.line_count,
            ),
            NAME_KEY_HEADER: _name_key_header(namekey),
        },
        request_body=commit.model_dump_json(),
        response_code=None,
        response_headers=None,
        response_body=None,
        received_at_unix_usec=None,
        duration_usec=None,
        commit_request_body=commit,
    )


def _run_outcome_snapshot_configuration(session_id: str | None) -> _PushConfiguration:
    rollout_name = (
        f"{ROLLOUT_FILENAME_PREFIX}{session_id or 'run-outcome-snapshot'}{ROLLOUT_FILENAME_SUFFIX}"
    )
    return push_configuration(str(CODEX_SESSIONS_ROOT / rollout_name))


def capture_run_outcome_snapshot(
    runtime: AiAugmentBackendContext,
) -> tuple[RunOutcomeResponseBody, str | None, tuple[Exception, ...]]:
    with BACKEND_WORKFLOW_STATE_LOCK:
        session_id = BACKEND_SESSION_ID
        pull_record_id = BACKEND_PENDING_PULL_RECORD_ID or BACKEND_CURRENT_PULL_RECORD_ID
        push_record_id = BACKEND_LATEST_PUSH_RECORD_ID

    rollout_archive: _ArchivedFile | None = None
    rollout_filename: str | None = None
    appendwatch_report: bytes | None = None
    failures: list[Exception] = []

    if session_id is not None:
        try:
            rollout_configuration = push_configuration_for_session(session_id)
            rollout_archive = copy_rollout_to_cas(rollout_configuration, runtime)
            rollout_filename = rollout_configuration.rollout_relative_path.name
        except (OSError, _PushConfigurationError) as exc:
            failures.append(exc)

    try:
        appendwatch_configuration = _run_outcome_snapshot_configuration(session_id)
        appendwatch_report = _read_appendwatch_bytes(appendwatch_configuration)
    except (OSError, _PushConfigurationError) as exc:
        failures.append(exc)

    snapshot = RunOutcomeResponseBody(
        pull_record_id=pull_record_id,
        push_record_id=push_record_id,
        codex_session_record=CodexSessionRecord(
            session_id=None if session_id is None else UUID(session_id),
            codex_rollout_record=(
                None
                if rollout_archive is None
                else CodexRolloutRecord(
                    sha256=rollout_archive.sha256,
                    size=rollout_archive.size,
                    line_count=rollout_archive.line_count,
                )
            ),
            appendwatch_report_record=(
                None
                if appendwatch_report is None
                else AppendwatchReportRecord(
                    encoding=AppendwatchReportEncoding.BASE64,
                    data=base64.b64encode(appendwatch_report).decode(BASE64_TEXT_ENCODING),
                )
            ),
        ),
    )
    return snapshot, rollout_filename, tuple(failures)


def _apply_prepared_pull_response(
    prepared_pull_response: PreparedPullResponse,
) -> None:
    global BACKEND_PREPARED_PULL_RESPONSE
    global BACKEND_WORKFLOW_STATUS

    with BACKEND_WORKFLOW_STATE_LOCK:
        BACKEND_PREPARED_PULL_RESPONSE = prepared_pull_response
        if prepared_pull_response.response_code == status.HTTP_200_OK:
            BACKEND_WORKFLOW_STATUS = BackendWorkflowStatus.RETRY
        elif prepared_pull_response.response_code == status.HTTP_410_GONE:
            BACKEND_WORKFLOW_STATUS = BackendWorkflowStatus.COMPLETE
        else:
            BACKEND_WORKFLOW_STATUS = BackendWorkflowStatus.FAILED


def _mark_workflow_failed(error: Exception) -> None:
    global BACKEND_PREPARED_PULL_RESPONSE
    global BACKEND_WORKFLOW_STATUS

    logger.error(Locale.POST_ACCEPT_PROCESSING_FAILED_LOG, error)
    with BACKEND_WORKFLOW_STATE_LOCK:
        BACKEND_PREPARED_PULL_RESPONSE = None
        BACKEND_WORKFLOW_STATUS = BackendWorkflowStatus.FAILED


def _commit_accepted_push(record: HttpRequestLogRecord) -> None:
    runtime = runtime_configuration()
    with BACKEND_WORKFLOW_STATE_LOCK:
        pull_record_id = BACKEND_PENDING_PULL_RECORD_ID
        session_id = BACKEND_SESSION_ID
    if (
        pull_record_id is None
        or session_id is None
        or runtime.configured_namekey is None
    ):
        _mark_workflow_failed(_PushConfigurationError(Locale.PUSH_LINKAGE_MISSING))
        return
    try:
        configuration = push_configuration_for_session(session_id)
        rollout_archive = copy_rollout_to_cas(configuration, runtime)
        report_bytes = _read_appendwatch_bytes(configuration)
    except (OSError, _PushConfigurationError) as exc:
        _mark_workflow_failed(exc)
        return
    with synchronized_detour_database(runtime) as connection:
        _pull_ordinal, pull_record = _projected_http_record(
            connection,
            pull_record_id,
        )
    commit_record = _synthetic_commit_record(
        pull_record=pull_record,
        push_record=record,
        session_id=UUID(session_id),
        rollout_archive=rollout_archive,
        rollout_filename=configuration.rollout_relative_path.name,
        appendwatch_report=report_bytes,
        namekey=runtime.configured_namekey.to_json_key(),
    )
    try:
        append_authoritative_record(commit_record)
        _apply_prepared_pull_response(
            _projected_prepared_pull_response(runtime, commit_record.record_id)
        )
    except Exception as exc:
        logger.critical(Locale.COMMIT_APPEND_FATAL_LOG, exc)
        raise SystemExit(1) from exc


def _authoritative_background_finished(task: asyncio.Task[None]) -> None:
    AUTHORITATIVE_BACKGROUND_TASKS.discard(task)
    if task.cancelled():
        return
    failure = task.exception()
    if failure is not None:
        logger.critical(Locale.COMMIT_APPEND_FATAL_LOG, failure)
        os._exit(1)


async def _after_authoritative_public_record(record: HttpRequestLogRecord) -> None:
    global BACKEND_CURRENT_PULL_RECORD_ID
    global BACKEND_LATEST_PUSH_RECORD_ID

    route = (record.method, record.path)
    if route == (HTTP_GET_METHOD, PULL_PATH):
        if record.response_code == status.HTTP_200_OK:
            with BACKEND_WORKFLOW_STATE_LOCK:
                BACKEND_CURRENT_PULL_RECORD_ID = record.record_id
        return
    if route != (HTTP_POST_METHOD, PUSH_PATH) or (record.response_code != status.HTTP_202_ACCEPTED):
        return
    with BACKEND_WORKFLOW_STATE_LOCK:
        BACKEND_LATEST_PUSH_RECORD_ID = record.record_id
    task = asyncio.create_task(asyncio.to_thread(_commit_accepted_push, record))
    AUTHORITATIVE_BACKGROUND_TASKS.add(task)
    task.add_done_callback(_authoritative_background_finished)


def configured_pull_lines(outerdict: AiAugmentOuterDict) -> Iterator[str]:
    for innerdict in (*outerdict.xlsx_innerdicts, *outerdict.ssn_innerdicts):
        yield json_line(innerdict.data)
    yield json_line({
        KTP_FIRST_NAME_COL: outerdict.namekey.first_name,
        KTP_LAST_NAME_COL: outerdict.namekey.last_name,
        **dict.fromkeys(AI_AUGMENT_COLUMNS),
    })


def ground_truth_for_researcher(
    outerdict: AiAugmentOuterDict,
) -> dict[str, object] | None:
    if outerdict.ai_augment_cohort is AiAugmentCohort.NO_GROUND_TRUTH:
        return None
    required_columns = tuple(
        column for column in DOCX_COLUMNS if column not in KTP_DOCX_OPTIONAL_EMPTY_COLS
    )
    complete_rows = [
        innerdict.data
        for innerdict in outerdict.docx_innerdicts
        if all(
            column in innerdict.data
            and bool(str(innerdict.data[column]).strip())
            for column in required_columns
        )
    ]
    if not complete_rows:
        raise _PushValidationError(Locale.GROUND_TRUTH_DOCX_INCOMPLETE)
    return select_columns(complete_rows[0])


def render_codex_values(
    submission: StandardizedSubmission,
    evidence: ValidatedEvidence,
    *,
    attempt_timestamp: datetime,
    argument_ref_urls: Mapping[str, str],
) -> dict[str, str | None]:
    rendered: dict[str, str | None] = {}
    ordered_matches: list[_EvidenceMatch] = []
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


def _replace_codex_output_view(conn: duckdb.DuckDBPyConnection) -> None:
    projection = ", ".join(
        duckdb_quote_identifier(column) for column, _data_type in CODEX_OUTPUT_SCHEMA
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {CODEX_OUTPUT_VIEW} AS
        SELECT {projection}
        FROM {CODEX_OUTPUT_ROWS_TABLE}
        ORDER BY
            {duckdb_quote_identifier(KTP_FILENAME_COL)},
            {duckdb_quote_identifier(KTP_FRAGMENT_COL)},
            {duckdb_quote_identifier(KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL)}
        """
    )
    materialize_innerdicts_from_rows_table(
        conn,
        source_relation=CODEX_OUTPUT_VIEW,
        table_name=CODEX_INNERDICT_TABLE,
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
        raise _PushValidationError(Locale.ACCEPTED_IDENTITY_DUPLICATE) from exc
    _replace_codex_output_view(conn)


def selected_card_outer_dict(
    outerdict: AiAugmentOuterDict,
) -> OuterDict:
    selected = OuterDict(
        data={
            outerdict.namekey.to_json_key(): [
                inner.model_copy(deep=True)
                for inner in (
                    *outerdict.xlsx_innerdicts,
                    *(item.innerdict for item in outerdict.committed_innerdicts),
                    *outerdict.docx_innerdicts,
                    *outerdict.ssn_innerdicts,
                )
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
    runtime: AiAugmentBackendContext,
    *,
    submission: StandardizedSubmission,
    evidence: ValidatedEvidence,
    outerdict: AiAugmentOuterDict,
    rollout_index: _RolloutIndex,
    rollout_archive: _ArchivedFile,
    attempt_dir: Path,
    commit_record: BackendCommitRecord,
    attempt_timestamp: datetime,
    manage_transaction: bool = True,
    materialize_files: bool = True,
) -> tuple[tuple[str, ...], _ArchivedFile | None]:
    commit_request_body = commit_record.request_body
    assert commit_request_body is not None
    commit_record_id = str(commit_record.record_id)
    normalized_submission = submission.normalized_values()
    response_path = attempt_dir / RESPONSE_FILENAME
    zip_name = CARD_ZIP_FILENAME_TEMPLATE.format(
        prefix=CARD_ZIP_PREFIX,
        attempt_id=commit_record_id,
    )
    zip_path = runtime.pipeline_config.output_dir / zip_name
    if materialize_files and zip_path.exists():
        raise _PushValidationError(Locale.ATTEMPT_CARD_ZIP_EXISTS)

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
        KTP_NAMEKEY_COL: outerdict.namekey.to_json_key(),
        KTP_FILENAME_COL: rollout_index.session.rollout_filename,
        KTP_FRAGMENT_COL: rollout_archive.line_count,
        KTP_FRAGMENT_TYPE_COL: ROLLOUT_LINE_FRAGMENT_TYPE,
        DRAW_LABEL: outerdict.draw_number,
        KTP_FIRST_NAME_COL: outerdict.namekey.first_name,
        KTP_LAST_NAME_COL: outerdict.namekey.last_name,
        KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL: commit_record_id,
        KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL: commit_request_body,
        KTP_AI_AUGMENT_SESSION_METADATA_COL: rollout_index.session.summary_json,
        **rendered,
    }

    if manage_transaction:
        detour_conn.execute("BEGIN TRANSACTION")
    try:
        append_codex_output(detour_conn, output_row)
        submitted_line = json_line(normalized_submission)
        truth = ground_truth_for_researcher(outerdict)
        response_lines = (submitted_line,) if truth is None else (submitted_line, json_line(truth))
        if materialize_files:
            committed_innerdicts = tuple(
                committed
                for committed in _committed_innerdicts(detour_conn)
                if name_key_from_header_value(
                    committed.commit_record.request_headers.get(NAME_KEY_HEADER)
                )
                == outerdict.namekey
            )
            card_outer_dict = selected_card_outer_dict(
                outerdict.model_copy(
                    update={"committed_innerdicts": committed_innerdicts}
                )
            )
            intro_date = attempt_timestamp.astimezone(
                ZoneInfo(runtime.pipeline_config.timezone)
            ).strftime(
                Locale.CARD_INTRO_DATE_FORMAT
            )
            cards = build_cards(
                card_outer_dict,
                total_draws=runtime.pipeline_config.total_draws,
                intro=CARD_INTRODUCTION.format(intro_date),
                excluded_cols=CARD_EXCLUDED_COLUMNS,
            )
            if len(cards) != 1:
                raise _PushValidationError(Locale.RESEARCHER_CARD_COUNT_INVALID)
            write_cards_zip(
                cards,
                runtime.pipeline_config.output_dir,
                zip_name,
                output_format=runtime.pipeline_config.output_format,
                reference_docx=runtime.pipeline_config.pandoc_reference_docx,
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


def _execute_attempt(
    detour_conn: duckdb.DuckDBPyConnection,
    runtime: AiAugmentBackendContext,
    *,
    commit_record: BackendCommitRecord,
    rollout_archive: _ArchivedFile,
    appendwatch_report: AppendwatchReportRecord,
    rollout_relative_path: PurePosixPath,
    run_id: UUID,
    namekey: NameKey,
    materialize_files: bool,
) -> tuple[PreparedPullResponse, bool]:
    commit_request_body = commit_record.request_body
    body = commit_record.commit_request_body
    push_request_body = body.push_record.request_body
    session_id = body.codex_session_record.session_id
    assert commit_request_body is not None
    assert push_request_body is not None
    assert session_id is not None

    attempt_timestamp = datetime.fromtimestamp(
        commit_record.record_id.time / 1_000,
        tz=timezone.utc,
    )
    canonical_namekey = namekey.to_json_key()
    retry_submission_expected = False
    stage = PostCommitValidationStage.APPENDWATCH_REPORT_VALIDATION

    def result(
        *,
        validation_result: PostCommitValidationResult,
        detail: str | None,
        error: Exception | None,
        commit_database: bool,
        accepted_response_body: str = "",
    ) -> tuple[PreparedPullResponse, bool]:
        post_commit_validation = PostCommitValidation(
            stage=stage,
            result=validation_result,
            detail=detail,
        )
        _log_post_commit_validation(
            str(body.push_record.record_id),
            post_commit_validation,
            error,
        )
        return (
            _prepared_pull_response_from_validation(
                record=commit_record,
                post_commit_validation=post_commit_validation,
                accepted_response_body=accepted_response_body,
            ),
            commit_database,
        )

    with tempfile.TemporaryDirectory() as temporary_directory:
        attempt_dir = Path(temporary_directory)
        try:
            report_path = attempt_dir / APPENDWATCH_ARCHIVE_FILENAME_TEMPLATE.format(
                attempt_id=commit_record.record_id
            )
            report_path.write_bytes(appendwatch_report.decoded_bytes())
            parse_appendwatch_report(
                report_path,
                rollout_relative_path,
            )
            stage = PostCommitValidationStage.ROLLOUT_INDEX
            rollout_index = build_rollout_index(
                parse_rollout(rollout_archive.path),
                timezone_name=runtime.pipeline_config.timezone,
                configured_rollout_basename=rollout_relative_path.name,
            )
            if rollout_index.session.session_id != str(session_id):
                raise _PushValidationError(Locale.CONFIGURED_SESSION_MISMATCH)
            persist_rollout_index(
                detour_conn,
                rollout_index,
                codex_match_version=(
                    runtime.pipeline_config.match_rule_version.codex_match
                ),
                manage_transaction=False,
            )

            stage = PostCommitValidationStage.PYDANTIC_VALIDATION
            retry_submission_expected = _retry_baseline_exists(
                detour_conn,
                run_id=run_id,
                namekey=canonical_namekey,
                session_id=str(session_id),
            )
            submission: SubmissionPayload = (
                StandardizedSubmission.model_validate_json(push_request_body)
                if retry_submission_expected
                else Submission.model_validate_json(push_request_body)
            )

            stage = PostCommitValidationStage.DUCKDB_EVIDENCE_VALIDATION
            _seed_evidence_random(runtime.pipeline_config.sample_seed)
            evidence_assessment = assess_submission_evidence(
                detour_conn,
                submission,
                rollout_filename=rollout_index.session.rollout_filename,
                codex_match_version=(
                    runtime.pipeline_config.match_rule_version.codex_match
                ),
            )
            _log_evidence_assessment(
                evidence_assessment,
                attempt_id=str(commit_record.record_id),
            )
            retry_violations = _process_retry_attempt(
                detour_conn,
                run_id=run_id,
                namekey=canonical_namekey,
                session_id=str(session_id),
                attempt_id=str(commit_record.record_id),
                attempt_timestamp=attempt_timestamp,
                submission=submission,
                assessment=evidence_assessment,
                manage_transaction=False,
            )
            if not evidence_assessment.accepted or retry_violations:
                raise _EvidenceAssessmentError(
                    Locale.EVIDENCE_SUBMISSION_REJECTED,
                    public_detail=_assessment_public_detail(
                        evidence_assessment,
                        violations=retry_violations,
                        include_retry_contract=True,
                    ),
                )
            accepted_submission = (
                submission
                if isinstance(submission, StandardizedSubmission)
                else _standardized_initial_submission(submission)
            )

            stage = PostCommitValidationStage.RESEARCHER_RESOLUTION
            outerdict = _configured_ai_augment_outerdict(
                namekey,
                runtime.ai_augment_outerdicts,
            )

            stage = PostCommitValidationStage.INNERDICT_AND_CARD
            response_lines, _card_archive = write_accepted_submission(
                detour_conn,
                runtime,
                submission=accepted_submission,
                evidence=evidence_assessment.validated,
                outerdict=outerdict,
                rollout_index=rollout_index,
                rollout_archive=rollout_archive,
                attempt_dir=attempt_dir,
                commit_record=commit_record,
                attempt_timestamp=attempt_timestamp,
                manage_transaction=False,
                materialize_files=materialize_files,
            )
            stage = PostCommitValidationStage.ACCEPTED
            return result(
                validation_result=PostCommitValidationResult.ACCEPTED,
                detail=None,
                error=None,
                commit_database=True,
                accepted_response_body="".join(response_lines),
            )
        except _PushConfigurationError as exc:
            return result(
                validation_result=PostCommitValidationResult.CONFIGURATION_ERROR,
                detail=Locale.CONFIGURATION_ERROR_DETAIL,
                error=exc,
                commit_database=False,
            )
        except _MultipleEvidenceMatches as exc:
            return result(
                validation_result=PostCommitValidationResult.REJECTED,
                detail=Locale.MULTIPLE_MATCH_DETAIL_TEMPLATE.format(excerpt=exc.excerpt),
                error=exc,
                commit_database=(stage is PostCommitValidationStage.DUCKDB_EVIDENCE_VALIDATION),
            )
        except _PushValidationError as exc:
            return result(
                validation_result=PostCommitValidationResult.REJECTED,
                detail=(
                    exc.public_detail
                    if isinstance(exc, _EvidenceAssessmentError)
                    else Locale.VALIDATION_ERROR_DETAIL
                ),
                error=exc,
                commit_database=(
                    stage
                    in {
                        PostCommitValidationStage.PYDANTIC_VALIDATION,
                        PostCommitValidationStage.DUCKDB_EVIDENCE_VALIDATION,
                    }
                ),
            )
        except ValidationError as exc:
            return result(
                validation_result=PostCommitValidationResult.REJECTED,
                detail=Locale.VALIDATION_ERROR_DETAIL
                + (f"\n{RETRY_SUBMISSION_PUBLIC_GUIDANCE}" if retry_submission_expected else ""),
                error=exc,
                commit_database=True,
            )
        except (OSError, ValueError, duckdb.Error, subprocess.SubprocessError) as exc:
            return result(
                validation_result=PostCommitValidationResult.REJECTED,
                detail=Locale.VALIDATION_ERROR_DETAIL,
                error=exc,
                commit_database=False,
            )


def validate_transport(request: Request) -> None:
    content_type = (
        request.headers.get(HTTP_REQUEST_CONTENT_TYPE_HEADER, "").partition(";")[0].strip().lower()
    )
    if content_type != JSON_MEDIA_TYPE:
        raise _PushValidationError(Locale.REQUEST_CONTENT_TYPE_INVALID)
    content_length = request.headers.get(HTTP_REQUEST_CONTENT_LENGTH_HEADER)
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise _PushValidationError(Locale.REQUEST_CONTENT_LENGTH_INVALID) from exc
        if declared_length < 0 or declared_length > MAX_PUSH_BODY_BYTES:
            raise _PushValidationError(Locale.REQUEST_BODY_TOO_LARGE)


async def bounded_request_body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_PUSH_BODY_BYTES:
            raise _PushValidationError(Locale.REQUEST_BODY_TOO_LARGE)
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


def _attempt_records(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[AgentRuntimeAttempt, ...]:
    rows = conn.execute(
        f"SELECT records.{AUTHORITATIVE_RECORD_PAYLOAD_COLUMN}, "
        f"results.{AUTHORITATIVE_OUTCOME_PAYLOAD_COLUMN} "
        f"FROM {AUTHORITATIVE_RECORDS_TABLE} AS records "
        f"JOIN {AUTHORITATIVE_OUTCOMES_TABLE} AS results "
        f"ON records.{AUTHORITATIVE_RECORD_ID_COLUMN} = "
        f"results.{AUTHORITATIVE_OUTCOME_COMMIT_ID_COLUMN} "
        f"ORDER BY records.{AUTHORITATIVE_RECORD_ORDINAL_COLUMN}"
    ).fetchall()
    try:
        attempts: list[AgentRuntimeAttempt] = []
        for record_json, response_json in rows:
            record = HttpRequestLogRecord.model_validate_json(str(record_json))
            commit_record = _backend_commit_record(conn, record)
            prepared_pull_response = PreparedPullResponse.model_validate_json(str(response_json))
            attempts.append(
                AgentRuntimeAttempt(
                    pull_record=commit_record.commit_request_body.pull_record,
                    commit_record=commit_record,
                    post_commit_validation=(prepared_pull_response.post_commit_validation),
                )
            )
        return tuple(attempts)
    except (_PushValidationError, ValidationError, ValueError) as exc:
        raise _PushConfigurationError(Locale.REPLAY_PROJECTION_CONFLICT) from exc


def _committed_innerdicts(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[CommittedInnerDict, ...]:
    exists = conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
        [CODEX_OUTPUT_ROWS_TABLE],
    ).fetchone()
    if exists is None or int(exists[0]) == 0:
        return ()
    result = conn.execute(
        f"SELECT * FROM {CODEX_OUTPUT_ROWS_TABLE} "
        f"ORDER BY {duckdb_quote_identifier(KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL)}"
    )
    column_names = tuple(column[0] for column in result.description)
    rows = result.fetchall()
    committed_innerdicts: list[CommittedInnerDict] = []
    for row in rows:
        values = dict(zip(column_names, row, strict=True))
        try:
            commit_record_id = UUID(str(values[KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL]))
            _ordinal, http_record = _projected_http_record(conn, commit_record_id)
            committed_innerdicts.append(
                CommittedInnerDict(
                    innerdict=InnerDict.from_mapping(
                        values,
                        _CodexMatchProcedure(),
                    ),
                    commit_record=_backend_commit_record(conn, http_record),
                )
            )
        except (
            KeyError,
            TypeError,
            ValidationError,
            ValueError,
            _PushValidationError,
        ) as exc:
            raise _PushConfigurationError(Locale.REPLAY_PROJECTION_CONFLICT) from exc
    return tuple(committed_innerdicts)


def _log_post_commit_validation(
    attempt_id: str,
    post_commit_validation: PostCommitValidation,
    error: Exception | None,
) -> None:
    if error is None:
        logger.info(Locale.PUSH_ACCEPTED_LOG, attempt_id)
    elif isinstance(error, ValidationError):
        field, reason, failed_input = pydantic_failure(error)
        logger.warning(
            Locale.PUSH_PYDANTIC_FAILED_LOG,
            attempt_id,
            post_commit_validation.stage,
            field or Locale.UNKNOWN_FIELD,
            failed_input,
            reason,
        )
    elif isinstance(error, _PushConfigurationError):
        logger.error(
            Locale.PUSH_CONFIGURATION_FAILED_LOG,
            attempt_id,
            post_commit_validation.stage,
            error,
        )
    elif isinstance(error, _PushValidationError):
        logger.warning(
            Locale.PUSH_VALIDATION_FAILED_LOG,
            attempt_id,
            post_commit_validation.stage,
            error,
        )
    else:
        logger.warning(
            Locale.PUSH_UNEXPECTED_FAILED_LOG,
            attempt_id,
            post_commit_validation.stage,
            error,
        )


def dashboard_query_response(
    runtime: AiAugmentBackendContext,
    conn: duckdb.DuckDBPyConnection,
    *,
    namekey: str | None,
    run_outcome_records: tuple[RunOutcomeResponse, ...],
) -> QueryResponse:
    committed_by_namekey: dict[str, list[CommittedInnerDict]] = {}
    for committed in _committed_innerdicts(conn):
        committed_namekey = name_key_from_header_value(
            committed.commit_record.request_headers.get(NAME_KEY_HEADER)
        ).to_json_key()
        committed_by_namekey.setdefault(committed_namekey, []).append(committed)
    selected_outerdicts = tuple(
        outerdict.model_copy(
            update={
                "committed_innerdicts": tuple(
                    committed_by_namekey.get(outerdict.namekey.to_json_key(), ())
                )
            }
        )
        for outerdict in runtime.ai_augment_outerdicts
        if namekey is None or outerdict.namekey.to_json_key() == namekey
    )
    return QueryResponse(
        attempts=_attempt_records(conn),
        ai_augment_outerdicts=selected_outerdicts,
        run_outcome_records=run_outcome_records,
    )


@app.get(**PULL_ROUTE)
def authoritative_pull() -> Response:
    runtime = runtime_configuration()
    with BACKEND_WORKFLOW_STATE_LOCK:
        workflow_status = BACKEND_WORKFLOW_STATUS
        prepared_pull_response = BACKEND_PREPARED_PULL_RESPONSE
    if workflow_status is BackendWorkflowStatus.BUSY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=Locale.CONFIGURATION_ERROR_DETAIL,
            headers={RETRY_AFTER_HEADER: RETRY_AFTER_SECONDS},
        )
    if workflow_status is BackendWorkflowStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=Locale.CONFIGURATION_ERROR_DETAIL,
        )
    if workflow_status in {BackendWorkflowStatus.RETRY, BackendWorkflowStatus.COMPLETE}:
        if prepared_pull_response is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=Locale.CONFIGURATION_ERROR_DETAIL,
            )
        return Response(
            content=prepared_pull_response.response_body,
            status_code=prepared_pull_response.response_code,
            media_type=prepared_pull_response.response_headers[
                HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_HEADER
            ],
        )
    try:
        outerdict = runtime.configured_ai_augment_outerdict()
        if outerdict is None:
            raise _PushConfigurationError(Locale.PUSH_LINKAGE_MISSING)
        lines = tuple(configured_pull_lines(outerdict))
        return StreamingResponse(iter(lines), media_type=MEDIA_TYPE_WITH_CHARSET)
    except (_PushConfigurationError, _PushValidationError, OSError, duckdb.Error) as exc:
        logger.error(Locale.PULL_FAILED_LOG, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=Locale.CONFIGURATION_ERROR_DETAIL,
        ) from None


@app.post(**PUSH_ROUTE)
async def authoritative_push(request: Request) -> Response:
    del request
    global BACKEND_CURRENT_PULL_RECORD_ID
    global BACKEND_PENDING_PULL_RECORD_ID
    global BACKEND_PREPARED_PULL_RESPONSE
    global BACKEND_WORKFLOW_STATUS

    with BACKEND_WORKFLOW_STATE_LOCK:
        if BACKEND_WORKFLOW_STATUS is BackendWorkflowStatus.BUSY:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": Locale.CONFIGURATION_ERROR_DETAIL},
                headers={LOCATION_HEADER: PULL_PATH},
            )
        if (
            BACKEND_WORKFLOW_STATUS
            not in {BackendWorkflowStatus.READY, BackendWorkflowStatus.RETRY}
            or BACKEND_SESSION_ID is None
        ):
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": Locale.CONFIGURATION_ERROR_DETAIL},
            )
        if BACKEND_CURRENT_PULL_RECORD_ID is None:
            logger.warning(Locale.PUSH_CURRENT_PULL_REQUIRED_LOG)
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": Locale.CONFIGURATION_ERROR_DETAIL},
                headers={LOCATION_HEADER: PULL_PATH},
            )
        BACKEND_PENDING_PULL_RECORD_ID = BACKEND_CURRENT_PULL_RECORD_ID
        BACKEND_CURRENT_PULL_RECORD_ID = None
        BACKEND_PREPARED_PULL_RESPONSE = None
        BACKEND_WORKFLOW_STATUS = BackendWorkflowStatus.BUSY
    return Response(
        status_code=status.HTTP_202_ACCEPTED,
        headers={LOCATION_HEADER: PULL_PATH},
    )
