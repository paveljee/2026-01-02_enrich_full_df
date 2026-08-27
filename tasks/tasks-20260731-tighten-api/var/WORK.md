# HTTP request log v1/v2 coercion fix

## Objective

Make the shared `HttpRequestLogRecord` faithfully validate schema v1 and v2,
with `coerce_schema_v1` acting only as an explicit v1-to-v2 migration request.

## Required behavior

| Input | `coerce_schema_v1` | Result |
|---|---:|---|
| valid v1 | false/absent | valid v1 object |
| invalid v1 | false/absent | reject as v1 |
| valid v1 | true | validate original v1, then produce v2 object |
| invalid v1 | true | reject before migration |
| v2 | true/false/absent | validate as v2; flag value has no effect |

Schema v1 must retain its original wire behavior: v2-only fields are absent on
serialization and produce native field-level Pydantic `extra_forbidden` errors
on input. Its non-null `response_body: str` rule must produce Pydantic's native
`string_type` error. Schema v2 permits a null response body.

## Implementation state

- `HttpRequestLogRecord.validate_versioned_fields()` now fully validates an
  explicit v1 projection before opt-in promotion. The migration directive is
  removed only from that validation copy, then the promoted input continues
  through ordinary v2 field validation.
- Native v2 no longer undergoes any v1 projection, regardless of the flag.
- Version-specific v1 errors use `ValidationError.from_exception_data()` with
  native `extra_forbidden` and `string_type` error details and field locations,
  replacing root-level custom `ValueError` messages.
- Focused tests cover every matrix row, migration round-trip, invalid v1 before
  migration, and invalid v2 with the flag absent/false/true.
- Two v1-only OpenAlex consumers now assert their already-guaranteed non-null
  response-body invariant so the v2 nullable type remains mypy-safe.
- Pre-existing staged changes in the model/tests and the unrelated detour README
  remain preserved; no staging or unstaging was performed.

## Verification state

- Focused test suite: 21 passed.
- Focused Ruff: passed before the final small test additions; rerun pending.
- Focused mypy previously exposed only the two now-fixed OpenAlex narrowings;
  rerun pending.
- `git diff --check`: passed before final small edits; rerun pending.
- Final repository-prescribed verification contour remains pending.
