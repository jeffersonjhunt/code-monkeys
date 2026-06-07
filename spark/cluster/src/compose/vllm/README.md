# vLLM stack

Single vLLM service serving `RedHatAI/Qwen3-Coder-Next-NVFP4` on port 8000. Identical config on both starsky and hutch.

## Files

- `compose.yml` — the stack
- `.env.example` — template for `.env` (which holds your HF token); `.env` is gitignored

## Deploy

Use `src/scripts/deploy.sh` from the repo root — it rsyncs this directory to the remote and runs `docker compose up -d`. Don't run `docker compose up` here directly.

## Override knobs

All compose variables have sensible defaults; override by uncommenting lines in `.env`. Most likely to tune:

- `VLLM_MAX_MODEL_LEN` — context window. Lower frees memory for KV cache.
- `VLLM_GPU_MEM_UTIL` — fraction of GPU memory vLLM may use. Default 0.90.
- `VLLM_IMAGE` — defaults to the locally-built `cuda-vllm:latest` (native
  sm_89/120/121 cutlass; the `cuda-vllm` primate lives at `primates/cuda-vllm.dockerfile`
  in the repo root and is shipped to both Sparks via
  `docker save | zstd | ssh hutch | docker load`).
  Override to upstream `vllm/vllm-openai:vX.Y.Z-cu129-ubuntu2404` if needed.

## Smoke test

Once running on a box (e.g. starsky):

```bash
curl -s http://starsky:8000/v1/models | jq .
curl -s http://starsky:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"qwen3-coder-next","messages":[{"role":"user","content":"hello"}]}' | jq .
```

The model takes several minutes to load on first start (downloads weights).
