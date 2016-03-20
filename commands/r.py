# from portmgr import cli
from portmgr import command_list, bcolors
import subprocess

def func(action):
    directory = action['directory']
    relative = action['relative']

    p = subprocess.Popen(["docker-compose", "rm"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    out, err = p.communicate()

    if p.returncode == 0:
        print('Removed container in ' + relative)
    else:
        print("Error removing " + relative + "!")
        print(bcolors.FAIL + err.decode("UTF-8") + bcolors.ENDC)

    return 0

command_list['r'] = {
    'hlp': 'Remove container',
    'ord': 'rev',
    'fnc': func
}
