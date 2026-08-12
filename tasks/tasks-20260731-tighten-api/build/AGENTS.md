## human written - ai never touches this
### prerequisites and setup
```bash
([ "$PWD" = "/Volumes/home/aicode/2026-01-02_enrich_full_df" ] || exit 1)
TASK_DIR="$PWD/tasks/tasks-20260731-tighten-api"
TASK="$TASK_DIR/src/TASK.md"
```

AI must interpret how it understood this TASK
as prescribed in `$TASK_DIR/Makefile`,
whose `make validate` will be used to verify AI's work.

> [!IMPORTANT]
> When writing `$TASK_DIR/build/SPEC.ipynb`, AI should know:
> - The procedure is called atomic requirement-to-evidence mapping.
> - One Markdown cell represents one requirement unit:
>   - A requirement unit is the smallest contiguous set of TASK lines expressing one independently verifiable behavior.
>   - A unit may span multiple contiguous TASK lines.
> - An evidence (code) cell must prove only its preceding requirement unit:
>   - Exactly one evidence cell must immediately follow each Markdown cell.
>   - Its task_lines must exactly match that Markdown cell’s source lines.
>   - A code cell must not define paths, test IDs, setup, or assertions for other units.
>   - No shared “miscellaneous evidence” code cells or consecutive code cells.

```bash
sed -n '8,212p' "$TASK_DIR/legacy/SPEC.md"
```
every case above must have a dedicated roundtrip test.
