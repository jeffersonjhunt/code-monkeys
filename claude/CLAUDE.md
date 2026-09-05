# Global notes for Claude Code inside a primate

## Docker-out-of-Docker

Docker IS available in this container: the host daemon's `/var/run/docker.sock` is bind-mounted
and `docker`, `docker buildx`, and `docker compose` are installed. **Never mark Docker
"unavailable" without running `docker version` first.**

- Plain `docker …` works as the unprivileged `codemonkey` user: `primate()` starts the container
  with `--group-add <socket gid>`, and `/usr/local/bin/docker` is a shim that falls back to
  `sudo -n` quietly if the socket is still denied. If you ever see `permission denied while
  trying to connect to the docker API`, run `sudo docker …` — sudo is passwordless. Never
  `chmod`/`chgrp` the socket; it is the host's inode.
- **Bind mounts resolve on the DAEMON HOST, not in this container.** `-v /tmp/x:/x` or a compose
  `./data` volume gives an EMPTY directory (or Docker Desktop's file-sharing error), because the
  host has no such path. Only host-shared dirs can be mounted, under their HOST path — translate
  `/home/codemonkey/workspace/<x>` to `$HOST_WORKSPACE/<x>` (also `HOST_SSH_DIR`, `HOST_AWS_DIR`),
  or let `hostpath` do it: `docker run -v "$(hostpath ~/workspace/proj/data):/data" …`,
  `docker compose -f ~/workspace/proj/compose.yaml --project-directory "$(hostpath ~/workspace/proj)" up`.
  `docker build .`, `docker cp` and `COPY` are unaffected — the client streams those from here.
