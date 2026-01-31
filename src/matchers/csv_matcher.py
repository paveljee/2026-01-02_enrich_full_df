from __future__ import annotations

import duckdb
import pandas as pd

from src._vars import (
    CSV_ROW_INDEX_COL,
    HCR_FILENAME_COL,
    HCR_ROW_NUMBER_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    SOURCE_KEY_COL,
)
from src.data_models import (
    InnerDict,
    MatchingProcedure,
    NameKey,
    OuterDict,
    RegisteredResource,
    SourceKey,
)


class CsvDuckdbMatchProcedure:
    dataset_id_field = SOURCE_KEY_COL


def _build_name_key_frame(outer_dict: OuterDict) -> pd.DataFrame:
    rows = []
    for key in outer_dict.data:
        name_key = NameKey.from_json_key(key)
        rows.append(
            {
                "name_key": key,
                KTP_FIRST_NAME_COL: name_key.first_name,
                KTP_LAST_NAME_COL: name_key.last_name,
            }
        )
    return pd.DataFrame(rows)


def _validate_csv_matches(csv_df: pd.DataFrame, population_df: pd.DataFrame) -> None:
    if csv_df.empty:
        return

    required_cols = {HCR_FILENAME_COL, HCR_ROW_NUMBER_COL}
    missing = required_cols - set(csv_df.columns)
    if missing:
        raise ValueError(f"CSV data missing expected columns: {sorted(missing)}")

    conn = duckdb.connect()
    conn.register("csv_df", csv_df)
    conn.register("population_df", population_df)
    result = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM csv_df c
        LEFT JOIN population_df p
          ON c."{HCR_FILENAME_COL}" = p."{HCR_FILENAME_COL}"
         AND c."{HCR_ROW_NUMBER_COL}" = p."{HCR_ROW_NUMBER_COL}"
        WHERE p."{HCR_ROW_NUMBER_COL}" IS NULL
        """
    ).fetchone()
    mismatch_count = int(result[0]) if result else 0
    conn.close()

    if mismatch_count:
        raise ValueError(
            "CSV rows did not match population rows; "
            f"{mismatch_count} row(s) were not found in the XLSX population."
        )


def append_csv_matches(
    outer_dict: OuterDict,
    csv_df: pd.DataFrame,
    population_df: pd.DataFrame,
    resources: dict[str, RegisteredResource],
    *,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> None:
    _validate_csv_matches(csv_df, population_df)
    required_cols = {KTP_FILENAME_COL, CSV_ROW_INDEX_COL}
    missing = required_cols - set(csv_df.columns)
    if missing:
        raise ValueError(f"CSV data missing required columns: {sorted(missing)}")

    name_keys = _build_name_key_frame(outer_dict)
    if name_keys.empty or csv_df.empty:
        return

    owns_conn = conn is None
    if conn is None:
        conn = duckdb.connect()

    conn.register("csv_df", csv_df)
    conn.register("name_keys_df", name_keys)

    matched = conn.execute(
        f"""
        SELECT n.name_key, c.*
        FROM csv_df c
        JOIN name_keys_df n
          ON c."{KTP_FIRST_NAME_COL}" = n."{KTP_FIRST_NAME_COL}"
         AND c."{KTP_LAST_NAME_COL}" = n."{KTP_LAST_NAME_COL}"
        """
    ).df()

    procedure: MatchingProcedure = CsvDuckdbMatchProcedure()
    for record in matched.to_dict("records"):
        name_key = record.pop("name_key")
        filename = record.get(KTP_FILENAME_COL)
        resource = resources.get(filename)
        if resource is None:
            raise ValueError(f"Missing registered resource for filename '{filename}'")
        fragment = record.get(CSV_ROW_INDEX_COL)
        record[SOURCE_KEY_COL] = SourceKey(
            resource=resource,
            fragment=str(fragment),
        ).to_string_key()
        inner = InnerDict.from_mapping(record, procedure)
        outer_dict.add_inner_by_key(name_key, inner)

    if owns_conn:
        conn.close()
