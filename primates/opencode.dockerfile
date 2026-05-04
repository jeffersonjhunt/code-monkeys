FROM miniforge3:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Create conda environment for this image
ARG IMAGE_NAME=opencode
ARG UNSAFE_SSL=false
RUN if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --set ssl_verify false; fi \
    && /opt/miniforge3/bin/conda create -y -n ${IMAGE_NAME}-env python \
    && echo "${IMAGE_NAME}-env" > /opt/miniforge3/.default-env \
    && if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --remove-key ssl_verify; fi

# Configure apt and install packages
RUN  apt-get update \
  && apt-get -y install npm

# Add Open Code support
RUN if [ "$UNSAFE_SSL" = "true" ]; then npm config set strict-ssl false; fi \
  && npm install -g opencode-ai \
  && if [ "$UNSAFE_SSL" = "true" ]; then npm config delete strict-ssl; fi

# Clean up APT when done.
RUN  apt-get autoclean -y \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Fin
