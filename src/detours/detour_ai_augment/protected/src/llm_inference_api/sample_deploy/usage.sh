#!/bin/bash

if [[ ! -v WORK_REPO_DIR ]]; then
  echo "WORK_REPO_DIR environment variable is not set. Do it before running the script. Set it to the path to the repo that contains this script. " >&2
  exit 1
fi

SUBREPO_PATH="src/detours/detour_ai_augment/src/llm_inference_api/sample_deploy"

python3 "$WORK_REPO_DIR/$SUBREPO_PATH/proxy.py" summary \
        --db "$HOME/.local/state/llama-server/usage.sqlite"
