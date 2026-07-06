#!/usr/bin/env bash
# samba-entrypoint — build /etc/samba/smb.conf from a small, macOS-friendly base plus the subset of
# the dperson/samba flag interface g.deceiver uses, then exec smbd in the foreground.
#
#   -u  <username;password[;uid;group;gid]>   create/enable a Samba user (repeatable)
#   -g  <"key = value">                       append a line to [global]         (repeatable)
#   -s  <name;path[;browsable;readonly;guest;valid-users;admin-users;write-list;comment]>
#                                             define a share                    (repeatable)
#
# The [global] block below reproduces the effective config the fleet ran under dperson/samba (fruit +
# streams_xattr + recycle, Time Machine, SMB2+, 0664/0775 masks) so swapping in this maintained Samba
# changes the binary and nothing else. See primates/samba.dockerfile for the why.
set -euo pipefail

CONF=/etc/samba/smb.conf
GLOBALS=()
SHARES=()
USERS=()

while getopts ":u:g:s:" opt; do
  case "$opt" in
    u) USERS+=("$OPTARG") ;;
    g) GLOBALS+=("$OPTARG") ;;
    s) SHARES+=("$OPTARG") ;;
    :) echo "samba-entrypoint: -$OPTARG needs an argument" >&2; exit 2 ;;
    \?) echo "samba-entrypoint: unknown flag -$OPTARG" >&2; exit 2 ;;
  esac
done

mkdir -p /var/lib/samba/private /var/log/samba /run/samba

# --- base [global]: the macOS/Time-Machine defaults dperson/samba baked in, pinned explicitly so the
#     behaviour is identical across the Samba version bump (no reliance on version-default drift). ---
cat > "$CONF" <<'EOF'
[global]
   workgroup = MYGROUP
   server string = Samba Server
   server role = standalone server
   map to guest = Bad User
   usershare allow guests = yes
   dns proxy = no
   load printers = no
   printing = bsd
   printcap name = /dev/null
   disable spoolss = yes
   pam password change = yes
   log file = /dev/stdout
   max log size = 50
   server min protocol = SMB2
   client min protocol = SMB2
   client max protocol = SMB3
   client ipc min protocol = SMB2
   client ipc max protocol = SMB3
   strict locking = no
   aio read size = 0
   aio write size = 0
   create mask = 0664
   force create mode = 0664
   directory mask = 0775
   force directory mode = 0775
   # macOS Finder + Time Machine compatibility (identical to the prior dperson/samba defaults).
   vfs objects = catia fruit recycle streams_xattr
   fruit:metadata = netatalk
   fruit:veto_appledouble = no
   fruit:wipe_intentionally_left_blank_rfork = yes
   fruit:delete_empty_adfiles = yes
   fruit:time machine = yes
   recycle:repository = .deleted
   recycle:keeptree = yes
   recycle:versions = yes
   recycle:maxsize = 0
EOF

# --- extra [global] params (-g); appended while we are still inside [global] (before any share) ---
for g in "${GLOBALS[@]}"; do
  [ -n "$g" ] && printf '   %s\n' "$g" >> "$CONF"
done

# --- users (-u): username;password;uid;group;gid ---
for u in "${USERS[@]}"; do
  [ -n "$u" ] || continue
  IFS=';' read -r uname upass uid ugroup ugid <<<"$u"
  if [ -n "${ugroup:-}" ] && ! getent group "$ugroup" >/dev/null 2>&1; then
    groupadd ${ugid:+-g "$ugid"} "$ugroup"
  fi
  if ! getent passwd "$uname" >/dev/null 2>&1; then
    useradd ${uid:+-u "$uid"} ${ugroup:+-g "$ugroup"} -M -s /usr/sbin/nologin "$uname"
  fi
  printf '%s\n%s\n' "$upass" "$upass" | smbpasswd -s -a "$uname" >/dev/null
  smbpasswd -e "$uname" >/dev/null 2>&1 || true
done

# --- shares (-s): name;path;browsable;readonly;guest;valid-users;admin-users;write-list;comment ---
for s in "${SHARES[@]}"; do
  [ -n "$s" ] || continue
  IFS=';' read -r sname spath sbrowse sro sguest susers sadmin swrite scomment <<<"$s"
  {
    printf '\n[%s]\n' "$sname"
    printf '   path = %s\n' "$spath"
    [ -n "${scomment:-}" ] && printf '   comment = %s\n' "$scomment"
    printf '   browseable = %s\n' "${sbrowse:-yes}"
    printf '   read only = %s\n' "${sro:-no}"
    printf '   guest ok = %s\n' "${sguest:-no}"
    [ -n "${susers:-}" ] && printf '   valid users = %s\n' "$susers"
    [ -n "${sadmin:-}" ] && printf '   admin users = %s\n' "$sadmin"
    [ -n "${swrite:-}" ] && printf '   write list = %s\n' "$swrite"
  } >> "$CONF"
done

# Fail closed on a malformed config instead of starting a half-broken server.
if ! testparm -s "$CONF" >/dev/null 2>&1; then
  echo "samba-entrypoint: generated smb.conf is invalid:" >&2
  testparm -s "$CONF" >&2 || true
  exit 1
fi

echo "samba-entrypoint: starting smbd ($(smbd --version))"
exec smbd --foreground --no-process-group
