# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a personal development environment repository (dotfiles + containerized dev environments) maintained by Jefferson J. Hunt. It contains shell configurations, dotfiles, and the **primates** Docker image build system.

## Repository Structure

- **Root directory**: Dotfiles and shell configuration (zshrc.template, zbase, zaliases, zfuncs, vimrc, etc.)
- **`codemonkey.dockerfile`**: Base Docker image (debian:13-slim) that all primates inherit from
- **`primates/`**: Specialized Docker images built on top of codemonkey (see `primates/CLAUDE.md` for details)
- **`setup`**: Host machine setup script that symlinks dotfiles into `$HOME` and `bin/` shims into `~/.local/bin/`
- **`bin/`**: Host shim scripts symlinked individually into `~/.local/bin/` (e.g. `aws` — local-first wrapper that falls back to running in the `minion` container if no `aws` binary is on PATH)
- **`zfuncs`**: Shell functions for launching containers (`primate()`, `primate-upgrade()`, `clamscan()`, etc.)
- **`env`**: Environment variable definitions (tokens, API keys) — never commit secrets here
- **`aws/`**: AWS CLI config and credentials — managed by vault, never commit plaintext
- **`claude/`**: Claude Code settings and custom slash commands (symlinked to `~/.claude` by setup, copied into claude primate image)
- **`007/skills/`**: Agent skills library — portable skills installed into `~/.kiro/skills/` and `~/.claude/skills/` by `setup`. Run `make test` from `007/` to test. See `007/skills/CONTRIBUTING.md` for authoring guidelines.
- **`007/clients/kiro/`**: Kiro-specific client files — MCP servers (LDAP, Obsidian Tasks), agent definitions (`pa.json`), and AI context resources. Installed to `~/.local/share/kiro/` and `~/.kiro/agents/` via `make -C 007/clients/kiro install`. MCP server credentials (LDAP, Obsidian) come from the vault-managed `env` file (see `env.template` for all variables).
- **`Library/`**: macOS-only assets (`KeyBindings/DefaultKeyBinding.dict` is copied to `~/Library/KeyBindings` by setup)
- **`spark/`**: DGX Spark cluster ops. `spark/cluster/` is a host-name-agnostic vLLM replica cluster (compose stacks, scripts, runbook) that consumes the `vllm-spark` primate. Hosts and roles come from a gitignored `spark/cluster/cluster.env`; the maintainer's deployment is two DGX Spark nodes (starsky, hutch). See `spark/cluster/CLAUDE.md`.

## Build Commands

All Docker builds are run from the `primates/` directory:

```bash
cd primates
make all                    # Build codemonkey base + all standard targets
make codemonkey.build       # Build just the base image (builds from parent dir)
make <name>.build           # Build a specific image (claude, miniforge3, embedded, etc.)
make all UNSAFE_SSL=true    # Build with SSL verification disabled (tainted build)
make all FRESH=false        # Skip freshclam during codemonkey build (faster, no ClamAV DB update)
make llama-cpp-spark.build  # Requires NVIDIA kernel
make comfy-ui-spark.build   # Requires NVIDIA kernel
make vllm-spark.build       # Requires NVIDIA kernel — vLLM v0.21.0 source build, sm_121 native cutlass
make clean                  # Remove all built images
```

## Image Hierarchy

```
debian:13-slim → codemonkey → miniforge3 (miniforge3-env) → claude (claude-env) | opencode (opencode-env) | kiro (kiro-env)
                            → embedded                              → spark-bench (spark-bench-env)
                            → lamp
                            → huggingface
                            → minion

nvidia/cuda:13.2.1 → llama-cpp-spark (multi-stage: full/light/server)
                   → comfy-ui-spark
                   → vllm-spark      (vLLM v0.21.0 source, sm_121 native cutlass — backs the spark-cluster)
```

Miniforge3-derived images each get a conda environment (`<image>-env`) that is auto-activated at login. See `primates/CLAUDE.md` for details on adding this to new images.

The codemonkey/miniforge3 chain is **arch-aware via runtime detection** (`uname -m`, `dpkg --print-architecture`) and **TARGETARCH** — the same dockerfiles build cleanly on both aarch64 (Mjolnir, primary dev) and x86_64 (intel-nuc.tworivers, used for `spark-bench`). The CUDA chain is sm_121-only and only builds on Spark hardware.

## Key Conventions

- Dockerfiles use `<image-name>.dockerfile` naming; `codemonkey.dockerfile` lives at root, all others in `primates/`
- Container user is `codemonkey` (UID/GID 1000) with sudo, shell is zsh with Oh-My-Zsh
- APT cleanup pattern in Dockerfiles: `apt-get autoclean -y && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*`
- Standard images target aarch64 (ARM64); CUDA images target sm_121 (Blackwell/DGX Spark)
- Shell config is layered: `zshrc.template` sources `~/.zbase` and `~/.zaliases`; functions live in `zfuncs`
- Git remote is GitHub; main branch is `master`
- Vault files (`*.vault`) and personal assets (`face`, `gitconfig`) are gitignored — secrets are never committed
- `UNSAFE_SSL=true` build arg disables SSL verification for curl, wget, git, conda, npm, and apt HTTPS during build; skips freshclam; sets `TAINTED_BUILD=true` env var in the image (login warning displayed to user). All config changes are reverted at the end of each install RUN so verification is restored at runtime.
- `FRESH=false` build arg skips `freshclam` (ClamAV signature DB update) on `codemonkey.dockerfile` to speed up builds. Independent of `UNSAFE_SSL` — either knob will skip freshclam.
