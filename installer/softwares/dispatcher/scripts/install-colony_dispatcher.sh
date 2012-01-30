#!/bin/bash


colony_dispatcher_dir="../dispatcher/"
cwd=`pwd`

pushd $colony_dispatcher_dir
pip install -r tools/pip-requires

python setup.py bdist
python setup.py install --record=$cwd/softwares/dispatcher/data/install-files.txt

popd
