"""Export distinct complete HCR-derived name pairs in first-draw order.

Allowed dependencies: stdlib and the local shared module only.
"""

import csv
import json
from pathlib import Path

from shared import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL, TEXT_ENCODING

SCRIPT_DIR = Path(__file__).resolve().parent
WORKDIR = SCRIPT_DIR.parent
SEED = WORKDIR / "out/master.seed.jsonl"
OUTPUT = WORKDIR / "out/distinct_names_in_draw_order.tsv"
EXPECTED_NAME_PAIRS = 18_468
ERR_SEED_LINE = "Seed line {line} does not contain exactly one NameKey"
ERR_NAME_PAIRS = "Expected {expected} distinct complete name pairs, got {actual}"
MSG_EXPORTED = "Exported {count} distinct complete name pairs to {path}"


def main() -> None:
    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[str, str]] = []
    with SEED.open(encoding=TEXT_ENCODING) as source:
        for line_number, line in enumerate(source, start=1):
            entry = json.loads(line)
            if len(entry) != 1:
                raise ValueError(ERR_SEED_LINE.format(line=line_number))
            key = json.loads(next(iter(entry)))
            pair = (key[KTP_FIRST_NAME_COL], key[KTP_LAST_NAME_COL])
            if not all(pair) or pair in seen:
                continue
            seen.add(pair)
            ordered.append(pair)
    if len(ordered) != EXPECTED_NAME_PAIRS:
        raise ValueError(
            ERR_NAME_PAIRS.format(expected=EXPECTED_NAME_PAIRS, actual=len(ordered))
        )

    with OUTPUT.open("w", encoding=TEXT_ENCODING, newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(("first_name", "last_name"))
        writer.writerows(ordered)
    print(MSG_EXPORTED.format(count=len(ordered), path=OUTPUT))


if __name__ == "__main__":
    main()
