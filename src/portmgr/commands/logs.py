from portmgr import command_list, bcolors, runCompose


def func(action):
    directory = action['directory']
    relative = action['relative']

    res = runCompose(["logs", "--follow", "--tail=200"])

    if res != 0:
        print("Error showing logs for " + relative + "!\n")

    return 0

command_list['l'] = {
    'hlp': 'Show logs',
    'ord': 'nrm',
    'fnc': func
}
