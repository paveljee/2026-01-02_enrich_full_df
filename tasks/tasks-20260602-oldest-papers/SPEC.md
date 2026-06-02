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
ascending by year):

```
**ktp.ssn_top_oldest_papers**: [{"ssnp.year":...,"ktp.ssnp_paperid_url":"https://openalex.org/W1568216332"}, ...]
```

all relevant
manipulations with
paper parquet
should be properly logged
in `repl_session.log`.

## how ai understood the spec
