from __future__ import annotations

import duckdb

from ..helpers.context import PipelineContext, StepResult
from ..helpers.hcr import build_population_table
from ..helpers.schema import POPULATION_TABLE
from ..helpers.vars import HCR_FILENAME_COL, HCR_ROW_COL


def run(context: PipelineContext) -> StepResult:
    if context.resources is None:
        raise ValueError("Resources not initialized. Run register_resources first.")

    conn: duckdb.DuckDBPyConnection = context.conn
    build_population_table(
        conn,
        context.resources.xlsx_resources,
        table_name=POPULATION_TABLE,
        filename_col=HCR_FILENAME_COL,
        row_col=HCR_ROW_COL,
    )

    population_df = conn.execute(f"SELECT * FROM {POPULATION_TABLE}").df()
    row_count = len(population_df)
    col_count = population_df.shape[1]

    return StepResult(
        step_id="load_xlsx",
        artifacts={"population_df": population_df},
        messages=[f"Loaded population rows: {row_count}", f"Columns: {col_count}"],
        diagnostics=[f"Rows: {row_count}", f"Columns: {col_count}"],
    )
