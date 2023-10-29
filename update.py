from git import Repo
import shutil
import sys
import subprocess
import configparser

def compare_and_update_config_files(file1_path, file2_path):
    config1 = configparser.ConfigParser()
    config2 = configparser.ConfigParser()

    config1.read(file1_path)
    config2.read(file2_path)

    updated = False

    for section in config2.sections():
        if not config1.has_section(section):
            config1.add_section(section)
            updated = True
        for option, value in config2.items(section):
            if not config1.has_option(section, option):
                config1.set(section, option, value)
                updated = True

    if updated:
        with open(file1_path, 'w') as file1:
            config1.write(file1)
        print("Updated file1.ini with missing items.")
    else:
        print("No updates needed.")

#file1_path = 'config.ini'  # Replace with the path to your first config file
#file2_path = 'config.ini'  # Replace with the path to your second config file


with open('config.ini', 'r') as file:
  filedata = file.read()

filedata = filedata.replace('DEFAULT', 'MAIN')

with open('config.ini', 'w') as file:
  file.write(filedata)

config = configparser.ConfigParser()
config.read('config.ini')
release = config['MAIN']['release']

status = subprocess.check_output("systemctl show -p ActiveState --value haier", shell=True)
print(status)
subprocess.check_output("systemctl stop haier", shell=True)
status = subprocess.check_output("systemctl show -p ActiveState --value haier", shell=True)
print(status)

if status == 'inactive':
    Repo.clone_from("https://github.com/ktostam/HaierPi.git", "/opt/haierupdate", branch=release)
    shutil.copy('/opt/haier/config.ini','/opt/haierupdate/')
    shutil.copy('/opt/haier/users.json', '/opt/haierupdate/')
    try:
        shutil.rmtree('/opt/haier.back')
    except FileNotFoundError:
        print("/opt/haier.back not exist")
    subprocess.check_call(['/opt/haier/env/bin/pip', 'install', '-r', '/opt/haierupdate/requirements.txt'])
    configold='/opt/haier/config.ini'
    confignew='/opt/haierupdate/config.ini'
    compare_and_update_config_files(configold, confignew)
    shutil.move('/opt/haier', '/opt/haier.back')
    shutil.move('/opt/haierupdate', '/opt/haier')
    shutil.copytree('/opt/haier.back/env', '/opt/haier/env/')
    subprocess.check_output("systemctl start haier", shell=True)

    status = subprocess.check_output("systemctl show -p ActiveState --value haier", shell=True)
    if status == 'active':
        print("HaierPi updated")
