from portmgr import command_list, runCompose
from portmgr.wrapper import buildFile


def func(action):
    relative = action['relative']

    with buildFile() as (services, files):
        if files and not services:
            print("Nothing to build in " + relative)
            return 0
        res = runCompose(
                [*files, 'build', '--pull'],
                env={
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
