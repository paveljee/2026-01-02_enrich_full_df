from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import stat
import threading
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from contextlib import (
    AbstractContextManager,
    asynccontextmanager,
    closing,
    contextmanager,
    nullcontext,
)
from http import HTTPStatus
from pathlib import Path
from types import FrameType
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response
from flask import Flask, request
from flask import Response as FlaskResponse
from pydantic import BaseModel, ConfigDict, PrivateAttr
from rich.console import Console
from starlette.types import ASGIApp, Receive, Scope, Send
from werkzeug.serving import BaseWSGIServer, make_server
from werkzeug.wsgi import ClosingIterator

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend import ipc
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (  # noqa: E501
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    BACKEND_STORE_CLOSED_CLEANLY,
    HTTP_POST_METHOD,
    ContentType,
)
from src.helpers.architecture import FrozenStrictModel

from ..control_centre.dashboard.helpers.data_models.run_outcome import (
    RUN_OUTCOME_PATHS,
    RunOutcomePath,
)
from . import api
from .helpers.data_models.ai_augment_backend_store import (
    AiAugmentBackendStore,
    initialize_backend_store,
)
from .helpers.data_models.ai_augment_context import AiAugmentBackendContext

CONFIG_OPTION = "--config"
IPC_ONLY_OPTION = "--ipc-only"
DANGER_NO_VERIFY_HASH_OPTION = "--danger-no-verify-hash"
logger = logging.getLogger(__name__)


class _BackendRequestGate(FrozenStrictModel):
    """Full-Backend HTTP/IPC admission, owned by its server event loop."""

    _condition: asyncio.Condition = PrivateAttr(default_factory=asyncio.Condition)
    _http_requests: int = PrivateAttr(default=0)
    _ipc_pending: bool = PrivateAttr(default=False)

    @asynccontextmanager
    async def http(self) -> AsyncIterator[None]:
        async with self._condition:
            await self._condition.wait_for(lambda: not self._ipc_pending)
            self._http_requests += 1
        try:
            yield
        finally:
            async with self._condition:
                self._http_requests -= 1
                self._condition.notify_all()

    @asynccontextmanager
    async def ipc(self) -> AsyncIterator[None]:
        """Admit IPC after all in-flight HTTP and authoritative work finishes.

        IPC intentionally permits clients to time out while FastAPI work finishes.
        Client timeouts do not cancel Backend processing or durable persistence;
        there is no IPC admission timeout or automatic retry.
        """
        try:
            async with self._condition:
                self._ipc_pending = True
                logger.info("IPC waiting for %d active HTTP exchanges", self._http_requests)
                await self._condition.wait_for(lambda: self._http_requests == 0)
            pending = tuple(api.AUTHORITATIVE_BACKGROUND_TASKS)
            if pending:
                logger.info("IPC waiting for %d authoritative background tasks", len(pending))
                await asyncio.gather(*(asyncio.shield(task) for task in pending))
            logger.info("IPC admitted after HTTP persistence and authoritative work")
            yield
        finally:
            async with self._condition:
                self._ipc_pending = False
                self._condition.notify_all()


class _BackendRequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def serve() -> None:
            async with scope["app"].state.request_gate.http():
                await self.app(scope, receive, send)

        processing = asyncio.create_task(serve())
        try:
            await asyncio.shield(processing)
        except asyncio.CancelledError:
            # A disconnected client cannot abandon request durability/pull-state wiring.
            await asyncio.shield(processing)
            raise


@contextmanager
def backend_store_lifecycle(
    runtime: AiAugmentBackendContext, *, new: bool, confirmed: bool, yes: bool = False,
) -> Iterator[AiAugmentBackendStore]:
    if not confirmed:
        raise ValueError(Locale.STORE_STARTUP_CONFIRMATION_REQUIRED)
    acquired_lock = api.BACKEND_PROCESS_LOCK_DESCRIPTOR is None
    if acquired_lock:
        api._acquire_backend_process_lock()
    try:
        logger.info("Opening writable Backend Store: new=%s", new)
        with initialize_backend_store(
            runtime,
            ipc_only=False,
            new=new,
            confirmed=confirmed,
            confirm_replay=lambda: confirm_nonempty_replay(yes=yes),
        ) as store:
            logger.info("Writable Backend Store ready")
            yield store
    finally:
        if acquired_lock:
            api._release_backend_process_lock()
    # Not reached on failed startup, application, task settlement or resource cleanup.
    logger.info("Writable Backend Store closed cleanly")
    print(BACKEND_STORE_CLOSED_CLEANLY, flush=True)


@asynccontextmanager
async def lifespan(
    app: FastAPI, runtime: AiAugmentBackendContext, *,
    new: bool, confirmed: bool, yes: bool = False,
) -> AsyncGenerator[None, None]:
    gate = _BackendRequestGate()
    app.state.request_gate = gate
    loop = asyncio.get_running_loop()

    @contextmanager
    def ipc_request_scope() -> Iterator[None]:
        scope = gate.ipc()
        asyncio.run_coroutine_threadsafe(scope.__aenter__(), loop).result()
        try:
            yield
        finally:
            asyncio.run_coroutine_threadsafe(
                scope.__aexit__(None, None, None), loop,
            ).result()

    with backend_store_lifecycle(runtime, new=new, confirmed=confirmed, yes=yes) as store:
        app.state.store = store
        async with api.lifespan(runtime):
            dashboard_query_server = start_full_dashboard_query_server(
                runtime,
                store,
                request_scope=ipc_request_scope,
            )
            try:
                yield
            finally:
                await asyncio.to_thread(stop_dashboard_query_server, dashboard_query_server)


app = FastAPI(**api.APP_CONFIG)


async def _prepared_http_request(request: Request) -> requests.PreparedRequest:
    body = await request.body()
    logger.info(
        Locale.HTTP_REQUEST_RECEIVED_LOG, request.method, request.url.path, len(body)
    )
    return requests.Request(
        request.method,
        str(request.url),
        headers=dict(request.headers),
        data=body,
    ).prepare()


def _http_response(response: requests.Response) -> Response:
    logger.info(
        Locale.HTTP_RESPONSE_SENT_LOG,
        response.request.method,
        response.request.path_url,
        response.status_code,
        len(response.content),
    )
    return Response(
        response.content, status_code=response.status_code, headers=dict(response.headers)
    )


@app.get(**api.PULL_ROUTE, response_class=Response)
async def pull(request: Request) -> Response:
    try:
        return _http_response(
            await api.authoritative_pull(
                await _prepared_http_request(request),
                request.app.state.runtime,
                request.app.state.store,
            )
        )
    except Exception as exc:
        logger.exception(Locale.PULL_PROCESSING_FATAL_LOG)
        raise SystemExit(1) from exc


@app.post(**api.PUSH_ROUTE, response_class=Response)
async def push(request: Request) -> Response:
    try:
        return _http_response(
            await api.authoritative_push(
                await _prepared_http_request(request),
                request.app.state.store,
            )
        )
    except Exception as exc:
        logger.exception(Locale.PUSH_PROCESSING_FATAL_LOG)
        raise SystemExit(1) from exc


def full_backend_application(
    runtime: AiAugmentBackendContext, *, new: bool, confirmed: bool, yes: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def application_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        async with lifespan(app, runtime, new=new, confirmed=confirmed, yes=yes):
            yield

    if not any(
        isinstance(middleware.cls, type) and issubclass(middleware.cls, _BackendRequestMiddleware)
        for middleware in app.user_middleware
    ):
        app.add_middleware(_BackendRequestMiddleware)
    app.state.runtime = runtime
    app.router.lifespan_context = application_lifespan
    return app


IpcRequestScope = Callable[[], AbstractContextManager[None]]


class _DashboardQueryApp(Flask):
    def __init__(self, request_scope: IpcRequestScope) -> None:
        super().__init__("detour-ai-augment-dashboard-query")
        self._request_scope = request_scope

    def wsgi_app(
        self,
        environ: dict[str, Any],
        start_response: Callable[..., Any],
    ) -> Iterator[bytes]:
        with (
            self._request_scope(),
            closing(ClosingIterator(super().wsgi_app(environ, start_response))) as response,
        ):
            yield from response


def create_dashboard_query_app(
    query_response_handler: Callable[[requests.PreparedRequest], requests.Response],
    *,
    query_path: str,
    run_outcome_handler: Callable[[requests.PreparedRequest], requests.Response] | None = None,
    run_outcome_paths: frozenset[RunOutcomePath] = frozenset(),
    fatal_exit: Callable[[int], NoReturn] = os._exit,
    request_scope: IpcRequestScope = nullcontext,
) -> Flask:
    app = _DashboardQueryApp(request_scope)

    def prepared_request() -> requests.PreparedRequest:
        # No loopback request: Requests is only the adapter boundary representation.
        prepared = requests.Request(
            request.method,
            request.url,
            headers=dict(request.headers),
            data=request.get_data(),
        ).prepare()
        return prepared

    def response_from_adapter(response: requests.Response) -> FlaskResponse:
        return FlaskResponse(
            response.content, status=response.status_code, headers=dict(response.headers)
        )

    @app.get(query_path)
    def dashboard_query() -> FlaskResponse:
        prepared = prepared_request()
        try:
            ipc.validate_query_request(prepared)
        except ValueError as exc:
            return FlaskResponse(
                str(exc), status=HTTPStatus.BAD_REQUEST, content_type=ContentType.PLAIN_TEXT,
            )
        try:
            return response_from_adapter(query_response_handler(prepared))
        except BaseException:
            app.logger.exception(Locale.IPC_QUERY_FATAL_LOG)
            fatal_exit(1)

    def run_outcome_request(path: RunOutcomePath) -> FlaskResponse:
        if run_outcome_handler is None:
            raise RuntimeError(Locale.IPC_OUTCOME_HANDLER_UNAVAILABLE)
        try:
            return response_from_adapter(run_outcome_handler(prepared_request()))
        except BaseException:
            app.logger.exception(Locale.IPC_OUTCOME_FATAL_LOG)
            fatal_exit(1)

    for run_outcome_path in sorted(run_outcome_paths):
        app.add_url_rule(
            run_outcome_path.value,
            endpoint=f"run-outcome-{run_outcome_path.removeprefix('/')}",
            view_func=lambda path=run_outcome_path: run_outcome_request(path),
            methods=[HTTP_POST_METHOD],
        )

    return app


# =====================================================
# Functions to start/stop IPC server for downstream use
# =====================================================


class _DashboardIpcServer(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        arbitrary_types_allowed=True,
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
        raise RuntimeError(Locale.IPC_PATH_NOT_SOCKET_TEMPLATE.format(path=path))
    path.unlink()


def start_dashboard_query_server(
    socket_path: Path,
    query_response_handler: Callable[[requests.PreparedRequest], requests.Response],
    *,
    query_path: str,
    run_outcome_handler: Callable[[requests.PreparedRequest], requests.Response] | None = None,
    run_outcome_paths: frozenset[RunOutcomePath] = frozenset(),
    request_scope: IpcRequestScope = nullcontext,
) -> _DashboardIpcServer:
    app = create_dashboard_query_app(
        query_response_handler,
        query_path=query_path,
        run_outcome_handler=run_outcome_handler,
        run_outcome_paths=run_outcome_paths,
        request_scope=request_scope,
    )
    if not socket_path.is_absolute():
        raise RuntimeError(Locale.IPC_PATH_NOT_ABSOLUTE_TEMPLATE.format(path=socket_path))
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
        socket_path.chmod(ipc.SOCKET_PERMISSIONS)
        thread = threading.Thread(
            target=server.serve_forever,
            name="detour-ai-augment-dashboard-ipc",
            daemon=True,
        )
        thread.start()
        print(Locale.IPC_RUNNING_TEMPLATE.format(path=socket_path), flush=True)
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
    store: BackendComponent.FullStoreProperty,
    *,
    request_scope: IpcRequestScope = nullcontext,
) -> _DashboardIpcServer:
    def outcome(request: requests.PreparedRequest) -> requests.Response:
        return asyncio.run(ipc.handle_run_outcome_request(runtime, store, request))

    def query(request: requests.PreparedRequest) -> requests.Response:
        return asyncio.run(ipc.handle_query_request(store, request))

    return start_dashboard_query_server(
        ipc.DASHBOARD_SOCKET_PATH,
        query,
        query_path=ipc.DASHBOARD_QUERY_PATH,
        run_outcome_handler=outcome,
        run_outcome_paths=RUN_OUTCOME_PATHS,
        request_scope=request_scope,
    )


def serve_dashboard_query_only(
    store: BackendComponent.QueryOnlyStoreProperty,
) -> None:
    """
    Wrapper for `start_dashboard_query_server`
    together with `stop_dashboard_query_server`
    for downstream use as a standalone app;
    owns its own start and stop lifecycle.
    """

    def query_response_handler(request: requests.PreparedRequest) -> requests.Response:
        return asyncio.run(ipc.handle_query_request(store, request))

    server = start_dashboard_query_server(
        ipc.DASHBOARD_SOCKET_PATH,
        query_response_handler,
        query_path=ipc.DASHBOARD_QUERY_PATH,
    )
    stopped = False

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        nonlocal stopped
        stopped = True

    previous = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGINT)}
    try:
        for signum in previous:
            signal.signal(signum, request_stop)
        while not stopped:
            if not server.thread.is_alive():
                raise RuntimeError(Locale.IPC_QUERY_STOPPED_UNEXPECTEDLY)
            time.sleep(0.1)
    finally:
        try:
            stop_dashboard_query_server(server)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def configure_runtime(
    config_path: Path,
    *,
    require_namekey: bool = True,
    verify_hash_on_init: bool = True,
) -> AiAugmentBackendContext:
    logger.info("Loading Backend configuration/resources: %s; verify_hashes=%s",
                config_path, verify_hash_on_init)
    try:
        pipeline = AiAugmentDetourConfig.from_json(
            config_path,
            verify_hash_on_init=verify_hash_on_init,
        )
    except (OSError, ValueError) as exc:
        raise api._PushConfigurationError(
            Locale.CONFIG_INVALID_TEMPLATE.format(config_path=config_path)
        ) from exc
    if not pipeline.db_file.is_file() or not os.access(pipeline.db_file, os.R_OK):
        raise api._PushConfigurationError(
            Locale.SOURCE_DUCKDB_UNREADABLE_TEMPLATE.format(
                db_file=pipeline.db_file
            )
        )
    try:
        ZoneInfo(pipeline.timezone)
    except (KeyError, ValueError) as exc:
        raise api._PushConfigurationError(
            Locale.TIMEZONE_INVALID_TEMPLATE.format(timezone=pipeline.timezone)
        ) from exc

    configured_namekey = api._configured_namekey() if require_namekey else None
    runtime = AiAugmentBackendContext(
        pipeline_config=pipeline,
        configured_namekey=configured_namekey,
    )
    logger.info("Loading researchers from read-only source DB: %s", pipeline.db_file)
    try:
        singular_outerdicts = runtime.ai_augment_singular_outerdicts
        if configured_namekey is not None:
            api._configured_ai_augment_singular_outerdict(
                configured_namekey,
                singular_outerdicts,
            )
    except ValueError as exc:
        raise api._PushConfigurationError(str(exc)) from exc
    logger.info("Backend runtime ready: %d researchers; selected=%s",
                len(singular_outerdicts), configured_namekey)
    return runtime


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=Locale.CLI_DESCRIPTION)
    parser.add_argument(CONFIG_OPTION, required=True, type=Path)
    parser.add_argument(IPC_ONLY_OPTION, action="store_true")
    parser.add_argument(DANGER_NO_VERIFY_HASH_OPTION, action="store_true")
    parser.add_argument("--new", action="store_true")
    parser.add_argument("--resume", "--continue", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.ipc_only:
        # Initialization flags have no effect in query-only mode.
        args.new = False
        args.resume = False
    elif args.new == args.resume:
        parser.error("Full Backend requires exactly one of --new or --resume/--continue")
    return args


def confirm_startup(args: argparse.Namespace) -> bool:
    if args.yes:
        return True
    prompt = (
        "Recreate the AI augment detour database from the replay log? [y/N] "
        if args.new else "Resume the AI augment detour database without rebuilding? [y/N] "
    )
    try:
        confirmed = Console().input(prompt, markup=False).strip().lower() == "y"
    except EOFError:
        confirmed = False
    if not confirmed:
        raise ValueError(Locale.STORE_STARTUP_CONFIRMATION_REQUIRED)
    return True


def confirm_nonempty_replay(*, yes: bool) -> bool:
    if yes:
        return True
    try:
        return Console().input(
            "Registered a nonempty replay log. Replay it into the new database? [y/N] ",
            markup=False,
        ).strip().lower() == "y"
    except EOFError:
        return False


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args(argv)
    logger.info("Starting Backend: config=%s; ipc_only=%s; new=%s; resume=%s",
                args.config, args.ipc_only, args.new, args.resume)
    confirmed = False if args.ipc_only else confirm_startup(args)
    verify_hash_on_init = not args.danger_no_verify_hash
    api._acquire_backend_process_lock()
    try:
        runtime = configure_runtime(
            args.config,
            require_namekey=not args.ipc_only,
            verify_hash_on_init=verify_hash_on_init,
        )
        if args.ipc_only:
            logger.info("Opening read-only Backend Store")
            with initialize_backend_store(runtime, ipc_only=True) as store:
                logger.info("Read-only Backend Store ready; starting query-only IPC")
                serve_dashboard_query_only(store)
            logger.info("Query-only IPC stopped; read-only Backend Store closed cleanly")
            print(BACKEND_STORE_CLOSED_CLEANLY, flush=True)
        else:
            logger.info("Starting Backend HTTP API at %s:%s", api.SERVER_HOST, api.SERVER_PORT)
            uvicorn.run(
                full_backend_application(
                    runtime, new=args.new, confirmed=confirmed, yes=args.yes,
                ),
                host=api.SERVER_HOST,
                port=api.SERVER_PORT,
            )
    except BaseException:
        logger.exception("Backend failed; exiting without recovery")
        raise
    finally:
        api._release_backend_process_lock()
        logger.info("Backend process lock released")


if __name__ == "__main__":
    main()
