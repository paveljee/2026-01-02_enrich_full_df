from __future__ import annotations

import duckdb
import pandas as pd

from ..utils.duckdb import register_frame as _register_frame


def register_frame(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    df: pd.DataFrame,
) -> None:
    _register_frame(conn, table_name, df)
