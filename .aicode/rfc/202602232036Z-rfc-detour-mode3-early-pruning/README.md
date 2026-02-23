# RFC: Detour for Early Mode-3 Pruning Before SciSciNet Parquet Expansion

**Timestamp (UTC):** 2026-02-23 20:36Z  \
**Author:** GPT-5 Codex (OpenAI)

## Task summary
Document the investigation into why `config_p_gf.json` is not executable in the main REPL pipeline (step 9 disk blow-up), then capture the user's follow-up request and constraints for a new detour implementation that preserves main-pipeline behavior through step 6 and applies mode-3-style pruning earlier (starting from step 7+) to avoid downstream database explosion.

This RFC is intentionally pre-implementation and serves as a review checkpoint before any detour code is written.

## Goals
- Record the full exploration and evidence gathered for the step-9 failure and DB bloat.
- State the root-cause analysis clearly (primary vs secondary causes).
- Capture the user's detour requirements precisely and in implementation-ready detail.
- Define my interpretation of the requested detour architecture, code-copy strategy, and tests.
- Establish a clear, reviewable plan before touching detour code.

## Non-goals
- Implementing the new detour in this RFC.
- Rerunning `config_p_gf.json` in the main REPL pipeline.
- Modifying `src/repl.py` or the main step modules as part of this RFC.

---

## Context and motivation

The user attempted to run:
- `config_p_gf.json`

The run failed in step 9 (`09_match_parquet`) with:
- `IOException: ... No space left on device`

The resulting DuckDB file reached ~35 GB, which is far outside expected bounds for this workflow and unsuitable for continued use in the main REPL pipeline. The user deleted the DB file after investigation due to space pressure.

The user explicitly wants to treat this config as unexecutable in main REPL and implement a dedicated detour (detours package architecture) that keeps main behavior intact up to step 6, then applies targeted changes beginning at step 7 to avoid waiting until step 10 for subset partitioning.

---

## Investigation scope and constraints (as requested by user)

The user asked for exploration only, with no pipeline rerun and no code changes:
- Do **not** rerun the failing config in main REPL.
- It was acceptable to read:
  - the failed DB file (read-only)
  - the REPL session log
  - source code (especially step 9)
- Reflect and diagnose; do not change behavior.

The user also shared:
- failed DB path: `/Volumes/home/aicode/2026-01-02_enrich_full_df/data/scisci_process.duckdb`
- failing log path: `/Volumes/home/aicode/2026-01-02_enrich_full_df/data/diagnostics/20260223_150005/repl_session.log`

---

## Investigation log (full exploration record)

This section records the exploration performed so far, including intermediate findings and the exact evidence that led to the current diagnosis.

### 1. Confirmed file sizes and failure point from shared artifacts

Checked:
- DB file size
- REPL log size and tail
- step-9 module location

Observed:
- `scisci_process.duckdb`: `33G` on disk (`ls -lh`)
- REPL log exists and is small (~2 KB), containing the step progression and failure
- Run progresses through steps 1-8 and fails in step 9 during parquet work

Key log sequence (from shared log):
- Step 1-8 complete successfully
- Step 9 begins and logs:
  - `Match author details to name keys (author_details scan)`
  - `Create matched author_details table`
  - `Create matched authors table`
  - `Create author->paper table`
  - `Create matched paper-author-affiliation table`
  - `Create matched affiliations table`
  - `Create hits union view`
  - `Aggregate author-level hit stats`
  - `Create author-level output table`
- Then failure:
  - `IOException: ... Could not write file ".../scisci_process.duckdb": No space left on device`

Interpretation at this stage:
- Failure happens late in step 9, specifically while materializing the author-level output table.

### 2. Read-only inspection of the failed DuckDB file showed live DB content is tiny

Opened the shared DB file read-only and checked DuckDB metadata:
- `PRAGMA database_size`
- `SHOW TABLES`

Observed:
- DuckDB reported only ~`161.5 MiB` live database size (`used_blocks`-based)
- `SHOW TABLES` contained only step-8-era tables/views (e.g., population/samples/xlsx/docx outputs)
- No step-9 `ssn_*` tables persisted

Interpretation:
- The DB file grew massively during failed writes in step 9, but the step failed before the materialized step-9 objects were durably committed/live.
- The huge file size is mostly failed-write growth / non-live file bloat, not committed database contents.

### 3. File-system-level size checks confirmed the apparent contradiction

Checked OS-level file stats:
- `du -sh` on the DB file
- `stat` logical size and block counts

Observed:
- `du -sh`: still ~`33G`
- logical size reported as ~`35,437,948,928` bytes

Interpretation:
- OS-visible file size remained enormous after the failure.
- DuckDB metadata simultaneously reporting small live DB content confirms this was not “35 GB of valid persisted tables.”

### 4. Reviewed `config_p_gf.json` and confirmed this is near-full-population workload

Read:
- `config_p_gf.json`

Relevant values:
- `card_subset_mode = 3`
- `sample_draw_sizes = [20, 40, 40, 40, 40, 40, 40, 40, 59355]`
- `total_draws = 59665`

Interpretation:
- This config is effectively full-scale / near-full-population, not a normal small sample run.
- That greatly increases sensitivity to ambiguous matching in step 9.

### 5. Reviewed step 9 code (`src/steps/step_09_match_parquet.py`) to map possible blow-up points

Read step 9 in detail and identified likely expansion sites:

1. **Initial name-to-author matching (`PARQUET_AUTHOR_MATCH_TABLE`)**
   - Matches normalized `first last` name keys to `author_details.display_name` and `display_name_alternatives`
   - Uses `UNION ALL` over:
     - `unnest(display_name_alternatives)`
     - `display_name`
   - Join condition is exact normalized-name equality

2. **Large downstream joins keyed by `authorid`**
   - `ssn_author_papers`
   - matched `paper_author_affiliation`
   - these can explode if the initial match set is large/ambiguous

3. **Final author-level output join**
   - `_create_parquet_table(...)` prejoins `author_details` and `authors` to the match table (on `authorid`)
   - final output joins match table + these prejoined tables again on `authorid`
   - introduces duplication when one `authorid` matches multiple `name_key`s

Initial hypothesis (after code review, before deeper probes):
- Main driver likely huge ambiguous-name match set in `PARQUET_AUTHOR_MATCH_TABLE`
- Secondary driver likely final-output duplication due to prejoin + rejoin on `authorid`

### 6. Determined why `unaccent()` works in pipeline but not in plain ad-hoc DuckDB sessions

When running ad-hoc probes, `unaccent()` was missing in a plain DuckDB session.

Findings:
- `src/helpers/pipeline_manager.py` loads:
  - `INSTALL splink_udfs FROM community; LOAD splink_udfs;`
- In a plain ad-hoc DuckDB session:
  - `unaccent()` was unavailable
  - `strip_accents()` was available
- After loading `splink_udfs`, `unaccent()` became available for probes

Interpretation:
- Any reproduction of step-9 matching logic must account for `splink_udfs` to match pipeline behavior exactly.

### 7. Cardinality probe: quantified the initial step-9 name-to-author match explosion

Built an in-memory probe (read-only against the shared DB for `outerdict_name_keys`, scanning `author_details` parquet) that reproduced the step-9 match logic using `unaccent()`.

Measured the effective `PARQUET_AUTHOR_MATCH_TABLE` cardinality:

- `names_count`: `16,554`
- `match_rows` (`name_key x authorid` after `DISTINCT`): `216,518`
- `matched_name_keys`: `13,517`
- `matched_authorids`: `212,628`
- `max_namekeys_per_authorid`: `66`
- `max_authorids_per_namekey`: `4,432`
- `authorids_with_multiple_namekeys`: `3,720`
- `authorids_with_5plus_namekeys`: `5`
- `authorids_with_10plus_namekeys`: `1`

Top ambiguous names by matched OpenAlex author IDs (examples):
- `X. Liu` -> `4,432`
- `Yang Liu` -> `1,764`
- `Wei Zhang` -> `1,649`
- `Yu Zhang` -> `1,455`
- many additional high-collision names in the 1,000+ range

Interpretation:
- This is the primary source of blow-up. The step-9 input to downstream joins is already enormous due to exact normalized full-name collisions at full scale.

### 8. Quantified downstream join sizes caused by that match set

Materialized a temporary `matches` table in an ad-hoc DuckDB session (still read-only with respect to the shared DB file) and measured downstream join cardinalities:

- `authors_paper_rows_join` (equivalent to `ssn_author_papers` join shape): `20,296,163`
- `paper_author_affiliation_rows_join` (equivalent matched PAA join shape): `20,296,163`

Top names by downstream `authors_paper` rows (examples):
- `Wei Zhang` -> `110,384`
- `X. Zhao` -> `102,629`
- `Yang Liu` -> `102,091`
- `Wei Li` -> `95,044`
- `X. Liu` -> `92,568`
- many more in the 70k-80k range

Interpretation:
- Even before the final step-9 author-level output table, the pipeline is creating ~20.3M-row intermediates.
- This alone can drive very large temporary/materialized storage growth.

### 9. Quantified the secondary final-output duplication issue (real bug, but not the main driver)

Estimated row counts for the final author-level output join under two scenarios:
- current step-9 join shape (with prejoined `author_details` / `authors` tables that already duplicate per matched `name_key`)
- a baseline without that prejoin-induced duplication

Results:
- estimated final rows with current join shape: `528,500`
- estimated final rows without prejoin duplication: `216,518`
- extra rows from prejoin duplication: `311,982`

Interpretation:
- This is a genuine duplication bug / inefficiency in step 9.
- It contributes additional rows and bytes, but it is secondary to the ~20.3M-row expansion from ambiguous name matching.

### 10. Final diagnosis from investigation (pre-detour)

Primary cause:
- Step 9 exact-name matching on full-ish population (`config_p_gf.json`) creates a huge ambiguous `name_key x authorid` relation (`216,518` rows; some names match thousands of author IDs), which expands into ~`20.3M` row intermediates in parquet joins.

Secondary cause:
- Final author-level output join shape introduces avoidable duplication due to prejoining `author_details` and `authors` to the match table and then joining again on `authorid`.

Why the DB file hit ~35 GB:
- Step 9 was writing large materializations when disk filled.
- Failure occurred before step-9 tables became committed/live.
- DuckDB file remained huge afterward (failed-write growth not compacted automatically).

---

## Findings summary (succinct)

1. `config_p_gf.json` is effectively a near-full-population run (`total_draws = 59665`), not a small sampled workflow.
2. Main REPL step 9 is not feasible for this config under current name-matching strategy and storage behavior.
3. The dominant cost is the ambiguous-name explosion in `PARQUET_AUTHOR_MATCH_TABLE` and downstream parquet joins (~20.3M rows).
4. There is also a smaller but real duplication issue in the final author-level output join.
5. A detour that applies mode-3-style pruning earlier (before or within steps 7-9) is a reasonable direction because waiting until step 10 partitions too late.

---

## User follow-up request (captured requirements)

After the investigation, the user stated (paraphrased accurately):

- The 35 GB file was deleted due to space pressure.
- We should treat `config_p_gf.json` as unexecutable in the main REPL.
- The correct solution direction is a **detour** (not modifying main REPL behavior).
- Use the existing detours package and the `step4_breakdown` detour + its tests as the reference implementation.
- If needed, read the detours wiring RFC in `.aicode/rfc/` for philosophy and architecture.

Requested new detour behavior:
- Follow the normal pipeline **unchanged through step 6 inclusive** and build `OuterDict` as expected.
- Starting at **step 7**, implement changes corresponding to mode 3:
  - `"Exactly one sciscinet innerdict and all present ktp.xlsx_match payloads are exact"`
- Do this **early**, at DB/materialization time, instead of waiting for step 10 subset partitioning.

Strong implementation constraints from user:
- Do **not** impact main REPL (`src/repl.py`) behavior.
- Detour must be self-contained and follow the established detours approach.
- For diffability, **copy step code literally** and make only minimal meaningful changes.
- Specifically:
  - step 7 and step 9 logic should be copied into detour-local files so they can be diffed against originals
  - step 8 should be used unchanged (no detour modifications needed there)
- User explicitly wants to compare:
  - detour `step7.py` vs `src/steps/step_07_match_xlsx.py`
  - detour `step9.py` vs `src/steps/step_09_match_parquet.py`
- User also requested that I perform these diffs myself and keep overhead minimal (only meaningful changes should appear).

Requested detour package shape (allowed / preferred):
- Implement as a subpackage under `src/detours/` with:
  - `__main__.py` (orchestration / entrypoint)
  - `step7.py` (modified copy of step 7)
  - `step9.py` (modified copy of step 9)
- Step 8 must be used unchanged from main step module.

Testing requirements (user-specified):
- Add both fast and slow tests, modeled after the reference detour tests.
- Most important guarantee: logic up to and including step 6 must match main pipeline exactly.
- Create fast and slow full-scale tests for this pre-deviation identicality, same style as the reference detour.
- Slow test should **cut execution right after step 6**, then do comparisons (because steps 7+ are detour-specific and intentionally divergent).
- User does **not** want me to run the detour itself; user will run it manually.
- I **must** run both tests (fast and slow) during implementation work.

Then the user redirected scope for the current turn:
- First create an RFC in `.aicode/rfc/` documenting:
  - all exploration and findings so far
  - the user follow-up request
  - my interpretation
- Do **not** start implementing the detour yet; user will review the RFC first.

---

## My interpretation of the requested detour (implementation intent, not code yet)

This section captures how I currently understand the requested implementation. This is the portion the user asked to review before coding.

### 1. Detour purpose

Create a new detour that is safe for `config_p_gf.json`-style runs by applying mode-3-style filtering earlier than step 10, reducing step-9 parquet expansion.

This detour is an additive workflow variant and must not alter main REPL semantics or wiring.

### 2. Deviation point

Pre-deviation identicality point:
- Steps 1-6 inclusive must be behaviorally identical to main pipeline.

Detour-specific deviation begins:
- Step 7 (XLSX matching), because this is where we can begin pruning toward the mode-3 criteria
  - exact SciSciNet count condition is only fully knowable after downstream matching, but the detour can start structuring data flow for early pruning
  - exact `ktp.xlsx_match` condition is directly relevant starting in step 7

Step 8:
- Must remain unchanged (reuse main module, no detour edits)

Step 9:
- Must be copied into detour-local code and minimally modified to apply the early mode-3 logic / pruning strategy, with special care to keep the diff clean and reviewable.

### 3. Self-contained detour structure (per user direction)

I interpret the requested package layout as something like:
- `src/detours/<new_detour_name>/__main__.py`
- `src/detours/<new_detour_name>/step7.py` (copy of `step_07_match_xlsx.py` + minimal changes)
- `src/detours/<new_detour_name>/step9.py` (copy of `step_09_match_parquet.py` + minimal changes)

And likely additional local detour orchestration code in `__main__.py` to:
- set up detour-specific DB/state paths
- run main steps 1-6 from the normal step registry or direct imports
- run detour-local step 7
- run main step 8 unchanged
- run detour-local step 9
- then proceed as needed (possibly step 10+ depending on detour goal definition), but the user has not asked for final runtime semantics yet beyond the early intervention plan

### 4. Code-copy discipline (important review requirement)

The user emphasized diffability.

My interpretation:
- For detour `step7.py` and `step9.py`, I should start from near-literal copies of the main step modules.
- Changes should be narrowly scoped and obvious.
- Before presenting implementation, I should run explicit diffs:
  - detour `step7.py` vs main `step_07_match_xlsx.py`
  - detour `step9.py` vs main `step_09_match_parquet.py`
- If the diffs show incidental churn (formatting noise, import reordering beyond necessity, unrelated edits), that is a failure against the requested standard.

### 5. Test strategy interpretation (fast + slow, pre-deviation through step 6)

I interpret the requested tests as mirroring the reference detour pattern, but with a different declared deviation point:
- `STEPS_TO_DEVIATION = [steps 1..6]`

Fast test(s):
- in-repo synthetic/minimal config
- compare main vs detour DB objects and artifact hashes step-by-step through step 6
- verify isolation (no `src/cli.py` coupling, separate DB/state)
- verify detour entrypoint contract if applicable

Slow test(s):
- real config resources (skip if unavailable), similar to the reference `@pytest.mark.slow` pattern
- compare main vs detour snapshots through step 6 only
- explicitly stop before step 7 detour-specific logic for equivalence checks

Important nuance from user:
- The slow test should cut right after step 6 and then compare, rather than running into detour-specific logic.

### 6. What I will *not* do in the detour implementation (per current interpretation)

- No changes to `src/repl.py`
- No “detour registry” or centralized dispatcher
- No coupling from detour to other detours
- No silent modification of main step modules
- No running the detour end-to-end during implementation validation (user will run it)

---

## Proposed implementation plan (deferred until RFC approval)

This is a planned sequence only. No implementation work is included in this RFC.

1. Review `src/detours` reference implementation (`detour_step4_breakdown`) and tests in detail and clone the structure/style for a new detour package.
2. Create a new detour subpackage with `__main__.py`, `step7.py`, and `step9.py` (and only minimal additional local modules if absolutely necessary).
3. In `__main__.py`, implement self-contained orchestration with dedicated detour DB/state paths and explicit step execution.
4. Ensure steps 1-6 use main pipeline logic unchanged and remain strictly identical to main flow.
5. Copy `step_07_match_xlsx.py` into detour `step7.py`; apply only the mode-3-related early-pruning changes required.
6. Reuse main step 8 unchanged.
7. Copy `step_09_match_parquet.py` into detour `step9.py`; apply only the mode-3-related early-pruning changes required (and any directly necessary guardrails for storage explosion avoidance).
8. Add a new detour test module modeled after `tests/test_detour_step4_breakdown.py` with:
   - fast pre-deviation identicality through step 6
   - slow real-config pre-deviation identicality through step 6 (cut after step 6)
   - isolation checks
   - entrypoint/contract checks as appropriate
9. Run the required tests (fast + slow) and project checks; do not run the detour itself unless user later asks.
10. Produce self-diffs for detour step7/step9 against main step modules and verify minimal change surface.

---

## Risks and considerations for the upcoming implementation

- **Risk: accidental behavior drift before step 6**
  - Mitigation: strict pre-deviation DB-object and artifact-hash comparisons (fast + slow), modeled on reference detour tests.

- **Risk: excessive changes in copied step 7/step 9 code**
  - Mitigation: literal copy-first approach and explicit diff review against main step modules.

- **Risk: unclear exact insertion point for mode-3 pruning**
  - Mitigation: keep RFC-approved interpretation explicit; implement smallest viable early-pruning hook and preserve observability.

- **Risk: detour-specific logic leaks into main pipeline**
  - Mitigation: confine all changes to new detour subpackage and tests only.

---

## Acceptance criteria for this RFC checkpoint

- A new RFC exists under `.aicode/rfc/` in the established format.
- The RFC records the full investigation findings and supporting evidence (including quantified row-explosion metrics).
- The RFC captures the user's follow-up requirements and constraints for the new detour.
- The RFC states a clear interpretation and implementation plan without writing detour code yet.

---

## Notes for review

This RFC intentionally front-loads the investigation evidence because the detour design is motivated by a very specific failure mode:
- exact-name matching ambiguity at full scale causes massive step-9 parquet expansion
- partitioning in step 10 happens too late to prevent that cost

If the user approves this RFC framing, the next step is detour implementation only (not more main-pipeline changes).
