# Build stage stays on the raw CUDA devel image (throwaway — only its
# compiled artifacts are copied forward). The shipping stages extend the
# shared cuda-base:runtime, which provides the codemonkey user, nvtop, and
# the sudo/zsh/curl floor.
ARG UBUNTU_VERSION=24.04
ARG CUDA_VERSION=13.2.1

ARG BASE_CUDA_DEV_CONTAINER=nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION}
ARG CUDA_BASE=cuda-base:runtime

FROM ${BASE_CUDA_DEV_CONTAINER} AS build

# Cross-GPU by default: sm_89 (RTX 4090) + sm_120 (RTX 5090) + sm_121 (DGX
# Spark). llama.cpp's CUDA build is cheap and low-RAM, so building all three
# is fine on any of the boxes. Override to a single arch (e.g. "121") for a
# slimmer, faster single-target build.
ARG CUDA_DOCKER_ARCH=89;120;121

# Clone llama.cpp at build time
ARG LLAMA_CPP_VERSION=b9296

RUN apt-get update && \
    apt-get install -y build-essential cmake python3 python3-pip git libcurl4-openssl-dev libgomp1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone llama.cpp repository
RUN git clone https://github.com/ggml-org/llama.cpp.git . && \
    git checkout ${LLAMA_CPP_VERSION}

# Build with explicit CUDA architecture for DGX Spark
RUN if [ "${CUDA_DOCKER_ARCH}" != "default" ]; then \
    export CMAKE_ARGS="-DCMAKE_CUDA_ARCHITECTURES=${CUDA_DOCKER_ARCH}"; \
    fi && \
    cmake -B build -DGGML_CUDA=ON -DCMAKE_EXE_LINKER_FLAGS="-lcuda" ${CMAKE_ARGS} && \
    cmake --build build -j$(nproc)

RUN mkdir -p /app/lib && \
    find build -name "*.so*" -exec cp -P {} /app/lib \;

RUN mkdir -p /app/full \
    && cp build/bin/* /app/full \
    && cp *.py /app/full \
    && cp -r gguf-py /app/full \
    && cp -r requirements /app/full \
    && cp requirements.txt /app/full \
    && cp .devops/tools.sh /app/full/tools.sh

## Base image — codemonkey user, nvtop, sudo/zsh/curl come from cuda-base.
FROM ${CUDA_BASE} AS base

RUN apt-get update \
    && apt-get install -y libgomp1 \
    && apt autoremove -y \
    && apt clean -y \
    && rm -rf /tmp/* /var/tmp/* \
    && find /var/cache/apt/archives /var/lib/apt/lists -not -name lock -type f -delete \
    && find /var/cache -type f -delete

COPY --from=build /app/lib/ /app
RUN chown -R codemonkey:codemonkey /app

### Full
FROM base AS full

COPY --from=build /app/full /app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y \
    git \
    python3 \
    python3-pip \
    && pip install --break-system-packages -r requirements.txt \
    && apt autoremove -y \
    && apt clean -y \
    && rm -rf /tmp/* /var/tmp/* \
    && find /var/cache/apt/archives /var/lib/apt/lists -not -name lock -type f -delete \
    && find /var/cache -type f -delete


USER codemonkey
ENTRYPOINT ["/app/tools.sh"]

### Light, CLI only
FROM base AS light

COPY --from=build /app/full/llama-cli /app

WORKDIR /app

USER codemonkey
ENTRYPOINT [ "/app/llama-cli" ]

### Server, Server only
FROM base AS server

ENV LLAMA_ARG_HOST=0.0.0.0

COPY --from=build /app/full/llama-server /app

WORKDIR /app

HEALTHCHECK CMD [ "curl", "-f", "http://localhost:8080/health" ]

USER codemonkey
ENTRYPOINT [ "/app/llama-server" ]
