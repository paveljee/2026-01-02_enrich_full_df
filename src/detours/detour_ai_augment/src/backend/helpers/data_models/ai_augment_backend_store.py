from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime, timezone
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
    ControlCentreComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.aivm_audit import (
    _AivmAuditError,
    aivm_connection_options,
    audit_configuration,
    audit_configuration_for_session,
    read_appendwatch_bytes,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_detour_db import (  # noqa: E501
    AiAugmentDetourDB,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.post_commit_validation import (  # noqa: E501
    PostCommitValidation,
    _AppliedRetryAuditRow,
    _CommitConfigFacts,
    _CommitEvaluationInputs,
    _DetourDbValidationReads,
    _RetryBaselineRow,
    _RolloutIndex,
    _ValidationProjection,
    evaluate_commit,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.replay_log import (  # noqa: E501
    ReplayLogRegisteredResource,
    _ReplayProjectionConflictError,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AUTHORITATIVE_ATTEMPT_COMMIT_REQUEST_RECORD_ID_COLUMN,
    AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN,
    AUTHORITATIVE_ATTEMPT_VALIDATION_ID_KEY,
    AUTHORITATIVE_ATTEMPTS_TABLE,
    AUTHORITATIVE_EMPTY_OFFSET,
    AUTHORITATIVE_FIRST_LINE,
    AUTHORITATIVE_RECORD_ID_COLUMN,
    AUTHORITATIVE_RECORD_METHOD_COLUMN,
    AUTHORITATIVE_RECORD_ORDINAL_COLUMN,
    AUTHORITATIVE_RECORD_PATH_COLUMN,
    AUTHORITATIVE_RECORD_PAYLOAD_COLUMN,
    AUTHORITATIVE_RECORDS_TABLE,
    BASE64_TEXT_ENCODING,
    CODEX_CALL_ID_COL,
    CODEX_CALLS_TABLE,
    CODEX_CITE_TEXT_COL,
    CODEX_CITE_TOKENS_COL,
    CODEX_EVIDENCE_ACCEPTED_COL,
    CODEX_EVIDENCE_APPLIED_COL,
    CODEX_EVIDENCE_ASSESSMENT_COL,
    CODEX_EVIDENCE_AUDIT_ID_COL,
    CODEX_EVIDENCE_AUDIT_TABLE,
    CODEX_EVIDENCE_SUBMISSION_COL,
    CODEX_FC_ARGUMENTS_COL,
    CODEX_FC_ID_COL,
    CODEX_FC_NAME_COL,
    CODEX_FC_NAMESPACE_COL,
    CODEX_FC_TABLE,
    CODEX_FC_TIMESTAMP_COL,
    CODEX_FCO_ID_COL,
    CODEX_FCO_TABLE,
    CODEX_FCO_TIMESTAMP_COL,
    CODEX_ID_COL,
    CODEX_INNERDICT_TABLE,
    CODEX_OUTPUT_ROWS_TABLE,
    CODEX_OUTPUT_SCHEMA,
    CODEX_OUTPUT_VIEW,
    CODEX_REF_DOMAIN_COL,
    CODEX_REF_ID_COL,
    CODEX_REF_SNIPPET_COL,
    CODEX_REF_THUMBNAIL_URL_COL,
    CODEX_REF_TITLE_COL,
    CODEX_REF_URL_COL,
    CODEX_RETRY_ATTEMPT_ID_COL,
    CODEX_RETRY_BASELINE_COL,
    CODEX_RETRY_BASELINE_TABLE,
    CODEX_RETRY_CREATED_AT_COL,
    CODEX_RETRY_NAMEKEY_COL,
    CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL,
    CODEX_RETRY_SESSION_ID_COL,
    CODEX_ROLLOUT_FILENAME_COL,
    CODEX_TURN_REF_NORMALIZED_VIEW,
    CODEX_TURN_REF_TABLE,
    CREATE_AUTHORITATIVE_ATTEMPTS_TABLE_SQL,
    CREATE_AUTHORITATIVE_RECORDS_TABLE_SQL,
    CUMULATIVE_KEY_SEPARATOR,
    HTTP_CONTENT_TYPE_HEADER,
    HTTP_GET_METHOD,
    HTTP_POST_METHOD,
    ISO_8601_UTC_OFFSET,
    ISO_8601_UTC_SUFFIX,
    KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL,
    KTP_AI_AUGMENT_COMMIT_REQUEST_RECORD_ID_COL,
    KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL,
    KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_RECORD_COL,
    KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL,
    MILLISECONDS_PER_SECOND,
    NANOSECONDS_PER_MICROSECOND,
    PULL_PATH,
    PUSH_PATH,
    SOURCE_KEY_HEADER,
    SYNTHETIC_COMMIT_HOST,
    SYNTHETIC_COMMIT_SCHEME,
    TEXT_ENCODING,
    VALIDATION_BODY_COMMIT_REQUEST_RECORD_KEY,
    VALIDATION_BODY_INITIAL_VALIDATION_REQUEST_RECORD_KEY,
    VALIDATION_BODY_OPENALEX_ROR_RECORDS_KEY,
    VALIDATION_BODY_POST_COMMIT_VALIDATION_KEY,
    VALIDATION_COMMIT_PULL_RESPONSE_RECORD_KEY,
    VALIDATION_COMMIT_PUSH_RESPONSE_RECORD_KEY,
    VALIDATION_COMMIT_SELF_HTTP_RECORD_KEY,
    ContentType,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.validation_request import (
    VALIDATE_PATH,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome_event import (  # noqa: E501
    NAME_KEY_HEADER,
    RUN_OUTCOME_PATHS,
    RunOutcome,
    RunOutcomePath,
    RunOutcomeRequestRecord,
)
from src.detours.detour_ai_augment.src.shared import (
    name_key_from_header_value,
    source_key_from_header_value,
    source_key_header_value,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models import InnerDict, NameKey
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
    redact_http_request_log_query,
)
from src.helpers.duckdb_utils import duckdb_quote_identifier, materialize_innerdicts_from_rows_table
from src.helpers.jsonlines import loads_jsonlines
from src.helpers.name_matching import normalized_tokens_sql
from src.helpers.vars import (
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
    KTP_INNERDICT_JSONLINES_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
)

from ....control_centre.dashboard.helpers.data_models.query_event import (
    QueryRequestRecord,
    QueryResponseRecord,
)
from ....control_centre.dashboard.helpers.data_models.run_outcome_event import (
    RunOutcomeResponseRecord,
)
from .ai_augment_cas import AiAugmentCAS, CASCodexRolloutRecord
from .ai_augment_context import AiAugmentBackendContext
from .ai_augment_singular_outer_dict import AiAugmentSingularOuterDict
from .codex_innerdict import CodexInnerDict, _CodexInnerDictProcedure
from .commit_request import (
    COMMIT_PATH,
    AppendwatchReportEncoding,
    AppendwatchReportRecord,
    BackendCommitRequestRecord,
    CodexRolloutRecord,
    CodexSessionRecord,
    CommitRequestBody,
    _synthetic_commit_request_record,
)
from .lifecycle import BackendLifecycle
from .model_http_interceptor import (
    ModelHttpInterceptor,
    ModelHttpRequired,
    ReplayInputMissing,
    record_key,
    request_body,
    request_key,
)
from .pull_event import PullResponseRecord
from .push_event import PushRequestRecord, PushResponseRecord
from .response_record_promise import (
    BackendStoreAcknowledgment,
    BackendStoreException,
    ResponseRecordPromise,
)
from .validation_request import BackendValidationRequestRecord, ValidationRequestBody

StoreMode = Literal["writable", "read_only"]
type ReplayedLifecycleRecord = (
    PullResponseRecord | PushResponseRecord | BackendCommitRequestRecord
    | BackendValidationRequestRecord | RunOutcomeResponseRecord
)
logger = logging.getLogger(__name__)
# Literally empty file, like `printf "" | sha256sum`
EMPTY_LOG_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class _ReplayCommitInvalidError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class _ReplayRecordContourInvalidError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(Locale.REPLAY_RECORD_CONTOUR_INVALID)


class _ReplayCommitLinkMissingError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(Locale.REPLAY_COMMIT_LINK_MISSING)


class _ReplayLogLineInvalidError(RuntimeError):
    def __init__(self, line_number: int) -> None:
        super().__init__(
            Locale.REPLAY_LOG_LINE_INVALID_TEMPLATE.format(line_number=line_number)
        )


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
    _context: AiAugmentBackendContext | None = PrivateAttr(default=None)
    _next_line_number: int = PrivateAttr(default=1)
    _log_offset: int = PrivateAttr(default=0)
    _transaction_active: bool = PrivateAttr(default=False)
    _reading_active: bool = PrivateAttr(default=False)
    _rebuilding: bool = PrivateAttr(default=False)
    _failure: BaseException | None = PrivateAttr(default=None)
    _loop: asyncio.AbstractEventLoop | None = PrivateAttr(default=None)
    _append_offset: int = PrivateAttr(default=0)
    _append_ordinal: int = PrivateAttr(default=0)
    _current_replayed_record: ReplayedLifecycleRecord | None = PrivateAttr(default=None)

    @property
    def context(self) -> AiAugmentBackendContext:
        if self._context is None:
            raise RuntimeError(Locale.STORE_CONTEXT_UNAVAILABLE)
        return self._context

    @property
    def current_replayed_record(self) -> ReplayedLifecycleRecord | None:
        return self._current_replayed_record

    def _reset_current_replayed_record(self) -> None:
        self._current_replayed_record = None

    def ai_augment_singular_outerdicts(self) -> tuple[AiAugmentSingularOuterDict, ...]:
        context = self._context
        if context is None:
            raise RuntimeError(Locale.STORE_CONTEXT_UNAVAILABLE)
        with self._reading():
            committed_by_namekey: dict[str, list[CodexInnerDict]] = {}
            for committed in self._codex_innerdicts():
                namekey = committed.run_outcome_response_record.run_outcome_request_record.namekey
                if namekey is None:
                    raise _ReplayProjectionConflictError
                committed_by_namekey.setdefault(namekey.to_json_key(), []).append(
                    committed,
                )
            selected: list[AiAugmentSingularOuterDict] = []
            for blueprint in context.ai_augment_singular_outerdict_blueprints:
                namekey = blueprint.namekey
                selected.append(AiAugmentSingularOuterDict(
                    namekey=namekey,
                    xlsx_innerdicts=blueprint.xlsx_innerdicts,
                    ssn_innerdicts=blueprint.ssn_innerdicts,
                    docx_innerdicts=blueprint.docx_innerdicts,
                    codex_innerdicts=tuple(
                        committed_by_namekey.get(namekey.to_json_key(), ())
                    ),
                    ai_augment_rnd=blueprint.ai_augment_rnd,
                    ai_augment_cohort=blueprint.ai_augment_cohort,
                    ai_augment_ineligibility_category=(
                        blueprint.ai_augment_ineligibility_category
                    ),
                ))
            return tuple(selected)

    def configured_ai_augment_singular_outerdict(
        self,
    ) -> AiAugmentSingularOuterDict | None:
        context = self._context
        if context is None:
            raise RuntimeError(Locale.STORE_CONTEXT_UNAVAILABLE)
        return context.configured_ai_augment_singular_outerdict()

    def _remember_reconstructed_record(
        self,
        record: HttpRequestLogRecord,
    ) -> None:
        if isinstance(record, PullResponseRecord) and record.response_code == HTTPStatus.OK:
            assert not isinstance(
                self._current_replayed_record,
                (PushResponseRecord, BackendCommitRequestRecord),
            )
            self._current_replayed_record = record
        elif isinstance(record, PushResponseRecord) and record.response_code == HTTPStatus.ACCEPTED:
            self._current_replayed_record = record
        elif isinstance(record, (BackendCommitRequestRecord, BackendValidationRequestRecord)):
            self._current_replayed_record = record
        elif isinstance(record, RunOutcomeResponseRecord) and record.response_code == HTTPStatus.OK:
            self._current_replayed_record = record

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
        context: AiAugmentBackendContext | None = None,
    ) -> Generator[Self, None, None]:
        self._require_closed()
        self._raise_if_failed()
        with self._replay_log._locked(append_allowed=mode == "writable"):
            self._mode = mode
            self._context = context
            try:
                with self._lock:
                    verified_anchor = self._verify_log_projection()
                    if mode == "writable":
                        self._replay_log._preflight_append()
                        if verified_anchor is not None:
                            with self._transaction():
                                self._write_anchor(verified_anchor)
                            logger.info(Locale.REPLAY_ACCEPTED_HASH_LOG,
                                        verified_anchor.sha256, verified_anchor.ordinal,
                                        verified_anchor.byte_offset)
                self.ai_augment_singular_outerdicts()
                if context is not None and context.configured_namekey is not None:
                    self.configured_ai_augment_singular_outerdict()
                yield self
                self._raise_if_failed()
            finally:
                self._context = None
                self._mode = None

    @contextmanager
    def _writable(self, context: AiAugmentBackendContext) -> Generator[Self, None, None]:
        """Continue a known-clean DB; reconstruction is explicit, never implicit."""
        with self._opened("writable", context) as store:
            yield store

    @contextmanager
    def _read_only(self, context: AiAugmentBackendContext) -> Generator[Self, None, None]:
        with self._opened("read_only", context) as store:
            yield store

    def _rebuild_from_log(
        self,
        context: AiAugmentBackendContext,
        *,
        reset_confirmed: bool,
        confirm_replay: Callable[[], bool] = lambda: False,
    ) -> None:

        if not reset_confirmed:
            raise ValueError(Locale.STORE_RESET_CONFIRMATION_REQUIRED)
        with self._lock:
            self._require_closed()
            with self._replay_log._locked(append_allowed=False):
                # Only explicit --new can reconstruct; refusal precedes any DB deletion.
                self._replay_log.verify_hash()
                size = self._replay_log._size()
                if size and not confirm_replay():
                    raise ValueError(Locale.REPLAY_CONFIRMATION_REQUIRED)
                if not size and self._replay_log.hash != EMPTY_LOG_SHA256:
                    raise ValueError(Locale.REPLAY_EMPTY_HASH_INVALID)
                path = self._detour_db.path
                protected_paths = (context.pipeline_config.db_file, Path(self._replay_log))
                if path.is_symlink() or any(
                    path.resolve() == protected.resolve()
                    or (path.exists() and protected.exists() and path.samefile(protected))
                    for protected in protected_paths
                ):
                    raise ValueError(Locale.STORE_DB_ISOLATION_REQUIRED)
                self._failure = None
                self._mode = "read_only"
                self._context = context
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
                    logger.info(Locale.REPLAY_NEW_DB_LOG, total, size)
                    self._next_line_number = 1
                    self._log_offset = 0
                    self._append_offset = 0
                    self._append_ordinal = 0
                    self._reset_current_replayed_record()
                    for ordinal, line in enumerate(self._replay_log._lines(), start=1):
                        logger.info(Locale.REPLAY_LINE_LOG, ordinal, total)
                        try:
                            record = self._authoritative_log_records(line)[0][0]
                            self._append_ordinal = ordinal
                            self._append_offset += len(line)
                            reconstructed = self._replay_durable_record(
                                record, ordinal=ordinal, raw_line=line,
                            )
                            self._remember_reconstructed_record(reconstructed)
                        except Exception:
                            logger.exception(Locale.REPLAY_RECORD_FAILED_LOG, ordinal)
                            raise
                    with self._transaction():
                        self._write_anchor(_ReplayAnchor(
                            sha256=self._replay_log.hash, ordinal=total,
                            byte_offset=self._log_offset,
                        ))
                    logger.info(Locale.REPLAY_COMPLETE_LOG,
                                self._replay_log.hash, total, self._log_offset)
                except BaseException as exc:
                    self._failure = exc
                    raise
                finally:
                    self._rebuilding = False
                    self._context = None
                    self._mode = None

    @contextmanager
    def _threading_lock(self) -> Generator[Self, None, None]:
        self._require_writable()
        with self._lock:
            self._raise_if_failed()
            yield self

    def _response_record_for_http(
        self, record: HttpRequestLogRecord,
    ) -> HttpRequestLogRecord:
        current = self._current_replayed_record
        if (record.method, record.path) == (HTTP_GET_METHOD, PULL_PATH):
            prior = None
            if record.response_code == HTTPStatus.OK:
                if isinstance(current, BackendValidationRequestRecord):
                    prior = current
                elif isinstance(current, PullResponseRecord):
                    prior = current.validation_request_record
            return PullResponseRecord.from_http_request_log_record(
                http_request_log_record=record,
                validation_request_record=prior,
            )
        if (record.method, record.path) == (HTTP_POST_METHOD, PUSH_PATH):
            pull_ref = current if isinstance(current, PullResponseRecord) else None
            return PushResponseRecord.from_http_request_log_record(
                http_request_log_record=record,
                pull_response_record=pull_ref,
            )
        return record

    @staticmethod
    def _initial_validation_for_commit(
        commit: BackendCommitRequestRecord,
    ) -> BackendValidationRequestRecord | None:
        pull = commit.commit_request_body.pull_response_record
        assert isinstance(pull, PullResponseRecord)
        prior = pull.validation_request_record
        if prior is None:
            return None
        return prior.validation_request_body.initial_validation_request_record or prior

    def _validation_from_cursor(self) -> BackendValidationRequestRecord | None:
        current = self._current_replayed_record
        if isinstance(current, BackendValidationRequestRecord):
            return current
        if isinstance(current, PullResponseRecord):
            return current.validation_request_record
        if isinstance(current, PushResponseRecord):
            pull = current.pull_response_record
            return None if pull is None else pull.validation_request_record
        if isinstance(current, BackendCommitRequestRecord):
            commit_pull = current.commit_request_body.pull_response_record
            assert isinstance(commit_pull, PullResponseRecord)
            return commit_pull.validation_request_record
        if isinstance(current, RunOutcomeResponseRecord):
            attempt = current.attempt
            assert attempt is None or isinstance(attempt, BackendValidationRequestRecord)
            return attempt
        return None

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
        # This follows the request ACK boundary: readback failure cannot undo fsync.
        durable = tuple(self._replay_log._lines(offset=self._append_offset - len(line)))
        if durable != (line,):
            raise RuntimeError(Locale.STORE_DURABLE_APPEND_MISMATCH)
        return self._authoritative_log_records(durable[0])[0][0]

    def _assert_lifecycle_links(
        self,
        record: HttpRequestLogRecord,
        previous: ReplayedLifecycleRecord | None,
    ) -> None:
        if isinstance(record, PullResponseRecord):
            expected = None
            if record.response_code == HTTPStatus.OK:
                if isinstance(previous, BackendValidationRequestRecord):
                    expected = previous
                elif isinstance(previous, PullResponseRecord):
                    expected = previous.validation_request_record
            assert record.validation_request_record is expected
        elif isinstance(record, PushResponseRecord):
            assert record.pull_response_record is (
                previous if isinstance(previous, PullResponseRecord) else None
            )
        elif isinstance(record, BackendCommitRequestRecord):
            assert isinstance(previous, PushResponseRecord)
            assert record.commit_request_body.pull_response_record is previous.pull_response_record
            assert record.commit_request_body.push_response_record is previous
        elif isinstance(record, BackendValidationRequestRecord):
            assert isinstance(previous, BackendCommitRequestRecord)
            body = record.validation_request_body
            assert body.commit_request_record is previous
            assert body.initial_validation_request_record is (
                self._initial_validation_for_commit(previous)
            )
        elif isinstance(record, RunOutcomeResponseRecord):
            assert record.attempt is (
                self._validation_from_cursor()
                if record._body().validation_record_id is not None
                else None
            )

    def _append_authoritative_record(self, record: HttpRequestLogRecord) -> HttpRequestLogRecord:
        with self._threading_lock():
            try:
                record = self._response_record_for_http(record)
                previous = self._current_replayed_record
                stored, ordinal, line = self._append_request(record)
                reconstructed = self._replay_durable_record(
                    self._read_appended_record(line), ordinal=ordinal, raw_line=line
                )
                if self._http_record(stored.record_id).model_dump(
                    mode="json",
                ) != record.model_dump(mode="json"):
                    raise RuntimeError(Locale.STORE_RECONSTRUCTION_AUTHORITATIVE_MISMATCH)
                if (
                    reconstructed is record
                    or type(reconstructed) is not type(record)
                    or reconstructed != record
                ):
                    raise RuntimeError(Locale.STORE_RECONSTRUCTION_ORIGINAL_MISMATCH)
                self._assert_lifecycle_links(record, previous)
                self._remember_reconstructed_record(reconstructed)
                advances = (
                    isinstance(reconstructed, PullResponseRecord)
                    and reconstructed.response_code == HTTPStatus.OK
                ) or (
                    isinstance(reconstructed, PushResponseRecord)
                    and reconstructed.response_code == HTTPStatus.ACCEPTED
                ) or isinstance(
                    reconstructed, (BackendCommitRequestRecord, BackendValidationRequestRecord)
                ) or (
                    isinstance(reconstructed, RunOutcomeResponseRecord)
                    and reconstructed.response_code == HTTPStatus.OK
                )
                if advances:
                    assert self._current_replayed_record is reconstructed
                else:
                    assert self._current_replayed_record is previous
                return reconstructed
            except BaseException as exc:
                self._failure = exc
                raise

    def promise_pull_response_record(
        self,
        request: BackendComponent.PullRequestRecordProperty,
    ) -> ResponseRecordPromise[PullResponseRecord]:
        with self._lock:
            before_append = self._append_ordinal
            try:
                http_record = self._append_authoritative_record(
                    HttpRequestLogRecord(**request.http_request_log_record.model_dump(mode="python")),
                )
                assert isinstance(http_record, PullResponseRecord)
                return ResponseRecordPromise[PullResponseRecord]._resolved(
                    BackendStoreAcknowledgment.ACK,
                    (http_record, None),
                )
            except Exception as exc:
                self._failure = exc
                return ResponseRecordPromise[PullResponseRecord]._resolved(
                    (BackendStoreAcknowledgment.ACK if self._append_ordinal > before_append
                     else BackendStoreAcknowledgment.NAK),
                    (None, BackendStoreException._from_exception(exc)),
                )

    def promise_push_response_record(
        self,
        request: BackendComponent.PushRequestRecordProperty,
        *,
        session_id: UUID | None,
    ) -> tuple[
        PushResponseRecord | None,
        ResponseRecordPromise[PushResponseRecord],
    ]:
        with self._lock:
            before_append = self._append_ordinal
            try:
                captured_push_request_http_record = HttpRequestLogRecord(
                    **request.http_request_log_record.model_dump(mode="python")
                )
                push_response_record = self._append_authoritative_record(
                    captured_push_request_http_record
                )
                assert isinstance(push_response_record, PushResponseRecord)
            except Exception as exc:
                self._failure = exc
                return None, ResponseRecordPromise[PushResponseRecord]._resolved(
                    (BackendStoreAcknowledgment.ACK if self._append_ordinal > before_append
                     else BackendStoreAcknowledgment.NAK),
                    (None, BackendStoreException._from_exception(exc)),
                )
            try:
                push_request_record = PushRequestRecord.model_validate(
                    request, from_attributes=True
                )
                if push_response_record.response_code != HTTPStatus.ACCEPTED:
                    return (
                        push_response_record,
                        ResponseRecordPromise[PushResponseRecord]._resolved(
                            BackendStoreAcknowledgment.ACK,
                            (push_response_record, None),
                        ),
                    )
                if self._loop is None:
                    raise RuntimeError(Locale.PUSH_SERVER_LOOP_REQUIRED)
                return push_response_record, ResponseRecordPromise[PushResponseRecord]._start(
                    BackendStoreAcknowledgment.ACK,
                    lambda: self._process_push(push_request_record, session_id=session_id),
                    self._loop,
                )
            except Exception as exc:
                self._failure = exc
                return push_response_record, ResponseRecordPromise[PushResponseRecord]._resolved(
                    BackendStoreAcknowledgment.ACK,
                    (None, BackendStoreException._from_exception(exc)),
                )

    def _capture_push_commit(
        self, request: PushRequestRecord, *, session_id: UUID | None,
    ) -> BackendCommitRequestRecord:
        context = self.context
        push = self._current_replayed_record
        if (
            session_id is None
            or context.configured_namekey is None
            or not isinstance(push, PushResponseRecord)
            or push.record_id != request.record_id
            or push.pull_response_record is None
        ):
            raise RuntimeError(Locale.PUSH_LINKAGE_MISSING)
        pull = push.pull_response_record
        configuration = audit_configuration_for_session(session_id)
        assert configuration.rollout_relative_path is not None
        logger.info(Locale.PUSH_CAPTURE_START_LOG, request.record_id, session_id)
        try:
            rollout: CodexRolloutRecord = context.pipeline_config.rollout_cas.copy_rollout(
                rollout_relative_path=configuration.rollout_relative_path,
                ssh_target=configuration.ssh_target,
                ssh_options=aivm_connection_options(
                    lima_ssh_config=configuration.lima_ssh_config,
                    identity_file=configuration.identity_file,
                    known_hosts_file=configuration.known_hosts_file,
                    ssh_user=configuration.ssh_user,
                    host_key_alias=configuration.host_key_alias,
                ),
            )
        except (OSError, ValueError) as exc:
            raise _AivmAuditError(str(exc)) from exc
        report_bytes = read_appendwatch_bytes(configuration)
        logger.info(
            Locale.PUSH_CAPTURE_COMPLETE_LOG,
            request.record_id,
            rollout.sha256,
            rollout.size,
            rollout.line_count,
            len(report_bytes),
        )
        commit = _synthetic_commit_request_record(
            pull_response_record=pull,
            push_response_record=push,
            session_id=session_id,
            rollout=rollout,
            rollout_filename=configuration.rollout_relative_path.name,
            appendwatch_report=report_bytes,
            namekey=context.configured_namekey,
        )
        assert commit.commit_request_body.pull_response_record is pull
        assert commit.commit_request_body.push_response_record is push
        return commit

    def capture_run_outcome_snapshot(
        self, session_id: UUID | None,
    ) -> tuple[CodexSessionRecord, str | None, tuple[Exception, ...]]:
        rollout_record: CodexRolloutRecord | None = None
        rollout_filename: str | None = None
        appendwatch_report: bytes | None = None
        failures: list[Exception] = []

        if session_id is not None:
            try:
                configuration = audit_configuration_for_session(session_id)
                assert configuration.rollout_relative_path is not None
                rollout_record = self.context.pipeline_config.rollout_cas.copy_rollout(
                    ssh_target=configuration.ssh_target,
                    rollout_relative_path=configuration.rollout_relative_path,
                    ssh_options=aivm_connection_options(
                        lima_ssh_config=configuration.lima_ssh_config,
                        identity_file=configuration.identity_file,
                        known_hosts_file=configuration.known_hosts_file,
                        ssh_user=configuration.ssh_user,
                        host_key_alias=configuration.host_key_alias,
                    ),
                )
                rollout_filename = configuration.rollout_relative_path.name
            except (OSError, ValueError, _AivmAuditError) as exc:
                failures.append(exc)

        try:
            report_configuration = audit_configuration(report_only=True)
            appendwatch_report = read_appendwatch_bytes(report_configuration)
        except (OSError, _AivmAuditError) as exc:
            failures.append(exc)

        session = CodexSessionRecord(
            session_id=session_id,
            codex_rollout_record=rollout_record,
            appendwatch_report_record=(
                None if appendwatch_report is None else AppendwatchReportRecord(
                    encoding=AppendwatchReportEncoding.BASE64,
                    data=base64.b64encode(appendwatch_report).decode(BASE64_TEXT_ENCODING),
                )
            ),
        )
        return session, rollout_filename, tuple(failures)

    def _process_push(
        self, request: PushRequestRecord, *, session_id: UUID | None,
    ) -> PushResponseRecord:
        """Actual push/commit/validation cycle entrypoint."""

        try:
            context = self._context
            if context is None:
                raise RuntimeError(Locale.STORE_CONTEXT_UNAVAILABLE)
            accepted_push = self._current_replayed_record
            if (
                not isinstance(accepted_push, PushResponseRecord)
                or accepted_push.record_id != request.record_id
            ):
                raise RuntimeError(Locale.REPLAY_COMMIT_PUSH_MISMATCH)
            assert isinstance(accepted_push, PushResponseRecord)
            commit = self._capture_push_commit(request, session_id=session_id)
            stored_commit = self._append_authoritative_record(commit)
            logger.info(
                Locale.PUSH_COMMIT_PERSISTED_LOG,
                request.record_id,
                stored_commit.record_id,
            )
            attempt = self._validate_commit(stored_commit.record_id)
            validation_ref = self._current_replayed_record
            if not isinstance(validation_ref, BackendValidationRequestRecord):
                raise RuntimeError(Locale.PUSH_RESULT_LINKAGE_INVALID)
            commit_ref = validation_ref.validation_request_body.commit_request_record
            if (
                attempt is not validation_ref
                or commit_ref.record_id != stored_commit.record_id
            ):
                raise RuntimeError(Locale.PUSH_RESULT_LINKAGE_INVALID)
            assert attempt is validation_ref
            assert commit_ref.commit_request_body.push_response_record is accepted_push
            assert commit_ref.commit_request_body.pull_response_record is (
                accepted_push.pull_response_record
            )
            return accepted_push
        except Exception as exc:
            with self._lock:
                self._failure = exc
            raise

    def query_response_record(
        self,
        request: ControlCentreComponent.BackendPort.QueryRequestRecordProperty,
    ) -> ResponseRecordPromise[QueryResponseRecord]:
        try:
            selected = QueryRequestRecord.model_validate(request, from_attributes=True)
            response = QueryResponseRecord.from_query_request(
                selected,
                ai_augment_singular_outerdicts=self.ai_augment_singular_outerdicts(),
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

    def run_outcome_response_record(
        self,
        request: ControlCentreComponent.BackendPort.RunOutcomeRequestRecordProperty,
        *,
        codex_session_record: CodexSessionRecord,
        rollout_filename: str | None,
    ) -> ResponseRecordPromise[RunOutcomeResponseRecord]:
        try:
            selected = RunOutcomeRequestRecord.model_validate(request, from_attributes=True)
            with self._threading_lock():
                if isinstance(
                    self._current_replayed_record,
                    (PushResponseRecord, BackendCommitRequestRecord),
                ):
                    raise RuntimeError(Locale.RUN_OUTCOME_BEFORE_VALIDATION)
                record = self._construct_run_outcome_response_record(
                    selected, codex_session_record=codex_session_record,
                    rollout_filename=rollout_filename,
                )
                response = self._append_authoritative_record(record)
                if not isinstance(response, RunOutcomeResponseRecord):
                    raise RuntimeError(Locale.STORE_RUN_OUTCOME_RECONSTRUCTION_MISSING)
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

    def _construct_run_outcome_response_record(
        self,
        request: RunOutcomeRequestRecord,
        *,
        codex_session_record: CodexSessionRecord,
        rollout_filename: str | None,
    ) -> RunOutcomeResponseRecord:
        code, headers, pull_id, push_id, commit_id, validation_id, attempt = (
            self._run_outcome_response_parts(
                request,
                codex_session_record=codex_session_record,
                rollout_filename=rollout_filename,
            )
        )
        response = RunOutcomeResponseRecord.from_run_outcome_request_record(
            request,
            response_code=code,
            response_headers=headers,
            pull_record_id=pull_id,
            push_record_id=push_id,
            commit_request_record_id=commit_id,
            validation_record_id=validation_id,
            codex_session_record=codex_session_record,
            ready_to_respond_at_unix_usec=time.time_ns() // NANOSECONDS_PER_MICROSECOND,
            attempt=attempt,
        )
        assert response.run_outcome_request_record is request
        return response

    def _http_record(self, record_id: UUID) -> HttpRequestLogRecord:

        self._require_open()
        with self._lock:
            return self._http_record_with_ordinal(record_id)[1]

    def _recorded_model_http(
        self,
        request: requests.PreparedRequest,
        **kwargs: Any,
    ) -> HttpRequestLogRecord:

        key = request_key(request)
        rows = self._execute(
            f"SELECT {AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
            f"FROM {AUTHORITATIVE_RECORDS_TABLE} "
            f"ORDER BY {AUTHORITATIVE_RECORD_ORDINAL_COLUMN} DESC"
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
            assert self._context is not None
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

    def _validate_commit(self, commit_id: UUID) -> BackendValidationRequestRecord:
        from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_mixin import (  # noqa: E501
            submission_http_context,
        )
        self._require_writable()
        assert self._context is not None
        while True:
            missing: ModelHttpRequired | None = None
            with self._lock:
                existing = self._execute(
                    f"SELECT {AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN} "
                    f"FROM {AUTHORITATIVE_ATTEMPTS_TABLE} "
                    f"WHERE {AUTHORITATIVE_ATTEMPT_COMMIT_REQUEST_RECORD_ID_COLUMN} = ?",
                    [str(commit_id)],
                ).fetchone()
                current = self._current_replayed_record
                validation = self._validation_from_cursor()
                commit = (
                    current if isinstance(current, BackendCommitRequestRecord)
                    else None if validation is None
                    else validation.validation_request_body.commit_request_record
                )
                if commit is None or commit.record_id != commit_id:
                    raise RuntimeError(Locale.VALIDATION_CURRENT_RECONSTRUCTED_COMMIT_REQUIRED)
                if existing is not None:
                    if validation is None:
                        raise RuntimeError(Locale.PERSISTED_ATTEMPT_CURRENT_VALIDATION_MISSING)
                    self._assert_attempt_projection(
                        existing[0],
                        commit_request_record=commit,
                        validation_request_record=validation,
                    )
                    assert self._current_replayed_record is validation
                    return validation
                if not isinstance(current, BackendCommitRequestRecord):
                    raise RuntimeError(Locale.VALIDATION_CURRENT_RECONSTRUCTED_COMMIT_REQUIRED)
                initial_ref = self._initial_validation_for_commit(commit)
                http = ModelHttpInterceptor(record_get=self._recorded_model_http)
                try:
                    with submission_http_context(http):
                        inputs, db_reads = self._validated_commit_inputs(
                            commit,
                            initial_validation_request_record=initial_ref,
                        )
                        evaluated, projection = evaluate_commit(
                            commit,
                            initial_validation_request_record=initial_ref,
                            inputs=inputs,
                            db_reads=db_reads,
                        )
                        assert projection.commit_request_record is commit
                except ModelHttpRequired as exc:
                    missing = exc
                # Preparation is read-only; missing provider responses can be
                # captured while the logged push/commit projection stays intact.
            if missing is not None:
                self._capture_model_http(missing)
                continue
            body = ValidationRequestBody(
                commit_request_record=commit,
                post_commit_validation=evaluated,
                initial_validation_request_record=initial_ref,
                openalex_ror_records=tuple(
                    self._http_record(record_id) for record_id in http.record_ids
                ),
            )
            assert body.commit_request_record is commit
            assert body.initial_validation_request_record is initial_ref
            self._append_authoritative_record(body.http_record())
            # Return the applied, serialized result, not the speculative evaluation.
            with self._lock:
                row = self._execute(
                    f"SELECT {AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN} "
                    f"FROM {AUTHORITATIVE_ATTEMPTS_TABLE} "
                    f"WHERE {AUTHORITATIVE_ATTEMPT_COMMIT_REQUEST_RECORD_ID_COLUMN} = ?",
                    [str(commit_id)],
                ).fetchone()
                if row is None:
                    raise RuntimeError(Locale.VALIDATION_RESULT_NOT_APPLIED)
                validation = self._validation_from_cursor()
                if validation is None:
                    raise RuntimeError(Locale.APPLIED_ATTEMPT_CURRENT_VALIDATION_MISSING)
                self._assert_attempt_projection(
                    row[0],
                    commit_request_record=commit,
                    validation_request_record=validation,
                )
                assert self._current_replayed_record is validation
                return validation

    def _write_anchor(self, anchor: _ReplayAnchor) -> None:
        # Table comments are transactional metadata, not a separate checkpoint table.
        if not self._transaction_active:
            raise RuntimeError(Locale.STORE_ANCHOR_TRANSACTION_REQUIRED)
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
            raise ValueError(Locale.REPLAY_ANCHOR_MISSING)
        anchor = _ReplayAnchor.model_validate_json(row[0])
        # Missing legacy columns fail here without migration or mutation.
        rows = self._execute(
            "SELECT record_ordinal, raw_line_sha256 FROM detour_http_records "
            "ORDER BY record_ordinal"
        ).fetchall()
        size = self._replay_log._size()
        logger.info(
            Locale.REPLAY_VERIFY_LOG,
            anchor.sha256, anchor.ordinal, anchor.byte_offset, self._replay_log.hash, size,
        )
        if anchor.byte_offset > size or anchor.ordinal > len(rows):
            raise ValueError(Locale.REPLAY_PREFIX_TRUNCATED)
        prefix = hashlib.sha256()
        offset = 0
        ordinal = 0
        boundary_seen = anchor.ordinal == 0 and anchor.byte_offset == 0
        if boundary_seen and anchor.sha256 != EMPTY_LOG_SHA256:
            raise ValueError(Locale.REPLAY_EMPTY_ANCHOR_HASH_MISMATCH)
        logger.info(Locale.REPLAY_VERIFY_PREFIX_LOG, anchor.ordinal, anchor.byte_offset)
        if boundary_seen:
            logger.info(Locale.REPLAY_PREFIX_HASH_MATCH_LOG)
        for ordinal, line in enumerate(self._replay_log._lines(), start=1):
            if ordinal > anchor.ordinal:
                logger.info(Locale.REPLAY_VERIFY_SUFFIX_LINE_LOG, ordinal)
            if not line.endswith(b"\n") or not line.strip():
                raise ValueError(Locale.REPLAY_LINE_INVALID_JSONL_TEMPLATE.format(ordinal=ordinal))
            if ordinal > len(rows) or rows[ordinal - 1][0] != ordinal:
                raise ValueError(
                    Locale.REPLAY_LINE_DB_RECORD_MISSING_TEMPLATE.format(ordinal=ordinal)
                )
            digest = rows[ordinal - 1][1]
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(
                    Locale.REPLAY_LINE_RAW_HASH_MISSING_TEMPLATE.format(ordinal=ordinal)
                )
            offset += len(line)
            if ordinal <= anchor.ordinal:
                prefix.update(line)
                if ordinal == anchor.ordinal:
                    if offset != anchor.byte_offset or prefix.hexdigest() != anchor.sha256:
                        raise ValueError(
                            Locale.REPLAY_PREFIX_MISMATCH_TEMPLATE.format(
                                ordinal=ordinal, offset=offset,
                            )
                        )
                    boundary_seen = True
                    logger.info(Locale.REPLAY_PREFIX_HASH_MATCH_LOG)
            elif hashlib.sha256(line).hexdigest() != digest:
                raise ValueError(
                    Locale.REPLAY_LINE_RAW_HASH_MISMATCH_TEMPLATE.format(ordinal=ordinal)
                )
        if not boundary_seen or ordinal != len(rows) or offset != size:
            raise ValueError(Locale.REPLAY_COVERAGE_MISMATCH)
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
        logger.info(Locale.REPLAY_COVERAGE_VERIFIED_LOG,
                    ordinal, offset)
        return verified_anchor

    def _raise_if_failed(self) -> None:
        if self._failure is not None:
            raise RuntimeError(
                Locale.STORE_FAILED_REBUILD_REQUIRED
            ) from self._failure

    def _require_closed(self) -> None:
        if self._mode is not None:
            raise RuntimeError(Locale.STORE_ALREADY_OPEN)

    def _require_writable(self) -> None:
        if self._mode != "writable":
            raise RuntimeError(Locale.STORE_WRITABLE_CONTEXT_REQUIRED)

    def _require_open(self) -> None:
        if self._mode is None:
            raise RuntimeError(Locale.STORE_CONTEXT_REQUIRED)

    def _initialize_http_record_schema(self) -> None:

        self._execute(CREATE_AUTHORITATIVE_RECORDS_TABLE_SQL)
        self._execute(CREATE_AUTHORITATIVE_ATTEMPTS_TABLE_SQL)

    def _http_record_with_ordinal(
        self,
        record_id: UUID,
    ) -> tuple[int, HttpRequestLogRecord]:

        row = self._execute(
            f"SELECT {AUTHORITATIVE_RECORD_ORDINAL_COLUMN}, "
            f"{AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
            f"FROM {AUTHORITATIVE_RECORDS_TABLE} "
            f"WHERE {AUTHORITATIVE_RECORD_ID_COLUMN} = ?",
            [str(record_id)],
        ).fetchone()
        if row is None:
            raise _ReplayCommitLinkMissingError
        try:
            return int(row[0]), self._validated_http_record(
                HttpRequestLogRecord.model_validate_json(str(row[1]))
            )
        except ValidationError as exc:
            raise _ReplayCommitLinkMissingError from exc

    def _insert_projected_http_record(
        self,
        record: HttpRequestLogRecord,
        *,
        line_number: int,
        raw_line: bytes,
    ) -> None:

        conn = self._detour_db.connection
        conn.execute(
            f"INSERT INTO {AUTHORITATIVE_RECORDS_TABLE} VALUES (?, ?, ?, ?, ?, ?)",
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
        validation_request_record: BackendValidationRequestRecord,
    ) -> None:

        conn = self._detour_db.connection
        conn.execute(
            f"INSERT INTO {AUTHORITATIVE_ATTEMPTS_TABLE} VALUES (?, ?)",
            [
                str(validation_request_record.validation_request_body.commit_request_record.record_id),
                json.dumps(
                    {
                        AUTHORITATIVE_ATTEMPT_VALIDATION_ID_KEY:
                        str(validation_request_record.record_id)
                    }
                ),
            ],
        )

    def _replay_durable_record(
        self,
        record: HttpRequestLogRecord,
        *,
        ordinal: int,
        raw_line: bytes,
    ) -> HttpRequestLogRecord:
        previous = self._current_replayed_record
        reconstructed = self._apply_durable_record(
            record, ordinal=ordinal, raw_line=raw_line,
        )
        persisted = self._http_record(record.record_id)
        if persisted.model_dump(mode="json") != record.model_dump(mode="json"):
            raise RuntimeError(Locale.STORE_PROJECTION_REPLAY_MISMATCH)
        self._assert_lifecycle_links(reconstructed, previous)
        return reconstructed

    def _apply_durable_record(
        self,
        record: HttpRequestLogRecord,
        *,
        ordinal: int,
        raw_line: bytes,
    ) -> HttpRequestLogRecord:
        from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome_event import (  # noqa: E501
            RUN_OUTCOME_PATHS,
        )

        context = self._context
        if context is None:
            raise RuntimeError(Locale.STORE_CONTEXT_UNAVAILABLE)
        with self._transaction():
            self._insert_projected_http_record(record, line_number=ordinal, raw_line=raw_line)
            record = self._http_record(record.record_id)
            if (record.method, record.path) == (HTTP_POST_METHOD, COMMIT_PATH):
                push_ref = self._current_replayed_record
                if (
                    not isinstance(push_ref, PushResponseRecord)
                    or push_ref.response_code != HTTPStatus.ACCEPTED
                ):
                    raise ValueError(Locale.REPLAY_COMMIT_PUSH_MISMATCH)
                pull_ref = push_ref.pull_response_record
                if pull_ref is None:
                    raise ValueError(Locale.REPLAY_COMMIT_PUSH_MISMATCH)
                refs: dict[UUID, PullResponseRecord | PushResponseRecord] = {
                    pull_ref.record_id: pull_ref,
                    push_ref.record_id: push_ref,
                }
                commit = BackendCommitRequestRecord.from_http_request_log_record(
                    record,
                    resolve_http_record=lambda record_id: refs[record_id],
                )
                if (
                    commit.commit_request_body.pull_response_record is not pull_ref
                    or commit.commit_request_body.push_response_record is not push_ref
                ):
                    raise ValueError(Locale.REPLAY_COMMIT_PUSH_MISMATCH)
                reconstructed: HttpRequestLogRecord = commit
            elif (record.method, record.path) == (HTTP_POST_METHOD, VALIDATE_PATH):
                commit_ref = self._current_replayed_record
                if not isinstance(commit_ref, BackendCommitRequestRecord):
                    raise ValueError(Locale.REPLAY_VALIDATION_COMMIT_MISMATCH)
                if record.request_body is None:
                    raise ValueError(Locale.VALIDATION_BODY_MISSING)
                parsed = json.loads(record.request_body)
                initial_ref = self._initial_validation_for_commit(commit_ref)
                body = ValidationRequestBody(
                    commit_request_record=commit_ref,
                    post_commit_validation=PostCommitValidation.model_validate(
                        parsed[VALIDATION_BODY_POST_COMMIT_VALIDATION_KEY], strict=False,
                    ),
                    initial_validation_request_record=initial_ref,
                    openalex_ror_records=tuple(
                        HttpRequestLogRecord.model_validate(value, strict=False)
                        for value in parsed[VALIDATION_BODY_OPENALEX_ROR_RECORDS_KEY]
                    ),
                )
                self._apply_validation_record(
                    record,
                    body=body,
                    parsed=parsed,
                    commit_ref=commit_ref,
                    initial_ref=initial_ref,
                )
                validation = BackendValidationRequestRecord.from_http_request_log_record(
                    record,
                    validation_request_body=body,
                )
                assert validation.validation_request_body is body
                if body.commit_request_record is not commit_ref:
                    raise ValueError(Locale.REPLAY_VALIDATION_COMMIT_MISMATCH)
                if body.initial_validation_request_record is not initial_ref:
                    raise ValueError(Locale.VALIDATION_INITIAL_LINK_INVALID)
                self._insert_attempt_record(validation)
                reconstructed = validation
            elif record.method == HTTP_POST_METHOD and record.path in RUN_OUTCOME_PATHS:
                if isinstance(
                    self._current_replayed_record,
                    (PushResponseRecord, BackendCommitRequestRecord),
                ):
                    raise ValueError(Locale.RUN_OUTCOME_BEFORE_VALIDATION)
                if record.response_body is None:
                    raise ValueError(Locale.RUN_OUTCOME_REPLAY_MISMATCH)
                outcome_body = RunOutcomeResponseRecord._parse_response_body(record.response_body)
                attempt_ref = (
                    self._validation_from_cursor()
                    if outcome_body.validation_record_id is not None else None
                )
                outcome = RunOutcomeResponseRecord.from_http_request_log_record(
                    record, attempt=attempt_ref,
                )
                if outcome._body().validation_record_id != (
                    None if attempt_ref is None else attempt_ref.record_id
                ):
                    raise ValueError(Locale.RUN_OUTCOME_REPLAY_MISMATCH)
                self._verify_run_outcome_record(outcome)
                self._apply_run_outcome_record(outcome)
                reconstructed = outcome
            else:
                if (record.method, record.path, record.response_code) == (
                    HTTP_POST_METHOD, PUSH_PATH, HTTPStatus.ACCEPTED,
                ):
                    if isinstance(
                        self._current_replayed_record,
                        (PushResponseRecord, BackendCommitRequestRecord),
                    ):
                        raise ValueError(Locale.REPLAY_ACCEPTED_PUSH_OVERLAP)
                    self._create_codex_schema(
                        codex_match_version=context.pipeline_config.match_rule_version.codex_match
                    )
                    self._create_codex_output_schema()
                reconstructed = self._response_record_for_http(record)
        self._next_line_number = ordinal + 1
        self._log_offset += len(raw_line)
        return reconstructed

    @contextmanager
    def _transaction(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Only Store application/evaluation/schema methods may open a write window."""
        with self._lock:
            self._require_open()
            self._raise_if_failed()
            if self._mode != "writable" and not self._rebuilding:
                raise RuntimeError(Locale.STORE_READ_ONLY)
            if self._transaction_active or self._reading_active:
                raise RuntimeError(Locale.STORE_NESTED_WRITE_TRANSACTION)
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
                            conn.execute("COMMIT")
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
    def _reading(self) -> Generator[None, None, None]:
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
            raise RuntimeError(Locale.STORE_SQL_SCOPE_INVALID)

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
                raise RuntimeError(Locale.STORE_MATERIALIZATION_TRANSACTION_REQUIRED)
            materialize_innerdicts_from_rows_table(
                self._detour_db.connection, source_relation=source_relation, table_name=table_name,
            )

    @staticmethod
    def _validated_http_record(record: HttpRequestLogRecord) -> HttpRequestLogRecord:
        validated = HttpRequestLogRecord.model_validate_json(record.model_dump_json())
        if (
            validated.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            or validated.record_id.version != 7
        ):
            raise _ReplayRecordContourInvalidError
        route = (validated.method, validated.path)
        if validated.method == HTTP_POST_METHOD and validated.path in RUN_OUTCOME_PATHS:
            try:
                RunOutcomeResponseRecord.from_http_request_log_record(validated)
            except ValueError as exc:
                raise _ReplayRecordContourInvalidError from exc
            return validated

        if route not in {
            (HTTP_POST_METHOD, COMMIT_PATH),
            (HTTP_POST_METHOD, VALIDATE_PATH),
        }:
            transport_failure = (
                validated.host != SYNTHETIC_COMMIT_HOST
                and route not in {
                    (HTTP_GET_METHOD, PULL_PATH), (HTTP_POST_METHOD, PUSH_PATH),
                }
                and validated.response_code is None
                and validated.response_headers is None
                and validated.response_body is None
            )
            if (
                not transport_failure and (validated.response_code is None
                or validated.response_headers is None
                or validated.response_body is None)
                or validated.ready_to_respond_at_unix_usec is None
                or validated.duration_usec is None
            ):
                raise _ReplayRecordContourInvalidError
            return validated
        if (
            validated.scheme != SYNTHETIC_COMMIT_SCHEME
            or validated.host != SYNTHETIC_COMMIT_HOST
            or validated.port is not None
            or validated.ready_to_respond_at_unix_usec is not None
            or validated.query
            or set(validated.request_headers) != {SOURCE_KEY_HEADER, NAME_KEY_HEADER}
            or not isinstance(validated.request_body, str)
            or validated.response_code is not None
            or validated.response_headers is not None
            or validated.response_body is not None
            or validated.received_at_unix_usec is not None
            or validated.duration_usec is not None
        ):
            raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_INVALID)
        if route == (HTTP_POST_METHOD, VALIDATE_PATH):
            return validated
        try:
            CommitRequestBody.validate_serialized_json(validated.request_body)
        except (ValidationError, ValueError) as exc:
            raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_INVALID) from exc
        return validated

    @classmethod
    def _authoritative_log_records(
        cls, value: bytes,
    ) -> tuple[tuple[HttpRequestLogRecord, int], ...]:
        records: list[tuple[HttpRequestLogRecord, int]] = []
        byte_offset = AUTHORITATIVE_EMPTY_OFFSET
        for line_number, line in enumerate(
            value.splitlines(keepends=True), start=AUTHORITATIVE_FIRST_LINE,
        ):
            if not line.endswith(b"\n") or not line.strip():
                raise _ReplayLogLineInvalidError(line_number)
            try:
                record = cls._validated_http_record(
                    HttpRequestLogRecord.model_validate_json(line)
                )
            except (
                ValidationError,
                _ReplayCommitInvalidError,
                _ReplayRecordContourInvalidError,
            ) as exc:
                raise _ReplayLogLineInvalidError(line_number) from exc
            byte_offset += len(line)
            records.append((record, byte_offset))
        return tuple(records)

    def _backend_commit_request_record(
        self,
        record: HttpRequestLogRecord,
    ) -> BackendCommitRequestRecord:
        commit, _validation = self._cursor_commit_validation()
        if (
            commit is None
            or commit.record_id != record.record_id
            or commit.http_request_log_record.model_dump(mode="json")
            != record.model_dump(mode="json")
        ):
            raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_INVALID)
        return commit

    @staticmethod
    def _parse_source_key_header(value: object) -> tuple[str, int]:
        try:
            return source_key_from_header_value(value)
        except ValueError as exc:
            raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_SOURCE_KEY_INVALID) from exc

    @staticmethod
    def _parse_name_key_header(value: object) -> NameKey:
        try:
            return name_key_from_header_value(value)
        except ValueError as exc:
            raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_NAME_KEY_INVALID) from exc

    @staticmethod
    def _namekey_from_original_pull_response_record(
        original_pull_response_record: PullResponseRecord,
    ) -> NameKey:
        content_type = next(
            (
                value.partition(";")[0].strip().casefold()
                for key, value in (original_pull_response_record.response_headers or {}).items()
                if key.casefold() == HTTP_CONTENT_TYPE_HEADER.casefold()
            ),
            None,
        )
        if (
            original_pull_response_record.response_code != HTTPStatus.OK
            or content_type != ContentType.NDJSON
            or not original_pull_response_record.response_body
        ):
            raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_PULL_INVALID)
        try:
            lines = tuple(
                json.loads(line)
                for line in original_pull_response_record.response_body.splitlines()
            )
            identity = next(
                line for line in reversed(lines)
                if isinstance(line, dict)
                and KTP_FIRST_NAME_COL in line and KTP_LAST_NAME_COL in line
            )
            return NameKey(**{
                KTP_FIRST_NAME_COL: identity[KTP_FIRST_NAME_COL],
                KTP_LAST_NAME_COL: identity[KTP_LAST_NAME_COL],
            })
        except (StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_PULL_INVALID) from exc

    def _validated_commit_inputs(
        self,
        commit_request_record: BackendCommitRequestRecord,
        *,
        initial_validation_request_record: BackendValidationRequestRecord | None,
    ) -> tuple[_CommitEvaluationInputs, _DetourDbValidationReads]:
        if self._current_replayed_record is not commit_request_record:
            raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_LINK_INVALID)
        record = commit_request_record
        body = commit_request_record.commit_request_body
        pull = body.pull_response_record
        push = body.push_response_record
        pull_ordinal, _ = self._http_record_with_ordinal(pull.record_id)
        push_ordinal, _ = self._http_record_with_ordinal(push.record_id)
        commit_ordinal, _ = self._http_record_with_ordinal(record.record_id)
        if not (
            pull_ordinal < push_ordinal < commit_ordinal
            and (pull.method, pull.path) == (HTTP_GET_METHOD, PULL_PATH)
            and pull.response_code == HTTPStatus.OK
            and (push.method, push.path) == (HTTP_POST_METHOD, PUSH_PATH)
            and push.response_code == HTTPStatus.ACCEPTED
            and isinstance(push.request_body, str)
        ):
            raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_LINK_INVALID)
        namekey = self._parse_name_key_header(record.request_headers.get(NAME_KEY_HEADER))
        initial_commit = (
            commit_request_record if initial_validation_request_record is None
            else initial_validation_request_record.validation_request_body.commit_request_record
        )
        original_pull_response_record = initial_commit.commit_request_body.pull_response_record
        assert isinstance(original_pull_response_record, PullResponseRecord)
        if (
            self._namekey_from_original_pull_response_record(original_pull_response_record)
            != namekey
        ):
            raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_NAME_KEY_INVALID)
        filename, source_line_count = self._parse_source_key_header(
            record.request_headers.get(SOURCE_KEY_HEADER)
        )
        rollout = body.codex_session_record.codex_rollout_record
        if rollout is None or source_line_count != rollout.line_count:
            raise _ReplayCommitInvalidError(Locale.REPLAY_COMMIT_SOURCE_KEY_INVALID)
        assert isinstance(push, PushResponseRecord)
        assert push.pull_response_record is pull
        context = self.context
        config = context.pipeline_config
        session_id = body.codex_session_record.session_id
        assert session_id is not None

        def draw_number() -> tuple[str | None, Exception | None]:
            try:
                blueprint = context.configured_ai_augment_singular_outerdict()
                if blueprint is None or blueprint.namekey != namekey:
                    return None, None
                assert any(
                    blueprint is item
                    for item in context.ai_augment_singular_outerdict_blueprints
                )
                return blueprint.draw_number, None
            except Exception as exc:
                return None, exc

        def cas_rollout() -> tuple[CASCodexRolloutRecord | None, Exception | None]:
            try:
                result = self.rollout_cas.validated_rollout(rollout)
                assert (
                    result.sha256 == rollout.sha256
                    and result.size == rollout.size
                    and result.line_count == rollout.line_count
                )
                return result, None
            except Exception as exc:
                return None, exc

        def retry_baseline_exists() -> tuple[bool | None, Exception | None]:
            try:
                return self._retry_baseline_exists(
                    original_pull=original_pull_response_record,
                    namekey=namekey,
                    session_id=session_id,
                ), None
            except Exception as exc:
                return None, exc

        def retry_baseline_row() -> tuple[_RetryBaselineRow | None, Exception | None]:
            try:
                row = self._retry_baseline_row(original_pull_response_record.record_id)
                return (None if row is None else _RetryBaselineRow(
                    namekey_json=row[0],
                    session_id_text=row[1],
                    attempt_id_text=row[2],
                    obligations_json=row[3],
                )), None
            except Exception as exc:
                return None, exc

        def applied_retry_audit_rows(
            baseline_attempt_id: UUID,
        ) -> tuple[tuple[_AppliedRetryAuditRow, ...] | None, Exception | None]:
            try:
                return tuple(
                    _AppliedRetryAuditRow(
                        submission_json=submission_json,
                        assessment_json=assessment_json,
                    )
                    for submission_json, assessment_json in self._applied_retry_audit_rows(
                        original_pull_record_id=original_pull_response_record.record_id,
                        baseline_attempt_id=baseline_attempt_id,
                    )
                ), None
            except Exception as exc:
                return None, exc

        def output_identity_exists() -> tuple[bool | None, Exception | None]:
            try:
                return self._codex_output_identity_exists({
                    KTP_FILENAME_COL: filename,
                    KTP_FRAGMENT_COL: rollout.line_count,
                }), None
            except Exception as exc:
                return None, exc

        inputs = _CommitEvaluationInputs(
            original_pull_response_record=original_pull_response_record,
            namekey=namekey,
            config_facts=_CommitConfigFacts(
                timezone_name=config.timezone,
                sample_seed=config.sample_seed,
                codex_match_version=config.match_rule_version.codex_match,
            ),
            draw_number=draw_number,
            cas_codex_rollout_record=cas_rollout,
        )
        assert inputs.original_pull_response_record is original_pull_response_record
        return inputs, _DetourDbValidationReads(
            retry_baseline_exists=retry_baseline_exists,
            retry_baseline_row=retry_baseline_row,
            applied_retry_audit_rows=applied_retry_audit_rows,
            output_identity_exists=output_identity_exists,
        )

    def _cursor_commit_validation(
        self,
    ) -> tuple[BackendCommitRequestRecord | None, BackendValidationRequestRecord | None]:
        current = self.current_replayed_record
        validation = self._validation_from_cursor()
        commit = (
            current if isinstance(current, BackendCommitRequestRecord) else
            None if validation is None else validation.validation_request_body.commit_request_record
        )
        return commit, validation

    def _assert_attempt_projection(
        self,
        value: str,
        *,
        commit_request_record: BackendCommitRequestRecord,
        validation_request_record: BackendValidationRequestRecord,
    ) -> None:
        payload = json.loads(value)
        if not isinstance(payload, dict) or set(payload) != {
            AUTHORITATIVE_ATTEMPT_VALIDATION_ID_KEY
        }:
            raise _ReplayProjectionConflictError
        validation_id = UUID(payload[AUTHORITATIVE_ATTEMPT_VALIDATION_ID_KEY])
        if (
            validation_request_record.record_id != validation_id
            or self._http_record(validation_id).model_dump(mode="json")
            != validation_request_record.http_request_log_record.model_dump(mode="json")
            or validation_request_record.validation_request_body.commit_request_record
            is not commit_request_record
            or validation_request_record.request_headers
            != commit_request_record.request_headers
        ):
            raise _ReplayProjectionConflictError

    def _apply_validation_record(
        self,
        record: HttpRequestLogRecord,
        *,
        body: ValidationRequestBody,
        parsed: Mapping[str, Any],
        commit_ref: BackendCommitRequestRecord,
        initial_ref: BackendValidationRequestRecord | None,
    ) -> None:
        from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_mixin import (  # noqa: E501
            submission_http_context,
        )
        assert body.commit_request_record is commit_ref
        assert body.initial_validation_request_record is initial_ref
        ordinal, _ = self._http_record_with_ordinal(record.record_id)
        embedded = parsed[VALIDATION_BODY_COMMIT_REQUEST_RECORD_KEY]
        embedded_commit = HttpRequestLogRecord.model_validate(
            embedded[VALIDATION_COMMIT_SELF_HTTP_RECORD_KEY], strict=False,
        )
        embedded_pull = HttpRequestLogRecord.model_validate(
            embedded[VALIDATION_COMMIT_PULL_RESPONSE_RECORD_KEY], strict=False,
        )
        embedded_push = HttpRequestLogRecord.model_validate(
            embedded[VALIDATION_COMMIT_PUSH_RESPONSE_RECORD_KEY], strict=False,
        )
        commit_ordinal, commit = self._http_record_with_ordinal(
            embedded_commit.record_id
        )
        if (
            self._current_replayed_record is not commit_ref
            or commit_ref.record_id != embedded_commit.record_id
            or commit_ordinal >= ordinal
            or record.request_headers != commit.request_headers
            or embedded_commit != commit
            or any(
                getattr(commit_ref, field) != getattr(embedded_commit, field)
                for field in HttpRequestLogRecord.model_fields
            )
            or any(
                getattr(commit_ref.commit_request_body.pull_response_record, field)
                != getattr(embedded_pull, field)
                or getattr(commit_ref.commit_request_body.push_response_record, field)
                != getattr(embedded_push, field)
                for field in HttpRequestLogRecord.model_fields
            )
        ):
            raise ReplayInputMissing(Locale.VALIDATION_COMMIT_LINK_INVALID)
        initial_value = parsed[VALIDATION_BODY_INITIAL_VALIDATION_REQUEST_RECORD_KEY]
        initial = (
            None if initial_value is None else
            HttpRequestLogRecord.model_validate(initial_value, strict=False)
        )
        if initial is not None:
            initial_ordinal, persisted = self._http_record_with_ordinal(initial.record_id)
            if initial_ordinal >= commit_ordinal or persisted != initial:
                raise ValueError(Locale.VALIDATION_INITIAL_LINK_INVALID)
        if (initial is None) != (initial_ref is None) or (
            initial is not None and initial_ref is not None and any(
                getattr(initial, field) != getattr(initial_ref, field)
                for field in HttpRequestLogRecord.model_fields
            )
        ):
            raise ReplayInputMissing(Locale.VALIDATION_INITIAL_LINK_INVALID)
        session_id = commit_ref.commit_request_body.codex_session_record.session_id
        namekey = name_key_from_header_value(commit.request_headers.get(NAME_KEY_HEADER))
        placeholders = ", ".join("?" for _path in RUN_OUTCOME_PATHS)
        outcomes = self._execute(
            f"SELECT {AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} FROM {AUTHORITATIVE_RECORDS_TABLE} "
            f"WHERE {AUTHORITATIVE_RECORD_METHOD_COLUMN} = ? "
            f"AND {AUTHORITATIVE_RECORD_PATH_COLUMN} IN ({placeholders})",
            [HTTP_POST_METHOD, *(path.value for path in sorted(RUN_OUTCOME_PATHS))],
        ).fetchall()
        for (payload,) in outcomes:
            outcome = RunOutcomeResponseRecord.from_http_request_log_record(
                HttpRequestLogRecord.model_validate_json(payload),
            )
            if (
                outcome.response_code not in {HTTPStatus.BAD_REQUEST, HTTPStatus.CONFLICT}
                and session_id is not None
                and outcome.run_outcome_request_record.namekey == namekey
                and outcome._codex_session_record().session_id == session_id
            ):
                raise ReplayInputMissing(Locale.VALIDATION_AFTER_OUTCOME)
        inputs: list[HttpRequestLogRecord] = []
        for captured in body.openalex_ror_records:
            input_ordinal, http_record = self._http_record_with_ordinal(captured.record_id)
            if (
                input_ordinal >= ordinal or http_record.ready_to_respond_at_unix_usec is None
                or captured != http_record
            ):
                raise ReplayInputMissing(Locale.VALIDATION_HTTP_INPUT_INVALID)
            inputs.append(http_record)
        http = ModelHttpInterceptor.from_records(inputs)
        with submission_http_context(http):
            evaluation_inputs, db_reads = self._validated_commit_inputs(
                commit_ref,
                initial_validation_request_record=initial_ref,
            )
            evaluated, projection = evaluate_commit(
                commit_ref,
                initial_validation_request_record=initial_ref,
                inputs=evaluation_inputs,
                db_reads=db_reads,
            )
        assert projection.commit_request_record is commit_ref
        observed = body.post_commit_validation
        if (
            evaluated != observed
            or http.record_ids != tuple(item.record_id for item in body.openalex_ror_records)
        ):
            raise ReplayInputMissing(Locale.VALIDATION_REPLAY_MISMATCH)
        self._project_validation(commit_ref, projection, accepted=(
            observed.result is BackendLifecycle.ACCEPTED
        ))

    def _project_validation(
        self,
        commit: BackendCommitRequestRecord,
        projection: _ValidationProjection,
        *,
        accepted: bool,
    ) -> None:
        assert commit is self._current_replayed_record
        assert projection.commit_request_record is commit
        index = projection.rollout_index
        if index is not None:
            assert self._context is not None
            self._persist_rollout_index(
                index,
                codex_match_version=self._context.pipeline_config.match_rule_version.codex_match,
            )
        if projection.submission_json is not None:
            if index is None:
                raise ReplayInputMissing(Locale.VALIDATION_REPLAY_MISMATCH)
            namekey = name_key_from_header_value(commit.request_headers.get(NAME_KEY_HEADER))
            attempt_timestamp = datetime.fromtimestamp(
                commit.record_id.time / MILLISECONDS_PER_SECOND,
                tz=timezone.utc,
            )
            self._project_retry_attempt(
                commit,
                projection,
                namekey=namekey,
                attempt_timestamp=attempt_timestamp,
            )
        elif (
            projection.assessment_json is not None or projection.applied is not None
            or projection.accepted is not None or projection.baseline_obligations_json is not None
        ):
            raise ReplayInputMissing(Locale.VALIDATION_REPLAY_MISMATCH)
        if projection.output_row is not None:
            if not accepted or projection.accepted is not True:
                raise ReplayInputMissing(Locale.VALIDATION_REPLAY_MISMATCH)
            self._append_codex_output(dict(projection.output_row))
        elif accepted:
            raise ReplayInputMissing(Locale.VALIDATION_REPLAY_MISMATCH)

    def _project_retry_attempt(
        self,
        commit: BackendCommitRequestRecord,
        projection: _ValidationProjection,
        *,
        namekey: NameKey,
        attempt_timestamp: datetime,
    ) -> None:
        assert projection.commit_request_record is commit
        submission_json = projection.submission_json
        assessment_json = projection.assessment_json
        applied = projection.applied
        accepted = projection.accepted
        if (
            submission_json is None or assessment_json is None
            or applied is None or accepted is None
        ):
            raise ReplayInputMissing(Locale.VALIDATION_REPLAY_MISMATCH)
        body = commit.commit_request_body
        pull = body.pull_response_record
        push = body.push_response_record
        assert isinstance(pull, PullResponseRecord)
        assert isinstance(push, PushResponseRecord)
        assert push.pull_response_record is pull
        session_id = body.codex_session_record.session_id
        assert session_id is not None
        if projection.baseline_obligations_json is not None and not self._insert_retry_baseline(
            original_pull_record_id=pull.record_id,
            namekey=namekey,
            session_id=session_id,
            attempt_id=commit.record_id,
            attempt_timestamp=attempt_timestamp,
            obligations_json=projection.baseline_obligations_json,
        ):
            raise _ReplayProjectionConflictError
        self._append_evidence_audit(
            attempt_id=commit.record_id,
            original_pull_record_id=pull.record_id,
            namekey=namekey,
            session_id=session_id,
            attempt_timestamp=attempt_timestamp,
            submission_json=submission_json,
            assessment_json=assessment_json,
            applied=applied,
            accepted=accepted,
        )

    def _next_codex_row_id(self, table_name: str) -> int:
        """Allocate from the maximum projected row ID in the active transaction."""
        row = self._execute(
            f"SELECT COALESCE(MAX(id), 0) + 1 FROM {duckdb_quote_identifier(table_name)}"
        ).fetchone()
        assert row is not None
        return int(row[0])

    def _insert_or_validate(
        self,
        *,
        table_name: str,
        key_column: str,
        key_value: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
    ) -> None:
        projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
        existing = self._execute(
            f"SELECT {projection} FROM {table_name} "
            f"WHERE {duckdb_quote_identifier(key_column)} = ?",
            [key_value],
        ).fetchall()
        if existing:
            if len(existing) != 1 or existing[0] != values:
                raise ReplayInputMissing(
                    Locale.CUMULATIVE_ROW_CONFLICT_TEMPLATE.format(
                        table_name=table_name,
                        key_value=key_value,
                    )
                )
            return
        columns = (CODEX_ID_COL, *columns)
        values = (self._next_codex_row_id(table_name), *values)
        projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
        placeholders = ", ".join("?" for _column in columns)
        self._execute(
            f"INSERT INTO {table_name} ({projection}) VALUES ({placeholders})",
            list(values),
        )

    @staticmethod
    def _datetime_value(timestamp: str) -> datetime:
        return datetime.fromisoformat(timestamp.replace(ISO_8601_UTC_SUFFIX, ISO_8601_UTC_OFFSET))

    def _retry_baseline_exists(
        self,
        *,
        original_pull: PullResponseRecord,
        namekey: NameKey,
        session_id: UUID,
    ) -> bool:
        row = self._execute(
            f"""
            SELECT
                {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)}
            FROM {CODEX_RETRY_BASELINE_TABLE}
            WHERE {duckdb_quote_identifier(CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL)} = ?
            """,
            [str(original_pull.record_id)],
        ).fetchone()
        if row is None:
            return False
        if row != (namekey.to_json_key(), str(session_id)):
            raise ReplayInputMissing(Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH)
        return True

    def _applied_retry_audit_rows(
        self,
        *,
        original_pull_record_id: UUID,
        baseline_attempt_id: UUID,
    ) -> tuple[tuple[str, str], ...]:
        rows: list[tuple[str, str]] = self._execute(
            f"""
            SELECT
                {duckdb_quote_identifier(CODEX_EVIDENCE_SUBMISSION_COL)},
                {duckdb_quote_identifier(CODEX_EVIDENCE_ASSESSMENT_COL)}
            FROM {CODEX_EVIDENCE_AUDIT_TABLE}
            WHERE {duckdb_quote_identifier(CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL)} = ?
              AND {duckdb_quote_identifier(CODEX_EVIDENCE_APPLIED_COL)}
              AND {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)} <> ?
            ORDER BY {duckdb_quote_identifier(CODEX_EVIDENCE_AUDIT_ID_COL)}
            """,
            [str(original_pull_record_id), str(baseline_attempt_id)],
        ).fetchall()
        return tuple(rows)

    def _insert_retry_baseline(
        self,
        *,
        original_pull_record_id: UUID,
        namekey: NameKey,
        session_id: UUID,
        attempt_id: UUID,
        attempt_timestamp: datetime,
        obligations_json: str,
    ) -> bool:
        return self._execute(
            f"""
            INSERT INTO {CODEX_RETRY_BASELINE_TABLE} (
                {duckdb_quote_identifier(CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_CREATED_AT_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_BASELINE_COL)}
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            RETURNING {duckdb_quote_identifier(CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL)}
            """,
            [
                str(original_pull_record_id),
                namekey.to_json_key(),
                str(session_id),
                str(attempt_id),
                attempt_timestamp,
                obligations_json,
            ],
        ).fetchone() is not None

    def _retry_baseline_row(
        self, original_pull_record_id: UUID,
    ) -> tuple[str, str, str, str] | None:
        row: tuple[str, str, str, str] | None = self._execute(
            f"""
            SELECT
                {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_BASELINE_COL)}
            FROM {CODEX_RETRY_BASELINE_TABLE}
            WHERE {duckdb_quote_identifier(CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL)} = ?
            """,
            [str(original_pull_record_id)],
        ).fetchone()
        return row

    def _append_evidence_audit(
        self,
        *,
        attempt_id: UUID,
        original_pull_record_id: UUID,
        namekey: NameKey,
        session_id: UUID,
        attempt_timestamp: datetime,
        submission_json: str,
        assessment_json: str,
        applied: bool,
        accepted: bool,
    ) -> None:
        self._execute(
            f"""
            INSERT INTO {CODEX_EVIDENCE_AUDIT_TABLE} (
                {duckdb_quote_identifier(CODEX_EVIDENCE_AUDIT_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)},
                {duckdb_quote_identifier(CODEX_RETRY_CREATED_AT_COL)},
                {duckdb_quote_identifier(CODEX_EVIDENCE_SUBMISSION_COL)},
                {duckdb_quote_identifier(CODEX_EVIDENCE_ASSESSMENT_COL)},
                {duckdb_quote_identifier(CODEX_EVIDENCE_APPLIED_COL)},
                {duckdb_quote_identifier(CODEX_EVIDENCE_ACCEPTED_COL)}
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                self._next_codex_row_id(CODEX_EVIDENCE_AUDIT_TABLE),
                str(attempt_id),
                str(original_pull_record_id),
                namekey.to_json_key(),
                str(session_id),
                attempt_timestamp,
                submission_json,
                assessment_json,
                applied,
                accepted,
            ],
        )

    def _persist_rollout_index(
        self,
        rollout_index: _RolloutIndex,
        *,
        codex_match_version: int = 1,
    ) -> None:
        self._create_codex_schema(codex_match_version=codex_match_version)
        current_call_ids = {row.call_id for row in rollout_index.fc_rows}
        existing_call_rows: list[tuple[str]] = self._execute(
            f"SELECT {duckdb_quote_identifier(CODEX_CALL_ID_COL)} "
            f"FROM {CODEX_CALLS_TABLE} WHERE "
            f"{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?",
            [rollout_index.session.rollout_filename],
        ).fetchall()
        existing_call_ids = {
            row[0]
            for row in existing_call_rows
        }
        if not existing_call_ids.issubset(current_call_ids):
            raise ReplayInputMissing(Locale.PROVENANCE_PREFIX_OLDER)
        current_turn_keys = {(row.call_id, row.ref_id) for row in rollout_index.turn_ref_rows}
        existing_turn_rows: list[tuple[str, str]] = self._execute(
            f"SELECT "
            f"ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)}, "
            f"ts.{duckdb_quote_identifier(CODEX_REF_ID_COL)} "
            f"FROM {CODEX_TURN_REF_TABLE} ts "
            f"JOIN {CODEX_CALLS_TABLE} calls ON "
            f"calls.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} = "
            f"ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} "
            f"WHERE calls.{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?",
            [rollout_index.session.rollout_filename],
        ).fetchall()
        existing_turn_keys = {
            (row[0], row[1])
            for row in existing_turn_rows
        }
        if not existing_turn_keys.issubset(current_turn_keys):
            raise ReplayInputMissing(Locale.CITATION_PREFIX_OLDER)

        fc_by_call = {row.call_id: row for row in rollout_index.fc_rows}
        fco_by_call = {row.call_id: row for row in rollout_index.fco_rows}
        if set(fc_by_call) != current_call_ids or set(fco_by_call) != current_call_ids:
            raise ReplayInputMissing(Locale.ROLLOUT_LINKAGES_INCOMPLETE)
        for function_call_row in rollout_index.fc_rows:
            self._insert_or_validate(
                table_name=CODEX_FC_TABLE,
                key_column=CODEX_FC_ID_COL,
                key_value=function_call_row.fc_id,
                columns=(
                    CODEX_FC_TIMESTAMP_COL,
                    CODEX_FC_ID_COL,
                    CODEX_FC_NAME_COL,
                    CODEX_FC_NAMESPACE_COL,
                    CODEX_FC_ARGUMENTS_COL,
                ),
                values=(
                    self._datetime_value(function_call_row.timestamp),
                    function_call_row.fc_id,
                    function_call_row.name,
                    function_call_row.namespace,
                    function_call_row.arguments_json,
                ),
            )
        for function_output_row in rollout_index.fco_rows:
            self._insert_or_validate(
                table_name=CODEX_FCO_TABLE,
                key_column=CODEX_FCO_ID_COL,
                key_value=function_output_row.fco_id,
                columns=(CODEX_FCO_TIMESTAMP_COL, CODEX_FCO_ID_COL),
                values=(
                    self._datetime_value(function_output_row.timestamp),
                    function_output_row.fco_id,
                ),
            )
        for call_id in sorted(current_call_ids):
            fc_row = fc_by_call[call_id]
            fco_row = fco_by_call[call_id]
            self._insert_or_validate(
                table_name=CODEX_CALLS_TABLE,
                key_column=CODEX_CALL_ID_COL,
                key_value=call_id,
                columns=(
                    CODEX_CALL_ID_COL,
                    CODEX_FC_ID_COL,
                    CODEX_FCO_ID_COL,
                    CODEX_ROLLOUT_FILENAME_COL,
                ),
                values=(
                    call_id,
                    fc_row.fc_id,
                    fco_row.fco_id,
                    rollout_index.session.rollout_filename,
                ),
            )
        for turn_ref_row in rollout_index.turn_ref_rows:
            key_value = f"{turn_ref_row.call_id}{CUMULATIVE_KEY_SEPARATOR}{turn_ref_row.ref_id}"
            columns: tuple[str, ...] = (
                CODEX_REF_ID_COL,
                CODEX_CALL_ID_COL,
                CODEX_REF_DOMAIN_COL,
                CODEX_REF_SNIPPET_COL,
                CODEX_REF_THUMBNAIL_URL_COL,
                CODEX_REF_TITLE_COL,
                CODEX_REF_URL_COL,
                CODEX_CITE_TEXT_COL,
            )
            projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
            existing = self._execute(
                f"SELECT {projection} FROM {CODEX_TURN_REF_TABLE} WHERE "
                f"{duckdb_quote_identifier(CODEX_CALL_ID_COL)} = ? AND "
                f"{duckdb_quote_identifier(CODEX_REF_ID_COL)} = ?",
                [turn_ref_row.call_id, turn_ref_row.ref_id],
            ).fetchall()
            values: tuple[object, ...] = (
                turn_ref_row.ref_id,
                turn_ref_row.call_id,
                turn_ref_row.domain,
                turn_ref_row.snippet,
                turn_ref_row.thumbnail_url,
                turn_ref_row.title,
                turn_ref_row.url,
                turn_ref_row.cite_text,
            )
            if existing:
                if len(existing) != 1 or existing[0] != values:
                    raise ReplayInputMissing(
                        Locale.CUMULATIVE_ROW_CONFLICT_TEMPLATE.format(
                            table_name=CODEX_TURN_REF_TABLE,
                            key_value=key_value,
                        )
                    )
            else:
                columns = (CODEX_ID_COL, *columns)
                values = (self._next_codex_row_id(CODEX_TURN_REF_TABLE), *values)
                projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
                placeholders = ", ".join("?" for _column in columns)
                self._execute(
                    f"INSERT INTO {CODEX_TURN_REF_TABLE} ({projection}) VALUES ({placeholders})",
                    list(values),
                )

        integrity_checks = (
            (
                CODEX_FC_TABLE,
                duckdb_quote_identifier(CODEX_FC_ID_COL),
            ),
            (
                CODEX_FCO_TABLE,
                duckdb_quote_identifier(CODEX_FCO_ID_COL),
            ),
            (
                CODEX_CALLS_TABLE,
                duckdb_quote_identifier(CODEX_CALL_ID_COL),
            ),
            (
                CODEX_TURN_REF_TABLE,
                "("
                + duckdb_quote_identifier(CODEX_CALL_ID_COL)
                + ", "
                + duckdb_quote_identifier(CODEX_REF_ID_COL)
                + ")",
            ),
        )
        for table_name, distinct_expression in integrity_checks:
            integrity_row = self._execute(
                f"SELECT COUNT(*), COUNT(DISTINCT {distinct_expression}) FROM {table_name}"
            ).fetchone()
            if integrity_row is None:
                raise ReplayInputMissing(
                    Locale.PROVENANCE_INTEGRITY_QUERY_FAILED_TEMPLATE.format(table_name=table_name)
                )
            total, distinct = integrity_row
            if total != distinct:
                raise ReplayInputMissing(
                    Locale.PROVENANCE_UNIQUENESS_FAILED_TEMPLATE.format(table_name=table_name)
                )

        linkage_row = self._execute(
            f"""
            SELECT
                (
                    SELECT COUNT(*)
                    FROM {CODEX_CALLS_TABLE} calls
                    LEFT JOIN {CODEX_FC_TABLE} fc
                      ON fc.{duckdb_quote_identifier(CODEX_FC_ID_COL)} =
                         calls.{duckdb_quote_identifier(CODEX_FC_ID_COL)}
                    WHERE fc.{duckdb_quote_identifier(CODEX_ID_COL)} IS NULL
                ),
                (
                    SELECT COUNT(*)
                    FROM {CODEX_CALLS_TABLE} calls
                    LEFT JOIN {CODEX_FCO_TABLE} fco
                      ON fco.{duckdb_quote_identifier(CODEX_FCO_ID_COL)} =
                         calls.{duckdb_quote_identifier(CODEX_FCO_ID_COL)}
                    WHERE fco.{duckdb_quote_identifier(CODEX_ID_COL)} IS NULL
                ),
                (
                    SELECT COUNT(*)
                    FROM {CODEX_TURN_REF_TABLE} ts
                    LEFT JOIN {CODEX_CALLS_TABLE} calls
                      ON calls.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} =
                         ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)}
                    WHERE calls.{duckdb_quote_identifier(CODEX_ID_COL)} IS NULL
                )
            """
        ).fetchone()
        if linkage_row is None:
            raise ReplayInputMissing(Locale.PROVENANCE_LINKAGE_QUERY_FAILED)
        missing_fc_links, missing_fco_links, missing_call_links = linkage_row
        if missing_fc_links or missing_fco_links or missing_call_links:
            raise ReplayInputMissing(Locale.PROVENANCE_RELATIONSHIPS_INCOMPLETE)

        persisted_call_rows: list[tuple[str]] = self._execute(
            f"SELECT {duckdb_quote_identifier(CODEX_CALL_ID_COL)} "
            f"FROM {CODEX_CALLS_TABLE} WHERE "
            f"{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?",
            [rollout_index.session.rollout_filename],
        ).fetchall()
        persisted_call_ids = {row[0] for row in persisted_call_rows}
        persisted_turn_rows: list[tuple[str, str]] = self._execute(
            f"SELECT "
            f"ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)}, "
            f"ts.{duckdb_quote_identifier(CODEX_REF_ID_COL)} "
            f"FROM {CODEX_TURN_REF_TABLE} ts "
            f"JOIN {CODEX_CALLS_TABLE} calls ON "
            f"calls.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} = "
            f"ts.{duckdb_quote_identifier(CODEX_CALL_ID_COL)} "
            f"WHERE calls.{duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} = ?",
            [rollout_index.session.rollout_filename],
        ).fetchall()
        persisted_turn_keys = {
            (row[0], row[1])
            for row in persisted_turn_rows
        }
        if persisted_call_ids != current_call_ids or persisted_turn_keys != current_turn_keys:
            raise ReplayInputMissing(Locale.PROVENANCE_PREFIX_MISMATCH)

    def _create_codex_schema(self, *, codex_match_version: int = 1) -> None:
        id_col = duckdb_quote_identifier(CODEX_ID_COL)
        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {CODEX_FC_TABLE} (
                {id_col} BIGINT PRIMARY KEY,
                {duckdb_quote_identifier(CODEX_FC_TIMESTAMP_COL)} TIMESTAMPTZ NOT NULL,
                {duckdb_quote_identifier(CODEX_FC_ID_COL)} VARCHAR NOT NULL UNIQUE,
                {duckdb_quote_identifier(CODEX_FC_NAME_COL)} VARCHAR NOT NULL,
                {duckdb_quote_identifier(CODEX_FC_NAMESPACE_COL)} VARCHAR NOT NULL,
                {duckdb_quote_identifier(CODEX_FC_ARGUMENTS_COL)} JSON NOT NULL
            )
            """
        )
        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {CODEX_RETRY_BASELINE_TABLE} (
                {duckdb_quote_identifier(CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL)}
                    VARCHAR PRIMARY KEY,
                {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)} VARCHAR NOT NULL,
                {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)} VARCHAR NOT NULL,
                {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)} VARCHAR NOT NULL,
                {duckdb_quote_identifier(CODEX_RETRY_CREATED_AT_COL)} TIMESTAMPTZ NOT NULL,
                {duckdb_quote_identifier(CODEX_RETRY_BASELINE_COL)} JSON NOT NULL
            )
            """
        )
        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {CODEX_EVIDENCE_AUDIT_TABLE} (
                {duckdb_quote_identifier(CODEX_EVIDENCE_AUDIT_ID_COL)} BIGINT PRIMARY KEY,
                {duckdb_quote_identifier(CODEX_RETRY_ATTEMPT_ID_COL)} VARCHAR NOT NULL UNIQUE,
                {duckdb_quote_identifier(CODEX_RETRY_ORIGINAL_PULL_RECORD_ID_COL)} VARCHAR NOT NULL,
                {duckdb_quote_identifier(CODEX_RETRY_NAMEKEY_COL)} VARCHAR NOT NULL,
                {duckdb_quote_identifier(CODEX_RETRY_SESSION_ID_COL)} VARCHAR NOT NULL,
                {duckdb_quote_identifier(CODEX_RETRY_CREATED_AT_COL)} TIMESTAMPTZ NOT NULL,
                {duckdb_quote_identifier(CODEX_EVIDENCE_SUBMISSION_COL)} JSON NOT NULL,
                {duckdb_quote_identifier(CODEX_EVIDENCE_ASSESSMENT_COL)} JSON NOT NULL,
                {duckdb_quote_identifier(CODEX_EVIDENCE_APPLIED_COL)} BOOLEAN NOT NULL,
                {duckdb_quote_identifier(CODEX_EVIDENCE_ACCEPTED_COL)} BOOLEAN NOT NULL
            )
            """
        )
        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {CODEX_FCO_TABLE} (
                {id_col} BIGINT PRIMARY KEY,
                {duckdb_quote_identifier(CODEX_FCO_TIMESTAMP_COL)} TIMESTAMPTZ NOT NULL,
                {duckdb_quote_identifier(CODEX_FCO_ID_COL)} VARCHAR NOT NULL UNIQUE
            )
            """
        )
        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {CODEX_CALLS_TABLE} (
                {id_col} BIGINT PRIMARY KEY,
                {duckdb_quote_identifier(CODEX_CALL_ID_COL)} VARCHAR NOT NULL UNIQUE,
                {duckdb_quote_identifier(CODEX_FC_ID_COL)} VARCHAR NOT NULL UNIQUE,
                {duckdb_quote_identifier(CODEX_FCO_ID_COL)} VARCHAR NOT NULL UNIQUE,
                {duckdb_quote_identifier(CODEX_ROLLOUT_FILENAME_COL)} VARCHAR NOT NULL
            )
            """
        )
        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {CODEX_TURN_REF_TABLE} (
                {id_col} BIGINT PRIMARY KEY,
                {duckdb_quote_identifier(CODEX_REF_ID_COL)} VARCHAR NOT NULL,
                {duckdb_quote_identifier(CODEX_CALL_ID_COL)} VARCHAR NOT NULL,
                {duckdb_quote_identifier(CODEX_REF_DOMAIN_COL)} VARCHAR,
                {duckdb_quote_identifier(CODEX_REF_SNIPPET_COL)} VARCHAR,
                {duckdb_quote_identifier(CODEX_REF_THUMBNAIL_URL_COL)} VARCHAR,
                {duckdb_quote_identifier(CODEX_REF_TITLE_COL)} VARCHAR,
                {duckdb_quote_identifier(CODEX_REF_URL_COL)} VARCHAR NOT NULL,
                {duckdb_quote_identifier(CODEX_CITE_TEXT_COL)} VARCHAR NOT NULL,
                UNIQUE (
                    {duckdb_quote_identifier(CODEX_CALL_ID_COL)},
                    {duckdb_quote_identifier(CODEX_REF_ID_COL)}
                )
            )
            """
        )
        if codex_match_version == 2:
            self._execute(
                f"""
                CREATE OR REPLACE VIEW {CODEX_TURN_REF_NORMALIZED_VIEW} AS
                SELECT
                    *,
                    {normalized_tokens_sql(duckdb_quote_identifier(CODEX_CITE_TEXT_COL))}
                        AS {duckdb_quote_identifier(CODEX_CITE_TOKENS_COL)}
                FROM {CODEX_TURN_REF_TABLE}
                """
            )

    def _codex_output_identity_exists(self, row: Mapping[str, object]) -> bool:
        return self._execute(
            f"SELECT 1 FROM {CODEX_OUTPUT_ROWS_TABLE} WHERE "
            f"{duckdb_quote_identifier(KTP_FILENAME_COL)} = ? AND "
            f"{duckdb_quote_identifier(KTP_FRAGMENT_COL)} = ?",
            [row[KTP_FILENAME_COL], row[KTP_FRAGMENT_COL]],
        ).fetchone() is not None

    def _append_codex_output(
        self,
        row: Mapping[str, object],
    ) -> None:
        self._create_codex_output_schema()
        columns = tuple(column for column, _data_type in CODEX_OUTPUT_SCHEMA)
        projection = ", ".join(duckdb_quote_identifier(column) for column in columns)
        placeholders = ", ".join("?" for _column in columns)
        try:
            self._execute(
                f"INSERT INTO {CODEX_OUTPUT_ROWS_TABLE} ({projection}) VALUES ({placeholders})",
                [row[column] for column in columns],
            )
        except duckdb.ConstraintException as exc:
            raise ReplayInputMissing(Locale.ACCEPTED_IDENTITY_DUPLICATE) from exc

    def _create_codex_output_schema(self) -> None:
        definitions = ", ".join(
            f"{duckdb_quote_identifier(column)} {data_type}"
            for column, data_type in CODEX_OUTPUT_SCHEMA
        )
        self._execute(
            f"CREATE TABLE IF NOT EXISTS {CODEX_OUTPUT_ROWS_TABLE} ("
            f"{definitions}, UNIQUE ("
            f"{duckdb_quote_identifier(KTP_FILENAME_COL)}, "
            f"{duckdb_quote_identifier(KTP_FRAGMENT_COL)}))"
        )

    def _replace_codex_output_view(self) -> None:
        projection = ", ".join(
            duckdb_quote_identifier(column) for column, _data_type in CODEX_OUTPUT_SCHEMA
            if column not in {
                KTP_AI_AUGMENT_COMMIT_REQUEST_RECORD_ID_COL, KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL,
                KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL, KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL,
            }
        )
        self._execute(
            f"""
            CREATE OR REPLACE VIEW {CODEX_OUTPUT_VIEW} AS
            SELECT {projection}
            FROM {CODEX_OUTPUT_ROWS_TABLE}
            WHERE {duckdb_quote_identifier(KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL)} IS NOT NULL
              AND {duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL)} IS NOT NULL
            ORDER BY
                {duckdb_quote_identifier(KTP_FILENAME_COL)},
                {duckdb_quote_identifier(KTP_FRAGMENT_COL)},
                {duckdb_quote_identifier(KTP_AI_AUGMENT_COMMIT_REQUEST_RECORD_ID_COL)}
            """
        )
        self._materialize_innerdicts(
            source_relation=CODEX_OUTPUT_VIEW,
            table_name=CODEX_INNERDICT_TABLE,
        )

    def _check_run_outcome_references(
        self,
        commit: BackendCommitRequestRecord | None,
        validation: BackendValidationRequestRecord | None,
        *,
        namekey: NameKey,
        session_id: UUID,
    ) -> None:
        if validation is not None and (
            commit is None
            or validation.validation_request_body.commit_request_record.record_id
            != commit.record_id
        ):
            raise BackendStoreException(Locale.RUN_OUTCOME_VALIDATION_LINKAGE_CORRUPT)
        if commit is None:
            return
        commit_ordinal, persisted_commit = self._http_record_with_ordinal(commit.record_id)
        if (
            persisted_commit.model_dump() != commit.model_dump()
            or commit.commit_request_body.codex_session_record.session_id != session_id
            or name_key_from_header_value(commit.request_headers.get(NAME_KEY_HEADER)) != namekey
        ):
            raise BackendStoreException(Locale.RUN_OUTCOME_REPLAY_INPUTS_DIFFER)
        if validation is None:
            return
        validation_ordinal, persisted_validation = self._http_record_with_ordinal(
            validation.record_id
        )
        if (
            validation_ordinal <= commit_ordinal
            or validation.request_headers != commit.request_headers
            or persisted_validation.model_dump() != validation.model_dump()
        ):
            raise BackendStoreException(Locale.RUN_OUTCOME_VALIDATION_LINKAGE_CORRUPT)
        row = self._execute(
            f"SELECT {AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN} FROM {AUTHORITATIVE_ATTEMPTS_TABLE} "
            f"WHERE {AUTHORITATIVE_ATTEMPT_COMMIT_REQUEST_RECORD_ID_COLUMN} = ?",
            [str(commit.record_id)],
        ).fetchone()
        if row is None:
            raise BackendStoreException(Locale.RUN_OUTCOME_PROJECTION_INCONSISTENT)
        # Verify the explicit persisted inputs without reapplying derived effects.
        try:
            self._assert_attempt_projection(
                row[0],
                commit_request_record=commit,
                validation_request_record=validation,
            )
        except _ReplayProjectionConflictError as exc:
            raise BackendStoreException(Locale.RUN_OUTCOME_REPLAY_INPUTS_DIFFER) from exc
        for provider in validation.validation_request_body.openalex_ror_records:
            provider_ordinal, persisted = self._http_record_with_ordinal(provider.record_id)
            if persisted != provider or provider_ordinal >= validation_ordinal:
                raise BackendStoreException(Locale.RUN_OUTCOME_PROVIDER_INPUT_CORRUPT)

    @staticmethod
    def _run_outcome_identity_error(
        request: RunOutcomeRequestRecord,
        *,
        namekey: NameKey | None,
        session_id: UUID | None,
        validation: BackendValidationRequestRecord | None,
    ) -> str | None:
        if namekey is None or request.namekey is None or request.namekey != namekey:
            return Locale.RUN_OUTCOME_NAMEKEY_MISMATCH
        if session_id is None or request.session_id is None or request.session_id != session_id:
            return Locale.RUN_OUTCOME_SESSION_MISMATCH
        if SOURCE_KEY_HEADER in request.request_headers:
            return Locale.RUN_OUTCOME_HEADERS_INVALID
        if request.request_body not in (None, ""):
            return Locale.RUN_OUTCOME_BODY_UNEXPECTED
        if request.query:
            return Locale.RUN_OUTCOME_QUERY_UNEXPECTED
        if request.run_outcome is RunOutcome.COMPLETED and (
            validation is None or request.validation_request_record_id != validation.record_id
        ):
            return Locale.RUN_OUTCOME_ETAG_MISMATCH
        return None

    @staticmethod
    def _run_outcome_code(
        path: str,
        session: CodexSessionRecord,
        validation: BackendValidationRequestRecord | None,
    ) -> HTTPStatus:
        if (
            session.session_id is None
            or session.codex_rollout_record is None
            or session.appendwatch_report_record is None
        ):
            return HTTPStatus.INTERNAL_SERVER_ERROR
        accepted = validation is not None and (
            validation.validation_request_body.post_commit_validation.result
            is BackendLifecycle.ACCEPTED
        )
        if (path == RunOutcomePath.COMPLETED and not accepted) or (
            path == RunOutcomePath.FAILED and accepted
        ):
            return HTTPStatus.CONFLICT
        return HTTPStatus.OK

    def _cursor_http_ids(self) -> tuple[UUID | None, UUID | None]:
        current = self.current_replayed_record
        if isinstance(current, PullResponseRecord):
            return current.record_id, None
        if isinstance(current, PushResponseRecord):
            pull = current.pull_response_record
            return None if pull is None else pull.record_id, current.record_id
        if isinstance(current, BackendCommitRequestRecord):
            body = current.commit_request_body
            return body.pull_response_record.record_id, body.push_response_record.record_id
        if isinstance(current, BackendValidationRequestRecord):
            body = current.validation_request_body.commit_request_record.commit_request_body
            return body.pull_response_record.record_id, body.push_response_record.record_id
        if isinstance(current, RunOutcomeResponseRecord):
            outcome_body = current._body()
            return outcome_body.pull_record_id, outcome_body.push_record_id
        return None, None

    def _run_outcome_response_parts(
        self,
        request: RunOutcomeRequestRecord,
        *,
        codex_session_record: CodexSessionRecord,
        rollout_filename: str | None,
    ) -> tuple[
        HTTPStatus, Mapping[str, str] | None,
        UUID | None, UUID | None, UUID | None, UUID | None,
        BackendValidationRequestRecord | None,
    ]:
        context = self.context
        commit, validation = self._cursor_commit_validation()
        identity_error = self._run_outcome_identity_error(
            request, namekey=context.configured_namekey,
            session_id=codex_session_record.session_id, validation=validation,
        )
        if identity_error is None and validation is not None and (
            commit is None
            or validation.validation_request_body.commit_request_record.record_id
            != commit.record_id
        ):
            identity_error = Locale.RUN_OUTCOME_VALIDATION_LINKAGE_CORRUPT
        if identity_error is None and commit is not None and (
            commit.commit_request_body.codex_session_record.session_id != request.session_id
            or name_key_from_header_value(commit.request_headers.get(NAME_KEY_HEADER))
            != request.namekey
        ):
            identity_error = Locale.RUN_OUTCOME_REPLAY_INPUTS_DIFFER
        if identity_error is not None:
            logger.error(Locale.RUN_OUTCOME_REJECTED_LOG, request.path, identity_error)
        pull_record_id, push_record_id = self._cursor_http_ids()
        rollout = codex_session_record.codex_rollout_record
        headers = None
        if rollout is not None:
            if rollout_filename is None:
                raise BackendStoreException(Locale.RUN_OUTCOME_ROLLOUT_FILENAME_MISSING)
            headers = {
                SOURCE_KEY_HEADER: source_key_header_value(
                    rollout_filename, rollout.line_count,
                )
            }
        return (
            (
                HTTPStatus.BAD_REQUEST if identity_error is not None else
                self._run_outcome_code(request.path, codex_session_record, validation)
            ),
            headers,
            pull_record_id,
            push_record_id,
            None if commit is None else commit.record_id,
            None if validation is None else validation.record_id,
            validation,
        )

    def _verify_run_outcome_record(
        self,
        outcome: RunOutcomeResponseRecord,
    ) -> None:
        body = outcome._body()
        ordinal, _ = self._http_record_with_ordinal(outcome.record_id)
        validation = None
        if body.validation_record_id is not None:
            validation_ordinal, record = self._http_record_with_ordinal(body.validation_record_id)
            validation = outcome.attempt
            if (
                validation_ordinal >= ordinal
                or validation is None
                or validation is not self._validation_from_cursor()
                or validation.record_id != body.validation_record_id
                or validation.http_request_log_record.model_dump(mode="json")
                != record.model_dump(mode="json")
            ):
                raise ReplayInputMissing(Locale.RUN_OUTCOME_REPLAY_MISMATCH)
        elif outcome.attempt is not None:
            raise ReplayInputMissing(Locale.RUN_OUTCOME_REPLAY_MISMATCH)
        # A rejected client exchange is authoritative history, never derived acceptance.
        if outcome.response_code == HTTPStatus.BAD_REQUEST:
            return
        commit = None
        if body.commit_request_record_id is not None:
            commit_ordinal, record = self._http_record_with_ordinal(body.commit_request_record_id)
            if commit_ordinal >= ordinal:
                raise ReplayInputMissing(Locale.RUN_OUTCOME_REPLAY_MISMATCH)
            commit = self._backend_commit_request_record(record)
        request = outcome.run_outcome_request_record
        namekey = request.namekey
        session_id = body.codex_session_record.codex_session_id
        identity_error = self._run_outcome_identity_error(
            request, namekey=namekey, session_id=session_id, validation=validation,
        )
        if identity_error is not None:
            raise ReplayInputMissing(identity_error)
        assert namekey is not None and session_id is not None
        self._check_run_outcome_references(
            commit, validation, namekey=namekey, session_id=session_id,
        )
        if outcome.response_code != self._run_outcome_code(
            outcome.path, outcome._codex_session_record(), validation,
        ):
            raise ReplayInputMissing(Locale.RUN_OUTCOME_REPLAY_MISMATCH)

    def _apply_run_outcome_record(
        self,
        outcome: RunOutcomeResponseRecord,
    ) -> None:
        session_id = outcome._codex_session_record().session_id
        if (
            outcome.response_code != HTTPStatus.OK
            or outcome.run_outcome_request_record.run_outcome is not RunOutcome.COMPLETED
            or session_id is None
        ):
            return
        commit_request_record_id = outcome._body().commit_request_record_id
        if commit_request_record_id is None:
            raise ReplayInputMissing(Locale.RUN_OUTCOME_VALIDATION_LINKAGE_CORRUPT)
        exists = self._execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
            [CODEX_OUTPUT_ROWS_TABLE],
        ).fetchone()
        if exists is None or int(exists[0]) == 0:
            return
        namekey = outcome.run_outcome_request_record.namekey
        assert namekey is not None
        rows = self._execute(
            f"SELECT {duckdb_quote_identifier(KTP_AI_AUGMENT_COMMIT_REQUEST_RECORD_ID_COL)} "
            f"FROM {CODEX_OUTPUT_ROWS_TABLE} "
            f"WHERE {duckdb_quote_identifier(KTP_NAMEKEY_COL)} = ? "
            f"AND {duckdb_quote_identifier(KTP_AI_AUGMENT_COMMIT_REQUEST_RECORD_ID_COL)} = ? "
            f"AND {duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL)} IS NULL",
            [namekey.to_json_key(), str(commit_request_record_id)],
        ).fetchall()
        outcome_ordinal, _ = self._http_record_with_ordinal(outcome.record_id)
        updated = 0
        for (value,) in rows:
            commit_id = UUID(str(value))
            commit_ordinal, http_commit = self._http_record_with_ordinal(commit_id)
            commit = self._backend_commit_request_record(http_commit)
            if commit.commit_request_body.codex_session_record.session_id != session_id:
                continue
            if name_key_from_header_value(commit.request_headers.get(NAME_KEY_HEADER)) != namekey:
                raise ReplayInputMissing(Locale.RUN_OUTCOME_COMMIT_NAMEKEY_MISMATCH)
            linked = self._execute(
                f"SELECT json_extract_string({AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN}, "
                "'$.validation_record_id') "
                f"FROM {AUTHORITATIVE_ATTEMPTS_TABLE} "
                f"WHERE {AUTHORITATIVE_ATTEMPT_COMMIT_REQUEST_RECORD_ID_COLUMN} = ?",
                [str(commit_id)],
            ).fetchone()
            if linked is None or linked[0] is None:
                raise ReplayInputMissing(Locale.RUN_OUTCOME_ACCEPTED_ROW_VALIDATION_MISSING)
            validation_id = UUID(linked[0])
            validation_ordinal, http_validation = self._http_record_with_ordinal(
                validation_id
            )
            validation = self._validation_from_cursor()
            if (
                validation is None
                or validation.record_id != validation_id
                or validation.http_request_log_record.model_dump(mode="json")
                != http_validation.model_dump(mode="json")
                or validation.validation_request_body.commit_request_record is not commit
                or validation.request_headers != commit.request_headers
                or validation.validation_request_body.post_commit_validation.result
                is not BackendLifecycle.ACCEPTED
                or not commit_ordinal < validation_ordinal < outcome_ordinal
            ):
                raise ReplayInputMissing(Locale.RUN_OUTCOME_VALIDATION_LINKAGE_INVALID)
            self._execute(
                f"UPDATE {CODEX_OUTPUT_ROWS_TABLE} SET "
                f"{duckdb_quote_identifier(KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL)} = ?, "
                f"{duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL)} = ?, "
                f"{duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_RECORD_COL)} = ? "
                f"WHERE {duckdb_quote_identifier(KTP_AI_AUGMENT_COMMIT_REQUEST_RECORD_ID_COL)} = ?",
                [
                    str(validation.record_id), str(outcome.record_id),
                    json.dumps(outcome.serialize()), str(commit.record_id),
                ],
            )
            updated += 1
        if updated:
            self._replace_codex_output_view()
            logger.info(
                Locale.RUN_OUTCOME_MATERIALIZED_SECTIONS_LOG,
                outcome.record_id, updated,
            )

    def _codex_innerdicts(self) -> tuple[CodexInnerDict, ...]:
        exists = self._execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
            [CODEX_INNERDICT_TABLE],
        ).fetchone()
        if exists is None or int(exists[0]) == 0:
            return ()
        rows = self._execute(
            f"SELECT {duckdb_quote_identifier(KTP_NAMEKEY_COL)}, "
            f"{duckdb_quote_identifier(KTP_INNERDICT_JSONLINES_COL)} "
            f"FROM {CODEX_INNERDICT_TABLE} "
            f"ORDER BY {duckdb_quote_identifier(KTP_NAMEKEY_COL)}"
        ).fetchall()
        codex_innerdicts: list[CodexInnerDict] = []
        for namekey_json, payload in rows:
            try:
                for values in loads_jsonlines(payload):
                    outcome_json = values[KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_RECORD_COL]
                    if not isinstance(outcome_json, str):
                        raise ReplayInputMissing(Locale.RUN_OUTCOME_PROJECTION_INCONSISTENT)
                    codex_innerdicts.append(
                        CodexInnerDict(
                            innerdict=InnerDict.from_mapping(
                                {KTP_NAMEKEY_COL: namekey_json, **values},
                                _CodexInnerDictProcedure(),
                            ),
                            run_outcome_response_record=(
                                RunOutcomeResponseRecord.from_serialized_json(
                                    value=outcome_json,
                                )
                            ),
                        )
                    )
            except (
                KeyError,
                TypeError,
                ValidationError,
                ValueError,
                _ReplayCommitInvalidError,
                _ReplayRecordContourInvalidError,
            ) as exc:
                raise _ReplayProjectionConflictError from exc
        return tuple(codex_innerdicts)


@implements[BackendComponent.QueryOnlyStoreProperty]()
class AiAugmentQueryBackendStore(FrozenStrictModel):
    """IPC-only capability: no writable operation or exposed engine."""

    _engine: AiAugmentBackendStore = PrivateAttr()

    def query_response_record(
        self,
        request: ControlCentreComponent.BackendPort.QueryRequestRecordProperty,
    ) -> ResponseRecordPromise[QueryResponseRecord]:
        return self._engine.query_response_record(request)


@overload
def initialize_backend_store(
    context: AiAugmentBackendContext,
    *,
    ipc_only: Literal[True],
) -> AbstractContextManager[AiAugmentQueryBackendStore]: ...


@overload
def initialize_backend_store(
    context: AiAugmentBackendContext,
    *,
    ipc_only: Literal[False],
    new: bool,
    confirmed: bool,
    confirm_replay: Callable[[], bool],
) -> AbstractContextManager[AiAugmentBackendStore]: ...


def initialize_backend_store(
    context: AiAugmentBackendContext,
    *,
    ipc_only: bool,
    new: bool = False,
    confirmed: bool = False,
    confirm_replay: Callable[[], bool] = lambda: False,
) -> AbstractContextManager[AiAugmentQueryBackendStore | AiAugmentBackendStore]:
    return _initialize_backend_store(
        context,
        ipc_only=ipc_only,
        new=new,
        confirmed=confirmed,
        confirm_replay=confirm_replay,
    )


@contextmanager
def _initialize_backend_store(
    context: AiAugmentBackendContext,
    *,
    ipc_only: bool,
    new: bool,
    confirmed: bool,
    confirm_replay: Callable[[], bool],
) -> Generator[AiAugmentQueryBackendStore | AiAugmentBackendStore, None, None]:
    config = context.pipeline_config
    store = AiAugmentBackendStore._from_resources(
        replay_log=config.replay_log,
        detour_db=AiAugmentDetourDB.from_pipeline_db(
            config.db_file,
            duckdb_extensions=config.duckdb_extensions,
        ),
        rollout_cas=config.rollout_cas,
    )
    if ipc_only:
        capability = AiAugmentQueryBackendStore()
        capability._engine = store
        with store._read_only(context):
            yield capability
        return
    if not confirmed:
        raise ValueError(Locale.STORE_STARTUP_CONFIRMATION_REQUIRED)
    if new:
        store._rebuild_from_log(
            context, reset_confirmed=confirmed, confirm_replay=confirm_replay,
        )
    store._reset_current_replayed_record()
    try:
        store._loop = asyncio.get_running_loop()
    except RuntimeError:
        # CLI/startup-only callers do not serve HTTP or accept pushes.
        store._loop = None
    with store._writable(context):
        yield store
