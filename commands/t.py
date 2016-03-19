# from dckrmgr import cli
from dckrmgr import command_list

def func(action):
    # cnf = ctx['cnf']
    directory = action['directory']
    relative = action['relative']
    # cli.stop(cnf['name'])
    print('Stopped container in ' + relative)
    return 0

command_list['t'] = {
    'hlp': 'Stop container',
    'ord': 'rev',
    'fnc': func
}
