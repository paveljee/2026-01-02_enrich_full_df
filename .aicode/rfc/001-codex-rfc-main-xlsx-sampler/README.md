# RFC 001: Main XLSX Sampler (2025-08-19) Integration

Timestamp: 2026-01-26T14:16:34Z

## Scope (Single Testable Unit)
Implement the *main* deterministic XLSX sampler using the exact logic from the 2025-08-19 sampler, wired into the new roadmap project at `./pkg_20260126_roadmap/`.

This RFC is ONLY about sampling XLSX files into CSVs (including draw-number sequencing, priority logic, column normalization, and output schema). It does not cover pilot sampling, merging, DOCX enrichment, or downstream enrichment steps.

## Required Source of Truth (Must Reuse)
The 2025-08-19 sampler logic is the authoritative source and **must be reused with minimal changes** (do not alter logic or comments unless strictly required for integration). Implementers **must fetch** the upstream file and preserve it verbatim:

- https://github.com/paveljee/research-integrity-ktp/blob/analysis/2025-08-19-sampler/analyses/2025-08-19_sampler/sampler.py
- Ground-truth samples (review for expected output shape and draw sequencing):
  - https://github.com/paveljee/research-integrity-ktp/blob/analysis/2025-08-19-sampler/analyses/2025-08-19_sampler/

## Existing Local Schema Constraints
The output schema must match the “full_df” schema used elsewhere in this repo. The canonical schema example is in:
- `./pkg_20251223_word_tables/tests/test_unify_names.py::hcr_row`

Key expected columns (non-exhaustive, must preserve full schema from XLSX normalization):
- `hcr.row_number`, `hcr.filename`
- `hcr.first_name`, `hcr.last_name`, `hcr.firstname_middlename`, `hcr.familyname`, `hcr.firstname`
- `hcr.category`, `hcr.primary_affiliation`, `hcr.secondary_affiliation`, `hcr.secondary_affiliations`
- `ktp.draw_number`, `ktp.priority`

## Implementation Instructions (Must Follow)
1. **Create the new project module** inside `./pkg_20260126_roadmap/`.
   - Implement a sampler module that is functionally identical to the upstream sampler file linked above.
2. **Preserve the deterministic draw-number logic**:
   - RNG seeded with `seed=42`.
   - Burn RNG draws based on prior CSV draws to preserve sequence when appending.
3. **Preserve column normalization rules**:
   - Header normalization uses `hcr.` prefix and replaces spaces/colons with underscores.
4. **Preserve priority logic**:
   - The country-affiliation priority and region lists (`ENGLISH_HICS`, `EU_COUNTRIES`, `GREATER_CHINA`, `NON_ENGLISH_NON_EU_HICS_NO_CHINA`) must be identical.
5. **Preserve output ordering**:
   - Metadata columns (`ktp.draw_number`, `hcr.filename`, `hcr.row_number`, `ktp.priority`) must appear first, followed by the rest of the columns in their original order.

## Data & Fixture Requirements for Tests
Because source XLSX files are not available in this repo, tests must create fixture XLSX files based on the *final schema*:
- Use the column set from `test_unify_names.py::hcr_row` as baseline.
- Provide at least **two fixture XLSX files** where the name columns differ:
  - Example: one uses `First Name Middle Name`, another uses `First Name` / `Last Name`, so normalization produces the `hcr.` variants.
- Ensure fixtures include affiliation fields with countries that trigger all 5 priority tiers in the sampler.

## Testing Requirements (Implement With This RFC)
### Unit Tests
- Verify header normalization produces the expected `hcr.*` column names.
- Verify deterministic sampling with a fixed seed yields identical draw numbers and row selections.
- Verify priority assignment ordering for each country category.

### Integration Tests
- Generate two fixture XLSX files, sample `n` rows from each, and confirm:
  - `ktp.draw_number` sequences correctly across runs.
  - Output CSV schema matches the canonical schema from `test_unify_names.py::hcr_row`.
  - Output sorting honors `ktp.priority`, then `ktp.draw_number` when `affiliation_sort=True`.

### Regression Tests
- Freeze a known fixture XLSX pair and seed; compare output CSV checksums against golden files.

## Output Location
All new implementation for the roadmap must live under:
- `./pkg_20260126_roadmap/`
