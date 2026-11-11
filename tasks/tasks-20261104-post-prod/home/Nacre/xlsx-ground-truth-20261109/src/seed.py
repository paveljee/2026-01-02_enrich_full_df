"""Seed one JSONL line per all-mode3 draw, with first-draw ownership.

Allowed dependencies: `pixi list -e $FEATURE --explicit`.
"""

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import duckdb
import numpy as np
from shared import (
    MSG_APPENDIX_HEADER,
    MSG_DEFINITIONS,
    MSG_DRAW_OBSERVATION,
    MSG_NAME_REPEAT,
    MSG_NO_NAME_REPEATS,
    NAME_FIRST_COL,
    NAME_LAST_COL,
    REVIEW_SOURCE_COLUMNS,
    TEXT_ENCODING,
    ReportQualifier,
    ReportText,
    SeedHandoff,
    report_path,
)

SCRIPT_DIR = Path(__file__).resolve().parent
WORKDIR = SCRIPT_DIR.parent
ROOT = WORKDIR.parents[4]
ASSIGNEE = "Pavel"
INPUT_DIR = WORKDIR / "in"
CONFIG = INPUT_DIR / "config.repl.all_mode3.json"
DB = INPUT_DIR / "scisci_process.duckdb"
SOURCE = INPUT_DIR / "population_with_names_economy_review.jsonl"
ROLLOUT = INPUT_DIR / "rollout-2026-11-04T19-58-37-01a1a824-5a66-7703-8730-fcb46438b6e5.jsonl"
OUTPUT = WORKDIR / "out/master.seed.jsonl"
MASTER = WORKDIR / "out/master.jsonl"
NAMES = WORKDIR / "out/distinct_names_in_draw_order.tsv"
SEED_REPORT = WORKDIR / "out/seed_report_template.md"
SEED_HANDOFF = WORKDIR / "out/seed_handoff.json"
OUTERDICT_MODEL_SOURCE = ROOT / "src/helpers/data_models/outerdict.py"
SOURCEKEY_MODEL_SOURCE = ROOT / "src/helpers/data_models/sourcekey.py"
DRAW_STEP_SOURCE = ROOT / "src/steps/step_05_sampling.py"
SEED_SOURCE = SCRIPT_DIR / "seed.py"
DUCKDB_SETTINGS = ("SET threads=1", "SET memory_limit='128MB'")
ERR_PILOT_ROWS = "Expected {expected} pilot rows, got {actual}"
ERR_DUPLICATE_PILOT_INDEX = "Duplicate pilot population index"
ERR_SAMPLE_SIZES = "Sample draw sizes do not match all-mode3 configuration"
ERR_DRAW_COUNT = "Draw count does not match all-mode3 configuration"
ERR_DUPLICATE_SOURCE_INDEX = "Duplicate population index in review source"
ERR_SOURCE_DRAW_COVERAGE = "All-mode3 draws do not cover each HCR source row exactly once"
ERR_REPLACEMENT_ORDER = "Report template requires replacement batches before the final batch"
ERR_ROLLOUT_HANDOFF = "Pinned Codex rollout link is unavailable for the seed handoff"
MSG_SEEDED = "draws={draws} namekeys={namekeys} excluded_draws={excluded}"
MSG_DRAW = "{draw}: {entry}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _describe_batches(sizes: list[int]) -> str:
    counts = Counter(sizes)
    return " and ".join(
        f"{count} {'batch' if count == 1 else 'batches'} of {size:,} rows"
        for size, count in counts.items()
    )


def main() -> None:
    sys.path.insert(0, str(ROOT))
    from src.helpers.config import PipelineConfig
    from src.helpers.data_models import FragmentType, InnerDict, NameKey, OuterDict
    from src.helpers.procedures import XlsxMatchProcedure
    from src.helpers.schema import (
        POPULATION_ECON_VIEW,
        POPULATION_TABLE,
        REGISTERED_RESOURCES_TABLE,
    )
    from src.helpers.vars import (
        DRAW_LABEL,
        HCR_CATEGORY_COL,
        HCR_FIRST_NAME_COL,
        HCR_LAST_NAME_COL,
        KTP_FILENAME_COL,
        KTP_FIRST_NAME_COL,
        KTP_FRAGMENT_COL,
        KTP_FRAGMENT_TYPE_COL,
        KTP_HCR_FILENAME_COL,
        KTP_HCR_ROW_NUMBER_COL,
        KTP_LAST_NAME_COL,
        KTP_POPULATION_INDEX_COL,
        NAME_EDGE_WHITESPACE_REGEX,
        PILOT_NAME_CATEGORY_TRIPLES,
    )
    from src.steps.step_05_sampling import _precompute_draw_batches

    config = PipelineConfig.from_json(CONFIG)
    con = duckdb.connect(str(DB), read_only=True)
    try:
        for statement in DUCKDB_SETTINGS:
            con.execute(statement)
        pool = np.array(
            [
                row[0]
                for row in con.execute(
                    f'SELECT "{KTP_POPULATION_INDEX_COL}" FROM {POPULATION_TABLE}'
                ).fetchall()
            ],
            dtype=np.int64,
        )

        values = ", ".join("(?, ?, ?, ?)" for _ in PILOT_NAME_CATEGORY_TRIPLES)
        pilot_params = [
            item
            for position, triple in enumerate(PILOT_NAME_CATEGORY_TRIPLES)
            for item in (position, *triple)
        ]
        pilot_rows = con.execute(
            f"""
            SELECT t.position, p."{KTP_POPULATION_INDEX_COL}"
            FROM (VALUES {values}) AS t(position, first_name, last_name, category)
            JOIN {POPULATION_TABLE} p
              ON p."{HCR_FIRST_NAME_COL}" = t.first_name
             AND p."{HCR_LAST_NAME_COL}" = t.last_name
             AND p."{HCR_CATEGORY_COL}" = t.category
            WHERE p."{KTP_HCR_FILENAME_COL}" = ?
            ORDER BY t.position
            """,
            [*pilot_params, config.pilot_xlsx_name],
        ).fetchall()
        if len(pilot_rows) != len(PILOT_NAME_CATEGORY_TRIPLES):
            raise ValueError(
                ERR_PILOT_ROWS.format(
                    expected=len(PILOT_NAME_CATEGORY_TRIPLES), actual=len(pilot_rows)
                )
            )
        pilot_indices = [int(index) for _, index in pilot_rows]
        if len(set(pilot_indices)) != len(pilot_indices):
            raise ValueError(ERR_DUPLICATE_PILOT_INDEX)

        specs = config.sample_draw_sizes
        if sum(spec.size for spec in specs) != config.total_draws - len(pilot_indices):
            raise ValueError(ERR_SAMPLE_SIZES)
        seen_nonreplacement = False
        for spec in specs:
            if not spec.replace:
                seen_nonreplacement = True
            elif seen_nonreplacement:
                raise ValueError(ERR_REPLACEMENT_ORDER)
        batches = _precompute_draw_batches(
            index_pool=pool,
            draw_specs=specs,
            rng=np.random.default_rng(config.sample_seed),
            seen_indices_initial=set(pilot_indices),
        )
        random_indices = [int(index) for batch in batches for index in batch]
        # Step 5 appends pilots to the samples table, but its ordered view puts them first.
        draws = [(f"pilot.{number}", index) for number, index in enumerate(pilot_indices, 1)] + [
            (str(number), index) for number, index in enumerate(random_indices, 1)
        ]
        if len(draws) != config.total_draws:
            raise ValueError(ERR_DRAW_COUNT)

        derived = {
            KTP_FILENAME_COL: f'p."{KTP_HCR_FILENAME_COL}"',
            KTP_FRAGMENT_COL: f'p."{KTP_HCR_ROW_NUMBER_COL}"',
            KTP_FRAGMENT_TYPE_COL: (
                f"COALESCE(rr.fragment_type, '{FragmentType.EXCEL_ROW.value}')"
            ),
            KTP_FIRST_NAME_COL: (
                f'regexp_replace(p."{KTP_FIRST_NAME_COL}", '
                f"'{NAME_EDGE_WHITESPACE_REGEX}', '', 'g')"
            ),
            KTP_LAST_NAME_COL: (
                f'regexp_replace(p."{KTP_LAST_NAME_COL}", '
                f"'{NAME_EDGE_WHITESPACE_REGEX}', '', 'g')"
            ),
        }
        projection_parts = []
        for column in REVIEW_SOURCE_COLUMNS[1:]:
            expression = derived.get(column, f'p."{column}"')
            projection_parts.append(f'{expression} AS "{column}"')
        projection = ", ".join(projection_parts)
        cursor = con.execute(
            f"""
            SELECT p."{KTP_POPULATION_INDEX_COL}", {projection}
            FROM {POPULATION_ECON_VIEW} p
            LEFT JOIN {REGISTERED_RESOURCES_TABLE} rr
              ON rr.resource_name = p."{KTP_HCR_FILENAME_COL}"
            """
        )
        rows_by_index: dict[int, tuple[object, ...]] = {}
        while batch := cursor.fetchmany(2048):
            for index, *source_values in batch:
                if index in rows_by_index:
                    raise ValueError(ERR_DUPLICATE_SOURCE_INDEX)
                rows_by_index[int(index)] = tuple(source_values)
    finally:
        con.close()

    if len(draws) != len(rows_by_index) or {index for _, index in draws} != rows_by_index.keys():
        raise ValueError(ERR_SOURCE_DRAW_COVERAGE)

    seen_namekeys: set[str] = set()
    ordered_names: list[tuple[str, str]] = []
    lines: list[str] = []
    source_lines: list[str] = []
    all_refs: Counter[tuple[str, str, str]] = Counter()
    pilot_refs: Counter[tuple[str, str, str]] = Counter()
    initial_refs: Counter[tuple[str, str, str]] = Counter()
    replacement_names: dict[tuple[str, str], list[str]] = {}
    pilot_count = len(pilot_indices)
    replacement_count = sum(spec.size for spec in specs if spec.replace)
    initial_count = pilot_count + replacement_count
    excluded = 0
    procedure = XlsxMatchProcedure()
    for position, (draw, index) in enumerate(draws):
        row = {
            DRAW_LABEL: draw,
            **dict(zip(REVIEW_SOURCE_COLUMNS[1:], rows_by_index[index], strict=True)),
        }
        source_lines.append(json.dumps(row, ensure_ascii=False) + "\n")
        ref = (
            str(row[KTP_FILENAME_COL]),
            str(row[KTP_FRAGMENT_TYPE_COL]),
            str(row[KTP_FRAGMENT_COL]),
        )
        all_refs[ref] += 1
        if position < pilot_count:
            pilot_refs[ref] += 1
        if position < initial_count:
            initial_refs[ref] += 1
        if pilot_count <= position < initial_count:
            name = (str(row[KTP_FIRST_NAME_COL]), str(row[KTP_LAST_NAME_COL]))
            replacement_names.setdefault(name, []).append(draw)
        filename = row[KTP_FILENAME_COL]
        row_number = row[KTP_FRAGMENT_COL]
        first = row[KTP_FIRST_NAME_COL]
        last = row[KTP_LAST_NAME_COL]
        if first is None or last is None or first == "" or last == "":
            # Step 6 excludes these names; retain an empty line at their draw position.
            excluded += 1
            excluded_key = json.dumps(
                {KTP_FIRST_NAME_COL: first, KTP_LAST_NAME_COL: last}, sort_keys=True
            )
            outer = OuterDict(data={excluded_key: []})
        else:
            namekey = NameKey(first_name=first, last_name=last)
            outer = OuterDict.from_name_keys([namekey])
            serialized_key = namekey.to_json_key()
            if serialized_key not in seen_namekeys:
                seen_namekeys.add(serialized_key)
                ordered_names.append((namekey.first_name, namekey.last_name))
                inner = InnerDict.from_mapping(
                    {
                        KTP_FILENAME_COL: filename,
                        KTP_FRAGMENT_COL: {
                            "type": FragmentType.EXCEL_ROW.value,
                            FragmentType.EXCEL_ROW.value: row_number,
                        },
                    },
                    procedure,
                )
                outer.add_inner(namekey, inner)
        lines.append(json.dumps(outer.to_serializable(), ensure_ascii=False) + "\n")

    SOURCE.write_text("".join(source_lines), encoding=TEXT_ENCODING)
    OUTPUT.write_text("".join(lines), encoding=TEXT_ENCODING)
    with NAMES.open("w", encoding=TEXT_ENCODING, newline="") as file:
        writer = csv.writer(file, delimiter="\t", lineterminator="\n")
        writer.writerow((NAME_FIRST_COL, NAME_LAST_COL))
        writer.writerows(ordered_names)

    def duplicate_count(refs: Counter[tuple[str, str, str]]) -> int:
        return sum(count - 1 for count in refs.values())

    repeated_names = sorted(
        ((name, labels) for name, labels in replacement_names.items() if len(labels) > 1),
        key=lambda item: int(item[1][0]),
    )
    name_repeats = ", ".join(
        MSG_NAME_REPEAT.format(
            name=ReportText.format(f"{first} {last}", ReportQualifier.IMPORTED),
            draws=ReportText.format(", ".join(labels), ReportQualifier.IMPORTED),
        )
        for (first, last), labels in repeated_names
    ) or ReportText.format(MSG_NO_NAME_REPEATS, ReportQualifier.COMPUTED)
    appendix_body = MSG_DEFINITIONS.format(
        outerdict_source=ReportText.format(
            report_path(OUTERDICT_MODEL_SOURCE),
            ReportQualifier.IMPORTED,
        ),
        sourcekey_source=ReportText.format(
            report_path(SOURCEKEY_MODEL_SOURCE),
            ReportQualifier.IMPORTED,
        ),
        draw_source=ReportText.format(report_path(DRAW_STEP_SOURCE), ReportQualifier.IMPORTED),
        seed_source=ReportText.format(
            report_path(SEED_SOURCE),
            ReportQualifier.IMPORTED,
        ),
        config_source=ReportText.format(
            report_path(CONFIG),
            ReportQualifier.IMPORTED,
        ),
        sourcekey_example=ReportText.format(
            "2024_HCR.xlsx#excel_row:1890", ReportQualifier.IMPORTED
        ),
        pilot_example=ReportText.format("pilot.1", ReportQualifier.IMPORTED),
        config_sha256=ReportText.format(_sha256(CONFIG), ReportQualifier.COMPUTED),
        pilot_draws=ReportText.format(pilot_count, ReportQualifier.COMPUTED),
        pilot_source=ReportText.format(config.pilot_xlsx_name, ReportQualifier.IMPORTED),
        sample_seed=ReportText.format(config.sample_seed, ReportQualifier.IMPORTED),
        replacement_batches=ReportText.format(
            _describe_batches([spec.size for spec in specs if spec.replace]),
            ReportQualifier.COMPUTED,
        ),
        nonreplacement_batches=ReportText.format(
            _describe_batches([spec.size for spec in specs if not spec.replace]),
            ReportQualifier.COMPUTED,
        ),
    )
    appendix_body += " " + MSG_DRAW_OBSERVATION.format(
        total_draws=ReportText.format(len(draws), ReportQualifier.COMPUTED),
        duplicate_rows=ReportText.format(duplicate_count(all_refs), ReportQualifier.COMPUTED),
        initial_draws=ReportText.format(initial_count, ReportQualifier.COMPUTED),
        initial_duplicate_rows=ReportText.format(
            duplicate_count(initial_refs), ReportQualifier.COMPUTED
        ),
        replacement_duplicate_rows=ReportText.format(
            duplicate_count(initial_refs) - duplicate_count(pilot_refs),
            ReportQualifier.COMPUTED,
        ),
        replacement_draws=ReportText.format(replacement_count, ReportQualifier.COMPUTED),
        name_repeats=name_repeats,
    )
    seed_report = MSG_APPENDIX_HEADER + "\n\n" + ReportText.attest(ASSIGNEE, appendix_body) + "\n"
    SEED_REPORT.write_text(seed_report, encoding=TEXT_ENCODING)
    if not ROLLOUT.is_file():
        raise ValueError(ERR_ROLLOUT_HANDOFF)
    SeedHandoff(
        version=1,
        assignee=ASSIGNEE,
        total_draws=len(draws),
        pilot_draws=pilot_count,
        source_file=str(SOURCE.relative_to(WORKDIR)),
        source_sha256=_sha256(SOURCE),
        seed_mask_file=str(OUTPUT.relative_to(WORKDIR)),
        seed_mask_sha256=_sha256(OUTPUT),
        names_file=str(NAMES.relative_to(WORKDIR)),
        names_sha256=_sha256(NAMES),
        rollout_file=str(ROLLOUT.relative_to(WORKDIR)),
        master_file=str(MASTER.relative_to(WORKDIR)),
        report_template_file=str(SEED_REPORT.relative_to(WORKDIR)),
        report_template_sha256=_sha256(SEED_REPORT),
    ).dump(SEED_HANDOFF)
    print(MSG_SEEDED.format(draws=len(draws), namekeys=len(seen_namekeys), excluded=excluded))
    for ordinal, line in enumerate(lines[:2], start=1):
        print(MSG_DRAW.format(draw=draws[ordinal - 1][0], entry=line.rstrip()))


if __name__ == "__main__":
    main()
