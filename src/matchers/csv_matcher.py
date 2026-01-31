from __future__ import annotations

import duckdb
import pandas as pd

from .._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from ..data_models import OuterDict, RegisteredResource
from ..dict_utils import build_name_key_frame
from .utils import append_records, register_frame

CSV_ROW_FRAGMENT_COL = "ktp.csv_row_index"


class CsvMatchProcedure:
    dataset_id_field = "ktp.source_key"


def match_csv_df(
    conn: duckdb.DuckDBPyConnection,
    outer_dict: OuterDict,
    csv_df: pd.DataFrame,
    population_df: pd.DataFrame,
    resources: dict[str, RegisteredResource],
) -> None:
    name_keys = build_name_key_frame(outer_dict)
    if name_keys.empty or csv_df.empty:
        return

    register_frame(conn, "ktp_csv", csv_df)
    register_frame(conn, "ktp_population", population_df)
    register_frame(conn, "ktp_name_keys", name_keys)

    matched = conn.execute(
        f"""
        SELECT
            n.name_key,
            c.*
        FROM ktp_csv c
        JOIN ktp_name_keys n
          ON c."{KTP_FIRST_NAME_COL}" = n."{KTP_FIRST_NAME_COL}"
         AND c."{KTP_LAST_NAME_COL}" = n."{KTP_LAST_NAME_COL}"
        """
    ).df()
    if matched.empty:
        return

    shared_columns = [
        col
        for col in csv_df.columns
        if col in population_df.columns
    ]
    if shared_columns:
        cols_sql = ", ".join(f'"{col}"' for col in shared_columns)
        result = conn.execute(
            f"""
            SELECT COUNT(*) AS missing_count
            FROM (
                SELECT {cols_sql} FROM ktp_csv
                EXCEPT
                SELECT {cols_sql} FROM ktp_population
            ) missing
            """
        ).fetchone()
        unmatched = result[0] if result else 0
        if unmatched:
            raise ValueError(
                "CSV rows do not all match population XLSX data. "
                f"Missing rows count: {unmatched}"
            )

    append_records(
        outer_dict,
        matched.to_dict("records"),
        CsvMatchProcedure(),
        resources,
        name_key_field="name_key",
        fragment_field=CSV_ROW_FRAGMENT_COL,
    )
