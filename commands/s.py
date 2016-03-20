# from portmgr import cli
from portmgr import command_list, bcolors
import subprocess

def func(action):
    # cnf = ctx['cnf']
    directory = action['directory']
    relative = action['relative']

    p = subprocess.Popen(["docker-compose", "start"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    out, err = p.communicate()

    if p.returncode == 0:
        print('Started container in ' + relative)
    else:
        print("Error starting " + relative + "!")
        print(bcolors.FAIL + err.decode("UTF-8") + bcolors.ENDC)

    return 0

command_list['s'] = {
    'hlp': 'Start container',
    'ord': 'nrm',
    'fnc': func
}
