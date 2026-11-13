"""Compare actual and fair HCR award-row sampling designs on the stored population.

The designated DuckDB file is read only, with one thread and a 128 MB limit
(reported by DuckDB as 122 MiB). The later permutation of undrawn rows cannot
change the first-310-draw outcomes compared here.
"""

import argparse
from collections.abc import Sequence
from contextlib import redirect_stdout
from functools import cache
from io import StringIO
from math import expm1, log1p, sqrt
from pathlib import Path
from typing import Literal

import duckdb
import numpy as np

from src.detours.detour_hcr_algebra.shared import markdown_table
from src.helpers.schema import POPULATION_ECON_VIEW, POPULATION_TABLE, SAMPLES_TABLE
from src.helpers.vars import (
    DRAW_LABEL,
    HCR_CATEGORY_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_HCR_FILENAME_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_ROW_NUMBER_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_LAST_NAME_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_GROUP_COL,
)

REPS, BATCH, SEED = 20_000, 1_000, 20261112
SD_CHECK_MIN_RANDOM_COUNT, SD_CHECK_RTOL = 5, 0.05
MISSING_VALUE = "<missing>"
PILOT_DRAW_PREFIX = "pilot."


def format_number(
    value: float,
    kind: Literal["integer", "decimal"],
    *,
    signed: bool = False,
) -> str:
    """Centralize report rounding; all calculations use unrounded values."""
    number = float(value)
    if kind == "integer":
        return f"{int(round(number)):,}"
    if kind == "decimal":
        magnitude = abs(number)
        places = 2 if magnitude == 0 or magnitude >= 0.01 else 4 if magnitude >= 0.0001 else 6
        return f"{number:+,.{places}f}" if signed else f"{number:,.{places}f}"
    raise ValueError(f"Unknown number kind: {kind}")


@cache
def inclusion_probability(
    population_size: int, draws: int, group_size: int, *, replacement: bool
) -> float:
    """Probability that at least one row from a group occurs among the draws."""
    if draws == 0 or group_size == 0:
        return 0.0
    if group_size == population_size:
        return 1.0
    if replacement:
        return -expm1(draws * log1p(-group_size / population_size))
    if group_size > population_size - draws:
        return 1.0
    return -expm1(
        sum(log1p(-group_size / (population_size - draw)) for draw in range(draws))
    )


def main() -> None:
    con = duckdb.connect("data/scisci_process.duckdb", read_only=True)
    try:
        con.execute("SET threads = 1")
        con.execute("SET memory_limit = '128MB'")
        rows = con.execute(f'''
            SELECT "{KTP_POPULATION_INDEX_COL}", "{KTP_HCR_FILENAME_COL}",
                   "{KTP_FIRST_NAME_COL}", "{KTP_LAST_NAME_COL}",
                   "{HCR_CATEGORY_COL}", "{KTP_HCR_PRIMARY_AFFILIATIONS_COL}",
                   "{KTP_HCR_SECONDARY_AFFILIATIONS_COL}",
                   "{KTP_PRIORITY_GROUP_COL}", "{KTP_ECONOMIES_INCOME_GROUP_COL}"
            FROM {POPULATION_ECON_VIEW}
            ORDER BY "{KTP_POPULATION_INDEX_COL}"
        ''').fetchall()
        sampled = con.execute(f'''
            SELECT p."{KTP_POPULATION_INDEX_COL}", s."{DRAW_LABEL}"
            FROM {SAMPLES_TABLE} s JOIN {POPULATION_ECON_VIEW} p
              ON s."{KTP_FILENAME_COL}" = p."{KTP_HCR_FILENAME_COL}"
             AND s."{KTP_FRAGMENT_COL}" = p."{KTP_HCR_ROW_NUMBER_COL}"
        ''').fetchall()
    finally:
        con.close()

    population_size = len(rows)
    stored_indices = np.array([index for index, _ in sampled], dtype=np.int32)
    pilots = np.array(
        [index for index, draw in sampled if str(draw).startswith(PILOT_DRAW_PREFIX)],
        dtype=np.int32,
    )
    assert population_size == 59_665 and [row[0] for row in rows] == list(range(population_size))
    assert len(stored_indices) == 310 and len(pilots) == 10 and len(np.unique(pilots)) == 10
    draws_per_sample = len(stored_indices)
    random_draws = draws_per_sample - len(pilots)

    award_year = np.array([int(row[1][:4]) for row in rows], dtype=np.int16)
    years = sorted(set(award_year.tolist()))
    assert years == list(range(2014, 2025))
    assert np.all(award_year[pilots] == award_year[pilots[0]])
    pilot_year = int(award_year[pilots[0]])

    name_map: dict[tuple[str, str], int] = {}
    name_id = np.full(population_size, -1, dtype=np.int32)
    for index, (_, _, first, last, *_) in enumerate(rows):
        if first is not None and last is not None and first.strip() and last.strip():
            name_id[index] = name_map.setdefault((first, last), len(name_map))

    canonical_fields = (
        KTP_FIRST_NAME_COL,
        KTP_LAST_NAME_COL,
        KTP_HCR_PRIMARY_AFFILIATIONS_COL,
        KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    )
    source_category = [row[4] for row in rows]
    source_priority = [row[7] for row in rows]
    source_income = [row[8] for row in rows]
    assert all(
        MISSING_VALUE not in values
        for values in (source_category, source_priority, source_income)
    )
    category_values = np.array(
        [value if value is not None else MISSING_VALUE for value in source_category], dtype=object
    )
    priority_values = np.array(
        [value if value is not None else MISSING_VALUE for value in source_priority], dtype=object
    )
    income_values = np.array(
        [value if value is not None else MISSING_VALUE for value in source_income], dtype=object
    )
    categories = sorted(set(category_values.tolist()))
    priorities = sorted(set(priority_values.tolist()))
    income_groups = sorted(set(income_values.tolist()))
    field_offset = 0
    category_offset = len(canonical_fields)
    priority_offset = category_offset + len(categories)
    income_offset = priority_offset + len(priorities)
    year_offset = income_offset + len(income_groups)
    feature_labels = (
        [f"nonblank:{column}" for column in canonical_fields]
        + [f"category:{category}" for category in categories]
        + [f"priority:{priority}" for priority in priorities]
        + [f"income:{group}" for group in income_groups]
        + [f"year:{year}" for year in years]
    )
    features = np.empty((population_size, len(feature_labels)), dtype=np.bool_)
    features[:, :len(canonical_fields)] = np.fromiter(
        (
            value is not None and bool(value.strip())
            for row in rows
            for value in (row[2], row[3], row[5], row[6])
        ),
        dtype=np.bool_,
        count=population_size * len(canonical_fields),
    ).reshape(population_size, len(canonical_fields))
    for offset, category in enumerate(categories, start=category_offset):
        features[:, offset] = category_values == category
    for offset, priority in enumerate(priorities, start=priority_offset):
        features[:, offset] = priority_values == priority
    for offset, group in enumerate(income_groups, start=income_offset):
        features[:, offset] = income_values == group
    for offset, year in enumerate(years, start=year_offset):
        features[:, offset] = award_year == year
    for start, end in (
        (category_offset, priority_offset),
        (priority_offset, income_offset),
        (income_offset, year_offset),
        (year_offset, len(feature_labels)),
    ):
        assert np.all(features[:, start:end].sum(axis=1) == 1)

    def metrics(draws: np.ndarray) -> np.ndarray:
        sources = np.sort(draws, axis=1)
        keys = np.sort(name_id[draws], axis=1)
        distinct_awards = 1 + (sources[:, 1:] != sources[:, :-1]).sum(axis=1)
        distinct_keys = 1 + (keys[:, 1:] != keys[:, :-1]).sum(axis=1) - (keys[:, 0] == -1)
        return np.column_stack(
            (distinct_awards, distinct_keys, features[draws].sum(axis=1, dtype=np.int32))
        )

    fair_rng, actual_rng = (
        np.random.default_rng(seed) for seed in np.random.SeedSequence(SEED).spawn(2)
    )
    metric_count = 2 + len(feature_labels)
    fair = np.empty((REPS, metric_count), dtype=np.float64)
    actual = np.empty_like(fair)
    for start in range(0, REPS, BATCH):
        batch_size = min(BATCH, REPS - start)
        fixed = np.broadcast_to(pilots, (batch_size, len(pilots)))
        # Actual protocol: hand-picked pilots plus original full-pool replacement draws.
        actual_draws = np.concatenate(
            (fixed, actual_rng.integers(population_size, size=(batch_size, random_draws))),
            axis=1,
        )
        # Fair design: uniform award rows without replacement.
        fair_draws = np.stack(
            [
                fair_rng.choice(population_size, size=draws_per_sample, replace=False)
                for _ in range(batch_size)
            ]
        )
        end = start + batch_size
        actual[start:end] = metrics(actual_draws)
        fair[start:end] = metrics(fair_draws)

    population_counts = features.sum(axis=0, dtype=np.int64)
    pilot_counts = features[pilots].sum(axis=0, dtype=np.int64)
    prevalence = population_counts / population_size
    fair_mean = np.empty(metric_count)
    actual_mean = np.empty(metric_count)
    fair_mean[2:] = draws_per_sample * prevalence
    actual_mean[2:] = pilot_counts + random_draws * prevalence
    fair_mean[0] = draws_per_sample
    actual_mean[0] = len(pilots) + (population_size - len(pilots)) * inclusion_probability(
        population_size, random_draws, 1, replacement=True
    )

    name_frequencies = np.bincount(name_id[name_id >= 0])
    pilot_keys = {int(key) for key in name_id[pilots] if key >= 0}
    fair_mean[1] = sum(
        inclusion_probability(population_size, draws_per_sample, int(frequency), replacement=False)
        for frequency in name_frequencies
    )
    actual_mean[1] = len(pilot_keys) + sum(
        inclusion_probability(population_size, random_draws, int(frequency), replacement=True)
        for key, frequency in enumerate(name_frequencies)
        if key not in pilot_keys
    )
    difference = actual_mean - fair_mean

    simulated_fair_sd = fair.std(axis=0, ddof=1)
    simulated_actual_sd = actual.std(axis=0, ddof=1)
    fair_sd = simulated_fair_sd.copy()
    actual_sd = simulated_actual_sd.copy()
    fair_sd[2:] = np.sqrt(
        draws_per_sample * prevalence * (1 - prevalence)
        * (population_size - draws_per_sample) / (population_size - 1)
    )
    actual_sd[2:] = np.sqrt(random_draws * prevalence * (1 - prevalence))
    # Rare indicators have noisy simulated SDs; compare where both outcomes recur.
    sd_check = random_draws * np.minimum(prevalence, 1 - prevalence) >= SD_CHECK_MIN_RANDOM_COUNT
    assert sd_check.any()
    for simulated_sd, exact_sd in (
        (simulated_fair_sd, fair_sd),
        (simulated_actual_sd, actual_sd),
    ):
        assert np.all(
            np.abs(simulated_sd[2:][sd_check] - exact_sd[2:][sd_check])
            <= SD_CHECK_RTOL * exact_sd[2:][sd_check]
        )
    fair_range = np.quantile(fair, [0.025, 0.975], axis=0, method="nearest")
    actual_range = np.quantile(actual, [0.025, 0.975], axis=0, method="nearest")
    rmse_actual = np.sqrt(actual_sd**2 + difference**2)
    sd_ratio = np.divide(
        difference,
        fair_sd,
        out=np.full(metric_count, np.nan),
        where=fair_sd > 0,
    )
    rmse_ratio = np.divide(
        rmse_actual,
        fair_sd,
        out=np.full(metric_count, np.nan),
        where=fair_sd > 0,
    )

    # Independent formulas check the simulated design means, not their significance.
    for simulated, expected, simulated_sd in (
        (fair, fair_mean, simulated_fair_sd),
        (actual, actual_mean, simulated_actual_sd),
    ):
        simulation_se = simulated_sd / sqrt(REPS)
        assert np.all(np.abs(simulated.mean(axis=0) - expected) <= 6 * simulation_se + 1e-7)
    assert np.all(fair[:, 0] == draws_per_sample)

    def design_cell(column: int, *, fair_design: bool) -> str:
        mean = fair_mean if fair_design else actual_mean
        sd = fair_sd if fair_design else actual_sd
        interval = fair_range if fair_design else actual_range
        return (
            f"{format_number(mean[column], 'decimal')} ± "
            f"{format_number(sd[column], 'decimal')} "
            f"[{format_number(interval[0, column], 'integer')}, "
            f"{format_number(interval[1, column], 'integer')}]"
        )

    def ratio_cell(value: float, *, signed: bool = False) -> str:
        return "—" if np.isnan(value) else format_number(value, "decimal", signed=signed)

    def comparison_row(
        label: str, column: int, population_rows: int | None, pilot_rows: int | None
    ) -> tuple[str, ...]:
        return (
            label,
            "—" if population_rows is None else format_number(population_rows, "integer"),
            "—" if pilot_rows is None else format_number(pilot_rows, "integer"),
            design_cell(column, fair_design=True),
            design_cell(column, fair_design=False),
            format_number(difference[column], "decimal", signed=True),
            ratio_cell(sd_ratio[column], signed=True),
            ratio_cell(rmse_ratio[column]),
        )

    headers = (
        "Metric", "Population rows", "Pilot rows", "Fair E ± SD [95% range]",
        "Actual E ± SD [95% range]", "Δ expected count", "Δ / fair SD",
        "RMSE ratio (actual/fair)",
    )
    print("# HCR award-row sampling comparison\n")
    print(f"Generated by `{Path(__file__).name}`.\n")
    print(
        f"{format_number(len(pilots), 'integer')} pilots were picked by hand before "
        "the original sampler, which then unintentionally used replacement for "
        f"{format_number(random_draws, 'integer')} draws and could redraw those "
        "pilots. Although neither duplication nor pilot redraw occurred in the "
        "stored run, this report compares that actual procedure with "
        f"{format_number(draws_per_sample, 'integer')} uniform draws without "
        "replacement.\n"
    )
    print(
        f"Source: read-only DuckDB post-normalization view `{POPULATION_ECON_VIEW}` "
        f"with **{format_number(population_size, 'integer')} award rows**; "
        f"observed `{SAMPLES_TABLE}` contain "
        f"**{format_number(draws_per_sample, 'integer')} draws**, including "
        f"**{format_number(len(pilots), 'integer')} fixed pilots** from {pilot_year}.\n"
    )
    print("## Data lineage\n")
    print(
        "1. Step 1 registers the configured Clarivate HCR XLSX inputs and verifies "
        "their configured SHA-256 hashes."
    )
    print(
        "2. Step 2 reads the XLSX rows, normalizes header spelling, coerces "
        "non-index fields to strings, aligns columns across files, and appends "
        f"the rows to `{POPULATION_TABLE}` with filename, Excel row, and population index."
    )
    print(
        f"3. Step 3 maps year-specific name headers to `{KTP_FIRST_NAME_COL}` "
        f"and `{KTP_LAST_NAME_COL}`."
    )
    print(
        "4. Step 4 maps year-specific affiliation headers to canonical primary/"
        "secondary affiliations, matches World Bank economies and income groups, "
        "and computes priority labels. This report selects those post-normalization "
        "columns from "
        f"`{POPULATION_ECON_VIEW}`; category values remain exact source labels.\n"
    )
    print("## Measures\n")
    print(
        "All indicator counts are **draw occurrences**: repeated selection of an "
        "award row counts again. `Distinct award rows` and `Distinct canonical "
        "name pairs` instead count distinct values; a name-pair key is the exact "
        "canonical first-name/last-name pair when both are nonblank, not a "
        "verified person ID."
    )
    print(
        "Both designs sample award rows, so a researcher with multiple award "
        "rows can appear more than once in the population."
    )
    print(
        f"For an indicator with {format_number(population_size, 'integer')} population "
        "rows, K matching rows, and H matching pilots, exact expected draw counts "
        f"are fair = {format_number(draws_per_sample, 'integer')} × K / N and "
        f"actual = H + {format_number(random_draws, 'integer')} × K / N. "
        "Distinct-count expectations use exact inclusion probabilities."
    )
    print(
        "At a fixed random-draw count, replacement changes indicator dispersion "
        "but not expected counts, so indicator mean shifts here are set by these "
        "pilots; distinct-award repeats can arise within the random draws or when "
        "a draw reselects a pilot."
    )
    print(
        "SD is sample-to-sample variation: exact for indicator counts and estimated "
        f"from {format_number(REPS, 'integer')} simulated samples per design for "
        f"the distinct counts. Independent streams come from seed {SEED}. "
        "Bracketed ranges are the central 95% of simulated "
        "individual-sample counts (nearest simulated quantiles), not confidence "
        "intervals for design means."
    )
    print(
        "Δ is actual minus fair expected count. `Δ / fair SD` expresses that shift "
        "relative to fair samples' typical variation. RMSE measures each design's "
        "root-mean-square distance from the fair design's exact expectation; the "
        "last column is actual RMSE divided by fair RMSE. A ratio of 1.00 means "
        "equal RMSE; above 1.00 means larger actual RMSE and below 1.00 means "
        "smaller actual RMSE. Its percentage difference is 100 × (ratio − 1). "
        "A zero fair SD makes those ratios undefined (`—`).\n"
    )
    print(
        "**Rounding:** population and pilot counts and sample-range bounds are "
        "integers with thousands separators. Means, SDs, differences, and ratios "
        "use 2 decimals, 4 when nonzero magnitude is below 0.01, and 6 when "
        "nonzero magnitude is below 0.0001. Calculations use unrounded values.\n"
    )
    print("## Distinct counts\n")
    markdown_table(
        headers,
        [
            comparison_row("Distinct award rows", 0, None, None),
            comparison_row("Distinct canonical name pairs", 1, None, None),
        ],
    )

    rank_columns = [0, 1, *range(2, metric_count)]
    ranked = sorted(rank_columns, key=lambda column: -abs(difference[column]))[:10]
    print("## Ten largest absolute expected-count differences\n")
    markdown_table(
        ("Metric", "Δ expected count", "Fair SD", "Δ / fair SD", "RMSE ratio (actual/fair)"),
        [
            (
                f"`{['distinct_awards', 'distinct_name_pairs', *feature_labels][column]}`",
                format_number(difference[column], "decimal", signed=True),
                format_number(fair_sd[column], "decimal"),
                ratio_cell(sd_ratio[column], signed=True),
                ratio_cell(rmse_ratio[column]),
            )
            for column in ranked
        ],
    )

    def indicator_rows(values: Sequence[str], feature_offset: int) -> list[tuple[str, ...]]:
        return [
            comparison_row(
                f"`{value}`", column,
                int(population_counts[column - 2]),
                int(pilot_counts[column - 2]),
            )
            for column, value in enumerate(values, start=2 + feature_offset)
        ]

    print("## Award year\n")
    print(f"Year is parsed from `{KTP_HCR_FILENAME_COL}`.\n")
    markdown_table(headers, indicator_rows([str(year) for year in years], year_offset))

    print("## Canonical post-normalization fields: nonblank draw occurrences\n")
    markdown_table(headers, indicator_rows(canonical_fields, field_offset))

    print("## HCR category: exact-value draw occurrences\n")
    markdown_table(headers, indicator_rows(categories, category_offset))

    print("## Derived priority label: draw occurrences\n")
    markdown_table(headers, indicator_rows(priorities, priority_offset))

    print("## Derived World Bank income group: draw occurrences\n")
    print(f"`{MISSING_VALUE}` denotes a null source value in any categorical group.\n")
    markdown_table(headers, indicator_rows(income_groups, income_offset))


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Compare actual-protocol and fair HCR award-row sampling designs.",
        epilog="Without --output, the Markdown report is written to stdout.",
    )
    parser.add_argument(
        "-o", "--output", type=Path, metavar="PATH",
        help="Write the Markdown report to PATH instead of stdout.",
    )
    args = parser.parse_args()
    if args.output is None:
        main()
        return

    report = StringIO()
    with redirect_stdout(report):
        main()
    args.output.write_text(report.getvalue().rstrip("\n") + "\n", encoding="utf-8")


if __name__ == "__main__":
    cli()
