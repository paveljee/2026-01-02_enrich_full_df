# RFC: CLI test coverage improvements

Timestamp (UTC): 2026-01-28 19:14Z  
Author: Codex

## Plan

- Review prior RFC notes under `.aicode/rfc/` to understand previous work or guidance.
- Inspect `pkg_20251223_word_tables/src/cli.py` and its imported modules to understand current behavior and test surfaces.
- Review `pkg_20251223_word_tables/tests/` to catalog existing tests, identify missing coverage, and note outdated tests.
- Add/update unit tests for `cli.py` behaviors; add integration/regression tests where feasible.
- Add `ruff` and `mypy` as Pixi dependencies (`pixi add --pypi`) and wire them into Pixi tasks in `pyproject.toml`.
- Run tests and lint/type-check tasks via Pixi, ensure all pass.
- Document outcomes and actions in a "report" section appended to this RFC.

## Report

- Reviewed prior RFCs for the outer-dict refactor and matcher extraction to align new tests with the current CLI and matcher architecture.
- Audited existing tests in `pkg_20251223_word_tables/tests/`, fixed outdated imports and debug artifacts, and confirmed dataset-dependent tests remain skipped when fixtures are absent.
- Added focused unit tests for CLI helpers (`build_outer_dict_from_names`, file discovery, CSV header validation) and a mocked `process_documents` flow to validate output ZIP creation.
- Added matcher-focused tests to validate CSV and DOCX matching behavior, including cleaned-name matching logic.
- Updated matching logic in `DocxMatcher` to use element-wise string containment checks that operate correctly on the cross-joined data.
- Cleaned up lint/type issues in supporting modules (`name_utils`, `_vars`, `cli`) and ensured constants are typed for mypy.
- Added `ruff` and `mypy` to Pixi dependencies and configured tasks/config to run linting and typing checks.
- Ran Pixi tasks for ruff, mypy, and pytest; all checks now pass (with dataset-dependent tests skipped when data is unavailable).
