from __future__ import annotations

import duckdb
import pandas as pd

from .data_models import InnerDict, OuterDict
from .jsonlines import dumps_jsonlines, loads_jsonlines
from .schema import INNERDICT_TABLE_SCHEMA
from .vars import KTP_INNERDICT_JSONLINES_COL, KTP_NAMEKEY_COL


def duckdb_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def duckdb_quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def register_frame(conn: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame) -> None:
    conn.register(name, df)
    conn.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM {name}")
    # Avoid name collisions between the registered view and the materialized table.
    try:
        conn.unregister(name)
    except Exception:
        # Older DuckDB versions or already-unregistered names should be ignored.
        pass


def materialize_innerdicts_from_rows_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    source_relation: str,
    table_name: str,
) -> tuple[int, int]:
    """Persist ordered flat rows under the common two-column JSONL contract.

    DuckDB exposes ``SUM(INTEGER)`` as ``HUGEINT``, which pandas converts to a
    float. Producers must cast domain-bounded aggregates to ``BIGINT`` before
    this boundary so integer payloads remain integers. Other pandas missing
    values are normalized to JSON ``null`` here.

    Returns ``(source_key_count, innerdict_record_count)``.
    """
    source_schema = conn.execute(
        f"DESCRIBE SELECT * FROM {source_relation}"
    ).fetchall()
    source_columns = [str(row[0]) for row in source_schema]
    if KTP_NAMEKEY_COL not in source_columns:
        raise ValueError(
            f"Innerdict source relation '{source_relation}' is missing "
            f"'{KTP_NAMEKEY_COL}'."
        )

    hugeint_columns = [
        str(row[0]) for row in source_schema if str(row[1]).upper() == "HUGEINT"
    ]
    if hugeint_columns:
        columns = ", ".join(hugeint_columns)
        raise ValueError(
            f"Innerdict source relation '{source_relation}' contains HUGEINT "
            f"column(s): {columns}. Cast domain-bounded values to BIGINT in "
            "the producing SQL before JSONL materialization."
        )

    ordered_rows = conn.execute(f"SELECT * FROM {source_relation}").df()
    if ordered_rows[KTP_NAMEKEY_COL].isna().any():
        raise ValueError(
            f"Innerdict source relation '{source_relation}' contains a NULL "
            f"'{KTP_NAMEKEY_COL}'."
        )

    inner_rows: list[dict[str, str]] = []
    for source_key, group in ordered_rows.groupby(
        KTP_NAMEKEY_COL,
        dropna=False,
        sort=False,
    ):
        payload_df = group.drop(columns=[KTP_NAMEKEY_COL]).astype(object)
        payload_df = payload_df.where(pd.notna(payload_df), None)
        inner_rows.append(
            {
                KTP_NAMEKEY_COL: str(source_key),
                KTP_INNERDICT_JSONLINES_COL: dumps_jsonlines(
                    payload_df.to_dict("records")
                ),
            }
        )

    schema_columns = [name for name, _data_type in INNERDICT_TABLE_SCHEMA]
    if not inner_rows:
        definitions = ", ".join(
            f"{duckdb_quote_identifier(name)} {data_type}"
            for name, data_type in INNERDICT_TABLE_SCHEMA
        )
        conn.execute(f"CREATE OR REPLACE TABLE {table_name} ({definitions})")
    else:
        frame_name = f"{table_name}_frame"
        inner_df = pd.DataFrame(inner_rows, columns=schema_columns)
        register_frame(conn, frame_name, inner_df)
        try:
            projection = ", ".join(
                f"CAST({duckdb_quote_identifier(name)} AS {data_type}) "
                f"AS {duckdb_quote_identifier(name)}"
                for name, data_type in INNERDICT_TABLE_SCHEMA
            )
            conn.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS "
                f"SELECT {projection} FROM {frame_name}"
            )
        finally:
            conn.execute(f"DROP TABLE IF EXISTS {frame_name}")

    return len(inner_rows), len(ordered_rows)


def append_innerdicts_from_jsonlines_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    outer_dict: OuterDict,
    procedure,
    required_columns: set[str] | None = None,
) -> None:
    rows = conn.execute(
        f"SELECT {duckdb_quote_identifier(KTP_NAMEKEY_COL)}, "
        f"{duckdb_quote_identifier(KTP_INNERDICT_JSONLINES_COL)} "
        f"FROM {table_name}"
    ).fetchall()
    required = required_columns or set()
    for name_key, payload in rows:
        for record in loads_jsonlines(payload or ""):
            for col in required:
                if col not in record:
                    raise ValueError(f"Innerdict missing required column '{col}'")
            inner = InnerDict.from_mapping(record, procedure)
            outer_dict.add_inner_by_key(str(name_key), inner)


__all__ = [
    "duckdb_string_literal",
    "register_frame",
    "materialize_innerdicts_from_rows_table",
    "append_innerdicts_from_jsonlines_table",
]
