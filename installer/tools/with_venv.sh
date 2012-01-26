#!/bin/bash
TOOLS=`dirname $0`
VENV=$TOOLS/../.installer-venv
source $VENV/bin/activate && $@
