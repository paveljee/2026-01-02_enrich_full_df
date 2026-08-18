from __future__ import annotations

from typing import Final


class Locale:
    CONTROL_CENTRE_LOG_PREFIX: Final = "[control-centre]"
    BACKEND_LOG_PREFIX: Final = "[backend]"

    ACTION_QUEUE: Final = "Queue run"
    ACTION_CANCEL: Final = "Cancel run"
    ACTION_RERUN: Final = "Rerun"
    ACTION_DISABLED: Final = "Ineligible"
    ACTION_SELECT_RESEARCHER: Final = "Select a researcher"
    ACTION_VIEW_CARD: Final = "View researcher card"

    PAGE_TITLE: Final = "AI augmentation Control Centre"
    BACKEND_STARTING: Final = "Backend: starting"
    SUMMARY_LOADING: Final = "Loading researcher state…"
    VARIABLE_FILTER: Final = "Variable"
    STATUS_FILTER: Final = "Status"
    COHORT_FILTER: Final = "Cohort"
    SEARCH_FILTER: Final = "Search name, draw, or source key"
    ALL_STATUSES: Final = "All statuses"
    ALL_COHORTS: Final = "All cohorts"
    NO_RESEARCHER_SELECTED: Final = "No researcher selected"
    ATTEMPT_HISTORY: Final = "Attempt history"
    BACKEND_STATUS_TEMPLATE: Final = "Backend: {status}"
    SUMMARY_TEMPLATE: Final = (
        "Total {total} · ground truth {ground_truth} · "
        "no ground truth {no_ground_truth} · ineligible {ineligible} · "
        "ready {ready} · queued {queued} · running {running} · "
        "complete {complete} · failed {failed} · cancelled {canceled}"
    )
    RESEARCHER_SELECTION_TEMPLATE: Final = (
        "{first_name} {last_name} · draw(s) {draw_number}"
    )
    ATTEMPT_HISTORY_TEMPLATE: Final = (
        "Attempt history: {first_name} {last_name}"
    )
    CARD_INTRO_DATE_FORMAT: Final = "%B %d, %Y"

    ACCEPTED_IDENTIFIERS_INVALID: Final = (
        "accepted-run identifiers must be non-blank and normalized"
    )
    ELIGIBLE_COHORTS_NOT_CONFIGURED: Final = "eligible cohorts were not configured"
    GROUND_TRUTH_MISSING: Final = "ground-truth cohort contains no ground truth"
    SOURCE_KEYS_NOT_UNIQUE: Final = "researcher source keys are not unique"
    POPULATION_INVARIANTS_FAILED: Final = "researcher population invariants failed"
    INELIGIBILITY_INVARIANTS_FAILED: Final = (
        "researcher ineligibility category invariants failed"
    )
    ACCEPTED_METADATA_INVALID: Final = "accepted output has invalid session metadata"
    JOURNAL_APPEND_INCOMPLETE: Final = "run journal append was incomplete"
    JOURNAL_MALFORMED_TEMPLATE: Final = (
        "run journal is malformed at line {line_number}"
    )
    JOURNAL_DUPLICATE_RUN_ID: Final = (
        "run journal contains a duplicate queued run ID"
    )
    JOURNAL_EVENT_WITHOUT_RUN: Final = (
        "run journal event has no matching queued run"
    )
    JOURNAL_SESSION_ID_MISSING: Final = (
        "session-discovered event has no session ID"
    )
    JOURNAL_ROLLOUT_PATH_MISSING: Final = (
        "rollout-discovered event has no path"
    )
    JOURNAL_ATTEMPT_ID_MISSING: Final = "push-accepted event has no attempt ID"
    UNKNOWN_SOURCE_KEY_TEMPLATE: Final = "unknown source key: {source_key}"
    CARD_COUNT_INVALID: Final = "selected researcher did not render exactly one card"
    BACKEND_OUTPUT_PIPE_MISSING: Final = "backend output pipe was not created"
    BACKEND_OPENAPI_NOT_READY: Final = "backend OpenAPI endpoint is not ready"
    BACKEND_EXITED_EARLY: Final = "backend exited before becoming ready"
    BACKEND_READY_TIMEOUT: Final = "backend did not become ready"
    BACKEND_NOT_RUNNING: Final = "backend is not running"
    OPENALEX_API_KEY_MISSING: Final = (
        "OPENALEX_API_KEY is required in the Control Centre environment"
    )
    AIVM_COMMAND_FAILED_TEMPLATE: Final = (
        "AIVM command failed with exit {return_code}: {stderr}"
    )
    CODEX_EXITED_BEFORE_DISCOVERY: Final = (
        "Codex exited before its session was discovered"
    )
    CODEX_SESSION_DISCOVERY_TIMEOUT: Final = "Codex session was not discovered"
    CODEX_ROLLOUT_NOT_UNIQUE: Final = "Codex rollout path did not resolve uniquely"
    CODEX_REMOTE_PID_MISSING: Final = (
        "Codex remote PID was not available for cancellation"
    )
    CODEX_SSH_DID_NOT_EXIT: Final = (
        "Codex SSH process did not exit during cancellation"
    )
    CODEX_REMOTE_PID_NOT_POSITIVE: Final = "remote PID must be positive"
    CODEX_REMOTE_DID_NOT_EXIT: Final = (
        "Codex remote process did not exit during cancellation"
    )
    SANCTION_ALREADY_ACTIVE: Final = "another run is already sanctioned"
    RESTART_INTERRUPTED_RUN: Final = (
        "Control Centre restarted before the run completed"
    )
    INELIGIBLE_QUEUE: Final = "ineligible source keys cannot be queued"
    UNKNOWN_RUN_ID_TEMPLATE: Final = "unknown run ID: {run_id}"
    CODEX_CANCEL_FAILED_TEMPLATE: Final = "Codex cancellation failed: {error}"
    ACCEPTED_PUSH_MISMATCH: Final = (
        "accepted push does not match the current sanctioned run"
    )
    CARD_READ_SUSPENDED: Final = (
        "detour card reads are suspended while a run is active"
    )
    CODEX_CANCELED_BEFORE_SANCTION: Final = (
        "Codex run was cancelled before sanctioning"
    )
    CODEX_HANDLE_MISMATCH: Final = "Codex handle does not match the active run"
    ACCEPTED_SESSION_DUPLICATE: Final = (
        "accepted output contains duplicate session attempts"
    )
    UNKNOWN_VARIABLE_TEMPLATE: Final = "unknown variable: {variable_key}"
    SERVICES_NOT_STARTED: Final = "Control Centre services have not started"

    READY_LOG_TEMPLATE: Final = "ready at {url}"
    STOPPING_LOG: Final = "stopping"
    STOPPED_LOG: Final = "stopped"
