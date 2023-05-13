from git import Repo
import shutil
import sys
import subprocess
import configparser

config = configparser.ConfigParser()
config.read('config.ini')
release = config['DEFAULT']['release']

status = subprocess.check_output("systemctl show -p ActiveState --value haier", shell=True)
print(status)

subprocess.check_output("systemctl stop haier", shell=True)
status = subprocess.check_output("systemctl show -p ActiveState --value haier", shell=True)
print(status)
Repo.clone_from("https://github.com/ktostam/HaierPi.git", "/opt/haierupdate", branch=release)

shutil.copy('/opt/haier/config.ini','/opt/haierupdate/')
shutil.copy('/opt/haier/users.json', '/opt/haierupdate/')

try:
    shutil.rmtree('/opt/haier.back')
except FileNotFoundError:
    print("/opt/haier.back not exist")
subprocess.check_call(['/opt/haier/env/bin/pip', 'install', '-r', '/opt/haierupdate/requirements.txt'])
shutil.move('/opt/haier', '/opt/haier.back')
shutil.move('/opt/haierupdate', '/opt/haier')
shutil.copytree('/opt/haier.back/env', '/opt/haier/env/')
subprocess.check_output("systemctl start haier", shell=True)
status = subprocess.check_output("systemctl show -p ActiveState --value haier", shell=True)
print(status)