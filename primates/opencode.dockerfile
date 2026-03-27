FROM miniforge3:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Create conda environment for this image
ARG IMAGE_NAME=opencode
RUN /opt/miniforge3/bin/conda create -y -n ${IMAGE_NAME}-env python \
    && echo "${IMAGE_NAME}-env" > /opt/miniforge3/.default-env

# Configure apt and install packages
RUN  apt-get update \
  && apt-get -y install npm

# Add Open Code support
RUN npm install -g opencode-ai

# Clean up APT when done.
RUN  apt-get autoclean -y \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Fin
