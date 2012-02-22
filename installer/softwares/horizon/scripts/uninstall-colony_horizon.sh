#!/bin/bash

source common/function.sh

basedir=/usr/local/
bindir=/usr/local/bin
pythondir=/usr/local/lib/python2.7/dist-packages

echo "uninstall colony-horizon"

for package in Django django_mailer django_nose django_openstack django_registration nose openstack_dashboard prettytable
do
    pip uninstall -y $package
done

for link in Quantum glance openstack.compute openstackx python-novaclient
do
    pip uninstall -y $link
    rm -rf $pythondir/$link.egg-link
done

for com in django-admin.py glance glance-api glance-cache-prefetcher glance-cache-pruner glance-cache-reaper glance-control glance-manage glance-registry glance-scrubber glance-upload
do
    echo "removing $bindir/$com"
    rm -rf $bindir/$com
done

for com in openstack-compute nova 
do
    echo "removing $bindir/$com"
    rm -rf $bindir/$com
done

remove_templates "horizon" "colony_horizon"

rm -rf /usr/local/share/dash
rm -rf /usr/local/share/horizon


