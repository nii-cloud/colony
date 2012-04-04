#!/bin/bash


colony_keystone_dir="../keystone/"
cwd=`pwd`

source common/function.sh
create_datadir "keystone"

pushd $colony_keystone_dir

apt-get -y install python-dev libxml2-dev libxslt1-dev libsasl2-dev libsqlite3-dev libssl-dev libldap2-dev
apt-get -y install libjs-jquery libxml2 libxslt1.1 python-eventlet python-formencode python-greenlet python-lxml python-openid python-openssl python-paste python-pastedeploy python-pastescript python-pkg-resources python-routes python-scgi python-setuptools python-sqlalchemy python-sqlalchemy-ext python-support python-webob sgml-base xml-core  python-argparse python-ldap

if [ -f ../installer/bundle/keystone.pybundle ] ; then
  pip install   ../installer/bundle/keystone.pybundle
else
  if [ -n "${https_proxy}" ]; then
    pip install -r tools/pip-requires --proxy=${https_proxy}
  elif [ -n "${http_proxy}" ]; then
    pip install -r tools/pip-requires --proxy=${http_proxy}
  else
    pip install -r tools/pip-requires
  fi
fi

python setup.py bdist
echo "###bdist###"
python setup.py install --record=$cwd/softwares/keystone/data/install-files.txt
echo "###install###"

popd


if [ ! -d  /var/log/keystone ] ; then mkdir /var/log/keystone ; fi
if [ ! -d  /var/lib/keystone ] ; then mkdir /var/lib/keystone ; fi
