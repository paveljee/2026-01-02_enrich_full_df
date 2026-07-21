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
build a tiny new detour.
review existing ones to see how they work.
the most important bit is that
they are inspired by some components of the main pipeline
yet are completely standalone in operation.

the detour does one simplest thing:
user passes --config and
--authorid together with it and
the detour prints to stdout
the exact replica of step 9 innerdict
for this authorid
(from --config, parquet registered resources are extracted)
from parquet resources directly.
this output should be identical
to the corresponding innerdict subsection
in a step 10 card, txt only.
reuse all same logic.

note: the detour actually replicates step 9
(not importing it - replicates the logic;
helpers may be imported),
just for a single authorid.
that is, there is only going to be
ktp.ssn* and ssn*  fields.

test data for constructing
end to end tests 
(to be put in a single
test module for the detour)
are here:
`data/test_data/detour_authorid_card/`

## how ai understood the spec

### outcome

Add the standalone command-line module `src.detours.detour_authorid_card`:

```bash
pixi run python -m src.detours.detour_authorid_card \
  --config config.repl.json \
  --authorid A5000000000
```

Both arguments are required. `--authorid` is an opaque exact-match string. On
success, stdout is exactly the corresponding step-10 TXT innerdict subsection,
with no surrounding card text or other output, and no file is written.

### implementation rule

The current `src/steps/step_09_match_parquet.py` is the implementation source of
truth. Start by copying that module to
`src/detours/detour_authorid_card.py`, then adapt the copy as lightly as
possible. Do not independently redesign or restate its SciSciNet SQL:

1. replace `PipelineContext`/outerdict/step orchestration with `--config`,
   `--authorid`, and an in-memory DuckDB connection;
2. treat `--authorid` as the already selected author, so remove the upstream
   name matching, candidate selection, hit-based author selection, and author
   confidence gates;
3. retain step 9's downstream SciSciNet retrieval, paper-level enrichment, final
   innerdict construction, ordering, and value formatting as literally as
   practical, scoped to that author ID; and
4. render that one innerdict subsection to stdout.

The detour must not import step 9. Continue importing the neutral helpers the
copied code needs, but do not refactor step 9 as part of this task. The executor
should be able to compare the two modules and see a copied, lightly adapted path
rather than a second interpretation of its behavior.

### detour-specific boundaries

Read only the SciSciNet parquet resources that the step-9 author output uses:
`author_details`, `authors`, `authors_paper`, `paper_author_affiliation`,
`affiliations`, `hit_papers_0`, `hit_papers_1`, `fields`, and `papers`.
Extract/register those entries from the supplied config without broad pipeline
resource registration.

Everything else is unused. Do not open `config.db_file`, pipeline state, HCR or
other source families, generated artifacts, OpenAlex logs/title data, or the
network. Do not create a persistent database or another output artifact.

The hit and paper relations remain part of the copied downstream enrichment;
they simply do not choose the author. In particular, do not carry across a
selection-stage rejection of the author supplied on the command line.

### innerdict and text shape

Take the copied step-9 final innerdict for the supplied author and retain its
SciSciNet-derived `ktp.ssn*` and `ssn*` body fields. Fields produced only by the
removed matching/selection/gate path are not retained or synthesized, even if a
name shares one of those prefixes. OpenAlex-only values are likewise absent.

`ktp.filename` remains the structural subsection heading. Reuse the existing
step-10/card formatting logic in the smallest practical way; this specification
does not define a second formatter. Existing card output must remain
byte-identical. Build the complete text before writing stdout so an error cannot
leave partial output.

### failures and implementation boundary

The module remains standalone: it must not import `src.repl`, `src.steps`,
pipeline initialization/runtime orchestration, or another detour. It may import
neutral `src.helpers` code. Keep import side effects at zero and expose `main()`.

Argparse handles CLI misuse. Data/config failures are concise, nonzero, stderr
only, with empty stdout. Preserve the copied step-9 behavior wherever the
detour-specific boundaries above do not require a change. No new dependency is
expected. Add concise README usage.

### tests and acceptance

Put all detour tests in
`tests/test_detours/test_detour_authorid_card.py`. Use the checked-in cards under
`data/test_data/detour_authorid_card/` to construct end-to-end cases that invoke
the CLI with an author ID and compare stdout with the corresponding SciSciNet
subsection projection.

The tests demonstrate exact text parity, preservation of the copied paper-level
step-9 result, direct-author behavior without author selection, and standalone
isolation from the pipeline DB, unused sources, and network. Keep any small
supporting cases in the same module. The fixtures and current step-9 behavior
are the oracle; do not reproduce step 9 as a separate expected-results
implementation inside the tests.

Run the focused module, the repository detour suite, and Ruff/mypy for touched
Python files.
