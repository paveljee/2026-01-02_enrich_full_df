from __future__ import annotations

import io
import json
import os
import pwd
from pathlib import Path

import pytest

from src.detours.detour_ai_augment.src.control_centre.appendwatch import audit_read

SESSION_ID = "019fa457-aac5-7652-8669-9d571206e7cb"
ROLLOUT_RELATIVE_PATH = Path(
    "2026/07/27/"
    "rollout-2026-07-27T12-10-36-019fa457-aac5-7652-8669-9d571206e7cb.jsonl"
)


def configuration(tmp_path: Path) -> audit_read.AuditReadConfiguration:
    account = pwd.getpwuid(os.geteuid()).pw_name
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    report = tmp_path / "appendwatch-tree.txt"
    report.write_bytes(b".\n")
    return audit_read.AuditReadConfiguration(
        runtime_user=account,
        audit_user=account,
        sessions_root=sessions_root,
        appendwatch_report=report,
    )


def test_audit_protocol_finds_and_reads_only_configured_artifacts(
    tmp_path: Path,
) -> None:
    configured = configuration(tmp_path)
    rollout = configured.sessions_root / ROLLOUT_RELATIVE_PATH
    rollout.parent.mkdir(parents=True)
    rollout.write_bytes(b'{"type":"session_meta"}\n')

    found = io.BytesIO()
    audit_read.execute(
        configured,
        f"{audit_read.FIND_ROLLOUT_COMMAND} {SESSION_ID}",
        output=found,
    )
    assert found.getvalue() == f"{rollout}\n".encode()

    rollout_output = io.BytesIO()
    audit_read.execute(
        configured,
        f"{audit_read.READ_ROLLOUT_COMMAND} {ROLLOUT_RELATIVE_PATH.as_posix()}",
        output=rollout_output,
    )
    assert rollout_output.getvalue() == rollout.read_bytes()

    report_output = io.BytesIO()
    audit_read.execute(
        configured,
        f"{audit_read.READ_APPENDWATCH_REPORT_COMMAND} "
        f"{configured.appendwatch_report}",
        output=report_output,
    )
    assert report_output.getvalue() == b".\n"

    audit_read.execute(configured, audit_read.PROBE_COMMAND, output=io.BytesIO())


@pytest.mark.parametrize(
    "command",
    (
        "",
        "id -un",
        audit_read.READ_APPENDWATCH_REPORT_COMMAND,
        f"{audit_read.READ_APPENDWATCH_REPORT_COMMAND} /tmp/not-configured",
        f"{audit_read.READ_ROLLOUT_COMMAND} ../rollout-{SESSION_ID}.jsonl",
        f"{audit_read.FIND_ROLLOUT_COMMAND} {SESSION_ID.upper()}",
    ),
)
def test_audit_protocol_rejects_unpermitted_requests(
    tmp_path: Path,
    command: str,
) -> None:
    with pytest.raises((audit_read.AuditReadError, OSError)):
        audit_read.execute(configuration(tmp_path), command, output=io.BytesIO())


def test_audit_protocol_refuses_rollout_symlinks(tmp_path: Path) -> None:
    configured = configuration(tmp_path)
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"secret\n")
    rollout = configured.sessions_root / ROLLOUT_RELATIVE_PATH
    rollout.parent.mkdir(parents=True)
    rollout.symlink_to(outside)

    with pytest.raises(OSError):
        audit_read.execute(
            configured,
            f"{audit_read.READ_ROLLOUT_COMMAND} {ROLLOUT_RELATIVE_PATH.as_posix()}",
            output=io.BytesIO(),
        )


def test_audit_configuration_must_be_protected_and_has_exact_shape(
    tmp_path: Path,
) -> None:
    configured = configuration(tmp_path)
    path = tmp_path / "audit-read.json"
    path.write_text(
        json.dumps({
            "runtime_user": configured.runtime_user,
            "audit_user": configured.audit_user,
            "sessions_root": str(configured.sessions_root),
            "appendwatch_report": str(configured.appendwatch_report),
        }),
        encoding="utf-8",
    )
    path.chmod(0o600)

    assert audit_read.load_configuration(path) == configured

    path.chmod(0o620)
    with pytest.raises(audit_read.AuditReadError):
        audit_read.load_configuration(path)
