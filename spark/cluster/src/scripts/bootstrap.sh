#!/usr/bin/env bash
# bootstrap.sh — one-time host prep for the spark-cluster.
#
# Idempotent: safe to re-run. Pipe via SSH or run directly on a box.
#
# Usage (remote, from workstation):
#   ssh jhunt@<host> 'bash -s' < src/scripts/bootstrap.sh

set -euo pipefail

# Where the weights live. This MUST be the directory the vllm stack mounts at /models
# (src/compose/vllm/compose.yml: ${MODEL_DIR:-/srv/models}) — bootstrap used to create
# ~/Models, which nothing mounted, so a freshly bootstrapped host had no weights directory
# at all and vLLM failed to load. Piped in like CLUSTER_PEERS; this script is `bash -s`'d
# onto a bare host, so it cannot source load-config.sh — keep the default in sync with it.
MODEL_DIR="${MODEL_DIR:-/srv/models}"

if [[ ! -d "$MODEL_DIR" ]]; then
  # /srv is root-owned, so creating under it needs sudo. Hand it to the invoking admin user
  # and make it group-writable: model-pull.sh downloads as the directory's owner, and vLLM
  # mounts it read-only.
  echo ">> create $MODEL_DIR (owner $(id -un):$(id -gn), 775)"
  sudo mkdir -p "$MODEL_DIR"
  sudo chown "$(id -u):$(id -g)" "$MODEL_DIR"
  sudo chmod 775 "$MODEL_DIR"
else
  # Never re-chown an existing tree: on a live replica this is tens of GB of weights owned by
  # whoever staged them, and stealing it from under vLLM would be a great way to break serving.
  echo ">> $MODEL_DIR exists (owner $(stat -c '%U:%G' "$MODEL_DIR")) — leaving ownership alone"
fi

# Defensive cleanup: an earlier version of this script wrote a managed block to
# /etc/hosts. DNS handles resolution; we don't shadow it here. Remove the block
# if a previous run left one behind.
if grep -q '^# spark-cluster BEGIN' /etc/hosts 2>/dev/null; then
  echo ">> remove legacy /etc/hosts block (DNS is authoritative)"
  sudo sed -i '/^# spark-cluster BEGIN/,/^# spark-cluster END/d' /etc/hosts
fi

echo ">> verify"
ls -ld "$MODEL_DIR"
# Caller may pipe in CLUSTER_PEERS="hostA hostB" to have the remote box verify
# DNS for each peer. Silent when unset — bootstrap stays usable as a plain
# `bash -s` pipe.
if [[ -n "${CLUSTER_PEERS:-}" ]]; then
  for h in $CLUSTER_PEERS; do
    if host "$h" >/dev/null 2>&1; then
      echo "DNS: $h OK"
    else
      echo "DNS: $h FAIL" >&2
    fi
  done
fi
echo "OK."
