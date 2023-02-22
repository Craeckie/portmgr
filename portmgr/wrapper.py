import json

from portmgr import runCompose


def getServices(includeOnlyBuildable=False):
    data = runCompose(['docker-compose', 'config', '--format', 'json'])
    config = json.loads(data)
    services = config['services']
    if includeOnlyBuildable:
        services = [s for s in services if 'build' in s.keys()]
    return services


def getServicesRunning():
    data = runCompose(['docker-compose', 'ps', '--format', 'json'])
    container_list = json.loads(data)
    container_names = [s['name'] for s in container_list]
    return container_names


def getImages():
    data = runCompose(['docker-compose', 'images', '--format', 'json'])
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
    data = runCompose(['docker', 'stats', '--format', 'json', '--no-stream'] + containers)
    stats = json.loads(data)
    return stats
