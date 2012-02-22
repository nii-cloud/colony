#!/bin/bash

source common/function.sh
create_datadir "squid"

(
/usr/bin/apt-get -y install squid
)

exit 0
