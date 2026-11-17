#!/usr/bin/env bash
# build-push.sh — build primates natively for THIS host's arch and push arch-tagged images to the fleet registry.
#
# The CPU primates FROM local tags (codemonkey → miniforge3 → …), so a clean multi-arch build means
# building the chain natively on an x86_64 host AND an aarch64 host, pushing per-arch tags, then
# assembling the multi-arch manifest with ./manifest-push.sh. Run this on one host of each arch.
#
# Usage:  ./build-push.sh [primate ...]      # default: the full CPU chain, in dependency order
# Pushes: <registry>/codemonkeys/<name>:latest-<amd64|arm64>   (arch derived from uname -m)
#         The registry: registry-lib.sh (CODEMONKEYS_REGISTRY / registry.conf; ECR refused). Nothing is built
#         without one.
# Creds:  the build-push robot for this run only, logged in into a THROWAWAY DOCKER_CONFIG used for the pushes
#         alone (the builds keep yours): GD_REGISTRY_PASSWORD_FILE (g.deceiver's harbor-cred.sh build-push --), or
#         CM_PASSWORD_STDIN=1 with the secret on stdin (a remote build host:  ... ssh <host> 'CM_PASSWORD_STDIN=1
#         ./build-push.sh cuda-vllm' < "$GD_REGISTRY_PASSWORD_FILE"). No credential = exit 8, nothing built.
set -uo pipefail

NS=codemonkeys
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=registry-lib.sh
. "$HERE/registry-lib.sh"
REG="$(cm_registry build-push)" || exit 2
case "${ECR_REGISTRY:-}" in *.dkr.ecr.*) echo "build-push: REFUSED: ECR_REGISTRY names ECR -- retired" >&2; exit 2 ;; esac
PUSHCFG="$(cm_push_login build-push "$REG")" || exit 8
trap 'cm_shred_dir "$PUSHCFG"' EXIT
trap 'exit 130' INT TERM HUP        # -> the EXIT trap: the login is shredded on every path

case "$(uname -m)" in
  x86_64)        ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "unsupported arch $(uname -m)" >&2; exit 1 ;;
esac

# Dependency-ordered CPU chain (base first). GPU primates (cuda-*) build on a GPU host — pass explicitly.
DEFAULT=(codemonkey minion embedded rust miniforge3 lamp huggingface claude opencode aichat kiro spark-bench)
if [ "$#" -gt 0 ]; then PRIMATES=("$@"); else PRIMATES=("${DEFAULT[@]}"); fi

cd "$HERE"
fail=0
for p in "${PRIMATES[@]}"; do
  echo ">>> [$ARCH] build $p @ $(date +%H:%M:%S)"
  if ! make "${p}.build" FRESH=false; then echo "!!! [$ARCH] build FAILED: $p"; fail=1; break; fi
  docker tag "${p}:latest" "$REG/$NS/${p}:latest-$ARCH" || { fail=1; break; }
  echo ">>> [$ARCH] push $REG/$NS/${p}:latest-$ARCH"
  if ! DOCKER_CONFIG="$PUSHCFG" docker push "$REG/$NS/${p}:latest-$ARCH"; then echo "!!! [$ARCH] push FAILED: $p"; fail=1; break; fi
  echo ">>> [$ARCH] ok $p"
done
echo ">>> [$ARCH] FINISHED (fail=$fail): ${PRIMATES[*]} @ $(date +%H:%M:%S)"
exit $fail
