from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Literal, Self

import duckdb
from pydantic import BaseModel, ConfigDict, PrivateAttr

from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_detour_db import (  # noqa: E501
    AiAugmentDetourDB,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.replay_log import (  # noqa: E501
    ReplayLogRegisteredResource,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    TEXT_ENCODING,
)
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

from .ai_augment_cas import AiAugmentCAS
from .query_response import AgentRuntimeAttemptRecord

StoreMode = Literal["writable", "read_only"]
AuthoritativeRecordProjector = Callable[..., AgentRuntimeAttemptRecord | None]


class AiAugmentBackendStore(BaseModel):
    """Authoritative replay log and its managed DuckDB projection."""

    model_config = ConfigDict(frozen=True)

    replay_log: ReplayLogRegisteredResource
    detour_db: AiAugmentDetourDB
    rollout_cas: AiAugmentCAS
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _mode: StoreMode | None = PrivateAttr(default=None)
    _project_record: AuthoritativeRecordProjector | None = PrivateAttr(default=None)
    _next_line_number: int = PrivateAttr(default=1)
    _log_offset: int = PrivateAttr(default=0)

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._mode is None:
            raise RuntimeError("AiAugmentBackendStore must be used inside a 'with' block")
        return self.detour_db.connection

    @contextmanager
    def writable(
        self,
        project_record: AuthoritativeRecordProjector,
    ) -> Iterator[Self]:
        self._require_closed()
        with self.replay_log:
            with self.detour_db.writable():
                self._mode = "writable"
                self._project_record = project_record
                try:
                    with self.threading_lock():
                        self._synchronize_authoritative_projection_locked()
                    yield self
                finally:
                    self._project_record = None
                    self._mode = None

    @contextmanager
    def read_only(self) -> Iterator[Self]:
        self._require_closed()
        with self.replay_log:
            with self.detour_db.read_only():
                self._mode = "read_only"
                try:
                    self._assert_projection_current()
                    yield self
                finally:
                    self._mode = None

    @contextmanager
    def threading_lock(self) -> Iterator[Self]:
        self._require_writable()
        with self._lock:
            yield self

    def append_authoritative_record(
        self,
        record: HttpRequestLogRecord,
    ) -> AgentRuntimeAttemptRecord | None:
        from src.detours.detour_ai_augment.src.backend import api

        validated = api._validated_readme_record(record)
        line = (validated.model_dump_json(ensure_ascii=True) + "\n").encode(
            TEXT_ENCODING
        )
        line_sha256 = hashlib.sha256(line).hexdigest()
        with self.threading_lock():
            self._synchronize_authoritative_projection_locked()
            byte_offset = self.replay_log.append(
                line,
                expected_offset=self._log_offset,
            )
            line_number = self._next_line_number
            self._log_offset = byte_offset
            self._next_line_number += 1
            return self._require_project_record()(
                conn=self.connection,
                record=validated,
                line_number=line_number,
                byte_offset=self._log_offset,
                line_sha256=line_sha256,
                materialize_files=True,
            )

    def authoritative_records(
        self,
    ) -> tuple[tuple[HttpRequestLogRecord, int, str], ...]:
        from src.detours.detour_ai_augment.src.backend import api

        self._require_open()
        if self._mode == "read_only":
            return api._authoritative_log_records(self.replay_log.read())
        with self.threading_lock():
            return api._authoritative_log_records(self.replay_log.read())

    def _synchronize_authoritative_projection_locked(self) -> None:
        from src.detours.detour_ai_augment.src.backend import api

        try:
            records = api._authoritative_log_records(self.replay_log.read())
            self.rollout_cas.initialize()
            conn = self.connection
            api._initialize_readme_authoritative_schema(conn)
            checkpoint = api._projection_checkpoint(conn)
            projected_count_row = conn.execute(
                f"SELECT count(*) FROM {api.AUTHORITATIVE_RECORDS_TABLE}"
            ).fetchone()
            projected_count = (
                0 if projected_count_row is None else int(projected_count_row[0])
            )
            if checkpoint is None:
                if projected_count:
                    raise api._PushConfigurationError(
                        Locale.REPLAY_PROJECTION_CONFLICT
                    )
                projected_line_count = 0
            else:
                projected_line_count, byte_offset, line_sha256 = checkpoint
                if (
                    projected_line_count != projected_count
                    or projected_line_count > len(records)
                ):
                    raise api._PushConfigurationError(
                        Locale.REPLAY_PROJECTION_CONFLICT
                    )
                if projected_line_count:
                    _, expected_offset, expected_hash = records[
                        projected_line_count - 1
                    ]
                    if byte_offset != expected_offset or line_sha256 != expected_hash:
                        raise api._PushConfigurationError(
                            Locale.REPLAY_PROJECTION_CONFLICT
                        )
            for line_number, (record, byte_offset, line_sha256) in enumerate(
                records[projected_line_count:],
                start=projected_line_count + api.AUTHORITATIVE_FIRST_LINE,
            ):
                self._require_project_record()(
                    conn=conn,
                    record=record,
                    line_number=line_number,
                    byte_offset=byte_offset,
                    line_sha256=line_sha256,
                    materialize_files=False,
                )
            self._next_line_number = len(records) + api.AUTHORITATIVE_FIRST_LINE
            self._log_offset = (
                records[-1][1] if records else api.AUTHORITATIVE_EMPTY_OFFSET
            )
        except Exception as exc:
            raise api._PushConfigurationError(Locale.REPLAY_PROJECTION_FAILED) from exc

    def _assert_projection_current(self) -> None:
        from src.detours.detour_ai_augment.src.backend import api

        try:
            records = api._authoritative_log_records(self.replay_log.read())
            conn = self.connection
            checkpoint = api._projection_checkpoint(conn)
            projected_count_row = conn.execute(
                f"SELECT count(*) FROM {api.AUTHORITATIVE_RECORDS_TABLE}"
            ).fetchone()
            projected_count = (
                0 if projected_count_row is None else int(projected_count_row[0])
            )
            if checkpoint is None:
                if projected_count or records:
                    raise api._PushConfigurationError(
                        Locale.REPLAY_PROJECTION_CONFLICT
                    )
            else:
                projected_line_count, byte_offset, line_sha256 = checkpoint
                if (
                    projected_line_count != projected_count
                    or projected_line_count != len(records)
                ):
                    raise api._PushConfigurationError(
                        Locale.REPLAY_PROJECTION_CONFLICT
                    )
                if projected_line_count:
                    _, expected_offset, expected_hash = records[-1]
                    if byte_offset != expected_offset or line_sha256 != expected_hash:
                        raise api._PushConfigurationError(
                            Locale.REPLAY_PROJECTION_CONFLICT
                        )
            self._next_line_number = len(records) + api.AUTHORITATIVE_FIRST_LINE
            self._log_offset = (
                records[-1][1] if records else api.AUTHORITATIVE_EMPTY_OFFSET
            )
        except Exception as exc:
            raise api._PushConfigurationError(Locale.REPLAY_PROJECTION_FAILED) from exc

    def _require_closed(self) -> None:
        if self._mode is not None:
            raise RuntimeError("AiAugmentBackendStore is already open")

    def _require_writable(self) -> None:
        if self._mode != "writable":
            raise RuntimeError(
                "AiAugmentBackendStore must be used inside a writable 'with' block"
            )

    def _require_open(self) -> None:
        if self._mode is None:
            raise RuntimeError("AiAugmentBackendStore must be used inside a 'with' block")

    def _require_project_record(self) -> AuthoritativeRecordProjector:
        if self._project_record is None:
            raise RuntimeError("AiAugmentBackendStore projector is unavailable")
        return self._project_record
