# Active context

- Task: `tasks/tasks-20261104-post-prod`; Pixi feature `default`. Operator is debugging OGHIST relative-path failure in `tests/test_detours/test_detour_step4_breakdown.py::test_slow_real_config_pre_deviation_full_equivalence`. They explicitly authorized the narrowest change to `_write_slow_config` after rolling back a previous patch.
- Repository constraints: read `.aicode/AGENTS.md` and apply Kernighan–Pike skill for substantive work (both done); Git read-only; never run `src.repl` or detours; do not inspect data/artifacts except designated main DuckDB read-only (not needed here); preserve human-signed-off comments. Use Pixi for Python/tests. WORK is agent-maintained; TASK is human-owned.

# Diagnosis

- Operator's subprocess fails in main mode, Step 01, while hashing World Bank XLSX: it looks for `resources/OGHIST_2025_07_01.xlsx` under pytest's temporary directory rather than repository root.
- `config.repl.json:109` now gives relative `resources/OGHIST_2025_07_01.xlsx`. Test's `_resource_paths_from_config` checks resource existence relative to repo cwd, so preflight passes. `_write_slow_config` copies that relative input path unchanged while relocating config to `tmp_path`. `_run_pipeline_subprocess` sets child cwd to `config_path.parent`, the temp directory. `register_resource` resolves the relative path against that child cwd, causing the exact missing-file path in traceback. `pandoc_reference_docx` is another relative input requiring the same treatment; output paths are already redirected to tmp and must remain there.
- Git history: the test helper, subprocess cwd, and slow test were added in Feb 2026 and are unchanged. `c0f832e` (Nov 2, 10:42) changed OGHIST path from absolute to relative `data/...`; `59c7393` (Nov 2, 10:54) moved it to relative `resources/...`. Therefore a prior pass with the absolute path is fully consistent with the evidence; the path change is the regression trigger. The 12-minute intermediate `data/...` state may have skipped if the file was absent; no evidence it passed there.

# Current state and verification

- The operator's earlier staged change moved only `_base_config_dict`'s synthetic fixture XLSX to `tmp_path/resources`; that fixture is not used by the failing slow real-config test. At last inspection after applying current patch, `git diff --cached` was empty and `git status --short` showed only unstaged WORK and test-file modifications; agent ran no Git write commands.
- `_write_slow_config` now has exactly one new assignment (three lines) anchoring `files_config.world_bank_xlsx.path` to the original config's directory before writing the temp config. No other inputs, tests, production code, or subprocess cwd changed. `git diff --check` passed. The slow test was not run because it launches prohibited main pipeline/detour code; no runtime pass claimed.
