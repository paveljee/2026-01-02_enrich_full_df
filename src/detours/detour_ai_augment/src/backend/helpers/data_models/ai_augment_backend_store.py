from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, Self, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import duckdb
import requests
from pydantic import PrivateAttr, ValidationError

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
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
from src.detours.detour_ai_augment.src.backend.helpers.data_models.validation_event import (
    VALIDATE_PATH,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.query_request import (  # noqa: E501
    QueryRequest,
)
from src.helpers.architecture import FrozenStrictModel
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
    redact_http_request_log_query,
)
from src.helpers.duckdb_utils import materialize_innerdicts_from_rows_table

from .ai_augment_cas import AiAugmentCAS
from .committed_innerdict import CommittedInnerDict
from .model_http_interceptor import (
    ModelHttpInterceptor,
    ModelHttpRequired,
    record_key,
    request_body,
    request_key,
)
from .query_response import AgentRuntimeAttemptRecord, QueryResponse
from .validation_event import ValidationRequestBody

StoreMode = Literal["writable", "read_only"]


class ExecuteResult:
    """Detached rows with DuckDB-style consuming fetch methods."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = iter(rows)

    def fetchone(self) -> tuple[Any, ...] | None:
        return next(self._rows, None)

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._rows)


class AiAugmentBackendStore(FrozenStrictModel):
    """Authoritative replay log and its managed DuckDB projection."""

    rollout_cas: AiAugmentCAS
    _replay_log: ReplayLogRegisteredResource = PrivateAttr()
    _detour_db: AiAugmentDetourDB = PrivateAttr()
    _lock: threading.RLock = PrivateAttr(default_factory=threading.RLock)
    _mode: StoreMode | None = PrivateAttr(default=None)
    _runtime: BackendComponent.ContextProperty | None = PrivateAttr(default=None)
    _next_line_number: int = PrivateAttr(default=1)
    _log_offset: int = PrivateAttr(default=0)
    _transaction_active: bool = PrivateAttr(default=False)
    _reading_active: bool = PrivateAttr(default=False)
    _rebuilding: bool = PrivateAttr(default=False)
    _failure: BaseException | None = PrivateAttr(default=None)

    @classmethod
    def from_resources(
        cls, *, replay_log: ReplayLogRegisteredResource,
        detour_db: AiAugmentDetourDB, rollout_cas: AiAugmentCAS,
    ) -> Self:
        store = cls(rollout_cas=rollout_cas)
        store._replay_log = replay_log
        store._detour_db = detour_db
        return store

    @property
    def detour_db_path(self) -> Path:
        return self._detour_db.path

    @contextmanager
    def _opened(
        self, mode: StoreMode, runtime: BackendComponent.ContextProperty | None = None,
    ) -> Iterator[Self]:
        self._require_closed()
        self._raise_if_failed()
        with self._replay_log._locked(append_allowed=mode == "writable"):
            self._mode = mode
            self._runtime = runtime
            try:
                with self._lock:
                    self._restore_append_position()
                    if runtime is not None:
                        self._publish_stored_cards(runtime)
                yield self
                self._raise_if_failed()
            finally:
                self._runtime = None
                self._mode = None

    @contextmanager
    def writable(self, runtime: BackendComponent.ContextProperty) -> Iterator[Self]:
        """Continue a known-clean DB; reconstruction is explicit, never implicit."""
        with self._opened("writable", runtime) as store:
            yield store

    @contextmanager
    def read_only(self) -> Iterator[Self]:
        with self._opened("read_only") as store:
            yield store

    def rebuild_from_log(
        self, runtime: BackendComponent.ContextProperty, *, reset_confirmed: bool,
    ) -> None:
        from src.detours.detour_ai_augment.src.backend import api

        if not reset_confirmed:
            raise ValueError("Database reset confirmation required for --new.")
        with self._lock:
            self._require_closed()
            with self._replay_log._locked(append_allowed=False):
                # Reject invalid JSONL before touching the old derived DB. Never repair it.
                records = api._authoritative_log_records(self._replay_log._read())
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
                    for ordinal, (record, _) in enumerate(records, start=1):
                        self._apply_log_record(runtime, record, line_number=ordinal)
                    self._next_line_number = len(records) + 1
                    self._log_offset = self._replay_log._size()
                    self._publish_stored_cards(runtime)
                except BaseException as exc:
                    self._failure = exc
                    raise
                finally:
                    self._rebuilding = False
                    self._runtime = None
                    self._mode = None

    @contextmanager
    def threading_lock(self) -> Iterator[Self]:
        self._require_writable()
        with self._lock:
            self._raise_if_failed()
            yield self

    def _publish_stored_cards(self, runtime: BackendComponent.ContextProperty) -> None:
        """Opening for live work or replay always completes stored card publication."""
        from src.detours.detour_ai_augment.src.backend import api

        from .ai_augment_context import AiAugmentBackendContext

        rows = self.execute(
            f"SELECT {api.AUTHORITATIVE_RECORD_ID_COLUMN} "
            f"FROM {api.AUTHORITATIVE_RECORDS_TABLE} "
            f"WHERE {api.AUTHORITATIVE_RECORD_METHOD_COLUMN} = ? "
            f"AND {api.AUTHORITATIVE_RECORD_PATH_COLUMN} = ? "
            f"ORDER BY {api.AUTHORITATIVE_RECORD_ORDINAL_COLUMN}",
            [api.HTTP_POST_METHOD, VALIDATE_PATH],
        ).fetchall()
        for (record_id,) in rows:
            api.publish_card_zip(self, cast(AiAugmentBackendContext, runtime), UUID(str(record_id)))

    def append_authoritative_record(
        self,
        record: HttpRequestLogRecord,
    ) -> HttpRequestLogRecord:
        from src.detours.detour_ai_augment.src.backend import api

        validated = api._validated_http_record(record)
        line = (validated.model_dump_json(ensure_ascii=True) + "\n").encode(TEXT_ENCODING)
        with self.threading_lock():
            try:
                self._replay_log._append(line, expected_offset=self._log_offset)
                # Consume the durable bytes, exactly as during read-only-log reconstruction.
                self._consume_log_suffix()
                return self.http_record_with_ordinal(validated.record_id)[1]
            except BaseException as exc:
                self._failure = exc
                raise

    def http_record(self, record_id: UUID) -> HttpRequestLogRecord:

        self._require_open()
        with self._lock:
            return self.http_record_with_ordinal(record_id)[1]

    def query(
        self, runtime: BackendComponent.ContextProperty, request: QueryRequest
    ) -> QueryResponse:
        """Read the complete snapshot under the Store's connection lock."""
        from src.detours.detour_ai_augment.src.backend import api
        from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome import (  # noqa: E501
            NAME_KEY_HEADER,
            RUN_OUTCOME_PATHS,
            name_key_from_header_value,
        )

        from .ai_augment_context import AiAugmentBackendContext
        from .ai_augment_singular_outer_dict import AiAugmentSingularOuterDict
        from .query_response import QueryResponse
        from .run_outcome_response import RunOutcomeResponse

        runtime = cast(AiAugmentBackendContext, runtime)
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

            def run_outcome_records() -> tuple[RunOutcomeResponse, ...]:
                placeholders = ", ".join("?" for _path in RUN_OUTCOME_PATHS)
                rows = conn.execute(
                    f"SELECT {api.AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
                    f"FROM {api.AUTHORITATIVE_RECORDS_TABLE} "
                    f"WHERE {api.AUTHORITATIVE_RECORD_METHOD_COLUMN} = ? "
                    f"AND {api.AUTHORITATIVE_RECORD_PATH_COLUMN} IN ({placeholders}) "
                    f"ORDER BY {api.AUTHORITATIVE_RECORD_ORDINAL_COLUMN}",
                    [
                        api.HTTP_POST_METHOD,
                        *(path.value for path in sorted(RUN_OUTCOME_PATHS)),
                    ],
                ).fetchall()
                try:
                    records = tuple(
                        HttpRequestLogRecord.model_validate_json(str(row[0])) for row in rows
                    )
                    return tuple(
                        RunOutcomeResponse.from_http_request_log_record(record)
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
        rows = self.execute(
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
            return self.append_authoritative_record(record)
        target = urlsplit(request.url or "")
        record = HttpRequestLogRecord(
            schema_version="1.1",
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
        return self.append_authoritative_record(record)

    def validate_commit(self, commit_id: UUID) -> AgentRuntimeAttemptRecord:
        from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_mixin import (  # noqa: E501
            submission_http_context,
        )
        from src.detours.detour_ai_augment.src.backend import api

        from .ai_augment_context import AiAugmentBackendContext

        self._require_writable()
        assert self._runtime is not None
        while True:
            missing: ModelHttpRequired | None = None
            with self._lock:
                existing = self.execute(
                    f"SELECT {api.AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN} "
                    f"FROM {api.AUTHORITATIVE_ATTEMPTS_TABLE} "
                    f"WHERE {api.AUTHORITATIVE_ATTEMPT_COMMIT_ID_COLUMN} = ?",
                    [str(commit_id)],
                ).fetchone()
                commit = api._backend_commit_record(
                    self,
                    self.http_record_with_ordinal(commit_id)[1],
                )
                if existing is not None:
                    applied = api._attempt_record_from_serialized_json(
                        cast(AiAugmentBackendContext, self._runtime),
                        existing[0],
                        commit_http_record=commit,
                    )
                    if applied.validation_record is not None:
                        try:
                            api.publish_card_zip(
                                self, cast(AiAugmentBackendContext, self._runtime),
                                applied.validation_record.record_id,
                            )
                        except BaseException as exc:
                            self._failure = exc
                            raise
                    return applied
                http = ModelHttpInterceptor(self._recorded_model_http)
                try:
                    with self._transaction(rollback=True), submission_http_context(http):
                        evaluated, _ = api._validate_projected_commit(
                            self,
                            cast(AiAugmentBackendContext, self._runtime),
                            commit,
                        )
                except ModelHttpRequired as exc:
                    missing = exc
                # Evaluation is always rolled back before capturing missing HTTP inputs
                # or appending /validate. Only durable application publishes DB state.
            if missing is not None:
                self._capture_model_http(missing)
                continue
            submission = evaluated.submission
            body = ValidationRequestBody(
                commit_id=commit_id,
                post_commit_validation=evaluated.attempt.post_commit_validation,
                submission_type=None
                if submission is None
                else (
                    "StandardizedSubmission"
                    if type(submission).__name__ == "StandardizedSubmission"
                    else "Submission"
                ),
                submission=(
                    None
                    if submission is None
                    else submission.model_dump(
                        mode="json",
                        by_alias=True,
                    )
                ),
                http_record_ids=http.record_ids,
            )
            self.append_authoritative_record(body.http_record(commit))
            # Return the applied, serialized result, not the speculative evaluation.
            with self._lock:
                row = self.execute(
                    f"SELECT {api.AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN} "
                    f"FROM {api.AUTHORITATIVE_ATTEMPTS_TABLE} "
                    f"WHERE {api.AUTHORITATIVE_ATTEMPT_COMMIT_ID_COLUMN} = ?",
                    [str(commit_id)],
                ).fetchone()
                if row is None:
                    raise RuntimeError("Validation result was not applied")
                return api._attempt_record_from_serialized_json(
                    cast(AiAugmentBackendContext, self._runtime),
                    row[0],
                    commit_http_record=commit,
                )

    def _consume_log_suffix(self) -> None:
        from src.detours.detour_ai_augment.src.backend import api

        assert self._runtime is not None
        records = api._authoritative_log_records(
            self._replay_log._read(offset=self._log_offset)
        )
        for record, _ in records:
            self._apply_log_record(self._runtime, record, line_number=self._next_line_number)
            self._next_line_number += 1
        if records:
            self._log_offset += records[-1][1]

    def _restore_append_position(self) -> None:
        """Resume is explicitly restricted to a previously clean Store lifecycle."""
        from src.detours.detour_ai_augment.src.backend import api

        row = self.execute(
            f"SELECT COALESCE(MAX({api.AUTHORITATIVE_RECORD_ORDINAL_COLUMN}), 0) "
            f"FROM {api.AUTHORITATIVE_RECORDS_TABLE}"
        ).fetchone()
        assert row is not None
        self._next_line_number = int(row[0]) + 1
        self._log_offset = self._replay_log._size()
        if self._log_offset and self._replay_log._read(offset=self._log_offset - 1) != b"\n":
            raise ValueError("Replay log has an incomplete tail; --resume is unavailable")

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

        self.execute(api.CREATE_AUTHORITATIVE_RECORDS_TABLE_SQL)
        self.execute(api.CREATE_AUTHORITATIVE_ATTEMPTS_TABLE_SQL)

    def http_record_with_ordinal(
        self,
        record_id: UUID,
    ) -> tuple[int, HttpRequestLogRecord]:
        from src.detours.detour_ai_augment.src.backend import api

        row = self.execute(
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
    ) -> None:
        from src.detours.detour_ai_augment.src.backend import api

        conn = self._detour_db.connection
        conn.execute(
            f"INSERT INTO {api.AUTHORITATIVE_RECORDS_TABLE} VALUES (?, ?, ?, ?, ?)",
            [
                line_number,
                str(record.record_id),
                record.method,
                record.path,
                record.model_dump_json(),
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

    def _apply_log_record(
        self, runtime: BackendComponent.ContextProperty, record: HttpRequestLogRecord,
        *, line_number: int,
    ) -> AgentRuntimeAttemptRecord | None:
        from src.detours.detour_ai_augment.src.backend import api

        from .ai_augment_context import AiAugmentBackendContext

        applied: AgentRuntimeAttemptRecord | None = None
        with self._transaction() as conn:
            self._insert_projected_http_record(record, line_number=line_number)
            record = self.http_record_with_ordinal(record.record_id)[1]
            if (record.method, record.path) == (api.HTTP_POST_METHOD, VALIDATE_PATH):
                applied, commit_database = api._apply_validation_record(
                    self, cast(AiAugmentBackendContext, runtime), record,
                )
                if not commit_database:
                    conn.execute("ROLLBACK")
                    conn.execute("BEGIN TRANSACTION")
                    self._insert_projected_http_record(record, line_number=line_number)
                self._insert_attempt_record(applied)
        # Publication is outside the committed DB transaction in both live and replay.
        # Failure leaves the durable validation intact for recovery, never a new verdict.
        if (record.method, record.path) == (api.HTTP_POST_METHOD, VALIDATE_PATH):
            api.publish_card_zip(self, cast(AiAugmentBackendContext, runtime), record.record_id)
        return applied

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

    def query_mappings(
        self, sql: str, parameters: Sequence[object] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        with self._reading():
            self._check_sql(sql)
            result = self._detour_db.connection.execute(sql, parameters)
            columns = tuple(column[0] for column in result.description)
            return tuple(dict(zip(columns, row, strict=True)) for row in result.fetchall())

    def execute(self, sql: str, parameters: Sequence[object] | None = None) -> ExecuteResult:
        with self._reading():
            self._check_sql(sql)
            rows = self._detour_db.connection.execute(sql, parameters).fetchall()
            return ExecuteResult(rows)

    def materialize_innerdicts(self, *, source_relation: str, table_name: str) -> None:
        with self._lock:
            self._raise_if_failed()
            if not self._transaction_active:
                raise RuntimeError("Materialization requires a Store write transaction")
            materialize_innerdicts_from_rows_table(
                self._detour_db.connection, source_relation=source_relation, table_name=table_name,
            )
