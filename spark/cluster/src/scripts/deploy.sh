#!/usr/bin/env bash
# deploy.sh — sync a compose stack to a remote box and bring it up.
#
# Hosts and roles come from cluster.env (see cluster.env.example).
#
# Usage:
#   ./deploy.sh <host> <stack>...     # one host, one or more stacks
#   ./deploy.sh all                   # vllm on every replica, litellm on LB_HOST
#
# Examples:
#   ./deploy.sh hutch   vllm
#   ./deploy.sh minerva litellm       # the LB (LiteLLM replaced HAProxy 2026-06-28)
#   ./deploy.sh minerva haproxy       # retired fallback LB — never deployed by `all`
#   ./deploy.sh all
#
# Requires: tar, ssh keys to $SSH_USER@<host>.

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/load-config.sh
. "$script_dir/lib/load-config.sh"

REMOTE_USER="$SSH_USER"
REMOTE_BASE="/home/$REMOTE_USER/spark-deploy"
COMPOSE_DIR="$(cd "$script_dir/../compose" && pwd)"

# The vllm stack pulls the cuda-vllm primate from private ECR and gets its .env (HF_TOKEN + serving
# config) by decrypting hemlighet on the target — replacing the retired ship-image.sh (host->host
# docker save|ssh|load) and the tar'd plaintext .env. Matches g.deceiver's deploy path. The target host
# needs ~/.aws, an age key (~/.config/sops/age/keys.txt), and a hemlighet clone.
ECR_REGISTRY="${ECR_REGISTRY:-521147433280.dkr.ecr.us-east-1.amazonaws.com}"
NYCKEL="$ECR_REGISTRY/codemonkeys/nyckel:latest"

# Generate haproxy.cfg from haproxy.cfg.template by expanding $REPLICAS into
# `server <h> <h>:$VLLM_PORT check` lines on the # __REPLICAS__ marker, and
# substituting the public bind port (__LB_PORT__) from $LB_PORT.
render_haproxy_cfg() {
  local template="$COMPOSE_DIR/haproxy/haproxy.cfg.template"
  local out="$COMPOSE_DIR/haproxy/haproxy.cfg"
  if [[ ! -f "$template" ]]; then
    echo "error: missing $template" >&2
    return 1
  fi
  local server_lines=""
  for h in $REPLICAS; do
    server_lines+="    server $h $h:$VLLM_PORT check"$'\n'
  done
  # Strip the trailing newline so the inserted block matches the template's indent.
  server_lines="${server_lines%$'\n'}"
  awk -v block="$server_lines" -v lb_port="$LB_PORT" '
    /^[[:space:]]*#[[:space:]]*__REPLICAS__[[:space:]]*$/ { print block; next }
    { gsub(/__LB_PORT__/, lb_port); print }
  ' "$template" > "$out"
}

deploy_stack() {
  local host="$1"
  local stack="$2"

  if [[ ! -d "$COMPOSE_DIR/$stack" ]]; then
    echo "no such stack: $stack" >&2
    return 1
  fi

  # If a stack has a .env.example, require the real .env to exist before deploy — EXCEPT vllm, whose
  # .env now comes from hemlighet (decrypted on the target at deploy), not a local plaintext file.
  if [[ "$stack" != "vllm" && -f "$COMPOSE_DIR/$stack/.env.example" && ! -f "$COMPOSE_DIR/$stack/.env" ]]; then
    echo "missing $COMPOSE_DIR/$stack/.env — cp .env.example .env and fill in" >&2
    return 1
  fi

  if [[ "$stack" == "haproxy" ]]; then
    render_haproxy_cfg
  fi

  echo ">> [$host] sync $stack -> $REMOTE_BASE/$stack"
  ssh "$REMOTE_USER@$host" "mkdir -p '$REMOTE_BASE/$stack'"
  # tar streaming: no rsync dependency, preserves perms, includes dotfiles,
  # excludes .env.example and the template. For vllm we ALSO exclude .env — it's
  # a secret, delivered by decrypting hemlighet on the target, not shipped in the
  # clear. No --delete: remove stale files by hand if you rename or drop one.
  local -a tar_excludes=(--exclude='.env.example' --exclude='haproxy.cfg.template')
  [[ "$stack" == "vllm" ]] && tar_excludes+=(--exclude='.env')
  tar -C "$COMPOSE_DIR/$stack" "${tar_excludes[@]}" -cf - . | \
    ssh "$REMOTE_USER@$host" "tar -C '$REMOTE_BASE/$stack' -xpf -"

  # --force-recreate so bind-mounted config / .env changes are picked up. For vLLM the container
  # restarts and re-loads the model from disk cache (~5 min); for HAProxy/LiteLLM it's near-instant.
  if [[ "$stack" == "vllm" ]]; then
    echo ">> [$host] ECR login + decrypt .env (hemlighet) + pull + up ($stack)"
    ssh "$REMOTE_USER@$host" "REG='$ECR_REGISTRY' NYCKEL='$NYCKEL' BASE='$REMOTE_BASE/$stack' bash -s" <<'RSH'
set -euo pipefail
cd "$BASE"
# ECR login (containerized aws-cli; verify token non-empty — a cold aws-cli pull once yielded an
# empty token that "logged in" with no creds, then image pulls hit "no basic auth credentials").
docker image inspect amazon/aws-cli >/dev/null 2>&1 || docker pull -q amazon/aws-cli >/dev/null
TOK="$(docker run --rm -v "$HOME/.aws:/root/.aws:ro" amazon/aws-cli ecr get-login-password --region us-east-1)"
[ -n "$TOK" ] || { echo "deploy: empty ECR token (aws creds on $(hostname)?)" >&2; exit 8; }
echo "$TOK" | docker login --username AWS --password-stdin "$REG" >/dev/null
# secrets: decrypt the vllm env (HF_TOKEN + config) from hemlighet -> .env
[ -d "$HOME/hemlighet/.git" ] || { echo "deploy: ~/hemlighet not cloned on $(hostname) — clone it first" >&2; exit 9; }
git -C "$HOME/hemlighet" pull -q --ff-only origin main 2>/dev/null || true
docker run --rm -v "$HOME/.config/sops/age:/age:ro" -v "$HOME/hemlighet:/hl:ro" \
  -e SOPS_AGE_KEY_FILE=/age/keys.txt "$NYCKEL" \
  sops -d --input-type binary --output-type binary /hl/code-monkeys/cluster-vllm.env > .env.tmp
mv .env.tmp .env && chmod 600 .env
echo ">> decrypted .env from hemlighet"
docker compose pull
docker compose up -d --force-recreate --remove-orphans
docker logout "$REG" >/dev/null 2>&1 || true
RSH
  else
    echo ">> [$host] docker compose up -d --force-recreate ($stack)"
    ssh "$REMOTE_USER@$host" "cd '$REMOTE_BASE/$stack' && docker compose up -d --force-recreate --remove-orphans"
  fi
}

if [[ "${1:-}" == "all" ]]; then
  for h in $REPLICAS; do
    deploy_stack "$h" vllm
  done
  # The LB host runs the model-aware router (LiteLLM), which replaced the round-robin
  # HAProxy on 2026-06-28. The haproxy stack is retained for fallback but is deployed
  # explicitly (`deploy.sh <lb> haproxy`), never by `all`.
  deploy_stack "$LB_HOST" litellm
elif [[ $# -ge 2 ]]; then
  host="$1"; shift
  for stack in "$@"; do
    deploy_stack "$host" "$stack"
  done
else
  echo "Usage: $0 <host> <stack>... | all" >&2
  exit 2
fi
