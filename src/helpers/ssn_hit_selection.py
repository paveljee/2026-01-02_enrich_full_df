from __future__ import annotations

from .duckdb_utils import duckdb_string_literal
from .schema import (
    PARQUET_AUTHOR_HIT_AGG_TABLE,
    PARQUET_AUTHOR_MATCH_HIT_CANDIDATE_TABLE,
    PARQUET_AUTHOR_MATCH_HIT_SELECTED_AUTHOR_IDS_VIEW,
    PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
    PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW,
    PARQUET_AUTHOR_MATCH_TABLE,
)
from .vars import (
    KTP_SSN_HIT_CITED_BY_COUNT_IS_TUKEY_OUTLIER_COL,
    KTP_SSN_HIT_FALLBACK_NO_TUKEY_OUTLIER_COL,
    KTP_SSN_HIT_ROW_HAS_TUKEY_OUTLIER_COL,
    KTP_SSN_HIT_RULE_KEY,
    KTP_SSN_HIT_RULE_V2,
    KTP_SSN_HIT_SUM_HIT_1PCT_IS_TUKEY_OUTLIER_COL,
    KTP_SSN_HIT_WORKS_COUNT_IS_TUKEY_OUTLIER_COL,
    KTP_SSN_HIT_WORKS_COUNT_RAW_COL,
    KTP_SSN_SUM_HIT_1PCT_COL,
    SSNAD_RAW_AUTHORID_COL,
    SSNAD_RAW_CITED_BY_COUNT_COL,
    SSNAD_RAW_WORKS_COUNT_COL,
)


def _qualified_col(table_alias: str, col: str) -> str:
    return f'{table_alias}."{col}"' if table_alias else f'"{col}"'


def ssn_removed_zero_hit_count_sql(*, author_id_col: str) -> str:
    return f"""
        SELECT COUNT(*)
        FROM {PARQUET_AUTHOR_MATCH_TABLE} m
        LEFT JOIN {PARQUET_AUTHOR_HIT_AGG_TABLE} agg
          ON agg.authorid = m."{author_id_col}"
         AND agg.name_key = m.name_key
        WHERE agg."{KTP_SSN_SUM_HIT_1PCT_COL}" = 0
    """


def ssn_nonzero_hit_view_sql(*, author_id_col: str) -> str:
    return f"""
        CREATE OR REPLACE VIEW {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} AS
        SELECT m.*
        FROM {PARQUET_AUTHOR_MATCH_TABLE} m
        LEFT JOIN {PARQUET_AUTHOR_HIT_AGG_TABLE} agg
          ON agg.authorid = m."{author_id_col}"
         AND agg.name_key = m.name_key
        WHERE agg."{KTP_SSN_SUM_HIT_1PCT_COL}" IS NULL
           OR agg."{KTP_SSN_SUM_HIT_1PCT_COL}" <> 0
    """


def ssn_hit_selected_author_ids_view_sql(*, author_id_col: str) -> str:
    return f"""
        CREATE OR REPLACE VIEW {PARQUET_AUTHOR_MATCH_HIT_SELECTED_AUTHOR_IDS_VIEW} AS
        SELECT DISTINCT
            m."{author_id_col}" AS "{author_id_col}"
        FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} m
    """


def ssn_hit_metadata_select_sql(*, hit_rule_version: int, table_alias: str = "m") -> str:
    if hit_rule_version == 1:
        return ""
    if hit_rule_version != 2:
        raise ValueError(f"Unsupported SSN hit rule version: {hit_rule_version}")

    return f""",
            {_qualified_col(table_alias, KTP_SSN_HIT_RULE_KEY)} AS "{KTP_SSN_HIT_RULE_KEY}",
            {_qualified_col(table_alias, KTP_SSN_HIT_SUM_HIT_1PCT_IS_TUKEY_OUTLIER_COL)}
                AS "{KTP_SSN_HIT_SUM_HIT_1PCT_IS_TUKEY_OUTLIER_COL}",
            {_qualified_col(table_alias, KTP_SSN_HIT_WORKS_COUNT_IS_TUKEY_OUTLIER_COL)}
                AS "{KTP_SSN_HIT_WORKS_COUNT_IS_TUKEY_OUTLIER_COL}",
            {_qualified_col(table_alias, KTP_SSN_HIT_CITED_BY_COUNT_IS_TUKEY_OUTLIER_COL)}
                AS "{KTP_SSN_HIT_CITED_BY_COUNT_IS_TUKEY_OUTLIER_COL}",
            {_qualified_col(table_alias, KTP_SSN_HIT_ROW_HAS_TUKEY_OUTLIER_COL)}
                AS "{KTP_SSN_HIT_ROW_HAS_TUKEY_OUTLIER_COL}",
            {_qualified_col(table_alias, KTP_SSN_HIT_WORKS_COUNT_RAW_COL)}
                AS "{KTP_SSN_HIT_WORKS_COUNT_RAW_COL}",
            {_qualified_col(table_alias, KTP_SSN_HIT_FALLBACK_NO_TUKEY_OUTLIER_COL)}
                AS "{KTP_SSN_HIT_FALLBACK_NO_TUKEY_OUTLIER_COL}"
        """


def ssn_hit_v2_candidate_metrics_table_sql(
    *,
    author_details_path: str,
    author_id_col: str,
) -> str:
    author_details_literal = duckdb_string_literal(author_details_path)
    return f"""
        CREATE OR REPLACE TABLE {PARQUET_AUTHOR_MATCH_HIT_CANDIDATE_TABLE} AS
        WITH candidate_metrics AS (
            SELECT
                m.*,
                TRY_CAST(agg."{KTP_SSN_SUM_HIT_1PCT_COL}" AS DOUBLE)
                    AS ssn_hit_sum_hit_1pct_metric,
                ad."{SSNAD_RAW_WORKS_COUNT_COL}" AS ssn_hit_works_count_raw,
                TRY_CAST(ad."{SSNAD_RAW_WORKS_COUNT_COL}" AS DOUBLE)
                    AS ssn_hit_works_count_metric,
                TRY_CAST(ad."{SSNAD_RAW_CITED_BY_COUNT_COL}" AS DOUBLE)
                    AS ssn_hit_cited_by_count_metric
            FROM {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} m
            LEFT JOIN {PARQUET_AUTHOR_HIT_AGG_TABLE} agg
              ON agg.authorid = m."{author_id_col}"
             AND agg.name_key = m.name_key
            LEFT JOIN (
                SELECT
                    "{SSNAD_RAW_AUTHORID_COL}",
                    "{SSNAD_RAW_WORKS_COUNT_COL}",
                    "{SSNAD_RAW_CITED_BY_COUNT_COL}"
                FROM read_parquet({author_details_literal})
            ) ad
              ON CAST(ad."{SSNAD_RAW_AUTHORID_COL}" AS VARCHAR)
               = CAST(m."{author_id_col}" AS VARCHAR)
        ),
        bounds_raw AS (
            SELECT
                quantile_cont(ssn_hit_sum_hit_1pct_metric, 0.25) AS ssn_q1,
                quantile_cont(ssn_hit_sum_hit_1pct_metric, 0.75) AS ssn_q3,
                quantile_cont(ssn_hit_works_count_metric, 0.25) AS works_q1,
                quantile_cont(ssn_hit_works_count_metric, 0.75) AS works_q3,
                quantile_cont(ssn_hit_cited_by_count_metric, 0.25) AS cited_q1,
                quantile_cont(ssn_hit_cited_by_count_metric, 0.75) AS cited_q3
            FROM candidate_metrics
        ),
        bounds AS (
            SELECT
                ssn_q1,
                ssn_q3,
                ssn_q1 - 1.5 * (ssn_q3 - ssn_q1) AS ssn_lower,
                ssn_q3 + 1.5 * (ssn_q3 - ssn_q1) AS ssn_upper,
                works_q1,
                works_q3,
                works_q1 - 1.5 * (works_q3 - works_q1) AS works_lower,
                works_q3 + 1.5 * (works_q3 - works_q1) AS works_upper,
                cited_q1,
                cited_q3,
                cited_q1 - 1.5 * (cited_q3 - cited_q1) AS cited_lower,
                cited_q3 + 1.5 * (cited_q3 - cited_q1) AS cited_upper
            FROM bounds_raw
        ),
        flagged_metrics AS (
            SELECT
                c.*,
                b.*,
                COALESCE(
                    c.ssn_hit_sum_hit_1pct_metric < b.ssn_lower
                    OR c.ssn_hit_sum_hit_1pct_metric > b.ssn_upper,
                    false
                ) AS ssn_hit_sum_hit_1pct_is_tukey_outlier,
                COALESCE(
                    c.ssn_hit_works_count_metric < b.works_lower
                    OR c.ssn_hit_works_count_metric > b.works_upper,
                    false
                ) AS ssn_hit_works_count_is_tukey_outlier,
                COALESCE(
                    c.ssn_hit_cited_by_count_metric < b.cited_lower
                    OR c.ssn_hit_cited_by_count_metric > b.cited_upper,
                    false
                ) AS ssn_hit_cited_by_count_is_tukey_outlier
            FROM candidate_metrics c
            CROSS JOIN bounds b
        ),
        flagged AS (
            SELECT
                f.*,
                (
                    f.ssn_hit_sum_hit_1pct_is_tukey_outlier
                    OR f.ssn_hit_works_count_is_tukey_outlier
                    OR f.ssn_hit_cited_by_count_is_tukey_outlier
                ) AS ssn_hit_row_has_tukey_outlier
            FROM flagged_metrics f
        )
        SELECT
            f.*,
            MAX(CASE WHEN f.ssn_hit_row_has_tukey_outlier THEN 1 ELSE 0 END)
                OVER (PARTITION BY f.name_key) = 1 AS ssn_hit_name_key_has_tukey_outlier
        FROM flagged f
    """


def ssn_hit_v2_bounds_summary_sql() -> str:
    return f"""
        SELECT
            MAX(ssn_q1) AS ssn_q1,
            MAX(ssn_q3) AS ssn_q3,
            MAX(ssn_lower) AS ssn_lower,
            MAX(ssn_upper) AS ssn_upper,
            MAX(works_q1) AS works_q1,
            MAX(works_q3) AS works_q3,
            MAX(works_lower) AS works_lower,
            MAX(works_upper) AS works_upper,
            MAX(cited_q1) AS cited_q1,
            MAX(cited_q3) AS cited_q3,
            MAX(cited_lower) AS cited_lower,
            MAX(cited_upper) AS cited_upper
        FROM {PARQUET_AUTHOR_MATCH_HIT_CANDIDATE_TABLE}
    """


def ssn_hit_v2_selection_breakdown_sql(*, author_id_col: str) -> str:
    return f"""
        WITH selected AS (
            SELECT
                name_key,
                "{author_id_col}" AS selected_author_id
            FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW}
        ),
        selected_counts AS (
            SELECT
                name_key,
                COUNT(*) AS selected_rows
            FROM selected
            GROUP BY name_key
        ),
        candidate_with_selection AS (
            SELECT
                c.*,
                s.selected_author_id IS NOT NULL AS is_selected
            FROM {PARQUET_AUTHOR_MATCH_HIT_CANDIDATE_TABLE} c
            LEFT JOIN selected s
              ON s.name_key = c.name_key
             AND CAST(s.selected_author_id AS VARCHAR) = CAST(c."{author_id_col}" AS VARCHAR)
        )
        SELECT
            COUNT(*) AS candidate_rows,
            COUNT(DISTINCT name_key) AS candidate_name_keys,
            COUNT(DISTINCT "{author_id_col}") AS candidate_authors,
            COUNT(*) FILTER (WHERE ssn_hit_sum_hit_1pct_is_tukey_outlier)
                AS sum_hit_outlier_rows,
            COUNT(*) FILTER (WHERE ssn_hit_works_count_is_tukey_outlier)
                AS works_count_outlier_rows,
            COUNT(*) FILTER (WHERE ssn_hit_cited_by_count_is_tukey_outlier)
                AS cited_by_count_outlier_rows,
            COUNT(*) FILTER (WHERE ssn_hit_row_has_tukey_outlier)
                AS any_tukey_outlier_rows,
            COUNT(DISTINCT name_key) FILTER (WHERE ssn_hit_name_key_has_tukey_outlier)
                AS name_keys_with_tukey_outlier,
            COUNT(DISTINCT name_key) FILTER (WHERE NOT ssn_hit_name_key_has_tukey_outlier)
                AS fallback_no_outlier_name_keys,
            COUNT(*) FILTER (WHERE is_selected) AS selected_rows,
            COUNT(DISTINCT name_key) FILTER (WHERE is_selected) AS selected_name_keys,
            COUNT(DISTINCT "{author_id_col}") FILTER (WHERE is_selected) AS selected_authors,
            COUNT(*) FILTER (WHERE is_selected AND ssn_hit_name_key_has_tukey_outlier)
                AS selected_tukey_max_work_rows,
            COUNT(*) FILTER (WHERE is_selected AND NOT ssn_hit_name_key_has_tukey_outlier)
                AS selected_fallback_rows,
            COUNT(*) FILTER (
                WHERE NOT is_selected
                  AND ssn_hit_name_key_has_tukey_outlier
                  AND NOT ssn_hit_row_has_tukey_outlier
            ) AS pruned_non_outlier_rows,
            COUNT(*) FILTER (
                WHERE NOT is_selected
                  AND ssn_hit_name_key_has_tukey_outlier
                  AND ssn_hit_row_has_tukey_outlier
            ) AS pruned_outlier_nonmax_rows,
            COALESCE((
                SELECT COUNT(*)
                FROM selected_counts
                WHERE selected_rows = 1
            ), 0) AS one_selected_row_name_keys,
            COALESCE((
                SELECT COUNT(*)
                FROM selected_counts
                WHERE selected_rows > 1
            ), 0) AS multi_selected_row_name_keys,
            COALESCE((
                SELECT MAX(selected_rows)
                FROM selected_counts
            ), 0) AS max_selected_rows_per_name_key
        FROM candidate_with_selection
    """


def ssn_hit_selected_view_sql(
    *,
    author_id_col: str,
    hit_rule_version: int,
) -> str:
    if hit_rule_version == 1:
        return f"""
            CREATE OR REPLACE VIEW {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} AS
            SELECT m.*
            FROM {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} m
        """

    if hit_rule_version != 2:
        raise ValueError(f"Unsupported SSN hit rule version: {hit_rule_version}")

    return f"""
        CREATE OR REPLACE VIEW {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} AS
        WITH
        outlier_max_works AS (
            SELECT
                name_key,
                MAX(ssn_hit_works_count_metric) AS max_works_count
            FROM {PARQUET_AUTHOR_MATCH_HIT_CANDIDATE_TABLE}
            WHERE ssn_hit_row_has_tukey_outlier
            GROUP BY name_key
        )
        SELECT
            w.* EXCLUDE (
                ssn_hit_sum_hit_1pct_metric,
                ssn_hit_works_count_raw,
                ssn_hit_works_count_metric,
                ssn_hit_cited_by_count_metric,
                ssn_q1,
                ssn_q3,
                ssn_lower,
                ssn_upper,
                works_q1,
                works_q3,
                works_lower,
                works_upper,
                cited_q1,
                cited_q3,
                cited_lower,
                cited_upper,
                ssn_hit_sum_hit_1pct_is_tukey_outlier,
                ssn_hit_works_count_is_tukey_outlier,
                ssn_hit_cited_by_count_is_tukey_outlier,
                ssn_hit_row_has_tukey_outlier,
                ssn_hit_name_key_has_tukey_outlier
            ),
            '{KTP_SSN_HIT_RULE_V2}' AS "{KTP_SSN_HIT_RULE_KEY}",
            w.ssn_hit_sum_hit_1pct_is_tukey_outlier
                AS "{KTP_SSN_HIT_SUM_HIT_1PCT_IS_TUKEY_OUTLIER_COL}",
            w.ssn_hit_works_count_is_tukey_outlier
                AS "{KTP_SSN_HIT_WORKS_COUNT_IS_TUKEY_OUTLIER_COL}",
            w.ssn_hit_cited_by_count_is_tukey_outlier
                AS "{KTP_SSN_HIT_CITED_BY_COUNT_IS_TUKEY_OUTLIER_COL}",
            w.ssn_hit_row_has_tukey_outlier
                AS "{KTP_SSN_HIT_ROW_HAS_TUKEY_OUTLIER_COL}",
            w.ssn_hit_works_count_raw AS "{KTP_SSN_HIT_WORKS_COUNT_RAW_COL}",
            NOT w.ssn_hit_name_key_has_tukey_outlier
                AS "{KTP_SSN_HIT_FALLBACK_NO_TUKEY_OUTLIER_COL}"
        FROM {PARQUET_AUTHOR_MATCH_HIT_CANDIDATE_TABLE} w
        LEFT JOIN outlier_max_works o
          ON o.name_key = w.name_key
        WHERE (
            w.ssn_hit_name_key_has_tukey_outlier
            AND w.ssn_hit_row_has_tukey_outlier
            AND w.ssn_hit_works_count_metric IS NOT DISTINCT FROM o.max_works_count
        )
        OR NOT w.ssn_hit_name_key_has_tukey_outlier
    """
