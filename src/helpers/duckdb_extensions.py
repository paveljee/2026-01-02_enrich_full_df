from __future__ import annotations

import json
import platform
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, Protocol

from .config import DuckDBExtensionConfig
from .duckdb_utils import duckdb_string_literal

DEFAULT_DUCKDB_EXTENSIONS_CONFIG_PATH: Final = Path("config.repl.json")


class DuckDBConnectionLike(Protocol):
    def execute(self, query: str, parameters: object | None = None) -> Any: ...


@dataclass(frozen=True)
class DuckDBExtensionLoadResult:
    extension_name: str
    source: Literal["repo", "bin", "community"]
    location: str | None = None
    fallback_error: str | None = None

    @property
    def message(self) -> str:
        return duckdb_extension_load_message(self)


def _print_load_message(message: str) -> None:
    print(message)


DEFAULT_DUCKDB_EXTENSION_LOAD_LOG: Final[Callable[[str], None]] = _print_load_message


def duckdb_extension_platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    system_key = {
        "darwin": "osx",
        "linux": "linux",
        "windows": "windows",
    }.get(system, system)
    machine_key = {
        "aarch64": "arm64",
        "arm64": "arm64",
        "amd64": "amd64",
        "x86_64": "amd64",
    }.get(machine, machine)
    return f"{system_key}_{machine_key}"


def configured_duckdb_extension_binary_path(
    config: DuckDBExtensionConfig | None,
    *,
    platform_key: str | None = None,
) -> Path | None:
    if config is None:
        return None
    key = platform_key or duckdb_extension_platform_key()
    return config.bin.get(key)


def duckdb_extensions_from_config_path(
    config_path: Path = DEFAULT_DUCKDB_EXTENSIONS_CONFIG_PATH,
) -> dict[str, DuckDBExtensionConfig]:
    if not config_path.exists():
        return {}
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    extensions_payload = payload.get("duckdb_extensions", {})
    if not isinstance(extensions_payload, dict):
        raise ValueError("duckdb_extensions must be an object keyed by extension name.")
    return {
        str(extension_name): DuckDBExtensionConfig.model_validate(extension_config)
        for extension_name, extension_config in extensions_payload.items()
    }


def _repository_sql(repo: str) -> str:
    if repo in {"community", "core", "local_build_debug", "local_build_release"}:
        return repo
    return duckdb_string_literal(repo)


def _load_from_repo(
    conn: DuckDBConnectionLike,
    *,
    extension_name: str,
    repo: str,
) -> None:
    conn.execute(f"INSTALL {extension_name} FROM {_repository_sql(repo)};")
    conn.execute(f"LOAD {extension_name};")


def _load_from_binary(conn: DuckDBConnectionLike, extension_path: Path) -> None:
    if not extension_path.exists():
        raise FileNotFoundError(f"Configured DuckDB extension not found: {extension_path}")
    conn.execute(f"LOAD {duckdb_string_literal(str(extension_path))}")


def load_duckdb_extension(
    conn: DuckDBConnectionLike,
    extension_name: str,
    config: DuckDBExtensionConfig | None = None,
    *,
    log: Callable[[str], None] | None = DEFAULT_DUCKDB_EXTENSION_LOAD_LOG,
) -> DuckDBExtensionLoadResult:
    fallback_errors: list[str] = []
    try:
        _load_from_repo(conn, extension_name=extension_name, repo="community")
        return _emit_load_result(
            DuckDBExtensionLoadResult(
                extension_name=extension_name,
                source="community",
                location="community",
            ),
            log,
        )
    except Exception as exc:
        fallback_errors.append(f"community: {exc}")

    if config is not None and config.repo:
        try:
            _load_from_repo(conn, extension_name=extension_name, repo=config.repo)
            return _emit_load_result(
                DuckDBExtensionLoadResult(
                    extension_name=extension_name,
                    source="repo",
                    location=config.repo,
                    fallback_error="; ".join(fallback_errors),
                ),
                log,
            )
        except Exception as exc:
            fallback_errors.append(f"repo: {exc}")

    extension_path = configured_duckdb_extension_binary_path(config)
    if extension_path is not None:
        _load_from_binary(conn, extension_path)
        return _emit_load_result(
            DuckDBExtensionLoadResult(
                extension_name=extension_name,
                source="bin",
                location=str(extension_path),
                fallback_error="; ".join(fallback_errors),
            ),
            log,
        )

    raise RuntimeError(
        f"Failed to load DuckDB extension {extension_name!r}: "
        + "; ".join(fallback_errors)
    )


def load_duckdb_extension_from_config_path(
    conn: DuckDBConnectionLike,
    extension_name: str,
    config_path: Path = DEFAULT_DUCKDB_EXTENSIONS_CONFIG_PATH,
    *,
    log: Callable[[str], None] | None = DEFAULT_DUCKDB_EXTENSION_LOAD_LOG,
) -> DuckDBExtensionLoadResult:
    extensions = duckdb_extensions_from_config_path(config_path)
    return load_duckdb_extension(
        conn,
        extension_name,
        extensions.get(extension_name),
        log=log,
    )


def duckdb_extension_load_message(result: DuckDBExtensionLoadResult) -> str:
    source_label = {
        "community": "default community repository",
        "repo": "configured repository",
        "bin": "configured binary",
    }[result.source]
    location = f": {result.location}" if result.location else ""
    fallback = " after earlier load attempts failed" if result.fallback_error else ""
    return (
        f"DuckDB extension {result.extension_name} loaded from "
        f"{source_label}{location}{fallback}."
    )


def _emit_load_result(
    result: DuckDBExtensionLoadResult,
    log: Callable[[str], None] | None,
) -> DuckDBExtensionLoadResult:
    if log is not None:
        log(result.message)
    return result


__all__ = [
    "DEFAULT_DUCKDB_EXTENSION_LOAD_LOG",
    "DEFAULT_DUCKDB_EXTENSIONS_CONFIG_PATH",
    "DuckDBExtensionLoadResult",
    "configured_duckdb_extension_binary_path",
    "duckdb_extension_platform_key",
    "duckdb_extension_load_message",
    "duckdb_extensions_from_config_path",
    "load_duckdb_extension",
    "load_duckdb_extension_from_config_path",
]
