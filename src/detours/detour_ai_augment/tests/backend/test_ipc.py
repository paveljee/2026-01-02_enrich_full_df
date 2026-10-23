from __future__ import annotations

import asyncio
import stat
import threading
import time
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager, contextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any, NoReturn
from unittest.mock import Mock
from uuid import UUID, uuid7

import pytest
from fastapi import FastAPI, status
from requests.structures import CaseInsensitiveDict
from starlette.responses import Response
from starlette.types import Message, Scope

from src.detours.detour_ai_augment.protected.src.architecture import ControlCentreComponent
from src.detours.detour_ai_augment.protected.src.backend import server
from src.detours.detour_ai_augment.protected.src.backend.helpers import api
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (  # noqa: E501
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.store import (  # noqa: E501
    AiAugmentBackendStore,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    ASGI_BODY_KEY,
    ASGI_HTTP_REQUEST_MESSAGE_TYPE,
    ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE,
    ASGI_HTTP_SCOPE_TYPE,
    ASGI_MORE_BODY_KEY,
    ASGI_TYPE_KEY,
    DASHBOARD_IPC_HOST,
    DASHBOARD_IPC_SCHEME,
    DASHBOARD_QUERY_PATH,
    HTTP_CONTENT_LENGTH_HEADER,
    HTTP_CONTENT_TYPE_HEADER,
    HTTP_GET_METHOD,
    HTTP_POST_METHOD,
    INIT_PATH,
    NANOSECONDS_PER_MICROSECOND,
    PULL_PATH,
    PUSH_PATH,
    SESSION_ID_HEADER,
    SOCKET_PERMISSIONS,
    TEXT_ENCODING,
    ContentType,
)
from src.detours.detour_ai_augment.protected.src.backend.server import (
    create_dashboard_query_app,
    start_dashboard_query_server,
    stop_dashboard_query_server,
)
from src.detours.detour_ai_augment.protected.src.shared import name_key_header_value
from src.detours.detour_ai_augment.protected.tests.fixtures.pytest_fixtures import (
    init_request_record,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (  # noqa: E501
    AiAugmentBackendContext,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_request import (
    CodexSessionRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.response_record_promise import (
    BackendStoreAcknowledgment,
    ResponseRecordPromise,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    run_outcome_event as run_outcome_models,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.dashboard_query_snapshot import (  # noqa: E501
    DashboardQuerySnapshot,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.query_event import (  # noqa: E501
    QueryRequestRecord,
    QueryResponseRecord,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.run_outcome_event import (  # noqa: E501
    RunOutcomeRequestRecord,
    RunOutcomeResponseRecord,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.ui import (
    _BackendDatabaseClient,
)
from src.detours.detour_ai_augment.tests.backend import test_api as fixtures
from src.helpers.data_models import NameKey
from src.helpers.vars import KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1

backend_test_paths = fixtures.backend_test_paths
api_runtime = fixtures.api_runtime
api_store = fixtures.api_store

TEST_NAMEKEY = '{"ktp.first_name": "A.", "ktp.last_name": "Sheikh"}'


def empty_query_response(
    request_record: ControlCentreComponent.BackendPort.QueryRequestRecordProperty,
) -> ResponseRecordPromise[QueryResponseRecord]:
    body = DashboardQuerySnapshot(ai_augment_singular_outerdicts=()).model_dump_json()
    ready = time.time_ns() // NANOSECONDS_PER_MICROSECOND
    assert request_record.received_at_unix_usec is not None
    response_record = QueryResponseRecord(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        method=request_record.method,
        scheme=request_record.scheme,
        host=request_record.host,
        port=request_record.port,
        path=request_record.path,
        query=request_record.query,
        request_headers=request_record.request_headers,
        request_body=request_record.request_body,
        response_code=HTTPStatus.OK,
        response_headers={
            HTTP_CONTENT_TYPE_HEADER: ContentType.JSON,
            HTTP_CONTENT_LENGTH_HEADER: str(len(body.encode(TEXT_ENCODING))),
        },
        response_body=body,
        received_at_unix_usec=None,
        ready_to_respond_at_unix_usec=ready,
        duration_usec=ready - request_record.received_at_unix_usec,
        ai_augment_singular_outerdicts=(),
    )
    return ResponseRecordPromise[QueryResponseRecord]._resolved(
        BackendStoreAcknowledgment.NAK, (response_record, None),
    )


def test_fastapi_module_does_not_own_flask_ipc_routes() -> None:
    assert set(server.app.openapi()["paths"]) == {PULL_PATH, PUSH_PATH}


def test_full_backend_composition_stops_ipc_before_domain_shutdown(
    monkeypatch: pytest.MonkeyPatch, threaded_loop: asyncio.Runner,
) -> None:
    events: list[object] = []
    ipc_server = object()
    runtime = Mock(spec=AiAugmentBackendContext)

    @asynccontextmanager
    async def domain_lifespan() -> AsyncIterator[None]:
        events.append("domain-start")
        try:
            yield
        finally:
            events.append("domain-stop")

    def start_ipc(
        _store: object,
        *, request_scope: server.IpcRequestScope,
    ) -> object:
        events.append("ipc-start")
        return ipc_server

    @contextmanager
    def store_lifecycle(*_args: object, **_kwargs: object) -> Generator[None, None, None]:
        events.append("store-start")
        try:
            yield
        finally:
            events.append("store-stop")

    monkeypatch.setattr(server, "backend_store_lifecycle", store_lifecycle)
    monkeypatch.setattr(api, "lifespan", domain_lifespan)
    monkeypatch.setattr(
        server,
        "start_full_dashboard_query_server",
        start_ipc,
    )
    monkeypatch.setattr(
        server,
        "stop_dashboard_query_server",
        lambda handle: events.append(("ipc-stop", handle)),
    )

    async def exercise() -> None:
        async with server.lifespan(
            server.app, runtime,
            init_request_record=init_request_record(NameKey.from_json_key(TEST_NAMEKEY)),
            new=True, confirmed=True,
        ):
            events.append("running")

    threaded_loop.run(asyncio.wait_for(exercise(), timeout=10))

    assert events == [
        "store-start",
        "domain-start",
        "ipc-start",
        "running",
        ("ipc-stop", ipc_server),
        "domain-stop",
        "store-stop",
    ]


def test_dashboard_query_flask_application_is_separate_and_unauthenticated() -> None:
    observed: list[ControlCentreComponent.BackendPort.QueryRequestRecordProperty] = []
    query_response = DashboardQuerySnapshot(ai_augment_singular_outerdicts=())
    payload = query_response.model_dump_json()

    def query(
        request_record: ControlCentreComponent.BackendPort.QueryRequestRecordProperty,
    ) -> ResponseRecordPromise[QueryResponseRecord]:
        observed.append(request_record)
        return empty_query_response(request_record)

    app = create_dashboard_query_app(
        query,
        query_path=DASHBOARD_QUERY_PATH,
    )

    availability_response = app.test_client().options(DASHBOARD_QUERY_PATH)
    response = app.test_client().get(DASHBOARD_QUERY_PATH)

    assert availability_response.status_code == 200
    assert response.status_code == 200
    assert response.content_type == ContentType.JSON
    assert response.get_data(as_text=True) == payload
    assert [(item.method, item.path) for item in observed] == [
        (HTTP_GET_METHOD, DASHBOARD_QUERY_PATH)
    ]
    assert id(app) != id(server.app)


@pytest.mark.parametrize("parameters, body", [
    ({"ktp.namekey": TEST_NAMEKEY}, b""),
    ({"namekey": TEST_NAMEKEY}, b""),
    ({"unknown": "value"}, b""),
    ({}, b"{}"),
])
def test_query_rejects_filters_and_bodies_without_dispatch_or_fatal_exit(
    parameters: dict[str, str], body: bytes,
) -> None:
    handler = Mock(side_effect=empty_query_response)
    fatal_exit = Mock()
    app = create_dashboard_query_app(
        handler, query_path=DASHBOARD_QUERY_PATH, fatal_exit=fatal_exit,
    )
    client = app.test_client()

    response = client.get(DASHBOARD_QUERY_PATH, query_string=parameters, data=body)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.get_data(as_text=True) == Locale.QUERY_REQUEST_INVALID
    handler.assert_not_called()
    fatal_exit.assert_not_called()
    assert client.options(DASHBOARD_QUERY_PATH).status_code == status.HTTP_200_OK
    handler.assert_not_called()
    assert client.get(DASHBOARD_QUERY_PATH).status_code == status.HTTP_200_OK
    handler.assert_called_once()
    assert handler.call_args.args[0].path == DASHBOARD_QUERY_PATH


def test_query_request_is_wholesale_only() -> None:
    request = QueryRequestRecord(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        method=HTTP_GET_METHOD, scheme=DASHBOARD_IPC_SCHEME,
        host=DASHBOARD_IPC_HOST,
        port=None, path=DASHBOARD_QUERY_PATH, query="", request_headers={}, request_body=None,
        response_code=None, response_headers=None, response_body=None,
        received_at_unix_usec=1, ready_to_respond_at_unix_usec=None,
        duration_usec=0,
    )
    assert (request.method, request.path, request.query) == (
        HTTP_GET_METHOD, DASHBOARD_QUERY_PATH, "",
    )
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        QueryRequestRecord.model_validate({**request.model_dump(), "namekey": None})


def test_dashboard_query_failure_exits_loudly() -> None:
    exit_codes: list[int] = []

    class FatalDashboardQuery(RuntimeError):
        pass

    def failed_query(
        _request_record: ControlCentreComponent.BackendPort.QueryRequestRecordProperty,
    ) -> ResponseRecordPromise[QueryResponseRecord]:
        raise RuntimeError("projection failed")

    def fatal_exit(code: int) -> NoReturn:
        exit_codes.append(code)
        raise FatalDashboardQuery

    app = create_dashboard_query_app(
        failed_query,
        query_path=DASHBOARD_QUERY_PATH,
        fatal_exit=fatal_exit,
    )
    app.testing = True

    with pytest.raises(FatalDashboardQuery):
        app.test_client().get(DASHBOARD_QUERY_PATH)

    assert exit_codes == [1]


def test_full_backend_ipc_forwards_run_outcome_http_exchange_exactly(
    api_runtime: AiAugmentBackendContext,
    api_store: AiAugmentBackendStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    namekey = NameKey.from_json_key(TEST_NAMEKEY)
    session_id = uuid7()
    session = CodexSessionRecord(
        session_id=session_id, codex_rollout_record=None, appendwatch_report_record=None,
    )
    monkeypatch.setattr(api, "BACKEND_SESSION_ID", session_id)

    def capture_snapshot(
        _store: AiAugmentBackendStore, captured_session_id: UUID | None,
    ) -> tuple[CodexSessionRecord, None, tuple[()]]:
        assert captured_session_id == session_id
        return session, None, ()

    monkeypatch.setattr(
        AiAugmentBackendStore, "capture_run_outcome_snapshot", capture_snapshot,
    )
    app = create_dashboard_query_app(
        api_store.query_response_record,
        query_path=DASHBOARD_QUERY_PATH,
        run_outcome_store=api_store,
        run_outcome_paths=run_outcome_models.RUN_OUTCOME_PATHS,
        fatal_exit=lambda code: pytest.fail(f"IPC fatal exit: {code}"),
    )
    with api_store._writable(api_runtime):
        response = app.test_client().post(
            run_outcome_models.FAILED_PATH,
            base_url=f"{DASHBOARD_IPC_SCHEME}://{DASHBOARD_IPC_HOST}",
            headers={
                run_outcome_models.NAME_KEY_HEADER: name_key_header_value(namekey),
                SESSION_ID_HEADER: str(session_id),
            },
        )
        records = [
            item for item, _ in AiAugmentBackendStore._authoritative_log_records(
                Path(api_store._replay_log).read_bytes()
            )
        ]
        assert len(records) == 2
        assert records[0].path == INIT_PATH
        persisted = RunOutcomeResponseRecord.from_http_request_log_record(records[-1])
        assert api_store._http_record(persisted.record_id) == records[-1]

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.content_type == ContentType.JSON
    assert persisted.response_body is not None
    assert response.data == persisted.response_body.encode(TEXT_ENCODING)
    assert persisted._codex_session_record() == session
    assert persisted._body().run_outcome_record_id == persisted.record_id
    request_record = persisted.run_outcome_request_record
    assert isinstance(request_record, RunOutcomeRequestRecord)
    assert request_record.record_id != persisted.record_id
    assert request_record.method == HTTP_POST_METHOD
    assert (
        request_record.scheme, request_record.host, request_record.path
    ) == (DASHBOARD_IPC_SCHEME, DASHBOARD_IPC_HOST, "/failed")
    request_headers = CaseInsensitiveDict(request_record.request_headers)
    assert request_headers[run_outcome_models.NAME_KEY_HEADER] == name_key_header_value(namekey)
    assert request_headers[SESSION_ID_HEADER] == str(session_id)
    assert request_record.request_body is None


def test_ipc_only_flask_application_has_no_run_outcome_routes() -> None:
    app = create_dashboard_query_app(
        empty_query_response,
        query_path=DASHBOARD_QUERY_PATH,
    )

    assert (
        app.test_client().post(run_outcome_models.COMPLETED_PATH).status_code
        == 404
    )


def test_dashboard_client_queries_real_mode_0600_unix_socket(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    socket_path = tmp_path / "dashboard.sock"
    observed: list[ControlCentreComponent.BackendPort.QueryRequestRecordProperty] = []
    query_response = DashboardQuerySnapshot(ai_augment_singular_outerdicts=())

    def query(
        request_record: ControlCentreComponent.BackendPort.QueryRequestRecordProperty,
    ) -> ResponseRecordPromise[QueryResponseRecord]:
        observed.append(request_record)
        return empty_query_response(request_record)

    try:
        server = start_dashboard_query_server(
            socket_path,
            query,
            query_path=DASHBOARD_QUERY_PATH,
        )
    except (OSError, SystemExit) as exc:
        pytest.skip(f"Unix sockets are unavailable in this execution environment: {exc}")
    try:
        assert stat.S_ISSOCK(socket_path.stat().st_mode)
        assert stat.S_IMODE(socket_path.stat().st_mode) == SOCKET_PERMISSIONS
        assert capsys.readouterr().out == (f"Dashboard IPC running on unix://{socket_path}\n")
        client = _BackendDatabaseClient(
            socket_path=socket_path,
            pipeline_config=Mock(spec=AiAugmentDetourConfig),
        )
        assert client.available() is True
        assert observed == []
        assert client.send_query_request() == query_response
        assert [(item.method, item.path) for item in observed] == [
        (HTTP_GET_METHOD, DASHBOARD_QUERY_PATH)
    ]
    finally:
        stop_dashboard_query_server(server)

    assert not socket_path.exists()


def test_dashboard_ipc_refuses_to_replace_non_socket_path(tmp_path: Path) -> None:
    socket_path = tmp_path / "dashboard.sock"
    socket_path.write_text("owned by someone else", encoding=TEXT_ENCODING)
    with pytest.raises(RuntimeError, match="not a Unix socket"):
        start_dashboard_query_server(
            socket_path,
            empty_query_response,
            query_path=DASHBOARD_QUERY_PATH,
        )

    assert socket_path.read_text(encoding=TEXT_ENCODING) == "owned by someone else"


def test_http_response_and_background_completion_precede_ipc_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        gate = server._BackendRequestGate()
        app = FastAPI()
        app.state.request_gate = gate
        response_started = asyncio.Event()
        release_response = asyncio.Event()
        release_background = asyncio.Event()
        background_started = asyncio.Event()
        ipc_admitted = asyncio.Event()
        release_ipc = asyncio.Event()
        next_http_admitted = asyncio.Event()
        messages: list[Message] = []

        async def background() -> None:
            background_started.set()
            await release_background.wait()

        task = asyncio.create_task(background())
        monkeypatch.setattr(api, "AUTHORITATIVE_BACKGROUND_TASKS", {task})

        async def receive() -> Message:
            return {
                ASGI_TYPE_KEY: ASGI_HTTP_REQUEST_MESSAGE_TYPE,
                ASGI_BODY_KEY: b"", ASGI_MORE_BODY_KEY: False,
            }

        async def send(message: Message) -> None:
            messages.append(message)
            if message[ASGI_TYPE_KEY] == ASGI_HTTP_RESPONSE_BODY_MESSAGE_TYPE:
                response_started.set()
                await release_response.wait()

        # Ordinary HTTP503 remains possible while post202 work is outstanding.
        middleware = server._BackendRequestMiddleware(Response(status_code=503))
        scope: Scope = {ASGI_TYPE_KEY: ASGI_HTTP_SCOPE_TYPE, "app": app}
        first_http = asyncio.create_task(middleware(scope, receive, send))
        await response_started.wait()
        await background_started.wait()
        assert messages[0]["status"] == 503

        async def ipc_request() -> None:
            async with gate.ipc():
                ipc_admitted.set()
                await release_ipc.wait()

        ipc_task = asyncio.create_task(ipc_request())
        await asyncio.sleep(0)

        async def next_http() -> None:
            async with gate.http():
                next_http_admitted.set()

        next_task = asyncio.create_task(next_http())
        await asyncio.sleep(0)
        assert not ipc_admitted.is_set() and not next_http_admitted.is_set()
        release_response.set()
        await first_http
        assert not ipc_admitted.is_set()
        release_background.set()
        await ipc_admitted.wait()
        assert not next_http_admitted.is_set()
        release_ipc.set()
        await asyncio.gather(ipc_task, next_task, task)
        assert next_http_admitted.is_set()

    asyncio.run(asyncio.wait_for(exercise(), timeout=5))


@pytest.mark.parametrize("failure", ("http", "ipc", "background"))
def test_request_gate_releases_admission_after_failure(
    monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    async def exercise() -> None:
        gate = server._BackendRequestGate()
        monkeypatch.setattr(api, "AUTHORITATIVE_BACKGROUND_TASKS", set())
        with pytest.raises(RuntimeError, match="injected"):
            if failure == "http":
                async with gate.http():
                    raise RuntimeError("injected")
            elif failure == "ipc":
                async with gate.ipc():
                    raise RuntimeError("injected")
            else:
                async def failed_work() -> None:
                    raise RuntimeError("injected")
                task = asyncio.create_task(failed_work())
                api.AUTHORITATIVE_BACKGROUND_TASKS.add(task)
                async with gate.ipc():
                    pytest.fail("Failed work must prevent IPC dispatch")
        api.AUTHORITATIVE_BACKGROUND_TASKS.clear()
        async with gate.http():
            pass
        async with gate.ipc():
            pass

    asyncio.run(asyncio.wait_for(exercise(), timeout=5))


@pytest.mark.parametrize(("method", "path", "code"), (
    ("OPTIONS", DASHBOARD_QUERY_PATH, 200), (HTTP_GET_METHOD, DASHBOARD_QUERY_PATH, 200),
    (HTTP_GET_METHOD, "/query?namekey=invalid", 400), (HTTP_GET_METHOD, "/missing", 404),
))
def test_ipc_scope_covers_complete_wsgi_exchange(method: str, path: str, code: int) -> None:
    events: list[str] = []

    @contextmanager
    def request_scope() -> Generator[None, None, None]:
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    def query(
        request_record: ControlCentreComponent.BackendPort.QueryRequestRecordProperty,
    ) -> ResponseRecordPromise[QueryResponseRecord]:
        assert events == ["enter"]
        return empty_query_response(request_record)

    app = server.create_dashboard_query_app(
        query, query_path=DASHBOARD_QUERY_PATH, request_scope=request_scope,
    )
    response = app.test_client().open(path, method=method, buffered=True)
    assert response.status_code == code
    assert events == ["enter", "exit"]


def test_server_shutdown_keeps_loop_available_for_inflight_ipc(
    monkeypatch: pytest.MonkeyPatch, threaded_loop: asyncio.Runner,
) -> None:
    runtime = Mock(spec=AiAugmentBackendContext)
    thread_errors: list[BaseException] = []
    received_scopes: list[server.IpcRequestScope] = []
    worker: threading.Thread | None = None
    worker_started = threading.Event()
    response_codes: list[int] = []

    @contextmanager
    def store_lifecycle(*_args: Any, **_kwargs: Any) -> Generator[None, None, None]:
        yield

    @asynccontextmanager
    async def domain_lifespan() -> AsyncIterator[None]:
        yield

    def start_ipc(
        _store: object, *, request_scope: server.IpcRequestScope,
    ) -> object:
        received_scopes.append(request_scope)
        return object()

    def stop_ipc(_handle: object) -> None:
        assert worker is not None
        worker.join(timeout=5)
        assert not worker.is_alive(), "IPC needs the event loop during shutdown"

    monkeypatch.setattr(server, "backend_store_lifecycle", store_lifecycle)
    monkeypatch.setattr(api, "lifespan", domain_lifespan)
    monkeypatch.setattr(server, "start_full_dashboard_query_server", start_ipc)
    monkeypatch.setattr(server, "stop_dashboard_query_server", stop_ipc)
    monkeypatch.setattr(api, "AUTHORITATIVE_BACKGROUND_TASKS", set())

    async def exercise() -> None:
        nonlocal worker
        app = FastAPI()
        async with server.lifespan(
            app, runtime,
            init_request_record=init_request_record(NameKey.from_json_key(TEST_NAMEKEY)),
            new=False, confirmed=True,
        ):
            flask_app = server.create_dashboard_query_app(
                empty_query_response,
                query_path=DASHBOARD_QUERY_PATH, request_scope=received_scopes[0],
            )

            def request() -> None:
                try:
                    worker_started.set()
                    response = flask_app.test_client().options(DASHBOARD_QUERY_PATH, buffered=True)
                    response_codes.append(response.status_code)
                except BaseException as exc:
                    thread_errors.append(exc)
            async with app.state.request_gate.http():
                worker = threading.Thread(target=request)
                worker.start()
                while not worker_started.is_set():
                    await asyncio.sleep(0)
                # Let the real thread enter the bridge before ending HTTP/shutdown.
                while not app.state.request_gate._ipc_pending:
                    await asyncio.sleep(0)
                assert not response_codes
        assert response_codes == [200]
        assert not thread_errors

    threaded_loop.run(asyncio.wait_for(exercise(), timeout=10))


def test_full_backend_factory_registers_admission_once(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    monkeypatch.setattr(server, "app", app)
    runtime = Mock(spec=AiAugmentBackendContext)
    for _ in range(2):
        assert server.full_backend_application(
            runtime,
            init_request_record=init_request_record(NameKey.from_json_key(TEST_NAMEKEY)),
            new=False, confirmed=True,
        ) is app
    assert len(app.user_middleware) == 1
    for entry, expected in zip(app.user_middleware, (
        server._BackendRequestMiddleware,
    ), strict=True):
        assert isinstance(entry.cls, type)
        assert issubclass(entry.cls, expected)
    assert not hasattr(app.state, "context")
