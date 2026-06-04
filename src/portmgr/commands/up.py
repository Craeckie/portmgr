from portmgr import command_list, bcolors, runCompose
from portmgr import secrets

_unsealed_count = [0]
_total_count = [0]


def func(action):
    directory = action['directory']
    relative = action['relative']

    try:
        res = runCompose(["up", "-d"])
    except Exception as exc:
        print("Error creating " + relative + ": " + str(exc))
        res = 1

    if res != 0:
        print("Error creating " + relative + "!")

    try:
        _total_count[0] += 1
        state, _ = secrets.service_status(directory)
        if state != 'DONE':
            _unsealed_count[0] += 1
    except Exception:
        pass

    return 0


def fin():
    if _unsealed_count[0] > 0:
        print(
            f"\n{bcolors.WARNING}⚠ {_unsealed_count[0]}/{_total_count[0]} "
            f"services not yet sealed{bcolors.ENDC}"
        )
    _unsealed_count[0] = 0
    _total_count[0] = 0


command_list['u'] = {
    'hlp': 'Create container',
    'ord': 'nrm',
    'fnc': func,
    'fin': fin
}
