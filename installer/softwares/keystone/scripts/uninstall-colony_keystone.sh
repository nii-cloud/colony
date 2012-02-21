#!/bin/bash

source common/function.sh

basedir=/usr/local/bin

echo "uninstall colony-horizon"

apt-get -y remove python-dev libxml2-dev libxslt1-dev libsasl2-dev libsqlite3-dev libssl-dev libldap2-dev
apt-get -y remove libjs-jquery python-eventlet python-formencode python-greenlet python-lxml python-openid python-openssl python-paste python-pastedeploy python-pastescript python-routes python-scgi python-sqlalchemy python-sqlalchemy-ext python-webob python-ldap

pip uninstall -y keystone

for com in keystone keystone-admin keystone-auth keystone-control keystone-import keystone-manage
do
   echo "removing $basedir/$com"
   rm -rf $basedir/$com
done

remove_templates "keystone"
