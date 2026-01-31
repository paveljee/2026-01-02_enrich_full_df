from __future__ import annotations

import duckdb
import pandas as pd

from .._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from ..data_models import OuterDict, RegisteredResource
from ..dict_utils import build_name_key_frame
from .utils import append_records, register_frame

XLSX_ROW_FRAGMENT_COL = "ktp.xlsx_row_fragment"


class XlsxMatchProcedure:
    dataset_id_field = "ktp.source_key"


def match_population_df(
    conn: duckdb.DuckDBPyConnection,
    outer_dict: OuterDict,
    population_df: pd.DataFrame,
    resources: dict[str, RegisteredResource],
) -> None:
    name_keys = build_name_key_frame(outer_dict)
    if name_keys.empty or population_df.empty:
        return

    register_frame(conn, "ktp_population", population_df)
    register_frame(conn, "ktp_name_keys", name_keys)

    matched = conn.execute(
        f"""
        SELECT
            n.name_key,
            p.*,
            p."hcr.row_number" AS "{XLSX_ROW_FRAGMENT_COL}"
        FROM ktp_population p
        JOIN ktp_name_keys n
          ON p."{KTP_FIRST_NAME_COL}" = n."{KTP_FIRST_NAME_COL}"
         AND p."{KTP_LAST_NAME_COL}" = n."{KTP_LAST_NAME_COL}"
        """
    ).df()
    if matched.empty:
        return

    append_records(
        outer_dict,
        matched.to_dict("records"),
        XlsxMatchProcedure(),
        resources,
        name_key_field="name_key",
        fragment_field=XLSX_ROW_FRAGMENT_COL,
    )
