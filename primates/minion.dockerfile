# docker buildx build -t minion:latest -f ./minion.dockerfile .
FROM codemonkey:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Ops/secrets tooling for the fleet's SOPS + age secrets (the `hemlighet` repo). It lives in this
# minimal utility primate so it is always run CONTAINERIZED — `docker run --rm minion age-keygen` /
# `docker run --rm minion sops ...` — and NEVER installed on a host or a Mac (no brew, ever; see the
# containerize-tooling-deps rule). Multi-arch: age/sops publish linux amd64+arm64 assets whose suffix
# matches $TARGETARCH (amd64|arm64) directly.
# TODO(hardening): verify release checksums before install.
ARG TARGETARCH
ARG AGE_VERSION=v1.3.1
ARG SOPS_VERSION=v3.13.2
RUN set -eux; \
    curl -fsSL "https://github.com/FiloSottile/age/releases/download/${AGE_VERSION}/age-${AGE_VERSION}-linux-${TARGETARCH}.tar.gz" | tar -xz -C /tmp; \
    install -m0755 /tmp/age/age         /usr/local/bin/age; \
    install -m0755 /tmp/age/age-keygen  /usr/local/bin/age-keygen; \
    rm -rf /tmp/age; \
    curl -fsSL -o /usr/local/bin/sops "https://github.com/getsops/sops/releases/download/${SOPS_VERSION}/sops-${SOPS_VERSION}.linux.${TARGETARCH}"; \
    chmod 0755 /usr/local/bin/sops; \
    age --version; sops --version

# Fin
