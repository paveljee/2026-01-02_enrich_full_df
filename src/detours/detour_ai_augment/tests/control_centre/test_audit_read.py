from __future__ import annotations

import ast
import io
import json
import os
import pwd
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest
from pydantic import BaseModel, ConfigDict, field_validator

from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (
    AiAugmentBackendContext,
)
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


def test_runtime_provisioning_preserves_reverse_sshfs_ownership(
    pytestconfig: pytest.Config,
) -> None:
    runtime_root = (
        pytestconfig.rootpath
        / "src"
        / "detours"
        / "detour_ai_augment"
        / "protected"
        / "src"
        / "agent_runtime"
    )
    provision_path = runtime_root / "provision.sh"
    deploy_path = runtime_root / "deploy.sh"
    provision = provision_path.read_text(encoding="utf-8")
    deploy = deploy_path.read_text(encoding="utf-8")

    assert 'chown root:"$AIVM_AUDIT_USER" "$APPENDWATCH_DIR"' not in provision
    assert 'chmod 0700 "$APPENDWATCH_DIR"' in provision
    assert '--report-mode 0640' in provision
    assert 'chown root:root "$AIVM_AUDIT_HOME/.ssh/authorized_keys"' in provision
    assert 'chmod 0644 "$AIVM_AUDIT_HOME/.ssh/authorized_keys"' in provision
    assert 'stat -c %a $GUEST_CONTROL_DIR_Q)\\\" = 700' in deploy
    assert 'stat -c %G $GUEST_CONTROL_DIR_Q' not in deploy
    assert 'stat -c %G $GUEST_APPENDWATCH_REPORT_Q' not in deploy

    for script in (provision_path, deploy_path):
        subprocess.run(["bash", "-n", str(script)], check=True)


ROOT = Path(__file__).resolve().parents[5]
DETOUR = ROOT / "src/detours/detour_ai_augment"


def test_deployed_guest_imports_unchanged_shared_model_outside_repository(tmp_path: Path) -> None:
    libexec = tmp_path / "libexec"
    helpers = libexec / "src/helpers"
    helpers.mkdir(parents=True)
    shared = ROOT / "src/helpers/architecture.py"
    shutil.copyfile(shared, helpers / "architecture.py")
    audit = DETOUR / "src/control_centre/appendwatch/audit_read.py"
    watcher = DETOUR / "protected/src/control_centre/appendwatch/appendwatch.py"
    shutil.copyfile(audit, libexec / "aivm-audit-read")
    deployed_watcher = tmp_path / "appendwatch.py"
    shutil.copyfile(watcher, deployed_watcher)
    for source in (shared, audit, watcher):
        ast.parse(source.read_text(), feature_version=(3, 12))
    script = '''
import runpy
from pathlib import Path
from src.helpers.architecture import FrozenStrictModel
audit = runpy.run_path("libexec/aivm-audit-read", run_name="deployed_audit")
assert issubclass(audit["AuditReadConfiguration"], FrozenStrictModel)
model = audit["AuditReadConfiguration"](
    runtime_user="ai", audit_user="audit", sessions_root=Path("/sessions"),
    appendwatch_report=Path("/report"),
)
assert model.runtime_user == "ai"
watch = runpy.run_path("appendwatch.py", run_name="deployed_watch")
record = watch["Record"](dev=1, ino=2, size=0, mtime_ns=0, ctime_ns=0, digest=b"a")
record.size = 2
copied = record.model_copy(update={"exists": False})
assert record.exists and not copied.exists and copied.size == 2
print("DEPLOYED_MODELS_OK")
'''
    environment = dict(os.environ, PYTHONPATH=str(libexec), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=environment,
                            capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    assert "DEPLOYED_MODELS_OK" in result.stdout
    assert (helpers / "architecture.py").read_bytes() == shared.read_bytes()


def isolated_class(path: Path, name: str, namespace: dict[str, Any]) -> type[Any]:
    """Do not import/collect the operator or paused BDD suite to test a DTO."""
    node = next(node for node in ast.parse(path.read_text()).body
                if isinstance(node, ast.ClassDef) and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return cast(type[Any], namespace[name])


def test_operator_output_buffer_identity_and_paused_bdd_mutability() -> None:
    namespace: dict[str, Any] = {
        "__name__": __name__, "BaseModel": BaseModel, "ConfigDict": ConfigDict,
        "field_validator": field_validator, "threading": threading, "subprocess": subprocess,
        "Any": Any, "AiAugmentBackendContext": AiAugmentBackendContext,
    }
    dashboard = isolated_class(DETOUR / "protected/tests/operator/test_operator_e2e.py",
                               "DashboardProcess", namespace)
    output: list[str] = []
    thread = threading.Thread()
    process = Mock(spec=subprocess.Popen)
    handle = dashboard(process=process, output=output, output_thread=thread)
    output.append("ready")
    assert handle.output is output and handle.output == ["ready"]
    assert handle.process is process and handle.output_thread is thread
    state = isolated_class(DETOUR / "protected/tests/bdd/test_detour_ai_augment_bdd.py",
                           "LifecycleState", namespace)()
    state.captured_contour_passed = True
    assert state.captured_contour_passed
