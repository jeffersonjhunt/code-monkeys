#!/usr/bin/env bash
# model-pull.sh — fetch a HuggingFace repo into the flat $MODEL_DIR/<org>/<name>
# layout that the vLLM compose expects (default /srv/models). Idempotent.
#
# Hosts come from cluster.env ($REPLICAS, $SSH_USER).
#
# Usage:
#   ./model-pull.sh <host>|all <org/repo>
#   ./model-pull.sh starsky RedHatAI/Qwen3-Coder-Next-NVFP4
#   ./model-pull.sh all     QuantTrio/Qwen3.6-35B-A3B-AWQ
#
# Reads HF_TOKEN from ~$SSH_USER/spark-deploy/vllm/.env on the remote host
# (deployed by deploy.sh). Uses the locally-built cuda-vllm image's `hf` CLI
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
  echo ">> [$host] pull $REPO into $MODEL_DIR/$REPO"
  ssh "$REMOTE_USER@$host" "
    set -e
    # Stage into the SAME directory the vllm stack mounts at /models. This used to pull into
    # ~/Models while vLLM served \$MODEL_DIR, so a freshly pulled model was invisible to the
    # server. Never re-derive the path here — it comes from cluster.env via load-config.sh.
    if [ ! -d '$MODEL_DIR' ]; then
      echo \"error: $MODEL_DIR does not exist on $host — run bootstrap.sh on it first\" >&2
      exit 1
    fi
    # \$SSH_USER often cannot write \$MODEL_DIR directly (it belongs to the admin user), but it
    # is in the docker group — so download as the directory's own uid:gid rather than assuming.
    owner=\$(stat -c '%u:%g' '$MODEL_DIR')
    docker run --rm \
      --user \"\$owner\" \
      --entrypoint hf \
      -v '$MODEL_DIR':/models \
      --env-file ~/spark-deploy/vllm/.env \
      cuda-vllm:latest \
      download '$REPO' --local-dir '/models/$REPO' --quiet
    du -sh '$MODEL_DIR/$REPO' | sed 's/^/   /'
  "
}

if [[ "$HOST" == "all" ]]; then
  for h in $REPLICAS; do
    pull_one "$h"
  done
else
  pull_one "$HOST"
fi
