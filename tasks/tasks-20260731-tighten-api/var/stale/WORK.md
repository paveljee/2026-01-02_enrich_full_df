# Tighten API — current handoff

## Operating rules

- Read this file and `tasks/tasks-20260731-tighten-api/src/TASK.md` in full
  immediately after every compaction; together they are the complete context.
- Keep this file current and standalone, replacing superseded content rather
  than retaining a progress diary.
- `src/TASK.md` is human-owned. Do not edit it, the frozen legacy SPEC, README,
  `.env.example`, sample runs, historical submissions/rollouts, or ground truth.
- Run every command through `pixi run`. Git is read-only. Apply edits only with
  a complete `pixi run apply_patch <<'PATCH' ... PATCH` command.
- Never remove or alter inline comments marked as signed off by the human.
- Verify only with `pixi run pre-commit 2>&1`; operator tests remain separate.

## Current objective

Provide only in chat a pytest-bdd operator scenario for the behavior at
`src/detours/detour_ai_augment/README.md:76`. It must depend on line 75 having
passed first, then connect to the real Agent Runtime over production SSH and
verify its required configuration. Only after the assertions pass may it print
the exact README source line. The proposed Python should contain only the test
and Given/When/Then function definitions. Do not create or edit production/test
files.

The literal source line is:

```text
1. The Human Operator connects\* to the AI Agent Runtime over the SSH (Secure Shell) protocol and configures it. This includes provisioning a Codex session and any environment variables required by the AI Agent Runtime.
```

## Active behavioral interpretation

No pytest dependency/order plugin is installed. The BDD Given step therefore
requires the line-75 pytest item to have been collected earlier with no prior
failure and requires the already started/provisioned `aivm` to accept
`limactl shell ... true`; line 76 does not provision or start it. The When step
then uses the production
`AIVM_SSH_CONNECTION_COMMAND` and target to prove SSH access as `ai`; checks the
Codex executable, config, sessions directory, and authenticated login status;
and verifies that `/home/ai/workdir/.openalex.env` is ai-owned, mode 600,
sourceable, and provides a nonempty `OPENALEX_API_KEY` without exposing it. The
Then step asserts the result and prints the exact line. The existing operator
task's `--capture=tee-sys` displays it.

## Current repository state

No production/test/feature implementation has been changed. Only this WORK
handoff was refreshed as required. The human-owned TASK remains modified.

## Next

Return the Gherkin and pytest-bdd proposal and await further instruction.
