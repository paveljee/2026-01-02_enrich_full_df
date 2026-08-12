## human written - ai never touches this
### prerequisites and setup
```bash
([ "$PWD" = "/Volumes/home/aicode/2026-01-02_enrich_full_df" ] || exit 1)
TASK_DIR="tasks/tasks-20260731-tighten-api"
sed -n '3,207p' "$TASK_DIR/legacy/SPEC.md"
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
every case above must have a dedicated roundtrip test.
