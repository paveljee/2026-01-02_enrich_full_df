## human written part - ai never touches this
### task title
Strategize re subset 2 resolution

### prerequisites and setup
review relevant code base
in particular everything that's involved
when running command
`pixi run python -m src.repl --config config.repl.json --new`.
DO NOT ATTEMPT TO RUN THE COMMAND.
you are disallowed to use src.repl at all.
this won't execute in your env anyway
because no access to resources here
so don't even try.
your goal will be different.

so when you've explored the repo sufficiently and
are confident that you understand what's going on
under the hood when this command is run,
appreciate the following:

this command has already been run, 
with current config.repl.json
(that is, in subset mode 2).
the db itself is here,
`data/scisci_process.duckdb`;
you may ONLY used it in READONLY mode.

that is to say,
all further SPEC details
that follow assume the following
workflow on your end,
use scisci_process.duckdb in READONLY mode ->
that's it.

you only work with the duckdb file
I mentioned above. You don't touch
or look for any other artifacts or whatnot.
The duckdb file is your single
and only source of truth.

You may re-review code of this repo
(i.e., `src/`, config json, `tests/` etc
but not data files,
e.g., not `data/` or `.aicode/`),
**in readonly mode,**
as appropriate/you feel you need.

You may **edit** the code
as appropriate to achieve the **goal**
(as specified below), but **only**
once you've got to the stage
where you are actually ready to do so.

git usage:
you may not stage/unstage anything in git;
only readonly use of git is allowed.

### the problem
ideally we would like
all 310 (100%) of drawn samples
of outerdict entries to
qualify under subset 1.
only those that qualify
are taken up by downstream
tasks (that is, how outputs of
this pipeline are used -
outside of this repo).

sadly,
some outerdict entries fail to
qualify under subset 1 and
as such, 
these impeding factors
need to be intentionally resolved to
bring them in compliance with subset 1.

What resolve means:
ensure that all innerdicts
under a given namekey
truly refer to the
researcher that the namekey represents, so
remove incorrectly matched innerdicts.

these failing compliance entries are
obviously under subset 2,
which is the complement of subset 1.

subset 2,
by its definition,
includes outerdict entries with
varying degree of ease to resolve.

### solution
we need to reorder the 
subset 2 outerdict entries in
a queue for downstream
(outside of this repo)
**manual resolution by humans***
in the order that
enables the best combo of
"quickest to review" and
"quickest to dispatch", with
the ultimate goal of dispatching
subset 2 entries gradually
downstream asap.

To do this reordering,
we need to understand
how many namekeys we have that
contain at least one innerdict
with the following, 
in the following priority subcategories,
from highest to lowest
(let's call the subcategories `ktp.partition` -
put this into vars.py;
assume that the value of this field,
defined per namekey,
will be the result of bitwise operation on
over all `ktp.partition_flag_*` fields,
each of which will be one bit 
usually, or int as necessary -
see below):

1. xlsx innerdict 
matched inexactly, and
_if_, say,
after human manual resolution
this match was assumed to
be correct (i.e., resolved),
then the namekey would
qualify under subset 1.
So basically those namekeys where
only an/several unresolved xlsx innerdict
(i.e., any non-exact ktp.xlsx_match or
no present ktp.xlsx_match at all)
prevents it from being in subset 1.
so this involves two ktp partition flags, let's call them:
`ktp.partition_flag_xlsx_non_exact_any`
a bitwise flag true if has any non-exact ktp.xlsx_match; and
`ktp.partition_flag_xlsx_any`,
false if no ktp.xlsx_match are present at all.
be sure to centralize these labels in vars.py.
to be sure,
entries in this ktp partition
should have all other conditions of
subset 1 fulfilled other than
the xlsx bits.
1. this second ktp.partition
should assume that the ones from
the higher tier ktp.partition have been resolved.
so, out of the remaining ones,
we want to see  the ones that
fully qualify under all xlsx conditions,
fully qualify under all docx conditions, 
but have zero or >1 sciscinet innerdict,
**in the order from fewer sciscinet innerdicts
to more sciscinet innerdicts**
(that is, the fewer the count of
sciscinet innerdicts the higher
the ktp partition priority because
those with fewer sciscinet innerdicts
will be easier for human to review and
manually resolve;
if ties need to be broken 
for the same sciscinet innerdict count,
move up entries with sciscinet only failure
but without xlsx failure, and
those that have both sciscinet and xlsx failure
should trail but within the same
sciscinet innerdict count).
accordingly,
this involves one flag which we'll call:
`ktp.partition_flag_sciscinet_count`
which contains count of sciscinet innerdicts and
so we give it type of int rather than bool.
centralize this label in vars.py.
1. finally,
exclusive of first two higher tier ktp partitions,
we want to see all the remaining ones,
that is, remaining should be only those that
fully qualify under all xlsx and sciscinet but
fail to qualify due to docx innerdict issues
(i.e., any empty required ktp.table_1_* value or
no docx innerdict present at all).
so this again involves two ktp partition flags,
let's call them:
`ktp.partition_flag_docx_table_1_required_all`
a bitwise flag false if any required ktp.table_1_* value is empty
within the given innerdict; and
`ktp.partition_flag_docx_any`,
false if no docx innerdict present at all.
be sure to centralize these labels in vars.py.
just to be sure,
we honour the same logic as in step 10 currently
as it concerns across-innerdict reasoning for docx,
namely that if
a namekey has _at least one_ docx innerdict 
in which ALL required ktp.table_1_* value are non-empty,
then this is sufficient for
`ktp.partition_flag_docx_table_1_required_all` and
it is set to true.

so to recap,
the logical order is:
- resolve those
only encumbered by xlsx, and
here we go they are complete -
dispatch them downstream;
- of those that remain,
resolve those only encumbered by sciscinet
(first resolve those that have fewer
sciscinet innerdicts to check, then
those that have progressively more) -
dispatch downstream;
- and so only those remain that
don't have any docx innerdicts
with all required fields filled in,
or no docx innerdicts at all;
these will need to undergo
data augmentation before they can be
dispatched downstream, unlike
the higher tiers that only required
conflict resolution based on existing data, and
so these are the most complex ones
kept for the end.

as a result,
we should get a nice breakdown
(long format):

| ktp.source_key | ktp.partition | _one ktp partition flag..._| _another ktp partition flag..._ | ... | _last one of ktp partition flags..._|
|---|---|---|---|---|---|
| _value of..._ | _calculated across all flags bitwise op value of_ | _value of..._ | _value of..._ | _value of..._ |

for a total of 231 namekeys.
this will allow efficient resorting
moving forward.
note that
all ktp partitition flags
will therefore be boolean
with the exception of
`ktp.partition_flag_sciscinet_count`
which will be int
(and of course can be zero).

### the goal
at step 10
of main repl,
refactor the current
subsetting mechanism 
implementing the solution above.
at the end of the mechanism
this will produce a persistent
new _table_ in duckdb which
will contain the 
long format breakdown table
exemplified above, and
appropriately ordered 
also as described above.

there must also be created
a _view_ that will contain
the same info and
ordering but also
show the following informative columns
that will help humans review,
in the following order of columns
from left to write:

- ktp.source_key
- ktp.partition
- note that the values of the
  following fields
  must depend on the mutual
  exclusiveness of ktp.partition
  as described above, so
  for example if the namekey falls into
  the ktp partition associated
  with xlsx then use values from 
  xlsx, and if in the lower tier
  parition associated with docx
  then from docx;
  of course this means that in this view,
  there may be multiple rows 
  per same source key and it's ok
  as long as ordering is made 
  as specified above in "solution";
  some special cases are 
  where there is a single matching value
  (that is, be it xlsx or sciscinet), and
  in that case we may print the values
  in the respective field - for example,
  say we have a row that represents a
  sciscinet author id but the given
  ktp namekey only has a single
  xlsx match - in that case we do
  fill in the hcr category field etc.
    - ktp.filename
    - ktp.fragment
    - ktp.fragment_type
    - ktp.ff_discard
    (this will be an empty field -
    be sure to add label to vars.py;
    ff_discard means bitwise var
    true if this filename-fragment entry
    is to be discarded;
    humans will review entries and
    put boolean values in this field;
    these will be used up by some logic
    that we'll implement in the future;
    for now just offer this empty field)
    - ktp.ff_note
    (this will be an empty field -
    be sure to add label to vars.py;
    ff_note means text var where
    humans may add any notes for
    this filename-fragment entry;
    humans will review entries and
    put str values in this field;
    these will be used up by some logic
    that we'll implement in the future;
    for now just offer this empty field)
    - ktp.draw_number
    - ktp.first_name
    - ktp.last_name
    - ssnad.display_name
    - ssnad.display_name_alternatives
    - hcr.category
    - ktp.ssn_field_display_names_list
    - ktp.hcr_world_bank_economies
    - ktp.hcr_world_bank_economies_match
    - ktp.hcr_primary_affiliations
    - ktp.hcr_secondary_affiliations
    - ktp.ssn_top_institutions
    - ktp xlsx partition flags
    (these are per namekey so
    will be same for each innerdict
    within outerdict entry)
    - ktp.xlsx_match
    - ktp sciscinet count flag
    (this is per namekey so
    will be same for each innerdict
    within outerdict entry)
    - ktp.ssnad_match
    - ktp.ssn_sum_hit_1pct
    - ssnad.works_count
    - ssnad.cited_by_count
    - ssnad.works_api_url
    - ktp docx partition flags
    (these are per namekey so
    will be same for each innerdict
    within outerdict entry)
    - ktp.docx_match
    - all required ktp table 1 cols

this view should be dumped
as csv step artifact.

be sure to centralize the
new table and view names
in schema.py.

### approach
You will see that
(and when i say "you will see"
interpret this as you must confirm
this via direct SQLing the duckdb, and
if what you find is different then
get back to human immediately for debrief)
subset 2 contains
231 namekeys with
their innerdicts.

you will also see that:

Rule                                           Pass   Fail
----------------------------------------------------------
xlsx: all present ktp.xlsx_match exact          225     82

which means that 82 namekeys
were not matched simply because
the xlsx match is inexact.

you take it from there.

## how ai understood the spec

### operating constraints and implementation contract

Do not run `src.repl`. The data source for confirming this spec is only
`data/scisci_process.duckdb`, opened read-only. Code, config, and tests
may be read as needed; do not inspect other `data/` or `.aicode/`
artifacts. Git usage remains read-only: no staging, unstaging, reset, or
checkout operations.

Step 10 should be refactored without making the new artifact names or
code path specific to `card_subset_mode = 2`. The current config uses
mode 2, so the current concrete output is the 231-namekey subset-2
resolution queue, but the implementation should not create
mode-2-specific schema names or otherwise assume that the REPL can only
be run in mode 2.

The partition/breakdown/review-view logic described here applies only
when `card_subset_mode` is 1 or 2, because it is specifically about
subset-1 qualification and the subset-2 complement. For any other
supported `card_subset_mode`, keep the existing card-selection/building
behavior and skip this partition artifact logic entirely.

Separate three concerns:

1. Compute per-namekey rule state for all outerdict keys: xlsx state,
   docx state, and sciscinet count.
2. Select the card subset using the existing `card_subset_mode` behavior.
3. If the selected mode is 1 or 2, materialize partition artifacts:
   subset-1 rows get the no-resolution sentinel, while subset-2 rows get
   a manual-resolution `ktp.partition` bucket. If the selected mode is
   anything else, stop after normal card subset selection/building.

For the current mode-2 run, every selected row is a subset-2 row and the
queue priority is:

1. xlsx tier: dispatch after resolving only xlsx match ambiguity.
2. sciscinet tier: dispatch after resolving sciscinet ambiguity; sort by
   fewer sciscinet innerdicts first.
3. docx tier: keep for last because these require data augmentation, not
   only conflict resolution over existing rows.

Within the sciscinet tier, ties on `ktp.partition_flag_sciscinet_count`
should put raw sciscinet-only failures before raw xlsx+sciscinet
failures. Raw flags stay visible; `ktp.partition` is the selected queue
bucket, not a lossless encoding of every raw problem.

### source-of-truth semantics

Reuse existing step-10 semantics rather than creating parallel rule
logic. Current subset 1 is:

```text
xlsx_ok and docx_ok and sciscinet_ok
```

where:

- `xlsx_ok`: at least one present `ktp.xlsx_match` payload exists, and
  all present xlsx match payloads are exact. Reuse the behavior currently
  implemented by `_has_present_xlsx_match_payload` and
  `_is_exact_xlsx_match_payload` in `src/steps/step_10_build_cards.py`.
- `docx_ok`: at least one docx innerdict exists, and at least one docx
  innerdict has all required `ktp.table_1_*` values non-empty. Reuse the
  current `_has_complete_docx_table_fields` behavior.
- `sciscinet_ok`: exactly one sciscinet innerdict exists under the
  namekey, using the same sciscinet row detection/count source as step
  10.

Keep repo-owned definitions centralized. In particular, docx requiredness
should derive from `KTP_DOCX_TABLE_1_PREFIX`,
`KTP_DOCX_OPTIONAL_EMPTY_COLS`, and
`KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS` in `src/helpers/vars.py`, not from
a duplicated literal required-column list.

### repo/db context

- Current `config.repl.json` uses `card_subset_mode = 2` and
  `db_file = data/scisci_process.duckdb`.
- Step 10 is `src/steps/step_10_build_cards.py`; it filters
  `context.outer_dict`, which is populated by earlier steps from the
  persisted `xlsx_innerdicts`, `docx_innerdicts`, and `ssn_innerdicts`
  tables.
- Useful persisted DB relations for this refactor are
  `outerdict_stub` / `outerdict_name_keys`, `xlsx_innerdicts`,
  `docx_innerdicts`, `ssn_innerdicts`, `xlsx_output`, `docx_output`, and
  `ssn_parquet_output`.
- Review-view SQL may reference views that call `unaccent`; direct
  read-only DuckDB checks should run `LOAD splink_udfs;` before querying
  those views. Normal pipeline connections load this extension in
  `PipelineManager.connect_db()`.

### verified mode-2 counts

Current DB totals under current step-10 semantics:

| item | count |
|---|---:|
| outerdict namekeys | 307 |
| subset 1 namekeys | 76 |
| subset 2 namekeys | 231 |
| xlsx rule pass | 225 |
| xlsx rule fail | 82 |
| docx rule pass | 207 |
| docx rule fail | 100 |
| sciscinet exactly-one pass | 153 |
| sciscinet exactly-one fail | 154 |

Raw subset-2 failure combinations:

| raw failing condition(s) | namekeys |
|---|---:|
| xlsx only | 31 |
| sciscinet only | 66 |
| docx only | 36 |
| xlsx + sciscinet | 34 |
| xlsx + docx | 10 |
| docx + sciscinet | 47 |
| xlsx + docx + sciscinet | 7 |
| total subset 2 | 231 |

Mode-2 queue implied by the human section:

| ktp.partition meaning | included raw groups | namekeys |
|---|---|---:|
| xlsx tier | xlsx only | 31 |
| sciscinet tier | sciscinet only; xlsx + sciscinet | 100 |
| docx tier | docx only; xlsx + docx; docx + sciscinet; xlsx + docx + sciscinet | 100 |
| total |  | 231 |

Sciscinet-tier tie-break classes:

| class | namekeys |
|---|---:|
| sciscinet only | 66 |
| xlsx + sciscinet | 34 |
| total | 100 |

### table fields and constants

Use mode-agnostic table/view names centralized in
`src/helpers/schema.py`. The human spec requires a persistent table and
a review view, but does not prescribe their literal names. Choose
generic, current-mode-neutral constants that fit the existing
`schema.py` naming pattern, for example `CARD_PARTITION_TABLE` and
`CARD_PARTITION_REVIEW_VIEW`. Do not use `subset2_*` names: the same
step-10 code must remain runnable under any supported
`card_subset_mode`, even though these schema objects are only
materialized for modes 1 and 2.

Add/centralize these labels in `src/helpers/vars.py`:

- `KTP_PARTITION_COL = "ktp.partition"`
- `KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL =
  "ktp.partition_flag_xlsx_non_exact_any"`
- `KTP_PARTITION_FLAG_XLSX_ANY_COL =
  "ktp.partition_flag_xlsx_any"`
- `KTP_PARTITION_FLAG_SCISCINET_COUNT_COL =
  "ktp.partition_flag_sciscinet_count"`
- `KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL =
  "ktp.partition_flag_docx_table_1_required_all"`
- `KTP_PARTITION_FLAG_DOCX_ANY_COL =
  "ktp.partition_flag_docx_any"`
- `KTP_FF_DISCARD_COL = "ktp.ff_discard"`
- `KTP_FF_NOTE_COL = "ktp.ff_note"`

The persistent breakdown table should be one row per selected namekey
and should include, at minimum, `ktp.source_key`, `ktp.partition`, and
all five `ktp.partition_flag_*` columns named above. `card_subset_mode`
metadata is optional but useful for later inspection because modes 1 and
2 share the same generic table name.

Use named partition-value constants in `src/helpers/vars.py` or the
nearest existing constants module. The human spec requires bit-like,
mutually exclusive queue buckets but does not prescribe exact numeric
values. Define named values for these meanings:

| partition meaning | use |
|---|---|
| xlsx tier | selected row is queued for xlsx-only manual resolution |
| sciscinet tier | selected row is queued for sciscinet manual resolution |
| docx tier | selected row is queued for docx/data-augmentation work |
| no-resolution sentinel | selected row already satisfies subset 1; in this spec, materialized only for mode 1 |

The resolution values should be bit-like labels for mutually exclusive
queue buckets. Do not OR the raw flags together: raw conditions are not
mutually exclusive, and `ktp.partition_flag_sciscinet_count` is an
integer count. Tests should assert partition meanings through the named
constants rather than literal numeric values.

### partition assignment

For modes 1 and 2, compute raw flags per namekey, select rows using the
configured `card_subset_mode`, then assign one partition value to each
selected row:

```text
xlsx_ok = xlsx_any and not xlsx_non_exact_any
docx_ok = docx_any and docx_table_1_required_all
sciscinet_ok = sciscinet_count == 1
subset1_ok = xlsx_ok and docx_ok and sciscinet_ok

if subset1_ok:
    ktp.partition = NO_RESOLUTION_PARTITION  # selected but no resolution needed
elif not xlsx_ok and docx_ok and sciscinet_ok:
    ktp.partition = XLSX_PARTITION
elif docx_ok and not sciscinet_ok:
    ktp.partition = SCISCINET_PARTITION
else:
    ktp.partition = DOCX_PARTITION
```

For the current mode-2 run, no subset-1 rows are selected, so the table
contains 231 rows with counts 31 xlsx, 100 sciscinet, and 100 docx. If
mode 1 is selected, selected rows satisfy subset 1 and should receive
the no-resolution sentinel. Modes other than 1 or 2 should not write the
partition table/view, should not apply partition ordering, and should not
write mode-specific schema objects such as `subset2_*`.

### implementation shape

In `src/steps/step_10_build_cards.py`:

- Extract the current subset-rule helpers out of `_filtered_outer_dict()`
  enough that card filtering and partition materialization use the same
  definitions.
- For modes 1 and 2, compute rule/partition rows before card building
  and persist rows for the currently selected card subset to the generic
  partition table constant in `src/helpers/schema.py`.
- For modes other than 1 or 2, skip partition-row persistence and review
  view creation; card generation should behave as it does now.
- Preserve existing card generation behavior unless separately changed;
  with the current config, cards are still built from subset mode 2.
- For modes 1 and 2, create the generic partition review view constant
  in `src/helpers/schema.py` and return its DataFrame in
  `StepResult.artifacts`, e.g. as `card_partition_review_df`, so the
  existing `run_step.dump_artifacts()` path writes the CSV artifact.

Recommended ordering:

```text
ORDER BY
    partition priority: xlsx, sciscinet, docx, no-resolution,
    CASE WHEN partition is sciscinet THEN sciscinet_count ELSE 0 END,
    CASE WHEN partition is sciscinet AND xlsx_ok THEN 0 ELSE 1 END,
    draw ordering compatible with shared.draw_sort_ctes_sql(),
    ktp.source_key,
    ktp.filename,
    ktp.fragment
```

The second sciscinet CASE implements the same-count tie-break: raw
sciscinet-only rows first, raw xlsx+sciscinet rows second. Current
sciscinet-tier distribution is 28 namekeys with zero sciscinet rows, 35
with two, 15 with three, and a long tail with larger candidate counts.

### review view

The breakdown table is one row per selected namekey. The review view may
have multiple rows per namekey, but its columns should follow the human
spec's requested order exactly:

1. `ktp.source_key`
2. `ktp.partition`
3. `ktp.filename`
4. `ktp.fragment`
5. `ktp.fragment_type`
6. `ktp.ff_discard`
7. `ktp.ff_note`
8. `ktp.draw_number`
9. `ktp.first_name`
10. `ktp.last_name`
11. `ssnad.display_name`
12. `ssnad.display_name_alternatives`
13. `hcr.category`
14. `ktp.ssn_field_display_names_list`
15. `ktp.hcr_world_bank_economies`
16. `ktp.hcr_world_bank_economies_match`
17. `ktp.hcr_primary_affiliations`
18. `ktp.hcr_secondary_affiliations`
19. `ktp.ssn_top_institutions`
20. xlsx partition flags:
    `ktp.partition_flag_xlsx_non_exact_any`,
    `ktp.partition_flag_xlsx_any`
21. `ktp.xlsx_match`
22. sciscinet count flag: `ktp.partition_flag_sciscinet_count`
23. `ktp.ssnad_match`
24. `ktp.ssn_sum_hit_1pct`
25. `ssnad.works_count`
26. `ssnad.cited_by_count`
27. `ssnad.works_api_url`
28. docx partition flags:
    `ktp.partition_flag_docx_table_1_required_all`,
    `ktp.partition_flag_docx_any`
29. `ktp.docx_match`
30. all required `ktp.table_1_*` columns, derived from the current repo
    constants/schema rather than a duplicated literal list

Every explicitly named human-spec column above should be emitted under
that exact label. Only the literal expansion of item 30 is delegated to
repo-owned definitions, because the human spec names the column family
but not the required-column list.

For human-editable fields, add empty typed columns in the requested
positions:

- `CAST(NULL AS BOOLEAN) AS "ktp.ff_discard"`
- `CAST(NULL AS VARCHAR) AS "ktp.ff_note"`

Values for row-scoped fields follow one global rule. The partition's
focus domain is exploded by row, so humans get one review row per
candidate value in the domain they are resolving. Every other domain is
singleton-filled: if that non-focus domain has exactly one linked
innerdict/value for the same `ktp.source_key`, fill its informative
columns; if it has zero or multiple linked values, leave those columns
empty.

The focus domain by partition is:

- xlsx tier: expand matching rows from `xlsx_output` or flattened
  `xlsx_innerdicts`; populate xlsx/HCR fields where available.
- sciscinet tier: expand rows from `ssn_parquet_output` or
  `ssn_innerdicts`; populate sciscinet/OpenAlex fields where available.
- sciscinet count zero: emit one placeholder review row so the source key
  stays visible; populate source/name/draw/flags and leave row-specific
  sciscinet fields empty.
- docx tier: expand matching rows from `docx_output` or flattened
  `docx_innerdicts`; populate docx/table-1 fields where available. If a
  future DB has no docx innerdict for a docx-tier namekey, emit one
  placeholder row with source/name/draw/flags.
- no-resolution rows, when mode 1 is selected, can be omitted from the
  review view or placed after all resolution buckets; mode-2 output is
  unaffected because mode 2 selects only resolution rows.

This global singleton-fill rule applies equally to excel-row review
rows, sciscinet author-id rows, and docx rows. For example:

- an xlsx-partition `excel_row` should show singleton sciscinet/OpenAlex
  and singleton docx/table-1 context when exactly one such linked row is
  available;
- a sciscinet-partition author row should show singleton HCR/xlsx and
  singleton docx/table-1 context when exactly one such linked row is
  available;
- a docx-partition row should show singleton HCR/xlsx and singleton
  sciscinet/OpenAlex context when exactly one such linked row is
  available.

In all cases, non-focus columns remain empty when that domain has zero or
multiple linked rows, because multiple linked rows would introduce
ambiguous context into a row whose purpose is to review a different
partition focus.

With the current mode-2 DB, this expansion produces 1,250 review rows:
234 xlsx-tier rows, 916 sciscinet-tier rows/placeholders, and 100
docx-tier rows.

### tests to add

Add focused tests around the extracted partition helper and review view:

- mode-2 run produces 231 partition rows for the fixture/current-style
  subset-2 inputs.
- mode-1 subset-1 rows get the no-resolution partition value.
- raw xlsx-only failure becomes the xlsx partition value.
- raw sciscinet-only failure becomes the sciscinet partition value and
  sorts by count.
- raw xlsx+sciscinet failure becomes the sciscinet partition value, keeps
  xlsx flags visible, and trails sciscinet-only rows with the same
  sciscinet count.
- raw docx-only failure becomes the docx partition value.
- raw xlsx+docx, docx+sciscinet, and xlsx+docx+sciscinet failures become
  the docx partition value with raw xlsx/sciscinet flags still visible.
- sciscinet count 0 emits a placeholder review row and sorts before count
  2+ rows.
- singleton non-primary context is populated in the review view, while
  ambiguous non-primary context remains empty.
- missing xlsx/docx cases set `*_any` flags false.
- invalid/non-dict xlsx match payloads count as non-exact.
- multi-docx-row case preserves current subset semantics: if at least
  one docx row is complete, `docx_table_1_required_all` is true.
- docx required-field tests derive required columns from repo constants,
  not a duplicated literal list.
- artifact dumping includes the review DataFrame as a CSV through the
  existing `run_step.dump_artifacts()` path.
