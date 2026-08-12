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

### other issues that need addressing:
- review docx and txt renderers and identify where markdown is being produced - and enclose any  underscore containing items into backticks. so basically field names etc. otherwise in nicegui they are incorrectly rendered as markdown.
- in main nicegui table and in researcher card, somehow the line spacing is too large. in the attempt history table it's perfect.
- in main nicegui table the row clicked on doesn't get highlighted which is confusing.
- when nicegui table row is selected/unselected multiple times, this expands and collapses attempts table which is not intuitive. what should happen is that once it's selected, the attempt history should be expanded, and any future clicks will be idempotent.
when clicking on a different row, the selection will change.
therefore when for the first time a row has been selected, rows never get unselected
and therefore attempt history persists.
- in the search box when i remove the value, the search doesn't get reset. **already addressed in commit: `eeeaeacd8aef6d425c27935d2b00cd8777c196fa`. only remains to wire in spec.**
- a spec that uses the docx card building functionality to build a sample researcher's card from db. the card includes full featured output identical to that on a nicegui card. the spec saves it under `$TASK_DIR/data/sample.docx` for future review of rendering.
every case above must have a dedicated roundtrip test.
