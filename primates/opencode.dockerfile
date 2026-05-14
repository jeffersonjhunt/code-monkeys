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

# Point opencode at the spark-cluster vLLM (HAProxy on starsky:8080).
# apiKey is hardcoded in the json (vLLM ignores it; OpenAI-compatible SDK
# just requires non-empty). To use a real provider key, drop a project-
# local opencode.json in the working dir or edit ~/.config/opencode/.
COPY opencode.json /home/codemonkey/.config/opencode/opencode.json
RUN chown -R codemonkey:codemonkey /home/codemonkey/.config

# Clean up APT when done.
RUN  apt-get autoclean -y \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Fin
