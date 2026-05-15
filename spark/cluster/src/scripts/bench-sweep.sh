#!/usr/bin/env bash
# bench-sweep.sh — run bench.py at increasing concurrency.
#
# Usage:
#   ./bench-sweep.sh [target]
#   ./bench-sweep.sh starsky:8080            # default — through HAProxy
#   ./bench-sweep.sh starsky                 # → starsky:8000 (one replica direct)
#
# Sweeps c in {1, 2, 4, 8, 16, 32}. Each level runs 4×c requests with 256 max tokens.
# c=32 is included to find cluster peak — at lower concurrency the LB is far from saturated.

set -euo pipefail
target="${1:-starsky:8080}"
script_dir="$(cd "$(dirname "$0")" && pwd)"

echo "==== bench sweep: $target ===="
for c in 1 2 4 8 16 32; do
  python3 "$script_dir/bench.py" --target "$target" --concurrency "$c" --requests $((c * 4)) --warmup 1 --quiet
done
echo "==== done ===="
