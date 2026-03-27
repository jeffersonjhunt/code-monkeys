# docker buildx build -t lamp:latest -f ./lamp.dockerfile .
FROM codemonkey:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

# Configure apt and install LAMP packages
RUN  apt-get update \
  && apt-get -y install \
        apache2 \
        mariadb-server \
        php \
        libapache2-mod-php \
        php-mysql

# Clean up APT when done.
RUN  apt-get autoclean -y \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Fin
