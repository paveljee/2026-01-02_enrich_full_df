## Sample installation on macOS

```shell
REPO_DIR="/path/to/this/repo"
ENV_FILE_PATH="$REPO_DIR/.env"
DEPLOY_SCRIPT="$REPO_DIR/src/detours/detour_ai_augment/src/agent_runtime/deploy.sh"

cat >> ~/.zshrc <<EOF

aivm() {
    OPENALEX_API_KEY="\$(
        python -c 'from dotenv import dotenv_values; print(dotenv_values("$ENV_FILE_PATH").get("OPENALEX_API_KEY", ""), end="")'
    )" \\
    REPO_DIR="$REPO_DIR" \\
    bash "$DEPLOY_SCRIPT" "\$@"
}
EOF
```

Deployment creates one host-held Ed25519 key and authorizes its public key for
two private guest accounts. The Human Operator and Control Centre use `ai` to
run Codex. Backend uses `aivm-audit`, whose SSH authorization has no shell or
forwarding and accepts only the installed read protocol for Codex rollout
discovery/streaming and the configured appendwatch report. The report and the
protected audit configuration remain under the Lima `--mount` control
directory. Appendwatch retains its generic `0600` report default; this
deployment opts into `0640`. Because reverse SSHFS does not support assigning
guest ownership to this host-mounted directory, `aivm-audit` reads the
atomically replaced report only through its forced, narrowly scoped root
dispatcher rather than through direct filesystem access.

## Closing a manually operated session

Before ending or killing a manually operated Codex session or its full Backend,
the Human Operator sends the corresponding terminal request to the Backend's
Unix socket: `/completed`, `/failed`, or `/cancelled`. The request has an empty
body and the configured `Name-Key` header. For example, from the host repository
root, while the full Backend is still running:

```bash
NAMEKEY='{"ktp.first_name": "A.", "ktp.last_name": "Sheikh"}'
SOCKET_PATH="/tmp/detour-manual-${UID}.sock"
OUTCOME="completed"
NAME_KEY_HEADER="$(
  pixi run -e detour-ai-augment python -c '
import sys
from src.detours.detour_ai_augment.src.backend.api import name_key_header
print(name_key_header(sys.argv[1]), end="")
' "$NAMEKEY"
)"

curl --silent --show-error --include \
  --unix-socket "$SOCKET_PATH" \
  --request POST \
  --header "Name-Key: $NAME_KEY_HEADER" \
  "http://invalid/$OUTCOME"
```

Send `/cancelled` before killing Codex. On natural completion, send `/completed`
after Codex exits and before stopping Backend. `200 OK` confirms a complete
terminal rollout and appendwatch snapshot; `500 Internal Server Error` reports
a partial snapshot, whose actual response is still preserved in the replay log
while authoritative logging remains operational.

## OpenAI's official guide on reasoning effort
Captured from 
`https://developers.openai.com/api/docs/guides/reasoning.md` on
2026-09-04 11:37:43 UTC-4
and available at
`src/detours/detour_ai_augment/src/agent_runtime/docs/reasoning.md`.

Based on this guide,
`high` seems to be
the appropriate setting
for this detour's AI Agent Runtime.

On a separate note
(outside of this guide),
`high` seems to be
the highest option available
in ChatGPT Plus chat interface,
which may also signal that
this is sufficient
for most workflows.
