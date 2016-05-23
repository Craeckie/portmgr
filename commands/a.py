from portmgr import command_list, bcolors
import subprocess

def func(action):
    directory = action['directory']
    relative = action['relative']
    
    p = subprocess.Popen(["docker-compose", "ps", "-q"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    out, err = p.communicate()
    
    if p.returncode == 0:
      lines = out.split('\n')
      index = 0
      if lines.length > 1:
        # ask..
        index = 1
      container_id = lines[index]
      subprocess.call("docker-compose", "exec", "-it", container_id, "bash")

    # res = subprocess.call(["docker-compose", "logs", "--follow", "--tail=200"])

    # if res != 0:
        print("Error showing logs for " + relative + "!\n")

    return 0

command_list['a'] = {
    'hlp': 'Attach to process',
    'ord': 'nrm',
    'fnc': func
}
