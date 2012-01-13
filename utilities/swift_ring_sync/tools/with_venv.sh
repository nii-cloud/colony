#!/bin/bash
TOOLS=`dirname $0`
VENV=$TOOLS/../.swift-ring-sync-venv
source $VENV/bin/activate && $@
