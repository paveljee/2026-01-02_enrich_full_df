from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .._vars import DRAW_LABEL, HCR_LIST_LABEL, HCR_ROW_LABEL, PRIORITY_LABEL

COUNTRY_PREFIX = ", "
ENGLISH_HICS = [
    "United States",
    "USA",
    "U.S.A.",
    "US",
    "U.S.",
    "United Kingdom",
    "UK",
    "U.K.",
    "Australia",
    "Canada",
    "New Zealand",
]
GREATER_CHINA = ["China", "Hong Kong", "Macau", "Taiwan"]
EU_COUNTRIES = [
    "Austria",
    "Belgium",
    "Bulgaria",
    "Croatia",
    "Cyprus",
    "Czechia",
    "Denmark",
    "Estonia",
    "Finland",
    "France",
    "Germany",
    "Greece",
    "Hungary",
    "Ireland",
    "Italy",
    "Latvia",
    "Lithuania",
    "Luxembourg",
    "Malta",
    "Netherlands",
    "Poland",
    "Portugal",
    "Romania",
    "Slovakia",
    "Slovenia",
    "Spain",
    "Sweden",
]
HIGH_INCOME_COUNTRIES_FY2025 = [
    "American Samoa",
    "Andorra",
    "Antigua and Barbuda",
    "Aruba",
    "Australia",
    "Austria",
    "Bahamas, The",
    "Bahrain",
    "Barbados",
    "Belgium",
    "Bermuda",
    "British Virgin Islands",
    "Brunei Darussalam",
    "Bulgaria",
    "Canada",
    "Cayman Islands",
    "Channel Islands",
    "Chile",
    "Croatia",
    "Curaçao",
    "Cyprus",
    "Czechia",
    "Denmark",
    "Estonia",
    "Faeroe Islands",
    "Finland",
    "France",
    "French Polynesia",
    "Germany",
    "Gibraltar",
    "Greece",
    "Greenland",
    "Guam",
    "Guyana",
    "Hong Kong SAR, China",
    "Hungary",
    "Iceland",
    "Ireland",
    "Isle of Man",
    "Israel",
    "Italy",
    "Japan",
    "Korea, Rep.",
    "Kuwait",
    "Latvia",
    "Liechtenstein",
    "Lithuania",
    "Luxembourg",
    "Macao SAR, China",
    "Malta",
    "Monaco",
    "Nauru",
    "Netherlands",
    "New Caledonia",
    "New Zealand",
    "Northern Mariana Islands",
    "Norway",
    "Oman",
    "Palau",
    "Panama",
    "Poland",
    "Portugal",
    "Puerto Rico (U.S.)",
    "Qatar",
    "Romania",
    "Russian Federation",
    "San Marino",
    "Saudi Arabia",
    "Seychelles",
    "Singapore",
    "Sint Maarten (Dutch part)",
    "Slovak Republic",
    "Slovenia",
    "Spain",
    "St. Kitts and Nevis",
    "St. Martin (French part)",
    "Sweden",
    "Switzerland",
    "Taiwan, China",
    "Trinidad and Tobago",
    "Turks and Caicos Islands",
    "United Arab Emirates",
    "United Kingdom",
    "United States",
    "Uruguay",
    "Virgin Islands (U.S.)",
]
NON_ENGLISH_NON_EU_HICS_NO_CHINA = [
    hic
    for hic in HIGH_INCOME_COUNTRIES_FY2025
    if not any(c in hic for c in ENGLISH_HICS + EU_COUNTRIES + GREATER_CHINA)
]

MATCHING_COLS = ["hcr.first_name", "hcr.last_name", "hcr.category"]


@dataclass(frozen=True)
class SamplePlan:
    seed: int
    draw_sizes: list[int]
    affiliation_sort: bool


def _hcr_header_unify(cat: str) -> str:
    return "hcr." + cat.replace(" ", "_").replace(":", "")


def load_population_from_xlsx(xlsx_paths: list[Path]) -> pd.DataFrame:
    dfs: dict[Path, pd.DataFrame] = {}
    for path in xlsx_paths:
        if path.suffix.lower() != ".xlsx" or path.name.startswith("~$"):
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            df = pd.read_excel(path)
            df.columns = [_hcr_header_unify(str(col).lower()) for col in df.columns]
        dfs[path] = df

    if not dfs:
        raise FileNotFoundError("No Excel files found.")

    full_df = pd.concat(
        [df.assign(**{HCR_LIST_LABEL: path.name}) for path, df in dfs.items()],
        ignore_index=False,
    )
    full_df = full_df.reset_index().rename(columns={"index": HCR_ROW_LABEL})
    full_df[HCR_ROW_LABEL] = full_df[HCR_ROW_LABEL] + 2
    return full_df


def _affiliation_priority(sampled_df: pd.DataFrame) -> pd.Series:
    aff_cols = [c for c in sampled_df.columns if "affiliation" in c.lower()]
    values = sampled_df[aff_cols].fillna("").astype(str).agg(" ".join, axis=1)

    def priority(value: str) -> int:
        if not any(
            COUNTRY_PREFIX + country in value
            for country in (
                ENGLISH_HICS
                + EU_COUNTRIES
                + GREATER_CHINA
                + NON_ENGLISH_NON_EU_HICS_NO_CHINA
            )
        ):
            return 1
        if any(COUNTRY_PREFIX + country in value for country in GREATER_CHINA):
            return 2
        if any(COUNTRY_PREFIX + country in value for country in NON_ENGLISH_NON_EU_HICS_NO_CHINA):
            return 3
        if any(COUNTRY_PREFIX + country in value for country in EU_COUNTRIES):
            return 4
        return 5

    return values.map(priority)


def sample_fixed_seed(
    full_df: pd.DataFrame,
    *,
    seed: int,
    draw_sizes: list[int],
    affiliation_sort: bool,
) -> list[pd.DataFrame]:
    rng = np.random.default_rng(seed)
    draws: list[pd.DataFrame] = []
    draw_number = 0

    for size in draw_sizes:
        rand_idxs = rng.integers(0, len(full_df), size=size)
        sampled_df = full_df.iloc[rand_idxs].copy()
        sampled_df[DRAW_LABEL] = np.arange(draw_number + 1, draw_number + 1 + size)
        draw_number += size

        if affiliation_sort:
            sampled_df[PRIORITY_LABEL] = _affiliation_priority(sampled_df)
            sampled_df = sampled_df.sort_values([PRIORITY_LABEL, DRAW_LABEL])
        else:
            sampled_df[PRIORITY_LABEL] = pd.NA

        first_cols = [DRAW_LABEL, HCR_LIST_LABEL, HCR_ROW_LABEL, PRIORITY_LABEL]
        cols = first_cols + [c for c in sampled_df.columns if c not in first_cols]
        sampled_df = sampled_df[cols]
        draws.append(sampled_df.reset_index(drop=True))

    return draws


def select_pilot_sample(
    full_df: pd.DataFrame,
    name_category_triples: list[tuple[str, str, str]],
    *,
    affiliation_sort: bool | None = None,
) -> pd.DataFrame:
    sampled_df = (
        full_df[
            full_df[MATCHING_COLS]
            .apply(tuple, axis=1)
            .isin(name_category_triples)
        ]
        .assign(
            __order=lambda x: x[MATCHING_COLS]
            .apply(tuple, axis=1)
            .map({pair: i for i, pair in enumerate(name_category_triples)})
        )
        .sort_values("__order")
        .drop(columns="__order")
        .copy()
    )

    sampled_df[DRAW_LABEL] = "pilot." + (sampled_df.reset_index(drop=True).index + 1).astype(str)

    if affiliation_sort is not None:
        sampled_df[PRIORITY_LABEL] = _affiliation_priority(sampled_df)
        if affiliation_sort:
            sampled_df = sampled_df.sort_values([PRIORITY_LABEL, DRAW_LABEL])
    else:
        sampled_df[PRIORITY_LABEL] = pd.NA

    first_cols = [DRAW_LABEL, HCR_LIST_LABEL, HCR_ROW_LABEL, PRIORITY_LABEL]
    cols = first_cols + [c for c in sampled_df.columns if c not in first_cols]
    sampled_df = sampled_df[cols]
    return sampled_df.reset_index(drop=True)
