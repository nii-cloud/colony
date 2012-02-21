#!/bin/bash

source common/function.sh

a2dismod wsgi

apt-get -y remove libapache2-mod-wsgi

remove_templates "colony_mod_wsgi"
