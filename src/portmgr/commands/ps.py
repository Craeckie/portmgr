from portmgr import command_list, bcolors, runCompose


def func(action):
    directory = action['directory']
    relative = action['relative']

    res = runCompose(["ps"])

    if res != 0:
        print("Error listing containers for " + relative + "!\n")

    return 0

command_list['c'] = {
    'hlp': 'List containers',
    'ord': 'nrm',
    'fnc': func
}
