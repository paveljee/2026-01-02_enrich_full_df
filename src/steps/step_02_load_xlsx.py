from __future__ import annotations

import warnings
from pathlib import Path

import duckdb
import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.data_models import RegisteredResource
from ..helpers.duckdb_utils import register_frame
from ..helpers.schema import POPULATION_TABLE
from ..helpers.vars import HCR_FILENAME_COL, HCR_ROW_COL, KTP_POPULATION_INDEX_COL, STEP_LOAD_XLSX


def _normalize_hcr_header(name: str) -> str:
    return "hcr." + name.replace(" ", "_").replace(":", "")


def _build_population_table(
    conn: duckdb.DuckDBPyConnection,
    resources: dict[str, RegisteredResource],
    *,
    table_name: str,
    filename_col: str = HCR_FILENAME_COL,
    row_col: str = HCR_ROW_COL,
    population_index_col: str = KTP_POPULATION_INDEX_COL,
) -> None:
    counter = 0
    for resource in resources.values():
        path = Path(resource.__fspath__())
        if path.suffix.lower() != ".xlsx" or path.name.startswith("~$"):
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            df = pd.read_excel(path, engine="openpyxl")
        df.columns = [_normalize_hcr_header(str(col).lower()) for col in df.columns]
        df = df.reset_index().rename(columns={"index": row_col})
        df[row_col] = df[row_col] + 2
        df[filename_col] = path.name
        df[population_index_col] = range(counter, counter + len(df))
        for col in df.columns:
            if col in {row_col, population_index_col}:
                continue
            df[col] = df[col].astype("string")
        counter += len(df)
        result = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            [table_name],
        ).fetchone()
        exists = result[0] if result else 0
        if exists:
            table_info = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
            table_cols = [row[1] for row in table_info]
            table_col_set = set(table_cols)
            df_col_set = set(df.columns)

            new_cols = df_col_set - table_col_set
            for col in sorted(new_cols):
                dtype = df[col].dtype
                if pd.api.types.is_integer_dtype(dtype):
                    col_type = "BIGINT"
                elif pd.api.types.is_float_dtype(dtype):
                    col_type = "DOUBLE"
                elif pd.api.types.is_bool_dtype(dtype):
                    col_type = "BOOLEAN"
                elif pd.api.types.is_datetime64_any_dtype(dtype):
                    col_type = "TIMESTAMP"
                else:
                    col_type = "VARCHAR"
                conn.execute(f'ALTER TABLE {table_name} ADD COLUMN "{col}" {col_type}')

            missing_cols = table_col_set - df_col_set
            for col in missing_cols:
                df[col] = pd.NA

            table_info = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
            table_cols = [row[1] for row in table_info]
            df = df[table_cols]

            register_frame(conn, "population_frame", df)
            conn.execute(f"INSERT INTO {table_name} SELECT * FROM population_frame")
        else:
            register_frame(conn, table_name, df)


def run(context: PipelineContext) -> StepResult:
    if context.resources is None:
        raise ValueError("Resources not initialized. Run register_resources first.")

    conn: duckdb.DuckDBPyConnection = context.conn
    _build_population_table(
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
        step_id=STEP_LOAD_XLSX,
        artifacts={"population_df": population_df},
        messages=[f"Loaded population rows: {row_count}", f"Columns: {col_count}"],
        diagnostics=[f"Rows: {row_count}", f"Columns: {col_count}"],
    )
