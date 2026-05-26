## 2026-05-25

### Goal
- Fill the AI section of `SPEC.md` for the subset 5/6 design task.
- Ground the writeup in the approved prior subset 1/2 task and the pertinent code paths.

### Current plan
1. Read the new task spec and the prior task spec in full.
2. Inspect the xlsx matching and step 10 subset/partition code paths.
3. Run read-only database checks only if useful for validating impact/counts.
4. Update only the AI section of the new `SPEC.md`.
5. Re-read the edited section for lead/implementer usefulness.

### Notes
- Do not stage/unstage anything in git.
- Do not run `src.repl`.
- Treat `data/scisci_process.duckdb` as read-only if queried.

### Status
- Completed: read the new spec and the prior subset-2 spec.
- Completed: inspected `src/steps/step_07_match_xlsx.py`,
  `src/steps/step_10_build_cards.py`, `src/helpers/vars.py`,
  `src/helpers/schema.py`, and related step-10 tests.
- Completed: ran read-only DuckDB checks through `pixi run python` against
  `data/scisci_process.duckdb`.
- Completed: wrote and reviewed the AI section of `SPEC.md`.

### Findings
- The current xlsx matching row already exists for the dot/initial examples.
  The rejection happens in step 10 exactness, specifically
  `_is_exact_xlsx_match_payload()`, which compares stripped token strings
  literally.
- Best surgical design is to preserve legacy xlsx exactness for existing
  modes 1/2 and add a relaxed xlsx exactness signal for new modes 5/6.
- Proposed relaxed xlsx exactness should remove punctuation from first-name
  tokens, drop empty tokens, and compare compact non-first initials such as
  `rb` with `r b`; last-name comparison should remain the existing trimmed
  normalized equality.
- Current DB impact under that proposed relaxed rule:
  - legacy partition rows remain `31/100/100`;
  - 20 of the 31 legacy xlsx-tier rows become new relaxed subset-1 additions;
  - 11 legacy xlsx-tier rows remain xlsx-tier failures;
  - expected mode 5 count is 20 and mode 6 count is 211.

### Sciscinet spot-check requested by user
- Checked five manually reviewed OpenAlex IDs against persisted DB relations
  with author-id/fragment columns. None of the five IDs are present in the
  persisted DB relations.
- Matching code in `step_09_match_parquet.py` uses exact normalized full-name
  equality against `author_details.display_name` and alternatives, then applies
  a nonzero-hit filter before writing sciscinet output/innerdicts.
- Three examples have trailing spaces in `ktp.first_name`; current step 9 does
  not trim/collapse whitespace before building the sciscinet match key, so the
  match key contains a double space.
- Claire M Fraser exact-matched a different author ID (`A5103968663`) but that
  candidate had `ktp.ssn_sum_hit_1pct = 0` and was filtered out, leaving
  sciscinet count zero.
