from __future__ import annotations

import warnings
from pathlib import Path

import duckdb
import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.data_models import RegisteredResource
from ..helpers.duckdb_utils import register_frame
from ..helpers.schema import (
    POPULATION_ECON_TABLE,
    POPULATION_ECON_VIEW,
    POPULATION_NAMES_TABLE,
    POPULATION_TABLE,
)
from ..helpers.vars import (
    COUNTRY_PREFIX,
    ENGLISH_HICS,
    EU_COUNTRIES,
    GREATER_CHINA,
    HCR_FILENAME_COL,
    HIGH_INCOME_COUNTRIES_FY2025,
    KTP_ECONOMIES_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_PRIORITY_GROUP_LABELS,
)


def _load_high_income_economies(resource: RegisteredResource) -> list[str]:
    path = Path(resource.__fspath__())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df = pd.read_excel(path, sheet_name="Country Analytical History", engine="openpyxl")
    filtered = df[df.iloc[:, 38] == "H"]
    return filtered.iloc[:, 1].tolist()


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


def _preprocess_samples(
    df: pd.DataFrame,
    *,
    economies: list[str] | None = None,
    filename_col: str = HCR_FILENAME_COL,
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


def run(context: PipelineContext) -> StepResult:
    if context.resources is None:
        raise ValueError("Resources not initialized. Run register_resources first.")

    conn: duckdb.DuckDBPyConnection = context.conn
    population_df = conn.execute(f"SELECT * FROM {POPULATION_TABLE}").df()

    economies = _load_high_income_economies(context.resources.world_bank_resource)
    processed = _preprocess_samples(
        population_df,
        economies=economies,
        filename_col=HCR_FILENAME_COL,
        economies_col=KTP_ECONOMIES_COL,
        priority_col=KTP_PRIORITY_COL,
        priority_group_col=KTP_PRIORITY_GROUP_COL,
    )
    econ_df = processed[
        [
            KTP_POPULATION_INDEX_COL,
            KTP_ECONOMIES_COL,
            KTP_PRIORITY_COL,
            KTP_PRIORITY_GROUP_COL,
        ]
    ]

    register_frame(conn, "population_econ_frame", econ_df)
    conn.execute(
        f"CREATE OR REPLACE TABLE {POPULATION_ECON_TABLE} AS SELECT * FROM population_econ_frame"
    )
    conn.execute("DROP TABLE IF EXISTS population_econ_frame")
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {POPULATION_ECON_VIEW} AS
        SELECT
            p.*,
            n.*,
            e."{KTP_ECONOMIES_COL}",
            e."{KTP_PRIORITY_COL}",
            e."{KTP_PRIORITY_GROUP_COL}"
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
