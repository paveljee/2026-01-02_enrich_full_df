from __future__ import annotations

from typing import Final

from .vars import (
    PYDANTIC_TO_PASTE_SOURCE,
)


class Locale:
    API_TITLE: Final = "Highly-Cited Researcher Annotation API"
    API_DESCRIPTION: Final = (
        "Pull a JSONL annotation task, submit completed values, and compare the "
        "submission with ground truth."
    )
    PULL_SUMMARY: Final = "Pull the annotation task"
    PULL_DESCRIPTION: Final = (
        "Returns the configured JSON Lines annotation task, Markdown resubmission "
        "instructions, the accepted result, or the current processing state."
    )
    PULL_RESPONSE_DESCRIPTION: Final = "JSON Lines annotation task or Markdown retry"
    PUSH_SUMMARY: Final = "Submit completed annotations"
    PUSH_DESCRIPTION: Final = (
        "Durably accepts the submission before asynchronous validation."
    )
    PUSH_RESPONSE_DESCRIPTION: Final = "Submission durably accepted; poll Location for outcome."
    EXCERPT_URL_NONBLANK = "excerpt and url must be non-blank"
    VALUE_NONBLANK = "value must be non-blank"
    EXCERPT_PAIRS_UNIQUE = "web_search_excerpts must not contain duplicate pairs"
    EXAMPLE_EXCERPT_TEMPLATE: Final = (
        "Exact contiguous excerpt from a cited web result supporting {claim}."
    )
    EXAMPLE_RESULT_URL: Final = "https://example.test/result"
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
    SESSION_ID_STDIN_INVALID: Final = "Backend stdin session ID is not a canonical UUID"
    SESSION_ID_STDIN_CONFLICT: Final = "Backend stdin supplied conflicting session IDs"
    SESSION_ID_STDIN_MISSING: Final = "Backend stdin closed before supplying a session ID"
    SESSION_ID_STDIN_ACCEPTED_LOG: Final = "Backend stdin accepted Codex session ID %s"
    SESSION_ID_STDIN_FAILED_LOG: Final = "Backend stdin session-ID reader failed: %s"
    APPENDWATCH_READABLE_LOG: Final = "proved APPENDWATCH_REPORT readable: %s"
    CODEX_SESSIONS_READABLE_LOG: Final = "proved Codex sessions directory readable: %s"
    CODEX_SESSIONS_UNREADABLE: Final = "Codex sessions directory is not readable"
    CONTROL_PARENT_PID_INVALID: Final = "Control Centre parent PID is invalid"
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
    INNERDICTS_NON_TEXT_TEMPLATE: Final = "{table_name} has non-text innerdicts for {namekey}"
    INNERDICTS_MALFORMED_TEMPLATE: Final = (
        "{table_name} has malformed JSONL for {namekey} at line {line_number}"
    )
    INNERDICTS_NON_OBJECT_TEMPLATE: Final = (
        "{table_name} has a non-object row for {namekey} at line {line_number}"
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
    CARD_PARTITION_UNKNOWN_NAMEKEYS: Final = (
        "card-partition eligibility contains unknown namekeys"
    )
    COHORTS_OVERLAP: Final = "ground-truth and no-ground-truth cohorts overlap"
    GROUND_TRUTH_CARDINALITY_TEMPLATE: Final = (
        "ground-truth cohort cardinality is invalid: expected {expected}, got {actual}"
    )
    NO_GROUND_TRUTH_CARDINALITY_TEMPLATE: Final = (
        "no-ground-truth cohort cardinality is invalid: expected {expected}, got {actual}"
    )
    ELIGIBLE_COHORT_CARDINALITY_INVALID: Final = "eligible cohort union cardinality is invalid"
    CARD_PARTITION_NAMEKEYS_MISMATCH: Final = (
        "card-partition namekeys do not match innerdict-owned namekeys"
    )
    INELIGIBILITY_CATEGORY_UNKNOWN: Final = "an ineligible namekey has no recognized category"
    SOURCE_POPULATION_COHORTS_INVALID: Final = "source population cohort cardinalities are invalid"
    SOURCE_POPULATION_INELIGIBILITY_INVALID: Final = (
        "source population ineligibility categories are invalid"
    )
    SOURCE_POPULATION_CARDINALITY_INVALID: Final = "source population cardinality is invalid"
    SOURCE_POPULATION_RND_INVALID: Final = "source population rnd values are invalid"
    SOURCE_POPULATION_MULTIDRAW_INVALID: Final = (
        "source population contracted-draw count is invalid"
    )
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
    SCP_ROLLOUT_ARCHIVE_INVALID: Final = (
        "SCP did not produce a regular rollout archive; verify AIVM deployment"
    )
    ROLLOUT_SCP_FAILED: Final = (
        "rollout SCP failed; verify the configured rollout and AIVM SSH deployment"
    )
    ROLLOUT_DISCOVERY_FAILED: Final = "rollout discovery on the Agent Runtime failed"
    ROLLOUT_DISCOVERY_NOT_UNIQUE: Final = (
        "Codex session ID did not resolve to exactly one rollout"
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
    EVIDENCE_LOCATION_TEMPLATE: Final = "{field}.web_search_excerpts[{index}]"
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
    EVIDENCE_RETRY_STANDARDIZED_VALUES: Final = (
        "The resubmission must also supply standardized_value for every "
        "evidence-bearing field. Pydantic schema: "
        "\n\n```python\n{}\n```\n\n"
    ).format(PYDANTIC_TO_PASTE_SOURCE)
    EVIDENCE_RETRY_EXAMPLE_TEMPLATE: Final = (
        "Complete standardized resubmission example:\n\n```json\n{example}\n```"
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
        "stored retry state does not match the configured namekey/session identity"
    )
    EVIDENCE_AUDIT_REPLAY_FAILED: Final = (
        "stored evidence attempt audit cannot be replayed from its immutable baseline"
    )
    EVIDENCE_SUBMISSION_REJECTED: Final = (
        "submission contains evidence that is not yet exactly verified"
    )

    REPLAY_LOG_TAIL_REPAIR_FAILED: Final = "authoritative replay-log tail repair failed"
    REPLAY_LOG_TAIL_REPAIR_PROMPT_TEMPLATE: Final = (
        "Authoritative replay log {path} ends with an incomplete record. "
        "Discard its final {discarded_bytes} byte(s)? [y/N] "
    )
    REPLAY_LOG_TAIL_REPAIR_DECLINED: Final = (
        "operator declined authoritative replay-log tail repair"
    )
    REPLAY_LOG_UNREADABLE: Final = "authoritative replay log is unreadable"
    REPLAY_LOG_ALREADY_LOCKED: Final = (
        "another backend process already owns the authoritative replay log"
    )
    REPLAY_LOG_LINE_INVALID_TEMPLATE: Final = (
        "authoritative replay log line {line_number} is invalid"
    )
    REPLAY_PROJECTION_CONFLICT: Final = (
        "detour database projection conflicts with the authoritative replay log"
    )
    REPLAY_PROJECTION_FAILED: Final = "authoritative replay projection failed"
    REPLAY_RECORD_CONTOUR_INVALID: Final = "authoritative HTTP record contour is invalid"
    REPLAY_COMMIT_INVALID: Final = "authoritative private commit is inconsistent"
    REPLAY_COMMIT_LINK_MISSING: Final = "private commit references a missing HTTP record"
    REPLAY_COMMIT_LINK_INVALID: Final = "private commit references an invalid HTTP exchange"
    REPLAY_COMMIT_PULL_INVALID: Final = "private commit references an invalid pull"
    REPLAY_COMMIT_SOURCE_KEY_INVALID: Final = "private commit Source-Key is invalid"
    REPLAY_COMMIT_NAME_KEY_INVALID: Final = "private commit Name-Key is invalid"
    REPLAY_PUBLIC_PUSH_INVALID: Final = "authoritative public push audit is inconsistent"
    ROLLOUT_CAS_CONFLICT: Final = "rollout content-addressed storage contains a conflict"
    ROLLOUT_CAS_BLOB_INVALID: Final = "committed rollout snapshot is missing or invalid"
    INTERNAL_COMMIT_API_TITLE: Final = "AI Augmentation Private Commit API"
    AUTHORITATIVE_RESPONSE_NOT_UTF8: Final = (
        "backend push responses must be finite UTF-8 payloads"
    )
    AUTHORITATIVE_RESPONSE_INCOMPLETE_LOG: Final = (
        "authoritative %s %s handler produced an incomplete ASGI response"
    )
    AUTHORITATIVE_LOG_NOT_OPEN: Final = "authoritative replay log is not open"
    AUTHORITATIVE_LOG_APPEND_FAILED: Final = "authoritative replay-log append failed"
    AUTHORITATIVE_COMMAND_BUSY: Final = (
        "Another state-changing request is in progress; retry by polling first."
    )
    AUTHORITATIVE_PROJECTION_FAILED_LOG: Final = (
        "authoritative log line %s committed but DuckDB projection failed; "
        "backend is unhealthy: %s"
    )
    AUTHORITATIVE_HANDLER_FAILED_LOG: Final = "authoritative %s %s handler failed"
    AUTHORITATIVE_LOG_APPEND_FAILED_LOG: Final = (
        "authoritative %s %s response could not be committed to the replay log: %s"
    )
    AUTHORITATIVE_BACKEND_UNHEALTHY_LOG: Final = (
        "rejecting authoritative %s %s because an earlier committed record is not projected"
    )
    POST_COMMIT_VALIDATION_FAILED_LOG: Final = (
        "post-commit validation commit=%s stage=%s failed: %s"
    )
    PUSH_LINKAGE_MISSING: Final = "accepted push has no current pull or Codex session"
    POST_ACCEPT_PROCESSING_FAILED_LOG: Final = "accepted push post-processing failed: %s"
    COMMIT_APPEND_FATAL_LOG: Final = "private commit append failed fatally: %s"

    OPENALEX_API_KEY_MISSING: Final = (
        "OPENALEX_API_KEY is required to validate an OpenAlex institution"
    )
    OPENALEX_INSTITUTION_UNKNOWN_TEMPLATE: Final = (
        "OpenAlex institution was not found: {openalex_id}"
    )
    OPENALEX_INSTITUTION_NAME_MISMATCH_TEMPLATE: Final = (
        "OpenAlex institution name {actual!r} does not match submitted name {submitted!r}"
    )
    OPENALEX_INSTITUTION_ROR_MISMATCH_TEMPLATE: Final = (
        "OpenAlex institution ROR {actual!r} does not match submitted ROR {submitted!r}"
    )
    ROR_INSTITUTION_UNKNOWN_TEMPLATE: Final = "ROR institution was not found: {ror}"
    ROR_INSTITUTION_NAME_MISMATCH_TEMPLATE: Final = (
        "ROR institution name {actual!r} does not match submitted name {submitted!r}"
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
    CONFIGURED_ROWS_DUPLICATE_TEMPLATE: Final = (
        "{table_name} contains duplicate rows for configured namekey"
    )
    CONFIGURED_NAMEKEY_INELIGIBLE: Final = "configured namekey is not eligible for this detour"
    CONFIGURED_NAMEKEY_INELIGIBLE_TEMPLATE: Final = (
        "configured namekey is ineligible for this detour: {category}"
    )
    CONFIGURED_NAMEKEY_MALFORMED: Final = "configured namekey is malformed"
    CONFIGURED_NAMEKEY_NONCANONICAL: Final = "configured namekey is not canonical"
    CONFIGURED_NAMEKEY_NOT_FOUND: Final = "configured namekey was not found"
    CONFIGURED_NAMEKEY_NOT_FOUND_SUGGESTIONS_TEMPLATE: Final = (
        "configured namekey was not found; did you mean {suggestions}?"
    )
    NAMEKEY_NOT_SET_TEMPLATE: Final = "namekey is not set in {environment_name}"
    CONFIGURED_XLSX_CONTEXT_MISSING: Final = "configured namekey has no xlsx innerdict context"
    CONFIGURED_DRAW_MISSING: Final = "configured namekey has no innerdict-owned draw"
    GROUND_TRUTH_DOCX_INCOMPLETE: Final = "ground-truth researcher has no complete docx innerdict"
    RESEARCHER_NOT_UNIQUE: Final = "selected researcher did not resolve uniquely"
    ACCEPTED_IDENTITY_DUPLICATE: Final = (
        "attempt ID or rollout filename/line-count fragment is already accepted"
    )
    ATTEMPT_CARD_ZIP_EXISTS: Final = "attempt card ZIP already exists"
    ATTEMPT_HTTP_LOG_EXISTS: Final = "attempt HTTP request log already exists"
    ARCHIVED_ATTEMPT_PATH_INVALID: Final = "archived attempt path is invalid"
    ARCHIVED_ATTEMPT_MANIFEST_INVALID: Final = "archived attempt manifest is invalid"
    ARCHIVED_ATTEMPT_ARTIFACT_INVALID_TEMPLATE: Final = (
        "archived attempt artifact is invalid: {artifact}"
    )
    ARCHIVED_ATTEMPT_HTTP_INVALID: Final = "archived attempt HTTP request log is invalid"
    ARCHIVED_ATTEMPT_OUTCOME_MISMATCH: Final = "archived attempt result does not match replay"
    RESEARCHER_CARD_COUNT_INVALID: Final = "selected researcher did not produce exactly one card"
    REQUEST_CONTENT_TYPE_INVALID: Final = "request Content-Type must be application/json"
    REQUEST_CONTENT_LENGTH_INVALID: Final = "request Content-Length is invalid"
    REQUEST_BODY_TOO_LARGE: Final = "request body exceeds the configured size limit"
    CONFIGURED_SESSION_MISMATCH: Final = "configured session does not match archived rollout"
    CARD_INTRO_DATE_FORMAT: Final = "%B %d, %Y"

    API_STARTUP_FAILED_LOG: Final = "API startup failed: %s"
    ROUTES_DISABLED_LOG: Final = "pull and push are disabled: %s"
    ATTEMPT_RECORD_FAILED_LOG: Final = "push attempt=%s could not record stage=%s result=%s"
    PULL_FAILED_LOG: Final = "pull failed configuration validation: %s"
    PUSH_ACCEPTED_LOG: Final = "push attempt=%s accepted"
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
