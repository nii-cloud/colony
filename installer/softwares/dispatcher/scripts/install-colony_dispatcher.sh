#!/bin/bash


source common/function.sh

create_datadir "dispatcher"
colony_dispatcher_dir="../dispatcher/"
cwd=`pwd`

pushd $colony_dispatcher_dir
apt-get -y install python-swift

python setup.py bdist

if test ! -d $colony_dispatcher_dir/data; then
   mkdir $colony_dispatcher_dir/data
fi
python setup.py install --record=$cwd/softwares/dispatcher/data/install-files.txt

popd
