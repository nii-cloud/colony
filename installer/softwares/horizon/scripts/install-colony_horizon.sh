#!/bin/bash


colony_horizon_dir="../horizon/"
cwd=`pwd`


pip install -r $colony_horizon_dir/openstack-dashboard/tools/pip-requires

python $colony_horizon_dir/django-openstack/setup.py install --record=$cwd/softwares/horizon/data/install-files.txt

