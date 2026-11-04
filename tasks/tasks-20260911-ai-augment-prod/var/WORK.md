# Dashboard snapshot authority — 2026-10-30

The Human Operator closed this rollout after the detour branch was merged and production release batch 9 was released. Further changes belong to separate tasks. This WORK file has no active action list.

## Completion evidence

- Git commit `3200cf0` merged PR #21 (`aicode/feat/detour-ai-augment`); it is in the current branch's history.
- Commit `e703156` enabled subset 9 in the released ground-truth cohort rule, which remains present in `protected/src/backend/helpers/vars.py`.
- Commits `7efb8ff` and `6b9b0a2` on `origin/aicode/staging` document the 2026-11-02 production runs in the detour README. The final dashboard status is 307 total researchers, 11 completed, 0 failed, 0 queued; the README also records output exports and a successful replay into a throwaway database. Alan C. Evans had an earlier failed run and completed on rerun. These two reporting commits are not ancestors of the current checkout (`aicode/fix/openalex-v1-regression`).
- The Operator confirms that batch 9 was released. Git and the README corroborate the merge, cohort configuration, recorded production run, and export procedure; they do not independently verify external distribution of the released artifacts.

## Findings handed off outside this closed task

- Alan's earlier failure came from a captured web-output citation `turn4search7` with no matching structured `web_search_end` result; replay faithfully reproduces that rejection. The later run completed. Any tool-output or validator-policy change is separate work.
- Accepted age values mix current biological age, years since first publication, and full-field `NR`. Edward T Furlong chose `NR` as his first standardized age despite a cited 1982 publication; there was no failed computed-age submission. Hideo Ohno's birth month/day, not his whole standardized age, were `NR`. Future semantic/schema and review decisions are separate work.
- The fresh-instance procedure in the production-run README still uses internet access and reuses heavy pipeline artifacts; it does not establish fully offline reproduction. The numeric v1 OpenAlex paper-title log regression also remains separate work.
- Exact-evidence acceptance is not factual agreement with manual extraction. Previously noted education and source-quality discrepancies require separate adjudication if pursued.

## Closeout housekeeping

The human-authored `src/TASK.md` was not edited. Git was used read-only. No pipeline, detour, production command, or test was run for this closeout; the work was repository/history/README review and this WORK update. No changes to production logic were made here.
