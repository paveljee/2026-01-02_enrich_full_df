from __future__ import annotations

import duckdb
import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.docx_loader import DOCX_ROW_NUMBER_COL, load_single_table_docx, normalize_docx_column_name
from ..helpers.duckdb_utils import register_frame
from ..helpers.jsonlines import dumps_jsonlines
from ..helpers.outerdict_io import append_innerdicts_from_table
from ..helpers.procedures import DocxMatchProcedure
from ..helpers.schema import (
    DOCX_INNERDICT_TABLE,
    DOCX_MATCH_VIEW,
    DOCX_OUTPUT_VIEW,
    DOCX_TABLE,
    OUTERDICT_NAME_VIEW,
    POPULATION_NAMES_TABLE,
    POPULATION_TABLE,
    SAMPLES_WITH_NAMES_VIEW,
)
from ..helpers.vars import DRAW_LABEL, KTP_FIRST_NAME_COL, KTP_FRAGMENT_COL, KTP_LAST_NAME_COL, RIGHT_NAME_COL


def run(context: PipelineContext) -> StepResult:
    if context.outer_dict is None:
        raise ValueError("OuterDict not initialized. Run build_outerdict first.")
    if context.resources is None:
        raise ValueError("Resources not initialized. Run register_resources first.")

    conn: duckdb.DuckDBPyConnection = context.conn
    docx_df = load_single_table_docx(context.resources.docx_resources)
    if docx_df.empty:
        raise ValueError("No DOCX rows loaded.")

    register_frame(conn, "docx_frame", docx_df)
    conn.execute(f"CREATE OR REPLACE TABLE {DOCX_TABLE} AS SELECT * FROM docx_frame")
    conn.execute("DROP TABLE IF EXISTS docx_frame")

    name_col = normalize_docx_column_name(RIGHT_NAME_COL)
    if name_col not in docx_df.columns:
        raise ValueError(
            f"Docx data does not contain expected name column '{RIGHT_NAME_COL}'."
        )

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {DOCX_MATCH_VIEW} AS
        WITH name_draws AS (
            SELECT nk.name_key,
                   nk."{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
                   nk."{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
                   s."{DRAW_LABEL}" AS "{DRAW_LABEL}"
            FROM {OUTERDICT_NAME_VIEW} nk
            LEFT JOIN {SAMPLES_WITH_NAMES_VIEW} s
              ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(s."{KTP_FIRST_NAME_COL}")
             AND lower(nk."{KTP_LAST_NAME_COL}") = lower(s."{KTP_LAST_NAME_COL}")
        )
        SELECT
            nd.name_key,
            nd."{KTP_FIRST_NAME_COL}",
            nd."{KTP_LAST_NAME_COL}",
            nd."{DRAW_LABEL}",
            d."ktp.filename" AS "ktp.filename",
            d."{DOCX_ROW_NUMBER_COL}" AS "{KTP_FRAGMENT_COL}",
            json_object(
                lower(unaccent(nd."{KTP_FIRST_NAME_COL}" || ' ' || nd."{KTP_LAST_NAME_COL}")),
                lower(unaccent(d."{name_col}"))
            ) AS "ktp.docx_match"
        FROM {DOCX_TABLE} d
        RIGHT JOIN name_draws nd
          ON array_length(
                list_intersect(
                    regexp_split_to_array(lower(unaccent(d."{name_col}")), '\\s+'),
                    regexp_split_to_array(
                        lower(unaccent(nd."{KTP_FIRST_NAME_COL}" || ' ' || nd."{KTP_LAST_NAME_COL}")),
                        '\\s+'
                    )
                )
             ) = array_length(
                regexp_split_to_array(
                    lower(unaccent(nd."{KTP_FIRST_NAME_COL}" || ' ' || nd."{KTP_LAST_NAME_COL}")),
                    '\\s+'
                )
             )
        """
    )

    matched_df = conn.execute(f"SELECT * FROM {DOCX_MATCH_VIEW}").df()
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
    register_frame(conn, "docx_innerdict_frame", inner_df)
    conn.execute(
        f"CREATE OR REPLACE TABLE {DOCX_INNERDICT_TABLE} AS SELECT * FROM docx_innerdict_frame"
    )
    conn.execute("DROP TABLE IF EXISTS docx_innerdict_frame")

    append_innerdicts_from_table(
        conn,
        context.outer_dict,
        table_name=DOCX_INNERDICT_TABLE,
        procedure=DocxMatchProcedure(),
        resources=context.resources.docx_resources,
    )

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {DOCX_OUTPUT_VIEW} AS
        SELECT d.*, nk."{KTP_FIRST_NAME_COL}", nk."{KTP_LAST_NAME_COL}",
               s."{DRAW_LABEL}" AS sample_draw,
               s."ktp.filename" AS sample_filename,
               s."ktp.fragment" AS sample_fragment,
               p.*, n.*
        FROM {DOCX_INNERDICT_TABLE} d
        FULL OUTER JOIN {OUTERDICT_NAME_VIEW} nk
          ON d.name_key = nk.name_key
        FULL OUTER JOIN {SAMPLES_WITH_NAMES_VIEW} s
          ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(s."{KTP_FIRST_NAME_COL}")
         AND lower(nk."{KTP_LAST_NAME_COL}") = lower(s."{KTP_LAST_NAME_COL}")
        FULL OUTER JOIN {POPULATION_NAMES_TABLE} n
          ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(n."{KTP_FIRST_NAME_COL}")
         AND lower(nk."{KTP_LAST_NAME_COL}") = lower(n."{KTP_LAST_NAME_COL}")
        FULL OUTER JOIN {POPULATION_TABLE} p
          ON p."ktp.population_index" = n."ktp.population_index"
        """
    )

    output_df = conn.execute(f"SELECT * FROM {DOCX_OUTPUT_VIEW}").df()

    return StepResult(
        step_id="match_docx",
        artifacts={"docx_matches_df": output_df},
        messages=[f"Matched DOCX rows: {len(matched_df)}"],
        diagnostics=[f"Matched DOCX rows: {len(matched_df)}"],
    )
