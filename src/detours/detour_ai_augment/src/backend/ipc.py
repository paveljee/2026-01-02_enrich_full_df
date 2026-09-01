from __future__ import annotations

import os
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from flask import Flask, Response, request
from werkzeug.serving import BaseWSGIServer, make_server

from .helpers.vars import TEXT_ENCODING

JSON_MEDIA_TYPE = "application/json"
SOCKET_PERMISSIONS = 0o600


def create_dashboard_query_app(
    query: Callable[[str | None], str],
    *,
    namekey_parameter: str,
    query_path: str,
    fatal_exit: Callable[[int], NoReturn] = os._exit,
) -> Flask:
    app = Flask("detour-ai-augment-dashboard-query")

    @app.get(query_path)
    def dashboard_query() -> Response:
        try:
            payload = query(request.args.get(namekey_parameter))
        except BaseException:
            app.logger.exception("dashboard query failed fatally")
            fatal_exit(1)
        return Response(
            payload.encode(TEXT_ENCODING),
            status=200,
            content_type=JSON_MEDIA_TYPE,
        )

    return app


@dataclass(frozen=True, slots=True)
class DashboardIpcServer:
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


def start_dashboard_ipc_server(
    socket_path: Path,
    app: Flask,
) -> DashboardIpcServer:
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
        return DashboardIpcServer(
            socket_path=socket_path,
            server=server,
            thread=thread,
        )
    except BaseException:
        if server is not None:
            server.server_close()
        _unlink_stale_socket(socket_path)
        raise


def stop_dashboard_ipc_server(handle: DashboardIpcServer) -> None:
    handle.server.shutdown()
    handle.thread.join()
    handle.server.server_close()
    _unlink_stale_socket(handle.socket_path)
