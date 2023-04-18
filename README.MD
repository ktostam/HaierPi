# HaierPi

This project 

## PCB
PCB layout is designed for both RaspberryPi zeroW and NanoPi neo 1.4. 

## INSTALL

### Download
git clone http://github.com/ktostam/HaierPi.git

### use install script
sudo install.sh

### manual install
create Virtual Env

python -m venv env

goto env

source env/bin/activate

install requirements:

pip install -r requirements.txt

manual install PyHaier

pip install git+http://github.com/ktostam/PyHaier.git

edit config file

run

python haierpi.py

