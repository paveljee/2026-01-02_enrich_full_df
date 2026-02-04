from __future__ import annotations

import re
from pathlib import Path

import duckdb


def normalize_parquet_column_name(column: str, prefix: str) -> str:
    normalized = re.sub(r"[^\w\s]", "_", str(column).lower())
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return f"{prefix}.{normalized}"


def parquet_columns(conn: duckdb.DuckDBPyConnection, path: str) -> list[str]:
    rows = conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()
    return [row[0] for row in rows]


def parquet_filename(path: str) -> str:
    return Path(path).name
