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

## how ai understood the spec
