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
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import AsyncGenerator, Coroutine, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path, PurePosixPath
from random import Random
from typing import Any, Callable, Literal, Self, TextIO, get_args
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

import duckdb
import requests
from fastapi import status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    ValidationError,
    model_validator,
)

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers import codex_parse
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.pydantic_to_paste import (  # noqa: E501
    MAX_PUSH_BODY_BYTES,
    AcademicPositionsSubmission,
    AgeFirstPublicationSubmission,
    EducationSubmission,
    EvidenceSubmission,
    EvidenceWithdrawal,
    FieldSubmission,
    GenderSubmission,
    NotAvailableOrApplicable,
    NotReported,
    PlaceOfResidenceStandardized,
    PlaceOfResidenceSubmission,
    RaceEthnicityLanguageCultureStandardized,
    RaceEthnicityLanguageCultureSubmission,
    ResearcherAuthorStandardized,
    ResearcherAuthorSubmission,
    ResearcherLinksSubmission,
    SocialCapitalSubmission,
    StandardizedFieldSubmission,
    StandardizedSubmission,
    StandardizedValue,
    WebSearchExcerpt,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_fixture import (  # noqa: E501
    L_FEI_FEI_INITIAL_FIXTURE,
    L_FEI_FEI_RETRY_FIXTURE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_init import (  # noqa: E501
    Submission,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_mixin import (  # noqa: E501
    submission_http_context,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AI_AUGMENT_COLUMNS,
    AI_AUGMENT_EVIDENCE_COLUMNS,
    AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS,
    AI_AUGMENT_STANDARDIZED_COLUMNS,
    DOCX_COLUMNS,
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
    KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL,
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
    KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL,
    TEXT_ENCODING,
    AiAugmentCohort,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.model_http_interceptor import (  # noqa: E501
    ModelHttpInterceptor,
    ModelHttpRequired,
    ReplayInputMissing,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.validation_event import (  # noqa: E501
    VALIDATE_PATH,
    BackendValidationRecord,
)
from src.helpers.architecture import FrozenStrictModel
from src.helpers.data_models import (
    FragmentType,
    InnerDict,
    NameKey,
    OuterDict,
)
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
)
from src.helpers.duckdb_utils import duckdb_quote_identifier
from src.helpers.jsonlines import loads_jsonlines
from src.helpers.name_matching import normalized_tokens_sql
from src.helpers.vars import (
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
    KTP_INNERDICT_JSONLINES_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
    KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS,
)

from ..control_centre.dashboard.helpers.data_models.run_outcome import (
    NAME_KEY_HEADER,
    RUN_OUTCOME_PATHS,
    RunOutcomePath,
    RunOutcomeRequest,
    name_key_from_header_value,
    name_key_header_value,
)
from .helpers.data_models.ai_augment_backend_store import AiAugmentBackendStore
from .helpers.data_models.ai_augment_context import (
    AiAugmentBackendContext,
)
from .helpers.data_models.ai_augment_singular_outer_dict import (
    AiAugmentSingularOuterDict,
)
from .helpers.data_models.commit_event import (
    COMMIT_PATH,
    SOURCE_KEY_HEADER,
    AppendwatchReportEncoding,
    AppendwatchReportRecord,
    BackendCommitRecord,
    BackendLifecycle,
    CodexRolloutRecord,
    CodexSessionRecord,
    CommitRequestBody,
    PostCommitValidation,
    source_key_from_header_value,
    source_key_header_value,
)
from .helpers.data_models.committed_innerdict import CommittedInnerDict
from .helpers.data_models.query_response import (
    AgentRuntimeAttempt,
    AgentRuntimeAttemptRecord,
)
from .helpers.data_models.request_response_records import (
    PullRequestRecord,
    PushRequestRecord,
    PushResponseRecord,
    RunOutcomeRequestRecord,
)
from .helpers.data_models.response_record_promise import (
    BackendStoreAcknowledgment,
    BackendStoreException,
)
from .helpers.data_models.run_outcome_record import RunOutcomeRecord, RunOutcomeResponseBody

logger = logging.getLogger(__name__)


AIVM_WORKDIR = PurePosixPath("/home/ai/workdir")

ROLLOUT_ENV_NAME = "FASTAPI_DETOUR_ROLLOUT_JSONL"
ROLLOUT_JSONL = os.environ.get(ROLLOUT_ENV_NAME, "")
APPENDWATCH_REPORT_ENV_NAME = "FASTAPI_DETOUR_APPENDWATCH_REPORT"
NAMEKEY_ENV_NAME = "FASTAPI_DETOUR_NAMEKEY"
CODEX_SESSIONS_ROOT_ENV_NAME = "FASTAPI_DETOUR_CODEX_SESSIONS_DIR"
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
WEB_FIND_ACTION = "find"
WEB_RESPONSE_LENGTH_ARGUMENT = "response_length"
ELIGIBLE_WEB_ACTIONS = frozenset({
    WEB_SEARCH_QUERY_ACTION,
    WEB_OPEN_ACTION,
    WEB_CLICK_ACTION,
    WEB_FIND_ACTION,
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
ROLLOUT_FILENAME_PREFIX = "rollout-"
ROLLOUT_FILENAME_SUFFIX = ".jsonl"
ROLLOUT_TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%S"
CUMULATIVE_KEY_SEPARATOR = "\0"
FCO_TIMESTAMP_TIMESPEC = "milliseconds"
API_VERSION = "1.0.0"
PULL_PATH = "/pull"
PUSH_PATH = "/push"
PYDANTIC_ERROR_MESSAGE_KEY = "msg"
PYDANTIC_ERROR_LOCATION_KEY = "loc"
PYDANTIC_ERROR_TYPE_KEY = "type"
PYDANTIC_ERROR_INPUT_KEY = "input"
PYDANTIC_MISSING_ERROR_TYPE = "missing"
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
AUTHORITATIVE_FIRST_LINE = 1
AUTHORITATIVE_EMPTY_OFFSET = 0
AUTHORITATIVE_LOG_BASE64_ENCODING = "base64"
AUTHORITATIVE_LOG_ENCODING_KEY = "encoding"
AUTHORITATIVE_LOG_DATA_KEY = "data"
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

BACKEND_PROCESS_LOCK_DESCRIPTOR: int | None = None
AUTHORITATIVE_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()
BACKEND_WORKFLOW_STATE_LOCK = threading.Lock()
BACKEND_LIFECYCLE = BackendLifecycle.READY
BACKEND_PUSH_RESPONSE_RECORD: PushResponseRecord | None = None
BACKEND_CURRENT_PULL_RECORD: HttpRequestLogRecord | None = None
BACKEND_PENDING_PULL_RECORD: HttpRequestLogRecord | None = None
BACKEND_LATEST_PUSH_RECORD: HttpRequestLogRecord | None = None
BACKEND_SESSION_ID: UUID | None = None
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
CREATE_AUTHORITATIVE_RECORDS_TABLE_SQL = (
    f"CREATE TABLE IF NOT EXISTS {AUTHORITATIVE_RECORDS_TABLE} ("
    f"{AUTHORITATIVE_RECORD_ORDINAL_COLUMN} BIGINT PRIMARY KEY, "
    f"{AUTHORITATIVE_RECORD_ID_COLUMN} VARCHAR NOT NULL UNIQUE, "
    f"{AUTHORITATIVE_RECORD_METHOD_COLUMN} VARCHAR NOT NULL, "
    f"{AUTHORITATIVE_RECORD_PATH_COLUMN} VARCHAR NOT NULL, "
    f"{AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} JSON NOT NULL, "
    "raw_line_sha256 VARCHAR NOT NULL)"
)
CREATE_AUTHORITATIVE_ATTEMPTS_TABLE_SQL = (
    f"CREATE TABLE IF NOT EXISTS {AUTHORITATIVE_ATTEMPTS_TABLE} ("
    f"{AUTHORITATIVE_ATTEMPT_COMMIT_ID_COLUMN} VARCHAR PRIMARY KEY, "
    f"{AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN} JSON NOT NULL)"
)
HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_HEADER = "content-type"
HTTP_REQUEST_LOG_RESPONSE_CONTENT_TYPE_JSON = "application/json"
NANOSECONDS_PER_MICROSECOND = 1_000

NOT_REPORTED_VALUE: NotReported = get_args(NotReported)[0]
NOT_AVAILABLE_OR_APPLICABLE_VALUE: NotAvailableOrApplicable = get_args(
    NotAvailableOrApplicable
)[0]
STANDARDIZED_VALUE_FIELD = next(
    field
    for field in StandardizedFieldSubmission.model_fields
    if field not in FieldSubmission.model_fields
)
INITIAL_RESEARCHER_AUTHOR_STANDARDIZED = ResearcherAuthorStandardized(
    first_name=NOT_REPORTED_VALUE,
    last_name=NOT_REPORTED_VALUE,
    orcid=NOT_REPORTED_VALUE,
    openalex_id=NOT_REPORTED_VALUE,
)
INITIAL_PLACE_OF_RESIDENCE_STANDARDIZED = PlaceOfResidenceStandardized(
    place=NOT_REPORTED_VALUE,
    location=NOT_REPORTED_VALUE,
)
INITIAL_RACE_ETHNICITY_LANGUAGE_CULTURE_STANDARDIZED = (
    RaceEthnicityLanguageCultureStandardized(
        race=NOT_AVAILABLE_OR_APPLICABLE_VALUE,
        ethnicity=NOT_AVAILABLE_OR_APPLICABLE_VALUE,
        language=NOT_REPORTED_VALUE,
        culture=NOT_AVAILABLE_OR_APPLICABLE_VALUE,
    )
)
INITIAL_STANDARDIZED_VALUES: Mapping[str, StandardizedValue] = {
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL: INITIAL_RESEARCHER_AUTHOR_STANDARDIZED,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL: INITIAL_PLACE_OF_RESIDENCE_STANDARDIZED,
    KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL: (
        INITIAL_RACE_ETHNICITY_LANGUAGE_CULTURE_STANDARDIZED
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
CODEX_OUTPUT_SCHEMA = (
    (KTP_NAMEKEY_COL, "VARCHAR NOT NULL"),
    (KTP_FILENAME_COL, "VARCHAR NOT NULL"),
    (KTP_FRAGMENT_COL, "BIGINT NOT NULL"),
    (KTP_FRAGMENT_TYPE_COL, "VARCHAR NOT NULL"),
    (DRAW_LABEL, "VARCHAR NOT NULL"),
    (KTP_FIRST_NAME_COL, "VARCHAR NOT NULL"),
    (KTP_LAST_NAME_COL, "VARCHAR NOT NULL"),
    (KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL, "VARCHAR NOT NULL UNIQUE"),
    (KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL, "VARCHAR"),
    (KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL, "VARCHAR"),
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

MEDIA_TYPE = "application/x-ndjson"
MEDIA_TYPE_WITH_CHARSET = f"{MEDIA_TYPE}; charset=utf-8"


@asynccontextmanager
async def lifespan(
    runtime: AiAugmentBackendContext,
) -> AsyncGenerator[None, None]:
    try:
        with BACKEND_WORKFLOW_STATE_LOCK:
            global BACKEND_CURRENT_PULL_RECORD
            global BACKEND_LATEST_PUSH_RECORD
            global BACKEND_PENDING_PULL_RECORD
            global BACKEND_SESSION_ID
            global BACKEND_PUSH_RESPONSE_RECORD
            global BACKEND_LIFECYCLE
            BACKEND_CURRENT_PULL_RECORD = None
            BACKEND_PENDING_PULL_RECORD = None
            BACKEND_LATEST_PUSH_RECORD = None
            BACKEND_SESSION_ID = None
            BACKEND_PUSH_RESPONSE_RECORD = None
            BACKEND_LIFECYCLE = BackendLifecycle.READY
        prove_workflow_inputs_readable()
        start_backend_session_reader()
        try:
            yield
        finally:
            if AUTHORITATIVE_BACKGROUND_TASKS:
                results = await asyncio.gather(
                    *tuple(AUTHORITATIVE_BACKGROUND_TASKS),
                    return_exceptions=True,
                )
                failures = [result for result in results if isinstance(result, BaseException)]
                if failures:
                    raise BaseExceptionGroup("Backend background work failed", failures)
    except Exception as exc:
        logger.error(Locale.API_LIFESPAN_FAILED_LOG, exc)
        raise


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
}

PULL_ROUTE: dict[str, Any] = {
    "path": PULL_PATH,
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


class _RetryEvidenceObligation(FrozenStrictModel):
    outcome: EvidenceOutcome
    excerpt: StrictStr | None = None
    url: StrictStr | None = None
    normalized_tokens: list[StrictStr] = Field(default_factory=list)


class _RetryFieldObligation(FrozenStrictModel):
    value: StrictStr
    evidence: list[_RetryEvidenceObligation]
    accepted: bool


class _RetryObligations(FrozenStrictModel):
    fields: dict[StrictStr, _RetryFieldObligation]


class _EvidenceCandidateAudit(FrozenStrictModel):
    ref_id: StrictStr
    call_id: StrictStr
    cite_text: StrictStr
    excerpt_position: int
    url: StrictStr


class _EvidenceItemAudit(FrozenStrictModel):
    field: StrictStr
    index: int
    outcome: EvidenceOutcome
    excerpt: StrictStr | None
    url: StrictStr | None
    normalized_tokens: list[StrictStr]
    candidates: list[_EvidenceCandidateAudit]


class _EvidenceAttemptAudit(FrozenStrictModel):
    items: list[_EvidenceItemAudit]


class _CodexTextResult(BaseModel):
    """Note `extra="ignore"`"""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

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


class _PushConfiguration(FrozenStrictModel):
    rollout_guest_path: str
    rollout_relative_path: PurePosixPath
    appendwatch_report: PurePosixPath
    lima_ssh_config: Path
    identity_file: Path
    known_hosts_file: Path
    ssh_user: str
    ssh_target: str
    host_key_alias: str


class _ArchivedFile(FrozenStrictModel):
    path: Path
    size: int
    sha256: str
    line_count: int


class _RolloutRecord(FrozenStrictModel):
    line_number: int
    line_sha256: str
    value: dict[str, object]


class _SessionMetadata(FrozenStrictModel):
    session_id: UUID
    timestamp: str
    rollout_filename: str
    summary_json: str


class _CodexFcRow(FrozenStrictModel):
    timestamp: str
    fc_id: str
    call_id: str
    name: str
    namespace: str
    arguments_json: str


class _CodexFcoRow(FrozenStrictModel):
    timestamp: str
    fco_id: str
    call_id: str


class _CodexTurnRefRow(FrozenStrictModel):
    ref_id: str
    call_id: str
    domain: str | None
    snippet: str | None
    thumbnail_url: str | None
    title: str | None
    url: str
    cite_text: str


class _RolloutIndex(FrozenStrictModel):
    session: _SessionMetadata
    fc_rows: tuple[_CodexFcRow, ...]
    fco_rows: tuple[_CodexFcoRow, ...]
    turn_ref_rows: tuple[_CodexTurnRefRow, ...]


class _EvidenceMatch(FrozenStrictModel):
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


class _EvidenceCandidate(FrozenStrictModel):
    ref_id: str
    call_id: str
    cite_text: str
    excerpt_position: int
    url: str
    fco_timestamp: datetime
    arguments_json: object


class _EvidenceItemAssessment(FrozenStrictModel):
    field: str
    index: int
    evidence_number: int
    submission: EvidenceSubmission
    outcome: EvidenceOutcome
    match: _EvidenceMatch | None
    normalized_tokens: tuple[str, ...] = ()
    candidates: tuple[_EvidenceCandidate, ...] = ()


class _EvidenceAssessment(FrozenStrictModel):
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


def _has_control_character(value: str) -> bool:
    return any(
        ord(character) < CONTROL_CHARACTER_CEILING or ord(character) == DELETE_CHARACTER_CODEPOINT
        for character in value
    )


def _require_nonblank_text(
    value: object,
    error: _PushConfigurationError | _PushValidationError,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or _has_control_character(value)
    ):
        raise error
    return value


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


def _seed_evidence_random(sample_seed: int) -> None:
    EVIDENCE_RANDOM.seed(sample_seed)


def _configured_ai_augment_singular_outerdict(
    configured_namekey: NameKey,
    singular_outerdicts: Sequence[AiAugmentSingularOuterDict],
) -> AiAugmentSingularOuterDict:
    configured = next(
        (
            singular_outerdict
            for singular_outerdict in singular_outerdicts
            if singular_outerdict.namekey == configured_namekey
        ),
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
        singular_outerdict.namekey.to_json_key()
        for singular_outerdict in singular_outerdicts
        if (
            singular_outerdict.namekey.first_name.strip(),
            singular_outerdict.namekey.last_name.strip(),
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
    raw_namekey = _require_nonblank_text(
        os.environ.get(NAMEKEY_ENV_NAME, ""),
        _PushConfigurationError(
            Locale.NAMEKEY_NOT_SET_TEMPLATE.format(environment_name=NAMEKEY_ENV_NAME)
        ),
    )
    try:
        return NameKey.from_json_key(raw_namekey)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise _PushConfigurationError(Locale.CONFIGURED_NAMEKEY_MALFORMED) from exc


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

    _require_nonblank_text(
        AIVM_INSTANCE,
        _PushConfigurationError(Locale.AIVM_INSTANCE_INVALID),
    )
    _require_nonblank_text(
        AIVM_AUDIT_USER,
        _PushConfigurationError(Locale.AIVM_AUDIT_USER_INVALID),
    )
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
        if BACKEND_SESSION_ID is not None and BACKEND_SESSION_ID != session_id:
            raise _PushConfigurationError(Locale.SESSION_ID_STDIN_CONFLICT)
        BACKEND_SESSION_ID = session_id


def read_backend_session_id(stream: TextIO | None = None) -> None:
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
            _mark_backend_lifecycle_failed(exc)

    reader = threading.Thread(
        target=read_or_fail,
        name="detour-ai-augment-session-reader",
        daemon=True,
    )
    reader.start()
    return reader


def push_configuration_for_session(session_id: UUID) -> _PushConfiguration:
    session_id_text = str(session_id)
    placeholder = (
        CODEX_SESSIONS_ROOT
        / f"{ROLLOUT_FILENAME_PREFIX}{session_id_text}{ROLLOUT_FILENAME_SUFFIX}"
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
                shlex.join([AUDIT_FIND_ROLLOUT_COMMAND, session_id_text]),
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
        rollout_value: dict[str, object] = value
        records.append(
            _RolloutRecord(
                line_number=line_number,
                line_sha256=hashlib.sha256(raw_line).hexdigest(),
                value=rollout_value,
            )
        )
    return tuple(records)


def _timestamp(value: object, *, label: str) -> str:
    raw = _require_nonblank_text(
        value,
        _PushValidationError(Locale.TIMESTAMP_INVALID_TEMPLATE.format(label=label)),
    )
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _PushValidationError(Locale.TIMESTAMP_INVALID_TEMPLATE.format(label=label)) from exc
    if parsed.tzinfo is None:
        raise _PushValidationError(Locale.TIMESTAMP_TIMEZONE_MISSING_TEMPLATE.format(label=label))
    return raw


def _web_arguments(
    payload: Mapping[str, object], line_number: int,
) -> dict[str, object] | None:
    """Decode arguments; unsupported commands are ineligible, not corrupt evidence.

    Upstream SearchCommands permits multiple action keys. Our evidence subset
    allows any combination of supported actions, plus the response_length option.
    """
    call_id = _require_nonblank_text(
        payload.get(CODEX_CALL_ID_KEY),
        _PushValidationError(
            Locale.WEB_CALL_ID_INVALID_TEMPLATE.format(line_number=line_number)
        ),
    )
    arguments = payload.get(CODEX_ARGUMENTS_KEY)
    if not isinstance(arguments, str):
        raise _PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_UNSUPPORTED_TEMPLATE.format(call_id=call_id)
        )
    try:
        decoded_value: object = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise _PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_MALFORMED_TEMPLATE.format(call_id=call_id)
        ) from exc
    if not isinstance(decoded_value, dict):
        raise _PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_NON_OBJECT_TEMPLATE.format(call_id=call_id)
        )
    decoded: dict[str, object] = decoded_value
    if (
        decoded.keys() - ELIGIBLE_WEB_ACTIONS - {WEB_RESPONSE_LENGTH_ARGUMENT}
        or not any(decoded.get(action) for action in ELIGIBLE_WEB_ACTIONS)
    ):
        logger.info(Locale.WEB_CALL_EVIDENCE_INELIGIBLE_LOG, call_id, sorted(decoded))
        return None
    return decoded


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
    session_id_text = _require_nonblank_text(
        payload.get(CODEX_SESSION_ID_KEY),
        _PushValidationError(Locale.SESSION_META_SESSION_ID_INVALID),
    )
    try:
        session_id = UUID(session_id_text)
    except ValueError as exc:
        raise _PushValidationError(Locale.SESSION_META_SESSION_ID_INVALID) from exc
    if str(session_id) != session_id_text:
        raise _PushValidationError(Locale.SESSION_META_SESSION_ID_INVALID)
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

    turn_context_payload: dict[str, object] | None = None
    for record in records:
        candidate = record.value.get(CODEX_PAYLOAD_KEY)
        if (
            record.value.get(CODEX_TYPE_KEY) == CODEX_TURN_CONTEXT_TYPE
            and isinstance(candidate, dict)
        ):
            turn_context_payload = candidate
            break
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
            CODEX_SESSION_ID_KEY: str(session_id),
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


def _has_cite_marker(payload: Mapping[str, object]) -> bool:
    output = payload.get(CODEX_OUTPUT_KEY)
    marker_start = f"{CODEX_CITE_MARKER_PREFIX}turn"
    if isinstance(output, list):
        for block in output:
            if not isinstance(block, dict):
                continue
            block_text = block.get(CODEX_TEXT_KEY)
            if isinstance(block_text, str) and marker_start in block_text:
                return True
    elif isinstance(output, str):
        return marker_start in output
    return False


def _cited_fco_text(record: _RolloutRecord, payload: Mapping[str, object]) -> str:
    output = payload.get(CODEX_OUTPUT_KEY)
    if not isinstance(output, list) or len(output) != 1:
        raise _PushValidationError(
            Locale.CITED_OUTPUT_BLOCK_INVALID_TEMPLATE.format(line_number=record.line_number)
        )
    output_block = output[0]
    if not isinstance(output_block, dict):
        raise _PushValidationError(
            Locale.CITED_OUTPUT_BLOCK_INVALID_TEMPLATE.format(line_number=record.line_number)
        )
    output_text = output_block.get(CODEX_TEXT_KEY)
    if (
        output_block.get(CODEX_TYPE_KEY) != CODEX_INPUT_TEXT_TYPE
        or not isinstance(output_text, str)
    ):
        raise _PushValidationError(
            Locale.CITED_OUTPUT_BLOCK_INVALID_TEMPLATE.format(line_number=record.line_number)
        )
    return output_text


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
    cited_outputs: list[tuple[_RolloutRecord, dict[str, object]]] = []

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
            call_id = _require_nonblank_text(
                payload.get(CODEX_CALL_ID_KEY),
                _PushValidationError(
                    Locale.WEB_CALL_ID_INVALID_TEMPLATE.format(line_number=record.line_number)
                ),
            )
            calls.setdefault(call_id, []).append(record)
        elif (
            value.get(CODEX_TYPE_KEY) == CODEX_EVENT_MESSAGE_TYPE
            and payload_type == CODEX_WEB_SEARCH_END_TYPE
        ):
            call_id = _require_nonblank_text(
                payload.get(CODEX_CALL_ID_KEY),
                _PushValidationError(
                    Locale.WEB_EVENT_CALL_ID_INVALID_TEMPLATE.format(line_number=record.line_number)
                ),
            )
            events.setdefault(call_id, []).append(record)
        elif (
            value.get(CODEX_TYPE_KEY) == CODEX_RESPONSE_ITEM_TYPE
            and payload_type == CODEX_FUNCTION_CALL_OUTPUT_TYPE
        ):
            if _has_cite_marker(payload):
                cited_outputs.append((record, payload))

    fc_rows: list[_CodexFcRow] = []
    fco_rows: list[_CodexFcoRow] = []
    turn_ref_rows: list[_CodexTurnRefRow] = []
    seen_fc_ids: set[str] = set()
    seen_fco_ids: set[str] = set()
    seen_call_ids: set[str] = set()
    for output_record, output_payload in cited_outputs:
        call_id = _require_nonblank_text(
            output_payload.get(CODEX_CALL_ID_KEY),
            _PushValidationError(
                Locale.CITED_OUTPUT_IDS_INVALID_TEMPLATE.format(
                    line_number=output_record.line_number
                )
            ),
        )
        fco_id = _require_nonblank_text(
            output_payload.get(CODEX_ID_KEY),
            _PushValidationError(
                Locale.CITED_OUTPUT_IDS_INVALID_TEMPLATE.format(
                    line_number=output_record.line_number
                )
            ),
        )
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
        call_payload_value = call_record.value.get(CODEX_PAYLOAD_KEY)
        if not isinstance(call_payload_value, dict):
            raise _PushValidationError(
                Locale.CITED_WEB_CHAIN_COUNT_TEMPLATE.format(call_id=call_id)
            )
        call_payload: dict[str, object] = call_payload_value
        fc_id = _require_nonblank_text(
            call_payload.get(CODEX_ID_KEY),
            _PushValidationError(
                Locale.WEB_CALL_FC_ID_INVALID_TEMPLATE.format(call_id=call_id)
            ),
        )
        if fc_id in seen_fc_ids:
            raise _PushValidationError(
                Locale.WEB_CALL_FC_ID_INVALID_TEMPLATE.format(call_id=call_id)
            )
        seen_fc_ids.add(fc_id)
        arguments = _web_arguments(call_payload, call_record.line_number)
        if arguments is None:
            continue
        output_text = _cited_fco_text(output_record, output_payload)
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
        event_payload_value = event_record.value.get(CODEX_PAYLOAD_KEY)
        if not isinstance(event_payload_value, dict):
            raise _PushValidationError(
                Locale.CITED_WEB_CHAIN_COUNT_TEMPLATE.format(call_id=call_id)
            )
        event_payload: dict[str, object] = event_payload_value
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
            result_url = result.url
            if (
                not isinstance(result_url, str)
                or not result_url.strip()
                or result_url != result_url.strip()
                or _has_control_character(result_url)
            ):
                continue
            turn_ref_rows.append(
                _CodexTurnRefRow(
                    ref_id=section.ref_id,
                    call_id=call_id,
                    domain=result.domain,
                    snippet=result.snippet,
                    thumbnail_url=result.thumbnail_url,
                    title=result.title,
                    url=result_url,
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
    store: AiAugmentBackendStore,
    *,
    codex_match_version: int = 1,
) -> None:
    id_col = duckdb_quote_identifier(CODEX_ID_COL)
    store._execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CODEX_FC_TABLE} (
            {id_col} BIGINT PRIMARY KEY,
            {duckdb_quote_identifier(CODEX_FC_TIMESTAMP_COL)} TIMESTAMPTZ NOT NULL,
            {duckdb_quote_identifier(CODEX_FC_ID_COL)} VARCHAR NOT NULL UNIQUE,
            {duckdb_quote_identifier(CODEX_FC_NAME_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_FC_NAMESPACE_COL)} VARCHAR NOT NULL,
            {duckdb_quote_identifier(CODEX_FC_ARGUMENTS_COL)} JSON NOT NULL
        )
        """
    )
    store._execute(
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
    store._execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CODEX_EVIDENCE_AUDIT_TABLE} (
            {duckdb_quote_identifier(CODEX_EVIDENCE_AUDIT_ID_COL)} BIGINT PRIMARY KEY,
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
    store._execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CODEX_FCO_TABLE} (
            {id_col} BIGINT PRIMARY KEY,
            {duckdb_quote_identifier(CODEX_FCO_TIMESTAMP_COL)} TIMESTAMPTZ NOT NULL,
            {duckdb_quote_identifier(CODEX_FCO_ID_COL)} VARCHAR NOT NULL UNIQUE
        )
        """
    )
    store._execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CODEX_CALLS_TABLE} (
            {id_col} BIGINT PRIMARY KEY,
            {duckdb_quote_identifier(CODEX_CALL_ID_COL)} VARCHAR NOT NULL UNIQUE,
            {duckdb_quote_identifier(CODEX_FC_ID_COL)} VARCHAR NOT NULL UNIQUE,
            {duckdb_quote_identifier(CODEX_FCO_ID_COL)} VARCHAR NOT NULL UNIQUE,
            {duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} VARCHAR NOT NULL
        )
        """
    )
    store._execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CODEX_TURN_REF_TABLE} (
            {id_col} BIGINT PRIMARY KEY,
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
        store._execute(
            f"""
            CREATE OR REPLACE VIEW {CODEX_TURN_REF_NORMALIZED_VIEW} AS
            SELECT
                *,
                {normalized_tokens_sql(duckdb_quote_identifier(CODEX_CITE_TEXT_COL))}
                    AS {duckdb_quote_identifier(CODEX_CITE_TOKENS_COL)}
            FROM {CODEX_TURN_REF_TABLE}
            """
        )


def _next_codex_row_id(store: AiAugmentBackendStore, table_name: str) -> int:
    """Allocation shares the caller's Store transaction, so rollback consumes no IDs."""
    row = store._execute(
        f"SELECT COALESCE(MAX(id), 0) + 1 FROM {duckdb_quote_identifier(table_name)}"
    ).fetchone()
    assert row is not None
    return int(row[0])


def _insert_or_validate(
    store: AiAugmentBackendStore,
    *,
    table_name: str,
    key_column: str,
    key_value: str,
    columns: tuple[str, ...],
    values: tuple[object, ...],
) -> None:
    projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
    existing = store._execute(
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
    columns = (CODEX_ID_COL, *columns)
    values = (_next_codex_row_id(store, table_name), *values)
    projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _column in columns)
    store._execute(
        f"INSERT INTO {table_name} ({projection}) VALUES ({placeholders})",
        list(values),
    )


def _datetime_value(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def persist_rollout_index(
    store: AiAugmentBackendStore,
    rollout_index: _RolloutIndex,
    *,
    codex_match_version: int = 1,
) -> None:
    _create_codex_schema(
        store,
        codex_match_version=codex_match_version,
    )
    current_call_ids = {row.call_id for row in rollout_index.fc_rows}
    existing_call_rows: list[tuple[str]] = store._execute(
        f"SELECT {duckdb_quote_identifier(CODEX_CALL_ID_COL)} "
        f"FROM {CODEX_CALLS_TABLE} WHERE "
        f"{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?",
        [rollout_index.session.rollout_filename],
    ).fetchall()
    existing_call_ids = {
        row[0]
        for row in existing_call_rows
    }
    if not existing_call_ids.issubset(current_call_ids):
        raise _PushValidationError(Locale.PROVENANCE_PREFIX_OLDER)
    current_turn_keys = {(row.call_id, row.ref_id) for row in rollout_index.turn_ref_rows}
    existing_turn_rows: list[tuple[str, str]] = store._execute(
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
    existing_turn_keys = {
        (row[0], row[1])
        for row in existing_turn_rows
    }
    if not existing_turn_keys.issubset(current_turn_keys):
        raise _PushValidationError(Locale.CITATION_PREFIX_OLDER)

    fc_by_call = {row.call_id: row for row in rollout_index.fc_rows}
    fco_by_call = {row.call_id: row for row in rollout_index.fco_rows}
    if set(fc_by_call) != current_call_ids or set(fco_by_call) != current_call_ids:
        raise _PushValidationError(Locale.ROLLOUT_LINKAGES_INCOMPLETE)
    for function_call_row in rollout_index.fc_rows:
        _insert_or_validate(
            store,
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
            store,
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
            store,
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
        columns: tuple[str, ...] = (
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
        existing = store._execute(
            f"SELECT {projection} FROM {CODEX_TURN_REF_TABLE} WHERE "
            f"{duckdb_quote_identifier(CODEX_CALL_ID_COL)} = ? AND "
            f"{duckdb_quote_identifier(CODEX_REF_ID_COL)} = ?",
            [turn_ref_row.call_id, turn_ref_row.ref_id],
        ).fetchall()
        values: tuple[object, ...] = (
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
            columns = (CODEX_ID_COL, *columns)
            values = (_next_codex_row_id(store, CODEX_TURN_REF_TABLE), *values)
            projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
            placeholders = ", ".join("?" for _column in columns)
            store._execute(
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
        integrity_row = store._execute(
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

    linkage_row = store._execute(
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

    persisted_call_rows: list[tuple[str]] = store._execute(
        f"SELECT {duckdb_quote_identifier(CODEX_CALL_ID_COL)} "
        f"FROM {CODEX_CALLS_TABLE} WHERE "
        f"{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?",
        [rollout_index.session.rollout_filename],
    ).fetchall()
    persisted_call_ids = {row[0] for row in persisted_call_rows}
    persisted_turn_rows: list[tuple[str, str]] = store._execute(
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
    persisted_turn_keys = {
        (row[0], row[1])
        for row in persisted_turn_rows
    }
    if persisted_call_ids != current_call_ids or persisted_turn_keys != current_turn_keys:
        raise _PushValidationError(Locale.PROVENANCE_PREFIX_MISMATCH)


def _render_fco_timestamp(value: datetime) -> str:
    return (
        value
        .astimezone(timezone.utc)
        .isoformat(timespec=FCO_TIMESTAMP_TIMESPEC)
        .replace("+00:00", "Z")
    )


def _evidence_candidates(
    rows: list[tuple[str, str, str, int, str, datetime, object]],
) -> tuple[_EvidenceCandidate, ...]:
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
                ref_id=ref_id,
                call_id=call_id,
                cite_text=cite_text,
                excerpt_position=excerpt_position,
                url=url,
                fco_timestamp=fco_timestamp,
                arguments_json=arguments_json,
            )
        )
    return tuple(candidates)


def _exact_evidence_candidates(
    store: AiAugmentBackendStore,
    *,
    rollout_filename: str,
    excerpt: str,
) -> tuple[_EvidenceCandidate, ...]:
    rows = store._execute(
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
    store: AiAugmentBackendStore,
    excerpt: str,
) -> tuple[str, ...]:
    row = store._execute(
        f"SELECT {normalized_tokens_sql('?')}",
        [excerpt],
    ).fetchone()
    if row is None or not isinstance(row[0], list):
        return ()
    tokens: list[str] = row[0]
    return tuple(tokens)


def _near_evidence_candidates(
    store: AiAugmentBackendStore,
    *,
    rollout_filename: str,
    url: str,
    submitted_tokens: tuple[str, ...],
) -> tuple[_EvidenceCandidate, ...]:
    if not submitted_tokens:
        return ()
    rows = store._execute(
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
    store: AiAugmentBackendStore,
    submission_payload: Submission | StandardizedSubmission,
    *,
    rollout_filename: str,
    codex_match_version: int,
) -> _EvidenceAssessment:
    assessments: list[_EvidenceItemAssessment] = []
    evidence_number = 0
    for field, field_submission in submission_payload.evidence_items():
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

            exact_candidates = _exact_evidence_candidates(store,

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
                normalized_tokens = _normalized_evidence_tokens(store, evidence.excerpt)
                near_candidates = _near_evidence_candidates(store,

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
    submission_payload: Submission | StandardizedSubmission,
    assessment: _EvidenceAssessment,
) -> _RetryObligations:
    fields: dict[str, _RetryFieldObligation] = {}
    for field, field_submission in submission_payload.evidence_items():
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
    commit_record: BackendCommitRecord,
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
            commit_record.record_id,
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
    store: AiAugmentBackendStore,
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
                    current_tokens = _normalized_evidence_tokens(store,
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
    store: AiAugmentBackendStore,
    *,
    baseline_json: str,
    baseline_attempt_id: UUID,
    original_pull: HttpRequestLogRecord,
) -> _RetryObligations:
    try:
        obligations = _RetryObligations.model_validate_json(baseline_json)
        rows: list[tuple[str, str]] = store._execute(
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
            [str(original_pull.record_id), str(baseline_attempt_id)],
        ).fetchall()
        for submission_json, assessment_json in rows:
            submission = StandardizedSubmission.model_validate_with_http_records(submission_json)
            assessment = _assessment_from_audit(
                submission,
                _EvidenceAttemptAudit.model_validate_json(assessment_json),
            )
            obligations, violations = _apply_retry_obligations(
                store,
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
    store: AiAugmentBackendStore,
    *,
    original_pull: HttpRequestLogRecord,
    commit_record: BackendCommitRecord,
    namekey: NameKey,
    attempt_timestamp: datetime,
    submission_payload: Submission | StandardizedSubmission,
    assessment: _EvidenceAssessment,
) -> tuple[str, ...]:
    session_id = commit_record.commit_request_body.codex_session_record.session_id
    assert session_id is not None
    run_id_text = str(original_pull.record_id)
    session_id_text = str(session_id)
    attempt_id_text = str(commit_record.record_id)
    namekey_json = namekey.to_json_key()
    initial_obligations = _retry_obligations_from_assessment(
        submission_payload,
        assessment,
    )
    submission_json = submission_payload.model_dump_json(by_alias=True)
    assessment_json = _assessment_audit(assessment).model_dump_json()
    inserted_baseline = False
    if not assessment.accepted:
        inserted_baseline = (
            store._execute(
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
                    namekey_json,
                    session_id_text,
                    attempt_id_text,
                    attempt_timestamp,
                    initial_obligations.model_dump_json(),
                ],
            ).fetchone()
            is not None
        )

    baseline_row: tuple[str, str, str, str] | None = store._execute(
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
            baseline_attempt_id_text,
            baseline_json,
        ) = baseline_row
        if (
            baseline_namekey != namekey_json
            or baseline_session_id != session_id_text
        ):
            raise _PushValidationError(Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH)
        if inserted_baseline:
            obligations = initial_obligations
            violations = tuple(
                Locale.EVIDENCE_WITHDRAWAL_WITHOUT_BASELINE
                for item in assessment.items
                if item.outcome == EVIDENCE_OUTCOME_WITHDRAWN
            )
        else:
            try:
                baseline_attempt_id = UUID(baseline_attempt_id_text)
            except ValueError as exc:
                raise _PushValidationError(
                    Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH
                ) from exc
            if str(baseline_attempt_id) != baseline_attempt_id_text:
                raise _PushValidationError(
                    Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH
                )
            obligations = _derive_retry_obligations(
                store,
                baseline_json=baseline_json,
                baseline_attempt_id=baseline_attempt_id,
                original_pull=original_pull,
            )
            if not isinstance(submission_payload, StandardizedSubmission):
                raise _PushConfigurationError(Locale.EVIDENCE_AUDIT_REPLAY_FAILED)
            _next_obligations, violations = _apply_retry_obligations(
                store,
                submission_payload,
                assessment,
                obligations,
            )

    applied = not violations
    accepted = assessment.accepted and applied
    store._execute(
        f"""
        INSERT INTO {CODEX_EVIDENCE_AUDIT_TABLE} (
            {duckdb_quote_identifier(CODEX_EVIDENCE_AUDIT_ID_COL)},
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            _next_codex_row_id(store, CODEX_EVIDENCE_AUDIT_TABLE),
            attempt_id_text,
            run_id_text,
            namekey_json,
            session_id_text,
            attempt_timestamp,
            submission_json,
            assessment_json,
            applied,
            accepted,
        ],
    )
    return violations


def _retry_baseline_exists(
    store: AiAugmentBackendStore,
    *,
    original_pull: HttpRequestLogRecord,
    namekey: NameKey,
    session_id: UUID,
) -> bool:
    row = store._execute(
        f"""
        SELECT
            {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)},
            {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)}
        FROM {CODEX_RETRY_BASELINE_TABLE}
        WHERE {duckdb_quote_identifier(CODEX_RETRY_RUN_ID_COL)} = ?
        """,
        [str(original_pull.record_id)],
    ).fetchone()
    if row is None:
        return False
    if row != (namekey.to_json_key(), str(session_id)):
        raise _PushValidationError(Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH)
    return True


def _rollout_ref_urls(
    store: AiAugmentBackendStore,
    *,
    rollout_filename: str,
) -> dict[str, str]:
    rows: list[tuple[str, str, str]] = store._execute(
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
        rows_by_ref.setdefault(ref_id, set()).add((call_id, url))
    return {
        ref_id: next(iter(ref_rows))[1]
        for ref_id, ref_rows in rows_by_ref.items()
        if len(ref_rows) == 1
    }


def validate_submission_evidence(
    store: AiAugmentBackendStore,
    submission_payload: Submission | StandardizedSubmission,
    *,
    rollout_filename: str,
    codex_match_version: int = 1,
) -> ValidatedEvidence:
    assessment = assess_submission_evidence(
        store,
        submission_payload,
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
    request: requests.PreparedRequest,
    response: requests.Response,
    *,
    started_ns: int,
) -> HttpRequestLogRecord:
    parsed = urlsplit(request.url or "")
    return HttpRequestLogRecord(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        method=request.method or "",
        scheme=parsed.scheme,
        host=parsed.hostname or "",
        port=parsed.port,
        path=parsed.path,
        query=parsed.query,
        request_headers=dict(request.headers),
        request_body=_request_body_for_authoritative_log(_prepared_request_body(request)),
        response_code=response.status_code,
        response_headers=dict(response.headers),
        response_body=response.content.decode(TEXT_ENCODING),
        received_at_unix_usec=None,
        ready_to_respond_at_unix_usec=time.time_ns() // NANOSECONDS_PER_MICROSECOND,
        duration_usec=(time.monotonic_ns() - started_ns) // NANOSECONDS_PER_MICROSECOND,
    )


def _prepared_request_body(request: requests.PreparedRequest) -> bytes:
    if request.body is None:
        return b""
    if isinstance(request.body, bytes):
        return request.body
    if isinstance(request.body, str):
        return request.body.encode(TEXT_ENCODING)
    raise ValueError(Locale.BUFFERED_REQUEST_REQUIRED)


def _validated_http_record(record: HttpRequestLogRecord) -> HttpRequestLogRecord:
    validated = HttpRequestLogRecord.model_validate_json(record.model_dump_json())
    if (
        validated.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
        or validated.record_id.version != 7
    ):
        raise _PushValidationError(Locale.REPLAY_RECORD_CONTOUR_INVALID)
    route = (validated.method, validated.path)
    if validated.method == HTTP_POST_METHOD and validated.path in RUN_OUTCOME_PATHS:
        try:
            RunOutcomeRecord.from_http_request_log_record(validated)
        except ValueError as exc:
            raise _PushValidationError(Locale.REPLAY_RECORD_CONTOUR_INVALID) from exc
        return validated

    if route == (HTTP_POST_METHOD, VALIDATE_PATH):
        try:
            BackendValidationRecord.from_http_request_log_record(validated)
        except ValueError as exc:
            raise _PushValidationError(Locale.REPLAY_COMMIT_INVALID) from exc
        return validated

    if route != AUTHORITATIVE_COMMIT_ROUTE:
        transport_failure = (
            validated.host != SYNTHETIC_COMMIT_HOST
            and route not in AUTHORITATIVE_FASTAPI_ROUTES
            and validated.response_code is None
            and validated.response_headers is None
            and validated.response_body is None
        )
        if (
            not transport_failure and (validated.response_code is None
            or validated.response_headers is None
            or validated.response_body is None)
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
    store: AiAugmentBackendStore,
    value: object,
) -> CommitRequestBody:
    if not isinstance(value, str):
        raise _PushValidationError(Locale.REPLAY_COMMIT_INVALID)
    try:
        return CommitRequestBody.from_serialized_json(
            value,
            resolve_http_record=lambda record_id: store._http_record_with_ordinal(
                record_id,
            )[1],
        )
    except (KeyError, ValidationError, ValueError) as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_INVALID) from exc


def _backend_commit_record(
    store: AiAugmentBackendStore,
    record: HttpRequestLogRecord,
) -> BackendCommitRecord:
    try:
        return BackendCommitRecord.from_http_request_log_record(
            record,
            resolve_http_record=lambda record_id: store._http_record_with_ordinal(
                record_id,
            )[1],
        )
    except (KeyError, ValidationError, ValueError) as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_INVALID) from exc


def _authoritative_log_records(
    value: bytes,
) -> tuple[tuple[HttpRequestLogRecord, int], ...]:
    records: list[tuple[HttpRequestLogRecord, int]] = []
    byte_offset = AUTHORITATIVE_EMPTY_OFFSET
    for line_number, line in enumerate(
        value.splitlines(keepends=True),
        start=AUTHORITATIVE_FIRST_LINE,
    ):
        if not line.endswith(b"\n") or not line.strip():
            raise _PushValidationError(
                Locale.REPLAY_LOG_LINE_INVALID_TEMPLATE.format(line_number=line_number)
            )
        try:
            record = _validated_http_record(
                HttpRequestLogRecord.model_validate_json(line)
            )
        except (ValidationError, _PushValidationError) as exc:
            raise _PushValidationError(
                Locale.REPLAY_LOG_LINE_INVALID_TEMPLATE.format(line_number=line_number)
            ) from exc
        byte_offset += len(line)
        records.append((record, byte_offset))
    return tuple(records)


def _source_key_header(filename: str, line_count: int) -> str:
    return source_key_header_value(filename, line_count)


def _parse_source_key_header(value: object) -> tuple[str, int]:
    try:
        return source_key_from_header_value(value)
    except ValueError as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_SOURCE_KEY_INVALID) from exc


def _name_key_header(namekey: NameKey) -> str:
    return name_key_header_value(namekey)


def name_key_header(namekey: NameKey) -> str:
    return _name_key_header(namekey)


def _parse_name_key_header(value: object) -> NameKey:
    try:
        return name_key_from_header_value(value)
    except ValueError as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_NAME_KEY_INVALID) from exc


def parse_name_key_header(value: object) -> NameKey:
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


def _original_pull_record(
    store: AiAugmentBackendStore,
    pull_record: HttpRequestLogRecord,
) -> HttpRequestLogRecord:
    pull_ordinal, pull = store._http_record_with_ordinal(pull_record.record_id)
    if (pull.method, pull.path) != (HTTP_GET_METHOD, PULL_PATH):
        raise _PushValidationError(Locale.REPLAY_COMMIT_PULL_INVALID)
    if _response_content_type(pull) != MARKDOWN_MEDIA_TYPE:
        return pull
    row = store._execute(
        f"SELECT records.{AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
        f"FROM {AUTHORITATIVE_RECORDS_TABLE} AS records "
        f"JOIN {AUTHORITATIVE_ATTEMPTS_TABLE} AS attempts "
        f"ON records.{AUTHORITATIVE_RECORD_ID_COLUMN} = "
        f"attempts.{AUTHORITATIVE_ATTEMPT_COMMIT_ID_COLUMN} "
        f"WHERE records.{AUTHORITATIVE_RECORD_ORDINAL_COLUMN} < ? "
        f"ORDER BY records.{AUTHORITATIVE_RECORD_ORDINAL_COLUMN} DESC LIMIT 1",
        [pull_ordinal],
    ).fetchone()
    if row is None:
        raise _PushValidationError(Locale.REPLAY_COMMIT_PULL_INVALID)
    try:
        prior_record = HttpRequestLogRecord.model_validate_json(str(row[0]))
        prior_commit_record = _backend_commit_record(store, prior_record)
    except (ValidationError, _PushValidationError) as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_PULL_INVALID) from exc
    return _original_pull_record(
        store,
        prior_commit_record.commit_request_body.pull_record,
    )


def _namekey_from_original_pull(pull: HttpRequestLogRecord) -> NameKey:
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
        })
    except (StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _PushValidationError(Locale.REPLAY_COMMIT_PULL_INVALID) from exc


def _failed_attempt_record(
    *,
    commit_record: BackendCommitRecord,
    stage: BackendLifecycle,
    error: Exception,
) -> AgentRuntimeAttemptRecord:
    logger.error(
        Locale.POST_COMMIT_VALIDATION_FAILED_LOG,
        commit_record.record_id,
        stage,
        error,
    )
    return AgentRuntimeAttemptRecord(
        attempt=AgentRuntimeAttempt(
            pull_record=commit_record.commit_request_body.pull_record,
            commit_record=commit_record,
            post_commit_validation=PostCommitValidation(
                stage=stage,
                result=BackendLifecycle.CONFIGURATION_ERROR,
                detail=Locale.CONFIGURATION_ERROR_DETAIL,
            ),
        ),
        submission=None,
        ground_truth_innerdict=None,
    )


def _validate_projected_commit(
    store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    record: HttpRequestLogRecord,
) -> tuple[AgentRuntimeAttemptRecord, bool]:
    commit_record = _backend_commit_record(store, record)
    commit = commit_record.commit_request_body
    pull = commit.pull_record
    push = commit.push_record
    session_id = commit.codex_session_record.session_id
    rollout = commit.codex_session_record.codex_rollout_record
    appendwatch_report = commit.codex_session_record.appendwatch_report_record
    assert session_id is not None
    assert rollout is not None
    assert appendwatch_report is not None
    stage = BackendLifecycle.CONFIGURATION
    try:
        namekey = _parse_name_key_header(
            record.request_headers.get(NAME_KEY_HEADER)
        )
        pull_ordinal, _pull = store._http_record_with_ordinal(pull.record_id)
        push_ordinal, _push = store._http_record_with_ordinal(push.record_id)
        commit_ordinal, _commit_record = store._http_record_with_ordinal(record.record_id)
        if not (
            pull_ordinal < push_ordinal < commit_ordinal
            and (pull.method, pull.path) == (HTTP_GET_METHOD, PULL_PATH)
            and pull.response_code == status.HTTP_200_OK
            and (push.method, push.path) == (HTTP_POST_METHOD, PUSH_PATH)
            and push.response_code == status.HTTP_202_ACCEPTED
            and isinstance(push.request_body, str)
        ):
            raise _PushValidationError(Locale.REPLAY_COMMIT_LINK_INVALID)
        original_pull = _original_pull_record(store, pull)
        if _namekey_from_original_pull(original_pull) != namekey:
            raise _PushValidationError(Locale.REPLAY_COMMIT_NAME_KEY_INVALID)
        filename, source_line_count = _parse_source_key_header(
            record.request_headers.get(SOURCE_KEY_HEADER)
        )
        if source_line_count != rollout.line_count:
            raise _PushValidationError(Locale.REPLAY_COMMIT_SOURCE_KEY_INVALID)
        stage = BackendLifecycle.ROLLOUT_INDEX
        try:
            rollout_path = runtime.pipeline_config.rollout_cas.validated_rollout(
                rollout
            )
        except (OSError, ValueError) as exc:
            raise _PushValidationError(str(exc)) from exc
        rollout_archive = _ArchivedFile(
            path=rollout_path,
            size=rollout.size,
            sha256=rollout.sha256,
            line_count=rollout.line_count,
        )
        stage = BackendLifecycle.APPENDWATCH_REPORT_VALIDATION
        return _execute_attempt(
            store,
            runtime,
            commit_record=commit_record,
            rollout_archive=rollout_archive,
            appendwatch_report=appendwatch_report,
            rollout_relative_path=PurePosixPath(filename),
            original_pull=original_pull,
            namekey=namekey,
        )
    except (ModelHttpRequired, ReplayInputMissing):
        raise
    except Exception as exc:
        return (
            _failed_attempt_record(
                commit_record=commit_record,
                stage=stage,
                error=exc,
            ),
            False,
        )


def _apply_validation_record(
    store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    record: HttpRequestLogRecord,
) -> tuple[AgentRuntimeAttemptRecord, bool]:
    validation_record = BackendValidationRecord.from_http_request_log_record(record)
    body = validation_record.validation_request_body
    ordinal, _ = store._http_record_with_ordinal(record.record_id)
    commit_ordinal, commit = store._http_record_with_ordinal(body.commit_id)
    if commit_ordinal >= ordinal or record.request_headers != commit.request_headers:
        raise ReplayInputMissing("Validation commit linkage is invalid")
    typed_commit = _backend_commit_record(store, commit)
    session_id = typed_commit.commit_request_body.codex_session_record.session_id
    namekey = name_key_from_header_value(commit.request_headers.get(NAME_KEY_HEADER))
    placeholders = ", ".join("?" for _path in RUN_OUTCOME_PATHS)
    outcomes = store._execute(
        f"SELECT {AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} FROM {AUTHORITATIVE_RECORDS_TABLE} "
        f"WHERE {AUTHORITATIVE_RECORD_METHOD_COLUMN} = ? "
        f"AND {AUTHORITATIVE_RECORD_PATH_COLUMN} IN ({placeholders})",
        [HTTP_POST_METHOD, *(path.value for path in sorted(RUN_OUTCOME_PATHS))],
    ).fetchall()
    for (payload,) in outcomes:
        outcome = RunOutcomeRecord.from_http_request_log_record(
            HttpRequestLogRecord.model_validate_json(payload),
        )
        if (
            outcome.response_code != HTTPStatus.CONFLICT
            and session_id is not None
            and outcome.run_outcome_request.namekey == namekey
            and outcome.run_outcome_response_body.codex_session_record.session_id == session_id
        ):
            raise ReplayInputMissing("Validation must precede its session's run outcome")
    inputs: list[HttpRequestLogRecord] = []
    for record_id in body.http_record_ids:
        input_ordinal, http_record = store._http_record_with_ordinal(record_id)
        if input_ordinal >= ordinal or http_record.ready_to_respond_at_unix_usec is None:
            raise ReplayInputMissing("Validation HTTP input must precede validation")
        inputs.append(http_record)
    http = ModelHttpInterceptor.from_records(inputs)
    with submission_http_context(http):
        evaluated, commit_database = _validate_projected_commit(
            store, runtime, commit,
        )
    observed = body.post_commit_validation
    submission = evaluated.submission
    if (
        evaluated.attempt.post_commit_validation != observed
        or (None if submission is None else type(submission).__name__) != body.submission_type
        or (None if submission is None else submission.model_dump(mode="json", by_alias=True))
        != body.submission
        or http.record_ids != body.http_record_ids
    ):
        raise ReplayInputMissing("Recorded validation does not match its replay inputs")
    return evaluated.model_copy(update={
        "http_records": tuple(inputs), "validation_record": validation_record,
    }), commit_database


def _run_outcome_references(
    store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    namekey: NameKey,
    session_id: UUID | None,
    *,
    before_ordinal: int | None = None,
) -> tuple[BackendCommitRecord | None, BackendValidationRecord | None]:
    if session_id is None:
        return None, None
    records = store._execute(
        f"SELECT {AUTHORITATIVE_RECORD_ORDINAL_COLUMN}, {AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
        f"FROM {AUTHORITATIVE_RECORDS_TABLE} WHERE {AUTHORITATIVE_RECORD_PATH_COLUMN} = ? "
        f"ORDER BY {AUTHORITATIVE_RECORD_ORDINAL_COLUMN} DESC",
        [COMMIT_PATH],
    ).fetchall()
    for ordinal, payload in records:
        if before_ordinal is not None and ordinal >= before_ordinal:
            continue
        commit = _backend_commit_record(store, HttpRequestLogRecord.model_validate_json(payload))
        if (
            commit.commit_request_body.codex_session_record.session_id != session_id
            or name_key_from_header_value(commit.request_headers.get(NAME_KEY_HEADER)) != namekey
        ):
            continue
        row = store._execute(
            f"SELECT {AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN} FROM {AUTHORITATIVE_ATTEMPTS_TABLE} "
            f"WHERE {AUTHORITATIVE_ATTEMPT_COMMIT_ID_COLUMN} = ?",
            [str(commit.record_id)],
        ).fetchone()
        validations = store._execute(
            f"SELECT {AUTHORITATIVE_RECORD_ORDINAL_COLUMN}, {AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
            f"FROM {AUTHORITATIVE_RECORDS_TABLE} WHERE {AUTHORITATIVE_RECORD_PATH_COLUMN} = ? "
            f"AND json_extract_string({AUTHORITATIVE_RECORD_PAYLOAD_COLUMN}, "
            "'$.request_body') IS NOT NULL",
            [VALIDATE_PATH],
        ).fetchall()
        linked: list[BackendValidationRecord] = []
        for validation_ordinal, validation_payload in validations:
            if before_ordinal is not None and validation_ordinal >= before_ordinal:
                continue
            validation = BackendValidationRecord.from_http_request_log_record(
                HttpRequestLogRecord.model_validate_json(validation_payload),
            )
            if validation.validation_request_body.commit_id != commit.record_id:
                continue
            if (
                validation_ordinal <= ordinal
                or validation.request_headers != commit.request_headers
            ):
                raise ReplayInputMissing(Locale.RUN_OUTCOME_VALIDATION_LINKAGE_CORRUPT)
            linked.append(validation)
        if not linked:
            if row is not None:
                raise ReplayInputMissing(Locale.RUN_OUTCOME_DURABLE_VALIDATION_MISSING)
            return commit, None
        if len(linked) != 1 or row is None:
            raise ReplayInputMissing(Locale.RUN_OUTCOME_PROJECTION_INCONSISTENT)
        # Rehydrate against recorded provider inputs; never reapply evidence/output writes.
        attempt = _attempt_record_from_serialized_json(runtime, row[0], commit_http_record=commit)
        validation = linked[0]
        if (
            attempt.attempt.commit_record.model_dump() != commit.model_dump()
            or attempt.validation_record is None
            or attempt.validation_record.model_dump() != validation.model_dump()
        ):
            raise ReplayInputMissing(Locale.RUN_OUTCOME_REPLAY_INPUTS_DIFFER)
        for provider in attempt.http_records:
            provider_ordinal, persisted = store._http_record_with_ordinal(provider.record_id)
            validation_ordinal, _ = store._http_record_with_ordinal(validation.record_id)
            if persisted != provider or provider_ordinal >= validation_ordinal:
                raise ReplayInputMissing(Locale.RUN_OUTCOME_PROVIDER_INPUT_CORRUPT)
        return commit, validation
    return None, None


def _run_outcome_code(
    path: str,
    session: CodexSessionRecord,
    validation: BackendValidationRecord | None,
) -> HTTPStatus:
    if (
        session.session_id is None
        or session.codex_rollout_record is None
        or session.appendwatch_report_record is None
    ):
        return HTTPStatus.INTERNAL_SERVER_ERROR
    accepted = validation is not None and (
        validation.validation_request_body.post_commit_validation.result
        is BackendLifecycle.ACCEPTED
    )
    if (path == RunOutcomePath.COMPLETED and not accepted) or (
        path == RunOutcomePath.FAILED and accepted
    ):
        return HTTPStatus.CONFLICT
    return HTTPStatus.OK


def _run_outcome_record(
    store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext | None,
    request: RunOutcomeRequestRecord,
) -> RunOutcomeRecord:
    if runtime is None:
        raise BackendStoreException(Locale.STORE_RUNTIME_UNAVAILABLE)
    ipc_request = RunOutcomeRequest.from_http_request_log_record(
        HttpRequestLogRecord.model_validate(request.model_dump()),
    )
    commit, validation = _run_outcome_references(
        store,
        runtime,
        ipc_request.namekey,
        request.codex_session_record.session_id,
    )
    body = RunOutcomeResponseBody(
        pull_record_id=request.pull_record_id,
        push_record_id=request.push_record_id,
        commit_record_id=None if commit is None else commit.record_id,
        validation_record_id=None if validation is None else validation.record_id,
        run_outcome_record_id=request.record_id,
        codex_session_record=request.codex_session_record,
    )
    rollout = request.codex_session_record.codex_rollout_record
    headers = None
    if rollout is not None:
        if request.rollout_filename is None:
            raise BackendStoreException(Locale.RUN_OUTCOME_ROLLOUT_FILENAME_MISSING)
        headers = {
            SOURCE_KEY_HEADER: _source_key_header(request.rollout_filename, rollout.line_count)
        }
    return RunOutcomeRecord.from_run_outcome_request(
        ipc_request,
        response_code=_run_outcome_code(request.path, request.codex_session_record, validation),
        response_headers=headers,
        response_body=body,
        ready_to_respond_at_unix_usec=time.time_ns() // NANOSECONDS_PER_MICROSECOND,
    )


def _verify_run_outcome_record(
    store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    outcome: RunOutcomeRecord,
) -> None:
    body = outcome.run_outcome_response_body
    ordinal, _ = store._http_record_with_ordinal(outcome.record_id)
    commit, validation = _run_outcome_references(
        store,
        runtime,
        outcome.run_outcome_request.namekey,
        body.codex_session_record.session_id,
        before_ordinal=ordinal,
    )
    if (
        body.commit_record_id != (None if commit is None else commit.record_id)
        or body.validation_record_id != (None if validation is None else validation.record_id)
        or outcome.response_code
        != _run_outcome_code(outcome.path, body.codex_session_record, validation)
    ):
        raise ReplayInputMissing(Locale.RUN_OUTCOME_REPLAY_MISMATCH)


def _apply_run_outcome_record(
    store: AiAugmentBackendStore,
    outcome: RunOutcomeRecord,
) -> None:
    session_id = outcome.run_outcome_response_body.codex_session_record.session_id
    if outcome.response_code == HTTPStatus.CONFLICT or session_id is None:
        return
    exists = store._execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
        [CODEX_OUTPUT_ROWS_TABLE],
    ).fetchone()
    if exists is None or int(exists[0]) == 0:
        return
    namekey = outcome.run_outcome_request.namekey
    rows = store._execute(
        f"SELECT {duckdb_quote_identifier(KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL)} "
        f"FROM {CODEX_OUTPUT_ROWS_TABLE} "
        f"WHERE {duckdb_quote_identifier(KTP_NAMEKEY_COL)} = ? "
        f"AND {duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL)} IS NULL",
        [namekey.to_json_key()],
    ).fetchall()
    outcome_ordinal, _ = store._http_record_with_ordinal(outcome.record_id)
    updated = 0
    for (value,) in rows:
        commit_id = UUID(str(value))
        commit_ordinal, http_commit = store._http_record_with_ordinal(commit_id)
        commit = _backend_commit_record(store, http_commit)
        if commit.commit_request_body.codex_session_record.session_id != session_id:
            continue
        if name_key_from_header_value(commit.request_headers.get(NAME_KEY_HEADER)) != namekey:
            raise ReplayInputMissing("Run outcome commit NameKey does not match")
        linked = store._execute(
            f"SELECT json_extract_string({AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN}, "
            "'$.validation_record.record_id') "
            f"FROM {AUTHORITATIVE_ATTEMPTS_TABLE} "
            f"WHERE {AUTHORITATIVE_ATTEMPT_COMMIT_ID_COLUMN} = ?",
            [str(commit_id)],
        ).fetchone()
        if linked is None or linked[0] is None:
            raise ReplayInputMissing("Run outcome accepted row has no validation record")
        validation_ordinal, http_validation = store._http_record_with_ordinal(UUID(linked[0]))
        validation = BackendValidationRecord.from_http_request_log_record(http_validation)
        body = validation.validation_request_body
        if (
            body.commit_id != commit_id
            or validation.request_headers != commit.request_headers
            or body.post_commit_validation.result is not BackendLifecycle.ACCEPTED
            or not commit_ordinal < validation_ordinal < outcome_ordinal
        ):
            raise ReplayInputMissing("Run outcome validation linkage is invalid")
        store._execute(
            f"UPDATE {CODEX_OUTPUT_ROWS_TABLE} SET "
            f"{duckdb_quote_identifier(KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL)} = ?, "
            f"{duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL)} = ? "
            f"WHERE {duckdb_quote_identifier(KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL)} = ?",
            [str(validation.record_id), str(outcome.record_id), str(commit.record_id)],
        )
        updated += 1
    if updated:
        _replace_codex_output_view(store)
        logger.info("Run outcome %s: materialized %d accepted sections", outcome.record_id, updated)


def _attempt_record_from_serialized_json(
    runtime: AiAugmentBackendContext,
    value: str,
    *,
    commit_http_record: HttpRequestLogRecord,
) -> AgentRuntimeAttemptRecord:
    namekey = name_key_from_header_value(
        commit_http_record.request_headers.get(NAME_KEY_HEADER)
    )
    singular_outerdict = _configured_ai_augment_singular_outerdict(
        namekey,
        runtime.ai_augment_singular_outerdicts,
    )
    procedure = (
        None
        if not singular_outerdict.docx_innerdicts
        else singular_outerdict.docx_innerdicts[0].procedure
    )
    return AgentRuntimeAttemptRecord.from_serialized_json(
        value,
        procedure=procedure,
    )


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
    rollout: CodexRolloutRecord,
    rollout_filename: str,
    appendwatch_report: bytes,
    namekey: NameKey,
) -> BackendCommitRecord:
    codex_session_record = CodexSessionRecord(
        session_id=session_id,
        codex_rollout_record=rollout,
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
                rollout.line_count,
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


def update_pull_state(response: PushResponseRecord) -> None:
    global BACKEND_PUSH_RESPONSE_RECORD
    global BACKEND_LIFECYCLE

    if response.validation_record is None:
        raise BackendStoreException(Locale.PUSH_VALIDATION_RECORD_MISSING)
    validation = response.validation_record.validation_request_body.post_commit_validation
    with BACKEND_WORKFLOW_STATE_LOCK:
        BACKEND_PUSH_RESPONSE_RECORD = response
        if validation.result is BackendLifecycle.ACCEPTED:
            BACKEND_LIFECYCLE = BackendLifecycle.COMPLETED
        elif validation.result is BackendLifecycle.REJECTED and validation.stage in {
            BackendLifecycle.PYDANTIC_VALIDATION,
            BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION,
        }:
            BACKEND_LIFECYCLE = BackendLifecycle.RETRY
        else:
            BACKEND_LIFECYCLE = BackendLifecycle.FAILED
    logger.info(
        Locale.PUSH_RESULT_STATE_LOG,
        response.record_id,
        None if response.commit_record is None else response.commit_record.record_id,
        response.validation_record.record_id,
        validation.stage,
        validation.result,
        BACKEND_LIFECYCLE,
    )


def _mark_backend_lifecycle_failed(error: Exception) -> None:
    global BACKEND_PUSH_RESPONSE_RECORD
    global BACKEND_LIFECYCLE
    logger.error(Locale.POST_ACCEPT_PROCESSING_FAILED_LOG, error)
    with BACKEND_WORKFLOW_STATE_LOCK:
        BACKEND_PUSH_RESPONSE_RECORD = None
        BACKEND_LIFECYCLE = BackendLifecycle.FAILED


def _capture_push_commit(
    store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    record: PushRequestRecord,
) -> BackendCommitRecord:
    session_id = record.session_id
    if record.pull_record_id is None or session_id is None or runtime.configured_namekey is None:
        raise _PushConfigurationError(Locale.PUSH_LINKAGE_MISSING)
    pull_record = store._http_record(record.pull_record_id)
    try:
        configuration = push_configuration_for_session(session_id)
        logger.info("Push %s: capturing rollout and appendwatch evidence for session %s",
                    record.record_id, session_id)
        try:
            rollout = runtime.pipeline_config.rollout_cas.copy_rollout(
                rollout_relative_path=configuration.rollout_relative_path,
                ssh_target=configuration.ssh_target,
                ssh_options=_aivm_connection_options(
                    lima_ssh_config=configuration.lima_ssh_config,
                    identity_file=configuration.identity_file,
                    known_hosts_file=configuration.known_hosts_file,
                    ssh_user=configuration.ssh_user,
                    host_key_alias=configuration.host_key_alias,
                ),
            )
        except (OSError, ValueError) as exc:
            raise _PushConfigurationError(str(exc)) from exc
        report_bytes = _read_appendwatch_bytes(configuration)
        logger.info("Push %s: captured rollout sha256=%s, bytes=%d, lines=%d; report bytes=%d",
                    record.record_id, rollout.sha256, rollout.size, rollout.line_count,
                    len(report_bytes))
    except (OSError, _PushConfigurationError):
        raise
    return _synthetic_commit_record(
        pull_record=pull_record,
        push_record=record,
        session_id=session_id,
        rollout=rollout,
        rollout_filename=configuration.rollout_relative_path.name,
        appendwatch_report=report_bytes,
        namekey=runtime.configured_namekey,
    )


def _authoritative_background_finished(task: asyncio.Task[None]) -> None:
    AUTHORITATIVE_BACKGROUND_TASKS.discard(task)
    if task.cancelled():
        return
    failure = task.exception()
    if failure is not None:
        logger.critical(Locale.COMMIT_APPEND_FATAL_LOG, failure)
        os._exit(1)


async def finish_push(
    promise: BackendComponent.ResponseRecordPromiseProperty[
        BackendComponent.PushResponseRecordProperty
    ],
) -> None:
    try:
        response, error = await promise.response_record()
        if error is not None:
            error.raise_exception()
        if response is None:
            raise BackendStoreException(Locale.PUSH_RESPONSE_RECORD_MISSING)
        update_pull_state(PushResponseRecord.model_validate(response, from_attributes=True))
    except Exception as exc:
        _mark_backend_lifecycle_failed(exc)
        raise


def register_processing(work: Coroutine[object, object, None]) -> None:
    task = asyncio.create_task(work)
    AUTHORITATIVE_BACKGROUND_TASKS.add(task)
    task.add_done_callback(_authoritative_background_finished)


def configured_pull_lines(singular_outerdict: AiAugmentSingularOuterDict) -> Iterator[str]:
    for innerdict in (*singular_outerdict.xlsx_innerdicts, *singular_outerdict.ssn_innerdicts):
        yield json_line(innerdict.data)
    yield json_line({
        KTP_FIRST_NAME_COL: singular_outerdict.namekey.first_name,
        KTP_LAST_NAME_COL: singular_outerdict.namekey.last_name,
        **dict.fromkeys(AI_AUGMENT_COLUMNS),
    })


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


def _create_codex_output_schema(store: AiAugmentBackendStore) -> None:
    definitions = ", ".join(
        f"{duckdb_quote_identifier(column)} {data_type}"
        for column, data_type in CODEX_OUTPUT_SCHEMA
    )
    store._execute(
        f"CREATE TABLE IF NOT EXISTS {CODEX_OUTPUT_ROWS_TABLE} ("
        f"{definitions}, UNIQUE ("
        f"{duckdb_quote_identifier(KTP_FILENAME_COL)}, "
        f"{duckdb_quote_identifier(KTP_FRAGMENT_COL)}))"
    )


def _replace_codex_output_view(store: AiAugmentBackendStore) -> None:
    projection = ", ".join(
        duckdb_quote_identifier(column) for column, _data_type in CODEX_OUTPUT_SCHEMA
    )
    store._execute(
        f"""
        CREATE OR REPLACE VIEW {CODEX_OUTPUT_VIEW} AS
        SELECT {projection}
        FROM {CODEX_OUTPUT_ROWS_TABLE}
        WHERE {duckdb_quote_identifier(KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL)} IS NOT NULL
          AND {duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL)} IS NOT NULL
        ORDER BY
            {duckdb_quote_identifier(KTP_FILENAME_COL)},
            {duckdb_quote_identifier(KTP_FRAGMENT_COL)},
            {duckdb_quote_identifier(KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL)}
        """
    )
    store._materialize_innerdicts(
        source_relation=CODEX_OUTPUT_VIEW,
        table_name=CODEX_INNERDICT_TABLE,
    )


def append_codex_output(
    store: AiAugmentBackendStore,
    row: Mapping[str, object],
) -> None:
    _create_codex_output_schema(store)
    columns = tuple(column for column, _data_type in CODEX_OUTPUT_SCHEMA)
    projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _column in columns)
    try:
        store._execute(
            f"INSERT INTO {CODEX_OUTPUT_ROWS_TABLE} ({projection}) VALUES ({placeholders})",
            [row[column] for column in columns],
        )
    except duckdb.ConstraintException as exc:
        raise _PushValidationError(Locale.ACCEPTED_IDENTITY_DUPLICATE) from exc


def selected_card_outer_dict(
    singular_outerdict: AiAugmentSingularOuterDict,
) -> OuterDict:
    selected = OuterDict(
        data={
            singular_outerdict.namekey.to_json_key(): [
                inner.model_copy(deep=True)
                for inner in (
                    *singular_outerdict.xlsx_innerdicts,
                    *(item.innerdict for item in singular_outerdict.committed_innerdicts),
                    *singular_outerdict.docx_innerdicts,
                    *singular_outerdict.ssn_innerdicts,
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
                else:
                    inner.data[column] = codex_parse.render_ai_standardized_value(value)
    return selected


def _standardized_initial_submission(
    submission: Submission,
) -> StandardizedSubmission:
    return StandardizedSubmission.model_validate({
        KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL: ResearcherAuthorSubmission(
            value=submission.researcher_author.value,
            web_search_excerpts=submission.researcher_author.web_search_excerpts,
            standardized_value=INITIAL_RESEARCHER_AUTHOR_STANDARDIZED,
        ),
        KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL: PlaceOfResidenceSubmission(
            value=submission.place_of_residence.value,
            web_search_excerpts=submission.place_of_residence.web_search_excerpts,
            standardized_value=INITIAL_PLACE_OF_RESIDENCE_STANDARDIZED,
        ),
        KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL: (
            RaceEthnicityLanguageCultureSubmission(
                value=submission.race_ethnicity_language_culture.value,
                web_search_excerpts=(
                    submission.race_ethnicity_language_culture.web_search_excerpts
                ),
                standardized_value=(
                    INITIAL_RACE_ETHNICITY_LANGUAGE_CULTURE_STANDARDIZED
                ),
            )
        ),
        KTP_AI_AUGMENT_GENDER_COL: GenderSubmission(
            value=submission.gender.value,
            web_search_excerpts=submission.gender.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL: AgeFirstPublicationSubmission(
            value=submission.age_first_publication.value,
            web_search_excerpts=submission.age_first_publication.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_EDUCATION_COL: EducationSubmission(
            value=submission.education.value,
            web_search_excerpts=submission.education.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL: AcademicPositionsSubmission(
            value=submission.academic_positions.value,
            web_search_excerpts=submission.academic_positions.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL: SocialCapitalSubmission(
            value=submission.social_capital.value,
            web_search_excerpts=submission.social_capital.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_LINKS_COL: ResearcherLinksSubmission(
            value=submission.links.value,
            web_search_excerpts=submission.links.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_COMMENTS_COL: submission.comments,
    })


def write_accepted_submission(
    store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    *,
    submission: StandardizedSubmission,
    evidence: ValidatedEvidence,
    singular_outerdict: AiAugmentSingularOuterDict,
    rollout_index: _RolloutIndex,
    rollout_archive: _ArchivedFile,
    commit_record: BackendCommitRecord,
    attempt_timestamp: datetime,
) -> InnerDict | None:
    commit_request_body = commit_record.request_body
    assert commit_request_body is not None
    commit_record_id = str(commit_record.record_id)
    rendered = render_codex_values(
        submission,
        evidence,
        attempt_timestamp=attempt_timestamp,
        argument_ref_urls=_rollout_ref_urls(store,

            rollout_filename=rollout_index.session.rollout_filename,
        ),
    )
    output_row: dict[str, object] = {
        KTP_NAMEKEY_COL: singular_outerdict.namekey.to_json_key(),
        KTP_FILENAME_COL: rollout_index.session.rollout_filename,
        KTP_FRAGMENT_COL: rollout_archive.line_count,
        KTP_FRAGMENT_TYPE_COL: ROLLOUT_LINE_FRAGMENT_TYPE,
        DRAW_LABEL: singular_outerdict.draw_number,
        KTP_FIRST_NAME_COL: singular_outerdict.namekey.first_name,
        KTP_LAST_NAME_COL: singular_outerdict.namekey.last_name,
        KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL: commit_record_id,
        KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL: None,
        KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL: None,
        KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL: commit_request_body,
        KTP_AI_AUGMENT_SESSION_METADATA_COL: rollout_index.session.summary_json,
        **rendered,
    }

    append_codex_output(store, output_row)
    return singular_outerdict.ground_truth_innerdict()


def _execute_attempt(
    store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
    *,
    commit_record: BackendCommitRecord,
    rollout_archive: _ArchivedFile,
    appendwatch_report: AppendwatchReportRecord,
    rollout_relative_path: PurePosixPath,
    original_pull: HttpRequestLogRecord,
    namekey: NameKey,
) -> tuple[AgentRuntimeAttemptRecord, bool]:
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
    retry_submission_expected = False
    stage = BackendLifecycle.APPENDWATCH_REPORT_VALIDATION
    submission_payload: Submission | StandardizedSubmission | None = None
    ground_truth_innerdict: InnerDict | None = None

    def result(
        *,
        validation_result: BackendLifecycle,
        detail: str | None,
        error: Exception | None,
        commit_database: bool,
    ) -> tuple[AgentRuntimeAttemptRecord, bool]:
        post_commit_validation = PostCommitValidation(
            stage=stage,
            result=validation_result,
            detail=detail,
        )
        _log_post_commit_validation(
            body.push_record,
            post_commit_validation,
            error,
        )
        return (
            AgentRuntimeAttemptRecord(
                attempt=AgentRuntimeAttempt(
                    pull_record=body.pull_record,
                    commit_record=commit_record,
                    post_commit_validation=post_commit_validation,
                ),
                submission=submission_payload,
                ground_truth_innerdict=ground_truth_innerdict,
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
            stage = BackendLifecycle.ROLLOUT_INDEX
            rollout_index = build_rollout_index(
                parse_rollout(rollout_archive.path),
                timezone_name=runtime.pipeline_config.timezone,
                configured_rollout_basename=rollout_relative_path.name,
            )
            if rollout_index.session.session_id != session_id:
                raise _PushValidationError(Locale.CONFIGURED_SESSION_MISMATCH)
            persist_rollout_index(store,
                rollout_index,
                codex_match_version=(
                    runtime.pipeline_config.match_rule_version.codex_match
                ),
            )

            stage = BackendLifecycle.PYDANTIC_VALIDATION
            retry_submission_expected = _retry_baseline_exists(store,

                original_pull=original_pull,
                namekey=namekey,
                session_id=session_id,
            )
            submission_payload = (
                StandardizedSubmission.model_validate_with_http_records(push_request_body)
                if retry_submission_expected
                else Submission.model_validate_with_http_records(push_request_body)
            )

            stage = BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION
            _seed_evidence_random(runtime.pipeline_config.sample_seed)
            evidence_assessment = assess_submission_evidence(
                store,
                submission_payload,
                rollout_filename=rollout_index.session.rollout_filename,
                codex_match_version=(
                    runtime.pipeline_config.match_rule_version.codex_match
                ),
            )
            _log_evidence_assessment(
                evidence_assessment,
                commit_record=commit_record,
            )
            retry_violations = _process_retry_attempt(
                store,
                original_pull=original_pull,
                commit_record=commit_record,
                namekey=namekey,
                attempt_timestamp=attempt_timestamp,
                submission_payload=submission_payload,
                assessment=evidence_assessment,
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
                submission_payload
                if isinstance(submission_payload, StandardizedSubmission)
                else _standardized_initial_submission(submission_payload)
            )

            stage = BackendLifecycle.RESEARCHER_RESOLUTION
            singular_outerdict = _configured_ai_augment_singular_outerdict(
                namekey,
                runtime.ai_augment_singular_outerdicts,
            )

            stage = BackendLifecycle.INNERDICT_AND_CARD
            submission_payload = accepted_submission
            ground_truth_innerdict = write_accepted_submission(
                store,
                runtime,
                submission=accepted_submission,
                evidence=evidence_assessment.validated,
                singular_outerdict=singular_outerdict,
                rollout_index=rollout_index,
                rollout_archive=rollout_archive,
                commit_record=commit_record,
                attempt_timestamp=attempt_timestamp,
                )
            stage = BackendLifecycle.ACCEPTED
            return result(
                validation_result=BackendLifecycle.ACCEPTED,
                detail=None,
                error=None,
                commit_database=True,
            )
        except _PushConfigurationError as exc:
            return result(
                validation_result=BackendLifecycle.CONFIGURATION_ERROR,
                detail=Locale.CONFIGURATION_ERROR_DETAIL,
                error=exc,
                commit_database=False,
            )
        except _MultipleEvidenceMatches as exc:
            return result(
                validation_result=BackendLifecycle.REJECTED,
                detail=Locale.MULTIPLE_MATCH_DETAIL_TEMPLATE.format(excerpt=exc.excerpt),
                error=exc,
                commit_database=(stage is BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION),
            )
        except _PushValidationError as exc:
            return result(
                validation_result=BackendLifecycle.REJECTED,
                detail=(
                    exc.public_detail
                    if isinstance(exc, _EvidenceAssessmentError)
                    else Locale.VALIDATION_ERROR_DETAIL
                ),
                error=exc,
                commit_database=(
                    stage
                    in {
                        BackendLifecycle.PYDANTIC_VALIDATION,
                        BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION,
                    }
                ),
            )
        except ValidationError as exc:
            return result(
                validation_result=BackendLifecycle.REJECTED,
                detail=Locale.VALIDATION_ERROR_DETAIL
                + (f"\n{RETRY_SUBMISSION_PUBLIC_GUIDANCE}" if retry_submission_expected else ""),
                error=exc,
                commit_database=True,
            )
        except (OSError, ValueError, duckdb.Error, subprocess.SubprocessError) as exc:
            return result(
                validation_result=BackendLifecycle.REJECTED,
                detail=Locale.VALIDATION_ERROR_DETAIL,
                error=exc,
                commit_database=False,
            )


def validate_transport(request: requests.PreparedRequest) -> None:
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


def bounded_request_body(request: requests.PreparedRequest) -> bytes:
    body = _prepared_request_body(request)
    if len(body) > MAX_PUSH_BODY_BYTES:
        raise _PushValidationError(Locale.REQUEST_BODY_TOO_LARGE)
    return body


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


def _committed_innerdicts(
    store: AiAugmentBackendStore,
) -> tuple[CommittedInnerDict, ...]:
    exists = store._execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
        [CODEX_INNERDICT_TABLE],
    ).fetchone()
    if exists is None or int(exists[0]) == 0:
        return ()
    rows = store._execute(
        f"SELECT {duckdb_quote_identifier(KTP_NAMEKEY_COL)}, "
        f"{duckdb_quote_identifier(KTP_INNERDICT_JSONLINES_COL)} "
        f"FROM {CODEX_INNERDICT_TABLE} "
        f"ORDER BY {duckdb_quote_identifier(KTP_NAMEKEY_COL)}"
    ).fetchall()
    committed_innerdicts: list[CommittedInnerDict] = []
    for namekey_json, payload in rows:
        try:
            for values in loads_jsonlines(payload):
                commit_record_id = UUID(str(values[KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL]))
                _ordinal, http_record = store._http_record_with_ordinal(commit_record_id)
                committed_innerdicts.append(
                    CommittedInnerDict(
                        innerdict=InnerDict.from_mapping(
                            {KTP_NAMEKEY_COL: namekey_json, **values}, _CodexMatchProcedure(),
                        ),
                        commit_record=_backend_commit_record(store, http_record),
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
    push_record: HttpRequestLogRecord,
    post_commit_validation: PostCommitValidation,
    error: Exception | None,
) -> None:
    if error is None:
        logger.info(Locale.PUSH_ACCEPTED_LOG, push_record.record_id)
    elif isinstance(error, ValidationError):
        field, reason, failed_input = pydantic_failure(error)
        logger.warning(
            Locale.PUSH_PYDANTIC_FAILED_LOG,
            push_record.record_id,
            post_commit_validation.stage,
            field or Locale.UNKNOWN_FIELD,
            failed_input,
            reason,
        )
    elif isinstance(error, _PushConfigurationError):
        logger.error(
            Locale.PUSH_CONFIGURATION_FAILED_LOG,
            push_record.record_id,
            post_commit_validation.stage,
            error,
        )
    elif isinstance(error, _PushValidationError):
        logger.warning(
            Locale.PUSH_VALIDATION_FAILED_LOG,
            push_record.record_id,
            post_commit_validation.stage,
            error,
        )
    else:
        logger.warning(
            Locale.PUSH_UNEXPECTED_FAILED_LOG,
            push_record.record_id,
            post_commit_validation.stage,
            error,
        )


def _response(
    request: requests.PreparedRequest,
    code: HTTPStatus,
    body: str = "",
    *,
    content_type: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> requests.Response:
    response = requests.Response()
    response.status_code = code
    response.request = request
    response.url = request.url or ""
    response.encoding = TEXT_ENCODING
    response._content = body.encode(TEXT_ENCODING)
    _ = response.content
    if headers is not None:
        response.headers.update(headers)
    if content_type is not None:
        response.headers["Content-Type"] = content_type
    response.headers["Content-Length"] = str(len(response.content))
    return response


def _error_response(
    request: requests.PreparedRequest,
    code: HTTPStatus,
    *,
    headers: Mapping[str, str] | None = None,
) -> requests.Response:
    return _response(
        request,
        code,
        json.dumps(
            {"detail": Locale.CONFIGURATION_ERROR_DETAIL},
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
        ),
        content_type=JSON_MEDIA_TYPE,
        headers=headers,
    )


def _pull_response(
    request: requests.PreparedRequest,
    runtime: AiAugmentBackendContext,
) -> requests.Response:
    with BACKEND_WORKFLOW_STATE_LOCK:
        lifecycle = BACKEND_LIFECYCLE
        push_response = BACKEND_PUSH_RESPONSE_RECORD
    logger.info(
        Locale.PULL_STATE_LOG,
        lifecycle,
        None
        if push_response is None or push_response.commit_record is None
        else push_response.commit_record.record_id,
    )
    if lifecycle is BackendLifecycle.BUSY:
        logger.info(Locale.PULL_PROCESSING_LOG)
        return _error_response(
            request, HTTPStatus.SERVICE_UNAVAILABLE,
            headers={RETRY_AFTER_HEADER: RETRY_AFTER_SECONDS},
        )
    if lifecycle is BackendLifecycle.FAILED:
        logger.error(Locale.PULL_WORKFLOW_FAILED_LOG)
        return _error_response(request, HTTPStatus.INTERNAL_SERVER_ERROR)
    if lifecycle in {BackendLifecycle.RETRY, BackendLifecycle.COMPLETED}:
        if push_response is None or push_response.validation_record is None:
            raise BackendStoreException(Locale.PULL_VALIDATION_RECORD_MISSING)
        body = push_response.validation_record.validation_request_body
        validation = body.post_commit_validation
        if lifecycle is BackendLifecycle.RETRY:
            if validation.result is not BackendLifecycle.REJECTED or validation.stage not in {
                BackendLifecycle.PYDANTIC_VALIDATION,
                BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION,
            }:
                raise BackendStoreException(Locale.PULL_RETRY_VALIDATION_INCONSISTENT)
            logger.info(Locale.PULL_RETRY_STAGE_LOG, validation.stage)
            return _response(
                request,
                HTTPStatus.OK,
                (validation.detail or Locale.VALIDATION_ERROR_DETAIL).rstrip() + "\n",
                content_type=MARKDOWN_MEDIA_TYPE + "; charset=utf-8",
            )
        if (
            validation.result is not BackendLifecycle.ACCEPTED
            or body.submission_type != "StandardizedSubmission"
            or body.submission is None
        ):
            raise BackendStoreException(Locale.PULL_COMPLETED_RESULT_INVALID)
        # Render the Store-validated serialized values; never revalidate providers in API.
        values: dict[str, str] = {}
        for column in (*AI_AUGMENT_EVIDENCE_COLUMNS, KTP_AI_AUGMENT_COMMENTS_COL):
            field = body.submission[column]
            if column == KTP_AI_AUGMENT_COMMENTS_COL and field is None:
                continue
            if not isinstance(field, dict) or not isinstance(field.get("value"), str):
                raise BackendStoreException(Locale.PULL_SUBMISSION_VALUE_INVALID)
            value = field["value"]
            assert isinstance(value, str)
            values[column] = value
        singular = runtime.configured_ai_augment_singular_outerdict()
        if singular is None:
            raise BackendStoreException(Locale.PULL_COMPLETED_RESEARCHER_MISSING)
        ground_truth = singular.ground_truth_innerdict()
        lines = [json_line(values)]
        if ground_truth is not None:
            lines.append(json_line(select_columns(ground_truth.data)))
        logger.info(Locale.PULL_COMPLETED_GROUND_TRUTH_LOG, ground_truth is not None)
        return _response(
            request, HTTPStatus.GONE, "".join(lines), content_type=MEDIA_TYPE_WITH_CHARSET,
        )
    try:
        singular = runtime.configured_ai_augment_singular_outerdict()
        if singular is None:
            raise _PushConfigurationError(Locale.PUSH_LINKAGE_MISSING)
        initial_lines = tuple(configured_pull_lines(singular))
        logger.info(
            Locale.PULL_INITIAL_TASK_LOG, singular.namekey, len(initial_lines)
        )
        return _response(
            request, HTTPStatus.OK, "".join(initial_lines), content_type=MEDIA_TYPE_WITH_CHARSET,
        )
    except (_PushConfigurationError, _PushValidationError, OSError, duckdb.Error) as exc:
        logger.error(Locale.PULL_FAILED_LOG, exc)
        return _error_response(request, HTTPStatus.INTERNAL_SERVER_ERROR)


async def authoritative_pull(
    request: requests.PreparedRequest,
    runtime: AiAugmentBackendContext,
    store: BackendComponent.FullStoreProperty,
) -> requests.Response:
    global BACKEND_CURRENT_PULL_RECORD
    started_ns = time.monotonic_ns()
    response = _pull_response(request, runtime)
    record = PullRequestRecord.model_validate(
        _authoritative_http_record(request, response, started_ns=started_ns).model_dump(),
    )
    promise = await asyncio.to_thread(store.pull, record)
    response_record, error = await promise.response_record()
    if error is not None:
        error.raise_exception()
    if promise.acknowledgment is not BackendStoreAcknowledgment.ACK or response_record is None:
        raise BackendStoreException(Locale.PULL_DURABLE_RESPONSE_MISSING)
    if response_record.response_code == HTTPStatus.OK:
        with BACKEND_WORKFLOW_STATE_LOCK:
            BACKEND_CURRENT_PULL_RECORD = HttpRequestLogRecord.model_validate(
                response_record,
                from_attributes=True,
            )
    logger.info(
        Locale.PULL_PERSISTED_LOG,
        response_record.record_id,
        response_record.response_code,
    )
    return response_record.to_response()


def _push_response(request: requests.PreparedRequest) -> requests.Response:
    global BACKEND_PUSH_RESPONSE_RECORD, BACKEND_CURRENT_PULL_RECORD
    global BACKEND_PENDING_PULL_RECORD, BACKEND_LIFECYCLE
    with BACKEND_WORKFLOW_STATE_LOCK:
        lifecycle = BACKEND_LIFECYCLE
        logger.info(
            Locale.PUSH_REQUEST_STATE_LOG,
            lifecycle,
            BACKEND_SESSION_ID,
            None if BACKEND_CURRENT_PULL_RECORD is None else BACKEND_CURRENT_PULL_RECORD.record_id,
        )
        if lifecycle is BackendLifecycle.BUSY:
            return _error_response(
                request, HTTPStatus.CONFLICT, headers={LOCATION_HEADER: PULL_PATH},
            )
        if (
            lifecycle not in {BackendLifecycle.READY, BackendLifecycle.RETRY}
            or BACKEND_SESSION_ID is None
        ):
            logger.error(Locale.PUSH_SESSION_NOT_READY_LOG)
            return _error_response(request, HTTPStatus.INTERNAL_SERVER_ERROR)
        if BACKEND_CURRENT_PULL_RECORD is None:
            logger.warning(Locale.PUSH_CURRENT_PULL_REQUIRED_LOG)
            return _error_response(
                request, HTTPStatus.CONFLICT, headers={LOCATION_HEADER: PULL_PATH},
            )
        BACKEND_PENDING_PULL_RECORD = BACKEND_CURRENT_PULL_RECORD
        BACKEND_CURRENT_PULL_RECORD = None
        BACKEND_PUSH_RESPONSE_RECORD = None
        BACKEND_LIFECYCLE = BackendLifecycle.BUSY
    return _response(request, HTTPStatus.ACCEPTED, headers={LOCATION_HEADER: PULL_PATH})


async def authoritative_push(
    request: requests.PreparedRequest,
    store: BackendComponent.FullStoreProperty,
) -> requests.Response:
    global BACKEND_LATEST_PUSH_RECORD
    started_ns = time.monotonic_ns()
    response = _push_response(request)
    with BACKEND_WORKFLOW_STATE_LOCK:
        pull = BACKEND_PENDING_PULL_RECORD
        session = BACKEND_SESSION_ID
    record = PushRequestRecord(
        **_authoritative_http_record(request, response, started_ns=started_ns).model_dump(),
        pull_record_id=None if pull is None else pull.record_id,
        session_id=session,
    )
    promise = await asyncio.to_thread(store.push, record)
    if promise.acknowledgment is not BackendStoreAcknowledgment.ACK:
        _record, error = await promise.response_record()
        if error is not None:
            error.raise_exception()
        raise BackendStoreException(Locale.PUSH_NAK_ERROR_MISSING)
    if response.status_code == HTTPStatus.ACCEPTED:
        with BACKEND_WORKFLOW_STATE_LOCK:
            BACKEND_LATEST_PUSH_RECORD = record
        register_processing(finish_push(promise))
        logger.info(Locale.PUSH_DURABLY_ACCEPTED_LOG, record.record_id)
        return response
    response_record, error = await promise.response_record()
    if error is not None:
        error.raise_exception()
    if response_record is None:
        raise BackendStoreException(Locale.PUSH_RESPONSE_RECORD_MISSING)
    logger.info(Locale.PUSH_PERSISTED_LOG, response_record.record_id, response_record.response_code)
    return response_record.to_response()
