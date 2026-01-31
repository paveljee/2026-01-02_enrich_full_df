from __future__ import annotations

import warnings
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

HCR_LIST_LABEL = "hcr.filename"
HCR_ROW_LABEL = "hcr.row_number"
DRAW_LABEL = "ktp.draw_number"
PRIORITY_LABEL = "ktp.priority"
MATCHING_COLS = ["hcr.first_name", "hcr.last_name", "hcr.category"]

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

PILOT_NAME_CATEGORY_TRIPLES = [
    ("Bin", "Gao", "Cross-Field"),
    ("Beatriz Roldan", "Cuenya", "Chemistry"),
    ("Lizhi", "Zhang", "Chemistry"),
    ("Rudolf A.", "de Boer", "Clinical Medicine"),
    ("Hidenori", "Arai", "Cross-Field"),
    ("Mark A.", "Bradford", "Cross-Field"),
    ("Salim", "Yusuf", "Clinical Medicine"),
    ("Nicholas C.", "Turner", "Clinical Medicine"),
    ("Osman M.", "Bakr", "Chemistry"),
    ("Rainer", "Blatt", "Physics"),
]


def normalize_hcr_header(name: str) -> str:
    return "hcr." + name.replace(" ", "_").replace(":", "")


def concat_dfs_from_file_list(excel_file_paths: Iterable[Path]) -> pd.DataFrame:
    dfs: dict[str, pd.DataFrame] = {}
    for file in excel_file_paths:
        if file.suffix.lower() != ".xlsx" or file.name.startswith("~$"):
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                df = pd.read_excel(file, engine="openpyxl")
                df.columns = [normalize_hcr_header(str(col).lower()) for col in df.columns]
            dfs[str(file)] = df
        except Exception as exc:
            raise RuntimeError(f"Error reading {file}: {exc}") from exc
    if not dfs:
        raise FileNotFoundError("No Excel files found.")
    full_df = pd.concat(
        [df.assign(**{HCR_LIST_LABEL: Path(path).name}) for path, df in dfs.items()],
        ignore_index=False,
    )
    full_df = full_df.reset_index().rename(columns={"index": HCR_ROW_LABEL})
    full_df[HCR_ROW_LABEL] = full_df[HCR_ROW_LABEL] + 2
    return full_df


def apply_affiliation_priority(df: pd.DataFrame) -> pd.Series:
    aff_cols = [c for c in df.columns if "affiliation" in c.lower()]

    def affiliation_priority(row: pd.Series) -> int:
        values = " ".join(str(row[c]) for c in aff_cols if pd.notna(row[c]))
        if not any(
            COUNTRY_PREFIX + country in values
            for country in (
                ENGLISH_HICS + EU_COUNTRIES + GREATER_CHINA + NON_ENGLISH_NON_EU_HICS_NO_CHINA
            )
        ):
            return 1
        if any(COUNTRY_PREFIX + country in values for country in GREATER_CHINA):
            return 2
        if any(
            COUNTRY_PREFIX + country in values for country in NON_ENGLISH_NON_EU_HICS_NO_CHINA
        ):
            return 3
        if any(COUNTRY_PREFIX + country in values for country in EU_COUNTRIES):
            return 4
        return 5

    return df.apply(affiliation_priority, axis=1)


def sample_population_df(
    full_df: pd.DataFrame,
    *,
    draw_sizes: list[int],
    seed: int,
    affiliation_sort: bool,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    samples: list[pd.DataFrame] = []
    draw_number = 1
    for draw_size in draw_sizes:
        rand_idxs = rng.integers(0, len(full_df), size=draw_size)
        sampled_df = full_df.iloc[rand_idxs].copy()
        sampled_df[DRAW_LABEL] = np.arange(draw_number, draw_number + draw_size)
        if affiliation_sort:
            sampled_df[PRIORITY_LABEL] = apply_affiliation_priority(sampled_df)
            sampled_df = sampled_df.sort_values([PRIORITY_LABEL, DRAW_LABEL])
        first_cols = [DRAW_LABEL, HCR_LIST_LABEL, HCR_ROW_LABEL, PRIORITY_LABEL]
        cols = first_cols + [c for c in sampled_df.columns if c not in first_cols]
        sampled_df = sampled_df[cols]
        samples.append(sampled_df)
        draw_number += draw_size
    return pd.concat(samples, ignore_index=True)


def build_pilot_sample(
    excel_file_path: Path,
    folder_path: Path,
    *,
    name_category_triples: list[tuple[str, str, str]] | None = None,
    affiliation_sort: bool = False,
) -> pd.DataFrame:
    name_category_triples = name_category_triples or PILOT_NAME_CATEGORY_TRIPLES
    folder_file_paths = [
        file
        for file in sorted(folder_path.iterdir())
        if file.suffix.lower() == ".xlsx" and not file.name.startswith("~$")
    ]
    folder_full_df = concat_dfs_from_file_list(folder_file_paths)
    folder_full_df = folder_full_df.iloc[0:0]
    full_df = concat_dfs_from_file_list([excel_file_path])
    full_df = full_df.reindex(columns=folder_full_df.columns)

    sampled_df = (
        full_df[full_df[MATCHING_COLS].apply(tuple, axis=1).isin(name_category_triples)]
        .assign(
            __order=lambda x: x[MATCHING_COLS]
            .apply(tuple, axis=1)
            .map({pair: i for i, pair in enumerate(name_category_triples)})
        )
        .sort_values("__order")
        .drop(columns="__order")
        .copy()
    )

    sampled_df[DRAW_LABEL] = "pilot." + (sampled_df.reset_index(drop=True).index + 1).astype(
        str
    )

    if affiliation_sort is not None:
        sampled_df[PRIORITY_LABEL] = apply_affiliation_priority(sampled_df)
        if affiliation_sort:
            sampled_df = sampled_df.sort_values([PRIORITY_LABEL, DRAW_LABEL])

    first_cols = [DRAW_LABEL, HCR_LIST_LABEL, HCR_ROW_LABEL, PRIORITY_LABEL]
    cols = first_cols + [c for c in sampled_df.columns if c not in first_cols]
    sampled_df = sampled_df[cols]
    return sampled_df
