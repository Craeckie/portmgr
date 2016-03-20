# from dckrmgr import cli
from dckrmgr import command_list, bcolors
import subprocess

import os

def func(action):
    # cnf = action['cnf']
    directory = action['directory']
    relative = action['relative']

    p = subprocess.Popen(["docker-compose", "create"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    #res = subprocess.run(["docker-compose", "create"], stdout=FNULL, stderr=subprocess.STDOUT)
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
