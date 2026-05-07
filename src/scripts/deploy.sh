#!/usr/bin/env bash
# deploy.sh — sync a compose stack to a remote box and bring it up.
#
# Usage:
#   ./deploy.sh starsky vllm haproxy   # both stacks on starsky
#   ./deploy.sh hutch vllm             # just vllm on hutch
#   ./deploy.sh all                    # vllm on both, haproxy on starsky
#
# Requires: tar, ssh keys to jhunt@<host>.

set -euo pipefail

REMOTE_USER=jhunt
REMOTE_BASE="/home/$REMOTE_USER/spark-deploy"
COMPOSE_DIR="$(cd "$(dirname "$0")/../compose" && pwd)"

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

  echo ">> [$host] sync $stack -> $REMOTE_BASE/$stack"
  ssh "$REMOTE_USER@$host" "mkdir -p '$REMOTE_BASE/$stack'"
  # tar streaming: no rsync dependency, preserves perms (.env stays 0600),
  # includes dotfiles, excludes .env.example. No --delete: remove stale files
  # by hand if you ever rename or drop one.
  tar -C "$COMPOSE_DIR/$stack" --exclude='.env.example' -cf - . | \
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
  deploy_stack starsky vllm
  deploy_stack hutch   vllm
  deploy_stack starsky haproxy
elif [[ $# -ge 2 ]]; then
  host="$1"; shift
  for stack in "$@"; do
    deploy_stack "$host" "$stack"
  done
else
  echo "Usage: $0 <host> <stack>... | all" >&2
  exit 2
fi
