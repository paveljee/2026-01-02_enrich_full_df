# Tighten API — current handoff

## Purpose

This file contains only the live context needed to continue the current task after
compaction. Read this file and `tasks/tasks-20260731-tighten-api/src/TASK.md` in
full before doing anything else. Together they are the complete handoff; use only
focused repository lookups for implementation details.

## Operating constraints

- `src/TASK.md` is the immutable human specification. Do not edit it.
- Do not edit the frozen legacy SPEC, README, `.env.example`, sample runs,
  historical rollout/submission data, or ground-truth data.
- Every command uses `pixi run`. Git is read-only: do not stage, unstage, commit,
  reset, checkout, restore, or otherwise mutate Git state.
- Apply file edits through one complete, reviewable
  `pixi run apply_patch <<'PATCH' ... PATCH` command.
- Keep changes surgical. Do not add compatibility fallbacks for discarded
  schemas/databases and do not create new modules.
- Human-facing backend wording belongs in
  `backend/helpers/locale.py`. Tests belong in
  `src/detours/detour_ai_augment/tests`.
- Keep this handoff current whenever decisions, staged state, implementation
  state, or verification results change. Remove superseded material instead of
  accumulating history.

## Live objective and contract

- Implement all current requirements in TASK, including exhaustive v1/v2 Codex
  evidence assessment, immutable run-scoped retry baselines, structured
  withdrawal, standardized retry submissions, persistence/rendering, dedicated
  roundtrip tests, and executable requirement-to-evidence mapping.
- A first push is validated with
  `backend/helpers/data_models/submission.py::Submission`. Its public description
  and example are the legacy plain contract: every evidence-bearing variable,
  including race/ethnicity/language/culture, has `value` plus
  `web_search_excerpts`; optional comments have only `value`.
- A first Pydantic-valid but evidence-invalid push establishes the immutable
  baseline. Every later push for that sanctioned run is validated with
  `pydantic_to_paste.py::StandardizedSubmission`; retry guidance says
  standardized values are now required and includes that schema plus the full
  standardized L. Fei-Fei example. Pydantic-invalid first pushes create no
  baseline.
- A first push that is fully accepted persists `"NR"` as the standardized value
  for each evidence-bearing field. This does not require widening the retry
  schema's object-valued annotations: first-push conversion/persistence and
  retry validation are separate concerns.
- Retry immutability applies to raw field values and evidence as specified in
  TASK. Synthetic first-push NR values must not prevent a retry from supplying
  required standardized values after an evidence rejection.
- Each evidence-bearing variable gets a separate
  `ktp.ai_augment_*_standardized` DuckDB/card field immediately after its plain
  field. Store deterministic compact JSON for `standardized_value`; attach no
  duplicate footnotes. Hide only whole null/NA/NR standardized values in card
  display through a detour-local placeholder extension while retaining them in
  DuckDB.
- `pydantic_to_paste.py` remains the standalone schema shown to retrying agents.
  Ordinary academic-institution validation performs live OpenAlex/ROR checks;
  static fixture construction alone may bypass those checks with
  `model_construct`.
- Standardized scalar/list definitions remain typing aliases. Fixture-only
  `model_construct` assignments use their underlying validated-compatible
  scalar/list values directly; do not replace the aliases with Pydantic root
  models or add generic fixture machinery.

## Current repository and staged state

- Current HEAD: `64a06e2 detour ai augment: manually code two fixtures`.
- Current staged paths:
  - `backend/helpers/data_models/submission.py`
  - `backend/helpers/data_models/submission_fixture.py`
  - `backend/helpers/locale.py`
  - `backend/helpers/vars.py`
  - `tasks/tasks-20260731-tighten-api/manifest.json.old`
  - this WORK file
- `manifest.json.old` is operator-owned staged history of the former 39-line
  manifest. Preserve it.
- Accepted staged model changes currently make comments evidence-free through
  `CommentsSubmission`, add missing initial researcher-author evidence, add the
  retry author's ORCID/OpenAlex evidence, add the retry-example locale template,
  and derive standardized column labels/pairs from the evidence columns.
- No implementation wiring for the new two-model API flow, standardized
  persistence, or standardized card rendering has yet been completed.

## Current implementation findings

- The operator's latest fixture change preserves standardized typing aliases,
  assigns their scalar/list values directly under fixture-only
  `model_construct`, and retains the minimal non-generic `SubmissionFixture`.
  The previous alias-constructor import failure and generic-annotation mismatch
  are resolved.
- The focused Pydantic test currently fails during collection because it unpacks
  three fields from `schema.FieldSubmission`, which is now the plain two-field
  first-submission model. Tests must distinguish `FieldSubmission` from the
  standardized field model.
- Focused Ruff currently reports 12 findings across the staged files, including
  import/blank-line formatting and existing long fixture/constant lines. No
  current lint or test result is green, and no prior count should be relied on.
- `pixi run git diff --cached --check` passes.

## Next actions

1. Preserve the operator's accepted fixture/model choices and align the existing
   focused tests with the separate first/retry models.
2. Wire baseline-aware plain-versus-standardized body parsing, retry-only public
   schema/example guidance, and raw-only retry obligations in the existing API.
3. Add interleaved standardized persistence and placeholder-aware TXT/DOCX/UI
   card rendering, then implement the remaining TASK evidence-retry behavior.
4. Run focused tests, `pixi run test-detour-ai-augment-root`, and
   `pixi run lint`. Record only fresh results here.
5. Rebuild `build/AGENTS.md`, `build/SPECS.ipynb`, and `manifest.json` under the
   Makefile's atomic requirement-to-evidence rules, then run
   `pixi run --frozen make validate` from the task directory.
