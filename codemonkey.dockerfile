# docker buildx build -t codemonkey:latest -f ./codemonkey.dockerfile .
FROM debian:13-slim
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Avoid warnings by switching to noninteractive
ENV DEBIAN_FRONTEND=noninteractive

# The image comes with a base non-root 'codemonkey' user which this Dockerfile
# gives sudo access. However, for Linux, this user's GID/UID must match your local
# user UID/GID to avoid permission issues with bind mounts. Update USER_UID / USER_GID
# if yours is not 1000. See https://aka.ms/vscode-remote/containers/non-root-user.
ARG USER_UID=1000
ARG USER_GID=$USER_UID
ARG UNSAFE_SSL=false
ARG FRESH=true

# We are all just code monkeys at heart
RUN useradd \
    --home-dir /home/codemonkey \
    --shell /bin/zsh \
    --comment "Code Monkey,,," \
    codemonkey

COPY zaliases /home/codemonkey/.zaliases
COPY zbase /home/codemonkey/.zbase
COPY zprofile /home/codemonkey/.zprofile
COPY gitignore /home/codemonkey/.gitignore
COPY vimrc /home/codemonkey/.vimrc
COPY toprc /home/codemonkey/.toprc

# Configure apt and install packages
RUN apt-get update \
    && apt-get -y install --no-install-recommends apt-utils dialog 2>&1 \
    #
    # Verify git and needed tools are installed
    && apt-get install -y git procps \
    #
    # Create a non-root user to use if preferred - see https://aka.ms/vscode-remote/containers/non-root-user.
    && if [ "$USER_GID" != "1000" ]; then groupmod node --gid $USER_GID; fi \
    && if [ "$USER_UID" != "1000" ]; then usermod --uid $USER_UID node; fi \
    # [Optional] Add sudo support for non-root users
    && apt-get install -y sudo \
    && echo "codemonkey ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/codemonkey \
    && chmod 0440 /etc/sudoers.d/codemonkey \
    && passwd -d codemonkey \
    && chown -R codemonkey:codemonkey /home/codemonkey 

# dev tools
RUN apt-get -y install \
      ssh \
      locales \
      build-essential \
      bsdmainutils \
      cmake \
      python3 \
      graphicsmagick \
      libsixel-bin \
      clamav \
      nmap \
      curl \
      vim-nox \
      curl \
      wget \
      rsync \
      zip \
      tree \
      tmux \
      unzip \
      p7zip-full \
      zsh \
      nodejs \
      npm

# AWS CLI v2
RUN curl $([ "$UNSAFE_SSL" = "true" ] && echo "--insecure") -sL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o /tmp/awscliv2.zip \
  && unzip -q /tmp/awscliv2.zip -d /tmp \
  && /tmp/aws/install \
  && rm -rf /tmp/aws /tmp/awscliv2.zip

# Docker CLI + Buildx (for Docker-out-of-Docker via socket mount)
RUN install -m 0755 -d /etc/apt/keyrings \
  && curl $([ "$UNSAFE_SSL" = "true" ] && echo "--insecure") -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
  && chmod a+r /etc/apt/keyrings/docker.asc \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list \
  && if [ "$UNSAFE_SSL" = "true" ]; then echo 'Acquire::https::Verify-Peer "false";' > /etc/apt/apt.conf.d/99no-ssl-verify; fi \
  && apt-get update \
  && apt-get install -y --no-install-recommends docker-ce-cli docker-buildx-plugin \
  && rm -f /etc/apt/apt.conf.d/99no-ssl-verify \
  && rm -rf /var/lib/apt/lists/*

# make clams fresh (skip if FRESH=false, or if UNSAFE_SSL=true since freshclam requires valid certs)
RUN if [ "${FRESH}" != "false" ] && [ "${UNSAFE_SSL}" != "true" ]; then \
    freshclam; \
fi;

# Timezone/Locale
ENV TZ=America/Chicago
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen
RUN echo "LANG=en_US.UTF-8" >> /etc/locale.conf
RUN locale-gen && update-locale
ENV LANG=en_US.UTF-8

# Oh My ZSH
RUN if [ "$UNSAFE_SSL" = "true" ]; then \
      git config --global http.sslVerify false; \
      su -c "git config --global http.sslVerify false" codemonkey; \
    fi \
  && su -c "curl $([ "$UNSAFE_SSL" = "true" ] && echo "--insecure") -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh | sh" codemonkey \
  && rm -f /home/codemonkey/.zshrc \
  && git clone https://github.com/zsh-users/zsh-autosuggestions.git /home/codemonkey/.oh-my-zsh/custom/plugins/zsh-autosuggestions \
  && git clone https://github.com/zsh-users/zsh-completions.git /home/codemonkey/.oh-my-zsh/custom/plugins/zsh-completions \
  && git clone https://github.com/zsh-users/zsh-syntax-highlighting /home/codemonkey/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting \
  && if [ "$UNSAFE_SSL" = "true" ]; then \
      git config --global --unset http.sslVerify; \
      su -c "git config --global --unset http.sslVerify" codemonkey; \
    fi
COPY zshrc.template /home/codemonkey/.zshrc
COPY jjh.zsh-theme /home/codemonkey/.oh-my-zsh/custom/themes/jjh.zsh-theme

# Clean up APT when done.
RUN apt-get autoclean -y && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Fix codemonkey perms
RUN chown -R codemonkey:codemonkey /home/codemonkey 

ENV TAINTED_BUILD=${UNSAFE_SSL}

# Fin
