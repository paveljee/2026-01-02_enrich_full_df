from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

from .._vars import (
    COUNTRY_PREFIX,
    ENGLISH_HICS,
    EU_COUNTRIES,
    GREATER_CHINA,
    HIGH_INCOME_COUNTRIES_FY2025,
    KTP_ECONOMIES_COL,
    KTP_FILENAME_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_PRIORITY_GROUP_LABELS,
)
from ..data_models import RegisteredResource


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
    matches = [
        econ
        for econ in economies
        if f"{COUNTRY_PREFIX}{econ}" in values
    ]
    if not matches:
        return values
    return "; ".join(sorted(set(matches)))


def _priority_for_row(row: pd.Series, non_english_hics: list[str]) -> int:
    values = _find_affiliation_text(row)
    if not any(
        COUNTRY_PREFIX + country in values
        for country in (
            ENGLISH_HICS + EU_COUNTRIES + GREATER_CHINA + non_english_hics
        )
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
