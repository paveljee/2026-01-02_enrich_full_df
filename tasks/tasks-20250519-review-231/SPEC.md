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
in the order
from easiest/quickest to resolve
to the most complex/time-draining entries.

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
1. this second ktp.partition
should assume that the ones from
the higher tier ktp.partition have been resolved.
so, out of the remaining ones,
we want to see  the ones that
fail to qualify due to docx innerdict issues
(i.e., any empty required ktp.table_1_* value or
no docx innerdict present at all).
so this again involves two ktp partition flags,
let's call them:
`ktp.partition_flag_docx_table_1_required_all`
a bitwise flag false if any required ktp.table_1_* value is empty; and
`ktp.partition_flag_docx_any`,
false if no docx innerdict present at all.
be sure to centralize these labels in vars.py.
1. finally,
exclusive of first two higher tier ktp partitions,
we want to see all the remaining ones,
that is, remaining should be only those that have
zero or >1 sciscinet innerdict,
**in the order from fewer sciscinet innerdicts
to more sciscinet innerdicts**
(that is, the fewer the count of
sciscinet innerdicts the higher
the ktp partition priority because
those with fewer sciscinet innerdicts
will be easier for human to review and
manually resolve).
accordingly,
this involves one flag which we'll call:
`ktp.partition_flag_sciscinet_count`
which contains count of sciscinet innerdicts and
so we give it type of int rather than bool.
centralize this label in vars.py.

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
  as specified above in "solution"
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
    - ktp docx partition flags
    (these are per namekey so
    will be same for each innerdict
    within outerdict entry)
    - ktp.docx_match
    - all required ktp table 1 cols
    - ktp sciscinet count flag
    (this is per namekey so
    will be same for each innerdict
    within outerdict entry)
    - ktp.ssnad_match
    - ktp.ssn_sum_hit_1pct
    - ssnad.works_count
    - ssnad.cited_by_count
    - ssnad.works_api_url

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

### confirmed repo/db context

- I did not run `src.repl`; I queried `data/scisci_process.duckdb`
  directly in read-only mode.
- Current `config.repl.json` has `card_subset_mode = 2` and
  `db_file = data/scisci_process.duckdb`.
- Step 10 is `src/steps/step_10_build_cards.py`. The current subset
  logic is in the nested `_filtered_outer_dict()` helper and works from
  `context.outer_dict`, which by step 10 contains rows appended from:
  - `xlsx_innerdicts`
  - `docx_innerdicts`
  - `ssn_innerdicts` during a fresh run
- Existing persistent source tables relevant to this task are:
  - `outerdict_stub` / `outerdict_name_keys`
  - `xlsx_innerdicts`
  - `docx_innerdicts`
  - `ssn_innerdicts`
  - row-wise output views/tables such as `xlsx_output`, `docx_output`,
    and `ssn_parquet_output`
- The row-wise `xlsx_output` and `docx_output` views depend on
  `unaccent`; in the real pipeline connection this is loaded by
  `PipelineManager.connect_db()`. For the audit counts below, I used the
  persisted innerdict tables so the counts do not depend on re-running
  those views.

### confirmed counts

Using the current subset semantics from `step_10_build_cards.py`:

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

The requested mutually exclusive subset-2 queue should break down as:

| ktp.partition meaning | namekeys |
|---|---:|
| xlsx tier | 31 |
| docx tier | 46 |
| sciscinet tier | 154 |
| total | 231 |

Important audit detail: the 82 xlsx failures are not all xlsx-only
resolution cases. Under the mutually exclusive queue, they distribute as:

| bucket containing xlsx failures | namekeys |
|---|---:|
| xlsx tier | 31 |
| docx tier | 10 |
| sciscinet tier | 41 |
| total xlsx failures | 82 |

So the implementation should keep the 82 fail count as an audit flag,
but only 31 namekeys belong in the first/manual xlsx-only partition.

### partition semantics to implement

The new table should contain exactly the 231 subset-2 namekeys, one row
per namekey, with all partition flags persisted as audit columns.

Interpret `ktp.partition` as the mutually exclusive queue bucket, not as
a raw OR of every boolean/int flag. A simple ordered bit code is fine:

| value | meaning | priority |
|---:|---|---:|
| 1 | xlsx tier | 1 |
| 2 | docx tier | 2 |
| 4 | sciscinet tier | 3 |

Keep the raw flags separate so the bit/flag state can be audited without
overloading `ktp.partition`.

Per-namekey flags:

- `ktp.partition_flag_xlsx_any`
  - true when at least one present/nonblank `ktp.xlsx_match` payload
    exists under the namekey.
  - In the current DB this is true for all 307 namekeys, but implement
    the false case because the spec asks for it.
- `ktp.partition_flag_xlsx_non_exact_any`
  - true when any present `ktp.xlsx_match` payload is non-exact by the
    existing `_is_exact_xlsx_match_payload()` rules.
  - Exactness means source-key first-name token list equals matched HCR
    first-name token list, and source-key last-name norm equals matched
    HCR last-name norm.
  - Invalid JSON, non-dict JSON, or missing normalized source-key tokens
    should be treated as non-exact, matching current step 10 behavior.
- `ktp.partition_flag_docx_any`
  - true when at least one docx innerdict exists under the namekey.
  - In the current DB this is true for all 307 namekeys, but implement
    the false case.
- `ktp.partition_flag_docx_table_1_required_all`
  - to preserve the confirmed subset-2 count of 231, interpret this in
    line with current subset 1 logic: true when there is at least one
    docx innerdict whose required `ktp.table_1_*` fields are all
    non-empty.
  - Required fields are all `ktp.table_1_*` columns except:
    `ktp.table_1_socioeconomic_status`,
    `ktp.table_1_race_ethnicity_language_culture`,
    `ktp.table_1_topics`,
    `ktp.table_1_footnotes`,
    `ktp.table_1_comments`.
  - Empty means NULL, blank string, or one of the existing placeholders
    in `KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS`.
  - Caution: a literal "all docx rows must be complete" interpretation
    changes the DB result to subset 2 = 232, not 231. The two affected
    namekeys are Tom Beeckman and Zhiqun Lin. Do not switch to that
    stricter interpretation without human sign-off.
- `ktp.partition_flag_sciscinet_count`
  - integer count of sciscinet innerdicts under the namekey, using the
    same sciscinet row source as current step 10. In the persisted DB,
    this is `COUNT(*)` from `ssn_innerdicts` grouped by `ktp.source_key`.

Partition assignment:

```text
subset1_ok =
    sciscinet_count == 1
    and xlsx_any
    and not xlsx_non_exact_any
    and docx_table_1_required_all

if subset1_ok:
    exclude from the new table/view
elif sciscinet_count == 1
     and docx_table_1_required_all
     and (not xlsx_any or xlsx_non_exact_any):
    ktp.partition = 1  # xlsx tier
elif sciscinet_count == 1
     and not docx_table_1_required_all:
    ktp.partition = 2  # docx tier
else:
    ktp.partition = 4  # sciscinet tier
```

This assignment is intentionally hierarchical. Namekeys that have both
xlsx and docx problems are docx-tier once the xlsx tier is conceptually
handled, which is why 10 xlsx failures are counted in the docx tier.
After excluding xlsx and docx tiers, the remainder is exactly the
zero-or-many sciscinet bucket.

### implementation shape

Add constants in `src/helpers/vars.py`:

- `KTP_PARTITION_COL = "ktp.partition"`
- `KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL =
  "ktp.partition_flag_xlsx_non_exact_any"`
- `KTP_PARTITION_FLAG_XLSX_ANY_COL =
  "ktp.partition_flag_xlsx_any"`
- `KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL =
  "ktp.partition_flag_docx_table_1_required_all"`
- `KTP_PARTITION_FLAG_DOCX_ANY_COL =
  "ktp.partition_flag_docx_any"`
- `KTP_PARTITION_FLAG_SCISCINET_COUNT_COL =
  "ktp.partition_flag_sciscinet_count"`
- `KTP_FF_DISCARD_COL = "ktp.ff_discard"`
- `KTP_FF_NOTE_COL = "ktp.ff_note"`
- Optional but useful: partition value constants for xlsx/docx/sciscinet
  and a display/order mapping.

Add table/view constants in `src/helpers/schema.py`; suggested names:

- `SUBSET2_PARTITION_TABLE = "subset2_partitions"`
- `SUBSET2_PARTITION_REVIEW_VIEW = "subset2_partition_review"`

In `src/steps/step_10_build_cards.py`:

- Pull the existing xlsx exactness, xlsx-present, docx required-field,
  and sciscinet-count helpers out of `_filtered_outer_dict()` enough that
  both card filtering and partition materialization use one definition.
- Before building cards, compute a partition dataframe/table for all
  namekeys and persist only the non-subset-1 rows to
  `SUBSET2_PARTITION_TABLE`.
- Keep the existing card subset behavior unless the product decision is
  to replace cards entirely. With current config, cards should still be
  built from subset mode 2, and the new table/view/CSV are additional
  step-10 artifacts.
- Create `SUBSET2_PARTITION_REVIEW_VIEW` with the same queue ordering and
  the human-review columns requested in the human section.
- Load `SELECT * FROM SUBSET2_PARTITION_REVIEW_VIEW` into a DataFrame and
  include it in `StepResult.artifacts`, e.g. under
  `subset2_partition_review_df`; `run_step.dump_artifacts()` will then
  dump it as a CSV step artifact automatically.

Recommended ordering:

```text
ORDER BY
    partition priority: xlsx, docx, sciscinet,
    CASE WHEN partition is sciscinet THEN sciscinet_count ELSE 0 END,
    draw ordering compatible with shared.draw_sort_ctes_sql(),
    ktp.source_key,
    ktp.filename,
    ktp.fragment
```

The sciscinet tier must be sorted from fewer sciscinet innerdicts to
more. Current subset-2 sciscinet counts include 39 namekeys with zero
sciscinet rows, 49 with two, 18 with three, and a long tail up to very
large ambiguous candidate counts.

### review view row source

The breakdown table is one row per subset-2 namekey. The review view may
have multiple rows per namekey.

Use the row source that matches the mutually exclusive partition:

- xlsx tier: expand matching rows from `xlsx_output` or flattened
  `xlsx_innerdicts`; include the xlsx filename/fragment and HCR fields.
- docx tier: expand matching rows from `docx_output` or flattened
  `docx_innerdicts`; include all required `ktp.table_1_*` columns and
  `ktp.docx_match`.
- sciscinet tier: expand rows from `ssn_parquet_output` or
  `ssn_innerdicts`; include `ktp.ssnad_match`, `ktp.ssn_sum_hit_1pct`,
  `ssnad.works_count`, `ssnad.cited_by_count`, and
  `ssnad.works_api_url`.
- sciscinet count zero: still emit one placeholder review row so the
  source key is not lost. Populate source/name/draw and partition flags;
  leave filename/fragment and ssnad-specific fields NULL/blank.

For the human-editable columns, use empty typed fields in the view:

- `CAST(NULL AS BOOLEAN) AS "ktp.ff_discard"`
- `CAST(NULL AS VARCHAR) AS "ktp.ff_note"`

If the view expands rows this way, the current DB would produce about
2,873 review rows: 234 xlsx-tier rows, 46 docx-tier rows, and 2,593
sciscinet-tier rows including one placeholder for each zero-count
sciscinet namekey.

### tests to add

Add focused tests around the extracted partition helper rather than only
snapshotting CSV output:

- subset1 namekey is excluded from the new partition table.
- xlsx-only failure becomes partition 1.
- docx failure with xlsx pass becomes partition 2.
- combined xlsx+docx failure with sciscinet count 1 becomes partition 2,
  not partition 1.
- sciscinet count 0 and count >1 become partition 4 and sort by count
  ascending.
- missing xlsx/docx cases set `*_any` flags false.
- invalid/non-dict xlsx match payloads count as non-exact.
- multi-docx-row case preserves current subset semantics: if at least
  one docx row is complete, `docx_table_1_required_all` is true.
- artifact dumping includes the review DataFrame as a CSV through the
  existing `run_step.dump_artifacts()` path.
