from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import stat
import threading
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Generator, Iterator
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
from urllib.parse import urlsplit
from uuid import uuid7
from zoneinfo import ZoneInfo

import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response
from flask import Flask, request
from flask import Response as FlaskResponse
from pydantic import BaseModel, ConfigDict, PrivateAttr
from requests.structures import CaseInsensitiveDict
from rich.console import Console
from starlette.types import ASGIApp, Receive, Scope, Send
from werkzeug.serving import BaseWSGIServer, make_server
from werkzeug.wsgi import ClosingIterator

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
    ControlCentreComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers import api
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (  # noqa: E501
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.store import (
    AiAugmentBackendStore,
    initialize_backend_store,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_HTTP_SCOPE_TYPE,
    ASGI_TYPE_KEY,
    BACKEND_STORE_CLOSED_CLEANLY,
    DASHBOARD_QUERY_PATH,
    DASHBOARD_SOCKET_PATH,
    HTTP_CONTENT_TYPE_HEADER,
    HTTP_POST_METHOD,
    INIT_PATH,
    LOCATION_HEADER,
    NAME_KEY_HEADER,
    NAMEKEY_ENV_NAME,
    NANOSECONDS_PER_MICROSECOND,
    PULL_PATH,
    RETRY_AFTER_HEADER,
    RETRY_AFTER_SECONDS,
    SERVER_HOST,
    SERVER_PORT,
    SOCKET_PERMISSIONS,
    SOURCE_KEY_HEADER,
    SYNTHETIC_COMMIT_HOST,
    SYNTHETIC_COMMIT_SCHEME,
    TEXT_ENCODING,
    VALID_NONBLANK,
    ContentType,
)
from src.detours.detour_ai_augment.protected.src.shared import (
    name_key_from_header_value,
    name_key_header_value,
    source_key_header_value,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_request import (
    _CodexSessionRecordJson,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.init_request import (
    BackendInitRequestRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.lifecycle import BackendLifecycle
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
from src.detours.detour_ai_augment.src.backend.helpers.data_models.validation_request import (
    BackendValidationRequestRecord,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.query_event import (  # noqa: E501
    QueryRequestRecord,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome_event import (  # noqa: E501
    RUN_OUTCOME_PATHS,
    RunOutcome,
    RunOutcomePath,
    RunOutcomeRequestRecord,
    RunOutcomeResponseRecord,
    _RunOutcomeResponseBodyJson,
)
from src.helpers.architecture import FrozenStrictModel
from src.helpers.data_models import NameKey
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

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
            await self._condition.wait_for(
                lambda: not self._ipc_pending and self._http_requests == 0
            )
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
                logger.info(Locale.BACKEND_IPC_WAIT_HTTP_LOG, self._http_requests)
                await self._condition.wait_for(lambda: self._http_requests == 0)
            pending = tuple(api.AUTHORITATIVE_BACKGROUND_TASKS)
            if pending:
                logger.info(Locale.BACKEND_IPC_WAIT_WORK_LOG, len(pending))
                await asyncio.gather(*(asyncio.shield(task) for task in pending))
            logger.info(Locale.BACKEND_IPC_ADMITTED_LOG)
            yield
        finally:
            async with self._condition:
                self._ipc_pending = False
                self._condition.notify_all()


class _BackendRequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope[ASGI_TYPE_KEY] != ASGI_HTTP_SCOPE_TYPE:
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
    context: AiAugmentBackendContext, *, init_request_record: BackendInitRequestRecord,
    new: bool, confirmed: bool, yes: bool = False,
) -> Generator[AiAugmentBackendStore, None, None]:
    if not confirmed:
        raise ValueError(Locale.STORE_STARTUP_CONFIRMATION_REQUIRED)
    acquired_lock = api.BACKEND_PROCESS_LOCK_DESCRIPTOR is None
    if acquired_lock:
        api._acquire_backend_process_lock()
    try:
        logger.info(Locale.BACKEND_STORE_OPEN_WRITABLE_LOG, new)
        with initialize_backend_store(
            context,
            ipc_only=False,
            init_request_record=init_request_record,
            new=new,
            confirmed=confirmed,
            confirm_replay=lambda: confirm_nonempty_replay(yes=yes),
        ) as store:
            logger.info(Locale.BACKEND_STORE_READY_LOG)
            yield store
    finally:
        if acquired_lock:
            api._release_backend_process_lock()
    # Not reached on failed startup, application, task settlement or resource cleanup.
    logger.info(Locale.BACKEND_STORE_CLOSED_LOG)
    print(BACKEND_STORE_CLOSED_CLEANLY, flush=True)


@asynccontextmanager
async def lifespan(
    app: FastAPI, context: AiAugmentBackendContext, *,
    init_request_record: BackendInitRequestRecord,
    new: bool, confirmed: bool, yes: bool = False,
) -> AsyncGenerator[None, None]:
    gate = _BackendRequestGate()
    app.state.request_gate = gate
    loop = asyncio.get_running_loop()

    @contextmanager
    def ipc_request_scope() -> Generator[None, None, None]:
        scope = gate.ipc()
        asyncio.run_coroutine_threadsafe(scope.__aenter__(), loop).result()
        try:
            yield
        finally:
            asyncio.run_coroutine_threadsafe(
                scope.__aexit__(None, None, None), loop,
            ).result()

    with backend_store_lifecycle(
        context, init_request_record=init_request_record,
        new=new, confirmed=confirmed, yes=yes,
    ) as store:
        app.state.store = store
        async with api.lifespan():
            dashboard_query_server = start_full_dashboard_query_server(
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
    received = time.time_ns() // NANOSECONDS_PER_MICROSECOND
    try:
        prepared = await _prepared_http_request(request)
        target = urlsplit(prepared.url or "")
        request_record = PullRequestRecord(
            schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            method=prepared.method or "",
            scheme=target.scheme,
            host=target.hostname or "",
            port=target.port,
            path=target.path,
            query=target.query,
            request_headers=dict(prepared.headers),
            request_body=api._request_body_for_authoritative_log(
                api._prepared_request_body(prepared)
            ),
            response_code=None,
            response_headers=None,
            response_body=None,
            received_at_unix_usec=received,
            ready_to_respond_at_unix_usec=None,
            duration_usec=0,
        )
        assert request_record.received_at_unix_usec is not None
        store = request.app.state.store
        try:
            reply = api._pull_response(store)
        except Exception as exc:
            logger.error(Locale.PULL_FAILED_LOG, exc)
            reply = api._error_response(HTTPStatus.INTERNAL_SERVER_ERROR)
        ready = time.time_ns() // NANOSECONDS_PER_MICROSECOND
        current = store.current_replayed_record
        linked_validation = None
        if (
            reply.status_code == HTTPStatus.OK
            and reply.headers.get(HTTP_CONTENT_TYPE_HEADER) == ContentType.MARKDOWN_UTF8
        ):
            if isinstance(current, BackendValidationRequestRecord):
                linked_validation = current
            elif isinstance(current, PullResponseRecord):
                linked_validation = current.validation_request_record
        response_record = PullResponseRecord(
            schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            method=prepared.method or "",
            scheme=target.scheme,
            host=target.hostname or "",
            port=target.port,
            path=target.path,
            query=target.query,
            request_headers=dict(prepared.headers),
            request_body=api._request_body_for_authoritative_log(
                api._prepared_request_body(prepared)
            ),
            response_code=reply.status_code,
            response_headers=dict(reply.headers),
            response_body=reply.content.decode(TEXT_ENCODING),
            received_at_unix_usec=None,
            ready_to_respond_at_unix_usec=ready,
            duration_usec=ready - request_record.received_at_unix_usec,
            validation_request_record=linked_validation,
        )
        promise = await asyncio.to_thread(store.promise_pull_response_record, response_record)
        stored, error = await promise.response_record_promise()
        if error is not None:
            error.raise_exception()
        if promise.acknowledgment is not BackendStoreAcknowledgment.ACK or stored is None:
            raise BackendStoreException(Locale.PULL_DURABLE_RESPONSE_MISSING)
        logger.info(Locale.PULL_PERSISTED_LOG, stored.record_id, stored.response_code)
        return _http_response(stored.to_response())
    except Exception as exc:
        logger.exception(Locale.PULL_PROCESSING_FATAL_LOG)
        raise SystemExit(1) from exc


@app.post(**api.PUSH_ROUTE, response_class=Response)
async def push(request: Request) -> Response:
    received = time.time_ns() // NANOSECONDS_PER_MICROSECOND
    try:
        prepared = await _prepared_http_request(request)
        target = urlsplit(prepared.url or "")
        request_record = PushRequestRecord(
            schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            method=prepared.method or "",
            scheme=target.scheme,
            host=target.hostname or "",
            port=target.port,
            path=target.path,
            query=target.query,
            request_headers=dict(prepared.headers),
            request_body=api._request_body_for_authoritative_log(
                api._prepared_request_body(prepared)
            ),
            response_code=None,
            response_headers=None,
            response_body=None,
            received_at_unix_usec=received,
            ready_to_respond_at_unix_usec=None,
            duration_usec=0,
        )
        assert request_record.received_at_unix_usec is not None
        store = request.app.state.store
        with api.BACKEND_WORKFLOW_STATE_LOCK:
            lifecycle = api.BACKEND_LIFECYCLE
            session_id = api.BACKEND_SESSION_ID
            current_replayed_record = store.current_replayed_record
            pull_response_record = (
                current_replayed_record
                if isinstance(current_replayed_record, PullResponseRecord)
                else None
            )
            logger.info(
                Locale.PUSH_REQUEST_STATE_LOG, lifecycle, session_id,
                None if pull_response_record is None else pull_response_record.record_id,
            )

            if lifecycle is BackendLifecycle.BUSY:
                provisional_reply = api._error_response(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    headers={RETRY_AFTER_HEADER: RETRY_AFTER_SECONDS},
                )
            elif (
                lifecycle not in {BackendLifecycle.READY, BackendLifecycle.RETRY}
                or session_id is None
            ):
                logger.error(Locale.PUSH_SESSION_NOT_READY_LOG)
                provisional_reply = api._error_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            else:
                commit_request_record, _ = store._cursor_commit_validation()
                if (
                    pull_response_record is None
                    or pull_response_record.response_code != HTTPStatus.OK
                    or (
                        commit_request_record is not None
                        and commit_request_record.commit_request_body.pull_response_record.record_id
                        == pull_response_record.record_id
                    )
                ):
                    logger.warning(Locale.PUSH_CURRENT_PULL_REQUIRED_LOG)
                    provisional_reply = api._error_response(
                        HTTPStatus.CONFLICT,
                        headers={LOCATION_HEADER: PULL_PATH},
                    )
                else:
                    api.BACKEND_LIFECYCLE = BackendLifecycle.BUSY
                    provisional_reply = api._response(
                        HTTPStatus.ACCEPTED,
                        headers={LOCATION_HEADER: PULL_PATH},
                    )
        ready = time.time_ns() // NANOSECONDS_PER_MICROSECOND
        response_record = PushResponseRecord(
            schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            method=prepared.method or "",
            scheme=target.scheme,
            host=target.hostname or "",
            port=target.port,
            path=target.path,
            query=target.query,
            request_headers=dict(prepared.headers),
            request_body=api._request_body_for_authoritative_log(
                api._prepared_request_body(prepared)
            ),
            response_code=provisional_reply.status_code,
            response_headers=dict(provisional_reply.headers),
            response_body=provisional_reply.content.decode(TEXT_ENCODING),
            received_at_unix_usec=None,
            ready_to_respond_at_unix_usec=ready,
            duration_usec=ready - request_record.received_at_unix_usec,
            pull_response_record=(
                pull_response_record
                if provisional_reply.status_code == HTTPStatus.ACCEPTED else None
            ),
        )
        immediate, promise = await asyncio.to_thread(
            store.promise_push_response_record, response_record, session_id=session_id,
        )
        # The immediate record is the replayed push for this HTTP reply. The promise yields
        # that same instance later, after commit/validation, for `finish_push` to check.
        if promise.acknowledgment is not BackendStoreAcknowledgment.ACK:
            _, error = await promise.response_record_promise()
            if error is not None:
                error.raise_exception()
            raise BackendStoreException(Locale.PUSH_NAK_ERROR_MISSING)
        if immediate is None:
            _, error = await promise.response_record_promise()
            if error is not None:
                error.raise_exception()
            raise BackendStoreException(Locale.PUSH_RESPONSE_RECORD_MISSING)
        assert immediate.response_code == provisional_reply.status_code
        expected_pull = (
            pull_response_record if immediate.response_code == HTTPStatus.ACCEPTED else None
        )
        assert immediate.pull_response_record is expected_pull
        if immediate.response_code == HTTPStatus.ACCEPTED:
            # this below hands off the awaiting to a new asyncio task,
            # allowing server to release a response to the HTTP client
            # who had sent the push request:
            api._continue_awaiting_on_stores_push_promise(promise, store)
            logger.info(Locale.PUSH_DURABLY_ACCEPTED_LOG, immediate.record_id)
            return _http_response(immediate.to_response())
        resolved, error = await promise.response_record_promise()
        if error is not None:
            error.raise_exception()
        assert resolved is immediate
        logger.info(Locale.PUSH_PERSISTED_LOG, resolved.record_id, resolved.response_code)
        return _http_response(resolved.to_response())
    except Exception as exc:
        logger.exception(Locale.PUSH_PROCESSING_FATAL_LOG)
        raise SystemExit(1) from exc


def full_backend_application(
    context: AiAugmentBackendContext, *, init_request_record: BackendInitRequestRecord,
    new: bool, confirmed: bool, yes: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def application_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        async with lifespan(
            app, context, init_request_record=init_request_record,
            new=new, confirmed=confirmed, yes=yes,
        ):
            yield

    if not any(
        isinstance(middleware.cls, type) and issubclass(middleware.cls, _BackendRequestMiddleware)
        for middleware in app.user_middleware
    ):
        app.add_middleware(_BackendRequestMiddleware)
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
    query_response_handler: Callable[
        [ControlCentreComponent.BackendPort.QueryRequestRecordProperty],
        BackendComponent.ResponseRecordPromiseProperty[
            ControlCentreComponent.BackendPort.QueryResponseRecordProperty
        ],
    ],
    *,
    query_path: str,
    run_outcome_store: AiAugmentBackendStore | None = None,
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
        received = time.time_ns() // NANOSECONDS_PER_MICROSECOND
        prepared = prepared_request()
        target = urlsplit(prepared.url or "")
        try:
            request_record = QueryRequestRecord(
                schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
                method=prepared.method or "",
                scheme=target.scheme,
                host=target.hostname or "",
                port=target.port,
                path=target.path,
                query=target.query,
                request_headers=dict(prepared.headers),
                request_body=(
                    api._request_body_for_authoritative_log(api._prepared_request_body(prepared))
                    if api._prepared_request_body(prepared) else None
                ),
                response_code=None,
                response_headers=None,
                response_body=None,
                received_at_unix_usec=received,
                ready_to_respond_at_unix_usec=None,
                duration_usec=0,
            )
            if target.query or api._prepared_request_body(prepared):
                raise ValueError(Locale.QUERY_REQUEST_INVALID)
        except ValueError as exc:
            return FlaskResponse(
                str(exc), status=HTTPStatus.BAD_REQUEST, content_type=ContentType.PLAIN_TEXT,
            )
        try:
            logger.info(Locale.QUERY_SNAPSHOT_READING_LOG)
            promise = query_response_handler(request_record)
            if promise.acknowledgment is not BackendStoreAcknowledgment.NAK:
                raise BackendStoreException(Locale.IPC_REQUEST_UNEXPECTEDLY_PERSISTED)
            response_record, error = asyncio.run(promise.response_record_promise())
            if error is not None:
                error.raise_exception()
            if response_record is None:
                raise BackendStoreException(Locale.IPC_RESPONSE_MISSING)
            logger.info(
                Locale.QUERY_SNAPSHOT_READY_LOG,
                len(response_record.ai_augment_singular_outerdicts),
            )
            return response_from_adapter(response_record.to_response())
        except BaseException:
            app.logger.exception(Locale.IPC_QUERY_FATAL_LOG)
            fatal_exit(1)

    def run_outcome_request(path: RunOutcomePath) -> FlaskResponse:
        received = time.time_ns() // NANOSECONDS_PER_MICROSECOND
        if run_outcome_store is None:
            raise RuntimeError(Locale.IPC_OUTCOME_HANDLER_UNAVAILABLE)
        try:
            prepared = prepared_request()
            target = urlsplit(prepared.url or "")
            raw_body = api._prepared_request_body(prepared)
            request_record = RunOutcomeRequestRecord(
                schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
                method=prepared.method or "",
                scheme=target.scheme,
                host=target.hostname or "",
                port=target.port,
                path=target.path,
                query=target.query,
                request_headers=dict(prepared.headers),
                request_body=(
                    api._request_body_for_authoritative_log(raw_body) if raw_body else None
                ),
                response_code=None,
                response_headers=None,
                response_body=None,
                received_at_unix_usec=received,
                ready_to_respond_at_unix_usec=None,
                duration_usec=0,
            )
            with api.BACKEND_WORKFLOW_STATE_LOCK:
                session_id = api.BACKEND_SESSION_ID
            session, rollout_filename, failures = run_outcome_store.capture_run_outcome_snapshot(
                session_id,
            )
            if failures:
                logger.error(
                    Locale.RUN_OUTCOME_SNAPSHOT_FAILED_LOG,
                    request_record.path,
                    "; ".join(str(failure) for failure in failures),
                )
            init_request_record = run_outcome_store._init_request_record
            if init_request_record is None:
                raise RuntimeError(Locale.INIT_REQUEST_RECORD_REQUIRED)
            commit, validation = run_outcome_store._cursor_commit_validation()
            if request_record.namekey != init_request_record.namekey:
                identity_error = Locale.RUN_OUTCOME_NAMEKEY_MISMATCH
            elif session.session_id is None or request_record.session_id != session.session_id:
                identity_error = Locale.RUN_OUTCOME_SESSION_MISMATCH
            elif SOURCE_KEY_HEADER in CaseInsensitiveDict(request_record.request_headers):
                identity_error = Locale.RUN_OUTCOME_HEADERS_INVALID
            elif request_record.request_body not in (None, ""):
                identity_error = Locale.RUN_OUTCOME_BODY_UNEXPECTED
            elif request_record.query:
                identity_error = Locale.RUN_OUTCOME_QUERY_UNEXPECTED
            elif request_record.run_outcome is RunOutcome.COMPLETED and (
                validation is None
                or request_record.validation_request_record_id != validation.record_id
            ):
                identity_error = Locale.RUN_OUTCOME_ETAG_MISMATCH
            else:
                identity_error = None
            if identity_error is None and validation is not None and (
                commit is None
                or validation.validation_request_body.commit_request_record.record_id
                != commit.record_id
            ):
                identity_error = Locale.RUN_OUTCOME_VALIDATION_LINKAGE_CORRUPT
            if identity_error is None and commit is not None and (
                commit.commit_request_body.codex_session_record.session_id
                != request_record.session_id
                or name_key_from_header_value(commit.request_headers.get(NAME_KEY_HEADER))
                != request_record.namekey
            ):
                identity_error = Locale.RUN_OUTCOME_REPLAY_INPUTS_DIFFER
            if identity_error is not None:
                logger.error(Locale.RUN_OUTCOME_REJECTED_LOG, request_record.path, identity_error)
            pull_id, push_id = run_outcome_store._cursor_http_ids()
            rollout = session.codex_rollout_record
            headers = None
            if rollout is not None:
                if rollout_filename is None:
                    raise BackendStoreException(Locale.RUN_OUTCOME_ROLLOUT_FILENAME_MISSING)
                headers = {
                    SOURCE_KEY_HEADER: source_key_header_value(
                        rollout_filename, rollout.line_count,
                    )
                }
            code = (
                HTTPStatus.BAD_REQUEST if identity_error is not None
                else run_outcome_store._run_outcome_code(request_record.path, session, validation)
            )
            response_id = uuid7()
            body = _RunOutcomeResponseBodyJson(
                pull_record_id=pull_id,
                push_record_id=push_id,
                commit_request_record_id=None if commit is None else commit.record_id,
                validation_record_id=None if validation is None else validation.record_id,
                run_outcome_record_id=response_id,
                codex_session_record=_CodexSessionRecordJson(
                    codex_session_id=session.session_id,
                    codex_rollout_record=session.codex_rollout_record,
                    appendwatch_report_record=session.appendwatch_report_record,
                ),
            ).model_dump_json()
            reply = api._response(code, body, content_type=ContentType.JSON, headers=headers)
            ready = time.time_ns() // NANOSECONDS_PER_MICROSECOND
            response_record = RunOutcomeResponseRecord(
                schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
                record_id=response_id,
                method=prepared.method or "",
                scheme=target.scheme,
                host=target.hostname or "",
                port=target.port,
                path=target.path,
                query=target.query,
                request_headers=dict(prepared.headers),
                request_body=(
                    api._request_body_for_authoritative_log(raw_body) if raw_body else None
                ),
                response_code=reply.status_code,
                response_headers=dict(reply.headers),
                response_body=reply.content.decode(TEXT_ENCODING),
                received_at_unix_usec=None,
                ready_to_respond_at_unix_usec=ready,
                duration_usec=ready - received,
                run_outcome_request_record=request_record,
                attempt=validation,
            )
            promise = run_outcome_store.run_outcome_response_record(response_record)
            if promise.acknowledgment is not BackendStoreAcknowledgment.NAK:
                raise BackendStoreException(Locale.IPC_REQUEST_UNEXPECTEDLY_PERSISTED)
            stored, error = asyncio.run(promise.response_record_promise())
            if error is not None:
                error.raise_exception()
            if stored is None:
                raise BackendStoreException(Locale.IPC_RESPONSE_MISSING)
            logger.info(Locale.RUN_OUTCOME_PERSISTED_LOG, stored.record_id, stored.response_code)
            return response_from_adapter(stored.to_response())
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
    query_response_handler: Callable[
        [ControlCentreComponent.BackendPort.QueryRequestRecordProperty],
        BackendComponent.ResponseRecordPromiseProperty[
            ControlCentreComponent.BackendPort.QueryResponseRecordProperty
        ],
    ],
    *,
    query_path: str,
    run_outcome_store: AiAugmentBackendStore | None = None,
    run_outcome_paths: frozenset[RunOutcomePath] = frozenset(),
    request_scope: IpcRequestScope = nullcontext,
) -> _DashboardIpcServer:
    app = create_dashboard_query_app(
        query_response_handler,
        query_path=query_path,
        run_outcome_store=run_outcome_store,
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
        socket_path.chmod(SOCKET_PERMISSIONS)
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
    store: AiAugmentBackendStore,
    *,
    request_scope: IpcRequestScope = nullcontext,
) -> _DashboardIpcServer:
    return start_dashboard_query_server(
        DASHBOARD_SOCKET_PATH,
        store.query_response_record,
        query_path=DASHBOARD_QUERY_PATH,
        run_outcome_store=store,
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

    server = start_dashboard_query_server(
        DASHBOARD_SOCKET_PATH,
        store.query_response_record,
        query_path=DASHBOARD_QUERY_PATH,
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
    verify_hash_on_init: bool = True,
) -> AiAugmentBackendContext:
    logger.info(Locale.BACKEND_CONFIG_LOADING_LOG,
                config_path, verify_hash_on_init)
    try:
        pipeline = AiAugmentDetourConfig.from_json(
            config_path,
            verify_hash_on_init=verify_hash_on_init,
        )
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            Locale.CONFIG_INVALID_TEMPLATE.format(config_path=config_path)
        ) from exc
    if not pipeline.db_file.is_file() or not os.access(pipeline.db_file, os.R_OK):
        raise RuntimeError(
            Locale.SOURCE_DUCKDB_UNREADABLE_TEMPLATE.format(
                db_file=pipeline.db_file
            )
        )
    try:
        ZoneInfo(pipeline.timezone)
    except (KeyError, ValueError) as exc:
        raise RuntimeError(
            Locale.TIMEZONE_INVALID_TEMPLATE.format(timezone=pipeline.timezone)
        ) from exc

    try:
        context = AiAugmentBackendContext(pipeline_config=pipeline)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    logger.info(
        Locale.BACKEND_CONFIG_VALIDATED_LOG,
        len(context.ai_augment_singular_outerdict_blueprints),
    )
    return context


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
        parser.error(Locale.BACKEND_START_FLAGS_REQUIRED)
    return args


def confirm_startup(args: argparse.Namespace) -> bool:
    if args.yes:
        return True
    prompt = (
        Locale.BACKEND_RECREATE_PROMPT
        if args.new else Locale.BACKEND_RESUME_PROMPT
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
            Locale.BACKEND_NONEMPTY_REPLAY_PROMPT,
            markup=False,
        ).strip().lower() == "y"
    except EOFError:
        return False


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args(argv)
    logger.info(Locale.BACKEND_STARTING_LOG,
                args.config, args.ipc_only, args.new, args.resume)
    confirmed = False if args.ipc_only else confirm_startup(args)
    verify_hash_on_init = not args.danger_no_verify_hash
    api._acquire_backend_process_lock()
    try:
        context = configure_runtime(
            args.config,
            verify_hash_on_init=verify_hash_on_init,
        )
        if args.ipc_only:
            logger.info(Locale.BACKEND_STORE_OPEN_READ_ONLY_LOG)
            with initialize_backend_store(context, ipc_only=True) as store:
                logger.info(Locale.BACKEND_STORE_READ_ONLY_READY_LOG)
                serve_dashboard_query_only(store)
            logger.info(Locale.BACKEND_STORE_READ_ONLY_CLOSED_LOG)
            print(BACKEND_STORE_CLOSED_CLEANLY, flush=True)
        else:
            raw_namekey = os.environ.get(NAMEKEY_ENV_NAME)
            if not VALID_NONBLANK(raw_namekey):
                raise ValueError(
                    Locale.NAMEKEY_NOT_SET_TEMPLATE.format(
                        environment_name=NAMEKEY_ENV_NAME,
                    )
                )
            assert isinstance(raw_namekey, str)
            try:
                startup_namekey = NameKey.from_json_key(raw_namekey)
            except (TypeError, ValueError) as exc:
                raise ValueError(Locale.CONFIGURED_NAMEKEY_MALFORMED) from exc
            context.blueprint_for_namekey(startup_namekey)
            init_request_record = BackendInitRequestRecord(
                schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
                method=HTTP_POST_METHOD,
                scheme=SYNTHETIC_COMMIT_SCHEME,
                host=SYNTHETIC_COMMIT_HOST,
                port=None,
                path=INIT_PATH,
                query="",
                request_headers={
                    NAME_KEY_HEADER: name_key_header_value(startup_namekey),
                },
                request_body=None,
                response_code=None,
                response_headers=None,
                response_body=None,
                received_at_unix_usec=None,
                ready_to_respond_at_unix_usec=(
                    time.time_ns() // NANOSECONDS_PER_MICROSECOND
                ),
                duration_usec=0,
            )
            logger.info(Locale.BACKEND_HTTP_STARTING_LOG, SERVER_HOST, SERVER_PORT)
            uvicorn.run(
                full_backend_application(
                    context, init_request_record=init_request_record,
                    new=args.new, confirmed=confirmed, yes=args.yes,
                ),
                host=SERVER_HOST,
                port=SERVER_PORT,
            )
    except BaseException:
        logger.exception(Locale.BACKEND_FAILED_LOG)
        raise
    finally:
        api._release_backend_process_lock()
        logger.info(Locale.BACKEND_LOCK_RELEASED_LOG)


if __name__ == "__main__":
    main()
