#!/bin/bash


basedir="/usr/local/share/horizon"
colony_horizon_dir="../horizon/"
cwd=`pwd`


apt-get -y install python-kombu python-cloudfiles python-dateutil python-routes python-webob python-sqlalchemy python-paste python-pastedeploy python-migrate python-eventlet python-xattr pep8 pylint python-coverage python-lxml python-mox

source common/function.sh
create_datadir "horizon"

# install pybundle
mkdir -p $basedir
cp -a bundle/openstack-dashboard.pybundle $basedir

pushd $basedir
    if test -f openstack-dashboard.pybundle ; then
        pip install openstack-dashboard.pybundle
        rm -rf openstack-dashboard.pybundle
    elif [ -n "${https_proxy}" ]; then
        pip install -r $cwd/$colony_horizon_dir/tools/pip-requires --proxy=${https_proxy}
    elif [ -n "${http_proxy}" ]; then
        pip install -r $cwd/$colony_horizon_dir/tools/pip-requires --proxy=${http_proxy}
    else
        pip install -r $cwd/$colony_horizon_dir/tools/pip-requires
    fi
popd

pushd $colony_horizon_dir/openstack-dashboard

python setup.py install --record=$cwd/softwares/horizon/data/install-files2.txt
cp -a debian/openstack-dashboard/var/lib/dash /usr/local/share
ln -s /usr/local/share/dash/local /usr/local/share/dash/dashboard/local

popd

pushd $colony_horizon_dir/django-openstack
python setup.py install --record=$cwd/softwares/horizon/data/install-files.txt
popd


