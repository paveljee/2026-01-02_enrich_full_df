## human written - ai never touches this
### environment
```bash
[ "$PWD" = "/Volumes/home/aicode/2026-01-02_enrich_full_df" ] || exit 1
TASK_DIR="$PWD/tasks/tasks-20260731-tighten-api"
TASK="$TASK_DIR/src/TASK.md"
WORK="$TASK_DIR/var/WORK.md"
```

### prerequisites and setup
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

If `apply_patch` does not work,
use the `env` workaround.

AI only uses git readonly.

Use `pixi run -e detour-ai-augment` for everything.

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
in chat.