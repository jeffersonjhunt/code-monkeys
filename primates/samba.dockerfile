# docker buildx build -t samba:latest -f ./samba.dockerfile .
#
# samba — the fleet's file-server primate: a maintained Samba (Debian trixie, Samba 4.22.x) that
# replaces the abandoned `dperson/samba` image (Samba 4.12.2 on Alpine 3.12 — both EOL since 2022),
# whose smbd SEGFAULTED on modern macOS Finder copies, tearing down the connection and surfacing on
# the Mac as the generic error -8062. Like `nyckel`, this is a standalone single-purpose primate
# (deliberately NOT FROM codemonkey): it carries only smbd + the VFS modules, so it stays small,
# builds on any host and both arches (Debian ships `samba` for amd64 + arm64), and has a minimal
# attack surface. Always run as a container (see the g.deceiver control-plane compose).
#
# The entrypoint reimplements the small subset of the dperson/samba flag interface g.deceiver used
# (-u user, -g global, -s share) on top of the SAME macOS/Time-Machine-friendly [global] defaults the
# fleet already ran on, so the control-plane compose swaps the image with no command changes — the
# only thing that actually changes is the Samba version.
FROM debian:trixie-slim
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# samba            — smbd/nmbd
# samba-common-bin — testparm, smbpasswd, pdbedit (config validation + user setup)
# samba-vfs-modules— vfs_fruit / vfs_catia / vfs_recycle / vfs_streams_xattr (macOS + recycle)
# acl              — get/setfacl (POSIX ACL support + on-box debugging)
# procps           — pidof, for the compose healthcheck (`pidof smbd`)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        samba samba-common-bin samba-vfs-modules acl procps; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/*

COPY samba-entrypoint.sh /usr/local/bin/samba-entrypoint
RUN chmod 0755 /usr/local/bin/samba-entrypoint

# 445 = SMB over TCP (primary); 139 = NetBIOS session service (legacy, still mapped by the fleet).
EXPOSE 139 445

ENTRYPOINT ["/usr/local/bin/samba-entrypoint"]

# Fin
