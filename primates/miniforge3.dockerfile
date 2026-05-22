FROM codemonkey:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Add Miniforge3 support (replaces Miniconda — BSD licensed, conda-forge default)
ARG MINIFORGE_VERSION=26.1.0-0
ARG TARGETARCH
ARG IMAGE_NAME=miniforge3
ARG UNSAFE_SSL=false
RUN ARCH=$([ "$TARGETARCH" = "arm64" ] && echo "aarch64" || echo "x86_64") \
    && wget $([ "$UNSAFE_SSL" = "true" ] && echo "--no-check-certificate") https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/Miniforge3-${MINIFORGE_VERSION}-Linux-${ARCH}.sh -O /tmp/miniforge.sh \
    && bash /tmp/miniforge.sh -b -u -p /opt/miniforge3 \
    && rm /tmp/miniforge.sh

# Create the default conda env and install uv into base. uv lands in
# /opt/miniforge3/bin (on PATH for every miniforge3-derived image), giving
# downstream images PEP 621 / uv.lock project workflows (e.g. 007 skills tests).
RUN if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --set ssl_verify false; fi \
    && /opt/miniforge3/bin/conda create -y -n ${IMAGE_NAME}-env python \
    && echo "${IMAGE_NAME}-env" > /opt/miniforge3/.default-env \
    && /opt/miniforge3/bin/conda install -y -n base -c conda-forge uv \
    && if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --remove-key ssl_verify; fi

# Fin
