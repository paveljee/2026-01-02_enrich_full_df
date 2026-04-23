from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from rich import box
from rich.console import Console
from rich.table import Table

from src.helpers.config import PipelineConfig
from src.helpers.data_models import FragmentType, ResourceGroup
from src.helpers.jsonlines import loads_jsonlines
from src.helpers.resource_monitor import ResourceMonitor
from src.helpers.resources import register_resource
from src.helpers.schema import (
    OUTERDICT_STUB_TABLE,
    PARQUET_INNERDICT_TABLE,
    PARQUET_OUTPUT_VIEW,
    POPULATION_ECON_VIEW,
    XLSX_INNERDICT_TABLE,
)
from src.helpers.vars import (
    CARD_BUILD_SUBSET_DESCRIPTIONS,
    ENGLISH_HICS,
    EU_COUNTRIES,
    GREATER_CHINA,
    HCR_CATEGORY_COL,
    HCR_FILENAME_COL,
    HCR_ROW_COL,
    HCR_XLSX_NAME_COLS,
    KTP_ECONOMIES_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    KTP_ECONOMIES_ISO_COL,
    KTP_ECONOMY_MATCH_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_LAST_NAME_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_PRIORITY_GROUP_LABELS,
    KTP_SOURCE_KEY_COL,
    KTP_XLSX_MATCH_FIRST_TOKENS_KEY,
    KTP_XLSX_MATCH_LAST_NAME_NORM_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY,
    OGHIST_INCOME_LABELS,
    WORLD_BANK_FORMER_ECONOMY_CODES,
    WORLD_BANK_INCOME_FISCAL_YEAR,
    WORLD_BANK_XLSX_KEY,
)

console = Console()

DETOUR_ID = "mode0-econ-stats"
DETOUR_NAME = "Mode 0 Economy Stats"
DETOUR_DESCRIPTION = (
    "Read-only detour that analyzes income-group and priority-group coverage across "
    "all HCR population rows and all persisted name keys."
)
DETOUR_STEPS: list[str] = []

MODE = 0
UNCOVERED_COUNTRIES_SVG_PATH = Path("tmp") / "mode0_econ_stats_not_covered_countries.svg"
POPULATION_WITH_ECONOMY_PARQUET_CSV_PATH = (
    Path("tmp") / "mode0_econ_stats_population_with_economy_and_parquet.csv"
)
UNCOVERED_COLOUR = "#DA7842"
PARQUET_LEFT_JOIN_COLS = [
    "ssnau.p_gf",
    "ssnau.inference_counts",
    "ssnau.inference_sources",
]
BRIDGE_FIRST_NAME_COL = "__bridge_first_name"
BRIDGE_LAST_NAME_COL = "__bridge_last_name"

PRIORITY_GROUP_PRECEDENCE = [
    KTP_PRIORITY_GROUP_LABELS[2],
    KTP_PRIORITY_GROUP_LABELS[3],
    KTP_PRIORITY_GROUP_LABELS[4],
    KTP_PRIORITY_GROUP_LABELS[5],
    KTP_PRIORITY_GROUP_LABELS[1],
]
PRIORITY_GROUP_PRECEDENCE_LOW_FIRST = list(reversed(PRIORITY_GROUP_PRECEDENCE))
PRIORITY_GROUP_RULES = [
    {
        "label": KTP_PRIORITY_GROUP_LABELS[2],
        "rule": "Any matched country is in the Greater China set.",
    },
    {
        "label": KTP_PRIORITY_GROUP_LABELS[3],
        "rule": (
            "No higher-priority rule fired and any matched country is a non-English, "
            "non-EU high-income country."
        ),
    },
    {
        "label": KTP_PRIORITY_GROUP_LABELS[4],
        "rule": "No higher-priority rule fired and any matched country is in the EU set.",
    },
    {
        "label": KTP_PRIORITY_GROUP_LABELS[5],
        "rule": "No higher-priority rule fired and any matched country is in the English-HIC set.",
    },
    {
        "label": KTP_PRIORITY_GROUP_LABELS[1],
        "rule": (
            "Fallback bucket for no matched countries, LMIC-only countries, or countries "
            "outside the higher-priority sets."
        ),
    },
]
MISSING_BREAKDOWN_LABEL = "Missing"
INCOME_GROUP_ORDER = [
    OGHIST_INCOME_LABELS["H"],
    OGHIST_INCOME_LABELS["UM"],
    OGHIST_INCOME_LABELS["LM"],
    OGHIST_INCOME_LABELS["L"],
]
INCOME_GROUP_ORDER_LOW_FIRST = [
    OGHIST_INCOME_LABELS["L"],
    OGHIST_INCOME_LABELS["LM"],
    OGHIST_INCOME_LABELS["UM"],
    OGHIST_INCOME_LABELS["H"],
]


@dataclass
class DetourResult:
    success: bool
    steps_completed: list[str]
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _has_present_xlsx_match_payload(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return not bool(pd.isna(value))


def _is_exact_xlsx_match_payload(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return True
    raw = value.strip()
    if not raw:
        return True
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    source_key_tokens = payload.get(KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY, [])
    source_key_last = payload.get(KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY)
    first_tokens = payload.get(KTP_XLSX_MATCH_FIRST_TOKENS_KEY, [])
    last_name_norm = payload.get(KTP_XLSX_MATCH_LAST_NAME_NORM_KEY)
    if not isinstance(source_key_tokens, list):
        source_key_tokens = []
    if not isinstance(first_tokens, list):
        first_tokens = []
    source_key_last_str = str(source_key_last).strip() if source_key_last is not None else ""
    last_name_norm_str = str(last_name_norm).strip() if last_name_norm is not None else ""
    source_key_token_values = sorted(
        {str(token).strip() for token in source_key_tokens if str(token).strip()}
    )
    if not source_key_token_values or not source_key_last_str:
        return False
    first_token_values = sorted(
        {str(token).strip() for token in first_tokens if str(token).strip()}
    )
    return (
        source_key_token_values == first_token_values
        and bool(last_name_norm_str)
        and source_key_last_str == last_name_norm_str
    )


def _pct(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator * 100.0


def _round_or_none(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _scalar_int(conn: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    if row is None:
        raise RuntimeError(f"Expected one-row scalar result for query: {sql}")
    return int(row[0])


def _db_file_from_pragma(conn: duckdb.DuckDBPyConnection) -> str:
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None:
        return ""
    return str(row[2])


def _fmt_float(value: float | None, digits: int = 6) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.3f}%"


def _normalize_country_list(value: object) -> list[str]:
    if value is None:
        return []
    items: list[object]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            items = [raw]
        else:
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, str):
                items = [parsed]
            else:
                items = [raw]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        if bool(pd.isna(value)):
            return []
        items = [value]

    normalized = sorted({str(item).strip() for item in items if str(item).strip()})
    return normalized


def _json_country_list(values: list[str]) -> str:
    return json.dumps(values)


def _iso_codes_for_countries(
    countries: list[str] | set[str],
    country_to_iso: dict[str, str],
) -> list[str]:
    return [
        iso_code
        for country in sorted(set(countries))
        if (iso_code := country_to_iso.get(country)) is not None
    ]


def _iso_country_list_json(value: object, country_to_iso: dict[str, str]) -> str:
    countries = _normalize_country_list(value)
    return _json_country_list(_iso_codes_for_countries(countries, country_to_iso))


def _normalize_optional_label(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        return raw or None
    if bool(pd.isna(value)):
        return None
    raw = str(value).strip()
    return raw or None


def _ordered_labels(observed: set[str], preferred: list[str]) -> list[str]:
    preferred_set = set(preferred)
    ordered = [label for label in preferred if label in observed]
    ordered.extend(sorted(label for label in observed if label not in preferred_set))
    return ordered


def _preferred_income_group_for_countries(
    countries: set[str] | list[str],
    country_to_income: dict[str, str],
    precedence: list[str],
) -> str | None:
    observed = {
        income_group
        for country in countries
        if (income_group := country_to_income.get(country)) is not None
    }
    for label in precedence:
        if label in observed:
            return label
    if observed:
        return sorted(observed)[0]
    return None


def _preferred_label(observed: set[str], precedence: list[str]) -> str | None:
    for label in precedence:
        if label in observed:
            return label
    if observed:
        return sorted(observed)[0]
    return None


def _preferred_priority_group_for_countries(
    countries: set[str] | list[str],
    priority_sets: dict[str, set[str]],
    precedence: list[str],
) -> str:
    if not countries:
        return KTP_PRIORITY_GROUP_LABELS[1]
    observed = {_priority_group_for_country(country, priority_sets) for country in countries}
    preferred = _preferred_label(observed, precedence)
    if preferred is None:
        return KTP_PRIORITY_GROUP_LABELS[1]
    return preferred


def _parse_name_key(name_key: str) -> tuple[str | None, str | None]:
    try:
        parsed = json.loads(name_key)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    first_name = _normalize_optional_label(parsed.get(KTP_FIRST_NAME_COL))
    last_name = _normalize_optional_label(parsed.get(KTP_LAST_NAME_COL))
    return first_name, last_name


def _display_name(name_key: str, rows: list[dict[str, object]]) -> str:
    first_name, last_name = _parse_name_key(name_key)
    if first_name is None:
        for row in rows:
            if (first_name := _normalize_optional_label(row.get(KTP_FIRST_NAME_COL))) is not None:
                break
    if last_name is None:
        for row in rows:
            if (last_name := _normalize_optional_label(row.get(KTP_LAST_NAME_COL))) is not None:
                break

    if last_name and first_name:
        return f"{last_name}, {first_name}"
    if last_name:
        return last_name
    if first_name:
        return first_name
    return name_key


def _join_display(values: list[str], delimiter: str = " | ") -> str:
    if not values:
        return MISSING_BREAKDOWN_LABEL
    return delimiter.join(values)


def _load_income_label_maps_from_db(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[dict[str, str], dict[str, str]]:
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    if "income_map" not in tables:
        raise RuntimeError(
            "Required persisted table 'income_map' is missing from the DB; "
            "mode-0 econ stats must run from persisted DB content only."
        )

    country_to_income: dict[str, str] = {}
    alias_to_country: dict[str, str] = {}
    for match_name, country, income_label in conn.execute(
        """
        SELECT DISTINCT match_name, country, income_label
        FROM income_map
        WHERE country IS NOT NULL AND income_label IS NOT NULL
        """
    ).fetchall():
        country_str = str(country).strip()
        income_label_str = str(income_label).strip()
        match_name_str = str(match_name).strip() if match_name is not None else ""
        if not country_str or not income_label_str:
            continue
        country_to_income[country_str] = income_label_str
        if match_name_str:
            alias_to_country[match_name_str] = country_str
        alias_to_country.setdefault(country_str, country_str)

    return country_to_income, alias_to_country


def _non_english_non_eu_hics(economies: list[str]) -> list[str]:
    return [
        hic
        for hic in economies
        if not any(country in hic for country in ENGLISH_HICS + EU_COUNTRIES + GREATER_CHINA)
    ]


def _priority_country_sets(
    country_to_income: dict[str, str],
    alias_to_country: dict[str, str],
) -> dict[str, set[str]]:
    high_income = sorted(
        {
            country
            for country, label in country_to_income.items()
            if label == OGHIST_INCOME_LABELS["H"]
        }
    )
    non_english_hics = _non_english_non_eu_hics(high_income)

    def _countries_for(match_names: list[str]) -> list[str]:
        countries: list[str] = []
        for name in match_names:
            country = alias_to_country.get(name)
            if country and country not in countries:
                countries.append(country)
        return countries

    english_countries = _countries_for(ENGLISH_HICS)
    eu_countries = _countries_for(EU_COUNTRIES)
    china_countries = _countries_for(GREATER_CHINA)
    non_english_countries = [
        country for country in non_english_hics if country not in english_countries + eu_countries
    ]

    return {
        "greater_china": set(china_countries),
        "non_english_non_eu_hics": set(non_english_countries),
        "eu_countries": set(eu_countries),
        "english_hics": set(english_countries),
    }


def _priority_group_for_country(country: str, priority_sets: dict[str, set[str]]) -> str:
    if country in priority_sets["greater_china"]:
        return KTP_PRIORITY_GROUP_LABELS[2]
    if country in priority_sets["non_english_non_eu_hics"]:
        return KTP_PRIORITY_GROUP_LABELS[3]
    if country in priority_sets["eu_countries"]:
        return KTP_PRIORITY_GROUP_LABELS[4]
    if country in priority_sets["english_hics"]:
        return KTP_PRIORITY_GROUP_LABELS[5]
    return KTP_PRIORITY_GROUP_LABELS[1]


def _record_first_non_missing(
    by_row_id: dict[tuple[str, str], str | None],
    row_id: tuple[str, str],
    value: str | None,
) -> None:
    current = by_row_id.get(row_id)
    if current is None and value is not None:
        by_row_id[row_id] = value
    elif row_id not in by_row_id:
        by_row_id[row_id] = value


def _registered_world_bank_resource(config: PipelineConfig):
    if WORLD_BANK_XLSX_KEY not in config.files_config:
        raise KeyError(f"Missing '{WORLD_BANK_XLSX_KEY}' entry in files_config")
    meta = config.files_config[WORLD_BANK_XLSX_KEY]
    return register_resource(
        Path(meta["path"]),
        group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
        fragment_type=FragmentType.EXCEL_ROW,
        description=meta.get("desc", "World Bank country list"),
        expected_hash=meta.get("sha256"),
    )


def _normalize_iso3_code(value: object) -> str | None:
    if value is None or bool(pd.isna(value)):
        return None
    raw = str(value).strip().upper()
    if len(raw) != 3 or raw == "NAN":
        return None
    return raw


def _load_world_bank_country_rows(
    config: PipelineConfig,
    *,
    priority_sets: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    resource = _registered_world_bank_resource(config)
    path = Path(resource.__fspath__())
    df = pd.read_excel(
        path,
        sheet_name="Country Analytical History",
        engine="openpyxl",
        header=None,
    )
    fy_row = None
    for _, row in df.iterrows():
        if row.astype(str).str.contains(r"\bFY\d{2}\b", regex=True).any():
            fy_row = row
            break
    if fy_row is None:
        raise ValueError("Unable to locate FY column in World Bank history sheet.")
    fy_col = None
    for col_idx, value in fy_row.items():
        if isinstance(value, str) and value.strip() == WORLD_BANK_INCOME_FISCAL_YEAR:
            fy_col = col_idx
            break
    if fy_col is None:
        raise ValueError(
            f"Unable to locate {WORLD_BANK_INCOME_FISCAL_YEAR} column in World Bank history sheet."
        )
    fiscal_year = WORLD_BANK_INCOME_FISCAL_YEAR

    rows: list[dict[str, Any]] = []
    excluded_former_economies: list[dict[str, str]] = []
    missing_income_group_countries: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    for _, row in df.iterrows():
        raw_country_code = _normalize_optional_label(row.get(0))
        country = _normalize_optional_label(row.get(1))
        if raw_country_code is None or country is None:
            continue
        if raw_country_code in WORLD_BANK_FORMER_ECONOMY_CODES or "(former)" in country.lower():
            excluded_former_economies.append(
                {
                    "country_code": raw_country_code,
                    "country": country,
                }
            )
            continue
        country_code = _normalize_iso3_code(raw_country_code)
        if country_code is None or country_code in seen_codes:
            continue
        income_code = _normalize_optional_label(row.get(fy_col))
        income_group = (
            OGHIST_INCOME_LABELS.get(income_code)
            if income_code is not None
            else None
        )
        if income_group is None:
            missing_income_group_countries.append(
                {
                    "country_code": country_code,
                    "country": country,
                }
            )
        priority_group = _priority_group_for_country(country, priority_sets)
        rows.append(
            {
                "country_code": country_code,
                "country": country,
                "income_group": (
                    income_group if income_group is not None else MISSING_BREAKDOWN_LABEL
                ),
                "priority_group": priority_group,
            }
        )
        seen_codes.add(country_code)

    metadata = {
        "resource_name": resource.name,
        "resource_hash": resource.hash,
        "resource_path": str(path),
        "income_group_fiscal_year": fiscal_year,
        "country_code_column": 0,
        "country_name_column": 1,
        "excluded_former_economies": excluded_former_economies,
        "missing_income_group_countries": missing_income_group_countries,
    }
    return rows, metadata


def _country_coverage_rows(
    *,
    country_rows: list[dict[str, Any]],
    covered_countries: set[str],
    priority_sets: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []
    for row in country_rows:
        country = str(row["country"])
        covered = country in covered_countries
        enriched_rows.append({**row, "covered": covered})

    total_countries = len(enriched_rows)
    covered_country_rows = [row for row in enriched_rows if row["covered"]]
    not_covered_country_rows = [row for row in enriched_rows if not row["covered"]]

    def _breakdown(
        label_key: str,
        labels: list[str],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for label in labels:
            in_label = [row for row in enriched_rows if row[label_key] == label]
            covered_in_label = [row for row in in_label if row["covered"]]
            not_covered_in_label = [row for row in in_label if not row["covered"]]
            rows.append(
                {
                    "label": label,
                    "total_countries": len(in_label),
                    "pct_of_total_countries": _pct(len(in_label), total_countries),
                    "covered_countries": len(covered_in_label),
                    "pct_of_covered_countries": _pct(
                        len(covered_in_label), len(covered_country_rows)
                    ),
                    "not_covered_countries": len(not_covered_in_label),
                    "pct_of_not_covered_countries": _pct(
                        len(not_covered_in_label), len(not_covered_country_rows)
                    ),
                    "coverage_pct_within_label": _pct(len(covered_in_label), len(in_label)),
                }
            )
        return rows

    income_labels = [*INCOME_GROUP_ORDER, MISSING_BREAKDOWN_LABEL]
    priority_labels = [*PRIORITY_GROUP_PRECEDENCE, MISSING_BREAKDOWN_LABEL]
    coverage = {
        "total_countries": total_countries,
        "covered_countries": len(covered_country_rows),
        "not_covered_countries": len(not_covered_country_rows),
        "covered_pct_of_total_countries": _pct(len(covered_country_rows), total_countries),
        "not_covered_pct_of_total_countries": _pct(
            len(not_covered_country_rows), total_countries
        ),
        "covered_country_names": sorted(row["country"] for row in covered_country_rows),
        "not_covered_country_names": sorted(row["country"] for row in not_covered_country_rows),
        "not_covered_country_codes": sorted(
            row["country_code"] for row in not_covered_country_rows
        ),
        "income_group_breakdown": _breakdown("income_group", income_labels),
        "priority_group_breakdown": _breakdown("priority_group", priority_labels),
        "priority_set_country_counts": {
            key: len(value) for key, value in sorted(priority_sets.items())
        },
    }
    return enriched_rows, coverage


def _uncovered_country_rows(country_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = [
        {
            "country_code": str(row["country_code"]),
            "country": str(row["country"]),
            "coverage": "Not covered",
        }
        for row in country_rows
        if not row["covered"]
    ]
    return sorted(rows, key=lambda row: (row["country_code"], row["country"]))


def _write_uncovered_countries_svg(
    uncovered_country_rows: list[dict[str, str]],
    output_path: Path,
) -> None:
    try:
        import plotly.express as px
    except ImportError as exc:
        raise RuntimeError(
            "Writing the uncovered-country SVG requires the optional pixi environment "
            "'detour-mode0-econ-stats' (plotly + kaleido). Run with "
            "`pixi run -e detour-mode0-econ-stats ...`."
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        uncovered_country_rows,
        columns=["country_code", "country", "coverage"],
    )
    fig = px.choropleth(
        df,
        locations="country_code",
        locationmode="ISO-3",
        hover_name="country",
        color="coverage",
        color_discrete_map={"Not covered": UNCOVERED_COLOUR},
    )
    fig.update_geos(
        projection_type="natural earth",
        showframe=False,
        showcoastlines=False,
        showcountries=True,
        countrycolor="white",
        showland=True,
        landcolor="#e5e7eb",
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    fig.write_image(str(output_path), format="svg", width=1200, height=650)


def _step4_population_with_economy_columns(
    conn: duckdb.DuckDBPyConnection,
) -> list[str]:
    view_columns = [
        row[0]
        for row in conn.execute(f"DESCRIBE {POPULATION_ECON_VIEW}").fetchall()
        if "unnamed" not in row[0].lower()
        and row[0] != f"{KTP_POPULATION_INDEX_COL}_1"
    ]
    if not view_columns:
        return []

    hcr_cols = [col for col in view_columns if col.startswith("hcr.")]
    explicit_name_cols: set[str] = set()
    for _, (first_col, last_col) in HCR_XLSX_NAME_COLS.items():
        explicit_name_cols.update({first_col, last_col})
    if not explicit_name_cols:
        explicit_name_cols = {
            col
            for col in hcr_cols
            if ("first" in col.lower() and "name" in col.lower())
            or ("last" in col.lower() and "name" in col.lower())
            or "firstname" in col.lower()
            or "lastname" in col.lower()
            or "familyname" in col.lower()
        }
    hcr_cols = [
        col
        for col in hcr_cols
        if col not in explicit_name_cols and "unnamed" not in col.lower()
    ]
    ordered_hcr: list[str] = []
    for col in (HCR_FILENAME_COL, HCR_ROW_COL, HCR_CATEGORY_COL):
        if col in hcr_cols:
            ordered_hcr.append(col)
    ordered_hcr += [col for col in hcr_cols if col not in ordered_hcr]

    ordered_cols = (
        [
            KTP_POPULATION_INDEX_COL,
            HCR_FILENAME_COL,
            HCR_ROW_COL,
            KTP_FIRST_NAME_COL,
            KTP_LAST_NAME_COL,
            HCR_CATEGORY_COL,
        ]
        + [
            col
            for col in ordered_hcr
            if col not in {HCR_FILENAME_COL, HCR_ROW_COL, HCR_CATEGORY_COL}
        ]
        + [
            KTP_HCR_PRIMARY_AFFILIATIONS_COL,
            KTP_HCR_SECONDARY_AFFILIATIONS_COL,
            KTP_ECONOMIES_COL,
            KTP_ECONOMIES_INCOME_GROUP_COL,
            KTP_ECONOMY_MATCH_COL,
            KTP_PRIORITY_COL,
            KTP_PRIORITY_GROUP_COL,
        ]
    )
    extra_cols = [
        col
        for col in view_columns
        if not col.startswith("hcr.") and col not in ordered_cols
    ]
    ordered_cols += extra_cols
    return [col for col in ordered_cols if col in view_columns]


def _xlsx_match_bridge_df(
    xlsx_rows_by_key: dict[str, list[dict[str, object]]],
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for source_key, inner_rows in xlsx_rows_by_key.items():
        try:
            parsed_name_key = json.loads(source_key)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed_name_key, dict):
            continue
        key_first_name = parsed_name_key.get(KTP_FIRST_NAME_COL)
        key_last_name = parsed_name_key.get(KTP_LAST_NAME_COL)
        for inner in inner_rows:
            filename = _normalize_optional_label(inner.get(KTP_FILENAME_COL))
            fragment = _normalize_optional_label(inner.get(KTP_FRAGMENT_COL))
            inner_first_name = inner.get(KTP_FIRST_NAME_COL)
            inner_last_name = inner.get(KTP_LAST_NAME_COL)
            if (
                filename is None
                or fragment is None
                or key_first_name != inner_first_name
                or key_last_name != inner_last_name
            ):
                continue
            bridge_first_name = str(inner_first_name)
            bridge_last_name = str(inner_last_name)
            dedupe_key = (
                source_key,
                filename,
                fragment,
                bridge_first_name,
                bridge_last_name,
            )
            if dedupe_key in seen:
                continue
            rows.append(
                {
                    KTP_SOURCE_KEY_COL: source_key,
                    KTP_FILENAME_COL: filename,
                    KTP_FRAGMENT_COL: fragment,
                    BRIDGE_FIRST_NAME_COL: bridge_first_name,
                    BRIDGE_LAST_NAME_COL: bridge_last_name,
                }
            )
            seen.add(dedupe_key)
    return pd.DataFrame(
        rows,
        columns=[
            KTP_SOURCE_KEY_COL,
            KTP_FILENAME_COL,
            KTP_FRAGMENT_COL,
            BRIDGE_FIRST_NAME_COL,
            BRIDGE_LAST_NAME_COL,
        ],
    )


def _fallback_population_with_economy_rows(
    xlsx_rows_by_key: dict[str, list[dict[str, object]]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for source_key, inner_rows in xlsx_rows_by_key.items():
        try:
            parsed_name_key = json.loads(source_key)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed_name_key, dict):
            continue
        key_first_name = parsed_name_key.get(KTP_FIRST_NAME_COL)
        key_last_name = parsed_name_key.get(KTP_LAST_NAME_COL)
        for inner in inner_rows:
            filename = _normalize_optional_label(inner.get(KTP_FILENAME_COL))
            fragment = _normalize_optional_label(inner.get(KTP_FRAGMENT_COL))
            inner_first_name = inner.get(KTP_FIRST_NAME_COL)
            inner_last_name = inner.get(KTP_LAST_NAME_COL)
            if (
                filename is None
                or fragment is None
                or key_first_name != inner_first_name
                or key_last_name != inner_last_name
            ):
                continue
            dedupe_key = (
                source_key,
                filename,
                fragment,
                str(inner_first_name),
                str(inner_last_name),
            )
            if dedupe_key in seen:
                continue
            rows.append({KTP_SOURCE_KEY_COL: source_key, **inner})
            seen.add(dedupe_key)
    return pd.DataFrame(rows)


def _parquet_left_join_df(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[pd.DataFrame, list[str]]:
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    source_name = None
    if PARQUET_OUTPUT_VIEW in tables:
        source_name = PARQUET_OUTPUT_VIEW
    elif PARQUET_INNERDICT_TABLE in tables:
        source_name = PARQUET_INNERDICT_TABLE
    if source_name is None:
        return pd.DataFrame(columns=[KTP_SOURCE_KEY_COL]), []

    parquet_df = conn.execute(f"SELECT * FROM {source_name}").df()
    join_cols = [col for col in PARQUET_LEFT_JOIN_COLS if col in parquet_df.columns]
    keep_cols = [col for col in [KTP_SOURCE_KEY_COL, *join_cols] if col in parquet_df.columns]
    if not keep_cols:
        return pd.DataFrame(columns=[KTP_SOURCE_KEY_COL]), []
    parquet_df = parquet_df[keep_cols].copy()
    parquet_df = parquet_df.drop_duplicates(subset=[KTP_SOURCE_KEY_COL], keep="first")
    return parquet_df, join_cols


def _write_population_with_economy_and_parquet_csv(
    conn: duckdb.DuckDBPyConnection,
    *,
    xlsx_rows_by_key: dict[str, list[dict[str, object]]],
    country_to_iso: dict[str, str],
    output_path: Path,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    base_cols = (
        _step4_population_with_economy_columns(conn)
        if POPULATION_ECON_VIEW in tables
        else []
    )
    bridge_df = _xlsx_match_bridge_df(xlsx_rows_by_key)

    if (
        POPULATION_ECON_VIEW in tables
        and HCR_FILENAME_COL in base_cols
        and HCR_ROW_COL in base_cols
    ):
        select_cols = ", ".join(f'"{col}"' for col in base_cols)
        base_df = conn.execute(f"SELECT {select_cols} FROM {POPULATION_ECON_VIEW}").df()
        if not bridge_df.empty:
            base_df = base_df.copy()
            base_df[HCR_FILENAME_COL] = base_df[HCR_FILENAME_COL].map(
                lambda value: None if pd.isna(value) else str(value)
            )
            base_df[HCR_ROW_COL] = base_df[HCR_ROW_COL].map(
                lambda value: None if pd.isna(value) else str(value)
            )
            base_df[KTP_FIRST_NAME_COL] = base_df[KTP_FIRST_NAME_COL].map(
                lambda value: None if pd.isna(value) else str(value)
            )
            base_df[KTP_LAST_NAME_COL] = base_df[KTP_LAST_NAME_COL].map(
                lambda value: None if pd.isna(value) else str(value)
            )
            bridge_df = bridge_df.copy()
            bridge_df[KTP_FILENAME_COL] = bridge_df[KTP_FILENAME_COL].astype(str)
            bridge_df[KTP_FRAGMENT_COL] = bridge_df[KTP_FRAGMENT_COL].astype(str)
            merged_df = base_df.merge(
                bridge_df,
                how="left",
                left_on=[
                    HCR_FILENAME_COL,
                    HCR_ROW_COL,
                    KTP_FIRST_NAME_COL,
                    KTP_LAST_NAME_COL,
                ],
                right_on=[
                    KTP_FILENAME_COL,
                    KTP_FRAGMENT_COL,
                    BRIDGE_FIRST_NAME_COL,
                    BRIDGE_LAST_NAME_COL,
                ],
            ).drop(
                columns=[
                    KTP_FILENAME_COL,
                    KTP_FRAGMENT_COL,
                    BRIDGE_FIRST_NAME_COL,
                    BRIDGE_LAST_NAME_COL,
                ],
                errors="ignore",
            )
        else:
            merged_df = base_df.copy()
            merged_df[KTP_SOURCE_KEY_COL] = None
    else:
        merged_df = _fallback_population_with_economy_rows(xlsx_rows_by_key)
        if not base_cols:
            fallback_base_cols = [
                KTP_FILENAME_COL,
                KTP_FRAGMENT_COL,
                KTP_FIRST_NAME_COL,
                KTP_LAST_NAME_COL,
                KTP_HCR_PRIMARY_AFFILIATIONS_COL,
                KTP_HCR_SECONDARY_AFFILIATIONS_COL,
                KTP_ECONOMIES_COL,
                KTP_ECONOMIES_INCOME_GROUP_COL,
                KTP_PRIORITY_GROUP_COL,
            ]
            base_cols = [col for col in fallback_base_cols if col in merged_df.columns]

    if KTP_ECONOMIES_COL in merged_df.columns:
        merged_df[KTP_ECONOMIES_ISO_COL] = merged_df[KTP_ECONOMIES_COL].map(
            lambda value: _iso_country_list_json(value, country_to_iso)
        )
    else:
        merged_df[KTP_ECONOMIES_ISO_COL] = _json_country_list([])

    parquet_df, parquet_join_cols = _parquet_left_join_df(conn)
    if (
        not parquet_df.empty
        and KTP_SOURCE_KEY_COL in merged_df.columns
        and KTP_SOURCE_KEY_COL in parquet_df.columns
    ):
        merged_df = merged_df.merge(parquet_df, how="left", on=KTP_SOURCE_KEY_COL)

    final_cols = [col for col in base_cols if col in merged_df.columns]
    if KTP_ECONOMIES_ISO_COL in merged_df.columns:
        final_cols.append(KTP_ECONOMIES_ISO_COL)
    final_cols.extend(
        [
            col
            for col in parquet_join_cols
            if col in merged_df.columns and col not in final_cols
        ]
    )
    if not final_cols:
        final_cols = [
            col
            for col in merged_df.columns
            if col != KTP_SOURCE_KEY_COL
        ]

    final_df = merged_df[final_cols].copy()
    final_df.to_csv(output_path, index=False)
    step4_base_columns = [col for col in base_cols if col in final_df.columns]
    return {
        "path": str(output_path),
        "rows": len(final_df),
        "step4_base_columns": final_cols[: len(step4_base_columns)],
        "parquet_prefixed_columns": [
            col for col in parquet_join_cols if col in final_df.columns
        ],
    }


def _covered_countries_from_population_rows(
    conn: duckdb.DuckDBPyConnection,
    fallback_rows_by_id: dict[tuple[str, str], set[str]],
) -> set[str]:
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    if "population_with_names_economy" in tables:
        columns = {
            row[0]
            for row in conn.execute("DESCRIBE population_with_names_economy").fetchall()
        }
        if KTP_ECONOMIES_COL in columns:
            countries: set[str] = set()
            for (value,) in conn.execute(
                f'SELECT "{KTP_ECONOMIES_COL}" FROM population_with_names_economy'
            ).fetchall():
                countries.update(_normalize_country_list(value))
            return countries

    countries = set()
    for row_countries in fallback_rows_by_id.values():
        countries.update(row_countries)
    return countries


def _build_mode0_econ_metadata(
    config: PipelineConfig,
    conn: duckdb.DuckDBPyConnection,
) -> dict[str, Any]:
    population_rows = _scalar_int(conn, "SELECT COUNT(*) FROM population_with_names_economy")

    outer_keys = [
        row[0]
        for row in conn.execute(
            f"SELECT name_key FROM {OUTERDICT_STUB_TABLE} ORDER BY name_key"
        ).fetchall()
    ]
    outerdict_keys = len(outer_keys)

    country_to_income, alias_to_country = _load_income_label_maps_from_db(conn)
    priority_sets = _priority_country_sets(country_to_income, alias_to_country)

    xlsx_rows_by_key: dict[str, list[dict[str, object]]] = defaultdict(list)
    for name_key, inner_blob in conn.execute(
        f"SELECT name_key, innerdicts FROM {XLSX_INNERDICT_TABLE}"
    ).fetchall():
        if name_key is None:
            continue
        for inner in loads_jsonlines(inner_blob or ""):
            filename = inner.get(KTP_FILENAME_COL)
            fragment = inner.get(KTP_FRAGMENT_COL)
            if filename is None or fragment is None:
                raise RuntimeError(
                    "XLSX innerdict row is missing persisted population row identity "
                    f"({KTP_FILENAME_COL}, {KTP_FRAGMENT_COL}) for {name_key!r}."
                )
            xlsx_rows_by_key[name_key].append(inner)

    mode0_selected_keys: list[str] = []
    name_countries_by_key: dict[str, set[str]] = defaultdict(set)
    name_row_income_groups_by_key: dict[str, set[str]] = defaultdict(set)
    name_row_priority_groups_by_key: dict[str, set[str]] = defaultdict(set)
    name_row_ids_by_key: dict[str, set[tuple[str, str]]] = defaultdict(set)
    selected_row_ids: set[tuple[str, str]] = set()
    selected_row_countries_by_id: dict[tuple[str, str], set[str]] = defaultdict(set)
    selected_row_income_group_by_id: dict[tuple[str, str], str | None] = {}
    selected_row_priority_group_by_id: dict[tuple[str, str], str | None] = {}

    for name_key in outer_keys:
        mode0_selected_keys.append(name_key)
        for inner in xlsx_rows_by_key.get(name_key, []):
            row_id = (str(inner[KTP_FILENAME_COL]), str(inner[KTP_FRAGMENT_COL]))
            selected_row_ids.add(row_id)
            name_row_ids_by_key[name_key].add(row_id)

            countries = set(_normalize_country_list(inner.get(KTP_ECONOMIES_COL)))
            selected_row_countries_by_id[row_id].update(countries)
            name_countries_by_key[name_key].update(countries)

            income_group = _normalize_optional_label(inner.get(KTP_ECONOMIES_INCOME_GROUP_COL))
            _record_first_non_missing(selected_row_income_group_by_id, row_id, income_group)
            if income_group is not None:
                name_row_income_groups_by_key[name_key].add(income_group)

            priority_group = _normalize_optional_label(inner.get(KTP_PRIORITY_GROUP_COL))
            _record_first_non_missing(selected_row_priority_group_by_id, row_id, priority_group)
            if priority_group is not None:
                name_row_priority_groups_by_key[name_key].add(priority_group)

    selected_names = len(mode0_selected_keys)
    mode0_selected_population_rows = len(selected_row_ids)

    selected_names_with_countries = sum(
        bool(name_countries_by_key.get(name_key)) for name_key in mode0_selected_keys
    )
    selected_names_with_income_group = sum(
        bool(name_row_income_groups_by_key.get(name_key)) for name_key in mode0_selected_keys
    )
    selected_names_with_priority_group = sum(
        bool(name_row_priority_groups_by_key.get(name_key)) for name_key in mode0_selected_keys
    )
    selected_population_rows_with_countries = sum(
        bool(selected_row_countries_by_id.get(row_id)) for row_id in selected_row_ids
    )
    selected_population_rows_with_income_group = sum(
        selected_row_income_group_by_id.get(row_id) is not None for row_id in selected_row_ids
    )
    selected_population_rows_with_priority_group = sum(
        selected_row_priority_group_by_id.get(row_id) is not None for row_id in selected_row_ids
    )

    country_cardinality = [
        len(name_countries_by_key.get(name_key, set())) for name_key in mode0_selected_keys
    ]
    country_cardinality_values = np.array(country_cardinality, dtype=float)
    card_n = int(country_cardinality_values.size)
    mean = float(country_cardinality_values.mean()) if card_n else None
    sd = float(country_cardinality_values.std(ddof=1)) if card_n > 1 else None
    se = float(sd / math.sqrt(card_n)) if card_n > 1 and sd is not None else None
    ci95_lo = float(mean - 1.96 * se) if mean is not None and se is not None else None
    ci95_hi = float(mean + 1.96 * se) if mean is not None and se is not None else None
    min_v = float(country_cardinality_values.min()) if card_n else None
    q1 = (
        float(np.quantile(country_cardinality_values, 0.25, method="linear"))
        if card_n
        else None
    )
    median = (
        float(np.quantile(country_cardinality_values, 0.5, method="linear"))
        if card_n
        else None
    )
    q3 = (
        float(np.quantile(country_cardinality_values, 0.75, method="linear"))
        if card_n
        else None
    )
    max_v = float(country_cardinality_values.max()) if card_n else None

    iqr = float(q3 - q1) if q1 is not None and q3 is not None else None
    lower_fence = float(q1 - 1.5 * iqr) if iqr is not None and q1 is not None else None
    upper_fence = float(q3 + 1.5 * iqr) if iqr is not None and q3 is not None else None
    lower_outliers = (
        int(np.sum(country_cardinality_values < lower_fence))
        if card_n and lower_fence is not None
        else 0
    )
    upper_outliers = (
        int(np.sum(country_cardinality_values > upper_fence))
        if card_n and upper_fence is not None
        else 0
    )
    total_outliers = lower_outliers + upper_outliers

    bucket_exact_0 = sum(value == 0 for value in country_cardinality)
    bucket_exact_1 = sum(value == 1 for value in country_cardinality)
    bucket_exact_2 = sum(value == 2 for value in country_cardinality)
    bucket_exact_3 = sum(value == 3 for value in country_cardinality)
    bucket_4_or_more = sum(value >= 4 for value in country_cardinality)
    if (
        bucket_exact_0
        + bucket_exact_1
        + bucket_exact_2
        + bucket_exact_3
        + bucket_4_or_more
        != selected_names
    ):
        raise RuntimeError("Bucket partition invariant failed for mode-0 country cardinality.")

    income_row_counts: dict[str, int] = defaultdict(int)
    priority_row_counts: dict[str, int] = defaultdict(int)

    for row_id in selected_row_ids:
        income_group = selected_row_income_group_by_id.get(row_id)
        if income_group is not None:
            income_row_counts[income_group] += 1
        priority_group = selected_row_priority_group_by_id.get(row_id)
        if priority_group is not None:
            priority_row_counts[priority_group] += 1

    selected_names_without_income_group = sum(
        not name_row_income_groups_by_key.get(name_key) for name_key in mode0_selected_keys
    )
    selected_names_without_priority_group = sum(
        not name_row_priority_groups_by_key.get(name_key) for name_key in mode0_selected_keys
    )
    selected_names_with_exactly_one_row_income_group = sum(
        len(name_row_income_groups_by_key.get(name_key, set())) == 1
        for name_key in mode0_selected_keys
    )
    selected_names_with_multiple_row_income_groups = sum(
        len(name_row_income_groups_by_key.get(name_key, set())) > 1
        for name_key in mode0_selected_keys
    )
    selected_names_with_exactly_one_row_priority_group = sum(
        len(name_row_priority_groups_by_key.get(name_key, set())) == 1
        for name_key in mode0_selected_keys
    )
    selected_names_with_multiple_row_priority_groups = sum(
        len(name_row_priority_groups_by_key.get(name_key, set())) > 1
        for name_key in mode0_selected_keys
    )
    selected_rows_missing_income_group = (
        mode0_selected_population_rows - selected_population_rows_with_income_group
    )
    selected_rows_missing_priority_group = (
        mode0_selected_population_rows - selected_population_rows_with_priority_group
    )
    selected_row_lower_tier_income_group_by_id: dict[tuple[str, str], str | None] = {}
    lower_tier_income_row_counts: dict[str, int] = defaultdict(int)

    for row_id in selected_row_ids:
        lower_tier_income_group = _preferred_income_group_for_countries(
            selected_row_countries_by_id.get(row_id, set()),
            country_to_income,
            INCOME_GROUP_ORDER_LOW_FIRST,
        )
        selected_row_lower_tier_income_group_by_id[row_id] = lower_tier_income_group
        if lower_tier_income_group is not None:
            lower_tier_income_row_counts[lower_tier_income_group] += 1

    selected_rows_missing_lower_tier_income_group = sum(
        selected_row_lower_tier_income_group_by_id.get(row_id) is None
        for row_id in selected_row_ids
    )

    income_breakdown = [
        {
            "income_group": label,
            "selected_population_rows": income_row_counts.get(label, 0),
            "pct_of_selected_population_rows": _pct(
                income_row_counts.get(label, 0), mode0_selected_population_rows
            ),
            "pct_of_non_missing_selected_population_rows": _pct(
                income_row_counts.get(label, 0), selected_population_rows_with_income_group
            ),
        }
        for label in INCOME_GROUP_ORDER
    ]
    income_breakdown.append(
        {
            "income_group": MISSING_BREAKDOWN_LABEL,
            "selected_population_rows": selected_rows_missing_income_group,
            "pct_of_selected_population_rows": _pct(
                selected_rows_missing_income_group, mode0_selected_population_rows
            ),
            "pct_of_non_missing_selected_population_rows": None,
        }
    )
    income_breakdown_lower_tier_preferred = [
        {
            "income_group": label,
            "selected_population_rows": lower_tier_income_row_counts.get(label, 0),
            "pct_of_selected_population_rows": _pct(
                lower_tier_income_row_counts.get(label, 0), mode0_selected_population_rows
            ),
            "pct_of_non_missing_selected_population_rows": _pct(
                lower_tier_income_row_counts.get(label, 0),
                mode0_selected_population_rows - selected_rows_missing_lower_tier_income_group,
            ),
        }
        for label in INCOME_GROUP_ORDER_LOW_FIRST
    ]
    income_breakdown_lower_tier_preferred.append(
        {
            "income_group": MISSING_BREAKDOWN_LABEL,
            "selected_population_rows": selected_rows_missing_lower_tier_income_group,
            "pct_of_selected_population_rows": _pct(
                selected_rows_missing_lower_tier_income_group, mode0_selected_population_rows
            ),
            "pct_of_non_missing_selected_population_rows": None,
        }
    )

    priority_breakdown = [
        {
            "priority_group": label,
            "selected_population_rows": priority_row_counts.get(label, 0),
            "pct_of_selected_population_rows": _pct(
                priority_row_counts.get(label, 0), mode0_selected_population_rows
            ),
            "pct_of_non_missing_selected_population_rows": _pct(
                priority_row_counts.get(label, 0), selected_population_rows_with_priority_group
            ),
        }
        for label in PRIORITY_GROUP_PRECEDENCE
    ]
    priority_breakdown.append(
        {
            "priority_group": MISSING_BREAKDOWN_LABEL,
            "selected_population_rows": selected_rows_missing_priority_group,
            "pct_of_selected_population_rows": _pct(
                selected_rows_missing_priority_group, mode0_selected_population_rows
            ),
            "pct_of_non_missing_selected_population_rows": None,
        }
    )

    name_derived_income_groups_by_key: dict[str, set[str]] = {}
    name_derived_priority_groups_by_key: dict[str, set[str]] = {}
    name_final_income_group_high_by_key: dict[str, str] = {}
    name_final_income_group_low_by_key: dict[str, str] = {}
    name_final_priority_group_high_by_key: dict[str, str] = {}
    name_final_priority_group_low_by_key: dict[str, str] = {}
    derived_name_group_breakdown_higher_preferred: list[dict[str, Any]] = []
    derived_name_group_breakdown_lower_preferred: list[dict[str, Any]] = []

    higher_income_name_counts: dict[str, int] = defaultdict(int)
    lower_income_name_counts: dict[str, int] = defaultdict(int)
    higher_priority_name_counts: dict[str, int] = defaultdict(int)
    lower_priority_name_counts: dict[str, int] = defaultdict(int)

    for name_key in mode0_selected_keys:
        countries = name_countries_by_key.get(name_key, set())
        derived_income_groups = {
            income_group
            for country in countries
            if (income_group := country_to_income.get(country)) is not None
        }
        derived_priority_groups = {
            _priority_group_for_country(country, priority_sets) for country in countries
        }
        name_derived_income_groups_by_key[name_key] = derived_income_groups
        name_derived_priority_groups_by_key[name_key] = derived_priority_groups

        higher_income_label = _preferred_income_group_for_countries(
            countries,
            country_to_income,
            INCOME_GROUP_ORDER,
        )
        lower_income_label = _preferred_income_group_for_countries(
            countries,
            country_to_income,
            INCOME_GROUP_ORDER_LOW_FIRST,
        )
        higher_priority_label = _preferred_priority_group_for_countries(
            countries,
            priority_sets,
            PRIORITY_GROUP_PRECEDENCE,
        )
        lower_priority_label = _preferred_priority_group_for_countries(
            countries,
            priority_sets,
            PRIORITY_GROUP_PRECEDENCE_LOW_FIRST,
        )

        name_final_income_group_high_by_key[name_key] = (
            higher_income_label if higher_income_label is not None else MISSING_BREAKDOWN_LABEL
        )
        name_final_income_group_low_by_key[name_key] = (
            lower_income_label if lower_income_label is not None else MISSING_BREAKDOWN_LABEL
        )
        name_final_priority_group_high_by_key[name_key] = higher_priority_label
        name_final_priority_group_low_by_key[name_key] = lower_priority_label

        higher_income_name_counts[name_final_income_group_high_by_key[name_key]] += 1
        lower_income_name_counts[name_final_income_group_low_by_key[name_key]] += 1
        higher_priority_name_counts[higher_priority_label] += 1
        lower_priority_name_counts[lower_priority_label] += 1

    for label in [*INCOME_GROUP_ORDER, MISSING_BREAKDOWN_LABEL]:
        derived_name_group_breakdown_higher_preferred.append(
            {
                "group_type": "Income group",
                "label": label,
                "selected_names": higher_income_name_counts.get(label, 0),
                "pct_of_mode0_selected_names": _pct(
                    higher_income_name_counts.get(label, 0), selected_names
                ),
            }
        )
    for label in [*PRIORITY_GROUP_PRECEDENCE, MISSING_BREAKDOWN_LABEL]:
        derived_name_group_breakdown_higher_preferred.append(
            {
                "group_type": "Priority group",
                "label": label,
                "selected_names": higher_priority_name_counts.get(label, 0),
                "pct_of_mode0_selected_names": _pct(
                    higher_priority_name_counts.get(label, 0), selected_names
                ),
            }
        )

    for label in [*INCOME_GROUP_ORDER_LOW_FIRST, MISSING_BREAKDOWN_LABEL]:
        derived_name_group_breakdown_lower_preferred.append(
            {
                "group_type": "Income group",
                "label": label,
                "selected_names": lower_income_name_counts.get(label, 0),
                "pct_of_mode0_selected_names": _pct(
                    lower_income_name_counts.get(label, 0), selected_names
                ),
            }
        )
    for label in [*PRIORITY_GROUP_PRECEDENCE_LOW_FIRST, MISSING_BREAKDOWN_LABEL]:
        derived_name_group_breakdown_lower_preferred.append(
            {
                "group_type": "Priority group",
                "label": label,
                "selected_names": lower_priority_name_counts.get(label, 0),
                "pct_of_mode0_selected_names": _pct(
                    lower_priority_name_counts.get(label, 0), selected_names
                ),
            }
        )

    multi_country_names = 0
    multi_country_different_income_groups = 0
    multi_country_different_priority_groups = 0
    for name_key in mode0_selected_keys:
        countries = name_countries_by_key.get(name_key, set())
        if len(countries) <= 1:
            continue
        multi_country_names += 1
        derived_income_groups = {
            income_group
            for country in countries
            if (income_group := country_to_income.get(country)) is not None
        }
        derived_priority_groups = {
            _priority_group_for_country(country, priority_sets) for country in countries
        }
        if len(derived_income_groups) > 1:
            multi_country_different_income_groups += 1
        if len(derived_priority_groups) > 1:
            multi_country_different_priority_groups += 1

    researcher_profiles: list[dict[str, Any]] = []
    for name_key in mode0_selected_keys:
        rows = xlsx_rows_by_key.get(name_key, [])
        sorted_countries = sorted(name_countries_by_key.get(name_key, set()))
        primary_affiliations = sorted(
            {
                value
                for row in rows
                if (value := _normalize_optional_label(row.get(KTP_HCR_PRIMARY_AFFILIATIONS_COL)))
                is not None
            }
        )
        secondary_affiliations = sorted(
            {
                value
                for row in rows
                if (
                    value := _normalize_optional_label(row.get(KTP_HCR_SECONDARY_AFFILIATIONS_COL))
                )
                is not None
            }
        )
        derived_country_income_groups = _ordered_labels(
            name_derived_income_groups_by_key.get(name_key, set()),
            INCOME_GROUP_ORDER_LOW_FIRST,
        )
        derived_country_priority_groups = _ordered_labels(
            name_derived_priority_groups_by_key.get(name_key, set()),
            PRIORITY_GROUP_PRECEDENCE,
        )
        researcher_profiles.append(
            {
                "name_key": name_key,
                "researcher_name": _display_name(name_key, rows),
                "selected_population_row_count": len(name_row_ids_by_key.get(name_key, set())),
                "country_count": len(sorted_countries),
                "countries": sorted_countries,
                "primary_affiliations": primary_affiliations,
                "secondary_affiliations": secondary_affiliations,
                "row_income_groups": _ordered_labels(
                    name_row_income_groups_by_key.get(name_key, set()),
                    INCOME_GROUP_ORDER,
                ),
                "lower_tier_row_income_groups": _ordered_labels(
                    {
                        lower_tier_label
                        for row_id in name_row_ids_by_key.get(name_key, set())
                        if (
                            lower_tier_label := selected_row_lower_tier_income_group_by_id.get(
                                row_id
                            )
                        ) is not None
                    },
                    INCOME_GROUP_ORDER_LOW_FIRST,
                ),
                "derived_country_income_groups": derived_country_income_groups,
                "derived_country_priority_groups": derived_country_priority_groups,
                "final_income_group_high": name_final_income_group_high_by_key[name_key],
                "final_income_group_low": name_final_income_group_low_by_key[name_key],
                "final_priority_group_high": name_final_priority_group_high_by_key[name_key],
                "final_priority_group_low": name_final_priority_group_low_by_key[name_key],
                "row_priority_groups": _ordered_labels(
                    name_row_priority_groups_by_key.get(name_key, set()),
                    PRIORITY_GROUP_PRECEDENCE,
                ),
            }
        )

    researcher_profiles.sort(key=lambda row: (row["researcher_name"], row["name_key"]))
    researcher_detail_highlights = {
        "any_low_income_affiliated_country": [
            row
            for row in researcher_profiles
            if OGHIST_INCOME_LABELS["L"] in row["derived_country_income_groups"]
        ],
        "missing_income_group": [
            row
            for row in researcher_profiles
            if row["final_income_group_high"] == MISSING_BREAKDOWN_LABEL
        ],
        "four_or_more_countries": [
            row for row in researcher_profiles if row["country_count"] >= 4
        ],
    }

    covered_countries = _covered_countries_from_population_rows(
        conn,
        selected_row_countries_by_id,
    )
    world_bank_country_rows, world_bank_metadata = _load_world_bank_country_rows(
        config,
        priority_sets=priority_sets,
    )
    country_to_iso = {
        str(row["country"]): str(row["country_code"])
        for row in world_bank_country_rows
    }
    country_rows_with_coverage, country_coverage = _country_coverage_rows(
        country_rows=world_bank_country_rows,
        covered_countries=covered_countries,
        priority_sets=priority_sets,
    )
    uncovered_country_rows = _uncovered_country_rows(country_rows_with_coverage)
    _write_uncovered_countries_svg(uncovered_country_rows, UNCOVERED_COUNTRIES_SVG_PATH)
    population_with_economy_and_parquet_csv = _write_population_with_economy_and_parquet_csv(
        conn,
        xlsx_rows_by_key=xlsx_rows_by_key,
        country_to_iso=country_to_iso,
        output_path=POPULATION_WITH_ECONOMY_PARQUET_CSV_PATH,
    )

    return {
        "detour_id": DETOUR_ID,
        "mode": MODE,
        "mode_description": CARD_BUILD_SUBSET_DESCRIPTIONS[MODE],
        "db_file": _db_file_from_pragma(conn),
        "tables_used": [OUTERDICT_STUB_TABLE, XLSX_INNERDICT_TABLE],
        "world_bank_country_resource": world_bank_metadata,
        "country_coverage": country_coverage,
        "uncovered_countries": uncovered_country_rows,
        "country_coverage_map_svg": str(UNCOVERED_COUNTRIES_SVG_PATH),
        "population_with_economy_parquet_csv": population_with_economy_and_parquet_csv,
        "priority_group_definitions": PRIORITY_GROUP_RULES,
        "counts": {
            "population_rows": population_rows,
            "outerdict_keys": outerdict_keys,
            "mode0_selected_names": selected_names,
            "mode0_selected_pct_of_outerdict_keys": _pct(selected_names, outerdict_keys),
            "mode0_selected_population_rows": mode0_selected_population_rows,
            "mode0_selected_pct_of_population_rows": _pct(
                mode0_selected_population_rows, population_rows
            ),
            "selected_names_with_countries": selected_names_with_countries,
            "selected_names_with_countries_pct_of_mode0": _pct(
                selected_names_with_countries, selected_names
            ),
            "selected_names_with_income_group": selected_names_with_income_group,
            "selected_names_with_income_group_pct_of_mode0": _pct(
                selected_names_with_income_group, selected_names
            ),
            "selected_names_with_priority_group": selected_names_with_priority_group,
            "selected_names_with_priority_group_pct_of_mode0": _pct(
                selected_names_with_priority_group, selected_names
            ),
            "selected_population_rows_with_countries": selected_population_rows_with_countries,
            "selected_population_rows_with_countries_pct_of_population_rows": _pct(
                selected_population_rows_with_countries, population_rows
            ),
            "selected_population_rows_with_income_group": (
                selected_population_rows_with_income_group
            ),
            "selected_population_rows_with_income_group_pct_of_population_rows": _pct(
                selected_population_rows_with_income_group, population_rows
            ),
            "selected_population_rows_with_priority_group": (
                selected_population_rows_with_priority_group
            ),
            "selected_population_rows_with_priority_group_pct_of_population_rows": _pct(
                selected_population_rows_with_priority_group, population_rows
            ),
        },
        "country_cardinality_distribution": {
            "n": card_n,
            "mean": mean,
            "sd": sd,
            "se": se,
            "mean_ci95_lo": ci95_lo,
            "mean_ci95_hi": ci95_hi,
            "min": min_v,
            "q1": q1,
            "median": median,
            "q3": q3,
            "max": max_v,
        },
        "country_cardinality_outliers_tukey": {
            "iqr": iqr,
            "lower_fence": lower_fence,
            "upper_fence": upper_fence,
            "lower_outliers": lower_outliers,
            "upper_outliers": upper_outliers,
            "total_outliers": total_outliers,
            "outlier_pct_of_selected_names": _pct(total_outliers, selected_names),
        },
        "country_cardinality_buckets": {
            "exact_0": bucket_exact_0,
            "exact_1": bucket_exact_1,
            "exact_2": bucket_exact_2,
            "exact_3": bucket_exact_3,
            "exact_4_or_more": bucket_4_or_more,
            "exact_0_pct_of_mode0": _pct(bucket_exact_0, selected_names),
            "exact_1_pct_of_mode0": _pct(bucket_exact_1, selected_names),
            "exact_2_pct_of_mode0": _pct(bucket_exact_2, selected_names),
            "exact_3_pct_of_mode0": _pct(bucket_exact_3, selected_names),
            "exact_4_or_more_pct_of_mode0": _pct(bucket_4_or_more, selected_names),
        },
        "income_group_breakdown": income_breakdown,
        "income_group_breakdown_lower_tier_preferred": income_breakdown_lower_tier_preferred,
        "priority_group_breakdown": priority_breakdown,
        "derived_name_group_breakdown_higher_preferred": (
            derived_name_group_breakdown_higher_preferred
        ),
        "derived_name_group_breakdown_lower_preferred": (
            derived_name_group_breakdown_lower_preferred
        ),
        "multi_country_divergence": {
            "multi_country_names": multi_country_names,
            "multi_country_pct_of_mode0": _pct(multi_country_names, selected_names),
            "different_income_groups": multi_country_different_income_groups,
            "different_income_groups_pct_of_mode0": _pct(
                multi_country_different_income_groups, selected_names
            ),
            "different_income_groups_pct_of_multi_country": _pct(
                multi_country_different_income_groups, multi_country_names
            ),
            "different_priority_groups": multi_country_different_priority_groups,
            "different_priority_groups_pct_of_mode0": _pct(
                multi_country_different_priority_groups, selected_names
            ),
            "different_priority_groups_pct_of_multi_country": _pct(
                multi_country_different_priority_groups, multi_country_names
            ),
        },
        "label_coverage_consistency_audit": {
            "selected_names_without_income_group": selected_names_without_income_group,
            "selected_names_without_priority_group": selected_names_without_priority_group,
            "selected_names_with_exactly_one_row_income_group": (
                selected_names_with_exactly_one_row_income_group
            ),
            "selected_names_with_multiple_row_income_groups": (
                selected_names_with_multiple_row_income_groups
            ),
            "selected_names_with_exactly_one_row_priority_group": (
                selected_names_with_exactly_one_row_priority_group
            ),
            "selected_names_with_multiple_row_priority_groups": (
                selected_names_with_multiple_row_priority_groups
            ),
            "selected_rows_missing_income_group": selected_rows_missing_income_group,
            "selected_rows_missing_priority_group": selected_rows_missing_priority_group,
        },
        "researcher_detail_highlights": researcher_detail_highlights,
    }


def _print_summary(metadata: dict[str, Any]) -> None:
    counts = metadata["counts"]
    country_coverage = metadata["country_coverage"]
    dist = metadata["country_cardinality_distribution"]
    buckets = metadata["country_cardinality_buckets"]
    income_breakdown = metadata["income_group_breakdown"]
    income_breakdown_lower_tier_preferred = metadata["income_group_breakdown_lower_tier_preferred"]
    priority_breakdown = metadata["priority_group_breakdown"]
    derived_name_group_breakdown_higher_preferred = metadata[
        "derived_name_group_breakdown_higher_preferred"
    ]
    derived_name_group_breakdown_lower_preferred = metadata[
        "derived_name_group_breakdown_lower_preferred"
    ]
    divergence = metadata["multi_country_divergence"]
    audit = metadata["label_coverage_consistency_audit"]
    outliers = metadata["country_cardinality_outliers_tukey"]
    highlights = metadata["researcher_detail_highlights"]

    console.print("[cyan]Mode-0 Economy Stats Detour (read-only)[/cyan]")
    console.print(f"[white]DB: {metadata['db_file']}[/white]")
    console.print(f"[white]Mode {metadata['mode']}: {metadata['mode_description']}[/white]")
    console.print(
        "[white]Tables used: "
        + ", ".join(str(name) for name in metadata["tables_used"])
        + "[/white]"
    )
    console.print(
        "[white]World Bank country resource: "
        f"{metadata['world_bank_country_resource']['resource_name']} "
        f"({metadata['world_bank_country_resource']['resource_hash']})[/white]"
    )
    console.print(
        "[white]Uncovered countries SVG: "
        f"{metadata['country_coverage_map_svg']}[/white]"
    )
    console.print(
        "[white]Population+parquet CSV: "
        f"{metadata['population_with_economy_parquet_csv']['path']}[/white]"
    )
    excluded_former_economies = metadata["world_bank_country_resource"].get(
        "excluded_former_economies",
        [],
    )
    if excluded_former_economies:
        console.print(
            "[white]Excluded former economies: "
            f"{len(excluded_former_economies)}[/white]"
        )
        excluded_table = Table(title="Excluded Former Economies", box=box.SIMPLE)
        excluded_table.add_column("Code", style="cyan")
        excluded_table.add_column("Country", style="white")
        for row in excluded_former_economies:
            excluded_table.add_row(row["country_code"], row["country"])
        console.print(excluded_table)
    missing_income_group_countries = metadata["world_bank_country_resource"].get(
        "missing_income_group_countries",
        [],
    )
    if missing_income_group_countries:
        missing_income_table = Table(
            title=f"Countries with Missing {WORLD_BANK_INCOME_FISCAL_YEAR} Economy Category",
            box=box.SIMPLE,
        )
        missing_income_table.add_column("ISO-3", style="cyan")
        missing_income_table.add_column("Country", style="white")
        for row in missing_income_group_countries:
            missing_income_table.add_row(row["country_code"], row["country"])
        console.print(missing_income_table)

    definitions_table = Table(title="Priority-Group Definitions (Step-4 Rules)", box=box.SIMPLE)
    definitions_table.add_column("Label", style="cyan")
    definitions_table.add_column("Rule", style="white")
    for definition in metadata["priority_group_definitions"]:
        definitions_table.add_row(definition["label"], definition["rule"])
    console.print(definitions_table)
    console.print("[white]Priority-group precedence:[/white]")
    for definition in metadata["priority_group_definitions"]:
        console.print(f"[white]- {definition['label']}: {definition['rule']}[/white]")

    counts_table = Table(title="Selection Counts", box=box.SIMPLE)
    counts_table.add_column("Metric", style="cyan")
    counts_table.add_column("Value", style="magenta", justify="right")
    counts_table.add_row("Population rows", f"{counts['population_rows']:,}")
    counts_table.add_row("OuterDict keys (step 6)", f"{counts['outerdict_keys']:,}")
    counts_table.add_row("Mode-0 selected names", f"{counts['mode0_selected_names']:,}")
    counts_table.add_row(
        "Mode-0 selected % of OuterDict keys",
        _fmt_pct(counts["mode0_selected_pct_of_outerdict_keys"]),
    )
    counts_table.add_row(
        "Population rows containing mode-0 selected names",
        f"{counts['mode0_selected_population_rows']:,}",
    )
    counts_table.add_row(
        "Mode-0 selected % of population rows",
        _fmt_pct(counts["mode0_selected_pct_of_population_rows"]),
    )
    counts_table.add_row(
        "Selected names with at least one country",
        f"{counts['selected_names_with_countries']:,}",
    )
    counts_table.add_row(
        "Selected names with at least one country % of mode-0",
        _fmt_pct(counts["selected_names_with_countries_pct_of_mode0"]),
    )
    counts_table.add_row(
        "Selected names with at least one income-group label",
        f"{counts['selected_names_with_income_group']:,}",
    )
    counts_table.add_row(
        "Selected names with income-group label % of mode-0",
        _fmt_pct(counts["selected_names_with_income_group_pct_of_mode0"]),
    )
    counts_table.add_row(
        "Selected names with at least one priority-group label",
        f"{counts['selected_names_with_priority_group']:,}",
    )
    counts_table.add_row(
        "Selected names with priority-group label % of mode-0",
        _fmt_pct(counts["selected_names_with_priority_group_pct_of_mode0"]),
    )
    counts_table.add_row(
        "Selected population rows with at least one country",
        f"{counts['selected_population_rows_with_countries']:,}",
    )
    counts_table.add_row(
        "Selected rows with countries % of population rows",
        _fmt_pct(counts["selected_population_rows_with_countries_pct_of_population_rows"]),
    )
    counts_table.add_row(
        "Selected population rows with non-missing income-group label",
        f"{counts['selected_population_rows_with_income_group']:,}",
    )
    counts_table.add_row(
        "Selected rows with income-group label % of population rows",
        _fmt_pct(counts["selected_population_rows_with_income_group_pct_of_population_rows"]),
    )
    counts_table.add_row(
        "Selected population rows with non-missing priority-group label",
        f"{counts['selected_population_rows_with_priority_group']:,}",
    )
    counts_table.add_row(
        "Selected rows with priority-group label % of population rows",
        _fmt_pct(counts["selected_population_rows_with_priority_group_pct_of_population_rows"]),
    )
    console.print(counts_table)

    country_scope_table = Table(title="Country Coverage Scope", box=box.SIMPLE)
    country_scope_table.add_column("Metric", style="cyan")
    country_scope_table.add_column("Value", style="magenta", justify="right")
    country_scope_table.add_row(
        "World Bank countries",
        f"{country_coverage['total_countries']:,}",
    )
    country_scope_table.add_row(
        "Covered in any population row",
        f"{country_coverage['covered_countries']:,}",
    )
    country_scope_table.add_row(
        "Covered % of World Bank countries",
        _fmt_pct(country_coverage["covered_pct_of_total_countries"]),
    )
    country_scope_table.add_row(
        "Not covered in any population row",
        f"{country_coverage['not_covered_countries']:,}",
    )
    country_scope_table.add_row(
        "Not covered % of World Bank countries",
        _fmt_pct(country_coverage["not_covered_pct_of_total_countries"]),
    )
    console.print(country_scope_table)

    def _print_country_coverage_breakdown(title: str, rows: list[dict[str, Any]]) -> None:
        table = Table(title=title, box=box.SIMPLE)
        table.add_column("Label", style="cyan")
        table.add_column("Total", style="magenta", justify="right")
        table.add_column("% total", style="magenta", justify="right")
        table.add_column("Covered", style="magenta", justify="right")
        table.add_column("% covered", style="magenta", justify="right")
        table.add_column("Not covered", style="magenta", justify="right")
        table.add_column("% not covered", style="magenta", justify="right")
        table.add_column("Coverage within label", style="magenta", justify="right")
        for row in rows:
            table.add_row(
                row["label"],
                f"{row['total_countries']:,}",
                _fmt_pct(row["pct_of_total_countries"]),
                f"{row['covered_countries']:,}",
                _fmt_pct(row["pct_of_covered_countries"]),
                f"{row['not_covered_countries']:,}",
                _fmt_pct(row["pct_of_not_covered_countries"]),
                _fmt_pct(row["coverage_pct_within_label"]),
            )
        console.print(table)

    _print_country_coverage_breakdown(
        "Country Coverage by Economy Category",
        country_coverage["income_group_breakdown"],
    )
    _print_country_coverage_breakdown(
        "Country Coverage by Priority Category",
        country_coverage["priority_group_breakdown"],
    )

    uncovered_table = Table(
        title="Uncovered Countries Shown in SVG",
        box=box.SIMPLE,
    )
    uncovered_table.add_column("ISO-3", style="cyan")
    uncovered_table.add_column("Country", style="white")
    for row in metadata["uncovered_countries"]:
        uncovered_table.add_row(row["country_code"], row["country"])
    console.print(uncovered_table)

    dist_table = Table(
        title="Country Cardinality Distribution (Mode-0 Selected Names)",
        box=box.SIMPLE,
    )
    dist_table.add_column("Metric", style="cyan")
    dist_table.add_column("Value", style="magenta", justify="right")
    dist_table.add_row("N (selected names)", f"{dist['n']:,}")
    dist_table.add_row("Mean", _fmt_float(dist["mean"]))
    dist_table.add_row(
        "95% CI (mean)",
        f"[{_fmt_float(dist['mean_ci95_lo'])}, {_fmt_float(dist['mean_ci95_hi'])}]",
    )
    dist_table.add_row("SD", _fmt_float(dist["sd"]))
    dist_table.add_row("SE", _fmt_float(dist["se"]))
    dist_table.add_row("Min", _fmt_float(dist["min"]))
    dist_table.add_row("Q1", _fmt_float(dist["q1"]))
    dist_table.add_row("Median", _fmt_float(dist["median"]))
    dist_table.add_row("Q3", _fmt_float(dist["q3"]))
    dist_table.add_row("Max", _fmt_float(dist["max"]))
    console.print(dist_table)

    bucket_table = Table(
        title="Country Cardinality Buckets (Mode-0 Selected Names)",
        box=box.SIMPLE,
    )
    bucket_table.add_column("Bucket", style="cyan")
    bucket_table.add_column("Raw", style="magenta", justify="right")
    bucket_table.add_column("% of mode-0", style="magenta", justify="right")
    bucket_table.add_row(
        "0 countries",
        f"{buckets['exact_0']:,}",
        _fmt_pct(buckets["exact_0_pct_of_mode0"]),
    )
    bucket_table.add_row(
        "1 country",
        f"{buckets['exact_1']:,}",
        _fmt_pct(buckets["exact_1_pct_of_mode0"]),
    )
    bucket_table.add_row(
        "2 countries",
        f"{buckets['exact_2']:,}",
        _fmt_pct(buckets["exact_2_pct_of_mode0"]),
    )
    bucket_table.add_row(
        "3 countries",
        f"{buckets['exact_3']:,}",
        _fmt_pct(buckets["exact_3_pct_of_mode0"]),
    )
    bucket_table.add_row(
        "4+ countries",
        f"{buckets['exact_4_or_more']:,}",
        _fmt_pct(buckets["exact_4_or_more_pct_of_mode0"]),
    )
    console.print(bucket_table)

    console.print(
        "[white]Persisted row-label tables below are row-level only. "
        "Exclusive one-label-per-name counts appear in the derived combined-country tables "
        "that follow.[/white]"
    )

    income_table = Table(title="Income-Group Breakdown (Selected Population Rows)", box=box.SIMPLE)
    income_table.add_column("Income group", style="cyan")
    income_table.add_column("Rows", style="magenta", justify="right")
    income_table.add_column("% selected rows", style="magenta", justify="right")
    for row in income_breakdown:
        income_table.add_row(
            row["income_group"],
            f"{row['selected_population_rows']:,}",
            _fmt_pct(row["pct_of_selected_population_rows"]),
        )
    console.print(income_table)
    console.print(
        "[white]Lower-tier preferred income label uses affiliated-country income groups "
        "with precedence: Low > Lower middle > Upper middle > High.[/white]"
    )
    income_lower_table = Table(
        title="Income-Group Breakdown (Selected Population Rows; Lower-Tier Preferred)",
        box=box.SIMPLE,
    )
    income_lower_table.add_column("Income group", style="cyan")
    income_lower_table.add_column("Rows", style="magenta", justify="right")
    income_lower_table.add_column("% selected rows", style="magenta", justify="right")
    for row in income_breakdown_lower_tier_preferred:
        income_lower_table.add_row(
            row["income_group"],
            f"{row['selected_population_rows']:,}",
            _fmt_pct(row["pct_of_selected_population_rows"]),
        )
    console.print(income_lower_table)

    priority_table = Table(
        title="Priority-Group Breakdown (Selected Population Rows)",
        box=box.SIMPLE,
    )
    priority_table.add_column("Priority group", style="cyan")
    priority_table.add_column("Rows", style="magenta", justify="right")
    priority_table.add_column("% selected rows", style="magenta", justify="right")
    for row in priority_breakdown:
        priority_table.add_row(
            row["priority_group"],
            f"{row['selected_population_rows']:,}",
            _fmt_pct(row["pct_of_selected_population_rows"]),
        )
    console.print(priority_table)

    console.print(
        "[white]Derived name-level tables below combine distinct affiliated countries across "
        "all selected rows for each KTP name and then assign exactly one final label per "
        "name. These counts sum to Mode-0 selected names.[/white]"
    )
    derived_higher_table = Table(
        title="Derived Final Name-Level Groups (Combined Countries; Higher Preferred)",
        box=box.SIMPLE,
    )
    derived_higher_table.add_column("Group type", style="cyan")
    derived_higher_table.add_column("Label", style="white")
    derived_higher_table.add_column("Selected names", style="magenta", justify="right")
    derived_higher_table.add_column("% mode-0 names", style="magenta", justify="right")
    for row in derived_name_group_breakdown_higher_preferred:
        derived_higher_table.add_row(
            row["group_type"],
            row["label"],
            f"{row['selected_names']:,}",
            _fmt_pct(row["pct_of_mode0_selected_names"]),
        )
    console.print(derived_higher_table)

    derived_lower_table = Table(
        title="Derived Final Name-Level Groups (Combined Countries; Lower Preferred)",
        box=box.SIMPLE,
    )
    derived_lower_table.add_column("Group type", style="cyan")
    derived_lower_table.add_column("Label", style="white")
    derived_lower_table.add_column("Selected names", style="magenta", justify="right")
    derived_lower_table.add_column("% mode-0 names", style="magenta", justify="right")
    for row in derived_name_group_breakdown_lower_preferred:
        derived_lower_table.add_row(
            row["group_type"],
            row["label"],
            f"{row['selected_names']:,}",
            _fmt_pct(row["pct_of_mode0_selected_names"]),
        )
    console.print(derived_lower_table)

    divergence_table = Table(
        title="Multi-Country Divergence (Mode-0 Selected Names)",
        box=box.SIMPLE,
    )
    divergence_table.add_column("Metric", style="cyan")
    divergence_table.add_column("Value", style="magenta", justify="right")
    divergence_table.add_row(
        "Selected names with >1 countries",
        f"{divergence['multi_country_names']:,}",
    )
    divergence_table.add_row(
        "Selected names with >1 countries % of mode-0",
        _fmt_pct(divergence["multi_country_pct_of_mode0"]),
    )
    divergence_table.add_row(
        "Selected names with >1 countries and >1 derived income groups",
        f"{divergence['different_income_groups']:,}",
    )
    divergence_table.add_row(
        "Different derived income groups % of mode-0",
        _fmt_pct(divergence["different_income_groups_pct_of_mode0"]),
    )
    divergence_table.add_row(
        "Different derived income groups % of multi-country selected names",
        _fmt_pct(divergence["different_income_groups_pct_of_multi_country"]),
    )
    divergence_table.add_row(
        "Selected names with >1 countries and >1 derived priority groups",
        f"{divergence['different_priority_groups']:,}",
    )
    divergence_table.add_row(
        "Different derived priority groups % of mode-0",
        _fmt_pct(divergence["different_priority_groups_pct_of_mode0"]),
    )
    divergence_table.add_row(
        "Different derived priority groups % of multi-country selected names",
        _fmt_pct(divergence["different_priority_groups_pct_of_multi_country"]),
    )
    console.print(divergence_table)

    low_income_table = Table(
        title=(
            "Researcher Details: Any Low-Income Affiliated Country "
            f"({len(highlights['any_low_income_affiliated_country'])} names)"
        ),
        box=box.SIMPLE,
    )
    low_income_table.add_column("Researcher", style="cyan")
    low_income_table.add_column("Primary affiliations", style="white")
    low_income_table.add_column("Countries", style="white")
    low_income_table.add_column("Derived country income groups", style="magenta")
    low_income_table.add_column("Final income high", style="magenta")
    low_income_table.add_column("Final income low", style="magenta")
    for row in highlights["any_low_income_affiliated_country"]:
        low_income_table.add_row(
            row["researcher_name"],
            _join_display(row["primary_affiliations"]),
            _join_display(row["countries"], delimiter=", "),
            _join_display(row["derived_country_income_groups"], delimiter=", "),
            row["final_income_group_high"],
            row["final_income_group_low"],
        )
    console.print(low_income_table)

    missing_income_table = Table(
        title=(
            "Researcher Details: Missing Income Group "
            f"({len(highlights['missing_income_group'])} names)"
        ),
        box=box.SIMPLE,
    )
    missing_income_table.add_column("Researcher", style="cyan")
    missing_income_table.add_column("Primary affiliations", style="white")
    missing_income_table.add_column("Secondary affiliations", style="white")
    missing_income_table.add_column("Countries", style="white")
    missing_income_table.add_column("Final priority high", style="magenta")
    missing_income_table.add_column("Final priority low", style="magenta")
    for row in highlights["missing_income_group"]:
        missing_income_table.add_row(
            row["researcher_name"],
            _join_display(row["primary_affiliations"]),
            _join_display(row["secondary_affiliations"]),
            _join_display(row["countries"], delimiter=", "),
            row["final_priority_group_high"],
            row["final_priority_group_low"],
        )
    console.print(missing_income_table)

    four_plus_countries_table = Table(
        title=(
            "Researcher Details: 4+ Countries "
            f"({len(highlights['four_or_more_countries'])} names)"
        ),
        box=box.SIMPLE,
    )
    four_plus_countries_table.add_column("Researcher", style="cyan")
    four_plus_countries_table.add_column("Primary affiliations", style="white")
    four_plus_countries_table.add_column("Country count", style="magenta", justify="right")
    four_plus_countries_table.add_column("Countries", style="white")
    four_plus_countries_table.add_column("Final income high", style="magenta")
    four_plus_countries_table.add_column("Final income low", style="magenta")
    for row in highlights["four_or_more_countries"]:
        four_plus_countries_table.add_row(
            row["researcher_name"],
            _join_display(row["primary_affiliations"]),
            f"{row['country_count']:,}",
            _join_display(row["countries"], delimiter=", "),
            row["final_income_group_high"],
            row["final_income_group_low"],
        )
    console.print(four_plus_countries_table)

    audit_table = Table(
        title="Label Coverage / Consistency Audit (Mode-0 Selected Names)",
        box=box.SIMPLE,
    )
    audit_table.add_column("Metric", style="cyan")
    audit_table.add_column("Value", style="magenta", justify="right")
    audit_table.add_row(
        "Selected names with no income-group labels",
        f"{audit['selected_names_without_income_group']:,}",
    )
    audit_table.add_row(
        "Selected names with no priority-group labels",
        f"{audit['selected_names_without_priority_group']:,}",
    )
    audit_table.add_row(
        "Selected names with exactly one distinct row income-group label",
        f"{audit['selected_names_with_exactly_one_row_income_group']:,}",
    )
    audit_table.add_row(
        "Selected names with 2+ distinct row income-group labels",
        f"{audit['selected_names_with_multiple_row_income_groups']:,}",
    )
    audit_table.add_row(
        "Selected names with exactly one distinct row priority-group label",
        f"{audit['selected_names_with_exactly_one_row_priority_group']:,}",
    )
    audit_table.add_row(
        "Selected names with 2+ distinct row priority-group labels",
        f"{audit['selected_names_with_multiple_row_priority_groups']:,}",
    )
    audit_table.add_row(
        "Selected rows with missing income-group label",
        f"{audit['selected_rows_missing_income_group']:,}",
    )
    audit_table.add_row(
        "Selected rows with missing priority-group label",
        f"{audit['selected_rows_missing_priority_group']:,}",
    )
    console.print(audit_table)

    outlier_table = Table(
        title="Country Cardinality Outliers (Tukey 1.5*IQR)",
        box=box.SIMPLE,
    )
    outlier_table.add_column("Metric", style="cyan")
    outlier_table.add_column("Value", style="magenta", justify="right")
    outlier_table.add_row("IQR", _fmt_float(outliers["iqr"]))
    outlier_table.add_row("Lower fence", _fmt_float(outliers["lower_fence"]))
    outlier_table.add_row("Upper fence", _fmt_float(outliers["upper_fence"]))
    outlier_table.add_row("Lower outliers", f"{outliers['lower_outliers']:,}")
    outlier_table.add_row("Upper outliers", f"{outliers['upper_outliers']:,}")
    outlier_table.add_row("Total outliers", f"{outliers['total_outliers']:,}")
    outlier_table.add_row(
        "Outliers % of selected names",
        _fmt_pct(outliers["outlier_pct_of_selected_names"]),
    )
    console.print(outlier_table)


def run_detour(
    config: PipelineConfig,
    interactive: bool = True,
    diagnostics: Any = None,
) -> DetourResult:
    del interactive
    del diagnostics

    monitor = ResourceMonitor()
    monitor.start()
    conn: duckdb.DuckDBPyConnection | None = None

    try:
        conn = duckdb.connect(str(config.db_file), read_only=True)
        metadata = _build_mode0_econ_metadata(config, conn)
        _print_summary(metadata)
        result = DetourResult(
            success=True,
            steps_completed=[],
            summary="Computed read-only mode-0 economy stats from persisted tables.",
            metadata=metadata,
        )
    except Exception as exc:
        console.print(f"[red]Exited prematurely: {type(exc).__name__}: {exc}[/red]")
        raise
    finally:
        peak_ram = monitor.stop()
        if conn is not None:
            conn.close()

    m_table = Table(title="Execution Metrics", box=box.SIMPLE)
    m_table.add_column("Metric", style="cyan")
    m_table.add_column("Value", style="magenta")
    m_table.add_row("Peak RAM Usage", f"{peak_ram:.2f} GB")
    console.print(m_table)
    console.print("[cyan]Execution Metrics[/cyan]")
    console.print(f"[magenta]Peak RAM Usage: {peak_ram:.2f} GB[/magenta]")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only detour that analyzes mode-0 rows from persisted tables "
            "and prints income-group / priority-group stats."
        )
    )
    parser.add_argument("--config", type=Path, required=True, help="Path to JSON config file.")
    args = parser.parse_args()

    try:
        config = PipelineConfig.from_json(args.config)
        result = run_detour(config)
        if not result.success:
            raise RuntimeError(result.summary)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        raise


if __name__ == "__main__":
    main()
