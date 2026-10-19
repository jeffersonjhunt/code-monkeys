#!/usr/bin/env bash
# manifest-push.sh — assemble multi-arch :latest manifests from the per-arch tags build-push.sh pushed.
#
# Run once, on any host with ECR creds, AFTER build-push.sh has run on both an x86_64 and an aarch64
# host. Combines <name>:latest-amd64 + <name>:latest-arm64 into a multi-arch <name>:latest manifest.
# Pass names to limit the set (e.g. single-arch or GPU primates handled separately).
#
# Usage:  ./manifest-push.sh [primate ...]
set -uo pipefail

ECR="${ECR_REGISTRY:-521147433280.dkr.ecr.us-east-1.amazonaws.com}"
NS=codemonkeys

# The default sweep. Deliberately excluded, publish these by name instead:
#   nyckel, samba  — standalone primates, published explicitly (see primates/CLAUDE.md)
#   cuda-base      — ships :runtime + :devel, has no :latest to assemble
#   cuda-vllm      — reaches ECR through the spark-cluster's own deploy pipeline, not this sweep
#                    (see spark/cluster/README.md); run `./manifest-push.sh cuda-vllm` to do it here
ALL=(codemonkey minion embedded rust miniforge3 lamp huggingface claude opencode aichat kiro spark-bench cuda-comfy cuda-llama-cpp)
if [ "$#" -gt 0 ]; then ALL=("$@"); fi

# ECR auth is docker-credential-ecr-login (installed by ../setup; a credHelpers entry for $ECR in
# ~/.docker/config.json): the buildx imagetools calls below authenticate straight from ~/.aws, no
# `docker login`. If ~/.aws holds only a named profile (no [default]), export AWS_PROFILE first.
fail=0
for p in "${ALL[@]}"; do
  repo="$ECR/$NS/$p"
  # `docker push` wraps each arch build in a single-entry manifest LIST, which `docker manifest create`
  # refuses to nest. `buildx imagetools create` dereferences the source lists and assembles + pushes a
  # real multi-arch manifest in one step. Only include arches that exist (e.g. spark-bench is amd64-only).
  members=()
  docker buildx imagetools inspect "$repo:latest-amd64" >/dev/null 2>&1 && members+=("$repo:latest-amd64")
  docker buildx imagetools inspect "$repo:latest-arm64" >/dev/null 2>&1 && members+=("$repo:latest-arm64")
  if [ "${#members[@]}" -eq 0 ]; then echo "  skip $p — no arch tags in ECR"; continue; fi
  if docker buildx imagetools create -t "$repo:latest" "${members[@]}"; then
    echo "  manifest $p:latest -> ${members[*]##*:}"
  else
    echo "  !!! manifest FAILED: $p"; fail=1
  fi
done
exit $fail
