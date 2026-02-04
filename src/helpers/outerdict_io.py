from __future__ import annotations

from collections.abc import Iterable, Mapping

import duckdb

from .data_models import (
    InnerDict,
    MatchingProcedure,
    NameKey,
    OuterDict,
    RegisteredResource,
)
from .jsonlines import loads_jsonlines
from .vars import KTP_FILENAME_COL, KTP_FRAGMENT_COL


def load_outerdict_stub(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
) -> OuterDict:
    rows = conn.execute(f"SELECT name_key FROM {table_name}").fetchall()
    name_keys = [NameKey.from_json_key(row[0]) for row in rows]
    return OuterDict.from_name_keys(name_keys)


def _append_records(
    outer_dict: OuterDict,
    records: Iterable[Mapping[str, object]],
    procedure: MatchingProcedure,
    resources: Mapping[str, RegisteredResource],
    *,
    name_key_field: str,
    fragment_field: str,
) -> None:
    for record in records:
        name_key = record[name_key_field]
        payload = dict(record)
        payload.pop(name_key_field, None)
        inner = InnerDict.from_mapping(payload, procedure)
        outer_dict.add_inner_by_key(str(name_key), inner)


def append_innerdicts_from_table(
    conn: duckdb.DuckDBPyConnection,
    outer_dict: OuterDict,
    *,
    table_name: str,
    procedure: MatchingProcedure,
    resources: Mapping[str, RegisteredResource],
) -> None:
    rows = conn.execute(f"SELECT name_key, innerdicts FROM {table_name}").fetchall()
    for name_key, payload in rows:
        for record in loads_jsonlines(payload or ""):
            record["name_key"] = name_key
            if KTP_FILENAME_COL not in record:
                raise ValueError(f"Innerdict missing required column '{KTP_FILENAME_COL}'")
            if KTP_FRAGMENT_COL not in record:
                raise ValueError(f"Innerdict missing required column '{KTP_FRAGMENT_COL}'")
            _append_records(
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
    procedure: MatchingProcedure,
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
