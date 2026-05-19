# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

vLLM replica cluster across two NVIDIA DGX Spark nodes (Blackwell GB10, ARM64, 128 GB unified memory). Currently serves `QuantTrio/Qwen3.6-35B-A3B-AWQ` (community AWQ of the Qwen3.6-A3B DeltaNet+MoE hybrid) via an OpenAI-compatible HTTP API behind HAProxy. The original target `RedHatAI/Qwen3-Coder-Next-NVFP4` is parked pending an upstream FlashInfer NVFP4-MoE-on-sm_120 fix — see `docs/parking-lot.md`.

## Topology

The cluster is configured by `cluster.env` at the repo root (gitignored — see `cluster.env.example`). It defines:

- `REPLICAS` — space-separated list of vLLM replica hosts
- `LB_HOST` — which replica fronts the cluster with HAProxy (must be in `REPLICAS`)
- `SSH_USER` — shared user account on every box
- `VLLM_PORT`, `LB_PORT`, `LB_STATS_PORT` — defaults 8000 / 8080 / 8404

Maintainer's current cluster (worked example): `REPLICAS="starsky hutch"`, `LB_HOST=starsky`, `SSH_USER=jhunt`. starsky and hutch are NVIDIA DGX Spark boxes (Blackwell GB10, ARM64, 128 GB UMA) connected by a ConnectX-7 link (currently unused; reserved for future sharded mode). HAProxy on `$LB_HOST` is an accepted SPOF for the API endpoint.

When Claude sessions need to refer to hosts, read `cluster.env` rather than assuming names — the project is meant to be portable.

## Access

- SSH user on every box: `$SSH_USER` (from `cluster.env`)
- NOPASSWD sudo on every box
- `$SSH_USER` must be in the `docker` group → no sudo needed for `docker` / `docker compose`
- Test connectivity: `for h in $REPLICAS; do ssh "$SSH_USER@$h" hostname; done`

## Orchestration approach

Plain Docker Compose + SSH + small shell scripts. **No Ansible, no Kubernetes.** Each compose file is the actual source of truth — what you read is what runs. The one exception: `haproxy.cfg` is generated from `haproxy.cfg.template` at deploy time so the backend `server` list tracks `$REPLICAS` automatically. Edit the template, not the generated file.

- `cluster.env` — inventory (hosts, roles, ports); sourced by every script via `src/scripts/lib/load-config.sh`
- `src/compose/vllm/` — vLLM stack (deployed identically on every replica)
- `src/compose/haproxy/` — HAProxy stack (`$LB_HOST` only)
- `src/scripts/bootstrap.sh` — one-time host prep (`~/Models`; DNS handles resolution)
- `src/scripts/model-pull.sh` — fetch a HF repo into `~/Models/<org>/<name>` on one or all hosts
- `src/scripts/deploy.sh` — `rsync` a compose stack to a host and `docker compose up -d`

If the fleet ever grows past ~5 boxes or roles diverge meaningfully, revisit (Ansible/Salt/k8s would earn their keep then; today they don't).

## Repo layout

- `src/compose/{vllm,haproxy}/` — compose stacks, each with its own `compose.yml`, supporting files, and README
- `src/scripts/` — `preflight.sh` (read-only discovery), `bootstrap.sh` (one-time), `deploy.sh` (sync + up)
- `docs/` — architecture, decisions, inventory, runbook, parking-lot
- `docs/parking-lot.md` — deferred items with retry triggers (notably: NIM serving the original Qwen3-Coder-Next-NVFP4)
- `TASKS.md` — phased work tracker; check this first to see current state
- `CHANGELOG.md` — append a dated entry whenever a phase completes or anything material changes

## Conventions

- All scripts must be idempotent and safe to re-run
- Container image tags are pinned (no `:latest`)
- Model weights live at `~/Models/<org>/<name>` (flat HF org/name layout, not the `models--<org>--<name>/snapshots/<sha>/` HF cache layout) on each box; never bake them into images. Pre-stage via `model-pull.sh` — vLLM is launched with `--model /models/${HF_MODEL_ID}` and does not auto-download.
- `.env` files (real, with secrets) are gitignored; commit only `.env.example`
- Update `TASKS.md` (check off items) and `CHANGELOG.md` (append dated entry) as part of any material change — they are the project's working memory
- Discovery / inspection scripts must be read-only on the remote hosts; provisioning is via `bootstrap.sh` / `deploy.sh` only
