from portmgr import command_list, command_extra, runCompose, runBuildx
import subprocess
import os

from portmgr.runlog import flush_output, format_duration, service_images
from portmgr.wrapper import buildFile, build_timeout


def func(action):
    with buildFile() as (services, files):
        action['images'] = service_images(services)
        return build_and_push(action['relative'], services, files,
                              no_cache='--no-cache' in command_extra)


def build_and_push(relative, services, files, no_cache=False):
    print('Services to build: ' + ', '.join(services))
    # --pull refreshes FROM, but a cached `RUN apk add` / `apt-get install` layer survives until
    # the base digest changes; --no-cache rebuilds every layer to pick up distro-package fixes.
    cache_flag = ['--no-cache'] if no_cache else []

    res = 0
    for service in services.keys():
        print(f"\nBuilding {service}")
        timeout = build_timeout(service, services[service])
        timed_out = f"Error building {service}! Build timed out after {format_duration(timeout)}."

        new_res = 2
        if multi_platform := os.environ.get("PORTMGR_MULTI_PLATFORM", "").lower():
            try:
                new_res = runBuildx(
                    ['bake',
                     *files,
                     '--pull',
                     *cache_flag,
                     '--push',
                     '--set', f'*.platform={multi_platform}',
                     service
                     ], timeout=timeout
                )
                if new_res != 0:
                    res = new_res
                    print(f"Error building {service}!")
            except subprocess.TimeoutExpired:
                res = new_res
                print(timed_out)
        else:
            try:
                new_res = runCompose(
                        [*files,
                         'build',
                         '--pull',
                         *cache_flag,
                         '--force-rm',
                         '--compress',
                         service
                         ], timeout=timeout
                        )
                if new_res != 0:
                    res = new_res
                    print(f"Error building {service}!")
                else:
                    new_res = runCompose(
                            [*files,
                             'push',
                             '--ignore-missing',
                             service
                             ]
                            )
                    if new_res != 0:
                        print(f"Error pushing {service}!")
            except subprocess.TimeoutExpired:
                print(timed_out)
            if new_res not in (0, 1):  # a failed push (1) is reported above, not counted
                res = new_res
        if os.environ.get("PORTMGR_CLEAN_AFTER_PUSH", "").lower() == "true":
            flush_output()
            subprocess.call(['docker', 'system', 'prune', '--all', '--force'])
            subprocess.call(['docker', 'buildx', 'prune', '--all', '--force'])

    if res != 0:
        print("Error building&pushing " + relative + "!")
        return res

    return res


command_list['r'] = {
    'hlp': 'build, push to registry & remove image',
    'ord': 'nrm',
    'fnc': func,
    'args': ('--no-cache',),
}
