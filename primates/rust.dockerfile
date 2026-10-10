# docker buildx build -t rust:latest -f ./rust.dockerfile .
FROM codemonkey:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

ARG UNSAFE_SSL=false

# Rust toolchain via rustup — plain stable, with clippy and rustfmt.
#
# Installed into /opt/rust, NOT /home/codemonkey, for the same reason opencode's binary
# lives in /usr/local/bin: the <image>-home volume that primate() mounts would otherwise
# shadow a toolchain under $HOME. RUSTUP_HOME (the toolchains) and the cargo/rustc proxy
# binaries sit in /opt/rust, world-readable; the toolchain is image-managed, so rebuild to
# upgrade (`rustup update` can't write /opt). At runtime CARGO_HOME points at ~/.cargo in
# the home volume, so the per-user crate registry cache, config and `cargo install` output
# persist there and stay writable; ~/.cargo/bin is on PATH so installed tools are found.
RUN curl $([ "$UNSAFE_SSL" = "true" ] && echo "--insecure") --proto '=https' --tlsv1.2 -sSf \
      https://sh.rustup.rs -o /tmp/rustup-init.sh \
  && RUSTUP_HOME=/opt/rust/rustup CARGO_HOME=/opt/rust/cargo \
     sh /tmp/rustup-init.sh -y --no-modify-path \
       --profile minimal --default-toolchain stable --component rustfmt --component clippy \
  && rm -f /tmp/rustup-init.sh \
  && chmod -R a+rX /opt/rust

ENV RUSTUP_HOME=/opt/rust/rustup \
    CARGO_HOME=/home/codemonkey/.cargo \
    PATH=/opt/rust/cargo/bin:/home/codemonkey/.cargo/bin:$PATH

# Prove the toolchain and both components resolve under the runtime env.
RUN rustc --version \
  && cargo --version \
  && cargo clippy --version \
  && cargo fmt --version

# Fin
