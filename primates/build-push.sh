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

# Dependency-ordered CPU chain (base first), derived from primates/fleet.conf: push_default=yes
# rows whose `arches` column includes this host's arch. Row order in fleet.conf IS the build order,
# so miniforge3 stays ahead of everything that FROMs it. GPU primates (cuda-*) are push_default=no —
# build them on a GPU host by passing their names explicitly.
FLEET="$HERE/fleet.conf"
if [ "$#" -gt 0 ]; then
  # Explicit names (the documented way to push the GPU images) read nothing from the inventory,
  # so do not couple them to it.
  PRIMATES=("$@")
else
  [ -r "$FLEET" ] || { echo "ERROR: $FLEET missing or unreadable — refusing to guess the fleet" >&2; exit 9; }
  # while-read, not mapfile: mapfile is bash 4+, and #!/usr/bin/env bash on a stock macOS host
  # resolves to 3.2, where `set -u` would then abort on DEFAULT with a message pointing nowhere.
  PRIMATES=()
  while IFS= read -r p; do PRIMATES+=("$p"); done < <(
    awk -F: -v arch="$ARCH" '/^#/{next} {gsub(/[ \t\r]+/,"")} NF==7 && $5=="yes" && index($4,arch) {print $1}' < "$FLEET")
  [ "${#PRIMATES[@]}" -gt 0 ] || { echo "ERROR: zero primates selected (fleet.conf parsed empty for push_default=yes, arch=$ARCH) — aborting rather than silently doing nothing" >&2; exit 9; }
fi

# ECR login (containerized aws-cli — no host aws install; fail closed on an empty token).
docker image inspect amazon/aws-cli >/dev/null 2>&1 || docker pull -q amazon/aws-cli >/dev/null
TOKEN="$(docker run --rm -v "$HOME/.aws:/root/.aws:ro" \
  -e AWS_PROFILE -e AWS_REGION -e AWS_DEFAULT_REGION \
  amazon/aws-cli ecr get-login-password --region "$REGION")"
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
