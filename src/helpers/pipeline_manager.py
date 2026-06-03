from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from .config import DuckDBExtensionConfig
from .duckdb_extensions import DuckDBExtensionLoadResult, load_duckdb_extension


class PipelineManager:
    def __init__(
        self,
        state_file: Path,
        db_file: Path,
        *,
        duckdb_extensions: dict[str, DuckDBExtensionConfig] | None = None,
    ) -> None:
        self.state_file = state_file
        self.db_file = db_file
        self.duckdb_extensions = duckdb_extensions or {}
        self.duckdb_extension_load_results: list[DuckDBExtensionLoadResult] = []
        self.duckdb_extension_load_messages: list[str] = []
        self.state = self._load_state()
        self.conn: duckdb.DuckDBPyConnection | None = None

    def _load_state(self) -> dict[str, Any]:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        return {"steps_completed": [], "session_dir": None}

    def reset_state(self) -> None:
        self.state = {"steps_completed": [], "session_dir": None}
        if self.state_file.exists():
            self.state_file.unlink()

    def save_state(self, step_name: str) -> None:
        if step_name not in self.state["steps_completed"]:
            self.state["steps_completed"].append(step_name)
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state), encoding="utf-8")

    def set_session_dir(self, session_dir: str) -> None:
        self.state["session_dir"] = session_dir
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state), encoding="utf-8")

    def get_session_dir(self) -> str | None:
        value = self.state.get("session_dir")
        return value if isinstance(value, str) else None

    def is_done(self, step_name: str) -> bool:
        return step_name in self.state["steps_completed"]

    def connect_db(self) -> duckdb.DuckDBPyConnection:
        if self.conn is None:
            self.conn = duckdb.connect(str(self.db_file))
            self.conn.execute("SET memory_limit='20GB'")
            self.duckdb_extension_load_results.append(
                load_duckdb_extension(
                    self.conn,
                    "splink_udfs",
                    self.duckdb_extensions.get("splink_udfs"),
                    log=self.duckdb_extension_load_messages.append,
                )
            )
        return self.conn

    def close(self) -> None:
        if self.conn:
            self.conn.close()
