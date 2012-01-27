#!/bin/bash


rm -rf install.log

python tools/install_venv.py >>install.log
bash tools/with_venv.sh python install.py
