ARG UBUNTU_VERSION=24.04
ARG CUDA_VERSION=13.1.1

ARG BASE_CUDA_RUN_CONTAINER=nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION}

FROM ${BASE_CUDA_RUN_CONTAINER}

# CUDA architecture for DGX Spark Blackwell GPUs (sm_121)
ARG CUDA_DOCKER_ARCH=121

# Replace the default ubuntu user (UID 1000) with codemonkey so bind
# mounts from the host (workspace, .ssh, .aws) have matching ownership
RUN userdel -r ubuntu 2>/dev/null || true \
    && useradd \
    --uid 1000 \
    --home-dir /home/codemonkey \
    --create-home \
    --shell /bin/zsh \
    --comment "Code Monkey,,," \
    codemonkey

RUN apt-get update \
    && apt-get install -y \
    sudo \
    zsh \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    libgl1 \
    libglib2.0-0 \
    && echo "codemonkey ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/codemonkey \
    && chmod 0440 /etc/sudoers.d/codemonkey \
    && apt autoremove -y \
    && apt clean -y \
    && rm -rf /tmp/* /var/tmp/* \
    && find /var/cache/apt/archives /var/lib/apt/lists -not -name lock -type f -delete \
    && find /var/cache -type f -delete

WORKDIR /app

ARG COMFYUI_VERSION=v0.15.1
RUN git clone --branch ${COMFYUI_VERSION} --depth 1 https://github.com/Comfy-Org/ComfyUI.git .

ARG PYTORCH_VERSION=2.10.0
RUN pip install --break-system-packages \
    torch==${PYTORCH_VERSION} torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu130

RUN pip install --break-system-packages -r requirements.txt

RUN chown -R codemonkey:codemonkey /app

EXPOSE 8188
USER codemonkey

COPY comfy-ui-spark-entrypoint.sh /usr/local/bin/entrypoint.sh
ENTRYPOINT ["entrypoint.sh"]
