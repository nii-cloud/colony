#!/bin/bash

source common/function.sh

echo "uninstall colony-apache"

remove_templates "apache" "colony_apache"
