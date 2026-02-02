from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from .._vars import (
    DRAW_LABEL,
    HCR_FILENAME_COL,
    KTP_FILENAME_COL,
    KTP_POPULATION_INDEX_COL,
    PILOT_NAME_CATEGORY_TRIPLES,
)
from ..utils.duckdb import register_frame
from .preprocessor import preprocess_samples


def _append_samples_table(
    conn: duckdb.DuckDBPyConnection,
    samples_table: str,
    df: pd.DataFrame,
) -> None:
    for col in df.columns:
        if col == KTP_POPULATION_INDEX_COL:
            continue
        df[col] = df[col].astype("string")

    result = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [samples_table],
    ).fetchone()
    exists = result[0] if result else 0
    if exists:
        table_info = conn.execute(f"PRAGMA table_info('{samples_table}')").fetchall()
        table_cols = [row[1] for row in table_info]
        table_col_set = set(table_cols)
        df_col_set = set(df.columns)

        new_cols = df_col_set - table_col_set
        for col in sorted(new_cols):
            conn.execute(f'ALTER TABLE {samples_table} ADD COLUMN "{col}" VARCHAR')

        missing_cols = table_col_set - df_col_set
        for col in missing_cols:
            df[col] = pd.NA

        table_info = conn.execute(f"PRAGMA table_info('{samples_table}')").fetchall()
        table_cols = [row[1] for row in table_info]
        df = df[table_cols]

        register_frame(conn, "sample_frame", df)
        conn.execute(f"INSERT INTO {samples_table} SELECT * FROM sample_frame")
    else:
        register_frame(conn, samples_table, df)


def sample_population(
    conn: duckdb.DuckDBPyConnection,
    *,
    population_table: str,
    samples_table: str,
    draw_sizes: list[int],
    seed: int,
    economies: list[str],
) -> None:
    result = conn.execute(f"SELECT COUNT(*) FROM {population_table}").fetchone()
    count = result[0] if result else 0
    population_indices = conn.execute(
        f'SELECT "{KTP_POPULATION_INDEX_COL}" FROM {population_table}'
    ).df()
    index_pool = population_indices[KTP_POPULATION_INDEX_COL].to_numpy()
    rng = np.random.default_rng(seed)
    draw_number = 1
    for draw_size in draw_sizes:
        if count == 0 or len(index_pool) == 0:
            raise ValueError("Population table is empty; cannot sample.")
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
            SELECT s.sample_id, p.*
            FROM {population_table} p
            JOIN sample_indices s
              ON p."{KTP_POPULATION_INDEX_COL}" = s."{KTP_POPULATION_INDEX_COL}"
            """
        ).df()
        sample_df = sample_df.sort_values("sample_id").reset_index(drop=True)
        sample_df[DRAW_LABEL] = np.arange(draw_number, draw_number + draw_size)
        sample_df[KTP_FILENAME_COL] = sample_df[HCR_FILENAME_COL]
        sample_df = preprocess_samples(sample_df, economies=economies)
        sample_df = sample_df.drop(columns=["sample_id"])
        _append_samples_table(conn, samples_table, sample_df)
        draw_number += draw_size


def sample_pilot(
    conn: duckdb.DuckDBPyConnection,
    *,
    population_table: str,
    samples_table: str,
    pilot_filename: str,
    economies: list[str],
    name_category_triples: list[tuple[str, str, str]] | None = None,
) -> None:
    name_category_triples = name_category_triples or PILOT_NAME_CATEGORY_TRIPLES
    triples_df = pd.DataFrame(
        name_category_triples,
        columns=["hcr.first_name", "hcr.last_name", "hcr.category"],
    )
    register_frame(conn, "pilot_triples", triples_df)
    sample_df = conn.execute(
        f"""
        SELECT p.*
        FROM {population_table} p
        JOIN pilot_triples t
          ON p."hcr.first_name" = t."hcr.first_name"
         AND p."hcr.last_name" = t."hcr.last_name"
         AND p."hcr.category" = t."hcr.category"
        WHERE p."{HCR_FILENAME_COL}" = ?
        """,
        [pilot_filename],
    ).df()
    if sample_df.empty:
        return
    order_map = {pair: i for i, pair in enumerate(name_category_triples)}
    sample_df["__order"] = sample_df[
        ["hcr.first_name", "hcr.last_name", "hcr.category"]
    ].apply(tuple, axis=1).map(order_map)
    sample_df = sample_df.sort_values("__order").drop(columns="__order")
    sample_df[DRAW_LABEL] = "pilot." + (
        sample_df.reset_index(drop=True).index + 1
    ).astype(str)
    sample_df[KTP_FILENAME_COL] = sample_df[HCR_FILENAME_COL]
    sample_df = preprocess_samples(sample_df, economies=economies)
    _append_samples_table(conn, samples_table, sample_df)
