from __future__ import annotations

import duckdb
import pandas as pd

from .._vars import HCR_FILENAME_COL, HCR_XLSX_NAME_COLS, KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from ..data_models import NameKey, OuterDict
from ..utils.name_keys import NAME_KEY_COL, build_outer_dict_from_names


def _resolve_name_columns(filename: str) -> tuple[str, str]:
    if filename not in HCR_XLSX_NAME_COLS:
        raise ValueError(f"Missing name column mapping for {filename}")
    return HCR_XLSX_NAME_COLS[filename]


def index_samples(
    conn: duckdb.DuckDBPyConnection,
    *,
    samples_table: str,
    first_name_col: str = KTP_FIRST_NAME_COL,
    last_name_col: str = KTP_LAST_NAME_COL,
) -> OuterDict:
    sample_df = conn.execute(f"SELECT * FROM {samples_table}").df()
    if sample_df.empty:
        return OuterDict()

    def derive_first_last(row: pd.Series) -> tuple[str, str]:
        first_col, last_col = _resolve_name_columns(str(row[HCR_FILENAME_COL]))
        return str(row.get(first_col, "")), str(row.get(last_col, ""))

    derived = sample_df.apply(derive_first_last, axis=1, result_type="expand")
    sample_df[first_name_col] = derived[0]
    sample_df[last_name_col] = derived[1]
    sample_df[NAME_KEY_COL] = [
        NameKey(first_name=str(first), last_name=str(last)).to_json_key()
        for first, last in zip(sample_df[first_name_col], sample_df[last_name_col])
    ]

    conn.register("samples_indexed", sample_df)
    conn.execute(f"CREATE OR REPLACE TABLE {samples_table} AS SELECT * FROM samples_indexed")

    name_keys = sample_df[[first_name_col, last_name_col]].drop_duplicates()
    return build_outer_dict_from_names(name_keys)
