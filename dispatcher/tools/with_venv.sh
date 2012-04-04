#!/bin/bash
TOOLS=`dirname $0`
VENV=$TOOLS/../.dispatcher-venv
source $VENV/bin/activate && $@
