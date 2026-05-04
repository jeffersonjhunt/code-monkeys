FROM miniforge3:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Create conda environment for this image
ARG IMAGE_NAME=claude
ARG UNSAFE_SSL=false
RUN if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --set ssl_verify false; fi \
    && /opt/miniforge3/bin/conda create -y -n ${IMAGE_NAME}-env python \
    && echo "${IMAGE_NAME}-env" > /opt/miniforge3/.default-env \
    && if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --remove-key ssl_verify; fi

# Install Claude Code via native installer (npm is deprecated)
RUN su -c "curl $([ "$UNSAFE_SSL" = "true" ] && echo "--insecure") -fsSL https://claude.ai/install.sh | bash" codemonkey

# Claude Code configuration (settings + custom commands)
COPY --chown=codemonkey:codemonkey claude/settings.json /home/codemonkey/.claude/settings.json
COPY --chown=codemonkey:codemonkey claude/commands/ /home/codemonkey/.claude/commands/
# Fin
