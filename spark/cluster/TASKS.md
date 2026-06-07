# Tasks

Phased plan for bringing up the vLLM replica cluster. Check off items as they ship; cross-reference with `CHANGELOG.md`.

## Phase 1 — Discovery (read-only)

- [x] Verify SSH to starsky and hutch as `jhunt`
- [x] Run `src/scripts/preflight.sh` on starsky, save output to `docs/inventory-starsky.md`
- [x] Run `src/scripts/preflight.sh` on hutch, save output to `docs/inventory-hutch.md`
- [x] Distilled findings → `docs/inventory-summary.md`
- [x] Verify model param count (80B MoE, 3B active; ~40 GB NVFP4 weights — fits 128 GB unified)
- [x] Pin vLLM container tag (`vllm/vllm-openai:v0.20.1-cu129-ubuntu2404`)

## Phase 2 — Repo scaffolding

- [x] Compose stack for vLLM under `src/compose/vllm/`
- [x] Compose stack for HAProxy under `src/compose/haproxy/`
- [x] `src/scripts/bootstrap.sh` (one-time host prep)
- [x] `src/scripts/deploy.sh` (rsync + docker compose up -d)
- [x] `.env.example` for vLLM; `.gitignore` for real `.env`
- [x] (Reverted earlier Ansible scaffolding — see CHANGELOG and `docs/decisions.md`)

## Phase 3 — Base provisioning

Phase 1 confirmed driver, CUDA, Docker, and nvidia-container-toolkit are already in place — no install work needed. This phase is just `bootstrap.sh` on each box.

- [x] Run `bootstrap.sh` on starsky (`/srv/models` created)
- [x] Run `bootstrap.sh` on hutch (same)
- [x] Cross-resolution + connectivity verified via DNS (starsky↔hutch ping <2ms)
- [x] Reverted earlier `/etc/hosts` writes — DNS already resolves both names; managed block removed
- [ ] Populate `src/compose/vllm/.env` with `HUGGING_FACE_HUB_TOKEN` (carries into Phase 5)

## Phase 4 — Model weights

vLLM downloads the model on first start using `HUGGING_FACE_HUB_TOKEN` from `.env`, caching to `/srv/models`. No separate pre-pull needed unless we want to parallelize the first-start time.

- [ ] (Optional) Add `src/scripts/pull-model.sh` for parallel pre-pull on both boxes if first-start latency is a problem

## Track A — NIM (parked, see `docs/parking-lot.md`)

Parked. Two-round investigation showed: (a) `llm-nim:latest` was the wrong image, (b) `model-free-nim:2.0.3` is right but `Qwen3-Coder-Next-NVFP4` triggers an upstream cutlass sm_120 grouped-GEMM bug (the kernels are present but every TRT-LLM autotuner tactic fails at runtime). Same root-cause class as stock vLLM. Retry triggers + how-to-retry steps are in `docs/parking-lot.md`. NIM compose stack removed 2026-05-12 after `vllm-spark` resolved the NVFP4 path; reconstruct from `git show 4cf2a3a:src/compose/nim/...` if a retry is ever needed.

## Phase 5 — vLLM bring-up

Track D (validation with known-good model). Long-term target Qwen3-Coder-Next-NVFP4 still blocked by upstream vLLM bugs (#41477, #41564); NIM LLM not viable today (see Track A above).

- [x] `deploy.sh` debugged (rsync → tar streaming, exit-code propagation, `--force-recreate`)
- [x] `src/scripts/smoke-test.sh` ready (auto-discovers served model id)
- [x] Switched to `Qwen/Qwen2.5-Coder-32B-Instruct` for stack validation; tool-call args temporarily disabled
- [x] Redeployed starsky + hutch; weights downloaded; model loaded
- [x] Both `/health` returning 200 (watcher fired at 18:04:30 UTC)
- [x] Smoke test starsky:8000 direct PASS
- [x] Smoke test hutch:8000 direct PASS
- [x] Re-enable tool calling (`--enable-auto-tool-choice --tool-call-parser hermes`); verified `tool_choice: "required"` works reliably; `auto` has a model-quirk caveat (see `docs/runbook.md` §Tool calling)

## Phase 6 — HAProxy

- [x] `deploy.sh starsky haproxy`
- [x] Bind issue (port 80 needs CAP_NET_BIND_SERVICE) → switched to non-privileged `:8080`
- [x] Both backends UP in `:8404/stats`
- [x] Smoke test through `starsky:8080` PASS; 6 round-robin requests served
- [x] Failover drill: stopped hutch's vllm, HAProxy marked it DOWN within 30 s, 4 requests served via starsky alone, restored on restart

## Phase 7 — Persistence

- [x] Log rotation added to both compose stacks (vLLM 3×100M, HAProxy 3×20M)
- [x] vLLM in-container healthcheck switched from `wget` (not in image) to `python3` urllib — applies on next vLLM redeploy
- [x] Operate / teardown / failover / model-swap procedures in `docs/runbook.md`
- [ ] Confirm container `restart: unless-stopped` survives a reboot on each box (manual, when convenient)

## Phase 8 — Verification

- [x] Throughput sanity check (`src/scripts/bench.py`, c=1..32 sweep through HAProxy: 38 → 788 tok/s aggregate)
- [x] Failover drill end-to-end through HAProxy (Phase 6 — stop hutch, requests served via starsky alone, restored on restart)
- [x] GPU memory headroom under load (model ~22.23 GiB at gpu_memory_utilization=0.50, plenty of UMA headroom)

## Phase 9 — Production model (Qwen3.6-35B-A3B-AWQ)

- [x] Switched served model from `Qwen/Qwen2.5-Coder-32B-Instruct` to `QuantTrio/Qwen3.6-35B-A3B-AWQ` (community AWQ of Qwen3.6-35B-A3B; DeltaNet hybrid + MoE, 3B active)
- [x] Added Qwen3-recommended env vars to `.env`: `VLLM_USE_DEEP_GEMM=0`, `VLLM_USE_FLASHINFER_MOE_FP16=1`, `VLLM_USE_FLASHINFER_SAMPLER=0`
- [x] Removed `--swap-space` from compose.yml — deprecated/removed in vLLM 0.20.x
- [x] Tool-call parser switched to `qwen3_coder`, reasoning parser to `qwen3`; auto-mode tool calling now reliable
- [x] Cross-box weights transfer via `tar | ssh tar` (24 GB starsky → hutch in 14m23s)
- [x] Both replicas healthy and smoke-test PASS
- [x] HAProxy round-robin verified; both backends UP
- [x] Bench shows ~10× single-stream tok/s and ~14× cluster aggregate vs Qwen2.5-Coder baseline

## Phase 10 — Inventory-driven hosts (2026-05-19)

- [x] `cluster.env` / `cluster.env.example` at project root; gitignored real file
- [x] `src/scripts/lib/load-config.sh` shared loader; validates required vars; LB_HOST ∈ REPLICAS
- [x] All seven scripts source the inventory (`deploy.sh`, `ship-image.sh`, `model-pull.sh`, `bootstrap.sh`, `smoke-test.sh`, `bench-sweep.sh`, `bench.py`)
- [x] `haproxy.cfg` → `haproxy.cfg.template` with `# __REPLICAS__` marker; `deploy.sh` renders before sync; generated cfg gitignored
- [x] Living docs updated (README, CLAUDE.md, architecture.md, runbook.md); historical docs preserved
- [x] Validated against live cluster: `deploy.sh all` clean, all three containers recovered to healthy, smoke-test PASS through HAProxy + each replica direct

## Phase 11 — Primate rename + cross-GPU unification (2026-06-07)

- [x] GPU primates renamed `vllm-spark`→`cuda-vllm`, `comfy-ui-spark`→`cuda-comfy`, `llama-cpp-spark`→`cuda-llama-cpp`; `cuda-vllm` arch broadened to native sm_89/120/121 with `MAX_JOBS`/`NVCC_THREADS` build-args (code-monkeys `primates/`)
- [x] Cluster `compose.yml` default flipped to `${VLLM_IMAGE:-cuda-vllm:latest}`; `.env(.example)`, READMEs, `CLAUDE.md`, `ship-image.sh`, `model-pull.sh` updated
- [x] Rolled both Sparks to `cuda-vllm:latest` one at a time (retag of the identical sm_121 artifact → compose flip → recreate); cluster never lost a backend; old `*-spark` tags dropped
- [x] Smoke-test PASS through HAProxy (`starsky:8080`) + both replicas direct (`:8000`) on `qwen3-coder-next`
- [x] Cross-GPU proof: fresh `cuda-vllm` built on x86 4090 `ren` (job-tuned), shipped to `stimpy`, smoke-tested on both — builds/serves on sm_89 as well as sm_121
