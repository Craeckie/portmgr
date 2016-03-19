# from dckrmgr import cli
from dckrmgr import command_list

import os
# import docker

def func(action):
    # cnf = action['cnf']
    directory = action['directory']

    print('Created container in ' + directory)

    #if res['Warnings'] != None:
    #    print('Warnings generated:')
    #    print(res['Warnings'])

    return 0

command_list['c'] = {
    'hlp': 'Create container',
    'ord': 'nrm',
    'fnc': func
}
