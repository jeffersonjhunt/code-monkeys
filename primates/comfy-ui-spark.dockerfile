# comfy-ui-spark — ComfyUI on the shared CUDA base (runtime flavor).
# The codemonkey user, nvtop, and the sudo/zsh/git/curl floor come from
# cuda-base; ComfyUI rides PyTorch's prebuilt wheels (already multi-arch),
# so it inherits cuda-base's broad TORCH_CUDA_ARCH_LIST and runs on
# sm_89/sm_120/sm_121 without a source build.
ARG CUDA_BASE=cuda-base:runtime
FROM ${CUDA_BASE}

RUN apt-get update \
    && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    libgl1 \
    libglib2.0-0 \
    && apt autoremove -y \
    && apt clean -y \
    && rm -rf /tmp/* /var/tmp/* \
    && find /var/cache/apt/archives /var/lib/apt/lists -not -name lock -type f -delete \
    && find /var/cache -type f -delete

WORKDIR /app

ARG COMFYUI_VERSION=v0.22.0
RUN git clone --branch ${COMFYUI_VERSION} --depth 1 https://github.com/Comfy-Org/ComfyUI.git .

ARG PYTORCH_VERSION=2.11.0
ARG TORCHVISION_VERSION=0.26.0
ARG TORCHAUDIO_VERSION=2.11.0
RUN pip install --break-system-packages \
    torch==${PYTORCH_VERSION} torchvision==${TORCHVISION_VERSION} torchaudio==${TORCHAUDIO_VERSION} \
    --index-url https://download.pytorch.org/whl/cu130

RUN pip install --break-system-packages -r requirements.txt

RUN chown -R codemonkey:codemonkey /app

EXPOSE 8188
USER codemonkey

COPY comfy-ui-spark-entrypoint.sh /usr/local/bin/entrypoint.sh
ENTRYPOINT ["entrypoint.sh"]
