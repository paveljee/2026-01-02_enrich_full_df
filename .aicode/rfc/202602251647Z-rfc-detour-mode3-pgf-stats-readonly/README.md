# RFC: Read-Only Detour for Mode-3 `p_gf` Stats from Persisted Tables

**Timestamp (UTC):** 2026-02-25 16:47Z  \
**Author:** GPT-5 Codex (OpenAI)

## Task summary
Define a new detour that computes **mode-3** (`card_subset_mode = 3`) statistics for `ssnau.p_gf` using an already-produced pipeline DuckDB file, without running any pipeline steps and without modifying the database.

This RFC is intentionally pre-implementation and captures:
- the exact derivation logic needed to match step-10 mode-3 semantics,
- the read-only detour architecture,
- and the test strategy following the existing detours philosophy.

## Goals
- Add a self-contained detour module under `src/detours` for mode-3 `p_gf` stats.
- Keep the detour **read-only** and independent from `src/repl.py`.
- Derive mode-3 membership from persisted tables already present in the DB.
- Match current step-10 mode-3 semantics exactly (including non-vacuous XLSX rule).
- Emit clear human-readable stats plus structured metadata for reproducibility/tests.
- Follow the existing detour philosophy (standalone module, direct module entrypoint, dedicated test module).

## Non-goals
- Re-running the main pipeline or any pipeline steps from the detour.
- Writing any new pipeline tables/views into the DB.
- Changing step-10 logic as part of this detour.
- Generalizing to arbitrary subset modes beyond the concrete mode-3 need (at least in v1).

---

## Background and why a detour is appropriate

The user asked for clean code to reproduce the mode-3 `p_gf` summary/statistics directly from a completed `config_p_gf.json` run, and explicitly pointed out:
- this is an analysis task,
- the DB is already available,
- and no pipeline steps need to run.

That makes this a good detour because it:
- preserves `src/repl.py` and main pipeline behavior,
- provides a repeatable entrypoint for future read-only analyses,
- and can be tested independently.

This detour is different from `detour_step4_breakdown`:
- `detour_step4_breakdown` runs steps 1-4 and intentionally creates a detour DB.
- **This detour should run zero steps and only read an existing DB.**

---

## Key finding: what data is (and is not) sufficient

### `ssn_innerdicts` alone is not enough

`ssn_innerdicts` (step-9 parquet innerdict table) contains:
- `ktp.source_key` (name key)
- `ssnau.p_gf`
- enough info to count sciscinet innerdicts per name key

So from `ssn_innerdicts` alone we can derive:
- `sciscinet_count == 1`
- `p_gf` stats for that subset

But `ssn_innerdicts` **does not contain the step-10 XLSX exactness predicate inputs** in a complete way.

### Exact mode-3 requires three persisted tables

To reconstruct step-10 mode-3 exactly, we need:
1. `outerdict_stub` (step-6 key universe / denominator)
2. `xlsx_innerdicts` (step-7 XLSX innerdict payloads, including `ktp.xlsx_match`)
3. `ssn_innerdicts` (step-9 sciscinet innerdict rows + `ssnau.p_gf`)

This is the minimal persisted-table set for exact mode-3 stats.

---

## Current mode-3 semantics that must be matched

From current `src/steps/step_10_build_cards.py`, mode 3 is:

- `sciscinet_exactly_one_ok`
- `and xlsx_exact_ok`
- docx rule is ignored for mode 3

And `xlsx_exact_ok` is currently **non-vacuous**:
- requires **at least one present** `ktp.xlsx_match` payload
- and **all present** payloads must be exact

Important implication:
- This detour must mirror the exact step-10 helper semantics for:
  - `_has_present_xlsx_match_payload(...)`
  - `_is_exact_xlsx_match_payload(...)`

It should not “simplify” the rule or infer mode 3 from sciscinet rows alone.

---

## Important storage-format discovery (must be handled in implementation)

`xlsx_innerdicts.innerdicts` is **JSON Lines**, not a single JSON object.

That means:
- `json.loads(blob)` fails with `JSONDecodeError: Extra data`
- the detour must parse via JSONL semantics (one JSON object per line)

Existing helper to reuse:
- `src/helpers/jsonlines.py` -> `loads_jsonlines(...)`

This is a key implementation detail and should be explicitly tested.

---

## Proposed detour (v1)

### Module
- `src/detours/detour_mode3_pgf_stats.py`

### Test module
- `tests/test_detour_mode3_pgf_stats.py`

### Entrypoint
- `python -m src.detours.detour_mode3_pgf_stats --config config_p_gf.json`

CLI behavior should stay straightforward and close to the reference detour:
- required `--config` only
- print results to stdout using Rich-formatted CLI output (human-readable summary)
- no extra detour-specific flags in v1

### Runtime model (read-only)

This detour should:
1. Parse config using `PipelineConfig` (for `db_file`, labels, etc.).
2. Open the DB with `duckdb.connect(..., read_only=True)`.
3. Run **no** pipeline steps.
4. Compute mode-3 membership from persisted tables.
5. Compute `p_gf` stats for the selected unique names.
6. Print a stable human-readable summary to stdout using Rich (same style philosophy as the reference detour).
7. Return structured metadata (deterministic enough for tests).

This detour should **not**:
- call `init_pipeline(...)`
- call `run_step(...)`
- touch `STEP_REGISTRY`
- create detourized DB/state paths

Rationale:
- unlike step-running detours, this one is an analysis over an already-built DB
- read-only opening is the isolation boundary

---

## Exact derivation plan (code-level)

The implementation should be explicit and boring (in a good way).

### Inputs (persisted tables only)

Use these tables from the DB:
- `outerdict_stub`
- `xlsx_innerdicts`
- `ssn_innerdicts`

Avoid views for this detour (`xlsx_output`, `docx_output`, etc.) because:
- they are unnecessary here
- some depend on runtime UDFs (e.g., `unaccent`) in ad-hoc sessions

### Step A: load step-6 key universe

Query:
- `SELECT name_key FROM outerdict_stub`

This defines the mode-3 denominator at the unique-name level.

### Step B: load step-7 XLSX payloads per name key

Query:
- `SELECT name_key, innerdicts FROM xlsx_innerdicts`

For each row:
- parse `innerdicts` with `loads_jsonlines(...)`
- collect `inner["ktp.xlsx_match"]` payloads per `name_key`

Then compute for each `name_key`:
- `xlsx_has_present = any(_has_present_xlsx_match_payload(payload))`
- `xlsx_all_present_exact = all(_is_exact_xlsx_match_payload(payload))`
- `xlsx_exact_ok = xlsx_has_present and xlsx_all_present_exact`

### Step C: load step-9 sciscinet rows and `p_gf`

Query:
- `SELECT "ktp.source_key", "ssnau.p_gf" FROM ssn_innerdicts`

For each `ktp.source_key`:
- count rows -> `sciscinet_count`
- collect `p_gf` values

For mode 3, selected names must satisfy:
- `sciscinet_count == 1`
- so exactly one `p_gf` value should exist for selected names

Implementation should fail loudly if this invariant is violated for a selected key.

### Step D: reconstruct mode-3 selected unique names

For each `name_key` in `outerdict_stub`:
- `selected = (sciscinet_count == 1) and xlsx_exact_ok`

This reconstructed selected count should match step-10 log output for the same DB (example observed: `7312`).

### Step E: compute requested stats on `p_gf`

On mode-3 selected unique names:
- total selected names
- `p_gf` non-missing count and percentage
- missing count and percentage
- mean
- SD, SE
- 95% CI for mean (normal approximation)
- median, Q1, Q3
- min, max
- IQR and Tukey fences
- outlier counts (lower / upper / total)

### Step F: compute requested `p_gf` buckets

On mode-3 selected unique names, count:
- missing
- exactly `0`
- exactly `0.5`
- exactly `1`
- between `0` and `1` (excluding `0.5`)
- (optionally also report between `0` and `1` including `0.5`)

The detour should report both:
- raw counts
- percentages of mode-3 selected names

It is also useful (and should be included) to report bucket percentages among **non-missing** values.

---

## Output contract (proposed)

The detour should print a stable summary with sections similar to:

1. **Scope**
   - DB path
   - table names used
   - mode definition (mode 3)

2. **Selection counts**
   - `outerdict` keys total
   - mode-3 selected unique names
   - selected % of `outerdict` keys

3. **Participation (`p_gf` present/missing)**
   - non-missing / missing raw + %

4. **Distribution stats (`p_gf`, non-missing only)**
   - mean, 95% CI, median, quartiles, min/max

5. **Buckets**
   - missing / `0` / `0.5` / `1` / between

6. **Outliers (Tukey 1.5*IQR)**
   - fences and counts

Structured metadata (`DetourResult.metadata`) should include the same values for tests, but stdout should remain the primary user-facing output (Rich CLI summary).

---

## Testing strategy (following detour philosophy closely)

Use one dedicated test file:
- `tests/test_detour_mode3_pgf_stats.py`

### Fast tests (required)

1. **Contract + entrypoint shape**
- detour module exposes `DETOUR_ID`, `DETOUR_NAME`, `DETOUR_DESCRIPTION`, `run_detour(...)`
- returns structured result with `success`, `summary`, `metadata`

2. **Import isolation**
- no imports of `src.repl`
- no imports of `src.steps` / `STEP_REGISTRY`
- no use of `run_step(...)` or `init_pipeline(...)`

3. **Read-only DB behavior**
- create a tiny fixture DuckDB with only required tables:
  - `outerdict_stub`
  - `xlsx_innerdicts`
  - `ssn_innerdicts`
- run detour against it
- assert expected stats exactly
- verify table row counts unchanged after run

4. **JSONL parsing correctness**
- fixture should include at least one `xlsx_innerdicts` row with multiple JSONL entries
- ensure mode-3 selection reflects all rows, not just the first line

5. **Mode-3 semantics parity (targeted)**
- fixture cases should cover:
  - `sciscinet_count = 0`, `1`, `>1`
  - no present XLSX payload (fail)
  - invalid/non-exact payload (fail)
  - exact payload(s) only (pass)
  - `p_gf` missing / `0` / `0.5` / `1` / interior values

### Slow test(s) (optional but recommended)

1. **Real-DB smoke/equivalence test (if shared DB is available)**
- open known completed p_gf DB read-only
- run detour
- assert stable headline values (example from current known run):
  - mode-3 selected names = `7312`
  - `p_gf` non-missing = `6708`
  - `p_gf` missing = `604`

This should be marked `@pytest.mark.slow` and skipped if the DB path is absent.

---

## Risks and mitigations

- **Risk: drift from step-10 mode-3 semantics**
  - Mitigation: mirror helper logic exactly and add fixture tests for edge cases.

- **Risk: hidden dependence on views/UDFs**
  - Mitigation: use persisted tables only (`outerdict_stub`, `xlsx_innerdicts`, `ssn_innerdicts`).

- **Risk: accidental writes to DB**
  - Mitigation: enforce `read_only=True`; add tests asserting row counts unchanged.

- **Risk: floating-point comparison brittleness in tests**
  - Mitigation: assert exact counts, and use tolerance for means/CI where needed.

---

## Implementation plan

1. Add `src/detours/detour_mode3_pgf_stats.py` (self-contained, read-only).
2. Implement a small deterministic stats helper inside the detour (or local functions).
3. Parse `xlsx_innerdicts.innerdicts` via `loads_jsonlines(...)`.
4. Reconstruct mode-3 selection exactly from persisted tables.
5. Emit human-readable summary + structured metadata.
6. Add `tests/test_detour_mode3_pgf_stats.py`.
7. Run targeted tests and `pixi run pre-commit`.

---

## Acceptance criteria

- New detour runs directly via module entrypoint.
- Detour opens the DB read-only and runs no pipeline steps.
- Mode-3 selected count matches step-10 for the same DB.
- `p_gf` stats include:
  - participation raw + %
  - mean + 95% CI
  - median / quartiles
  - min / max
  - outlier counts
  - bucket counts for missing / `0` / `0.5` / `1` / between
- Tests cover read-only behavior, JSONL parsing, and mode-3 semantics.

---

## My interpretation of the user request (explicit)

This detour should be treated as a **read-only analytical replay** of step-10 mode-3 selection logic for one metric (`ssnau.p_gf`), built on already-materialized tables, not a mini-pipeline.

That means:
- no step execution
- no DB mutation
- no coupling to `repl.py`
- exact semantic parity for the mode-3 selector
- clean, repeatable stats output for the completed p_gf run DB

This interpretation matches the user's emphasis:
- “all we do is really just read db”
- “no steps at all”
- “follow detours philosophy”
- “clean code”
