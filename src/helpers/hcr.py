from __future__ import annotations

import warnings
from pathlib import Path

import duckdb
import pandas as pd

from .data_models import RegisteredResource
from .duckdb_utils import register_frame
from .vars import (
    COUNTRY_PREFIX,
    ENGLISH_HICS,
    EU_COUNTRIES,
    GREATER_CHINA,
    HCR_FILENAME_COL,
    HCR_ROW_COL,
    HIGH_INCOME_COUNTRIES_FY2025,
    KTP_ECONOMIES_COL,
    KTP_FILENAME_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_PRIORITY_GROUP_LABELS,
)


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


def load_high_income_economies(resource: RegisteredResource) -> list[str]:
    path = Path(resource.__fspath__())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df = pd.read_excel(path, sheet_name="Country Analytical History", engine="openpyxl")
    filtered = df[df.iloc[:, 38] == "H"]
    values = filtered.iloc[:, 1].tolist()
    return values


def _non_english_non_eu_hics(economies: list[str]) -> list[str]:
    return [
        hic
        for hic in economies
        if not any(c in hic for c in ENGLISH_HICS + EU_COUNTRIES + GREATER_CHINA)
    ]


def _find_affiliation_text(row: pd.Series) -> str:
    aff_cols = [c for c in row.index if "affiliation" in c.lower()]
    return " ".join(str(row[c]) for c in aff_cols if pd.notna(row[c]))


def _economies_for_row(row: pd.Series, economies: list[str]) -> str:
    values = _find_affiliation_text(row)
    matches = [econ for econ in economies if f"{COUNTRY_PREFIX}{econ}" in values]
    if not matches:
        return values
    return "; ".join(sorted(set(matches)))


def _priority_for_row(row: pd.Series, non_english_hics: list[str]) -> int:
    values = _find_affiliation_text(row)
    if not any(
        COUNTRY_PREFIX + country in values
        for country in (ENGLISH_HICS + EU_COUNTRIES + GREATER_CHINA + non_english_hics)
    ):
        return 1
    if any(COUNTRY_PREFIX + country in values for country in GREATER_CHINA):
        return 2
    if any(COUNTRY_PREFIX + country in values for country in non_english_hics):
        return 3
    if any(COUNTRY_PREFIX + country in values for country in EU_COUNTRIES):
        return 4
    return 5


def preprocess_samples(
    df: pd.DataFrame,
    *,
    economies: list[str] | None = None,
    filename_col: str = KTP_FILENAME_COL,
    economies_col: str = KTP_ECONOMIES_COL,
    priority_col: str = KTP_PRIORITY_COL,
    priority_group_col: str = KTP_PRIORITY_GROUP_COL,
) -> pd.DataFrame:
    economies = economies or HIGH_INCOME_COUNTRIES_FY2025
    non_english_hics = _non_english_non_eu_hics(economies)
    df[filename_col] = df[filename_col].astype(str)
    df[economies_col] = df.apply(lambda row: _economies_for_row(row, economies), axis=1)
    df[priority_col] = df.apply(lambda row: _priority_for_row(row, non_english_hics), axis=1)
    df[priority_group_col] = df[priority_col].map(KTP_PRIORITY_GROUP_LABELS)
    return df


__all__ = [
    "build_population_table",
    "load_high_income_economies",
    "normalize_hcr_header",
    "preprocess_samples",
]
