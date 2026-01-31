from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from src._vars import DRAW_LABEL, HCR_FILENAME_COL, HCR_ROW_NUMBER_COL, PRIORITY_LABEL

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

PILOT_NAME_CATEGORY_TRIPLES: list[tuple[str, str, str]] = [
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


def hcr_header_unify(category: str) -> str:
    return "hcr." + category.replace(" ", "_").replace(":", "")


def load_hcr_excels(excel_paths: list[Path]) -> pd.DataFrame:
    dfs: dict[str, pd.DataFrame] = {}
    for path in excel_paths:
        if path.name.startswith("~$"):
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                df = pd.read_excel(path, engine="openpyxl")
                df.columns = [hcr_header_unify(str(col).lower()) for col in df.columns]
            dfs[str(path)] = df
        except Exception as exc:
            raise RuntimeError(f"Error reading {path.name}: {exc}") from exc

    if not dfs:
        raise FileNotFoundError("No Excel files found.")

    full_df = pd.concat(
        [df.assign(**{HCR_FILENAME_COL: Path(path).name}) for path, df in dfs.items()],
        ignore_index=False,
    )
    full_df = full_df.reset_index().rename(columns={"index": HCR_ROW_NUMBER_COL})
    full_df[HCR_ROW_NUMBER_COL] = full_df[HCR_ROW_NUMBER_COL] + 2
    return full_df


def load_population_from_xlsx(folder_path: Path) -> pd.DataFrame:
    excel_paths = sorted(folder_path.glob("*.xlsx"))
    return load_hcr_excels(excel_paths)


def apply_affiliation_priority(sampled_df: pd.DataFrame) -> pd.DataFrame:
    aff_cols = [c for c in sampled_df.columns if "affiliation" in c.lower()]

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
        if any(COUNTRY_PREFIX + country in values for country in NON_ENGLISH_NON_EU_HICS_NO_CHINA):
            return 3
        if any(COUNTRY_PREFIX + country in values for country in EU_COUNTRIES):
            return 4
        return 5

    sampled_df[PRIORITY_LABEL] = sampled_df.apply(affiliation_priority, axis=1)
    sampled_df = sampled_df.sort_values([PRIORITY_LABEL, DRAW_LABEL])
    return sampled_df


def sample_random_draws(
    population_df: pd.DataFrame,
    *,
    seed: int,
    draw_sizes: list[int],
    affiliation_sort: bool,
    max_total: int | None = None,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    draw_number = 1
    samples: list[pd.DataFrame] = []
    running_total = 0

    for draw_size in draw_sizes:
        if max_total is not None and running_total >= max_total:
            break
        if max_total is not None and running_total + draw_size > max_total:
            draw_size = max_total - running_total
        if draw_size <= 0:
            break
        rand_idxs = rng.integers(0, len(population_df), size=draw_size)
        sampled_df = population_df.iloc[rand_idxs].copy()
        sampled_df[DRAW_LABEL] = np.arange(draw_number, draw_number + draw_size)
        draw_number += draw_size
        running_total += draw_size
        if affiliation_sort:
            sampled_df = apply_affiliation_priority(sampled_df)
        samples.append(sampled_df)

    return pd.concat(samples, ignore_index=True)


def sample_pilot_from_2024(
    excel_file_path: Path,
    folder_path: Path,
    *,
    name_category_triples: list[tuple[str, str, str]] | None = None,
    affiliation_sort: bool | None = None,
) -> pd.DataFrame:
    if name_category_triples is None:
        name_category_triples = PILOT_NAME_CATEGORY_TRIPLES

    if not (str(excel_file_path).endswith(".xlsx") and "2024" in str(excel_file_path)):
        raise RuntimeError("Only 2024 xlsx is supported")

    folder_file_paths = [
        f
        for f in sorted(folder_path.iterdir())
        if f.name.endswith(".xlsx") and not f.name.startswith("~$")
    ]
    folder_full_df = load_hcr_excels(folder_file_paths)
    folder_full_df = folder_full_df.iloc[0:0]

    full_df = load_hcr_excels([excel_file_path])
    full_df = full_df.reindex(columns=folder_full_df.columns)

    sampled_df = (
        full_df[
            full_df[MATCHING_COLS].apply(tuple, axis=1).isin(name_category_triples)
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
        sampled_df = apply_affiliation_priority(sampled_df)
        if not affiliation_sort:
            sampled_df = sampled_df.sort_values(DRAW_LABEL)

    return sampled_df
