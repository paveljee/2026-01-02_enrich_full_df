from __future__ import annotations

from dataclasses import dataclass

import duckdb

from .._vars import SOURCE_KEY_COL
from ..data_models import FragmentType, InnerDict, OuterDict, RegisteredResource, SourceKey
from .utils import NAME_KEY_COL, build_name_key_frame


@dataclass(frozen=True)
class ParquetPaths:
    author_details: str
    authors_paper: str
    hit_papers_0: str
    hit_papers_1: str


class ParquetMatchProcedure:
    dataset_id_field = SOURCE_KEY_COL


class ParquetMatcher:
    def __init__(
        self,
        outer_dict: OuterDict,
        author_resource: RegisteredResource,
        paths: ParquetPaths,
    ) -> None:
        self.outer_dict = outer_dict
        self.author_resource = author_resource
        self.paths = paths
        self.procedure = ParquetMatchProcedure()
        self._inner_lists = {
            key: outer_dict.ensure_inner_list_by_key(key)
            for key in outer_dict.data
        }

    def match(self) -> None:
        if self.author_resource.fragment_type != FragmentType.AUTHOR_ID:
            raise ValueError("Author details resource must use AUTHOR_ID fragment type")
        name_keys = build_name_key_frame(self.outer_dict)
        if name_keys.empty:
            return

        name_keys["match_name"] = (
            name_keys["ktp.first_name"].astype(str) + " " + name_keys["ktp.last_name"].astype(str)
        )

        conn = duckdb.connect()
        conn.execute("INSTALL splink_udfs FROM community; LOAD splink_udfs;")
        conn.register("name_keys", name_keys)
        conn.execute(
            """
            CREATE OR REPLACE TABLE input_researchers AS
            SELECT *, lower(unaccent(match_name)) AS match_key_norm
            FROM name_keys
            """
        )

        matched_query = f"""
            CREATE OR REPLACE TABLE matched_authors_bridge AS
            WITH parq AS (
                SELECT
                    authorid,
                    display_name,
                    display_name_alternatives,
                    unnest(CAST(json(display_name_alternatives) AS VARCHAR[])) AS alt_name
                FROM read_parquet('{self.paths.author_details}')

                UNION ALL

                SELECT
                    authorid,
                    display_name,
                    display_name_alternatives,
                    display_name as alt_name
                FROM read_parquet('{self.paths.author_details}')
            )
            SELECT DISTINCT
                i.{NAME_KEY_COL} AS name_key,
                i.match_key_norm,
                p.authorid,
                p.display_name,
                p.display_name_alternatives
            FROM input_researchers i
            JOIN parq p ON lower(unaccent(p.alt_name)) = i.match_key_norm
        """
        conn.execute(matched_query)

        conn.execute(
            f"""
            CREATE OR REPLACE TABLE author_papers AS
            SELECT
                b.name_key,
                b.authorid,
                pap.paperid
            FROM matched_authors_bridge b
            JOIN read_parquet('{self.paths.authors_paper}') pap
            ON b.authorid = pap.authorid
            """
        )

        conn.execute(
            f"""
            CREATE OR REPLACE VIEW all_hits AS
            SELECT paperid, fieldid, hit_1pct, 'level0' as level
            FROM read_parquet('{self.paths.hit_papers_0}')
            UNION ALL
            SELECT paperid, fieldid, hit_1pct, 'level1' as level
            FROM read_parquet('{self.paths.hit_papers_1}')
            """
        )

        conn.execute(
            """
            CREATE OR REPLACE TABLE final_agg AS
            SELECT
                ap.name_key,
                ap.authorid,
                SUM(COALESCE(h.hit_1pct, 0)) as sum_hit_1pct,
                list(ap.paperid) FILTER (WHERE h.level = 'level0') as paperids_level0_list,
                list(ap.paperid) FILTER (WHERE h.level = 'level1') as paperids_level1_list,
                LIST(DISTINCT h.fieldid) as field_ids
            FROM author_papers ap
            LEFT JOIN all_hits h ON ap.paperid = h.paperid
            GROUP BY ap.name_key, ap.authorid
            """
        )

        final_df = conn.execute(
            """
            SELECT
                mb.name_key,
                mb.authorid,
                mb.display_name,
                mb.display_name_alternatives,
                f.sum_hit_1pct,
                CAST(f.paperids_level0_list AS VARCHAR) as paperids_level0,
                CAST(f.paperids_level1_list AS VARCHAR) as paperids_level1,
                CAST(f.field_ids AS VARCHAR) as field_ids_list
            FROM matched_authors_bridge mb
            LEFT JOIN final_agg f ON (f.authorid = mb.authorid)
            """
        ).df()
        conn.close()

        for record in final_df.to_dict("records"):
            name_key = record.pop("name_key")
            fragment = record.get("authorid")
            if fragment is None:
                raise ValueError("Parquet record missing authorid fragment")
            record[SOURCE_KEY_COL] = SourceKey(
                resource=self.author_resource,
                fragment=str(fragment),
            ).to_string_key()
            inner = InnerDict.from_mapping(record, self.procedure)
            self._inner_lists[name_key].append(inner)
