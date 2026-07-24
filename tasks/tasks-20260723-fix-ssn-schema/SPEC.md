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

## how ai understood the spec

### outcome and storage contract

This is a schema-and-boundary refactor. Do not change matching, SSN candidate
selection, subset assignment, card contents, or card ordering.

After a new pipeline build, each of these persistent tables must have exactly
the same two columns, in this order:

| table | column 1 | column 2 |
|---|---|---|
| `xlsx_innerdicts` | `ktp.source_key` (`VARCHAR`) | `ktp.innerdicts` (`VARCHAR`) |
| `docx_innerdicts` | `ktp.source_key` (`VARCHAR`) | `ktp.innerdicts` (`VARCHAR`) |
| `ssn_innerdicts` | `ktp.source_key` (`VARCHAR`) | `ktp.innerdicts` (`VARCHAR`) |

`ktp.innerdicts` retains the existing XLSX/DOCX JSON Lines contract: one JSON
object per non-empty line, with the source key omitted from each object. A table
has at most one row for a source key and contains a row only when that source
key has at least one innerdict. Within a blob, preserve the same stable
filename/fragment/draw ordering used by the corresponding flat output.

Add `KTP_INNERDICTS_COL = "ktp.innerdicts"` to `src/helpers/vars.py` and use it
with the existing `KTP_SOURCE_KEY_COL`. No code that reads one of the three
tables should contain the old literal column names.

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
  payload object, and writes only `ktp.source_key` and `ktp.innerdicts`;
- the loader selects those exact quoted columns, validates required innerdict
  fields, parses the JSONL payload, and appends by the already persisted source
  key; and
- fresh execution and resume hydration must use the same loader, so their
  in-memory `OuterDict` values are equivalent.

Step 7 and step 8 should use this path instead of constructing DataFrames with
literal `name_key`/`innerdicts` labels.

Step 9 needs one additional internal, schema-centralized relation because its
current `ssn_innerdicts` table serves two incompatible purposes. Materialize
the existing expensive wide result under a new internal table such as
`ssn_innerdict_rows` (for example,
`PARQUET_INNERDICT_ROWS_TABLE` in `src/helpers/schema.py`). Build:

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
objects. Add regression coverage before choosing a pandas- or SQL-based
materializer.

Update reset/cleanup for the new internal SSN relation. Split step-9 diagnostics
between wide innerdict-row count and grouped source-key count rather than
reporting the latter as though it were the former.

### DuckDB owns source-key JSON

The additional requirement concerns the conversion boundary
`(first_name, last_name) <-> ktp.source_key`. It does not require rewriting
unrelated JSON such as configuration, pipeline state, OpenAlex responses,
match payloads, JSONL innerdict bodies, or whole-artifact dumps.

Centralize SQL expressions for this boundary in one neutral helper:

- serialize with DuckDB `json_object`, always supplying
  `ktp.first_name` first and `ktp.last_name` second, and cast the result to
  `VARCHAR`; and
- deserialize with DuckDB `json_extract_string` using the quoted JSON paths
  for `ktp.first_name` and `ktp.last_name`.

Step 6 must create both included and excluded source keys with that serializer.
Its name views must use the shared extractor expressions. Delete the local
Python `_name_key_json` path.

After creation, Python must treat `ktp.source_key` as an opaque identifier and
carry its exact persisted string through the pipeline. It must not parse and
re-serialize the key merely to recover a `NameKey` or look up state. Concretely:

- remove production dependence on `NameKey.to_json_key()` and
  `NameKey.from_json_key()`; remove those JSON-owning methods if no non-pipeline
  contract still needs them;
- adapt `OuterDict` to retain each DuckDB-produced source key alongside the
  typed first/last-name value used for cards;
- expose keyed iteration or an equivalent small API so step 10 receives the
  source key rather than regenerating it;
- build selected/subset outerdicts by carrying the same key forward;
- on resume, hydrate names and source keys from `outerdict_name_keys` (or an
  equivalent DuckDB query that performs extraction), not by `json.loads`; and
- replace source-key parsing in `detour_mode0_econ_stats.py` with columns
  extracted by DuckDB.

Python `json.loads` calls for `ktp.xlsx_match`, filename-list payloads, or other
non-source-key JSON are unaffected and should not be removed under this task.

DuckDB's canonical output may differ byte-for-byte from the existing
Python-spaced JSON (for example, compact separators). This is acceptable and is
why there must be one producer. All joins in a new database will use the same
opaque value. Do not add Python whitespace post-processing or dual
serializers to mimic the old representation.

### affected consumers and compatibility

Update `src/helpers/init_pipeline.py` so all three completed matching steps
hydrate through the common two-column loader. The old wide-row SSN loader is no
longer valid.

Update the two existing read-only detours rather than leaving hidden
dependencies on the old schema:

- both detours must select the renamed XLSX columns through constants;
- `detour_mode3_pgf_stats.py` must obtain flat SSN fields from
  `ssn_parquet_output`, not from the now-grouped `ssn_innerdicts`; and
- the mode-0 flat-SSN fallback must use the wide output/internal row relation or
  explicitly support the new blob contract. It must never treat the two-column
  table as a wide relation.

Keep `ssn_parquet_output`, the step-10 partition review view, cards, and their
CSV/TXT/DOCX artifacts semantically unchanged apart from the canonical source
key string. Update detour fixtures and any schema fingerprints or metadata that
describe the three innerdict tables.

This is a clean-build schema break. Do not implement a migration, legacy
column aliases, or dual-read compatibility. A database checkpoint made with
the old schemas is not resumable under the new code; fail early with a concise
schema error if encountered and require a full `--new` rebuild. Never run that
command as part of this task's implementation or verification.

### tests and acceptance

Add focused tests that prove:

- `DESCRIBE` reports exactly the two required columns, in order, for all three
  innerdict tables;
- multiple ordered flat rows for one key become one JSONL blob, payload objects
  omit `ktp.source_key`, and loading restores the same ordered innerdict values;
- empty/missing-match keys do not produce malformed or phantom innerdicts;
- SSN `NULL`, numeric, boolean, string, and JSON-typed values survive
  materialization and hydration without card-visible changes;
- `ssn_parquet_output` retains the old wide columns, row count, and order while
  `ssn_innerdicts` has one row per represented source key;
- fresh step execution and resume hydration produce equivalent outerdict/card
  inputs for XLSX, DOCX, and SSN;
- source keys containing Unicode, apostrophes, quotes, and backslashes are
  created and extracted by DuckDB and remain exact opaque keys through
  `OuterDict` and step 10;
- step-10 subset counts, partition rows, review rows, and rendered card content
  do not change because of the storage refactor; and
- both detours work against the new schemas and remain read-only.

Construct source keys in tests with the production DuckDB SQL helper, not
`json.dumps`. Any test or direct database check that evaluates pipeline views
using `unaccent` must load `splink_udfs` through the existing extension helper
or the same `LOAD splink_udfs` setup used by the pipeline.

Run the focused data-model/init/steps 6-10/detour tests, then the repository's
normal Ruff, mypy, and pre-commit test gate for touched code. Do not run or
import `src.repl`, and do not mutate the supplied database.
