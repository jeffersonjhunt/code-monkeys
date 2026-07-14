# Decisions

Architectural decision log. Newest first.

## 2026-06-28 — Replaced HAProxy with a model-aware router (LiteLLM) on `minerva`

The 2026-06-10 split left two boxes serving two different models (coder on hutch, reasoning on starsky) behind a round-robin HAProxy that could only front a single pool — it ignored the request `model` field. That meant the reasoning box sat outside the cluster endpoint, and g.deceiver's orchestrator had to call `starsky:8000` directly.

Replaced the HAProxy LB with a **LiteLLM proxy** (`src/compose/litellm/`, pinned `ghcr.io/berriai/litellm:v1.90.0`, `network_mode: host` on `minerva:8888`). It routes by the OpenAI `model` field via a declarative `config.yaml` map:

- `qwen3-coder-next` → `hutch.tworivers:8000` (coding cluster / opencode)
- `reasoning` → `starsky.tworivers:8000` (g.deceiver reasoning-llm)
- unknown `model` → HTTP 400 (no silent misroute)

**Why LiteLLM over an HAProxy body-ACL:** model-name routing is its core competency, and we will hang a third model off this same endpoint (the Phase 6 g.deceiver captioning VLM on starsky) — that's one `config.yaml` line, versus a growing pile of HAProxy `req.body` regexes with buffer-size foot-guns. Cost is one lightweight async service on the LB host (no GPU), which already ran HAProxy.

**Cutover was zero-downtime:** stood up LiteLLM on `minerva:8889` alongside the live HAProxy on `:8888`, verified both routes (incl. the reasoning model's thinking-channel surviving the proxy) and the unknown-model 400, then stopped HAProxy and rebound LiteLLM to `:8888`. opencode needed no change (same base_url, same `model`); g.deceiver's orchestrator repointed `REASONING_LLM_URL` `starsky:8000` → `minerva:8888` (g.deceiver `v0.6.9`, scoped orchestrator redeploy).

- `deploy.sh all` now deploys the `litellm` stack to `$LB_HOST` (was `haproxy`). The `haproxy` stack stays in the repo as a documented fallback; deploy it explicitly if ever needed.
- **Consequence/opening:** with a model-aware endpoint, "both Sparks in one cluster" no longer requires one shared model. A 2nd coder replica becomes a 2nd `qwen3-coder-next` backend in `config.yaml` (LiteLLM load-balances same-name backends); the captioning VLM becomes the `caption` model. Tracked in `TASKS.md`.

## 2026-06-10 — Moved HAProxy to the control plane (`minerva`) and pulled `starsky` for g.deceiver reasoning

The g.deceiver build needed a dedicated GB10 for its reasoning model (`reasoning-llm`); a dense bf16 32B is memory-bandwidth-bound at ~4 tok/s on a GB10, so it wants a whole box for the A3B-AWQ thinking model. We pulled `starsky` from the coding cluster rather than co-locating (only ~25 GiB was free alongside the coding replica).

That forced the LB decoupling we'd already wanted (see `architecture.md` SPOF note): HAProxy lived **on** `starsky`, so freeing `starsky` meant moving the LB. It now runs as a standalone container on `minerva` (control plane, no GPU) at **`:8888`**, fronting `hutch` alone.

- Tooling changes (this branch): `load-config.sh` no longer requires `LB_HOST ∈ REPLICAS` (a dedicated LB host is valid); `haproxy.cfg.template`/`deploy.sh` now honor `$LB_PORT` for the public bind (was hardcoded `:8080`).
- Cutover was zero-downtime: stood up `minerva:8888` alongside the live `starsky:8080`, repointed coding clients, then tore down starsky's HAProxy + coding vLLM.
- **Consequence:** the coding cluster is now single-replica (`hutch` only). Accepted for now; tracked in `TASKS.md` Phase 12.
- **Follow-up:** HAProxy is still a dumb round-robin and ignores the request `model`. Replacing it with a model-aware router (so one endpoint serves both the coding model on hutch and the reasoning model on starsky) is the open task in `TASKS.md` Phase 12.

## 2026-05-06 — Switched served model to `QuantTrio/Qwen3.6-35B-A3B-AWQ`

After Qwen2.5-Coder-32B-Instruct (Track D) validated the cluster, we tried two more rounds toward the original NVFP4 target before settling here:

- Round 3: `RedHatAI/Qwen3-30B-A3B-NVFP4` (smaller, no Mamba) — same `cutlass TMA WS grouped gemm` failure. Confirmed the bug is FlashInfer's `fused_moe_120.so` NVFP4 kernel pack, not specific to Qwen3-Coder-Next or hybrid Mamba.
- Round 4: `QuantTrio/Qwen3.6-35B-A3B-AWQ` — community AWQ of Qwen3.6-A3B (DeltaNet hybrid + MoE, 3B active). vLLM auto-selects `awq_marlin`, which **bypasses the FlashInfer NVFP4 path entirely**. Loaded cleanly on both replicas, ~22 GiB GPU memory each.

Why this model:
- AWQ + Marlin is a known-good kernel path on sm_120 (sidesteps the NVFP4-MoE bug class).
- Qwen3.6-A3B is the closest available substitute for Qwen3-Coder-Next: same 3B-active MoE topology, same DeltaNet hybrid attention, similar size class. Coder tuning is the only missing piece — acceptable for now.
- `qwen3_coder` tool-call parser + `qwen3` reasoning parser make `tool_choice: "auto"` reliable (a major regression-fix vs the Qwen2.5-Coder + hermes path, where auto was unreliable).
- Per-stream throughput ~10× Qwen2.5-Coder-32B (38 vs 3.7 tok/s). Cluster aggregate peak ~752 tok/s at c=32 through HAProxy.

The `RedHatAI/Qwen3-Coder-Next-NVFP4` long-term target stays parked in `docs/parking-lot.md` with retry triggers (vLLM 0.20.2 release, FlashInfer kernel fix, NVIDIA shipping a `qwen3-coder-*-dgx-spark` NIM, etc.).

## 2026-05-05 — NIM model-free + Qwen3-Coder-Next-NVFP4 hits the same upstream gap as stock vLLM; cluster stays on Track D

Two-round Track A experiment, both confirming the cluster stays on vLLM today:

1. `llm-nim:latest` (NIM 1.15.5) — wrong image; `list-model-profiles` returned `<None>` for both pre-built and JIT-compile buckets on GB10. User identified the correct path.
2. `model-free-nim:2.0.3` with `NIM_MODEL_PATH=hf://RedHatAI/Qwen3-Coder-Next-NVFP4` — got further (UMA detection, weight load, engine init started) before crashing with `[TensorRT-LLM][ERROR] Assertion failed: Failed to initialize cutlass TMA WS grouped gemm`. NIM 2.0.3 *does* ship sm_120 cutlass kernels, but the NVFP4-grouped-GEMM (fused MoE) tactics all fail at runtime. Same root-cause class as stock vLLM 0.20.1's `cudaErrorNoKernelImageForDevice` — the upstream NVFP4-MoE-on-sm_120 path isn't ready in either runtime today.

Conclusion: serving `Qwen3-Coder-Next-NVFP4` on DGX Spark requires either an upstream cutlass/TRT-LLM fix or a hand-validated per-model NIM (which NVIDIA hasn't shipped for the Coder variants — only general-purpose `qwen3-32b-dgx-spark` and similar). Cluster moved on to `QuantTrio/Qwen3.6-35B-A3B-AWQ` via vLLM `awq_marlin` (see the 2026-05-06 entry). NIM stack kept in repo (`src/compose/nim/`) as documentation; trivially re-runnable when the kernels land. (Stack removed 2026-05-12 after `vllm-spark` resolved the NVFP4 path; reconstruct from `git show 4cf2a3a:src/compose/nim/...` if needed.)

## 2026-05-05 — DNS, not /etc/hosts, for cluster name resolution

Initial `bootstrap.sh` wrote a managed block to `/etc/hosts` on each box "to make sure starsky and hutch can resolve each other." Both names already resolved via DNS (verified with `host hutch.tworivers` from each box, which bypasses `/etc/hosts`). The defensive entries had zero upside and a real downside: nsswitch order is `files mdns4_minimal [NOTFOUND=return] dns`, so `/etc/hosts` shadows DNS, and any future IP change in DNS would be silently ignored locally.

Resolved by removing the `/etc/hosts` management from `bootstrap.sh` (kept the cleanup logic for backward compatibility) and switching HAProxy backends from hardcoded IPs to hostnames so DNS stays the single source of truth.

## 2026-05-05 — TP=1 per replica (override model card's TP=2 recommendation)

The HF model card for `RedHatAI/Qwen3-Coder-Next-NVFP4` recommends `--tensor-parallel-size 2`, but that's a validated-on-datacenter-GPU config (e.g. 2× H100). With Qwen3-Coder-Next at 80B total params (3B active, MoE) quantized to NVFP4 ≈ 40 GB, the full model fits in a single Spark's 128 GB unified memory with plenty of room for KV cache. Each replica runs `--tensor-parallel-size 1`.

## 2026-05-05 — vLLM image pinned to `v0.20.1-cu129-ubuntu2404`

This tag has the linux/arm64 manifest needed for DGX Spark, ships CUDA 12.9 runtime (forward-compatible with the box's CUDA 13.0 driver), and well exceeds the model card's "vLLM 0.14.1+" minimum. Re-evaluate quarterly or when issues surface.

## 2026-05-05 — Replicas over sharded

Two independent vLLM replicas behind HAProxy. Sharded (Ray + NCCL over ConnectX-7) is technically supported by both vLLM and the hardware, but unnecessary at this model size and would lose us redundancy. Revisit if we ever need to serve a model that exceeds ~100 GB of unified memory per box.

## 2026-05-05 — HAProxy on starsky (not a third host)

LB co-located on starsky. Accepted SPOF for simplicity; no third host wanted. Upgrade path to active/passive HAProxy via keepalived when availability requirements demand it.

## 2026-05-05 — Containers, pinned tags

`vllm/vllm-openai` with explicit version tag, never `:latest`. Reproducibility > convenience.

## 2026-05-05 — Model weights at `/srv/models`, not in image

Avoids 50+ GB image rebuilds when iterating, and the cache survives container restarts. Mount read-only into the container.

**Superseded 2026-05-11** by the move to `~/Models/<org>/<name>` (see below).

## 2026-05-11 — Flat `~/Models/<org>/<name>` layout, pre-staged downloads

Replaced `/srv/models` (HF auto-cache layout, `models--<org>--<name>/snapshots/<sha>/` with hardlink-to-`blobs/`) with `/home/jhunt/Models/<org>/<name>/` (flat HuggingFace org/name layout, real files in place).

**Why:**
- Matches the user's existing convention for other model stores on these boxes (e.g. `~/Models/nvidia/Gemma-4-31B-IT-NVFP4`).
- Human-readable layout — `ls ~/Models` shows what's deployed; no parsing of snapshots/blobs/refs.
- Cleaner deletion: `rm -rf ~/Models/<org>/<name>` vs hunting for the right `models--*` dir and its blob backreferences.
- Eliminates an entire class of permission/cache-state foot-guns we hit earlier (`/srv/models/.locks/` owned by root, HF cache layout assuming a specific user).

**Trade-off:** no auto-download from inside the container. vLLM is now invoked with `--model /models/${HF_MODEL_ID}` (local path), and weights must be pre-staged via `src/scripts/model-pull.sh <host>|all <repo>`. This is arguably a feature: no surprise 30 min downloads on container start, explicit step in the runbook.

**Partially superseded 2026-07-13** — the *layout* stuck, the *location* did not. See below.

## 2026-07-13 — `MODEL_DIR` is `/srv/models`, and it is one setting

The 2026-05-11 decision changed two things at once — the **layout** (flat `<org>/<name>`) and the
**location** (`/srv/models` → `~/Models`). Only the layout ever landed. On the live replica the
weights are at **`/srv/models/<org>/<name>`**, flat layout, owned by `jhunt` — and `~/Models` does
not exist at all. The tooling never caught up, and had drifted into three different answers:

- `compose.yml` mounted `${MODEL_DIR:-/srv/models}` — what vLLM actually serves from.
- `bootstrap.sh` created `$HOME/Models` — a directory nothing mounts, so a freshly bootstrapped
  host got **no `/srv/models` at all** and vLLM would fail to load.
- `model-pull.sh` downloaded into `~/Models` and mounted it — so a newly pulled model landed
  somewhere the server never reads. The only reason this was not noticed is that nobody had pulled
  a new model since the weights were staged at `/srv/models` by hand.

**Decision: `/srv/models` is the location, and it is declared once** — `MODEL_DIR` in `cluster.env`
(default in `load-config.sh`), consumed by `bootstrap.sh`, `model-pull.sh`, and the vllm stack.

**Why `/srv` and not `~`:** it is where the weights already are (moving ~100 GB on a serving box to
satisfy a doc is a bad trade), it is not inside a home directory that a user rename or an
`os-service-accounts` change could move, and the SSH user (`gdeceiver`, uid 1001) is deliberately
*not* the owner — `model-pull.sh` downloads as the directory's own uid, and vLLM mounts it `:ro`.

**Kept from 2026-05-11:** the flat `<org>/<name>` layout and no-auto-download, both of which were
the actual point of that decision and are unaffected.

Also lose HF cache's blob dedup across snapshots — irrelevant in practice since we keep one revision per repo.

## 2026-05-05 — Reverted: plain Docker Compose, no Ansible

Replaced an earlier Ansible-based plan after user pushback. At 2 hosts, Ansible was indirection without leverage:

- Compose handles `${VAR}` substitution natively; only HAProxy had truly templated content (the backend list — two static lines).
- `docker compose up -d` is already idempotent.
- The "starsky runs LB, hutch doesn't" split is one extra script invocation, not a templated inventory.
- Cost: extra dependency on the workstation, mental overhead of role/templates indirection, ~10 files of scaffolding to read before answering "what's running on the box?"

Replaced with: plain compose stacks under `src/compose/{vllm,haproxy}/`, `src/scripts/bootstrap.sh` (one-time host prep), and `src/scripts/deploy.sh` (rsync + `docker compose up -d`). Compose files are now the source of truth.

Revisit threshold: if the fleet grows past ~5 hosts, hosts diverge into meaningfully different roles, or we adopt orchestration tooling for unrelated reasons.
