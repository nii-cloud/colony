#!/bin/bash
TOOLS=`dirname $0`
if test "x$COLONY_INSTALL_HOME" != "x"; then
    VENV=$COLONY_INSTALL_HOME
else
    VENV=$TOOLS/../.installer-venv
fi

source $VENV/bin/activate && $@
