---
name: spark-build
description: Build the cuda-* primate images (cuda-llama-cpp, cuda-comfy, cuda-vllm — the shared base for g.deceiver's six vLLM services) on a Blackwell GB10, freeing that box's unified memory first by stopping whatever it runs, then restarting it. NOTE the standalone coding cluster (qwen3-coder-next) was RETIRED 2026-09-05, so a "drain" is no longer a coding outage — it's a g.deceiver-service outage (hutch = memory stack; starsky = the live 27B brain, never build there mid-stream). Checks memory BEFORE stopping anything; --allow-outage / --skip-drain control the trade.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# spark-build

The spark-class primate images can only build on an NVIDIA-kernel host with a Blackwell GPU — in practice, one of the spark cluster replicas. Building from source while a vLLM container is loaded will exhaust the 128 GB unified memory and OOM the build. This skill handles the cluster-aware orchestration:

1. **Check capacity first** — verify a *peer* replica is still serving (its own vLLM `/health`), before anything is stopped
2. Drain the target node (stop `vllm`, freeing the unified memory) and confirm it actually stopped
3. Sync the working tree to the build host (`rsync` by default, or `git pull` of a named ref)
4. Build the requested spark images on the host (each `make <img>.build` builds the shared `cuda-base` base — `:runtime` + `:devel` — first as a prerequisite; it carries `nvtop` and the codemonkey user, and is cached after the first run)
5. Restart the vLLM container and wait for it to serve again (~2 min cold weight load)

## When to Use

- Bumping pins in `primates/{cuda-llama-cpp,cuda-comfy,cuda-vllm}.dockerfile`
- Rebuilding any spark image after a code change
- Rolling a vLLM version through the cluster one replica at a time

Do NOT use for the standard primates (claude / opencode / kiro / etc.) — those build on the workstation (Mjolnir), don't touch the cluster, and the chain depends on `codemonkey:latest`.

## Prerequisites

- Passwordless SSH to the build host as `$SSH_USER` from `spark/cluster/cluster.env`
- `$SSH_USER` is in the `docker` group on the host (so `make` works without sudo). **Root is not needed** — the build is a `docker build`. The service account (`gdeceiver`) deliberately has no sudo.
- `spark/cluster/cluster.env` exists locally (gitignored — copy `cluster.env.example` and fill in)

## Topology Assumptions

The skill reads `spark/cluster/cluster.env`:
- `REPLICAS` — space-separated cluster hosts (currently one: `hutch.tworivers`)
- `LB_HOST` — the host running the LB. Today that is `minerva.tworivers`, a standalone control-plane box running **LiteLLM** — not a replica, and not something you ever build on
- `SSH_USER`, `VLLM_PORT`, `LB_PORT`, `LB_STATS_PORT` (the last is vestigial — it was HAProxy's stats port; LiteLLM has none)

Default build target is the first replica that is **not** `LB_HOST`. With `LB_HOST` off the replica list, that is simply the first entry of `$REPLICAS` (hutch). Override with `--host`.

## DNS / Hostname Notes

The cluster scripts use bare hostnames (e.g. `hutch`) which resolve on the workstation and on each cluster box. When run from **inside a primate container**, bare names may not resolve — pass the FQDN (e.g. `--host hutch.tworivers`).

When `--host` is an FQDN and `LB_HOST` from `cluster.env` is bare, the skill auto-suffixes the LB SSH target with the same domain (so `--host hutch.tworivers` + `LB_HOST=minerva` → LB target `minerva.tworivers`). Override explicitly with `--lb-host`. The current `cluster.env` already uses FQDNs, so this is a no-op there.

## Usage

```bash
# Build all three spark images on the default non-LB replica (rsync working tree)
./scripts/spark-build

# Build just cuda-vllm on a specific host
./scripts/spark-build --host hutch.tworivers --image cuda-vllm

# Build multiple images
./scripts/spark-build --image cuda-llama-cpp --image cuda-vllm

# Build a specific committed ref instead of the working tree
./scripts/spark-build --sync git --ref master

# Preview without doing anything (network-free)
./scripts/spark-build --dry-run

# Already drained the host manually (e.g. mid-incident)
./scripts/spark-build --skip-drain --no-restart
```

## Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--host HOST` | first non-`LB_HOST` in `$REPLICAS` | SSH target (use FQDN if bare name doesn't resolve) |
| `--lb-host HOST` | `LB_HOST` from cluster.env (auto-suffixed with `--host`'s domain when `--host` is an FQDN) | Explicit SSH target for the LB host |
| `--image NAME` | `all` (all three spark images) | Repeatable; image to build |
| `--sync rsync\|git` | `rsync` | How to get code onto the host |
| `--ref REF` | current branch | Git ref for `--sync git` |
| `--dry-run` | off | Print every step without executing |
| `--skip-drain` | off | Don't stop vLLM before building (skips the capacity gate; the build then competes with the server for unified memory) |
| `--allow-outage` | off | Proceed when draining leaves **no** serving replica (single-replica cluster). Without it the script refuses rather than silently taking the model offline |
| `--no-restart` | off | Don't restart vLLM after building |
| `--force` | off | Allow targeting `LB_HOST` (takes the API down) |
| `--help` | — | Show usage |

## Recovery

If the build is interrupted (Ctrl-C, network drop), an EXIT trap attempts to restart vLLM on the drained host so the cluster recovers. If the trap doesn't fire (kill -9, host crash), restart manually:

```bash
ssh gdeceiver@hutch.tworivers 'cd ~/spark-deploy/vllm && docker compose up -d'
```

The replica serves again ~2 min after restart (model cold-load); the script polls its `/health` and tells you when it's back.

## ⚠️ The coding cluster is RETIRED (2026-09-05) — this builds a shared base, not a serving replica

The old premise — hutch is a `qwen3-coder-next` coding replica you drain so peers keep serving — is
**gone**. The standalone coder (`RedHatAI/Qwen3-Coder-Next-NVFP4`) was retired 2026-09-05; coding
folded onto g.deceiver's `Qwen3.8-27B-FP8` on starsky (route renamed `qwen3-coder-next` → `code`; see
the g.deceiver `model-consolidation-27b` note). `REPLICAS="hutch.tworivers"` no longer names a
*coding* replica: **hutch now runs g.deceiver's memory stack** (embeddings + reranker), and **starsky
runs the live co-host reasoning brain** (the 27B).

This skill still matters — **`cuda-vllm` is the shared base for all six g.deceiver vLLM services**, so
it's still rebuilt here on a Blackwell (sm_121) GB10. But a "drain" is no longer a *coding* outage;
it's whatever **g.deceiver service** shares the target GB10's UMA:

- **Build on hutch** → contends with / stops the **memory stack** (embeddings, reranker). Retrieval
  degrades during the build; no coding impact — lower stakes.
- **Build on starsky** → contends with the **live co-host brain** (reason + code + caption + vision).
  **NEVER build on starsky while a stream is live** — it takes Gay's reasoning down mid-stream.
- **`--skip-drain`** — build alongside the running g.deceiver service (no downtime, but competes for
  the 128 GB UMA — slower, can OOM). Fine next to hutch's memory stack; risky next to starsky's 27B.

The `--allow-outage` / capacity-gate machinery still runs, but "peer replica serving" maps onto
nothing now — read the gate as "is it safe to starve this box's g.deceiver service right now," which
for starsky means **not streaming**.

## What This Skill Doesn't Do

- It does not rebuild standard primates (`make all` on Mjolnir is the path for those)
- It does not roll the build across the *whole* cluster — by design, only one replica at a time. Run it once per replica if you want fleet-wide updates
- It does not run smoke tests against the new image — verify manually via the cluster runbook (`spark/cluster/docs/runbook.md`)

## Dependencies

- `bash` 4+, `ssh`, `rsync` (workstation side)
- `docker`, `docker compose`, `make`, `git`, `curl` (build host side)
- A populated `spark/cluster/cluster.env`

## Agent Instructions

When the user asks to rebuild a spark-class image or roll a vLLM update through the cluster:

1. Confirm which images and which host they want (default to the non-LB replica — today, hutch)
2. **Warn which g.deceiver service the build starves** (the coding cluster is retired — see the ⚠️ section): building on **hutch** stops the memory stack (retrieval degrades — low stakes); building on **starsky** stops the live 27B brain — **confirm no stream is live first**, never take Gay's reasoning down mid-stream. The script still refuses to stop a box's service without `--allow-outage` and refuses *before* stopping anything. Get explicit agreement, then choose:
   - `--allow-outage` — accept the service downtime, fastest build
   - `--skip-drain` — no downtime, but the build competes for unified memory and can OOM (fine next to hutch's memory stack, risky next to starsky's 27B)
3. Let the script's output stream so the user sees the memory check → stop → build → restore progression
4. After a `cuda-vllm` rebuild, the six g.deceiver vLLM services (reasoning, embeddings, reranker, guard, …) that layer on it can be rebuilt/redeployed via the g.deceiver config-layer pipeline; test tool-calling on the `code`/`reasoning` routes through minerva:8888
5. Never build on both GB10s at once — starsky's is the live co-host brain
