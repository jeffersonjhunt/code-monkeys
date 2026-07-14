# Parking Lot

Items intentionally deferred. Each entry has a clear retry trigger so we know when it's worth picking up again.

## Try `Qwen/Qwen3.6-27B-FP8` (dense, native FP8) once vLLM ships sm_121-native cutlass kernels

**Resolved 2026-05-08:** `vllm-spark:latest` (locally-built, sm_121 native cutlass via `compute_120f` family-flag forward-compat — see `~/workspace/code-monkeys/primates/vllm-spark.dockerfile`) serves `Qwen/Qwen3.6-27B-FP8` cleanly. CUDA graph capture and the FP8 GEMM path (`cutlass_scaled_mm`) both go through without `Error Internal`. Smoke-tested via `/v1/chat/completions` against the canary model. Historical context below preserved for future kernel debugging.

**Status:** blocked by the upstream `vllm-openai` images being built with `TORCH_CUDA_ARCH_LIST=...12.0` (sm_120) max — DGX Spark / GB10 is **sm_121**, not sm_120. Pre-compiled cutlass `.so` blobs use sm_120-specific instructions and fail on sm_121 hardware with `Error Internal`. Triton-JIT paths (Marlin) work because Triton compiles from `compute_120` PTX → sm_121 native at runtime; pre-compiled cutlass blobs don't get the same JIT recompile and crash.

**What we tried (2026-05-07):**

Pre-flight checks all green: `Qwen3_5ForConditionalGeneration` is in vLLM's model registry, `torch.float8_e4m3fn` works on the GPU, `vllm.model_executor.layers.quantization.Fp8Config` is registered, FP8 cast roundtrip succeeded. Pulled 29 GB of weights to both starsky and hutch in parallel. Deployed with `--quantization fp8` (auto-detected from the model's quantization_config). The **model loaded cleanly** — 28.51 GiB GPU memory, attention block aligned to 784 tokens (this dense version has Mamba/DeltaNet layers too, just no MoE routing), torch.compile completed successfully.

**Crash during the first warmup forward pass**, both replicas, same error within seconds of each other:

```
RuntimeError: cutlass_gemm_caller,
/workspace/csrc/libtorch_stable/quantization/w8a8/cutlass/c3x/cutlass_gemm_caller.cuh:61,
Error Internal
```

Failing op was `torch.ops._C.cutlass_scaled_mm.default(...)` on a 5120×16384 weight tensor with FP8 scaling. The kernel binary in the upstream image was compiled targeting sm_120; on sm_121 hardware it hits the same `Error Internal` class as the FlashInfer fused-MoE NVFP4 path. (Inside the container, `torch.cuda.get_arch_list()` is `['sm_80', 'sm_90', 'sm_100', 'sm_120', 'compute_120']` and `TORCH_CUDA_ARCH_LIST=8.0 8.7 8.9 9.0 10.0 12.0` — no sm_121 native, only `compute_120` PTX.)

**Workaround attempted (2026-05-07): `VLLM_TEST_FORCE_FP8_MARLIN=1` does NOT work for this model on vLLM 0.20.1.** Per the NVIDIA forum thread (https://forums.developer.nvidia.com/t/marlin-fix-nvfp4-actually-works-on-sm121-dgx-spark/365119), forcing FP8 through Marlin fixes the cutlass crash on sm_121. Tried it — same crash. Root cause: the model uses **block-scaled FP8** (per-token-group activation quantization with 128-element groups, `quantization_config: {quant_method: "fp8", fmt: "e4m3", activation_scheme: "dynamic"}`), and in vLLM 0.20.1's source (`vllm/model_executor/kernels/linear/__init__.py:_POSSIBLE_FP8_BLOCK_KERNELS`) the priority order is:

```
1. FlashInferFp8DeepGEMMDynamicBlockScaledKernel
2. DeepGemmFp8BlockScaledMMKernel
3. CutlassFp8BlockScaledMMKernel        ← crashes on sm_121
4. MarlinFP8ScaledMMLinearKernel        ← only ELIGIBLE when env var set
5. TritonFp8BlockScaledMMKernel
```

`VLLM_TEST_FORCE_FP8_MARLIN=1` only flips Marlin's `is_supported()` from False to True at sm ≥ 89 (`vllm/model_executor/kernels/linear/scaled_mm/marlin.py`) — it does not change the priority order. So Cutlass is still picked first, and crashes. The forum's NVFP4 fix worked because NVFP4 has a *selector* env var (`VLLM_NVFP4_GEMM_BACKEND=marlin`) that maps directly to a kernel class via `_NVFP4_BACKEND_TO_KERNEL`. **There is no equivalent selector for FP8 dense block-scaled in 0.20.1.**

Possible paths forward:

- **Build a sm_121-native vLLM image** (a `vllm-spark` primate). Plan in `docs/vllm-spark-build-plan.md`. Mirrors `~/workspace/code-monkeys/primates/llama-cpp-spark.dockerfile` (CUDA 13.1.1 base + `CMAKE_CUDA_ARCHITECTURES=121`) but for vLLM. This is the principled fix — it gives us native sm_121 binaries everywhere and unblocks every cutlass-bound path in one go.
- **Wait for upstream vLLM** to add sm_121 to their default `TORCH_CUDA_ARCH_LIST`, *and* add a `VLLM_FP8_GEMM_BACKEND` selector env var (analogous to the existing `VLLM_NVFP4_GEMM_BACKEND`). Two independent upstream changes needed.
- **Patch the 0.20.1 image** to pass `force_kernel=MarlinFP8ScaledMMLinearKernel` in the `init_fp8_linear_kernel` call inside `vllm/model_executor/layers/quantization/fp8.py:377`. Routes through Marlin's Triton JIT path which already works on sm_121. Two-line patch.
- **Try the per-tensor-FP8 variant** if Qwen ships one — that takes the non-block path (`_POSSIBLE_FP8_KERNELS`) which has different priority and may dodge the broken cutlass blob.

**Side note from the deploy:** the model has a sidecar `mtp.safetensors` (multi-token prediction speculator). vLLM 0.20.1 spins up a *second* engine to host it after the main model finishes loading — roughly doubles startup time. Worth budgeting for if/when this works.

**Retry triggers:**

- The `vllm-spark` primate is built and available locally (see `docs/vllm-spark-build-plan.md`) — biggest unlock; closes this entry directly.
- Upstream vLLM ships an aarch64 image with `TORCH_CUDA_ARCH_LIST` containing `12.1` (sm_121). Watch the tag list: `curl -sS 'https://hub.docker.com/v2/repositories/vllm/vllm-openai/tags?page_size=50&ordering=last_updated'`.
- vLLM release notes mention sm_121 / DGX Spark / GB10 support, or cutlass `Error Internal` on Blackwell-consumer.
- NVIDIA ships a per-model `-dgx-spark` NIM for Qwen3.6 27B (would also work as a comparison datapoint).

**How to retry:**

1. Weights staged at `/srv/models/Qwen/Qwen3.6-27B-FP8` on both boxes (~29 GB each). No re-download needed.
2. Bump the vLLM image tag in `src/compose/vllm/compose.yml` (e.g. `v0.20.2-cu129-ubuntu2404` if available).
3. Edit `src/compose/vllm/.env`:
   ```
   HF_MODEL_ID=Qwen/Qwen3.6-27B-FP8
   VLLM_SERVED_NAME=qwen3.6-27b-fp8
   VLLM_TOOL_PARSER=qwen3_xml
   VLLM_REASONING_PARSER=qwen3
   VLLM_GPU_MEM_UTIL=0.55
   ```
   (Drop the `VLLM_USE_FLASHINFER_MOE_FP16` etc. — those are MoE-specific.)
4. `./src/scripts/deploy.sh starsky vllm` and watch `docker logs vllm` for the cutlass error.
5. If clean, deploy hutch, run `./src/scripts/bench-sweep.sh starsky:8080`. Expect ~10 tok/s/stream peak (vs 38 on the AWQ MoE) — dense 27B reads ~5× more weights per token.

## Switching the cluster to NIM serving the original `RedHatAI/Qwen3-Coder-Next-NVFP4`

**Resolved 2026-05-08 (via `vllm-spark`, not NIM):** `vllm-spark:latest` serves `RedHatAI/Qwen3-Coder-Next-NVFP4` cleanly. FlashInfer's `get_gemm_sm120_module_cutlass_fp4` JIT-compiles the FP4 GEMM module against sm_121 at first NVFP4 forward pass (the venv has `ninja` for this); FlashInfer fused-MoE cutlass kernels then load and capture into CUDA graphs without `Error Internal`. Verified end-to-end via `/v1/chat/completions`. The NIM path below was the alternative we no longer need to chase. Historical context preserved below.

**Status:** blocked by upstream kernel work — neither vLLM nor NIM can serve this model on DGX Spark today. Hardware is sm_121 (GB10); the upstream `vllm-openai` images ship sm_120 native binaries plus `compute_120` PTX, so cutlass blobs targeted at sm_120 fail on sm_121. The `vllm-spark` primate (`docs/vllm-spark-build-plan.md`) would address this.

**What we tried (2026-05-05):**

1. `nvcr.io/nim/nvidia/llm-nim:latest` (NIM 1.15.5) — wrong image. `list-model-profiles` returned `<None>` for both pre-built and JIT-compile buckets on GB10. NIM 1.x doesn't have BYO-mode Spark coverage.
2. `nvcr.io/nim/nvidia/model-free-nim:2.0.3` with `NIM_MODEL_PATH=hf://RedHatAI/Qwen3-Coder-Next-NVFP4` — got much further: detected UMA (auto-clamped `gpu_memory_utilization 0.9 → 0.5`), downloaded weights (45 GB), loaded all 10 safetensors shards in ~4 min. **Crashed during engine init** with `[TensorRT-LLM][ERROR] Assertion failed: Failed to initialize cutlass TMA WS grouped gemm` — NVFP4 fused-MoE grouped-GEMM kernels are present (`cutlass_instantiations/120/gemm_grouped/...sm120_*.generated.cu`) but every tactic the FlashInfer autotuner tried failed at runtime with "Error Internal." Same fundamental gap that blocks stock vLLM 0.20.1.

**Root cause class:** NVFP4 quantization × MoE routing × sm_121 hardware running sm_120-targeted cutlass kernels. The pre-compiled blob lives in **FlashInfer's `fused_moe_120.so`** (path: `/usr/local/lib/python3.12/dist-packages/flashinfer_jit_cache/jit_cache/fused_moe_120/fused_moe_120.so`) — note the `_120` in the filename: this kernel pack was built targeting sm_120 (consumer Blackwell, e.g. RTX 5090), and on sm_121 hardware (DGX Spark / GB10) every cutlass TMA WS tactic the autotuner profiles fails with `Failed to initialize cutlass TMA WS grouped gemm. Error: Error Internal`. Verified universal across NVFP4 MoE models by also testing `RedHatAI/Qwen3-30B-A3B-NVFP4` (no Mamba, smaller, simpler) — same crash signature. So the gap is not specific to hybrid Mamba models or to a particular size; it's that the FlashInfer fused-MoE NVFP4 kernel pack ships sm_120 binaries while our hardware is sm_121. Tracked in vLLM upstream as #41477 (Triton MXFP4 MoE PTX) and #41564 (`/wake_up` on hybrid SWA/Mamba) — neither is exactly this bug, but the fix area overlaps.

**Workaround landed (different path):** the cluster currently serves `QuantTrio/Qwen3.6-35B-A3B-AWQ` instead — AWQ quantization auto-selects vLLM's `awq_marlin` kernel which compiles via Triton JIT (correctly targeting sm_121 from `compute_120` PTX at runtime), sidestepping the broken pre-compiled NVFP4 blob entirely. So the immediate need for an NVFP4-MoE-on-sm_121 fix has eased; this entry stays open only because the original target (`Qwen3-Coder-Next-NVFP4`) is *coder-tuned* and there's no AWQ equivalent yet. If a coder-tuned AWQ MoE drops, that's another way out.

**Backend-override workaround we haven't tried** (still relevant if NVFP4 is the only option): vLLM's log lists alternative MoE backends `{FLASHINFER_TRTLLM, FLASHINFER_CUTEDSL, FLASHINFER_CUTEDSL_BATCHED, FLASHINFER_CUTLASS, VLLM_CUTLASS, MARLIN, EMULATION}`. By default it auto-selects `FLASHINFER_CUTLASS` (the one that fails). Forcing `VLLM_CUTLASS`, `MARLIN`, or `EMULATION` via env (e.g. `VLLM_FUSED_MOE_BACKEND=...`) might bypass the broken kernel — at the cost of throughput. Worth one experiment cycle on the next retry.

**Per-model NIM alternative:** `nvcr.io/nim/qwen/qwen3-32b-dgx-spark` is confirmed to exist (manifest pulled). NVIDIA pre-builds and hand-validates these per-model NIMs, so it presumably dodges the kernel issue. But it's general-purpose Qwen3-32B, not Coder-tuned — and no `qwen3-coder-*-dgx-spark` is in NVIDIA's catalog yet.

**Retry triggers:**

- The `vllm-spark` primate is built and available locally (see `docs/vllm-spark-build-plan.md`) — would give us native sm_121 NVFP4 cutlass kernels.
- vLLM #41477 or #41564 close, or a vLLM release notes entry mentions Blackwell sm_121 / DGX Spark / GB10 grouped-GEMM / NVFP4 MoE kernel fixes.
- **vLLM v0.20.2 release.** Adjacent issue #41645 (gpt-oss MXFP4 MoE shape bug on B200/GB200) is targeted for v0.20.2, with PR #41646 open. Not our bug (different model, MXFP4 vs NVFP4, sm_100 vs sm_120), but it indicates the v0.20.2 release is the active Blackwell + MoE milestone — a good cadence point to re-test our NVFP4 stack.
- NVIDIA ships a coder-tuned NIM with `-dgx-spark` suffix (watch `nvcr.io/nim/qwen/qwen3-coder-*` and `nvcr.io/nim/redhatai/*`).
- A new TRT-LLM release that lists sm_121 cutlass grouped-GEMM tactics as supported.
- A NIM `model-free-nim` ≥ 2.1.x release.

**How to retry:**

1. Reconstruct the NIM compose stack — `git show 4cf2a3a:src/compose/nim/compose.yml > src/compose/nim/compose.yml` (same for `.env.example`, `README.md`). The stack was removed 2026-05-12; previous commit is `4cf2a3a`.
2. Bump the image tag in `compose.yml` to whatever's new.
3. From the repo root: `ssh jhunt@starsky 'cd ~/spark-deploy/vllm && docker compose stop'` (free the GPU)
4. `./src/scripts/deploy.sh starsky nim` — same pattern as before.
5. Watch logs for the cutlass error. If gone, smoke test on `starsky:8001`. If clean, plan migration: `deploy.sh hutch nim`, retire vLLM stack, update HAProxy backends to port 8001.
6. If a per-model NIM ships, swap `image:` and `NIM_MODEL_PATH` accordingly.

## Try `qwen3-32b-dgx-spark` per-model NIM as a NIM-blessed Qwen3 path

**Status:** not attempted yet. Would give us Qwen3 family + NVIDIA-curated for Spark, at the cost of losing Coder tuning (general-purpose 32B dense).

**Retry trigger:** wanting a Qwen3-flavored cluster without Coder specialization, or wanting to validate NIM operationally on Spark independently of the model selection.

**How to retry:**

1. Reconstruct `src/compose/nim/compose.yml` from git (`git show 4cf2a3a:src/compose/nim/compose.yml > src/compose/nim/compose.yml`), then change `image:` to `nvcr.io/nim/qwen/qwen3-32b-dgx-spark:latest`, drop `NIM_MODEL_PATH` (per-model NIMs come pre-configured with their model), bump `NIM_SERVED_MODEL_NAME` if desired.
2. Stop starsky vllm to free the GPU; deploy NIM to starsky.
3. If healthy, deploy to hutch, then update `haproxy.cfg` backends to port 8001 and redeploy haproxy.

## Migrate secrets from the `vault` (openssl + S3) to SOPS + age

**Deferred (2026-07-02).** g.deceiver is adopting **SOPS + age** with encrypted secrets in a new
CodeCommit repo `hemlighet` (see `g.deceiver/docs/plans/ecr-sops-deploy.md`). code-monkeys currently
manages secrets via the homegrown `vault` script (openssl-AES tarballs — `.ssh.vault`/`.env.vault`/
`.aws.vault` — synced to S3). Fold the cluster's secrets (`cluster.env`, per-stack `.env` incl.
`HF_TOKEN`) into the same SOPS/age model so the fleet has one secrets mechanism.

**Retry trigger:** after g.deceiver Phase 0 lands `hemlighet` + the age-key/`.sops.yaml` scaffolding —
reuse it here (add `code-monkeys/*.env.sops`, seed each host's age key), then retire `vault` for the
cluster. The SSH keys the vault also holds are a separate concern — keep or migrate deliberately.

**Update (2026-07-04) — env secrets DONE for the cluster.** The cluster's only real env secret,
`HF_TOKEN` (in `vllm/.env`, alongside its serving config), is now SOPS/age-encrypted in `hemlighet` as
`code-monkeys/cluster-vllm.env` (recipients admin + hutch); `deploy.sh` decrypts it on the target at
deploy. `cluster.env` is config-only (no secret) and stays in git. So `vault`'s **env** role is retired
for the cluster. **Still on `vault` (deliberately deferred):** the **SSH keys** and **`.aws` creds** it
bundles — those fold into the separate "off-`jhunt` / per-host IAM + service accounts" effort, not here.

**RESOLVED (2026-07-13) — migration complete.** The `vault` script itself was rewritten as a SOPS/age
wrapper (nyckel primate): all five items (ssh/, aws/, env, face, gitconfig) now live per-file,
binary-mode encrypted in `hemlighet` under `code-monkeys/personal/` (recipients: offline admin +
mjolnir + hutch; add hosts via `.sops.yaml` + `./vault rekey`). The openssl `.vault` tarballs and the
S3 sync (`VAULT_BUCKET`) are retired — machine sync is hemlighet git push/pull. One secrets mechanism
fleet-wide, as this entry wanted.

## Dedicated build machine when a 3rd+ Spark arrives

**Deferred (2026-07-02).** Today all images build **native-on-host** (the host that runs an image
builds + pushes it to ECR; prod hosts therefore carry build toolchains + push creds). When cluster
capacity grows (more Spark boxes), promote one to a **dedicated builder**: it does all `buildx`/push,
prod hosts go **pull-only** (tighter blast radius, builds stop competing with inference).

**Retry trigger:** a spare Spark (or any host not needed for serving) becomes available — move the
push IAM identity + build caches there and downgrade the serving hosts to ECR pull-only.
