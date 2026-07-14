---
name: spark-build
description: Build the cuda-* primate images (cuda-llama-cpp, cuda-comfy, cuda-vllm) on a cluster node while draining that node from the cluster, so users keep getting served by the remaining replicas. Stops the vLLM container on the target node first (frees the unified memory the build needs) and restarts it after the build finishes.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# spark-build

The spark-class primate images can only build on an NVIDIA-kernel host with a Blackwell GPU — in practice, one of the spark cluster replicas. Building from source while a vLLM container is loaded will exhaust the 128 GB unified memory and OOM the build. This skill handles the cluster-aware orchestration:

1. Drain the target node from the cluster (stop `vllm`)
2. Verify capacity remains before building
3. Sync the working tree to the build host (`rsync` by default, or `git pull` of a named ref)
4. Build the requested spark images on the host (each `make <img>.build` builds the shared `cuda-base` base — `:runtime` + `:devel` — first as a prerequisite; it carries `nvtop` and the codemonkey user, and is cached after the first run)
5. Restart the vLLM container

> **⚠️ The drain/verify steps are stale and currently break the script (as of the June 2026 LB migration).**
> Steps 1–2 and 5 were written for HAProxy: the script polls the HAProxy stats CSV on
> `$LB_STATS_PORT` (8404) to watch a replica go DOWN/UP and to confirm a *second* replica is still
> serving. Two things changed:
> - **The LB is LiteLLM now** (`minerva:8888`), and it exposes **no `:8404` stats UI** at all
>   (`spark/cluster/docs/runbook.md` — "Backend status"). Every stats poll now hits a closed port.
> - **There is only one coding replica** (`REPLICAS="hutch.tworivers"`). There is no "remaining
>   replica" to drain to — stopping vLLM on hutch is a full outage for `qwen3-coder-next` until it
>   restarts, and that is unavoidable if you want to build on it.
>
> Net effect: the "verify another replica is UP" gate sees zero UP replicas and **exits 1 after
> draining** (the EXIT trap does restart vLLM). Until the script is fixed, build with
> **`--skip-drain`** — and stop vLLM yourself first, because the build needs the memory:
>
> ```bash
> ssh gdeceiver@hutch.tworivers 'cd ~/spark-deploy/vllm && docker compose stop'
> ./scripts/spark-build --host hutch.tworivers --image cuda-vllm --skip-drain --no-restart
> ssh gdeceiver@hutch.tworivers 'cd ~/spark-deploy/vllm && docker compose up -d'
> ```
>
> Expect the coding API to be down for the duration of the build. Verify recovery with
> `curl http://hutch.tworivers:8000/health` and `curl http://minerva.tworivers:8888/v1/models`.

## When to Use

- Bumping pins in `primates/{cuda-llama-cpp,cuda-comfy,cuda-vllm}.dockerfile`
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
| `--skip-drain` | off | Don't stop vLLM before building |
| `--no-restart` | off | Don't restart vLLM after building |
| `--force` | off | Allow targeting `LB_HOST` (takes the API down) |
| `--help` | — | Show usage |

## Recovery

If the build is interrupted (Ctrl-C, network drop), an EXIT trap attempts to restart vLLM on the drained host so the cluster recovers. If the trap doesn't fire (kill -9, host crash), restart manually:

```bash
ssh gdeceiver@hutch.tworivers 'cd ~/spark-deploy/vllm && docker compose up -d'
```

The replica serves again ~2 min later, once vLLM has reloaded the model from disk and `/health` passes. LiteLLM has no backend-state machine to wait on — it routes to whatever `config.yaml` maps the model to, so the endpoint recovers the moment vLLM does. Confirm with `curl http://hutch.tworivers:8000/health`.

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
2. **Warn that building takes the coding API down**: there is one replica, so there is nothing to fail over to. Get explicit agreement before draining
3. Because the HAProxy-era drain/verify gate is broken (see the warning at the top), use the `--skip-drain` path with a manual `docker compose stop` / `up -d` around the build
4. Let the script's output stream so the user sees the build progression
5. After a vLLM rebuild, remind the user to test tool-calling and (if relevant) update the Qwen3-Coder-Next-NVFP4 bug memory note
6. If a second replica ever returns, roll the build one replica at a time — never drain both at once
