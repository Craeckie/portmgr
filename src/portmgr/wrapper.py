import json
import os
from contextlib import contextmanager
from subprocess import run, check_output

import yaml

from portmgr.runlog import flush_output

# Holds only the build sections of a stack; written next to the compose file so
# relative paths, .env and the project name resolve as they do for the original.
BUILD_FILE = '.portmgr-build.yml'
BUILD_KEYS = ('build', 'image', 'platform')


class _Reset:
    """Value of a `!reset` tag: the key counts as not set."""


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader that also accepts compose's `!reset` and `!override` tags."""


def _construct_untagged(loader, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


_ComposeLoader.add_constructor('!reset', lambda loader, node: _Reset())
_ComposeLoader.add_constructor('!override', _construct_untagged)


def _composeFile(directory):
    from portmgr.portmgr import compose_names
    for name in compose_names:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    return None


def _activeProfiles():
    return {p.strip() for p in os.environ.get('COMPOSE_PROFILES', '').split(',') if p.strip()}


def _readCompose(directory='.'):
    """The stack's compose file as a dict, or None if it can't be read."""
    path = _composeFile(directory)
    if path is None:
        return None
    try:
        with open(path) as stream:
            data = yaml.load(stream, Loader=_ComposeLoader)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get('services') or {}, dict):
        return None
    return data


def _buildServices(data):
    active = _activeProfiles()
    services = {}
    for name, service in (data.get('services') or {}).items():
        if not isinstance(service, dict):
            continue
        build = service.get('build')
        if build is None or isinstance(build, _Reset):
            continue
        profiles = service.get('profiles') or []
        if profiles and '*' not in active and not active.intersection(profiles):
            continue
        services[name] = {key: service[key] for key in BUILD_KEYS
                          if key in service and not isinstance(service[key], _Reset)}
    return services


def getBuildServices(directory='.'):
    """{service: {build, image, platform}} for every service with its own `build:`,
    read from the compose file without docker compose, or None if it can't be read.
    Profiled services count only if COMPOSE_PROFILES names one of their profiles."""
    data = _readCompose(directory)
    if data is None:
        return None
    return _buildServices(data)


def writeBuildFile(services, name=None, directory='.'):
    """Write BUILD_FILE with only `services` (and the project `name`); return its path."""
    content = {'name': name} if name else {}
    content['services'] = services
    path = os.path.join(directory, BUILD_FILE)
    with open(path, 'w') as stream:
        yaml.safe_dump(content, stream, sort_keys=False)
    return path


@contextmanager
def buildFile(directory='.'):
    """Yield (buildable services, compose file arguments) for `r` and `b`.

    Normally the services come from the compose file itself and are written to
    BUILD_FILE (removed afterwards), so compose never sees the rest of the stack.
    If the compose file can't be read, fall back to `docker compose config`."""
    data = _readCompose(directory)
    if data is None:
        print('Note: could not read the compose file, falling back to docker compose config')
        yield getServices(includeOnlyBuildable=True), []
        return
    services = _buildServices(data)
    path = writeBuildFile(services, data.get('name'), directory)
    try:
        yield services, ['-f', BUILD_FILE]
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def getServices(includeOnlyBuildable=False):
    flush_output()
    data = check_output(['docker', 'compose', 'config', '--format', 'json'])
    config = json.loads(data)
    services = config['services']
    if includeOnlyBuildable:
        services = {name: values for name, values in services.items() if 'build' in values.keys()}
    return services


def getServicesRunning():
    flush_output()
    data = check_output(['docker', 'compose', 'ps', '--format', 'json'])
    try:
        lines = data.decode().splitlines()
        if len(lines) > 1:
            container_list = []
            for line in lines:
                #print(f'l: {line}')
                container_list.append(json.loads(line.strip()))
        else:
            container_list = json.loads(data)
    except Exception as e:
        print(e)
        print(data.decode())
    if isinstance(container_list, dict):
        container_names = [container_list['Name']]
    else:
        container_names = [s['Name'] for s in container_list]
    return container_names


def getImages():
    flush_output()
    data = check_output(['docker', 'compose', 'images', '--format', 'json'])
    image_list = json.loads(data)
    images = [
        {'ID': image['ID'],
         'Name': image['Repository'],
         'ContainerName': image['ContainerName'],
         'Tag': image['Tag']}
        for image in image_list
    ]
    return images


def getStats():
    containers = getServicesRunning()
    flush_output()
    data = check_output(['docker', 'stats', '--format', 'json', '--no-stream'] + containers, text=True).strip()
    data_lines = data.split('\n')
    stats = [json.loads(line) for line in data_lines]
    return stats


def runCompose(args, **kwargs):
    command = ['docker', 'compose']
    if os.environ.get("PORTMGR_IN_SCRIPT", "").lower() == "true":
        command += ["--ansi", "never"]
    command += list(args)
    flush_output()
    return run(command, **kwargs).returncode

def runBuildx(args, **kwargs):
    command = ['docker', 'buildx']
    command += list(args)
    flush_output()
    return run(command, **kwargs).returncode
