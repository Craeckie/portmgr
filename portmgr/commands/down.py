from portmgr import command_list, bcolors, runCompose


def func(action):
    directory = action['directory']
    relative = action['relative']

    res = runCompose(["down"])
    # p = subprocess.Popen(["docker-compose", "down"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # out, err = p.communicate()

    # if out != "":
    #     print(out.decode("UTF-8"))

    if not res == 0:
        print("Error removing " + relative + "!")
    
    # print(bcolors.FAIL + err.decode("UTF-8") + bcolors.ENDC)

    return 0

command_list['d'] = {
    'hlp': 'Stop and remove container',
    'ord': 'rev',
    'fnc': func
}
