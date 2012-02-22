#!/bin/bash

basedir=/usr/local/bin

pip uninstall -y WebOb
pip uninstall -y WebTest
pip uninstall -y rython
pip uninstall -y empy
pip uninstall -y unittest2
pip uninstall -y yamlconfig

for com in unit2 unit2-2.7 unit2.py
do
    rm -rf $basedir/$com
done
