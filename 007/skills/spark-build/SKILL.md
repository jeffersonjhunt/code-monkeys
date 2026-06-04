---
name: spark-build
description: Build spark-class primate images (llama-cpp-spark, comfy-ui-spark, vllm-spark) on a cluster node while draining that node from the cluster, so users keep getting served by the remaining replicas. Stops the vLLM container on the target node first (frees the unified memory the build needs) and restarts it after the build finishes.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# spark-build

The spark-class primate images can only build on an NVIDIA-kernel host with a Blackwell GPU — in practice, one of the spark cluster replicas. Building from source while a vLLM container is loaded will exhaust the 128 GB unified memory and OOM the build. This skill handles the cluster-aware orchestration:

1. Drain the target node from the cluster (stop `vllm` so HAProxy marks it DOWN)
2. Verify another replica is still UP so the API stays available
3. Sync the working tree to the build host (`rsync` by default, or `git pull` of a named ref)
4. Build the requested spark images on the host (each `make <img>.build` builds the shared `cuda-base` base — `:runtime` + `:devel` — first as a prerequisite; it carries `nvtop` and the codemonkey user, and is cached after the first run)
5. Restart the vLLM container so HAProxy marks the node back UP

## When to Use

- Bumping pins in `primates/{llama-cpp-spark,comfy-ui-spark,vllm-spark}.dockerfile`
- Rebuilding any spark image after a code change
- Rolling a vLLM version through the cluster one replica at a time

Do NOT use for the standard primates (claude / opencode / kiro / etc.) — those build on the workstation (Mjolnir), don't touch the cluster, and the chain depends on `codemonkey:latest`.

## Prerequisites

- Passwordless SSH to the build host as `$SSH_USER` from `spark/cluster/cluster.env`
- `$SSH_USER` has NOPASSWD sudo on the host
- `$SSH_USER` is in the `docker` group on the host (so `make` works without sudo)
- `spark/cluster/cluster.env` exists locally (gitignored — copy `cluster.env.example` and fill in)

## Topology Assumptions

The skill reads `spark/cluster/cluster.env`:
- `REPLICAS` — space-separated cluster hosts
- `LB_HOST` — replica running HAProxy
- `SSH_USER`, `VLLM_PORT`, `LB_PORT`, `LB_STATS_PORT`

Default build target is the first replica that is **not** `LB_HOST` (so draining it doesn't take the API down). Override with `--host`.

## DNS / Hostname Notes

The cluster scripts use bare hostnames (e.g. `hutch`) which resolve on the workstation and on each cluster box. When run from **inside a primate container**, bare names may not resolve — pass the FQDN (e.g. `--host hutch.tworivers`).

When `--host` is an FQDN and `LB_HOST` from `cluster.env` is bare, the skill auto-suffixes the LB SSH target with the same domain (so `--host hutch.tworivers` + `LB_HOST=starsky` → LB target `starsky.tworivers`). Override explicitly with `--lb-host`.

## Usage

```bash
# Build all three spark images on the default non-LB replica (rsync working tree)
./scripts/spark-build

# Build just vllm-spark on a specific host
./scripts/spark-build --host hutch.tworivers --image vllm-spark

# Build multiple images
./scripts/spark-build --image llama-cpp-spark --image vllm-spark

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
| `--skip-drain` | off | Don't stop vLLM before building |
| `--no-restart` | off | Don't restart vLLM after building |
| `--force` | off | Allow targeting `LB_HOST` (takes the API down) |
| `--help` | — | Show usage |

## Recovery

If the build is interrupted (Ctrl-C, network drop), an EXIT trap attempts to restart vLLM on the drained host so the cluster recovers. If the trap doesn't fire (kill -9, host crash), restart manually:

```bash
ssh jhunt@hutch.tworivers 'cd ~/spark-deploy/vllm && docker compose up -d'
```

HAProxy will mark the replica UP again ~2 min after vLLM's `/health` passes (model cold-load time).

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

1. Confirm which images and which host they want (default to the non-LB replica)
2. Run the script — let its output stream so the user sees the drain/build/restore progression
3. After a vLLM rebuild, remind the user to test tool-calling and (if relevant) update the Qwen3-Coder-Next-NVFP4 bug memory note
4. If they need to roll the new image across all replicas, run the skill once per replica sequentially — never drain both at once
