Sample installation on macOS:

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
