## human written - ai never touches this
### prerequisites and setup
See prerequisites and setup in
`/tasks/tasks-20260519-review-231/SPEC.md`

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
you will need to wire through
several surgical patches
united by a common goal.

The common goal is to
improve match rate
between subset 1 and 2 by addressing
several longstanding issues 
related to name matches
while also improving review data
to enable identifying future
improvement paths.

The surgical patches include:

- at xlsx match step,
  wire through new matching rules:
  - before tokenization,
    any punctuation sequence or
    any whitespace sequence in 
    first name and
    last name is
    replaced with a
    single space.
  - last name is therefore
    now also tokenized, and
    the rule is token sequence
    must be identical
    between source key and target
    (that is,
    same rule as for first name).
  - all tokens from 
    both sides are
    left and right stripped of
    space;
    empty string tokens are
    dropped.
  - if match failed then
    try this additional assertion:
    one side has
    two or more single-letter tokens while
    the other side has a
    single token that is equal to
    the single-letter tokens above joined
    either with a space or
    without a space;
    for example:
    ["john","rb"] on one side and
    ["john","r","b"] on the other side
    should be considered a match
    under this scenario; as well as
    ["john","r b"] on one side and
    ["john","r","b"] on the other side
    should be considered a match
    under this scenario;
    note that the
    exact order and count of
    tokens matters for the match,
    for example
    ["rb", "john"] on one side and
    ["john","r","b"] on the other side
    is NOT a match;
    ["john","rb"] on one side and
    ["john","r","b","james"] on the other side
    is NOT a match;
    this rule applies both for
    first and last name matching.
  - if match failed then
    try this additional assertion:
    one side has
    one or more single-letter tokens while
    the other side has 
    exactly the same number of
    (single or non-single letter) tokens
    that start with these letters
    while all the other tokens are
    matched exactly, and
    the sequence and order of tokens are
    matched exactly; for example,
    ["abdul","latif","m"] on one side and
    ["abdul","l","m"] on the other side
    should be considered a match
    under this rule;
    as counter-examples,
    ["l","abdul",] on one side and
    ["abdul","latif"] on the other side
    is NOT a match,
    ["abdul","latif","merem"] on one side and
    ["abdul","l"] on the other side
    is NOT a match.
- the new rule must be wired
  as a new knob under `config.repl.json`
  according to this shape:
  
  ```json
  {
    ...
    "match_rule_version": {
      "xlsx_name": 1, // 1 or 2
      "docx_name": 1,  // only 1 exists
      "ssn_name": 1,  // 1 or 2
      "ssn_hit": 1 // 1 or 2
    },
    ...
  }
  ```
  
  where xlsx is set to 1
  but if set to 2
  activates the new rule.
- a unit test must be created
  under `/tests/` that
  tests xlsx matching and
  all of its edge cases for
  both the v1 and v2 rule.
  the unit test must use
  pytest but be straightforward and
  it must use duckdb directly, and
  import the def from `/src/` directly,
  rather than a rewrite
  the naming logic in another way,
  so simply put the exact same
  mechanism must be used in the
  unit test as in the actual pipeline.
- for sciscinet matching step, an
  architectural pivot is applied.
  as a bit of background,
  in step 9, specifically at
  "author_details exact-name matching",
  a CTE is created from right side
  (i.e., author details parquet)
  which UNION ALLs, as alt_name, across 
  display_name as well as
  `unnest(CAST(json(display_name_alternatives) AS VARCHAR[]))`
  while still preserving
  authorid column.
  with 100M rows in author details parquet,
  this is easily billions of rows in CTE.
  So we pivot to precomputing all this
  at step 01
  when registration of
  author details parquet is taking place.
  The new code for this
  first checks for
  "ktp_author_details_unnest" parquet in 
  files_config in --config json, and
  if found and hash matches then
  this parquet is reused;
  if hash not matches this is routinely
  raised by current registration tooling, and
  if not found then
  this parquet is created and
  message logged,
  together with sha256 of it, in the 
  repl session screen.
  during creation of this parquet,
  note that we also pivot to
  only keeping unique
  authorid-alt_name pairs
  in the parquet.
  note also that
  the creation of this parquet 
  must be implemented with care
  for RAM, for example
  it is totally fine
  if this procedure takes a short while,
  but if RAM crashes
  this is not fine.
  parquet
  also bears the version of
  the name matching rule used;
  upon loading from
  pre-existing parquet,
  this version is checked
  to match the version from --config.
  and so later in step 9,
  this parquet is used in
  the select as right side table
  instead of CTE.
- also for sciscinet,
  a new knob must be wired through
  in `config.repl.json` in
  the same way as for xlsx above;
  the knob modifies the rule
  the following way:
  - tokens are
    left and right stripped of
    any whitespaces
  - entire list of
    alt_name is 
    expanded with 
    punctuation-free versions,
    for example something like
    (an example, 
    not authoritative):

    ```
    regexp_replace(
      lower(unaccent({alt_name})),
      '[[:punct:]]+',
      ' ',
      'g'
    )
    ```

    this expansion happens
    before deduplication
    during parquet creation.
- also for sciscinet,
  at step 9,
  we add one more logic that
  reduces sciscinet innerdicts
  efficiently to exactly one
  in all cases
  except ties.
  it's been empirically shown
  to perform impressively.
  consider this query:
  `./context/duckdb_ui_20260601T1750Z.sql`.
  this is NOT the exact query
  we need to wire in here, but
  the actually query must be
  based off of that.
  after reading this query,
  the actual rule we wire in is
  (immediately after creating a
  view with nonzero hits):

  - create a new view that
    only keeps
    tukey outliers by
    at least any of the
    three metrics, and
    so this view has a
    bool col is tukey outlier for
    each of the three metrics, and
    this view also should have
    col with raw work count value;
  - select among the outliers
    one with max work count
    as the ultimate innerdict;
  - those that have a
    tie on work count,
    keep all outlier innerdicts
    (and therefore will go
    into subset 2 subsequently
    for human review);
  - If a `name_key` has
    nonzero-hit SSN candidates but
    none of them are Tukey outliers, then
    all nonzero candidates are
    selected as innerdicts
    (i.e., fallback to v1 behaviour).
- match_rule_version.ssn_hit
  from --config config.repl.json
  if set to 1, uses the old way
  where only nonzero hits is used
  else if set to 2 then this
  new rule is used.
- a unit test must be created
  for sciscinet matching
  along the same lines as xlsx.
- a unit test must be created
  for docx matching
  along the same lines as xlsx,
  though the rule itself
  remains unchanged.
- there should be a separate file
  under `/tests` for
  specifically these unit tests, so
  three files: 
  one for xlsx match tests,
  one for docx match tests, and
  one for sciscinet match tests
  (both name and hit match).
- in step 10 logic that builds
  `10_build_cards_card_partition_review_df.csv`
  the logic must be changed to show
  ALL values of available innerdicts
  (all of DOCX, XLSX, SciSciNet,
  depending on the column)
  rather than only when one exists;
  they must be merged within cell through
  one new line if no multiline text in either,
  or with '-----'
  if any innerdict value contains multiline text.

### follow-up
see "post-implementation" in
`./context/README.md`.

## how ai understood the spec

The AI-readable interpretation is:

### inherited operating constraints

- Honor all inherited prerequisites and setup from
  `/tasks/tasks-20260519-review-231/SPEC.md`.
- Do not run `src.repl` and do not run the full pipeline command. In
  particular, do not run
  `pixi run python -m src.repl --config config.repl.json --new`.
- If database evidence is needed, use only `data/scisci_process.duckdb`, opened
  read-only. Do not mutate that database.
- Git usage is read-only for the AI executor: do not stage, unstage, commit,
  reset, checkout away, or otherwise mutate git state.
- Use `tasks/tasks-20260526-match-patch/WORK.md` as the task-local workbook.
  Keep it current with concise notes about intent, work in progress, completed
  changes, verification, and caveats.
- The scope is surgical. Preserve the psyche and query shape of the original
  code wherever possible. Do not redesign unrelated pipeline stages.
- Matching logic must live in centralized matching helpers that emit DuckDB SQL
  or other production query fragments. Do not move name matching into Python
  callbacks or test-only reimplementations.
- Tests for matching must use the same DuckDB mechanisms as production,
  including DuckDB `unaccent` through `splink_udfs`. Do not use Python
  `unaccent` or separate Python normalization as the asserted mechanism.

### config shape and rule versions

- Replace the old boolean knobs and the interim `name_matching_rule_version`
  object with the structured config object:

  ```json
  "match_rule_version": {
    "xlsx_name": 1,
    "docx_name": 1,
    "ssn_name": 1,
    "ssn_hit": 1
  }
  ```

- Valid versions are:
  - `xlsx_name`: `1` or `2`;
  - `docx_name`: `1` only;
  - `ssn_name`: `1` or `2`;
  - `ssn_hit`: `1` or `2`.
- `PipelineConfig` should accept this object and reject unsupported rule
  versions. The old booleans `xlsx_match_name_tokens_v2` and
  `sciscinet_match_strip_tokens`, plus the interim
  `name_matching_rule_version`, are stale and should not remain the active
  control path.
- The task config may set `xlsx_name = 2`, `docx_name = 1`, `ssn_name = 2`, and
  `ssn_hit = 2`, while the code still supports version `1` as the
  conservative/default behavior for each supported rule.
- Versioned match payloads should be consistent across domains:
  - XLSX payloads carry `ktp.xlsx_match_rule`;
  - DOCX payloads should carry `ktp.docx_match_rule`, currently always `v1`;
  - SSN/SciSciNet name-match payloads should carry `ktp.ssn_match_rule`, `v1` or
    `v2`;
  - SSN hit-selection metadata should carry an auditable rule version as well,
    for example `ktp.ssn_hit_rule`, `v1` or `v2`, together with the v2 Tukey
    flags described below when the rule is active.
- Use `ssn` in internal output labels where applicable. In particular, the
  partition count flag is `ktp.partition_flag_ssn_count`, not
  `ktp.partition_flag_sciscinet_count`. It is still fine for prose to refer to
  the external data source as SciSciNet.

### XLSX matching

- XLSX v1 must remain the original pre-match-patch behavior. The
  `match_rule_version.xlsx_name = 1` path must use the same first-token and
  last-name equality semantics the pipeline had before this task.
- XLSX v2 is additive to v1 for review/partition safety. It introduces the new
  token/fallback matching rule, but it must not lose rows that original v1 would
  have detected as present non-exact XLSX matches.
- In v2 mode, generate relational match keys in DuckDB and join by equality on
  those keys. Do not put recursive/token comparison directly inside the `JOIN
  ON`, because that caused unacceptable memory growth.
- For v2 tokenization:
  - lower/unaccent using DuckDB;
  - replace punctuation sequences and whitespace sequences with a single space;
  - trim tokens;
  - drop empty tokens;
  - apply the same token-sequence rule to first and last names.
- V2 exact token-sequence matching requires identical token sequence, count, and
  order on source and target, separately for first and last names.
- V2 compact-initial fallback applies in either direction. A run of two or more
  single-letter tokens on one side may match one token on the other side equal
  to the run joined with no separator or with a single space. The full token
  sequence must still be consumed exactly and in order.
- V2 same-length initial-expansion fallback applies in either direction. A
  single-letter token may match a token at the same position that starts with
  that letter. All non-initial positions must match exactly, and both sides must
  have the same token count.
- In v2 mode, include the original v1 key path as a secondary rule path. For the
  same source/HCR row, prefer the v2 path over the v1 path. Rows matched only by
  the v1 path should carry `ktp.xlsx_match_rule = "v1"` and are present XLSX
  matches but non-exact for step 10 partitioning.
- XLSX tests must cover v1 and v2 positive and negative edge cases, including
  compact initials, same-length initials, order/count failures, punctuation,
  whitespace, last-name tokenization, v2 preference over v1, and v1-only rows
  being treated as non-exact in partitioning.

### DOCX matching

- DOCX matching behavior remains v1 only and should not be broadened as part of
  this task.
- The existing DOCX normalization/containment behavior should be centralized in
  the matching helper and covered by direct DuckDB pytest tests.
- DOCX match payloads should include `ktp.docx_match_rule = "v1"` so all
  matching domains expose a rule version consistently.

### SSN/SciSciNet matching

- SSN/SciSciNet v1 must preserve the original exact normalized display-name
  matching behavior. In v1, matching remains equality between the normalized KTP
  full name and normalized SciSciNet display/alternative name.
- The old step 9 right-side `parq` CTE is too large at full scale. It logically
  expands `author_details` into one row for `display_name` plus one row for each
  `display_name_alternatives` entry. With approximately 100M author rows, that
  can become billions of logical right-side rows.
- Pivot the right side of SSN author-details matching to a precomputed parquet
  produced during resource registration / step 01 for author details. Step 9
  should use that parquet as the right-side relation instead of rebuilding the
  display/alt-name expansion CTE.
- The precomputed parquet is keyed from the `files_config` entry named
  `ktp_author_details_unnest`.
  - If that entry exists and its registered hash matches, reuse it.
  - If it exists and the hash does not match, rely on existing registration
    validation to raise.
  - If it is absent, create the parquet, log that it was created, and log the
    sha256 so the user can add it to config.
- `ktp_author_details_unnest` is a required derived resource for step 9, but it
  is not necessarily a required pre-existing config input. If it is missing from
  `files_config`, step 01 must create it and register it before step 9 can run.
  Step 9 should not fall back to rebuilding the old giant author-details
  display/alt-name CTE.
- First-run creation of `ktp_author_details_unnest` is a heavy operation and
  must be logged live before the DuckDB `COPY` starts, not only as a completed
  `StepResult` message after the parquet has already been written. The REPL
  screen should warn that the derived author-details unnest build is starting,
  identify the output path, and identify the active SSN/SciSciNet matching rule
  version. Completion messages should still include the created path and sha256.
- Do not add `ktp_author_details_unnest` to `REQUIRED_FILES_CONFIG_KEYS` in a way
  that prevents first-run creation. Instead, guarantee that by the end of
  resource registration the runtime resources include the derived unnest parquet,
  whether it was reused from config or newly created. If present in
  `files_config`, it should still obey the existing per-entry shape (`path`,
  `sha256`, `desc`) unless the config model is deliberately extended with a
  clearer derived-resource schema.
- Resource registration is currently hard-coded for the required SciSciNet
  parquet inputs. Extend the existing registration flow surgically so the
  derived unnest parquet is created/reused and registered through the same
  resource model and registry table. Do not create a fragmented or parallel
  resource-registration path, and do not disrupt registration of the existing
  required parquet files.
- Creating this parquet must be done with RAM care:
  - use DuckDB/parquet operations, not pandas materialization;
  - avoid Python lists of author rows or alt-name rows;
  - avoid pairwise/Python matching logic;
  - prefer a query shape that can spill or stream through DuckDB rather than
    forcing all expanded rows into Python memory;
  - it is acceptable for this one-time build to take time, but it must not crash
    RAM on the intended full-scale input.
- The precomputed parquet should contain unique author/alt-name match rows after
  rule-specific expansion. Keep the row payload lean and explicit: the intended
  row columns are `ssnad.authorid` and `ktp.alt_name`. Centralize
  `ktp.alt_name` in `vars.py` as a named constant. Do not store repeated
  `display_name`, `display_name_alternatives`, or other large author-details
  payload columns in this derived match-key parquet; step 9 already has access
  to `author_details` and can retrieve display payloads there after author IDs
  are matched.
- The precomputed parquet must bear the SSN rule version as Parquet file-level
  key-value metadata in the file footer, not as a repeated column across every
  author/alt-name row and not as a normal sidecar file. DuckDB parquet
  `KV_METADATA` is available in the project environment and should be used with
  a small key such as `match_rule_version.ssn_name`. On reuse, after
  the normal registration/hash check passes, verify the stored footer metadata
  rule version against `match_rule_version.ssn_name` using DuckDB.
- If the derived parquet is created during registration, include it in the
  registered resource diagnostics/table so the user can see its path, hash,
  resource group, fragment type, and description. Do not silently create an
  untracked side artifact.
- Step 9 should cleanly consume the registered derived parquet in SQL. When
  replacing the old `parq AS (...)` CTE with `read_parquet()` against
  `ktp_author_details_unnest`, do not leave stale CTE punctuation such as
  `WITH names AS (...), SELECT ...`; the resulting query must parse as the
  simple equality join shape.
- Step 9 must also keep the first author-name match materialization narrow for
  RAM. The initial `ssn_author_matches` / `PARQUET_AUTHOR_MATCH_TABLE` query
  should join KTP name keys to `ktp_author_details_unnest` only and should not
  immediately join back to the full `author_details` parquet merely to carry
  `display_name` or `display_name_alternatives` payload columns. That early
  wide join is redundant because step 9 later materializes a filtered
  author-details table after nonzero-hit pruning and the final author output
  already takes display payload columns from that later filtered table.
- The intended immediate step 9 RAM fix is therefore surgical: keep
  `PARQUET_AUTHOR_MATCH_TABLE` to the minimal match payload needed downstream:
  source/name-key fields, `ssnad.authorid`, and `ktp.ssnad_match`. Apply
  `SELECT DISTINCT` over those narrow columns only. Continue to join the later
  filtered author-details table for full display payloads after the nonzero-hit
  filter has reduced candidate authors.
- Do not change the `ktp_author_details_unnest` resource schema as part of this
  immediate RAM fix. It remains the approved two-column parquet with
  `ssnad.authorid` and `ktp.alt_name`, with footer rule-version metadata.
- Evidence gathered for future optimization, not for the immediate patch:
  `data/output/ktp_author_details_unnest_v1.parquet` has 131,843,627
  author/name rows and 87,228,294 distinct `ktp.alt_name` strings. The source
  `tmp/sciscinet_author_details.parquet` has 100,418,971 rows and exact
  one-row-per-authorid cardinality; every `authorid` is `A` plus 10 digits, with
  numeric suffix range 5,000,000,002 through 5,115,709,198. This means a future
  normalized lookup design could store author IDs as `BIGINT` internally and
  reconstruct the canonical `A...` string at output boundaries, but this task's
  surgical RAM patch should not introduce that broader schema/resource pivot.
- If step 9 remains too memory-heavy after the narrow-match-table patch, the
  next optimization candidate is a separately specified and benchmarked
  normalized lookup resource, for example distinct `strings(sid, s)` plus
  `id_map(sid, authorid)` sorted by `sid`. Such a design must use deterministic
  `sid` assignment, preserve/declare parquet metadata and registration rules for
  all derived resources, and be benchmarked against the current long parquet;
  it is not part of the immediate surgical fix.
- The reason not to prioritize that normalized DuckDB lookup before the narrow
  step 9 patch is empirical rather than aesthetic. String deduplication is real
  but moderate at the measured scale: 131,843,627 author/name rows versus
  87,228,294 distinct `ktp.alt_name` strings, so dedupe removes roughly one
  third of string occurrences, not a 5-10x factor. Parquet already compresses
  repeated strings, so storage savings may be smaller than row-count savings,
  though lookup speed could still improve by comparing against fewer unique
  strings.
- Numeric author IDs are also a good future optimization candidate, since every
  source author ID is `A` plus 10 digits and fits in `BIGINT`; however, numeric
  author IDs alone are expected to save at most hundreds of MB in the current
  unnest, not explain a multi-GB step 9 peak. Also avoid applying
  `CAST(substr(authorid, 2) AS BIGINT)` on the huge source-parquet side of joins
  unless benchmarked; if numeric IDs are introduced later, prefer reconstructing
  the canonical `A...` string on the already-small matched side or building
  explicit numeric projections as a broader design.
- Ordering derived lookup data and using DuckDB storage rather than parquet may
  improve repeated lookup speed, especially if sorted integer `sid` columns make
  zonemap pruning effective and if explicit indexes are benchmarked. But this is
  a resource-schema/storage pivot with its own registration, metadata, storage,
  and memory tradeoffs. It should follow measurement after the narrow-table fix,
  not precede the immediate surgical regression fix.
- SSN v2 is intentionally not XLSX v2. Do not add XLSX compact-initial or
  same-length initial-expansion logic to SciSciNet matching.
- SSN v2 adds only the agreed string-edge/punctuation behavior:
  - strip leading/trailing whitespace from compared names/keys;
  - expand the right-side display/alt-name list with a punctuation-to-space
    variant before deduplication;
  - the punctuation-to-space variant should replace punctuation sequences with a
    single space, then normalize whitespace and trim. It must not remove
    whitespace entirely.
- Because SSN v2 equality matching requires both sides to speak the same key
  language, the KTP/namekey side must use the comparable v2 normalized key. For
  example, `Claire M` + `Fraser` should compare as `claire m fraser`, and the
  SciSciNet display name `Claire M. Fraser` should also produce
  `claire m fraser`.
- SSN v2 should still be an equality join over precomputed relational keys. It
  should not create a pairwise recursive comparator or broad token-expansion join
  against the full SciSciNet author universe.
- Step 9 still starts hit processing with the existing nonzero-hit filter: a raw
  author-details name match with `ktp.ssn_sum_hit_1pct == 0` is not an SSN
  candidate for downstream innerdict output. `match_rule_version.ssn_hit`
  controls what happens after that nonzero-hit candidate set exists.
- `match_rule_version.ssn_hit = 1` is the old behavior. The effective SSN
  candidate view for downstream enrichment/output is simply the nonzero-hit
  author-match view.
- `match_rule_version.ssn_hit = 2` adds the Tukey-outlier candidate reduction.
- The implementation contract for SSN hit v2 is fully specified in the bullets
  below.
- The production SSN hit v2 rule is: after the existing nonzero-hit SSN
  candidate set exists, calculate Tukey fences separately within each
  `name_key`, collect candidates that are outliers under at least one of the
  three metrics, and then use max `works_count` to select a single confident
  author when possible. No-outlier name keys still use the max-works rule over
  the full nonzero-hit candidate pool. The rule falls back to returning the full
  nonzero-hit candidate pool only when a confident max-works decision is not
  possible.
- For SSN hit v2, build a narrow candidate-metric relation from the nonzero-hit
  author matches and only the metric columns needed for selection:
  `ktp.ssn_sum_hit_1pct`, `ssnad.works_count`, and `ssnad.cited_by_count`. Keep
  the recent RAM fix intact: do not reintroduce a wide early join to full
  `author_details` payload columns. If `works_count` and `cited_by_count` must
  come from author_details at this stage, join only `authorid`, `works_count`,
  and `cited_by_count`, or reuse the already-filtered/narrow author-details
  materialization if it is available at that point in the step.
- The candidate-metric relation should be created only for
  `match_rule_version.ssn_hit = 2`. It should be narrow and should include the
  original columns from the nonzero-hit author-match view plus these SQL-derived
  metric columns:
  - `ssn_hit_sum_hit_1pct_metric = TRY_CAST(ktp.ssn_sum_hit_1pct AS DOUBLE)`,
    sourced from the hit aggregate joined by `name_key` and author id;
  - `ssn_hit_works_count_raw = ssnad.works_count`, preserved for audit/output;
  - `ssn_hit_works_count_metric = TRY_CAST(ssnad.works_count AS DOUBLE)`, used
    for quantiles and max-work comparison;
  - `ssn_hit_cited_by_count_metric = TRY_CAST(ssnad.cited_by_count AS DOUBLE)`,
    used for quantiles.
- Compute Tukey bounds per `name_key` over that name key's v2 nonzero-hit
  candidate rows for each metric:
  - `ssn_q1 = quantile_cont(ssn_hit_sum_hit_1pct_metric, 0.25)`;
  - `ssn_q3 = quantile_cont(ssn_hit_sum_hit_1pct_metric, 0.75)`;
  - `works_q1 = quantile_cont(ssn_hit_works_count_metric, 0.25)`;
  - `works_q3 = quantile_cont(ssn_hit_works_count_metric, 0.75)`;
  - `cited_q1 = quantile_cont(ssn_hit_cited_by_count_metric, 0.25)`;
  - `cited_q3 = quantile_cont(ssn_hit_cited_by_count_metric, 0.75)`.
- For each metric, derive `lower = q1 - 1.5 * (q3 - q1)` and
  `upper = q3 + 1.5 * (q3 - q1)` for that same `name_key`. A candidate is an
  outlier for that metric when `metric < lower OR metric > upper`. Wrap each
  metric flag with `COALESCE(..., false)` so null metric values do not create a
  true Tukey flag.
- Implement per-key bounds as relational SQL: group the candidate metric
  relation by `name_key` to compute the three q1/q3 pairs, derive lower/upper
  fences in that grouped relation, and join those per-key bounds back to
  candidate rows on `name_key`.
- The row-level combined flag is
  `ssn_hit_row_has_tukey_outlier = ssn_flag OR works_flag OR cited_flag`. The
  name-key-level combined flag is true if any row in that `name_key` has the
  row-level combined flag true, for example
  `MAX(CASE WHEN ssn_hit_row_has_tukey_outlier THEN 1 ELSE 0 END) OVER
  (PARTITION BY name_key) = 1`.
- The v2 candidate-metric view should expose auditable columns for the three
  metric flags, row-level combined flag, per-key combined flag, raw work count,
  and enough per-key bound columns to explain/debug selection. At minimum it
  should expose:
  `ktp.ssn_hit_sum_hit_1pct_is_tukey_outlier`,
  `ktp.ssn_hit_works_count_is_tukey_outlier`,
  `ktp.ssn_hit_cited_by_count_is_tukey_outlier`,
  `ktp.ssn_hit_row_has_tukey_outlier`,
  `ktp.ssn_hit_name_key_has_tukey_outlier`, and
  `ktp.ssn_hit_works_count_raw`. It should also expose the hit rule version,
  for example `ktp.ssn_hit_rule = "v2"`.
- For SSN hit v2 selection, first define the nonzero pool for each `name_key` as
  the rows in the existing nonzero-hit author-match view. Then apply these
  rules in order:
  - if the nonzero pool is empty, no SSN row is selected and the name key remains
    unresolved by SSN;
  - if the nonzero pool has exactly one row, select that row as the effective
    SSN row. The v2 hit-selection rule is only needed to adjudicate multiple
    nonzero SSN candidates; a singleton nonzero candidate is accepted as-is and
    does not require present/castable `works_count`;
  - if the nonzero pool has multiple rows and any row in that pool has missing
    or non-castable `works_count`, the v2 rule fails for that name key and all
    nonzero-pool rows are selected for subset 2 review;
  - otherwise, if the multi-row nonzero pool has one or more per-key Tukey outliers, the
    max-works decision pool is all outlier rows for that `name_key`;
  - otherwise, the max-works decision pool is the full nonzero pool for that
    `name_key`.
- Within the max-works decision pool, find the maximum numeric works-count
  metric. If exactly one author ID has that maximum works count, select that one
  candidate. If two or more author IDs share the maximum works count, the v2
  rule fails for that name key and all nonzero-pool rows are selected for subset
  2 review. Preserve `ktp.ssn_hit_works_count_raw` for audit/output.
- `ktp.ssn_sum_hit_1pct` and `ssnad.cited_by_count` participate in Tukey outlier
  classification, not in the max-work decision.
- Failure/fallback states should be auditable in the v2 selection relation,
  especially multi-candidate missing works count and max-works tie. These v2
  failure states select all nonzero-pool rows and therefore naturally leave at
  least two effective SSN rows; step 10 can continue using effective SSN row
  count for subset routing.
- The selected/effective SSN rows under v2 are therefore:
  - no rows when there are no nonzero-hit candidates;
  - exactly one candidate when there is exactly one nonzero-hit candidate,
    regardless of missing/non-castable auxiliary metrics;
  - all nonzero-hit candidates when a multi-row nonzero pool has any missing or
    non-castable `works_count`;
  - exactly one candidate when the max-works decision pool has a unique maximum
    raw/numeric `works_count`;
  - all nonzero-hit candidates when the max-works decision pool has a tie for
    maximum raw/numeric `works_count`.
- Downstream step 9 enrichment should consume one effective author-match view
  after hit selection. In v1 this view aliases or reproduces the nonzero-hit
  candidate set; in v2 it is the selected set described immediately above. This
  keeps all later SSN innerdict generation, top papers, institutions, field
  mapping, and step 10 partitioning aligned with the selected candidates.
- The SSN hit v2 implementation must keep the author-output SQL parse-safe when
  it injects audit columns. The generated select-list fragment for v2 hit
  metadata must close every quoted alias and leave a valid comma boundary before
  the next provenance column such as `ssnap.filename`. Add a focused test that
  executes or parses the v2 author-output metadata select fragment followed by a
  normal downstream column, so a malformed alias cannot recur.
- SSN hit v2 logging must be detailed enough to explain a reduction such as
  `312/2,824` without requiring ad hoc SQL after the run. After the nonzero-hit
  set exists and v2 hit selection is applied, log a breakdown of how the
  nonzero-hit rows were classified and selected.
- The v2 hit-selection breakdown should include Tukey bounds for each of the
  three metrics: q1, q3, lower fence, and upper fence for
  `ktp.ssn_sum_hit_1pct`, `ssnad.works_count`, and `ssnad.cited_by_count`.
  Because these bounds are per name key, expose the per-key bound columns in the
  v2 candidate metric artifact/relation for review queries, and keep step logs
  compact by reporting selection/count diagnostics rather than printing one row
  per name key.
- The v2 hit-selection breakdown should also include candidate and selection
  counts: total nonzero candidate rows/name keys/authors, rows outlying by each
  metric, rows with any Tukey outlier, name keys with at least one Tukey
  outlier, name keys whose max-works decision pool is the outlier pool, name
  keys whose max-works decision pool is the full nonzero pool because no
  outliers exist, singleton nonzero name keys accepted without adjudication,
  rows/name keys with missing or non-castable `works_count` in multi-row pools,
  unique max-work winner name keys, max-work tie/failure name keys, selected
  rows/name keys/authors, selected rows retained because there was only one
  nonzero candidate, selected rows retained by unique max-work selection,
  selected rows retained because multi-row missing works count selects all
  nonzero rows, selected rows retained because max-work ties select all nonzero rows,
  non-selected rows pruned by unique max-work selection, number of name keys
  with exactly one selected row, number with multiple selected rows/ties, and
  the maximum selected row count for any one name key.
- Implement the v2 logging breakdown from the same production SQL relations used
  by selection, preferably through the centralized SSN hit-selection helper, not
  by reimplementing Tukey classification in Python. Add a focused DuckDB test
  for the breakdown query on synthetic candidate rows, including cases where
  per-name-key bounds drive selection, max `works_count` outside the
  Tukey-outlier set must not be selected when outliers exist, singleton nonzero
  candidates are accepted even with missing/non-castable metrics, no-outlier
  keys with a unique max works count select that unique author, missing works
  count in a multi-row pool selects all nonzero candidates, and max-work ties
  select all nonzero candidates.
- Keep step 9 logging plumbing plain and local to the already-computed SQL
  result rows. Do not add generic row-to-dict formatting helpers in the step;
  the v1 branch should remain obviously the exact nonzero-hit alias, and the v2
  branch should be the only branch that creates/reads the candidate metric table.
- SSN tests must use the production helper SQL and DuckDB directly. They should
  cover name-rule behavior (v1 exact behavior, v2 leading/trailing whitespace,
  v2 punctuation-to-space behavior such as `Claire M. Fraser` matching
  `Claire M Fraser`, and negative cases proving v2 does not implement
  XLSX-style initials matching) and hit-rule behavior (`ssn_hit` v1 keeps all
  nonzero-hit candidates, `ssn_hit` v2 uses per-name-key Tukey bounds, v2 keeps
  a unique max-work author from the outlier pool when outliers exist, v2 keeps a
  unique max-work author from the full nonzero pool when no outliers exist, v2
  keeps a singleton nonzero candidate even when `works_count` is
  missing/non-castable, v2 falls back to all nonzero-hit candidates when any
  candidate in a multi-row nonzero pool has missing or non-castable
  `works_count`, and v2 falls back to all nonzero-hit candidates when there is a
  max-work tie).
- Use `tasks/tasks-20260526-match-patch/context/duckdb_ui_20260601T1750Z_export_edit_done.xlsx`
  as an edge-case catalog for SSN hit v2 tests. The `manual_best` and
  `manual_best_note` columns identify approximately 35 reviewed source keys and
  expected/observed behavior. Do not make the tests depend on the old run DB;
  translate representative workbook cases into small DuckDB fixtures that still
  execute the production helper SQL. Good fixture classes include: no per-key
  outliers with a unique max-work winner, unique per-key outlier max-work
  winner, high-work non-outlier that must not be selected when outliers exist,
  singleton nonzero candidates with missing metrics still being accepted,
  multi-row missing works count selecting all nonzero candidates for review,
  max-work ties selecting all nonzero candidates for review, and rows
  illustrating known SSN/OpenAlex data quality limits that the rule cannot solve.

### post-implementation follow-ups from context README

- The updated `tasks/tasks-20260526-match-patch/context/README.md` adds three
  final follow-up items. Treat them as part of the task interpretation, but keep
  them surgical and do not rewrite the already-approved matching architecture.
- Add a focused pytest output-fixture check under the SciSciNet/SSN test module.
  The test file should define these paths near the top of the module:
  - `tasks/tasks-20260526-match-patch/context/duckdb_ui_20260601T1750Z_export_edit_done.xlsx`;
  - `tmp/hcr_cards_subset1_20260602T1624Z_v2_ssn_hit_v2_per_namekey_Tukey`;
  - `tmp/hcr_cards_subset2_20260602T1754Z_v2_ssn_hit_v2_per_namekey_Tukey`.
- The fixture test should read rows with known `manual_best` from the reviewed
  XLSX and compare them against the actual production card outputs in the two
  fixture directories. For the same `ktp.source_key`, the selected SSN author id
  in the subset 1 output should equal `manual_best`.
- Keep this fixture test narrow. It is an acceptance/regression check against
  frozen outputs, not a broad pipeline rerun and not a replacement for the
  direct DuckDB unit tests. It should not run `src.repl`.
- Expected exceptions for the fixture check are limited to cases documented in
  the context README:
  - the three no-current-OpenAlex-result names listed there, currently
    `{"ktp.first_name": "Rasmus", "ktp.last_name": "Nielsenlo"}`,
    `{"ktp.first_name": "Baerbel-Maria", "ktp.last_name": "Kurth"}`, and
    `{"ktp.first_name": "Huaiyu Y", "ktp.last_name": "Mi"}`;
  - `{"ktp.first_name": "Baoshan ", "ktp.last_name": "Xing"}`, which is
    expected to be in subset 2 because of a non-exact XLSX match, while still
    carrying the correct SSN author id `A5035633946`.
- In other words, for known `manual_best` rows not covered by the documented
  exceptions, the test should assert the current fixture outputs select that
  author id. The test should explicitly encode the known exceptions rather than
  allowing broad skips.
- Add an OpenAlex current-data cross-check in step 9, but only when
  `match_rule_version.ssn_hit = 2` and the SSN hit rule has identified a single
  effective author id for a `name_key`. Multi-row SSN review cases are already
  unresolved and do not need an OpenAlex confidence check at this stage.
- Load `OPENALEX_API_KEY` from the repo `.env` file using `python-dotenv`.
  The request is:

  ```text
  GET https://api.openalex.org/authors?search={ktp.source_key_first}%20{ktp.source_key_last}&sort=relevance_score%3Adesc&select=id&per_page=1&api_key=OPENALEX_API_KEY
  ```

  where `{ktp.source_key_first}` and `{ktp.source_key_last}` come from the KTP
  source key fields for that `name_key`.
- Log every OpenAlex request/response/reuse to an append-only JSON Lines file
  under `data/`. Centralize the concrete filename in code. Each line should use
  schema version `1`; the schema-version constant must live in `vars.py`, not as
  an inline literal in the OpenAlex logging helper. Each line should include at
  least:

  ```json
  {
    "schema_version": 1,
    "method": "GET",
    "scheme": "https",
    "host": "api.openalex.org",
    "path": "/authors",
    "query": "...",
    "request_headers": {},
    "request_body": null,
    "response_code": 200,
    "response_headers": {},
    "response_body": "...",
    "received_at_unix_usec": 0,
    "duration_usec": 0
  }
  ```

  Additional fields needed for deterministic reuse, such as `ktp.source_key`,
  selected SSN author id, parsed OpenAlex top author id, and match verdict, are
  allowed and should be included if they make the cache/audit clearer.
- Before making an OpenAlex API request, scan the append-only JSONL log for an
  existing response for the same `ktp.source_key` and equivalent request. If one
  exists, reuse it instead of making a network call. Reuse must be logged in the
  REPL session just as readably as a fresh request.
- REPL logging for the OpenAlex check should be informative but compact. For
  each checked single-author `name_key`, log whether the response was reused or
  fetched, the response status, the parsed top OpenAlex author id if present,
  the selected SSN author id, the match/mismatch verdict, and request duration
  for fresh requests.
- Treat the OpenAlex check as a confidence gate for single SSN author selections
  under hit rule v2 and wire its result directly into the effective SSN
  selection. If the top current OpenAlex author id equals the selected SSN
  author id, keep that single author id as the effective SSN innerdict. If
  OpenAlex returns no result or returns a different top author id, consider SSN
  hit rule v2 failed for that `name_key` and select the entire nonzero-sum-1pct
  SSN candidate pool as effective innerdicts instead. This failed case must land
  in subset 2 for manual review. If the full nonzero-sum-1pct pool contains only
  one row, add whatever clear audit/partition signal is needed so the failed
  OpenAlex confidence check still routes to subset 2 rather than being silently
  accepted by count alone.
- Do not make ordinary unit tests depend on the live OpenAlex API. Use mocked or
  prewritten JSONL responses for tests of request construction, cache reuse,
  response parsing, and mismatch handling.
- The third context README item, forcing known `manual_best` author ids into the
  pipeline through a new `RegisteredResource` and handler, is explicitly
  recognized but remains pending. Do not implement manual-best forcing until a
  separate implementation pass is approved. The pending design should preserve
  resource registration/hash checking and should inject the forced author id
  early enough that downstream papers, hits, institutions, and final innerdict
  payloads are built for the forced author, but that handler is not part of the
  current implementation request.

### step 10 review dataframe

- Step 10 partitioning logic remains unchanged except for already-agreed naming
  cleanup from `sciscinet` to `ssn` where applicable. Do not change which
  namekeys land in subset 1 or subset 2 as part of the review-display fix.
  SSN hit v2 must express unresolved multi-candidate cases by returning all
  nonzero effective SSN rows, so step 10's effective SSN row-count logic remains
  sufficient for subset routing. Do not add a parallel step 10 failure flag for
  SSN hit v2.
- The review dataframe fix is presentation/context aggregation only. By step 10,
  processing is already done and innerdicts are available per namekey; the
  review CSV should faithfully display those innerdicts.
- `10_build_cards_card_partition_review_df.csv` must show all available
  relevant innerdict values for each reviewed source key. It should not show a
  blank just because the partition's primary branch has no row.
- Keep `ktp.source_key`, `ktp.partition`, partition flags, draw number, first
  name, and last name sourced from the card partition table.
- Keep `ktp.ff_discard` and `ktp.ff_note` as blank/editor columns.
- Treat `ktp.ff_author_id` specially. It is an SSN author id field:
  - for an SSN candidate row, keep the row's candidate author id available for
    editing/selection;
  - if aggregating context, use only SSN `ktp.fragment` values as possible
    author IDs;
  - never fill `ktp.ff_author_id` from XLSX row numbers or DOCX row fragments;
  - if there is no SSN innerdict, leave it blank.
- Generic provenance columns are relevant across domains. For
  `ktp.filename`, `ktp.fragment`, and `ktp.fragment_type`, aggregate available
  values from XLSX, DOCX, and SSN innerdicts for the source key. This is the fix
  for rows like Claire M Fraser, where XLSX and DOCX context exists but the
  missing SSN primary row caused blank provenance fields.
- Domain-specific columns should aggregate from their relevant domain:
  - XLSX/HCR columns from XLSX innerdicts, including `hcr.category`, economies,
    economy match, affiliations, and `ktp.xlsx_match`;
  - SSN columns from SSN innerdicts, including display names, alternatives,
    field display names, top institutions, `ktp.ssnad_match`, hit sums, works
    counts, citations, and works API URL;
  - DOCX columns from DOCX innerdicts, including `ktp.docx_match` and table 1
    extraction columns.
- Merge all non-empty values in-cell. Preserve repeated values when they come
  from multiple innerdicts; do not collapse them merely because the display text
  is identical. Use stable ordering, preferably by filename, fragment,
  fragment_type, and the source column value.
- If no merged value contains multiline text, separate values with one newline.
  If any value being merged contains multiline text, separate values with a line
  containing `-----`.
- Review context values should be cast to display `VARCHAR` before merging so
  JSON-typed values such as economies do not trigger DuckDB JSON re-casting
  errors after newline merging.
- The review view should handle both primary rows and placeholder rows. A
  placeholder row for the SSN partition with zero SSN candidates should still
  show all available XLSX and DOCX context.
- If a review artifact is emitted for subset mode 1, partition value `0`
  (`no resolution needed`) must be considered. The view should not produce an
  empty header-only CSV solely because all selected rows are partition `0`.

### verification expectations

- Add/maintain dedicated direct DuckDB pytest files:
  `tests/test_xlsx_name_matching.py`, `tests/test_docx_name_matching.py`, and
  `tests/test_sciscinet_name_matching.py`. The SciSciNet/SSN test file should
  cover both SSN name matching and SSN hit-selection rules.
- Add/maintain step 10 tests proving review rows aggregate all available
  context, including placeholder rows, JSON-typed values, multiline delimiter
  behavior, generic provenance fields, and SSN author-id special handling.
- Run focused matching and step 10 tests after implementation.
- Run `pixi run pre-commit` when done. If unrelated existing failures remain,
  record them precisely in `WORK.md` and the final response.
