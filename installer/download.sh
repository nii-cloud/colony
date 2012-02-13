#!/bin/bash

BUNDLE_DIR=./bundle
BUILD_DIR=./build

if [ ! -d ${BUNDLE_DIR} ] ; then mkdir ${BUNDLE_DIR}; fi
if [ ! -d ${BUNDLE_DIR}/horizon ] ; then mkdir ${BUNDLE_DIR}/horizon; fi

if [ -n "${https_proxy}" ]; then
  pip bundle --no-install --proxy=${https_proxy} -r ./tools/pip-requires \
    -b ${BUILD_DIR}-colony ${BUNDLE_DIR}/colony.pybundle
elif [ -n "${http_proxy}" ]; then
  pip bundle --no-install --proxy=${http_proxy} -r ./tools/pip-requires \
    -b ${BUILD_DIR}-colony ${BUNDLE_DIR}/colony.pybundle
else
  pip bundle --no-install -r ./tools/pip-requires \
    -b ${BUILD_DIR}-colony ${BUNDLE_DIR}/colony.pybundle
fi


for package in horizon/openstack-dashboard keystone
do
  if [ -n "${https_proxy}" ]; then
     pip bundle --no-install --proxy=${https_proxy} -r ../${package}/tools/pip-requires \
       -b ${BUILD_DIR}-${package} ${BUNDLE_DIR}/${package}.pybundle
  elif [ -n "${http_proxy}" ]; then
     pip bundle --no-install --proxy=${http_proxy} -r ../${package}/tools/pip-requires \
       -b ${BUILD_DIR}-${package} ${BUNDLE_DIR}/${package}.pybundle
  else
     pip bundle --no-install -r ../${package}/tools/pip-requires \
       -b ${BUILD_DIR}-${package} ${BUNDLE_DIR}/${package}.pybundle
  fi
done
