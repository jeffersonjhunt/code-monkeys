#!/usr/bin/env bash
# ship-image.sh — stream a docker image from one host to one or more others.
#
# Hosts come from cluster.env ($REPLICAS, $SSH_USER).
#
# Usage:
#   ./ship-image.sh <src-host> <dst-host>|all <image:tag>
#
# Examples:
#   ./ship-image.sh starsky hutch cuda-vllm:latest
#   ./ship-image.sh starsky all   cuda-vllm:latest    # every replica except src
#
# Streams `docker save | zstd` through ssh to `zstd -d | docker load` on the
# destination — no intermediate disk file on either side. zstd -3 is a sweet
# spot for ~10G LANs (compression keeps up with the wire, decompression is
# free on the receiving CPU).
#
# Requires: ssh keys to $SSH_USER@<host> on both sides; docker on both;
# zstd on both (apt install zstd).

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/load-config.sh
. "$script_dir/lib/load-config.sh"

REMOTE_USER="$SSH_USER"

usage() {
  cat >&2 <<EOF
Usage: $0 <src-host> <dst-host>|all <image:tag>

Examples:
  $0 starsky hutch cuda-vllm:latest
  $0 starsky all   cuda-vllm:latest
EOF
  exit 2
}

[[ $# -eq 3 ]] || usage
SRC="$1"; DST="$2"; IMAGE="$3"

ship_one() {
  local dst="$1"
  if [[ "$dst" == "$SRC" ]]; then
    echo ">> skip $dst (same as src)"
    return 0
  fi
  echo ">> [$SRC -> $dst] ship $IMAGE"
  local started
  started=$(date -u +%FT%TZ)
  ssh "$REMOTE_USER@$SRC" "docker save '$IMAGE' | zstd -T0 -3" \
    | ssh "$REMOTE_USER@$dst" "zstd -d | docker load"
  echo ">> [$dst] verify"
  ssh "$REMOTE_USER@$dst" "docker images '$IMAGE' --format '   {{.Repository}}:{{.Tag}}  {{.ID}}  {{.Size}}'"
  echo ">> [$SRC -> $dst] done (started $started)"
}

if [[ "$DST" == "all" ]]; then
  for host in $REPLICAS; do
    ship_one "$host"
  done
else
  ship_one "$DST"
fi
