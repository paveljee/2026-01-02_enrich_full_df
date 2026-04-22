# RFC: Read-Only Detour for Mode-3 Income-Group and Priority-Group Stats from Persisted Tables

**Timestamp (UTC):** 2026-04-22 18:52Z  \
**Author:** GPT-5 Codex (OpenAI)

## Task summary
Retarget `src/detours/detour_mode3_econ_stats.py` so it stops pretending to be a `p_gf` detour and instead computes a read-only **mode-3** breakdown for:
- `ktp.hcr_world_bank_economies_income_group`
- `ktp.priority_label`

This RFC is intentionally pre-implementation and captures:
- the exact persisted-table derivation needed to keep step-10 mode-3 semantics,
- the aggregation rules needed for XLSX-side country lists and row-level labels,
- the special handling needed for multi-country names that span multiple income groups or multiple priority groups,
- and a concrete output plan that preserves as much of the current `p_gf` detour structure as the new target variables reasonably allow.

## Goals
- Keep the work centered on the existing module path: `src/detours/detour_mode3_econ_stats.py`.
- Preserve as much of the current detour code shape and CLI behavior as possible.
- Keep the detour fully **read-only** and independent from `src/repl.py`.
- Reconstruct mode-3 membership from persisted tables exactly as the current `p_gf` detour does.
- Replace `p_gf`-specific summaries with income-group / priority-group summaries that are actually meaningful for the new target variables.
- Include the definition / rule for each `KTP_PRIORITY_GROUP_COL` label in the human-readable output report.
- Preserve the spirit of the current output sections:
  - scope
  - selection counts
  - rule counts
  - distribution-style summary
  - bucket-style summary
  - audit section
- Return structured metadata that is deterministic enough for tests.

## Non-goals
- Re-running any pipeline steps from the detour.
- Writing any new tables or views into the DB.
- Changing step-10 mode-3 selection semantics.
- Replacing `src/detours/detour_mode3_pgf_stats.py`.
- Turning this into a generic “mode-3 stats framework” in v1.

---

## Background and why this detour should stay a detour

The current `src/detours/detour_mode3_econ_stats.py` is effectively a copy of `detour_mode3_pgf_stats.py`:
- same detour id/name,
- same `p_gf` constants,
- same `p_gf` stats,
- same `p_gf`-specific stdout sections.

The user wants the same general analytical pattern, but for a different target:
- keep mode-3 reconstruction,
- keep the output structure where it still makes sense,
- and only change what the target variable truly forces us to change.

That is still a strong fit for a detour because:
- the DB already exists,
- this is an analysis over persisted tables,
- and we do not want to perturb main pipeline flow or `repl.py`.

---

## Key finding: selector logic stays the same, target fields do not

### Mode-3 membership still comes from the same three persisted tables

To reconstruct mode-3 exactly, we still need:
1. `outerdict_stub`
2. `xlsx_innerdicts`
3. `ssn_innerdicts`

Reason:
- `ssn_innerdicts` is still required for `sciscinet_count == 1`
- `xlsx_innerdicts` is still required for the non-vacuous XLSX exactness rule
- `outerdict_stub` is still the unique-name universe / denominator

### The target labels now live on the XLSX side

Unlike `ssnau.p_gf`, the new primary label fields are sourced from persisted XLSX innerdict rows:
- `ktp.hcr_world_bank_economies_income_group`
- `ktp.priority_label`

And the supporting multi-country list field is:
- `ktp.hcr_world_bank_economies`

These are carried into `xlsx_innerdicts.innerdicts` by step 7, alongside:
- `ktp.filename`
- `ktp.fragment`
- `ktp.xlsx_match`
- `ktp.priority`
- other row context

Important implication:
- mode-3 **selection** is still name-level,
- but country / income-group / priority-group **content** is naturally XLSX-row-level before we roll it up.

That means the implementation must be explicit about which metrics are:
- per selected unique name,
- per selected population row,
- or per distinct country mention.

---

## Current mode-3 semantics that must remain unchanged

From current step-10 logic, mode 3 is still:

- `sciscinet_exactly_one_ok`
- `and xlsx_exact_ok`
- docx rule ignored for mode 3

And `xlsx_exact_ok` remains **non-vacuous**:
- at least one present `ktp.xlsx_match` payload
- and all present payloads must be exact

So this retargeted detour must continue to mirror the current helper semantics for:
- `_has_present_xlsx_match_payload(...)`
- `_is_exact_xlsx_match_payload(...)`

This is the part we should cherish and leave alone unless the data model forces a change.

---

## Important storage-format findings

### `xlsx_innerdicts.innerdicts` is still JSON Lines

This is unchanged from the `p_gf` detour:
- one DB cell contains multiple JSON objects separated by newlines
- so the detour must keep using `loads_jsonlines(...)`

### `ktp.hcr_world_bank_economies` needs defensive normalization

The economies field originates as JSON-like content. In persisted XLSX innerdict rows it may appear as:
- a JSON string encoding a list,
- an already-decoded list,
- blank / null,
- or, in malformed edge cases, a scalar string

The detour should normalize this into a clean `list[str]` with:
- trimmed string items only,
- duplicates removed where the metric calls for set semantics,
- stable ordering for deterministic metadata/tests.

### `ktp.hcr_world_bank_economies_income_group` and `ktp.priority_label` are scalar row labels

These are the actual target labels for the headline breakdowns.

But both are row-level summaries:
- `ktp.hcr_world_bank_economies_income_group` collapses possibly multiple countries to one income-group label using step-4 precedence
- `ktp.priority_label` collapses possibly multiple countries to one priority-group label using step-4 precedence

That means they are sufficient for row-level breakdowns, but **not sufficient by themselves** for the requested “countries span multiple groups” audit.

### Multi-country divergence metrics need per-country classification

To answer:
- which selected names have `>1` countries in `ktp.hcr_world_bank_economies`
- and those countries fall into different income groups
- and those countries fall into different priority groups

the detour cannot rely only on the collapsed row labels.

Instead it should:
- use the normalized canonical countries from `ktp.hcr_world_bank_economies`
- build a small read-only country lookup from the same World Bank resource used in step 4 for income groups
- derive per-country priority groups from the same step-4 country sets and labels

This should be implemented locally inside the detour or via small local helpers, not by importing and running step code.

### Priority-group labels must use the exact step-4 precedence

The detour should document and use the same precedence that step 4 applies when producing `ktp.priority_label`:

1. `GREATER_CHINA` if any matched country is in the Greater China set
2. `NON_ENGLISH_NON_EU_HICS_NO_GREATER_CHINA` if no higher-priority rule fired and any matched country is in the non-English, non-EU HIC set
3. `EU_COUNTRIES` if no higher-priority rule fired and any matched country is in the EU set
4. `ENGLISH_HICS` if no higher-priority rule fired and any matched country is in the English-HIC set
5. `LMICS_NO_GREATER_CHINA_OR_UNKNOWN` otherwise, including:
   - no matched countries
   - only LMIC countries
   - countries that do not fall into the higher-priority sets above

This matters in two places:
- the row-level `ktp.priority_label` breakdown
- the derived per-country priority-group divergence audit

### `ktp.priority_label` may also vary across matched rows for one name

Each matched XLSX row has one priority-group label, but a selected mode-3 name may map to:
- one matched row,
- multiple matched rows with the same label,
- or multiple matched rows with different labels

So the detour needs a deliberate rule for:
- row-level priority-group distribution,
- and name-level priority-group consistency / multiplicity.

---

## Proposed detour (v1)

### Module
- `src/detours/detour_mode3_econ_stats.py`

### Test module
- `tests/test_detour_mode3_econ_stats.py`

### Entrypoint
- `python -m src.detours.detour_mode3_econ_stats --config <config>.json`

CLI behavior should stay as close as possible to the existing read-only detour:
- required `--config` only
- Rich stdout summary
- no extra detour-specific flags in v1

### Runtime model (read-only)

This detour should:
1. Parse config via `PipelineConfig`.
2. Open the DB with `duckdb.connect(..., read_only=True)`.
3. Run zero pipeline steps.
4. Reconstruct mode-3 selected names exactly as today.
5. Derive income-group / priority-group summaries from persisted XLSX innerdict rows belonging to those selected names, with country-based derived metrics for the multi-country divergence section.
6. Print a stable human-readable summary.
7. Return structured metadata for reproducibility and tests.

It should **not**:
- call `init_pipeline(...)`
- call `run_step(...)`
- touch `STEP_REGISTRY`
- create detour DB/state variants

---

## Exact derivation plan (code-level)

The safest implementation is a minimal retarget of the current file:
- preserve the selector helpers,
- preserve the high-level function boundaries,
- replace only the `p_gf`-specific extraction and reporting logic.

### Step A: keep the current population denominator

Keep:
- `SELECT COUNT(*) FROM population_with_names_economy`

Rationale:
- this is already used in the current detour,
- it preserves headline comparability with the existing output,
- and it minimizes unnecessary structural change.

### Step B: load step-6 key universe

Keep:
- `SELECT name_key FROM outerdict_stub ORDER BY name_key`

This remains the unique-name denominator.

### Step C: load step-7 XLSX payloads per name key

Use:
- `SELECT name_key, innerdicts FROM xlsx_innerdicts`

For each parsed innerdict row, collect:
- `ktp.xlsx_match`
- `ktp.filename`
- `ktp.fragment`
- `ktp.hcr_world_bank_economies`
- `ktp.hcr_world_bank_economies_income_group`
- `ktp.priority_label`

This lets the detour compute:
- `xlsx_exact_ok`
- selected population-row identities
- row-level country payloads
- row-level income-group payloads
- row-level priority-group payloads

### Step D: load step-9 sciscinet counts per name key

Use:
- `SELECT "ktp.source_key" FROM ssn_innerdicts`

For mode-3 selection we only need the count per source key, not `p_gf`.

### Step E: reconstruct mode-3 selected names

For each `name_key` in `outerdict_stub`:
- `selected = (sciscinet_count == 1) and xlsx_exact_ok`

This part should remain materially identical to the current detour.

### Step F: build normalized target payloads for selected names

For each selected `name_key`, derive both row-level and name-level views:

1. Selected population rows
- all `(filename, fragment)` identities attached to selected XLSX rows

2. Countries per selected row
- normalized list of countries for that row

3. Distinct countries per selected name
- union of normalized countries across that name's selected XLSX rows

4. Income groups per selected row
- normalized scalar label from `ktp.hcr_world_bank_economies_income_group`

5. Distinct row income groups per selected name
- distinct set of row labels across that name's selected XLSX rows

6. Priority groups per selected row
- normalized scalar label per row

7. Distinct row priority groups per selected name
- distinct set of labels across that name's selected XLSX rows

8. Derived per-country income groups per selected name
- use the canonical countries in `ktp.hcr_world_bank_economies`
- map each country to its World Bank income group via the same source data used in step 4

9. Derived per-country priority groups per selected name
- classify each canonical country into the same priority-group buckets that step 4 uses:
  - `GREATER_CHINA`
  - `NON_ENGLISH_NON_EU_HICS_NO_GREATER_CHINA`
  - `EU_COUNTRIES`
  - `ENGLISH_HICS`
  - fallback `LMICS_NO_GREATER_CHINA_OR_UNKNOWN`

This dual view is important because:
- row-level priority-group counts are naturally exclusive,
- row-level income-group counts are naturally exclusive,
- name-level country counts are more robust if the same name appears in multiple identical rows,
- and the requested multi-country divergence audit is about countries, not collapsed row labels.

---

## Aggregation rules to make explicit

### Income-group breakdown: primary row-level semantics, plus name-level coverage

For the main income-group breakdown, primary counts should be row-level:
- each selected XLSX row contributes one `ktp.hcr_world_bank_economies_income_group` label
- percentages are of selected population rows with non-missing income-group labels

Also include a selected-name coverage column if it stays clean:
- number of selected names that have at least one row with that income-group label

Rationale:
- the target label is the row-level income-group field, not country name,
- and the row-level label is already persisted exactly as step 7 carried it forward.

### Priority-group breakdown: primary row-level semantics, plus name-level audit

For priority groups, the main breakdown should be row-level:
- each selected XLSX row contributes one priority-group label
- percentages are of selected population rows with non-missing priority-group labels

Also compute a name-level audit:
- names with exactly one distinct priority group across matched rows
- names with multiple distinct priority groups across matched rows
- names with no priority group at all

Rationale:
- priority groups are naturally single-label at the row level,
- but name-level multiplicity is analytically important and should not be hidden.

### Country cardinality is the best “distribution” analog

Because the new target is categorical / multi-label, the closest analog to the current numeric distribution section is:
- number of distinct countries per selected name

On that derived numeric vector, we can still compute:
- N
- mean
- SD / SE
- 95% CI for mean
- min / Q1 / median / Q3 / max

This preserves both the shape and much of the code structure of the current distribution section.

### Multi-country divergence audit: percentages should use explicit denominators

The output must include a separate section for selected names that:
- have `>1` distinct countries in `ktp.hcr_world_bank_economies`
- and those countries span `>1` distinct income groups
- and those countries span `>1` distinct priority groups

To avoid ambiguity, report both:
- `% of mode-3 selected names`
- `% of multi-country selected names`

This makes it easy to answer both:
- “how common is this overall?”
- and “among names with multiple countries, how often do the countries cross groups?”

---

## Output contract (proposed)

The detour should preserve the current sectioning as much as possible, with the following mapping.

### 1. Scope
- DB path
- tables used
- mode definition

### 2. Priority-Group Definitions
- include a small legend in stdout describing the rule for each `KTP_PRIORITY_GROUP_COL` value
- definitions should be phrased in precedence order, not just as loose prose
- the report should make clear that these are the same step-4-derived groups used by the persisted data

Recommended legend content:
- `GREATER_CHINA`: any matched country is in the Greater China set
- `NON_ENGLISH_NON_EU_HICS_NO_GREATER_CHINA`: no higher-priority rule fired and any matched country is a non-English, non-EU high-income country
- `EU_COUNTRIES`: no higher-priority rule fired and any matched country is in the EU set
- `ENGLISH_HICS`: no higher-priority rule fired and any matched country is in the English-HIC set
- `LMICS_NO_GREATER_CHINA_OR_UNKNOWN`: fallback bucket for no matched countries, LMIC-only countries, or countries outside the higher-priority sets

### 3. Selection Counts
- population rows
- outerdict keys
- mode-3 selected names
- mode-3 selected % of outerdict keys
- population rows containing mode-3 selected names
- selected names with at least one country
- selected names with at least one income-group label
- selected names with at least one priority-group label
- selected population rows with non-missing country payload
- selected population rows with non-missing income-group payload
- selected population rows with non-missing priority-group payload

### 4. Mode-3 Rule Counts
- same as current detour:
  - sciscinet exactly one
  - xlsx present + exact

### 5. Country Cardinality Distribution (Mode-3 Selected Names)
- derived from `len(distinct countries per selected name)`
- this replaces the old `p_gf Distribution` section in spirit and shape

### 6. Country Cardinality Buckets (Mode-3 Selected Names)
- 0 countries
- exactly 1
- exactly 2
- exactly 3
- 4 or more

If real data suggests a cleaner cut, `3` and `4+` may become `3+`, but the bucket partition must stay exhaustive and explicit.

### 7. Income-Group Breakdown
- one row per observed `ktp.hcr_world_bank_economies_income_group`
- selected population rows
- `% of non-missing selected population rows`
- optional selected-name coverage column

This is the main replacement for the old `p_gf`-specific bucket table.

### 8. Priority-Group Breakdown
- one row per observed `ktp.priority_label`
- selected population rows
- `% of non-missing selected population rows`
- optional selected-name coverage column if cheap to add cleanly

### 9. Multi-Country Divergence Section
- selected names with `>1` distinct countries
- `% of mode-3 selected names`
- selected names with `>1` distinct countries and `>1` derived income groups
- `% of mode-3 selected names`
- `% of multi-country selected names`
- selected names with `>1` distinct countries and `>1` derived priority groups
- `% of mode-3 selected names`
- `% of multi-country selected names`

This section is required even though the headline label breakdown is row-level, because it answers a different name-level question.

### 10. Label Coverage / Consistency Audit
- selected names with no income-group labels
- selected names with no priority-group labels
- selected names with exactly one distinct row income-group label
- selected names with 2+ distinct row income-group labels
- selected names with exactly one distinct row priority-group label
- selected names with 2+ distinct row priority-group labels
- selected rows with missing income-group label
- selected rows with missing priority-group label

This replaces the old `missing p_gf inference audit` in spirit: it explains where interpretation may get messy.

### 11. Country Cardinality Outliers
- Tukey 1.5*IQR on distinct-country-count per selected name
- lower/upper fence
- lower/upper/total outliers

This preserves the old outlier section with a new but still meaningful numeric target.

Structured metadata should include all of the above in deterministic dict/list form.

---

## Testing strategy (following the current detour philosophy)

Use one dedicated test file:
- `tests/test_detour_mode3_econ_stats.py`

### Fast tests (required)

1. **Contract + identity**
- module exposes `DETOUR_ID`, `DETOUR_NAME`, `DETOUR_DESCRIPTION`, `run_detour(...)`
- detour identity strings are no longer `mode3-pgf-stats`

2. **Import isolation**
- no `src.repl`
- no `src.steps`
- no `run_step(...)`
- no `init_pipeline(...)`

3. **Read-only DB behavior**
- tiny DuckDB fixture with:
  - `outerdict_stub`
  - `xlsx_innerdicts`
  - `ssn_innerdicts`
  - `population_with_names_economy` or equivalent denominator support
- run detour
- assert row counts unchanged

4. **JSONL parsing correctness**
- at least one `xlsx_innerdicts` row contains multiple JSONL entries
- mode-3 selection and country/income-group/priority rollups must reflect all rows

5. **Country normalization**
- cover:
  - null / blank
  - JSON array string
  - already-decoded list
  - duplicated countries in one row
- assert stable normalized output

6. **Mode-3 semantics parity**
- cover:
  - `sciscinet_count = 0`, `1`, `>1`
  - no present XLSX payload
  - present but non-exact payload
  - exact payload(s)

7. **Name-level versus row-level aggregation**
- fixture should include a selected name with multiple XLSX rows
- assert:
  - duplicated same-country rows do not overcount name-level country cardinality
  - multiple row income-group labels for one name are surfaced by the audit
  - multiple row priority-group labels for one name are surfaced by the audit

8. **Multi-country divergence derivation**
- fixture should include a selected name with `>1` countries
- assert:
  - derived per-country income-group divergence is detected correctly
  - derived per-country priority-group divergence is detected correctly
  - collapsed row labels alone would not be sufficient for that assertion

9. **Priority-group legend / definitions**
- stdout should include the priority-group definitions section
- test that each expected `KTP_PRIORITY_GROUP_COL` label is described
- test that the definitions reflect precedence, not just label names

### Slow test(s) (recommended)

1. **Real-DB smoke test**
- open a known completed DB read-only
- run the detour
- assert basic invariants only, for example:
  - selected-name count is non-zero
  - country bucket partition sums to selected names
  - income-group breakdown rows sum to non-missing selected population rows
  - priority-group breakdown rows sum to non-missing selected population rows
  - divergence counts do not exceed multi-country selected names

For this detour, fixed exact headline counts may be less stable or less obvious than in the `p_gf` case because:
- countries are multi-label,
- the headline labels are row-level,
- and the divergence section is name-level and derived.

So real-DB slow tests should emphasize invariants more than exact full-table snapshots.

---

## Risks and mitigations

- **Risk: silently preserving the wrong detour identity**
  - Mitigation: explicitly rename detour id/name/description and test them.

- **Risk: name-level versus row-level counting becomes ambiguous**
  - Mitigation: define both views explicitly and label denominators in stdout/metadata.

- **Risk: country payloads arrive in mixed formats**
  - Mitigation: add a small normalization helper with targeted tests.

- **Risk: the requested divergence section cannot be inferred from collapsed row labels alone**
  - Mitigation: derive per-country income-group and priority-group assignments from the canonical countries in `ktp.hcr_world_bank_economies` using the same source logic as step 4, but keep that helper local and read-only.

- **Risk: priority-group labels are shown without enough meaning for readers**
  - Mitigation: print an explicit legend in the output report with the rule for each `KTP_PRIORITY_GROUP_COL` label and its precedence.

- **Risk: priority-group multiplicity gets flattened away**
  - Mitigation: include a dedicated consistency audit for selected names.

- **Risk: over-editing a file that is mostly correct structurally**
  - Mitigation: keep selector helpers, CLI wiring, read-only behavior, and Rich summary skeleton as-is where possible.

---

## Implementation plan

1. Retarget `src/detours/detour_mode3_econ_stats.py` instead of creating yet another detour module.
2. Preserve selector helpers and read-only DB flow.
3. Remove `p_gf`-specific constants, metadata keys, and summary tables.
4. Add small normalization helpers for:
   - country payloads
   - income-group labels
   - priority-group labels
5. Rebuild the stats section around:
   - priority-group definitions legend
   - country cardinality per selected name
   - income-group breakdown
   - priority-group breakdown
   - multi-country divergence section
   - label coverage / consistency audit
6. Add `tests/test_detour_mode3_econ_stats.py`.
7. Run targeted tests and repo formatting / hooks as appropriate.

---

## Acceptance criteria

- `src/detours/detour_mode3_econ_stats.py` is no longer a `p_gf` clone.
- The detour opens the DB read-only and runs no pipeline steps.
- Mode-3 selection semantics remain identical to the current `p_gf` detour.
- Output keeps the same high-level flow where it still makes sense:
  - selection counts
  - rule counts
  - distribution-like summary
  - buckets
  - audit
- The new target coverage includes both:
  - income-group breakdown
  - priority-group breakdown
- The output report includes the definition / rule for each `KTP_PRIORITY_GROUP_COL` label.
- The output includes a separate section reporting:
  - `%` of selected names with `>1` countries and `>1` derived income groups
  - `%` of selected names with `>1` countries and `>1` derived priority groups
- Tests cover JSONL parsing, normalization, aggregation semantics, and read-only behavior.

---

## My interpretation of the user request (explicit)

This should be a careful retarget, not a rewrite.

The right move is:
- keep the current detour's selector logic and structure,
- preserve as much of the section flow and implementation skeleton as possible,
- and swap only the parts that are truly `p_gf`-specific.

In practice that means:
- mode-3 selection logic should barely move,
- income-group / priority-group aggregation rules should be made explicit,
- `ktp.hcr_world_bank_economies` should stay in play as the supporting country list for the multi-country divergence section,
- and the final output should feel like the same detour grew up to talk about the variables it is actually named after.
