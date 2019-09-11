from portmgr import command_list, bcolors
import subprocess
from compose.cli.command import get_project
from compose import project
from compose.project import OneOffFilter
from operator import attrgetter

def func(action):
    directory = action['directory']
    relative = action['relative']

    project = get_project('.')

    containers = sorted(
        project.containers(stopped=False) +
        project.containers(one_off=OneOffFilter.only, stopped=False),
        key=attrgetter('name'))

    names = []
    for container in containers:
      print("Name: %s" % container.name)
      #names.append(container.name)
      ip = subprocess.run(["docker", "inspect", "-f", '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', container.id()], stdout=subprocess.PIPE).stdout
      print("IP: %s" % ip)
      print(container.inspect)


    #ID = subprocess.run(["docker-compose", "ps", '-q'], stdout=subprocess.PIPE).stdout

    if res != 0:
        print("Error listing containers for " + relative + "!\n")

    return 0

command_list['i'] = {
    'hlp': 'Show information about containers',
    'ord': 'nrm',
    'fnc': func
}
