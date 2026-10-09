import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final

from src.helpers.data_models import FragmentType
from src.helpers.vars import (
    BATCH_LABEL,
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
    KTP_NAMEKEY_COL,
)

NOT_REPORTED_VALUE: Final = "NR"
ISO_8601_UTC_SUFFIX: Final = "Z"
ISO_8601_UTC_OFFSET: Final = "+00:00"
MILLISECONDS_PER_SECOND: Final = 1_000
CUMULATIVE_KEY_SEPARATOR: Final = "\0"
NOT_AVAILABLE_OR_APPLICABLE_VALUE: Final = "NA"
ASGI_TYPE_KEY: Final = "type"
ASGI_METHOD_KEY: Final = "method"
ASGI_PATH_KEY: Final = "path"
ASGI_BODY_KEY: Final = "body"
ASGI_MORE_BODY_KEY: Final = "more_body"
ASGI_STATUS_KEY: Final = "status"
ASGI_HEADERS_KEY: Final = "headers"
ASGI_HTTP_SCOPE_TYPE: Final = "http"
ASGI_HTTP_REQUEST_MESSAGE_TYPE: Final = "http.request"
ASGI_HTTP_DISCONNECT_MESSAGE_TYPE: Final = "http.disconnect"
ASGI_HTTP_RESPONSE_START_MESSAGE_TYPE: Final = "http.response.start"
ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE: Final = "http.response.body"
PYDANTIC_TO_PASTE_SOURCE = Path(
    "src/detours/detour_ai_augment/protected/src/backend/helpers/data_models/"
    "pydantic_to_paste.py"
).read_text(encoding="utf-8").rstrip()

SESSION_ID_HEADER: Final = "Session-ID"
ETAG_HEADER: Final = "ETag"
SOURCE_KEY_HEADER: Final = "SourceKey"

HTTP_CONTENT_TYPE_HEADER: Final = "Content-Type"
HTTP_CONTENT_LENGTH_HEADER: Final = "Content-Length"
HTTP_GET_METHOD: Final = "GET"
HTTP_POST_METHOD: Final = "POST"
PULL_PATH: Final = "/pull"
PUSH_PATH: Final = "/push"
INIT_PATH: Final = "/init"
QUERY_PATH: Final = "/query"
SYNTHETIC_COMMIT_SCHEME: Final = "http"
SYNTHETIC_COMMIT_HOST: Final = "invalid"
CODEX_OUTPUT_ROWS_TABLE: Final = "codex_output_rows"
CODEX_FC_TABLE: Final = "codex_fc"
CODEX_FCO_TABLE: Final = "codex_fco"
CODEX_CALLS_TABLE: Final = "codex_calls"
CODEX_TURN_REF_TABLE: Final = "codex_turn_ref"
CODEX_TURN_REF_NORMALIZED_VIEW: Final = "codex_turn_ref_normalized"
POST_COMMIT_VALIDATION_RETRY_BASELINES_TABLE: Final = (
    "post_commit_validation_retry_baselines"
)
POST_COMMIT_VALIDATION_EVIDENCE_AUDITS_TABLE: Final = (
    "post_commit_validation_evidence_audits"
)
CODEX_ID_COL: Final = "id"
CODEX_FC_TIMESTAMP_COL: Final = "codex.fc_timestamp"
CODEX_FC_ID_COL: Final = "codex.fc_id"
CODEX_FC_NAME_COL: Final = "codex.fc_name"
CODEX_FC_NAMESPACE_COL: Final = "codex.fc_namespace"
CODEX_FC_ARGUMENTS_COL: Final = "codex.fc_arguments"
CODEX_FCO_TIMESTAMP_COL: Final = "codex.fco_timestamp"
CODEX_FCO_ID_COL: Final = "codex.fco_id"
CODEX_CALL_ID_COL: Final = "codex.call_id"
CODEX_ROLLOUT_FILENAME_COL: Final = "codex.rollout_filename"
CODEX_REF_ID_COL: Final = "codex.ref_id"
CODEX_REF_DOMAIN_COL: Final = "codex.ref_domain"
CODEX_REF_SNIPPET_COL: Final = "codex.ref_snippet"
CODEX_REF_THUMBNAIL_URL_COL: Final = "codex.ref_thumbnail_url"
CODEX_REF_TITLE_COL: Final = "codex.ref_title"
CODEX_REF_URL_COL: Final = "codex.ref_url"
CODEX_CITE_TEXT_COL: Final = "codex.cite_text"
CODEX_CITE_TOKENS_COL: Final = "codex.cite_tokens"
POST_COMMIT_VALIDATION_ORIGINAL_PULL_RECORD_ID_COL: Final = "original_pull_record_id"
POST_COMMIT_VALIDATION_NAMEKEY_COL: Final = "namekey"
POST_COMMIT_VALIDATION_SESSION_ID_COL: Final = "session_id"
POST_COMMIT_VALIDATION_COMMIT_RECORD_ID_COL: Final = "commit_record_id"
POST_COMMIT_VALIDATION_CREATED_AT_COL: Final = "created_at"
POST_COMMIT_VALIDATION_BASELINE_COL: Final = "baseline"
POST_COMMIT_VALIDATION_SUBMISSION_COL: Final = "submission"
POST_COMMIT_VALIDATION_ASSESSMENT_COL: Final = "assessment"
POST_COMMIT_VALIDATION_APPLIED_COL: Final = "applied"
POST_COMMIT_VALIDATION_ACCEPTED_COL: Final = "accepted"
POST_COMMIT_VALIDATION_AUDIT_ID_COL: Final = "id"
CODEX_INNERDICT_TABLE: Final = "codex_innerdicts"
RUN_OUTCOME_RECORDS_TABLE: Final = "run_outcome_records"
RUN_OUTCOME_RECORD_ID_COL: Final = "run_outcome_record_id"
RUN_OUTCOME_SERIALIZED_JSON_COL: Final = "serialized_json"
CODEX_SESSION_ID_JSON_KEY: Final = "session_id"
CODEX_TYPE_KEY: Final = "type"
CODEX_PAYLOAD_KEY: Final = "payload"
CODEX_CITE_MARKER_PREFIX: Final = "\ue200cite\ue202"
CODEX_CITE_MARKER_SUFFIX: Final = "\ue201"
AUTHORITATIVE_FIRST_LINE: Final = 1
AUTHORITATIVE_EMPTY_OFFSET: Final = 0
API_VERSION: Final = "1.0.0"
AUTHORITATIVE_LOG_BASE64_ENCODING: Final = "base64"
AUTHORITATIVE_LOG_ENCODING_KEY: Final = "encoding"
AUTHORITATIVE_LOG_DATA_KEY: Final = "data"
BASE64_TEXT_ENCODING: Final = "ascii"
COMPACT_JSON_SEPARATORS: Final = (",", ":")
LOCATION_HEADER: Final = "Location"
RETRY_AFTER_HEADER: Final = "Retry-After"
RETRY_AFTER_SECONDS: Final = "1"
AUTHORITATIVE_RECORDS_TABLE: Final = "replayed_http_request_log_records"
AUTHORITATIVE_RECORD_ORDINAL_COLUMN: Final = "record_ordinal"
AUTHORITATIVE_RECORD_ID_COLUMN: Final = "record_id"
AUTHORITATIVE_RECORD_METHOD_COLUMN: Final = "method"
AUTHORITATIVE_RECORD_PATH_COLUMN: Final = "path"
AUTHORITATIVE_RECORD_PAYLOAD_COLUMN: Final = "record"
COMMIT_VALIDATION_REQUEST_RECORD_INDEX_TABLE: Final = "commit_validation_request_record_index"
COMMIT_REQUEST_RECORD_ID_COLUMN: Final = "commit_request_record_id"
VALIDATION_REQUEST_RECORD_ID_COLUMN: Final = "validation_request_record_id"
CREATE_AUTHORITATIVE_RECORDS_TABLE_SQL: Final = (
    f"CREATE TABLE IF NOT EXISTS {AUTHORITATIVE_RECORDS_TABLE} ("
    f"{AUTHORITATIVE_RECORD_ORDINAL_COLUMN} BIGINT PRIMARY KEY, "
    f"{AUTHORITATIVE_RECORD_ID_COLUMN} VARCHAR NOT NULL UNIQUE, "
    f"{AUTHORITATIVE_RECORD_METHOD_COLUMN} VARCHAR NOT NULL, "
    f"{AUTHORITATIVE_RECORD_PATH_COLUMN} VARCHAR NOT NULL, "
    f"{AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} JSON NOT NULL, "
    "raw_line_sha256 VARCHAR NOT NULL)"
)
CREATE_COMMIT_VALIDATION_REQUEST_RECORD_INDEX_TABLE_SQL: Final = (
    f"CREATE TABLE IF NOT EXISTS {COMMIT_VALIDATION_REQUEST_RECORD_INDEX_TABLE} ("
    f"{COMMIT_REQUEST_RECORD_ID_COLUMN} VARCHAR PRIMARY KEY, "
    f"{VALIDATION_REQUEST_RECORD_ID_COLUMN} VARCHAR NOT NULL)"
)
SUBMISSION_TYPE: Final = "Submission"
STANDARDIZED_SUBMISSION_TYPE: Final = "StandardizedSubmission"
NANOSECONDS_PER_MICROSECOND: Final = 1_000


class ContentType(StrEnum):
    JSON = "application/json"
    NDJSON = "application/x-ndjson"
    MARKDOWN = "text/markdown"
    PLAIN_TEXT = "text/plain"
    NDJSON_UTF8 = "application/x-ndjson; charset=utf-8"
    MARKDOWN_UTF8 = "text/markdown; charset=utf-8"


AI_AUGMENT_COLUMN_PREFIX = "ktp.ai_augment_"

KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL = f"{AI_AUGMENT_COLUMN_PREFIX}researcher_author"
KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL = f"{AI_AUGMENT_COLUMN_PREFIX}place_of_residence"
KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}race_ethnicity_language_culture"
)
KTP_AI_AUGMENT_GENDER_COL = f"{AI_AUGMENT_COLUMN_PREFIX}gender"
KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}age_first_publication_according_to_openalex_profile"
)
KTP_AI_AUGMENT_EDUCATION_COL = f"{AI_AUGMENT_COLUMN_PREFIX}education"
KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}academic_position_s_"
KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL = f"{AI_AUGMENT_COLUMN_PREFIX}social_capital"
KTP_AI_AUGMENT_LINKS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}links_"
KTP_AI_AUGMENT_COMMENTS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}comments"
AI_AUGMENT_EVIDENCE_COLUMNS = (
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
    KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
    KTP_AI_AUGMENT_GENDER_COL,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    KTP_AI_AUGMENT_EDUCATION_COL,
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
    KTP_AI_AUGMENT_LINKS_COL,
)
AI_AUGMENT_COLUMNS = AI_AUGMENT_EVIDENCE_COLUMNS + (KTP_AI_AUGMENT_COMMENTS_COL,)
EVIDENCE_OUTCOME_V1_EXACT = "v1_exact"
EVIDENCE_OUTCOME_V2_NEAR = "v2_near"
EVIDENCE_OUTCOME_UNMATCHED = "unmatched"
EVIDENCE_OUTCOME_WITHDRAWN = "withdrawn"
EVIDENCE_ITEMS_ACCEPTED_DEF: Callable[[Sequence[str]], bool] = lambda outcomes: (
    EVIDENCE_OUTCOME_V1_EXACT in outcomes
    and all(
        outcome in {EVIDENCE_OUTCOME_V1_EXACT, EVIDENCE_OUTCOME_WITHDRAWN}
        for outcome in outcomes
    )
)
EVIDENCE_PROGRESS_PRAISE_DEF: Callable[[Sequence[str]], bool] = lambda outcomes: (
    EVIDENCE_OUTCOME_V2_NEAR in outcomes
    and outcomes.count(EVIDENCE_OUTCOME_V1_EXACT) > len(outcomes) // 2
)
AI_AUGMENT_STANDARDIZED_SUFFIX = "_standardized"
AI_AUGMENT_STANDARDIZED_COLUMNS = tuple(
    f"{column}{AI_AUGMENT_STANDARDIZED_SUFFIX}"
    for column in AI_AUGMENT_EVIDENCE_COLUMNS
)
AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS = tuple(
    zip(
        AI_AUGMENT_EVIDENCE_COLUMNS,
        AI_AUGMENT_STANDARDIZED_COLUMNS,
        strict=True,
    )
)

KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}run_outcome_response_body"
)
KTP_AI_AUGMENT_SESSION_METADATA_COL = f"{AI_AUGMENT_COLUMN_PREFIX}session_metadata"
KTP_AI_AUGMENT_FOOTNOTES_COL = f"{AI_AUGMENT_COLUMN_PREFIX}footnotes"
KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}footnote_arguments"

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
DOCX_COLUMNS = tuple(
    docx_column for docx_column, _ai_column in DOCX_TO_AI_AUGMENT_COLUMNS
)

TEXT_ENCODING = "utf-8"
CONTROL_CHARACTER_CEILING = 32
DELETE_CHARACTER_CODEPOINT = 127
HAS_CONTROL_CHARACTER: Callable[[str], bool] = lambda value: any(
    ord(character) < CONTROL_CHARACTER_CEILING
    or ord(character) == DELETE_CHARACTER_CODEPOINT
    for character in value
)
VALID_NONBLANK: Callable[[object], bool] = lambda value: (
    isinstance(value, str)
    and bool(value.strip())
    and value == value.strip()
    and not HAS_CONTROL_CHARACTER(value)
)

AI_AUGMENT_RND_START = 1
MAP_COLUMNS = (DRAW_LABEL, BATCH_LABEL)
EXPECTED_GROUND_TRUTH_RESEARCHERS = 196
EXPECTED_NO_GROUND_TRUTH_RESEARCHERS = 78
EXPECTED_ELIGIBLE_RESEARCHERS = 274
EXPECTED_INELIGIBLE_RESEARCHERS = 33
EXPECTED_SOURCE_RESEARCHERS = (
    EXPECTED_ELIGIBLE_RESEARCHERS + EXPECTED_INELIGIBLE_RESEARCHERS
)
EXPECTED_MULTIDRAW_SOURCE_RESEARCHERS = 5
DRAW_PILOT_PREFIX = "pilot."
DRAW_SORT_PART = re.compile(r"\d+|\D+")

CONFIG_FILENAME = "config_ai_augment.json"
MAP_SUBSET_0_TO_BATCH_KEY = "map_subset_0_to_batch"
REPLAY_LOG_KEY = "detour_ai_augment_backend_api_replay_log"

# ground truth is defined explicitly by released batch, exclusive of dupe
GROUND_TRUTH_RELEASE_BATCHES = frozenset({"subset 1", "subset 5", "subset 6", "subset 7"})
EXCLUDED_NAMEKEY = json.dumps(
    {KTP_FIRST_NAME_COL: "Mercouri G.", KTP_LAST_NAME_COL: "Kanatzidis"},
    sort_keys=True,
)
GROUND_TRUTH_DEF: Callable[
    [str, Mapping[str, str], tuple[str, ...]],
    bool,
] = lambda namekey, release_batches, draws: (
    namekey != EXCLUDED_NAMEKEY
    and any(release_batches.get(draw) in GROUND_TRUTH_RELEASE_BATCHES for draw in draws)
)
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

INELIGIBLE_RELEASE_BATCH = "subset 8"


class AiAugmentCohort(StrEnum):
    GROUND_TRUTH = "ground_truth"
    NO_GROUND_TRUTH = "no_ground_truth"
    INELIGIBLE = "ineligible"


class AiAugmentIneligibilityCategory(StrEnum):
    EXCLUDED_DUPLICATE_NAMEKEY = "excluded_duplicate_namekey"
    RELEASE_BATCH_SUBSET_8 = "release_batch_subset_8"
    STAGING_PARTITION_2 = "staging_partition_2"
    STAGING_PARTITION_4_XLSX_NON_EXACT = "staging_partition_4_xlsx_non_exact"
    STAGING_PARTITION_4_MULTIPLE_SSN = "staging_partition_4_multiple_ssn"


EXPECTED_INELIGIBILITY_COUNTS = {
    AiAugmentIneligibilityCategory.EXCLUDED_DUPLICATE_NAMEKEY: 1,
    AiAugmentIneligibilityCategory.RELEASE_BATCH_SUBSET_8: 3,
    AiAugmentIneligibilityCategory.STAGING_PARTITION_2: 7,
    AiAugmentIneligibilityCategory.STAGING_PARTITION_4_XLSX_NON_EXACT: 6,
    AiAugmentIneligibilityCategory.STAGING_PARTITION_4_MULTIPLE_SSN: 16,
}


BACKEND_STORE_CLOSED_CLEANLY = "AI_AUGMENT_BACKEND_STORE_CLOSED_CLEANLY"

CODEX_OUTPUT_VIEW = "codex_output"

CODEX_OUTPUT_SCHEMA = (
    (KTP_NAMEKEY_COL, "VARCHAR NOT NULL"),
    (KTP_FILENAME_COL, "VARCHAR"),
    (KTP_FRAGMENT_COL, "BIGINT"),
    (KTP_FRAGMENT_TYPE_COL, "VARCHAR"),
    (DRAW_LABEL, "VARCHAR NOT NULL"),
    (KTP_FIRST_NAME_COL, "VARCHAR NOT NULL"),
    (KTP_LAST_NAME_COL, "VARCHAR NOT NULL"),
    (KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL, "VARCHAR"),
    (KTP_AI_AUGMENT_SESSION_METADATA_COL, "VARCHAR NOT NULL"),
    *(
        definition
        for plain_column, standardized_column in AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS
        for definition in (
            (plain_column, "VARCHAR NOT NULL"),
            (standardized_column, "VARCHAR"),
        )
    ),
    (KTP_AI_AUGMENT_COMMENTS_COL, "VARCHAR"),
    (KTP_AI_AUGMENT_FOOTNOTES_COL, "VARCHAR NOT NULL"),
    (KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL, "VARCHAR NOT NULL"),
)

APPENDWATCH_REPORT_ENV_NAME = "FASTAPI_DETOUR_APPENDWATCH_REPORT"
NAMEKEY_ENV_NAME = "FASTAPI_DETOUR_NAMEKEY"
CODEX_SESSIONS_ROOT_ENV_NAME = "FASTAPI_DETOUR_CODEX_SESSIONS_DIR"
CODEX_SESSIONS_ROOT = PurePosixPath(
    os.environ.get(CODEX_SESSIONS_ROOT_ENV_NAME, "/home/ai/.codex/sessions")
)
FORBIDDEN_NORMALIZED_PATH_PARTS = frozenset({"", ".", ".."})

ROLLOUT_FILENAME_PREFIX = "rollout-"
ROLLOUT_FILENAME_SUFFIX = ".jsonl"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8612
CARD_EXCLUDED_COLUMNS = {
    KTP_FILENAME_COL,
    KTP_NAMEKEY_COL,
    CSV_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
}

NAME_KEY_HEADER = "NameKey"
STRUCTURED_FIELD_STRING = r'"(?:[\x20-\x21\x23-\x5b\x5d-\x7e]|\\["\\])*"'
NAME_KEY_PATTERN = re.compile(
    rf"^{re.escape(KTP_FIRST_NAME_COL)}=(?P<first>{STRUCTURED_FIELD_STRING}), "
    rf"{re.escape(KTP_LAST_NAME_COL)}=(?P<last>{STRUCTURED_FIELD_STRING})$"
)
ROLLOUT_LINE_FRAGMENT_TYPE = FragmentType.LINE_NUMBER.value
SOURCE_KEY_PATTERN = re.compile(
    rf"^{re.escape(KTP_FILENAME_COL)}=(?P<filename>{STRUCTURED_FIELD_STRING}), "
    rf'{re.escape(KTP_FRAGMENT_COL)};type="{ROLLOUT_LINE_FRAGMENT_TYPE}";'
    rf"{ROLLOUT_LINE_FRAGMENT_TYPE}=(?P<fragment>{STRUCTURED_FIELD_STRING})$"
)
ROLLOUT_ENV_NAME = "FASTAPI_DETOUR_ROLLOUT_JSONL"
ROLLOUT_JSONL = os.environ.get(ROLLOUT_ENV_NAME, "")
AIVM_INSTANCE_ENV_NAME = "FASTAPI_DETOUR_AIVM_INSTANCE"
AIVM_AUDIT_USER_ENV_NAME = "FASTAPI_DETOUR_AIVM_AUDIT_USER"
AIVM_SSH_PORT_ENV_NAME = "FASTAPI_DETOUR_AIVM_SSH_PORT"
AIVM_IDENTITY_FILE_ENV_NAME = "FASTAPI_DETOUR_AIVM_IDENTITY_FILE"
AIVM_KNOWN_HOSTS_FILE_ENV_NAME = "FASTAPI_DETOUR_AIVM_KNOWN_HOSTS_FILE"
LIMA_SSH_CONFIG_ENV_NAME = "FASTAPI_DETOUR_LIMA_SSH_CONFIG"
APPENDWATCH_REPORT = os.environ.get(APPENDWATCH_REPORT_ENV_NAME, "")
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
ARCHIVE_HASH_CHUNK_BYTES = 1024 * 1024
SSH_TIMEOUT_SECONDS = 60
MIN_TCP_PORT = 1
MAX_TCP_PORT = 65_535
SSH_EXECUTABLE = "ssh"
AUDIT_PROBE_COMMAND = "probe"
AUDIT_FIND_ROLLOUT_COMMAND = "find-rollout"
AUDIT_READ_ROLLOUT_COMMAND = "read-rollout"
AUDIT_READ_APPENDWATCH_REPORT_COMMAND = "read-appendwatch-report"


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
TREE_LINE = re.compile(
    rf"^(?P<{TREE_INDENT_GROUP}>(?:(?:│   )|(?:    ))*)"
    rf"(?:├── |└── )(?P<{TREE_BODY_GROUP}>.*)$"
)

# ===================
# From former ipc.py
# ===================

SOCKET_PERMISSIONS = 0o600
DASHBOARD_IPC_SCHEME = SYNTHETIC_COMMIT_SCHEME
DASHBOARD_IPC_HOST = SYNTHETIC_COMMIT_HOST
DASHBOARD_SOCKET_PATH_ENV_NAME = "FASTAPI_DETOUR_DASHBOARD_SOCKET"
DASHBOARD_QUERY_PATH = QUERY_PATH
DEFAULT_DASHBOARD_SOCKET_PATH = (
    Path(tempfile.gettempdir()) / f"ktp-hcr-detour-ai-augment-{os.getuid()}.sock"
)
DASHBOARD_SOCKET_PATH = Path(
    os.environ.get(DASHBOARD_SOCKET_PATH_ENV_NAME, DEFAULT_DASHBOARD_SOCKET_PATH)
).expanduser()
