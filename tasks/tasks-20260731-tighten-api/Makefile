# Requires a more recent GNU make on macOS
 
PYTHON ?= pixi run --frozen -e detour-ai-augment-backend-api python
VERBOSE ?= 0

TASK := src/TASK.md
MANIFEST := manifest.json
AGENTS := build/AGENTS.md
SPEC := build/SPEC.ipynb

SHELL := /usr/bin/env
.SHELLFLAGS := bash -c
.ONESHELL:

.PHONY: manifest validate

manifest:
	@$(PYTHON) - <<'PY'
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
	PY

validate:
	@$(PYTHON) - <<'PY'
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

	text_entries_by_destination = sorted(
	    text_entries,
	    key=lambda entry: entry["build"]["line"],
	)

	assert [
	    entry["build"]["line"] for entry in text_entries_by_destination
	] == list(range(1, len(agents_lines) + 1))
	assert [entry["line"] for entry in text_entries_by_destination] == sorted(
	    entry["line"] for entry in text_entries_by_destination
	)

	for entry in text_entries:
	    destination_line = entry["build"]["line"]
	    assert destination_line >= 1
	    assert destination_line <= len(agents_lines)
	    assert agents_lines[destination_line - 1] == task_lines[entry["line"] - 1]

	nb = json.loads(spec_path.read_text(encoding="utf-8"))
	assert nb["nbformat"] == 4
	cells = nb["cells"]

	def cell_source(cell):
	    source = cell["source"]
	    if isinstance(source, list):
	        return "".join(source)
	    assert isinstance(source, str)
	    return source

	ipynb_entries = [
	    entry for entry in entries
	    if entry["build"]["type"] == "ipynb"
	]

	by_cell = defaultdict(list)
	for entry in ipynb_entries:
	    cell = entry["build"]["cell"]
	    assert isinstance(cell, int)
	    assert 0 <= cell < len(cells)
	    by_cell[cell].append(entry)

	markdown_cells = {
	    index
	    for index, cell in enumerate(cells)
	    if cell["cell_type"] == "markdown"
	}

	assert set(by_cell) == markdown_cells
	assert all(cell["cell_type"] in {"markdown", "code"} for cell in cells)
	assert cells
	assert cells[0]["cell_type"] == "markdown"

	previous_source_number = 0

	for cell_index in sorted(by_cell):
	    cell_entries = by_cell[cell_index]
	    cell = cells[cell_index]
	    assert cell["cell_type"] == "markdown"

	    source_numbers = sorted(entry["line"] for entry in cell_entries)

	    assert source_numbers == list(
	        range(source_numbers[0], source_numbers[-1] + 1)
	    )
	    assert source_numbers[0] > previous_source_number
	    previous_source_number = source_numbers[-1]

	    expected = "".join(
	        task_lines[number - 1]
	        for number in source_numbers
	    )

	    assert cell_source(cell) == expected

	    next_markdown = min(
	        (index for index in markdown_cells if index > cell_index),
	        default=len(cells),
	    )
	    evidence_cells = cells[cell_index + 1:next_markdown]
	    assert evidence_cells
	    for evidence_cell in evidence_cells:
	        assert evidence_cell["cell_type"] == "code"
	        assert cell_source(evidence_cell).strip()
	        assert evidence_cell["metadata"].get("task_lines") == source_numbers

	reconstructed = [""] * len(task_lines)

	for entry in text_entries:
	    reconstructed[entry["line"] - 1] = agents_lines[
	        entry["build"]["line"] - 1
	    ]

	for cell_index, cell_entries in by_cell.items():
	    source_numbers = sorted(entry["line"] for entry in cell_entries)
	    cell_lines = cell_source(cells[cell_index]).splitlines(keepends=True)

	    assert len(cell_lines) == len(source_numbers)

	    for number, line in zip(source_numbers, cell_lines, strict=True):
	        reconstructed[number - 1] = line

	reconstructed_text = "".join(reconstructed)

	assert reconstructed_text == task_text
	assert hashlib.sha256(
	    reconstructed_text.encode("utf-8")
	).hexdigest() == manifest["source"]["sha256"]

	evidence_cells = [
	    (index, cell)
	    for index, cell in enumerate(cells)
	    if cell["cell_type"] == "code"
	]
	for _cell_index, evidence_cell in evidence_cells:
	    metadata = evidence_cell["metadata"]
	    assert metadata.get("evidence_id")
	    assert metadata.get("summary")
	    assert metadata.get("task_lines")

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
	block_results = defaultdict(lambda: {"passed": 0, "failed": 0})
	verbose = str("$(VERBOSE)").lower() not in {"", "0", "false", "no"}
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
	                f"{evidence_id:<8} PASS  {elapsed:6.2f}s  {summary}"
	            )
	        except Exception as exc:
	            block_results[block]["failed"] += 1
	            elapsed = time.monotonic() - started
	            reason = str(exc).strip() or type(exc).__name__
	            reason_lines = reason.splitlines()
	            concise_lines = reason_lines[:12]
	            if len(reason_lines) > len(concise_lines):
	                concise_lines.append(
	                    f"… {len(reason_lines) - len(concise_lines)} more lines"
	                )
	            print(
	                f"{evidence_id:<8} FAIL  {elapsed:6.2f}s  {summary}"
	            )
	            for reason_line in concise_lines:
	                print(f"{'':8}       {reason_line}")
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
	for (first_line, last_line), results in block_results.items():
	    line_range = (
	        str(first_line)
	        if first_line == last_line
	        else f"{first_line}-{last_line}"
	    )
	    print(
	        f"TASK {line_range:<7} "
	        f"{results['passed']} passed, {results['failed']} failed"
	    )

	print(
	    "\nTOTAL    "
	    f"{len(execution_passes)} passed, "
	    f"{len(execution_failures)} failed"
	)

	if execution_failures:
	    if verbose:
	        print("\nFULL TRACEBACKS")
	        for evidence_id, summary, failure in execution_failures:
	            print(f"\n{evidence_id} {summary}\n{failure}")
	    raise SystemExit(1)
	PY
