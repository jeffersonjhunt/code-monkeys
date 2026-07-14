# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a personal development environment repository (dotfiles + containerized dev environments) maintained by Jefferson J. Hunt. It contains shell configurations, dotfiles, and the **primates** Docker image build system.

## Repository Structure

- **Root directory**: Dotfiles and shell configuration (zshrc.template, zbase, zaliases, zfuncs, vimrc, etc.)
- **`codemonkey.dockerfile`**: Base Docker image (debian:13-slim) that all primates inherit from
- **`primates/`**: Specialized Docker images built on top of codemonkey (see `primates/CLAUDE.md` for details)
- **`setup`**: Host machine setup script that symlinks dotfiles into `$HOME` and `bin/` shims into `~/.local/bin/`
- **`bin/`**: Host shim scripts symlinked individually into `~/.local/bin/` (e.g. `aws` — local-first wrapper that falls back to running in the `minion` container if no `aws` binary is on PATH; `sops`/`age`/`age-keygen` — run in the `nyckel` primate)
- **`vault`**: Secrets manager — stores `ssh/`, `aws/`, `env`, `face`, `gitconfig` SOPS+age-encrypted (binary mode, one `.sops` file per original) in the private `hemlighet` repo (`~/hemlighet`, under `code-monkeys/personal/`); encrypt/decrypt runs in the containerized `nyckel` primate. `unlock`/`lock`/`status`/`rekey`; sync between machines is hemlighet git push/pull
- **`zfuncs`**: Shell functions for launching containers (`primate()`, `primate-session()`, `primate-kill()`, `primate-upgrade()`, `clamscan()`, etc.). `primate()` runs a foreground `--rm` container tied to the TTY; `primate-session()` runs a **detached, named, long-lived** container (PID 1 = `sleep infinity`) and `docker exec`s into an in-container `tmux` session, so the session survives SSH disconnects — reconnect and re-run `primate-session <image>` to re-attach. `primate-kill <image|name>` tears it down (the `<image>-home` volume persists).
- **`env`**: Environment variable definitions (tokens, API keys) — never commit secrets here
- **`aws/`**: AWS CLI config and credentials — managed by vault, never commit plaintext
- **`claude/`**: Claude Code settings and custom slash commands. `setup` links these **into** the real `~/.claude` (via `CHILD_LINKS`): `~/.claude/settings.json` and `~/.claude/commands` → this repo. Note `~/.claude` itself must stay a **real directory** — it is Claude Code's live state (credentials, history, projects, daemon cache), so it can never *be* a symlink. (The old `DIR_LINKS` entry `claude::claude` created `~/.claude/claude`, a path nothing reads; the settings never reached Claude Code at all. Fixed.) An existing real `settings.json`/`commands` is never clobbered — setup skips it and tells you to remove it first if you want the repo to manage it. Also copied into the claude primate image by `make -C primates <img>.upgrade`.
- **`007/skills/`**: Agent skills library — portable skills installed into `~/.kiro/skills/` and `~/.claude/skills/` by `setup`. Run `make test` from `007/` to test. See `007/skills/CONTRIBUTING.md` for authoring guidelines.
- **`Library/`**: macOS-only assets (`KeyBindings/DefaultKeyBinding.dict` is copied to `~/Library/KeyBindings` by setup)
- **`spark/`**: DGX Spark cluster ops. `spark/cluster/` is a host-name-agnostic vLLM replica cluster (compose stacks, scripts, runbook) that consumes the `cuda-vllm` primate, fronted by a model-aware LiteLLM router. Hosts and roles come from a gitignored `spark/cluster/cluster.env`; the maintainer's deployment is currently a single DGX Spark replica (`REPLICAS="hutch.tworivers"`) with the router on the control-plane host (`LB_HOST=minerva.tworivers`, port 8888) — `starsky` was repurposed out of the pool 2026-06-10. See `spark/cluster/CLAUDE.md`.

## Build Commands

All Docker builds are run from the `primates/` directory:

```bash
cd primates
make all                    # Build codemonkey base + all standard targets
make codemonkey.build       # Build just the base image (builds from parent dir)
make <name>.build           # Build a specific image (claude, miniforge3, embedded, etc.)
make all UNSAFE_SSL=true    # Build with SSL verification disabled (tainted build)
make all FRESH=false        # Skip freshclam during codemonkey build (faster, no ClamAV DB update)
make cuda-base.build        # Shared CUDA base (cuda-base:runtime + cuda-base:devel); auto-built by the cuda-* targets
make cuda-llama-cpp.build   # Requires NVIDIA kernel — llama.cpp, cross-GPU sm_89/120/121
make cuda-comfy.build       # Requires NVIDIA kernel — ComfyUI, cross-GPU
make cuda-vllm.build        # Requires NVIDIA kernel — vLLM v0.21.0 source build, native sm_89/120/121 cutlass
make cuda                   # Base + all standard + the three cuda-* GPU images
make clean                  # Remove all built images
```

## Image Hierarchy

```
debian:13-slim → codemonkey → miniforge3 (miniforge3-env) → claude (claude-env) | opencode (opencode-env) | kiro (kiro-env)
                            → embedded                              → spark-bench (spark-bench-env)
                            → lamp
                            → huggingface
                            → minion

nvidia/cuda:13.2.1 → cuda-base (runtime + devel flavors; nvtop, codemonkey user, cross-GPU arch defaults)
                       → cuda-llama-cpp (multi-stage: full/light/server; cross-GPU sm_89/120/121)
                       → cuda-comfy
                       → cuda-vllm       (vLLM v0.21.0 source, native sm_89/120/121 cutlass — backs the spark-cluster, runs on the 4090s)
```

Miniforge3-derived images each get a conda environment (`<image>-env`) that is auto-activated at login. See `primates/CLAUDE.md` for details on adding this to new images.

The codemonkey/miniforge3 chain is **arch-aware via runtime detection** (`uname -m`, `dpkg --print-architecture`) and **TARGETARCH** — the same dockerfiles build cleanly on both aarch64 (Mjolnir, primary dev) and x86_64 (intel-nuc.tworivers, used for `spark-bench`). The CUDA chain builds from `cuda-base`, whose arch defaults span sm_89 (RTX 4090), sm_120 (RTX 5090), and sm_121 (DGX Spark) so the family runs on x86 NVIDIA boxes as well as Spark. `cuda-vllm` now ships native sm_89 alongside sm_120/sm_121 (so it runs on the 4090s too); pass `--build-arg TORCH_CUDA_ARCH_LIST="12.0 12.1+PTX"` for a slimmer Spark-only build.

## Registry — published to ECR (`codemonkeys/*`)

The whole family is published to the private registry `521147433280.dkr.ecr.us-east-1.amazonaws.com/codemonkeys/*`,
**multi-arch** (`linux/amd64` + `linux/arm64`) so any fleet host pulls its native arch. Exceptions: **`spark-bench`
is amd64-only** (SWE-Bench testbed images are x86-only), and **`cuda-base` publishes `:runtime` + `:devel`** (no
`:latest`). Because the CPU chain `FROM`s local tags, a clean multi-arch build means building the chain **natively
on one x86_64 host and one aarch64 host**:

```bash
# on an x86_64 push host (e.g. minerva) AND an aarch64 push host (e.g. hutch):
primates/build-push.sh                       # CPU chain -> <name>:latest-<amd64|arm64>
primates/build-push.sh cuda-comfy cuda-llama-cpp   # GPU images, on a GPU host of each arch
# then once, anywhere with ECR creds:
primates/manifest-push.sh                     # assemble multi-arch :latest via buildx imagetools
```

Creds come from the host `~/.aws` (default profile = the scoped `fleet-ecr-push` identity, which covers
`codemonkeys/*`). The **`primate <name>` shell function pulls from ECR on demand** (`_primate_ensure_image`) and
retags to the local name, so a fresh host runs any primate without building it first.

## Key Conventions

- Dockerfiles use `<image-name>.dockerfile` naming; `codemonkey.dockerfile` lives at root, all others in `primates/`
- Container user is `codemonkey` (UID/GID 1000) with sudo, shell is zsh with Oh-My-Zsh
- APT cleanup pattern in Dockerfiles: `apt-get autoclean -y && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*`
- Standard images are **multi-arch (amd64 + arm64), published to ECR** (`codemonkeys/*`; see Registry above) — `spark-bench` is amd64-only; the `cuda-*` images build from `cuda-base` with cross-GPU arch defaults (sm_89/sm_120/sm_121), including `cuda-vllm` (override its `TORCH_CUDA_ARCH_LIST` for a slimmer single-target build)
- Shell config is layered: `zshrc.template` sources `~/.zbase` only; `zbase` in turn sources `~/.zfuncs` and `~/.zaliases`
- Git remote is GitHub; main branch is `master`
- Vault-managed plaintext (`ssh/`, `aws/`, `env`, `face`, `gitconfig`) is gitignored — this repo is PUBLIC and never holds secrets, plaintext or encrypted; the encrypted copies live only in `hemlighet`
- `UNSAFE_SSL=true` build arg disables SSL verification for curl, wget, git, conda, npm, and apt HTTPS during build; skips freshclam; sets `TAINTED_BUILD=true` env var in the image (login warning displayed to user). All config changes are reverted at the end of each install RUN so verification is restored at runtime.
- `FRESH=false` build arg skips `freshclam` (ClamAV signature DB update) on `codemonkey.dockerfile` to speed up builds. Independent of `UNSAFE_SSL` — either knob will skip freshclam.
