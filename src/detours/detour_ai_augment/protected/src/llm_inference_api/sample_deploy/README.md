Example `~/.zshrc`
(replace `/path/to` placeholders and other variables with actual values):

```shell
# Sample installation of llama.cpp binaries 
LLAMA_CPP_RELEASE="b10295"
export PATH="$HOME/.local/bin/llama-${LLAMA_CPP_RELEASE}:$PATH"

# Sample installation of run and usage scripts
DEVICE_FINGERPRINT="Mac16_12/10/10/24/512"
WORK_REPO_DIR="/path/to/this/repo"
MODELS_DIR="/path/to/dir/with/gguf/models"
SUBREPO_PATH="src/detours/detour_ai_augment/src/llm_inference_api/sample_deploy"
alias chat='MODELS_DIR="$MODELS_DIR" DEVICE_FINGERPRINT="$DEVICE_FINGERPRINT" bash "$WORK_REPO_DIR/$SUBREPO_PATH/run.sh"'
alias usage='WORK_REPO_DIR="$WORK_REPO_DIR" bash "$WORK_REPO_DIR/$SUBREPO_PATH/summary.sh"'
```
