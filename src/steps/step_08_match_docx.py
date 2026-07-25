from __future__ import annotations

import re
from pathlib import Path
from zipfile import BadZipFile

import duckdb
import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.data_models import RegisteredResource
from ..helpers.docx_parse import parse_docx_tables_and_notes
from ..helpers.duckdb_utils import (
    append_innerdicts_from_jsonlines_table,
    materialize_innerdicts_from_rows_table,
    register_frame,
)
from ..helpers.name_matching import docx_match_condition_sql, docx_name_norm_sql
from ..helpers.procedures import DocxMatchProcedure
from ..helpers.schema import (
    DOCX_INNERDICT_TABLE,
    DOCX_MATCH_VIEW,
    DOCX_OUTPUT_VIEW,
    DOCX_TABLE,
    INNERDICT_SOURCE_RELATIONS,
    OUTERDICT_NAME_VIEW,
    REGISTERED_RESOURCES_TABLE,
    SAMPLES_WITH_NAMES_VIEW,
)
from ..helpers.vars import (
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    DRAW_LABEL,
    KTP_DOCX_COMMENTS_COL,
    KTP_DOCX_FOOTNOTES_COL,
    KTP_DOCX_MATCH_COL,
    KTP_DOCX_MATCH_DOCX_NAME_NORM_KEY,
    KTP_DOCX_MATCH_KTP_FIRST_NORM_KEY,
    KTP_DOCX_MATCH_KTP_LAST_NORM_KEY,
    KTP_DOCX_MATCH_RULE_KEY,
    KTP_DOCX_MATCH_RULE_V1,
    KTP_DOCX_ROW_NUMBER_COL,
    KTP_DOCX_TABLE_1_PREFIX,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_LAST_NAME_COL,
    KTP_SOURCE_KEY_COL,
    RIGHT_NAME_COL,
    STEP_MATCH_DOCX,
)
from .shared import draw_sort_ctes_sql, draw_sort_order_by_sql


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
        tables, footnotes_text, comments_by_table_row = parse_docx_tables_and_notes(path)
        for table_index, df in enumerate(tables):
            table = df.copy()
            table.columns = [normalize_docx_column_name(col) for col in table.columns]
            table[KTP_DOCX_FOOTNOTES_COL] = footnotes_text
            row_comments = (
                comments_by_table_row[table_index]
                if table_index < len(comments_by_table_row)
                else [""] * len(table)
            )
            if len(row_comments) != len(table):
                raise ValueError(
                    f"DOCX row comments mismatch for '{path.name}' table {table_index}: "
                    f"{len(row_comments)} comments for {len(table)} rows."
                )
            table[KTP_DOCX_COMMENTS_COL] = row_comments
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
        if path.name.startswith("~$"):
            continue
        try:
            tables, footnotes_text, comments_by_table_row = parse_docx_tables_and_notes(path)
        except BadZipFile as exc:
            raise ValueError(
                f"Invalid DOCX file '{path.name}' (not a valid DOCX/zip archive). "
                "Remove temp/lock files (e.g., '~$*.docx') from docx_dir."
            ) from exc
        if len(tables) != 1:
            raise ValueError(
                f"Expected exactly one table in DOCX '{path.name}', got {len(tables)}"
            )
        table = tables[0].copy()
        table.columns = [normalize_docx_column_name(col) for col in table.columns]
        table[KTP_DOCX_FOOTNOTES_COL] = footnotes_text
        row_comments = comments_by_table_row[0] if comments_by_table_row else [""] * len(table)
        if len(row_comments) != len(table):
            raise ValueError(
                f"DOCX row comments mismatch for '{path.name}': "
                f"{len(row_comments)} comments for {len(table)} rows."
            )
        table[KTP_DOCX_COMMENTS_COL] = row_comments
        table[KTP_FILENAME_COL] = path.name
        table[KTP_DOCX_ROW_NUMBER_COL] = range(1, len(table) + 1)
        frames.append(table)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


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

    docx_first_norm_expr = docx_name_norm_sql('nd."' + KTP_FIRST_NAME_COL + '"')
    docx_last_norm_expr = docx_name_norm_sql('nd."' + KTP_LAST_NAME_COL + '"')
    docx_table_name_norm_expr = docx_name_norm_sql(
        'd."' + name_col + '"',
        coalesce_empty=True,
    )
    docx_join_condition = docx_match_condition_sql(
        "nd.first_clean",
        "nd.last_clean",
        "d.docx_clean",
    )

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {DOCX_MATCH_VIEW} AS
        WITH name_draws AS (
            SELECT nk."{KTP_SOURCE_KEY_COL}",
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
                {docx_first_norm_expr} AS first_clean,
                {docx_last_norm_expr} AS last_clean
            FROM name_draws nd
            WHERE nd."{KTP_FIRST_NAME_COL}" IS NOT NULL
              AND nd."{KTP_LAST_NAME_COL}" IS NOT NULL
              AND nd."{KTP_FIRST_NAME_COL}" <> ''
              AND nd."{KTP_LAST_NAME_COL}" <> ''
        ),
        docx_clean AS (
            SELECT
                d.*,
                {docx_table_name_norm_expr} AS docx_clean
            FROM {DOCX_TABLE} d
        ),
        base AS (
            SELECT
                nd."{KTP_SOURCE_KEY_COL}" AS "{KTP_SOURCE_KEY_COL}",
                d."{KTP_FILENAME_COL}" AS "{KTP_FILENAME_COL}",
                d."{KTP_DOCX_ROW_NUMBER_COL}" AS "{KTP_FRAGMENT_COL}",
                COALESCE(rr.fragment_type, 'docx_row') AS "{KTP_FRAGMENT_TYPE_COL}",
                nd."{DRAW_LABEL}" AS "{DRAW_LABEL}",
                nd."{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
                nd."{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
                json_object(
                    '{KTP_DOCX_MATCH_RULE_KEY}', '{KTP_DOCX_MATCH_RULE_V1}',
                    '{KTP_DOCX_MATCH_KTP_FIRST_NORM_KEY}', nd.first_clean,
                    '{KTP_DOCX_MATCH_KTP_LAST_NORM_KEY}', nd.last_clean,
                    '{KTP_DOCX_MATCH_DOCX_NAME_NORM_KEY}', d.docx_clean
                ) AS "{KTP_DOCX_MATCH_COL}",
                d.* EXCLUDE ("{KTP_FILENAME_COL}", "{KTP_DOCX_ROW_NUMBER_COL}", docx_clean)
            FROM docx_clean d
            RIGHT JOIN names_clean nd
              ON {docx_join_condition}
            LEFT JOIN {REGISTERED_RESOURCES_TABLE} rr
              ON rr.resource_name = d."{KTP_FILENAME_COL}"
            WHERE d."{KTP_FILENAME_COL}" IS NOT NULL
        )
        ,
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

    _innerdict_keys, matched_rows = materialize_innerdicts_from_rows_table(
        conn,
        source_relation=INNERDICT_SOURCE_RELATIONS[DOCX_INNERDICT_TABLE],
        table_name=DOCX_INNERDICT_TABLE,
    )

    append_innerdicts_from_jsonlines_table(
        conn,
        table_name=DOCX_INNERDICT_TABLE,
        outer_dict=context.outer_dict,
        procedure=DocxMatchProcedure(),
        required_columns={KTP_FILENAME_COL, KTP_FRAGMENT_COL},
    )

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {DOCX_OUTPUT_VIEW} AS
        WITH base AS (
            SELECT *
            FROM {DOCX_MATCH_VIEW}
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

    output_df = conn.execute(f"SELECT * FROM {DOCX_OUTPUT_VIEW}").df()

    return StepResult(
        step_id=STEP_MATCH_DOCX,
        artifacts={"docx_matches_df": output_df},
        messages=[f"Matched DOCX rows: {matched_rows}"],
        diagnostics=[f"Matched DOCX rows: {matched_rows}"],
    )
