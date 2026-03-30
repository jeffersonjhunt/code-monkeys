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
COPY gitconfig /home/codemonkey/.gitconfig
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
      zip \
      tree \
      unzip \
      p7zip-full \
      zsh \
      nodejs \
      npm

# AWS CLI v2
RUN curl -sL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o /tmp/awscliv2.zip \
  && unzip -q /tmp/awscliv2.zip -d /tmp \
  && /tmp/aws/install \
  && rm -rf /tmp/aws /tmp/awscliv2.zip

# make clams fresh
RUN if [ "${FRESH}" != "false" ]; then \
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
RUN su -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" codemonkey \
  && rm -f /home/codemonkey/.zshrc \
  && git clone https://github.com/zsh-users/zsh-autosuggestions.git /home/codemonkey/.oh-my-zsh/custom/plugins/zsh-autosuggestions \
  && git clone https://github.com/zsh-users/zsh-completions.git /home/codemonkey/.oh-my-zsh/custom/plugins/zsh-completions \
  && git clone https://github.com/zsh-users/zsh-syntax-highlighting /home/codemonkey/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting
COPY zshrc.template /home/codemonkey/.zshrc
COPY jjh.zsh-theme /home/codemonkey/.oh-my-zsh/custom/themes/jjh.zsh-theme

# Clean up APT when done.
RUN apt-get autoclean -y && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Fix codemonkey perms
RUN chown -R codemonkey:codemonkey /home/codemonkey 

# Fin
