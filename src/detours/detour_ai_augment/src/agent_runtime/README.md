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
deployment opts into `0640` so only the dedicated audit group can additionally
read the atomically replaced report.

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
