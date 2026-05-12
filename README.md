# spark-cluster

vLLM replica cluster on two NVIDIA DGX Spark nodes (Blackwell GB10, 128 GB UMA each) serving `QuantTrio/Qwen3.6-35B-A3B-AWQ` behind HAProxy. Runs the locally-built `vllm-spark` image (sm_121-native cutlass — built from `~/workspace/code-monkeys/primates/vllm-spark.dockerfile`) which unblocks both FP8 dense and NVFP4 MoE paths that crash on upstream `vllm/vllm-openai`. See `docs/parking-lot.md` for the resolved-canary write-ups.

## Hardware

| Host    | FQDN              | LAN IP         | Role                     |
|---------|-------------------|----------------|--------------------------|
| starsky | starsky.tworivers | 192.168.1.120  | vLLM replica + HAProxy   |
| hutch   | hutch.tworivers   | 192.168.1.163  | vLLM replica             |

ConnectX-7 direct link between the two nodes is reserved for future sharded-mode use.

## Architecture

```
client ──► starsky:8080 (HAProxy) ──► starsky:8000 (vLLM replica A)
                                  └─► hutch:8000   (vLLM replica B)
```

Each replica is independent: same compose, same model, full copy of weights at `~/Models/<org>/<name>` (flat HF org/name layout, pre-staged via `src/scripts/model-pull.sh`). Why replicas (not sharded)? See `docs/architecture.md`.

## Deploy

One-time per box:

```bash
ssh jhunt@starsky 'bash -s' < src/scripts/bootstrap.sh
ssh jhunt@hutch   'bash -s' < src/scripts/bootstrap.sh
```

Set up your HF token:

```bash
cp src/compose/vllm/.env.example src/compose/vllm/.env
# edit .env to add HUGGING_FACE_HUB_TOKEN
```

Deploy:

```bash
./src/scripts/deploy.sh all                    # vllm both, haproxy starsky
# or one piece at a time
./src/scripts/deploy.sh starsky vllm haproxy
./src/scripts/deploy.sh hutch   vllm
```

`deploy.sh` rsyncs the relevant `src/compose/<stack>/` directory to `/home/jhunt/spark-deploy/<stack>/` on the host and runs `docker compose up -d`.

When the `vllm-spark` image is rebuilt in `~/workspace/code-monkeys/primates/`, ship it from the box that built it to the others:

```bash
./src/scripts/ship-image.sh starsky hutch vllm-spark:latest   # one dest
./src/scripts/ship-image.sh starsky all   vllm-spark:latest   # every other host
```

It streams `docker save | zstd -3 | ssh | docker load` end-to-end (~3.5 min for 6.7 GB compressed over LAN). Then `deploy.sh` to pick up the new image.

## Status

Both replicas healthy on AWQ. Tool calling works in `auto` mode via the `qwen3_coder` parser. HAProxy round-robins; failover drill validated. Cluster peak ~752 tok/s aggregate at c=32. Current phase and history live in `TASKS.md` and `CHANGELOG.md`.

## Layout

```
spark-cluster/
├── CLAUDE.md          guidance for Claude Code sessions
├── README.md          this file
├── TASKS.md           phased work tracker
├── CHANGELOG.md       dated history
├── docs/              architecture, decisions, inventory, runbook
└── src/
    ├── compose/
    │   ├── vllm/      vLLM stack (both boxes)
    │   └── haproxy/   HAProxy stack (starsky only)
    └── scripts/
        ├── preflight.sh    read-only host discovery
        ├── bootstrap.sh    one-time host prep
        ├── deploy.sh       sync + docker compose up -d
        ├── ship-image.sh   stream a docker image src->dst via save | zstd | ssh | load
        ├── smoke-test.sh   /health + /v1/models + /v1/chat/completions probe
        ├── bench.py        concurrent-client throughput probe
        └── bench-sweep.sh  c=1..32 sweep wrapper
```

## Operating

Operating procedures will land in `docs/runbook.md` as each phase ships.
