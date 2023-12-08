import re
from git import Repo
import configparser
import os
import subprocess
import shutil

def backup():
    try:
        shutil.rmtree('/opt/haier.backup')
    except FileNotFoundError:
        print("/opt/haier.backup not exist")
    
    shutil.copytree('/opt/haier', '/opt/haier.backup')


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

#file1_path = 'config.ini'  # Replace with the path to your first config file
#file2_path = 'config.ini'  # Replace with the path to your second config file
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
    a_repo = Repo("/opt/haier/")
    behind = 0

    # Porcelain v2 is easier to parse, branch shows ahead/behind
    a_repo.git.fetch()
    #a_repo.git.checkout()

    this_branch= a_repo.active_branch.name
    branch = re.search(release, this_branch)
    if branch:
        bran = branch.group()
        print("check for update")
        repo_status = a_repo.git.status(porcelain="v2", branch=True)
        ahead_behind_match = re.search(r"#\sbranch\.ab\s\+(\d+)\s-(\d+)", repo_status)
        # If no remotes exist or the HEAD is detached, there is no ahead/behind info
        if ahead_behind_match:
            behind = int(ahead_behind_match.group(2))
    
        print(behind)
        if behind >= 1:
            print("Updating")
            backup()
            a_repo.git.stash()
            a_repo.git.pull()
            old_file = os.path.abspath("/opt/haier/config.ini")
            new_file = os.path.abspath("/opt/haier/config.ini.repo")
            a_repo.git.stash('pop')
            compare_and_update_config_files(old_file, new_file)
            subprocess.check_call(['/opt/haier/env/bin/pip', 'install', '--upgrade', '-r', '/opt/haier/requirements.txt'])

        repo_status = a_repo.git.status(porcelain="v2", branch=True)
        ahead_behind_match = re.search(r"#\sbranch\.ab\s\+(\d+)\s-(\d+)", repo_status)
        if ahead_behind_match:
            behind = int(ahead_behind_match.group(2))
        print(behind)

    else:
        print("you are not in good branch. Swtiching branch")
        backup()
        a_repo.git.stash()
        a_repo.git.checkout(release)
        old_file = os.path.abspath("/opt/haier/config.ini")
        new_file = os.path.abspath("/opt/haier/config.ini.repo")
        a_repo.git.stash('pop')
        compare_and_update_config_files(old_file, new_file)
        subprocess.check_call(['/opt/haier/env/bin/pip', 'install', '--upgrade', '-r', '/opt/haier/requirements.txt'])
        
    subprocess.check_output("systemctl start haier", shell=True)
    status = subprocess.check_output("systemctl show -p ActiveState --value haier", shell=True).decode().rstrip('\n')
    if status == 'active':
        print("HaierPi updated")