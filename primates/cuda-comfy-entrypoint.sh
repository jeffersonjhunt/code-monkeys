#!/bin/bash
set -e

EXTRA_ARGS=()

MODEL_PATHS="${COMFYUI_MODEL_PATHS:-/home/codemonkey/workspace/comfy-ui-model-paths.yaml}"
if [ -f "$MODEL_PATHS" ]; then
  EXTRA_ARGS+=(--extra-model-paths-config "$MODEL_PATHS")
fi

exec python3 main.py --listen 0.0.0.0 "${EXTRA_ARGS[@]}" "$@"
