from __future__ import annotations

from collections.abc import Iterable, Mapping

import duckdb
import pandas as pd

from .._vars import KTP_FILENAME_COL
from ..data_models import InnerDict, MatchingProcedure, OuterDict, RegisteredResource, SourceKey

SOURCE_KEY_COL = "ktp.source_key"


def register_frame(conn: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame) -> None:
    conn.register(name, df)
    conn.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM {name}")


def append_records(
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
        filename = record.get(KTP_FILENAME_COL)
        resource = resources.get(str(filename))
        if resource is None:
            raise ValueError(f"Missing registered resource for filename '{filename}'")
        fragment = record.get(fragment_field)
        source_key = SourceKey(resource=resource, fragment=str(fragment)).to_string_key()
        payload = dict(record)
        payload.pop(name_key_field, None)
        payload[SOURCE_KEY_COL] = source_key
        inner = InnerDict.from_mapping(payload, procedure)
        outer_dict.add_inner_by_key(str(name_key), inner)
