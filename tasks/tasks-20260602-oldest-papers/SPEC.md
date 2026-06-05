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
`api.openalex.org/works?filter=openalex_id:W2188173826|W2085049191&select=title&per_page=100&api_key=REDACTED"`.

Note that the
query retrieves in batches
for faster processing.
From [OpenAlex docs][openalex-recipes]:

> Use the OR operator (`|`) to fetch up to 100 IDs at once

Also,
from "Python example" (ibid.);
note that
`per_page=100` is max allowed:

```
import requests

def get_works(filter_str, per_page=100):
    """Fetch works with pagination."""
    url = "https://api.openalex.org/works"
    params = {
        "filter": filter_str,
        "per_page": per_page,
        "cursor": "*",
        "api_key": "YOUR_KEY"
    }

    all_works = []
    while True:
        response = requests.get(url, params=params).json()
        all_works.extend(response["results"])

        cursor = response["meta"].get("next_cursor")
        if not cursor:
            break
        params["cursor"] = cursor

    return all_works
```

Reuse also must happen in batch;
to that end
we must dump to a parquet;
wire it in as a
proper RegisteredResource,
mirror how we did with
ktp unnest parquet.
parquet, 
in its footer metadata,
must contain a hash of jsonlines files
(reuse logic from ktp unnest also);
if it matches then reuse parquet,
after reuse of parquet
check if any missing titles,
if yes then append to jsonl
(using logic we have) and
recreate parquet
(with updated hash in footer).
And so ultimately,
we **never** retrieve titles from jsonl;
instead we always retrieve from parquet.
so basically we use CQRS here.

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
card. Since the task fetches OpenAlex work titles, also enrich
`ktp.ssn_top_papers_hit_1pct` with those same work titles.

The final card should print the new value naturally through the card
renderer, e.g.

```text
**ktp.ssn_top_oldest_papers**: [{"ssnp.date":"1903-05-17","openalex.title":"...","ktp.ssnp_paperid_url":"https://openalex.org/W1568216332"}, ...]
```

No new card-rendering path is needed unless the implementation
accidentally excludes the column. `build_cards()` already emits ordinary
innerdict fields that are not in step 10's `excluded_cols`.

Title retrieval/cache shape: OpenAlex work titles must not be fetched
one paper at a time, and normal step-9 title lookup must not read titles
from JSONL records. The JSONL file is the request/response log and
rebuild source; the reusable lookup artifact is a parquet table
registered as a pipeline resource.

### prerequisite guidance and rules reviewed

This task inherits its setup rules from
`tasks/tasks-20260519-review-231/SPEC.md`. Treat those rules as
operating constraints, not as optional background:

- Understand the code path behind
  `pixi run python -m src.repl --config config.repl.json --new`, but do
  not run that command and do not use `src.repl` directly. Relevant code
  path:
  `src/repl.py`, `src/helpers/init.py`, `src/helpers/pipeline_manager.py`,
  `src/helpers/repl_runtime.py`, `src/steps/step_01_register_resources.py`,
  `src/steps/step_09_match_parquet.py`, and
  `src/steps/step_10_build_cards.py`.
- If persisted pipeline data has to be checked, use only
  `data/scisci_process.duckdb` and only in read-only mode. Do not browse
  other `data/` or `.aicode/` artifacts. No DB/data inspection is needed
  for this SPEC because code/config context is sufficient.
- Repo code, config, and tests may be reviewed as needed. Relevant repo
  context includes `config.repl.json`, `src/helpers/vars.py`,
  `src/helpers/resources.py`, `src/helpers/config.py`,
  `src/helpers/schema.py`, `src/helpers/parquet_utils.py`,
  `src/helpers/cards.py`, and nearby tests for config/resource, card, and
  SSN behavior.
- Code edits for the eventual implementation should happen only after
  the executor has enough context.
- Git usage is read-only under the linked prerequisite: do not stage,
  unstage, reset, or checkout anything.
- Use `./WORK.md` as a concise workbook for a busy tech lead and later
  executor.

Relevant linked context: the older SPEC's step-10 subset/card discussion
explains why card output is driven by effective innerdict rows, and
`tasks/tasks-20260526-match-patch/SPEC.md` documents the SSN hit v2 and
OpenAlex selection flow. Therefore oldest papers must be computed from
`PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW`, not from raw pre-selection SSN
candidates.

OpenAlex batch requirement: call
`/works?filter=openalex_id:W...|W...&select=title&per_page=100` with at
most 100 IDs per request. The quoted recipe and query in the human
section are the relevant requirements.

### implementation context

- `config.repl.json` provides `files_config.papers` for
  `sciscinet_papers.parquet`.
- Use `KTP_SSN_TOP_OLDEST_PAPERS_COL = "ktp.ssn_top_oldest_papers"` and
  `TOP_K_WORKS = 5` from `src/helpers/vars.py`.
- Step 9 should use effective SSN author rows after name matching,
  nonzero-hit filtering, SSN hit v2 selection, and the OpenAlex
  confidence gate. Top-paper output
  `ktp.ssn_top_papers_hit_1pct` is computed in the final
  `ssn_innerdicts` CTE from those effective author rows.
- The two reductions are independent: top works use selected author
  papers ordered by `hit_1pct DESC, paperid ASC`, while oldest papers use
  selected author papers joined to dated paper metadata ordered by
  `ssnp.date ASC, paperid ASC`.
- OpenAlex work-title fetching should use the same strict HTTP
  request-log schema as OpenAlex author search for batch interactions.
- The author-details unnest resource establishes the parquet-artifact
  pattern to mirror: optional configured artifact, default output path,
  parquet footer metadata via DuckDB `KV_METADATA`, validation on reuse,
  registration as `ResourceGroup.KTP_PIPELINE_ARTIFACT`, and
  `parquet_kv_metadata()` tests.
- Step 10/cards should not need semantic changes for this task.

Required resources:

- `papers` is a required and registered parquet resource.
- `openalex_paper_title_log.jsonl` is a registered writable JSONL request
  log resource.
- Add a separate OpenAlex paper-title parquet resource. This parquet, not
  the JSONL, is the reusable source that Step 9 reads for titles.

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
OpenAlex work metadata for the same work id. Title lookup should enrich
the already-ranked top-oldest/top-work papers; it must not alter either
paper ranking or drop a paper that otherwise qualifies. If OpenAlex has
no usable title for a qualifying paper, keep the paper row and leave the
title null/empty rather than replacing the paper.

Oldest-paper ranking should be deterministic:

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

The `ktp.ssn_top_papers_hit_1pct` top-works field should keep its
candidate population and ranking semantics: selected author
papers ordered by `hit_1pct` descending, then paperid ascending, capped
at `TOP_K_WORKS`. The change for that field is title enrichment, not a
ranking change. Its entries should include the OpenAlex title and
OpenAlex work URL using the same title lookup/cache used for oldest
papers.

Before any OpenAlex title work happens, Step 9 must derive the distinct
paper IDs that survive either of these two reductions:

```text
top-work IDs:   selected author papers ranked by hit_1pct DESC, paperid ASC, rn <= TOP_K_WORKS
top-oldest IDs: selected dated author papers ranked by ssnp.date ASC, paperid ASC, rn <= TOP_K_WORKS
needed title IDs = DISTINCT(top-work IDs UNION ALL top-oldest IDs)
```

Do not request titles for every selected author paper. The title parquet
should only need rows for `needed title IDs`.

### title cache and OpenAlex batching

The title cache has two layers with distinct responsibilities:

This is a CQRS-style split: the JSONL request log is the append-only
command/event history, and the title parquet is the query-side read model
used by Step 9.

- JSONL request log: append-only HTTP request/response records, redacted
  API keys, complete response metadata, same strict schema as author
  search (`KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION = 1`). This log records
  batch interactions with OpenAlex. It is not the normal lookup table for
  Step 9 joins.
- Title parquet: one row per OpenAlex work id/paper id needed by Step 9,
  with at least `paperid` and `openalex.title`. This parquet is what Step
  9 reads to join titles into both JSON payloads.

Reuse must happen at the parquet layer:

1. Compute the SHA-256 hash of the title JSONL log.
2. If the title parquet exists and its footer metadata contains the same
   JSONL hash, register/reuse it.
3. Read titles from the parquet and compare its paper IDs with the
   current `needed title IDs`.
4. If any needed paper IDs are absent from the parquet, request only
   those missing IDs from OpenAlex in batches of at most 100 IDs, append
   each batch response to the JSONL request log, then rebuild the title
   parquet from the updated JSONL and stamp the new JSONL hash into the
   parquet footer metadata.
5. After any rebuild, Step 9 reads titles from the parquet, never by
   looking up individual titles in JSONL records.

When rebuilding the parquet from JSONL, parse batch request records:

- request path should be `/works`;
- query should include `filter=openalex_id:W1|W2|...`, `select=title`,
  `per_page=100`, and a redacted `api_key` in the persisted record;
- response body should be parsed from the OpenAlex works-list shape,
  using `results[*].id` to map each returned work to its `W...` id and
  `results[*].title` for `openalex.title`;
- every requested id in a logged batch should be represented in the
  rebuilt parquet. If OpenAlex does not return a usable title for an id,
  keep a row with NULL title so Step 9 does not repeatedly refetch the
  same permanently missing title on every run.

If a paper ID appears in multiple JSONL batch records, use the latest
record by `received_at_unix_usec`/log order when rebuilding the parquet.
That keeps append-only refreshes deterministic.

### implementation notes

Expected touchpoints:

- `src/helpers/vars.py`
  - include `papers` in `REQUIRED_FILES_CONFIG_KEYS`;
  - define a config key/path constant for the OpenAlex work-title JSONL
    request log;
  - add a key/default path constant for the generated OpenAlex
    paper-title parquet, e.g. `OPENALEX_PAPER_TITLE_PARQUET_KEY` and a
    default under `config.output_dir`;
  - add parquet metadata key constants, including a JSONL-log SHA-256 key
    such as `OPENALEX_PAPER_TITLE_LOG_SHA256_METADATA_KEY` and, if useful,
    a schema-version key for the title parquet;
  - use one generic HTTP-request JSONL schema/model,
    `KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION = 1` with a helper under
    `src/helpers/data_models/http_request_log.py`, for both the
    author-search log and paper-title batch log rather than
    author-specific or title-specific schema constants;
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
  - add an `openalex_paper_title_parquet_resource` to `PipelineResources`;
  - implement an author-details-unnest-like ensure function for the title
    parquet: check configured artifact if present, otherwise default
    output path, validate footer metadata against the JSONL hash, reuse
    when valid, create/recreate when missing or stale, register as
    `ResourceGroup.KTP_PIPELINE_ARTIFACT` with `FragmentType.PAPER_ID`;
  - step 01's resource table and step 10's resource filename accounting
    should include both the JSONL log and title parquet resources.
- `src/helpers/openalex.py`
  - provide step-9 work-title fetching through batch requests;
  - add a batch title query builder using
    `GET https://api.openalex.org/works?filter=openalex_id:W1|W2|...&select=title&per_page=100&api_key=...`;
  - chunk missing paper IDs into batches of at most 100;
  - append one strict HTTP request-log record per batch request, with the
    query redacted before persisting;
  - add parsing helpers that turn batch JSONL records into paper-title
    rows for parquet rebuilds;
  - do not use JSONL as the normal title cache lookup during step 9.
- `src/steps/step_09_match_parquet.py`
  - read `papers_path = files["papers"]["path"]`;
  - include the papers filename in the parquet provenance payload;
  - materialize or otherwise explicitly join a filtered papers relation
    for only selected author papers;
  - build a `top_oldest_papers` CTE beside `top_papers`,
    then left join it into `enriched`;
  - after the top-work and top-oldest reductions are defined, materialize
    the distinct `needed title IDs` that survive either reduction;
  - ensure/rebuild the OpenAlex paper-title parquet for those IDs;
  - load a small title relation from the title parquet filtered to the
    needed IDs and join it into both JSON outputs;
  - enrich `ktp.ssn_top_papers_hit_1pct` with titles while preserving its
    hit-count-descending/paperid-ascending ordering;
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
inside each top-work entry, but order by the top-works ranking, not by
date.

The title parquet itself can be a narrow table, for example:

```text
paperid VARCHAR
openalex.title VARCHAR NULL
```

Extra audit columns such as response code or received timestamp are OK if
useful, but Step 9 should only depend on paper id and title.

### logging contract

All paper-parquet manipulations should go through the step-9
`log_tag()`/`context.log` path so they land in `repl_session.log`.
Log at least:

- that the papers parquet is being filtered/joined;
- the count of matched paper metadata rows and distinct papers;
- dated-paper coverage, if cheaply available;
- the top-`TOP_K_WORKS` oldest-paper reduction count, analogous to the
  top-paper and top-institution reduction diagnostics;
- the distinct title-needed paper ID count across both top-work and
  top-oldest reductions;
- title parquet cache status: configured/default path, JSONL hash found
  in parquet metadata, current JSONL hash, reused vs rebuilt;
- missing-title ID count after parquet reuse;
- OpenAlex batch request counts: number of batches, ids per batch,
  fetched batch records, HTTP status, successful returned titles, and
  missing/null titles;
- final title parquet row count and non-null title coverage.

Use the step-9 log tags (`TABLE/PARQUET`, `TABLE/EFF`,
`TABLE/INNERDICT`) consistently with the nearby step-9 blocks.

Do not log one line per paper as a substitute for batching. Log every
OpenAlex HTTP interaction, meaning every batch request, plus aggregate
paper/title coverage.

### tests to add or update

Add focused tests that do not require the real SciSciNet parquet files:

- config/resource tests should expect `papers` as a required registered
  parquet resource;
- config/resource tests should expect the separate OpenAlex work-title
  JSONL log as a required writable registered pipeline-artifact resource;
- config/resource tests should expect the generated/configured OpenAlex
  paper-title parquet as a registered pipeline-artifact resource with
  footer metadata validation;
- parquet metadata tests should verify the title parquet contains the
  JSONL SHA-256 metadata and that a stale/mismatched hash forces rebuild;
- a tiny DuckDB/parquet fixture should verify oldest-paper ranking by
  ascending full date, paperid tie-break, `TOP_K_WORKS` truncation,
  OpenAlex work URL construction, and omission of null-date papers;
- top-works tests should verify title enrichment without changing the
  hit-count-descending/paperid-ascending ordering;
- Step 9/request-set tests should verify that title-needed IDs are the
  distinct union of already top-K-reduced top-work IDs and already
  top-K-reduced top-oldest IDs, not all selected author papers;
- OpenAlex title tests should cover batch query construction, chunking at
  100 ids, redacted JSONL append-on-fetch, parsing a works-list response,
  rebuilding title parquet from JSONL, parquet reuse without JSONL title
  lookup, and no network request when the parquet is current and covers
  all needed IDs;
- batch tests should include a missing/unreturned OpenAlex ID and assert
  the rebuilt parquet still has a row with NULL title for that paper id;
- card output should include `ktp.ssn_top_oldest_papers` when present on
  an innerdict;
- step-10 partition/card tests should keep passing without
  changes to subset semantics.
  
[openalex-recipes]: https://developers.openalex.org/guides/recipes "Quick Recipes - OpenAlex Developers"
