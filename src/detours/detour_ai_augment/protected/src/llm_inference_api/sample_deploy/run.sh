#!/bin/bash

# fail on errors
set -euo pipefail

# # load aliases
# shopt -s expand_aliases
# if [ -f "$HOME/.bashrc" ]; then
#   source "$HOME/.bashrc"
# fi

if [[ ! -v MODELS_DIR ]]; then
  echo "MODELS_DIR environment variable is not set. Do it before running this script. Set it to the path where model subdirectories are located. Review model paths below to see what tree the script expects. " >&2
  exit 1
fi

if [[ ! -v DEVICE_FINGERPRINT ]]; then
  echo "DEVICE_FINGERPRINT environment variable is not set. If you want your device to be shown in the model slugs, set it before running this script, e.g.: " >&2
  SAMPLE_MAC_FINGERPRINT="Mac16_12/10/10/24/512"
  SAMPLE_SPARK_FINGERPRINT="NVIDIA_DGX_Spark/GB10/128/4TB"
  echo "DEVICE_FINGERPRINT=\"$SAMPLE_MAC_FINGERPRINT\"" >&2
  echo "DEVICE_FINGERPRINT=\"$SAMPLE_SPARK_FINGERPRINT\"" >&2
  read -r -p "Do you still want to continue? [y/N] " reply
  case "$reply" in
    [yY]|[yY][eE][sS])
      ;;
    *)
      exit 1
      ;;
  esac
fi

SCRIPT_PATH="${BASH_SOURCE[0]}"  # this script
WORK_REPO_DIR="$(dirname "$(dirname "$SCRIPT_PATH")")"  # one level up
SUBREPO_PATH="src/detours/detour_ai_augment/src/llm_inference_api/sample_deploy"
PROXY_PY="$WORK_REPO_DIR/$SUBREPO_PATH/proxy.py"  # as of now
[[ -f "$PROXY_PY" ]] || { echo "proxy script not found: $PROXY_PY" >&2; exit 1; }

usage() {
  echo "Usage: $0 {gpt|gemma|ministral|qwen} [key/mode] [mode]"
  echo "  Default mode for all models: repro"
  echo
  echo "  gpt [mode]             Run GPT OSS 20b (reasoning: high)"
  echo "  gemma [model] [mode]   Run Gemma 3/4 (reasoning: off)"
  echo "                         Models: 31b, e4b, 27b, 12b, 4b, 1b"
  echo "  ministral [mode]       Run Ministral 3 14B Reasoning (reasoning: on)"
  echo "  qwen [mode]            Run Qwen 3 30B A3B (reasoning: on)"
  echo "  ----------------------------------------------------------"
  echo "  Available modes: fast, repro"
}

# proxy/db env defaults
export PROXY_HOST="${PROXY_HOST:-0.0.0.0}"
export PROXY_PORT="${PROXY_PORT:-8000}"
export BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
export BACKEND_PORT="${BACKEND_PORT:-8001}"
export INJECT_OAI_STREAM_USAGE="${INJECT_OAI_STREAM_USAGE:-1}"
export DB_PATH="${DB_PATH:-$HOME/.local/state/llama-server/usage.sqlite}"
export OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"

# sqlite batching knobs (optional)
export SQLITE_BATCH_N="${SQLITE_BATCH_N:-100}"
export SQLITE_BATCH_MS="${SQLITE_BATCH_MS:-250}"

PROXY_PID=""

need_slug() {
  local slug="${1:-}"
  [[ -n "$slug" ]] || { echo "Missing pricing slug env var. Example: openrouter/openai/gpt-4" >&2; exit 1; }
}

wait_port() { # host port
  local host="$1" port="$2"
  for _ in {1..200}; do
    (echo >/dev/tcp/"$host"/"$port") >/dev/null 2>&1 && return 0
    sleep 0.05
  done
  echo "timeout waiting for $host:$port" >&2
  return 1
}

start_proxy() {
  local model_alias="$1"
  local pricing_slug="$2"
  need_slug "$pricing_slug"

  export MODEL_ALIAS="$model_alias"
  export PRICING_SLUG="$pricing_slug"

  python3 -u "$PROXY_PY" serve &
  PROXY_PID=$!

  sleep 0.1
  kill -0 "$PROXY_PID" 2>/dev/null || { echo "proxy failed to start" >&2; exit 1; }
  wait_port "127.0.0.1" "$PROXY_PORT"
}

# --- robustly kill proxy on Ctrl-C / termination, without hanging ---
_stop_pid_fast() { # pid
  local pid="${1:-}"
  [[ -n "$pid" ]] || return 0
  kill -0 "$pid" 2>/dev/null || return 0

  # try graceful
  kill -TERM "$pid" 2>/dev/null || true

  # wait briefly (don’t freeze the wrapper if the proxy is wedged)
  for _ in {1..60}; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.05
  done

  # last resort
  kill -KILL "$pid" 2>/dev/null || true
}

stop_proxy() {
  if [[ -n "${PROXY_PID:-}" ]]; then
    _stop_pid_fast "$PROXY_PID" || true
  fi
  PROXY_PID=""
}

# When you press Ctrl-C, bash runs this trap AFTER the foreground llama-server gets SIGINT.
# This makes sure the proxy dies too (so :8000 is released).
cleanup() {
  stop_proxy
}
trap cleanup EXIT INT TERM
# --- end robust kill ---

# mode vars
extra_args=""

# Helper to set performance variables based on mode
set_mode_vars() {
  local mode_key="${1:-repro}"
  case "$mode_key" in
    repro)
      seed="42"
      temp="0.8"
      gpu_layers="-1"  # auto
      batch_size="1"
      ubatch_size="1"
      threads="1"
      parallel="1"
      ;;
    fast)
      seed="42"  # for more consistency anyway
      temp="0.8"  # 0.8 by default, for better quality
      gpu_layers="99"  # offload all to VRAM
      batch_size="4096"  # Claude: "2048 or even 4096 should work fine" (rather than 1024); default: 2048
      ubatch_size="2048"  # Claude: "is typically better than 1024 for memory efficiency while maintaining speed"; default: 512
      threads="1"  # Metal handles generation anyway
      parallel="1"  # default as we don't have concurrent API calls
      #extra_args="--mlock"  # force system to keep model in RAM rather than swapping or compressing
      #extra_args="--no-mmap"  # do not memory-map model (slower load but may reduce pageouts if not using mlock)
      #extra_args="--cache-type-k q8_0 --cache-type-v q8_0"  # Claude: "model is already at ~4-bit precision... Quantizing KV to q8_0 is relatively safer"
      #extra_args="--no-warmup"  # skips empty run and may get borderline models running
      ;;
    *)
      echo "Unknown reproducibility mode: $mode_key"
      return 1
      ;;
  esac
}

gpt() {
  set_mode_vars "${1:-repro}" || return 1
  local precision="mxfp4"
  local alias_name="localhost/ggml-org/gpt-oss-20b-GGUF:${precision}${DEVICE_FINGERPRINT:+@$DEVICE_FINGERPRINT}"
  local pricing_slug="openrouter/openai/gpt-oss-20b"
  start_proxy "$alias_name" "$pricing_slug"

  llama-server \
  --host 0.0.0.0 \
    --port "$BACKEND_PORT" \
  --model "$MODELS_DIR/gpt-oss-20b/lfs/gpt-oss-20b-mxfp4.gguf" \
    --alias "$alias_name" \
  --ctx-size 81920 \
  --seed "$seed" \
  --temp "$temp" \
  --samplers "penalties;dry;top_n_sigma;top_k;typ_p;top_p;min_p;xtc;temperature" \
  --gpu-layers "$gpu_layers" \
  --ubatch-size "$ubatch_size" \
  --batch-size "$batch_size" \
  --no-cont-batching \
  --threads "$threads" \
  --parallel "$parallel" \
  --flash-attn on \
  --jinja \
  --chat-template-kwargs '{"reasoning_effort": "high"}' \
  --verbose \
  --metrics \
  ${extra_args:-}
}

gemma() {
  local model_key="${1:-12b}"
  set_mode_vars "${2:-repro}" || return 1
  local model_path mmproj_path alias_name pricing_slug

  case "$model_key" in
    31b)
      model_path="$MODELS_DIR/gemma-4-31b-it/lfs/gemma-4-31B-it-f16.gguf"
      mmproj_path="$MODELS_DIR/gemma-4-31b-it/lfs/mmproj-gemma-4-31B-it-f16.gguf"
      precision="f16"
      alias_name="localhost/ggml-org/gemma-4-31B-it-GGUF:${precision}${DEVICE_FINGERPRINT:+@$DEVICE_FINGERPRINT}"
      pricing_slug="openrouter/google/gemma-4-31b-it"
      ;;
    e4b)
      model_path="$MODELS_DIR/gemma-4-e4b-it/lfs/gemma-4-e4b-it-Q4_K_M.gguf"
      mmproj_path="$MODELS_DIR/gemma-4-e4b-it/lfs/mmproj-gemma-4-e4b-it-f16.gguf"
      precision="q4_k_m"
      alias_name="localhost/ggml-org/gemma-4-E4B-it-GGUF:${precision}${DEVICE_FINGERPRINT:+@$DEVICE_FINGERPRINT}"
      # unavailable on openrouter - using ballpark based on 4b/12b/27b/31b/26b a4b pricing
      pricing_slug="localhost/0.09/0.27"
      ;;
    27b)
      model_path="$MODELS_DIR/gemma-3-27b-it-qat/lfs/gemma-3-27b-it-q4_0.gguf"
      mmproj_path="$MODELS_DIR/gemma-3-27b-it-qat/lfs/mmproj-model-f16-27B.gguf"
      precision="q4_0"
      alias_name="localhost/google/gemma-3-27b-it-qat-q4_0-gguf:${precision}${DEVICE_FINGERPRINT:+@$DEVICE_FINGERPRINT}"
      pricing_slug="openrouter/google/gemma-3-27b-it"
      ;;
    12b)
      model_path="$MODELS_DIR/gemma-3-12b-it-qat/lfs/gemma-3-12b-it-q4_0.gguf"
      mmproj_path="$MODELS_DIR/gemma-3-12b-it-qat/lfs/mmproj-model-f16-12B.gguf"
      precision="q4_0"
      alias_name="localhost/google/gemma-3-12b-it-qat-q4_0-gguf:${precision}${DEVICE_FINGERPRINT:+@$DEVICE_FINGERPRINT}"
      pricing_slug="openrouter/google/gemma-3-12b-it"
      ;;
    4b)
      model_path="$MODELS_DIR/gemma-3-4b-it-qat/lfs/gemma-3-4b-it-q4_0.gguf"
      mmproj_path="$MODELS_DIR/gemma-3-4b-it-qat/lfs/mmproj-model-f16-4B.gguf"
      precision="q4_0"
      alias_name="localhost/google/gemma-3-4b-it-qat-q4_0-gguf:${precision}${DEVICE_FINGERPRINT:+@$DEVICE_FINGERPRINT}"
      pricing_slug="openrouter/google/gemma-3-4b-it"
      ;;
    1b)
      model_path="$MODELS_DIR/gemma-3-1b-it-qat/lfs/gemma-3-1b-it-q4_0.gguf"
      precision="q4_0"
      alias_name="localhost/google/gemma-3-1b-it-qat-q4_0-gguf:${precision}${DEVICE_FINGERPRINT:+@$DEVICE_FINGERPRINT}"
      # unavailable on openrouter - using ballpark based on 4b/12b/27b pricing
      pricing_slug="localhost/0.04/0.04"
      ;;
    *) echo "Unknown Gemma model: $model_key"; return 1 ;;
  esac

  start_proxy "$alias_name" "$pricing_slug"

    llama-server \
        --host 0.0.0.0 \
        --port "$BACKEND_PORT" \
        --model "$model_path" \
        ${mmproj_path:+--mmproj "$mmproj_path"} \
        --alias "$alias_name" \
        --ctx-size 32768 \
        --seed "$seed" \
        --temp "$temp" \
        --samplers "penalties;dry;top_n_sigma;top_k;typ_p;top_p;min_p;xtc;temperature" \
        --gpu-layers "$gpu_layers" \
        --ubatch-size "$ubatch_size" \
        --batch-size "$batch_size" \
        --no-cont-batching \
        --threads "$threads" \
        --parallel "$parallel" \
        --flash-attn on \
        --verbose \
        --metrics \
        --reasoning off \
        ${extra_args:-}
}

ministral() {
  set_mode_vars "${1:-repro}" || return 1
  local model_path="$MODELS_DIR/ministral-3-14b-reasoning-2512/lfs/Ministral-3-14B-Reasoning-2512-Q4_K_M.gguf"
  local precision="q4_k_m"
  local alias_name="localhost/mistralai/Ministral-3-14B-Reasoning-2512-GGUF:${precision}${DEVICE_FINGERPRINT:+@$DEVICE_FINGERPRINT}"
  local pricing_slug="openrouter/mistralai/ministral-14b-2512"
  start_proxy "$alias_name" "$pricing_slug"

  llama-server \
    --host 0.0.0.0 --port "$BACKEND_PORT" \
    --model "$model_path" \
    --alias "$alias_name" \
    --ctx-size 32768 --seed "$seed" --temp "$temp" --gpu-layers "$gpu_layers" \
    --samplers "penalties;dry;top_n_sigma;top_k;typ_p;top_p;min_p;xtc;temperature" \
    --ubatch-size "$ubatch_size" --batch-size "$batch_size" --threads "$threads" \
    --no-cont-batching \
    --jinja --reasoning-format deepseek \
    --parallel "$parallel" --flash-attn on --verbose
}

qwen() {
  set_mode_vars "${1:-repro}" || return 1
  local precision="q4_k_m"
  local alias_name="localhost/qwen/Qwen3-30B-A3B-GGUF:${precision}${DEVICE_FINGERPRINT:+@$DEVICE_FINGERPRINT}"
  local pricing_slug="openrouter/qwen/qwen3-30b-a3b"
  start_proxy "$alias_name" "$pricing_slug"

  llama-server \
    --host 0.0.0.0 --port "$BACKEND_PORT" \
    --model "$MODELS_DIR/qwen3-30b-a3b/lfs/Qwen3-30B-A3B-Q4_K_M.gguf" \
    --alias "$alias_name" \
    --ctx-size 32768 --seed "$seed" --temp "$temp" --gpu-layers "$gpu_layers" \
    --samplers "penalties;dry;top_n_sigma;top_k;typ_p;top_p;min_p;xtc;temperature" \
    --ubatch-size "$ubatch_size" --batch-size "$batch_size" --threads "$threads" \
    --no-cont-batching \
    --jinja --reasoning-format deepseek \
    --parallel "$parallel" --flash-attn on --verbose
}

# Call the function based on the first argument
if [[ "${1:-}" == "gpt" ]]; then
  gpt "${2:-}"
elif [[ "${1:-}" == "gemma" ]]; then
  gemma "${2:-}" "${3:-}"
elif [[ "${1:-}" == "ministral" ]]; then
  ministral "${2:-}"
elif [[ "${1:-}" == "qwen" ]]; then
  qwen "${2:-}"
else
  usage
fi
