# README
> [!NOTE]
> This was written manually
> by Pavel Zhelnov.
> 
> Started writing this
> on May 26, 2026.
> 
> This is a code review of
> the entire pipeline, prior
> primarily AI-generated.

## AI assistance
The pipeline code was
primarily generated with
OpenAI Codex (GPT 5.2+)
under paid Plus subscription
(~$30 CAD/month as of Q1-Q2 2026).

Original stub was
generated with
Gemini 3 Pro in
January 2026, see
`chats/chats-202601xx-original-gemini/`.

See more
AI coding artifacts under
`.aicode/rfc/` and
`chats/`.

## Pipeline overview
### Purpose
This a reproducible pipeline whose
outputs are threefold:

1. database filled in with helpful
   tables and views
   intended for reuse in
   secondary analyses;
1. diagnostic dumps such as
   text reports and
   ephemeral CSV renders;
1. final outputs, that is,
   DOCX or TXT cards per HCR researcher.

The final purpose is therefore to
produce as complete as possible
personal profile cards for
HCR researchers
across an arbitrary number of
yearly HCR spreadsheets.

### Scope
The HCR years covered are
2014–2024 in this release, and
adding further years will require a
review of the new year’s
XLSX schema to
ensure column names are
properly normalized, in particular in
[steps 2 and 3](#data-flow) of
the main pipeline.

In addition to the
original HCR XLSX spreadsheets,
other data sources are supported,
notably
SciSciNet v2 parquets and
custom-format DOCX tables
with augmented data.
JSON Lines with
AI-generated data are
not currently implemented but were
kept in mind from the very
conception of this pipeline and
so should be straightforward to add.

### Architecture
The repository tree is
intentionally flat, making it
easier for researchers to
locate what module is
responsible for what.

Let us review it:

```bash
$ { tree . -d -L 1 -I 'tmp|data|__pycache__'; echo; \
    tree ./src -d -L 1 -I '__pycache__'; }
.
├── chats
├── resources
├── src
├── tasks
└── tests

6 directories

./src
├── detours
├── github.com
├── helpers
└── steps

5 directories
```

- `src` contains all code;
- `tests` contains all tests;
- `resources` contains any
  helpful static assets for the
  code or tests;
- `chats` and `tasks`
  are reserved for
  AI interactions
  (as well as
  `.aicode`
  hidden directory
  used previously,
  now unused).

When it comes to `src`, the
entrypoint for the
main pipeline is in
`src/repl.py`, and the
entrypoint depends on
pipeline steps, which are
here `src/steps/`, and
any helper functions or
classes are exposed
here `src/helpers/`;
neither directory contains
nested subdirectories.

The pipeline’s
[threefold outputs](#purpose) will be
stored under `data/`:

1. `data/scisci_process.duckdb` will be the
   database file;
1. `data/diagnostics/` will contain
   diagnostic dumps;
1. `data/outputs/` will contain the
   final outputs, that is,
   DOCX or TXT cards per HCR researcher.

All detours
([see below](#detours)) are
under `src/detours/`.

Finally,
under `src/github.com/`,
there is some additional
external code
on which the main pipeline
does not depend.

### Main pipeline
On a high level, the pipeline makes
two major data transforms:

1. reduction of multiple HCR award rows
   across multiple HCR XLSX files
   into unique _name keys_,
   entitled a proxy for an
   individual researcher;
   the _dictionary_ of these
   name keys as keys and
   profile data as values is
   called here the _outer dict_;
2. stacking of multiple facts
   (i.e., dictionaries)
   about the given name key
   from multiple sources
   (e.g., XLSX, DOCX, JSONL); these
   dictionaries with facts are
   called here _inner dicts_;
   each inner dict contains,
   as key, some researcher property, and
   as value, the value of the property
   (either an object or a datatype
   in [OWL RDF terminology][owl-rdf]);
   in an outer dict key-value pair, the value is therefore always a
   _list of inner dicts._

Other data transformations are
of course done as well along the way, but
the two above are major conceptual ones.

### Detours
In addition to the main pipeline
(i.e., `src/repl.py` entry point), a
separate route called `src/detours/` exists;
these so-called detours contain variants of the
main pipeline 
created for a specific purpose.
Detours must not rely on the main pipeline but
rather use its design principles and
building blocks.
For example,
there is a detour for
gender analyses
(`src/detours/detour_mode3_pgf_stats.py`) and for
socioeconomic analyses
(`src/detours/detour_mode0_econ_stats.py`), which
return bespoke data reports.

## Environment
[pixi][pixi] is
used with a
lockfile (`./pixi.lock`)
for reproducibility;
see pixi version in
`./tool-versions`.

See
`./pyproject.toml`
for the configuration.
All direct dependencies are
also listed for redundancy in
`./requirements.txt`, though
versions are not pinned there.

Note that
all direct dependencies used so far are PyPI dependencies, but
the opportunity to add from Conda is
here with pixi.

All dependencies,
both for running and
testing, linting the pipeline, are
included in the same default environment
recognizing that
all of these are considered core components of this research project and
as such tighter coupling made sense.

This has been tested on
macOS arm64 and 
Linux arm64
(via Lima).
Note that the
`.pixi` directory
might need to be
removed and recreated
(e.g., using `pixi reinstall`)
if switching between the two
because the DuckDB binaries are incompatible across the operating systems.

> [!TIP]
> Alternatively,
> this pixi config
> `pixi config set detached-environments true --global`
> can be used to
> keep the environment global
> on each operating system.
> After activating this option,
> `rm -rf .pixi/envs && pixi install`
> in the repo directory
> may be necessary.

## User interface
### AI agent
This repository is
best interacted with through an
AI coding agent –
e.g., OpenAI Codex CLI.
I have been running it within a
Lima sandbox with only a
dedicated volume mounted,
connecting to it via SSH through a
Visual Studio Code extension.

A few routes may be taken:

- Instruct the agent to
  answer questions or
  solve tasks
  using an existing database
  (e.g., produced after a
  main pipeline run)
  in read-only mode
  (e.g., locked through
  file permissions).
- Instruct the agent to
  develop a bespoke [detour](#detours)
  for a specific purpose;
  this is particularly helpful
  when an intervention is 
  necessary mid-pipeline and
  as such artifacts from the
  main pipeline are not helpful.
- Intervene at the
  main pipeline,
  including through introduction of
  new knobs in
  `./config*.json`, though this is
  the least desirable route
  as side effects and
  regressions in main pipeline reproducibility guarantees must be
  seriously considered.

Some examples for
all of these approaches
may be found among
[AI coding artifacts](#ai-assistance)
in this repo;
also see
`tasks/`.

### Main pipeline CLI
Minimal usage notes for
the command-line interface (CLI) for
the main pipeline
can be viewed here:

```bash
pixi run python -m src.repl -h
```

Both interactive and
non-interactive usage is
supported.

### DuckDB UI
A DuckDB database produced from
the main pipeline or a detour
may be conveniently accessed via the
stock [DuckDB web UI][duckdb-ui]
(set to read-only by default):

```bash
pixi run duckdb-ui [OPTIONAL_PATH_TO_DB]
```

> [!TIP]
> This command can also
> read `*.parquet` files.

## Data flow

>[!NOTE]
> Here I will describe
> exactly how
> inputs are processed,
> what low-level transforms are applied within the pipeline, and
> how, which, and at what point outputs are expulsed.

<!--- Markdown refs --->

[owl-rdf]: http://www.w3.org/TR/owl-ref/ "OWL Web Ontology Language Reference"
[pixi]: https://pixi.prefix.dev/latest/installation/ "Pixi Installation"
[duckdb-ui]: https://duckdb.org/2025/03/12/duckdb-ui "The DuckDB Local UI"
