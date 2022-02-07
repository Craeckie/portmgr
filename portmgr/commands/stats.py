from functools import cmp_to_key

from portmgr import command_list
from compose.cli.command import get_project
from compose.project import OneOffFilter
from operator import attrgetter

from tabulate import tabulate
from humanfriendly import format_size, parse_size


def func(action):
    directory = action['directory']
    relative = action['relative']

    project = get_project('.')

    containers = sorted(
        project.containers(stopped=False) +
        project.containers(one_off=OneOffFilter.only, stopped=False),
        key=attrgetter('name'))

    values = []
    has_network_stats = False
    for container in containers:
        stats = project.client.stats(container.name, stream=False)
        memory = stats["memory_stats"]
        usage = format_size(memory['usage'])
        limit = format_size(memory['limit'])
        if 'networks' in stats:
            network = stats["networks"]
            received = format_size(sum(stats['rx_bytes'] for iface, stats in network.items()))
            sent = format_size(sum(stats['tx_bytes'] for iface, stats in network.items()))
            columns = (container.service, usage, limit, received, sent)
            has_network_stats = True
        else:
            columns = (container.service, usage, limit)
        values.append(columns)
    if values:
        # sort by memory usage
        values = sorted(values, key=cmp_to_key(lambda s1, s2: parse_size(s2[1]) - parse_size(s1[1])))
        print(tabulate(values,
                       headers=['Service', 'Mem Usage', 'Mem Limit', 'Net Recv', 'Net Sent'],
                       colalign=['left', 'right', 'right', 'right', 'right'] if has_network_stats
                           else ['left', 'right', 'right']))
        print('')

    return 0


command_list['o'] = {
    'hlp': 'Show container stats',
    'ord': 'nrm',
    'fnc': func
}
