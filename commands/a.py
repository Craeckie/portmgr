from portmgr import command_list, bcolors
import subprocess

def func(action):
    directory = action['directory']
    relative = action['relative']
    
    p = subprocess.Popen(["docker-compose", "ps", "-q"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    out, err = p.communicate()
    
    if p.returncode == 0:
      lines = [x for x in out.decode('utf8').split('\n') if x]
      index = 0
      if len(lines) == 0:
        print("No containers found!")
        return 1
      elif len(lines) > 1:
        # ask..
        print("Choose container:")
        index = 1
      container_id = lines[index]
      print("Attaching to " + container_id[:12])
      subprocess.call(["docker", "exec", "-it", container_id, "bash"])

    # res = subprocess.call(["docker-compose", "logs", "--follow", "--tail=200"])

    # if res != 0:
        # print("Error showing logs for " + relative + "!\n")

    return 0

command_list['a'] = {
    'hlp': 'Attach to process',
    'ord': 'nrm',
    'fnc': func
}
