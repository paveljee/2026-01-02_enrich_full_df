from __future__ import annotations

from typing import Iterable

import duckdb

from .._vars import KTP_FILENAME_COL, KTP_FRAGMENT_COL
from ..data_models import InnerDict, NameKey, OuterDict
from ..utils.records import append_records
from .jsonlines import loads_jsonlines


def load_outerdict_stub(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
) -> OuterDict:
    rows = conn.execute(f"SELECT name_key FROM {table_name}").fetchall()
    name_keys = [NameKey.from_json_key(row[0]) for row in rows]
    return OuterDict.from_name_keys(name_keys)


def append_innerdicts_from_table(
    conn: duckdb.DuckDBPyConnection,
    outer_dict: OuterDict,
    *,
    table_name: str,
    procedure: object,
    resources: dict[str, object],
) -> None:
    rows = conn.execute(f"SELECT name_key, innerdicts FROM {table_name}").fetchall()
    for name_key, payload in rows:
        for record in loads_jsonlines(payload or ""):
            record["name_key"] = name_key
            if KTP_FILENAME_COL not in record:
                raise ValueError(f"Innerdict missing required column '{KTP_FILENAME_COL}'")
            if KTP_FRAGMENT_COL not in record:
                raise ValueError(f"Innerdict missing required column '{KTP_FRAGMENT_COL}'")
            append_records(
                outer_dict,
                [record],
                procedure,
                resources,
                name_key_field="name_key",
                fragment_field=KTP_FRAGMENT_COL,
            )


def outerdict_record_count(outer_dict: OuterDict) -> int:
    return sum(len(items) for items in outer_dict.values())


def append_innerdicts_from_rows_table(
    conn: duckdb.DuckDBPyConnection,
    outer_dict: OuterDict,
    *,
    table_name: str,
    procedure: object,
) -> None:
    rel = conn.execute(f"SELECT * FROM {table_name}")
    cols = [desc[0] for desc in rel.description]
    name_idx = cols.index("name_key")
    outer_data = outer_dict._data
    while True:
        rows = rel.fetchmany(5000)
        if not rows:
            break
        for row in rows:
            name_key = row[name_idx]
            record = {col: row[i] for i, col in enumerate(cols) if i != name_idx}
            outer_data.setdefault(str(name_key), []).append(
                InnerDict.from_mapping(record, procedure)
            )
