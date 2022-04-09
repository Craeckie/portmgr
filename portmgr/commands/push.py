from operator import attrgetter
from portmgr import command_list, bcolors
import subprocess
from compose.cli.command import get_project


def func(action):
    directory = action['directory']
    relative = action['relative']

    project = get_project('.')

    services = sorted(
        [service for service in project.services if service.can_be_built()],
        key=attrgetter('name'))

    res = 0
    for service in services:
        name = service.name
        res = subprocess.call(
            ['docker-compose', 'build',
             '--pull',
             '--force-rm',
             '--compress',
             name
             ]
        )
        if res != 0:
            print(f"Error building {service.name}!")
            return res
        res = subprocess.call(['docker-compose', 'push', name])
        if res != 0:
            print(f"Error pushing {service.name}!")
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
