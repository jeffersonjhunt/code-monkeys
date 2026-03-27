ARG UBUNTU_VERSION=24.04
ARG CUDA_VERSION=13.1.1

ARG BASE_CUDA_DEV_CONTAINER=nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION}
ARG BASE_CUDA_RUN_CONTAINER=nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION}

FROM ${BASE_CUDA_DEV_CONTAINER} AS build

# CUDA architecture for DGX Spark Blackwell GPUs (sm_121)
ARG CUDA_DOCKER_ARCH=121

# Clone llama.cpp at build time
ARG LLAMA_CPP_VERSION=b8192

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

## Base image
FROM ${BASE_CUDA_RUN_CONTAINER} AS base

# Create codemonkey user for primate launcher compatibility
RUN useradd \
    --home-dir /home/codemonkey \
    --create-home \
    --shell /bin/zsh \
    --comment "Code Monkey,,," \
    codemonkey

RUN apt-get update \
    && apt-get install -y libgomp1 curl sudo zsh \
    && echo "codemonkey ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/codemonkey \
    && chmod 0440 /etc/sudoers.d/codemonkey \
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
