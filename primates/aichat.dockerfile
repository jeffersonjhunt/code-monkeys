FROM miniforge3:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Create conda environment for this image (family convention: <image>-env auto-activated at
# login). aichat itself is a static Rust binary and needs no Python, but the env keeps this
# image consistent with the rest of the miniforge3 family.
ARG IMAGE_NAME=aichat
ARG UNSAFE_SSL=false
RUN if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --set ssl_verify false; fi \
    && /opt/miniforge3/bin/conda create -y -n ${IMAGE_NAME}-env python \
    && echo "${IMAGE_NAME}-env" > /opt/miniforge3/.default-env \
    && if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --remove-key ssl_verify; fi

# Install aichat (sigoden/aichat) — a generic OpenAI-compatible chat REPL. Fetch the prebuilt
# static musl binary for THIS host's arch from the latest GitHub release and drop it in
# /usr/local/bin (on PATH, root-owned, OUTSIDE /home/codemonkey so it is not shadowed by the
# <image>-home volume that primate() mounts — same rationale as opencode's binary). aichat has
# no runtime self-update, so the version is image-managed: rebuild to upgrade.
RUN set -eux; \
    K="$([ "$UNSAFE_SSL" = "true" ] && echo --insecure || true)"; \
    case "$(uname -m)" in \
      x86_64)        TRIPLE=x86_64-unknown-linux-musl ;; \
      aarch64|arm64) TRIPLE=aarch64-unknown-linux-musl ;; \
      *) echo "unsupported arch $(uname -m)" >&2; exit 1 ;; \
    esac; \
    URL="$(curl $K -fsSL https://api.github.com/repos/sigoden/aichat/releases/latest \
            | grep -o "https://[^\"]*aichat-v[0-9][^\"]*-${TRIPLE}\.tar\.gz" | head -n1)"; \
    [ -n "$URL" ] || { echo "could not resolve aichat release asset for ${TRIPLE}" >&2; exit 1; }; \
    curl $K -fsSL "$URL" -o /tmp/aichat.tar.gz; \
    tar -xzf /tmp/aichat.tar.gz -C /tmp; \
    install -m0755 "$(find /tmp -maxdepth 2 -name aichat -type f | head -n1)" /usr/local/bin/aichat; \
    rm -rf /tmp/aichat*

# Ship a PLACEHOLDER config only — this image is deliberately g.deceiver-agnostic. The real
# endpoint, models, and Gay's persona role are injected at RUNTIME from the PRIVATE g.deceiver
# repo (its launcher sets AICHAT_CONFIG_DIR to a mounted config dir). Nothing g.deceiver — no
# hostnames, no model names, no persona — is ever baked into this public image. See the
# placeholder file's own comments for the injection contract.
COPY aichat.config.yaml /home/codemonkey/.config/aichat/config.yaml
RUN chown -R codemonkey:codemonkey /home/codemonkey/.config

# Clean up APT when done.
RUN  apt-get autoclean -y \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Fin
