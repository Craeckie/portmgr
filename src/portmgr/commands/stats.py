from functools import cmp_to_key

from portmgr import command_list

from tabulate import tabulate
from humanfriendly import format_size, parse_size

from portmgr.wrapper import getStats


def func(action):
    directory = action['directory']
    relative = action['relative']

    stats_list = getStats()

    values = []
    has_network_stats = False
    for stats in stats_list:
        name = stats['Name'] if 'Name' in stats else stats['Container']
        #memory = stats["memory_stats"]
        #usage = format_size(memory['usage'])
        #limit = format_size(memory['limit'])
        memory_string = stats["MemUsage"]
        usage, limit = [p.strip() for p in memory_string.split('/')]
        if 'NetIO' in stats:
            network = stats["NetIO"]
            received, sent = [p.strip() for p in memory_string.split('/')]
            #received = format_size(sum(stats['rx_bytes'] for iface, stats in network.items()))
            #sent = format_size(sum(stats['tx_bytes'] for iface, stats in network.items()))
            columns = (stats['Name'], usage, limit, received, sent)
            has_network_stats = True
        else:
            columns = (stats['Name'], usage, limit)
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
