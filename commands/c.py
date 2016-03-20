# from portmgr import cli
from portmgr import command_list, bcolors
import subprocess

def func(action):
    # cnf = action['cnf']
    directory = action['directory']
    relative = action['relative']

    p = subprocess.Popen(["docker-compose", "create"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    out, err = p.communicate()

    if p.returncode == 0:
        print('Created container in ' + relative)
    else:
        print("Error creating " + relative + "!")
        print(bcolors.FAIL + err.decode("UTF-8") + bcolors.ENDC)

    return 0

command_list['c'] = {
    'hlp': 'Create container',
    'ord': 'nrm',
    'fnc': func
}
