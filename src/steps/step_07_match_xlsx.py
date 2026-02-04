from __future__ import annotations

import duckdb
import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.data_models import InnerDict
from ..helpers.duckdb_utils import register_frame
from ..helpers.jsonlines import dumps_jsonlines, loads_jsonlines
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
    KTP_ECONOMIES_GROUP_COL,
    KTP_ECONOMY_MATCH_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_LAST_NAME_COL,
)


def _append_innerdicts_from_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    context: PipelineContext,
) -> None:
    if context.outer_dict is None:
        raise ValueError("OuterDict not initialized. Run build_outerdict first.")
    outer_dict = context.outer_dict
    procedure = XlsxMatchProcedure()
    rows = conn.execute(f"SELECT name_key, innerdicts FROM {table_name}").fetchall()
    for name_key, payload in rows:
        for record in loads_jsonlines(payload or ""):
            if KTP_FILENAME_COL not in record:
                raise ValueError(f"Innerdict missing required column '{KTP_FILENAME_COL}'")
            if KTP_FRAGMENT_COL not in record:
                raise ValueError(f"Innerdict missing required column '{KTP_FRAGMENT_COL}'")
            inner = InnerDict.from_mapping(record, procedure)
            outer_dict.add_inner_by_key(str(name_key), inner)


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
            SELECT nk.name_key,
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
                e."{KTP_ECONOMIES_GROUP_COL}" AS "{KTP_ECONOMIES_GROUP_COL}",
                e."{KTP_ECONOMY_MATCH_COL}" AS "{KTP_ECONOMY_MATCH_COL}",
                e."ktp.priority" AS "ktp.priority",
                e."ktp.priority_group" AS "ktp.priority_group"
            FROM {POPULATION_TABLE} p
            JOIN {POPULATION_NAMES_TABLE} n
              ON p."ktp.population_index" = n."ktp.population_index"
            LEFT JOIN {POPULATION_ECON_TABLE} e
              ON p."ktp.population_index" = e."ktp.population_index"
        )
        SELECT
            nd.name_key,
            nd."{KTP_FIRST_NAME_COL}",
            nd."{KTP_LAST_NAME_COL}",
            nd."{DRAW_LABEL}",
            p.*,
            p."{HCR_FILENAME_COL}" AS "ktp.filename",
            p."{HCR_ROW_COL}" AS "{KTP_FRAGMENT_COL}",
            json_object(
                lower(unaccent(nd."{KTP_FIRST_NAME_COL}" || ' ' || nd."{KTP_LAST_NAME_COL}")),
                lower(unaccent(p.pop_first || ' ' || p.pop_last))
            ) AS "ktp.xlsx_match"
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
    matched_df = matched_df[matched_df["ktp.filename"].notna()]

    inner_rows = []
    for name_key, group in matched_df.groupby("name_key", dropna=False):
        rows = group.drop(columns=["name_key"]).to_dict("records")
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

    _append_innerdicts_from_table(conn, table_name=XLSX_INNERDICT_TABLE, context=context)

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {XLSX_OUTPUT_VIEW} AS
        SELECT x.*, nk."{KTP_FIRST_NAME_COL}", nk."{KTP_LAST_NAME_COL}",
               s."{DRAW_LABEL}" AS sample_draw,
               s."ktp.filename" AS sample_filename,
               s."ktp.fragment" AS sample_fragment,
               p.*, n.*, e.*
        FROM {XLSX_INNERDICT_TABLE} x
        LEFT JOIN {OUTERDICT_NAME_VIEW} nk
          ON x.name_key = nk.name_key
        LEFT JOIN {SAMPLES_WITH_NAMES_VIEW} s
          ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(s."{KTP_FIRST_NAME_COL}")
         AND lower(nk."{KTP_LAST_NAME_COL}") = lower(s."{KTP_LAST_NAME_COL}")
        LEFT JOIN {POPULATION_NAMES_TABLE} n
          ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(n."{KTP_FIRST_NAME_COL}")
         AND lower(nk."{KTP_LAST_NAME_COL}") = lower(n."{KTP_LAST_NAME_COL}")
        LEFT JOIN {POPULATION_TABLE} p
          ON p."ktp.population_index" = n."ktp.population_index"
        LEFT JOIN {POPULATION_ECON_TABLE} e
          ON p."ktp.population_index" = e."ktp.population_index"
        """
    )

    output_df = conn.execute(f"SELECT * FROM {XLSX_OUTPUT_VIEW}").df()

    return StepResult(
        step_id="match_xlsx",
        artifacts={"xlsx_matches_df": output_df},
        messages=[f"Matched XLSX rows: {len(matched_df)}"],
        diagnostics=[f"Matched XLSX rows: {len(matched_df)}"],
    )
