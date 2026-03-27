# docker buildx build -t huggingface:latest -f ./huggingface.dockerfile .
FROM codemonkey:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Install python3 venv (prerequisite for huggingface-cli)
RUN  apt-get update \
  && apt-get -y install \
        python3.13-venv

# Install huggingface-cli
RUN export HF_HOME=/usr/local HF_CLI_BIN_DIR=/usr/local/bin \
  && curl -LsSf https://hf.co/cli/install.sh | bash -s -- --no-modify-path

# Clean up APT when done.
RUN  apt-get autoclean -y \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Fin
