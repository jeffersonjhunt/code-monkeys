# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

vLLM replica cluster across two NVIDIA DGX Spark nodes (Blackwell GB10, ARM64, 128 GB unified memory). Currently serves `QuantTrio/Qwen3.6-35B-A3B-AWQ` (community AWQ of the Qwen3.6-A3B DeltaNet+MoE hybrid) via an OpenAI-compatible HTTP API behind HAProxy. The original target `RedHatAI/Qwen3-Coder-Next-NVFP4` is parked pending an upstream FlashInfer NVFP4-MoE-on-sm_120 fix — see `docs/parking-lot.md`.

## Topology

- `starsky` (`starsky.tworivers`, 192.168.1.120) — vLLM replica + HAProxy front-end
- `hutch`   (`hutch.tworivers`, 192.168.1.163)   — vLLM replica
- ConnectX-7 direct link between the two; currently unused (reserved for future sharded mode)
- HAProxy on starsky is an accepted SPOF for the API endpoint

## Access

- SSH user on both boxes: `jhunt`
- NOPASSWD sudo on both
- `jhunt` is in the `docker` group → no sudo needed for `docker` / `docker compose`
- Test connectivity: `ssh jhunt@starsky hostname` / `ssh jhunt@hutch hostname`

## Orchestration approach

Plain Docker Compose + SSH + small shell scripts. **No Ansible, no Kubernetes.** Each compose file is the actual source of truth — what you read is what runs.

- `src/compose/vllm/` — vLLM stack (deployed identically on both boxes)
- `src/compose/haproxy/` — HAProxy stack (starsky only)
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
