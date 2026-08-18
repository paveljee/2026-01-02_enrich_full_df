# README
> [!IMPORTANT]
> This was written manually
> by Pavel Zhelnov.
> 
> Started writing this
> on May 26, 2026, and
> **have not updated it**
> **in a while,** so it 
> may be partially outdated.
> 
> This is a code review of
> the entire pipeline, prior
> primarily AI-generated.

## AI assistance
The pipeline code was
primarily generated with
OpenAI Codex (GPT 5.2+)
under a paid Plus subscription
(~\$30 CAD/month as of Q1-Q2 2026).
Sometimes I also had to
buy some credits,
e.g., \$10 USD worth,
if I needed to
complete a small chunk of
pending works urgently.
At other times I upgraded to
a Pro-x5 subscription for
~\$173 CAD/month total
(inclusive of taxes).

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

### File path conventions

File paths you may see in `config*.json` files or elsewhere may be located in various directories.
Those distinctions are meaningful:

* `/Volumes/Users/**` and `/Volumes/home/anonymous/**` directories are located on the host macOS machine within private human user files and outside of the AI coding agent scope; the AI agent will fail to access these and will receive pipeline failures whenever they are accessed by it.
  The former concerns mostly private data files in progress (e.g., manual annotations), generally to be released upon the project publication.
  The latter often concerns publicly available files that do not need to be committed to this repo, e.g., large SciSciNet v2 parquet files from HuggingFace.
  The distinction between the former and the latter is not strict, though, and/or is not within privilege scope of this repo but rather is reported for general reference.
* Relative paths like `data/**` or `resources/**` are the ones
  either committed in the repo
  or produced by the pipeline, and
  they are therefore expected to be available whenever the repository is cloned and used by a public user.
* `/Volumes/home/aicode/**` paths indicate the specific test instance of the repository in which development is being done.
  These are available to the AI coding agent
  but are often **not** committed into the public repo.
  Regardless, they will often fail to be found if the pipeline is cloned into a new directory thanks to the intentionally hardcoded top-level directories here.
  It is therefore considered that they are
  either an instance of files as in relative paths above
  or a responsibility of the pipeline user who should copy them from elsewhere.

   * In particular, files under the `**/data` subdirectory of this absolute path are the pipeline artifacts being worked on.
   The are **not** committed usually, but sometimes they are – if helpful for public reference.
   They may be regenerated but usually persist across pipeline executions.
   * Files under the `**/tmp` subdirectory of the absolute path are **not** committed and are ephemeral in the sense that they are copied by the human from elsewhere (i.e., the authoritative copy is held elsewhere) intentionally for the AI coding agent’s access.
   This may include, for example, some disclosable files from `/Volumes/Users/**` or from elsewhere.

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
> the following pixi config
> may be used.
> Though Pixi themselves
> [advise against this][pixi-detached-env]:
>
> > We recommend against using this because any environment created for a workspace is no longer placed in the same folder as the workspace. This creates a disconnect between the workspace and its environments and manual cleanup of the environments is required when deleting the workspace.
> > 
> > However, in some cases, this option can still be very useful, for instance to:
> > 
> > - force the installation on a specific filesystem/drive.
> > - install environments locally but keep the workspace on a network drive.
> > - let a system-administrator have more control over all environments on a system.
>
> Arguably,
> keeping OS-specific binaries is
> one of those special cases.
>
> If you would still like to do it
> against Pixi advice,
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
[pixi-detached-env]: https://pixi.prefix.dev/dev/reference/pixi_configuration/#detached-environments "detached-environments – Pixi Configuration"
[duckdb-ui]: https://duckdb.org/2025/03/12/duckdb-ui "The DuckDB Local UI"
