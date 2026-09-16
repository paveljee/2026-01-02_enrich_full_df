from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Self

import duckdb
from pydantic import Field, PrivateAttr

from src.helpers.architecture import FrozenStrictModel
from src.helpers.config import DuckDBExtensionConfig
from src.helpers.duckdb_extensions import load_duckdb_extension

from ..locale import Locale

DETOUR_ID = "ai-augment"
DETOUR_DB_SUFFIX = ".duckdb"
DETOUR_DB_FILENAME_TEMPLATE = "{stem}__detour_{detour_id}{suffix}"
READ_ONLY_PERMISSIONS = 0o400
READ_WRITE_PERMISSIONS = 0o600


class AiAugmentDetourDB(FrozenStrictModel):
    """
    Context-managed writable projection database.

    When used with `.writable()`, it sets the
    database file's  permissions for writing
    on context `__enter__` and sets them for
    reading on context `__exit__`.

    `.read_only()` also enforces read-only file permissions and
    initializes `duckdb.connect` with `read_only=True`.
    """

    path: Path
    duckdb_extensions: dict[str, DuckDBExtensionConfig] = Field(
        default_factory=dict
    )
    _conn: duckdb.DuckDBPyConnection | None = PrivateAttr(default=None)

    @classmethod
    def from_pipeline_db(
        cls,
        path: Path,
        *,
        duckdb_extensions: Mapping[str, object],
    ) -> Self:
        suffix = path.suffix or DETOUR_DB_SUFFIX
        stem = path.stem if path.suffix else path.name
        return cls.model_validate({
            "path": path.with_name(
                DETOUR_DB_FILENAME_TEMPLATE.format(
                    stem=stem,
                    detour_id=DETOUR_ID,
                    suffix=suffix,
                )
            ),
            "duckdb_extensions": duckdb_extensions,
        })

    def _connect(self, *, read_only: bool) -> duckdb.DuckDBPyConnection:
        connection = duckdb.connect(str(self.path), read_only=read_only)
        try:
            load_duckdb_extension(
                connection,
                "splink_udfs",
                self.duckdb_extensions.get("splink_udfs"),
                log=None,
            )
        except BaseException:
            connection.close()
            raise
        return connection

    @contextmanager
    def writable(self) -> Iterator[Self]:
        if self._conn is not None:
            raise RuntimeError("AiAugmentDetourDB is already open")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                self.path.chmod(READ_WRITE_PERMISSIONS)
            self._conn = self._connect(read_only=False)
            self.path.chmod(READ_WRITE_PERMISSIONS)
        except BaseException as exc:
            connection = self._conn
            self._conn = None
            if connection is not None:
                connection.close()
            if self.path.exists():
                self.path.chmod(READ_ONLY_PERMISSIONS)
            if isinstance(exc, (OSError, RuntimeError, duckdb.Error)):
                raise RuntimeError(Locale.DETOUR_DUCKDB_OPEN_FAILED) from exc
            raise

        try:
            yield self
        finally:
            connection = self._conn
            self._conn = None

            try:
                if connection is not None:
                    connection.close()
            finally:
                if self.path.exists():
                    self.path.chmod(READ_ONLY_PERMISSIONS)

    @contextmanager
    def read_only(self) -> Iterator[Self]:
        if self._conn is not None:
            raise RuntimeError("AiAugmentDetourDB is already open")
        try:
            if self.path.exists():
                self.path.chmod(READ_ONLY_PERMISSIONS)
            self._conn = self._connect(read_only=True)
        except (OSError, RuntimeError, duckdb.Error) as exc:
            self._conn = None
            raise RuntimeError(Locale.DETOUR_DUCKDB_READ_ONLY_OPEN_FAILED) from exc
        try:
            yield self
        finally:
            connection = self._conn
            self._conn = None
            if connection is not None:
                connection.close()

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            raise RuntimeError("AiAugmentDetourDB must be used inside a 'with' block")
        return self._conn
