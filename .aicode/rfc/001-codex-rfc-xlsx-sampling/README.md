# RFC 001: XLSX Sampling Integration

Timestamp: 2026-01-26T04:57:01Z

## Scope (Single Testable Unit)
Implement the XLSX sampling module that deterministically samples rows from input XLSX files and merges historical sample outputs into a single merged CSV.

## Context
Sampling is now part of the pipeline. The sampler must be deterministic (seeded) and produce sample CSVs that can be merged into `merged_samples.csv`.

## Implementation Details
- Create `core/ingestion/xlsx_sampler.py` with an `XLSXSampler` class:
  - `__init__(seed=42)` initializes a NumPy RNG.
  - `sample(xlsx_dir, n, output_path)` reads all XLSX inputs, applies sampling logic, increments `draw_count`, and writes `sample_YYYY-MM-DD.csv` outputs.
  - `merge_samples(sample_dir, output_path)` merges all `sample_*.csv` files in lexical order into `merged_samples.csv`.
- Ensure the output contains the required columns (e.g., `draw_number`, `hcr.filename`, `hcr.row_number`, `priority`, `hcr.first_name`, `hcr.last_name`).
- Sampling should be deterministic for the same seed and input ordering.

## Validation Gates
- Sampling should fail fast if no XLSX files are present.
- `merge_samples` should fail if no `sample_*.csv` files exist.

## Testing (to be implemented with this RFC)
### Unit Tests
- Verify `sample` produces deterministic output given the same seed and inputs.
- Verify `merge_samples` concatenates sorted `sample_*.csv` files in order.

### Integration Tests
- End-to-end sampling: ingest multiple XLSX files, generate sample CSVs, and merge to `merged_samples.csv` with expected row counts.

### Regression Tests
- Freeze a known seed/input fixture and compare the produced `sample_*.csv` checksum to a golden fixture.
