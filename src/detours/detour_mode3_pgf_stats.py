from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from collections.abc import Sequence
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
from src.helpers.schema import (
    OUTERDICT_STUB_TABLE,
    PARQUET_LEGACY_ROWS_INNERDICT_TABLE,
    XLSX_INNERDICT_TABLE,
)
from src.helpers.vars import (
    CARD_BUILD_SUBSET_DESCRIPTIONS,
    KTP_FILENAME_COL,
    KTP_FRAGMENT_COL,
    KTP_INNERDICT_JSONLINES_COL,
    KTP_NAMEKEY_COL,
    KTP_XLSX_MATCH_COL,
    KTP_XLSX_MATCH_FIRST_TOKENS_KEY,
    KTP_XLSX_MATCH_LAST_NAME_NORM_KEY,
    KTP_XLSX_MATCH_NAMEKEY_LAST_KEY,
    KTP_XLSX_MATCH_NAMEKEY_TOKENS_KEY,
)

console = Console()

DETOUR_ID = "mode3-pgf-stats"
DETOUR_NAME = "Mode 3 p_gf Stats"
DETOUR_DESCRIPTION = (
    "Read-only detour that reconstructs mode-3 selection from persisted tables and "
    "prints p_gf statistics for selected unique names."
)
DETOUR_STEPS: list[str] = []

P_GF_COL = "ssnau.p_gf"
INFERENCE_COUNTS_COL = "ssnau.inference_counts"
INFERENCE_SOURCES_COL = "ssnau.inference_sources"
MODE = 3
NQG_NAME_HANDLING_NOTICE = (
    "nomquamgender 0.1.0 normalizes each input name with unidecode, lower(), "
    "and strip(); it then tries the full normalized string first and, only if "
    "that is not found, falls back to the first whitespace-delimited token."
)
SCISCINET_PIPELINE_NOTICE = (
    "This database uses SciSciNet-v2 parquet data in step 09 "
    "(src/steps/step_09_match_parquet.py): matched HCR name keys are joined to "
    "SciSciNet author_details/authors tables, and ssnau.p_gf, "
    "ssnau.inference_counts, and ssnau.inference_sources are persisted in "
    "ssn_innerdicts."
)
SCISCINET_METHODS_NOTICE = (
    "SciSciNet-v2 reports following original SciSciNet methods; the original "
    "SciSciNet paper reports using nomquamgender for name-gender inference."
)


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
    source_key_tokens = payload.get(KTP_XLSX_MATCH_NAMEKEY_TOKENS_KEY, [])
    source_key_last = payload.get(KTP_XLSX_MATCH_NAMEKEY_LAST_KEY)
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


def _numeric_distribution(values: Sequence[int | float | None]) -> dict[str, float | int | None]:
    non_null_values = np.array([float(value) for value in values if value is not None], dtype=float)
    non_null_n = int(non_null_values.size)
    mean = float(non_null_values.mean()) if non_null_n else None
    sd = float(non_null_values.std(ddof=1)) if non_null_n > 1 else None
    se = float(sd / math.sqrt(non_null_n)) if non_null_n > 1 and sd is not None else None
    ci95_lo = float(mean - 1.96 * se) if mean is not None and se is not None else None
    ci95_hi = float(mean + 1.96 * se) if mean is not None and se is not None else None
    q1 = (
        float(np.quantile(non_null_values, 0.25, method="linear")) if non_null_n else None
    )
    median = (
        float(np.quantile(non_null_values, 0.5, method="linear")) if non_null_n else None
    )
    q3 = (
        float(np.quantile(non_null_values, 0.75, method="linear")) if non_null_n else None
    )
    return {
        "non_null_n": non_null_n,
        "null_n": len(values) - non_null_n,
        "mean": mean,
        "sd": sd,
        "se": se,
        "mean_ci95_lo": ci95_lo,
        "mean_ci95_hi": ci95_hi,
        "min": float(non_null_values.min()) if non_null_n else None,
        "q1": q1,
        "median": median,
        "q3": q3,
        "max": float(non_null_values.max()) if non_null_n else None,
    }


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


def _exact_binomial_inference(successes: int, trials: int) -> dict[str, float | int | None]:
    if trials == 0:
        return {
            "proportion": None,
            "ci95_lo": None,
            "ci95_hi": None,
            "excess_over_0_5": None,
            "excess_ci95_lo": None,
            "excess_ci95_hi": None,
            "p_two_sided": None,
            "p_two_sided_mantissa": None,
            "p_two_sided_exponent": None,
            "p_two_sided_log10": None,
        }

    def log_pmf(k: int, p: float) -> float:
        if p == 0.0:
            return 0.0 if k == 0 else -math.inf
        if p == 1.0:
            return 0.0 if k == trials else -math.inf
        return (
            math.lgamma(trials + 1)
            - math.lgamma(k + 1)
            - math.lgamma(trials - k + 1)
            + k * math.log(p)
            + (trials - k) * math.log1p(-p)
        )

    def log_tail_prob(start: int, end: int, p: float) -> float:
        logs = [log_pmf(k, p) for k in range(start, end + 1)]
        max_log = max(logs, default=-math.inf)
        if max_log == -math.inf:
            return -math.inf
        return max_log + math.log(sum(math.exp(value - max_log) for value in logs))

    def tail_prob(start: int, end: int, p: float) -> float:
        return math.exp(log_tail_prob(start, end, p))

    alpha_half = 0.025
    p_hat = successes / trials

    if successes == 0:
        ci_lo = 0.0
    else:
        lo, hi = 0.0, p_hat
        for _ in range(80):
            mid = (lo + hi) / 2.0
            if tail_prob(successes, trials, mid) < alpha_half:
                lo = mid
            else:
                hi = mid
        ci_lo = (lo + hi) / 2.0

    if successes == trials:
        ci_hi = 1.0
    else:
        lo, hi = p_hat, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2.0
            if tail_prob(0, successes, mid) > alpha_half:
                lo = mid
            else:
                hi = mid
        ci_hi = (lo + hi) / 2.0

    tail_count = min(successes, trials - successes)
    p_two_sided_log = min(0.0, math.log(2.0) + log_tail_prob(0, tail_count, 0.5))
    p_two_sided_log10 = p_two_sided_log / math.log(10.0)
    p_two_sided_exponent = math.floor(p_two_sided_log10)
    p_two_sided_mantissa = 10 ** (p_two_sided_log10 - p_two_sided_exponent)
    if p_two_sided_mantissa >= 10.0:
        p_two_sided_mantissa /= 10.0
        p_two_sided_exponent += 1
    p_two_sided = math.exp(p_two_sided_log)

    return {
        "proportion": p_hat,
        "ci95_lo": ci_lo,
        "ci95_hi": ci_hi,
        "excess_over_0_5": p_hat - 0.5,
        "excess_ci95_lo": ci_lo - 0.5,
        "excess_ci95_hi": ci_hi - 0.5,
        "p_two_sided": p_two_sided,
        "p_two_sided_mantissa": p_two_sided_mantissa,
        "p_two_sided_exponent": p_two_sided_exponent,
        "p_two_sided_log10": p_two_sided_log10,
    }


def _build_mode3_pgf_metadata(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    population_rows = _scalar_int(conn, "SELECT COUNT(*) FROM population_with_names_economy")

    outer_keys = [
        row[0]
        for row in conn.execute(
            f'SELECT "{KTP_NAMEKEY_COL}" FROM {OUTERDICT_STUB_TABLE} '
            f'ORDER BY "{KTP_NAMEKEY_COL}"'
        ).fetchall()
    ]
    outerdict_keys = len(outer_keys)

    xlsx_payloads_by_key: dict[str, list[object]] = defaultdict(list)
    xlsx_population_rows_by_key: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for name_key, inner_blob in conn.execute(
        f'SELECT "{KTP_NAMEKEY_COL}", "{KTP_INNERDICT_JSONLINES_COL}" '
        f"FROM {XLSX_INNERDICT_TABLE}"
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
            xlsx_population_rows_by_key[name_key].add((str(filename), str(fragment)))

    sciscinet_count_by_key: dict[str, int] = defaultdict(int)
    sciscinet_row_tuple = tuple[float | None, int | None, int | None]
    sciscinet_rows_by_key: dict[str, list[sciscinet_row_tuple]] = defaultdict(list)
    for source_key, p_gf, inference_counts, inference_sources in conn.execute(
        (
            f'SELECT "{KTP_NAMEKEY_COL}", "{P_GF_COL}", '
            f'"{INFERENCE_COUNTS_COL}", "{INFERENCE_SOURCES_COL}" '
            f"FROM {PARQUET_LEGACY_ROWS_INNERDICT_TABLE}"
        )
    ).fetchall():
        if source_key is None:
            continue
        sciscinet_count_by_key[source_key] += 1
        sciscinet_rows_by_key[source_key].append((p_gf, inference_counts, inference_sources))

    sciscinet_exactly_one_pass = 0
    xlsx_exact_pass = 0
    mode3_selected_keys: list[str] = []
    mode3_non_missing_keys: list[str] = []
    mode3_pgf_values: list[float | None] = []
    mode3_inference_counts_values: list[int | None] = []
    mode3_inference_sources_values: list[int | None] = []
    mode3_missing_pgf_inference_rows: list[tuple[int | None, int | None]] = []

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

        if sciscinet_exactly_one_ok and xlsx_exact_ok:
            mode3_selected_keys.append(name_key)
            sciscinet_rows = sciscinet_rows_by_key.get(name_key, [])
            if len(sciscinet_rows) != 1:
                raise RuntimeError(
                    "Mode-3 invariant violation: selected key should map to exactly one "
                    f"sciscinet innerdict, got {len(sciscinet_rows)} for {name_key!r}"
                )
            p_gf_value, inference_counts, inference_sources = sciscinet_rows[0]
            mode3_pgf_values.append(p_gf_value)
            mode3_inference_counts_values.append(inference_counts)
            mode3_inference_sources_values.append(inference_sources)
            if p_gf_value is None:
                mode3_missing_pgf_inference_rows.append((inference_counts, inference_sources))
            else:
                mode3_non_missing_keys.append(name_key)

    mode3_selected_population_rows = len(
        {
            row_id
            for name_key in mode3_selected_keys
            for row_id in xlsx_population_rows_by_key.get(name_key, set())
        }
    )
    pgf_non_missing_population_rows = len(
        {
            row_id
            for name_key in mode3_non_missing_keys
            for row_id in xlsx_population_rows_by_key.get(name_key, set())
        }
    )

    selected_names = len(mode3_selected_keys)
    non_missing_values = np.array(
        [float(value) for value in mode3_pgf_values if value is not None], dtype=float
    )
    non_missing_n = int(non_missing_values.size)
    missing_n = selected_names - non_missing_n

    mean = float(non_missing_values.mean()) if non_missing_n else None
    sd = float(non_missing_values.std(ddof=1)) if non_missing_n > 1 else None
    se = float(sd / math.sqrt(non_missing_n)) if non_missing_n > 1 and sd is not None else None
    ci95_lo = float(mean - 1.96 * se) if mean is not None and se is not None else None
    ci95_hi = float(mean + 1.96 * se) if mean is not None and se is not None else None
    min_v = float(non_missing_values.min()) if non_missing_n else None
    q1 = (
        float(np.quantile(non_missing_values, 0.25, method="linear")) if non_missing_n else None
    )
    median = (
        float(np.quantile(non_missing_values, 0.5, method="linear")) if non_missing_n else None
    )
    q3 = (
        float(np.quantile(non_missing_values, 0.75, method="linear")) if non_missing_n else None
    )
    max_v = float(non_missing_values.max()) if non_missing_n else None

    iqr = float(q3 - q1) if q1 is not None and q3 is not None else None
    lower_fence = float(q1 - 1.5 * iqr) if iqr is not None and q1 is not None else None
    upper_fence = float(q3 + 1.5 * iqr) if iqr is not None and q3 is not None else None
    lower_outliers = (
        int(np.sum(non_missing_values < lower_fence))
        if non_missing_n and lower_fence is not None
        else 0
    )
    upper_outliers = (
        int(np.sum(non_missing_values > upper_fence))
        if non_missing_n and upper_fence is not None
        else 0
    )
    total_outliers = lower_outliers + upper_outliers

    def _eq_count(value: float) -> int:
        return sum(v is not None and float(v) == value for v in mode3_pgf_values)

    bucket_missing = sum(value is None for value in mode3_pgf_values)
    bucket_exact_0 = _eq_count(0.0)
    bucket_exact_05 = _eq_count(0.5)
    bucket_exact_1 = _eq_count(1.0)
    bucket_between_0_and_0_5_exclusive = sum(
        value is not None and 0.0 < float(value) < 0.5 for value in mode3_pgf_values
    )
    bucket_between_0_5_and_1_exclusive = sum(
        value is not None and 0.5 < float(value) < 1.0 for value in mode3_pgf_values
    )

    if (
        bucket_missing
        + bucket_exact_0
        + bucket_exact_05
        + bucket_exact_1
        + bucket_between_0_and_0_5_exclusive
        + bucket_between_0_5_and_1_exclusive
        != selected_names
    ):
        raise RuntimeError("Bucket partition invariant failed for mode-3 p_gf values.")

    if len(mode3_missing_pgf_inference_rows) != bucket_missing:
        raise RuntimeError("Missing-p_gf inference audit invariant failed.")

    inference_counts_dist = _numeric_distribution(mode3_inference_counts_values)
    inference_sources_dist = _numeric_distribution(mode3_inference_sources_values)

    sign_test_n = (
        bucket_exact_0
        + bucket_between_0_and_0_5_exclusive
        + bucket_between_0_5_and_1_exclusive
        + bucket_exact_1
    )
    sign_test_above = bucket_between_0_5_and_1_exclusive + bucket_exact_1
    sign_test_below = bucket_exact_0 + bucket_between_0_and_0_5_exclusive
    sign_test = _exact_binomial_inference(sign_test_above, sign_test_n)

    missing_inference_counts_zero = sum(
        inference_counts == 0 for inference_counts, _ in mode3_missing_pgf_inference_rows
    )
    missing_inference_counts_nonzero = sum(
        inference_counts is not None and inference_counts != 0
        for inference_counts, _ in mode3_missing_pgf_inference_rows
    )
    missing_inference_counts_null = sum(
        inference_counts is None for inference_counts, _ in mode3_missing_pgf_inference_rows
    )
    missing_inference_sources_zero = sum(
        inference_sources == 0 for _, inference_sources in mode3_missing_pgf_inference_rows
    )
    missing_inference_sources_nonzero = sum(
        inference_sources is not None and inference_sources != 0
        for _, inference_sources in mode3_missing_pgf_inference_rows
    )
    missing_inference_sources_null = sum(
        inference_sources is None for _, inference_sources in mode3_missing_pgf_inference_rows
    )
    missing_inference_both_zero = sum(
        inference_counts == 0 and inference_sources == 0
        for inference_counts, inference_sources in mode3_missing_pgf_inference_rows
    )
    all_missing_pgf_have_both_zero: bool | None
    if bucket_missing == 0:
        all_missing_pgf_have_both_zero = None
    else:
        all_missing_pgf_have_both_zero = missing_inference_both_zero == bucket_missing

    return {
        "detour_id": DETOUR_ID,
        "mode": MODE,
        "mode_description": CARD_BUILD_SUBSET_DESCRIPTIONS[MODE],
        "db_file": _db_file_from_pragma(conn),
        "tables_used": [
            OUTERDICT_STUB_TABLE,
            XLSX_INNERDICT_TABLE,
            PARQUET_LEGACY_ROWS_INNERDICT_TABLE,
        ],
        "methodology_notice": {
            "nomquamgender_name_handling": NQG_NAME_HANDLING_NOTICE,
            "sciscinet_v2_pipeline_use": SCISCINET_PIPELINE_NOTICE,
            "sciscinet_methods": SCISCINET_METHODS_NOTICE,
        },
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
            "pgf_non_missing": non_missing_n,
            "pgf_missing": missing_n,
            "pgf_non_missing_pct_of_mode3": _pct(non_missing_n, selected_names),
            "pgf_missing_pct_of_mode3": _pct(missing_n, selected_names),
            "pgf_non_missing_pct_of_outerdict_keys": _pct(non_missing_n, outerdict_keys),
            "pgf_non_missing_population_rows": pgf_non_missing_population_rows,
            "pgf_non_missing_pct_of_population_rows": _pct(
                pgf_non_missing_population_rows, population_rows
            ),
        },
        "rule_counts": {
            "sciscinet_exactly_one_pass": sciscinet_exactly_one_pass,
            "sciscinet_exactly_one_fail": outerdict_keys - sciscinet_exactly_one_pass,
            "xlsx_exact_pass": xlsx_exact_pass,
            "xlsx_exact_fail": outerdict_keys - xlsx_exact_pass,
        },
        "pgf_distribution": {
            "non_missing_n": non_missing_n,
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
        "pgf_inference_evidence_distribution": {
            "inference_counts": inference_counts_dist,
            "inference_sources": inference_sources_dist,
        },
        "pgf_outliers_tukey": {
            "iqr": iqr,
            "lower_fence": lower_fence,
            "upper_fence": upper_fence,
            "lower_outliers": lower_outliers,
            "upper_outliers": upper_outliers,
            "total_outliers": total_outliers,
            "outlier_pct_of_non_missing": _pct(total_outliers, non_missing_n),
        },
        "pgf_buckets": {
            "missing": bucket_missing,
            "exact_0": bucket_exact_0,
            "exact_0_5": bucket_exact_05,
            "exact_1": bucket_exact_1,
            "between_0_and_0_5_exclusive": bucket_between_0_and_0_5_exclusive,
            "between_0_5_and_1_exclusive": bucket_between_0_5_and_1_exclusive,
            "missing_pct_of_mode3": _pct(bucket_missing, selected_names),
            "exact_0_pct_of_mode3": _pct(bucket_exact_0, selected_names),
            "exact_0_5_pct_of_mode3": _pct(bucket_exact_05, selected_names),
            "exact_1_pct_of_mode3": _pct(bucket_exact_1, selected_names),
            "between_0_and_0_5_exclusive_pct_of_mode3": _pct(
                bucket_between_0_and_0_5_exclusive, selected_names
            ),
            "between_0_5_and_1_exclusive_pct_of_mode3": _pct(
                bucket_between_0_5_and_1_exclusive, selected_names
            ),
            "exact_0_pct_of_non_missing": _pct(bucket_exact_0, non_missing_n),
            "exact_0_5_pct_of_non_missing": _pct(bucket_exact_05, non_missing_n),
            "exact_1_pct_of_non_missing": _pct(bucket_exact_1, non_missing_n),
            "between_0_and_0_5_exclusive_pct_of_non_missing": _pct(
                bucket_between_0_and_0_5_exclusive, non_missing_n
            ),
            "between_0_5_and_1_exclusive_pct_of_non_missing": _pct(
                bucket_between_0_5_and_1_exclusive, non_missing_n
            ),
        },
        "pgf_sign_test": {
            "null": "median p_gf = 0.5",
            "scope": "observed mode-3 complete-case unique names only",
            "caveat": (
                "Does not generalize to all unique names without missing-data assumptions "
                "or a missing-data model."
            ),
            "estimand": "unique name keys as a person proxy, not Clarivate award rows",
            "ties_at_0_5_excluded": bucket_exact_05,
            "non_tie_n": sign_test_n,
            "above_0_5": sign_test_above,
            "below_0_5": sign_test_below,
            "proportion_above_0_5": sign_test["proportion"],
            "proportion_above_0_5_ci95_lo": sign_test["ci95_lo"],
            "proportion_above_0_5_ci95_hi": sign_test["ci95_hi"],
            "excess_above_0_5": sign_test["excess_over_0_5"],
            "excess_above_0_5_ci95_lo": sign_test["excess_ci95_lo"],
            "excess_above_0_5_ci95_hi": sign_test["excess_ci95_hi"],
            "exact_binomial_p_two_sided": sign_test["p_two_sided"],
            "exact_binomial_p_two_sided_mantissa": sign_test["p_two_sided_mantissa"],
            "exact_binomial_p_two_sided_exponent": sign_test["p_two_sided_exponent"],
            "exact_binomial_p_two_sided_log10": sign_test["p_two_sided_log10"],
        },
        "missing_pgf_inference_audit": {
            "missing_pgf_rows": bucket_missing,
            "inference_counts_zero": missing_inference_counts_zero,
            "inference_counts_nonzero": missing_inference_counts_nonzero,
            "inference_counts_null": missing_inference_counts_null,
            "inference_sources_zero": missing_inference_sources_zero,
            "inference_sources_nonzero": missing_inference_sources_nonzero,
            "inference_sources_null": missing_inference_sources_null,
            "both_zero": missing_inference_both_zero,
            "all_missing_pgf_have_both_zero": all_missing_pgf_have_both_zero,
            "both_zero_pct_of_missing_pgf_rows": _pct(missing_inference_both_zero, bucket_missing),
        },
    }


def _print_summary(metadata: dict[str, Any]) -> None:
    counts = metadata["counts"]
    dist = metadata["pgf_distribution"]
    evidence = metadata["pgf_inference_evidence_distribution"]
    outliers = metadata["pgf_outliers_tukey"]
    buckets = metadata["pgf_buckets"]
    rules = metadata["rule_counts"]
    sign_test = metadata["pgf_sign_test"]
    missing_audit = metadata["missing_pgf_inference_audit"]

    console.print("[cyan]Mode-3 p_gf Stats Detour (read-only)[/cyan]")
    console.print(f"[white]DB: {metadata['db_file']}[/white]")
    console.print(f"[white]Mode {metadata['mode']}: {metadata['mode_description']}[/white]")
    console.print(
        "[white]Tables used: "
        + ", ".join(str(name) for name in metadata["tables_used"])
        + "[/white]"
    )

    methodology = metadata["methodology_notice"]
    methodology_table = Table(title="p_gf Methodology / Provenance Notice", box=box.SIMPLE)
    methodology_table.add_column("Topic", style="cyan")
    methodology_table.add_column("Notice", style="magenta")
    methodology_table.add_row(
        "nomquamgender name handling",
        methodology["nomquamgender_name_handling"],
    )
    methodology_table.add_row(
        "SciSciNet-v2 pipeline use",
        methodology["sciscinet_v2_pipeline_use"],
    )
    methodology_table.add_row(
        "SciSciNet methods",
        methodology["sciscinet_methods"],
    )
    console.print(methodology_table)

    counts_table = Table(title="Selection Counts", box=box.SIMPLE)
    counts_table.add_column("Metric", style="cyan")
    counts_table.add_column("Value", style="magenta", justify="right")
    counts_table.add_row("Population rows", f"{counts['population_rows']:,}")
    counts_table.add_row("OuterDict keys (step 6)", f"{counts['outerdict_keys']:,}")
    counts_table.add_row("Mode-3 selected names", f"{counts['mode3_selected_names']:,}")
    counts_table.add_row(
        "Mode-3 selected % of OuterDict keys",
        f"{counts['mode3_selected_pct_of_outerdict_keys']:.3f}%",
    )
    counts_table.add_row(
        "Population rows containing mode-3 selected names",
        f"{counts['mode3_selected_population_rows']:,}",
    )
    counts_table.add_row(
        "Mode-3 selected % of population rows",
        f"{counts['mode3_selected_pct_of_population_rows']:.3f}%",
    )
    counts_table.add_row("p_gf non-missing (selected names)", f"{counts['pgf_non_missing']:,}")
    counts_table.add_row("p_gf missing (selected names)", f"{counts['pgf_missing']:,}")
    counts_table.add_row(
        "p_gf non-missing % of mode-3",
        f"{counts['pgf_non_missing_pct_of_mode3']:.3f}%",
    )
    counts_table.add_row(
        "Population rows containing mode-3 selected names with non-missing p_gf",
        f"{counts['pgf_non_missing_population_rows']:,}",
    )
    counts_table.add_row(
        "p_gf non-missing % of population rows",
        f"{counts['pgf_non_missing_pct_of_population_rows']:.3f}%",
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

    dist_table = Table(title="p_gf Distribution (Mode-3, Non-missing Only)", box=box.SIMPLE)
    dist_table.add_column("Metric", style="cyan")
    dist_table.add_column("Value", style="magenta", justify="right")
    dist_table.add_row("N (non-missing)", f"{dist['non_missing_n']:,}")
    dist_table.add_row("Mean", f"{dist['mean']:.6f}")
    dist_table.add_row("95% CI (mean)", f"[{dist['mean_ci95_lo']:.6f}, {dist['mean_ci95_hi']:.6f}]")
    dist_table.add_row("SD", f"{dist['sd']:.6f}")
    dist_table.add_row("SE", f"{dist['se']:.6f}")
    dist_table.add_row("Min", f"{dist['min']:.6f}")
    dist_table.add_row("Q1", f"{dist['q1']:.6f}")
    dist_table.add_row("Median", f"{dist['median']:.6f}")
    dist_table.add_row("Q3", f"{dist['q3']:.6f}")
    dist_table.add_row("Max", f"{dist['max']:.6f}")
    console.print(dist_table)

    evidence_table = Table(
        title="p_gf Inference Evidence Distribution (Mode-3 Selected Names)",
        box=box.SIMPLE,
    )
    evidence_table.add_column("Metric", style="cyan")
    evidence_table.add_column("inference_counts", style="magenta", justify="right")
    evidence_table.add_column("inference_sources", style="magenta", justify="right")
    evidence_counts = evidence["inference_counts"]
    evidence_sources = evidence["inference_sources"]

    def _evidence_pair(metric: str, key: str) -> None:
        counts_value = evidence_counts[key]
        sources_value = evidence_sources[key]
        evidence_table.add_row(
            metric,
            "N/A" if counts_value is None else f"{counts_value:.6f}",
            "N/A" if sources_value is None else f"{sources_value:.6f}",
        )

    evidence_table.add_row(
        "N (non-null)",
        f"{evidence_counts['non_null_n']:,}",
        f"{evidence_sources['non_null_n']:,}",
    )
    evidence_table.add_row(
        "Null",
        f"{evidence_counts['null_n']:,}",
        f"{evidence_sources['null_n']:,}",
    )
    _evidence_pair("Mean", "mean")
    evidence_table.add_row(
        "95% CI (mean)",
        (
            "N/A"
            if evidence_counts["mean_ci95_lo"] is None
            else (
                f"[{evidence_counts['mean_ci95_lo']:.6f}, "
                f"{evidence_counts['mean_ci95_hi']:.6f}]"
            )
        ),
        (
            "N/A"
            if evidence_sources["mean_ci95_lo"] is None
            else (
                f"[{evidence_sources['mean_ci95_lo']:.6f}, "
                f"{evidence_sources['mean_ci95_hi']:.6f}]"
            )
        ),
    )
    _evidence_pair("SD", "sd")
    _evidence_pair("SE", "se")
    _evidence_pair("Min", "min")
    _evidence_pair("Q1", "q1")
    _evidence_pair("Median", "median")
    _evidence_pair("Q3", "q3")
    _evidence_pair("Max", "max")
    console.print(evidence_table)

    p_value = sign_test["exact_binomial_p_two_sided"]
    p_value_mantissa = sign_test["exact_binomial_p_two_sided_mantissa"]
    p_value_exponent = sign_test["exact_binomial_p_two_sided_exponent"]
    if p_value is None:
        p_value_text = "N/A"
    elif p_value < 0.001:
        p_value_text = f"{p_value_mantissa:.6f}e{p_value_exponent:+d}"
    else:
        p_value_text = f"{p_value:.6f}"
    proportion_text = (
        "N/A"
        if sign_test["proportion_above_0_5"] is None
        else (
            f"{sign_test['proportion_above_0_5']:.6f} "
            f"[{sign_test['proportion_above_0_5_ci95_lo']:.6f}, "
            f"{sign_test['proportion_above_0_5_ci95_hi']:.6f}]"
        )
    )
    excess_text = (
        "N/A"
        if sign_test["excess_above_0_5"] is None
        else (
            f"{sign_test['excess_above_0_5']:.6f} "
            f"[{sign_test['excess_above_0_5_ci95_lo']:.6f}, "
            f"{sign_test['excess_above_0_5_ci95_hi']:.6f}]"
        )
    )
    inference_table = Table(
        title="Exact Sign Test (Observed Complete-case Unique Names)",
        box=box.SIMPLE,
    )
    inference_table.add_column("Metric", style="cyan")
    inference_table.add_column("Value", style="magenta", justify="right")
    inference_table.add_row("Null", sign_test["null"])
    inference_table.add_row("Scope", sign_test["scope"])
    inference_table.add_row("Caveat", sign_test["caveat"])
    inference_table.add_row("Estimand", sign_test["estimand"])
    inference_table.add_row("N (p_gf != 0.5)", f"{sign_test['non_tie_n']:,}")
    inference_table.add_row("Above 0.5", f"{sign_test['above_0_5']:,}")
    inference_table.add_row("Below 0.5", f"{sign_test['below_0_5']:,}")
    inference_table.add_row("Ties at 0.5 excluded", f"{sign_test['ties_at_0_5_excluded']:,}")
    inference_table.add_row("Proportion above 0.5 (95% exact CI)", proportion_text)
    inference_table.add_row("Proportion above 0.5 minus 0.5", excess_text)
    inference_table.add_row("Exact binomial p-value (two-sided)", p_value_text)
    console.print(inference_table)

    bucket_table = Table(title="p_gf Buckets (Mode-3 Selected Names)", box=box.SIMPLE)
    bucket_table.add_column("Bucket", style="cyan")
    bucket_table.add_column("Raw", style="magenta", justify="right")
    bucket_table.add_column("% of mode-3", style="magenta", justify="right")
    bucket_table.add_row(
        "exactly 0",
        f"{buckets['exact_0']:,}",
        f"{buckets['exact_0_pct_of_mode3']:.3f}%",
    )
    bucket_table.add_row(
        "0 < p_gf < 0.5",
        f"{buckets['between_0_and_0_5_exclusive']:,}",
        f"{buckets['between_0_and_0_5_exclusive_pct_of_mode3']:.3f}%",
    )
    bucket_table.add_row(
        "exactly 0.5",
        f"{buckets['exact_0_5']:,}",
        f"{buckets['exact_0_5_pct_of_mode3']:.3f}%",
    )
    bucket_table.add_row(
        "0.5 < p_gf < 1",
        f"{buckets['between_0_5_and_1_exclusive']:,}",
        f"{buckets['between_0_5_and_1_exclusive_pct_of_mode3']:.3f}%",
    )
    bucket_table.add_row(
        "exactly 1",
        f"{buckets['exact_1']:,}",
        f"{buckets['exact_1_pct_of_mode3']:.3f}%",
    )
    bucket_table.add_row(
        "missing",
        f"{buckets['missing']:,}",
        f"{buckets['missing_pct_of_mode3']:.3f}%",
    )
    console.print(bucket_table)

    missing_table = Table(
        title="Missing p_gf Inference Audit (Mode-3 Selected Names)",
        box=box.SIMPLE,
    )
    missing_table.add_column("Metric", style="cyan")
    missing_table.add_column("Value", style="magenta", justify="right")
    missing_table.add_row("Missing p_gf rows", f"{missing_audit['missing_pgf_rows']:,}")
    if missing_audit["missing_pgf_rows"] == 0:
        missing_table.add_row("All missing rows have both zeros", "N/A (no missing p_gf rows)")
    else:
        missing_table.add_row(
            "All missing rows have both zeros",
            "Yes" if missing_audit["all_missing_pgf_have_both_zero"] else "No",
        )
        missing_table.add_row(
            "Both inference_counts=0 and inference_sources=0",
            (
                f"{missing_audit['both_zero']:,} "
                f"({missing_audit['both_zero_pct_of_missing_pgf_rows']:.3f}%)"
            ),
        )
    missing_table.add_row(
        "inference_counts == 0", f"{missing_audit['inference_counts_zero']:,}"
    )
    missing_table.add_row(
        "inference_counts != 0 (non-null)", f"{missing_audit['inference_counts_nonzero']:,}"
    )
    missing_table.add_row(
        "inference_counts is NULL", f"{missing_audit['inference_counts_null']:,}"
    )
    missing_table.add_row(
        "inference_sources == 0", f"{missing_audit['inference_sources_zero']:,}"
    )
    missing_table.add_row(
        "inference_sources != 0 (non-null)", f"{missing_audit['inference_sources_nonzero']:,}"
    )
    missing_table.add_row(
        "inference_sources is NULL", f"{missing_audit['inference_sources_null']:,}"
    )
    console.print(missing_table)

    outlier_table = Table(title="Outliers (Tukey 1.5*IQR, Non-missing)", box=box.SIMPLE)
    outlier_table.add_column("Metric", style="cyan")
    outlier_table.add_column("Value", style="magenta", justify="right")
    outlier_table.add_row("IQR", f"{outliers['iqr']:.6f}")
    outlier_table.add_row("Lower fence", f"{outliers['lower_fence']:.6f}")
    outlier_table.add_row("Upper fence", f"{outliers['upper_fence']:.6f}")
    outlier_table.add_row("Lower outliers", f"{outliers['lower_outliers']:,}")
    outlier_table.add_row("Upper outliers", f"{outliers['upper_outliers']:,}")
    outlier_table.add_row("Total outliers", f"{outliers['total_outliers']:,}")
    outlier_table.add_row(
        "Outliers % of non-missing",
        f"{outliers['outlier_pct_of_non_missing']:.3f}%",
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
        metadata = _build_mode3_pgf_metadata(conn)
        _print_summary(metadata)
        result = DetourResult(
            success=True,
            steps_completed=[],
            summary="Computed read-only mode-3 p_gf stats from persisted tables.",
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
            "and prints p_gf stats."
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
