ARG UBUNTU_VERSION=24.04
ARG CUDA_VERSION=13.1.1

ARG BASE_CUDA_DEV_CONTAINER=nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION}
ARG BASE_CUDA_RUN_CONTAINER=nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION}

FROM ${BASE_CUDA_DEV_CONTAINER} AS build

# sm_121 native + compute_120 PTX fallback. The native sm_121 build of vLLM's
# cutlass extensions is the whole point of this image — upstream vllm-openai
# stops at sm_120 native and crashes on FP8 dense / NVFP4 MoE on DGX Spark.
ARG TORCH_CUDA_ARCH_LIST="8.0 8.7 8.9 9.0 10.0 12.0 12.1+PTX"
ARG VLLM_VERSION=v0.20.1
ARG TORCH_VERSION=2.11.0
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu130

ENV DEBIAN_FRONTEND=noninteractive
ENV TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST}
ENV NVCC_THREADS=4
ENV MAX_JOBS=4
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
# (same pattern as primates/comfy-ui-spark.dockerfile). PEP 440 makes
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

# Build vLLM with the explicit arch list so cutlass blobs come out as sm_121.
RUN cd vllm && pip install . --no-build-isolation

RUN python3 -c 'import vllm; print("vllm", vllm.__version__)' \
 && python3 -c 'import torch; print("torch", torch.__version__, "cuda:", torch.version.cuda)'


FROM ${BASE_CUDA_RUN_CONTAINER} AS runtime

# Replace default ubuntu user (UID 1000) with codemonkey so bind mounts from
# the host (workspace, .ssh, .aws) have matching ownership. Same pattern as
# llama-cpp-spark.dockerfile.
RUN userdel -r ubuntu 2>/dev/null || true \
    && useradd \
       --uid 1000 \
       --home-dir /home/codemonkey \
       --create-home \
       --shell /bin/zsh \
       --comment "Code Monkey,,," \
       codemonkey

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        sudo \
        zsh \
        python3 \
        python3-venv \
        ca-certificates \
        libgomp1 \
    && echo "codemonkey ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/codemonkey \
    && chmod 0440 /etc/sudoers.d/codemonkey \
    && apt autoremove -y \
    && apt clean -y \
    && rm -rf /tmp/* /var/tmp/* \
    && find /var/cache/apt/archives /var/lib/apt/lists -not -name lock -type f -delete \
    && find /var/cache -type f -delete

COPY --from=build /opt/venv /opt/venv

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
