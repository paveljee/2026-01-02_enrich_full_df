# RFC 008: RDF Export (Minimal)

Timestamp: 2026-01-26T14:16:34Z

## Scope (Single Testable Unit)
Implement minimal RDF export for the enriched dataframe. All implementation lives under `./pkg_20260126_roadmap/`.

This RFC is intentionally minimal; card outputs are higher priority. RDF export should be a thin layer that serializes the enriched dataset into `.trig`, `.nquads`, and `.jsonld` formats.

## Required Source of Truth (Must Reuse)
Use the simple RDF logic from the pilot test-run as inspiration (do not over-engineer):
- https://github.com/paveljee/research-integrity-ktp/blob/v0.1.0-pilot.1751566592/test_run.py

## Implementation Instructions (Must Follow)
1. **Minimal graph model**
   - Create a small RDF graph that encodes researcher nodes and key properties (authorid, names, affiliations, fields).
2. **Output formats**
   - Export `.trig`, `.nquads`, and `.jsonld` using the same graph.
3. **Location**
   - Store outputs under `./pkg_20260126_roadmap/` in a stable output directory.

## Test Fixture Requirements
- Use a minimal dataframe fixture (2–3 rows) with the columns required by the RDF exporter.

## Testing Requirements (Implement With This RFC)
### Unit Tests
- Validate RDF graph creation for a single row.

### Integration Tests
- Generate `.trig`, `.nquads`, `.jsonld` from fixture data and confirm files are non-empty.

### Regression Tests
- Snapshot fixture output hashes for each format and compare to golden files.

## Output Location
All new implementation for the roadmap must live under:
- `./pkg_20260126_roadmap/`
