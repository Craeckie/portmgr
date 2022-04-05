from operator import attrgetter
from portmgr import command_list, bcolors
import subprocess
from compose.cli.command import get_project
from compose.project import OneOffFilter


def func(action):
    directory = action['directory']
    relative = action['relative']

    project = get_project('.')

    containers = sorted(
        project.containers(stopped=True) +
        project.containers(one_off=OneOffFilter.only, stopped=False),
        key=attrgetter('name'))

    res = 0
    for container in containers:
        name = container.service
        res = subprocess.call(
            ['docker-compose', 'build',
             '--pull',
             '--force-rm',
             '--compress',
             name
             ]
        )
        if res != 0:
            print(f"Error building {container.name}!")
            return res
        res = subprocess.call(['docker-compose', 'push', name])
        if res != 0:
            print(f"Error pushing {container.name}!")
            return res
        # res = subprocess.call(['docker', 'system', 'prune', '--all', '--force'])



    if res != 0:
        print("Error pushing " + relative + "!")
        return res

    return res


command_list['r'] = {
    'hlp': 'build, push to registry & remove image',
    'ord': 'nrm',
    'fnc': func
}
