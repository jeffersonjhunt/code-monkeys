FROM codemonkey:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Add Miniforge3 support (replaces Miniconda — BSD licensed, conda-forge default)
ARG MINIFORGE_VERSION=26.1.0-0
ARG TARGETARCH
ARG IMAGE_NAME=miniforge3
RUN ARCH=$([ "$TARGETARCH" = "arm64" ] && echo "aarch64" || echo "x86_64") \
    && wget https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/Miniforge3-${MINIFORGE_VERSION}-Linux-${ARCH}.sh -O /tmp/miniforge.sh \
    && bash /tmp/miniforge.sh -b -u -p /opt/miniforge3 \
    && rm /tmp/miniforge.sh

RUN /opt/miniforge3/bin/conda create -y -n ${IMAGE_NAME}-env python \
    && echo "${IMAGE_NAME}-env" > /opt/miniforge3/.default-env

# Fin
