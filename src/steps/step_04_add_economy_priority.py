from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Mapping

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
    ENGLISH_HICS,
    EU_COUNTRIES,
    GREATER_CHINA,
    HCR_CATEGORY_COL,
    HCR_FILENAME_COL,
    HCR_ROW_COL,
    HCR_XLSX_AFFILIATIONS_COLS,
    HCR_XLSX_NAME_COLS,
    KTP_COUNTRY_ALIASES,
    KTP_ECONOMIES_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    KTP_ECONOMY_MATCH_COL,
    KTP_FIRST_NAME_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_LAST_NAME_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_PRIORITY_GROUP_LABELS,
    OGHIST_INCOME_LABELS,
    STEP_ADD_ECONOMY_PRIORITY,
)


def _load_income_labels(
    resource: RegisteredResource,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    path = Path(resource.__fspath__())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df = pd.read_excel(
            path,
            sheet_name="Country Analytical History",
            engine="openpyxl",
            header=None,
        )
    fy_row = None
    for idx, row in df.iterrows():
        if row.astype(str).str.contains(r"\bFY\d{2}\b", regex=True).any():
            fy_row = row
            break
    if fy_row is None:
        raise ValueError("Unable to locate FY column in World Bank history sheet.")
    fy_cols = [
        col_idx for col_idx, value in fy_row.items()
        if isinstance(value, str) and value.startswith("FY")
    ]
    if not fy_cols:
        raise ValueError("Unable to locate fiscal year columns in World Bank history sheet.")
    fy_col = fy_cols[-1]
    codes = df[fy_col].astype(str).str.strip()
    countries = df[1].astype(str).str.strip()
    mapping: dict[str, str] = {}
    rows: list[dict[str, str]] = []

    def _normalize_match(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    for country, code in zip(countries, codes):
        label = OGHIST_INCOME_LABELS.get(code)
        if label and country and country != "nan":
            mapping[country] = label
            rows.append(
                {
                    "match_name": country,
                    "match_norm": _normalize_match(country),
                    "country": country,
                    "income_label": label,
                }
            )
    for country, label in mapping.items():
        for alias in KTP_COUNTRY_ALIASES.get(country, ()):
            rows.append(
                {
                    "match_name": alias,
                    "match_norm": _normalize_match(alias),
                    "country": country,
                    "income_label": label,
                }
            )
    return rows, mapping


def _non_english_non_eu_hics(economies: list[str]) -> list[str]:
    return [
        hic
        for hic in economies
        if not any(c in hic for c in ENGLISH_HICS + EU_COUNTRIES + GREATER_CHINA)
    ]


def _affiliation_expression(columns: list[str], table_alias: str = "p") -> str:
    parts = [f'COALESCE(CAST({table_alias}."{col}" AS VARCHAR), \'\')' for col in columns]
    joined = " || ' ' || ".join(parts) if parts else "''"
    return f"TRIM({joined})"


def _infer_affiliation_columns(columns: list[str], keyword: str) -> list[str]:
    return [
        col
        for col in columns
        if keyword in col.lower() and "affiliation" in col.lower()
    ]


def _normalize_affiliation_map(
    raw_map: Mapping[str, list[str] | tuple[list[str], list[str]] | str],
    *,
    index: int,
) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for filename, cols in raw_map.items():
        if isinstance(cols, tuple):
            selected = cols[index] if len(cols) > index else []
        elif isinstance(cols, list):
            selected = cols
        elif isinstance(cols, str):
            selected = [cols]
        else:
            selected = []
        normalized[filename] = selected
    return normalized


def _affiliation_case(
    *,
    filename_col: str,
    default_cols: list[str],
    filename_map: dict[str, list[str]],
) -> str:
    if not filename_map:
        return _affiliation_expression(default_cols)
    cases = []
    for filename, cols in filename_map.items():
        expr = _affiliation_expression(cols)
        safe_filename = filename.replace("'", "''")
        cases.append(f"WHEN {filename_col} = '{safe_filename}' THEN {expr}")
    default_expr = _affiliation_expression(default_cols)
    return f"(CASE {' '.join(cases)} ELSE {default_expr} END)"


def run(context: PipelineContext) -> StepResult:
    if context.resources is None:
        raise ValueError("Resources not initialized. Run register_resources first.")

    conn: duckdb.DuckDBPyConnection = context.conn
    income_rows, canonical_map = _load_income_labels(context.resources.world_bank_resource)
    econ_rows = pd.DataFrame(income_rows)
    register_frame(conn, "income_map_frame", econ_rows)
    conn.execute("CREATE OR REPLACE TABLE income_map AS SELECT * FROM income_map_frame")
    conn.execute("DROP TABLE IF EXISTS income_map_frame")

    aff_cols = [
        row[0]
        for row in conn.execute(f"DESCRIBE {POPULATION_TABLE}").fetchall()
        if "affiliation" in row[0].lower()
    ]
    primary_default = _infer_affiliation_columns(aff_cols, "primary")
    secondary_default = _infer_affiliation_columns(aff_cols, "secondary")
    primary_map = _normalize_affiliation_map(HCR_XLSX_AFFILIATIONS_COLS, index=0)
    secondary_map = _normalize_affiliation_map(HCR_XLSX_AFFILIATIONS_COLS, index=1)
    primary_expr = _affiliation_case(
        filename_col='p."hcr.filename"',
        default_cols=primary_default,
        filename_map=primary_map,
    )
    secondary_expr = _affiliation_case(
        filename_col='p."hcr.filename"',
        default_cols=secondary_default,
        filename_map=secondary_map,
    )
    aff_expr = "TRIM(" + " || ' ' || ".join([primary_expr, secondary_expr]) + ")"

    high_income = sorted(
        {name for name, label in canonical_map.items() if label == OGHIST_INCOME_LABELS["H"]}
    )
    non_english_hics = _non_english_non_eu_hics(high_income)

    match_name_to_country = {row["match_name"]: row["country"] for row in income_rows}

    def _countries_for(match_names: list[str]) -> list[str]:
        countries: list[str] = []
        for name in match_names:
            country = match_name_to_country.get(name)
            if country and country not in countries:
                countries.append(country)
        return countries

    english_countries = _countries_for(ENGLISH_HICS)
    eu_countries = _countries_for(EU_COUNTRIES)
    china_countries = _countries_for(GREATER_CHINA)
    non_english_countries = [
        country for country in non_english_hics if country not in english_countries + eu_countries
    ]

    def _sql_in_list(values: list[str]) -> str:
        if not values:
            return "FALSE"

        def _escape(value: str) -> str:
            return value.replace("'", "''")

        quoted = ", ".join(f"'{_escape(value)}'" for value in values)
        return f"m.country IN ({quoted})"

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {POPULATION_ECON_TABLE} AS
        WITH aff AS (
            SELECT
                p."{KTP_POPULATION_INDEX_COL}" AS "{KTP_POPULATION_INDEX_COL}",
                {aff_expr} AS aff_text,
                TRIM(regexp_replace(lower(unaccent({aff_expr})), '[^a-z0-9]+', ' ', 'g'))
                    AS aff_tokens,
                {primary_expr} AS "{KTP_HCR_PRIMARY_AFFILIATIONS_COL}",
                {secondary_expr} AS "{KTP_HCR_SECONDARY_AFFILIATIONS_COL}"
            FROM {POPULATION_TABLE} p
        ),
        matches AS (
            SELECT
                a."{KTP_POPULATION_INDEX_COL}",
                a.aff_text,
                m.country,
                m.income_label
            FROM aff a
            JOIN income_map m
              ON (' ' || a.aff_tokens || ' ') LIKE '% ' || m.match_norm || ' %'
        )
        SELECT
            a."{KTP_POPULATION_INDEX_COL}",
            COALESCE(
                to_json(list(DISTINCT m.country) FILTER (WHERE m.country IS NOT NULL)),
                '[]'
            ) AS "{KTP_ECONOMIES_COL}",
            CASE
                WHEN bool_or(m.income_label = '{OGHIST_INCOME_LABELS["H"]}')
                    THEN '{OGHIST_INCOME_LABELS["H"]}'
                WHEN bool_or(m.income_label = '{OGHIST_INCOME_LABELS["UM"]}')
                    THEN '{OGHIST_INCOME_LABELS["UM"]}'
                WHEN bool_or(m.income_label = '{OGHIST_INCOME_LABELS["LM"]}')
                    THEN '{OGHIST_INCOME_LABELS["LM"]}'
                WHEN bool_or(m.income_label = '{OGHIST_INCOME_LABELS["L"]}')
                    THEN '{OGHIST_INCOME_LABELS["L"]}'
                ELSE NULL
            END AS "{KTP_ECONOMIES_INCOME_GROUP_COL}",
            CASE
                WHEN count(m.country) = 0 THEN NULL
                ELSE json_object(a.aff_text, list(DISTINCT m.country))
            END AS "{KTP_ECONOMY_MATCH_COL}",
            a."{KTP_HCR_PRIMARY_AFFILIATIONS_COL}",
            a."{KTP_HCR_SECONDARY_AFFILIATIONS_COL}",
            CASE
                WHEN count(m.country) = 0 THEN 1
                WHEN bool_or({_sql_in_list(china_countries)}) THEN 2
                WHEN bool_or({_sql_in_list(non_english_countries)}) THEN 3
                WHEN bool_or({_sql_in_list(eu_countries)}) THEN 4
                WHEN bool_or({_sql_in_list(english_countries)}) THEN 5
                ELSE 1
            END AS "{KTP_PRIORITY_COL}",
            CASE
                WHEN count(m.country) = 0 THEN '{KTP_PRIORITY_GROUP_LABELS[1]}'
                WHEN bool_or({_sql_in_list(china_countries)})
                    THEN '{KTP_PRIORITY_GROUP_LABELS[2]}'
                WHEN bool_or({_sql_in_list(non_english_countries)})
                    THEN '{KTP_PRIORITY_GROUP_LABELS[3]}'
                WHEN bool_or({_sql_in_list(eu_countries)})
                    THEN '{KTP_PRIORITY_GROUP_LABELS[4]}'
                WHEN bool_or({_sql_in_list(english_countries)})
                    THEN '{KTP_PRIORITY_GROUP_LABELS[5]}'
                ELSE '{KTP_PRIORITY_GROUP_LABELS[1]}'
            END AS "{KTP_PRIORITY_GROUP_COL}"
        FROM aff a
        LEFT JOIN matches m
          ON a."{KTP_POPULATION_INDEX_COL}" = m."{KTP_POPULATION_INDEX_COL}"
        GROUP BY
            a."{KTP_POPULATION_INDEX_COL}",
            a.aff_text,
            a.aff_tokens,
            a."{KTP_HCR_PRIMARY_AFFILIATIONS_COL}",
            a."{KTP_HCR_SECONDARY_AFFILIATIONS_COL}"
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {POPULATION_ECON_VIEW} AS
        SELECT
            p.*,
            n.*,
            e."{KTP_ECONOMIES_COL}",
            e."{KTP_ECONOMIES_INCOME_GROUP_COL}",
            e."{KTP_ECONOMY_MATCH_COL}",
            e."{KTP_HCR_PRIMARY_AFFILIATIONS_COL}",
            e."{KTP_HCR_SECONDARY_AFFILIATIONS_COL}",
            e."{KTP_PRIORITY_COL}",
            e."{KTP_PRIORITY_GROUP_COL}"
        FROM {POPULATION_TABLE} p
        JOIN {POPULATION_NAMES_TABLE} n
          ON p."{KTP_POPULATION_INDEX_COL}" = n."{KTP_POPULATION_INDEX_COL}"
        JOIN {POPULATION_ECON_TABLE} e
          ON p."{KTP_POPULATION_INDEX_COL}" = e."{KTP_POPULATION_INDEX_COL}"
        """
    )

    view_columns = [
        row[0]
        for row in conn.execute(f"DESCRIBE {POPULATION_ECON_VIEW}").fetchall()
        if "unnamed" not in row[0].lower()
        and row[0] != f"{KTP_POPULATION_INDEX_COL}_1"
    ]
    hcr_cols = [col for col in view_columns if col.startswith("hcr.")]
    explicit_name_cols: set[str] = set()
    for _, (first_col, last_col) in HCR_XLSX_NAME_COLS.items():
        explicit_name_cols.update({first_col, last_col})
    if not explicit_name_cols:
        inferred_name_cols = {
            col
            for col in hcr_cols
            if ("first" in col.lower() and "name" in col.lower())
            or ("last" in col.lower() and "name" in col.lower())
            or "firstname" in col.lower()
            or "lastname" in col.lower()
            or "familyname" in col.lower()
        }
        explicit_name_cols = inferred_name_cols
    hcr_cols = [
        col
        for col in hcr_cols
        if col not in explicit_name_cols and "unnamed" not in col.lower()
    ]
    ordered_hcr = []
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
            col for col in ordered_hcr
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
    select_cols = ", ".join([f'"{col}"' for col in ordered_cols if col in view_columns])
    merged_df = conn.execute(f"SELECT {select_cols} FROM {POPULATION_ECON_VIEW}").df()

    return StepResult(
        step_id=STEP_ADD_ECONOMY_PRIORITY,
        artifacts={"population_with_economy_df": merged_df},
        messages=[f"Computed economies for {len(canonical_map)} country entries."],
        diagnostics=[f"Country income entries: {len(canonical_map)}"],
    )
