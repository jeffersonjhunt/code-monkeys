# Parking Lot

Items intentionally deferred. Each entry has a clear retry trigger so we know when it's worth picking up again.

## Switching the cluster to NIM serving the original `RedHatAI/Qwen3-Coder-Next-NVFP4`

**Status:** blocked by upstream kernel work — neither vLLM nor NIM can serve this model on DGX Spark sm_120 today.

**What we tried (2026-05-05):**

1. `nvcr.io/nim/nvidia/llm-nim:latest` (NIM 1.15.5) — wrong image. `list-model-profiles` returned `<None>` for both pre-built and JIT-compile buckets on GB10. NIM 1.x doesn't have BYO-mode Spark coverage.
2. `nvcr.io/nim/nvidia/model-free-nim:2.0.3` with `NIM_MODEL_PATH=hf://RedHatAI/Qwen3-Coder-Next-NVFP4` — got much further: detected UMA (auto-clamped `gpu_memory_utilization 0.9 → 0.5`), downloaded weights (45 GB), loaded all 10 safetensors shards in ~4 min. **Crashed during engine init** with `[TensorRT-LLM][ERROR] Assertion failed: Failed to initialize cutlass TMA WS grouped gemm` — NVFP4 fused-MoE grouped-GEMM kernels are present (`cutlass_instantiations/120/gemm_grouped/...sm120_*.generated.cu`) but every tactic the FlashInfer autotuner tried failed at runtime with "Error Internal." Same fundamental gap that blocks stock vLLM 0.20.1.

**Root cause class:** NVFP4 quantization × MoE routing × sm_120 (GB10) × cutlass grouped-GEMM kernels. The bug lives in **FlashInfer's `fused_moe_120.so`** (path: `/usr/local/lib/python3.12/dist-packages/flashinfer_jit_cache/jit_cache/fused_moe_120/fused_moe_120.so`) — every cutlass TMA WS tactic the autotuner profiles fails with `Failed to initialize cutlass TMA WS grouped gemm. Error: Error Internal`. Verified universal across NVFP4 MoE models on sm_120 by also testing `RedHatAI/Qwen3-30B-A3B-NVFP4` (no Mamba, smaller, simpler) — same crash signature. So the gap is not specific to hybrid Mamba models or to a particular size; it's the FlashInfer fused-MoE NVFP4 kernel pack for sm_120. Tracked in vLLM upstream as #41477 (Triton MXFP4 MoE PTX) and #41564 (`/wake_up` on hybrid SWA/Mamba) — neither is exactly this bug, but the fix area overlaps.

**Workaround landed (different path):** the cluster currently serves `QuantTrio/Qwen3.6-35B-A3B-AWQ` instead — AWQ quantization auto-selects vLLM's `awq_marlin` kernel, which sidesteps the FlashInfer NVFP4 fused-MoE entirely. So the immediate need for an NVFP4-MoE-on-sm_120 fix has eased; this entry stays open only because the original target (`Qwen3-Coder-Next-NVFP4`) is *coder-tuned* and there's no AWQ equivalent yet. If a coder-tuned AWQ MoE drops, that's another way out.

**Backend-override workaround we haven't tried** (still relevant if NVFP4 is the only option): vLLM's log lists alternative MoE backends `{FLASHINFER_TRTLLM, FLASHINFER_CUTEDSL, FLASHINFER_CUTEDSL_BATCHED, FLASHINFER_CUTLASS, VLLM_CUTLASS, MARLIN, EMULATION}`. By default it auto-selects `FLASHINFER_CUTLASS` (the one that fails). Forcing `VLLM_CUTLASS`, `MARLIN`, or `EMULATION` via env (e.g. `VLLM_FUSED_MOE_BACKEND=...`) might bypass the broken kernel — at the cost of throughput. Worth one experiment cycle on the next retry.

**Per-model NIM alternative:** `nvcr.io/nim/qwen/qwen3-32b-dgx-spark` is confirmed to exist (manifest pulled). NVIDIA pre-builds and hand-validates these per-model NIMs, so it presumably dodges the kernel issue. But it's general-purpose Qwen3-32B, not Coder-tuned — and no `qwen3-coder-*-dgx-spark` is in NVIDIA's catalog yet.

**Retry triggers:**

- vLLM #41477 or #41564 close, or a vLLM release notes entry mentions Blackwell sm_120 grouped-GEMM / NVFP4 MoE kernel fixes.
- **vLLM v0.20.2 release.** Adjacent issue #41645 (gpt-oss MXFP4 MoE shape bug on B200/GB200) is targeted for v0.20.2, with PR #41646 open. Not our bug (different model, MXFP4 vs NVFP4, sm_100 vs sm_120), but it indicates the v0.20.2 release is the active Blackwell + MoE milestone — a good cadence point to re-test our NVFP4 stack.
- NVIDIA ships a coder-tuned NIM with `-dgx-spark` suffix (watch `nvcr.io/nim/qwen/qwen3-coder-*` and `nvcr.io/nim/redhatai/*`).
- A new TRT-LLM release that lists sm_120 cutlass grouped-GEMM tactics as supported.
- A NIM `model-free-nim` ≥ 2.1.x release.

**How to retry:**

1. `cd src/compose/nim` — the stack is preserved.
2. Bump the image tag in `compose.yml` to whatever's new.
3. From the repo root: `ssh jhunt@starsky 'cd ~/spark-deploy/vllm && docker compose stop'` (free the GPU)
4. `./src/scripts/deploy.sh starsky nim` — same pattern as before.
5. Watch logs for the cutlass error. If gone, smoke test on `starsky:8001`. If clean, plan migration: `deploy.sh hutch nim`, retire vLLM stack, update HAProxy backends to port 8001.
6. If a per-model NIM ships, swap `image:` and `NIM_MODEL_PATH` accordingly.

## Try `qwen3-32b-dgx-spark` per-model NIM as a NIM-blessed Qwen3 path

**Status:** not attempted yet. Would give us Qwen3 family + NVIDIA-curated for Spark, at the cost of losing Coder tuning (general-purpose 32B dense).

**Retry trigger:** wanting a Qwen3-flavored cluster without Coder specialization, or wanting to validate NIM operationally on Spark independently of the model selection.

**How to retry:**

1. Edit `src/compose/nim/compose.yml`: change `image:` to `nvcr.io/nim/qwen/qwen3-32b-dgx-spark:latest`, drop `NIM_MODEL_PATH` (per-model NIMs come pre-configured with their model), bump `NIM_SERVED_MODEL_NAME` if desired.
2. Stop starsky vllm to free the GPU; deploy NIM to starsky.
3. If healthy, deploy to hutch, then update `haproxy.cfg` backends to port 8001 and redeploy haproxy.
