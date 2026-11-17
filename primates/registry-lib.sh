# shellcheck shell=bash
# registry-lib.sh -- where the primate family is published, for primate-pull, build-push.sh and manifest-push.sh.
#
# This repo is PUBLIC, so it names no registry host (the fleet's is private to it). The registry comes from
#   $CODEMONKEYS_REGISTRY, else the CODEMONKEYS_REGISTRY=<host[:port]> line of
#   ${CODEMONKEYS_CONF:-~/.config/code-monkeys/registry.conf}
# and nothing is pulled or pushed without one (exit 2). An ECR registry is refused (exit 2): the fleet moved its
# images to a self-hosted Harbor and retired ECR (g.deceiver forge F4).
#
# Pull credentials are FILE-based, in a docker config dir of their own -- ${CODEMONKEYS_DOCKER_CONFIG:-
# ~/.config/code-monkeys/docker}/config.json with an `auths` entry and NO credsStore -- so a pull works over ssh and
# from a zoo/tmux window on a Mac, where Docker Desktop's keychain store cannot be reached. `primate-pull --login`
# writes it from a secret on stdin. Pushes log in into a throwaway DOCKER_CONFIG (cm_push_login).

cm_registry() {   # WHAT -> prints the registry, or exits 2 with the reason
  local r=${CODEMONKEYS_REGISTRY:-} conf=${CODEMONKEYS_CONF:-$HOME/.config/code-monkeys/registry.conf}
  if [ -z "$r" ] && [ -r "$conf" ]; then r=$(sed -n 's/^CODEMONKEYS_REGISTRY=//p' "$conf" | tail -1); fi
  if [ -z "$r" ]; then
    echo "$1: no registry configured: set CODEMONKEYS_REGISTRY, or put CODEMONKEYS_REGISTRY=<host:port> in $conf" >&2
    echo "$1:   (this repo is public and names none)" >&2
    exit 2
  fi
  case "$r" in
    *.dkr.ecr.*.amazonaws.com*) echo "$1: REFUSED: $r is ECR -- retired; configure the fleet's Harbor" >&2; exit 2 ;;
  esac
  printf '%s\n' "$r"
}

cm_docker_config() { printf '%s\n' "${CODEMONKEYS_DOCKER_CONFIG:-$HOME/.config/code-monkeys/docker}"; }

# cm_write_auth REG USER: the secret on stdin (one line) -> <docker config>/config.json, 0600 in a 0700 dir, atomically.
# Never printed; no credsStore, so docker reads the file and never a keychain.
cm_write_auth() {
  local reg=$1 user=$2 dir secret tmp
  dir=$(cm_docker_config)
  IFS= read -r secret || true
  [ -n "$secret" ] || { echo "primate-pull --login: no secret on stdin" >&2; return 1; }
  umask 077; mkdir -p "$dir" && chmod 700 "$dir" || return 1
  tmp=$(mktemp "$dir/.config.XXXXXX") || return 1
  printf '{"auths": {"%s": {"auth": "%s"}}}\n' "$reg" "$(printf '%s:%s' "$user" "$secret" | base64 | tr -d '\n')" > "$tmp" \
    && chmod 600 "$tmp" && mv -f "$tmp" "$dir/config.json" || { rm -f "$tmp"; return 1; }
  echo "primate-pull: credentials for $reg ($user) written to $dir/config.json (0600; no keychain)"
}

# cm_push_login WHAT REG -> prints a fresh private DOCKER_CONFIG dir holding a login to REG (the caller removes it).
# The secret: $GD_REGISTRY_PASSWORD_FILE (g.deceiver's harbor-cred.sh) or, with CM_PASSWORD_STDIN=1, stdin. The user:
# $GD_REGISTRY_USER (default robot$build-push). Exit 8 with the reason when there is none or it is refused.
cm_push_login() {
  local what=$1 reg=$2 user=${GD_REGISTRY_USER:-robot\$build-push} d shm=${CM_SHM:-/dev/shm}
  # a 0700 dir under /dev/shm, so the login's base64 credential never touches a disk; only without /dev/shm elsewhere,
  # and it says so. The caller shreds it on every exit path: trap 'cm_shred_dir "$PUSHCFG"' EXIT + INT TERM HUP.
  if [ -d "$shm" ] && [ -w "$shm" ]; then d=$(mktemp -d "$shm/cm-push.XXXXXX") || return 8
  else echo "$what: no writable $shm: the push login goes under ${TMPDIR:-/tmp} (shredded on exit)" >&2; d=$(mktemp -d) || return 8; fi
  chmod 700 "$d"
  if [ -n "${GD_REGISTRY_PASSWORD_FILE:-}" ]; then
    [ -s "$GD_REGISTRY_PASSWORD_FILE" ] || { cm_shred_dir "$d"; echo "$what: $GD_REGISTRY_PASSWORD_FILE is empty or unreadable" >&2; return 8; }
    DOCKER_CONFIG="$d" docker login --username "$user" --password-stdin "$reg" < "$GD_REGISTRY_PASSWORD_FILE" >/dev/null 2>&1 \
      || { cm_shred_dir "$d"; echo "$what: docker login to $reg as $user was refused" >&2; return 8; }
  elif [ "${CM_PASSWORD_STDIN:-0}" = 1 ]; then
    DOCKER_CONFIG="$d" docker login --username "$user" --password-stdin "$reg" >/dev/null 2>&1 \
      || { cm_shred_dir "$d"; echo "$what: docker login to $reg as $user was refused" >&2; return 8; }
  else
    cm_shred_dir "$d"
    echo "$what: no push credential: GD_REGISTRY_PASSWORD_FILE (g.deceiver's harbor-cred.sh build-push --) or CM_PASSWORD_STDIN=1" >&2
    return 8
  fi
  printf '%s\n' "$d"
}

# cm_shred_dir DIR -- shred its files, remove it (idempotent; for traps)
cm_shred_dir() {
  [ -n "${1:-}" ] && [ -d "$1" ] || return 0
  find "$1" -type f -exec shred -u {} + 2>/dev/null
  rm -rf "$1"
}

# cm_drop_ecr_entries FILE -- remove every credHelpers AND auths entry for an ECR registry (any account, fips too: by
# pattern) from a docker config.json; everything else is kept. The file is rewritten (atomically, same owner/mode) ONLY
# when something was removed. python3, not jq: it is on every host, Mac and primate.
cm_drop_ecr_entries() {
  [ -s "${1:-}" ] || return 0
  python3 - "$1" <<'PY'
import json, os, re, sys
p = sys.argv[1]
ecr = re.compile(r"\.dkr\.ecr(-fips)?\.[a-z0-9-]+\.amazonaws\.com")
try:
    d = json.load(open(p))
except ValueError:
    print(f"  WARNING: {p} is not JSON -- left alone", file=sys.stderr); sys.exit(0)
n = 0
for k in ("credHelpers", "auths"):
    for r in [r for r in (d.get(k) or {}) if ecr.search(r)]:
        del d[k][r]; n += 1
    if k in d and d[k] == {}:
        del d[k]
if not n:
    print(f"  {p}: no retired ECR entry -- nothing to remove"); sys.exit(0)
st = os.stat(p); t = p + ".cm-tmp"
with open(t, "w") as f:
    json.dump(d, f, indent=1); f.write("\n")
os.chmod(t, st.st_mode & 0o7777)
try:
    os.chown(t, st.st_uid, st.st_gid)
except PermissionError:
    pass
os.replace(t, p)
print(f"  {p}: {n} retired ECR entr{'y' if n == 1 else 'ies'} removed")
PY
}
