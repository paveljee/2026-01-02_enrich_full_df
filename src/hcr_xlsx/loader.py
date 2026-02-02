from __future__ import annotations

import warnings
from pathlib import Path

import duckdb
import pandas as pd

from .._vars import HCR_FILENAME_COL, HCR_ROW_COL, KTP_POPULATION_INDEX_COL
from ..data_models import RegisteredResource
from ..utils.duckdb import register_frame


def normalize_hcr_header(name: str) -> str:
    return "hcr." + name.replace(" ", "_").replace(":", "")


def build_population_table(
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
        df.columns = [normalize_hcr_header(str(col).lower()) for col in df.columns]
        df = df.reset_index().rename(columns={"index": row_col})
        df[row_col] = df[row_col] + 2
        df[filename_col] = path.name
        df[population_index_col] = range(counter, counter + len(df))
        counter += len(df)
        result = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            [table_name],
        ).fetchone()
        exists = result[0] if result else 0
        if exists:
            register_frame(conn, "population_frame", df)
            conn.execute(
                f"INSERT INTO {table_name} SELECT * FROM population_frame"
            )
        else:
            register_frame(conn, table_name, df)
