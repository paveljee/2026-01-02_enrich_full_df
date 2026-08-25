## human written - ai never touches this
### environment
```bash
[ "$PWD" = "/Volumes/home/aicode/2026-01-02_enrich_full_df" ] || exit 1
TASK_DIR="$PWD/tasks/tasks-20260731-tighten-api"
TASK="$TASK_DIR/src/TASK.md"
WORK="$TASK_DIR/var/WORK.md"
FEATURE="detour-ai-augment"
```

### after each compaction
> [!IMPORTANT]
> Immediately after compaction,
> refresh TASK/WORK in full.

### always
> [!IMPORTANT]
> Remember to keep WORK current at all times -
> compaction can happen anytime.
> WORK should contain sufficient context for
> what we're currently doing.
> The TASK/WORK combo should stand alone 
> at all times.
> WORK should never carry any stale baggage.

### never
never remove inline comments
marked as signed-off by human.

### misc
#### pixi
Use `pixi run -e $FEATURE` for everything.

#### git usage
you may not stage/unstage anything in git;
only readonly use of git is allowed.

#### apply_patch
If `apply_patch` does not work,
use the `env` workaround.

#### WORK
Use `$TASK_DIR/var/WORK.md` as
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

#### testing philosophy
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

### prerequisites and setup
#### main pipeline
review relevant code base
in particular everything that's involved
when running command
`pixi run python -m src.repl --config config.repl.json --new`.
DO NOT ATTEMPT TO RUN THE COMMAND.
you are disallowed to use `src.repl` at all.
this won't execute in your env anyway
because no access to resources here,
so don't even try.
your goal will be different.

so when you've explored the repo sufficiently and
are confident that you understand what's going on
under the hood when this command is run,
appreciate the following:
this command has already been run, 
with current `config.repl.json`.
the db itself is here,
`data/scisci_process.duckdb`;
you may ONLY use it in READONLY mode.
The duckdb file is your single
and only source of truth.
You don't touch or look for any other
artifacts or whatnot. 
You may re-review code of this repo
(i.e., `src/`, config json, `tests/` etc
but not data files,
e.g., not `data/` or `.aicode/`),
**in readonly mode,**
as appropriate/you feel you need.

#### detours
Detours are isolated at four levels:

1. Detour development does not touch `src/cli.py`.
2. No detour imports another detour.
3. Each detour is launched directly via `pixi run -e $FEATURE python -m src.detours.<module>`.
4. Each detour uses its own DB and never touches main CLI DB state or another detour DB.

### actual task
ask human operator.
