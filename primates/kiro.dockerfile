FROM miniforge3:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Create conda environment for this image
ARG IMAGE_NAME=kiro
ARG UNSAFE_SSL=false
RUN if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --set ssl_verify false; fi \
    && /opt/miniforge3/bin/conda create -y -n ${IMAGE_NAME}-env python \
    && echo "${IMAGE_NAME}-env" > /opt/miniforge3/.default-env \
    && if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --remove-key ssl_verify; fi

# Install Kiro CLI via native installer
RUN su -c "curl $([ "$UNSAFE_SSL" = "true" ] && echo "--insecure") -fsSL https://cli.kiro.dev/install | bash" codemonkey

# Install Playwright Chromium and its system deps for MCP browser automation
RUN npx playwright install --with-deps chromium

# Fin
