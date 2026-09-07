from __future__ import annotations

import stat
from pathlib import Path
from typing import NoReturn

import pytest

from src.detours.detour_ai_augment.src.backend import api
from src.detours.detour_ai_augment.src.backend.ipc import (
    JSON_MEDIA_TYPE,
    SOCKET_PERMISSIONS,
    create_dashboard_query_app,
    start_dashboard_query_server,
    stop_dashboard_query_server,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.ui import (
    BackendDatabaseClient,
    Namekey,
)
from src.helpers.vars import KTP_NAMEKEY_COL


def test_dashboard_query_flask_application_is_separate_and_unauthenticated() -> None:
    observed: list[str | None] = []
    payload = api.DashboardQueryResponse(
        attempts=(),
        accepted_attempts=(),
        card_markdown=None,
    ).model_dump_json()

    def query(namekey: str | None) -> str:
        observed.append(namekey)
        return payload

    app = create_dashboard_query_app(
        query,
        namekey_parameter=KTP_NAMEKEY_COL,
        query_path=api.DASHBOARD_QUERY_PATH,
    )

    availability_response = app.test_client().options(api.DASHBOARD_QUERY_PATH)
    response = app.test_client().get(
        api.DASHBOARD_QUERY_PATH,
        query_string={KTP_NAMEKEY_COL: "researcher"},
    )

    assert availability_response.status_code == 200
    assert response.status_code == 200
    assert response.content_type == JSON_MEDIA_TYPE
    assert response.get_data(as_text=True) == payload
    assert observed == ["researcher"]
    assert app is not api.app


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
        query_path=api.DASHBOARD_QUERY_PATH,
        fatal_exit=fatal_exit,
    )
    app.testing = True

    with pytest.raises(FatalDashboardQuery):
        app.test_client().get(api.DASHBOARD_QUERY_PATH)

    assert exit_codes == [1]


def test_dashboard_client_queries_real_mode_0600_unix_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "dashboard.sock"
    observed: list[str | None] = []
    payload = api.DashboardQueryResponse(
        attempts=(),
        accepted_attempts=(),
        card_markdown="card",
    ).model_dump_json()

    def query(namekey: str | None) -> str:
        observed.append(namekey)
        return payload

    try:
        server = start_dashboard_query_server(
            socket_path,
            query,
            namekey_parameter=KTP_NAMEKEY_COL,
            query_path=api.DASHBOARD_QUERY_PATH,
        )
    except (OSError, SystemExit) as exc:
        pytest.skip(f"Unix sockets are unavailable in this execution environment: {exc}")
    try:
        assert stat.S_ISSOCK(socket_path.stat().st_mode)
        assert stat.S_IMODE(socket_path.stat().st_mode) == SOCKET_PERMISSIONS
        client = BackendDatabaseClient(socket_path=socket_path)
        assert client.available() is True
        assert observed == []
        assert client.pull(
            Namekey("researcher")
        ) == api.DashboardQueryResponse(
            attempts=(),
            accepted_attempts=(),
            card_markdown="card",
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
            query_path=api.DASHBOARD_QUERY_PATH,
        )

    assert socket_path.read_text(encoding="utf-8") == "owned by someone else"
