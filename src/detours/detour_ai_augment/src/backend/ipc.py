from __future__ import annotations

import logging
import os
import stat
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit

import duckdb
from fastapi import status
from flask import Flask, Response, request
from pydantic import ValidationError
from werkzeug.serving import BaseWSGIServer, make_server

from src.helpers.data_models import NameKey
from src.helpers.data_models.http_request_log import HttpRequestLogRecord
from src.helpers.vars import KTP_NAMEKEY_COL

from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    TEXT_ENCODING,
)

from ..control_centre.dashboard.helpers.data_models.run_outcome import (
    RUN_OUTCOME_PATHS,
    RunOutcomeRequest,
)
from . import api
from .helpers.data_models.commit_event import SOURCE_KEY_HEADER
from .helpers.data_models.run_outcome_response import RunOutcomeResponse

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


def _run_outcome_records(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[RunOutcomeResponse, ...]:
    placeholders = ", ".join("?" for _path in RUN_OUTCOME_PATHS)
    rows = connection.execute(
        f"SELECT {api.AUTHORITATIVE_RECORD_PAYLOAD_COLUMN} "
        f"FROM {api.AUTHORITATIVE_RECORDS_TABLE} "
        f"WHERE {api.AUTHORITATIVE_RECORD_METHOD_COLUMN} = ? "
        f"AND {api.AUTHORITATIVE_RECORD_PATH_COLUMN} IN ({placeholders}) "
        f"ORDER BY {api.AUTHORITATIVE_RECORD_ORDINAL_COLUMN}",
        [api.HTTP_POST_METHOD, *sorted(RUN_OUTCOME_PATHS)],
    ).fetchall()
    try:
        records = tuple(HttpRequestLogRecord.model_validate_json(str(row[0])) for row in rows)
        return tuple(
            RunOutcomeResponse.from_http_request_log_record(record)
            for record in records
        )
    except (ValidationError, ValueError) as exc:
        raise api._PushConfigurationError(Locale.REPLAY_PROJECTION_CONFLICT) from exc


def dashboard_query_payload(namekey: NameKey | None) -> str:
    runtime = api.runtime_configuration()
    with api.synchronized_detour_database(runtime) as connection:
        response = api.dashboard_query_response(
            runtime,
            connection,
            namekey=namekey,
            run_outcome_records=_run_outcome_records(connection),
        )
    return response.model_dump_json()


def ipc_only_dashboard_query_payload(namekey: NameKey | None) -> str:
    runtime = api.runtime_configuration()
    with api.DETOUR_DB_LOCK:
        connection = api.open_detour_database(runtime, read_only=True)
        try:
            response = api.dashboard_query_response(
                runtime,
                connection,
                namekey=namekey,
                run_outcome_records=_run_outcome_records(connection),
            )
        finally:
            connection.close()
    return response.model_dump_json()


def build_ipc_only_dashboard_query_payload_callback(
    config_path: Path,
    *,
    verify_hash_on_init: bool = True,
) -> Callable[[NameKey | None], str]:
    configured = False

    def query(namekey: NameKey | None) -> str:
        nonlocal configured

        if not configured:
            api.configure_runtime(
                config_path,
                require_namekey=False,
                verify_hash_on_init=verify_hash_on_init,
            )
            configured = True
        return ipc_only_dashboard_query_payload(namekey)

    return query


def handle_dashboard_run_outcome_request(
    ipc_request: RunOutcomeRequest,
) -> RunOutcomeResponse:
    runtime = api.runtime_configuration()
    if (
        runtime.configured_namekey is None
        or ipc_request.namekey != runtime.configured_namekey
    ):
        raise api._PushValidationError(Locale.REPLAY_RECORD_CONTOUR_INVALID)

    snapshot, rollout_filename, failures = api.capture_run_outcome_snapshot(runtime)
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
        api.append_authoritative_record(response.http_request_log_record)
    except Exception as exc:
        logger.critical(
            Locale.RUN_OUTCOME_SNAPSHOT_APPEND_FATAL_LOG,
            ipc_request.path,
            exc,
        )
        raise SystemExit(1) from exc
    return response


def create_dashboard_query_app(
    query: Callable[[NameKey | None], str],
    *,
    namekey_parameter: str,
    query_path: str,
    run_outcome_handler: RunOutcomeHandler | None = None,
    run_outcome_paths: frozenset[str] = frozenset(),
    fatal_exit: Callable[[int], NoReturn] = os._exit,
) -> Flask:
    app = Flask("detour-ai-augment-dashboard-query")

    @app.get(query_path)
    def dashboard_query() -> Response:
        try:
            namekey_json = request.args.get(namekey_parameter)
            namekey = (
                None
                if namekey_json is None
                else NameKey.from_json_key(namekey_json)
            )
            payload = query(namekey)
        except BaseException:
            app.logger.exception("dashboard query failed fatally")
            fatal_exit(1)
        return Response(
            payload.encode(TEXT_ENCODING),
            status=200,
            content_type=JSON_MEDIA_TYPE,
        )

    def run_outcome_request(path: str) -> Response:
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
            run_outcome_path,
            endpoint=f"run-outcome-{run_outcome_path.removeprefix('/')}",
            view_func=lambda path=run_outcome_path: run_outcome_request(path),
            methods=["POST"],
        )

    return app


@dataclass(frozen=True, slots=True)
class _DashboardIpcServer:
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
    query: Callable[[NameKey | None], str],
    *,
    namekey_parameter: str,
    query_path: str,
    run_outcome_handler: RunOutcomeHandler | None = None,
    run_outcome_paths: frozenset[str] = frozenset(),
) -> _DashboardIpcServer:
    app = create_dashboard_query_app(
        query,
        namekey_parameter=namekey_parameter,
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


def start_full_dashboard_query_server() -> _DashboardIpcServer:
    return start_dashboard_query_server(
        DASHBOARD_SOCKET_PATH,
        dashboard_query_payload,
        namekey_parameter=KTP_NAMEKEY_COL,
        query_path=DASHBOARD_QUERY_PATH,
        run_outcome_handler=handle_dashboard_run_outcome_request,
        run_outcome_paths=RUN_OUTCOME_PATHS,
    )


def serve_dashboard_query_only(
    config_path: Path,
    *,
    verify_hash_on_init: bool = True,
) -> None:
    server = start_dashboard_query_server(
        DASHBOARD_SOCKET_PATH,
        build_ipc_only_dashboard_query_payload_callback(
            config_path,
            verify_hash_on_init=verify_hash_on_init,
        ),
        namekey_parameter=KTP_NAMEKEY_COL,
        query_path=DASHBOARD_QUERY_PATH,
    )
    try:
        server.thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        stop_dashboard_query_server(server)
        api.close_backend_detour_database()
