> [!NOTE]
> Generated using Codex CLI
> gpt-5.6-sol xhigh
> on 2026-09-03;
> see corresponding rollout
> in the chat directory for
> `tasks/tasks-20260731-tighten-api`.
>
> Automated reference for this workflow:
> `pixi run test-detour-ai-augment`.
>
> Signed-off: Pavel

# How to manually reproduce the operator full workflow
Use the following sequence.

> **Important:** using `config_ai_augment.json` operates on the real configured detour outputs. Unlike the operator test, this does not construct an isolated temporary database/replay/CAS environment.

## 1. Start and check AIVM

From the repository root:

```bash
cd /Volumes/home/aicode/2026-01-02_enrich_full_df

pixi run -e detour-ai-augment limactl start aivm

pixi run -e detour-ai-augment limactl shell --workdir=/ aivm \
  sudo systemctl is-active --quiet aivm-appendwatch.service

pixi run -e detour-ai-augment limactl shell --workdir=/ aivm \
  sudo --user ai --set-home \
  /home/ai/.local/bin/codex login status
```

If Codex is not authenticated:

```bash
pixi run -e detour-ai-augment limactl shell --workdir=/ aivm \
  sudo --user ai --set-home \
  /home/ai/.local/bin/codex login --device-auth
```

A complete redeployment, if intentionally desired, is:

```bash
export OPENALEX_API_KEY="$(
  pixi run -e detour-ai-augment python -c '
import os
from dotenv import dotenv_values

path = os.path.join(os.environ["PIXI_PROJECT_ROOT"], ".env")
print(dotenv_values(path).get("OPENALEX_API_KEY", ""), end="")
'
)"

pixi run -e detour-ai-augment \
  bash src/detours/detour_ai_augment/src/agent_runtime/deploy.sh
```

That deployment script may delete and recreate the existing `aivm`.

## 2. Start Backend — terminal 1

Choose the desired namekey and run:

```bash
cd /Volumes/home/aicode/2026-01-02_enrich_full_df

export OPENALEX_API_KEY="$(
  pixi run -e detour-ai-augment python -c '
import os
from dotenv import dotenv_values

path = os.path.join(os.environ["PIXI_PROJECT_ROOT"], ".env")
print(dotenv_values(path).get("OPENALEX_API_KEY", ""), end="")
'
)"

test -n "$OPENALEX_API_KEY"

export FASTAPI_DETOUR_NAMEKEY='{"ktp.first_name":"A.","ktp.last_name":"Sheikh"}'
export FASTAPI_DETOUR_APPENDWATCH_REPORT='/Volumes/home/aicode/aivm/home/ai/.aivm-control/appendwatch/appendwatch-tree.txt'
export FASTAPI_DETOUR_CODEX_SESSIONS_DIR='/home/ai/.codex/sessions'
export FASTAPI_DETOUR_DASHBOARD_SOCKET="/tmp/detour-manual-${UID}.sock"

pixi run -e detour-ai-augment \
  python -m src.detours.detour_ai_augment.src.backend.api \
  --config config_ai_augment.json
```

Leave this terminal open. Backend is deliberately waiting for one line on stdin containing the Codex session UUID, while already serving requests.

The appendwatch path above is the current default deployment path. If AIVM was deployed with a custom `--mount`, substitute the corresponding host-side report path.

## 3. Start Codex with the reverse tunnel — terminal 2

```bash
cd /Volumes/home/aicode/2026-01-02_enrich_full_df

pixi run -e detour-ai-augment bash -c '
printf "%s\n" "http://127.0.0.1:8612/openapi.json" |
ssh \
  -F "$HOME/.lima/aivm/ssh.config" \
  -o ProxyJump=lima-aivm \
  -o HostName=127.0.0.1 \
  -o Port=22022 \
  -o User=ai \
  -o IdentityFile="$HOME/.local/share/aivm/.ssh/id_ed25519" \
  -o IdentitiesOnly=yes \
  -o BatchMode=yes \
  -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no \
  -o ForwardAgent=no \
  -o ClearAllForwardings=no \
  -o UserKnownHostsFile="$HOME/.local/share/aivm/.ssh/known_hosts" \
  -o HostKeyAlias=lima-aivm-ai \
  -o StrictHostKeyChecking=accept-new \
  -o ExitOnForwardFailure=yes \
  -R 127.0.0.1:8612:127.0.0.1:8612 \
  aivm-ai \
  "cd /home/ai &&
   . /home/ai/workdir/.openalex.env &&
   exec /home/ai/.local/bin/codex exec --skip-git-repo-check -"
'
```

Codex should print something like:

```text
session id: 01xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## 4. Supply the session ID to Backend

Return to **terminal 1**, type only that UUID, and press Enter:

```text
01xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

This timing is intentional:

1. Codex may already perform its first `GET /pull`.
2. Backend has assigned and logged that pull’s `record_id`.
3. The session ID only needs to be known before Codex’s first `POST /push`.
4. Backend finds the corresponding rollout JSONL from the supplied session UUID.

## 5. Let the workflow finish

Codex should repeatedly:

1. `GET /pull`
2. perform the requested work
3. `POST /push`
4. follow the returned `Location`
5. continue until Backend returns `410 Gone`

On normal completion, the Codex/SSH command exits. Then stop Backend with `Ctrl+C`.

To mirror the operator test, leave AIVM running. Otherwise stop it explicitly:

```bash
pixi run -e detour-ai-augment limactl stop aivm
```

This manual contour omits only the Dashboard queue, Playwright interaction, Control Centre process supervision, and the operator test’s isolated-data sanctuary.
