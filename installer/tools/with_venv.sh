#!/bin/bash
TOOLS=`dirname $0`
if test -n $COLONY_INSTALL_HOME; then
    VENV=$COLONY_INSTALL_HOME
else
    VENV=$TOOLS/../.installer-venv
fi
source $VENV/bin/activate && $@
