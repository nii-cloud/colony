#!/bin/bash


colony_dispatcher_dir="../dispatcher/"
cwd=`pwd`

pushd $colony_dispatcher_dir
apt-get -y install python-swift

python setup.py bdist
python setup.py install --record=$cwd/softwares/dispatcher/data/install-files.txt

popd
