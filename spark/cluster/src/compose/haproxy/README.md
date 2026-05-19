# HAProxy stack

Round-robin LB across the two vLLM replicas, deployed only on starsky. Listens on `0.0.0.0:80`; HAProxy's own stats/healthcheck on `127.0.0.1:8404`.

## Files

- `compose.yml` — the stack (host networking, mounts `haproxy.cfg`)
- `haproxy.cfg` — static config; edit backend IPs here if they change

## Deploy

Use `src/scripts/deploy.sh` from the repo root.

## Reload after editing `haproxy.cfg`

The config is bind-mounted, so `docker compose restart haproxy` is enough; no rebuild.

## Smoke test

```bash
# From any LAN host
curl -s http://starsky/v1/models | jq .

# HAProxy stats (only reachable from starsky itself)
ssh jhunt@starsky 'curl -s http://127.0.0.1:8404/stats | head'
```
