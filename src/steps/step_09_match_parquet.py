from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from ..helpers.models import NameKey
from ..helpers.context import PipelineContext, StepResult
from ..helpers.duckdb_utils import register_frame
from ..helpers.jsonlines import dumps_jsonlines
from ..helpers.outerdict_io import append_innerdicts_from_table
from ..helpers.parquet_utils import normalize_parquet_column_name, parquet_columns, parquet_filename
from ..helpers.procedures import ParquetMatchProcedure
from ..helpers.schema import (
    OUTERDICT_NAME_VIEW,
    PARQUET_AUTHOR_MATCH_TABLE,
    PARQUET_INNERDICT_TABLE,
    POPULATION_NAMES_TABLE,
    POPULATION_TABLE,
    SAMPLES_WITH_NAMES_VIEW,
    safe_identifier,
)
from ..helpers.vars import KTP_FILENAME_COL, KTP_FIRST_NAME_COL, KTP_FRAGMENT_COL, KTP_LAST_NAME_COL


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

    conn: duckdb.DuckDBPyConnection = context.conn
    files = context.config.files_config
    author_details_path = files["author_details"]["path"]
    authors_paper_path = files["authors_paper"]["path"]
    hit_papers0_path = files["hit_papers_0"]["path"]
    hit_papers1_path = files["hit_papers_1"]["path"]

    author_id_col = normalize_parquet_column_name("authorid", "ssnad")
    author_id_raw = "authorid"

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {PARQUET_AUTHOR_MATCH_TABLE} AS
        WITH names AS (
            SELECT
                name_key,
                "{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
                "{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
                lower(unaccent("{KTP_FIRST_NAME_COL}" || ' ' || "{KTP_LAST_NAME_COL}")) AS match_key_norm
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
            n."{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
            n."{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
            p.authorid AS "{author_id_col}",
            p.display_name AS "ssnad.display_name",
            p.display_name_alternatives AS "ssnad.display_name_alternatives",
            json_object(
                n.match_key_norm,
                lower(unaccent(p.alt_name))
            ) AS "ktp.ssnad_match"
        FROM names n
        JOIN parq p
          ON lower(unaccent(p.alt_name)) = n.match_key_norm
        """
    )

    author_table = f"ssn_{safe_identifier(Path(author_details_path).stem)}"
    _create_parquet_table(
        conn,
        table_name=author_table,
        path=author_details_path,
        prefix="ssnad",
        join_sql=f"JOIN {PARQUET_AUTHOR_MATCH_TABLE} m ON parq.{author_id_raw} = m.\"{author_id_col}\"",
    )

    authors_paper_table = f"ssn_{safe_identifier(Path(authors_paper_path).stem)}"
    _create_parquet_table(
        conn,
        table_name=authors_paper_table,
        path=authors_paper_path,
        prefix="ssnap",
        join_sql=f"JOIN {PARQUET_AUTHOR_MATCH_TABLE} m ON parq.{author_id_raw} = m.\"{author_id_col}\"",
    )

    authors_paper_author_col = normalize_parquet_column_name("authorid", "ssnap")
    authors_paper_paper_col = normalize_parquet_column_name("paperid", "ssnap")
    paper_id_col = authors_paper_paper_col
    matched_papers_sql = (
        f'SELECT DISTINCT "{paper_id_col}" AS paperid FROM {authors_paper_table}'
    )

    hit0_table = f"ssn_{safe_identifier(Path(hit_papers0_path).stem)}"
    _create_parquet_table(
        conn,
        table_name=hit0_table,
        path=hit_papers0_path,
        prefix="ssnhpl0",
        join_sql=f"JOIN ({matched_papers_sql}) mp ON parq.paperid = mp.paperid",
    )

    hit1_table = f"ssn_{safe_identifier(Path(hit_papers1_path).stem)}"
    _create_parquet_table(
        conn,
        table_name=hit1_table,
        path=hit_papers1_path,
        prefix="ssnhpl1",
        join_sql=f"JOIN ({matched_papers_sql}) mp ON parq.paperid = mp.paperid",
    )

    hit0_paper_col = normalize_parquet_column_name("paperid", "ssnhpl0")
    hit1_paper_col = normalize_parquet_column_name("paperid", "ssnhpl1")

    def view_name(base: str) -> str:
        return f"{base}_view"

    author_view = view_name(author_table)
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {author_view} AS
        SELECT m."{KTP_FIRST_NAME_COL}", m."{KTP_LAST_NAME_COL}",
               t."ssn.filename" AS "{KTP_FILENAME_COL}",
               t."{author_id_col}" AS "{KTP_FRAGMENT_COL}",
               t.*
        FROM {PARQUET_AUTHOR_MATCH_TABLE} m
        JOIN {author_table} t
          ON t."{author_id_col}" = m."{author_id_col}"
        """
    )

    authors_paper_view = view_name(authors_paper_table)
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {authors_paper_view} AS
        SELECT m."{KTP_FIRST_NAME_COL}", m."{KTP_LAST_NAME_COL}",
               t."ssn.filename" AS "{KTP_FILENAME_COL}",
               t."{authors_paper_paper_col}" AS "{KTP_FRAGMENT_COL}",
               t.*
        FROM {PARQUET_AUTHOR_MATCH_TABLE} m
        JOIN {authors_paper_table} t
          ON t."{authors_paper_author_col}" = m."{author_id_col}"
        """
    )

    hit0_view = view_name(hit0_table)
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {hit0_view} AS
        SELECT m."{KTP_FIRST_NAME_COL}", m."{KTP_LAST_NAME_COL}",
               t."ssn.filename" AS "{KTP_FILENAME_COL}",
               t."{hit0_paper_col}" AS "{KTP_FRAGMENT_COL}",
               t.*
        FROM {PARQUET_AUTHOR_MATCH_TABLE} m
        JOIN {authors_paper_table} ap
          ON ap."{authors_paper_author_col}" = m."{author_id_col}"
        JOIN {hit0_table} t
          ON t."{hit0_paper_col}" = ap."{authors_paper_paper_col}"
        """
    )

    hit1_view = view_name(hit1_table)
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {hit1_view} AS
        SELECT m."{KTP_FIRST_NAME_COL}", m."{KTP_LAST_NAME_COL}",
               t."ssn.filename" AS "{KTP_FILENAME_COL}",
               t."{hit1_paper_col}" AS "{KTP_FRAGMENT_COL}",
               t.*
        FROM {PARQUET_AUTHOR_MATCH_TABLE} m
        JOIN {authors_paper_table} ap
          ON ap."{authors_paper_author_col}" = m."{author_id_col}"
        JOIN {hit1_table} t
          ON t."{hit1_paper_col}" = ap."{authors_paper_paper_col}"
        """
    )

    view_names = [author_view, authors_paper_view, hit0_view, hit1_view]
    view_dfs = [conn.execute(f"SELECT * FROM {view_name}").df() for view_name in view_names]

    all_rows = []
    for df in view_dfs:
        if df.empty:
            continue
        for record in df.to_dict("records"):
            name_key = NameKey(
                first_name=record[KTP_FIRST_NAME_COL],
                last_name=record[KTP_LAST_NAME_COL],
            ).to_json_key()
            record["name_key"] = name_key
            all_rows.append(record)

    inner_rows = []
    if all_rows:
        rows_df = pd.DataFrame(all_rows)
        for name_key, group in rows_df.groupby("name_key", dropna=False):
            rows = group.drop(columns=["name_key"]).to_dict("records")
            inner_rows.append({"name_key": name_key, "innerdicts": dumps_jsonlines(rows)})

    inner_df = pd.DataFrame(inner_rows, columns=["name_key", "innerdicts"])
    register_frame(conn, "ssn_innerdict_frame", inner_df)
    conn.execute(
        f"CREATE OR REPLACE TABLE {PARQUET_INNERDICT_TABLE} AS SELECT * FROM ssn_innerdict_frame"
    )
    conn.execute("DROP TABLE IF EXISTS ssn_innerdict_frame")

    append_innerdicts_from_table(
        conn,
        context.outer_dict,
        table_name=PARQUET_INNERDICT_TABLE,
        procedure=ParquetMatchProcedure(),
        resources=context.resources.parquet_resources,
    )

    output_views: list[str] = []
    for base_view in view_names:
        out_view = f"{base_view}_output"
        conn.execute(
            f"""
            CREATE OR REPLACE VIEW {out_view} AS
            SELECT v.*, s."{KTP_FILENAME_COL}" AS sample_filename,
                   s."{KTP_FRAGMENT_COL}" AS sample_fragment,
                   s."ktp.draw_number" AS sample_draw,
                   p.*, n.*
            FROM {base_view} v
            FULL OUTER JOIN {SAMPLES_WITH_NAMES_VIEW} s
              ON lower(v."{KTP_FIRST_NAME_COL}") = lower(s."{KTP_FIRST_NAME_COL}")
             AND lower(v."{KTP_LAST_NAME_COL}") = lower(s."{KTP_LAST_NAME_COL}")
            FULL OUTER JOIN {POPULATION_NAMES_TABLE} n
              ON lower(v."{KTP_FIRST_NAME_COL}") = lower(n."{KTP_FIRST_NAME_COL}")
             AND lower(v."{KTP_LAST_NAME_COL}") = lower(n."{KTP_LAST_NAME_COL}")
            FULL OUTER JOIN {POPULATION_TABLE} p
              ON p."ktp.population_index" = n."ktp.population_index"
            """
        )
        output_views.append(out_view)

    output_dfs = [conn.execute(f"SELECT * FROM {view}").df() for view in output_views]

    return StepResult(
        step_id="match_parquet",
        artifacts={"parquet_match_dfs": output_dfs, "parquet_view_names": output_views},
        messages=[f"Parquet views created: {len(output_dfs)}"],
        diagnostics=[f"Parquet match views: {len(output_dfs)}"],
    )
