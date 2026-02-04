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
