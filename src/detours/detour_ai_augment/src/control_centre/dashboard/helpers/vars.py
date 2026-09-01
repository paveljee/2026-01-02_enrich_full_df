import shlex
from pathlib import Path, PurePosixPath
from typing import Final

# =============================================================================
# Paths / process configuration
# =============================================================================

REPOSITORY_ROOT_PARENT_INDEX: Final = 7
PATH_TO_THIS_MODULE = Path(__file__).resolve()
REPOSITORY_ROOT: Final = PATH_TO_THIS_MODULE.parents[REPOSITORY_ROOT_PARENT_INDEX]

DEFAULT_CONFIG_PATH: Final = REPOSITORY_ROOT / "config_ai_augment.json"

AIVM_INSTANCE: Final = "aivm"
AIVM_USER: Final = "ai"
AIVM_HOME: Final = PurePosixPath("/home/ai")
AIVM_SSH_PORT: Final = "22022"

AIVM_KEY_DIR: Final = Path.home() / ".local" / "share" / "aivm" / ".ssh"
AIVM_IDENTITY_FILE: Final = AIVM_KEY_DIR / "id_ed25519"
AIVM_KNOWN_HOSTS_FILE: Final = AIVM_KEY_DIR / "known_hosts"
LIMA_SSH_CONFIG_PATH: Final = Path.home() / ".lima" / AIVM_INSTANCE / "ssh.config"

AIVM_SSH_TARGET: Final = f"{AIVM_INSTANCE}-{AIVM_USER}"
AIVM_HOST_KEY_ALIAS: Final = f"lima-{AIVM_INSTANCE}-{AIVM_USER}"
SSH_EXECUTABLE: Final = "ssh"
SSH_CONFIG_FLAG: Final = "-F"
SSH_OPTION_FLAG: Final = "-o"
SSH_REMOTE_FORWARD_FLAG: Final = "-R"
AIVM_SSH_CONNECTION_COMMAND: Final = (
    SSH_EXECUTABLE,
    SSH_CONFIG_FLAG,
    str(LIMA_SSH_CONFIG_PATH),
    SSH_OPTION_FLAG,
    f"ProxyJump=lima-{AIVM_INSTANCE}",
    SSH_OPTION_FLAG,
    "HostName=127.0.0.1",
    SSH_OPTION_FLAG,
    f"Port={AIVM_SSH_PORT}",
    SSH_OPTION_FLAG,
    f"User={AIVM_USER}",
    SSH_OPTION_FLAG,
    f"IdentityFile={AIVM_IDENTITY_FILE}",
    SSH_OPTION_FLAG,
    "IdentitiesOnly=yes",
    SSH_OPTION_FLAG,
    "BatchMode=yes",
    SSH_OPTION_FLAG,
    "PasswordAuthentication=no",
    SSH_OPTION_FLAG,
    "KbdInteractiveAuthentication=no",
    SSH_OPTION_FLAG,
    "ForwardAgent=no",
    SSH_OPTION_FLAG,
    "ClearAllForwardings=no",
    SSH_OPTION_FLAG,
    f"UserKnownHostsFile={AIVM_KNOWN_HOSTS_FILE}",
    SSH_OPTION_FLAG,
    f"HostKeyAlias={AIVM_HOST_KEY_ALIAS}",
    SSH_OPTION_FLAG,
    "StrictHostKeyChecking=accept-new",
)

LIMA_CONFIG_PATH: Final = Path.home() / ".lima" / AIVM_INSTANCE / "lima.yaml"

BACKEND_HOST: Final = "127.0.0.1"
BACKEND_PORT: Final = 8612
BACKEND_BASE_URL: Final = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
BACKEND_OPENAPI_URL: Final = f"{BACKEND_BASE_URL}/openapi.json"
BACKEND_PULL_URL: Final = f"{BACKEND_BASE_URL}/pull"

BACKEND_MODULE: Final = "src.detours.detour_ai_augment.src.backend.api"

BACKEND_READY_TIMEOUT_SECONDS: Final = 30
BACKEND_READY_POLL_SECONDS: Final = 0.1
PROCESS_STOP_TIMEOUT_SECONDS: Final = 10
TEXT_ENCODING: Final = "utf-8"
TEXT_DECODE_ERROR_POLICY: Final = "replace"
CONTROL_CENTRE_HOST: Final = "127.0.0.1"
CONTROL_CENTRE_PORT: Final = 8611
CONTROL_CENTRE_BASE_URL: Final = f"http://{CONTROL_CENTRE_HOST}:{CONTROL_CENTRE_PORT}"

CHROME_DEVTOOLS_PATH: Final = "/.well-known/appspecific/com.chrome.devtools.json"

CONTROL_HTTP_TIMEOUT_SECONDS: Final = 10

CODEX_REMOTE_FORWARD: Final = f"{BACKEND_HOST}:{BACKEND_PORT}:{BACKEND_HOST}:{BACKEND_PORT}"
AIVM_SSH_FORWARD_COMMAND: Final = (
    *AIVM_SSH_CONNECTION_COMMAND,
    SSH_OPTION_FLAG,
    "ExitOnForwardFailure=yes",
    SSH_REMOTE_FORWARD_FLAG,
    CODEX_REMOTE_FORWARD,
    AIVM_SSH_TARGET,
)


CODEX_SESSIONS_ROOT: Final = AIVM_HOME / ".codex" / "sessions"
CODEX_WORKDIR: Final = AIVM_HOME / "workdir"
CODEX_ENV_PATH: Final = CODEX_WORKDIR / ".openalex.env"
CODEX_CLI_BIN_PATH: Final = AIVM_HOME / ".local" / "bin" / "codex"
CODEX_RUN_MARKER_TEMPLATE: Final = ".codex-run-{run_id}.marker"
CODEX_RUN_PID_TEMPLATE: Final = ".codex-run-{run_id}.pid"
CODEX_DISCOVERY_TIMEOUT_SECONDS: Final = 30
CODEX_DISCOVERY_POLL_SECONDS: Final = 0.1
CODEX_CANCEL_TIMEOUT_SECONDS: Final = 10
CODEX_REMOTE_PROCESS_ALIVE_MARKER: Final = "alive"
CODEX_REMOTE_BUSY_MARKER: Final = "busy"
CODEX_REMOTE_PID_READ_COMMAND_TEMPLATE: Final = "cat -- {pid_path}"
CODEX_REMOTE_PROCESS_ALIVE_COMMAND_TEMPLATE: Final = (
    "if kill -0 -- {remote_pid} 2>/dev/null; then printf '%s' {alive_marker}; fi"
)
CODEX_REMOTE_SIGNAL_COMMAND_TEMPLATE: Final = "kill -{signal} -- {remote_pid}"
CODEX_REMOTE_TERMINATE_SIGNAL: Final = "TERM"
CODEX_REMOTE_KILL_SIGNAL: Final = "KILL"
CODEX_REMOTE_EXEC_COMMAND_TEMPLATE: Final = (
    "printf '%s\\n' \"$$\" > {pid_path}; . {environment_path}; exec {codex_command}"
)
CODEX_ENV_EXPORT_TEMPLATE: Final = "export {name}={value}\\n"
CODEX_REMOTE_WRITE_FILE_COMMAND_TEMPLATE: Final = (
    "mkdir -p -- {parent_path} && umask 077 && cat > {file_path}"
)
CODEX_REMOTE_PREPARE_RUN_COMMAND_TEMPLATE: Final = (
    "mkdir -p -- {workdir} && rm -f -- {pid_path} && touch -- {marker_path}"
)
CODEX_REMOTE_FIND_NEW_ROLLOUT_COMMAND_TEMPLATE: Final = (
    "find {sessions_root} -type f -name 'rollout-*.jsonl' "
    "-newer {marker_path} -print | LC_ALL=C sort | tail -n 1"
)
CODEX_REMOTE_FIRST_LINE_COMMAND_TEMPLATE: Final = "head -n 1 -- {rollout_path}"
CODEX_REMOTE_FIND_ROLLOUT_COMMAND_TEMPLATE: Final = (
    "find {sessions_root} -type f -name {rollout_name} -print | LC_ALL=C sort"
)
CODEX_ROLLOUT_FILENAME_TEMPLATE: Final = (
    "rollout-{local_timestamp:%Y-%m-%dT%H-%M-%S}-{session_id}.jsonl"
)
CODEX_INPUT_TEMPLATE: Final = "{openapi_url}\n"
CODEX_EXEC_COMMAND: Final = (
    str(CODEX_CLI_BIN_PATH),
    "exec",
    "--skip-git-repo-check",
    "-",
)
CODEX_REMOTE_PROCESS_PATTERN: Final = " ".join(
    (
        str(CODEX_CLI_BIN_PATH.parent / "[c]odex"),
        *CODEX_EXEC_COMMAND[1:],
    )
)
CODEX_REMOTE_BUSY_COMMAND_TEMPLATE: Final = (
    "if pgrep -f -- {process_pattern} >/dev/null; then printf '%s' {busy_marker}; fi"
)

CODEX_REMOTE_BUSY_COMMAND: Final = CODEX_REMOTE_BUSY_COMMAND_TEMPLATE.format(
    process_pattern=shlex.quote(CODEX_REMOTE_PROCESS_PATTERN),
    busy_marker=shlex.quote(CODEX_REMOTE_BUSY_MARKER),
)
