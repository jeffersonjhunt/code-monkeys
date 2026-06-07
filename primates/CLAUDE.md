# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**primates** — A containerized development environment system that produces specialized Docker images for different development domains. Maintained by Jefferson J. Hunt.

## Build Commands

```bash
make all                    # Build codemonkey base + all targets (minion, embedded, miniforge3, claude, opencode, kiro, lamp, huggingface)
make codemonkey.build       # Build the codemonkey base image (from parent directory)
make <name>.build           # Build a specific image, e.g. make claude.build
make cuda-base.build        # Build the shared CUDA base (cuda-base:runtime + cuda-base:devel); auto-built by the spark targets
make cuda-llama-cpp.build   # Build llama.cpp, cross-GPU sm_89/120/121 (requires NVIDIA kernel)
make cuda-comfy.build       # Build ComfyUI, cross-GPU (requires NVIDIA kernel)
make cuda-vllm.build        # Build vLLM v0.21.0, native sm_89/120/121 cutlass (requires NVIDIA kernel)
make cuda                   # Build base + all standard + the three cuda-* GPU images
make spark-bench.build      # Build the LLM-eval harness primate (build on x86 host — intel-nuc.tworivers — for SWE-Bench testbed compatibility)
make all UNSAFE_SSL=true    # Build with SSL verification disabled (sets TAINTED_BUILD=true in images)
make all FRESH=false        # Skip freshclam during codemonkey build (faster)
make clean                  # Remove all built images
```

All builds use `docker buildx build`. `cuda-llama-cpp` and `cuda-vllm` are multi-stage (`--target`).

## Image Hierarchy

```
codemonkey (base, dockerfile in parent dir)
├── miniforge3       (adds Miniforge3 for aarch64/x86_64 via TARGETARCH, conda init for zsh, uv in base env)
│   ├── claude       (adds claude-code via native installer, claude-env conda env)
│   ├── opencode     (adds opencode via curl installer to /usr/local/bin, opencode-env conda env, pre-pointed at spark-cluster vLLM)
│   ├── kiro         (adds Amazon Kiro CLI via native installer, kiro-env conda env)
│   └── spark-bench  (x86-only — LLM eval harnesses for the spark-cluster; SWE-Bench Verified via SWE-agent, tau2-bench, LiveCodeBench, AIME/GPQA. Runs on intel-nuc.tworivers)
├── embedded         (adds libfmt, libboost, cc65, vasm 6502 assembler)
├── lamp             (adds Apache, MariaDB, PHP)
├── huggingface      (adds python3 venv, huggingface-cli)
└── minion           (empty extension of codemonkey)

nvidia/cuda:13.2.1-{runtime,devel}-ubuntu24.04
└── cuda-base        (shared CUDA base; one dockerfile, two flavors — cuda-base:runtime + cuda-base:devel. Adds nvtop, the codemonkey user, the sudo/zsh/git/curl floor, and cross-GPU arch defaults sm_89/sm_120/sm_121)
    ├── cuda-llama-cpp   (build stage on raw cuda devel; shipping stages on cuda-base:runtime — full/light/server; cross-GPU sm_89/120/121)
    ├── cuda-comfy       (cuda-base:runtime; ComfyUI node-based Stable Diffusion GUI, cross-GPU via PyTorch wheels)
    └── cuda-vllm        (build stage on raw cuda devel; runtime stage on cuda-base:devel; vLLM v0.21.0 source build with native sm_89/120/121 cutlass — backs the spark-cluster, unblocks FP8 dense / NVFP4 MoE on Blackwell, and runs on the 4090s)
```

`cuda-base` is built in two flavors from a single `cuda-base.dockerfile` via the `CUDA_FLAVOR` build arg: `:runtime` (slim, for images that only run prebuilt binaries) and `:devel` (ships nvcc + headers, for images that JIT-compile CUDA at runtime). The three `cuda-*` `.build` Makefile targets list `cuda-base.build` as a prerequisite, so it is built automatically (and the spark-build skill, which runs `make <img>.build`, picks it up for free). Build stages of the multi-stage images stay on the raw `nvidia/cuda` devel image — they are throwaway, so only the shipping stages extend `cuda-base`.

`cuda-vllm` keeps the `-devel` base at runtime (not `-runtime`) because FlashInfer and Triton JIT-compile CUDA kernels at first request — they need `nvcc`, `gcc`/`g++`, and `python3-dev` available inside the container. Its build parallelism (`MAX_JOBS`/`NVCC_THREADS`) defaults to Spark-sized (~48–60 GB peak); override both to a small equal value (e.g. `--build-arg MAX_JOBS=6 --build-arg NVCC_THREADS=6`) when building on a low-RAM host like the 30 GB 4090 boxes.

`opencode` installs its binary to `/usr/local/bin/opencode` (not `~/.opencode/bin`, where the installer defaults) so it sits outside `/home/codemonkey` and is not shadowed by the `<image>-home` volume that `primate()` mounts. The version is image-managed — rebuild the image to upgrade; opencode's runtime self-update is disabled in `opencode.json`. `make upgrade` does not touch it (it only syncs dotfiles into the home volume).

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
- the `cuda-*` images build cross-GPU (sm_89/sm_120/sm_121) from `cuda-base` and require the host to be running an NVIDIA kernel (or have a visible NVIDIA card — see the `_nv_check` guard in the Makefile)
- **`UNSAFE_SSL` build arg** — when `true`, disables SSL verification for curl (`--insecure`), wget (`--no-check-certificate`), git (`http.sslVerify false`), conda (`ssl_verify false`), npm (`strict-ssl false`), and apt HTTPS (`Acquire::https::Verify-Peer false`) **during the install RUN steps only**; the config changes are reverted at the end of each RUN so the resulting image still verifies SSL at runtime. Also skips `freshclam` (ClamAV DB update). Sets `TAINTED_BUILD=true` env var in the resulting image.
- **`FRESH` build arg** (codemonkey.dockerfile only) — when `false`, skips `freshclam` to speed up the base build. Independent of `UNSAFE_SSL`; either knob will skip freshclam.
- **`TAINTED_BUILD` env var** — baked into every image; `true` if built with `UNSAFE_SSL=true`, `false` otherwise. A login warning is displayed to the user when `TAINTED_BUILD=true`.

## Docker-out-of-Docker

All codemonkey-based containers include `docker-ce-cli` and `docker-buildx-plugin`. When launched via `primate()`, the host's `/var/run/docker.sock` is bind-mounted automatically (if present). Two ways to use the daemon from inside a primate:

- **`sudo docker …`** — works immediately. `codemonkey` has NOPASSWD sudo, so this is the simplest path for scripts and `make` invocations.
- **Plain `docker …`** — `zshrc.template` adds `codemonkey` to a group matching the socket's GID on first login, but `usermod -aG` doesn't update an already-running shell's credentials. After exiting and re-entering the container (or `newgrp <group>`), plain `docker` works without sudo.

This means you can build primate images from inside a running container:

```bash
cd workspace/primates   # assuming code-monkeys repo is the workspace
sudo make all           # builds all images via the host daemon
```
