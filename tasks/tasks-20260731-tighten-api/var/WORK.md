# HttpRequestLogRecord UUIDv7 identifier

## Scope

Surgically add `record_id: UUID` with a standard-library `uuid7` default
factory to schema v2 of the shared `HttpRequestLogRecord` while preserving the
schema-v1 wire contract.

## Corrected implementation contour

- Native schema v1 omits `record_id` when serialized and rejects it as a
  v2-only input field.
- Opt-in schema-v1 coercion validates the native v1 input, promotes it to v2,
  and then generates the UUIDv7 default.
- Native schema v2 generates a unique UUIDv7 when omitted and preserves it
  through JSON round-trip.
- Main-pipeline SciSciNet assertions remain schema-v1 assertions and therefore
  must not include `record_id`.

## Status

The schema correction is complete. Passing through Pixi:

- HTTP request-log module: 24 passed.
- The two schema-v1 SciSciNet log-shape tests: 2 passed with no test-file diff.
- Ruff and mypy on the affected model/test contour: passed.
- `git diff HEAD --check`: passed.

The main suite remains at 98 passed, 34 failed, and 4 skipped. The failures are
the checkout/environment baseline: unavailable `splink_udfs`/`httpfs` downloads
and missing host `/Volumes/...` fixtures. The aggregate `pre-commit` Pixi task
still cannot start because `test-detour-mode0-econ-stats` is not registered in
the `detour-ai-augment` environment; its component contour was previously run
explicitly and its unrelated baseline failures are unchanged.
