# RFC: REPL Diagnostics & Progress Messaging

**Timestamp (UTC):** 2026-02-02 22:30Z  \
**Author:** GPT-5.2-Codex (OpenAI)

## Task summary
Add informative, structured progress and diagnostic messaging to the REPL pipeline so users can spot issues as they happen without needing a separate debug mode. The REPL should surface **counts, timings, and rich examples** (e.g., researcher names, sample rows, matched keys) at each stage while remaining readable and non-noisy. When diagnostics are too large for the CLI, the REPL should **dump a structured report to file** and clearly instruct the user where to review it. Output should be incremental and comfortable to follow step-by-step.

## Goals
- Provide actionable runtime visibility for each pipeline step.
- Make errors easier to diagnose by showing **what was expected** and **what was observed**.
- Provide **small, curated examples** (e.g., researcher names, matched keys) in-console.
- Automatically **spill large diagnostics to a file** and summarize in-console.
- Keep output friendly for interactive use (REPL), with optional verbosity levels if needed.

## Non-goals
- No change in pipeline logic beyond safe logging and reporting.
- No raw full-dataset dumps unless the CLI output would be overwhelming; in that case emit a **bounded report file** (see below).

## Proposed messaging strategy

### Global structure
- Introduce a simple **stage logger** with:
  - `start` message
  - `end` message with **duration**, **counts**, and **example snippets**
  - consistent formatting
- Add optional **verbosity level** (e.g., `--verbose`) to include additional details.
- Add **diagnostic spill-to-file** when output would be too large for the CLI.

### Suggested stages & messages
1. **Input discovery**
   - Count of XLSX, DOCX files found.
   - Report any files skipped (e.g., `~$` temporary files).
   - Show a few example filenames.

2. **Resource registration**
   - Number of resources registered per group.
   - Note hash verification results or warnings if disabled.
   - Example resource names (3–5).

3. **Population load (XLSX)**
   - Total rows loaded across all XLSX files.
   - Table schema size (# columns).
   - Example rows (first/last name fields + category).

4. **World Bank economies**
   - Count of high-income economies loaded.
   - Example economies (5–10).

5. **Sampling**
   - Draw sizes, seed, total sampled rows.
   - Pilot sample size.
   - Example sampled researchers (first/last + filename).

6. **Indexing**
   - Number of unique name keys generated.
   - Confirm `name_key` presence in samples table.
   - Example name keys (first/last).

7. **Population match**
   - Number of matched population rows.
   - Example matched keys and fragments.

8. **DOCX load**
   - Number of DOCX tables, total rows parsed.
   - Example parsed researcher names (from DOCX column).

9. **DOCX match**
   - Matched docx rows count.
   - Example matched names and fragments.
   - Missing name column errors should show available columns.

10. **SciSciNet match**
    - Matched authors count.
    - Example author IDs and display names.
    - Count of missing SciSciNet files before run (if any).

11. **Cards + output**
    - Cards count, output format, output ZIP path.
    - Example card filenames (3–5).

### Example output snippet
```
[stage] Loading XLSX population...
  - files: 11
  - rows: 32,150
  - columns: 22
  - sample researchers: Ada Lovelace; Grace Hopper; Alan Turing
[done] Loading XLSX population (2.1s)

[stage] Sampling...
  - draws: [20, 40, 40, 40, 40, 40, 40, 40]
  - seed: 42
  - sampled rows: 300
  - pilot rows: 10
  - sample names: Lovelace, Ada; Hopper, Grace; Turing, Alan
[done] Sampling (0.3s)
```

## Implementation plan
1. Add a lightweight stage timing helper (context manager or small utility).
2. Extend `src/repl.py` to emit messages at each stage with counts and small examples.
3. Add a `--verbose` CLI flag to optionally print extra details.
4. Add **diagnostic spill-to-file** when output would be large (e.g., top N rows per stage into `data/diagnostics/`).
5. Add tests for formatting and key message presence (optional).

## Open questions and answers
1. Should verbosity be controlled by `--verbose` (default off) or `--quiet` (default on)? **default on**
2. Should the diagnostic report file default to `data/diagnostics/` or a timestamped temp dir? **data/diagnostics/**
3. Do you prefer a human-readable report (Markdown/CSV) or machine-readable (JSONL)? **human-readable**
