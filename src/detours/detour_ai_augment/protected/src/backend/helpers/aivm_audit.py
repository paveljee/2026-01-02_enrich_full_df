from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path, PurePosixPath
from uuid import UUID

from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AIVM_AUDIT_USER,
    AIVM_IDENTITY_FILE,
    AIVM_IDENTITY_FILE_ENV_NAME,
    AIVM_INSTANCE,
    AIVM_KNOWN_HOSTS_FILE,
    AIVM_KNOWN_HOSTS_FILE_ENV_NAME,
    AIVM_SSH_PORT,
    APPENDWATCH_REPORT,
    APPENDWATCH_REPORT_ENV_NAME,
    AUDIT_FIND_ROLLOUT_COMMAND,
    AUDIT_PROBE_COMMAND,
    AUDIT_READ_APPENDWATCH_REPORT_COMMAND,
    CODEX_SESSIONS_ROOT,
    CURRENT_DIRECTORY,
    FORBIDDEN_NORMALIZED_PATH_PARTS,
    HAS_CONTROL_CHARACTER,
    LIMA_SSH_CONFIG_ENV_NAME,
    LIMA_SSH_CONFIG_PATH,
    MAX_TCP_PORT,
    MIN_TCP_PORT,
    ROLLOUT_ENV_NAME,
    ROLLOUT_FILENAME_PREFIX,
    ROLLOUT_FILENAME_SUFFIX,
    ROLLOUT_JSONL,
    SSH_EXECUTABLE,
    SSH_TIMEOUT_SECONDS,
)
from src.detours.detour_ai_augment.src.shared import require_nonblank_text
from src.helpers.architecture import FrozenStrictModel

logger = logging.getLogger(__name__)


class _AivmAuditError(RuntimeError):
    pass


class _AivmAuditConfiguration(FrozenStrictModel):
    rollout_guest_path: str | None
    rollout_relative_path: PurePosixPath | None
    appendwatch_report: PurePosixPath
    lima_ssh_config: Path
    identity_file: Path
    known_hosts_file: Path
    ssh_user: str
    ssh_target: str
    host_key_alias: str


def _configuration_file(path: Path | None, setting: str) -> Path:
    if path is None:
        raise _AivmAuditError(Locale.SETTING_REQUIRED_TEMPLATE.format(setting=setting))
    if not path.is_absolute():
        raise _AivmAuditError(Locale.SETTING_ABSOLUTE_TEMPLATE.format(setting=setting))
    if path.is_symlink() or not path.is_file() or not os.access(path, os.R_OK):
        raise _AivmAuditError(Locale.SETTING_READABLE_FILE_TEMPLATE.format(setting=setting))
    return path


def _configuration_guest_path(value: str, setting: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or not path.is_absolute()
        or str(path) != value
        or any(part in FORBIDDEN_NORMALIZED_PATH_PARTS for part in path.parts)
        or HAS_CONTROL_CHARACTER(value)
    ):
        raise _AivmAuditError(Locale.SETTING_GUEST_PATH_TEMPLATE.format(setting=setting))
    return path


def audit_configuration(
    rollout_jsonl: str | None = None, *, report_only: bool = False,
) -> _AivmAuditConfiguration:
    raw_rollout: str | None = None
    relative_path: PurePosixPath | None = None
    if not report_only:
        raw_rollout = ROLLOUT_JSONL if rollout_jsonl is None else rollout_jsonl
        if not raw_rollout.strip():
            raise _AivmAuditError(
                Locale.ROLLOUT_NOT_SET_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
            )
        if raw_rollout != raw_rollout.strip() or HAS_CONTROL_CHARACTER(raw_rollout):
            raise _AivmAuditError(
                Locale.ROLLOUT_WHITESPACE_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
            )

        rollout_path = PurePosixPath(raw_rollout)
        if str(rollout_path) != raw_rollout or any(
            part in FORBIDDEN_NORMALIZED_PATH_PARTS for part in rollout_path.parts
        ):
            raise _AivmAuditError(
                Locale.ROLLOUT_NOT_NORMALIZED_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
            )
        try:
            relative_path = rollout_path.relative_to(CODEX_SESSIONS_ROOT)
        except ValueError as exc:
            raise _AivmAuditError(
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
            raise _AivmAuditError(
                Locale.ROLLOUT_FILENAME_INVALID_TEMPLATE.format(environment_name=ROLLOUT_ENV_NAME)
            )

    require_nonblank_text(
        AIVM_INSTANCE,
        _AivmAuditError(Locale.AIVM_INSTANCE_INVALID),
    )
    require_nonblank_text(
        AIVM_AUDIT_USER,
        _AivmAuditError(Locale.AIVM_AUDIT_USER_INVALID),
    )
    if not AIVM_SSH_PORT.isdecimal() or not MIN_TCP_PORT <= int(AIVM_SSH_PORT) <= MAX_TCP_PORT:
        raise _AivmAuditError(Locale.AIVM_SSH_PORT_INVALID)

    return _AivmAuditConfiguration(
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


def audit_configuration_for_session(session_id: UUID) -> _AivmAuditConfiguration:
    session_id_text = str(session_id)
    placeholder = (
        CODEX_SESSIONS_ROOT
        / f"{ROLLOUT_FILENAME_PREFIX}{session_id_text}{ROLLOUT_FILENAME_SUFFIX}"
    )
    base = audit_configuration(str(placeholder))
    assert base.rollout_relative_path is not None
    options = aivm_connection_options(
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
        raise _AivmAuditError(Locale.ROLLOUT_DISCOVERY_FAILED) from exc
    matches = tuple(line for line in completed.stdout.splitlines() if line)
    if len(matches) != 1:
        raise _AivmAuditError(Locale.ROLLOUT_DISCOVERY_NOT_UNIQUE)
    return audit_configuration(matches[0])


def prove_workflow_inputs_readable() -> None:
    probe_rollout = CODEX_SESSIONS_ROOT / (
        f"{ROLLOUT_FILENAME_PREFIX}startup-readability-probe{ROLLOUT_FILENAME_SUFFIX}"
    )
    configuration = audit_configuration(str(probe_rollout))
    try:
        read_appendwatch_bytes(configuration)
    except _AivmAuditError as exc:
        raise _AivmAuditError(Locale.APPENDWATCH_REPORT_UNREADABLE) from exc
    logger.info(Locale.APPENDWATCH_READABLE_LOG, configuration.appendwatch_report)
    options = aivm_connection_options(
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
        raise _AivmAuditError(Locale.CODEX_SESSIONS_UNREADABLE) from exc
    logger.info(Locale.CODEX_SESSIONS_READABLE_LOG, CODEX_SESSIONS_ROOT)


def aivm_connection_options(
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


def read_appendwatch_bytes(configuration: _AivmAuditConfiguration) -> bytes:
    options = aivm_connection_options(
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
        raise _AivmAuditError(Locale.APPENDWATCH_ARCHIVE_FAILED) from exc
    return completed.stdout
