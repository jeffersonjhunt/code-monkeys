#!/usr/bin/env bash
# bootstrap.sh — one-time host prep for the spark-cluster.
#
# Idempotent: safe to re-run. Pipe via SSH or run directly on a box.
#
# Usage (remote, from workstation):
#   ssh jhunt@<host> 'bash -s' < src/scripts/bootstrap.sh

set -euo pipefail

MODEL_DIR="$HOME/Models"

echo ">> create $MODEL_DIR (owned by $USER)"
mkdir -p "$MODEL_DIR"

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
