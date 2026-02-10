from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.duckdb_utils import register_frame
from ..helpers.schema import (
    POPULATION_ECON_TABLE,
    POPULATION_NAMES_TABLE,
    POPULATION_TABLE,
    SAMPLES_TABLE,
    SAMPLES_VIEW,
    SAMPLES_WITH_NAMES_VIEW,
)
from ..helpers.vars import (
    DRAW_LABEL,
    HCR_CATEGORY_COL,
    HCR_FILENAME_COL,
    HCR_FIRST_NAME_COL,
    HCR_LAST_NAME_COL,
    HCR_ROW_COL,
    KTP_ECONOMIES_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_LAST_NAME_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    PILOT_NAME_CATEGORY_TRIPLES,
    STEP_SAMPLE_POPULATION,
)
from .shared import hcr_excluded_columns


def _append_samples(conn: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    if df.empty:
        return
    register_frame(conn, "samples_frame", df)
    result = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [SAMPLES_TABLE],
    ).fetchone()
    exists = result[0] if result else 0
    if exists:
        conn.execute(
            f"""
            INSERT INTO {SAMPLES_TABLE}
            SELECT "{KTP_FILENAME_COL}",
                   "{KTP_FRAGMENT_COL}",
                   CAST("{DRAW_LABEL}" AS VARCHAR) AS "{DRAW_LABEL}"
            FROM samples_frame
            """
        )
    else:
        conn.execute(
            f"""
            CREATE TABLE {SAMPLES_TABLE} AS
            SELECT "{KTP_FILENAME_COL}",
                   "{KTP_FRAGMENT_COL}",
                   CAST("{DRAW_LABEL}" AS VARCHAR) AS "{DRAW_LABEL}"
            FROM samples_frame
            """
        )
    conn.execute("DROP TABLE IF EXISTS samples_frame")


def run(context: PipelineContext) -> StepResult:
    conn: duckdb.DuckDBPyConnection = context.conn

    if sum(context.config.sample_draw_sizes) != 300:
        raise ValueError(
            "Sample draw sizes must total 300 before pilot samples. "
            f"Got {sum(context.config.sample_draw_sizes)} from {context.config.sample_draw_sizes}."
        )

    population_indices = conn.execute(
        f'SELECT "{KTP_POPULATION_INDEX_COL}" FROM {POPULATION_TABLE}'
    ).df()
    index_pool = population_indices[KTP_POPULATION_INDEX_COL].to_numpy()
    if len(index_pool) == 0:
        raise ValueError("Population table is empty; cannot sample.")

    rng = np.random.default_rng(context.config.sample_seed)
    draw_number = 1
    for draw_size in context.config.sample_draw_sizes:
        indices = rng.choice(index_pool, size=draw_size, replace=True)
        idx_df = pd.DataFrame(
            {
                "sample_id": np.arange(draw_size),
                KTP_POPULATION_INDEX_COL: indices,
            }
        )
        register_frame(conn, "sample_indices", idx_df)
        sample_df = conn.execute(
            f"""
            SELECT s.sample_id,
                   p."{HCR_FILENAME_COL}" AS "{KTP_FILENAME_COL}",
                   p."{HCR_ROW_COL}" AS "{KTP_FRAGMENT_COL}"
            FROM {POPULATION_TABLE} p
            JOIN sample_indices s
              ON p."{KTP_POPULATION_INDEX_COL}" = s."{KTP_POPULATION_INDEX_COL}"
            ORDER BY s.sample_id
            """
        ).df()
        sample_df = sample_df.sort_values("sample_id").drop(columns="sample_id")
        sample_df[DRAW_LABEL] = np.arange(draw_number, draw_number + draw_size)
        _append_samples(conn, sample_df[[KTP_FILENAME_COL, KTP_FRAGMENT_COL, DRAW_LABEL]])
        draw_number += draw_size

    triples_df = pd.DataFrame(
        PILOT_NAME_CATEGORY_TRIPLES,
        columns=[HCR_FIRST_NAME_COL, HCR_LAST_NAME_COL, HCR_CATEGORY_COL],
    )
    register_frame(conn, "pilot_triples", triples_df)
    pilot_df = conn.execute(
        f"""
        SELECT p."{HCR_FILENAME_COL}" AS "{KTP_FILENAME_COL}",
               p."{HCR_ROW_COL}" AS "{KTP_FRAGMENT_COL}",
               p."{HCR_FIRST_NAME_COL}",
               p."{HCR_LAST_NAME_COL}",
               p."{HCR_CATEGORY_COL}"
        FROM {POPULATION_TABLE} p
        JOIN pilot_triples t
          ON p."{HCR_FIRST_NAME_COL}" = t."{HCR_FIRST_NAME_COL}"
         AND p."{HCR_LAST_NAME_COL}" = t."{HCR_LAST_NAME_COL}"
         AND p."{HCR_CATEGORY_COL}" = t."{HCR_CATEGORY_COL}"
        WHERE p."{HCR_FILENAME_COL}" = ?
        """,
        [context.config.pilot_xlsx_name],
    ).df()
    if not pilot_df.empty:
        order_map = {pair: i for i, pair in enumerate(PILOT_NAME_CATEGORY_TRIPLES)}
        pilot_df["__order"] = pilot_df[
            [HCR_FIRST_NAME_COL, HCR_LAST_NAME_COL, HCR_CATEGORY_COL]
        ].apply(tuple, axis=1).map(order_map)
        pilot_df = pilot_df.sort_values("__order").drop(columns="__order")
        pilot_df[DRAW_LABEL] = "pilot." + (
            pilot_df.reset_index(drop=True).index + 1
        ).astype(str)
        _append_samples(conn, pilot_df[[KTP_FILENAME_COL, KTP_FRAGMENT_COL, DRAW_LABEL]])

    p_columns = [row[0] for row in conn.execute(f"DESCRIBE {POPULATION_TABLE}").fetchall()]
    excluded_p_cols = hcr_excluded_columns(p_columns) | {
        HCR_FILENAME_COL,
        HCR_ROW_COL,
        KTP_POPULATION_INDEX_COL,
    }
    p_extra_cols = [col for col in p_columns if col not in excluded_p_cols]
    p_extra_select = ", ".join([f'p."{col}"' for col in p_extra_cols])

    select_parts = [
        f'p."{KTP_POPULATION_INDEX_COL}" AS "{KTP_POPULATION_INDEX_COL}"',
        f's."{KTP_FILENAME_COL}" AS "{KTP_FILENAME_COL}"',
        f's."{KTP_FRAGMENT_COL}" AS "{KTP_FRAGMENT_COL}"',
        f's."{DRAW_LABEL}" AS "{DRAW_LABEL}"',
        f'n."{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}"',
        f'n."{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}"',
        p_extra_select,
        f'e."{KTP_HCR_PRIMARY_AFFILIATIONS_COL}" AS "{KTP_HCR_PRIMARY_AFFILIATIONS_COL}"',
        f'e."{KTP_HCR_SECONDARY_AFFILIATIONS_COL}" AS "{KTP_HCR_SECONDARY_AFFILIATIONS_COL}"',
        f'e."{KTP_ECONOMIES_COL}" AS "{KTP_ECONOMIES_COL}"',
        f'e."{KTP_ECONOMIES_INCOME_GROUP_COL}" AS "{KTP_ECONOMIES_INCOME_GROUP_COL}"',
        f'e."{KTP_PRIORITY_COL}" AS "{KTP_PRIORITY_COL}"',
        f'e."{KTP_PRIORITY_GROUP_COL}" AS "{KTP_PRIORITY_GROUP_COL}"',
    ]
    select_expr = ", ".join(part for part in select_parts if part)

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {SAMPLES_VIEW} AS
        SELECT {select_expr}
        FROM {SAMPLES_TABLE} s
        JOIN {POPULATION_TABLE} p
          ON s."{KTP_FILENAME_COL}" = p."{HCR_FILENAME_COL}"
         AND s."{KTP_FRAGMENT_COL}" = p."{HCR_ROW_COL}"
        JOIN {POPULATION_NAMES_TABLE} n
          ON p."{KTP_POPULATION_INDEX_COL}" = n."{KTP_POPULATION_INDEX_COL}"
        JOIN {POPULATION_ECON_TABLE} e
          ON p."{KTP_POPULATION_INDEX_COL}" = e."{KTP_POPULATION_INDEX_COL}"
        ORDER BY
            CASE
                WHEN starts_with(s."{DRAW_LABEL}", 'pilot.') THEN 0
                WHEN TRY_CAST(s."{DRAW_LABEL}" AS BIGINT) IS NOT NULL THEN 1
                ELSE 2
            END,
            CASE
                WHEN starts_with(s."{DRAW_LABEL}", 'pilot.')
                    THEN TRY_CAST(split_part(s."{DRAW_LABEL}", '.', 2) AS BIGINT)
                WHEN TRY_CAST(s."{DRAW_LABEL}" AS BIGINT) IS NOT NULL
                    THEN CAST(s."{DRAW_LABEL}" AS BIGINT)
                ELSE NULL
            END,
            s."{DRAW_LABEL}"
        """
    )

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {SAMPLES_WITH_NAMES_VIEW} AS
        SELECT s."{KTP_FILENAME_COL}", s."{KTP_FRAGMENT_COL}", s."{DRAW_LABEL}",
               n."{KTP_FIRST_NAME_COL}", n."{KTP_LAST_NAME_COL}"
        FROM {SAMPLES_TABLE} s
        JOIN {POPULATION_TABLE} p
          ON s."{KTP_FILENAME_COL}" = p."{HCR_FILENAME_COL}"
         AND s."{KTP_FRAGMENT_COL}" = p."{HCR_ROW_COL}"
        JOIN {POPULATION_NAMES_TABLE} n
          ON p."{KTP_POPULATION_INDEX_COL}" = n."{KTP_POPULATION_INDEX_COL}"
        """
    )

    conn.execute("DROP TABLE IF EXISTS sample_indices")
    conn.execute("DROP TABLE IF EXISTS pilot_triples")

    joined_df = conn.execute(f"SELECT * FROM {SAMPLES_VIEW}").df()

    return StepResult(
        step_id=STEP_SAMPLE_POPULATION,
        artifacts={"samples_with_context_df": joined_df},
        messages=[f"Sample rows: {len(joined_df)}"],
        diagnostics=[
            f"Draw sizes: {context.config.sample_draw_sizes}",
            f"Seed: {context.config.sample_seed}",
            f"Sample rows: {len(joined_df)}",
        ],
    )
