# Architecture

## Topology decision: replicas, not shards

Two GPU nodes (DGX Sparks in the maintainer's deployment), each running an independent vLLM instance with a full copy of the model weights, fronted by a model-aware LiteLLM router on `$LB_HOST`. Hosts and the LB role come from `cluster.env` — examples below use the maintainer's names (`starsky`, `hutch`) but the orchestration is name-agnostic.

Reasoning:

- DGX Spark has 128 GB unified memory per box. NVFP4-quantized Qwen3-Coder-Next fits comfortably under that limit, so single-box inference is viable.
- Replicas double throughput vs. a single sharded model.
- Replicas survive a single-node failure: degraded throughput, but the API stays up.
- Sharding adds Ray + NCCL complexity and pins one model copy across nodes — we lose redundancy and gain operational complexity for no win at this model size.

ConnectX-7 direct link between the two boxes is left in place but unused. If we later need to serve a model that doesn't fit one box, we can switch to pipeline-parallel sharded mode without re-cabling.

## Load balancing

A **LiteLLM** model-aware router on `$LB_HOST` (replaced the round-robin HAProxy 2026-06-28; see `docs/decisions.md` + CHANGELOG):

- Front: HTTP on `0.0.0.0:$LB_PORT`
- Routing: **by request `model` name**, not round-robin — a single endpoint fronts both GPU boxes serving *different* models. `qwen3-coder-next` → hutch, `reasoning` → starsky, `caption` → starsky. Backends are addressed by FQDN (DNS is the source of truth); an unknown `model` is rejected rather than fanned out.
- Config: `src/compose/litellm/config.yaml` (`model_list` maps each model name to a `hosted_vllm/` backend `api_base`)
- Failover behavior: a second backend for the same model name is just another `model_list` entry, load-balanced by LiteLLM

`$LB_HOST` may be a replica (co-located, the original single-box topology) **or a dedicated host outside `$REPLICAS`** — e.g. the control plane, decoupling the LB from any GPU box. The backend list (`$REPLICAS`) and the LB host are independent; `deploy.sh` targets each separately. **Current deployment:** `$LB_HOST=minerva` (standalone, control plane), `$LB_PORT=8888`, `$REPLICAS="hutch"` — see `docs/decisions.md`.

Known SPOF: `$LB_HOST` losing power takes the API endpoint down. Accepted for current usage. Upgrade path is an HA router pair when availability requirements grow.

## Why containers

- The locally-built `cuda-vllm` image (pulled from private ECR; compose default `…/codemonkeys/cuda-vllm:latest`) bundles the right CUDA + Python + vLLM stack with native sm_89/120/121 support
- Image rollback is just a container restart with a different tag
- Pinned tags make environment drift impossible
- Weights live outside the image at `~/Models/<org>/<name>`, so model changes don't trigger image rebuilds

## Why plain Docker Compose (no Ansible, no Kubernetes)

Two hosts. The "fleet" doesn't justify a control-plane abstraction:

- Compose files are the source of truth — what you read is what runs.
- `docker compose up -d` is already idempotent; rerunning `deploy.sh` is safe.
- "`$LB_HOST` runs the LiteLLM router, the replicas don't" is one extra `deploy.sh` call driven by `cluster.env`, not a templated inventory engine.
- Templating engines (Ansible Jinja2, Helm) would add indirection without leverage at this scale.

We'd revisit if any of these change: fleet grows past ~5 boxes, hosts diverge into meaningfully different roles, or there's pre-existing in-house orchestration tooling we should fit into.

## Data paths

- Model weights: `$MODEL_DIR/<org>/<name>` on each node (compose `MODEL_DIR` default `/srv/models`), owned by `gdeceiver`, mounted read-only into the vLLM container at `/models`. Flat HF org/name layout, pre-staged by `model-pull.sh` — not the auto-managed HF cache layout. (A hutch redeploy to actually move its mount onto `/srv/models` is still pending; `/srv/models` is the documented/intended path.)
- Container logs: Docker JSON-file driver with rotation; aggregated by future log shipper if needed
- LiteLLM router logs: stdout, captured by Docker

## Networks and ports

| Port            | Where         | Purpose                                          |
|-----------------|---------------|--------------------------------------------------|
| `$VLLM_PORT`    | every replica | vLLM OpenAI-compatible API (internal)            |
| `$LB_PORT`      | `$LB_HOST`    | LiteLLM router public ingress (non-privileged port) |
| ?               | replica pair  | ConnectX-7 link (unused, reserved)               |

vLLM's `$VLLM_PORT` should not be exposed publicly — only the LiteLLM router on `$LB_HOST` terminates external traffic. Firewall rules enforce this.
