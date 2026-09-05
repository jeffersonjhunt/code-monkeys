# TODO

## Docker-out-of-Docker must just work in every primate (agents keep concluding Docker is unavailable)

**Problem (observed 2026-09-05, claude primate on Docker Desktop / arm64):**

- `/var/run/docker.sock` is mounted (`zfuncs` `primate()` / `primate-session()` do it), but inside
  the container it is `root:root` mode `660` and the `codemonkey` user (uid 1000, groups: only
  `codemonkey`) gets `permission denied while trying to connect to the docker API`.
- The base image installs `docker-ce-cli` + `docker-buildx-plugin` but **not**
  `docker-compose-plugin`, so `docker compose` is "unknown command" even once the socket works.
- Passwordless sudo exists (`/etc/sudoers.d/codemonkey`), so `sudo docker ...` works — but agents
  do not know that, and Claude Code's auto-mode classifier blocks `chmod`/`chgrp` on the socket,
  so they give up and mark Docker-dependent verification "not available". This has now happened
  repeatedly (evoc review loop 2 was the latest).
- `setfacl` is not installed, so the ACL route is not available either.

**Fix (make it work without sudo, and make it discoverable):** — done 2026-09-05 on branch `fix/docker-out-of-docker`

1. `codemonkey.dockerfile`: add `docker-compose-plugin` next to `docker-ce-cli docker-buildx-plugin`
   (and consider `acl` for `setfacl`). — [x] `docker-compose-plugin` + `acl` added; plus a `/usr/local/bin/docker` sudo-fallback shim
2. `zfuncs` `primate()` / `_primate()` / `primate-session()`: when the socket exists, pass
   `--group-add "$(stat -c '%g' /var/run/docker.sock)"` (macOS: `stat -f '%g'`) exactly as
   `bin/spark-bench` already does, so the socket is group-readable for `codemonkey` without
   touching perms. Fall back to a documented `sudo docker` path when the gid is 0 on the host side. — [x] `_primate_docker_gid` (Linux `stat -c %g`, Darwin `0`) in `primate()`/`primate-session()`
3. Entry/`zprofile`: if `docker info` fails with permission denied but sudo is passwordless,
   either fix the socket group at login (`sudo chgrp codemonkey /var/run/docker.sock`) or export a
   shim so `docker` transparently uses sudo. Do not rely on agents figuring this out. — [x] done as the image-baked shim (works in non-interactive shells/agents; no chgrp of the host inode)
4. `CLAUDE.md` (root) and `primates/CLAUDE.md`: state plainly that Docker-out-of-Docker is
   available in every primate, that `docker compose` is installed, and what to run if the socket
   is denied. Add the same line to the `claude` primate's copied settings/guidance so Claude Code
   instances see it at start. — [x] both CLAUDE.md files, `claude/CLAUDE.md` copied to `~/.claude/CLAUDE.md`, settings allowlist
5. Verification: `make codemonkey.build FRESH=false`, then from inside a fresh `primate claude`:
   `docker version`, `docker compose version`, `docker run --rm hello-world` all succeed as the
   unprivileged user. — [x] `codemonkey:dood-test` built; `docker version`/`docker compose version`/`hello-world`/`docker build` pass as uid 1000 with `--group-add`, denied without it (and sudo disabled)

**Extra (found during the fix):** bind mounts requested from inside a primate resolve on the
DAEMON HOST — `-v /tmp/x:/x` or a compose `./data` volume yields an empty host-created dir.
`primate()` now exports `HOST_WORKSPACE`/`HOST_SSH_DIR`/`HOST_AWS_DIR`, `hostpath` translates, and
both CLAUDE.md files document the rule. — [x]

**Acceptance:** a fresh instance of any primate can run `docker compose config` and
`docker build` as `codemonkey` with no sudo and no manual socket fiddling, and an agent reading
`CLAUDE.md` knows this. — [x] met (see the fix branch verification transcript; only the
`make codemonkey.build` + fresh `primate claude` re-run on the maintainer host remains).
