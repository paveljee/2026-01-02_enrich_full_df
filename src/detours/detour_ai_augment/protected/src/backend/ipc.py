from __future__ import annotations

import base64
import logging
import os
import signal
import stat
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import NoReturn
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import status
from flask import Flask, Response, request
from pydantic import BaseModel, ConfigDict
from werkzeug.serving import BaseWSGIServer, make_server

from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    TEXT_ENCODING,
)
from src.detours.detour_ai_augment.src.backend import api
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (  # noqa: E501
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_event import (  # noqa: E501
    BASE64_TEXT_ENCODING,
    SOURCE_KEY_HEADER,
    AppendwatchReportEncoding,
    AppendwatchReportRecord,
    CodexRolloutRecord,
    CodexSessionRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.query_response import (  # noqa: E501
    QueryResponse,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.run_outcome_response import (  # noqa: E501
    RunOutcomeResponse,
    RunOutcomeResponseBody,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.query_request import (  # noqa: E501
    QueryRequest,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome import (  # noqa: E501
    RUN_OUTCOME_PATHS,
    RunOutcomePath,
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


RunOutcomeHandler = Callable[
    [RunOutcomeRequest],
    RunOutcomeResponse,
]
QueryResponseHandler = Callable[[QueryRequest], QueryResponse]


# =============================================
# Functions for the POST run outcome endpoints
# =============================================


def _run_outcome_snapshot_configuration(session_id: UUID | None) -> api._PushConfiguration:
    rollout_name = (
        f"{api.ROLLOUT_FILENAME_PREFIX}{session_id or 'run-outcome-snapshot'}"
        f"{api.ROLLOUT_FILENAME_SUFFIX}"
    )
    return api.push_configuration(str(api.CODEX_SESSIONS_ROOT / rollout_name))


def _capture_run_outcome_snapshot(
    runtime: AiAugmentBackendContext,
) -> tuple[RunOutcomeResponseBody, str | None, tuple[Exception, ...]]:
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

    snapshot = RunOutcomeResponseBody(
        pull_record_id=None if pull_record is None else pull_record.record_id,
        push_record_id=None if push_record is None else push_record.record_id,
        codex_session_record=CodexSessionRecord(
            session_id=session_id,
            codex_rollout_record=(
                None
                if rollout_record is None
                else rollout_record
            ),
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
    return snapshot, rollout_filename, tuple(failures)


def handle_run_outcome_request(
    runtime: AiAugmentBackendContext,
    ipc_request: RunOutcomeRequest,
) -> RunOutcomeResponse:
    if (
        runtime.configured_namekey is None
        or ipc_request.namekey != runtime.configured_namekey
    ):
        raise api._PushValidationError(Locale.REPLAY_RECORD_CONTOUR_INVALID)

    snapshot, rollout_filename, failures = _capture_run_outcome_snapshot(runtime)
    session = snapshot.codex_session_record
    response_code = (
        status.HTTP_200_OK
        if (
            session.session_id is not None
            and session.codex_rollout_record is not None
            and session.appendwatch_report_record is not None
        )
        else status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    response_headers: dict[str, str] | None = None
    if session.codex_rollout_record is not None and rollout_filename is not None:
        response_headers = {
            SOURCE_KEY_HEADER: api._source_key_header(
                rollout_filename,
                session.codex_rollout_record.line_count,
            )
        }
    if failures:
        logger.error(
            Locale.RUN_OUTCOME_SNAPSHOT_FAILED_LOG,
            ipc_request.path,
            "; ".join(str(failure) for failure in failures),
        )

    ready_at_unix_usec = time.time_ns() // NANOSECONDS_PER_MICROSECOND
    response = RunOutcomeResponse.from_run_outcome_request(
        ipc_request,
        response_code=response_code,
        response_headers=response_headers,
        response_body=snapshot,
        ready_to_respond_at_unix_usec=ready_at_unix_usec,
    )
    try:
        stored = runtime.pipeline_config.backend_store.append_authoritative_record(
            response.http_request_log_record,
        )
    except Exception as exc:
        logger.critical(
            Locale.RUN_OUTCOME_SNAPSHOT_APPEND_FATAL_LOG,
            ipc_request.path,
            exc,
        )
        raise SystemExit(1) from exc
    return RunOutcomeResponse.from_http_request_log_record(stored)


# =====================================
# Functions for the GET query endpoint
# =====================================


def handle_query_request(
    runtime: AiAugmentBackendContext,
    ipc_request: QueryRequest,
) -> QueryResponse:
    logger.info("Query IPC: reading wholesale Backend snapshot")
    response = runtime.pipeline_config.backend_store.query(runtime, ipc_request)
    logger.info("Query IPC snapshot ready: %d researchers, %d attempts, %d run outcomes",
                len(response.ai_augment_singular_outerdicts), len(response.attempts),
                len(response.run_outcome_records))
    return response


# =============================================================
# Creation of a `Flask` app object that defines the HTTP routes
# =============================================================

def create_dashboard_query_app(
    query_response_handler: QueryResponseHandler,
    *,
    query_path: str,
    run_outcome_handler: RunOutcomeHandler | None = None,
    run_outcome_paths: frozenset[RunOutcomePath] = frozenset(),
    fatal_exit: Callable[[int], NoReturn] = os._exit,
) -> Flask:
    app = Flask("detour-ai-augment-dashboard-query")

    @app.get(query_path)
    def dashboard_query() -> Response:
        try:
            ipc_request = QueryRequest.from_http_request(
                method=request.method, path=request.path,
                query=request.query_string, body=request.get_data(),
            )
        except ValueError as exc:
            return Response(str(exc), status=400, content_type="text/plain")
        try:
            payload = query_response_handler(ipc_request).model_dump_json()
        except BaseException:
            app.logger.exception("dashboard query failed fatally")
            fatal_exit(1)
        return Response(
            payload.encode(TEXT_ENCODING),
            status=200,
            content_type=JSON_MEDIA_TYPE,
        )

    # ===============================
    # Dynamic registration for each
    # @app.post(run_outcome_path)
    # ===============================

    def run_outcome_request(path: RunOutcomePath) -> Response:
        if run_outcome_handler is None:
            raise RuntimeError("run-outcome IPC handler is unavailable")
        received_at_unix_usec = time.time_ns() // NANOSECONDS_PER_MICROSECOND
        parsed = urlsplit(request.url)
        try:
            request_body = request.get_data()
            ipc_request = RunOutcomeRequest.from_http_request(
                received_at_unix_usec=received_at_unix_usec,
                method=request.method,
                scheme=parsed.scheme,
                host=parsed.hostname or "",
                port=parsed.port,
                path=path,
                query=parsed.query,
                request_headers=dict(request.headers),
                request_body=request_body,
            )
            response_record = run_outcome_handler(ipc_request)
        except BaseException:
            app.logger.exception("dashboard run-outcome request failed fatally")
            fatal_exit(1)
        return Response(
            response_record.response_body,
            status=response_record.response_code,
            headers=dict(response_record.response_headers or {}),
            content_type=JSON_MEDIA_TYPE,
        )

    for run_outcome_path in sorted(run_outcome_paths):
        app.add_url_rule(
            run_outcome_path.value,
            endpoint=f"run-outcome-{run_outcome_path.removeprefix('/')}",
            view_func=lambda path=run_outcome_path: run_outcome_request(path),
            methods=["POST"],
        )

    return app


# =====================================================
# Functions to start/stop IPC server for downstream use
# =====================================================

class _DashboardIpcServer(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, arbitrary_types_allowed=True,
    )

    socket_path: Path
    server: BaseWSGIServer
    thread: threading.Thread


def _unlink_stale_socket(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(mode):
        raise RuntimeError(f"dashboard IPC path is not a Unix socket: {path}")
    path.unlink()


def start_dashboard_query_server(
    socket_path: Path,
    query_response_handler: QueryResponseHandler,
    *,
    query_path: str,
    run_outcome_handler: RunOutcomeHandler | None = None,
    run_outcome_paths: frozenset[RunOutcomePath] = frozenset(),
) -> _DashboardIpcServer:
    app = create_dashboard_query_app(
        query_response_handler,
        query_path=query_path,
        run_outcome_handler=run_outcome_handler,
        run_outcome_paths=run_outcome_paths,
    )
    if not socket_path.is_absolute():
        raise RuntimeError(f"dashboard IPC path is not absolute: {socket_path}")
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    _unlink_stale_socket(socket_path)
    server: BaseWSGIServer | None = None
    try:
        server = make_server(
            f"unix://{socket_path}",
            0,
            app,
            threaded=False,
        )
        socket_path.chmod(SOCKET_PERMISSIONS)
        thread = threading.Thread(
            target=server.serve_forever,
            name="detour-ai-augment-dashboard-ipc",
            daemon=True,
        )
        thread.start()
        print(f"Dashboard IPC running on unix://{socket_path}", flush=True)
        return _DashboardIpcServer(
            socket_path=socket_path,
            server=server,
            thread=thread,
        )
    except BaseException:
        if server is not None:
            server.server_close()
        _unlink_stale_socket(socket_path)
        raise


def stop_dashboard_query_server(handle: _DashboardIpcServer) -> None:
    handle.server.shutdown()
    handle.thread.join()
    handle.server.server_close()
    _unlink_stale_socket(handle.socket_path)


# ===================================================
# Downstream use of start/stop IPC server functions
# ===================================================


def start_full_dashboard_query_server(
    runtime: AiAugmentBackendContext,
) -> _DashboardIpcServer:
    """
    Wrapper for `start_dashboard_query_server` to be used
    downstream as part of another app's lifespan (e.g.,
    to inject in FastAPI's `app.router.lifespan_context`).

    Assumes that `stop_dashboard_query_server`
    is executed in the lifespan's `finally`.
    """
    def run_outcome_handler(request: RunOutcomeRequest) -> RunOutcomeResponse:
        return handle_run_outcome_request(runtime, request)

    def query_response_handler(request: QueryRequest) -> QueryResponse:
        return handle_query_request(runtime, request)

    return start_dashboard_query_server(
        DASHBOARD_SOCKET_PATH,
        query_response_handler,
        query_path=DASHBOARD_QUERY_PATH,
        run_outcome_handler=run_outcome_handler,
        run_outcome_paths=RUN_OUTCOME_PATHS,
    )


def serve_dashboard_query_only(
    runtime: AiAugmentBackendContext,
) -> None:
    """
    Wrapper for `start_dashboard_query_server`
    together with `stop_dashboard_query_server`
    for downstream use as a standalone app;
    owns its own start and stop lifecycle.
    """
    def query_response_handler(request: QueryRequest) -> QueryResponse:
        return handle_query_request(runtime, request)

    server = start_dashboard_query_server(
        DASHBOARD_SOCKET_PATH,
        query_response_handler,
        query_path=DASHBOARD_QUERY_PATH,
    )
    stopped = False

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        nonlocal stopped
        stopped = True

    previous = {
        signum: signal.getsignal(signum)
        for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        for signum in previous:
            signal.signal(signum, request_stop)
        while not stopped:
            if not server.thread.is_alive():
                raise RuntimeError("Backend query server stopped unexpectedly")
            time.sleep(0.1)
    finally:
        try:
            stop_dashboard_query_server(server)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
