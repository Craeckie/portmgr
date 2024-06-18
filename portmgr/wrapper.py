import json
import os
from subprocess import call, check_output


def getServices(includeOnlyBuildable=False):
    data = check_output(['sudo', 'docker', 'compose', 'config', '--format', 'json'])
    config = json.loads(data)
    services = config['services']
    if includeOnlyBuildable:
        services = {name: values for name, values in services.items() if 'build' in values.keys()}
    return services


def getServicesRunning():
    data = check_output(['sudo', 'docker', 'compose', 'ps', '--format', 'json'])
    try:
        lines = data.decode().splitlines()
        if len(lines) > 1:
            container_list = []
            for l in lines:
                #print(f'l: {l}')
                container_list.append(json.loads(l.strip()))
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
    data = check_output(['sudo', 'docker', 'compose', 'images', '--format', 'json'])
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
    data = check_output(['sudo', 'docker', 'stats', '--format', 'json', '--no-stream'] + containers, text=True).strip()
    data_lines = data.split('\n')
    stats = [json.loads(line) for line in data_lines]
    return stats


def runCompose(args, **kwargs):
    command = ['sudo', 'docker', 'compose']
    if os.environ.get("PORTMGR_IN_SCRIPT", "").lower() == "true":
        command += ["--ansi", "never"]
    command += list(args)
    return call(command, **kwargs)
