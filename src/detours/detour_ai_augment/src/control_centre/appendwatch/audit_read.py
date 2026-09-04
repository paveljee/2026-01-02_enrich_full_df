#!/usr/bin/env python3
"""Serve the narrow read-only Backend protocol for an AIVM audit principal."""

from __future__ import annotations

import json
import os
import pwd
import shlex
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Final
from uuid import UUID

CONFIGURATION_OPTION: Final = "--configuration"
READ_BUFFER_BYTES: Final = 1024 * 1024
ROLLOUT_FILENAME_PREFIX: Final = "rollout-"
ROLLOUT_FILENAME_SUFFIX: Final = ".jsonl"
PROBE_COMMAND: Final = "probe"
FIND_ROLLOUT_COMMAND: Final = "find-rollout"
READ_ROLLOUT_COMMAND: Final = "read-rollout"
READ_APPENDWATCH_REPORT_COMMAND: Final = "read-appendwatch-report"
ARGUMENT_COMMANDS: Final = frozenset(
    {FIND_ROLLOUT_COMMAND, READ_ROLLOUT_COMMAND, READ_APPENDWATCH_REPORT_COMMAND}
)
NO_ARGUMENT_COMMANDS: Final = frozenset({PROBE_COMMAND})
FORBIDDEN_PATH_PARTS: Final = frozenset({"", ".", ".."})


class AuditReadError(RuntimeError):
    """The requested audit operation is invalid or unavailable."""


@dataclass(frozen=True, slots=True)
class AuditReadConfiguration:
    runtime_user: str
    audit_user: str
    sessions_root: Path
    appendwatch_report: Path


def _absolute_path(value: object, *, field: str) -> Path:
    if not isinstance(value, str):
        raise AuditReadError(f"{field} must be a string")
    path = PurePosixPath(value)
    if (
        not path.is_absolute()
        or str(path) != value
        or any(part in FORBIDDEN_PATH_PARTS for part in path.parts)
    ):
        raise AuditReadError(f"{field} must be a normalized absolute path")
    return Path(value)


def load_configuration(path: Path) -> AuditReadConfiguration:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o022:
        raise AuditReadError("audit configuration is not a protected regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {
        "runtime_user",
        "audit_user",
        "sessions_root",
        "appendwatch_report",
    }:
        raise AuditReadError("audit configuration has an invalid shape")
    runtime_user = value["runtime_user"]
    if not isinstance(runtime_user, str) or not runtime_user:
        raise AuditReadError("runtime_user must be a nonempty string")
    audit_user = value["audit_user"]
    if not isinstance(audit_user, str) or not audit_user:
        raise AuditReadError("audit_user must be a nonempty string")
    sessions_root = _absolute_path(value["sessions_root"], field="sessions_root")
    appendwatch_report = _absolute_path(
        value["appendwatch_report"],
        field="appendwatch_report",
    )
    return AuditReadConfiguration(
        runtime_user=runtime_user,
        audit_user=audit_user,
        sessions_root=sessions_root,
        appendwatch_report=appendwatch_report,
    )


def parse_command(value: str) -> tuple[str, str | None]:
    try:
        parts = shlex.split(value)
    except ValueError as exc:
        raise AuditReadError("audit command is malformed") from exc
    if len(parts) == 1 and parts[0] in NO_ARGUMENT_COMMANDS:
        return parts[0], None
    if len(parts) == 2 and parts[0] in ARGUMENT_COMMANDS:
        return parts[0], parts[1]
    raise AuditReadError("audit command is not permitted")


def _canonical_session_id(value: str) -> str:
    try:
        session_id = UUID(value)
    except ValueError as exc:
        raise AuditReadError("session ID is invalid") from exc
    if str(session_id) != value:
        raise AuditReadError("session ID is not canonical")
    return value


def _rollout_path(sessions_root: Path, value: str) -> Path:
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or str(relative) != value
        or any(part in FORBIDDEN_PATH_PARTS for part in relative.parts)
        or not relative.name.startswith(ROLLOUT_FILENAME_PREFIX)
        or not relative.name.endswith(ROLLOUT_FILENAME_SUFFIX)
    ):
        raise AuditReadError("rollout path is invalid")
    return sessions_root.joinpath(*relative.parts)


def _drop_to_user(user: str) -> None:
    account = pwd.getpwnam(user)
    if os.geteuid() == account.pw_uid:
        return
    if os.geteuid() != 0:
        raise AuditReadError("audit helper cannot assume the runtime identity")
    os.initgroups(account.pw_name, account.pw_gid)
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)


def _open_regular(path: Path) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise AuditReadError("requested audit artifact is not a regular file")
    return descriptor


def _copy_descriptor(descriptor: int, output: BinaryIO) -> None:
    while chunk := os.read(descriptor, READ_BUFFER_BYTES):
        output.write(chunk)
    output.flush()


def _probe(configuration: AuditReadConfiguration) -> None:
    child_pid = os.fork()
    if child_pid == 0:
        try:
            _drop_to_user(configuration.runtime_user)
            with os.scandir(configuration.sessions_root):
                pass
        except (KeyError, OSError, AuditReadError):
            os._exit(1)
        os._exit(0)
    _pid, child_status = os.waitpid(child_pid, 0)
    if os.waitstatus_to_exitcode(child_status) != 0:
        raise AuditReadError("Codex sessions directory is not readable")
    _drop_to_user(configuration.audit_user)
    descriptor = _open_regular(configuration.appendwatch_report)
    os.close(descriptor)


def _find_rollout(
    configuration: AuditReadConfiguration,
    session_id: str,
    output: BinaryIO,
) -> None:
    canonical_session_id = _canonical_session_id(session_id)
    _drop_to_user(configuration.runtime_user)
    suffix = f"{canonical_session_id}{ROLLOUT_FILENAME_SUFFIX}"
    matches: list[str] = []

    def fail(error: OSError) -> None:
        raise error

    for directory, _directories, filenames in os.walk(
        configuration.sessions_root,
        followlinks=False,
        onerror=fail,
    ):
        for filename in filenames:
            if not filename.startswith(ROLLOUT_FILENAME_PREFIX) or not filename.endswith(
                suffix
            ):
                continue
            candidate = Path(directory, filename)
            try:
                metadata = candidate.lstat()
            except OSError:
                continue
            if stat.S_ISREG(metadata.st_mode):
                matches.append(str(candidate))
    for match in sorted(matches):
        output.write(f"{match}\n".encode())
    output.flush()


def _read_rollout(
    configuration: AuditReadConfiguration,
    relative_path: str,
    output: BinaryIO,
) -> None:
    path = _rollout_path(configuration.sessions_root, relative_path)
    _drop_to_user(configuration.runtime_user)
    descriptor = _open_regular(path)
    try:
        _copy_descriptor(descriptor, output)
    finally:
        os.close(descriptor)


def _read_appendwatch_report(
    configuration: AuditReadConfiguration,
    report_path: str,
    output: BinaryIO,
) -> None:
    requested_report = _absolute_path(report_path, field="appendwatch_report")
    if requested_report != configuration.appendwatch_report:
        raise AuditReadError("appendwatch report path is not permitted")
    _drop_to_user(configuration.audit_user)
    descriptor = _open_regular(requested_report)
    try:
        _copy_descriptor(descriptor, output)
    finally:
        os.close(descriptor)


def execute(
    configuration: AuditReadConfiguration,
    command_text: str,
    *,
    output: BinaryIO,
) -> None:
    command, argument = parse_command(command_text)
    if command == PROBE_COMMAND:
        _probe(configuration)
    elif command == FIND_ROLLOUT_COMMAND:
        assert argument is not None
        _find_rollout(configuration, argument, output)
    elif command == READ_ROLLOUT_COMMAND:
        assert argument is not None
        _read_rollout(configuration, argument, output)
    elif command == READ_APPENDWATCH_REPORT_COMMAND:
        assert argument is not None
        _read_appendwatch_report(configuration, argument, output)
    else:  # pragma: no cover - parse_command closes this branch
        raise AuditReadError("audit command is not permitted")


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[1] != CONFIGURATION_OPTION:
        raise SystemExit(
            "usage: aivm-audit-read --configuration PATH '<command>'"
        )
    if os.geteuid() != 0:
        raise SystemExit("aivm-audit-read must run as root")
    try:
        execute(
            load_configuration(_absolute_path(sys.argv[2], field="configuration")),
            sys.argv[3],
            output=sys.stdout.buffer,
        )
    except (AuditReadError, KeyError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"aivm-audit-read: {exc}") from exc


if __name__ == "__main__":
    main()
