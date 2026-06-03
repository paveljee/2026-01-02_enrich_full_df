from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest

from src.helpers.config import DuckDBExtensionConfig
from src.helpers.duckdb_extensions import (
    duckdb_extension_load_message,
    duckdb_extension_platform_key,
    duckdb_extensions_from_config_path,
    load_duckdb_extension,
    load_duckdb_extension_from_config_path,
)


class _FakeConn:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query: str, parameters: object | None = None) -> Any:
        self.queries.append(query)
        if query == "INSTALL splink_udfs FROM community;":
            raise duckdb.IOException("community unavailable")
        if query.startswith("INSTALL splink_udfs FROM "):
            raise duckdb.IOException("configured repo unavailable")
        return self


def test_config_accepts_duckdb_extension_repo_and_platform_bins() -> None:
    extensions = duckdb_extensions_from_config_path()

    extension = extensions.get("splink_udfs")
    assert extension is not None
    assert extension.repo == "https://github.com/RobinL/splink_udfs"
    assert duckdb_extension_platform_key() in extension.bin


def test_load_duckdb_extension_tries_default_then_repo_then_platform_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    extension_path = tmp_path / "splink_udfs.duckdb_extension"
    extension_path.write_bytes(b"fixture")
    fake_conn = _FakeConn()
    monkeypatch.setattr(
        "src.helpers.duckdb_extensions.duckdb_extension_platform_key",
        lambda: "linux_arm64",
    )

    result = load_duckdb_extension(
        fake_conn,
        "splink_udfs",
        DuckDBExtensionConfig(
            repo="https://github.com/RobinL/splink_udfs",
            bin={"linux_arm64": extension_path},
        ),
    )

    assert result.extension_name == "splink_udfs"
    assert result.source == "bin"
    assert result.message == duckdb_extension_load_message(result)
    assert result.location == str(extension_path)
    assert result.fallback_error == (
        "community: community unavailable; repo: configured repo unavailable"
    )
    assert fake_conn.queries == [
        "INSTALL splink_udfs FROM community;",
        "INSTALL splink_udfs FROM 'https://github.com/RobinL/splink_udfs';",
        f"LOAD '{extension_path}'",
    ]
    assert capsys.readouterr().out.strip() == result.message


def test_configured_duckdb_extension_binary_loads_unaccent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extension = duckdb_extensions_from_config_path().get("splink_udfs")
    assert extension is not None
    extension_path = extension.bin.get(duckdb_extension_platform_key())
    if extension_path is None or not extension_path.exists():
        pytest.skip("Configured splink_udfs binary is not available on this platform.")

    def fail_repo(*_args: object, **_kwargs: object) -> None:
        raise duckdb.IOException("forced default failure")

    monkeypatch.setattr("src.helpers.duckdb_extensions._load_from_repo", fail_repo)

    conn = duckdb.connect(":memory:")
    try:
        result = load_duckdb_extension(
            conn,
            "splink_udfs",
            DuckDBExtensionConfig(bin={duckdb_extension_platform_key(): extension_path}),
        )
        row = conn.execute("SELECT unaccent('José García')").fetchone()
    finally:
        conn.close()

    assert result.source == "bin"
    assert result.fallback_error == "community: forced default failure"
    assert row == ("Jose Garcia",)


def test_load_duckdb_extension_from_config_path_uses_repo_or_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConn()
    monkeypatch.setattr(
        "src.helpers.duckdb_extensions.duckdb_extension_platform_key",
        lambda: "linux_arm64",
    )

    result = load_duckdb_extension_from_config_path(
        fake_conn,
        "splink_udfs",
    )

    assert result.source == "bin"
    assert result.fallback_error == (
        "community: community unavailable; repo: configured repo unavailable"
    )
    assert fake_conn.queries[0] == (
        "INSTALL splink_udfs FROM community;"
    )
    assert fake_conn.queries[1] == (
        "INSTALL splink_udfs FROM 'https://github.com/RobinL/splink_udfs';"
    )
    assert fake_conn.queries[2].startswith("LOAD '")


def test_duckdb_extension_load_callback_receives_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extension_path = tmp_path / "splink_udfs.duckdb_extension"
    extension_path.write_bytes(b"fixture")
    messages: list[str] = []
    monkeypatch.setattr(
        "src.helpers.duckdb_extensions.duckdb_extension_platform_key",
        lambda: "linux_arm64",
    )

    result = load_duckdb_extension(
        _FakeConn(),
        "splink_udfs",
        DuckDBExtensionConfig(
            repo="https://github.com/RobinL/splink_udfs",
            bin={"linux_arm64": extension_path},
        ),
        log=messages.append,
    )

    assert messages == [result.message]
    assert result.message.endswith("after earlier load attempts failed.")
