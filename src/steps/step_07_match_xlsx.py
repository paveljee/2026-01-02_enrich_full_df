from __future__ import annotations

import duckdb
import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.duckdb_utils import append_innerdicts_from_jsonlines_table, register_frame
from ..helpers.jsonlines import dumps_jsonlines
from ..helpers.procedures import XlsxMatchProcedure
from ..helpers.schema import (
    OUTERDICT_NAME_VIEW,
    POPULATION_ECON_TABLE,
    POPULATION_NAMES_TABLE,
    POPULATION_TABLE,
    SAMPLES_WITH_NAMES_VIEW,
    XLSX_INNERDICT_TABLE,
    XLSX_MATCH_VIEW,
    XLSX_OUTPUT_VIEW,
)
from ..helpers.vars import (
    DRAW_LABEL,
    HCR_FILENAME_COL,
    HCR_ROW_COL,
    KTP_ECONOMIES_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    KTP_ECONOMY_MATCH_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_LAST_NAME_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_SOURCE_KEY_COL,
    KTP_XLSX_MATCH_COL,
    STEP_MATCH_XLSX,
)


def run(context: PipelineContext) -> StepResult:
    if context.outer_dict is None:
        raise ValueError("OuterDict not initialized. Run build_outerdict first.")
    if context.resources is None:
        raise ValueError("Resources not initialized. Run register_resources first.")

    conn: duckdb.DuckDBPyConnection = context.conn
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {XLSX_MATCH_VIEW} AS
        WITH name_draws AS (
            SELECT nk."{KTP_SOURCE_KEY_COL}" as "{KTP_SOURCE_KEY_COL}",
                   nk."{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
                   nk."{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
                   s."{DRAW_LABEL}" AS "{DRAW_LABEL}"
            FROM {OUTERDICT_NAME_VIEW} nk
            LEFT JOIN {SAMPLES_WITH_NAMES_VIEW} s
              ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(s."{KTP_FIRST_NAME_COL}")
             AND lower(nk."{KTP_LAST_NAME_COL}") = lower(s."{KTP_LAST_NAME_COL}")
        ),
        pop_names AS (
            SELECT
                p.*,
                n."{KTP_FIRST_NAME_COL}" AS pop_first,
                n."{KTP_LAST_NAME_COL}" AS pop_last,
                e."{KTP_ECONOMIES_COL}" AS "{KTP_ECONOMIES_COL}",
                e."{KTP_ECONOMIES_INCOME_GROUP_COL}" AS "{KTP_ECONOMIES_INCOME_GROUP_COL}",
                e."{KTP_ECONOMY_MATCH_COL}" AS "{KTP_ECONOMY_MATCH_COL}",
                e."{KTP_PRIORITY_COL}" AS "{KTP_PRIORITY_COL}",
                e."{KTP_PRIORITY_GROUP_COL}" AS "{KTP_PRIORITY_GROUP_COL}"
            FROM {POPULATION_TABLE} p
            JOIN {POPULATION_NAMES_TABLE} n
              ON p."{KTP_POPULATION_INDEX_COL}" = n."{KTP_POPULATION_INDEX_COL}"
            LEFT JOIN {POPULATION_ECON_TABLE} e
              ON p."{KTP_POPULATION_INDEX_COL}" = e."{KTP_POPULATION_INDEX_COL}"
        )
        SELECT
            nd."{KTP_SOURCE_KEY_COL}",
            nd."{KTP_FIRST_NAME_COL}",
            nd."{KTP_LAST_NAME_COL}",
            nd."{DRAW_LABEL}",
            p.*,
            p."{HCR_FILENAME_COL}" AS "{KTP_FILENAME_COL}",
            p."{HCR_ROW_COL}" AS "{KTP_FRAGMENT_COL}",
            json_object(
                lower(unaccent(nd."{KTP_FIRST_NAME_COL}" || ' ' || nd."{KTP_LAST_NAME_COL}")),
                lower(unaccent(p.pop_first || ' ' || p.pop_last))
            ) AS "{KTP_XLSX_MATCH_COL}"
        FROM pop_names p
        RIGHT JOIN name_draws nd
          ON lower(unaccent(nd."{KTP_LAST_NAME_COL}")) = lower(unaccent(p.pop_last))
         AND list_contains(
                regexp_split_to_array(lower(unaccent(p.pop_first)), '\\s+'),
                list_extract(
                    regexp_split_to_array(lower(unaccent(nd."{KTP_FIRST_NAME_COL}")), '\\s+'),
                    1
                )
             )
        """
    )

    matched_df = conn.execute(f"SELECT * FROM {XLSX_MATCH_VIEW}").df()
    matched_df = matched_df[matched_df[KTP_FILENAME_COL].notna()]

    inner_rows = []
    for name_key, group in matched_df.groupby(KTP_SOURCE_KEY_COL, dropna=False):
        rows = group.drop(columns=[KTP_SOURCE_KEY_COL]).to_dict("records")
        inner_rows.append(
            {
                "name_key": name_key,
                "innerdicts": dumps_jsonlines(rows),
            }
        )
    inner_df = pd.DataFrame(inner_rows, columns=["name_key", "innerdicts"])
    register_frame(conn, "xlsx_innerdict_frame", inner_df)
    conn.execute(
        f"CREATE OR REPLACE TABLE {XLSX_INNERDICT_TABLE} AS SELECT * FROM xlsx_innerdict_frame"
    )
    conn.execute("DROP TABLE IF EXISTS xlsx_innerdict_frame")

    append_innerdicts_from_jsonlines_table(
        conn,
        table_name=XLSX_INNERDICT_TABLE,
        outer_dict=context.outer_dict,
        procedure=XlsxMatchProcedure(),
        required_columns={KTP_FILENAME_COL, KTP_FRAGMENT_COL},
    )

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {XLSX_OUTPUT_VIEW} AS
        SELECT x.* EXCLUDE (name_key), x.name_key AS "{KTP_SOURCE_KEY_COL}",
               nk."{KTP_FIRST_NAME_COL}", nk."{KTP_LAST_NAME_COL}",
               s."{DRAW_LABEL}" AS sample_draw,
               s."{KTP_FILENAME_COL}" AS sample_filename,
               s."{KTP_FRAGMENT_COL}" AS sample_fragment,
               p.*, n.*, e.*
        FROM {XLSX_INNERDICT_TABLE} x
        LEFT JOIN {OUTERDICT_NAME_VIEW} nk
          ON x.name_key = nk."{KTP_SOURCE_KEY_COL}"
        LEFT JOIN {SAMPLES_WITH_NAMES_VIEW} s
          ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(s."{KTP_FIRST_NAME_COL}")
         AND lower(nk."{KTP_LAST_NAME_COL}") = lower(s."{KTP_LAST_NAME_COL}")
        LEFT JOIN {POPULATION_NAMES_TABLE} n
          ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(n."{KTP_FIRST_NAME_COL}")
         AND lower(nk."{KTP_LAST_NAME_COL}") = lower(n."{KTP_LAST_NAME_COL}")
        LEFT JOIN {POPULATION_TABLE} p
          ON p."{KTP_POPULATION_INDEX_COL}" = n."{KTP_POPULATION_INDEX_COL}"
        LEFT JOIN {POPULATION_ECON_TABLE} e
          ON p."{KTP_POPULATION_INDEX_COL}" = e."{KTP_POPULATION_INDEX_COL}"
        """
    )

    output_df = conn.execute(f"SELECT * FROM {XLSX_OUTPUT_VIEW}").df()

    return StepResult(
        step_id=STEP_MATCH_XLSX,
        artifacts={"xlsx_matches_df": output_df},
        messages=[f"Matched XLSX rows: {len(matched_df)}"],
        diagnostics=[f"Matched XLSX rows: {len(matched_df)}"],
    )
