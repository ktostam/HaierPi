#!/bin/bash
#
# USING dietpi-global for pretty look :D
#
if [ "$EUID" -ne 0 ]
  then echo "Please run as root"
  exit
fi
if [[ -f '/boot/dietpi/func/dietpi-globals' ]]
then
        . /boot/dietpi/func/dietpi-globals
else
        curl -sSf "https://raw.githubusercontent.com/${G_GITOWNER:=MichaIng}/DietPi/${G_GITBRANCH:=master}/dietpi/func/dietpi-globals" -o /tmp/dietpi-globals || exit 1
        # shellcheck disable=SC1091
        . /tmp/dietpi-globals

os=$(cat /etc/os-release |grep -oP 'PRETTY_NAME="\K[^"]+'|cut -d" " -f1)

G_EXEC_DESC="Checking Operating System" G_EXEC_NOHALT=1 G_EXEC [ $os == "Debian" ]
install_app='apt-get'
G_EXEC_DESC="Looking for Python 3"
G_EXEC_ARRAY_TEXT=( "Install" "Install missing packages" )
G_EXEC_ARRAY_ACTION=(["Install"]='apt-get install python3 python3-pip python3-venv')
G_EXEC command -v python3
version=$(python3 -V 2>&1 | grep -Po '(?<=Python )(.+)')
requiredver="3.9"
G_EXEC_DESC="Checking Python Version" G_EXEC_NOHALT=1 G_EXEC [ "$(printf '%s\n' "$requiredver" "$version" | sort -V | head -n1)" = "$requiredver" ]
workdir=$(pwd)
installation_dir="/opt/haier"
if [[ ! -d "$installation_dir" ]]
then
  mkdir $installation_dir
fi
G_EXEC_DESC="Copying files" G_EXEC cp -R main.py requirements.txt HPi config.ini users.json static templates .git* $installation_dir
G_EXEC_DESC="Generating virtual ENV" G_EXEC python3 -m venv $installation_dir/env
cd $installation_dir
G_EXEC source env/bin/activate
G_EXEC_DESC="Installing requirements" G_EXEC pip -q install --upgrade pip && pip -q install -r requirements.txt
G_EXEC_DESC="Generating systemd services" G_EXEC cp $workdir/etc/systemd/system/haier*.service /etc/systemd/system/
G_EXEC systemctl daemon-reload
echo -n -e "Do you want to activate systemd service to automatic start? Y/N "
read ans
if [[ ${ans^^} == "Y" ]]; then
        G_EXEC systemctl enable haier.service
fi
echo -e "[ \033[6;32mInstallation complete\033[0m ]"
