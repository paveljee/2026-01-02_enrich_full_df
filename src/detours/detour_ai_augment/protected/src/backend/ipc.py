from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend import api
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    HTTP_GET_METHOD,
    NANOSECONDS_PER_MICROSECOND,
    QUERY_PATH,
    SYNTHETIC_COMMIT_HOST,
    SYNTHETIC_COMMIT_SCHEME,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_backend_store import (
    AiAugmentBackendStore,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.response_record_promise import (
    BackendStoreAcknowledgment,
    BackendStoreException,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.query_event import (  # noqa: E501
    QueryRequestRecord,
    QueryResponseRecord,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome_event import (  # noqa: E501
    RunOutcomeRequestRecord,
)
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

logger = logging.getLogger(__name__)

SOCKET_PERMISSIONS = 0o600
DASHBOARD_IPC_SCHEME = SYNTHETIC_COMMIT_SCHEME
DASHBOARD_IPC_HOST = SYNTHETIC_COMMIT_HOST
DASHBOARD_SOCKET_PATH_ENV_NAME = "FASTAPI_DETOUR_DASHBOARD_SOCKET"
DASHBOARD_QUERY_PATH = QUERY_PATH
DEFAULT_DASHBOARD_SOCKET_PATH = (
    Path(tempfile.gettempdir()) / f"ktp-hcr-detour-ai-augment-{os.getuid()}.sock"
)
DASHBOARD_SOCKET_PATH = Path(
    os.environ.get(DASHBOARD_SOCKET_PATH_ENV_NAME, DEFAULT_DASHBOARD_SOCKET_PATH)
).expanduser()


async def handle_run_outcome_request(
    store: AiAugmentBackendStore,
    request: requests.PreparedRequest,
) -> requests.Response:
    parsed = urlsplit(request.url or "")
    raw_body = api._prepared_request_body(request)
    ipc_request = RunOutcomeRequestRecord.from_http_request(
        received_at_unix_usec=time.time_ns() // NANOSECONDS_PER_MICROSECOND,
        method=request.method or "",
        scheme=parsed.scheme,
        host=parsed.hostname or "",
        port=parsed.port,
        path=parsed.path,
        query=parsed.query,
        request_headers=dict(request.headers),
        request_body=(api._request_body_for_authoritative_log(raw_body) if raw_body else None),
    )
    with api.BACKEND_WORKFLOW_STATE_LOCK:
        session_id = api.BACKEND_SESSION_ID
    session, rollout_filename, failures = await asyncio.to_thread(
        store.capture_run_outcome_snapshot, session_id,
    )
    if failures:
        logger.error(
            Locale.RUN_OUTCOME_SNAPSHOT_FAILED_LOG,
            ipc_request.path,
            "; ".join(str(failure) for failure in failures),
        )
    promise = await asyncio.to_thread(
        store.run_outcome_response_record, ipc_request,
        codex_session_record=session, rollout_filename=rollout_filename,
    )
    if promise.acknowledgment is not BackendStoreAcknowledgment.NAK:
        raise BackendStoreException(Locale.IPC_REQUEST_UNEXPECTEDLY_PERSISTED)
    response_record, error = await promise.response_record_promise()
    if error is not None:
        error.raise_exception()
    if response_record is None:
        raise BackendStoreException(Locale.IPC_RESPONSE_MISSING)
    logger.info(
        Locale.RUN_OUTCOME_PERSISTED_LOG,
        response_record.record_id,
        response_record.response_code,
    )
    return response_record.to_response()


def validate_query_request(request: requests.PreparedRequest) -> None:
    parsed = urlsplit(request.url or "")
    if (
        (request.method, parsed.path) != (HTTP_GET_METHOD, QUERY_PATH)
        or parsed.query
        or api._prepared_request_body(request)
    ):
        raise ValueError(Locale.QUERY_REQUEST_INVALID)


async def handle_query_request(
    store: BackendComponent.QueryOnlyStoreProperty,
    request: requests.PreparedRequest,
) -> requests.Response:
    validate_query_request(request)
    parsed = urlsplit(request.url or "")
    request_record = QueryRequestRecord(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        method=request.method or "",
        scheme=parsed.scheme,
        host=parsed.hostname or "",
        port=parsed.port,
        path=parsed.path,
        query=parsed.query,
        request_headers=dict(request.headers),
        request_body=None,
        response_code=None,
        response_headers=None,
        response_body=None,
        received_at_unix_usec=time.time_ns() // NANOSECONDS_PER_MICROSECOND,
        ready_to_respond_at_unix_usec=None,
        duration_usec=None,
    )
    logger.info(Locale.QUERY_SNAPSHOT_READING_LOG)
    promise = await asyncio.to_thread(store.query_response_record, request_record)
    if promise.acknowledgment is not BackendStoreAcknowledgment.NAK:
        raise BackendStoreException(Locale.IPC_REQUEST_UNEXPECTEDLY_PERSISTED)
    response_record, error = await promise.response_record_promise()
    if error is not None:
        error.raise_exception()
    if response_record is None:
        raise BackendStoreException(Locale.IPC_RESPONSE_MISSING)
    response = QueryResponseRecord.from_http_request_log_record(
        http_request_log_record=response_record.http_request_log_record,
    )
    logger.info(
        Locale.QUERY_SNAPSHOT_READY_LOG,
        len(response.ai_augment_singular_outerdicts),
    )
    return response.to_response()
