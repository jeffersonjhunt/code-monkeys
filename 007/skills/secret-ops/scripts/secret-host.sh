#!/usr/bin/env bash
#
# secret-host.sh — run a command on the configured secret host over ssh with a login-grade PATH.
#
# A non-login ssh (`ssh host 'cmd'`) gets PATH=/usr/bin:/bin:/usr/sbin:/sbin only, so docker, sops,
# age and vault (in /usr/local/bin and ~/.local/bin) come back "command not found". This wrapper
# prepends those dirs and runs in the hemlighet clone by default. Every secret-ops host step uses it.
#
# Config (env wins, then ${SECRET_OPS_CONF:-~/.config/secret-ops.conf}):
#   SECRET_HOST   host where sops/age + the hemlighet clone + push creds live   (required)
#   SECRET_USER   ssh user on that host                                         (required)
#   HEMLIGHET_DIR hemlighet clone path (default: $HOME/.local/share/hemlighet)  (optional)
#
# Usage:
#   secret-host.sh [--cwd DIR] <command...>
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: secret-host.sh [--cwd DIR] <command...>
  Run <command> on $SECRET_USER@$SECRET_HOST with PATH=/usr/local/bin:~/.local/bin:$PATH.
  Default working dir: the hemlighet clone ($HEMLIGHET_DIR, default ~/.local/share/hemlighet).
  Config: env vars, then ${SECRET_OPS_CONF:-~/.config/secret-ops.conf}. See secret-ops.conf.example.
EOF
}

# --help must work without any config (so it is testable offline).
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then usage; exit 0; fi

CWD=""
if [ "${1:-}" = "--cwd" ]; then
  shift
  [ $# -ge 1 ] || { echo "Error: --cwd needs a directory" >&2; usage; exit 1; }
  CWD="$1"; shift
fi
if [ $# -eq 0 ]; then echo "Error: no command given" >&2; usage; exit 1; fi

CONF="${SECRET_OPS_CONF:-$HOME/.config/secret-ops.conf}"
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"
: "${SECRET_HOST:?Error: SECRET_HOST unset — set it in env or $CONF (see secret-ops.conf.example)}"
: "${SECRET_USER:?Error: SECRET_USER unset — set it in env or $CONF (see secret-ops.conf.example)}"
: "${HEMLIGHET_DIR:=\$HOME/.local/share/hemlighet}"
[ -n "$CWD" ] || CWD="$HEMLIGHET_DIR"

exec ssh -o BatchMode=yes -o ConnectTimeout=15 "${SECRET_USER}@${SECRET_HOST}" \
  "export PATH=/usr/local/bin:\$HOME/.local/bin:\$PATH; cd ${CWD} && $*"
