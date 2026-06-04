# cuda-base — shared base for the NVIDIA/CUDA primate family.
#
# One dockerfile, two flavors selected by CUDA_FLAVOR:
#   make cuda-base.build  ->  cuda-base:runtime  AND  cuda-base:devel
#
#   cuda-base:runtime  — slim; for images that only run prebuilt binaries
#                        (comfy-ui-spark; llama-cpp-spark final stages).
#   cuda-base:devel    — ships nvcc + headers; for images that JIT-compile
#                        CUDA at runtime (vllm-spark, whose FlashInfer/Triton
#                        paths shell out to nvcc on the first forward pass).
#
# Cross-GPU by design. nvidia/cuda:* is a multi-arch manifest, so buildx
# resolves x86_64 vs aarch64 from the build host automatically. The arch
# defaults below span every GPU this family targets:
#   sm_89  — RTX 4090 (Ada, x86)
#   sm_120 — RTX 5090 (Blackwell, x86)
#   sm_121 — DGX Spark GB10 (Blackwell, aarch64)
# These are defaults, not mandates: an image with an expensive source build
# (vllm-spark) narrows the list to its host arch to keep build time sane.

ARG UBUNTU_VERSION=24.04
ARG CUDA_VERSION=13.2.1
# runtime | devel — overridden per build by the Makefile to emit both tags.
ARG CUDA_FLAVOR=runtime

ARG BASE_CUDA_CONTAINER=nvidia/cuda:${CUDA_VERSION}-${CUDA_FLAVOR}-ubuntu${UBUNTU_VERSION}

FROM ${BASE_CUDA_CONTAINER}

ENV DEBIAN_FRONTEND=noninteractive

# Cross-GPU compile/JIT defaults. Children that source-build (vllm-spark)
# override these to a single host arch; PyTorch-wheel images (comfy-ui-spark)
# inherit the broad list so custom-node CUDA ops compile for any of the three.
ARG TORCH_CUDA_ARCH_LIST="8.9 12.0 12.1+PTX"
ARG CUDA_DOCKER_ARCH="89;120;121"
ENV TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST}
ENV CUDA_DOCKER_ARCH=${CUDA_DOCKER_ARCH}

# Replace the default ubuntu user (UID 1000) with codemonkey so bind mounts
# from the host (workspace, .ssh, .aws) have matching ownership. This block
# was previously duplicated verbatim across comfy/vllm/llama-cpp.
RUN userdel -r ubuntu 2>/dev/null || true \
    && useradd \
       --uid 1000 \
       --home-dir /home/codemonkey \
       --create-home \
       --shell /bin/zsh \
       --comment "Code Monkey,,," \
       codemonkey

# Common floor for every CUDA image. nvtop (GPU process monitor, from the
# Ubuntu universe pocket) is the reason this base exists; the rest is the
# shell/sudo/git/curl set every child needed anyway. Children add their own
# specifics (python3-dev, libgl1, libgomp1, gcc/g++, ...) on top.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       nvtop \
       sudo \
       zsh \
       git \
       curl \
       ca-certificates \
    && echo "codemonkey ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/codemonkey \
    && chmod 0440 /etc/sudoers.d/codemonkey \
    && apt autoremove -y \
    && apt clean -y \
    && rm -rf /tmp/* /var/tmp/* \
    && find /var/cache/apt/archives /var/lib/apt/lists -not -name lock -type f -delete \
    && find /var/cache -type f -delete
