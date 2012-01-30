#!/bin/bash




do_virtinstall()
{
echo "setting up installer"
python tools/install_venv.py >>install.log
echo "done"

bash tools/with_venv.sh python install.py $@
}

do_install()
{
python install.py
}

DEFAULT_VIRTENV_DIR=/tmp/colony

rm -rf install.log

read -p 'using virtualenv ?: [y/N]' usevirtenv
usevirtenv=$(echo $usevirtenv | tr "[:upper:]" "[:lower:]")

if test x"$usevirtenv" == x"y"; then
   read -p "virtualenv dir: [$DEFAULT_VIRTENV_DIR]" virtdir
   if test x"$virtdir" == x; then
       export COLONY_INSTALL_HOME=/tmp/colony
   else
       export COLONY_INSTALL_HOME=$virtdir
   fi
   do_virtinstall
fi
