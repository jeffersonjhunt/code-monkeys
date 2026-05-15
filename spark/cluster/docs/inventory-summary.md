# Discovery summary — 2026-05-05

Distilled from `docs/inventory-starsky.md` and `docs/inventory-hutch.md`. The two boxes are functionally identical, which simplifies replica deployment.

## Common stack (both starsky and hutch)

| Layer            | Value                                                              |
|------------------|--------------------------------------------------------------------|
| OS               | Ubuntu 24.04.4 LTS (Noble Numbat)                                  |
| Kernel           | 6.17.0-1014-nvidia, aarch64                                        |
| CPU              | ARM Cortex-X925 + Cortex-A725 heterogeneous, 20 logical CPUs       |
| RAM              | 121 GiB usable (DGX Spark unified memory) + 15 GiB swap            |
| Disk             | 3.7 TB NVMe, single partition at `/`                               |
| GPU              | NVIDIA GB10 (Blackwell), driver 580.142, CUDA 13.0                 |
| Docker           | 29.2.1, compose plugin v5.0.2                                      |
| NV container TK  | nvidia-container-toolkit 1.19.0 (installed, ARM64)                 |
| Python           | 3.12.3                                                             |
| User             | `jhunt` (uid 1000), in `sudo` and `docker` groups                  |
| ufw              | inactive                                                           |
| iptables         | default ACCEPT input/output, FORWARD DROP, Docker chains present   |

## Per-host

| Field                       | starsky                | hutch                  |
|-----------------------------|------------------------|------------------------|
| FQDN                        | starsky.tworivers      | hutch.tworivers        |
| LAN IP (`enP7s7`)           | 192.168.1.120/24       | 192.168.1.163/24       |
| ConnectX up port (`enp1s0f1np1`) | 169.254.44.136/16 | 169.254.127.30/16      |
| Disk free                   | 1.8 TB (50% used)      | 3.4 TB (3% used)       |
| Docker images cached        | 11                     | 21                     |
| GPU UUID                    | b8712075-…             | b0ec33a0-…             |

Both boxes are on the same LAN segment (192.168.1.0/24) — the control-plane path between them.

## ConnectX-7 link

Each box has 4 ConnectX-7 ports (2 chips × 2 ports). Currently:

- `enp1s0f0np0` — DOWN (no carrier) on both
- `enp1s0f1np1` — UP, link-local IPv4 on both, but **different /16 link-local subnets** (starsky 169.254.44.x vs hutch 169.254.127.x) — they would not auto-route to each other as configured
- `enP2p1s0f0np0` — DOWN
- `enP2p1s0f1np1` — UP, IPv6 link-local only

Implication: the high-speed direct link is up at L1 on `enp1s0f1np1` but not configured for L3 inter-host communication. Not a blocker for replicas mode (we don't use it). If we ever switch to sharded mode we'll need to assign matching static IPs on this interface and verify connectivity.

## Notable observations

1. **CUDA 13.0 driver** — bleeding edge. vLLM container images need to support it. The `nvidia-container-toolkit` handles forward-compat with older CUDA runtimes, but Blackwell (`sm_120`) kernels must be present in the chosen vLLM build. We'll prefer NVIDIA's NGC vLLM image (`nvcr.io/nvidia/vllm`) over Docker Hub for ARM64+Blackwell support, falling back to `vllm/vllm-openai` ARM tags if NGC isn't suitable. Pin tag in Phase 2.
2. **GUI desktop running** — Xorg + gnome-shell consume a tiny amount of GPU memory (~24 MB) on each box. Negligible for vLLM headroom; consider disabling for production later.
3. **No `/srv` mount** — weights live under `~/Models` on the root partition. Both boxes have ample headroom for a ~50 GB NVFP4 model. starsky has more disk used; investigate before model pull if it tightens.
4. **`docker` group membership** — no sudo needed for `docker`/`docker compose`; Ansible should not assume `become: yes` for container ops.
5. **`docker compose` v5.0.2** — Docker's new plugin numbering. Use the `docker compose ...` (subcommand) syntax, not the legacy `docker-compose` binary.
6. **Listening ports already free** — neither box is listening on 80, 443, or 8000.
7. **Host-name resolution** — both boxes reachable by short name from the workstation; verify in-cluster name resolution (`starsky` ↔ `hutch`) in Phase 3 before HAProxy config.

## Implications for plan

- Replicas mode is unchanged and clean to proceed.
- vLLM image selection is now a Phase 2 decision item — pin against NGC catalog with a known-good DGX Spark / Blackwell tag.
- ConnectX direct-connect can be parked: not needed for replicas; if future sharded mode arrives, treat that as a new sub-phase.
- No driver / toolkit installation work needed in Phase 3 — both boxes are already at the right level.

## Resolved during Phase 2 research (2026-05-05)

- **Model size**: `Qwen3-Coder-Next` is 80B total params, 3B active (MoE, 512 experts, 10 routed). NVFP4 weights ≈ 40 GB → fits in a single Spark's 128 GB unified memory with substantial headroom. TP=1 per replica is correct; the model card's TP=2 recommendation was validated for 2× datacenter GPU configs, not required.
- **vLLM image**: pinned to `vllm/vllm-openai:v0.20.1-cu129-ubuntu2404`. Has linux/arm64 manifest, CUDA 12.9 runtime (forward-compat with the box's 580.142 / CUDA 13.0 driver), and exceeds the model's "vLLM 0.14.1+" minimum.
- **Tool calling**: required by the model — `--enable-auto-tool-choice` and `--tool-call-parser qwen3_coder` are wired into the compose template via `group_vars`.

## Open items

- [ ] Verify `starsky` ↔ `hutch` name resolution from each host (will be addressed by `roles/common` /etc/hosts task in Phase 3)
