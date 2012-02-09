#!/bin/bash

PACKAGE=libapache2-mod-shib2

if `dpkg-query -W ${PACKAGE} &> /dev/null` ; then 
  apt-get -y install ${PACKAGE}
fi

exit 0
