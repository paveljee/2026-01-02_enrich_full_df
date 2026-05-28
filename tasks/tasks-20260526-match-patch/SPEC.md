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
          '[^[:alnum:]]+',
          '',
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

- Honor all inherited prerequisites and setup from
  `/tasks/tasks-20260519-review-231/SPEC.md`.
- Review the relevant codebase, especially the path that would be involved in
  `pixi run python -m src.repl --config config.repl.json --new`, but do not run
  that command.
- Do not use `src.repl` at all. The full pipeline command is explicitly
  disallowed and is expected not to execute in this environment because the
  external resources are unavailable.
- Assume that the full pipeline command has already been run with the current
  `config.repl.json`, meaning current subset mode 2. If database evidence is
  needed, use only `data/scisci_process.duckdb`, and open it only in read-only
  mode.
- For any data/context verification, the read-only DuckDB file is the single
  source of truth. Do not touch or look for any other generated artifacts.
- It is allowed to re-review repo code and configuration such as `src/`,
  `config.repl.json`, and `tests/`, but do not inspect data files or `.aicode/`.
- Code edits are allowed only after the implementation path is understood well
  enough to be ready to make the change.
- Git usage must remain read-only: do not stage, unstage, commit, reset, or
  otherwise mutate git state.
- Use `tasks/tasks-20260526-match-patch/WORK.md` as the task-local workbook.
  Keep it concise and organized for a busy tech lead and future executor,
  recording intended actions, in-progress work, completed work, verification,
  other useful notes, and relevant blockers or caveats.
- The implementation goal is a narrow code-and-test patch set that improves
  matching and review data, not an exploratory data rewrite.
- Add two config booleans, both defaulting to `false` in `config.repl.json`:
  - `xlsx_match_name_tokens_v2`
  - `sciscinet_match_strip_tokens`
- The XLSX knob preserves existing v1 behavior when false. When true, XLSX name
  matching switches to a shared token-sequence comparator for first and last
  names:
  - before tokenization, lowercase/unaccent as appropriate to current matching,
    then replace every punctuation sequence and whitespace sequence in first and
    last names with one space;
  - tokenize both first and last names, strip leading/trailing spaces from all
    tokens on both sides, and drop empty tokens;
  - first-name token sequences must match, and last-name token sequences must
    match;
  - if exact token-sequence matching fails, try the compact-initials rule in
    either direction, where a run of two or more single-letter tokens on one side
    may match one token on the other side equal to those initials joined either
    with no separator or with a single space, with order and total token coverage
    still exact;
  - if that fails, try the same-length initial-expansion rule in either
    direction, where a single-letter token may match a token at the same position
    that starts with that letter, while all other positions match exactly;
  - the fallback rules apply to both first-name and last-name matching, and exact
    token order/count constraints must be preserved.
- XLSX tests must cover both v1 and v2, including the stated positive and
  negative edge cases. The tests should use pytest and DuckDB directly, importing
  the actual matching def or registration/helper from `src/` so the pipeline and
  tests share the same logic.
- The SciSciNet knob preserves current exact normalized display-name matching
  when false. When true, it changes only token/string edge handling by stripping
  leading and trailing whitespace from compared tokens/strings before equality.
- SciSciNet tests should mirror the XLSX testing style: pytest, DuckDB directly,
  actual imported matching mechanism from `src/`, and coverage proving v1 rejects
  leading/trailing whitespace while v2 accepts it without adding unrelated XLSX
  punctuation or initials behavior.
- DOCX matching behavior remains unchanged, but add direct pytest/DuckDB tests
  around the actual imported DOCX matching mechanism so the existing
  normalization and containment behavior is pinned.
- Put these matching unit tests in three dedicated files under `tests/`: one
  file for XLSX matching, one file for DOCX matching, and one file for SciSciNet
  matching.
- For `10_build_cards_card_partition_review_df.csv`, the review dataframe should
  no longer show only singleton/one-available innerdict values for cross-domain
  context. For each review column, collect all available values from the relevant
  DOCX, XLSX, and/or SciSciNet innerdicts for the same source key, depending on
  the column's domain. Merge multiple values inside the cell. If none of the
  values contains multiline text, separate them with one newline. If any value is
  multiline, separate values with a line containing `-----`.
