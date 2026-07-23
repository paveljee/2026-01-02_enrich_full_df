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

upon review `ssn_innerdicts` table schema
does not follow the schema of
`docx_innerdicts` and `xlsx_innerdicts`,
in particular should be only
`name_key` and `innerdicts`.

also, in fact these should have been:

- `ktp.source_key`
- `ktp.innerdicts`

let's scope the minimal changes
needed to address these comprehensively and
what this will impact in the system.

## how ai understood the spec
