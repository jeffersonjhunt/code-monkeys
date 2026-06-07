ARG UBUNTU_VERSION=24.04
ARG CUDA_VERSION=13.2.1

ARG BASE_CUDA_DEV_CONTAINER=nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION}
# Runtime extends cuda-base:devel (the devel flavor, NOT :runtime) because
# Triton JIT needs a host C compiler and FlashInfer's py3-none-any wheel JITs
# CUDA kernels via nvcc at first use. The runtime flavor lacks both. Image
# size cost is ~4-5 GB.
ARG CUDA_BASE=cuda-base:devel

FROM ${BASE_CUDA_DEV_CONTAINER} AS build

# Cross-GPU: sm_89 (RTX 4090 / Ada) + sm_120 (RTX 5090) + sm_121 (DGX Spark
# GB10) native, with sm_121 PTX fallback. The native sm_121 build of vLLM's
# cutlass extensions is the whole reason this image exists — upstream
# vllm-openai stops at sm_120 native and crashes on FP8 dense / NVFP4 MoE on
# DGX Spark. Including 8.9 keeps the image runnable on the 4090 boxes too
# (~1.5 GB larger than a Spark-only build). Override to "12.0 12.1+PTX" for a
# slimmer Spark-only build.
ARG TORCH_CUDA_ARCH_LIST="8.9 12.0 12.1+PTX"
ARG VLLM_VERSION=v0.21.0
# Keep TORCH_VERSION at 2.11.0: vLLM v0.21.0's requirements/cuda.txt still
# pins torch==2.11.0 / torchvision==0.26.0 / torchaudio==2.11.0. Bumping
# torch here would conflict with vLLM's resolver during the pip step.
ARG TORCH_VERSION=2.11.0
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu130

ENV DEBIAN_FRONTEND=noninteractive
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=/opt/venv/bin:${CUDA_HOME}/bin:${PATH}

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        git \
        python3 \
        python3-dev \
        python3-venv \
        python3-pip \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Relocatable venv at /opt/venv (same path in runtime stage so shebangs work).
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip wheel setuptools

# PyTorch must be present before building vLLM extensions. cu131 wheels do
# not exist for aarch64; cu130 wheel runs fine on a cu131.x runtime base
# (same pattern as primates/cuda-comfy.dockerfile). PEP 440 makes
# torch==2.11.0+cu130 satisfy any subsequent torch==2.11.0 requirement.
RUN pip install torch==${TORCH_VERSION} --index-url ${TORCH_INDEX}

WORKDIR /opt/build
RUN git clone --depth 1 --branch ${VLLM_VERSION} https://github.com/vllm-project/vllm.git

# Pre-install vLLM's runtime deps with default per-package build isolation —
# transitive sdists like fastsafetensors need pybind11 etc. at metadata-prep
# time, which --no-build-isolation would block. --extra-index-url ensures
# any torch reinstall resolves to the cu130 wheel.
RUN pip install --extra-index-url ${TORCH_INDEX} -r vllm/requirements/cuda.txt

# vLLM's [build-system].requires from pyproject.toml — must be present for
# the no-build-isolation install of vllm itself. setuptools pinned <81.
RUN pip install \
        "cmake>=3.26.1" \
        ninja \
        "packaging>=24.2" \
        "setuptools>=77.0.3,<81.0.0" \
        "setuptools-scm>=8.0" \
        wheel \
        jinja2

# Compile-tunables placed AFTER the multi-minute cached install steps so
# future tweaks don't invalidate apt/torch/cuda.txt layers.
#
# vLLM's setup.py:191 computes ninja -j as (MAX_JOBS // NVCC_THREADS).
# Heavy cutlass templates (NVFP4, MLA, machete, qutlass) want 10–15 GB each.
# Defaults (MAX_JOBS=16 / NVCC_THREADS=4 → 4 parallel ninja jobs, ~48–60 GB
# peak) are sized for a 121 GB DGX Spark. On a low-RAM x86 host (the 4090 boxes
# have ~30 GB) override BOTH to a small equal value to force a single parallel
# job, e.g. --build-arg MAX_JOBS=6 --build-arg NVCC_THREADS=6 → 1 ninja job,
# ~15 GB peak. Slower (cutlass templates compile mostly serially) but fits.
ARG MAX_JOBS=16
ARG NVCC_THREADS=4
ENV TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST}
ENV NVCC_THREADS=${NVCC_THREADS}
ENV MAX_JOBS=${MAX_JOBS}

# Build vLLM with the explicit arch list so cutlass blobs come out as sm_121.
RUN cd vllm && pip install . --no-build-isolation

RUN python3 -c 'import vllm; print("vllm", vllm.__version__)' \
 && python3 -c 'import torch; print("torch", torch.__version__, "cuda:", torch.version.cuda)'


FROM ${CUDA_BASE} AS runtime

# Match the build stage's arch list so FlashInfer/Triton runtime JIT emit the
# right cubins at first forward pass (sm_89 on the 4090s, sm_120/sm_121 on
# Blackwell). cuda-base already sets this, but pin it explicitly here so the
# image is self-describing regardless of base drift.
ENV TORCH_CUDA_ARCH_LIST="8.9 12.0 12.1+PTX"

# codemonkey user, nvtop, sudo/zsh/ca-certificates come from cuda-base. This
# adds vLLM's runtime extras (python3 + the gcc/g++/libgomp1 the JIT paths
# shell out to).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-dev \
        python3-venv \
        libgomp1 \
        gcc \
        g++ \
    && apt autoremove -y \
    && apt clean -y \
    && rm -rf /tmp/* /var/tmp/* \
    && find /var/cache/apt/archives /var/lib/apt/lists -not -name lock -type f -delete \
    && find /var/cache -type f -delete

COPY --from=build /opt/venv /opt/venv

# Slim the runtime image. The cu131-devel base ships nvcc + headers (kept for
# Triton/FlashInfer JIT) plus link-time-only static archives and CUDA samples
# we'll never use.
#
# DO NOT pip-uninstall cmake/ninja from the venv — FlashInfer's NVFP4 cutlass
# GEMM JIT path shells out to ninja at first NVFP4 forward pass.
RUN find /usr/local/cuda* -name "*_static.a" -delete 2>/dev/null \
    && rm -rf /usr/local/cuda*/extras /usr/local/cuda*/samples /usr/local/cuda*/tools 2>/dev/null \
    || true

ENV PATH=/opt/venv/bin:${PATH}
ENV PYTHONUNBUFFERED=1
ENV VLLM_USAGE_SOURCE=docker

EXPOSE 8000

# Healthcheck via stdlib (runtime base has no curl/wget by default).
HEALTHCHECK --interval=30s --timeout=10s --start-period=5m --retries=3 \
    CMD python3 -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status==200 else 1)"

USER codemonkey
WORKDIR /home/codemonkey

ENTRYPOINT ["python3", "-m", "vllm.entrypoints.openai.api_server"]
