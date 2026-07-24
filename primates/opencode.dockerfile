FROM miniforge3:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Create conda environment for this image
ARG IMAGE_NAME=opencode
ARG UNSAFE_SSL=false
RUN if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --set ssl_verify false; fi \
    && /opt/miniforge3/bin/conda create -y -n ${IMAGE_NAME}-env python \
    && echo "${IMAGE_NAME}-env" > /opt/miniforge3/.default-env \
    && if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --remove-key ssl_verify; fi

# Add Open Code support via curl installer. The installer hardcodes its target
# to $HOME/.opencode/bin, so install under a throwaway HOME and relocate the
# binary into /usr/local/bin (on PATH, root-owned). Keeping it outside
# /home/codemonkey means it is not shadowed by the primate-home volume mount,
# so the version is image-managed: rebuild this image to upgrade. Runtime
# self-update is disabled in opencode.json since it cannot write here.
RUN export HOME=/tmp/oc \
  && mkdir -p "$HOME" \
  && curl $([ "$UNSAFE_SSL" = "true" ] && echo "--insecure") -fsSL https://opencode.ai/install | bash -s -- --no-modify-path \
  && install -m 0755 "$HOME/.opencode/bin/opencode" /usr/local/bin/opencode \
  && rm -rf "$HOME"

# Ship the PLACEHOLDER config (opencode.json.example) — this PUBLIC image is generic and
# buildable by anyone. The real config (real LiteLLM host, the g.deceiver-facing model list,
# and the corpus MCP URL) is gitignored here and lives SOPS+age-encrypted in the private
# hemlighet repo; `make opencode.upgrade` decrypts + syncs it into the opencode-home volume
# at runtime (which shadows this baked file anyway). apiKey is a non-empty placeholder (vLLM
# ignores it; the OpenAI-compatible SDK just requires it be set). To use a different endpoint,
# edit the config in ~/.config/opencode/ or drop a project-local opencode.json in the cwd.
COPY opencode.json.example /home/codemonkey/.config/opencode/opencode.json
RUN chown -R codemonkey:codemonkey /home/codemonkey/.config

# Clean up APT when done.
RUN  apt-get autoclean -y \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Fin
