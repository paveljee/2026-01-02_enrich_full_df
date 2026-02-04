from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .._vars import KTP_FILENAME_COL, KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from ..data_models import OuterDict, RegisteredResource
from ..utils.name_keys import NAME_KEY_COL
from ..utils.records import append_records

AUTHOR_ID_FRAGMENT_COL = "ktp.author_id_fragment"


class ParquetMatchProcedure:
    dataset_id_field = "ktp.source_key"


def match_parquet(
    conn: duckdb.DuckDBPyConnection,
    outer_dict: OuterDict,
    sample_df: pd.DataFrame,
    resources: dict[str, RegisteredResource],
    *,
    author_details_path: str,
    authors_paper_path: str,
    hit_papers_level0_path: str,
    hit_papers_level1_path: str,
) -> None:
    if sample_df.empty:
        return

    # Pre-calculate match key in Python to save DB compute
    # Strip diacritics via simple string methods if simple, but DB unaccent is
    # better for robust logic.
    #
    # For reference:
    # unaccent(VARCHAR) → VARCHAR
    # Provides a more comprehensive transliteration of a string. It first strips
    # all diacritics and then converts other special characters and ligatures
    # (e.g., Æ → AE, ø → o, ß → ss) to their basic Latin equivalents.
    # https://github.com/moj-analytical-services/splink_udfs

    input_df = sample_df.copy()
    if "hcr.first_name" in input_df.columns and "hcr.last_name" in input_df.columns:
        first_col = "hcr.first_name"
        last_col = "hcr.last_name"
    elif KTP_FIRST_NAME_COL in input_df.columns and KTP_LAST_NAME_COL in input_df.columns:
        first_col = KTP_FIRST_NAME_COL
        last_col = KTP_LAST_NAME_COL
    else:
        raise ValueError("Sample data missing required name columns for parquet matching.")

    input_df["match_name"] = (
        input_df[first_col].astype(str) + " " + input_df[last_col].astype(str)
    )
    input_df["match_key_norm"] = input_df["match_name"].str.lower()

    # Out register_frame won't work because we don't need
    # a persistent table here, so we use conn directly below
    # register_frame(conn, "input_researchers", input_df)
    
    # 1) Register a temporary relation (view-like) backed by the dataframe
    conn.register("input_researchers_view", input_df)

    # 2) Materialize the persistent table with normalization
    conn.execute("""
        CREATE OR REPLACE TABLE input_researchers AS
        SELECT
            *,
            lower(unaccent(match_name)) AS match_key_norm
        FROM input_researchers_view
    """)

    # 3) Cleanup the registered view
    try:
        conn.unregister("input_researchers_view")
    except Exception:
        pass

    ### DEBUG ###
    # Run your query
    # res = pm.conn.execute(f"""
    #     SELECT
    #         authorid,
    #         display_name,
    #         display_name_alternatives,
    #         length(display_name_alternatives) AS len,
    #         unnest(CAST(json(display_name_alternatives) AS VARCHAR[])) AS alt_name
    #     FROM read_parquet('{FILES_CONFIG["author_details"]["path"]}')
    #     LIMIT 10;
    # """)

    # # Fetch all rows
    # rows = res.fetchall()

    # # Print them nicely
    # for row in rows:
    #     print(row)

    # exit(0)
    ### END DEBUG ###
    
    # Technique: We don't load the parquet. We query it directly.
    # We handle the "serialized list" by treating it as string manipulation 
    # because JSON parsing can be strict about quotes.
    # Assumption: serialized list looks like `["Name A", "Name B"]`

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE matched_authors_bridge AS
        WITH parq AS (
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
            i."{NAME_KEY_COL}" AS name_key,
            i.match_key_norm,
            p.authorid,
            p.display_name,
            p.display_name_alternatives
        FROM input_researchers i
        JOIN parq p ON lower(unaccent(p.alt_name)) = i.match_key_norm
        """
    )

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE author_papers AS
        SELECT
            b.name_key,
            b.match_key_norm,
            b.authorid,
            pap.paperid
        FROM matched_authors_bridge b
        JOIN read_parquet('{authors_paper_path}') pap
          ON b.authorid = pap.authorid
        """
    )

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW all_hits AS
        SELECT paperid, fieldid, hit_1pct, 'level0' AS level
        FROM read_parquet('{hit_papers_level0_path}')
        UNION ALL
        SELECT paperid, fieldid, hit_1pct, 'level1' AS level
        FROM read_parquet('{hit_papers_level1_path}')
        """
    )

    conn.execute(
        """
        CREATE OR REPLACE TABLE final_agg AS
        SELECT
            ap.name_key,
            ap.authorid,
            SUM(COALESCE(h.hit_1pct, 0)) AS sum_hit_1pct,
            LIST(ap.paperid) FILTER (WHERE h.level = 'level0') AS paperids_level0_list,
            LIST(ap.paperid) FILTER (WHERE h.level = 'level1') AS paperids_level1_list,
            LIST(DISTINCT h.fieldid) AS field_ids
        FROM author_papers ap
        LEFT JOIN all_hits h ON ap.paperid = h.paperid
        GROUP BY ap.name_key, ap.authorid
        """
    )

    author_details_name = Path(author_details_path).name
    matched = conn.execute(
        f"""
        SELECT
            b.name_key,
            b.authorid,
            b.display_name,
            b.display_name_alternatives,
            f.sum_hit_1pct,
            CAST(f.paperids_level0_list AS VARCHAR) AS paperids_level0,
            CAST(f.paperids_level1_list AS VARCHAR) AS paperids_level1,
            CAST(f.field_ids AS VARCHAR) AS field_ids_list,
            b.authorid AS "{AUTHOR_ID_FRAGMENT_COL}",
            ? AS "{KTP_FILENAME_COL}"
        FROM matched_authors_bridge b
        LEFT JOIN final_agg f ON f.authorid = b.authorid AND f.name_key = b.name_key
        """,
        [author_details_name],
    ).df()

    if matched.empty:
        return

    append_records(
        outer_dict,
        matched.to_dict("records"),
        ParquetMatchProcedure(),
        resources,
        name_key_field="name_key",
        fragment_field=AUTHOR_ID_FRAGMENT_COL,
    )
