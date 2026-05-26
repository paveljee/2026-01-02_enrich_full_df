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
OpenAI Codex (GPT 5.2+).

Original stub was
generated with
Gemini 3 Pro in
January 2026, see
`/chats/chats-202601xx-original-gemini/`.

See more
AI coding artifacts under
`/.aicode/rfc/` and
`/chats/`.

## Pipeline overview
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
The years are
2014–2024 in this release, and
adding further years will require a
review of the new year’s
XLSX schema to
ensure column names are
properly normalized, in particular in
steps 2 and 3.

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

## Data flow

>[!NOTE]
> Here I will describe
> exactly how
> inputs are processed,
> what low-level transforms are applied within the pipeline, and
> how, which, and at what point outputs are expulsed.

<!--- Markdown refs --->

[owl-rdf]: http://www.w3.org/TR/owl-ref/ "OWL Web Ontology Language
Reference"
[pixi]: https://pixi.prefix.dev/latest/installation/
