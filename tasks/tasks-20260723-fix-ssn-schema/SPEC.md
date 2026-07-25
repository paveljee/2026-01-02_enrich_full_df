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

(but let's keep this migration
out of scope for now).

let's scope the minimal changes
needed to address these comprehensively and
what this will impact in the system.

**additional issue:**
(but let's keep it out of scope for now)
it has become clear throughout
the steps of the main pipeline that
jsonification of names -> source keys
and vice versa source keys -> names
is not done using duckdb.
preferably this would be addressed
such that all json serialization and
deserialization of source keys
should happen through duckdb.
add this to the consideration.

**of note:**
one change i've already made is this:

```
PARQUET_INNERDICT_TABLE = "ssn_innerdicts"
PARQUET_LEGACY_ROWS_INNERDICT_TABLE = "ssn_legacy_rows_innerdicts"
```

so the goal is to replace all
PARQUET_INNERDICT_TABLE  with
PARQUET_LEGACY_ROWS_INNERDICT_TABLE
first, to free PARQUET_INNERDICT_TABLE.

Then we should ensure
PARQUET_INNERDICT_TABLE is proper
suitable for `append_innerdicts_from_jsonlines_table`
just like xlsx and docx innerdicts tables are.

Then we must ask ourselves:
what downstream users depend on
PARQUET_LEGACY_ROWS_INNERDICT_TABLE now?
So, those that in good faith should
have made use of a jsonlines table,
we should migrate them to PARQUET_INNERDICT_TABLE
(the new one).
Those that just accidentally 
depended on the legacy rows table,
we may keep them on PARQUET_LEGACY_ROWS_INNERDICT_TABLE.

**other things that are worthy to note:**

- ssn innerdicts miss draw numbers, which is
not great because xlsx and docx have them and
it is better to have them. this is sincerely a
ssn schema inconsistency.
- while not directly related to step 9,
step 10 currently doesn't produce
artifacts for mode0.
this limits review of downstream reception of
step 9/ssn changes, and thus is
good to address.

## how ai understood the spec

### outcome and storage contract

This is a schema-and-boundary refactor. Do not change matching, SSN candidate
selection, subset assignment, card contents, or card ordering, apart from the
explicitly requested SSN draw-number consistency and mode-0 review artifacts.

After a new pipeline build, each of these persistent tables must have exactly
the same two columns, in this order:

| table | column 1 | column 2 |
|---|---|---|
| `xlsx_innerdicts` | `name_key` (`VARCHAR`) | `innerdicts` (`VARCHAR`) |
| `docx_innerdicts` | `name_key` (`VARCHAR`) | `innerdicts` (`VARCHAR`) |
| `ssn_innerdicts` | `name_key` (`VARCHAR`) | `innerdicts` (`VARCHAR`) |

`innerdicts` retains the existing XLSX/DOCX JSON Lines contract: one JSON
object per non-empty line, with the source key omitted from each object. A table
has at most one row for a source key and contains a row only when that source
key has at least one innerdict. Within a blob, preserve the same stable
filename/fragment/draw ordering used by the corresponding flat output.

The `ktp.source_key` / `ktp.innerdicts` label migration remains out of scope.
Keep the existing `name_key` / `innerdicts` labels and centralize them as the
shared table contract in `src/helpers/schema.py`.

This exact two-column contract is for the three named innerdict tables. Do not
mass-rename internal SQL `name_key` aliases or unrelated working relations such
as `outerdict_stub`; changing them is not needed to satisfy this task.

### current read-only baseline

The supplied `data/scisci_process.duckdb` currently shows:

| relation | persisted rows/source keys | represented innerdict rows |
|---|---:|---:|
| `xlsx_innerdicts` | 307 | 2,018 JSONL lines |
| `docx_innerdicts` | 307 | 317 JSONL lines |
| `ssn_innerdicts` | 2,044 wide rows / 304 distinct source keys | 2,044 rows |
| `ssn_parquet_output` | 2,044 wide rows | 2,044 rows |

Thus, with otherwise unchanged inputs, the refactored `ssn_innerdicts` should
have 304 rows containing 2,044 JSONL records, while
`ssn_parquet_output` should remain a 2,044-row wide view. Treat these as
read-only parity observations, not as universal fixture constants.

### one shared innerdict persistence path

Remove the current XLSX/DOCX-versus-SSN split in
`src/helpers/duckdb_utils.py`. Provide one shared materializer for ordered flat
innerdict rows and one shared JSONL loader for all three tables:

- the materializer groups by `ktp.source_key`, removes that field from each
  payload object, and writes only `name_key` and `innerdicts`;
- the loader selects those exact quoted columns, validates required innerdict
  fields, parses the JSONL payload, and appends by the already persisted source
  key; and
- fresh execution and resume hydration must use the same loader, so their
  in-memory `OuterDict` values are equivalent.

Step 7 and step 8 should use this path instead of constructing DataFrames with
literal `name_key`/`innerdicts` labels.

Step 9 needs one additional internal, schema-centralized relation because its
current `ssn_innerdicts` table serves two incompatible purposes. Materialize
the existing expensive wide result as `ssn_legacy_rows_innerdicts` through
`PARQUET_LEGACY_ROWS_INNERDICT_TABLE`. Build:

1. the unchanged wide `ssn_parquet_output` view from that internal row table;
2. the two-column `ssn_innerdicts` table from the same ordered rows through the
   shared materializer; and
3. the live `OuterDict` by loading the new two-column table.

Do not make downstream views unpack `ssn_innerdicts`; that would turn a simple
storage correction into a broad SQL rewrite and could repeatedly deserialize
the expensive payload. The internal wide table is an implementation detail;
`ssn_parquet_output` remains the flat consumer-facing relation.

The JSONL round trip must preserve the values that step 9 currently appends
directly from DuckDB. In particular, SQL `NULL` remains Python `None`/JSON
`null`, numeric and boolean values retain their meaning, and JSON-typed match
payloads do not silently change from display strings into nested Python
objects. DuckDB's bounded `ktp.ssn_sum_hit_1pct` sums must be cast to `BIGINT`
before the shared pandas boundary so they remain integers rather than integral
floats; reject an unhandled `HUGEINT` source column.

The ordered SSN legacy rows and the resulting SSN JSONL innerdicts must retain
`ktp.draw_number`, matching XLSX and DOCX. `ssn_parquet_output` and Step 10
review artifacts must expose one unsuffixed draw-number column immediately
after `ktp.fragment_type`.

Update reset/cleanup for the internal SSN relation. Split step-9 diagnostics
between wide innerdict-row count and grouped source-key count rather than
reporting the latter as though it were the former.

### DuckDB-owned source-key JSON consideration

The additional source-key serialization issue remains out of scope for this
task. A future change should centralize `(first_name, last_name) <->
ktp.source_key` in DuckDB, carry the persisted source key opaquely in Python,
and remove Python parse/re-serialize ownership. Do not implement that change,
alter `OuterDict`, or migrate labels here. Python `json.loads` calls for match
payloads and other non-source-key JSON are unaffected.

### affected consumers and compatibility

Update `src/helpers/init_pipeline.py` so all three completed matching steps
hydrate through the common two-column loader. The old wide-row SSN loader is no
longer valid.

Keep the read-only detours on the appropriate contract:

- XLSX innerdict consumers use the declared `name_key` / `innerdicts` columns;
- `detour_mode3_pgf_stats.py` obtains flat SSN fields from
  `ssn_parquet_output`, not from the now-grouped `ssn_innerdicts`; and
- the mode-0 flat-SSN fallback uses the wide output/internal row relation. It
  must never treat the two-column table as a wide relation.

Keep `ssn_parquet_output`, the Step 10 partition review view, cards, and their
CSV/TXT/DOCX artifacts semantically unchanged apart from the requested SSN
draw field. Step 10 must also emit its existing partition and review artifacts
for mode 0; fully resolved mode-0 rows use the existing no-resolution sentinel.

The mode-0 review implementation must remain DuckDB-owned without repeatedly
expanding the three output views inside the review query. Materialize the rows
for selected `card_partitions` source keys from `xlsx_output`,
`ssn_parquet_output`, and `docx_output` once into temporary DuckDB tables, then
run the existing review aggregation over those physical inputs. Materialize
the ranked rows into a small derived backing table and keep
`card_partition_review` as the public ordered view with the same columns,
values, row multiplicity, placeholders, multiline separators, and ordering.

This is a clean-build schema break. Do not implement a migration, legacy
column aliases, or dual-read compatibility. A database checkpoint made with
the old SSN schema is not resumable under the new code; require a full
`--new` rebuild. Never run that command as part of this task's implementation
or verification.

### tests and acceptance

Add focused tests that prove:

- `DESCRIBE` reports exactly `name_key` and `innerdicts`, in order, for all
  three innerdict tables;
- multiple ordered flat rows for one key become one JSONL blob, payload objects
  omit `ktp.source_key`, and loading restores the same ordered innerdict values;
- empty/missing-match keys do not produce malformed or phantom innerdicts;
- SSN `NULL`, numeric, boolean, string, and JSON-typed values survive
  materialization and hydration without card-visible changes;
- `ktp.ssn_sum_hit_1pct` remains an integer and `ktp.draw_number` survives the
  SSN JSONL round trip;
- `ssn_parquet_output` retains the old wide columns, row count, and order while
  `ssn_innerdicts` has one row per represented source key;
- fresh step execution and resume hydration produce equivalent outerdict/card
  inputs for XLSX, DOCX, and SSN;
- Step 10 subset counts, mode-0 partition rows, review rows, and rendered card
  content preserve the established contracts; and
- both detours work against the new schemas and remain read-only.

The remaining Step 10 review verification must be run by the human. The AI
must not run tests, run or import `src.repl`, mutate the supplied database, or
use Git.
