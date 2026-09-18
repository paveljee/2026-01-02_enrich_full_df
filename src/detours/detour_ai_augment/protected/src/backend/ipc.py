from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import requests

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.src.backend import api
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_event import (
    BASE64_TEXT_ENCODING,
    AppendwatchReportEncoding,
    AppendwatchReportRecord,
    CodexRolloutRecord,
    CodexSessionRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.request_response_records import (
    QueryRequestRecord,
    RunOutcomeRequestRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.response_record_promise import (
    BackendStoreAcknowledgment,
    BackendStoreException,
)

from ....src.control_centre.dashboard.helpers.data_models.query_request import (
    QueryRequest,
)
from ....src.control_centre.dashboard.helpers.data_models.run_outcome import (
    RunOutcomeRequest,
)

logger = logging.getLogger(__name__)

JSON_MEDIA_TYPE = "application/json"
SOCKET_PERMISSIONS = 0o600
NANOSECONDS_PER_MICROSECOND = 1_000
DASHBOARD_IPC_SCHEME = api.SYNTHETIC_COMMIT_SCHEME
DASHBOARD_IPC_HOST = api.SYNTHETIC_COMMIT_HOST
DASHBOARD_SOCKET_PATH_ENV_NAME = "FASTAPI_DETOUR_DASHBOARD_SOCKET"
DASHBOARD_QUERY_PATH = "/query"
DEFAULT_DASHBOARD_SOCKET_PATH = (
    Path(tempfile.gettempdir()) / f"ktp-hcr-detour-ai-augment-{os.getuid()}.sock"
)
DASHBOARD_SOCKET_PATH = Path(
    os.environ.get(DASHBOARD_SOCKET_PATH_ENV_NAME, DEFAULT_DASHBOARD_SOCKET_PATH)
).expanduser()


def _run_outcome_snapshot_configuration(session_id: UUID | None) -> api._PushConfiguration:
    rollout_name = (
        f"{api.ROLLOUT_FILENAME_PREFIX}{session_id or 'run-outcome-snapshot'}"
        f"{api.ROLLOUT_FILENAME_SUFFIX}"
    )
    return api.push_configuration(str(api.CODEX_SESSIONS_ROOT / rollout_name))


def _capture_run_outcome_snapshot(
    runtime: AiAugmentBackendContext,
    request: RunOutcomeRequest,
) -> tuple[RunOutcomeRequestRecord, tuple[Exception, ...]]:
    with api.BACKEND_WORKFLOW_STATE_LOCK:
        session_id = api.BACKEND_SESSION_ID
        pull_record = api.BACKEND_PENDING_PULL_RECORD or api.BACKEND_CURRENT_PULL_RECORD
        push_record = api.BACKEND_LATEST_PUSH_RECORD

    rollout_record: CodexRolloutRecord | None = None
    rollout_filename: str | None = None
    appendwatch_report: bytes | None = None
    failures: list[Exception] = []

    if session_id is not None:
        try:
            rollout_configuration = api.push_configuration_for_session(session_id)
            try:
                rollout_record = runtime.pipeline_config.rollout_cas.copy_rollout(
                    ssh_target=rollout_configuration.ssh_target,
                    rollout_relative_path=rollout_configuration.rollout_relative_path,
                    ssh_options=api._aivm_connection_options(
                        lima_ssh_config=rollout_configuration.lima_ssh_config,
                        identity_file=rollout_configuration.identity_file,
                        known_hosts_file=rollout_configuration.known_hosts_file,
                        ssh_user=rollout_configuration.ssh_user,
                        host_key_alias=rollout_configuration.host_key_alias,
                    ),
                )
            except (OSError, ValueError) as exc:
                raise api._PushConfigurationError(str(exc)) from exc
            rollout_filename = rollout_configuration.rollout_relative_path.name
        except (OSError, api._PushConfigurationError) as exc:
            failures.append(exc)

    try:
        appendwatch_configuration = _run_outcome_snapshot_configuration(session_id)
        appendwatch_report = api._read_appendwatch_bytes(appendwatch_configuration)
    except (OSError, api._PushConfigurationError) as exc:
        failures.append(exc)

    snapshot = RunOutcomeRequestRecord(
        **request.http_request_log_record.model_dump(),
        rollout_filename=rollout_filename,
        pull_record_id=None if pull_record is None else pull_record.record_id,
        push_record_id=None if push_record is None else push_record.record_id,
        codex_session_record=CodexSessionRecord(
            session_id=session_id,
            codex_rollout_record=(None if rollout_record is None else rollout_record),
            appendwatch_report_record=(
                None
                if appendwatch_report is None
                else AppendwatchReportRecord(
                    encoding=AppendwatchReportEncoding.BASE64,
                    data=base64.b64encode(appendwatch_report).decode(BASE64_TEXT_ENCODING),
                )
            ),
        ),
    )
    return snapshot, tuple(failures)


async def handle_run_outcome_request(
    runtime: AiAugmentBackendContext,
    store: BackendComponent.FullStoreProperty,
    request: requests.PreparedRequest,
) -> requests.Response:
    parsed = urlsplit(request.url or "")
    ipc_request = RunOutcomeRequest.from_http_request(
        received_at_unix_usec=time.time_ns() // NANOSECONDS_PER_MICROSECOND,
        method=request.method or "",
        scheme=parsed.scheme,
        host=parsed.hostname or "",
        port=parsed.port,
        path=parsed.path,
        query=parsed.query,
        request_headers=dict(request.headers),
        request_body=api._prepared_request_body(request),
    )
    if runtime.configured_namekey is None or ipc_request.namekey != runtime.configured_namekey:
        raise api._PushValidationError(Locale.REPLAY_RECORD_CONTOUR_INVALID)
    request_record, failures = await asyncio.to_thread(
        _capture_run_outcome_snapshot, runtime, ipc_request
    )
    if failures:
        logger.error(
            Locale.RUN_OUTCOME_SNAPSHOT_FAILED_LOG,
            ipc_request.path,
            "; ".join(str(failure) for failure in failures),
        )
    promise = await asyncio.to_thread(store.run_outcome, request_record)
    if promise.acknowledgment is not BackendStoreAcknowledgment.NAK:
        raise BackendStoreException(Locale.IPC_REQUEST_UNEXPECTEDLY_PERSISTED)
    response_record, error = await promise.response_record()
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
    QueryRequest.from_http_request(
        method=request.method or "",
        path=parsed.path,
        query=parsed.query.encode(),
        body=api._prepared_request_body(request),
    )


async def handle_query_request(
    store: BackendComponent.QueryOnlyStoreProperty,
    request: requests.PreparedRequest,
) -> requests.Response:
    validate_query_request(request)
    parsed = urlsplit(request.url or "")
    request_record = QueryRequestRecord(
        schema_version="1.1",
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
    promise = await asyncio.to_thread(store.query, request_record)
    if promise.acknowledgment is not BackendStoreAcknowledgment.NAK:
        raise BackendStoreException(Locale.IPC_REQUEST_UNEXPECTEDLY_PERSISTED)
    response_record, error = await promise.response_record()
    if error is not None:
        error.raise_exception()
    if response_record is None:
        raise BackendStoreException(Locale.IPC_RESPONSE_MISSING)
    body = response_record.query_response_body
    logger.info(
        Locale.QUERY_SNAPSHOT_READY_LOG,
        len(body.ai_augment_singular_outerdicts),
        len(body.attempts),
        len(body.run_outcome_records),
    )
    return response_record.to_response()
