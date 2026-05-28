from __future__ import annotations

import duckdb
import pandas as pd

from .data_models import InnerDict, OuterDict
from .jsonlines import loads_jsonlines


def duckdb_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def register_frame(conn: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame) -> None:
    conn.register(name, df)
    conn.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM {name}")
    # Avoid name collisions between the registered view and the materialized table.
    try:
        conn.unregister(name)
    except Exception:
        # Older DuckDB versions or already-unregistered names should be ignored.
        pass


def append_innerdicts_from_jsonlines_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    outer_dict: OuterDict,
    procedure,
    required_columns: set[str] | None = None,
) -> None:
    rows = conn.execute(f"SELECT name_key, innerdicts FROM {table_name}").fetchall()
    required = required_columns or set()
    for name_key, payload in rows:
        for record in loads_jsonlines(payload or ""):
            for col in required:
                if col not in record:
                    raise ValueError(f"Innerdict missing required column '{col}'")
            inner = InnerDict.from_mapping(record, procedure)
            outer_dict.add_inner_by_key(str(name_key), inner)


def append_innerdicts_from_rows_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    outer_dict: OuterDict,
    procedure,
    required_columns: set[str] | None = None,
    key_column: str = "name_key",
) -> None:
    rel = conn.execute(f"SELECT * FROM {table_name}")
    cols = [desc[0] for desc in rel.description]
    try:
        name_idx = cols.index(key_column)
    except ValueError as exc:
        raise ValueError(f"Missing {key_column} column in {table_name}") from exc
    required = required_columns or set()
    while True:
        rows = rel.fetchmany(5000)
        if not rows:
            break
        for row in rows:
            name_key = row[name_idx]
            record = {col: row[i] for i, col in enumerate(cols) if i != name_idx}
            for col in required:
                if col not in record:
                    raise ValueError(f"Innerdict missing required column '{col}'")
            inner = InnerDict.from_mapping(record, procedure)
            outer_dict.add_inner_by_key(str(name_key), inner)


__all__ = [
    "duckdb_string_literal",
    "register_frame",
    "append_innerdicts_from_jsonlines_table",
    "append_innerdicts_from_rows_table",
]
