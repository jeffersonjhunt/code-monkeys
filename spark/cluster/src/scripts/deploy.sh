#!/usr/bin/env bash
# deploy.sh — sync a compose stack to a remote box and bring it up.
#
# Hosts and roles come from cluster.env (see cluster.env.example).
#
# Usage:
#   ./deploy.sh <host> <stack>...     # one host, one or more stacks
#   ./deploy.sh all                   # vllm on every replica, haproxy on LB_HOST
#
# Examples:
#   ./deploy.sh starsky vllm haproxy
#   ./deploy.sh hutch   vllm
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

  # If a stack has a .env.example, require the real .env to exist before deploy.
  if [[ -f "$COMPOSE_DIR/$stack/.env.example" && ! -f "$COMPOSE_DIR/$stack/.env" ]]; then
    echo "missing $COMPOSE_DIR/$stack/.env — cp .env.example .env and fill in" >&2
    return 1
  fi

  if [[ "$stack" == "haproxy" ]]; then
    render_haproxy_cfg
  fi

  echo ">> [$host] sync $stack -> $REMOTE_BASE/$stack"
  ssh "$REMOTE_USER@$host" "mkdir -p '$REMOTE_BASE/$stack'"
  # tar streaming: no rsync dependency, preserves perms (.env stays 0600),
  # includes dotfiles, excludes .env.example and the template (only the
  # generated cfg ships). No --delete: remove stale files by hand if you
  # ever rename or drop one.
  tar -C "$COMPOSE_DIR/$stack" \
      --exclude='.env.example' \
      --exclude='haproxy.cfg.template' \
      -cf - . | \
    ssh "$REMOTE_USER@$host" "tar -C '$REMOTE_BASE/$stack' -xpf -"

  echo ">> [$host] docker compose up -d --force-recreate ($stack)"
  # --force-recreate so changes to bind-mounted config files (haproxy.cfg,
  # compose env values from .env, etc.) are picked up. For vLLM this means
  # the container restarts and re-loads the model from disk cache (~5 min);
  # for HAProxy it's instant. Acceptable cost for a deploy that always
  # converges to "what's in the repo right now."
  ssh "$REMOTE_USER@$host" "cd '$REMOTE_BASE/$stack' && docker compose up -d --force-recreate --remove-orphans"
}

if [[ "${1:-}" == "all" ]]; then
  for h in $REPLICAS; do
    deploy_stack "$h" vllm
  done
  deploy_stack "$LB_HOST" haproxy
elif [[ $# -ge 2 ]]; then
  host="$1"; shift
  for stack in "$@"; do
    deploy_stack "$host" "$stack"
  done
else
  echo "Usage: $0 <host> <stack>... | all" >&2
  exit 2
fi
