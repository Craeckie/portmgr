# from dckrmgr import cli
from dckrmgr import command_list

def func(ctx):
    # cnf = ctx['cnf']
    directory = ctx['directory']
    # cli.stop(cnf['name'])
    print('Stopped container in ' + directory)
    return 0

command_list['t'] = {
    'hlp': 'Stop container',
    'ord': 'rev',
    'fnc': func
}
