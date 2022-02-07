from portmgr import command_list
from compose.cli.command import get_project
from compose.project import OneOffFilter
from operator import attrgetter

from tabulate import tabulate
from humanfriendly import format_size


def func(action):
    directory = action['directory']
    relative = action['relative']

    project = get_project('.')

    containers = sorted(
        project.containers() +
        project.containers(one_off=OneOffFilter.only, stopped=False),
        key=attrgetter('name'))

    values = []
    for container in containers:
        stats = project.client.stats(container.name, stream=False)
        memory = stats["memory_stats"]
        usage = format_size(memory['usage'])
        limit = format_size(memory['limit'])
        network = stats["networks"]
        received = format_size(sum(stats['rx_bytes'] for iface, stats in network.items()))
        sent = format_size(sum(stats['tx_bytes'] for iface, stats in network.items()))
        values.append((container.service, usage, limit, received, sent))
    print(tabulate(values,
                   headers=['Service', 'Mem Usage', 'Mem Limit', 'Net Recv', 'Net Sent'],
                   colalign=['left', 'right', 'right', 'right', 'right']))

    return 0


command_list['o'] = {
    'hlp': 'Show container stats',
    'ord': 'nrm',
    'fnc': func
}
