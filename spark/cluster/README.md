# spark-cluster

vLLM replica cluster across two GPU nodes (designed for NVIDIA DGX Spark — Blackwell GB10, 128 GB UMA — but the orchestration is host-name agnostic and works with any pair of SSH-reachable boxes that meet the requirements below). Serves an OpenAI-compatible HTTP API behind a model-aware LiteLLM router. Runs the locally-built `cuda-vllm` image (native sm_89/120/121 cutlass — built from `../../primates/cuda-vllm.dockerfile`) which unblocks both FP8 dense and NVFP4 MoE paths that crash on upstream `vllm/vllm-openai`. See `docs/parking-lot.md` for the resolved-canary write-ups.

## Requirements

Two hosts that:
- Run Ubuntu (or any distro with Docker, `docker compose`, `zstd`, and `host` available)
- Each have an NVIDIA GPU + `nvidia-container-toolkit` (the included `cuda-vllm` image ships native sm_89/120/121; override `TORCH_CUDA_ARCH_LIST` for a slimmer single-target build)
- Are SSH-reachable from your workstation as a single shared user with passwordless sudo and membership in the `docker` group
- Resolve each other's short names via DNS (or `/etc/hosts`)

## Configure your hosts

Cluster scripts read host details from `cluster.env`. The example uses the placeholder FQDNs `hostA.example` and `hostB.example` (with `LB_HOST=hostA.example`, i.e. the router co-located on the first replica):

```bash
cp cluster.env.example cluster.env
# edit cluster.env — set SSH_USER, REPLICAS, LB_HOST
```

`REPLICAS` is the space-separated list of cluster boxes; `LB_HOST` is the one that fronts the cluster with the LiteLLM router. `LB_HOST` may be a member of `REPLICAS` (co-located) or a standalone host outside it (`load-config.sh` warns, doesn't error). The names you put here must be SSH targets and DNS-resolvable on each box.

Worked example (the maintainer's current cluster): `REPLICAS="hutch.tworivers"`, `LB_HOST=minerva.tworivers` (standalone control plane).

```
client ──► $LB_HOST:$LB_PORT (LiteLLM) ──► <replica>:$VLLM_PORT (vLLM), routed by model name
```

Each replica is independent: same compose, same model, full copy of weights at `/srv/models/<org>/<name>` (flat HF org/name layout, pre-staged via `src/scripts/model-pull.sh`). Why replicas (not sharded)? See `docs/architecture.md`.

## Deploy

One-time per box (run for each entry in `$REPLICAS`):

```bash
. cluster.env
for h in $REPLICAS; do
  ssh "$SSH_USER@$h" "CLUSTER_PEERS='$REPLICAS' bash -s" < src/scripts/bootstrap.sh
done
```

No local HF token setup is needed: the vllm stack's `.env` (with `HF_TOKEN` + serving config) is
decrypted on the target from the `hemlighet` repo (SOPS/age) by `deploy.sh` — the local `.env` is
excluded from the deploy tar and not required on your workstation.

Deploy:

```bash
./src/scripts/deploy.sh all                    # vllm on every replica, litellm on $LB_HOST
# or one piece at a time
./src/scripts/deploy.sh <host> vllm litellm
./src/scripts/deploy.sh <host> vllm
```

`deploy.sh` tar-streams the relevant `src/compose/<stack>/` directory to `~/spark-deploy/<stack>/` on the host and runs `docker compose up -d`. For the **vllm** stack it additionally, on the target: ECR-logs-in, **decrypts the stack `.env`** (HF_TOKEN + serving config) from the `hemlighet` repo, and **`docker compose pull`s `cuda-vllm` from private ECR** — so both the image and the secret arrive without a host-to-host copy or a plaintext `.env`. (Target needs `~/.aws`, an age key, and a `hemlighet` clone.) For haproxy it renders `haproxy.cfg` from the template first.

When the `cuda-vllm` image is rebuilt, **push it to ECR** (native-on-host → `codemonkeys/cuda-vllm:latest`; see `g.deceiver/infra/build-push.sh` for the pattern), then `deploy.sh <host> vllm` pulls it. The old host→host `ship-image.sh` (`docker save | zstd | ssh | docker load`) is **retired** — images come from ECR now.

## Status

**Coding is served by the consolidated `Qwen/Qwen3.8-27B-FP8` engine on `starsky`** (served-name `reasoning`, run no-think for code) via the **LiteLLM** `code` route on `minerva:8888`. The standalone `RedHatAI/Qwen3-Coder-Next-NVFP4` on `hutch` was **retired 2026-09-05** — a bake-off had the 27B FP8 beat it on both code and tool-calling (HumanEval 0.967 vs 0.850, tau2 0.95 vs 0.60), so one engine now serves reason+code+caption+vision and hutch's ~80 GB was freed (it now runs the g.deceiver memory stack + is the bench/failover box). The route was renamed `qwen3-coder-next` → `code` on 2026-09-05 (the old name lied about the model). Current phase and history live in `TASKS.md` and `CHANGELOG.md`.

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
    │   ├── litellm/      LiteLLM model-aware router ($LB_HOST only; current LB — config.yaml routes by model)
    │   └── haproxy/      retired round-robin LB stack (retained on disk as a fallback; haproxy.cfg from template)
    └── scripts/
        ├── lib/load-config.sh  sourced by all scripts to read cluster.env
        ├── preflight.sh        read-only host discovery
        ├── bootstrap.sh        one-time host prep
        ├── deploy.sh           sync config + ECR pull + SOPS-decrypt .env + docker compose up -d
        ├── smoke-test.sh       /health + /v1/models + /v1/chat/completions probe
        ├── bench.py            concurrent-client throughput probe
        └── bench-sweep.sh      c=1..32 sweep wrapper
```

## Operating

Operating procedures will land in `docs/runbook.md` as each phase ships.
