from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from uuid import uuid7

from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.helpers.architecture import FrozenStrictModel

from .commit_event import CodexRolloutRecord

ARCHIVE_HASH_CHUNK_BYTES = 1024 * 1024
AUDIT_COPY_TIMEOUT_SECONDS = 60
AUDIT_READ_ROLLOUT_COMMAND = "read-rollout"
ROLLOUT_CAS_TEMP_FILENAME_TEMPLATE = ".{nonce}.tmp"
SSH_EXECUTABLE = "ssh"


class AiAugmentCAS(FrozenStrictModel):
    """Immutable Codex rollout snapshots addressed by their SHA-256 digest."""

    path: Path

    def initialize(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)

    def copy_rollout(
        self,
        *,
        rollout_relative_path: PurePosixPath,
        ssh_target: str,
        ssh_options: Sequence[str],
    ) -> CodexRolloutRecord:
        self.initialize()
        temporary = self.path / ROLLOUT_CAS_TEMP_FILENAME_TEMPLATE.format(
            nonce=uuid7().hex
        )
        command = [
            SSH_EXECUTABLE,
            *ssh_options,
            "--",
            ssh_target,
            shlex.join([
                AUDIT_READ_ROLLOUT_COMMAND,
                str(rollout_relative_path),
            ]),
        ]
        try:
            with temporary.open("wb") as output:
                subprocess.run(
                    command,
                    check=True,
                    stdout=output,
                    stderr=subprocess.PIPE,
                    timeout=AUDIT_COPY_TIMEOUT_SECONDS,
                )
            if not temporary.is_file() or temporary.is_symlink():
                raise ValueError(Locale.AUDIT_ROLLOUT_ARCHIVE_INVALID)
            archived = self._record(temporary)
            destination = self._blob_path(archived.sha256)
            for directory in (destination.parent.parent, destination.parent):
                directory.mkdir(exist_ok=True)
                if directory.is_symlink() or not directory.is_dir():
                    raise ValueError(Locale.ROLLOUT_CAS_BLOB_INVALID)
            if destination.exists():
                existing = self._record(destination)
                if (
                    existing.sha256 != archived.sha256
                    or existing.size != archived.size
                ):
                    raise ValueError(Locale.ROLLOUT_CAS_CONFLICT)
                return existing
            return self._publish(temporary, destination)
        except (OSError, subprocess.SubprocessError) as exc:
            raise OSError(Locale.ROLLOUT_COPY_FAILED) from exc
        finally:
            temporary.unlink(missing_ok=True)

    def validated_rollout(
        self,
        reference: CodexRolloutRecord,
    ) -> Path:
        path = self._blob_path(reference.sha256)
        if (
            any(p.is_symlink() for p in (path.parent.parent, path.parent, path))
            or not path.is_file()
        ):
            raise ValueError(Locale.ROLLOUT_CAS_BLOB_INVALID)
        archived = self._record(path)
        if (
            archived.sha256 != reference.sha256
            or archived.size != reference.size
            or archived.line_count != reference.line_count
        ):
            raise ValueError(Locale.ROLLOUT_CAS_BLOB_INVALID)
        return path

    def _blob_path(self, sha256: str) -> Path:
        if re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
            raise ValueError(Locale.ROLLOUT_CAS_BLOB_INVALID)
        return self.path / sha256[:2] / sha256[2:4] / sha256

    @staticmethod
    def _record(path: Path) -> CodexRolloutRecord:
        digest = hashlib.sha256()
        size = 0
        line_count = 0
        final_byte = b""
        with path.open("rb") as stream:
            while chunk := stream.read(ARCHIVE_HASH_CHUNK_BYTES):
                size += len(chunk)
                digest.update(chunk)
                line_count += chunk.count(b"\n")
                final_byte = chunk[-1:]
        if size and final_byte != b"\n":
            line_count += 1
        return CodexRolloutRecord(
            size=size,
            sha256=digest.hexdigest(),
            line_count=line_count,
        )

    @classmethod
    def _publish(
        cls,
        temporary: Path,
        destination: Path,
    ) -> CodexRolloutRecord:
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        for directory in (destination.parent, destination.parent.parent, destination.parents[2]):
            descriptor = os.open(
                directory,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return cls._record(destination)
