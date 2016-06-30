from portmgr import command_list, bcolors
import subprocess

def func(action):
    directory = action['directory']
    relative = action['relative']

    res = subprocess.call(["docker-compose", "build"])

    if res != 0:
        print("Error building " + relative + "!")

    return 0

command_list['b'] = {
    'hlp': 'Build local image',
    'ord': 'nrm',
    'fnc': func
}
