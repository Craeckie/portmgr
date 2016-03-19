# from dckrmgr import cli
from dckrmgr import command_list

def func(ctx):
    # cnf = ctx['cnf']
    directory = ctx['directory']
    # cli.start(cnf['name'])
    print('Started container in ' + directory)
    return 0

command_list['s'] = {
    'hlp': 'Start container',
    'ord': 'nrm',
    'fnc': func
}
