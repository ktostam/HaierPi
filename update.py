import re
import git
import sys
import configparser
import os
import subprocess
import shutil
import urllib.request, json

def backup():
    try:
        shutil.rmtree('/opt/haier.backup')
    except FileNotFoundError:
        print("/opt/haier.backup not exist")
    
    print("Creating backup without env.")
    shutil.copytree('/opt/haier', '/opt/haier.backup')
    shutil.rmtree('/opt/haier.backup/env')

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
        print("Updated config.ini with missing items.")
    else:
        print("No updates needed.")

def update():
	status = subprocess.check_output("systemctl show -p ActiveState --value haier", shell=True).decode().rstrip('\n')
	print(status)
	subprocess.check_output("systemctl stop haier", shell=True)
    status = subprocess.check_output("systemctl show -p ActiveState --value haier", shell=True).decode().rstrip('\n')
    print(status)

    if status == 'inactive':
        with open('/opt/haier/config.ini', 'r') as file:
            filedata = file.read()

        filedata = filedata.replace('DEFAULT', 'MAIN')

        with open('/opt/haier/config.ini', 'w') as file:
            file.write(filedata)

        config = configparser.ConfigParser()
        config.read('/opt/haier/config.ini')
        release = config['MAIN']['release']
        print(release)
        backup()
        repo = git.Repo.clone_from('https://github.com/ktostam/HaierPi', '/opt/haier', branch=release)
        shutil.copyfile("/opt/haier.backup/config.ini", "/opt/haier/config.ini")
        old_file = os.path.abspath("/opt/haier/config.ini")
        new_file = os.path.abspath("/opt/haier/config.ini.repo")
        compare_and_update_config_files(old_file, new_file)
        subprocess.check_call(['python3', '-m', 'venv', '/opt/haier/env'])
        subprocess.check_call(['/opt/haier/env/bin/pip', 'install', '--upgrade', '-r', '/opt/haier/requirements.txt'])

        subprocess.check_output("systemctl start haier", shell=True)
        status = subprocess.check_output("systemctl show -p ActiveState --value haier", shell=True).decode().rstrip('\n')
        if status == 'active':
            print("HaierPi updated")

def check_for_update(release):
    with urllib.request.urlopen("https://haierpi.pl/software/release.json") as url:
        data = json.load(url)
        version = data["HaierPi"]["branches"][0][release][0]["latest_version"]
    return version
    

config = configparser.ConfigParser()
config.read('/opt/haier/config.ini')
release = config['MAIN']['release']

if (args_count := len(sys.argv)) > 2:
    print(f"One argument expected, got {args_count - 1}")
    raise SystemExit(2)
elif args_count < 2:
    print("robie update")
	update()


if sys.argv[1] == "check" :
    print(check_for_update(release))
    raise SystemExit(0)
