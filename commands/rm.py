from portmgr import command_list, bcolors
import subprocess

def func(action):
    directory = action['directory']
    relative = action['relative']

    res = subprocess.call(["docker-compose", "rm", "-f"])
    # p = subprocess.Popen(["docker-compose", "rm", "-f"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # out, err = p.communicate()

     #if out != "":
     #    print(out.decode("UTF-8"))

    if res != 0:
        print("Error removing " + relative + "!")
    #     print('Removed ' + relative)
    # else:
    
     #print(bcolors.FAIL + err.decode("UTF-8") + bcolors.ENDC)

    return 0

command_list['r'] = {
    'hlp': 'Remove container',
    'ord': 'rev',
    'fnc': func
}
