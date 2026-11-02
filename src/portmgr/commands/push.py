from portmgr import command_list, runCompose, runBuildx
import subprocess
import os

from portmgr.wrapper import buildFile


def func(action):
    with buildFile() as (services, files):
        return build_and_push(action['relative'], services, files)


def build_and_push(relative, services, files):
    print('Services to build: ' + ', '.join(services))

    res = 0
    for service in services.keys():
        print(f"\nBuilding {service}")

        new_res = 2
        if multi_platform := os.environ.get("PORTMGR_MULTI_PLATFORM", "").lower():
            try:
                new_res = runBuildx(
                    ['bake',
                     *files,
                     '--pull',
                     '--push',
                     '--set', f'*.platform={multi_platform}',
                     service
                     ], timeout=1200 #kill after 20mins
                )
                if new_res != 0:
                    res = new_res
                    print(f"Error building {service}!")
            except subprocess.TimeoutExpired:
                print(f"Error building {service}! Build timed out.")
        else:
            try:
                new_res = runCompose(
                        [*files,
                         'build',
                         '--pull',
                         '--force-rm',
                         '--compress',
                         service
                         ], timeout=1200
                        )
                if new_res != 0:
                    res = new_res
                    print(f"Error building {service}!")
                else:
                    new_res = runCompose(
                            [*files,
                             'push',
                             '--ignore-push-failures',
                             service
                             ]
                            )
                    if new_res != 0:
                        print(f"Error pushing {service}!")
            except subprocess.TimeoutExpired:
                print(f"Error building {service}! Build timed out.")
            if new_res != 1:
                res = new_res
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
