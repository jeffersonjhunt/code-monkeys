# litellm — model-aware router (LB host)

Replaces the round-robin HAProxy on `$LB_HOST` with a [LiteLLM](https://docs.litellm.ai)
proxy that routes by the OpenAI `model` field. One endpoint, multiple backends serving
**different** models:

| `model` in request | Backend | Workload |
|--------------------|---------|----------|
| `qwen3-coder-next` | `hutch.tworivers:8000`   | coding cluster / opencode |
| `reasoning`        | `starsky.tworivers:8000` | g.deceiver reasoning-llm |
| `caption` *(Phase 6)* | `starsky.tworivers:8002` | g.deceiver Sees VLM (commented until deployed) |

An unknown `model` is rejected rather than fanned out to the wrong box.

## Why this replaced HAProxy

HAProxy `balance roundrobin` ignored the request body, so it could only front replicas of
one model. Pulling `starsky` out for g.deceiver reasoning (2026-06-10) left two boxes
serving two different models with no single endpoint over both. LiteLLM reads `model` and
maps it to a backend — adding a third model (the Phase 6 captioner) is one entry in
`config.yaml`, not a new HAProxy body-ACL.

## Files

- `compose.yml` — the proxy service (pinned `ghcr.io/berriai/litellm:v1.90.0`,
  `network_mode: host`, binds `${LITELLM_PORT:-8888}`).
- `config.yaml` — the `model -> backend` map. **This is the file you edit.** Backends are
  FQDNs (DNS is the source of truth, same as the HAProxy backends were).

No `.env` is required — the map lives in `config.yaml` and the only knob is `LITELLM_PORT`
(shell env at `up` time). The endpoint runs open on the trusted LAN, matching the HAProxy
it replaces; to require auth, add `general_settings: { master_key: sk-... }` to
`config.yaml` and have clients send it as a Bearer token.

## Deploy

Zero-downtime cutover from the live HAProxy (stand up on a spare port first, verify, then
take 8888):

```bash
# from spark/cluster, after syncing this stack to the LB host (deploy.sh minerva litellm
# uses LITELLM_PORT's default 8888 — for the staged stand-up, run compose by hand):
ssh jhunt@minerva 'cd ~/spark-deploy/litellm && LITELLM_PORT=8889 docker compose up -d'

# verify both models route + unknown model is rejected:
curl -s http://minerva:8889/v1/models
curl -s http://minerva:8889/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"reasoning","messages":[{"role":"user","content":"ping"}],"max_tokens":8}'
curl -s http://minerva:8889/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"qwen3-coder-next","messages":[{"role":"user","content":"ping"}],"max_tokens":8}'

# cutover: stop HAProxy, bring LiteLLM up on 8888 (clients need no change — same port).
ssh jhunt@minerva 'cd ~/spark-deploy/haproxy && docker compose down'
ssh jhunt@minerva 'cd ~/spark-deploy/litellm && docker compose up -d'   # binds 8888
```

After cutover, point g.deceiver's orchestrator `REASONING_URL` at `http://minerva:8888/v1`
(model `reasoning`); opencode already targets `minerva:8888` and sends `qwen3-coder-next`,
so it needs no change.

## Health

- `GET /health/liveliness` — process up (used by the compose healthcheck).
- `GET /health/readiness` — proxy ready.
- `GET /v1/models` — lists the routable model names (`qwen3-coder-next`, `reasoning`).
