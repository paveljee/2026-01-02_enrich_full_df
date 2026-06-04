## human written - ai never touches this
### prerequisites and setup
See prerequisites and setup in
`tasks/tasks-20260519-review-231/SPEC.md`

Use `./WORK.md` as
your own workbook for
recording actions you have in mind and
recording in progress and completed, or
any other notes you feel you need.
Write as if for a
busy tech lead and
also to be helpful for the executor, so
lean concise text that 
contains all relevant info inplace but is
focused and very well organized.

### actual task
wire into step 9
`KTP_SSN_TOP_OLDEST_PAPERS_COL`
that has already been added to `vars.py`.
It uses the new
papers parquet
(already added to `config.repl.json`),
registered routinely.
It uses `TOP_K_WORKS`.

Here is how it should
look like in final card
(works should be sorted
ascending by year):

```
**ktp.ssn_top_oldest_papers**: [{"ssnp.year":...,"ktp.ssnp_paperid_url":"https://openalex.org/W1568216332"}, ...]
```

all relevant
manipulations with
paper parquet
should be properly logged
in `repl_session.log`.

## how ai understood the spec

### scope

Add a step-9 SSN enrichment column named by
`KTP_SSN_TOP_OLDEST_PAPERS_COL`
(`ktp.ssn_top_oldest_papers`) so each effective SciSciNet/OpenAlex
author innerdict can show up to `TOP_K_WORKS` oldest papers in the final
card.

The final card should print the new value naturally through the existing
card renderer, e.g.

```text
**ktp.ssn_top_oldest_papers**: [{"ssnp.year":1903,"ktp.ssnp_paperid_url":"https://openalex.org/W1568216332"}, ...]
```

No new card-rendering path is needed unless the implementation
accidentally excludes the column. `build_cards()` already emits ordinary
innerdict fields that are not in step 10's `excluded_cols`.

### prerequisite guidance and rules reviewed

This task inherits its setup rules from
`tasks/tasks-20260519-review-231/SPEC.md`. I reviewed those rules as
operating constraints, not as optional background:

- Understand the code path behind
  `pixi run python -m src.repl --config config.repl.json --new`, but do
  not run that command and do not use `src.repl` directly. For this
  SPEC-fill pass I read the relevant code path instead:
  `src/repl.py`, `src/helpers/init.py`, `src/helpers/pipeline_manager.py`,
  `src/helpers/repl_runtime.py`, `src/steps/step_01_register_resources.py`,
  `src/steps/step_09_match_parquet.py`, and
  `src/steps/step_10_build_cards.py`.
- If persisted pipeline data has to be checked, use only
  `data/scisci_process.duckdb` and only in read-only mode. Do not browse
  other `data/` or `.aicode/` artifacts. For this pass I did not inspect
  the DB or data files because code/config context was sufficient to fill
  the SPEC.
- Repo code, config, and tests may be reviewed as needed. I specifically
  reviewed `config.repl.json`, `src/helpers/vars.py`,
  `src/helpers/resources.py`, `src/helpers/config.py`,
  `src/helpers/schema.py`, `src/helpers/parquet_utils.py`,
  `src/helpers/cards.py`, and nearby tests for config/resource, card, and
  SSN behavior.
- Code edits for the eventual implementation should happen only after
  the executor has enough context. This pass only edits the AI-owned SPEC
  section and the task workbook.
- Git usage is read-only under the linked prerequisite. I used only
  read-only status/diff inspection and did not stage, unstage, reset, or
  checkout anything.
- The task asks to use `./WORK.md` as a concise workbook for a busy tech
  lead and later executor; I updated it with the context reviewed and the
  local `apply_patch` workaround used.

I also followed relevant references beyond the prerequisite header:
the older SPEC's step-10 subset/card discussion explains why current
card output is driven by effective innerdict rows, and
`tasks/tasks-20260526-match-patch/SPEC.md` documents the SSN hit v2 and
OpenAlex selection flow. Those references matter here because oldest
papers must be computed from `PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW`,
not from raw pre-selection SSN candidates.

### reviewed context

- The linked setup/spec in `tasks/tasks-20260519-review-231/SPEC.md`
  says not to run `src.repl`; I did not use it. The relevant code path is
  the normal pipeline ending in step 9 and step 10.
- `config.repl.json` already contains a `files_config.papers` entry for
  `sciscinet_papers.parquet`.
- `src/helpers/vars.py` already contains
  `KTP_SSN_TOP_OLDEST_PAPERS_COL = "ktp.ssn_top_oldest_papers"` and
  `TOP_K_WORKS = 5`.
- Step 9 currently builds effective SSN author rows after name matching,
  nonzero-hit filtering, SSN hit v2 selection, and the OpenAlex
  confidence gate. Existing top-paper output
  `ktp.ssn_top_papers_hit_1pct` is computed in the final
  `ssn_innerdicts` CTE from those effective author rows.
- Step 10/cards should not need semantic changes for this task.

One repo-context mismatch to resolve during implementation:
although the config has `papers`, the current resource validation and
registration path does not yet include it. To make the human premise
"registered routinely" true in code, add `papers` to the required
files/config/resource registration flow.

### data semantics

Use the same effective SSN author population as the rest of step 9:
`PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW` joined through
`PARQUET_AUTHOR_PAPERS_TABLE`. Do not compute oldest papers from
pre-selection SSN candidates, because that would disagree with the
author rows that become card innerdicts.

Candidate papers for one card row are:

```text
name_key + selected authorid
  -> ssn_author_papers.paperid
  -> papers parquet paperid/year metadata
```

The paper parquet should be normalized with prefix `ssnp`, so the year
field used in the payload is `ssnp.year`. The URL field in the JSON
payload should be `ktp.ssnp_paperid_url`, built as
`https://openalex.org/` plus the SciSciNet/OpenAlex work id.

Ranking should be deterministic:

```text
PARTITION BY name_key, authorid
ORDER BY ssnp.year ASC, paperid ASC
keep rn <= TOP_K_WORKS
```

Only rows with a non-null paper id and a non-null year should contribute
to "oldest" papers. If an author has fewer than `TOP_K_WORKS` dated
papers, return fewer. If there are none, leave
`ktp.ssn_top_oldest_papers` null/empty rather than fabricating an
undated oldest-paper record.

The JSON/list ordering must be ascending by year in the stored string,
not just in an intermediate CTE.

### implementation notes

Expected touchpoints:

- `src/helpers/vars.py`
  - add `papers` to `REQUIRED_FILES_CONFIG_KEYS`;
  - export `KTP_SSN_TOP_OLDEST_PAPERS_COL` in `__all__`;
  - consider adding centralized labels for `ssnp.filename`,
    `ssnp.year`, and `ktp.ssnp_paperid_url` rather than scattering
    string literals.
- `src/helpers/resources.py`
  - register the configured `papers` parquet as a `SCISCINET_HF`
    parquet resource, likely with `FragmentType.PAPER_ID`;
  - step 01's resource table will then include it through the existing
    resource-frame path.
- `src/steps/step_09_match_parquet.py`
  - read `papers_path = files["papers"]["path"]`;
  - include the papers filename in the parquet provenance payload;
  - materialize or otherwise explicitly join a filtered papers relation
    for only selected author papers;
  - build a `top_oldest_papers` CTE beside the existing `top_papers`,
    then left join it into `enriched`;
  - select the result as `"ktp.ssn_top_oldest_papers"`.

A suitable DuckDB expression shape is:

```sql
CAST(
    LIST(
        json_object(
            'ssnp.year', CAST(year AS BIGINT),
            'ktp.ssnp_paperid_url',
            'https://openalex.org/' || CAST(paperid AS VARCHAR)
        )
        ORDER BY year ASC, paperid ASC
    ) FILTER (WHERE rn <= TOP_K_WORKS)
    AS VARCHAR
) AS "ktp.ssn_top_oldest_papers"
```

Use the actual normalized paperid/year column names in code.

### logging contract

All paper-parquet manipulations should go through the existing step-9
`log_tag()`/`context.log` path so they land in `repl_session.log`.
Log at least:

- that the papers parquet is being filtered/joined;
- the count of matched paper metadata rows and distinct papers;
- dated-paper coverage, if cheaply available;
- the top-`TOP_K_WORKS` oldest-paper reduction count, analogous to the
  existing top-paper and top-institution reduction diagnostics.

Use the existing log tags (`TABLE/PARQUET`, `TABLE/EFF`,
`TABLE/INNERDICT`) consistently with the nearby step-9 blocks.

### tests to add or update

Add focused tests that do not require the real SciSciNet parquet files:

- config/resource tests should expect `papers` as a required registered
  parquet resource;
- a tiny DuckDB/parquet fixture should verify oldest-paper ranking by
  ascending year, paperid tie-break, `TOP_K_WORKS` truncation, OpenAlex
  work URL construction, and omission of null-year papers;
- card output should include `ktp.ssn_top_oldest_papers` when present on
  an innerdict;
- existing step-10 partition/card tests should keep passing without
  changes to subset semantics.
