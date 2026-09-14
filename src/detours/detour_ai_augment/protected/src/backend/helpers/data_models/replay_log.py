from __future__ import annotations

import fcntl
import os
import threading
from pathlib import Path
from types import TracebackType
from typing import Self

from pydantic import PrivateAttr, model_validator

from src.helpers.data_models import FragmentType

from ..locale import Locale
from .ai_augment_registered_resource import AiAugmentRegisteredResource

OPERATOR_CONFIRMATIONS = frozenset({"y", "yes"})
READ_CHUNK_BYTES = 1024 * 1024
READ_ONLY_PERMISSIONS = 0o400
READ_WRITE_PERMISSIONS = 0o600


class ReplayLogRegisteredResource(AiAugmentRegisteredResource):
    """Registered authoritative replay log with one locked append lifetime."""

    _fd: int | None = PrivateAttr(default=None)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    @classmethod
    def from_config_entry(
        cls,
        metadata: object,
        *,
        resource_key: str,
        fragment_type: FragmentType = FragmentType.LINE_NUMBER,
        verify_hash_on_init: bool,
    ) -> Self:
        if fragment_type is not FragmentType.LINE_NUMBER:
            raise ValueError("replay-log fragment type must be line_number")
        return super().from_config_entry(
            metadata,
            resource_key=resource_key,
            fragment_type=fragment_type,
            verify_hash_on_init=verify_hash_on_init,
        )

    @model_validator(mode="after")
    def verify_hash_if_requested(self) -> Self:
        try:
            with self:
                pass
        except (OSError, RuntimeError) as exc:
            raise ValueError(str(exc)) from exc
        return self

    def __enter__(self) -> Self:
        with self._lock:
            if self._fd is not None:
                raise RuntimeError("ReplayLogRegisteredResource is already open")
            path = Path(self)
            if path.is_symlink() or not path.is_file() or not os.access(path, os.R_OK):
                raise OSError(Locale.REPLAY_LOG_UNREADABLE)
            path.chmod(READ_WRITE_PERMISSIONS)
            fd: int | None = None
            try:
                fd = os.open(
                    path,
                    os.O_RDWR
                    | os.O_APPEND
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise RuntimeError(Locale.REPLAY_LOG_ALREADY_LOCKED) from exc
                self._fd = fd
                self._repair_incomplete_tail()
                if self.verify_hash_on_init:
                    self.verify_hash()
                path.chmod(READ_ONLY_PERMISSIONS)
            except BaseException:
                self._fd = None
                if fd is not None:
                    os.close(fd)
                path.chmod(READ_ONLY_PERMISSIONS)
                raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        with self._lock:
            fd = self._fd
            self._fd = None
            if fd is None:
                return
            try:
                os.fsync(fd)
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def append(self, data: bytes, *, expected_offset: int) -> int:
        with self._lock:
            fd = self._require_descriptor()
            end_offset = os.lseek(fd, 0, os.SEEK_END)
            if end_offset != expected_offset:
                raise ValueError(Locale.REPLAY_PROJECTION_CONFLICT)
            written = 0
            while written < len(data):
                count = os.write(fd, data[written:])
                if count <= 0:
                    raise OSError(Locale.AUTHORITATIVE_LOG_APPEND_FAILED)
                written += count
            os.fsync(fd)
            return end_offset + written

    def read(self) -> bytes:
        with self._lock:
            fd = self._require_descriptor()
            return self._read(fd)

    def _require_descriptor(self) -> int:
        if self._fd is None:
            raise RuntimeError(Locale.AUTHORITATIVE_LOG_NOT_OPEN)
        return self._fd

    @staticmethod
    def _read(fd: int) -> bytes:
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while chunk := os.read(fd, READ_CHUNK_BYTES):
            chunks.append(chunk)
        return b"".join(chunks)

    def _repair_incomplete_tail(self) -> None:
        fd = self._require_descriptor()
        try:
            value = self._read(fd)
            if not value or value.endswith(b"\n"):
                return
            truncate_at = value.rfind(b"\n") + 1
            discarded_bytes = len(value) - truncate_at
            reply = input(
                Locale.REPLAY_LOG_TAIL_REPAIR_PROMPT_TEMPLATE.format(
                    path=Path(self),
                    discarded_bytes=discarded_bytes,
                )
            )
            if reply.strip().casefold() not in OPERATOR_CONFIRMATIONS:
                raise ValueError(Locale.REPLAY_LOG_TAIL_REPAIR_DECLINED)
            os.ftruncate(fd, truncate_at)
            os.fsync(fd)
            directory_descriptor = os.open(Path(self).parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except (EOFError, OSError) as exc:
            raise ValueError(Locale.REPLAY_LOG_TAIL_REPAIR_FAILED) from exc
