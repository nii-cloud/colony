#!/bin/bash

source common/function.sh

a2dismod wsgi

remove_templates "apache" "colony_mod_wsgi"

apt-get -y remove libapache2-mod-wsgi

