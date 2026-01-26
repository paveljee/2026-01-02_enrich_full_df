# RFC 005: Card Generation (Markdown + DOCX)

Timestamp: 2026-01-26T14:16:34Z

## Scope (Single Testable Unit)
Generate markdown and DOCX “cards” from the enriched dataframe, reusing the existing card logic from `pkg_20251223_word_tables`. All implementation lives under `./pkg_20260126_roadmap/`.

This RFC is ONLY about card generation (markdown + docx) and zipping outputs. It does not include DOCX parsing or enrichment.

## Required Source of Truth (Must Reuse)
The card generation logic is already implemented in `pkg_20251223_word_tables/src/cli.py` and must be reused with minimal changes:

- `./pkg_20251223_word_tables/src/cli.py`
  - Card templating (`INTRODUCTION`, draw number formatting, field rendering)
  - Output ZIP naming (`{csv_dir.name}_combined_cards.zip`)
  - Pandoc conversion workflow for DOCX output
- `./pkg_20251223_word_tables/src/_vars.py`
  - `DRAW_LABEL`, `KTP_FIRST_NAME_COL`, `KTP_LAST_NAME_COL`

## Implementation Instructions (Must Follow)
1. **Card content**
   - Preserve the existing markdown structure, including the “Draw #X of TOTAL_DRAWS” header and the “Fun fact” line using the original column names.
2. **Output filename logic**
   - Use the same filename sanitization and `draw_number`-based naming.
3. **Markdown output**
   - Save individual `*.txt` markdown files and zip them in a single archive.
4. **DOCX output**
   - Use the Pandoc workflow and reference docx (`resources/pandoc-custom-reference.docx`) to generate DOCX cards.
5. **Location**
   - Integrate output into `./pkg_20260126_roadmap/` under a consistent output directory.

## Test Fixture Requirements
- Use a small dataframe fixture that includes:
  - Required `ktp.draw_number`, `ktp.first_name`, `ktp.last_name`.
  - Additional multi-line fields to verify markdown rendering.

## Testing Requirements (Implement With This RFC)
### Unit Tests
- Validate the generated markdown text includes the draw header, name line, and all fields.
- Validate that filenames are sanitized and unique.

### Integration Tests
- Generate markdown cards and verify the resulting ZIP contains all expected files.
- (Optional) Generate DOCX cards if Pandoc is available in CI; otherwise, gate with a skip.

### Regression Tests
- Snapshot a fixture input and compare a stable ZIP checksum for markdown output.

## Output Location
All new implementation for the roadmap must live under:
- `./pkg_20260126_roadmap/`
