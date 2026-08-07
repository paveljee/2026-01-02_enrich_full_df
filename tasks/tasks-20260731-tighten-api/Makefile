# Requires a more recent GNU make on macOS
 
PYTHON ?= pixi run -e detour-ai-augment-backend-api python

TASK := src/TASK.md
MANIFEST := manifest.json
AGENTS := build/AGENTS.md
SPEC := build/SPEC.ipynb

SHELL := /usr/bin/env
.SHELLFLAGS := bash -c
.ONESHELL:

.PHONY: manifest validate

manifest:
	$(PYTHON) - <<'PY'
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

	manifest_path.write_text(
	    json.dumps(manifest, indent=2) + "\n",
	    encoding="utf-8",
	)
	PY

validate:
	$(PYTHON) - <<'PY'
	import hashlib
	import json
	from collections import defaultdict
	from pathlib import Path

	import nbformat

	task_path = Path("$(TASK)")
	manifest_path = Path("$(MANIFEST)")
	agents_path = Path("$(AGENTS)")
	spec_path = Path("$(SPEC)")

	raw = task_path.read_bytes()
	task_text = raw.decode("utf-8")
	task_lines = task_text.splitlines(keepends=True)

	manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

	assert manifest["source"]["path"] == str(task_path)
	assert manifest["source"]["sha256"] == hashlib.sha256(raw).hexdigest()

	entries = manifest["lines"]

	assert len(entries) == len(task_lines)
	assert [entry["line"] for entry in entries] == list(
	    range(1, len(task_lines) + 1)
	)

	for entry, source_line in zip(entries, task_lines, strict=True):
	    assert entry["sha256"] == hashlib.sha256(
	        source_line.encode("utf-8")
	    ).hexdigest()
	    assert entry["build"] is not None
	    assert entry["build"]["type"] in {"text", "ipynb"}

	agents_lines = agents_path.read_text(
	    encoding="utf-8"
	).splitlines(keepends=True)

	text_entries = [
	    entry for entry in entries
	    if entry["build"]["type"] == "text"
	]

	assert sorted(
	    entry["build"]["line"] for entry in text_entries
	) == list(range(1, len(agents_lines) + 1))

	for entry in text_entries:
	    destination_line = entry["build"]["line"]
	    assert destination_line >= 1
	    assert destination_line <= len(agents_lines)
	    assert agents_lines[destination_line - 1] == task_lines[entry["line"] - 1]

	nb = nbformat.read(spec_path, as_version=4)

	ipynb_entries = [
	    entry for entry in entries
	    if entry["build"]["type"] == "ipynb"
	]

	by_cell = defaultdict(list)
	for entry in ipynb_entries:
	    cell = entry["build"]["cell"]
	    assert isinstance(cell, int)
	    assert 0 <= cell < len(nb.cells)
	    by_cell[cell].append(entry)

	markdown_cells = {
	    index
	    for index, cell in enumerate(nb.cells)
	    if cell.cell_type == "markdown"
	}

	assert set(by_cell) == markdown_cells

	for cell_index, cell_entries in by_cell.items():
	    cell = nb.cells[cell_index]
	    assert cell.cell_type == "markdown"

	    source_numbers = sorted(entry["line"] for entry in cell_entries)

	    assert source_numbers == list(
	        range(source_numbers[0], source_numbers[-1] + 1)
	    )

	    expected = "".join(
	        task_lines[number - 1]
	        for number in source_numbers
	    )

	    assert cell.source == expected

	reconstructed = [""] * len(task_lines)

	for entry in text_entries:
	    reconstructed[entry["line"] - 1] = agents_lines[
	        entry["build"]["line"] - 1
	    ]

	for cell_index, cell_entries in by_cell.items():
	    source_numbers = sorted(entry["line"] for entry in cell_entries)
	    cell_lines = nb.cells[cell_index].source.splitlines(keepends=True)

	    assert len(cell_lines) == len(source_numbers)

	    for number, line in zip(source_numbers, cell_lines, strict=True):
	        reconstructed[number - 1] = line

	reconstructed_text = "".join(reconstructed)

	assert reconstructed_text == task_text
	assert hashlib.sha256(
	    reconstructed_text.encode("utf-8")
	).hexdigest() == manifest["source"]["sha256"]

	print("valid")
	PY
