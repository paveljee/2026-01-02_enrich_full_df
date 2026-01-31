from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from src._vars import HCR_FIRST_NAME_COL, HCR_LAST_NAME_COL, SOURCE_KEY_COL
from src.data_models import (
    InnerDict,
    MatchingProcedure,
    NameKey,
    OuterDict,
    RegisteredResource,
    SourceKey,
)


class ParquetDuckdbMatchProcedure:
    dataset_id_field = SOURCE_KEY_COL


def append_parquet_matches(
    outer_dict: OuterDict,
    sample_df: pd.DataFrame,
    *,
    conn: duckdb.DuckDBPyConnection,
    resources: dict[str, RegisteredResource],
) -> None:
    if sample_df.empty:
        return

    input_df = sample_df.copy()
    input_df["match_name"] = (
        input_df[HCR_FIRST_NAME_COL] + " " + input_df[HCR_LAST_NAME_COL]
    ).astype(str)
    input_df["name_key"] = [
        NameKey(first_name=row[HCR_FIRST_NAME_COL], last_name=row[HCR_LAST_NAME_COL]).to_json_key()
        for row in input_df.to_dict("records")
    ]

    conn.register("input_df", input_df)
    conn.execute(
        """
        CREATE OR REPLACE TABLE input_researchers AS
        SELECT
            *,
            lower(unaccent(match_name)) as match_key_norm
        FROM input_df
        """
    )

    author_details = Path(resources["author_details"])
    authors_paper = Path(resources["authors_paper"])
    hit_papers_0 = Path(resources["hit_papers_0"])
    hit_papers_1 = Path(resources["hit_papers_1"])

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE matched_authors_bridge AS
        WITH parq AS (
            SELECT
                authorid,
                display_name,
                display_name_alternatives,
                unnest(CAST(json(display_name_alternatives) AS VARCHAR[])) AS alt_name
            FROM read_parquet('{author_details.as_posix()}')

            UNION ALL

            SELECT
                authorid,
                display_name,
                display_name_alternatives,
                display_name as alt_name
            FROM read_parquet('{author_details.as_posix()}')
        )
        SELECT DISTINCT
            i.name_key,
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
        JOIN read_parquet('{authors_paper.as_posix()}') pap
          ON b.authorid = pap.authorid
        """
    )

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW all_hits AS
        SELECT paperid, fieldid, hit_1pct, 'level0' as level
        FROM read_parquet('{hit_papers_0.as_posix()}')
        UNION ALL
        SELECT paperid, fieldid, hit_1pct, 'level1' as level
        FROM read_parquet('{hit_papers_1.as_posix()}')
        """
    )

    conn.execute(
        """
        CREATE OR REPLACE TABLE final_agg AS
        SELECT
            ap.name_key,
            ap.match_key_norm,
            ap.authorid,
            SUM(COALESCE(h.hit_1pct, 0)) as sum_hit_1pct,
            list(ap.paperid) FILTER (WHERE h.level = 'level0') as paperids_level0_list,
            list(ap.paperid) FILTER (WHERE h.level = 'level1') as paperids_level1_list,
            LIST(DISTINCT h.fieldid) as field_ids
        FROM author_papers ap
        LEFT JOIN all_hits h ON ap.paperid = h.paperid
        GROUP BY ap.name_key, ap.match_key_norm, ap.authorid
        """
    )

    final_df = conn.execute(
        """
        SELECT
            b.name_key,
            b.authorid,
            b.display_name,
            b.display_name_alternatives,
            f.sum_hit_1pct,
            CAST(f.paperids_level0_list AS VARCHAR) as paperids_level0,
            CAST(f.paperids_level1_list AS VARCHAR) as paperids_level1,
            CAST(f.field_ids AS VARCHAR) as field_ids_list
        FROM matched_authors_bridge b
        LEFT JOIN final_agg f
          ON f.authorid = b.authorid
         AND f.name_key = b.name_key
        """
    ).df()

    procedure: MatchingProcedure = ParquetDuckdbMatchProcedure()
    author_resource = resources["author_details"]
    for record in final_df.to_dict("records"):
        name_key = record.pop("name_key")
        fragment = record.get("authorid")
        record[SOURCE_KEY_COL] = SourceKey(
            resource=author_resource,
            fragment=str(fragment),
        ).to_string_key()
        inner = InnerDict.from_mapping(record, procedure)
        outer_dict.add_inner_by_key(name_key, inner)
