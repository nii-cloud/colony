#!/bin/bash

PACKAGE=libapache2-mod-shib2

if `dpkg-query -W ${PACKAGE} &> /dev/null` ; then
  apt-get -y install ${PACKAGE}

  # dirty fix for mod_shib2
  cp -a softwares/apache/data/libapache2-mod-shib2.postinst /var/lib/dpkg/info/
  dpkg-reconfigure --force libapache2-mod-shib2
fi
