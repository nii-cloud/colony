#!/bin/bash


colony_horizon_dir="../horizon/"
cwd=`pwd`


apt-get -y install python-kombu python-cloudfiles python-dateutil python-routes python-webob python-sqlalchemy python-paste python-pastedeploy python-migrate python-eventlet python-xattr pep8 pylint python-coverage python-lxml python-mox


pushd $colony_horizon_dir/openstack-dashboard

if [ -f ../../installer/bundle/horizon/openstack-dashboard.pybundle ] ; then
  pip install ../../installer/bundle/horizon/openstack-dashboard.pybundle
else
  if [ -n "${https_proxy}" ]; then
    pip install -r tools/pip-requires --proxy=${https_proxy}
  elif [ -n "${http_proxy}" ]; then
    pip install -r tools/pip-requires --proxy=${http_proxy}
  else
    pip install -r tools/pip-requires
  fi
fi

python setup.py install --record=$cwd/softwares/horizon/data/install-files2.txt
cp -a debian/openstack-dashboard/var/lib/dash /usr/local/share
ln -s /usr/local/share/dash/local /usr/local/share/dash/dashboard/local

popd

pushd $colony_horizon_dir/django-openstack
python setup.py install --record=$cwd/softwares/horizon/data/install-files.txt
popd


