#!/usr/bin/env bash
# load-config.sh — sourced by cluster scripts to import the inventory.
#
# Locates cluster.env at the repo root (one level above src/), sources it,
# and verifies the required variables. Defaults are filled in where the
# inventory is silent.
#
# Required variables:
#   SSH_USER, REPLICAS, LB_HOST
# Optional with defaults:
#   VLLM_PORT=8000, LB_PORT=8080, LB_STATS_PORT=8404

# This file is sourced, not executed; do not `set -e` here.

_load_config_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_ROOT="$(cd "$_load_config_script_dir/../../.." && pwd)"
CLUSTER_ENV="$CLUSTER_ROOT/cluster.env"

if [[ ! -f "$CLUSTER_ENV" ]]; then
  echo "error: $CLUSTER_ENV not found." >&2
  echo "       cp cluster.env.example cluster.env  and edit for your hosts." >&2
  exit 2
fi

# shellcheck source=/dev/null
set -a; . "$CLUSTER_ENV"; set +a

: "${VLLM_PORT:=8000}"
: "${LB_PORT:=8080}"
: "${LB_STATS_PORT:=8404}"

# Convenience derived value for tools that want the public endpoint without
# re-deriving it (notably bench.py, which reads CLUSTER_TARGET from the env).
export CLUSTER_TARGET="${LB_HOST:-}:${LB_PORT}"

_missing=()
for var in SSH_USER REPLICAS LB_HOST; do
  [[ -z "${!var:-}" ]] && _missing+=("$var")
done
if (( ${#_missing[@]} > 0 )); then
  echo "error: cluster.env is missing required variables: ${_missing[*]}" >&2
  exit 2
fi

# LB_HOST may either be co-located on a replica (the original single-box topology) or a
# dedicated host outside REPLICAS (e.g. the control plane, decoupling the LB from any GPU
# box). Both are valid — deploy.sh already treats the LB host and the backend list
# independently. We only note the standalone case so a typo in LB_HOST doesn't pass silently.
_lb_standalone=1
for h in $REPLICAS; do
  [[ "$h" == "$LB_HOST" ]] && _lb_standalone=0
done
(( _lb_standalone )) && echo "note: LB_HOST='$LB_HOST' is standalone (not in REPLICAS='$REPLICAS')" >&2
unset _lb_standalone _missing _load_config_script_dir
