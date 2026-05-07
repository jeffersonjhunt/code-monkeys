# Plan: build a `vllm-spark` primate (vLLM image with native sm_121 binaries)

Hand-off document for a parallel Claude instance. Written 2026-05-07. Self-contained — the executing agent has none of the conversation context that produced this plan.

## Context

**Hardware:** NVIDIA DGX Spark (GB10), ARM64, 128 GB unified memory, **compute capability sm_121** (distinct from sm_120 = RTX 5090 / RTX PRO 6000).

**Project consuming this deliverable:** `~/workspace/spark-cluster` — a vLLM replica cluster on two DGX Sparks (`starsky`, `hutch`) behind HAProxy. Currently serving `QuantTrio/Qwen3.6-35B-A3B-AWQ` via the official `vllm/vllm-openai:v0.20.1-cu129-ubuntu2404` image. **AWQ + Marlin works** because Marlin generates kernels via Triton JIT (which targets sm_121 from `compute_120` PTX at startup).

**The problem this image solves.** Upstream `vllm/vllm-openai` images are built with `TORCH_CUDA_ARCH_LIST="8.0 8.7 8.9 9.0 10.0 12.0"` — sm_120 max, no native sm_121. PyTorch's `compute_120` PTX gets JIT-compiled to sm_121 at runtime, so anything that goes through Triton or PTX→native works fine (AWQ Marlin is the proof). But hand-tuned native cutlass `.so` blobs (`fused_moe_120.so`, `cutlass_scaled_mm`, etc.) are baked as sm_120 binary code; native sm_120 → sm_121 is not forward-compatible the way PTX → native is. Result: `RuntimeError: cutlass_gemm_caller, ... Error Internal` for FP8 dense block-scaled, NVFP4 MoE, and similar kernels. See `docs/parking-lot.md` for the documented failures.

**Confirmed working pattern.** `~/workspace/code-monkeys/primates/llama-cpp-spark.dockerfile` builds llama.cpp on `nvidia/cuda:13.1.1-devel-ubuntu24.04` with `-DCMAKE_CUDA_ARCHITECTURES=121` and runs cleanly on these boxes. The recipe: **CUDA 13.x toolkit (knows sm_121) + explicit `121` arch flag.** Upstream vLLM has not applied this recipe.

## Goal

Produce a primate-style Dockerfile that builds a drop-in replacement for `vllm/vllm-openai:v0.20.1-cu129-ubuntu2404` with **native sm_121 binaries** for all C++/CUDA extensions (vLLM core, FlashInfer, cutlass instantiations, DeepGEMM if present).

### Acceptance criteria

A container built from this image, run with `--gpus all` on a DGX Spark, must show:

```python
import torch
torch.cuda.get_arch_list()    # includes 'sm_121' (or compute_121)
```

```bash
# inside container
echo $TORCH_CUDA_ARCH_LIST     # contains 12.1
ls /usr/local/lib/python3.*/dist-packages/flashinfer_jit_cache/jit_cache/ 2>/dev/null
# expect at least one fused_moe_121.so or equivalent path
```

And the previously-failing models must run without the `cutlass_gemm_caller Error Internal` crash:

- `Qwen/Qwen3.6-27B-FP8` (FP8 dense block-scaled — the canary that's been crashing)
- `RedHatAI/Qwen3-Coder-Next-NVFP4` (NVFP4 MoE — the long-term target)

## Approach (pick one path)

**Path A — fork vLLM's official Dockerfile (recommended).** vLLM's repo includes `docker/Dockerfile` (https://github.com/vllm-project/vllm/blob/main/docker/Dockerfile) that builds the official image. Fork it, swap the base to `nvidia/cuda:13.1.1-devel-ubuntu24.04`, and override `TORCH_CUDA_ARCH_LIST="8.0 8.7 8.9 9.0 10.0 12.0 12.1+PTX"`. This rebuilds all CUDA extensions natively for sm_121 from one place.

**Path B — overlay on top of upstream.** Start `FROM vllm/vllm-openai:v0.20.1-cu129-ubuntu2404`, identify the sm_120 `.so` files via `find / -name '*_120.so'`, recompile each from source against sm_121, drop the new blobs in. Less rebuild surface but fragile, scattered, and no clean upgrade path.

**Recommendation: Path A.** One source of truth, well-trodden upstream pattern, primate-style fits cleanly.

## Build steps (Path A)

These mirror the primates convention in `~/workspace/code-monkeys/primates/`:

1. **Add a Makefile target** in `primates/Makefile` next to `llama-cpp-spark.build`:

   ```make
   vllm-spark.build:
       docker buildx build \
           --platform linux/arm64 \
           --target final \
           --build-arg VLLM_VERSION=v0.20.1 \
           --build-arg TORCH_CUDA_ARCH_LIST="8.0 8.7 8.9 9.0 10.0 12.0 12.1+PTX" \
           -t vllm-spark:latest \
           -f vllm-spark.dockerfile .
   ```

2. **Create `primates/vllm-spark.dockerfile`** following the multi-stage pattern from `llama-cpp-spark.dockerfile`. Key differences:

   - Base: `nvidia/cuda:13.1.1-devel-ubuntu24.04` for build, `nvidia/cuda:13.1.1-runtime-ubuntu24.04` for runtime.
   - Install Python 3.12 + venv + build deps (cmake, ninja, gcc, git, etc.).
   - Install PyTorch built against CUDA 13.x for aarch64. Two ways:
     - Use NVIDIA's NGC PyTorch container layers, OR
     - Pip install from PyTorch's nightly index that includes cu13x aarch64 wheels (verify availability — fallback is build PyTorch from source, multi-hour).
   - `git clone https://github.com/vllm-project/vllm.git --branch v0.20.1`.
   - Set `ENV TORCH_CUDA_ARCH_LIST="8.0 8.7 8.9 9.0 10.0 12.0 12.1+PTX"` and `ENV NVCC_THREADS=4` (parallelism for nvcc).
   - `pip install -e . --no-build-isolation` from the vllm checkout — this rebuilds all C++/CUDA extensions against the requested arch list.
   - Rebuild **FlashInfer** from source with the same arch list (`pip install --no-build-isolation flashinfer-python` from source, OR clone flashinfer repo and `pip install -e .`). Their PyPI wheels are arch-specific; the wheels we want for sm_121 don't exist, so source build is required.
   - For the runtime stage: copy the venv + only the runtime CUDA libs, drop devel toolchain. Mirror the primates pattern of `userdel ubuntu`, create `codemonkey` user, NOPASSWD sudo.
   - Final entrypoint should match `vllm/vllm-openai`: `ENTRYPOINT ["python3", "-m", "vllm.entrypoints.openai.api_server"]` (verify by inspecting the upstream image: `docker inspect vllm/vllm-openai:v0.20.1-cu129-ubuntu2404`).

3. **Build native on starsky.** Cross-compile aarch64 from an x86 workstation needs QEMU emulation and is hours-slow; native build on the Spark itself uses local nvcc and runs at full speed. The cluster's `hutch` keeps serving while starsky is busy, so this is acceptable. Keep `vllm` container running on starsky during build (build runs in a separate container, GPU not needed during compile — only at validation time).

   Estimated build time: 1–4 hours depending on parallelism and which deps need source builds.

4. **Save image as tarball** for transport to hutch:

   ```bash
   docker save vllm-spark:latest | zstd > vllm-spark.tar.zst
   scp vllm-spark.tar.zst jhunt@hutch:~/
   ssh jhunt@hutch 'zstd -d < vllm-spark.tar.zst | docker load'
   ```

   Or push to a private registry if one exists.

## Validation steps

Run **inside the built container** on the Spark:

```bash
# 1. Arch list includes sm_121
python3 -c 'import torch; al = torch.cuda.get_arch_list(); print(al); assert any("121" in a for a in al), "no sm_121 in arch list"'

# 2. CUDA 13.x runtime
python3 -c 'import torch; print("cuda:", torch.version.cuda)'  # expect 13.x

# 3. Find a native sm_121 cutlass blob — should now exist
find / -name '*_121.so' 2>/dev/null | head
find / -name '*sm_121*' 2>/dev/null | head

# 4. Trial-run the canary that crashed before
vllm serve Qwen/Qwen3.6-27B-FP8 --max-model-len 4096 --gpu-memory-utilization 0.55 &
# wait ~5min for warmup; expect /health 200 instead of cutlass_gemm_caller Error Internal
```

If validation passes, also run a quick smoke through the OpenAI-compatible endpoint:

```bash
curl -fsS http://127.0.0.1:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"Qwen/Qwen3.6-27B-FP8","messages":[{"role":"user","content":"hello"}],"max_tokens":32}'
```

## Integration with `spark-cluster`

Once the image exists on both `starsky` and `hutch` (either built or loaded from tarball):

1. Edit `spark-cluster/src/compose/vllm/compose.yml`:
   ```yaml
   image: ${VLLM_IMAGE:-vllm-spark:latest}
   ```
   (or whatever local tag was chosen).
2. Optionally bump `spark-cluster/src/compose/vllm/.env.example` with a comment noting `VLLM_IMAGE=vllm-spark:latest` is now the local-built option.
3. `./src/scripts/deploy.sh starsky vllm` then `./src/scripts/deploy.sh hutch vllm`.
4. Smoke test through HAProxy: `./src/scripts/smoke-test.sh starsky:8080`.
5. Update `docs/parking-lot.md` — close the FP8 and NVFP4 entries (or downgrade them to "verified working with sm_121-native build").

## Risks and open questions

- **PyTorch aarch64 + CUDA 13.x wheels.** Verify these exist on https://download.pytorch.org/whl/nightly/cu131 (or cu130) for aarch64. If missing, the plan needs a PyTorch source build (multi-hour, but doable). Check first: `pip download torch --index-url https://download.pytorch.org/whl/nightly/cu131 --platform manylinux_2_28_aarch64 --no-deps`.
- **FlashInfer source build complexity.** FlashInfer has heavy CUDA template instantiation; build time can be substantial. May need `FLASHINFER_ENABLE_AOT=0` or selective arch flags to keep build manageable.
- **Build-time disk usage.** vLLM + FlashInfer source builds together want 50–100 GB scratch. Verify `/tmp` and Docker overlay storage on starsky have headroom.
- **Image size.** Final image likely 30–40 GB even after cleanup — comparable to `vllm/vllm-openai`. Loading on hutch via tarball is the practical distribution path absent a private registry.
- **`compute_120` vs `12.1+PTX`.** PTX backward-compatibility means `12.1+PTX` covers Spark, but if anything in the toolchain emits raw assembly during build, that step must see arch=121. The arch list above includes both for safety.

## Stretch goals (not required for first cut)

- Add a `vllm-spark-server` lighter target that strips devel artifacts from the runtime stage (analog to `llama-cpp-spark`'s `light` and `server` stages).
- Bake a healthcheck consistent with the spark-cluster compose pattern (Python urllib `/health` probe, since the upstream image lacks `wget`).
- Make `VLLM_VERSION` a build arg and pin the cutlass / flashinfer SHA to known-good versions, rather than `main`.

## Inputs already discovered (useful for the executing agent)

- DGX Spark capability per `nvidia-smi`: `compute_cap=12.1`, name `NVIDIA GB10`.
- Confirmed primates target works on identical hardware: `~/workspace/code-monkeys/primates/llama-cpp-spark.dockerfile` (CUDA 13.1.1, `CMAKE_CUDA_ARCHITECTURES=121`).
- Upstream vLLM already has working aarch64 + CUDA 13.0 builds (`vllm/vllm-openai:v0.20.0-aarch64-cu130-ubuntu2404`) but their `TORCH_CUDA_ARCH_LIST` stops at `12.0+PTX` — the only thing we're really changing is the arch list.
- vLLM Docker source: https://github.com/vllm-project/vllm/tree/main/docker
