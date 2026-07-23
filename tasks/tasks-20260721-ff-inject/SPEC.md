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



we are incorporating a mechanism
to inject helpful values
from external jsonl files.
any number of jsonl files
may be supplied, but
they must be properly registered resources
in config json.

any of those jsonl files get the
resource group KTP_JSONL_INJECTION.
their fragment type is LINE_NUMBER.
in pipeline context, they get passed as
jsonl_resources of PipelineResources.

the following patterns are supported:

pattern 1

(e.g., file called `data/ktp_test_fill_na.jsonl` -
but can be any name really):

```jsonl
{
    "ktp.source_key": "{\"ktp.first_name\": \"Bin\", \"ktp.last_name\": \"Gao\"}",
    "ktp.table_1_place_of_residence": "4002 Jonsson Engineering Center, 49 College Ave, Troy, NY 12180, United States"
}
```

this pattern means that at
step 6 of main pipeline,
this is immediately injected
into the outerdict stub
by source key.
all injections must be meticulously
logged in repl session log
as well as of course the get a
separate section in the final card
(i.e., in this example
there will be a subsection with
ktp.filename ktp_test_fill_na.jsonl
where a single "ktp.table_1_place_of_residence" item will be).
of course in diagnostics and
in step artifacts this is also reflected
everywhere as appropriate.
so this pattern does not interact with
match xlsx, docx, or parquet
(steps 7-9).

pattern 2

(e.g., file called `data/ktp_test_discard.jsonl` -
but can be any name really):

```jsonl
{
    "ktp.source_key": "{\"ktp.first_name\": \"Paul G\", \"ktp.last_name\": \"Richardson\"}",
    "ktp.ff_discard": {
        "ktp.filename": "2014_HCR.xlsx",
        "ktp.fragment": "2024"
    }
}
{
    "ktp.source_key": "{\"ktp.first_name\": \"Kuishuang\", \"ktp.last_name\": \"Feng\"}",
    "ktp.ff_discard": {
        "ktp.filename": "sciscinet_author_details.parquet",
        "ktp.fragment": "A5076843232"
    }
}
```

this means that the pipeline
should detect the appropriate
**registered resource** (by filename),
identify corresponding fragment type, and
try to use "ktp.fragment" as a fragment of that type
in the corresponding step
(that is,
step 7 if the identified registered resource is under xlsx_resources,
step 8 if under docx_resources, and
step 9 if under parquet_resources).
If this name and fragment are identified,
and uniquely identified,
the pipeline interprets the "ktp.ff_discard" directive
to discard the corresponding unique row.
this is meticulously logged in repl session log.
in the final card ()
this is recorded as a separate section
with filename, fragment type and fragment and
a message that this was discarded
using ktp.ff_discard directive
coming from (indicate jsonl filename,
fragment type - i.e., line number - and fragment).
of course this is also reflected in diagnostics/step artifacts.

## how ai understood the spec
