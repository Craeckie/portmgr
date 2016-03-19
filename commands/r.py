# from dckrmgr import cli
from dckrmgr import command_list

def func(action):
    # cnf = ctx['cnf']
    directory = action['directory']
    #cli.remove_container(container = cnf['name'])
    print('Removed container in ' + directory)
    return 0

command_list['r'] = {
    'hlp': 'Remove container',
    'ord': 'rev',
    'fnc': func
}
