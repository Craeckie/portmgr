from portmgr import command_list, bcolors, runCompose


def func(action):
    directory = action['directory']
    relative = action['relative']

    res = runCompose(["pull"])

    if res != 0:
        print("Error pulling " + relative + "!")

    return 0

command_list['p'] = {
    'hlp': 'Pull image from repository',
    'ord': 'nrm',
    'fnc': func
}
