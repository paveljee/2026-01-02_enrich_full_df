from __future__ import annotations

import json
from dataclasses import dataclass
from inspect import getsource
from typing import Final

from . import pydantic_to_paste
from .pydantic_to_paste import (
    AI_AUGMENT_COLUMN_PREFIX,
    AI_AUGMENT_COLUMNS,
    AI_AUGMENT_EVIDENCE_COLUMNS,
    EVIDENCE_WITHDRAWAL_ACTION,
    EVIDENCE_WITHDRAWAL_ACTION_KEY,
    EVIDENCE_WITHDRAWAL_ATTESTED_KEY,
    EVIDENCE_WITHDRAWAL_REASON,
    EVIDENCE_WITHDRAWAL_REASON_KEY,
    EXCERPT_PAIRS_UNIQUE as PYDANTIC_EXCERPT_PAIRS_UNIQUE,
    EXCERPT_URL_NONBLANK as PYDANTIC_EXCERPT_URL_NONBLANK,
    MAX_PUSH_BODY_BYTES,
    SUBMISSION_EVIDENCE_KEY,
    SUBMISSION_EXCERPT_KEY,
    SUBMISSION_STANDARDIZED_VALUE_KEY,
    SUBMISSION_URL_KEY,
    SUBMISSION_VALUE_KEY,
    VALUE_NONBLANK as PYDANTIC_VALUE_NONBLANK,
    EvidenceSubmission,
    EvidenceWithdrawal,
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    KTP_AI_AUGMENT_COMMENTS_COL,
    KTP_AI_AUGMENT_EDUCATION_COL,
    KTP_AI_AUGMENT_GENDER_COL,
    KTP_AI_AUGMENT_LINKS_COL,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
    StandardizedValue,
    Submission,
    WebSearchExcerpt,
)

PYDANTIC_TO_PASTE_SOURCE = getsource(pydantic_to_paste).rstrip()

KTP_AI_AUGMENT_ATTEMPT_ID_COL = f"{AI_AUGMENT_COLUMN_PREFIX}attempt_id"
KTP_AI_AUGMENT_SESSION_METADATA_COL = f"{AI_AUGMENT_COLUMN_PREFIX}session_metadata"
KTP_AI_AUGMENT_FOOTNOTES_COL = f"{AI_AUGMENT_COLUMN_PREFIX}footnotes"
KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}footnote_arguments"


@dataclass(frozen=True)
class SubmissionFixture:
    """One complete pull identity and its Pydantic-valid push submission."""

    identity: tuple[str, str]
    submission: Submission


class Locale:
    API_TITLE: Final = "Highly-Cited Researcher Annotation API"
    API_DESCRIPTION: Final = (
        "Pull a JSONL annotation task, submit completed values, and compare the "
        "submission with ground truth."
    )
    PULL_SUMMARY: Final = "Pull the annotation task"
    PULL_DESCRIPTION: Final = (
        "Streams the source JSONL through the selected row. The selected row contains "
        "only the annotation columns with all values replaced by null."
    )
    PULL_RESPONSE_DESCRIPTION: Final = "JSON Lines annotation task"
    PUSH_SUMMARY: Final = "Submit completed annotations"
    PUSH_DESCRIPTION: Final = "Validates and stores the completed submission."
    PUSH_RESPONSE_DESCRIPTION: Final = (
        "Submission followed by ground truth. Pydantic schema:\n\n"
        f"```python\n{PYDANTIC_TO_PASTE_SOURCE}\n```"
    )
    EXCERPT_URL_NONBLANK: Final = PYDANTIC_EXCERPT_URL_NONBLANK
    VALUE_NONBLANK: Final = PYDANTIC_VALUE_NONBLANK
    EXCERPT_PAIRS_UNIQUE: Final = PYDANTIC_EXCERPT_PAIRS_UNIQUE
    CLI_DESCRIPTION: Final = "Serve the AI augmentation detour API."
    CONFIGURATION_ERROR_DETAIL: Final = (
        "API is not properly configured. Contact the human operator."
    )
    VALIDATION_ERROR_DETAIL: Final = (
        "Submission did not pass validation. Recheck every evidence excerpt and URL "
        "before retrying. Copy each excerpt verbatim as one contiguous span from the "
        "cited web-tool output, preserving every character—including repeated spaces, "
        "line breaks, punctuation, capitalization, and Unicode typography—and copy its "
        "associated URL exactly. Do not paraphrase, normalize, retype, or join separated "
        "text."
    )
    MULTIPLE_MATCH_DETAIL_TEMPLATE: Final = (
        "Excerpt matched multiple entries. Resubmit with an excerpt unique across "
        "the searched web pages: {excerpt}"
    )
    MULTIPLE_EVIDENCE_MATCHES_TEMPLATE: Final = (
        "excerpt matched multiple indexed results: {excerpt}"
    )
    PYDANTIC_MISSING_INPUT: Final = "<missing>"
    PYDANTIC_FAILURE: Final = "submission failed Pydantic validation"
    UNKNOWN_FIELD: Final = "unknown"

    SESSION_METADATA_NONBLANK: Final = "session metadata fields must be non-blank"
    CONTROL_RUN_NORMALIZED: Final = "control run fields must be non-blank and normalized"
    WEB_RESULT_REF_ID_NONBLANK: Final = "web result ref_id must be non-blank"

    SETTING_ABSOLUTE_TEMPLATE: Final = "{setting} must be an absolute path"
    SETTING_READABLE_FILE_TEMPLATE: Final = (
        "{setting} is not a readable regular file; rerun deploy.sh or correct .env"
    )
    FILES_CONFIG_RESOURCE_MISSING_TEMPLATE: Final = (
        "files_config is missing required detour resource {resource_key!r}"
    )
    CONFIGURED_RESOURCE_INVALID_TEMPLATE: Final = "configured {resource_key} resource is invalid"
    MAP_COLUMNS_INVALID_TEMPLATE: Final = "{resource_key} must have exactly columns {columns!r}"
    MAP_ROW_BLANK_TEMPLATE: Final = "{resource_key} row {row_number} has blank values"
    MAP_DRAW_CONFLICT_TEMPLATE: Final = "{resource_key} has conflicting draw {draw_number!r}"
    MAP_CSV_UNREADABLE_TEMPLATE: Final = "configured {resource_key} CSV is unreadable or malformed"
    MAP_CSV_EMPTY_TEMPLATE: Final = "configured {resource_key} CSV is empty"
    INNERDICTS_NON_TEXT_TEMPLATE: Final = "{table_name} has non-text innerdicts for {source_key}"
    INNERDICTS_MALFORMED_TEMPLATE: Final = (
        "{table_name} has malformed JSONL for {source_key} at line {line_number}"
    )
    INNERDICTS_NON_OBJECT_TEMPLATE: Final = (
        "{table_name} has a non-object row for {source_key} at line {line_number}"
    )
    SOURCE_DUCKDB_TABLE_MISSING_TEMPLATE: Final = "configured source DuckDB lacks {table_name}"
    TABLE_NAMEKEY_NON_TEXT_TEMPLATE: Final = "{table_name} contains a non-text name_key"
    TABLE_NAMEKEY_INVALID_TEMPLATE: Final = "{table_name} contains an invalid name_key"
    ELIGIBILITY_FLAGS_MISSING_TEMPLATE: Final = (
        "configured source DuckDB lacks usable {table_name} eligibility flags"
    )
    SOURCE_CLASSIFICATIONS_INVALID_TEMPLATE: Final = (
        "configured {table_name} contains invalid source classifications"
    )
    CARD_PARTITION_UNKNOWN_SOURCE_KEYS: Final = (
        "card-partition eligibility contains unknown source keys"
    )
    COHORTS_OVERLAP: Final = "ground-truth and no-ground-truth cohorts overlap"
    GROUND_TRUTH_CARDINALITY_TEMPLATE: Final = (
        "ground-truth cohort cardinality is invalid: expected {expected}, got {actual}"
    )
    NO_GROUND_TRUTH_CARDINALITY_TEMPLATE: Final = (
        "no-ground-truth cohort cardinality is invalid: expected {expected}, got {actual}"
    )
    ELIGIBLE_COHORT_CARDINALITY_INVALID: Final = "eligible cohort union cardinality is invalid"
    CARD_PARTITION_SOURCE_KEYS_MISMATCH: Final = (
        "card-partition source keys do not match innerdict-owned source keys"
    )
    INELIGIBILITY_CATEGORY_UNKNOWN: Final = "an ineligible source key has no recognized category"
    SOURCE_POPULATION_COHORTS_INVALID: Final = "source population cohort cardinalities are invalid"
    SOURCE_POPULATION_INELIGIBILITY_INVALID: Final = (
        "source population ineligibility categories are invalid"
    )
    SOURCE_POPULATION_CARDINALITY_INVALID: Final = "source population cardinality is invalid"
    SOURCE_POPULATION_RND_INVALID: Final = "source population rnd values are invalid"
    SOURCE_POPULATION_MULTIDRAW_INVALID: Final = (
        "source population contracted-draw count is invalid"
    )
    CONTROL_URL_INVALID_TEMPLATE: Final = "{environment_name} is invalid"
    CONTROL_URL_EXPECTED_TEMPLATE: Final = "{environment_name} must be http://{host}:{port}"
    CONTROL_ENDPOINT_UNAVAILABLE: Final = "Control Centre endpoint is unavailable"
    CONTROL_SANCTION_MALFORMED: Final = "Control Centre returned malformed sanction state"
    CONTROL_SANCTION_MISSING: Final = "Control Centre has no sanctioned run"
    CONTROL_SANCTION_CONSUMED: Final = "Control Centre run sanction has already been consumed"
    CONTROL_ACKNOWLEDGEMENT_MALFORMED: Final = "Control Centre returned malformed acknowledgement"
    CONTROL_ACKNOWLEDGEMENT_REFUSED: Final = "Control Centre refused accepted-run acknowledgement"
    CONFIG_INVALID_TEMPLATE: Final = "--config is invalid or unreadable: {config_path}"
    OUTPUT_FORMAT_INVALID: Final = "config output_format must be txt or docx"
    SOURCE_DUCKDB_UNREADABLE_TEMPLATE: Final = "configured source DuckDB is not readable: {db_file}"
    DOCX_REFERENCE_UNREADABLE: Final = (
        "configured DOCX output requires a readable pandoc_reference_docx"
    )
    TIMEZONE_INVALID_TEMPLATE: Final = "configured timezone is invalid: {timezone}"
    SOURCE_DUCKDB_VALIDATION_FAILED: Final = "configured source DuckDB could not be validated"
    DETOUR_DB_EQUALS_SOURCE: Final = "detour DuckDB path must differ from source DuckDB"
    API_CONFIG_REQUIRED_TEMPLATE: Final = (
        "API was not started with required --config {config_filename}"
    )
    ROLLOUT_NOT_SET_TEMPLATE: Final = (
        "{environment_name} is not set; add the active chat rollout path to the "
        "repository-root .env and restart the API"
    )
    ROLLOUT_WHITESPACE_TEMPLATE: Final = (
        "{environment_name} contains whitespace or control characters; correct .env and "
        "restart the API"
    )
    ROLLOUT_NOT_NORMALIZED_TEMPLATE: Final = (
        "{environment_name} must be normalized without traversal; correct .env and restart the API"
    )
    ROLLOUT_OUTSIDE_ROOT_TEMPLATE: Final = (
        "{environment_name} must be below {sessions_root}; correct .env and restart the API"
    )
    ROLLOUT_FILENAME_INVALID_TEMPLATE: Final = (
        "{environment_name} must name a rollout-*.jsonl file; correct .env and restart the API"
    )
    AIVM_INSTANCE_INVALID: Final = (
        "FASTAPI_DETOUR_AIVM_INSTANCE is invalid; correct .env and restart the API"
    )
    AIVM_USER_INVALID: Final = (
        "FASTAPI_DETOUR_AIVM_USER is invalid; correct .env and restart the API"
    )
    AIVM_SSH_PORT_INVALID: Final = (
        "FASTAPI_DETOUR_AIVM_SSH_PORT is invalid; correct .env and restart the API"
    )
    HOST_WORKBOOK_INVALID: Final = "host workbook is not a readable writable regular file"
    HOST_WORKBOOK_INITIALIZATION_FAILED: Final = (
        "host workbook could not be initialized in the AIVM workdir"
    )
    SCP_WORKBOOK_ARCHIVE_INVALID: Final = "SCP did not produce a regular workbook archive"
    GUEST_WORKBOOK_ARCHIVE_FAILED: Final = "guest workbook could not be archived"
    SCP_ROLLOUT_ARCHIVE_INVALID: Final = (
        "SCP did not produce a regular rollout archive; verify AIVM deployment"
    )
    ROLLOUT_SCP_FAILED: Final = (
        "rollout SCP failed; verify the configured rollout and AIVM SSH deployment"
    )
    APPENDWATCH_ARCHIVE_FAILED: Final = (
        "appendwatch status could not be archived; verify deployment and mounted report"
    )

    APPENDWATCH_REPORT_UNREADABLE: Final = "archived appendwatch report is unreadable"
    APPENDWATCH_REPORT_INCOMPLETE: Final = "archived appendwatch report is incomplete"
    APPENDWATCH_GLOBAL_DEGRADATION: Final = "appendwatch reports global monitoring degradation"
    APPENDWATCH_ROOT_MALFORMED: Final = "archived appendwatch report has a malformed root"
    APPENDWATCH_TREE_LINE_MALFORMED: Final = (
        "archived appendwatch report contains a malformed tree line"
    )
    APPENDWATCH_NESTING_INVALID: Final = "archived appendwatch report contains invalid nesting"
    APPENDWATCH_PATH_DUPLICATE: Final = "archived appendwatch report contains a duplicate path"
    APPENDWATCH_DIRECTORY_MALFORMED: Final = (
        "archived appendwatch report contains a malformed directory"
    )
    APPENDWATCH_FILE_ENTRY_MALFORMED: Final = (
        "archived appendwatch report contains a malformed file entry"
    )
    APPENDWATCH_STRAY_BLANK_LINE: Final = "archived appendwatch report has a stray blank line"
    APPENDWATCH_REMOVED_SECTION_MALFORMED: Final = (
        "archived appendwatch report has a malformed removed section"
    )
    APPENDWATCH_REMOVED_ENTRY_MALFORMED: Final = (
        "archived appendwatch report has a malformed removed entry"
    )
    ROLLOUT_REMOVED_OR_REPLACED: Final = "configured rollout was removed or replaced"
    ROLLOUT_STATUS_MISSING: Final = "missing"
    ROLLOUT_STATUS_AMBIGUOUS: Final = "ambiguous"
    ROLLOUT_STATUS_INVALID_TEMPLATE: Final = (
        "configured rollout status is {reason} in archived report"
    )
    ROLLOUT_NOT_OK: Final = "configured rollout is not OK beneath monitored ancestors"
    ROLLOUT_UNREADABLE: Final = "archived rollout is unreadable"
    ROLLOUT_JSONL_MALFORMED_TEMPLATE: Final = (
        "archived rollout contains malformed JSONL at line {line_number}"
    )
    ROLLOUT_LINE_NON_OBJECT_TEMPLATE: Final = (
        "archived rollout line {line_number} is not a JSON object"
    )
    TIMESTAMP_INVALID_TEMPLATE: Final = "{label} has an invalid timestamp"
    TIMESTAMP_TIMEZONE_MISSING_TEMPLATE: Final = "{label} timestamp must include a timezone"
    SESSION_META_PAYLOAD_LABEL: Final = "session_meta payload"
    SESSION_META_RESPONSE_LABEL: Final = "session_meta response"
    FUNCTION_OUTPUT_LABEL_TEMPLATE: Final = "function output {fco_id}"
    FUNCTION_CALL_LABEL_TEMPLATE: Final = "function call {fc_id}"
    WEB_CALL_ID_INVALID_TEMPLATE: Final = (
        "web call at rollout line {line_number} has an invalid call_id"
    )
    WEB_EVENT_CALL_ID_INVALID_TEMPLATE: Final = (
        "web event at rollout line {line_number} has an invalid call_id"
    )
    WEB_CALL_ARGUMENTS_UNSUPPORTED_TEMPLATE: Final = "web call {call_id} has unsupported arguments"
    WEB_CALL_ARGUMENTS_MALFORMED_TEMPLATE: Final = "web call {call_id} has malformed arguments"
    WEB_CALL_ARGUMENTS_NON_OBJECT_TEMPLATE: Final = (
        "web call {call_id} arguments are not a JSON object"
    )
    WEB_CALL_ACTION_COUNT_TEMPLATE: Final = (
        "web call {call_id} must contain exactly one eligible web action"
    )
    SESSION_META_COUNT_INVALID: Final = "rollout must contain exactly one session_meta record"
    SESSION_META_PAYLOAD_MALFORMED: Final = "session_meta payload is malformed"
    SESSION_META_SESSION_ID_INVALID: Final = "session_meta session_id is invalid"
    SESSION_META_ROLLOUT_MISMATCH: Final = (
        "session metadata does not match the configured rollout basename"
    )
    TURN_CONTEXT_MISSING: Final = "rollout has no valid turn_context metadata"
    SESSION_META_FIELDS_INCOMPLETE: Final = "rollout session metadata fields are incomplete"
    CITED_OUTPUT_BLOCK_INVALID_TEMPLATE: Final = (
        "cited function output at rollout line {line_number} must contain exactly one "
        "input_text block"
    )
    CITED_OUTPUT_IDS_INVALID_TEMPLATE: Final = (
        "cited function output at rollout line {line_number} has invalid IDs"
    )
    CITED_OUTPUT_IDS_DUPLICATE: Final = "cited function output IDs are duplicated"
    CITED_WEB_CHAIN_COUNT_TEMPLATE: Final = (
        "cited web chain {call_id} must have one function call and one web_search_end"
    )
    CITED_WEB_CHAIN_ORDER_TEMPLATE: Final = "cited web chain {call_id} is out of order"
    WEB_CALL_FC_ID_INVALID_TEMPLATE: Final = "web call {call_id} has an invalid or duplicate fc_id"
    WEB_EVENT_RESULTS_UNSUPPORTED_TEMPLATE: Final = "web event {call_id} has unsupported results"
    CITATION_RESULT_COUNT_TEMPLATE: Final = "citation {ref_id} does not resolve to one event result"
    CITATION_RESULT_METADATA_UNSUPPORTED_TEMPLATE: Final = (
        "citation {ref_id} has unsupported result metadata"
    )
    CUMULATIVE_ROW_CONFLICT_TEMPLATE: Final = (
        "conflicting cumulative rollout row in {table_name} for {key_value}"
    )
    PROVENANCE_PREFIX_OLDER: Final = (
        "archived rollout prefix is older than its persisted provenance index"
    )
    CITATION_PREFIX_OLDER: Final = (
        "archived rollout prefix is older than its persisted citation index"
    )
    ROLLOUT_LINKAGES_INCOMPLETE: Final = "normalized rollout call linkages are incomplete"
    PROVENANCE_INTEGRITY_QUERY_FAILED_TEMPLATE: Final = (
        "normalized provenance integrity query failed for {table_name}"
    )
    PROVENANCE_UNIQUENESS_FAILED_TEMPLATE: Final = (
        "normalized provenance uniqueness failed for {table_name}"
    )
    PROVENANCE_LINKAGE_QUERY_FAILED: Final = "normalized provenance linkage query failed"
    PROVENANCE_RELATIONSHIPS_INCOMPLETE: Final = (
        "normalized provenance relationships are incomplete"
    )
    PROVENANCE_PREFIX_MISMATCH: Final = (
        "persisted provenance does not match the current archived rollout prefix"
    )
    EVIDENCE_NO_MATCH_TEMPLATE: Final = (
        "{field}: excerpt has no indexed match; excerpt={excerpt!r} url={url!r}"
    )
    EVIDENCE_URL_MISMATCH_TEMPLATE: Final = (
        "{field}: submitted URL does not match; excerpt={excerpt!r} url={url!r}"
    )
    EVIDENCE_WITHDRAWAL_WITHOUT_BASELINE: Final = (
        "evidence withdrawal requires a prior unmatched retry item"
    )
    EVIDENCE_PROGRESS_TEMPLATE: Final = (
        "{verified} of {total} evidence items were verified. "
        "Preserve all verified values and evidence unchanged."
    )
    EVIDENCE_GOOD_PROGRESS_TEMPLATE: Final = (
        "Good progress: {verified} of {total} evidence items were verified. "
        "Preserve all verified values and evidence unchanged."
    )
    EVIDENCE_REVIEW_HEADER: Final = "Review the following flagged excerpts:"
    EVIDENCE_NEAR_ITEM_TEMPLATE: Final = (
        "- {location}; its wording appears close to the cited web result but may "
        "differ in case, accents, punctuation, whitespace, or line breaks."
    )
    EVIDENCE_UNMATCHED_ITEM_TEMPLATE: Final = (
        "- {location}; does not appear to match its cited web result. Verify this "
        "excerpt and URL against the original web-tool output."
    )
    EVIDENCE_WITHDRAWN_ITEM_TEMPLATE: Final = (
        "- {location}; was withdrawn as not present in the web results and does "
        "not count as verified evidence."
    )
    EVIDENCE_RETRY_INSTRUCTION: Final = (
        "Compare the flagged evidence items character-for-character with the "
        "originating web-tool output and resubmit the complete payload after correcting "
        "only the flagged items."
    )
    EVIDENCE_MINOR_CHANGE_ONLY_TEMPLATE: Final = (
        "{location} may receive only a minor textual correction that preserves its "
        "wording and cited URL."
    )
    EVIDENCE_EXACT_IMMUTABLE_TEMPLATE: Final = (
        "{immutable} was already verified and must be resubmitted unchanged."
    )
    EVIDENCE_ACCEPTED_FIELD_IMMUTABLE_TEMPLATE: Final = (
        EVIDENCE_EXACT_IMMUTABLE_TEMPLATE
        + "Preserve its value and complete evidence list unchanged."
    )
    EVIDENCE_COUNT_DECREASED_TEMPLATE: Final = (
        "{field} must retain every prior evidence item; use the explicit audited "
        "withdrawal object only for a previously unmatched item."
    )
    EVIDENCE_WITHDRAWAL_NOT_ALLOWED_TEMPLATE: Final = (
        "{location} cannot be withdrawn because it was already verified or resubmission is pending."
    )
    EVIDENCE_WITHDRAWAL_VALUE_UNCHANGED_TEMPLATE: Final = (
        "{field} withdrew unsupported evidence but did not correct the associated field value."
    )
    EVIDENCE_RETRY_IDENTITY_MISMATCH: Final = (
        "stored retry state does not match the sanctioned run identity"
    )
    EVIDENCE_AUDIT_REPLAY_FAILED: Final = (
        "stored evidence attempt audit cannot be replayed from its immutable baseline"
    )
    EVIDENCE_SUBMISSION_REJECTED: Final = (
        "submission contains evidence that is not yet exactly verified"
    )

    SOURCE_OPEN_FAILED_TEMPLATE: Final = "cannot open {source_file}: {error}"
    SOURCE_JSON_INVALID_TEMPLATE: Final = "invalid JSON in {source_file} at line {line_number}"
    SOURCE_ROW_NON_OBJECT_TEMPLATE: Final = (
        "expected an object in {source_file} at line {line_number}"
    )
    TARGET_ROW_KEYS_MISSING_TEMPLATE: Final = "target row is missing keys: {keys}"
    TARGET_ROW_IDENTITY_MISSING: Final = "target row is missing researcher identity"
    TARGET_GROUND_TRUTH_MISSING: Final = "target draw ground truth was not found"
    TASK_IDENTITY_INCOMPLETE: Final = "selected task identity is incomplete"
    TASK_IDENTITY_MISSING: Final = "selected task identity was not found"
    SOURCE_DUCKDB_OPEN_FAILED: Final = "configured source DuckDB could not be opened read-only"
    DETOUR_DUCKDB_OPEN_FAILED: Final = "detour DuckDB could not be opened"
    SANCTIONED_ROWS_DUPLICATE_TEMPLATE: Final = (
        "{table_name} contains duplicate rows for sanctioned source key"
    )
    SANCTIONED_SOURCE_INELIGIBLE: Final = "sanctioned source key is not eligible for this detour"
    SANCTIONED_SOURCE_MALFORMED: Final = "sanctioned source key is malformed"
    SANCTIONED_SOURCE_NONCANONICAL: Final = "sanctioned source key is not canonical"
    SANCTIONED_XLSX_CONTEXT_MISSING: Final = "sanctioned source key has no xlsx innerdict context"
    SANCTIONED_DRAW_MISSING: Final = "sanctioned source key has no innerdict-owned draw"
    GROUND_TRUTH_DOCX_INCOMPLETE: Final = "ground-truth researcher has no complete docx innerdict"
    RESEARCHER_NOT_UNIQUE: Final = "selected researcher did not resolve uniquely"
    ACCEPTED_IDENTITY_DUPLICATE: Final = (
        "attempt ID or rollout filename/line-count fragment is already accepted"
    )
    ATTEMPT_CARD_ZIP_EXISTS: Final = "attempt card ZIP already exists"
    RESEARCHER_CARD_COUNT_INVALID: Final = "selected researcher did not produce exactly one card"
    REQUEST_CONTENT_TYPE_INVALID: Final = "request Content-Type must be application/json"
    REQUEST_CONTENT_LENGTH_INVALID: Final = "request Content-Length is invalid"
    REQUEST_BODY_TOO_LARGE: Final = "request body exceeds the configured size limit"
    WORKBOOK_NOT_INITIALIZED: Final = "guest workbook was not initialized at backend startup"
    SANCTIONED_SESSION_MISMATCH: Final = "sanctioned session does not match archived rollout"
    CARD_INTRO_DATE_FORMAT: Final = "%B %d, %Y"

    API_STARTUP_FAILED_LOG: Final = "API startup failed: %s"
    ROUTES_DISABLED_LOG: Final = "pull and push are disabled: %s"
    ATTEMPT_RECORD_FAILED_LOG: Final = "push attempt=%s could not record stage=%s result=%s"
    PULL_FAILED_LOG: Final = "pull failed configuration/sanction validation: %s"
    PUSH_ACCEPTED_LOG: Final = "push attempt=%s accepted"
    CONTROL_ACKNOWLEDGEMENT_FAILED_LOG: Final = (
        "push attempt=%s accepted but Control Centre acknowledgement failed: %s"
    )
    PUSH_CONFIGURATION_FAILED_LOG: Final = "push attempt=%s failed stage=%s: %s"
    PUSH_MULTIPLE_MATCHES_LOG: Final = (
        "push attempt=%s failed stage=%s: excerpt matched multiple rows excerpt=%r"
    )
    PUSH_VALIDATION_FAILED_LOG: Final = "push attempt=%s failed stage=%s: %s"
    EVIDENCE_ITEM_ASSESSMENT_LOG: Final = (
        "push attempt=%s evidence field=%s index=%s outcome=%s excerpt=%r url=%r candidates=%r"
    )
    PUSH_PYDANTIC_FAILED_LOG: Final = "push attempt=%s failed stage=%s field=%s value=%r: %s"
    PUSH_UNEXPECTED_FAILED_LOG: Final = "push attempt=%s failed stage=%s: %s"


# Note: generated via chatgpt.com on 2026-07-27 UTC,
# using GPT-5.6-Sol-High with tools (context lost)
EXCERPT_PLACEHOLDER: Final = "Exact contiguous excerpt from a cited web result supporting {claim}."
URL_PLACEHOLDER: Final = "https://example.test/result"
L_FEI_FEI_FIXTURE = SubmissionFixture(
    identity=("L.", "Fei-Fei"),
    submission=Submission.model_validate_json(json.dumps({
        KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL: {
            SUBMISSION_VALUE_KEY: "Fei-Fei Li; publishes as L. Fei-Fei.",
            SUBMISSION_STANDARDIZED_VALUE_KEY: {
                "first_name": "Fei-Fei",
                "last_name": "Li",
            },
            SUBMISSION_EVIDENCE_KEY: [
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(claim="the value"),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                }
            ],
        },
        KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL: {
            SUBMISSION_VALUE_KEY: "Stanford campus, Stanford, California.",
            SUBMISSION_STANDARDIZED_VALUE_KEY: {
                "place": "Stanford campus, Stanford, California",
                "location": "US",
            },
            SUBMISSION_EVIDENCE_KEY: [
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(claim="the value"),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                }
            ],
        },
        KTP_AI_AUGMENT_GENDER_COL: {
            SUBMISSION_VALUE_KEY: "Female.",
            SUBMISSION_STANDARDIZED_VALUE_KEY: "Woman",
            SUBMISSION_EVIDENCE_KEY: [
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(claim="the value"),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                }
            ],
        },
        KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL: {
            SUBMISSION_VALUE_KEY: (
                "28–29; born in 1976, with the earliest visible work on the OpenAlex "
                "profile dated 2005."
            ),
            SUBMISSION_STANDARDIZED_VALUE_KEY: 1976,
            SUBMISSION_EVIDENCE_KEY: [
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim="the age/year of birth"
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim="the earliest visible publication date"
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
            ],
        },
        KTP_AI_AUGMENT_EDUCATION_COL: {
            SUBMISSION_VALUE_KEY: (
                "B.A. Physics, Princeton University, 1999; M.S. Electrical "
                "Engineering, Caltech, 2001; Ph.D. Electrical Engineering, "
                "Caltech, 2005."
            ),
            SUBMISSION_STANDARDIZED_VALUE_KEY: [
                {
                    "degree_conferred": "B.A. Physics",
                    "isced_level": "6",
                    "place_conferred": {
                        "organization_name": "Princeton University",
                        "openalex_id": "NR",
                        "ror": "NR",
                    },
                    "year_conferred": 1999,
                },
                {
                    "degree_conferred": "M.S. Electrical Engineering",
                    "isced_level": "7",
                    "place_conferred": {
                        "organization_name": "Caltech",
                        "openalex_id": "NR",
                        "ror": "NR",
                    },
                    "year_conferred": 2001,
                },
                {
                    "degree_conferred": "Ph.D. Electrical Engineering",
                    "isced_level": "8",
                    "place_conferred": {
                        "organization_name": "Caltech",
                        "openalex_id": "NR",
                        "ror": "NR",
                    },
                    "year_conferred": 2005,
                },
            ],
            SUBMISSION_EVIDENCE_KEY: [
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim="the bachelor degree place and year"
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim="the master's degree place and year"
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim="the PhD degree place and year"
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
            ],
        },
        KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL: {
            SUBMISSION_VALUE_KEY: (
                "Sequoia Capital Professor of Computer Science, Stanford; Senior "
                "Fellow, Stanford HAI; Professor by courtesy, Stanford Graduate "
                "School of Business; former Director, Stanford AI Lab, 2013–2018; "
                "former Vice President and Chief Scientist of AI/ML, Google Cloud, "
                "2017–2018; Co-founder and CEO, World Labs."
            ),
            SUBMISSION_STANDARDIZED_VALUE_KEY: [
                {
                    "academic_position": "Sequoia Capital Professor of Computer Science",
                    "academic_institution": {
                        "organization_name": "Stanford University",
                        "openalex_id": "NR",
                        "ror": "NR",
                    },
                },
                {
                    "academic_position": "Senior Fellow",
                    "academic_institution": {
                        "organization_name": "Stanford HAI",
                        "openalex_id": "NR",
                        "ror": "NR",
                    },
                },
                {
                    "academic_position": "Professor by courtesy",
                    "academic_institution": {
                        "organization_name": "Stanford Graduate School of Business",
                        "openalex_id": "NR",
                        "ror": "NR",
                    },
                },
                {
                    "academic_position": "Director",
                    "academic_institution": {
                        "organization_name": "Stanford AI Lab",
                        "openalex_id": "NR",
                        "ror": "NR",
                    },
                    "start": 2013,
                    "end": 2018,
                },
                {
                    "academic_position": "Vice President and Chief Scientist of AI/ML",
                    "academic_institution": {
                        "organization_name": "Google Cloud",
                        "openalex_id": "NR",
                        "ror": "NR",
                    },
                    "start": 2017,
                    "end": 2018,
                },
                {
                    "academic_position": "Co-founder and CEO",
                    "academic_institution": {
                        "organization_name": "World Labs",
                        "openalex_id": "NR",
                        "ror": "NR",
                    },
                },
            ],
            SUBMISSION_EVIDENCE_KEY: [
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim="the current academic position at Sequoia Capital"
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim="the current academic position at Stanford HAI"
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim=(
                            "the current academic position at Stanford Graduate School of Business"
                        )
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim=("the former academic position at Stanford AI Lab and the years")
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim=("the former academic positions at Google Cloud and the years")
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim="the current academic positions at World Labs"
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
            ],
        },
        KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL: {
            SUBMISSION_VALUE_KEY: (
                "Founding Co-Director, Stanford HAI; Co-founder and Chair, AI4ALL; "
                "member of the National Academy of Engineering, National Academy "
                "of Medicine, American Academy of Arts and Sciences, and Council "
                "on Foreign Relations; ACM Fellow; UN special adviser."
            ),
            SUBMISSION_STANDARDIZED_VALUE_KEY: [
                "Founding Co-Director, Stanford HAI",
                "Co-founder and Chair, AI4ALL",
                "Member, National Academy of Engineering",
                "Member, National Academy of Medicine",
                "Member, American Academy of Arts and Sciences",
                "Member, Council on Foreign Relations",
                "ACM Fellow",
                "United Nations special adviser",
            ],
            SUBMISSION_EVIDENCE_KEY: [
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim=("the professional membership/honours at Stanford HAI")
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim=("the professional membership/honours at AI4ALL")
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim=(
                            "the professional memberships/honours at "
                            "the National Academy of Engineering"
                        )
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim=(
                            "the professional membership/honours at "
                            "the National Academy of Medicine"
                        )
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim=(
                            "the professional membership/honours at "
                            "the American Academy of Arts and Sciences"
                        )
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim=(
                            "the professional membership/honours at "
                            "the Council on Foreign Relations"
                        )
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim=("the professional membership/honours at ACM")
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim=("the professional membership/honours at UN")
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
            ],
        },
        KTP_AI_AUGMENT_LINKS_COL: {
            SUBMISSION_VALUE_KEY: (
                "Stanford profile: https://profiles.stanford.edu/fei-fei-li; "
                "OpenAlex: https://openalex.org/A5100450462; "
                "AI4ALL: https://ai-4-all.org/our-people/fei-fei-li/"
            ),
            SUBMISSION_STANDARDIZED_VALUE_KEY: [
                {
                    "url": "https://profiles.stanford.edu/fei-fei-li",
                    "verified_with_orcid": False,
                },
                {
                    "url": "https://openalex.org/A5100450462",
                    "verified_with_orcid": True,
                },
                {
                    "url": "https://ai-4-all.org/our-people/fei-fei-li/",
                    "verified_with_orcid": False,
                },
            ],
            SUBMISSION_EVIDENCE_KEY: [
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim="the Stanford profile link/identifier"
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim="the OpenAlex link/identifier"
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
                {
                    SUBMISSION_EXCERPT_KEY: EXCERPT_PLACEHOLDER.format(
                        claim="the AI4ALL link/identifier"
                    ),
                    SUBMISSION_URL_KEY: URL_PLACEHOLDER,
                },
            ],
        },
        KTP_AI_AUGMENT_COMMENTS_COL: {
            SUBMISSION_VALUE_KEY: (
                "OpenAlex appears to conflate this author with unrelated researchers "
                "and institutions; age at first publication is therefore provisional."
            ),
        },
    }, ensure_ascii=False)),
)
