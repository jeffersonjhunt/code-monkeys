# docker buildx build -t minion:latest -f ./minion.dockerfile .
FROM codemonkey:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Configure apt and install packages
RUN  apt-get update \
  && apt-get -y install \
        libfmt-dev \
        libboost-dev \
        cc65 \
        cc65-doc

# vasm support (URL is plain HTTP — UNSAFE_SSL doesn't apply)
RUN curl -v http://sun.hasenbraten.de/vasm/release/vasm.tar.gz -o /tmp/vasm.tar.gz \
  && cd /tmp \
  && tar zxvf vasm.tar.gz \
  && cd vasm \
  && make CPU=6502 SYNTAX=oldstyle \
  && cp vasm6502_oldstyle /usr/local/bin \
  && cd .. \
  && rm -rf vasm*

# Clean up APT when done.
RUN  apt-get autoclean -y \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Fin
