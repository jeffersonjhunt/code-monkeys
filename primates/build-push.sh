#!/usr/bin/env bash
# build-push.sh — build primates natively for THIS host's arch and push arch-tagged images to ECR.
#
# The CPU primates FROM local tags (codemonkey → miniforge3 → …), so a clean multi-arch build means
# building the chain natively on an x86_64 host AND an aarch64 host, pushing per-arch tags, then
# assembling the multi-arch manifest with ./manifest-push.sh. Run this on one host of each arch.
#
# Usage:  ./build-push.sh [primate ...]      # default: the full CPU chain, in dependency order
# Pushes: <ECR>/codemonkeys/<name>:latest-<amd64|arm64>   (arch derived from uname -m)
# Creds:  host ~/.aws  (default profile = the scoped fleet-ecr-push identity covers codemonkeys/*)
set -uo pipefail

ECR="${ECR_REGISTRY:-521147433280.dkr.ecr.us-east-1.amazonaws.com}"
NS=codemonkeys
REGION="${AWS_REGION:-us-east-1}"
HERE="$(cd "$(dirname "$0")" && pwd)"

case "$(uname -m)" in
  x86_64)        ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "unsupported arch $(uname -m)" >&2; exit 1 ;;
esac

# Dependency-ordered CPU chain (base first). GPU primates (cuda-*) build on a GPU host — pass explicitly.
DEFAULT=(codemonkey minion embedded miniforge3 lamp huggingface claude opencode kiro spark-bench)
if [ "$#" -gt 0 ]; then PRIMATES=("$@"); else PRIMATES=("${DEFAULT[@]}"); fi

# ECR login (containerized aws-cli — no host aws install; fail closed on an empty token).
docker image inspect amazon/aws-cli >/dev/null 2>&1 || docker pull -q amazon/aws-cli >/dev/null
TOKEN="$(docker run --rm -v "$HOME/.aws:/root/.aws:ro" amazon/aws-cli ecr get-login-password --region "$REGION")"
[ -n "$TOKEN" ] || { echo "ERROR: empty ECR token" >&2; exit 8; }
echo "$TOKEN" | docker login --username AWS --password-stdin "$ECR" >/dev/null || exit 8

cd "$HERE"
fail=0
for p in "${PRIMATES[@]}"; do
  echo ">>> [$ARCH] build $p @ $(date +%H:%M:%S)"
  if ! make "${p}.build" FRESH=false; then echo "!!! [$ARCH] build FAILED: $p"; fail=1; break; fi
  docker tag "${p}:latest" "$ECR/$NS/${p}:latest-$ARCH" || { fail=1; break; }
  echo ">>> [$ARCH] push $ECR/$NS/${p}:latest-$ARCH"
  if ! docker push "$ECR/$NS/${p}:latest-$ARCH"; then echo "!!! [$ARCH] push FAILED: $p"; fail=1; break; fi
  echo ">>> [$ARCH] ok $p"
done
echo ">>> [$ARCH] FINISHED (fail=$fail): ${PRIMATES[*]} @ $(date +%H:%M:%S)"
exit $fail
