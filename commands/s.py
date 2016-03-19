# from dckrmgr import cli
from dckrmgr import command_list

def func(action):
    # cnf = ctx['cnf']
    directory = action['directory']
    relative = action['relative']
    # cli.start(cnf['name'])
    print('Started container in ' + relative)
    return 0

command_list['s'] = {
    'hlp': 'Start container',
    'ord': 'nrm',
    'fnc': func
}
