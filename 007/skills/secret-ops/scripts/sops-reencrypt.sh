#!/usr/bin/env bash
#
# sops-reencrypt.sh — re-encrypt a decrypted file into the hemlighet clone ON THE SECRET HOST, safely.
#
# Encodes the ritual that is easy to get wrong: BINARY-mode sops; the encrypt input must sit at the
# decrypted path that .sops.yaml's path_regex matches (so recipients resolve); verify the ciphertext
# decrypts back byte-identical BEFORE replacing the known-good file; atomic replace; never leave
# plaintext behind; then git add/commit/push. Aborts with the original untouched on any mismatch.
#
# Config (env, then ${SECRET_OPS_CONF:-~/.config/secret-ops.conf}): SECRET_HOST, SECRET_USER,
# HEMLIGHET_DIR (optional). See secret-ops.conf.example.
#
# Usage:
#   sops-reencrypt.sh [--no-push] <plaintext-path-on-host> <hemlighet-rel.sops> ["commit message"]
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: sops-reencrypt.sh [--no-push] <plaintext-path-on-host> <hemlighet-rel.sops> ["commit message"]
  Re-encrypts <plaintext-path> (a path ON THE SECRET HOST) into <hemlighet-rel.sops> (relative to the
  hemlighet clone), binary mode, verifying a byte-identical round-trip before replacing the existing
  file, then git add/commit/push (--no-push to skip the push). Aborts leaving the original intact on
  mismatch; never leaves plaintext behind.
  Config: env, then ${SECRET_OPS_CONF:-~/.config/secret-ops.conf}. See secret-ops.conf.example.
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then usage; exit 0; fi

PUSH=1
if [ "${1:-}" = "--no-push" ]; then PUSH=0; shift; fi

PLAIN="${1:-}"; SOPS_REL="${2:-}"; MSG="${3:-update ${SOPS_REL:-secret}}"
if [ -z "$PLAIN" ] || [ -z "$SOPS_REL" ]; then
  echo "Error: need <plaintext-path-on-host> and <hemlighet-rel.sops>" >&2; usage; exit 1
fi
case "$SOPS_REL" in
  *.sops) : ;;
  *) echo "Error: target must end in .sops (got: $SOPS_REL)" >&2; exit 1 ;;
esac

CONF="${SECRET_OPS_CONF:-$HOME/.config/secret-ops.conf}"
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"
: "${SECRET_HOST:?Error: SECRET_HOST unset — set it in env or $CONF (see secret-ops.conf.example)}"
: "${SECRET_USER:?Error: SECRET_USER unset — set it in env or $CONF (see secret-ops.conf.example)}"
HEMLIGHET_DIR="${HEMLIGHET_DIR:-\$HOME/.local/share/hemlighet}"

ssh -o BatchMode=yes -o ConnectTimeout=60 "${SECRET_USER}@${SECRET_HOST}" \
  bash -s -- "$PLAIN" "$SOPS_REL" "$MSG" "$PUSH" "$HEMLIGHET_DIR" <<'REMOTE'
set -euo pipefail
export PATH=/usr/local/bin:$HOME/.local/bin:$PATH
PLAIN="$1"; SOPS_REL="$2"; MSG="$3"; PUSH="$4"; HL="$5"
# HL may contain a literal $HOME from the config default; expand it.
HL="$(eval echo "$HL")"
command -v sops >/dev/null 2>&1 || { echo "Error: sops shim not on PATH on $(hostname)" >&2; exit 1; }
cd "$HL" || { echo "Error: hemlighet clone $HL not found on $(hostname)" >&2; exit 1; }
[ -f "$PLAIN" ] || { echo "Error: plaintext $PLAIN not found on $(hostname)" >&2; exit 1; }
[ -f "$SOPS_REL" ] || { echo "Error: target $SOPS_REL not found under $HL" >&2; exit 1; }

DEC="${SOPS_REL%.sops}"          # the decrypted name .sops.yaml's path_regex matches
TMP="$(mktemp)"; CHK="$(mktemp)"
cleanup() { rm -f "$TMP" "$CHK" "$DEC"; }
trap cleanup EXIT

cp "$PLAIN" "$DEC"
sops -e --input-type binary --output-type binary "$DEC" > "$TMP"
[ "$(wc -c < "$TMP")" -gt 200 ] || { echo "Error: encrypt produced too little output; aborting" >&2; exit 1; }
sops -d --input-type binary --output-type binary "$TMP" > "$CHK"
cmp -s "$PLAIN" "$CHK" || { echo "Error: round-trip mismatch; $SOPS_REL left unchanged" >&2; exit 1; }

cp "$TMP" "$SOPS_REL"            # replace only after verify
rm -f "$DEC"
git add "$SOPS_REL"
git commit -m "$MSG" >/dev/null
echo "committed: $(git log --oneline -1)"
if [ "$PUSH" = "1" ]; then git push 2>&1 | tail -2; else echo "(--no-push: not pushed)"; fi
REMOTE
