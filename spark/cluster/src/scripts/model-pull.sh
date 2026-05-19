#!/usr/bin/env bash
# model-pull.sh — fetch a HuggingFace repo into the flat ~/Models/<org>/<name>
# layout that the vLLM compose expects. Idempotent.
#
# Hosts come from cluster.env ($REPLICAS, $SSH_USER).
#
# Usage:
#   ./model-pull.sh <host>|all <org/repo>
#   ./model-pull.sh starsky RedHatAI/Qwen3-Coder-Next-NVFP4
#   ./model-pull.sh all     QuantTrio/Qwen3.6-35B-A3B-AWQ
#
# Reads HF_TOKEN from ~$SSH_USER/spark-deploy/vllm/.env on the remote host
# (deployed by deploy.sh). Uses the locally-built vllm-spark image's `hf` CLI
# via `--entrypoint hf` so we don't need huggingface_hub installed on the host.

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/load-config.sh
. "$script_dir/lib/load-config.sh"

REMOTE_USER="$SSH_USER"

usage() {
  cat >&2 <<EOF
Usage: $0 <host>|all <org/repo>

Examples:
  $0 starsky RedHatAI/Qwen3-Coder-Next-NVFP4
  $0 all     QuantTrio/Qwen3.6-35B-A3B-AWQ
EOF
  exit 2
}

[[ $# -eq 2 ]] || usage
HOST="$1"; REPO="$2"

pull_one() {
  local host="$1"
  echo ">> [$host] pull $REPO into ~/Models/$REPO"
  ssh "$REMOTE_USER@$host" "
    set -e
    mkdir -p ~/Models
    docker run --rm \
      --user 1000:1000 \
      --entrypoint hf \
      -v ~/Models:/models \
      --env-file ~/spark-deploy/vllm/.env \
      vllm-spark:latest \
      download '$REPO' --local-dir '/models/$REPO' --quiet
    du -sh ~/Models/$REPO | sed 's/^/   /'
  "
}

if [[ "$HOST" == "all" ]]; then
  for h in $REPLICAS; do
    pull_one "$h"
  done
else
  pull_one "$HOST"
fi
