#!/bin/bash


colony_horizon_dir="../horizon/"
cwd=`pwd`

pushd $colony_horizon_dir/openstack-django
pip install -r tools/pip-requires
python setup.py install --record=$cwd/softwares/horizon/data/install-files2.txt
popd

pushd $colony_horizon_dir/django-openstack
python setup.py install --record=$cwd/softwares/horizon/data/install-files.txt
popd

