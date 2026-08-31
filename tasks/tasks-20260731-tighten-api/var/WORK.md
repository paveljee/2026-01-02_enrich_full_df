# HttpRequestLogRecord schema 1.1

## Scope

Replace the provisional schema-v2 designation with schema 1.1. The evolved
schema is additive/relaxing and its reader retains the complete schema-v1
contract, so a major-version designation overstates the compatibility change.

Represent semantic versions as strings while retaining the legacy integer
wire value exactly: `HttpRequestLogSchemaVersion = Literal[1, "1", "1.1"]`.
String `"1"` is the canonical v1 producer value; readers and cache matching
continue to accept integer `1` as the same v1 schema.

## Corrected implementation contour

- Native schema v1 omits `record_id` when serialized and rejects it as a
  v1.1-only input field.
- Opt-in schema-v1 coercion validates the native v1 input, promotes it to v1.1,
  and then generates the UUIDv7 default.
- Native schema 1.1 generates a unique UUIDv7 when omitted and preserves it
  through JSON round-trip.
- Main-pipeline SciSciNet assertions remain schema-v1 assertions and therefore
  must not include `record_id`.

## Status

The 1.1 conversion is complete across the active shared model/constants,
Backend producer/reader, tests, and README workflow. Historical task records
remain unchanged. The workflow's full inline private-commit HTTP record JSON
contour is restored with schema `"1.1"`, every current model field, the complete
nested commit body, and the existing Structured Field header values.

Passing through Pixi:

- HTTP request-log module: 26 passed.
- OpenAlex/SciSciNet append and legacy integer-v1 cache reuse: 3 passed.
- Lightweight Backend authoritative-record probe emits string `"1.1"`.
- Ruff on all affected Python files: passed.
- Mypy on the shared model/constants/test contour: passed.
- Main suite: 100 passed, 34 failed, 4 skipped. The 34 failures remain the
  unavailable `splink_udfs`/`httpfs` downloads and missing host fixtures.
- `git diff --check`: passed.

The directly relevant Backend test is blocked before its body by the checkout's
stale autouse fixture expecting `dashboard.ui.LIMA_CONFIG_PATH`. Broad detour
mypy likewise reports existing stale API/test errors. The aggregate pre-commit
task still cannot start because `test-detour-mode0-econ-stats` is not registered
in the `detour-ai-augment` Pixi environment.
