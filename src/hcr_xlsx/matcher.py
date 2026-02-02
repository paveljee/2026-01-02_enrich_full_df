from __future__ import annotations

import duckdb

from .._vars import (
    HCR_FILENAME_COL,
    HCR_XLSX_NAME_COLS,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
)
from ..data_models import OuterDict, RegisteredResource
from ..utils.name_keys import build_name_key_frame
from ..utils.records import append_records

XLSX_ROW_FRAGMENT_COL = "ktp.xlsx_row_fragment"


class XlsxMatchProcedure:
    dataset_id_field = "ktp.source_key"


def _build_name_expr(column_index: int, table_alias: str) -> str:
    cases = []
    for filename, cols in HCR_XLSX_NAME_COLS.items():
        col = cols[column_index]
        cases.append(
            f"WHEN {table_alias}.\"{HCR_FILENAME_COL}\" = '{filename}' "
            f"THEN {table_alias}.\"{col}\""
        )
    if not cases:
        raise ValueError("HCR_XLSX_NAME_COLS is empty; cannot build name expressions.")
    return "CASE " + " ".join(cases) + " END"


def match_population(
    conn: duckdb.DuckDBPyConnection,
    outer_dict: OuterDict,
    *,
    population_table: str,
    resources: dict[str, RegisteredResource],
) -> None:
    name_keys = build_name_key_frame(outer_dict)
    if name_keys.empty:
        return

    conn.register("name_keys", name_keys)
    conn.execute("CREATE OR REPLACE TABLE name_keys AS SELECT * FROM name_keys")

    population_first = _build_name_expr(0, "p")
    population_last = _build_name_expr(1, "p")

    matched = conn.execute(
        f"""
        SELECT
            n.name_key,
            p.*,
            p."hcr.row_number" AS "{XLSX_ROW_FRAGMENT_COL}",
            p."{HCR_FILENAME_COL}" AS "{KTP_FILENAME_COL}"
        FROM {population_table} p
        JOIN name_keys n
          ON lower({population_last}) = lower(n."{KTP_LAST_NAME_COL}")
         AND POSITION(
                lower(split_part(n."{KTP_FIRST_NAME_COL}", ' ', 1))
                IN lower({population_first})
             ) > 0
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
