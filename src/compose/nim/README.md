# NIM for LLMs stack

NVIDIA's generic LLM NIM (`nvcr.io/nim/nvidia/llm-nim`) — vLLM-based runtime with NVIDIA's hardware-specific patches and TRT-LLM acceleration where available.

This stack is the **Track A experiment**: serve `RedHatAI/Qwen3-Coder-Next-NVFP4` (the original target) to see if NVIDIA's patched build dodges the upstream sm_120 NVFP4 MoE / hybrid Mamba bug that blocks plain vLLM on DGX Spark.

## Files

- `compose.yml` — the stack
- `.env.example` — template for `.env` (which holds NGC API key + HF token); `.env` is gitignored

## Deploy

`./src/scripts/deploy.sh starsky nim` from the repo root. The first start does:
1. Image pull (~10 GB, several minutes)
2. Model download from HF or NGC (~40 GB for the NVFP4 model, may reuse HF cache if NIM looks at the right path)
3. Engine build / TRT-LLM compile (variable; can take 10–20 min)
4. Healthcheck `/v1/health/ready` succeeds → ready

Healthcheck `start_period` is 1200 s for that reason.

## Coexistence with vLLM during the experiment

NIM uses host port **8001** (vLLM uses 8000) so they don't collide on the network side, but **both want the GPU**. During the NIM experiment, stop vLLM on the same box first:

```bash
ssh jhunt@starsky 'cd ~/spark-deploy/vllm && docker compose stop'
```

HAProxy drains starsky within 30 s; hutch keeps serving the cluster.

To revert (vLLM only on starsky):

```bash
ssh jhunt@starsky 'cd ~/spark-deploy/nim  && docker compose down'
ssh jhunt@starsky 'cd ~/spark-deploy/vllm && docker compose start'
```

## Smoke test

```bash
./src/scripts/smoke-test.sh starsky:8001
```
