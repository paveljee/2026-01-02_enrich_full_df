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
    COUNTRY_PREFIX,
    ENGLISH_HICS,
    EU_COUNTRIES,
    GREATER_CHINA,
    HCR_XLSX_AFFILIATIONS_COLS,
    HCR_XLSX_NAME_COLS,
    KTP_COUNTRY_ALIASES,
    KTP_ECONOMIES_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    KTP_ECONOMY_MATCH_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_PRIORITY_GROUP_LABELS,
    OGHIST_INCOME_LABELS,
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
    aff_text_col = "a.aff_text"
    aff_tokens_col = "a.aff_tokens"

    high_income = sorted(
        {name for name, label in canonical_map.items() if label == OGHIST_INCOME_LABELS["H"]}
    )
    non_english_hics = _non_english_non_eu_hics(high_income)

    def _normalize_match(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    def _like_clause(items: list[str]) -> str:
        clauses = []
        for item in items:
            match_norm = _normalize_match(item).replace("'", "''")
            if not match_norm:
                continue
            clauses.append(
                f"(' ' || {aff_tokens_col} || ' ') LIKE '% {match_norm} %'"
            )
        return " OR ".join(clauses) if clauses else "FALSE"

    any_priority_clause = _like_clause(
        ENGLISH_HICS + EU_COUNTRIES + GREATER_CHINA + non_english_hics
    )
    china_clause = _like_clause(GREATER_CHINA)
    non_english_clause = _like_clause(non_english_hics)
    eu_clause = _like_clause(EU_COUNTRIES)

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {POPULATION_ECON_TABLE} AS
        WITH aff AS (
            SELECT
                p."{KTP_POPULATION_INDEX_COL}" AS "{KTP_POPULATION_INDEX_COL}",
                {aff_expr} AS aff_text,
                TRIM(regexp_replace(lower(unaccent({aff_expr})), '[^a-z0-9]+', ' '))
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
                WHEN NOT ({any_priority_clause}) THEN 1
                WHEN {china_clause} THEN 2
                WHEN {non_english_clause} THEN 3
                WHEN {eu_clause} THEN 4
                ELSE 5
            END AS "{KTP_PRIORITY_COL}",
            CASE
                WHEN NOT ({any_priority_clause}) THEN '{KTP_PRIORITY_GROUP_LABELS[1]}'
                WHEN {china_clause} THEN '{KTP_PRIORITY_GROUP_LABELS[2]}'
                WHEN {non_english_clause} THEN '{KTP_PRIORITY_GROUP_LABELS[3]}'
                WHEN {eu_clause} THEN '{KTP_PRIORITY_GROUP_LABELS[4]}'
                ELSE '{KTP_PRIORITY_GROUP_LABELS[5]}'
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
    for col in ("hcr.filename", "hcr.row_number", "hcr.category"):
        if col in hcr_cols:
            ordered_hcr.append(col)
    ordered_hcr += [col for col in hcr_cols if col not in ordered_hcr]
    ordered_cols = (
        [
            KTP_POPULATION_INDEX_COL,
            "hcr.filename",
            "hcr.row_number",
            "ktp.first_name",
            "ktp.last_name",
            "hcr.category",
        ]
        + [col for col in ordered_hcr if col not in {"hcr.filename", "hcr.row_number", "hcr.category"}]
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
        step_id="add_economy_priority",
        artifacts={"population_with_economy_df": merged_df},
        messages=[f"Computed economies for {len(canonical_map)} country entries."],
        diagnostics=[f"Country income entries: {len(canonical_map)}"],
    )
