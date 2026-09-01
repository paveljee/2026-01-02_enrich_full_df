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
    SEARCH_FILTER: Final = "Search name, draw, or namekey"
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

    ELIGIBLE_COHORTS_NOT_CONFIGURED: Final = "eligible cohorts were not configured"
    GROUND_TRUTH_MISSING: Final = "ground-truth cohort contains no ground truth"
    NAMEKEYS_NOT_UNIQUE: Final = "researcher namekeys are not unique"
    POPULATION_INVARIANTS_FAILED: Final = "researcher population invariants failed"
    INELIGIBILITY_INVARIANTS_FAILED: Final = (
        "researcher ineligibility category invariants failed"
    )
    ACCEPTED_METADATA_INVALID: Final = "accepted output has invalid session metadata"
    ATTEMPT_DATABASE_INCONSISTENT: Final = (
        "validated attempt database state is inconsistent"
    )
    JOURNAL_DUPLICATE_RUN_ID: Final = (
        "dashboard run events contain a duplicate queued run ID"
    )
    JOURNAL_STORAGE_INVALID: Final = "dashboard run journal storage is invalid"
    JOURNAL_EVENT_WITHOUT_RUN: Final = (
        "dashboard run event has no matching run"
    )
    JOURNAL_SESSION_ID_MISSING: Final = (
        "session-discovered event has no session ID"
    )
    JOURNAL_REMOTE_PID_MISSING: Final = (
        "remote-PID-discovered event has no remote PID"
    )
    JOURNAL_ROLLOUT_PATH_MISSING: Final = (
        "rollout-discovered event has no path"
    )
    JOURNAL_ATTEMPT_ID_MISSING: Final = "push-accepted event has no attempt ID"
    UNKNOWN_NAMEKEY_TEMPLATE: Final = "unknown namekey: {namekey}"
    BACKEND_OUTPUT_PIPE_MISSING: Final = "backend output pipe was not created"
    BACKEND_OPENAPI_NOT_READY: Final = "backend OpenAPI endpoint is not ready"
    BACKEND_PULL_NOT_READY: Final = "backend cannot serve the configured pull"
    BACKEND_EXITED_EARLY: Final = "backend exited before becoming ready"
    BACKEND_READY_TIMEOUT: Final = "backend did not become ready"
    BACKEND_NOT_RUNNING: Final = "backend is not running"
    BACKEND_STDIN_MISSING: Final = "backend stdin pipe is unavailable"
    BACKEND_DATABASE_REQUEST_FAILED: Final = "backend database IPC query failed"
    BACKEND_DATABASE_RESPONSE_INVALID: Final = "backend database IPC response is invalid"
    BACKEND_CARD_MISSING: Final = "backend returned no researcher card"
    OPENALEX_API_KEY_MISSING: Final = (
        "OPENALEX_API_KEY is required in the Control Centre environment"
    )
    LIMA_CONFIG_UNREADABLE: Final = "Lima instance configuration is unreadable"
    LIMA_CONFIG_INVALID: Final = (
        "Lima instance configuration does not contain valid appendwatch topology; "
        "rerun deploy.sh"
    )
    LIMA_APPENDWATCH_PATH_INVALID: Final = (
        "Lima appendwatch parameter is not one normalized absolute guest path"
    )
    LIMA_MOUNT_INVALID: Final = "Lima configuration contains an invalid mount mapping"
    LIMA_APPENDWATCH_MOUNT_INVALID: Final = (
        "Lima appendwatch path does not map through exactly one configured mount"
    )
    LIMA_APPENDWATCH_REPORT_UNREADABLE: Final = (
        "Lima appendwatch mount does not expose one readable regular host report; "
        "rerun deploy.sh"
    )
    AIVM_COMMAND_FAILED_TEMPLATE: Final = (
        "AIVM command failed with exit {return_code}: {stderr}"
    )
    CODEX_EXITED_BEFORE_DISCOVERY: Final = (
        "Codex exited before its session was discovered"
    )
    CODEX_STDIN_UNAVAILABLE: Final = "Codex input stream is unavailable"
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
    RESTART_INTERRUPTED_RUN: Final = (
        "Control Centre restarted before the run completed"
    )
    SHUTDOWN_INTERRUPTED_RUN: Final = "Control Centre stopped before the run completed"
    INELIGIBLE_QUEUE: Final = "ineligible namekeys cannot be queued"
    UNKNOWN_RUN_ID_TEMPLATE: Final = "unknown run ID: {run_id}"
    CODEX_CANCEL_FAILED_TEMPLATE: Final = "Codex cancellation failed: {error}"
    CODEX_CANCELED_BEFORE_SESSION_HANDOFF: Final = (
        "Codex run was cancelled before session handoff"
    )
    CODEX_HANDLE_MISMATCH: Final = "Codex handle does not match the active run"
    ACCEPTED_SESSION_DUPLICATE: Final = (
        "accepted output contains duplicate session attempts"
    )
    UNKNOWN_VARIABLE_TEMPLATE: Final = "unknown variable: {variable_key}"
    SERVICES_NOT_STARTED: Final = "Control Centre services have not started"

    READY_LOG_TEMPLATE: Final = "ready at {url}"
    RUN_FAILED_LOG_TEMPLATE: Final = (
        "run failed: run_id={run_id} namekey={namekey} detail={detail}"
    )
    BACKEND_STOPPING_LOG_TEMPLATE: Final = "stopping Backend process: pid={pid}"
    BACKEND_STOPPED_LOG_TEMPLATE: Final = (
        "Backend process stopped: pid={pid} return_code={return_code}"
    )
    CODEX_REMOTE_STOPPING_LOG_TEMPLATE: Final = (
        "stopping recorded remote Codex process: run_id={run_id} "
        "session_id={session_id} remote_pid={remote_pid}"
    )
    CODEX_REMOTE_STOPPED_LOG_TEMPLATE: Final = (
        "recorded remote Codex process stopped: run_id={run_id} remote_pid={remote_pid}"
    )
    CODEX_SSH_STOPPING_LOG_TEMPLATE: Final = (
        "stopping local Codex SSH process: run_id={run_id} pid={pid}"
    )
    CODEX_SSH_STOPPED_LOG_TEMPLATE: Final = (
        "local Codex SSH process stopped: run_id={run_id} pid={pid} "
        "return_code={return_code}"
    )
    STOPPING_LOG: Final = "stopping"
    STOPPED_LOG: Final = "stopped"
