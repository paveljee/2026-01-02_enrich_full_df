# Requires a more recent GNU make on macOS

.PHONY: \
	manifest \
	validate \
	test \
	test-manifest \
	test-validate

SHELL := /usr/bin/env
.SHELLFLAGS := bash -c
.ONESHELL:

PYTHON ?= pixi run --frozen -e detour-ai-augment python
PYTHON_STDIN := $(PYTHON) -c \
    'import sys; exec(compile(sys.stdin.read(), sys.argv[1], "exec"))'

TASK := src/TASK.md
MANIFEST := manifest.json
AGENTS := build/AGENTS.md
SPEC := build/SPEC.ipynb
VERBOSE ?= 0

manifest:
	@$(PYTHON_STDIN) "Makefile:$@" <<'PY'
	$(MANIFEST_PY)
	PY

validate:
	@$(PYTHON_STDIN) "Makefile:$@" <<'PY'
	$(VALIDATE_PY)
	PY

test: \
	test-manifest \
	test-validate

test-manifest:
	@set -euo pipefail
	tmp=$$(mktemp -d)
	trap 'rm -rf "$$tmp"' EXIT
	module="$$tmp/module.py"
	test_module="$$tmp/test_module.py"
	cat >"$$module" <<'PY'
	$(MANIFEST_PY)
	PY
	cat >"$$test_module" <<'PY'
	$(TEST_MANIFEST_PY)
	PY
	MANIFEST_MODULE="$$module" \
	$(PYTHON) -m pytest \
	    -vv \
	    -srA \
	    "$$test_module"

test-validate:
	@set -euo pipefail
	tmp=$$(mktemp -d)
	trap 'rm -rf "$$tmp"' EXIT
	module="$$tmp/module.py"
	test_module="$$tmp/test_module.py"
	cat >"$$module" <<'PY'
	$(VALIDATE_PY)
	PY
	cat >"$$test_module" <<'PY'
	$(TEST_VALIDATE_PY)
	PY
	VALIDATE_MODULE="$$module" \
	$(PYTHON) -m pytest \
	    -vv \
	    -srA \
	    "$$test_module"

define MANIFEST_PY
import hashlib
import json
from pathlib import Path

task_path = Path("$(TASK)")
manifest_path = Path("$(MANIFEST)")

raw = task_path.read_bytes()
text = raw.decode("utf-8")
lines = text.splitlines(keepends=True)

manifest = {
    "source": {
        "path": str(task_path),
        "sha256": hashlib.sha256(raw).hexdigest(),
    },
    "lines": [
        {
            "line": number,
            "sha256": hashlib.sha256(line.encode("utf-8")).hexdigest(),
            "build": None,
        }
        for number, line in enumerate(lines, start=1)
    ],
}

with manifest_path.open("x", encoding="utf-8") as f:
    f.write(json.dumps(manifest, indent=2) + "\n")
endef

define VALIDATE_PY
import hashlib
import json
import os
import time
import traceback
from collections import defaultdict
from pathlib import Path


task_path = Path("$(TASK)")
manifest_path = Path("$(MANIFEST)")
agents_path = Path("$(AGENTS)")
spec_path = Path("$(SPEC)")

raw = task_path.read_bytes()
task_text = raw.decode("utf-8")
task_lines = task_text.splitlines(keepends=True)

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

assert (
    manifest["source"]["path"] == str(task_path)
), (
    "source path mismatch: "
    f"expected {str(task_path)!r}, "
    f"got {manifest['source']['path']!r}"
)

expected_source_sha256 = hashlib.sha256(raw).hexdigest()
assert (
    manifest["source"]["sha256"] == expected_source_sha256
), (
    "source sha256 mismatch: "
    f"expected {expected_source_sha256!r}, "
    f"got {manifest['source']['sha256']!r}"
)

entries = manifest["lines"]

assert (
    len(entries) == len(task_lines)
), (
    "line count mismatch: "
    f"manifest has {len(entries)} entries, "
    f"TASK has {len(task_lines)} lines"
)

assert (
    [entry["line"] for entry in entries]
    == list(range(1, len(task_lines) + 1))
), (
    "line numbers must be consecutive and start at 1"
)

for entry, source_line in zip(entries, task_lines, strict=True):
    expected_line_sha256 = hashlib.sha256(
        source_line.encode("utf-8")
    ).hexdigest()

    assert (
        entry["sha256"] == expected_line_sha256
    ), (
        f"line {entry['line']} sha256 mismatch: "
        f"expected {expected_line_sha256!r}, "
        f"got {entry['sha256']!r}"
    )

    assert (
        entry["build"] is not None
    ), (
        f"line {entry['line']} has no build mapping"
    )

    assert (
        entry["build"]["type"] in {"text", "ipynb"}
    ), (
        f"line {entry['line']} has invalid build type: "
        f"{entry['build']['type']!r}"
    )

agents_lines = agents_path.read_text(
    encoding="utf-8"
).splitlines(keepends=True)

text_entries = [
    entry for entry in entries
    if entry["build"]["type"] == "text"
]

text_entries_by_destination = sorted(
    text_entries,
    key=lambda entry: entry["build"]["line"],
)

assert (
    [
        entry["build"]["line"]
        for entry in text_entries_by_destination
    ]
    == list(range(1, len(agents_lines) + 1))
), (
    "text destination lines must be consecutive and start at 1"
)

assert (
    [
        entry["line"]
        for entry in text_entries_by_destination
    ]
    == sorted(
        entry["line"]
        for entry in text_entries_by_destination
    )
), (
    "text source lines must preserve source order"
)

for entry in text_entries:
    destination_line = entry["build"]["line"]

    assert (
        destination_line >= 1
    ), (
        f"text destination line must be >= 1: "
        f"got {destination_line}"
    )

    assert (
        destination_line <= len(agents_lines)
    ), (
        f"text destination line {destination_line} "
        f"is outside AGENTS.md with "
        f"{len(agents_lines)} lines"
    )

    assert (
        agents_lines[destination_line - 1]
        == task_lines[entry["line"] - 1]
    ), (
        f"text content mismatch for source line "
        f"{entry['line']} at destination line "
        f"{destination_line}"
    )

nb = json.loads(spec_path.read_text(encoding="utf-8"))

assert (
    nb["nbformat"] == 4
), (
    f"nbformat must be 4, got {nb['nbformat']!r}"
)

cells = nb["cells"]


def cell_source(cell):
    source = cell["source"]

    if isinstance(source, list):
        return "".join(source)

    assert (
        isinstance(source, str)
    ), (
        "cell source must be a string or list of strings, "
        f"got {type(source).__name__}"
    )

    return source


ipynb_entries = [
    entry for entry in entries
    if entry["build"]["type"] == "ipynb"
]

by_cell = defaultdict(list)

for entry in ipynb_entries:
    cell = entry["build"]["cell"]

    assert (
        isinstance(cell, int)
    ), (
        f"cell index for source line {entry['line']} "
        f"must be an integer, got {cell!r}"
    )

    assert (
        0 <= cell < len(cells)
    ), (
        f"cell index {cell} for source line "
        f"{entry['line']} is outside notebook "
        f"with {len(cells)} cells"
    )

    by_cell[cell].append(entry)

markdown_cells = {
    index
    for index, cell in enumerate(cells)
    if cell["cell_type"] == "markdown"
}

assert (
    set(by_cell) == markdown_cells
), (
    "markdown cell mapping mismatch: "
    f"manifest maps {sorted(by_cell)}, "
    f"notebook has {sorted(markdown_cells)}"
)

assert (
    all(
        cell["cell_type"] in {"markdown", "code"}
        for cell in cells
    )
), (
    "cell type must be either 'markdown' or 'code'"
)

assert (
    cells
), (
    "notebook must contain at least one cell"
)

assert (
    cells[0]["cell_type"] == "markdown"
), (
    "first notebook cell must be markdown, "
    f"got {cells[0]['cell_type']!r}"
)

previous_source_number = 0

for cell_index in sorted(by_cell):
    cell_entries = by_cell[cell_index]
    cell = cells[cell_index]

    assert (
        cell["cell_type"] == "markdown"
    ), (
        f"mapped cell {cell_index} must be markdown, "
        f"got {cell['cell_type']!r}"
    )

    source_numbers = sorted(
        entry["line"] for entry in cell_entries
    )

    assert (
        source_numbers
        == list(
            range(
                source_numbers[0],
                source_numbers[-1] + 1,
            )
        )
    ), (
        f"markdown cell {cell_index} source lines "
        f"must be contiguous, got {source_numbers}"
    )

    assert (
        source_numbers[0] > previous_source_number
    ), (
        "markdown source blocks must preserve source order: "
        f"cell {cell_index} starts at line "
        f"{source_numbers[0]} after "
        f"{previous_source_number}"
    )

    previous_source_number = source_numbers[-1]

    expected = "".join(
        task_lines[number - 1]
        for number in source_numbers
    )

    assert (
        cell_source(cell) == expected
    ), (
        f"markdown content mismatch in cell {cell_index} "
        f"for task lines {source_numbers}"
    )

    next_markdown = min(
        (
            index
            for index in markdown_cells
            if index > cell_index
        ),
        default=len(cells),
    )

    evidence_cells = cells[
        cell_index + 1:next_markdown
    ]

    assert (
        evidence_cells
    ), (
        f"markdown cell {cell_index} must be followed "
        "by at least one evidence cell"
    )

    for evidence_cell in evidence_cells:
        assert (
            evidence_cell["cell_type"] == "code"
        ), (
            f"evidence after markdown cell {cell_index} "
            f"must be a code cell, got "
            f"{evidence_cell['cell_type']!r}"
        )

        assert (
            cell_source(evidence_cell).strip()
        ), (
            f"evidence after markdown cell {cell_index} "
            "must contain non-empty source"
        )

        assert (
            evidence_cell["metadata"].get("task_lines")
            == source_numbers
        ), (
            f"evidence task_lines mismatch after "
            f"markdown cell {cell_index}: "
            f"expected {source_numbers}, got "
            f"{evidence_cell['metadata'].get('task_lines')!r}"
        )

reconstructed = [""] * len(task_lines)

for entry in text_entries:
    reconstructed[entry["line"] - 1] = agents_lines[
        entry["build"]["line"] - 1
    ]

for cell_index, cell_entries in by_cell.items():
    source_numbers = sorted(
        entry["line"] for entry in cell_entries
    )

    cell_lines = cell_source(
        cells[cell_index]
    ).splitlines(keepends=True)

    assert (
        len(cell_lines) == len(source_numbers)
    ), (
        f"markdown cell {cell_index} line count mismatch: "
        f"cell has {len(cell_lines)} lines, "
        f"manifest maps {len(source_numbers)}"
    )

    for number, line in zip(
        source_numbers,
        cell_lines,
        strict=True,
    ):
        reconstructed[number - 1] = line

reconstructed_text = "".join(reconstructed)

assert (
    reconstructed_text == task_text
), (
    "reconstructed task text does not match source task text"
)

reconstructed_sha256 = hashlib.sha256(
    reconstructed_text.encode("utf-8")
).hexdigest()

assert (
    reconstructed_sha256
    == manifest["source"]["sha256"]
), (
    "reconstructed sha256 mismatch: "
    f"expected {manifest['source']['sha256']!r}, "
    f"got {reconstructed_sha256!r}"
)

evidence_cells = [
    (index, cell)
    for index, cell in enumerate(cells)
    if cell["cell_type"] == "code"
]

for _cell_index, evidence_cell in evidence_cells:
    metadata = evidence_cell["metadata"]

    assert (
        metadata.get("evidence_id")
    ), (
        "evidence cell is missing evidence_id"
    )

    assert (
        metadata.get("summary")
    ), (
        "evidence cell is missing summary"
    )

    assert (
        metadata.get("task_lines")
    ), (
        "evidence cell is missing task_lines"
    )

print(
    "ROUTING  PASS  "
    f"{len(task_lines)}/{len(task_lines)} lines, "
    f"sha256={manifest['source']['sha256'][:12]}…"
)

print(
    "NOTEBOOK PASS  "
    f"{len(markdown_cells)} human cells, "
    f"{len(evidence_cells)} evidence cells"
)

print()

task_root = task_path.resolve().parent.parent
repository_root = task_root.parents[1]

namespace = {
    "__name__": "__executable_spec__",
    "REPOSITORY_ROOT": repository_root,
    "TASK_ROOT": task_root,
}

execution_passes = []
execution_failures = []

block_results = defaultdict(
    lambda: {
        "passed": 0,
        "failed": 0,
    }
)

verbose = (
    str("$(VERBOSE)").lower()
    not in {"", "0", "false", "no"}
)

previous_cwd = Path.cwd()

try:
    os.chdir(repository_root)

    for cell_index, cell in evidence_cells:
        metadata = cell["metadata"]
        evidence_id = metadata["evidence_id"]
        summary = metadata["summary"]
        task_lines_for_cell = metadata["task_lines"]

        block = (
            task_lines_for_cell[0],
            task_lines_for_cell[-1],
        )

        started = time.monotonic()

        try:
            code = compile(
                cell_source(cell),
                f"{spec_path}#cell-{cell_index}",
                "exec",
            )

            exec(code, namespace)

            execution_passes.append(cell_index)
            block_results[block]["passed"] += 1

            elapsed = time.monotonic() - started

            print(
                f"{evidence_id:<8} PASS  "
                f"{elapsed:6.2f}s  "
                f"{summary}"
            )

        except Exception as exc:
            block_results[block]["failed"] += 1

            elapsed = time.monotonic() - started

            reason = (
                str(exc).strip()
                or type(exc).__name__
            )

            reason_lines = reason.splitlines()
            concise_lines = reason_lines[:12]

            if len(reason_lines) > len(concise_lines):
                concise_lines.append(
                    f"… "
                    f"{len(reason_lines) - len(concise_lines)} "
                    "more lines"
                )

            print(
                f"{evidence_id:<8} FAIL  "
                f"{elapsed:6.2f}s  "
                f"{summary}"
            )

            for reason_line in concise_lines:
                print(
                    f"{'':8}       "
                    f"{reason_line}"
                )

            execution_failures.append(
                (
                    evidence_id,
                    summary,
                    traceback.format_exc(),
                )
            )

finally:
    os.chdir(previous_cwd)

print("\nBLOCK SUMMARY")

for (
    first_line,
    last_line,
), results in block_results.items():
    line_range = (
        str(first_line)
        if first_line == last_line
        else f"{first_line}-{last_line}"
    )

    print(
        f"TASK {line_range:<7} "
        f"{results['passed']} passed, "
        f"{results['failed']} failed"
    )

print(
    "\nTOTAL    "
    f"{len(execution_passes)} passed, "
    f"{len(execution_failures)} failed"
)

if execution_failures:
    if verbose:
        print("\nFULL TRACEBACKS")

        for (
            evidence_id,
            summary,
            failure,
        ) in execution_failures:
            print(
                f"\n{evidence_id} "
                f"{summary}\n"
                f"{failure}"
            )

    raise SystemExit(1)
endef

define TEST_MANIFEST_PY
import hashlib
import json
import os
import runpy
from pathlib import Path

import pytest


MANIFEST_MODULE = os.environ["MANIFEST_MODULE"]


def run_manifest(tmp_path, raw=b"first\nsecond\n"):
    task_path = tmp_path / "src" / "TASK.md"
    task_path.parent.mkdir(parents=True)
    task_path.write_bytes(raw)

    previous_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        runpy.run_path(MANIFEST_MODULE)
    finally:
        os.chdir(previous_cwd)

    return task_path, tmp_path / "manifest.json"


def read_manifest(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_source_and_lines(tmp_path):
    raw = b"first\nsecond\n"

    task_path, manifest_path = run_manifest(
        tmp_path,
        raw,
    )

    manifest = read_manifest(manifest_path)

    assert manifest["source"] == {
        "path": "src/TASK.md",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }

    assert manifest["lines"] == [
        {
            "line": 1,
            "sha256": hashlib.sha256(
                b"first\n"
            ).hexdigest(),
            "build": None,
        },
        {
            "line": 2,
            "sha256": hashlib.sha256(
                b"second\n"
            ).hexdigest(),
            "build": None,
        },
    ]


@pytest.mark.parametrize(
    ("raw", "expected_lines"),
    [
        (
            b"",
            [],
        ),
        (
            b"one",
            [b"one"],
        ),
        (
            b"one\n",
            [b"one\n"],
        ),
        (
            b"one\r\ntwo",
            [
                b"one\r\n",
                b"two",
            ],
        ),
        (
            "café\n猫\n".encode("utf-8"),
            [
                "café\n".encode("utf-8"),
                "猫\n".encode("utf-8"),
            ],
        ),
    ],
)
def test_manifest_preserves_line_bytes(
    tmp_path,
    raw,
    expected_lines,
):
    _, manifest_path = run_manifest(
        tmp_path,
        raw,
    )

    manifest = read_manifest(manifest_path)

    assert len(manifest["lines"]) == len(
        expected_lines
    )

    for number, (entry, line) in enumerate(
        zip(
            manifest["lines"],
            expected_lines,
            strict=True,
        ),
        start=1,
    ):
        assert entry == {
            "line": number,
            "sha256": hashlib.sha256(
                line
            ).hexdigest(),
            "build": None,
        }


def test_manifest_refuses_overwrite_and_preserves_existing_file(
    tmp_path,
):
    task_path = tmp_path / "src" / "TASK.md"
    task_path.parent.mkdir(parents=True)
    task_path.write_text(
        "hello\n",
        encoding="utf-8",
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        "do not replace me\n",
        encoding="utf-8",
    )

    previous_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)

        with pytest.raises(FileExistsError):
            runpy.run_path(MANIFEST_MODULE)
    finally:
        os.chdir(previous_cwd)

    assert manifest_path.read_text(
        encoding="utf-8"
    ) == "do not replace me\n"


def test_manifest_rejects_invalid_utf8_without_creating_manifest(
    tmp_path,
):
    task_path = tmp_path / "src" / "TASK.md"
    task_path.parent.mkdir(parents=True)
    task_path.write_bytes(b"\xff")

    previous_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)

        with pytest.raises(UnicodeDecodeError):
            runpy.run_path(MANIFEST_MODULE)
    finally:
        os.chdir(previous_cwd)

    assert not (
        tmp_path / "manifest.json"
    ).exists()


def test_manifest_requires_task_file(tmp_path):
    (tmp_path / "src").mkdir()

    previous_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)

        with pytest.raises(FileNotFoundError):
            runpy.run_path(MANIFEST_MODULE)
    finally:
        os.chdir(previous_cwd)

    assert not (
        tmp_path / "manifest.json"
    ).exists()


def test_manifest_json_ends_with_single_newline(
    tmp_path,
):
    _, manifest_path = run_manifest(tmp_path)

    raw = manifest_path.read_bytes()

    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
endef

define TEST_VALIDATE_PY
import hashlib
import json
import os
import runpy
from pathlib import Path

import pytest


VALIDATE_MODULE = os.environ["VALIDATE_MODULE"]


def line_entry(number, line, build):
    return {
        "line": number,
        "sha256": hashlib.sha256(
            line.encode("utf-8")
        ).hexdigest(),
        "build": build,
    }


def markdown(source):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source,
    }


def evidence(
    task_lines,
    source="assert True\n",
    evidence_id="E1",
    summary="evidence",
):
    return {
        "cell_type": "code",
        "execution_count": None,
        "outputs": [],
        "metadata": {
            "evidence_id": evidence_id,
            "summary": summary,
            "task_lines": task_lines,
        },
        "source": source,
    }


def make_case(tmp_path):
    work = (
        tmp_path
        / "repo"
        / "tasks"
        / "case"
    )
    work.mkdir(parents=True)

    task_lines = [
        "agent line\n",
        "notebook line\n",
    ]

    raw = "".join(
        task_lines
    ).encode("utf-8")

    return {
        "repo": tmp_path / "repo",
        "work": work,
        "task_raw": raw,
        "agents_text": task_lines[0],
        "manifest": {
            "source": {
                "path": "src/TASK.md",
                "sha256": hashlib.sha256(
                    raw
                ).hexdigest(),
            },
            "lines": [
                line_entry(
                    1,
                    task_lines[0],
                    {
                        "type": "text",
                        "line": 1,
                    },
                ),
                line_entry(
                    2,
                    task_lines[1],
                    {
                        "type": "ipynb",
                        "cell": 0,
                    },
                ),
            ],
        },
        "notebook": {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                markdown(task_lines[1]),
                evidence(
                    [2],
                    summary="base evidence",
                ),
            ],
        },
    }


def write_case(case):
    work = case["work"]

    task_path = (
        work
        / "src"
        / "TASK.md"
    )
    task_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    task_path.write_bytes(
        case["task_raw"]
    )

    manifest_path = (
        work
        / "manifest.json"
    )
    manifest_path.write_text(
        json.dumps(
            case["manifest"],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    build_path = work / "build"
    build_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        build_path
        / "AGENTS.md"
    ).write_text(
        case["agents_text"],
        encoding="utf-8",
    )

    (
        build_path
        / "SPEC.ipynb"
    ).write_text(
        json.dumps(
            case["notebook"],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run_validate(case):
    write_case(case)

    previous_cwd = Path.cwd()

    try:
        os.chdir(case["work"])

        result = runpy.run_path(
            VALIDATE_MODULE
        )

        assert Path.cwd() == case["work"]

        return result
    finally:
        os.chdir(previous_cwd)


def assert_validation_error(case, match=None):
    with pytest.raises(
        AssertionError,
        match=match,
    ):
        run_validate(case)


def set_case(
    case,
    task_lines,
    builds,
    agents_text,
    cells,
):
    raw = "".join(
        task_lines
    ).encode("utf-8")

    case["task_raw"] = raw
    case["agents_text"] = agents_text

    case["manifest"] = {
        "source": {
            "path": "src/TASK.md",
            "sha256": hashlib.sha256(
                raw
            ).hexdigest(),
        },
        "lines": [
            line_entry(
                number,
                line,
                build,
            )
            for number, (line, build)
            in enumerate(
                zip(
                    task_lines,
                    builds,
                    strict=True,
                ),
                start=1,
            )
        ],
    }

    case["notebook"] = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": cells,
    }


def test_validate_accepts_minimal_valid_case(
    tmp_path,
    capsys,
):
    case = make_case(tmp_path)

    run_validate(case)

    out = capsys.readouterr().out

    assert (
        "ROUTING  PASS  "
        "2/2 lines"
        in out
    )

    assert (
        "NOTEBOOK PASS  "
        "1 human cells, "
        "1 evidence cells"
        in out
    )

    assert (
        "TOTAL    "
        "1 passed, "
        "0 failed"
        in out
    )


def test_validate_accepts_list_form_cell_sources(
    tmp_path,
):
    case = make_case(tmp_path)

    case["notebook"]["cells"][0]["source"] = [
        "notebook ",
        "line\n",
    ]

    case["notebook"]["cells"][1]["source"] = [
        "assert ",
        "True\n",
    ]

    run_validate(case)


def test_validate_rejects_wrong_source_path(
    tmp_path,
):
    case = make_case(tmp_path)

    case["manifest"]["source"]["path"] = (
        "wrong/TASK.md"
    )

    assert_validation_error(
        case,
        "source path",
    )


def test_validate_rejects_wrong_source_hash(
    tmp_path,
):
    case = make_case(tmp_path)

    case["manifest"]["source"]["sha256"] = (
        "0" * 64
    )

    assert_validation_error(
        case,
        "sha256",
    )


def test_validate_rejects_missing_manifest_line(
    tmp_path,
):
    case = make_case(tmp_path)

    case["manifest"]["lines"].pop()

    assert_validation_error(
        case,
        "line",
    )


def test_validate_rejects_wrong_line_number(
    tmp_path,
):
    case = make_case(tmp_path)

    case["manifest"]["lines"][1]["line"] = 99

    assert_validation_error(
        case,
        "line",
    )


def test_validate_rejects_wrong_line_hash(
    tmp_path,
):
    case = make_case(tmp_path)

    case["manifest"]["lines"][0]["sha256"] = (
        "0" * 64
    )

    assert_validation_error(
        case,
        "sha256",
    )


@pytest.mark.parametrize(
    "build",
    [
        None,
        {
            "type": "other",
        },
    ],
)
def test_validate_rejects_missing_or_unknown_build(
    tmp_path,
    build,
):
    case = make_case(tmp_path)

    case["manifest"]["lines"][0][
        "build"
    ] = build

    assert_validation_error(
        case,
        "build",
    )


def test_validate_rejects_text_destination_gap(
    tmp_path,
):
    case = make_case(tmp_path)

    case["manifest"]["lines"][0][
        "build"
    ]["line"] = 2

    assert_validation_error(
        case,
        "text",
    )


def test_validate_rejects_text_content_mismatch(
    tmp_path,
):
    case = make_case(tmp_path)

    case["agents_text"] = "different\n"

    assert_validation_error(
        case,
        "text",
    )


def test_validate_rejects_reordered_text_source_lines(
    tmp_path,
):
    case = make_case(tmp_path)

    task_lines = [
        "first\n",
        "second\n",
        "markdown\n",
    ]

    builds = [
        {
            "type": "text",
            "line": 2,
        },
        {
            "type": "text",
            "line": 1,
        },
        {
            "type": "ipynb",
            "cell": 0,
        },
    ]

    cells = [
        markdown(task_lines[2]),
        evidence([3]),
    ]

    set_case(
        case,
        task_lines,
        builds,
        task_lines[1] + task_lines[0],
        cells,
    )

    assert_validation_error(
        case,
        "order",
    )


def test_validate_rejects_wrong_notebook_format(
    tmp_path,
):
    case = make_case(tmp_path)

    case["notebook"]["nbformat"] = 3

    assert_validation_error(
        case,
        "nbformat",
    )


def test_validate_rejects_ipynb_cell_out_of_range(
    tmp_path,
):
    case = make_case(tmp_path)

    case["manifest"]["lines"][1][
        "build"
    ]["cell"] = 99

    assert_validation_error(
        case,
        "cell",
    )


def test_validate_rejects_unmapped_markdown_cell(
    tmp_path,
):
    case = make_case(tmp_path)

    case["notebook"]["cells"].extend(
        [
            markdown("extra\n"),
            evidence(
                [2],
                evidence_id="E2",
            ),
        ]
    )

    assert_validation_error(
        case,
        "markdown",
    )


def test_validate_rejects_non_markdown_or_code_cells(
    tmp_path,
):
    case = make_case(tmp_path)

    case["notebook"]["cells"][1][
        "cell_type"
    ] = "raw"

    assert_validation_error(
        case,
        "cell",
    )


def test_validate_requires_first_cell_to_be_markdown(
    tmp_path,
):
    case = make_case(tmp_path)

    task_lines = [
        "markdown\n",
    ]

    builds = [
        {
            "type": "ipynb",
            "cell": 1,
        },
    ]

    cells = [
        evidence([1]),
        markdown(task_lines[0]),
        evidence(
            [1],
            evidence_id="E2",
        ),
    ]

    set_case(
        case,
        task_lines,
        builds,
        "",
        cells,
    )

    assert_validation_error(
        case,
        "first",
    )


def test_validate_rejects_noncontiguous_source_lines_in_markdown(
    tmp_path,
):
    case = make_case(tmp_path)

    task_lines = [
        "one\n",
        "agent\n",
        "three\n",
    ]

    builds = [
        {
            "type": "ipynb",
            "cell": 0,
        },
        {
            "type": "text",
            "line": 1,
        },
        {
            "type": "ipynb",
            "cell": 0,
        },
    ]

    cells = [
        markdown(
            task_lines[0]
            + task_lines[2]
        ),
        evidence(
            [1, 3]
        ),
    ]

    set_case(
        case,
        task_lines,
        builds,
        task_lines[1],
        cells,
    )

    assert_validation_error(
        case,
        "contiguous",
    )


def test_validate_rejects_markdown_blocks_out_of_source_order(
    tmp_path,
):
    case = make_case(tmp_path)

    task_lines = [
        "one\n",
        "two\n",
    ]

    builds = [
        {
            "type": "ipynb",
            "cell": 2,
        },
        {
            "type": "ipynb",
            "cell": 0,
        },
    ]

    cells = [
        markdown(task_lines[1]),
        evidence(
            [2],
            evidence_id="E2",
        ),
        markdown(task_lines[0]),
        evidence(
            [1],
            evidence_id="E1",
        ),
    ]

    set_case(
        case,
        task_lines,
        builds,
        "",
        cells,
    )

    assert_validation_error(
        case,
        "order",
    )


def test_validate_rejects_markdown_content_mismatch(
    tmp_path,
):
    case = make_case(tmp_path)

    case["notebook"]["cells"][0][
        "source"
    ] = "changed\n"

    assert_validation_error(
        case,
        "markdown",
    )


def test_validate_requires_evidence_after_each_markdown(
    tmp_path,
):
    case = make_case(tmp_path)

    case["notebook"]["cells"] = (
        case["notebook"]["cells"][:1]
    )

    assert_validation_error(
        case,
        "evidence",
    )


def test_validate_rejects_empty_evidence_source(
    tmp_path,
):
    case = make_case(tmp_path)

    case["notebook"]["cells"][1][
        "source"
    ] = " \n"

    assert_validation_error(
        case,
        "evidence",
    )


def test_validate_rejects_evidence_task_line_mismatch(
    tmp_path,
):
    case = make_case(tmp_path)

    case["notebook"]["cells"][1][
        "metadata"
    ]["task_lines"] = [1]

    assert_validation_error(
        case,
        "task_lines",
    )


@pytest.mark.parametrize(
    "field",
    [
        "evidence_id",
        "summary",
    ],
)
def test_validate_requires_evidence_metadata(
    tmp_path,
    field,
):
    case = make_case(tmp_path)

    del case["notebook"]["cells"][1][
        "metadata"
    ][field]

    assert_validation_error(
        case,
        field,
    )


def test_validate_executes_evidence_from_repository_root_with_expected_globals(
    tmp_path,
):
    case = make_case(tmp_path)

    case["notebook"]["cells"][1][
        "source"
    ] = """
from pathlib import Path

assert Path.cwd() == REPOSITORY_ROOT
assert TASK_ROOT == REPOSITORY_ROOT / "tasks" / "case"

(REPOSITORY_ROOT / "evidence.marker").write_text(
    "ok"
)
"""

    run_validate(case)

    assert (
        case["repo"]
        / "evidence.marker"
    ).read_text() == "ok"


def test_validate_evidence_cells_share_namespace(
    tmp_path,
):
    case = make_case(tmp_path)

    case["notebook"]["cells"] = [
        markdown(
            "notebook line\n"
        ),
        evidence(
            [2],
            "shared_value = 41\n",
            evidence_id="E1",
        ),
        evidence(
            [2],
            (
                "assert "
                "shared_value + 1 == 42\n"
            ),
            evidence_id="E2",
        ),
    ]

    run_validate(case)


def test_validate_reports_evidence_failure_and_exits_nonzero(
    tmp_path,
    capsys,
):
    case = make_case(tmp_path)

    case["notebook"]["cells"][1][
        "source"
    ] = (
        'raise RuntimeError("boom")\n'
    )

    with pytest.raises(
        SystemExit
    ) as exc_info:
        run_validate(case)

    assert exc_info.value.code == 1

    out = capsys.readouterr().out

    assert "E1       FAIL" in out
    assert "boom" in out

    assert (
        "TOTAL    "
        "0 passed, "
        "1 failed"
        in out
    )


def test_validate_continues_after_evidence_failure(
    tmp_path,
):
    case = make_case(tmp_path)

    case["notebook"]["cells"] = [
        markdown(
            "notebook line\n"
        ),
        evidence(
            [2],
            (
                'raise RuntimeError'
                '("first failed")\n'
            ),
            evidence_id="E1",
        ),
        evidence(
            [2],
            (
                "from pathlib import Path\n"
                'Path("continued.marker")'
                '.write_text("yes")\n'
            ),
            evidence_id="E2",
        ),
    ]

    with pytest.raises(
        SystemExit
    ) as exc_info:
        run_validate(case)

    assert exc_info.value.code == 1

    assert (
        case["repo"]
        / "continued.marker"
    ).read_text() == "yes"
endef
