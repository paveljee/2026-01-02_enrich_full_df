from __future__ import annotations

from pathlib import Path

import duckdb

from ..helpers.context import PipelineContext, StepResult
from ..helpers.data_models import InnerDict
from ..helpers.parquet_utils import normalize_parquet_column_name, parquet_columns, parquet_filename
from ..helpers.procedures import ParquetMatchProcedure
from ..helpers.schema import (
    OUTERDICT_NAME_VIEW,
    PARQUET_AUTHOR_MATCH_TABLE,
    PARQUET_AUTHOR_OUTPUT_TABLE,
    POPULATION_ECON_TABLE,
    POPULATION_TABLE,
    SAMPLES_WITH_NAMES_VIEW,
    safe_identifier,
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
    KTP_SSNAD_MATCH_COL,
)


def _append_innerdicts_from_rows_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    context: PipelineContext,
) -> None:
    if context.outer_dict is None:
        raise ValueError("OuterDict not initialized. Run build_outerdict first.")
    outer_dict = context.outer_dict
    procedure = ParquetMatchProcedure()
    rel = conn.execute(f"SELECT * FROM {table_name}")
    cols = [desc[0] for desc in rel.description]
    try:
        name_idx = cols.index("name_key")
    except ValueError as exc:
        raise ValueError(f"Missing name_key column in {table_name}") from exc
    while True:
        rows = rel.fetchmany(5000)
        if not rows:
            break
        for row in rows:
            name_key = row[name_idx]
            record = {col: row[i] for i, col in enumerate(cols) if i != name_idx}
            inner = InnerDict.from_mapping(record, procedure)
            outer_dict.add_inner_by_key(str(name_key), inner)


def _create_parquet_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    path: str,
    prefix: str,
    join_sql: str,
) -> dict[str, str]:
    columns = parquet_columns(conn, path)
    select_cols = ", ".join(
        [f'parq."{col}" AS "{normalize_parquet_column_name(col, prefix)}"' for col in columns]
    )
    filename = parquet_filename(path)
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {table_name} AS
        SELECT {select_cols},
               '{filename}' AS "ssn.filename"
        FROM read_parquet('{path}') parq
        {join_sql}
        """
    )
    return {col: normalize_parquet_column_name(col, prefix) for col in columns}


def run(context: PipelineContext) -> StepResult:
    if context.outer_dict is None:
        raise ValueError("OuterDict not initialized. Run build_outerdict first.")
    if context.resources is None:
        raise ValueError("Resources not initialized. Run register_resources first.")

    def log(msg: str) -> None:
        if context.log:
            context.log(msg, "cyan")

    conn: duckdb.DuckDBPyConnection = context.conn
    files = context.config.files_config
    author_details_path = files["author_details"]["path"]
    authors_paper_path = files["authors_paper"]["path"]
    hit_papers0_path = files["hit_papers_0"]["path"]
    hit_papers1_path = files["hit_papers_1"]["path"]

    author_id_col = normalize_parquet_column_name("authorid", "ssnad")
    author_id_raw = "authorid"

    log("Match author details to name keys (author_details scan)")
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {PARQUET_AUTHOR_MATCH_TABLE} AS
        WITH names AS (
            SELECT
                name_key,
                "{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
                "{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
                lower(
                    unaccent("{KTP_FIRST_NAME_COL}" || ' ' || "{KTP_LAST_NAME_COL}")
                ) AS match_key_norm
            FROM {OUTERDICT_NAME_VIEW}
        ),
        parq AS (
            SELECT
                authorid,
                display_name,
                display_name_alternatives,
                unnest(CAST(json(display_name_alternatives) AS VARCHAR[])) AS alt_name
            FROM read_parquet('{author_details_path}')
            UNION ALL
            SELECT
                authorid,
                display_name,
                display_name_alternatives,
                display_name AS alt_name
            FROM read_parquet('{author_details_path}')
        )
        SELECT DISTINCT
            n.name_key AS name_key,
            n."{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
            n."{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
            p.authorid AS "{author_id_col}",
            p.display_name AS "ssnad.display_name",
            p.display_name_alternatives AS "ssnad.display_name_alternatives",
            json_object(
                n.match_key_norm,
                lower(unaccent(p.alt_name))
            ) AS "{KTP_SSNAD_MATCH_COL}"
        FROM names n
        JOIN parq p
          ON lower(unaccent(p.alt_name)) = n.match_key_norm
        """
    )

    log("Create matched author_details table")
    author_table = f"ssn_{safe_identifier(Path(author_details_path).stem)}"
    _create_parquet_table(
        conn,
        table_name=author_table,
        path=author_details_path,
        prefix="ssnad",
        join_sql=(
            "JOIN "
            f"{PARQUET_AUTHOR_MATCH_TABLE} m ON parq.{author_id_raw} = m.\"{author_id_col}\""
        ),
    )

    log("Create author->paper table")
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE ssn_author_papers AS
        SELECT
            m.name_key AS name_key,
            m."{author_id_col}" AS authorid,
            pap.paperid AS paperid
        FROM {PARQUET_AUTHOR_MATCH_TABLE} m
        JOIN read_parquet('{authors_paper_path}') pap
          ON pap.authorid = m."{author_id_col}"
        """
    )

    log("Create hits union view")
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW ssn_all_hits AS
        SELECT paperid, fieldid, "Hit_1pct" AS hit_1pct, 'level0' AS level
        FROM read_parquet('{hit_papers0_path}')
        UNION ALL
        SELECT paperid, fieldid, "Hit_1pct" AS hit_1pct, 'level1' AS level
        FROM read_parquet('{hit_papers1_path}')
        """
    )

    log("Aggregate author-level hit stats")
    conn.execute(
        """
        CREATE OR REPLACE TABLE ssn_author_agg AS
        SELECT
            ap.name_key AS name_key,
            ap.authorid AS authorid,
            SUM(COALESCE(h.hit_1pct, 0)) AS "ssn.sum_hit_1pct",
            LIST(ap.paperid) FILTER (WHERE h.level = 'level0') AS "ssn.paperids_level0",
            LIST(ap.paperid) FILTER (WHERE h.level = 'level1') AS "ssn.paperids_level1",
            LIST(DISTINCT h.fieldid) AS "ssn.field_ids_list"
        FROM ssn_author_papers ap
        LEFT JOIN ssn_all_hits h
          ON ap.paperid = h.paperid
        GROUP BY ap.name_key, ap.authorid
        """
    )

    log("Create author-level output table")
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {PARQUET_AUTHOR_OUTPUT_TABLE} AS
        SELECT
            m.name_key AS name_key,
            m."{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
            m."{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
            a."{author_id_col}" AS "{KTP_FRAGMENT_COL}",
            a.*,
            CAST(agg."ssn.paperids_level0" AS VARCHAR) AS "ssn.paperids_level0",
            CAST(agg."ssn.paperids_level1" AS VARCHAR) AS "ssn.paperids_level1",
            CAST(agg."ssn.field_ids_list" AS VARCHAR) AS "ssn.field_ids_list",
            agg."ssn.sum_hit_1pct"
        FROM {PARQUET_AUTHOR_MATCH_TABLE} m
        JOIN {author_table} a
          ON a."{author_id_col}" = m."{author_id_col}"
        LEFT JOIN ssn_author_agg agg
          ON agg.authorid = m."{author_id_col}"
         AND agg.name_key = m.name_key
        """
    )

    log("Append parquet matches into OuterDict")
    _append_innerdicts_from_rows_table(
        conn,
        table_name=PARQUET_AUTHOR_OUTPUT_TABLE,
        context=context,
    )

    log("Create parquet output view")
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW ssn_parquet_output AS
        WITH sample_context AS (
            SELECT
                s."{KTP_FILENAME_COL}" AS sample_filename,
                s."{KTP_FRAGMENT_COL}" AS sample_fragment,
                s."{DRAW_LABEL}" AS sample_draw,
                s."{KTP_FIRST_NAME_COL}",
                s."{KTP_LAST_NAME_COL}",
                p.*,
                e."{KTP_ECONOMIES_COL}" AS "{KTP_ECONOMIES_COL}",
                e."{KTP_ECONOMIES_INCOME_GROUP_COL}" AS "{KTP_ECONOMIES_INCOME_GROUP_COL}",
                e."{KTP_ECONOMY_MATCH_COL}" AS "{KTP_ECONOMY_MATCH_COL}",
                e."{KTP_PRIORITY_COL}" AS "{KTP_PRIORITY_COL}",
                e."{KTP_PRIORITY_GROUP_COL}" AS "{KTP_PRIORITY_GROUP_COL}"
            FROM {SAMPLES_WITH_NAMES_VIEW} s
            JOIN {POPULATION_TABLE} p
              ON s."{KTP_FILENAME_COL}" = p."{HCR_FILENAME_COL}"
             AND s."{KTP_FRAGMENT_COL}" = p."{HCR_ROW_COL}"
            LEFT JOIN {POPULATION_ECON_TABLE} e
              ON p."{KTP_POPULATION_INDEX_COL}" = e."{KTP_POPULATION_INDEX_COL}"
        )
        SELECT v.*, sc.*
        FROM {PARQUET_AUTHOR_OUTPUT_TABLE} v
        LEFT JOIN sample_context sc
          ON lower(v."{KTP_FIRST_NAME_COL}") = lower(sc."{KTP_FIRST_NAME_COL}")
         AND lower(v."{KTP_LAST_NAME_COL}") = lower(sc."{KTP_LAST_NAME_COL}")
        """
    )

    log("Load parquet output dataframe")
    output_dfs = [conn.execute("SELECT * FROM ssn_parquet_output").df()]
    output_views = ["ssn_parquet_output"]

    return StepResult(
        step_id="match_parquet",
        artifacts={"parquet_match_dfs": output_dfs, "parquet_view_names": output_views},
        messages=[f"Parquet views created: {len(output_dfs)}"],
        diagnostics=[f"Parquet match views: {len(output_dfs)}"],
    )
