from __future__ import annotations

import duckdb
import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.duckdb_utils import (
    append_innerdicts_from_jsonlines_table,
    register_frame,
)
from ..helpers.jsonlines import dumps_jsonlines
from ..helpers.procedures import XlsxMatchProcedure
from ..helpers.schema import (
    OUTERDICT_NAME_VIEW,
    POPULATION_ECON_TABLE,
    POPULATION_NAMES_TABLE,
    POPULATION_TABLE,
    REGISTERED_RESOURCES_TABLE,
    SAMPLES_TABLE,
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
    KTP_FRAGMENT_TYPE_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_LAST_NAME_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_SOURCE_KEY_COL,
    KTP_XLSX_MATCH_COL,
    KTP_XLSX_MATCH_FIRST_TOKENS_KEY,
    KTP_XLSX_MATCH_LAST_NAME_NORM_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_FIRST_TOKEN_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY,
    STEP_MATCH_XLSX,
)
from .shared import draw_sort_ctes_sql, draw_sort_order_by_sql, hcr_excluded_columns


def run(context: PipelineContext) -> StepResult:
    if context.outer_dict is None:
        raise ValueError("OuterDict not initialized. Run build_outerdict first.")
    if context.resources is None:
        raise ValueError("Resources not initialized. Run register_resources first.")

    conn: duckdb.DuckDBPyConnection = context.conn
    population_columns = [row[0] for row in conn.execute(f"DESCRIBE {POPULATION_TABLE}").fetchall()]
    hcr_excluded = hcr_excluded_columns(population_columns)
    hcr_payload_columns = [
        col for col in population_columns if col.startswith("hcr.") and col not in hcr_excluded
    ]
    hcr_payload_select = ",\n                ".join([f'p."{col}"' for col in hcr_payload_columns])
    hcr_payload_suffix = f",\n                {hcr_payload_select}" if hcr_payload_select else ""
    hcr_projection_select = ",\n            ".join([f'p."{col}"' for col in hcr_payload_columns])
    hcr_projection_suffix = (
        f",\n            {hcr_projection_select}" if hcr_projection_select else ""
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {XLSX_MATCH_VIEW} AS
        WITH name_draws AS (
            SELECT nk."{KTP_SOURCE_KEY_COL}" as "{KTP_SOURCE_KEY_COL}",
                   nk."{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
                   nk."{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
                   lower(unaccent(nk."{KTP_FIRST_NAME_COL}")) AS nd_first_clean,
                   lower(unaccent(nk."{KTP_LAST_NAME_COL}")) AS nd_last_clean,
                   list_extract(
                       regexp_split_to_array(lower(unaccent(nk."{KTP_FIRST_NAME_COL}")), '\\s+'),
                       1
                   ) AS nd_first_token
            FROM {OUTERDICT_NAME_VIEW} nk
        ),
        pop_names AS (
            SELECT
                p."{HCR_FILENAME_COL}",
                p."{HCR_ROW_COL}",
                n."{KTP_FIRST_NAME_COL}" AS pop_first,
                n."{KTP_LAST_NAME_COL}" AS pop_last,
                lower(unaccent(n."{KTP_FIRST_NAME_COL}")) AS pop_first_clean,
                lower(unaccent(n."{KTP_LAST_NAME_COL}")) AS pop_last_clean,
                regexp_split_to_array(lower(unaccent(n."{KTP_FIRST_NAME_COL}")), '\\s+')
                    AS pop_first_tokens,
                regexp_split_to_array(lower(unaccent(n."{KTP_LAST_NAME_COL}")), '\\s+')
                    AS pop_last_tokens,
                e."{KTP_ECONOMIES_COL}" AS "{KTP_ECONOMIES_COL}",
                e."{KTP_ECONOMIES_INCOME_GROUP_COL}" AS "{KTP_ECONOMIES_INCOME_GROUP_COL}",
                e."{KTP_ECONOMY_MATCH_COL}" AS "{KTP_ECONOMY_MATCH_COL}",
                e."{KTP_HCR_PRIMARY_AFFILIATIONS_COL}" AS "{KTP_HCR_PRIMARY_AFFILIATIONS_COL}",
                e."{KTP_HCR_SECONDARY_AFFILIATIONS_COL}" AS "{KTP_HCR_SECONDARY_AFFILIATIONS_COL}",
                e."{KTP_PRIORITY_COL}" AS "{KTP_PRIORITY_COL}",
                e."{KTP_PRIORITY_GROUP_COL}" AS "{KTP_PRIORITY_GROUP_COL}",
                rr.fragment_type AS resource_fragment_type{hcr_payload_suffix}
            FROM {POPULATION_TABLE} p
            JOIN {POPULATION_NAMES_TABLE} n
              ON p."{KTP_POPULATION_INDEX_COL}" = n."{KTP_POPULATION_INDEX_COL}"
            LEFT JOIN {POPULATION_ECON_TABLE} e
              ON p."{KTP_POPULATION_INDEX_COL}" = e."{KTP_POPULATION_INDEX_COL}"
            LEFT JOIN {REGISTERED_RESOURCES_TABLE} rr
              ON rr.resource_name = p."{HCR_FILENAME_COL}"
        ),
        base AS (
            SELECT
                nd."{KTP_SOURCE_KEY_COL}",
                p."{HCR_FILENAME_COL}" AS "{KTP_FILENAME_COL}",
                p."{HCR_ROW_COL}" AS "{KTP_FRAGMENT_COL}",
                COALESCE(p.resource_fragment_type, 'excel_row') AS "{KTP_FRAGMENT_TYPE_COL}",
                s."{DRAW_LABEL}" AS "{DRAW_LABEL}",
                p.pop_first AS "{KTP_FIRST_NAME_COL}",
                p.pop_last AS "{KTP_LAST_NAME_COL}",
                json_object(
                    '{KTP_XLSX_MATCH_SOURCE_KEY_FIRST_TOKEN_KEY}', nd.nd_first_token,
                    '{KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY}', nd.nd_last_clean,
                    '{KTP_XLSX_MATCH_FIRST_TOKENS_KEY}', to_json(p.pop_first_tokens),
                    '{KTP_XLSX_MATCH_LAST_NAME_NORM_KEY}', p.pop_last_clean
                ) AS "{KTP_XLSX_MATCH_COL}",
                p."{KTP_HCR_PRIMARY_AFFILIATIONS_COL}",
                p."{KTP_HCR_SECONDARY_AFFILIATIONS_COL}"{hcr_projection_suffix},
                p."{KTP_ECONOMIES_COL}",
                p."{KTP_ECONOMIES_INCOME_GROUP_COL}",
                p."{KTP_ECONOMY_MATCH_COL}",
                p."{KTP_PRIORITY_COL}",
                p."{KTP_PRIORITY_GROUP_COL}"
            FROM pop_names p
            JOIN name_draws nd
              ON nd.nd_last_clean = p.pop_last_clean
             AND list_contains(p.pop_first_tokens, nd.nd_first_token)
            LEFT JOIN {SAMPLES_TABLE} s
              ON s."{KTP_FILENAME_COL}" = p."{HCR_FILENAME_COL}"
             AND s."{KTP_FRAGMENT_COL}" = p."{HCR_ROW_COL}"
            WHERE p."{HCR_FILENAME_COL}" IS NOT NULL
        ),
        {draw_sort_ctes_sql(draw_col=DRAW_LABEL, source_key_col=KTP_SOURCE_KEY_COL)}
        SELECT * EXCLUDE (row_draw_group, row_draw_num, source_draw_group, source_draw_num)
        FROM ranked
        ORDER BY
            {draw_sort_order_by_sql(
                source_key_col=KTP_SOURCE_KEY_COL,
                filename_col=KTP_FILENAME_COL,
                fragment_col=KTP_FRAGMENT_COL,
            )}
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
        WITH base AS (
            SELECT *
            FROM {XLSX_MATCH_VIEW}
            WHERE "{KTP_FILENAME_COL}" IS NOT NULL
        ),
        {draw_sort_ctes_sql(draw_col=DRAW_LABEL, source_key_col=KTP_SOURCE_KEY_COL)}
        SELECT * EXCLUDE (row_draw_group, row_draw_num, source_draw_group, source_draw_num)
        FROM ranked
        ORDER BY
            {draw_sort_order_by_sql(
                source_key_col=KTP_SOURCE_KEY_COL,
                filename_col=KTP_FILENAME_COL,
                fragment_col=KTP_FRAGMENT_COL,
            )}
        """
    )

    output_df = conn.execute(f"SELECT * FROM {XLSX_OUTPUT_VIEW}").df()

    return StepResult(
        step_id=STEP_MATCH_XLSX,
        artifacts={"xlsx_matches_df": output_df},
        messages=[f"Matched XLSX rows: {len(matched_df)}"],
        diagnostics=[f"Matched XLSX rows: {len(matched_df)}"],
    )
