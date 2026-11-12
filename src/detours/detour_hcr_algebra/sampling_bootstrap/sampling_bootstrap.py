"""Bootstrap sampling contrasts using the post-normalization DuckDB population.

Only the designated DuckDB file is read, with one thread and a 128 MiB limit.
The completed remainder is a permutation of award rows absent from the prefix;
it does not alter the first-310-draw statistics compared across designs.
Canonical string fields are represented by nonblank indicators. Category,
priority label, and income group values are represented by one-hot indicators.
"""

import argparse
from collections.abc import Sequence
from contextlib import redirect_stdout
from io import StringIO
from math import erfc, sqrt
from pathlib import Path
from typing import Literal

import duckdb
import numpy as np

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

REPS, BOOT, BATCH = 20_000, 1_000, 1_000
ALPHA = 0.05
MISSING_INCOME_GROUP = "<missing>"


def format_number(
    value: float,
    kind: Literal["integer", "count", "p"],
    *,
    signed: bool = False,
) -> str:
    """Format all reported numbers by type; calculations retain full precision."""
    number = float(value)
    if kind == "integer":
        return f"{int(round(number)):,}"
    if kind == "count":
        places = 4 if 0 < abs(number) < 0.01 else 2
        return f"{number:+,.{places}f}" if signed else f"{number:,.{places}f}"
    if kind == "p":
        return "<0.0001" if number < 0.0001 else f"{number:.4f}"
    raise ValueError(f"Unknown number kind: {kind}")


def main() -> None:
    con = duckdb.connect("data/scisci_process.duckdb", read_only=True)
    try:
        con.execute("SET threads = 1")
        con.execute("SET memory_limit = '128MB'")
        canonical_fields = (
            KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL,
            KTP_HCR_PRIMARY_AFFILIATIONS_COL, KTP_HCR_SECONDARY_AFFILIATIONS_COL,
        )
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
    assert [row[0] for row in rows] == list(range(population_size))
    observed = np.array([index for index, _ in sampled], dtype=np.int32)
    pilots = np.array(
        [index for index, draw in sampled if str(draw).startswith("pilot.")],
        dtype=np.int32,
    )
    assert population_size == 59_665 and len(observed) == 310 and len(pilots) == 10
    award_year = np.array([int(row[1][:4]) for row in rows], dtype=np.int16)
    years = sorted(set(award_year.tolist()))
    assert years == list(range(2014, 2025))
    is_2024 = award_year == 2024
    assert is_2024[pilots].all()

    name_map: dict[tuple[str, str], int] = {}
    name_id = np.full(population_size, -1, dtype=np.int32)
    for index, (_, _, first, last, *_) in enumerate(rows):
        if first is not None and last is not None and first != "" and last != "":
            name_id[index] = name_map.setdefault((first, last), len(name_map))
    categories = sorted({row[4] for row in rows if row[4] is not None})
    category_values = np.array([row[4] for row in rows], dtype=object)
    priorities = sorted({row[7] for row in rows if row[7] is not None})
    priority_values = np.array([row[7] for row in rows], dtype=object)
    income_groups = sorted(
        {row[8] if row[8] is not None else MISSING_INCOME_GROUP for row in rows}
    )
    income_values = np.array(
        [row[8] if row[8] is not None else MISSING_INCOME_GROUP for row in rows],
        dtype=object,
    )
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

    def metrics(draws: np.ndarray) -> np.ndarray:
        source = np.sort(draws, axis=1)
        keys = np.sort(name_id[draws], axis=1)
        unique_sources = 1 + (source[:, 1:] != source[:, :-1]).sum(axis=1)
        unique_keys = 1 + (keys[:, 1:] != keys[:, :-1]).sum(axis=1) - (keys[:, 0] == -1)
        return np.column_stack(
            (
                unique_sources,
                unique_keys,
                is_2024[draws].sum(axis=1),
                np.isin(draws, pilots).sum(axis=1),
                features[draws].mean(axis=1, dtype=np.float64),
            )
        )

    rng = np.random.default_rng(20261112)
    protocol = np.empty((REPS, 4 + len(feature_labels)), dtype=np.float64)
    fair = np.empty_like(protocol)
    completed_lengths: list[int] = []
    for start in range(0, REPS, BATCH):
        batch_size = min(BATCH, REPS - start)
        fixed = np.broadcast_to(pilots, (batch_size, len(pilots)))
        # Actual protocol: hand-picked pilots plus original replacement sampler.
        protocol_draws = np.concatenate(
            (fixed, rng.integers(population_size, size=(batch_size, 300))),
            axis=1,
        )
        # Fair comparator: 310 distinct award rows, uniformly without replacement.
        fair_draws = np.stack(
            [
                rng.choice(
                    population_size,
                    size=len(observed),
                    replace=False,
                    shuffle=False,
                )
                for _ in range(batch_size)
            ]
        )
        end = start + batch_size
        protocol[start:end] = metrics(protocol_draws)
        fair[start:end] = metrics(fair_draws)

        if start == 0:
            for prefix in protocol_draws[:100]:
                seen = np.zeros(population_size, dtype=bool)
                seen[prefix] = True
                remainder = rng.permutation(np.flatnonzero(~seen))
                completed = np.concatenate((prefix, remainder))
                assert len(np.unique(completed)) == population_size
                completed_lengths.append(len(completed))

    assert np.all(fair[:, 0] == len(observed))

    boot_rng = np.random.default_rng(20261113)
    protocol_diff = np.empty((BOOT, protocol.shape[1]))
    for index in range(BOOT):
        fair_boot_mean = fair[boot_rng.integers(REPS, size=REPS)].mean(axis=0)
        protocol_diff[index] = (
            protocol[boot_rng.integers(REPS, size=REPS)].mean(axis=0)
            - fair_boot_mean
        )
    protocol_ci = np.quantile(protocol_diff, [0.025, 0.975], axis=0)
    actual = metrics(observed.reshape(1, -1))[0]

    # Infer on the protocol-minus-fair mean contrast, testing each metric once.
    test_columns = np.array([0, 1, 3, *range(4, protocol.shape[1])])
    test_labels = [
        "distinct_awards", "distinct_NameKeys", "pilot_row_occurrences", *feature_labels
    ]
    mean_difference = protocol.mean(axis=0) - fair.mean(axis=0)
    standard_error = np.sqrt(
        protocol.var(axis=0, ddof=1) / REPS + fair.var(axis=0, ddof=1) / REPS
    )
    varying = standard_error[test_columns] > 0
    test_columns = test_columns[varying]
    test_labels = [label for label, include in zip(test_labels, varying, strict=True) if include]
    test_count = len(test_labels)
    test_by_column = {int(column): position for position, column in enumerate(test_columns)}

    p_values = np.array(
        [
            erfc(abs(mean_difference[column]) / (sqrt(2) * standard_error[column]))
            for column in test_columns
        ]
    )
    p_order = np.argsort(p_values, kind="stable")
    holm_sorted = np.maximum.accumulate(
        np.minimum(1.0, (test_count - np.arange(test_count)) * p_values[p_order])
    )
    holm_p = np.empty_like(p_values)
    holm_p[p_order] = holm_sorted
    unadjusted_discoveries = int(
        ((protocol_ci[0, test_columns] > 0) | (protocol_ci[1, test_columns] < 0)).sum()
    )
    holm_discoveries = int((holm_p < ALPHA).sum())

    def comparison_cells(column: int, scale: float) -> tuple[str, ...]:
        protocol_mean = scale * protocol[:, column].mean()
        fair_mean = scale * fair[:, column].mean()
        return (
            format_number(protocol_mean, "count"),
            format_number(fair_mean, "count"),
            f"{format_number(protocol_mean - fair_mean, 'count', signed=True)} "
            f"[{format_number(scale * protocol_ci[0, column], 'count', signed=True)}, "
            f"{format_number(scale * protocol_ci[1, column], 'count', signed=True)}]",
        )

    year_2024_column = 4 + year_offset + years.index(2024)

    def p_cells(column: int) -> tuple[str, str]:
        position = test_by_column.get(year_2024_column if column == 2 else column)
        if position is None:
            return "—", "—"
        return format_number(p_values[position], "p"), format_number(holm_p[position], "p")

    def markdown_table(
        headers: tuple[str, ...], table_rows: Sequence[tuple[str, ...]]
    ) -> None:
        print("| " + " | ".join(headers) + " |")
        print("| " + " | ".join("---" for _ in headers) + " |")
        for cells in table_rows:
            print("| " + " | ".join(cells) + " |")
        print()

    print("# HCR award-row sampling comparison\n")
    print(f"Generated by `{Path(__file__).name}`.\n")
    print(
        f"{format_number(len(pilots), 'integer')} pilots were picked by hand before "
        "the original sampler, which then unintentionally used replacement for "
        f"{format_number(len(observed) - len(pilots), 'integer')} draws and could "
        "redraw those pilots. Although neither duplication nor pilot redraw occurred "
        "in the stored run, this report compares that actual procedure with "
        f"{format_number(len(observed), 'integer')} uniform draws without replacement.\n"
    )
    print(
        f"Source: read-only DuckDB post-normalization view "
        f"`{POPULATION_ECON_VIEW}` with **{format_number(population_size, 'integer')} "
        f"award rows**; observed `{SAMPLES_TABLE}` contain "
        f"**{format_number(len(observed), 'integer')} "
        f"draws**, including **{format_number(len(pilots), 'integer')} "
        "fixed pilots** from 2024.\n"
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
        f"columns from `{POPULATION_ECON_VIEW}`; category values remain "
        "exact source labels.\n"
    )
    print(
        f"Simulations: **{format_number(REPS, 'integer')} per design**; "
        f"bootstrap: **{format_number(BOOT, 'integer')} resamples**.\n"
    )
    print(
        "**Rounding:** observed, population, and simulation counts are integers "
        "with thousands separators; count means, differences, and interval bounds "
        "use 2 decimals, or 4 when nonzero magnitude is below 0.01; p-values use 4 "
        "decimals, with values below 0.0001 shown as `<0.0001`. Calculations "
        "use unrounded values.\n"
    )
    print(
        f"- **Actual protocol:** {format_number(len(pilots), 'integer')} hand-picked "
        f"pilots plus {format_number(len(observed) - len(pilots), 'integer')} draws "
        "from the original replacement sampler's full award-row pool."
    )
    print(
        f"- **Fair:** {format_number(len(observed), 'integer')} distinct award rows "
        "uniformly sampled without "
        "replacement from the full population.\n"
    )
    print(f"## First {format_number(len(observed), 'integer')} draws\n")
    core_headers = (
        "Metric", "Observed", "Actual-protocol mean", "Fair mean",
        "Δ protocol−fair, rows [95% CI]", "Two-sided p", "Holm p",
    )
    core_labels = (
        "Distinct award rows", "Distinct NameKeys", "2024 award rows",
        "Pilot-row occurrences",
    )
    core_rows = [
        (
            label, format_number(actual[column], "integer"),
            *comparison_cells(column, 1.0), *p_cells(column),
        )
        for column, label in enumerate(core_labels)
    ]
    markdown_table(core_headers, core_rows)
    print(
        "Pilot-row occurrences counts selections of the "
        f"{format_number(len(pilots), 'integer')} hand-picked award rows; "
        "replacement can select one again.\n"
    )

    print("## Protocol-versus-fair inference\n")
    print(
        "Each nonconstant first-310-draw metric tests whether the actual-protocol "
        "and fair **mean values differ**. The 2024 core count duplicates the "
        "year:2024 count and is tested once. Two-sided normal p-values use the "
        "Monte Carlo standard error of the simulated mean difference; Holm "
        "adjustment covers all tested metrics. The 95% bootstrap CIs describe "
        "precision of the estimated design-mean difference, not variation of "
        "one sample. Differences and intervals are reported in rows per "
        "first-310-draw sample.\n"
    )
    markdown_table(
        ("Statistic", "Computed value"),
        [
            ("Nonconstant metrics tested", format_number(test_count, "integer")),
            ("Constant metrics excluded", format_number((~varying).sum(), "integer")),
            (
                "Nominal false positives if all nulls hold (5% per metric)",
                format_number(ALPHA * test_count, "count"),
            ),
            (
                "Observed 95% bootstrap CIs excluding zero",
                format_number(unadjusted_discoveries, "integer"),
            ),
            (
                "Metrics with Holm-adjusted p < 0.05",
                format_number(holm_discoveries, "integer"),
            ),
        ],
    )

    print("### Ten largest absolute mean differences in rows\n")
    top_rows = []
    difference_rows = mean_difference[test_columns] * np.where(
        test_columns < 4, 1, len(observed)
    )
    size_order = np.argsort(-np.abs(difference_rows), kind="stable")
    for position in size_order[:10]:
        column = int(test_columns[position])
        scale = 1.0 if column < 4 else float(len(observed))
        top_rows.append(
            (
                f"`{test_labels[position]}`",
                comparison_cells(column, scale)[2],
                format_number(p_values[position], "p"),
                format_number(holm_p[position], "p"),
            )
        )
    markdown_table(
        ("Metric", "Δ mean rows [95% bootstrap CI]", "Two-sided p", "Holm p"),
        top_rows,
    )

    print("## Completion checks\n")
    markdown_table(
        ("Metric", "Computed value"),
        [
            (
                "Completed actual-protocol runs",
                format_number(len(completed_lengths), "integer"),
            ),
            (
                "Distinct award rows per completed run",
                format_number(population_size, "integer"),
            ),
            (
                "Completed sequence length, mean",
                format_number(np.mean(completed_lengths), "count"),
            ),
            (
                "Completed sequence length, minimum",
                format_number(min(completed_lengths), "integer"),
            ),
            (
                "Completed sequence length, maximum",
                format_number(max(completed_lengths), "integer"),
            ),
        ],
    )

    print("## Award year\n")
    print("Year is taken from each award row's stored HCR filename. Values are **row counts**.\n")
    year_headers = (
        "Year", "Population rows", "Observed rows", "Actual-protocol mean",
        "Fair mean", "Δ protocol−fair, rows [95% CI]", "Two-sided p", "Holm p",
    )
    year_rows = []
    for offset, year in enumerate(years, start=4 + year_offset):
        year_rows.append(
            (
                str(year), format_number((award_year == year).sum(), "integer"),
                format_number(len(observed) * actual[offset], "integer"),
                *comparison_cells(offset, float(len(observed))),
                *p_cells(offset),
            )
        )
    markdown_table(year_headers, year_rows)

    indicator_headers = (
        "Value", "Observed rows", "Actual-protocol mean", "Fair mean",
        "Δ protocol−fair, rows [95% CI]", "Two-sided p", "Holm p",
    )

    def indicator_rows(values: Sequence[str], feature_offset: int) -> list[tuple[str, ...]]:
        table_rows = []
        for offset, value in enumerate(values, start=4 + feature_offset):
            table_rows.append(
                (
                    f"`{value}`",
                    format_number(len(observed) * actual[offset], "integer"),
                    *comparison_cells(offset, float(len(observed))),
                    *p_cells(offset),
                )
            )
        return table_rows

    print("## Canonical post-normalization fields: nonblank row counts\n")
    print("Counts include rows with a nonblank canonical field value.\n")
    markdown_table(indicator_headers, indicator_rows(canonical_fields, 0))

    print("## HCR category: exact-value row counts\n")
    markdown_table(indicator_headers, indicator_rows(categories, category_offset))

    print("## Derived priority labels: row counts\n")
    markdown_table(indicator_headers, indicator_rows(priorities, priority_offset))

    print("## Derived World Bank income groups: row counts\n")
    print(f"`{MISSING_INCOME_GROUP}` represents a null income-group value.\n")
    markdown_table(indicator_headers, indicator_rows(income_groups, income_offset))
    print(
        "**Method note:** Δ is actual-protocol mean minus fair mean. The bootstrap "
        "intervals and p-values quantify Monte Carlo precision of the estimated "
        "design-mean contrast, not variation across individual samples."
    )


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Compare the historical HCR sample protocol with fair sampling.",
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
    args.output.write_text(report.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    cli()
