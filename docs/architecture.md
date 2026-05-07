# Architecture

## Topology decision: replicas, not shards

Two DGX Spark nodes, each running an independent vLLM instance with a full copy of the model weights, fronted by HAProxy on starsky.

Reasoning:

- DGX Spark has 128 GB unified memory per box. NVFP4-quantized Qwen3-Coder-Next fits comfortably under that limit, so single-box inference is viable.
- Replicas double throughput vs. a single sharded model.
- Replicas survive a single-node failure: degraded throughput, but the API stays up.
- Sharding adds Ray + NCCL complexity and pins one model copy across nodes — we lose redundancy and gain operational complexity for no win at this model size.

ConnectX-7 direct link between the two boxes is left in place but unused. If we later need to serve a model that doesn't fit one box, we can switch to pipeline-parallel sharded mode without re-cabling.

## Load balancing

HAProxy on starsky:

- Front: HTTP on `0.0.0.0:8080`
- Back: `starsky:8000`, `hutch:8000` (resolved via DNS at HAProxy startup)
- Health check: `GET /health` on each backend (vLLM exposes this)
- Failover behavior: HAProxy drains a backend on health-check failure

Known SPOF: starsky losing power takes the API endpoint down. Accepted for current usage. Upgrade path is active/passive HAProxy via keepalived when availability requirements grow.

## Why containers

- `vllm/vllm-openai` images bundle the right CUDA + Python + vLLM stack, including ARM64/Blackwell support
- Image rollback is just a container restart with a different tag
- Pinned tags make environment drift impossible
- Weights live outside the image at `/srv/models`, so model changes don't trigger image rebuilds

## Why plain Docker Compose (no Ansible, no Kubernetes)

Two hosts. The "fleet" doesn't justify a control-plane abstraction:

- Compose files are the source of truth — what you read is what runs.
- `docker compose up -d` is already idempotent; rerunning `deploy.sh` is safe.
- "starsky runs HAProxy, hutch doesn't" is one extra `deploy.sh` call, not a templated inventory.
- Templating engines (Ansible Jinja2, Helm) would add indirection without leverage at this scale.

We'd revisit if any of these change: fleet grows past ~5 boxes, hosts diverge into meaningfully different roles, or there's pre-existing in-house orchestration tooling we should fit into.

## Data paths

- Model weights: `/srv/models/<model-name>` on each node, owned by `jhunt`, mounted read-only into the vLLM container
- Container logs: Docker JSON-file driver with rotation; aggregated by future log shipper if needed
- HAProxy logs: stdout, captured by Docker

## Networks and ports

| Port    | Where        | Purpose                                          |
|---------|--------------|--------------------------------------------------|
| 8000    | both nodes   | vLLM OpenAI-compatible API (internal)            |
| 8080    | starsky      | HAProxy public ingress (non-privileged port)     |
| ?       | both nodes   | ConnectX-7 link (unused, reserved)               |

vLLM's `:8000` should not be exposed publicly — only HAProxy on starsky terminates external traffic. Firewall rules enforce this.
