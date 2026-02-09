from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.data_models import InnerDict, RegisteredResource
from ..helpers.docx_parse import parse_docx_table
from ..helpers.duckdb_utils import register_frame
from ..helpers.jsonlines import dumps_jsonlines, loads_jsonlines
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
from ..helpers.vars import (
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    DRAW_LABEL,
    KTP_DOCX_MATCH_COL,
    KTP_DOCX_ROW_NUMBER_COL,
    KTP_DOCX_TABLE_1_PREFIX,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_LAST_NAME_COL,
    KTP_POPULATION_INDEX_COL,
    RIGHT_NAME_COL,
    STEP_MATCH_DOCX,
)


def normalize_docx_column_name(column: str) -> str:
    if re.match(r"^[\w_]+\.", str(column)):
        return str(column)
    normalized = re.sub(r"[^\w\s]", "_", str(column).lower())
    normalized = re.sub(r"\s", "_", normalized)
    normalized = f"{KTP_DOCX_TABLE_1_PREFIX}{normalized}"
    normalized = re.sub(r"_+", "_", normalized)
    return normalized


def load_docx_tables(resources: dict[str, RegisteredResource]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for resource in resources.values():
        path = Path(resource.__fspath__())
        tables = parse_docx_table(path)
        for table_index, df in enumerate(tables):
            table = df.copy()
            table.columns = [normalize_docx_column_name(col) for col in table.columns]
            table[KTP_FILENAME_COL] = path.name
            table[DOCX_TABLE_INDEX_COL] = table_index
            table[DOCX_ROW_INDEX_COL] = range(len(table))
            table[DOCX_FRAGMENT_COL] = [
                f"table{table_index}_row{row_index}" for row_index in range(len(table))
            ]
            frames.append(table)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_single_table_docx(resources: dict[str, RegisteredResource]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for resource in resources.values():
        path = Path(resource.__fspath__())
        tables = parse_docx_table(path)
        if len(tables) != 1:
            raise ValueError(
                f"Expected exactly one table in DOCX '{path.name}', got {len(tables)}"
            )
        table = tables[0].copy()
        table.columns = [normalize_docx_column_name(col) for col in table.columns]
        table[KTP_FILENAME_COL] = path.name
        table[KTP_DOCX_ROW_NUMBER_COL] = range(1, len(table) + 1)
        frames.append(table)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _append_innerdicts_from_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    context: PipelineContext,
) -> None:
    if context.outer_dict is None:
        raise ValueError("OuterDict not initialized. Run build_outerdict first.")
    outer_dict = context.outer_dict
    procedure = DocxMatchProcedure()
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
        ),
        names_clean AS (
            SELECT
                nd.*,
                regexp_replace(lower(unaccent(nd."{KTP_FIRST_NAME_COL}")), '[^0-9a-z]+', '', 'g')
                    AS first_clean,
                regexp_replace(lower(unaccent(nd."{KTP_LAST_NAME_COL}")), '[^0-9a-z]+', '', 'g')
                    AS last_clean
            FROM name_draws nd
            WHERE nd."{KTP_FIRST_NAME_COL}" IS NOT NULL
              AND nd."{KTP_LAST_NAME_COL}" IS NOT NULL
              AND nd."{KTP_FIRST_NAME_COL}" <> ''
              AND nd."{KTP_LAST_NAME_COL}" <> ''
        ),
        docx_clean AS (
            SELECT
                d.*,
                regexp_replace(lower(unaccent(COALESCE(d."{name_col}", ''))), '[^0-9a-z]+', '', 'g')
                    AS docx_clean
            FROM {DOCX_TABLE} d
        )
        SELECT
            nd.name_key,
            nd."{KTP_FIRST_NAME_COL}",
            nd."{KTP_LAST_NAME_COL}",
            nd."{DRAW_LABEL}",
            d.*,
            d."{KTP_DOCX_ROW_NUMBER_COL}" AS "{KTP_FRAGMENT_COL}",
            json_object(
                lower(unaccent(nd."{KTP_FIRST_NAME_COL}" || ' ' || nd."{KTP_LAST_NAME_COL}")),
                lower(unaccent(d."{name_col}"))
            ) AS "{KTP_DOCX_MATCH_COL}"
        FROM docx_clean d
        RIGHT JOIN names_clean nd
          ON POSITION(nd.first_clean IN d.docx_clean) > 0
         AND POSITION(nd.last_clean IN d.docx_clean) > 0
        """
    )

    matched_df = conn.execute(f"SELECT * FROM {DOCX_MATCH_VIEW}").df()
    if "docx_clean" in matched_df.columns:
        matched_df = matched_df.drop(columns=["docx_clean"])
    matched_df = matched_df[matched_df[KTP_FILENAME_COL].notna()]

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

    _append_innerdicts_from_table(conn, table_name=DOCX_INNERDICT_TABLE, context=context)

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {DOCX_OUTPUT_VIEW} AS
        SELECT d.*, nk."{KTP_FIRST_NAME_COL}", nk."{KTP_LAST_NAME_COL}",
               s."{DRAW_LABEL}" AS sample_draw,
               s."{KTP_FILENAME_COL}" AS sample_filename,
               s."{KTP_FRAGMENT_COL}" AS sample_fragment,
               p.*, n.*
        FROM {DOCX_INNERDICT_TABLE} d
        LEFT JOIN {OUTERDICT_NAME_VIEW} nk
          ON d.name_key = nk.name_key
        LEFT JOIN {SAMPLES_WITH_NAMES_VIEW} s
          ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(s."{KTP_FIRST_NAME_COL}")
         AND lower(nk."{KTP_LAST_NAME_COL}") = lower(s."{KTP_LAST_NAME_COL}")
        LEFT JOIN {POPULATION_NAMES_TABLE} n
          ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(n."{KTP_FIRST_NAME_COL}")
         AND lower(nk."{KTP_LAST_NAME_COL}") = lower(n."{KTP_LAST_NAME_COL}")
        LEFT JOIN {POPULATION_TABLE} p
          ON p."{KTP_POPULATION_INDEX_COL}" = n."{KTP_POPULATION_INDEX_COL}"
        """
    )

    output_df = conn.execute(f"SELECT * FROM {DOCX_OUTPUT_VIEW}").df()

    return StepResult(
        step_id=STEP_MATCH_DOCX,
        artifacts={"docx_matches_df": output_df},
        messages=[f"Matched DOCX rows: {len(matched_df)}"],
        diagnostics=[f"Matched DOCX rows: {len(matched_df)}"],
    )
