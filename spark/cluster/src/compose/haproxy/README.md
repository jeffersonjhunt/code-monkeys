# HAProxy stack — RETIRED

**This is no longer the cluster LB.** LiteLLM (`../litellm/`) replaced it on 2026-06-28: HAProxy round-robins across replicas of a *single* model and ignores the request body, so it cannot front boxes serving different models. The stack is kept on disk as a fallback only — `deploy.sh all` deploys `litellm` on `$LB_HOST`, never this one. To bring it up you must ask for it explicitly:

```bash
./src/scripts/deploy.sh <lb-host> haproxy
```

What it does when deployed: round-robin LB across the hosts in `$REPLICAS`, on `$LB_HOST` (currently `minerva`, the standalone control plane — not a GPU replica). It listens on `0.0.0.0:$LB_PORT` (rendered from `cluster.env`; currently **8888**) — *not* `:80`: the `haproxy:alpine` image runs as the unprivileged `haproxy` user under `network_mode: host` and cannot bind a port below 1024 without `cap_add: [NET_BIND_SERVICE]` (see the comment in `haproxy.cfg.template`). Its own stats/healthcheck stay on `127.0.0.1:8404`.

## Files

- `compose.yml` — the stack (host networking, mounts `haproxy.cfg`)
- `haproxy.cfg.template` — **the file you edit.** `deploy.sh` renders it to `haproxy.cfg` at deploy time: the `# __REPLICAS__` marker expands to one `server <host> <host>:$VLLM_PORT check` line per entry in `$REPLICAS`, and `__LB_PORT__` is substituted from `$LB_PORT`
- `haproxy.cfg` — **generated**, overwritten on every deploy. Never edit it

## Deploy

Use `src/scripts/deploy.sh` from the repo root — it renders `haproxy.cfg` first.

## Reload after editing the template

`deploy.sh` uses `--force-recreate`, so re-deploying picks up the new config (~1 s of dropped connections). For a graceful in-place reload of an already-valid config:

```bash
ssh gdeceiver@minerva 'docker kill -s HUP haproxy'
```

## Smoke test

```bash
# From any LAN host
curl -s http://minerva:8888/v1/models | jq .

# HAProxy stats (loopback-only — reachable from the LB host itself)
ssh gdeceiver@minerva 'curl -s http://127.0.0.1:8404/stats | head'
```
