#!/bin/bash
if [ "$EUID" -ne 0 ]
  then echo "Please run as root"
  exit
fi

if ! command -v python &> /dev/null
then
  echo -e "Python                     [ \033[0;31mFAIL\033[0m ]"
  echo -e -n "\033[0;31mPython not found on your system do you want to install it?\033[0m Y/N"
  read ans
  if [[ $ans == "Y" ]]; then
  	$install_app install python
  else
	  echo "Please install python"
	  exit 1
  fi
else
	echo -e "Python                     [ \033[0;32mOK\033[0m ]"
fi

version=$(python -V 2>&1 | grep -Po '(?<=Python )(.+)')
requiredver="3.9"
 if [ "$(printf '%s\n' "$requiredver" "$version" | sort -V | head -n1)" = "$requiredver" ]; then
	 echo -e "Python version             [ \033[0;32mOK\033[0m ]"
 else
	 echo -e "\033[0;31mPython version is too old\033[0m"
 fi

os=$(cat /etc/os-release |grep -oP 'PRETTY_NAME="\K[^"]+')

if [[ $os == *"Raspbian"* ]]; then
	echo -e "Operating System           [ \033[0;32mOK\033[0m ]"
	install_app='apt-get'
else
	echo -e "Operating System           [ \033[0;31mFAIL\033[0m ]"
	echo -e -n "\033[0;31mSoftware not tested on this system, do you want install anyway? Y/N: \033[0m"
	read ans
	if [[ ${ans^^} == "N" ]]; then
		echo "Installation cancelled"
		exit 1
	fi
fi
installation_dir="/opt/haier"
mkdir $installation_dir
echo -n -e "Copying files              [ \033[5;33mIN PROGRESS\033[0m ]\r"
cp -R main.py requirements.txt config.ini users.json static templates .git* $installation_dir
echo -e "\rCopying files              [ \033[0;32mOK\033[0m ]         "
echo -n -e "Generating virtual ENV     [ \033[5;33mIN PROGRESS\033[0m ]\r"
python -m venv $installation_dir/env
echo -e "\rPython VENV                [ \033[0;32mOK\033[0m ]             "
cd $installation_dir
source env/bin/activate
echo -n -e "Installing requirements    [ \033[5;33mIN PROGRESS\033[0m ]\r"
pip -q install --upgrade pip
pip -q install -r requirements.txt
echo -e "\rPython requirements        [ \033[0;32mOK\033[0m ]            "
echo -e -n "Generating systemd service...\r"
cp ./etc/systemd/system/haier.service /etc/systemd/system/
cp ./etc/systemd/system/haierupdate.service /etc/systemd/system/
systemctl daemon-reload
echo -e "\rGenerating systemd service [ \033[0;32mOK\033[0m ]"
echo -e "Do you want to activate systemd service to automatic start? Y/N"
read ans
if [[ ${ans^^} == "Y" ]]; then
	systemctl enable haier.service
fi
echo -e "[ \033[6;32mInstallation complete\033[0m ]"