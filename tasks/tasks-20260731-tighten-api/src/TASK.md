## human written - ai never touches this
### environment
```bash
[ "$PWD" = "/Volumes/home/aicode/2026-01-02_enrich_full_df" ] || exit 1
TASK_DIR="$PWD/tasks/tasks-20260731-tighten-api"
TASK="$TASK_DIR/src/TASK.md"
WORK="$TASK_DIR/var/WORK.md"
```

## after each compaction
> [!IMPORTANT]
> Immediately after compaction, refresh TASK/WORK in full.

## always
> [!IMPORTANT]
> Remember to keep WORK current at all times - compaction can happen anytime.
> WORK should contain sufficient context for what we're currently doing.
> The TASK/WORK combo should stand alone at all times.
> WORK should never carry any stale baggage.

## never
never remove inline comments
marked as signed-off by human.

## testing philosophy
human operator-run e2e tests that
test production behaviour are the
cornerstone of our testing strategy.
Our development is test-driven
in the sense that we ultimately aim to
pass on these operator-driven real E2E tests.

Note, however, that this testing is expensive
because **the user** is sitting there in sync
and providing **the Codex coding agent** with
valuable failure modes.

Therefore, wherever possible,
all failures/bugs should be caught _upstream_
at hermetic unit/integration/regression/
within-guest-e2e-tests
rather that at human operated e2e.

If it so happens that failures happen
at human operated e2e, **Codex the coding agent**
must learn from this and wire in, without reminders,
appropriate upstream tests right away to secure coverage
before this falls out of context.

### actual task

```yaml
feature:
  description:
    name: "KTP HCR Detour: AI Augmentation"
    pixi: detour-ai-augment
  background:  # human-curated
    readme: src/detours/detour_ai_augment/README.md
    rdf:   src/detours/detour_ai_augment/assets/hcr_augment_agent_architecture.drawrdf.ttl
    # plus, see below
# scenarios: []
```

#### background
As given in `readme`,
the feature's Acme ADL architecture
consists of five main components:

- Human Operator
- Control Centre
- Inference API
- Agent Runtime
- Backend

Useful-to-know
aliases and examples:

- Human Operator,
  e.g., **the user**
- Control Centre
  is operationally synonymous with
  **Host Machine**,
  e.g., a Mac16,12
  (macOS arm64)
- Agent Runtime
  is operationally synonymous with
  **Guest Machine**,
  e.g., a Lima AIVM
  (Ubuntu arm64)
- Inference API,
  e.g., via OpenAI ChatGPT login
- Backend,
  e.g., FastAPI

As given in `readme`,
in particular in `rdf`,
the following 8 connectors
are defined:

- Human Operator <-> Control Centre
- Human Operator <-> Inference API
- Human Operator <-> Agent Runtime
- Human Operator <-> Backend
- Control Centre <-> Agent Runtime
- Control Centre <-> Backend
- Inference API <-> Agent Runtime
- Agent Runtime <-> Backend

We proceed to describing
the feature lifecycle
by describing the behaviours
each connector is required
to demonstrate, grouped by
the attached component.

But prior to proceeding,
there is room to reduce complexity:

- Human Operator may be omitted as a component
  because we do not prescribe the behaviour
  of the human operator in this description
  of the feature behaviour.
- Inference API, in this set-up,
  only interfaces with Agent Runtime, and
  therefore it may be omitted as a component;
  it will be sufficient to describe the
  Inference API – Agent Runtime connector
  and how Agent Runtime uses it, as
  Inference API is not controlled or
  described in this feature description.
- Note that connectors are two-way,
  so they may as well be grouped
  by the dominating component, or the
  component "owning" the connector may
  be designated.

Therefore, this is tentatively reduced
to, ordered from higher to lower priority
in the feature's lifecycle:

- Part 1: Backend-owned Connectors
  - 1.1. Backend <-> Control Centre
  - 1.2. Backend <-> Agent Runtime
  - 1.3. Backend <-> Human Operator
- Part 2: Control Centre-owned Connectors
  - 2.1. Control Centre <-> Human Operator
  - 2.2. Control Centre <-> Agent Runtime
- Part 3: Agent Runtime-owned Connectors
  - 3.1. Agent Runtime <-> Inference API
  - 3.2. Agent Runtime <-> Human Operator
- Omitted:
  - Human Operator <-> Inference API

As this is insufficient to
fully describe the feature's lifecycle,
several lower-level components need to
be noted and the connectors prescribed:

- config file\* (`PipelineConfig`, `AiAugmentDetourConfig`). interfaces with human (omitted), with backend (read-only, owned by backend), with control centre (read-only, owned by control centre).
- main db (`PipelineConfig.db_file`). interfaces with human (omitted), with config file (read-only, owned by config file), with control centre (read-only, owned by control centre), with backend (read-only, owned by backend).
- output dir (`PipelineConfig.output_dir`). interfaces with config file (read-only, owned by config file), with backend (write, owned by backend).
- rollout CAS (`AiAugmentDetourConfig.rollout_cas_dir`). interfaces with config file (read-only, owned by config file), with backend (write, owned by backend).
- detour db (`AiAugmentBackendContext.detour_db_path`). interfaces with human (omitted), with config file (read-only, owned by config file), with backend (owned by backend).
- http replay jsonl (`AiAugmentBackendContext.replay_log`). interfaces with config (read-only, owned by config), with backend (write, owned by backend).

\* Note that for this detour,
the main pipeline machinery
(`src/helpers/config.py::PipelineConfig`)
is supported with custom fields in `config_ai_augment.json`
and supporting code, owned by the detour
(`src/detours/detour_ai_augment/src/backend/helpers/data_models/ai_augment_config.py::AiAugmentDetourConfig`).
This is reflective of
the **Architectural Rule** in this repo
that **requires** that detour logic is owned by the detour
and must not spill over onto the main pipeline.
For the purpose of this breakdown,
it is helpful to separate the fields offered
in the main pipeline machinery vs. fields
the detour introduces for itself.

Further,
it is important to mention internal interfacing
that happens between inner components of
the detour-owned components:

- Backend <-> Backend
- Control Centre <-> Control Centre
- Agent Runtime <-> Agent Runtime

It is therefore helpful to revise and extend the above breakdown:

- Part 1: Backend-owned Connectors
  - C001.01. Backend <-> `PipelineConfig` (read-only)
  - C001.02. Backend <-> `AiAugmentDetourConfig` (read-only)
  - C001.03. Backend <-> Detour DB
  - C001.04. Backend <-> Detour output directory
  - C001.05. Backend <-> Detour replay JSONL
  - C001.06. Backend <-> Rollout CAS
  - C001.07. Backend <-> Control Centre
  - C001.08. Backend <-> Agent Runtime
  - C001.09. Backend <-> Human Operator
  - C001.10. Backend <-> Backend
  - C001.11. Backend <-> Main DB (read-only)
- Part 2: Control Centre-owned Connectors
  - C002.01. Control Centre <-> `PipelineConfig` (read-only)
  - C002.02. Control Centre <-> `AiAugmentDetourConfig` (read-only)
  - C002.03. Control Centre <-> Main DB (read-only)
  - C002.04. Control Centre <-> Human Operator
  - C002.05. Control Centre <-> Agent Runtime
  - C002.06. Control Centre <-> Control Centre
- Part 3: Agent Runtime-owned Connectors
  - C003.01. Agent Runtime <-> Human Operator
  - C003.02. Agent Runtime <-> Inference API
  - C003.03. Agent Runtime <-> Agent Runtime
- Omitted:
  - Most Human Operator's connectors
  - `PipelineConfig` <-> Main DB
    (outside of detour scope,
    as this is prescribed in the main pipeline)
  - `PipelineConfig` <-> Detour output directory
    (outside of detour scope,
    as this is prescribed in the main pipeline)
  - Connectors between
    lower-level detour-owned components
    (as all of them are fully prescribed
    as part of the above-listed connectors)

Total:
  19 prescribed connectors

It is also helpful to
illustrate the **communication methods**
that may be employed by the connectors:

- HTTP protocol
- SSH protocol
- Non-interactive CLI
- REPL CLI/chat
- GUI
- SDK
- Config/env vars
- Disk I/O
- Unix shell

#### scenarios
##### C001.01. Backend <-> `PipelineConfig` (read-only)
Human Operator — interfaces with Control Centre via CLI/HTTP: `pixi run dashboard`; `http://127.0.0.1:8611`

```gherkin
Given `--config` is passed
When it is a valid `PipelineConfig`
* it is a valid `AiAugmentDetourConfig`
Then `Backend` is properly configured
```

##### C001.02. Backend <-> `AiAugmentDetourConfig` (read-only)

##### C001.03. Backend <-> Detour DB
Backend — interfaces with detour DB via SQL/DuckDB API: derived detour `.duckdb` opened read/write

##### C001.04. Backend <-> Detour output directory
Backend — interfaces with filesystem via POSIX: configured `output_dir`

##### C001.05. Backend <-> Detour replay JSONL
Backend — interfaces with filesystem via POSIX: authoritative `detour_ai_augment_backend_api_replay_log`

##### C001.06. Backend <-> Rollout CAS
Backend — interfaces with filesystem via POSIX: configured `rollout_cas_dir`

##### C001.07. Backend <-> Control Centre

##### C001.08. Backend <-> Agent Runtime
Agent Runtime — interfaces with Backend via HTTP: `GET /openapi.json`; `GET /pull`; `POST /push`

##### C001.09. Backend <-> Human Operator

##### C001.10. Backend <-> Backend

##### C001.11. Backend <-> Main DB (read-only)
Backend — interfaces with main DB via SQL/DuckDB API: configured `db_file`, `read_only=True`

##### C002.01. Control Centre <-> `PipelineConfig` (read-only)

##### C002.02. Control Centre <-> `AiAugmentDetourConfig` (read-only)

##### C002.03. Control Centre <-> Main DB (read-only)
Control Centre — interfaces with main DB via SQL/DuckDB API: configured `db_file`, `read_only=True`

##### C002.04. Control Centre <-> Human Operator

##### C002.05. Control Centre <-> Agent Runtime
Control Centre — interfaces with Agent Runtime via SSH: `ssh -F ~/.lima/aivm/ssh.config … aivm-ai`

##### C002.06. Control Centre <-> Control Centre

##### C003.01. Agent Runtime <-> Human Operator
Agent Runtime — interfaces with guest OS via POSIX: `/home/ai/workdir`; `/home/ai/.codex/sessions`

##### C003.02. Agent Runtime <-> Inference API

##### C003.03. Agent Runtime <-> Agent Runtime
