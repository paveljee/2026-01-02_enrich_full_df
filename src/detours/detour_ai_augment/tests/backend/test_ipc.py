from __future__ import annotations

import asyncio
import stat
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import NoReturn

import pytest
from fastapi import status

from src.detours.detour_ai_augment.src.backend import api, ipc, server
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_config import (
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_context import (
    QueryResponse,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.server_event import (
    CodexSessionRecord,
    RunOutcomeResponse,
    RunOutcomeResponseBody,
)
from src.detours.detour_ai_augment.src.backend.helpers.vars import TEXT_ENCODING
from src.detours.detour_ai_augment.src.backend.ipc import (
    DASHBOARD_IPC_HOST,
    DASHBOARD_IPC_SCHEME,
    DASHBOARD_QUERY_PATH,
    JSON_MEDIA_TYPE,
    SOCKET_PERMISSIONS,
    create_dashboard_query_app,
    start_dashboard_query_server,
    stop_dashboard_query_server,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models import (
    run_outcome as run_outcome_models,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.ui import (
    Namekey,
    _BackendDatabaseClient,
)
from src.helpers.data_models import NameKey
from src.helpers.vars import KTP_NAMEKEY_COL

TEST_NAMEKEY = '{"ktp.first_name": "A.", "ktp.last_name": "Sheikh"}'


def test_fastapi_module_does_not_own_flask_ipc_routes() -> None:
    for name in (
        "DASHBOARD_QUERY_PATH",
        "COMPLETED_PATH",
        "FAILED_PATH",
        "CANCELLED_PATH",
        "RUN_OUTCOME_PATHS",
    ):
        assert not hasattr(api, name)


def test_full_backend_composition_stops_ipc_before_domain_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    ipc_server = object()

    @asynccontextmanager
    async def domain_lifespan(_app: object) -> AsyncIterator[None]:
        events.append("domain-start")
        try:
            yield
        finally:
            events.append("domain-stop")

    def start_ipc() -> object:
        events.append("ipc-start")
        return ipc_server

    monkeypatch.setattr(api, "lifespan", domain_lifespan)
    monkeypatch.setattr(
        ipc,
        "start_full_dashboard_query_server",
        start_ipc,
    )
    monkeypatch.setattr(
        ipc,
        "stop_dashboard_query_server",
        lambda handle: events.append(("ipc-stop", handle)),
    )

    async def exercise() -> None:
        async with server.lifespan(api.app):
            events.append("running")

    asyncio.run(exercise())

    assert events == [
        "domain-start",
        "ipc-start",
        "running",
        ("ipc-stop", ipc_server),
        "domain-stop",
    ]


def test_dashboard_query_flask_application_is_separate_and_unauthenticated() -> None:
    observed: list[str | None] = []
    payload = QueryResponse(
        attempts=(),
        ai_augment_outerdicts=(),
    ).model_dump_json()

    def query(namekey: str | None) -> str:
        observed.append(namekey)
        return payload

    app = create_dashboard_query_app(
        query,
        namekey_parameter=KTP_NAMEKEY_COL,
        query_path=DASHBOARD_QUERY_PATH,
    )

    availability_response = app.test_client().options(DASHBOARD_QUERY_PATH)
    response = app.test_client().get(
        DASHBOARD_QUERY_PATH,
        query_string={KTP_NAMEKEY_COL: "researcher"},
    )

    assert availability_response.status_code == 200
    assert response.status_code == 200
    assert response.content_type == JSON_MEDIA_TYPE
    assert response.get_data(as_text=True) == payload
    assert observed == ["researcher"]
    assert id(app) != id(api.app)


def test_dashboard_query_failure_exits_loudly() -> None:
    exit_codes: list[int] = []

    class FatalDashboardQuery(RuntimeError):
        pass

    def failed_query(_namekey: str | None) -> str:
        raise RuntimeError("projection failed")

    def fatal_exit(code: int) -> NoReturn:
        exit_codes.append(code)
        raise FatalDashboardQuery

    app = create_dashboard_query_app(
        failed_query,
        namekey_parameter=KTP_NAMEKEY_COL,
        query_path=DASHBOARD_QUERY_PATH,
        fatal_exit=fatal_exit,
    )
    app.testing = True

    with pytest.raises(FatalDashboardQuery):
        app.test_client().get(DASHBOARD_QUERY_PATH)

    assert exit_codes == [1]


def test_full_backend_ipc_forwards_run_outcome_http_exchange_exactly() -> None:
    observed: list[run_outcome_models.RunOutcomeRequest] = []
    snapshot = RunOutcomeResponseBody(
        pull_record_id=None,
        push_record_id=None,
        codex_session_record=CodexSessionRecord(
            session_id=None,
            codex_rollout_record=None,
            appendwatch_report_record=None,
        ),
    )
    response_body = snapshot.model_dump_json().encode(TEXT_ENCODING)

    def run_outcome(
        request: run_outcome_models.RunOutcomeRequest,
    ) -> RunOutcomeResponse:
        observed.append(request)
        received_at_unix_usec = request.http_request_log_record.received_at_unix_usec
        assert received_at_unix_usec is not None
        return RunOutcomeResponse.from_run_outcome_request(
            request,
            response_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            response_headers=None,
            response_body=snapshot,
            ready_to_respond_at_unix_usec=received_at_unix_usec + 1,
        )

    app = create_dashboard_query_app(
        lambda _namekey: "{}",
        namekey_parameter=KTP_NAMEKEY_COL,
        query_path=DASHBOARD_QUERY_PATH,
        run_outcome_handler=run_outcome,
        run_outcome_paths=run_outcome_models.RUN_OUTCOME_PATHS,
    )
    response = app.test_client().post(
        run_outcome_models.FAILED_PATH,
        base_url=f"{DASHBOARD_IPC_SCHEME}://{DASHBOARD_IPC_HOST}",
        headers={
            run_outcome_models.NAME_KEY_HEADER: api.name_key_header(TEST_NAMEKEY)
        },
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.content_type == JSON_MEDIA_TYPE
    assert response.data == response_body
    assert len(observed) == 1
    request = observed[0]
    assert request.run_outcome is run_outcome_models.RunOutcome.FAILED
    assert request.namekey == NameKey.from_json_key(TEST_NAMEKEY)
    request_record = request.http_request_log_record
    assert request_record.received_at_unix_usec is not None
    assert request_record.received_at_unix_usec > 0
    assert request_record.method == api.HTTP_POST_METHOD
    assert request_record.scheme == DASHBOARD_IPC_SCHEME
    assert request_record.host == DASHBOARD_IPC_HOST
    assert request_record.port is None
    assert request_record.path == run_outcome_models.FAILED_PATH
    assert request_record.query == ""
    assert request_record.request_headers[
        run_outcome_models.NAME_KEY_HEADER
    ] == api.name_key_header(TEST_NAMEKEY)
    assert request_record.request_body is None


def test_ipc_only_flask_application_has_no_run_outcome_routes() -> None:
    app = create_dashboard_query_app(
        lambda _namekey: "{}",
        namekey_parameter=KTP_NAMEKEY_COL,
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
    observed: list[str | None] = []
    payload = QueryResponse(
        attempts=(),
        ai_augment_outerdicts=(),
    ).model_dump_json()

    def query(namekey: str | None) -> str:
        observed.append(namekey)
        return payload

    try:
        server = start_dashboard_query_server(
            socket_path,
            query,
            namekey_parameter=KTP_NAMEKEY_COL,
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
            pipeline_config=AiAugmentDetourConfig.model_construct(),
        )
        assert client.available() is True
        assert observed == []
        assert client.pull(Namekey("researcher")) == QueryResponse(
            attempts=(),
            ai_augment_outerdicts=(),
        )
        assert observed == ["researcher"]
    finally:
        stop_dashboard_query_server(server)

    assert not socket_path.exists()


def test_dashboard_ipc_refuses_to_replace_non_socket_path(tmp_path: Path) -> None:
    socket_path = tmp_path / "dashboard.sock"
    socket_path.write_text("owned by someone else", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not a Unix socket"):
        start_dashboard_query_server(
            socket_path,
            lambda _namekey: "{}",
            namekey_parameter=KTP_NAMEKEY_COL,
            query_path=DASHBOARD_QUERY_PATH,
        )

    assert socket_path.read_text(encoding="utf-8") == "owned by someone else"
