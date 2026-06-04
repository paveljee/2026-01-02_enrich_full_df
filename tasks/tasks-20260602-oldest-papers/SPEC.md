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
ascending by date;
break ties by
sorting by paperid,
ascending):

```
**ktp.ssn_top_oldest_papers**: [{"ssnp.date":...,"openalex.title":"...","ktp.ssnp_paperid_url":"https://openalex.org/W1568216332"}, ...]
```

all relevant
manipulations with
paper parquet
should be properly logged
in `repl_session.log`.

"openalex.title"
should be fetched from OpenAlex,
reusing the whole same mechanism
currently used for
`openalex_author_search_log.jsonl`,
except that a separate file log is used.
Everything else is handled identically,
like RegisteredResouce, reuse of data, etc.
query to use:
`api.openalex.org/works/{paperid}?select=title&per_page=1&api_key=REDACTED"`

also,
as long as we are adding titles here,
let's also wire in titles for
top works.

## how ai understood the spec

### scope

Add a step-9 SSN enrichment column named by
`KTP_SSN_TOP_OLDEST_PAPERS_COL`
(`ktp.ssn_top_oldest_papers`) so each effective SciSciNet/OpenAlex
author innerdict can show up to `TOP_K_WORKS` oldest papers in the final
card. Since the task now fetches OpenAlex work titles, also enrich the
existing top-works output `ktp.ssn_top_papers_hit_1pct` with those same
work titles.

The final card should print the new value naturally through the existing
card renderer, e.g.

```text
**ktp.ssn_top_oldest_papers**: [{"ssnp.date":"1903-05-17","openalex.title":"...","ktp.ssnp_paperid_url":"https://openalex.org/W1568216332"}, ...]
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

The new title lookup should mirror the existing
`openalex_author_search_log.jsonl` machinery in `src/helpers/openalex.py`:
use a JSONL request log/cache with redacted API keys, reuse matching
records before network, append complete response metadata after network,
and represent the log as a registered pipeline-artifact resource. It
should be a separate log file/resource from the author-search log. The
same work-title lookup/cache should serve both `ktp.ssn_top_oldest_papers`
and `ktp.ssn_top_papers_hit_1pct`.

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
  -> papers parquet paperid/date metadata
```

The paper parquet should be normalized with prefix `ssnp`, so the full
date field used in the payload is `ssnp.date`. Date replaces the
earlier year-only idea outright: do not emit a year-only payload field,
do not add a fallback to year, and do not retain an `ssnp.year`/
`SSNP_YEAR_COL` compatibility path. Year-only ordering is too coarse and
makes within-year order fuzzy.

The JSON payload for each oldest paper should include:

```text
ssnp.date
openalex.title
ktp.ssnp_paperid_url
```

The URL field should be built as `https://openalex.org/` plus the
SciSciNet/OpenAlex work id. The title field should be fetched from
OpenAlex work metadata for the same work id, using the separate JSONL
request-cache/log resource described above. Title lookup should enrich
the already-ranked oldest papers; it must not alter paper ranking or
drop a paper that otherwise qualifies. If OpenAlex has no usable title
for a qualifying paper, keep the paper row and leave the title null/empty
rather than replacing the paper.

Ranking should be deterministic:

```text
PARTITION BY name_key, authorid
ORDER BY ssnp.date ASC, paperid ASC
keep rn <= TOP_K_WORKS
```

Only rows with a non-null paper id and a non-null date should contribute
to "oldest" papers. If an author has fewer than `TOP_K_WORKS` dated
papers, return fewer. If there are none, leave
`ktp.ssn_top_oldest_papers` null/empty rather than fabricating an
undated oldest-paper record.

The JSON/list ordering must be ascending by full date in the stored
string, not just in an intermediate CTE. Break equal-date ties by
paperid ascending for deterministic output.

The existing `ktp.ssn_top_papers_hit_1pct` top-works field should keep
its current candidate population and ranking semantics: selected author
papers ordered by `hit_1pct` descending, then paperid ascending, capped
at `TOP_K_WORKS`. The change for that field is title enrichment, not a
ranking change. Its entries should include the OpenAlex title and
OpenAlex work URL using the same title lookup/cache used for oldest
papers.

### implementation notes

Expected touchpoints:

- `src/helpers/vars.py`
  - add `papers` to `REQUIRED_FILES_CONFIG_KEYS`;
  - add a required config key/path/schema-version constant for the
    separate OpenAlex work-title JSONL log;
  - export `KTP_SSN_TOP_OLDEST_PAPERS_COL` in `__all__`;
  - add/use centralized labels for `ssnp.filename`, `ssnp.date`, and
    `ktp.ssnp_paperid_url` rather than scattering string literals;
  - add/use a centralized label for `openalex.title`;
  - use a date constant such as `SSNP_DATE_COL`, not `SSNP_YEAR_COL`.
- `src/helpers/resources.py`
  - register the configured `papers` parquet as a `SCISCINET_HF`
    parquet resource, likely with `FragmentType.PAPER_ID`;
  - validate/register the separate OpenAlex work-title JSONL log the
    same way the author-search JSONL log is validated/registered, as a
    writable `KTP_PIPELINE_ARTIFACT` resource;
  - step 01's resource table will then include it through the existing
    resource-frame path.
- `src/helpers/openalex.py`
  - add a work-title fetch/reuse helper parallel to
    `check_openalex_author()`, using the same request-log shape,
    redaction, cache-first behavior, request timing, and JSONL append
    semantics;
  - use `GET api.openalex.org/works/{paperid}` with query parameters
    `select=title`, `per_page=1`, and `api_key=...`; the persisted log
    should store the redacted query, just like the author-search log;
  - fetch only the needed OpenAlex work record/title, not a broader
    search result set.
- `src/steps/step_09_match_parquet.py`
  - read `papers_path = files["papers"]["path"]`;
  - include the papers filename in the parquet provenance payload;
  - materialize or otherwise explicitly join a filtered papers relation
    for only selected author papers;
  - build a `top_oldest_papers` CTE beside the existing `top_papers`,
    then left join it into `enriched`;
  - fetch/reuse OpenAlex titles only for distinct paper ids that survive
    either the top-oldest selection or the existing top-works selection,
    store those titles in a small relation, and join them into both JSON
    outputs;
  - enrich `ktp.ssn_top_papers_hit_1pct` with titles while preserving its
    existing hit-count-descending/paperid-ascending ordering;
  - select the result as `"ktp.ssn_top_oldest_papers"`.

A suitable DuckDB expression shape is:

```sql
CAST(
    LIST(
        json_object(
            'ssnp.date', CAST(date_value AS VARCHAR),
            'openalex.title', title,
            'ktp.ssnp_paperid_url',
            'https://openalex.org/' || CAST(paperid AS VARCHAR)
        )
        ORDER BY date_value ASC, paperid ASC
    ) FILTER (WHERE rn <= TOP_K_WORKS)
    AS VARCHAR
) AS "ktp.ssn_top_oldest_papers"
```

Use the actual normalized paperid/date column names in code, and use a
sortable date value for ordering. Do not add a year fallback.

For `ktp.ssn_top_papers_hit_1pct`, use the same title field label
(`openalex.title`) and URL field label (`ktp.ssnp_paperid_url`)
inside each top-work entry, but order by the existing top-works ranking,
not by date.

### logging contract

All paper-parquet manipulations should go through the existing step-9
`log_tag()`/`context.log` path so they land in `repl_session.log`.
Log at least:

- that the papers parquet is being filtered/joined;
- the count of matched paper metadata rows and distinct papers;
- dated-paper coverage, if cheaply available;
- the top-`TOP_K_WORKS` oldest-paper reduction count, analogous to the
  existing top-paper and top-institution reduction diagnostics;
- OpenAlex work-title lookup counts, including distinct paper ids across
  both oldest papers and top works, reused records, fetched records,
  successful titles, and missing/failed titles.

Use the existing log tags (`TABLE/PARQUET`, `TABLE/EFF`,
`TABLE/INNERDICT`) consistently with the nearby step-9 blocks.

### tests to add or update

Add focused tests that do not require the real SciSciNet parquet files:

- config/resource tests should expect `papers` as a required registered
  parquet resource;
- config/resource tests should expect the separate OpenAlex work-title
  JSONL log as a required writable registered pipeline-artifact resource;
- a tiny DuckDB/parquet fixture should verify oldest-paper ranking by
  ascending full date, paperid tie-break, `TOP_K_WORKS` truncation,
  OpenAlex work URL construction, and omission of null-date papers;
- top-works tests should verify title enrichment without changing the
  existing hit-count-descending/paperid-ascending ordering;
- OpenAlex title tests should cover JSONL cache reuse, append-on-fetch,
  title parsing from a work response, and no network request when a
  matching cached work record exists;
- card output should include `ktp.ssn_top_oldest_papers` when present on
  an innerdict;
- existing step-10 partition/card tests should keep passing without
  changes to subset semantics.
