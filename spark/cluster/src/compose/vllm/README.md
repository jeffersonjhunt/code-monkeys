# vLLM stack

Single vLLM service serving `RedHatAI/Qwen3-Coder-Next-NVFP4` on port 8000. Deployed with identical config on every host in `$REPLICAS` — currently just `hutch` (starsky was pulled from the pool 2026-06-10).

## Files

- `compose.yml` — the stack
- `.env.example` — template for `.env` (which holds your HF token); `.env` is gitignored

The real `.env` is **not** shipped from your workstation: `deploy.sh` excludes it from the tar and instead SOPS-decrypts it from the `hemlighet` repo on the target host.

## Deploy

Use `src/scripts/deploy.sh` from the repo root — it tar-streams this directory to the remote (no rsync dependency), ECR-logs-in, decrypts `.env`, then `docker compose pull && up -d`. Don't run `docker compose up` here directly.

## Override knobs

All compose variables have sensible defaults; override by uncommenting lines in `.env`. Most likely to tune:

- `VLLM_MAX_MODEL_LEN` — context window. Lower frees memory for KV cache.
- `VLLM_GPU_MEM_UTIL` — fraction of GPU memory vLLM may use. Compose default 0.90 (the maintainer's `.env` sets 0.75).
- `VLLM_IMAGE` — defaults to the private-ECR `cuda-vllm` ref
  (`521147433280.dkr.ecr.us-east-1.amazonaws.com/codemonkeys/cuda-vllm:latest` — native
  sm_89/120/121 cutlass; built from `primates/cuda-vllm.dockerfile` in the repo root and
  **pushed to ECR**, from where `deploy.sh` pulls it. The old host-to-host
  `docker save | zstd | ssh | docker load` path — `ship-image.sh` — was retired 2026-07-04.)
  Override to a local tag, or to upstream `vllm/vllm-openai:vX.Y.Z-cu129-ubuntu2404` if needed.
- `MODEL_DIR` — host path mounted read-only at `/models`. Compose default `/srv/models`.

## Smoke test

Once running on a box (e.g. hutch):

```bash
curl -s http://hutch:8000/v1/models | jq .
curl -s http://hutch:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"qwen3-coder-next","messages":[{"role":"user","content":"hello"}]}' | jq .
```

vLLM does **not** download weights: it is launched with `--model /models/${HF_MODEL_ID}`, so the weights must be pre-staged on the host by `src/scripts/model-pull.sh`. If they are missing, the container fails to start rather than fetching them. With weights present, first start still takes several minutes (model load + JIT); subsequent restarts come up in ~2–5 min from the disk and JIT caches.
