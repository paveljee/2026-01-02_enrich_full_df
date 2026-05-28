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
    "name_matching_rule_version": {
      "xlsx": 1, // 1 or 2
      "docx": 1,  // only 1 exists
      "sciscinet": 1  // 1 or 2
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
  one for sciscinet match tests.
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

- Replace the old boolean knobs with the structured config object:

  ```json
  "name_matching_rule_version": {
    "xlsx": 1,
    "docx": 1,
    "sciscinet": 1
  }
  ```

- Valid versions are:
  - `xlsx`: `1` or `2`;
  - `docx`: `1` only;
  - `sciscinet`: `1` or `2`.
- `PipelineConfig` should accept this object and reject unsupported rule
  versions. The old booleans `xlsx_match_name_tokens_v2` and
  `sciscinet_match_strip_tokens` are stale and should not remain the active
  control path.
- The task config may set `xlsx = 2`, `docx = 1`, and `sciscinet = 2`, while the
  code still supports version `1` as the conservative/default behavior.
- Versioned match payloads should be consistent across domains:
  - XLSX payloads carry `ktp.xlsx_match_rule`;
  - DOCX payloads should carry `ktp.docx_match_rule`, currently always `v1`;
  - SSN/SciSciNet payloads should carry `ktp.ssn_match_rule`, `v1` or `v2`.
- Use `ssn` in internal output labels where applicable. In particular, the
  partition count flag is `ktp.partition_flag_ssn_count`, not
  `ktp.partition_flag_sciscinet_count`. It is still fine for prose to refer to
  the external data source as SciSciNet.

### XLSX matching

- XLSX v1 must remain the original pre-match-patch behavior. The
  `name_matching_rule_version.xlsx = 1` path must use the same first-token and
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
  rule-specific expansion. At minimum it must preserve `authorid`, the matching
  alt-name/key value, and the SSN rule version used to create the parquet. It may
  avoid storing large display payloads if step 9 can join back to
  `author_details` for display fields after identifying matched author IDs.
- The precomputed parquet must bear the SSN rule version. A straightforward
  implementation is a column such as `ktp.ssn_match_rule` with a single expected
  value. On reuse, verify that the parquet's rule version matches
  `name_matching_rule_version.sciscinet`.
- If the derived parquet is created during registration, include it in the
  registered resource diagnostics/table so the user can see its path, hash,
  resource group, fragment type, and description. Do not silently create an
  untracked side artifact.
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
- Step 9 can still apply its downstream nonzero-hit filter. A raw author-details
  name match that is later filtered out by `ktp.ssn_sum_hit_1pct == 0` will not
  produce an SSN innerdict and therefore will still count as zero in step 10.
  This task does not change that filter unless explicitly requested.
- SSN tests must use the production helper SQL and DuckDB directly. They should
  cover v1 exact behavior, v2 leading/trailing whitespace, v2 punctuation-to-space
  behavior such as `Claire M. Fraser` matching `Claire M Fraser`, and negative
  cases proving v2 does not implement XLSX-style initials matching.

### step 10 review dataframe

- Step 10 partitioning logic remains unchanged except for already-agreed naming
  cleanup from `sciscinet` to `ssn` where applicable. Do not change which
  namekeys land in subset 1 or subset 2 as part of the review-display fix.
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
  `tests/test_sciscinet_name_matching.py`.
- Add/maintain step 10 tests proving review rows aggregate all available
  context, including placeholder rows, JSON-typed values, multiline delimiter
  behavior, generic provenance fields, and SSN author-id special handling.
- Run focused matching and step 10 tests after implementation.
- Run `pixi run pre-commit` when done. If unrelated existing failures remain,
  record them precisely in `WORK.md` and the final response.
