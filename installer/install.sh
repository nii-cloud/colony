#!/bin/bash


rm -rf install.log

echo "setting up installer"
python tools/install_venv.py >>install.log
echo "done"

bash tools/with_venv.sh python install.py $@
