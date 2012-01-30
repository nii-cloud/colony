#!/bin/bash


colony_keystone_dir="../keystone/"
cwd=`pwd`

pushd $colony_keystone_dir
pip install -r tools/pip-requires --log=$cwd/softwares/keystone/data/colony_keystone-install.log

python setup.py bdist
python setup.py install --record=$cwd/softwares/keystone/data/colony_keystone-install-files.txt

popd
