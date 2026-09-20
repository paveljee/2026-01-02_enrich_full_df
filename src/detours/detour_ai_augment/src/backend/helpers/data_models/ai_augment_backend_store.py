from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any, Literal, Self, overload
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import duckdb
import requests
from pydantic import Field, PrivateAttr, ValidationError

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_detour_db import (  # noqa: E501
    AiAugmentDetourDB,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.replay_log import (  # noqa: E501
    ReplayLogRegisteredResource,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_GET_METHOD,
    HTTP_POST_METHOD,
    NANOSECONDS_PER_MICROSECOND,
    PULL_PATH,
    PUSH_PATH,
    TEXT_ENCODING,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.validation_event import (
    VALIDATE_PATH,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
    redact_http_request_log_query,
)
from src.helpers.duckdb_utils import materialize_innerdicts_from_rows_table
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

from .ai_augment_cas import AiAugmentCAS
from .ai_augment_context import AiAugmentBackendContext
from .commit_event import COMMIT_PATH, BackendCommitRecord
from .committed_innerdict import CommittedInnerDict
from .model_http_interceptor import (
    ModelHttpInterceptor,
    ModelHttpRequired,
    record_key,
    request_body,
    request_key,
)
from .query_response import AgentRuntimeAttemptRecord, QueryResponse
from .request_response_records import (
    PullResponseRecord,
    PushRequestRecord,
    PushResponseRecord,
    QueryRequestRecord,
    QueryResponseRecord,
    RunOutcomeRequestRecord,
)
from .response_record_promise import (
    BackendStoreAcknowledgment,
    BackendStoreException,
    ResponseRecordPromise,
)
from .run_outcome_record import RunOutcomeResponseRecord
from .validation_event import BackendValidationRecord, ValidationRequestBody

StoreMode = Literal["writable", "read_only"]
logger = logging.getLogger(__name__)
# Literally empty file, like `printf "" | sha256sum`
EMPTY_LOG_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class _ReplayAnchor(FrozenStrictModel):
    """Accepted configured hash at an exact durable prefix boundary."""

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordinal: int = Field(ge=0)
    byte_offset: int = Field(ge=0)


class ExecuteResult:
    """Detached rows with DuckDB-style consuming fetch methods."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = iter(rows)

    def fetchone(self) -> tuple[Any, ...] | None:
        return next(self._rows, None)

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._rows)


@implements[BackendComponent.FullStoreProperty]()
class AiAugmentBackendStore(FrozenStrictModel):
    """Authoritative replay log and its managed DuckDB projection."""

    rollout_cas: AiAugmentCAS
    _replay_log: ReplayLogRegisteredResource = PrivateAttr()
    _detour_db: AiAugmentDetourDB = PrivateAttr()
    _lock: threading.RLock = PrivateAttr(default_factory=threading.RLock)
    _mode: StoreMode | None = PrivateAttr(default=None)
    _runtime: AiAugmentBackendContext | None = PrivateAttr(default=None)
    _next_line_number: int = PrivateAttr(default=1)
    _log_offset: int = PrivateAttr(default=0)
    _transaction_active: bool = PrivateAttr(default=False)
    _reading_active: bool = PrivateAttr(default=False)
    _rebuilding: bool = PrivateAttr(default=False)
    _failure: BaseException | None = PrivateAttr(default=None)
    _loop: asyncio.AbstractEventLoop | None = PrivateAttr(default=None)
    _append_offset: int = PrivateAttr(default=0)
    _append_ordinal: int = PrivateAttr(default=0)
    _group_records: list[tuple[int, bytes]] = PrivateAttr(default_factory=list)
    _group_scope: AbstractContextManager[AiAugmentDetourDB] | None = PrivateAttr(default=None)
    _group_push_id: UUID | None = PrivateAttr(default=None)
    _group_commit_id: UUID | None = PrivateAttr(default=None)

    _current_pull_record: HttpRequestLogRecord | None = PrivateAttr(default=None)
    _current_push_record: HttpRequestLogRecord | None = PrivateAttr(default=None)
    _current_commit_record: BackendCommitRecord | None = PrivateAttr(default=None)
    _current_validation_record: BackendValidationRecord | None = PrivateAttr(default=None)
    _initial_validation_record: BackendValidationRecord | None = PrivateAttr(default=None)
    _group_previous_records: tuple[
        HttpRequestLogRecord | None, HttpRequestLogRecord | None,
        BackendCommitRecord | None, BackendValidationRecord | None,
    ] | None = PrivateAttr(default=None)

    @property
    def current_pull_record(self) -> HttpRequestLogRecord | None:
        return self._current_pull_record

    @property
    def current_push_record(self) -> HttpRequestLogRecord | None:
        return self._current_push_record

    @property
    def current_commit_record(self) -> BackendCommitRecord | None:
        return self._current_commit_record

    @property
    def current_validation_record(self) -> BackendValidationRecord | None:
        return self._current_validation_record

    @property
    def initial_validation_record(self) -> BackendValidationRecord | None:
        return self._initial_validation_record

    def _reset_current_records(self) -> None:
        self._current_pull_record = None
        self._current_push_record = None
        self._current_commit_record = None
        self._current_validation_record = None
        self._initial_validation_record = None

    def _remember_http_record(self, record: HttpRequestLogRecord) -> None:
        if (record.method, record.path) == (HTTP_GET_METHOD, PULL_PATH):
            self._current_pull_record = record
        elif (record.method, record.path) == (HTTP_POST_METHOD, PUSH_PATH):
            self._current_push_record = record

    @classmethod
    def _from_resources(
        cls,
        *,
        replay_log: ReplayLogRegisteredResource,
        detour_db: AiAugmentDetourDB,
        rollout_cas: AiAugmentCAS,
    ) -> Self:
        store = cls(rollout_cas=rollout_cas)
        store._replay_log = replay_log
        store._detour_db = detour_db
        return store

    @property
    def _detour_db_path(self) -> Path:
        return self._detour_db.path

    @contextmanager
    def _opened(
        self,
        mode: StoreMode,
        runtime: AiAugmentBackendContext | None = None,
    ) -> Iterator[Self]:
        self._require_closed()
        self._raise_if_failed()
        with self._replay_log._locked(append_allowed=mode == "writable"):
            self._mode = mode
            self._runtime = runtime
            try:
                with self._lock:
                    verified_anchor = self._verify_log_projection()
                    if mode == "writable":
                        self._replay_log._preflight_append()
                        if verified_anchor is not None:
                            with self._transaction():
                                self._write_anchor(verified_anchor)
                            logger.info("Accepted new replay hash %s at line %d byte %d",
                                        verified_anchor.sha256, verified_anchor.ordinal,
                                        verified_anchor.byte_offset)
                yield self
                self._raise_if_failed()
                if self._group_scope is not None:
                    raise RuntimeError(Locale.STORE_PUSH_GROUP_INCOMPLETE)
            finally:
                with self._lock:
                    if self._group_scope is not None:
                        self._abort_group()
                self._runtime = None
                self._mode = None

    @contextmanager
    def _writable(self, runtime: AiAugmentBackendContext) -> Iterator[Self]:
        """Continue a known-clean DB; reconstruction is explicit, never implicit."""
        with self._opened("writable", runtime) as store:
            yield store

    @contextmanager
    def _read_only(self, runtime: AiAugmentBackendContext) -> Iterator[Self]:
        with self._opened("read_only", runtime) as store:
            yield store

    def _rebuild_from_log(
        self,
        runtime: AiAugmentBackendContext,
        *,
        reset_confirmed: bool,
        confirm_replay: Callable[[], bool] = lambda: False,
    ) -> None:
        from src.detours.detour_ai_augment.src.backend import api

        if not reset_confirmed:
            raise ValueError("Database reset confirmation required for --new.")
        with self._lock:
            self._require_closed()
            with self._replay_log._locked(append_allowed=False):
                # Only explicit --new can reconstruct; refusal precedes any DB deletion.
                self._replay_log.verify_hash()
                size = self._replay_log._size()
                if size and not confirm_replay():
                    raise ValueError("Nonempty replay log requires replay confirmation")
                if not size and self._replay_log.hash != EMPTY_LOG_SHA256:
                    raise ValueError("An empty replay log requires SHA256(empty)")
                path = self._detour_db.path
                protected_paths = (runtime.pipeline_config.db_file, Path(self._replay_log))
                if path.is_symlink() or any(
                    path.resolve() == protected.resolve()
                    or (path.exists() and protected.exists() and path.samefile(protected))
                    for protected in protected_paths
                ):
                    raise ValueError("Detour database must be separate from source and replay log")
                self._failure = None
                self._mode = "read_only"
                self._runtime = runtime
                self._rebuilding = True
                try:
                    path.unlink(missing_ok=True)
                    path.with_name(path.name + ".wal").unlink(missing_ok=True)
                    with self._transaction():
                        self._initialize_http_record_schema()
                        self._write_anchor(_ReplayAnchor(
                            sha256=EMPTY_LOG_SHA256, ordinal=0, byte_offset=0,
                        ))
                    total = sum(1 for _ in self._replay_log._lines())
                    logger.info("Replaying %d lines (%d bytes) into new detour DB", total, size)
                    self._next_line_number = 1
                    self._log_offset = 0
                    self._append_offset = 0
                    self._append_ordinal = 0
                    for ordinal, line in enumerate(self._replay_log._lines(), start=1):
                        logger.info("Replaying line %d/%d", ordinal, total)
                        try:
                            record = api._authoritative_log_records(line)[0][0]
                            self._append_ordinal = ordinal
                            self._append_offset += len(line)
                            self._apply_durable_record(record, ordinal=ordinal, raw_line=line)
                        except Exception:
                            origin = self._group_records[0][0] if self._group_records else ordinal
                            logger.exception(
                                Locale.REPLAY_GROUP_FAILED_LOG, ordinal, origin
                            )
                            raise
                    if self._group_records:
                        raise ValueError(
                            Locale.REPLAY_PUSH_GROUP_INCOMPLETE_TEMPLATE.format(line_number=self._group_records[0][0])
                        )
                    with self._transaction():
                        self._write_anchor(_ReplayAnchor(
                            sha256=self._replay_log.hash, ordinal=total,
                            byte_offset=self._log_offset,
                        ))
                    logger.info("Replay complete; accepted hash %s at line %d, byte %d",
                                self._replay_log.hash, total, self._log_offset)
                except BaseException as exc:
                    self._failure = exc
                    raise
                finally:
                    if self._group_scope is not None:
                        self._abort_group()
                    self._rebuilding = False
                    self._runtime = None
                    self._mode = None

    @contextmanager
    def _threading_lock(self) -> Iterator[Self]:
        self._require_writable()
        with self._lock:
            self._raise_if_failed()
            yield self

    def _append_request(
        self, record: HttpRequestLogRecord
    ) -> tuple[HttpRequestLogRecord, int, bytes]:
        self._require_writable()
        self._raise_if_failed()
        # Only the HTTP envelope constrains serialization. Domain validity must not gate fsync.
        validated = HttpRequestLogRecord.model_validate_json(record.model_dump_json())
        line = (validated.model_dump_json(ensure_ascii=True) + "\n").encode(TEXT_ENCODING)
        self._replay_log._append(line, expected_offset=self._append_offset)
        self._append_offset += len(line)
        self._append_ordinal += 1
        return validated, self._append_ordinal, line

    def _read_appended_record(self, line: bytes) -> HttpRequestLogRecord:
        from src.detours.detour_ai_augment.src.backend import api

        # This follows the request ACK boundary: readback failure cannot undo fsync.
        durable = tuple(self._replay_log._lines(offset=self._append_offset - len(line)))
        if durable != (line,):
            raise RuntimeError(Locale.STORE_DURABLE_APPEND_MISMATCH)
        return api._authoritative_log_records(durable[0])[0][0]

    def _append_authoritative_record(self, record: HttpRequestLogRecord) -> HttpRequestLogRecord:
        with self._threading_lock():
            try:
                stored, ordinal, line = self._append_request(record)
                self._apply_durable_record(
                    self._read_appended_record(line), ordinal=ordinal, raw_line=line
                )
                return self._http_record(stored.record_id)
            except BaseException as exc:
                self._failure = exc
                raise

    def pull(
        self,
        request: BackendComponent.PullRequestRecordProperty,
    ) -> ResponseRecordPromise[PullResponseRecord]:
        with self._lock:
            try:
                record, ordinal, line = self._append_request(
                    HttpRequestLogRecord.model_validate(request, from_attributes=True),
                )
            except Exception as exc:
                self._failure = exc
                return ResponseRecordPromise[PullResponseRecord]._resolved(
                    BackendStoreAcknowledgment.NAK,
                    (None, BackendStoreException._from_exception(exc)),
                )
            try:
                self._apply_durable_record(
                    self._read_appended_record(line), ordinal=ordinal, raw_line=line
                )
                http_record = self._http_record(record.record_id)
                response = PullResponseRecord(
                    schema_version=http_record.schema_version,
                    record_id=http_record.record_id,
                    method=http_record.method,
                    scheme=http_record.scheme,
                    host=http_record.host,
                    port=http_record.port,
                    path=http_record.path,
                    query=http_record.query,
                    request_headers=http_record.request_headers,
                    request_body=http_record.request_body,
                    response_code=http_record.response_code,
                    response_headers=http_record.response_headers,
                    response_body=http_record.response_body,
                    received_at_unix_usec=http_record.received_at_unix_usec,
                    ready_to_respond_at_unix_usec=http_record.ready_to_respond_at_unix_usec,
                    duration_usec=http_record.duration_usec,
                )
                return ResponseRecordPromise[PullResponseRecord]._resolved(
                    BackendStoreAcknowledgment.ACK,
                    (response, None),
                )
            except Exception as exc:
                self._failure = exc
                return ResponseRecordPromise[PullResponseRecord]._resolved(
                    BackendStoreAcknowledgment.ACK,
                    (None, BackendStoreException._from_exception(exc)),
                )

    def push(
        self,
        request: BackendComponent.PushRequestRecordProperty,
    ) -> ResponseRecordPromise[PushResponseRecord]:
        with self._lock:
            try:
                captured = HttpRequestLogRecord.model_validate(request, from_attributes=True)
                record, ordinal, line = self._append_request(captured)
            except Exception as exc:
                self._failure = exc
                return ResponseRecordPromise[PushResponseRecord]._resolved(
                    BackendStoreAcknowledgment.NAK,
                    (None, BackendStoreException._from_exception(exc)),
                )
            try:
                selected = PushRequestRecord.model_validate(request, from_attributes=True)
                self._apply_durable_record(
                    self._read_appended_record(line), ordinal=ordinal, raw_line=line
                )
                if record.response_code != HTTPStatus.ACCEPTED:
                    http_record = self._http_record(record.record_id)
                    response = PushResponseRecord(
                        schema_version=http_record.schema_version,
                        record_id=http_record.record_id,
                        method=http_record.method,
                        scheme=http_record.scheme,
                        host=http_record.host,
                        port=http_record.port,
                        path=http_record.path,
                        query=http_record.query,
                        request_headers=http_record.request_headers,
                        request_body=http_record.request_body,
                        response_code=http_record.response_code,
                        response_headers=http_record.response_headers,
                        response_body=http_record.response_body,
                        received_at_unix_usec=http_record.received_at_unix_usec,
                        ready_to_respond_at_unix_usec=http_record.ready_to_respond_at_unix_usec,
                        duration_usec=http_record.duration_usec,
                        commit_record=None,
                        validation_record=None,
                    )
                    return ResponseRecordPromise[PushResponseRecord]._resolved(
                        BackendStoreAcknowledgment.ACK,
                        (response, None),
                    )
                if self._loop is None:
                    raise RuntimeError(Locale.PUSH_SERVER_LOOP_REQUIRED)
                return ResponseRecordPromise[PushResponseRecord]._start(
                    BackendStoreAcknowledgment.ACK,
                    lambda: self._process_push(selected),
                    self._loop,
                )
            except Exception as exc:
                self._failure = exc
                return ResponseRecordPromise[PushResponseRecord]._resolved(
                    BackendStoreAcknowledgment.ACK,
                    (None, BackendStoreException._from_exception(exc)),
                )

    def _process_push(self, request: PushRequestRecord) -> PushResponseRecord:
        from src.detours.detour_ai_augment.src.backend import api

        try:
            runtime = self._runtime
            if runtime is None:
                raise RuntimeError(Locale.STORE_RUNTIME_UNAVAILABLE)
            commit = api._capture_push_commit(self, runtime, request)
            stored_commit = self._append_authoritative_record(commit)
            logger.info(
                Locale.PUSH_COMMIT_PERSISTED_LOG,
                request.record_id,
                stored_commit.record_id,
            )
            attempt = self._validate_commit(stored_commit.record_id)
            http_record = self._http_record(request.record_id)
            return PushResponseRecord(
                schema_version=http_record.schema_version,
                record_id=http_record.record_id,
                method=http_record.method,
                scheme=http_record.scheme,
                host=http_record.host,
                port=http_record.port,
                path=http_record.path,
                query=http_record.query,
                request_headers=http_record.request_headers,
                request_body=http_record.request_body,
                response_code=http_record.response_code,
                response_headers=http_record.response_headers,
                response_body=http_record.response_body,
                received_at_unix_usec=http_record.received_at_unix_usec,
                ready_to_respond_at_unix_usec=http_record.ready_to_respond_at_unix_usec,
                duration_usec=http_record.duration_usec,
                commit_record=attempt.attempt.commit_record,
                validation_record=attempt.validation_record,
            )
        except Exception as exc:
            with self._lock:
                self._failure = exc
                if self._group_scope is not None:
                    self._abort_group()
            raise

    def query(
        self,
        request: BackendComponent.QueryRequestRecordProperty,
    ) -> ResponseRecordPromise[QueryResponseRecord]:
        try:
            selected = QueryRequestRecord.model_validate(request, from_attributes=True)
            snapshot = self._query_snapshot()
            response = QueryResponseRecord.from_query_request(
                selected,
                body=snapshot,
                ready_to_respond_at_unix_usec=time.time_ns() // NANOSECONDS_PER_MICROSECOND,
            )
            return ResponseRecordPromise[QueryResponseRecord]._resolved(
                BackendStoreAcknowledgment.NAK,
                (response, None),
            )
        except Exception as exc:
            return ResponseRecordPromise[QueryResponseRecord]._resolved(
                BackendStoreAcknowledgment.NAK,
                (None, BackendStoreException._from_exception(exc)),
            )

    def run_outcome(
        self,
        request: BackendComponent.RunOutcomeRequestRecordProperty,
    ) -> ResponseRecordPromise[RunOutcomeResponseRecord]:
        from src.detours.detour_ai_augment.src.backend import api

        try:
            selected = RunOutcomeRequestRecord.model_validate(request, from_attributes=True)
            with self._threading_lock():
                if self._group_records:
                    raise RuntimeError(Locale.RUN_OUTCOME_PUSH_GROUP_OVERLAP)
                record = api._run_outcome_record(self, self._runtime, selected)
                stored = self._append_authoritative_record(record)
                response = RunOutcomeResponseRecord.from_http_request_log_record(stored)
            return ResponseRecordPromise[RunOutcomeResponseRecord]._resolved(
                BackendStoreAcknowledgment.NAK,
                (response, None),
            )
        except Exception as exc:
            self._failure = exc
            return ResponseRecordPromise[RunOutcomeResponseRecord]._resolved(
                BackendStoreAcknowledgment.NAK,
                (None, BackendStoreException._from_exception(exc)),
            )

    def _http_record(self, record_id: UUID) -> HttpRequestLogRecord:

        self._require_open()
        with self._lock:
            return self._http_record_with_ordinal(record_id)[1]

    def _query_snapshot(self) -> QueryResponse:
        """Read the complete snapshot under the Store's connection lock."""
        from src.detours.detour_ai_augment.src.backend import api
        from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome import (  # noqa: E501
            NAME_KEY_HEADER,
            RUN_OUTCOME_PATHS,
            name_key_from_header_value,
        )

        from .ai_augment_singular_outer_dict import AiAugmentSingularOuterDict
        from .query_response import QueryResponse
        from .run_outcome_record import RunOutcomeResponseRecord

        runtime = self._runtime
        if runtime is None:
            raise RuntimeError(Locale.STORE_RUNTIME_UNAVAILABLE)
        with self._reading():
            conn = self._detour_db.connection

            def attempt_records() -> tuple[AgentRuntimeAttemptRecord, ...]:
                rows = conn.execute(
                    f"SELECT records.{api.AUTHORITATIVE_RECORD_PAYLOAD_COLUMN}, "
                    f"attempts.{api.AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN} "
                    f"FROM {api.AUTHORITATIVE_ATTEMPTS_TABLE} AS attempts "
                    f"JOIN {api.AUTHORITATIVE_RECORDS_TABLE} AS records "
                    f"ON records.{api.AUTHORITATIVE_RECORD_ID_COLUMN} = "
                    f"attempts.{api.AUTHORITATIVE_ATTEMPT_COMMIT_ID_COLUMN} "
                    f"ORDER BY records.{api.AUTHORITATIVE_RECORD_ORDINAL_COLUMN}"
                ).fetchall()
                try:
                    attempts: list[AgentRuntimeAttemptRecord] = []
                    for record_json, attempt_json in rows:
                        record = HttpRequestLogRecord.model_validate_json(str(record_json))
                        api._parse_name_key_header(
                            record.request_headers.get(NAME_KEY_HEADER)
                        )
                        attempts.append(
                            api._attempt_record_from_serialized_json(
                                runtime,
                                str(attempt_json),
                                commit_http_record=record,
                            )
                        )
                    return tuple(attempts)
                except (api._PushValidationError, ValidationError, ValueError) as exc:
                    raise api._PushConfigurationError(Locale.REPLAY_PROJECTION_CONFLICT) from exc

            def run_outcome_records() -> tuple[RunOutcomeResponseRecord, ...]:
                placeholders = ", ".join("?" for _path in RUN_OUTCOME_PATHS)
                rows = conn.execute(
                    f"SELECT {api.AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
                    f"FROM {api.AUTHORITATIVE_RECORDS_TABLE} "
                    f"WHERE {api.AUTHORITATIVE_RECORD_METHOD_COLUMN} = ? "
                    f"AND {api.AUTHORITATIVE_RECORD_PATH_COLUMN} IN ({placeholders}) "
                    f"ORDER BY {api.AUTHORITATIVE_RECORD_ORDINAL_COLUMN}",
                    [
                        HTTP_POST_METHOD,
                        *(path.value for path in sorted(RUN_OUTCOME_PATHS)),
                    ],
                ).fetchall()
                try:
                    records = tuple(
                        HttpRequestLogRecord.model_validate_json(str(row[0])) for row in rows
                    )
                    return tuple(
                        RunOutcomeResponseRecord.from_http_request_log_record(record)
                        for record in records
                    )
                except (ValidationError, ValueError) as exc:
                    raise api._PushConfigurationError(Locale.REPLAY_PROJECTION_CONFLICT) from exc

            selected_attempts = attempt_records()
            committed_by_namekey: dict[str, list[CommittedInnerDict]] = {}
            for committed in api._committed_innerdicts(self):
                committed_namekey_json = name_key_from_header_value(
                    committed.commit_record.request_headers.get(NAME_KEY_HEADER)
                ).to_json_key()
                committed_by_namekey.setdefault(committed_namekey_json, []).append(committed)
            selected_singular_outerdicts: list[AiAugmentSingularOuterDict] = []
            for singular_outerdict in runtime.ai_augment_singular_outerdicts:
                selected_singular_outerdict = singular_outerdict.model_copy()
                selected_singular_outerdict.committed_innerdicts = tuple(
                    committed_by_namekey.get(singular_outerdict.namekey.to_json_key(), ())
                )
                selected_singular_outerdicts.append(selected_singular_outerdict)
            return QueryResponse(
                attempts=selected_attempts,
                ai_augment_singular_outerdicts=tuple(selected_singular_outerdicts),
                run_outcome_records=run_outcome_records(),
            )

    def _recorded_model_http(
        self,
        request: requests.PreparedRequest,
        **kwargs: Any,
    ) -> HttpRequestLogRecord:
        from src.detours.detour_ai_augment.src.backend import api

        key = request_key(request)
        rows = self._execute(
            f"SELECT {api.AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
            f"FROM {api.AUTHORITATIVE_RECORDS_TABLE} "
            f"ORDER BY {api.AUTHORITATIVE_RECORD_ORDINAL_COLUMN} DESC"
        ).fetchall()
        for (payload,) in rows:
            record = HttpRequestLogRecord.model_validate_json(payload)
            if record_key(record) == key:
                return record
        raise ModelHttpRequired(request, **kwargs)

    def _capture_model_http(self, required: ModelHttpRequired) -> HttpRequestLogRecord:
        self._require_writable()
        request = required.request.copy()
        target = urlsplit(request.url or "")
        if target.hostname == "api.openalex.org":
            # Provider credentials belong to live capture, not generic interception.
            assert self._runtime is not None
            key = os.environ["OPENALEX_API_KEY"]
            params = [
                (k, key if k == "api_key" else v)
                for k, v in parse_qsl(target.query, keep_blank_values=True)
            ]
            request.url = urlunsplit(target._replace(query=urlencode(params)))
        started_ns = time.monotonic_ns()
        response: requests.Response | None = None
        try:
            with requests.Session() as session:
                response = session.send(request, **required.send_kwargs, allow_redirects=False)
        except requests.RequestException:
            # Persist a request-only transport failure; replay raises the same class
            # of validation failure rather than inventing an HTTP response.
            pass
        if response is not None:
            record = HttpRequestLogRecord.from_response(
                response,
                ready_to_respond_at_unix_usec=time.time_ns() // 1000,
                duration_usec=(time.monotonic_ns() - started_ns) // 1000,
            )
            return self._append_authoritative_record(record)
        target = urlsplit(request.url or "")
        record = HttpRequestLogRecord(
            schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            method=request.method or "",
            scheme=target.scheme,
            host=target.hostname or "",
            port=target.port,
            path=target.path,
            query=redact_http_request_log_query(target.query),
            request_headers=dict(request.headers),
            request_body=request_body(request),
            response_code=None,
            response_headers=None,
            response_body=None,
            received_at_unix_usec=None,
            ready_to_respond_at_unix_usec=time.time_ns() // 1000,
            duration_usec=(time.monotonic_ns() - started_ns) // 1000,
        )
        return self._append_authoritative_record(record)

    def _validate_commit(self, commit_id: UUID) -> AgentRuntimeAttemptRecord:
        from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_mixin import (  # noqa: E501
            submission_http_context,
        )
        from src.detours.detour_ai_augment.src.backend import api

        self._require_writable()
        assert self._runtime is not None
        while True:
            missing: ModelHttpRequired | None = None
            with self._lock:
                existing = self._execute(
                    f"SELECT {api.AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN} "
                    f"FROM {api.AUTHORITATIVE_ATTEMPTS_TABLE} "
                    f"WHERE {api.AUTHORITATIVE_ATTEMPT_COMMIT_ID_COLUMN} = ?",
                    [str(commit_id)],
                ).fetchone()
                commit = api._backend_commit_record(
                    self,
                    self._http_record_with_ordinal(commit_id)[1],
                )
                if existing is not None:
                    applied = api._attempt_record_from_serialized_json(
                        self._runtime,
                        existing[0],
                        commit_http_record=commit,
                    )
                    return applied
                http = ModelHttpInterceptor(record_get=self._recorded_model_http)
                try:
                    with submission_http_context(http):
                        evaluated, _ = api._validate_projected_commit(
                            self,
                            self._runtime,
                            commit,
                            initial_validation_record=self._initial_validation_record,
                        )
                except ModelHttpRequired as exc:
                    missing = exc
                finally:
                    self._reset_group_projection()
                # Restore the group's durable inputs before capturing a missing provider
                # response. Only the recorded validation commits derived DB state.
            if missing is not None:
                self._capture_model_http(missing)
                continue
            body = ValidationRequestBody(
                commit_record=commit,
                post_commit_validation=evaluated.attempt.post_commit_validation,
                initial_validation_record=self._initial_validation_record,
                openalex_ror_records=tuple(
                    self._http_record(record_id) for record_id in http.record_ids
                ),
            )
            self._append_authoritative_record(body.http_record())
            # Return the applied, serialized result, not the speculative evaluation.
            with self._lock:
                row = self._execute(
                    f"SELECT {api.AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN} "
                    f"FROM {api.AUTHORITATIVE_ATTEMPTS_TABLE} "
                    f"WHERE {api.AUTHORITATIVE_ATTEMPT_COMMIT_ID_COLUMN} = ?",
                    [str(commit_id)],
                ).fetchone()
                if row is None:
                    raise RuntimeError("Validation result was not applied")
                return api._attempt_record_from_serialized_json(
                    self._runtime,
                    row[0],
                    commit_http_record=commit,
                )

    def _write_anchor(self, anchor: _ReplayAnchor) -> None:
        # Table comments are transactional metadata, not a separate checkpoint table.
        if not self._transaction_active:
            raise RuntimeError("Anchor changes require a Store transaction")
        payload = anchor.model_dump_json().replace("'", "''")
        self._detour_db.connection.execute(
            f"COMMENT ON TABLE detour_http_records IS '{payload}'"
        )

    def _verify_log_projection(self) -> _ReplayAnchor | None:
        """Verify only; missing history is never applied on resume or query startup."""
        row = self._execute(
            "SELECT comment FROM duckdb_tables() "
            "WHERE database_name = current_database() AND schema_name = 'main' "
            "AND table_name = 'detour_http_records'"
        ).fetchone()
        if row is None or row[0] is None:
            raise ValueError("Replay anchor missing; explicit --new is required")
        anchor = _ReplayAnchor.model_validate_json(row[0])
        # Missing legacy columns fail here without migration or mutation.
        rows = self._execute(
            "SELECT record_ordinal, raw_line_sha256 FROM detour_http_records "
            "ORDER BY record_ordinal"
        ).fetchall()
        size = self._replay_log._size()
        logger.info(
            "Verifying replay log: stored hash %s at line %d byte %d; config hash %s; %d bytes",
            anchor.sha256, anchor.ordinal, anchor.byte_offset, self._replay_log.hash, size,
        )
        if anchor.byte_offset > size or anchor.ordinal > len(rows):
            raise ValueError("Replay prefix is truncated or missing from DB")
        prefix = hashlib.sha256()
        offset = 0
        ordinal = 0
        boundary_seen = anchor.ordinal == 0 and anchor.byte_offset == 0
        if boundary_seen and anchor.sha256 != EMPTY_LOG_SHA256:
            raise ValueError("Empty replay anchor hash mismatch")
        logger.info("Verifying prefix: %d lines, %d bytes", anchor.ordinal, anchor.byte_offset)
        if boundary_seen:
            logger.info("Prefix hash matches stored anchor")
        for ordinal, line in enumerate(self._replay_log._lines(), start=1):
            if ordinal > anchor.ordinal:
                logger.info("Verifying suffix line %d", ordinal)
            if not line.endswith(b"\n") or not line.strip():
                raise ValueError(f"Replay line {ordinal}: invalid JSONL boundary")
            if ordinal > len(rows) or rows[ordinal - 1][0] != ordinal:
                raise ValueError(f"Replay line {ordinal}: missing or unordered DB record")
            digest = rows[ordinal - 1][1]
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(f"Replay line {ordinal}: missing raw-line hash")
            offset += len(line)
            if ordinal <= anchor.ordinal:
                prefix.update(line)
                if ordinal == anchor.ordinal:
                    if offset != anchor.byte_offset or prefix.hexdigest() != anchor.sha256:
                        raise ValueError(f"Replay prefix mismatch at line {ordinal}, byte {offset}")
                    boundary_seen = True
                    logger.info("Prefix hash matches stored anchor")
            elif hashlib.sha256(line).hexdigest() != digest:
                raise ValueError(f"Replay line {ordinal}: raw-line hash mismatch")
        if not boundary_seen or ordinal != len(rows) or offset != size:
            raise ValueError("Replay/DB coverage mismatch (extra rows or invalid anchor boundary)")
        # A Dashboard child's unchanged config may describe only the accepted old prefix.
        # A different hash must be verified by RegisteredResource, never trusted from a flag.
        verified_anchor = None
        if self._replay_log.hash != anchor.sha256:
            self._replay_log.verify_hash()
            verified_anchor = _ReplayAnchor(
                sha256=self._replay_log.hash, ordinal=ordinal, byte_offset=offset,
            )
        self._next_line_number = ordinal + 1
        self._log_offset = offset
        self._append_ordinal = ordinal
        self._append_offset = offset
        logger.info("DB/log ordinal and byte coverage verified: %d lines, %d bytes",
                    ordinal, offset)
        return verified_anchor

    def _raise_if_failed(self) -> None:
        if self._failure is not None:
            raise RuntimeError(
                "Backend Store failed; rebuild with --new before reuse"
            ) from self._failure

    def _require_closed(self) -> None:
        if self._mode is not None:
            raise RuntimeError("AiAugmentBackendStore is already open")

    def _require_writable(self) -> None:
        if self._mode != "writable":
            raise RuntimeError("AiAugmentBackendStore must be used inside a writable 'with' block")

    def _require_open(self) -> None:
        if self._mode is None:
            raise RuntimeError("AiAugmentBackendStore must be used inside a 'with' block")

    def _initialize_http_record_schema(self) -> None:
        from src.detours.detour_ai_augment.src.backend import api

        self._execute(api.CREATE_AUTHORITATIVE_RECORDS_TABLE_SQL)
        self._execute(api.CREATE_AUTHORITATIVE_ATTEMPTS_TABLE_SQL)

    def _http_record_with_ordinal(
        self,
        record_id: UUID,
    ) -> tuple[int, HttpRequestLogRecord]:
        from src.detours.detour_ai_augment.src.backend import api

        row = self._execute(
            f"SELECT {api.AUTHORITATIVE_RECORD_ORDINAL_COLUMN}, "
            f"{api.AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
            f"FROM {api.AUTHORITATIVE_RECORDS_TABLE} "
            f"WHERE {api.AUTHORITATIVE_RECORD_ID_COLUMN} = ?",
            [str(record_id)],
        ).fetchone()
        if row is None:
            raise api._PushValidationError(Locale.REPLAY_COMMIT_LINK_MISSING)
        try:
            return int(row[0]), api._validated_http_record(
                HttpRequestLogRecord.model_validate_json(str(row[1]))
            )
        except ValidationError as exc:
            raise api._PushValidationError(Locale.REPLAY_COMMIT_LINK_MISSING) from exc

    def _insert_projected_http_record(
        self,
        record: HttpRequestLogRecord,
        *,
        line_number: int,
        raw_line: bytes,
    ) -> None:
        from src.detours.detour_ai_augment.src.backend import api

        conn = self._detour_db.connection
        conn.execute(
            f"INSERT INTO {api.AUTHORITATIVE_RECORDS_TABLE} VALUES (?, ?, ?, ?, ?, ?)",
            [
                line_number,
                str(record.record_id),
                record.method,
                record.path,
                record.model_dump_json(),
                hashlib.sha256(raw_line).hexdigest(),
            ],
        )

    def _insert_attempt_record(
        self,
        attempt_record: AgentRuntimeAttemptRecord,
    ) -> None:
        from src.detours.detour_ai_augment.src.backend import api

        conn = self._detour_db.connection
        conn.execute(
            f"INSERT INTO {api.AUTHORITATIVE_ATTEMPTS_TABLE} VALUES (?, ?)",
            [
                str(attempt_record.attempt.commit_record.record_id),
                attempt_record.model_dump_json(),
            ],
        )

    def _begin_group(self, push_id: UUID) -> None:
        self._group_previous_records = (
            self._current_pull_record, self._current_push_record,
            self._current_commit_record, self._current_validation_record,
        )
        self._group_push_id = push_id
        self._group_commit_id = None
        scope = self._detour_db.writable()
        scope.__enter__()
        self._group_scope = scope
        self._detour_db.connection.execute("BEGIN TRANSACTION")
        self._transaction_active = True

    def _abort_group(self) -> None:
        scope = self._group_scope
        if scope is None:
            return
        try:
            self._detour_db.connection.execute("ROLLBACK")
        finally:
            self._transaction_active = False
            self._group_scope = None
            self._group_records.clear()
            if self._group_previous_records is not None:
                (
                    self._current_pull_record, self._current_push_record,
                    self._current_commit_record, self._current_validation_record,
                ) = self._group_previous_records
            self._group_previous_records = None
            self._group_push_id = None
            self._group_commit_id = None
            scope.__exit__(None, None, None)

    def _reset_group_projection(self) -> None:
        from src.detours.detour_ai_augment.src.backend import api

        if self._group_scope is None:
            raise RuntimeError(Locale.VALIDATION_PUSH_TRANSACTION_REQUIRED)
        conn = self._detour_db.connection
        conn.execute("ROLLBACK")
        conn.execute("BEGIN TRANSACTION")
        for ordinal, line in self._group_records:
            record = api._authoritative_log_records(line)[0][0]
            self._insert_projected_http_record(record, line_number=ordinal, raw_line=line)

    def _finish_group(self) -> None:
        scope = self._group_scope
        if scope is None:
            raise RuntimeError(Locale.STORE_PUSH_GROUP_MISSING)
        self._detour_db.connection.execute("COMMIT")
        self._transaction_active = False
        self._group_scope = None
        scope.__exit__(None, None, None)
        self._log_offset += sum(len(line) for _, line in self._group_records)
        self._next_line_number = self._group_records[-1][0] + 1
        self._group_previous_records = None
        self._group_records.clear()
        self._group_push_id = None
        self._group_commit_id = None

    def _apply_durable_record(
        self,
        record: HttpRequestLogRecord,
        *,
        ordinal: int,
        raw_line: bytes,
    ) -> None:
        from src.detours.detour_ai_augment.src.backend import api
        from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome import (  # noqa: E501
            RUN_OUTCOME_PATHS,
        )

        from .validation_event import BackendValidationRecord

        runtime = self._runtime
        if runtime is None:
            raise RuntimeError(Locale.STORE_RUNTIME_UNAVAILABLE)
        accepted_push = (record.method, record.path, record.response_code) == (
            HTTP_POST_METHOD, PUSH_PATH, HTTPStatus.ACCEPTED,
        )
        if accepted_push:
            if self._group_scope is not None:
                raise ValueError(Locale.REPLAY_PUSH_GROUP_OVERLAP)
            self._begin_group(record.record_id)
        if self._group_scope is not None:
            self._group_records.append((ordinal, raw_line))
            self._insert_projected_http_record(record, line_number=ordinal, raw_line=raw_line)
            record = self._http_record(record.record_id)
            self._remember_http_record(record)
            if (record.method, record.path) == (HTTP_POST_METHOD, COMMIT_PATH):
                commit = api._backend_commit_record(self, record)
                if (
                    self._group_commit_id is not None
                    or commit.commit_request_body.push_record.record_id != self._group_push_id
                ):
                    raise ValueError(Locale.REPLAY_PUSH_GROUP_COMMIT_MISMATCH)
                self._group_commit_id = record.record_id
                self._current_commit_record = commit
            elif (record.method, record.path) == (HTTP_POST_METHOD, VALIDATE_PATH):
                validation = BackendValidationRecord.from_http_request_log_record(record)
                body = validation.validation_request_body
                if body.commit_record.record_id != self._group_commit_id:
                    raise ValueError(Locale.REPLAY_PUSH_GROUP_VALIDATION_MISMATCH)
                initial = body.initial_validation_record
                if initial is None:
                    # An explicit root in replay marks a recorded Backend lifecycle boundary.
                    if self._initial_validation_record is not None and not self._rebuilding:
                        raise ValueError(Locale.VALIDATION_INITIAL_LINK_INVALID)
                elif initial != self._initial_validation_record:
                    raise ValueError(Locale.VALIDATION_INITIAL_LINK_INVALID)
                applied, commit_database = api._apply_validation_record(self, runtime, record)
                if not commit_database:
                    self._reset_group_projection()
                self._insert_attempt_record(applied)
                self._finish_group()
                if initial is None:
                    self._initial_validation_record = validation
                self._current_validation_record = validation
            elif record.method == HTTP_POST_METHOD and record.path in RUN_OUTCOME_PATHS:
                raise ValueError(Locale.REPLAY_PUSH_GROUP_OUTCOME_EARLY)
            return
        if (record.method, record.path) in {
            (HTTP_POST_METHOD, COMMIT_PATH), (HTTP_POST_METHOD, VALIDATE_PATH),
        }:
            raise ValueError(Locale.REPLAY_PUSH_GROUP_MISSING)
        with self._transaction():
            self._insert_projected_http_record(record, line_number=ordinal, raw_line=raw_line)
            record = self._http_record(record.record_id)
            if record.method == HTTP_POST_METHOD and record.path in RUN_OUTCOME_PATHS:
                outcome = RunOutcomeResponseRecord.from_http_request_log_record(record)
                api._verify_run_outcome_record(self, runtime, outcome)
                api._apply_run_outcome_record(self, outcome)
        self._remember_http_record(record)
        self._next_line_number = ordinal + 1
        self._log_offset += len(raw_line)

    @contextmanager
    def _transaction(self, *, rollback: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
        """Only Store application/evaluation/schema methods may open a write window."""
        with self._lock:
            self._require_open()
            self._raise_if_failed()
            if self._mode != "writable" and not self._rebuilding:
                raise RuntimeError("Backend Store is read-only")
            if self._transaction_active or self._reading_active:
                raise RuntimeError("Cannot nest a Store write transaction")
            try:
                with self._detour_db.writable():
                    conn = self._detour_db.connection
                    conn.execute("BEGIN TRANSACTION")
                    self._transaction_active = True
                    try:
                        yield conn
                    except BaseException:
                        try:
                            conn.execute("ROLLBACK")
                        except BaseException as exc:
                            self._failure = exc
                            raise
                        raise
                    else:
                        try:
                            conn.execute("ROLLBACK" if rollback else "COMMIT")
                        except BaseException as exc:
                            self._failure = exc
                            raise
                    finally:
                        self._transaction_active = False
            except ModelHttpRequired:
                # A successfully rolled-back preview requests the missing input outside SQL.
                raise
            except BaseException as exc:
                self._failure = exc
                raise

    @contextmanager
    def _reading(self) -> Iterator[None]:
        with self._lock:
            self._require_open()
            self._raise_if_failed()
            if self._transaction_active or self._reading_active:
                yield
            else:
                with self._detour_db.read_only():
                    self._reading_active = True
                    try:
                        yield
                    finally:
                        self._reading_active = False

    def _check_sql(self, sql: str) -> None:
        statements = duckdb.extract_statements(sql)
        allowed = {'SELECT', 'EXPLAIN'}
        if self._transaction_active:
            allowed |= {
                'INSERT', 'UPDATE',
                'DELETE', 'CREATE',
                'DROP', 'ALTER',
            }
        if len(statements) != 1 or statements[0].type.name not in allowed:
            raise RuntimeError("SQL is not allowed in the current Store transaction scope")

    def _query_mappings(
        self,
        sql: str,
        parameters: Sequence[object] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        with self._reading():
            self._check_sql(sql)
            result = self._detour_db.connection.execute(sql, parameters)
            columns = tuple(column[0] for column in result.description)
            return tuple(dict(zip(columns, row, strict=True)) for row in result.fetchall())

    def _execute(self, sql: str, parameters: Sequence[object] | None = None) -> ExecuteResult:
        with self._reading():
            self._check_sql(sql)
            rows = self._detour_db.connection.execute(sql, parameters).fetchall()
            return ExecuteResult(rows)

    def _materialize_innerdicts(self, *, source_relation: str, table_name: str) -> None:
        with self._lock:
            self._raise_if_failed()
            if not self._transaction_active:
                raise RuntimeError("Materialization requires a Store write transaction")
            materialize_innerdicts_from_rows_table(
                self._detour_db.connection, source_relation=source_relation, table_name=table_name,
            )


@implements[BackendComponent.QueryOnlyStoreProperty]()
class AiAugmentQueryBackendStore(FrozenStrictModel):
    """IPC-only capability: no writable operation or exposed engine."""

    _engine: AiAugmentBackendStore = PrivateAttr()

    def query(
        self,
        request: BackendComponent.QueryRequestRecordProperty,
    ) -> ResponseRecordPromise[QueryResponseRecord]:
        return self._engine.query(request)


@overload
def initialize_backend_store(
    runtime: AiAugmentBackendContext,
    *,
    ipc_only: Literal[True],
) -> AbstractContextManager[AiAugmentQueryBackendStore]: ...


@overload
def initialize_backend_store(
    runtime: AiAugmentBackendContext,
    *,
    ipc_only: Literal[False],
    new: bool,
    confirmed: bool,
    confirm_replay: Callable[[], bool],
) -> AbstractContextManager[AiAugmentBackendStore]: ...


def initialize_backend_store(
    runtime: AiAugmentBackendContext,
    *,
    ipc_only: bool,
    new: bool = False,
    confirmed: bool = False,
    confirm_replay: Callable[[], bool] = lambda: False,
) -> AbstractContextManager[AiAugmentQueryBackendStore | AiAugmentBackendStore]:
    return _initialize_backend_store(
        runtime,
        ipc_only=ipc_only,
        new=new,
        confirmed=confirmed,
        confirm_replay=confirm_replay,
    )


@contextmanager
def _initialize_backend_store(
    runtime: AiAugmentBackendContext,
    *,
    ipc_only: bool,
    new: bool,
    confirmed: bool,
    confirm_replay: Callable[[], bool],
) -> Iterator[AiAugmentQueryBackendStore | AiAugmentBackendStore]:
    config = runtime.pipeline_config
    store = AiAugmentBackendStore._from_resources(
        replay_log=config.replay_log,
        detour_db=AiAugmentDetourDB.from_pipeline_db(
            config.db_file,
            duckdb_extensions=config.duckdb_extensions,
        ),
        rollout_cas=config.rollout_cas,
    )
    if ipc_only:
        with store._read_only(runtime):
            capability = AiAugmentQueryBackendStore()
            capability._engine = store
            yield capability
        return
    if not confirmed:
        raise ValueError(Locale.STORE_STARTUP_CONFIRMATION_REQUIRED)
    if new:
        store._rebuild_from_log(runtime, reset_confirmed=confirmed, confirm_replay=confirm_replay)
    store._reset_current_records()
    try:
        store._loop = asyncio.get_running_loop()
    except RuntimeError:
        # CLI/startup-only callers do not serve HTTP or accept pushes.
        store._loop = None
    with store._writable(runtime):
        yield store
