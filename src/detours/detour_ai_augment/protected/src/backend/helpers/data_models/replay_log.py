from __future__ import annotations

import fcntl
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Self

from pydantic import PrivateAttr

from src.helpers.data_models import FragmentType

from ..locale import Locale
from .ai_augment_registered_resource import AiAugmentRegisteredResource

READ_CHUNK_BYTES = 1024 * 1024
READ_ONLY_PERMISSIONS = 0o400
READ_WRITE_PERMISSIONS = 0o600


class ReplayLogRegisteredResource(AiAugmentRegisteredResource):
    """Registered metadata; private I/O is used exclusively by Backend Store."""

    _fd: int | None = PrivateAttr(default=None)
    _append_allowed: bool = PrivateAttr(default=False)
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

    @contextmanager
    def _locked(self, *, append_allowed: bool) -> Iterator[None]:
        with self._lock:
            if self._fd is not None:
                raise RuntimeError("ReplayLogRegisteredResource is already open")
            fd = os.open(
                Path(self), os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                lock = fcntl.LOCK_EX if append_allowed else fcntl.LOCK_SH
                fcntl.flock(fd, lock | fcntl.LOCK_NB)
                os.fchmod(fd, READ_ONLY_PERMISSIONS)
                self._fd = fd
                self._append_allowed = append_allowed
            except BaseException:
                os.close(fd)
                raise
        try:
            yield
        finally:
            with self._lock:
                self._fd = None
                self._append_allowed = False
                # Closing also releases flock; the retained descriptor was never writable.
                os.close(fd)

    @contextmanager
    def _append_descriptor(self) -> Iterator[int]:
        """The same zero-creation append window for preflight and actual writes."""
        with self._lock:
            if not self._append_allowed:
                raise RuntimeError("Replay log is read-only")
            locked_fd = self._require_descriptor()
            locked = os.fstat(locked_fd)
            writer: int | None = None
            try:
                os.fchmod(locked_fd, READ_WRITE_PERMISSIONS)
                writer = os.open(
                    Path(self), os.O_WRONLY | os.O_APPEND | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                opened = os.fstat(writer)
                if (opened.st_dev, opened.st_ino) != (locked.st_dev, locked.st_ino):
                    raise ValueError(Locale.REPLAY_PROJECTION_CONFLICT)
                yield writer
            finally:
                try:
                    if writer is not None:
                        os.close(writer)
                finally:
                    os.fchmod(locked_fd, READ_ONLY_PERMISSIONS)

    def _preflight_append(self) -> None:
        with self._append_descriptor():
            pass

    def _append(self, data: bytes, *, expected_offset: int) -> int:
        with self._append_descriptor() as writer:
            if os.fstat(writer).st_size != expected_offset:
                raise ValueError(Locale.REPLAY_PROJECTION_CONFLICT)
            written = 0
            while written < len(data):
                count = os.write(writer, data[written:])
                if count <= 0:
                    raise OSError(Locale.AUTHORITATIVE_LOG_APPEND_FAILED)
                written += count
            os.fsync(writer)
        return expected_offset + len(data)

    def _lines(self, *, offset: int = 0) -> Iterator[bytes]:
        """Stream exact durable LF-delimited bytes, retaining any invalid final tail."""
        pending = b""
        while True:
            with self._lock:
                chunk = os.pread(self._require_descriptor(), READ_CHUNK_BYTES, offset)
            if not chunk:
                if pending:
                    yield pending
                return
            offset += len(chunk)
            parts = (pending + chunk).split(b"\n")
            pending = parts.pop()
            for part in parts:
                yield part + b"\n"

    def _read(self, *, offset: int = 0) -> bytes:
        with self._lock:
            fd = self._require_descriptor()
            chunks: list[bytes] = []
            while chunk := os.pread(fd, READ_CHUNK_BYTES, offset):
                chunks.append(chunk)
                offset += len(chunk)
            return b"".join(chunks)

    def _size(self) -> int:
        with self._lock:
            return os.fstat(self._require_descriptor()).st_size

    def _require_descriptor(self) -> int:
        if self._fd is None:
            raise RuntimeError(Locale.AUTHORITATIVE_LOG_NOT_OPEN)
        return self._fd
