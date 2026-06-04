from __future__ import annotations

from ..helpers.vars import (
    HCR_FIRST_NAME_COL,
    HCR_LAST_NAME_COL,
    HCR_XLSX_AFFILIATIONS_COLS,
    HCR_XLSX_NAME_COLS,
    KTP_HCR_FILENAME_COL,
    KTP_HCR_ROW_NUMBER_COL,
)


def hcr_excluded_columns(population_columns: list[str]) -> set[str]:
    excluded = {KTP_HCR_FILENAME_COL, KTP_HCR_ROW_NUMBER_COL, HCR_FIRST_NAME_COL, HCR_LAST_NAME_COL}
    for first_col, last_col in HCR_XLSX_NAME_COLS.values():
        excluded.add(first_col)
        excluded.add(last_col)
    for primary_cols, secondary_cols in HCR_XLSX_AFFILIATIONS_COLS.values():
        excluded.update(primary_cols)
        excluded.update(secondary_cols)
    excluded.update(
        col
        for col in population_columns
        if col.startswith("hcr.") and "affiliation" in col.lower()
    )
    return excluded


def draw_sort_ctes_sql(*, draw_col: str, source_key_col: str) -> str:
    return f"""
        row_ranked AS (
            SELECT
                b.*,
                CASE
                    WHEN starts_with(CAST(b."{draw_col}" AS VARCHAR), 'pilot.') THEN 0
                    WHEN TRY_CAST(b."{draw_col}" AS BIGINT) IS NOT NULL THEN 1
                    WHEN b."{draw_col}" IS NULL
                      OR trim(CAST(b."{draw_col}" AS VARCHAR)) = '' THEN 3
                    ELSE 2
                END AS row_draw_group,
                CASE
                    WHEN starts_with(CAST(b."{draw_col}" AS VARCHAR), 'pilot.')
                        THEN TRY_CAST(
                            split_part(CAST(b."{draw_col}" AS VARCHAR), '.', 2) AS BIGINT
                        )
                    WHEN TRY_CAST(b."{draw_col}" AS BIGINT) IS NOT NULL
                        THEN CAST(b."{draw_col}" AS BIGINT)
                    ELSE NULL
                END AS row_draw_num
            FROM base b
        ),
        ranked AS (
            SELECT
                rr.*,
                COALESCE(
                    MIN(CASE WHEN rr.row_draw_group < 3 THEN rr.row_draw_group ELSE NULL END)
                        OVER (PARTITION BY rr."{source_key_col}"),
                    3
                ) AS source_draw_group,
                MIN(CASE WHEN rr.row_draw_group < 3 THEN rr.row_draw_num ELSE NULL END)
                    OVER (PARTITION BY rr."{source_key_col}") AS source_draw_num
            FROM row_ranked rr
        )
    """


def draw_sort_order_by_sql(*, source_key_col: str, filename_col: str, fragment_col: str) -> str:
    return f"""
            source_draw_group,
            source_draw_num NULLS LAST,
            "{source_key_col}",
            row_draw_group,
            row_draw_num NULLS LAST,
            "{filename_col}",
            "{fragment_col}"
    """


__all__ = [
    "hcr_excluded_columns",
    "draw_sort_ctes_sql",
    "draw_sort_order_by_sql",
]
