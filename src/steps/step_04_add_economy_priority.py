from __future__ import annotations

import duckdb

from ..helpers.context import PipelineContext, StepResult
from ..helpers.duckdb_utils import register_frame
from ..helpers.hcr import load_high_income_economies, preprocess_samples
from ..helpers.schema import (
    POPULATION_ECON_TABLE,
    POPULATION_ECON_VIEW,
    POPULATION_NAMES_TABLE,
    POPULATION_TABLE,
)
from ..helpers.vars import (
    HCR_FILENAME_COL,
    KTP_ECONOMIES_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
)


def run(context: PipelineContext) -> StepResult:
    if context.resources is None:
        raise ValueError("Resources not initialized. Run register_resources first.")

    conn: duckdb.DuckDBPyConnection = context.conn
    population_df = conn.execute(f"SELECT * FROM {POPULATION_TABLE}").df()

    economies = load_high_income_economies(context.resources.world_bank_resource)
    processed = preprocess_samples(
        population_df,
        economies=economies,
        filename_col=HCR_FILENAME_COL,
        economies_col=KTP_ECONOMIES_COL,
        priority_col=KTP_PRIORITY_COL,
    )
    econ_df = processed[[KTP_POPULATION_INDEX_COL, KTP_ECONOMIES_COL, KTP_PRIORITY_COL]]

    register_frame(conn, "population_econ_frame", econ_df)
    conn.execute(
        f"CREATE OR REPLACE TABLE {POPULATION_ECON_TABLE} AS SELECT * FROM population_econ_frame"
    )
    conn.execute("DROP TABLE IF EXISTS population_econ_frame")
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {POPULATION_ECON_VIEW} AS
        SELECT p.*, n.*, e."{KTP_ECONOMIES_COL}", e."{KTP_PRIORITY_COL}"
        FROM {POPULATION_TABLE} p
        JOIN {POPULATION_NAMES_TABLE} n
          ON p."{KTP_POPULATION_INDEX_COL}" = n."{KTP_POPULATION_INDEX_COL}"
        JOIN {POPULATION_ECON_TABLE} e
          ON p."{KTP_POPULATION_INDEX_COL}" = e."{KTP_POPULATION_INDEX_COL}"
        """
    )

    merged_df = conn.execute(f"SELECT * FROM {POPULATION_ECON_VIEW}").df()

    return StepResult(
        step_id="add_economy_priority",
        artifacts={"population_with_economy_df": merged_df},
        messages=[f"Computed economies for {len(economies)} high-income entries."],
        diagnostics=[f"High-income economies: {len(economies)}"],
    )
