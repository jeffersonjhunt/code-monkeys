#!/usr/bin/env bash
# manifest-push.sh — assemble multi-arch :latest manifests from the per-arch tags build-push.sh pushed.
#
# Run once, with the build-push robot (as build-push.sh), AFTER build-push.sh has run on both an x86_64 and an aarch64
# host. Combines <name>:latest-amd64 + <name>:latest-arm64 into a multi-arch <name>:latest manifest.
# Pass names to limit the set (e.g. single-arch or GPU primates handled separately).
#
# Usage:  ./manifest-push.sh [primate ...]
set -uo pipefail

NS=codemonkeys
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=registry-lib.sh
. "$HERE/registry-lib.sh"
REG="$(cm_registry manifest-push)" || exit 2
case "${ECR_REGISTRY:-}" in *.dkr.ecr.*) echo "manifest-push: REFUSED: ECR_REGISTRY names ECR -- retired" >&2; exit 2 ;; esac
PUSHCFG="$(cm_push_login manifest-push "$REG")" || exit 8
trap 'rm -rf "$PUSHCFG"' EXIT
export DOCKER_CONFIG="$PUSHCFG"      # imagetools inspect + create both talk to the registry, nothing else here

# The default sweep. Deliberately excluded, publish these by name instead:
#   nyckel, samba  — standalone primates, published explicitly (see primates/CLAUDE.md)
#   cuda-base      — ships :runtime + :devel, has no :latest to assemble
#   cuda-vllm      — published through the spark-cluster's own deploy pipeline, not this sweep
#                    (see spark/cluster/README.md); run `./manifest-push.sh cuda-vllm` to do it here
ALL=(codemonkey minion embedded rust miniforge3 lamp huggingface claude opencode aichat kiro spark-bench cuda-comfy cuda-llama-cpp)
if [ "$#" -gt 0 ]; then ALL=("$@"); fi

fail=0
for p in "${ALL[@]}"; do
  repo="$REG/$NS/$p"
  # `docker push` wraps each arch build in a single-entry manifest LIST, which `docker manifest create`
  # refuses to nest. `buildx imagetools create` dereferences the source lists and assembles + pushes a
  # real multi-arch manifest in one step. Only include arches that exist (e.g. spark-bench is amd64-only).
  members=()
  docker buildx imagetools inspect "$repo:latest-amd64" >/dev/null 2>&1 && members+=("$repo:latest-amd64")
  docker buildx imagetools inspect "$repo:latest-arm64" >/dev/null 2>&1 && members+=("$repo:latest-arm64")
  if [ "${#members[@]}" -eq 0 ]; then echo "  skip $p — no arch tags in $REG"; continue; fi
  if docker buildx imagetools create -t "$repo:latest" "${members[@]}"; then
    echo "  manifest $p:latest -> ${members[*]##*:}"
  else
    echo "  !!! manifest FAILED: $p"; fail=1
  fi
done
exit $fail
