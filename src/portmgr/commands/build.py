import os

from portmgr import command_list, runCompose
from portmgr.runlog import service_images
from portmgr.wrapper import buildFile


def func(action):
    relative = action['relative']

    with buildFile() as (services, files):
        action['images'] = service_images(services)
        if files and not services:
            print("Nothing to build in " + relative)
            return 0
        res = runCompose(
                [*files, 'build', '--pull'],
                env={
                    **os.environ,
                    'COMPOSE_DOCKER_CLI_BUILD': '1',
                    'DOCKER_BUILDKIT': '1'
                    },
                )

    if res != 0:
        print("Error building " + relative + "!")

    return res

command_list['b'] = {
    'hlp': 'Build local image',
    'ord': 'nrm',
    'fnc': func
}
