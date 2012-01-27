#!/bin/bash

yes i | pip install -I -d source-archives -r tools/pip-requires --no-install --download-cache cache

exit

for package in horizon/openstack-dashboard keystone dispatcher
do
   yes i | pip install -d source-archives -I -r ../$package/tools/pip-requires --no-install --download-cache cache
done
