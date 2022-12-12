from operator import attrgetter
from portmgr import command_list, bcolors, runCompose
import subprocess
from compose.cli.command import get_project


def func(action):
    directory = action['directory']
    relative = action['relative']

    project = get_project('.')

    services = sorted(
        [service for service in project.services if service.can_be_built()],
        key=attrgetter('name'))

    print('Services to build: ' + ', '.join([s.name for s in services]))

    res = 0
    for service in services:
        name = service.name
        print(f"\nBuilding {name}")

        new_res = runCompose(
            ['build',
             '--pull',
             '--force-rm',
             '--compress',
             name
             ]
        )
        if new_res != 0:
            res = new_res
            print(f"Error building {service.name}!")
            #subprocess.call(['docker', 'system', 'prune', '--all', '--force'])
        else:
            new_res = runCompose(
                ['push',
                 '--ignore-push-failures',
                 name
                 ]
            )
        #subprocess.call(['docker', 'system', 'prune', '--all', '--force'])
            if new_res != 0:
                res = new_res
                print(f"Error pushing {service.name}!")

    if res != 0:
        print("Error building&pushing " + relative + "!")
        return res

    return res


command_list['r'] = {
    'hlp': 'build, push to registry & remove image',
    'ord': 'nrm',
    'fnc': func
}
