# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**primates** — A containerized development environment system that produces specialized Docker images for different development domains. Maintained by Jefferson J. Hunt.

## Build Commands

```bash
make all                    # Build codemonkey base + all targets (minion, embedded, miniforge3, claude, opencode, kiro, lamp, huggingface)
make codemonkey.build       # Build the codemonkey base image (from parent directory)
make <name>.build           # Build a specific image, e.g. make claude.build
make llama-cpp-spark.build  # Build llama.cpp for DGX Spark (requires NVIDIA kernel)
make comfy-ui-spark.build   # Build ComfyUI for DGX Spark (requires NVIDIA kernel)
make all UNSAFE_SSL=true    # Build with SSL verification disabled (sets TAINTED_BUILD=true in images)
make all FRESH=false        # Skip freshclam during codemonkey build (faster)
make clean                  # Remove all built images
```

All builds use `docker buildx build` except llama-cpp-spark which uses `docker build` with multi-stage targets.

## Image Hierarchy

```
codemonkey (base, dockerfile in parent dir)
├── miniforge3       (adds Miniforge3 for aarch64, conda init for zsh)
│   ├── claude       (adds claude-code via native installer, claude-env conda env)
│   ├── opencode     (adds npm, opencode-ai, opencode-env conda env)
│   └── kiro         (adds Amazon Kiro CLI via native installer, kiro-env conda env)
├── embedded         (adds libfmt, libboost, cc65, vasm 6502 assembler)
├── lamp             (adds Apache, MariaDB, PHP)
├── huggingface      (adds python3 venv, huggingface-cli)
└── minion           (empty extension of codemonkey)

nvidia/cuda:13.1.1-devel-ubuntu24.04 (independent)
└── llama-cpp-spark  (multi-stage: full, light, server targets for sm_121/Blackwell GPUs)

nvidia/cuda:13.1.1-runtime-ubuntu24.04 (independent)
└── comfy-ui-spark   (ComfyUI node-based Stable Diffusion GUI for sm_121/Blackwell GPUs)
```

## Conda Environments

Images extending miniforge3 automatically create and activate a conda environment named `<image>-env` (e.g., `claude-env`, `opencode-env`). This is driven by:

- **`IMAGE_NAME` build arg** — passed automatically by the Makefile's `%.build` target
- **`/opt/miniforge3/.default-env`** — marker file written at build time containing the env name
- **`zshrc.template`** — reads the marker file at login and runs `conda activate`

To add a conda env to a new miniforge3-derived image, add the following to its Dockerfile:

```dockerfile
ARG IMAGE_NAME=<default-name>
RUN /opt/miniforge3/bin/conda create -y -n ${IMAGE_NAME}-env python \
    && echo "${IMAGE_NAME}-env" > /opt/miniforge3/.default-env
```

## Key Conventions

- Dockerfiles follow the naming pattern `<image-name>.dockerfile`
- The `codemonkey.dockerfile` lives in the parent directory (`../`), not in this workspace
- The default user inside containers is `codemonkey` with home at `/home/codemonkey`
- Shell is zsh inside codemonkey-based images
- Architecture target is aarch64 (ARM64) for miniforge3
- APT cleanup pattern: `apt-get autoclean && autoremove && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*`
- llama-cpp-spark and comfy-ui-spark target CUDA architecture sm_121 (DGX Spark Blackwell GPUs) and require the host to be running an NVIDIA kernel
- **`UNSAFE_SSL` build arg** — when `true`, disables SSL verification for curl (`--insecure`), wget (`--no-check-certificate`), git (`http.sslVerify false`), conda (`ssl_verify false`), and npm (`strict-ssl false`) **during the install RUN steps only**; the config changes are reverted at the end of each RUN so the resulting image still verifies SSL at runtime. Also skips `freshclam` (ClamAV DB update). Sets `TAINTED_BUILD=true` env var in the resulting image.
- **`FRESH` build arg** (codemonkey.dockerfile only) — when `false`, skips `freshclam` to speed up the base build. Independent of `UNSAFE_SSL`; either knob will skip freshclam.
- **`TAINTED_BUILD` env var** — baked into every image; `true` if built with `UNSAFE_SSL=true`, `false` otherwise. A login warning is displayed to the user when `TAINTED_BUILD=true`.
