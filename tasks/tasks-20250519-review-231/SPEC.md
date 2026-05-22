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
assume that the value of this field
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
- note that the values of the
  following three fields
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
- ktp xlsx partition flags
- ktp.xlsx_match
- ktp docx partition flags
- ktp.docx_match
- all required ktp table 1 cols
- ktp sciscinet count flag
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

