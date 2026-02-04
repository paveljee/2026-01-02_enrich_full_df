from __future__ import annotations

import duckdb
import pandas as pd


def register_frame(conn: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame) -> None:
    conn.register(name, df)
    conn.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM {name}")
    # Avoid name collisions between the registered view and the materialized table.
    try:
        conn.unregister(name)
    except Exception:
        # Older DuckDB versions or already-unregistered names should be ignored.
        pass
