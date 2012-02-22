#!/bin/bash

source common/function.sh

a2dismod shib2
a2dissite default-shib

remove_templates "apache" "colony_mod_shib2"

apt-get -y remove libapache2-mod-shib2


