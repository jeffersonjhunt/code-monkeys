# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

vLLM replica cluster on NVIDIA DGX Spark nodes (Blackwell GB10, ARM64, 128 GB unified memory). Currently serves `RedHatAI/Qwen3-Coder-Next-NVFP4` (Qwen3-Coder-Next 80B-A3B MoE, NVFP4 quant) via an OpenAI-compatible HTTP API behind a **LiteLLM** model-aware router — unblocked 2026-05-08 by the locally-built `cuda-vllm` image (native sm_89/120/121 cutlass; formerly `vllm-spark`). The community AWQ `QuantTrio/Qwen3.6-35B-A3B-AWQ` remains a validated fallback canary. See `docs/parking-lot.md` for the resolved write-ups.

## Topology

The cluster is configured by `cluster.env` at the repo root (gitignored — see `cluster.env.example`). It defines:

- `REPLICAS` — space-separated list of vLLM replica hosts
- `LB_HOST` — the host that fronts the cluster with the LiteLLM router. May be a standalone control-plane host (it need not be in `REPLICAS`)
- `SSH_USER` — shared user account on every box
- `VLLM_PORT`, `LB_PORT`, `LB_STATS_PORT` — 8000 / 8888 / 8404 in the maintainer's `cluster.env` (`LB_STATS_PORT` is vestigial: it belongs to the retired HAProxy stack; LiteLLM exposes no stats port)

Maintainer's current cluster (worked example): `REPLICAS="hutch.tworivers"`, `LB_HOST=minerva.tworivers`, `SSH_USER=gdeceiver`. hutch is an NVIDIA DGX Spark box (Blackwell GB10, ARM64, 128 GB UMA) serving `qwen3-coder-next`; minerva is a standalone control-plane host (not a GPU replica) that fronts it with **LiteLLM on `LB_PORT=8888`**. starsky — a second GB10 Spark that was previously the LB *and* a replica — was repurposed for g.deceiver reasoning on 2026-06-10 and is no longer in this cluster's replica pool (LiteLLM still *routes* the `reasoning` and `caption` models to it; it is just not a coding replica). The router on `$LB_HOST` is an accepted SPOF for the API endpoint, and with one coding replica there is currently **no failover**.

**The LB is LiteLLM, not HAProxy** (cut over 2026-06-28 — see `CHANGELOG.md` and `src/scripts/deploy.sh`). HAProxy round-robins across replicas of *one* model and ignores the request body; LiteLLM routes on the OpenAI `model` field, which is what lets a single endpoint front boxes serving different models. The `haproxy` stack is retained on disk as a fallback but is never deployed by `deploy.sh all`. `docs/runbook.md` is the current operational reference.

When Claude sessions need to refer to hosts, read `cluster.env` rather than assuming names — the project is meant to be portable.

## Access

- SSH user on every box: `$SSH_USER` (from `cluster.env`)
- NOPASSWD sudo on every box
- `$SSH_USER` must be in the `docker` group → no sudo needed for `docker` / `docker compose`
- Test connectivity: `for h in $REPLICAS; do ssh "$SSH_USER@$h" hostname; done`

## Orchestration approach

Plain Docker Compose + SSH + small shell scripts. **No Ansible, no Kubernetes.** Each compose file is the actual source of truth — what you read is what runs. The LiteLLM `config.yaml` is likewise hand-edited and shipped as-is. The one exception: the fallback stack's `haproxy.cfg` is generated from `haproxy.cfg.template` at deploy time so the backend `server` list tracks `$REPLICAS` automatically. Edit the template, not the generated file.

- `cluster.env` — inventory (hosts, roles, ports); sourced by every script via `src/scripts/lib/load-config.sh`
- `src/compose/vllm/` — vLLM stack (deployed identically on every replica)
- `src/compose/litellm/` — LiteLLM model-aware router (`$LB_HOST` only) — the current LB. `config.yaml` is the `model -> backend` map and is the file you edit
- `src/compose/haproxy/` — retired round-robin HAProxy stack, kept as a fallback (`$LB_HOST` only; deploy it explicitly, never via `deploy.sh all`)
- `src/scripts/bootstrap.sh` — one-time host prep (creates `$MODEL_DIR`, default `/srv/models`; DNS handles resolution)
- `src/scripts/model-pull.sh` — fetch a HF repo into `$MODEL_DIR/<org>/<name>` on one or all hosts
- `src/scripts/deploy.sh` — tar-stream a compose stack to a host and `docker compose up -d` (no `rsync` dependency); for `vllm` it also ECR-logs-in, SOPS-decrypts the stack `.env` from `hemlighet` on the target, and `docker compose pull`s

If the fleet ever grows past ~5 boxes or roles diverge meaningfully, revisit (Ansible/Salt/k8s would earn their keep then; today they don't).

## Repo layout

- `src/compose/{vllm,litellm,haproxy}/` — compose stacks, each with its own `compose.yml`, supporting files, and README (`litellm` is the live LB; `haproxy` is the retired fallback)
- `src/scripts/` — `preflight.sh` (read-only discovery), `bootstrap.sh` (one-time), `deploy.sh` (sync + up)
- `docs/` — architecture, decisions, inventory, runbook, parking-lot
- `docs/parking-lot.md` — deferred items with retry triggers (notably: NIM serving the original Qwen3-Coder-Next-NVFP4)
- `TASKS.md` — phased work tracker; check this first to see current state
- `CHANGELOG.md` — append a dated entry whenever a phase completes or anything material changes

## Conventions

- All scripts must be idempotent and safe to re-run
- Container image tags are pinned (no `:latest`)
- Model weights live at `/srv/models/<org>/<name>` (flat HF org/name layout, not the `models--<org>--<name>/snapshots/<sha>/` HF cache layout) on each box; never bake them into images. Pre-stage via `model-pull.sh` — vLLM is launched with `--model /models/${HF_MODEL_ID}` and does not auto-download.
- `.env` files (real, with secrets) are gitignored; commit only `.env.example`
- Update `TASKS.md` (check off items) and `CHANGELOG.md` (append dated entry) as part of any material change — they are the project's working memory
- Discovery / inspection scripts must be read-only on the remote hosts; provisioning is via `bootstrap.sh` / `deploy.sh` only
