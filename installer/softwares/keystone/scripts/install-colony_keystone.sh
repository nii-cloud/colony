#!/bin/bash


colony_keystone_dir="../keystone/"
cwd=`pwd`

pushd $colony_keystone_dir
pip install -r tools/pip-requires

python setup.py bdist
python setup.py install --record=$cwd/softwares/keystone/data/install-files.txt

popd
