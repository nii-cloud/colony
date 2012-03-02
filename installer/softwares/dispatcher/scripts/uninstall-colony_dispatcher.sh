#!/bin/bash

source common/function.sh

echo 'Uninstalling colony_dispatcher'

basedir=/usr/local/bin
cwd=`pwd`

apt-get -y remove python-swift

pip uninstall -y dispatcher

for com in dispatcher
do
   echo "removing $basedir/$com"
   rm -rf $basedir/$com
done

if test -f  $cwd/softwares/dispatcher/data/install-templates.txt ; then
   for template in  `cat $cwd/softwares/dispatcher/data/install-templates.txt`
   do
       echo "removing $template"
       rm -rf $template
   done
fi

remove_templates "dispatcher" "colony_dispatcher"
