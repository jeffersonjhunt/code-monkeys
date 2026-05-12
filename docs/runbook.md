# Runbook

Operate / teardown procedures for the spark-cluster vLLM deployment.

## Endpoints

| Endpoint                      | Where               | Purpose                                  |
|-------------------------------|---------------------|------------------------------------------|
| `http://starsky:8080`         | LB (HAProxy)        | OpenAI-compatible API; what clients use  |
| `http://starsky:8000`         | direct replica A    | Bypass LB; debugging                     |
| `http://hutch:8000`           | direct replica B    | Bypass LB; debugging                     |
| `http://127.0.0.1:8404/stats` | starsky (loopback)  | HAProxy live stats UI                    |
| `http://127.0.0.1:8404/health`| starsky (loopback)  | HAProxy self-healthcheck (`monitor-uri`) |

## Health check

```bash
./src/scripts/smoke-test.sh starsky:8080      # through LB
./src/scripts/smoke-test.sh starsky           # replica A direct
./src/scripts/smoke-test.sh hutch             # replica B direct
```

The script auto-discovers the served model id from `/v1/models`, so it works against whatever's deployed.

## Tool calling (OpenCode-style agents)

vLLM is configured with `--enable-auto-tool-choice --tool-call-parser ${VLLM_TOOL_PARSER} --reasoning-parser ${VLLM_REASONING_PARSER}`. The parser is selected per-model in `.env`:

| Model family | `VLLM_TOOL_PARSER` | `VLLM_REASONING_PARSER` | Auto mode |
|---|---|---|---|
| Qwen3.6 / Qwen3-Coder (current) | `qwen3_coder` | `qwen3` | **Reliable.** Model emits well-formed `<tool_call>` XML; `tool_calls[]` populated correctly. |
| Qwen2.5-Coder (legacy) | `hermes` | `qwen3` | Unreliable — model sometimes emits `<tools>` (plural) or bare JSON. Use `tool_choice: "required"` or fall back to parsing `content`. |

**OpenCode integration**: with the current Qwen3.6 stack, `tool_choice: "auto"` works as expected — agents can leave routing to the model. `tool_choice: "required"` still works (guided decoding); use it when you've already routed and want to force a structured call.

**If you ever switch models**, update `VLLM_TOOL_PARSER` in `.env` to match. Run `docker run --rm --entrypoint /bin/bash --gpus all <vllm-image> -c 'vllm serve --help=tool-call-parser'` to see the supported list.

## Prefix caching

Enabled via `--enable-prefix-caching` in `compose.yml`. vLLM hashes prompt prefixes and reuses already-computed KV pages across requests.

- **Best speedup at TTFT for long shared prefixes** — measured ~**4× TTFT** on 4K-token system prompts (736 ms cold → 183 ms warm). Decode-dominated workloads (short prompts, long completions) see no measurable change since prefill was already cheap.
- **Hybrid model caveat:** vLLM warns that prefix caching for Mamba/SSM layers is experimental in this engine version (`align` mode). Watch for tail-latency spikes; if anything misbehaves, drop the flag and redeploy.
- **Each replica has its own cache.** HAProxy round-robin sends consecutive requests to different replicas, so a multi-turn conversation re-warms both caches. For agent traffic with heavy long-context per-conversation reuse, consider switching `balance roundrobin` → `balance source` (sticky by client IP) in `haproxy.cfg`.

Live stats from a replica:

```bash
ssh jhunt@starsky 'curl -s http://127.0.0.1:8000/metrics | grep prefix_cache'
# vllm:prefix_cache_queries_total — total tokens looked up
# vllm:prefix_cache_hits_total    — tokens served from cache
```

Hit rate ≈ `hits / queries`. Healthy agent traffic should see ≥ 50 %.

## Backend status

```bash
ssh jhunt@starsky 'curl -sS "http://127.0.0.1:8404/stats;csv" | awk -F, "/vllm_pool/ {print \$1\"/\"\$2\" \"\$18}"'
```

Or in a browser, tunnel: `ssh -L 8404:127.0.0.1:8404 jhunt@starsky` then open `http://127.0.0.1:8404/stats`.

## Start / stop a single replica

```bash
# stop
ssh jhunt@<host> 'cd ~/spark-deploy/vllm && docker compose stop'

# start (does NOT re-pull image or recreate; instant)
ssh jhunt@<host> 'cd ~/spark-deploy/vllm && docker compose start'

# restart (re-reads bind-mounted files only — does NOT pick up compose.yml command changes)
ssh jhunt@<host> 'cd ~/spark-deploy/vllm && docker compose restart'

# pick up compose.yml changes (command flags, env_file, image) — run a full deploy:
./src/scripts/deploy.sh <host> vllm   # uses --force-recreate
```

After stopping a replica, HAProxy will mark it DOWN within 30 s (3 × 10 s health-check interval).

## Swap the served model

1. Edit `src/compose/vllm/.env` — change `HF_MODEL_ID` and `VLLM_SERVED_NAME`.
2. Redeploy on each box: `./src/scripts/deploy.sh starsky vllm` and `./src/scripts/deploy.sh hutch vllm`.
3. Pre-stage weights on both boxes (vLLM no longer auto-downloads):

   ```bash
   ./src/scripts/model-pull.sh all <org>/<repo>
   ```

   First fetch takes ~10–30 min for tens of GB; subsequent vLLM starts mmap-load from `~/Models/<org>/<name>` in ~2 min.
4. **Cross-box transfer** — alternative to pulling on both boxes (saves bandwidth and HF rate-limit headroom):

   ```bash
   ssh jhunt@starsky 'tar -C ~/Models -cf - <org>/<repo>' | \
     ssh jhunt@hutch  'tar -C ~/Models -xpf -'
   ```

5. Smoke test each box, then re-test through `starsky:8080`.

## Re-deploy HAProxy after editing `haproxy.cfg`

`deploy.sh` uses `--force-recreate`, so editing `src/compose/haproxy/haproxy.cfg` and re-running `./src/scripts/deploy.sh starsky haproxy` is enough — the container is recreated and picks up the new config. Drop in connections during the ~1 s recreate.

For zero-disruption reload of HAProxy specifically, use the in-place reload (config must already be valid):

```bash
ssh jhunt@starsky 'docker kill -s HUP haproxy'
```

This is HAProxy's native graceful reload.

## Failover drill

```bash
# stop one replica
ssh jhunt@hutch 'docker stop vllm'

# wait ~30s; check stats
ssh jhunt@starsky 'curl -sS "http://127.0.0.1:8404/stats;csv" | awk -F, "/vllm_pool/ {print \$1\"/\"\$2\" \"\$18}"'
# expect: hutch DOWN, starsky UP, BACKEND UP

# requests still serve via the LB
./src/scripts/smoke-test.sh starsky:8080

# restore
ssh jhunt@hutch 'docker start vllm'
# (hutch needs ~2 min to reload model from cache before HAProxy marks it UP again)
```

## Reboot survival

Both stacks use `restart: unless-stopped`. After a host reboot, Docker auto-starts the containers. vLLM containers reload the model from `~/Models/<org>/<name>` (~2 min); HAProxy comes up immediately and marks backends DOWN until vLLM healthchecks pass.

## Logs

Per-container logs (compose stacks both use json-file driver with rotation):

```bash
ssh jhunt@<host> 'docker logs --tail 200 -f vllm'
ssh jhunt@starsky 'docker logs --tail 200 -f haproxy'
```

Rotation: vLLM keeps 3 × 100 MB; HAProxy keeps 3 × 20 MB. Tune in the respective `compose.yml` if needed.

## Teardown

```bash
# stop and remove containers (keeps images and model weights)
ssh jhunt@hutch  'cd ~/spark-deploy/vllm    && docker compose down'
ssh jhunt@starsky 'cd ~/spark-deploy/vllm    && docker compose down'
ssh jhunt@starsky 'cd ~/spark-deploy/haproxy && docker compose down'

# remove model weights cache (frees disk)
ssh jhunt@<host> 'rm -rf ~/Models/<org>/<name>'

# remove images
ssh jhunt@<host> 'docker image prune -a -f'

# remove deploy dirs entirely
ssh jhunt@<host> 'rm -rf ~/spark-deploy'
```
