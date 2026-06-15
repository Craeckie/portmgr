from portmgr import command_list, bcolors
from portmgr import secrets

_counts = {'DONE': 0, 'INCONSISTENT': 0, 'PENDING': 0, 'CLEAN': 0}

_STATE_COLOR = {
    'DONE':         bcolors.OKGREEN,
    'INCONSISTENT': bcolors.WARNING,
    'PENDING':      bcolors.FAIL,
    'CLEAN':        bcolors.OKBLUE,
}


def func(action):
    directory = action['directory']
    relative = action['relative']

    try:
        state, keys = secrets.service_status(directory)
    except Exception as exc:
        print(f"  {relative}: error reading status: {exc}")
        return 1

    color = _STATE_COLOR.get(state, '')
    line = f"  {color}{state}{bcolors.ENDC}  {relative}"
    if keys:
        key_list = ', '.join(f"{svc}/{k}" for svc, k in keys)
        line += f"  [{key_list}]"
    print(line)

    _counts[state] += 1
    return 0


def fin():
    total = sum(_counts.values())
    done = _counts['DONE']
    print(
        f"\n{done}/{total} services sealed  "
        f"({_counts['PENDING']} pending, "
        f"{_counts['INCONSISTENT']} inconsistent, "
        f"{_counts['CLEAN']} clean)"
    )
    for k in _counts:
        _counts[k] = 0


command_list['S'] = {
    'hlp': 'Show secret migration status',
    'ord': 'nrm',
    'fnc': func,
    'fin': fin
}
