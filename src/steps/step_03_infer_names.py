from __future__ import annotations

from pathlib import Path

import duckdb

from ..helpers.context import PipelineContext, StepResult
from ..helpers.name_inference import infer_name_columns_from_xlsx
from ..helpers.schema import POPULATION_NAMES_TABLE, POPULATION_NAMES_VIEW, POPULATION_TABLE
from ..helpers.vars import (
    HCR_FILENAME_COL,
    HCR_XLSX_NAME_COLS,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_POPULATION_INDEX_COL,
)


def _build_name_expr(mapping: dict[str, tuple[str, str]], column_index: int) -> str:
    cases = []
    for filename, cols in mapping.items():
        col = cols[column_index]
        filename_safe = filename.replace("'", "''")
        cases.append(
            f"WHEN p.\"{HCR_FILENAME_COL}\" = '{filename_safe}' THEN p.\"{col}\""
        )
    if not cases:
        raise ValueError("No inferred name columns available.")
    return "CASE " + " ".join(cases) + " END"


def run(context: PipelineContext) -> StepResult:
    if context.resources is None:
        raise ValueError("Resources not initialized. Run register_resources first.")

    if not HCR_XLSX_NAME_COLS:
        inferred: dict[str, tuple[str, str]] = {}
        for resource in context.resources.xlsx_resources.values():
            mapping = infer_name_columns_from_xlsx(Path(resource.__fspath__()))
            if mapping:
                inferred[Path(resource.__fspath__()).name] = mapping
        if not inferred:
            raise ValueError("Could not infer name columns from XLSX files.")
        HCR_XLSX_NAME_COLS.update(inferred)

    missing = [
        res.name
        for res in context.resources.xlsx_resources.values()
        if not res.name.startswith("~$")
        if res.name not in HCR_XLSX_NAME_COLS
    ]
    if missing:
        raise ValueError(f"Missing inferred name columns for XLSX files: {', '.join(missing)}")

    first_expr = _build_name_expr(HCR_XLSX_NAME_COLS, 0)
    last_expr = _build_name_expr(HCR_XLSX_NAME_COLS, 1)

    conn: duckdb.DuckDBPyConnection = context.conn
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {POPULATION_NAMES_TABLE} AS
        SELECT
            p."{KTP_POPULATION_INDEX_COL}" AS "{KTP_POPULATION_INDEX_COL}",
            {first_expr} AS "{KTP_FIRST_NAME_COL}",
            {last_expr} AS "{KTP_LAST_NAME_COL}"
        FROM {POPULATION_TABLE} p
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {POPULATION_NAMES_VIEW} AS
        SELECT p.*, n."{KTP_FIRST_NAME_COL}", n."{KTP_LAST_NAME_COL}"
        FROM {POPULATION_TABLE} p
        JOIN {POPULATION_NAMES_TABLE} n
          ON p."{KTP_POPULATION_INDEX_COL}" = n."{KTP_POPULATION_INDEX_COL}"
        """
    )

    merged_df = conn.execute(f"SELECT * FROM {POPULATION_NAMES_VIEW}").df()

    return StepResult(
        step_id="infer_names",
        artifacts={"population_with_names_df": merged_df},
        messages=[f"Inferred name columns for {len(HCR_XLSX_NAME_COLS)} XLSX files."],
        diagnostics=[f"Inferred mappings: {len(HCR_XLSX_NAME_COLS)} files"],
    )
