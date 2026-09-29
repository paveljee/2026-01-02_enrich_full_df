from __future__ import annotations

import asyncio
import base64
import fcntl
import json
import logging
import os
import sys
import tempfile
import threading
import time
from collections.abc import AsyncGenerator, Coroutine, Iterator, Mapping
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit
from uuid import UUID

import duckdb
import requests
from fastapi import status

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.pydantic_to_paste import (  # noqa: E501
    MAX_PUSH_BODY_BYTES,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_fixture import (  # noqa: E501
    L_FEI_FEI_INITIAL_FIXTURE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AI_AUGMENT_COLUMNS,
    AI_AUGMENT_EVIDENCE_COLUMNS,
    API_VERSION,
    AUTHORITATIVE_ATTEMPT_COMMIT_REQUEST_RECORD_ID_COLUMN,  # noqa: F401
    AUTHORITATIVE_LOG_BASE64_ENCODING,
    AUTHORITATIVE_LOG_DATA_KEY,
    AUTHORITATIVE_LOG_ENCODING_KEY,
    BASE64_TEXT_ENCODING,
    COMPACT_JSON_SEPARATORS,
    DOCX_COLUMNS,
    ETAG_HEADER,
    HTTP_CONTENT_LENGTH_HEADER,
    HTTP_CONTENT_TYPE_HEADER,
    KTP_AI_AUGMENT_COMMENTS_COL,
    NANOSECONDS_PER_MICROSECOND,
    STANDARDIZED_SUBMISSION_TYPE,
    TEXT_ENCODING,
    ContentType,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AIVM_AUDIT_USER as AIVM_AUDIT_USER,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AIVM_IDENTITY_FILE as AIVM_IDENTITY_FILE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AIVM_IDENTITY_FILE_ENV_NAME as AIVM_IDENTITY_FILE_ENV_NAME,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AIVM_INSTANCE as AIVM_INSTANCE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AIVM_KNOWN_HOSTS_FILE as AIVM_KNOWN_HOSTS_FILE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    APPENDWATCH_REPORT_ENV_NAME as APPENDWATCH_REPORT_ENV_NAME,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ARCHIVE_HASH_CHUNK_BYTES as ARCHIVE_HASH_CHUNK_BYTES,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_BODY_KEY as ASGI_BODY_KEY,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_HEADERS_KEY as ASGI_HEADERS_KEY,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_HTTP_DISCONNECT_MESSAGE_TYPE as ASGI_HTTP_DISCONNECT_MESSAGE_TYPE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_HTTP_REQUEST_MESSAGE_TYPE as ASGI_HTTP_REQUEST_MESSAGE_TYPE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE as ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_HTTP_RESPONSE_START_MESSAGE_TYPE as ASGI_HTTP_RESPONSE_START_MESSAGE_TYPE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_HTTP_SCOPE_TYPE as ASGI_HTTP_SCOPE_TYPE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_METHOD_KEY as ASGI_METHOD_KEY,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_MORE_BODY_KEY as ASGI_MORE_BODY_KEY,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_PATH_KEY as ASGI_PATH_KEY,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_STATUS_KEY as ASGI_STATUS_KEY,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_TYPE_KEY as ASGI_TYPE_KEY,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AUDIT_FIND_ROLLOUT_COMMAND as AUDIT_FIND_ROLLOUT_COMMAND,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AUDIT_PROBE_COMMAND as AUDIT_PROBE_COMMAND,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AUDIT_READ_APPENDWATCH_REPORT_COMMAND as AUDIT_READ_APPENDWATCH_REPORT_COMMAND,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AUDIT_READ_ROLLOUT_COMMAND as AUDIT_READ_ROLLOUT_COMMAND,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN as AUTHORITATIVE_ATTEMPT_PAYLOAD_COLUMN,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AUTHORITATIVE_ATTEMPTS_TABLE as AUTHORITATIVE_ATTEMPTS_TABLE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AUTHORITATIVE_RECORD_ORDINAL_COLUMN as AUTHORITATIVE_RECORD_ORDINAL_COLUMN,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AUTHORITATIVE_RECORDS_TABLE as AUTHORITATIVE_RECORDS_TABLE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    CARD_EXCLUDED_COLUMNS as CARD_EXCLUDED_COLUMNS,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    CODEX_INNERDICT_TABLE as CODEX_INNERDICT_TABLE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    CODEX_OUTPUT_ROWS_TABLE as CODEX_OUTPUT_ROWS_TABLE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    CODEX_OUTPUT_SCHEMA as CODEX_OUTPUT_SCHEMA,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    CODEX_SESSIONS_ROOT as CODEX_SESSIONS_ROOT,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    CODEX_SESSIONS_ROOT_ENV_NAME as CODEX_SESSIONS_ROOT_ENV_NAME,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    FORBIDDEN_NORMALIZED_PATH_PARTS as FORBIDDEN_NORMALIZED_PATH_PARTS,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_GET_METHOD as HTTP_GET_METHOD,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    LIMA_SSH_CONFIG_PATH as LIMA_SSH_CONFIG_PATH,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    LOCATION_HEADER as LOCATION_HEADER,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    NAMEKEY_ENV_NAME as NAMEKEY_ENV_NAME,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    NOT_AVAILABLE_OR_APPLICABLE_VALUE as NOT_AVAILABLE_OR_APPLICABLE_VALUE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    NOT_REPORTED_VALUE as NOT_REPORTED_VALUE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    PULL_PATH as PULL_PATH,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    PUSH_PATH as PUSH_PATH,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    RETRY_AFTER_HEADER as RETRY_AFTER_HEADER,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    RETRY_AFTER_SECONDS as RETRY_AFTER_SECONDS,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ROLLOUT_ENV_NAME as ROLLOUT_ENV_NAME,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ROLLOUT_FILENAME_PREFIX as ROLLOUT_FILENAME_PREFIX,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ROLLOUT_FILENAME_SUFFIX as ROLLOUT_FILENAME_SUFFIX,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ROLLOUT_LINE_FRAGMENT_TYPE as ROLLOUT_LINE_FRAGMENT_TYPE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    SERVER_HOST as SERVER_HOST,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    SERVER_PORT as SERVER_PORT,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    SSH_EXECUTABLE as SSH_EXECUTABLE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    SSH_TIMEOUT_SECONDS as SSH_TIMEOUT_SECONDS,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    SYNTHETIC_COMMIT_HOST as SYNTHETIC_COMMIT_HOST,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    SYNTHETIC_COMMIT_SCHEME as SYNTHETIC_COMMIT_SCHEME,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_backend_store import (
    AiAugmentBackendStore,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_singular_outer_dict import (  # noqa: E501
    AiAugmentSingularOuterDict,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_singular_outer_dict import (  # noqa: E501
    selected_card_outer_dict as selected_card_outer_dict,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.lifecycle import (
    BackendLifecycle,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.pull_event import (
    PullRequestRecord,
    PullResponseRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.push_event import (
    PushRequestRecord,
    PushResponseRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.response_record_promise import (
    BackendStoreAcknowledgment,
    BackendStoreException,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.validation_request import (  # noqa: E501
    BackendValidationRequestRecord,
)
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
)
from src.helpers.vars import (
    KTP_FIRST_NAME_COL,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
    KTP_LAST_NAME_COL,
)

logger = logging.getLogger(__name__)


BACKEND_PROCESS_LOCK_PATH = Path(tempfile.gettempdir()) / "ktp-hcr-detour-ai-augment-backend.lock"

BACKEND_PROCESS_LOCK_DESCRIPTOR: int | None = None
AUTHORITATIVE_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()
BACKEND_WORKFLOW_STATE_LOCK = threading.Lock()
BACKEND_LIFECYCLE = BackendLifecycle.READY
BACKEND_SESSION_ID: UUID | None = None


@asynccontextmanager
async def lifespan() -> AsyncGenerator[None, None]:
    try:
        with BACKEND_WORKFLOW_STATE_LOCK:
            global BACKEND_SESSION_ID
            global BACKEND_LIFECYCLE
            BACKEND_SESSION_ID = None
            BACKEND_LIFECYCLE = BackendLifecycle.READY
        start_backend_session_reader()
        try:
            yield
        finally:
            if AUTHORITATIVE_BACKGROUND_TASKS:
                results = await asyncio.gather(
                    *tuple(AUTHORITATIVE_BACKGROUND_TASKS),
                    return_exceptions=True,
                )
                failures = [result for result in results if isinstance(result, BaseException)]
                if failures:
                    raise BaseExceptionGroup(Locale.BACKEND_BACKGROUND_WORK_FAILED, failures)
    except Exception as exc:
        logger.error(Locale.API_LIFESPAN_FAILED_LOG, exc)
        raise


EVIDENCE_SUBMISSION_EXAMPLE = L_FEI_FEI_INITIAL_FIXTURE.submission.model_dump(
    by_alias=True,
    mode="json",
)
SUBMISSION_EXAMPLE: dict[str, object] = dict[str, object](
    L_FEI_FEI_INITIAL_FIXTURE.submission.normalized_values()
)
PULL_EXAMPLE_FIRST_NAME, PULL_EXAMPLE_LAST_NAME = L_FEI_FEI_INITIAL_FIXTURE.identity
NULL_SUBMISSION_EXAMPLE = {
    KTP_FIRST_NAME_COL: PULL_EXAMPLE_FIRST_NAME,
    KTP_LAST_NAME_COL: PULL_EXAMPLE_LAST_NAME,
    **dict.fromkeys(AI_AUGMENT_COLUMNS),
}

APP_CONFIG: dict[str, Any] = {
    "title": Locale.API_TITLE,
    "description": Locale.API_DESCRIPTION,
    "version": API_VERSION,
}

PULL_ROUTE: dict[str, Any] = {
    "path": PULL_PATH,
    "summary": Locale.PULL_SUMMARY,
    "description": Locale.PULL_DESCRIPTION,
    "responses": {
        status.HTTP_200_OK: {
            "description": Locale.PULL_RESPONSE_DESCRIPTION,
            "content": {
                ContentType.NDJSON: {
                    "example": (json.dumps(NULL_SUBMISSION_EXAMPLE, ensure_ascii=False) + "\n"),
                },
                ContentType.MARKDOWN: {
                    "example": Locale.VALIDATION_ERROR_DETAIL + "\n",
                },
            },
        },
        status.HTTP_410_GONE: {
            "description": Locale.PULL_ACCEPTED_DESCRIPTION,
            "content": {
                ContentType.NDJSON: {
                    "example": json.dumps(SUBMISSION_EXAMPLE, ensure_ascii=False) + "\n",
                },
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": Locale.CONFIGURATION_ERROR_DETAIL,
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": Locale.PULL_PROCESSING_DESCRIPTION,
            "headers": {
                RETRY_AFTER_HEADER: {
                    "schema": {"type": "string", "example": RETRY_AFTER_SECONDS},
                },
            },
        },
    },
}

PUSH_ROUTE: dict[str, Any] = {
    "path": PUSH_PATH,
    "status_code": status.HTTP_202_ACCEPTED,
    "summary": Locale.PUSH_SUMMARY,
    "description": Locale.PUSH_DESCRIPTION,
    "responses": {
        status.HTTP_202_ACCEPTED: {
            "description": Locale.PUSH_RESPONSE_DESCRIPTION,
            "headers": {
                LOCATION_HEADER: {
                    "schema": {"type": "string", "example": PULL_PATH},
                },
            },
        },
        status.HTTP_409_CONFLICT: {
            "description": (
                Locale.PUSH_ALREADY_PROCESSING_DESCRIPTION
            ),
            "headers": {
                LOCATION_HEADER: {
                    "schema": {"type": "string", "example": PULL_PATH},
                },
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": Locale.CONFIGURATION_ERROR_DETAIL,
        },
    },
    "openapi_extra": {
        "requestBody": {
            "required": True,
            "content": {ContentType.JSON: {"example": EVIDENCE_SUBMISSION_EXAMPLE}},
        }
    },
}


def _response(
    request: requests.PreparedRequest,
    code: HTTPStatus,
    body: str = "",
    *,
    content_type: ContentType | None = None,
    headers: Mapping[str, str] | None = None,
) -> requests.Response:
    response = requests.Response()
    response.status_code = code
    response.request = request
    response.url = request.url or ""
    response.encoding = TEXT_ENCODING
    response._content = body.encode(TEXT_ENCODING)
    _ = response.content
    if headers is not None:
        response.headers.update(headers)
    if content_type is not None:
        response.headers[HTTP_CONTENT_TYPE_HEADER] = content_type
    response.headers[HTTP_CONTENT_LENGTH_HEADER] = str(len(response.content))
    return response


def _error_response(
    request: requests.PreparedRequest,
    code: HTTPStatus,
    *,
    headers: Mapping[str, str] | None = None,
) -> requests.Response:
    return _response(
        request,
        code,
        json.dumps(
            {"detail": Locale.CONFIGURATION_ERROR_DETAIL},
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
        ),
        content_type=ContentType.JSON,
        headers=headers,
    )


def _pull_response(
    request: requests.PreparedRequest,
    store: AiAugmentBackendStore,
) -> requests.Response:
    with BACKEND_WORKFLOW_STATE_LOCK:
        lifecycle = BACKEND_LIFECYCLE
        commit_request_record, validation_request_record = store._cursor_commit_validation()
    logger.info(
        Locale.PULL_STATE_LOG,
        lifecycle,
        None
        if commit_request_record is None
        else commit_request_record.record_id,
    )
    if lifecycle is BackendLifecycle.BUSY:
        logger.info(Locale.PULL_PROCESSING_LOG)
        return _error_response(
            request, HTTPStatus.SERVICE_UNAVAILABLE,
            headers={RETRY_AFTER_HEADER: RETRY_AFTER_SECONDS},
        )
    if lifecycle is BackendLifecycle.FAILED:
        logger.error(Locale.PULL_WORKFLOW_FAILED_LOG)
        return _error_response(request, HTTPStatus.INTERNAL_SERVER_ERROR)
    if lifecycle in {BackendLifecycle.RETRY, BackendLifecycle.COMPLETED}:
        if validation_request_record is None:
            raise BackendStoreException(Locale.PULL_VALIDATION_RECORD_MISSING)
        body = validation_request_record.validation_request_body
        assert body.commit_request_record is commit_request_record
        validation = body.post_commit_validation
        if lifecycle is BackendLifecycle.RETRY:
            if validation.result is not BackendLifecycle.REJECTED or validation.stage not in {
                BackendLifecycle.PYDANTIC_VALIDATION,
                BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION,
            }:
                raise BackendStoreException(Locale.PULL_RETRY_VALIDATION_INCONSISTENT)
            logger.info(Locale.PULL_RETRY_STAGE_LOG, validation.stage)
            return _response(
                request,
                HTTPStatus.OK,
                (validation.detail or Locale.VALIDATION_ERROR_DETAIL).rstrip() + "\n",
                content_type=ContentType.MARKDOWN_UTF8,
            )
        if (
            validation.result is not BackendLifecycle.ACCEPTED
            or validation.submission_type != STANDARDIZED_SUBMISSION_TYPE
            or validation.submission is None
        ):
            raise BackendStoreException(Locale.PULL_COMPLETED_RESULT_INVALID)
        # Render the Store-validated serialized values; never revalidate providers in API.
        values: dict[str, str] = {}
        for column in (*AI_AUGMENT_EVIDENCE_COLUMNS, KTP_AI_AUGMENT_COMMENTS_COL):
            field = validation.submission[column]
            if column == KTP_AI_AUGMENT_COMMENTS_COL and field is None:
                continue
            if not isinstance(field, dict) or not isinstance(field.get("value"), str):
                raise BackendStoreException(Locale.PULL_SUBMISSION_VALUE_INVALID)
            value = field["value"]
            assert isinstance(value, str)
            values[column] = value
        singular = store.configured_ai_augment_singular_outerdict()
        if singular is None:
            raise BackendStoreException(Locale.PULL_COMPLETED_RESEARCHER_MISSING)
        ground_truth = singular.ground_truth_innerdict()
        lines = [json_line(values)]
        if ground_truth is not None:
            lines.append(json_line(select_columns(ground_truth.data)))
        logger.info(Locale.PULL_COMPLETED_GROUND_TRUTH_LOG, ground_truth is not None)
        return _response(
            request, HTTPStatus.GONE, "".join(lines), content_type=ContentType.NDJSON_UTF8,
            headers={ETAG_HEADER: f'"{validation_request_record.record_id}"'},
        )
    try:
        singular = store.configured_ai_augment_singular_outerdict()
        if singular is None:
            raise BackendStoreException(Locale.PULL_COMPLETED_RESEARCHER_MISSING)
        initial_lines = tuple(configured_pull_lines(singular))
        logger.info(
            Locale.PULL_INITIAL_TASK_LOG, singular.namekey, len(initial_lines)
        )
        return _response(
            request, HTTPStatus.OK, "".join(initial_lines), content_type=ContentType.NDJSON_UTF8,
        )
    except (RuntimeError, ValueError, OSError, duckdb.Error) as exc:
        logger.error(Locale.PULL_FAILED_LOG, exc)
        return _error_response(request, HTTPStatus.INTERNAL_SERVER_ERROR)


async def authoritative_pull(
    request: requests.PreparedRequest,
    store: AiAugmentBackendStore,
) -> requests.Response:
    started_ns = time.monotonic_ns()
    try:
        response = _pull_response(request, store)
    except Exception as exc:
        logger.error(Locale.PULL_FAILED_LOG, exc)
        response = _error_response(request, HTTPStatus.INTERNAL_SERVER_ERROR)
    http_record = _authoritative_http_record(request, response, started_ns=started_ns)
    record = PullRequestRecord(
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
    promise = await asyncio.to_thread(store.pull_response_record, record)
    response_record, error = await promise.response_record_promise()
    if error is not None:
        error.raise_exception()
    if promise.acknowledgment is not BackendStoreAcknowledgment.ACK or response_record is None:
        raise BackendStoreException(Locale.PULL_DURABLE_RESPONSE_MISSING)
    logger.info(
        Locale.PULL_PERSISTED_LOG,
        response_record.record_id,
        response_record.response_code,
    )
    return response_record.to_response()


def _push_response(
    request: requests.PreparedRequest,
    store: AiAugmentBackendStore,
    pull_response_record: PullResponseRecord | None,
) -> requests.Response:
    global BACKEND_LIFECYCLE
    with BACKEND_WORKFLOW_STATE_LOCK:
        lifecycle = BACKEND_LIFECYCLE
        logger.info(
            Locale.PUSH_REQUEST_STATE_LOG, lifecycle, BACKEND_SESSION_ID,
            None if pull_response_record is None else pull_response_record.record_id,
        )
        if lifecycle is BackendLifecycle.BUSY:
            return _error_response(
                request, HTTPStatus.CONFLICT, headers={LOCATION_HEADER: PULL_PATH},
            )
        if (
            lifecycle not in {BackendLifecycle.READY, BackendLifecycle.RETRY}
            or BACKEND_SESSION_ID is None
        ):
            logger.error(Locale.PUSH_SESSION_NOT_READY_LOG)
            return _error_response(request, HTTPStatus.INTERNAL_SERVER_ERROR)
        commit, _validation = store._cursor_commit_validation()
        if (
            pull_response_record is None or pull_response_record.response_code != HTTPStatus.OK
            or (
                commit is not None
                and commit.commit_request_body.pull_response_record.record_id
                == pull_response_record.record_id
            )
        ):
            logger.warning(Locale.PUSH_CURRENT_PULL_REQUIRED_LOG)
            return _error_response(
                request, HTTPStatus.CONFLICT, headers={LOCATION_HEADER: PULL_PATH},
            )
        BACKEND_LIFECYCLE = BackendLifecycle.BUSY
    return _response(request, HTTPStatus.ACCEPTED, headers={LOCATION_HEADER: PULL_PATH})


async def authoritative_push(
    request: requests.PreparedRequest,
    store: AiAugmentBackendStore,
) -> requests.Response:
    started_ns = time.monotonic_ns()
    with BACKEND_WORKFLOW_STATE_LOCK:
        current = store.current_replayed_record
        pull_response_record = current if isinstance(current, PullResponseRecord) else None
        session = BACKEND_SESSION_ID
    response = _push_response(request, store, pull_response_record)
    http_record = _authoritative_http_record(request, response, started_ns=started_ns)
    record = PushRequestRecord(
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
    promise = await asyncio.to_thread(store.push_response_record, record, session_id=session)
    if promise.acknowledgment is not BackendStoreAcknowledgment.ACK:
        _record, error = await promise.response_record_promise()
        if error is not None:
            error.raise_exception()
        raise BackendStoreException(Locale.PUSH_NAK_ERROR_MISSING)
    if response.status_code == HTTPStatus.ACCEPTED:
        register_processing(finish_push(promise, store))
        logger.info(Locale.PUSH_DURABLY_ACCEPTED_LOG, record.record_id)
        return response
    response_record, error = await promise.response_record_promise()
    if error is not None:
        error.raise_exception()
    if response_record is None:
        raise BackendStoreException(Locale.PUSH_RESPONSE_RECORD_MISSING)
    logger.info(Locale.PUSH_PERSISTED_LOG, response_record.record_id, response_record.response_code)
    return response_record.to_response()


def set_backend_session_id(value: str) -> None:
    global BACKEND_SESSION_ID

    normalized = value.strip()
    try:
        session_id = UUID(normalized)
    except ValueError as exc:
        raise RuntimeError(Locale.SESSION_ID_STDIN_INVALID) from exc
    if str(session_id) != normalized:
        raise RuntimeError(Locale.SESSION_ID_STDIN_INVALID)
    with BACKEND_WORKFLOW_STATE_LOCK:
        if BACKEND_SESSION_ID is not None and BACKEND_SESSION_ID != session_id:
            raise RuntimeError(Locale.SESSION_ID_STDIN_CONFLICT)
        BACKEND_SESSION_ID = session_id


def read_backend_session_id(stream: TextIO | None = None) -> None:
    input_stream = sys.stdin if stream is None else stream
    value = input_stream.readline()
    if not value:
        raise RuntimeError(Locale.SESSION_ID_STDIN_MISSING)
    set_backend_session_id(value)
    logger.info(Locale.SESSION_ID_STDIN_ACCEPTED_LOG, value.strip())


def start_backend_session_reader() -> threading.Thread:
    def read_or_fail() -> None:
        try:
            read_backend_session_id()
        except Exception as exc:
            logger.exception(Locale.SESSION_ID_STDIN_FAILED_LOG, exc)
            _mark_backend_lifecycle_failed(exc)

    reader = threading.Thread(
        target=read_or_fail,
        name="detour-ai-augment-session-reader",
        daemon=True,
    )
    reader.start()
    return reader


def _acquire_backend_process_lock() -> None:
    global BACKEND_PROCESS_LOCK_DESCRIPTOR

    if BACKEND_PROCESS_LOCK_DESCRIPTOR is not None:
        raise RuntimeError(Locale.BACKEND_ALREADY_RUNNING)
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(BACKEND_PROCESS_LOCK_PATH, flags, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise RuntimeError(Locale.BACKEND_ALREADY_RUNNING) from exc
    BACKEND_PROCESS_LOCK_DESCRIPTOR = descriptor


def _release_backend_process_lock() -> None:
    global BACKEND_PROCESS_LOCK_DESCRIPTOR

    descriptor = BACKEND_PROCESS_LOCK_DESCRIPTOR
    BACKEND_PROCESS_LOCK_DESCRIPTOR = None
    if descriptor is None:
        return
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def update_pull_state(validation_request_record: BackendValidationRequestRecord) -> None:
    global BACKEND_LIFECYCLE

    body = validation_request_record.validation_request_body
    validation = body.post_commit_validation
    commit_request_record = body.commit_request_record
    push_response_record = commit_request_record.commit_request_body.push_response_record
    with BACKEND_WORKFLOW_STATE_LOCK:
        if validation.result is BackendLifecycle.ACCEPTED:
            BACKEND_LIFECYCLE = BackendLifecycle.COMPLETED
        elif validation.result is BackendLifecycle.REJECTED and validation.stage in {
            BackendLifecycle.PYDANTIC_VALIDATION,
            BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION,
        }:
            BACKEND_LIFECYCLE = BackendLifecycle.RETRY
        else:
            BACKEND_LIFECYCLE = BackendLifecycle.FAILED
    logger.info(
        Locale.PUSH_RESULT_STATE_LOG,
        push_response_record.record_id,
        commit_request_record.record_id,
        validation_request_record.record_id,
        validation.stage,
        validation.result,
        BACKEND_LIFECYCLE,
    )


def _mark_backend_lifecycle_failed(error: Exception) -> None:
    global BACKEND_LIFECYCLE
    logger.error(Locale.POST_ACCEPT_PROCESSING_FAILED_LOG, error)
    with BACKEND_WORKFLOW_STATE_LOCK:
        BACKEND_LIFECYCLE = BackendLifecycle.FAILED


def _authoritative_background_finished(task: asyncio.Task[None]) -> None:
    AUTHORITATIVE_BACKGROUND_TASKS.discard(task)
    if task.cancelled():
        return
    failure = task.exception()
    if failure is not None:
        logger.critical(Locale.COMMIT_APPEND_FATAL_LOG, failure)
        os._exit(1)


async def finish_push(
    promise: BackendComponent.ResponseRecordPromiseProperty[
        BackendComponent.PushResponseRecordProperty
    ],
    store: AiAugmentBackendStore,
) -> None:
    try:
        response, error = await promise.response_record_promise()
        if error is not None:
            error.raise_exception()
        if response is None:
            raise BackendStoreException(Locale.PUSH_RESPONSE_RECORD_MISSING)
        assert isinstance(response, PushResponseRecord)
        validation = store.current_replayed_record
        if not isinstance(validation, BackendValidationRequestRecord):
            raise BackendStoreException(Locale.PUSH_VALIDATION_RECORD_MISSING)
        assert (
            validation.validation_request_body.commit_request_record
            .commit_request_body.push_response_record is response
        )
        update_pull_state(validation)
    except Exception as exc:
        _mark_backend_lifecycle_failed(exc)
        raise


def register_processing(work: Coroutine[object, object, None]) -> None:
    task = asyncio.create_task(work)
    AUTHORITATIVE_BACKGROUND_TASKS.add(task)
    task.add_done_callback(_authoritative_background_finished)


def select_columns(row: Mapping[str, object]) -> dict[str, object]:
    missing = [column for column in DOCX_COLUMNS if column not in row]

    if missing:
        raise RuntimeError(Locale.TARGET_ROW_KEYS_MISSING_TEMPLATE.format(keys=", ".join(missing)))

    return {column: row[column] for column in DOCX_COLUMNS}


def json_line(row: Mapping[str, object]) -> str:
    return (
        json.dumps(
            row,
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
        )
        + "\n"
    )


def http_error_response_body(detail: str) -> str:
    return json.dumps(
        {"detail": detail},
        ensure_ascii=False,
        separators=COMPACT_JSON_SEPARATORS,
    )


def _http_header_value(
    headers: Mapping[str, object] | None,
    name: str,
) -> str | None:
    if headers is None:
        return None
    normalized_name = name.casefold()
    for key, value in headers.items():
        if key.casefold() == normalized_name and isinstance(value, str):
            return value
    return None


def _request_body_for_authoritative_log(body: bytes) -> str:
    try:
        return body.decode(TEXT_ENCODING)
    except UnicodeDecodeError:
        return json.dumps(
            {
                AUTHORITATIVE_LOG_ENCODING_KEY: AUTHORITATIVE_LOG_BASE64_ENCODING,
                AUTHORITATIVE_LOG_DATA_KEY: base64.b64encode(body).decode(BASE64_TEXT_ENCODING),
            },
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
        )


def _authoritative_http_record(
    request: requests.PreparedRequest,
    response: requests.Response,
    *,
    started_ns: int,
) -> HttpRequestLogRecord:
    parsed = urlsplit(request.url or "")
    return HttpRequestLogRecord(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        method=request.method or "",
        scheme=parsed.scheme,
        host=parsed.hostname or "",
        port=parsed.port,
        path=parsed.path,
        query=parsed.query,
        request_headers=dict(request.headers),
        request_body=_request_body_for_authoritative_log(_prepared_request_body(request)),
        response_code=response.status_code,
        response_headers=dict(response.headers),
        response_body=response.content.decode(TEXT_ENCODING),
        received_at_unix_usec=None,
        ready_to_respond_at_unix_usec=time.time_ns() // NANOSECONDS_PER_MICROSECOND,
        duration_usec=(time.monotonic_ns() - started_ns) // NANOSECONDS_PER_MICROSECOND,
    )


def _prepared_request_body(request: requests.PreparedRequest) -> bytes:
    if request.body is None:
        return b""
    if isinstance(request.body, bytes):
        return request.body
    if isinstance(request.body, str):
        return request.body.encode(TEXT_ENCODING)
    raise ValueError(Locale.BUFFERED_REQUEST_REQUIRED)


def configured_pull_lines(singular_outerdict: AiAugmentSingularOuterDict) -> Iterator[str]:
    for innerdict in (*singular_outerdict.xlsx_innerdicts, *singular_outerdict.ssn_innerdicts):
        yield json_line(innerdict.data)
    yield json_line({
        KTP_FIRST_NAME_COL: singular_outerdict.namekey.first_name,
        KTP_LAST_NAME_COL: singular_outerdict.namekey.last_name,
        **dict.fromkeys(AI_AUGMENT_COLUMNS),
    })


def validate_transport(request: requests.PreparedRequest) -> None:
    content_type = (
        request.headers.get(HTTP_CONTENT_TYPE_HEADER, "").partition(";")[0].strip().lower()
    )
    if content_type != ContentType.JSON:
        raise ValueError(Locale.REQUEST_CONTENT_TYPE_INVALID)
    content_length = request.headers.get(HTTP_CONTENT_LENGTH_HEADER)
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise ValueError(Locale.REQUEST_CONTENT_LENGTH_INVALID) from exc
        if declared_length < 0 or declared_length > MAX_PUSH_BODY_BYTES:
            raise ValueError(Locale.REQUEST_BODY_TOO_LARGE)


def bounded_request_body(request: requests.PreparedRequest) -> bytes:
    body = _prepared_request_body(request)
    if len(body) > MAX_PUSH_BODY_BYTES:
        raise ValueError(Locale.REQUEST_BODY_TOO_LARGE)
    return body
