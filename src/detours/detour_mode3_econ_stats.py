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
from src.helpers.jsonlines import loads_jsonlines
from src.helpers.resource_monitor import ResourceMonitor
from src.helpers.schema import OUTERDICT_STUB_TABLE, PARQUET_INNERDICT_TABLE, XLSX_INNERDICT_TABLE
from src.helpers.vars import (
    CARD_BUILD_SUBSET_DESCRIPTIONS,
    ENGLISH_HICS,
    EU_COUNTRIES,
    GREATER_CHINA,
    KTP_ECONOMIES_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_LAST_NAME_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_PRIORITY_GROUP_LABELS,
    KTP_SOURCE_KEY_COL,
    KTP_XLSX_MATCH_COL,
    KTP_XLSX_MATCH_FIRST_TOKENS_KEY,
    KTP_XLSX_MATCH_LAST_NAME_NORM_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY,
    OGHIST_INCOME_LABELS,
)

console = Console()

DETOUR_ID = "mode3-econ-stats"
DETOUR_NAME = "Mode 3 Economy Stats"
DETOUR_DESCRIPTION = (
    "Read-only detour that reconstructs mode-3 selection from persisted tables and "
    "prints income-group and priority-group statistics for selected unique names."
)
DETOUR_STEPS: list[str] = []

MODE = 3

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
            "mode-3 econ stats must run from persisted DB content only."
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


def _build_mode3_econ_metadata(
    config: PipelineConfig,
    conn: duckdb.DuckDBPyConnection,
) -> dict[str, Any]:
    del config

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

    xlsx_payloads_by_key: dict[str, list[object]] = defaultdict(list)
    xlsx_rows_by_key: dict[str, list[dict[str, object]]] = defaultdict(list)
    for name_key, inner_blob in conn.execute(
        f"SELECT name_key, innerdicts FROM {XLSX_INNERDICT_TABLE}"
    ).fetchall():
        if name_key is None:
            continue
        for inner in loads_jsonlines(inner_blob or ""):
            xlsx_payloads_by_key[name_key].append(inner.get(KTP_XLSX_MATCH_COL))
            filename = inner.get(KTP_FILENAME_COL)
            fragment = inner.get(KTP_FRAGMENT_COL)
            if filename is None or fragment is None:
                raise RuntimeError(
                    "XLSX innerdict row is missing persisted population row identity "
                    f"({KTP_FILENAME_COL}, {KTP_FRAGMENT_COL}) for {name_key!r}."
                )
            xlsx_rows_by_key[name_key].append(inner)

    sciscinet_count_by_key: dict[str, int] = defaultdict(int)
    for (source_key,) in conn.execute(
        f'SELECT "{KTP_SOURCE_KEY_COL}" FROM {PARQUET_INNERDICT_TABLE}'
    ).fetchall():
        if source_key is None:
            continue
        sciscinet_count_by_key[source_key] += 1

    sciscinet_exactly_one_pass = 0
    xlsx_exact_pass = 0
    mode3_selected_keys: list[str] = []
    name_countries_by_key: dict[str, set[str]] = defaultdict(set)
    name_row_income_groups_by_key: dict[str, set[str]] = defaultdict(set)
    name_row_priority_groups_by_key: dict[str, set[str]] = defaultdict(set)
    name_row_ids_by_key: dict[str, set[tuple[str, str]]] = defaultdict(set)
    selected_row_ids: set[tuple[str, str]] = set()
    selected_row_countries_by_id: dict[tuple[str, str], set[str]] = defaultdict(set)
    selected_row_income_group_by_id: dict[tuple[str, str], str | None] = {}
    selected_row_priority_group_by_id: dict[tuple[str, str], str | None] = {}

    for name_key in outer_keys:
        sciscinet_exactly_one_ok = sciscinet_count_by_key.get(name_key, 0) == 1
        xlsx_payloads = xlsx_payloads_by_key.get(name_key, [])
        xlsx_exact_ok = any(
            _has_present_xlsx_match_payload(value) for value in xlsx_payloads
        ) and all(_is_exact_xlsx_match_payload(value) for value in xlsx_payloads)

        if sciscinet_exactly_one_ok:
            sciscinet_exactly_one_pass += 1
        if xlsx_exact_ok:
            xlsx_exact_pass += 1

        if not (sciscinet_exactly_one_ok and xlsx_exact_ok):
            continue

        mode3_selected_keys.append(name_key)
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

    selected_names = len(mode3_selected_keys)
    mode3_selected_population_rows = len(selected_row_ids)

    selected_names_with_countries = sum(
        bool(name_countries_by_key.get(name_key)) for name_key in mode3_selected_keys
    )
    selected_names_with_income_group = sum(
        bool(name_row_income_groups_by_key.get(name_key)) for name_key in mode3_selected_keys
    )
    selected_names_with_priority_group = sum(
        bool(name_row_priority_groups_by_key.get(name_key)) for name_key in mode3_selected_keys
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
        len(name_countries_by_key.get(name_key, set())) for name_key in mode3_selected_keys
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
        raise RuntimeError("Bucket partition invariant failed for mode-3 country cardinality.")

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
        not name_row_income_groups_by_key.get(name_key) for name_key in mode3_selected_keys
    )
    selected_names_without_priority_group = sum(
        not name_row_priority_groups_by_key.get(name_key) for name_key in mode3_selected_keys
    )
    selected_names_with_exactly_one_row_income_group = sum(
        len(name_row_income_groups_by_key.get(name_key, set())) == 1
        for name_key in mode3_selected_keys
    )
    selected_names_with_multiple_row_income_groups = sum(
        len(name_row_income_groups_by_key.get(name_key, set())) > 1
        for name_key in mode3_selected_keys
    )
    selected_names_with_exactly_one_row_priority_group = sum(
        len(name_row_priority_groups_by_key.get(name_key, set())) == 1
        for name_key in mode3_selected_keys
    )
    selected_names_with_multiple_row_priority_groups = sum(
        len(name_row_priority_groups_by_key.get(name_key, set())) > 1
        for name_key in mode3_selected_keys
    )
    selected_rows_missing_income_group = (
        mode3_selected_population_rows - selected_population_rows_with_income_group
    )
    selected_rows_missing_priority_group = (
        mode3_selected_population_rows - selected_population_rows_with_priority_group
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
                income_row_counts.get(label, 0), mode3_selected_population_rows
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
                selected_rows_missing_income_group, mode3_selected_population_rows
            ),
            "pct_of_non_missing_selected_population_rows": None,
        }
    )
    income_breakdown_lower_tier_preferred = [
        {
            "income_group": label,
            "selected_population_rows": lower_tier_income_row_counts.get(label, 0),
            "pct_of_selected_population_rows": _pct(
                lower_tier_income_row_counts.get(label, 0), mode3_selected_population_rows
            ),
            "pct_of_non_missing_selected_population_rows": _pct(
                lower_tier_income_row_counts.get(label, 0),
                mode3_selected_population_rows - selected_rows_missing_lower_tier_income_group,
            ),
        }
        for label in INCOME_GROUP_ORDER_LOW_FIRST
    ]
    income_breakdown_lower_tier_preferred.append(
        {
            "income_group": MISSING_BREAKDOWN_LABEL,
            "selected_population_rows": selected_rows_missing_lower_tier_income_group,
            "pct_of_selected_population_rows": _pct(
                selected_rows_missing_lower_tier_income_group, mode3_selected_population_rows
            ),
            "pct_of_non_missing_selected_population_rows": None,
        }
    )

    priority_breakdown = [
        {
            "priority_group": label,
            "selected_population_rows": priority_row_counts.get(label, 0),
            "pct_of_selected_population_rows": _pct(
                priority_row_counts.get(label, 0), mode3_selected_population_rows
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
                selected_rows_missing_priority_group, mode3_selected_population_rows
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

    for name_key in mode3_selected_keys:
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
                "pct_of_mode3_selected_names": _pct(
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
                "pct_of_mode3_selected_names": _pct(
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
                "pct_of_mode3_selected_names": _pct(
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
                "pct_of_mode3_selected_names": _pct(
                    lower_priority_name_counts.get(label, 0), selected_names
                ),
            }
        )

    multi_country_names = 0
    multi_country_different_income_groups = 0
    multi_country_different_priority_groups = 0
    for name_key in mode3_selected_keys:
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
    for name_key in mode3_selected_keys:
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

    return {
        "detour_id": DETOUR_ID,
        "mode": MODE,
        "mode_description": CARD_BUILD_SUBSET_DESCRIPTIONS[MODE],
        "db_file": _db_file_from_pragma(conn),
        "tables_used": [OUTERDICT_STUB_TABLE, XLSX_INNERDICT_TABLE, PARQUET_INNERDICT_TABLE],
        "priority_group_definitions": PRIORITY_GROUP_RULES,
        "counts": {
            "population_rows": population_rows,
            "outerdict_keys": outerdict_keys,
            "sciscinet_distinct_source_keys": len(sciscinet_count_by_key),
            "mode3_selected_names": selected_names,
            "mode3_selected_pct_of_outerdict_keys": _pct(selected_names, outerdict_keys),
            "mode3_selected_population_rows": mode3_selected_population_rows,
            "mode3_selected_pct_of_population_rows": _pct(
                mode3_selected_population_rows, population_rows
            ),
            "selected_names_with_countries": selected_names_with_countries,
            "selected_names_with_countries_pct_of_mode3": _pct(
                selected_names_with_countries, selected_names
            ),
            "selected_names_with_income_group": selected_names_with_income_group,
            "selected_names_with_income_group_pct_of_mode3": _pct(
                selected_names_with_income_group, selected_names
            ),
            "selected_names_with_priority_group": selected_names_with_priority_group,
            "selected_names_with_priority_group_pct_of_mode3": _pct(
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
        "rule_counts": {
            "sciscinet_exactly_one_pass": sciscinet_exactly_one_pass,
            "sciscinet_exactly_one_fail": outerdict_keys - sciscinet_exactly_one_pass,
            "xlsx_exact_pass": xlsx_exact_pass,
            "xlsx_exact_fail": outerdict_keys - xlsx_exact_pass,
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
            "exact_0_pct_of_mode3": _pct(bucket_exact_0, selected_names),
            "exact_1_pct_of_mode3": _pct(bucket_exact_1, selected_names),
            "exact_2_pct_of_mode3": _pct(bucket_exact_2, selected_names),
            "exact_3_pct_of_mode3": _pct(bucket_exact_3, selected_names),
            "exact_4_or_more_pct_of_mode3": _pct(bucket_4_or_more, selected_names),
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
            "multi_country_pct_of_mode3": _pct(multi_country_names, selected_names),
            "different_income_groups": multi_country_different_income_groups,
            "different_income_groups_pct_of_mode3": _pct(
                multi_country_different_income_groups, selected_names
            ),
            "different_income_groups_pct_of_multi_country": _pct(
                multi_country_different_income_groups, multi_country_names
            ),
            "different_priority_groups": multi_country_different_priority_groups,
            "different_priority_groups_pct_of_mode3": _pct(
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
    rules = metadata["rule_counts"]
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

    console.print("[cyan]Mode-3 Economy Stats Detour (read-only)[/cyan]")
    console.print(f"[white]DB: {metadata['db_file']}[/white]")
    console.print(f"[white]Mode {metadata['mode']}: {metadata['mode_description']}[/white]")
    console.print(
        "[white]Tables used: "
        + ", ".join(str(name) for name in metadata["tables_used"])
        + "[/white]"
    )

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
    counts_table.add_row("Mode-3 selected names", f"{counts['mode3_selected_names']:,}")
    counts_table.add_row(
        "Mode-3 selected % of OuterDict keys",
        _fmt_pct(counts["mode3_selected_pct_of_outerdict_keys"]),
    )
    counts_table.add_row(
        "Population rows containing mode-3 selected names",
        f"{counts['mode3_selected_population_rows']:,}",
    )
    counts_table.add_row(
        "Mode-3 selected % of population rows",
        _fmt_pct(counts["mode3_selected_pct_of_population_rows"]),
    )
    counts_table.add_row(
        "Selected names with at least one country",
        f"{counts['selected_names_with_countries']:,}",
    )
    counts_table.add_row(
        "Selected names with at least one country % of mode-3",
        _fmt_pct(counts["selected_names_with_countries_pct_of_mode3"]),
    )
    counts_table.add_row(
        "Selected names with at least one income-group label",
        f"{counts['selected_names_with_income_group']:,}",
    )
    counts_table.add_row(
        "Selected names with income-group label % of mode-3",
        _fmt_pct(counts["selected_names_with_income_group_pct_of_mode3"]),
    )
    counts_table.add_row(
        "Selected names with at least one priority-group label",
        f"{counts['selected_names_with_priority_group']:,}",
    )
    counts_table.add_row(
        "Selected names with priority-group label % of mode-3",
        _fmt_pct(counts["selected_names_with_priority_group_pct_of_mode3"]),
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

    rules_table = Table(title="Mode-3 Rule Counts (Across OuterDict Keys)", box=box.SIMPLE)
    rules_table.add_column("Rule", style="cyan")
    rules_table.add_column("Pass", style="green", justify="right")
    rules_table.add_column("Fail", style="red", justify="right")
    rules_table.add_row(
        "sciscinet: exactly one innerdict",
        f"{rules['sciscinet_exactly_one_pass']:,}",
        f"{rules['sciscinet_exactly_one_fail']:,}",
    )
    rules_table.add_row(
        "xlsx: present payload + all present exact",
        f"{rules['xlsx_exact_pass']:,}",
        f"{rules['xlsx_exact_fail']:,}",
    )
    console.print(rules_table)

    dist_table = Table(
        title="Country Cardinality Distribution (Mode-3 Selected Names)",
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
        title="Country Cardinality Buckets (Mode-3 Selected Names)",
        box=box.SIMPLE,
    )
    bucket_table.add_column("Bucket", style="cyan")
    bucket_table.add_column("Raw", style="magenta", justify="right")
    bucket_table.add_column("% of mode-3", style="magenta", justify="right")
    bucket_table.add_row(
        "0 countries",
        f"{buckets['exact_0']:,}",
        _fmt_pct(buckets["exact_0_pct_of_mode3"]),
    )
    bucket_table.add_row(
        "1 country",
        f"{buckets['exact_1']:,}",
        _fmt_pct(buckets["exact_1_pct_of_mode3"]),
    )
    bucket_table.add_row(
        "2 countries",
        f"{buckets['exact_2']:,}",
        _fmt_pct(buckets["exact_2_pct_of_mode3"]),
    )
    bucket_table.add_row(
        "3 countries",
        f"{buckets['exact_3']:,}",
        _fmt_pct(buckets["exact_3_pct_of_mode3"]),
    )
    bucket_table.add_row(
        "4+ countries",
        f"{buckets['exact_4_or_more']:,}",
        _fmt_pct(buckets["exact_4_or_more_pct_of_mode3"]),
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
        "name. These counts sum to Mode-3 selected names.[/white]"
    )
    derived_higher_table = Table(
        title="Derived Final Name-Level Groups (Combined Countries; Higher Preferred)",
        box=box.SIMPLE,
    )
    derived_higher_table.add_column("Group type", style="cyan")
    derived_higher_table.add_column("Label", style="white")
    derived_higher_table.add_column("Selected names", style="magenta", justify="right")
    derived_higher_table.add_column("% mode-3 names", style="magenta", justify="right")
    for row in derived_name_group_breakdown_higher_preferred:
        derived_higher_table.add_row(
            row["group_type"],
            row["label"],
            f"{row['selected_names']:,}",
            _fmt_pct(row["pct_of_mode3_selected_names"]),
        )
    console.print(derived_higher_table)

    derived_lower_table = Table(
        title="Derived Final Name-Level Groups (Combined Countries; Lower Preferred)",
        box=box.SIMPLE,
    )
    derived_lower_table.add_column("Group type", style="cyan")
    derived_lower_table.add_column("Label", style="white")
    derived_lower_table.add_column("Selected names", style="magenta", justify="right")
    derived_lower_table.add_column("% mode-3 names", style="magenta", justify="right")
    for row in derived_name_group_breakdown_lower_preferred:
        derived_lower_table.add_row(
            row["group_type"],
            row["label"],
            f"{row['selected_names']:,}",
            _fmt_pct(row["pct_of_mode3_selected_names"]),
        )
    console.print(derived_lower_table)

    divergence_table = Table(
        title="Multi-Country Divergence (Mode-3 Selected Names)",
        box=box.SIMPLE,
    )
    divergence_table.add_column("Metric", style="cyan")
    divergence_table.add_column("Value", style="magenta", justify="right")
    divergence_table.add_row(
        "Selected names with >1 countries",
        f"{divergence['multi_country_names']:,}",
    )
    divergence_table.add_row(
        "Selected names with >1 countries % of mode-3",
        _fmt_pct(divergence["multi_country_pct_of_mode3"]),
    )
    divergence_table.add_row(
        "Selected names with >1 countries and >1 derived income groups",
        f"{divergence['different_income_groups']:,}",
    )
    divergence_table.add_row(
        "Different derived income groups % of mode-3",
        _fmt_pct(divergence["different_income_groups_pct_of_mode3"]),
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
        "Different derived priority groups % of mode-3",
        _fmt_pct(divergence["different_priority_groups_pct_of_mode3"]),
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
        title="Label Coverage / Consistency Audit (Mode-3 Selected Names)",
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
        metadata = _build_mode3_econ_metadata(config, conn)
        _print_summary(metadata)
        result = DetourResult(
            success=True,
            steps_completed=[],
            summary="Computed read-only mode-3 economy stats from persisted tables.",
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
            "Read-only detour that reconstructs mode-3 selection from persisted tables "
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
