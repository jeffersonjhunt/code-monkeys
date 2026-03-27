# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a personal development environment repository (dotfiles + containerized dev environments) maintained by Jefferson J. Hunt. It contains shell configurations, dotfiles, and the **primates** Docker image build system.

## Repository Structure

- **Root directory**: Dotfiles and shell configuration (zshrc.template, zbase, zaliases, zfuncs, vimrc, gitconfig, etc.)
- **`codemonkey.dockerfile`**: Base Docker image (debian:13-slim) that all primates inherit from
- **`primates/`**: Specialized Docker images built on top of codemonkey (see `primates/CLAUDE.md` for details)
- **`setup`**: Host machine setup script that symlinks dotfiles into `$HOME`
- **`zfuncs`**: Shell functions for launching containers (`claude()`, `opencode()`, `msh()`, `clamscan()`, etc.)
- **`env`**: Environment variable definitions (tokens, API keys) — never commit secrets here
- **`aws/`**: AWS CLI config and credentials — managed by vault, never commit plaintext
- **`claude/`**: Claude Code settings and custom slash commands (symlinked to `~/.claude` by setup, copied into claude primate image)

## Build Commands

All Docker builds are run from the `primates/` directory:

```bash
cd primates
make all                    # Build codemonkey base + all standard targets
make codemonkey.build       # Build just the base image (builds from parent dir)
make <name>.build           # Build a specific image (claude, miniforge3, embedded, etc.)
make llama-cpp-spark.build  # Requires NVIDIA kernel
make comfy-ui-spark.build   # Requires NVIDIA kernel
make clean                  # Remove all built images
```

## Image Hierarchy

```
debian:13-slim → codemonkey → miniforge3 (miniforge3-env) → claude (claude-env) | opencode (opencode-env)
                            → embedded
                            → lamp
                            → huggingface
                            → minion

nvidia/cuda:13.1.1 → llama-cpp-spark (multi-stage: full/light/server)
                   → comfy-ui-spark
```

Miniforge3-derived images each get a conda environment (`<image>-env`) that is auto-activated at login. See `primates/CLAUDE.md` for details on adding this to new images.

## Key Conventions

- Dockerfiles use `<image-name>.dockerfile` naming; `codemonkey.dockerfile` lives at root, all others in `primates/`
- Container user is `codemonkey` (UID/GID 1000) with sudo, shell is zsh with Oh-My-Zsh
- APT cleanup pattern in Dockerfiles: `apt-get autoclean -y && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*`
- Standard images target aarch64 (ARM64); CUDA images target sm_121 (Blackwell/DGX Spark)
- Shell config is layered: `zshrc.template` sources `~/.zbase` and `~/.zaliases`; functions live in `zfuncs`
- Git remote is AWS CodeCommit; main branch is `master`
