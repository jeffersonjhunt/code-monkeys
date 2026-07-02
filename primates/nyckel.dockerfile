# docker buildx build -t nyckel:latest -f ./nyckel.dockerfile .
#
# nyckel ("key") — the fleet's minimal secrets-ops primate: just `age` + `sops` on Alpine, for the
# SOPS/age-encrypted secrets in the `hemlighet` repo. Deliberately NOT built FROM codemonkey — a
# secrets-handling image should carry nothing but the two tools, so it stays tiny, builds on any host
# (both arches, no base dependency), and has a small attack surface. Always run CONTAINERIZED —
# `docker run --rm nyckel age-keygen` / `docker run --rm nyckel sops ...` — never installed on a host
# or a Mac (no brew, ever; see the containerize-tooling-deps rule).
#
# Multi-arch: age/sops publish linux amd64+arm64 assets whose suffix matches $TARGETARCH directly.
# TODO(hardening): verify release checksums before install.
FROM alpine:3.21
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"
ARG TARGETARCH
ARG AGE_VERSION=v1.3.1
ARG SOPS_VERSION=v3.13.2
RUN set -eux; \
    apk add --no-cache ca-certificates curl tar; \
    curl -fsSL "https://github.com/FiloSottile/age/releases/download/${AGE_VERSION}/age-${AGE_VERSION}-linux-${TARGETARCH}.tar.gz" | tar -xz -C /tmp; \
    install -m0755 /tmp/age/age        /usr/local/bin/age; \
    install -m0755 /tmp/age/age-keygen /usr/local/bin/age-keygen; \
    rm -rf /tmp/age; \
    curl -fsSL -o /usr/local/bin/sops "https://github.com/getsops/sops/releases/download/${SOPS_VERSION}/sops-${SOPS_VERSION}.linux.${TARGETARCH}"; \
    chmod 0755 /usr/local/bin/sops; \
    age --version; sops --version

# No ENTRYPOINT: invoke a tool explicitly — `docker run --rm nyckel <age|age-keygen|sops> ...`.

# Fin
