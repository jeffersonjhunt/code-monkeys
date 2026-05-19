#!/usr/bin/env bash
# bench-sweep.sh — run bench.py at increasing concurrency.
#
# Default target comes from cluster.env ($LB_HOST:$LB_PORT).
#
# Usage:
#   ./bench-sweep.sh                       # → $LB_HOST:$LB_PORT (through HAProxy)
#   ./bench-sweep.sh starsky               # → starsky:$VLLM_PORT (one replica direct)
#   ./bench-sweep.sh host:port             # explicit
#
# Sweeps c in {1, 2, 4, 8, 16, 32}. Each level runs 4×c requests with 256 max tokens.
# c=32 is included to find cluster peak — at lower concurrency the LB is far from saturated.

set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/load-config.sh
. "$script_dir/lib/load-config.sh"

target="${1:-${LB_HOST}:${LB_PORT}}"
if [[ "$target" != *:* ]]; then
  target="$target:$VLLM_PORT"
fi

echo "==== bench sweep: $target ===="
for c in 1 2 4 8 16 32; do
  python3 "$script_dir/bench.py" --target "$target" --concurrency "$c" --requests $((c * 4)) --warmup 1 --quiet
done
echo "==== done ===="
