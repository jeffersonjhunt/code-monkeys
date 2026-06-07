# spark-cluster

vLLM replica cluster across two GPU nodes (designed for NVIDIA DGX Spark — Blackwell GB10, 128 GB UMA — but the orchestration is host-name agnostic and works with any pair of SSH-reachable boxes that meet the requirements below). Serves an OpenAI-compatible HTTP API behind HAProxy. Runs the locally-built `cuda-vllm` image (native sm_89/120/121 cutlass — built from `../../primates/cuda-vllm.dockerfile`) which unblocks both FP8 dense and NVFP4 MoE paths that crash on upstream `vllm/vllm-openai`. See `docs/parking-lot.md` for the resolved-canary write-ups.

## Requirements

Two hosts that:
- Run Ubuntu (or any distro with Docker, `docker compose`, `zstd`, and `host` available)
- Each have an NVIDIA GPU + `nvidia-container-toolkit` (the included `cuda-vllm` image ships native sm_89/120/121; override `TORCH_CUDA_ARCH_LIST` for a slimmer single-target build)
- Are SSH-reachable from your workstation as a single shared user with passwordless sudo and membership in the `docker` group
- Resolve each other's short names via DNS (or `/etc/hosts`)

## Configure your hosts

Cluster scripts read host details from `cluster.env`. The example uses placeholder names `A` and `B`:

```bash
cp cluster.env.example cluster.env
# edit cluster.env — set SSH_USER, REPLICAS, LB_HOST
```

`REPLICAS` is the space-separated list of cluster boxes; `LB_HOST` is the one that fronts the cluster with HAProxy (must be a member of `REPLICAS`). The names you put here must be SSH targets and DNS-resolvable on each box.

Worked example (the maintainer's current cluster): `REPLICAS="starsky hutch"`, `LB_HOST=starsky`.

```
client ──► $LB_HOST:$LB_PORT (HAProxy) ──► <each replica>:$VLLM_PORT (vLLM)
```

Each replica is independent: same compose, same model, full copy of weights at `~/Models/<org>/<name>` (flat HF org/name layout, pre-staged via `src/scripts/model-pull.sh`). Why replicas (not sharded)? See `docs/architecture.md`.

## Deploy

One-time per box (run for each entry in `$REPLICAS`):

```bash
. cluster.env
for h in $REPLICAS; do
  ssh "$SSH_USER@$h" "CLUSTER_PEERS='$REPLICAS' bash -s" < src/scripts/bootstrap.sh
done
```

Set up your HF token:

```bash
cp src/compose/vllm/.env.example src/compose/vllm/.env
# edit .env to add HUGGING_FACE_HUB_TOKEN
```

Deploy:

```bash
./src/scripts/deploy.sh all                    # vllm on every replica, haproxy on $LB_HOST
# or one piece at a time
./src/scripts/deploy.sh <host> vllm haproxy
./src/scripts/deploy.sh <host> vllm
```

`deploy.sh` rsyncs the relevant `src/compose/<stack>/` directory to `~/spark-deploy/<stack>/` on the host and runs `docker compose up -d`. For the haproxy stack it renders `haproxy.cfg` from `haproxy.cfg.template` with one `server` line per replica before syncing.

When the `cuda-vllm` image is rebuilt in `../../primates/`, ship it from the box that built it to the others:

```bash
./src/scripts/ship-image.sh <src-host> <dst-host> cuda-vllm:latest   # one dest
./src/scripts/ship-image.sh <src-host> all        cuda-vllm:latest   # every other replica
```

It streams `docker save | zstd -3 | ssh | docker load` end-to-end (~3.5 min for 6.7 GB compressed over LAN). Then `deploy.sh` to pick up the new image.

## Status

Both replicas healthy on `RedHatAI/Qwen3-Coder-Next-NVFP4` (unblocked by `vllm-spark` 2026-05-08). Tool calling works in `auto` mode via the `qwen3_coder` parser (known caveat: occasional malformed JSON in tool-call arguments — see memory note). HAProxy round-robins; failover drill validated. Cluster peak ~752 tok/s aggregate at c=32 (measured on the prior AWQ canary; NVFP4 numbers in `CHANGELOG.md`). Current phase and history live in `TASKS.md` and `CHANGELOG.md`.

## Layout

```
spark-cluster/
├── CLAUDE.md             guidance for Claude Code sessions
├── README.md             this file
├── cluster.env.example   inventory template (copy to cluster.env)
├── TASKS.md              phased work tracker
├── CHANGELOG.md          dated history
├── docs/                 architecture, decisions, inventory, runbook
└── src/
    ├── compose/
    │   ├── vllm/         vLLM stack (every replica)
    │   └── haproxy/      HAProxy stack ($LB_HOST only; haproxy.cfg generated from template)
    └── scripts/
        ├── lib/load-config.sh  sourced by all scripts to read cluster.env
        ├── preflight.sh        read-only host discovery
        ├── bootstrap.sh        one-time host prep
        ├── deploy.sh           sync + docker compose up -d
        ├── ship-image.sh       stream a docker image src->dst via save | zstd | ssh | load
        ├── smoke-test.sh       /health + /v1/models + /v1/chat/completions probe
        ├── bench.py            concurrent-client throughput probe
        └── bench-sweep.sh      c=1..32 sweep wrapper
```

## Operating

Operating procedures will land in `docs/runbook.md` as each phase ships.
