from portmgr import command_list, bcolors, runCompose, runBuildx
import subprocess
import os

from portmgr.wrapper import getServices


def func(action):
    directory = action['directory']
    relative = action['relative']

    services = getServices(includeOnlyBuildable=True)

    print('Services to build: ' + ', '.join(services))

    res = 0
    for service in services.keys():
        print(f"\nBuilding {service}")

        if multi_platform := os.environ.get("PORTMGR_MULTI_PLATFORM", "").lower():
            new_res = runBuildx(
                ['bake',
                 '--pull',
                 '--push',
                 '--set', f'*.platform={multi_platform}',
                 service
                 ]
            )
            if new_res != 0:
                res = new_res
                print(f"Error building {service}!")
        else:
            new_res = runCompose(
                    ['build',
                     '--pull',
                     '--force-rm',
                     '--compress',
                     service
                     ]
                    )
            if new_res != 0:
                res = new_res
                print(f"Error building {service}!")
            else:
                new_res = runCompose(
                        ['push',
                         '--ignore-push-failures',
                         service
                         ]
                        )
                if new_res != 0:
                    res = new_res
            print(f"Error pushing {service}!")
        if os.environ.get("PORTMGR_CLEAN_AFTER_PUSH", "").lower() == "true":
            subprocess.call(['docker', 'system', 'prune', '--all', '--force'])
            subprocess.call(['docker', 'buildx', 'prune', '--all', '--force'])

    if res != 0:
        print("Error building&pushing " + relative + "!")
        return res

    return res


command_list['r'] = {
    'hlp': 'build, push to registry & remove image',
    'ord': 'nrm',
    'fnc': func
}
