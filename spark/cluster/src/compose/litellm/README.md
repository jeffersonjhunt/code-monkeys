# litellm — model-aware router (LB host)

Replaces the round-robin HAProxy on `$LB_HOST` with a [LiteLLM](https://docs.litellm.ai)
proxy that routes by the OpenAI `model` field. One endpoint, multiple backends serving
**different** models:

| `model` in request | Backend | Workload |
|--------------------|---------|----------|
| `qwen3-coder-next` | `hutch.tworivers:8000`   | coding cluster / opencode |
| `reasoning`        | `starsky.tworivers:8000` | g.deceiver reasoning-llm |
| `caption` *(Phase 6)* | `starsky.tworivers:8001` | g.deceiver Sees VLM (Qwen2.5-VL, co-resident on starsky's spare UMA) |

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

The cutover from HAProxy happened on 2026-06-28; this stack now binds 8888 on `$LB_HOST` and is
what `deploy.sh all` puts there. Routine deploy / restore (idempotent):

```bash
./src/scripts/deploy.sh minerva.tworivers litellm   # tars this dir to ~/spark-deploy/litellm, up -d

# verify the routes (expect qwen3-coder-next, reasoning, caption):
curl -s http://minerva:8888/v1/models
curl -s http://minerva:8888/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"reasoning","messages":[{"role":"user","content":"ping"}],"max_tokens":8}'
```

To try a config change without touching the live endpoint, stand a second instance up on a spare
port and probe it before re-deploying 8888:

```bash
ssh gdeceiver@minerva 'cd ~/spark-deploy/litellm && LITELLM_PORT=8889 docker compose up -d'
```

Clients: g.deceiver's orchestrator `REASONING_URL` points at `http://minerva:8888/v1` (model
`reasoning`); opencode targets `minerva:8888` and sends `qwen3-coder-next` (`primates/opencode.json`).

## Health

- `GET /health/liveliness` — process up (used by the compose healthcheck).
- `GET /health/readiness` — proxy ready.
- `GET /v1/models` — lists the routable model names. All three entries in `config.yaml` are
  active, so expect `qwen3-coder-next`, `reasoning`, and `caption`.

There is no `:8404`-style stats UI (that was HAProxy's). Per-backend health is the vLLM `/health`
on each box direct; `/v1/models` is how you ask the router what it will route.
