import os

from portmgr import command_list, command_extra
from portmgr import secrets


def func(action):
    if not command_extra:
        print("Usage: portmgr e <file> [file ...]")
        return 1

    pyrage = secrets._load_pyrage()
    if pyrage is None:
        return 1

    directory = action['directory']
    relative = action['relative']

    for arg in command_extra:
        path = os.path.join(directory, arg) if not os.path.isabs(arg) else arg
        if not os.path.isfile(path):
            print(f"  {relative}: file not found: {arg}")
            continue
        try:
            secrets.seal(path)
            print(f"  {relative}: sealed {os.path.basename(path)} -> {os.path.basename(path)}.age")
        except Exception as exc:
            print(f"  {relative}: failed to seal {arg}: {exc}")
            return 1

    from portmgr.portmgr import compose_names
    compose_path = None
    for name in compose_names:
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            compose_path = candidate
            break
    if compose_path:
        remaining = secrets.find_secret_keys(compose_path)
        if remaining:
            print(f"  {relative}: literal secrets still present in compose file:")
            for svc, key in remaining:
                print(f"    {svc}: {key}")

    return 0


command_list['e'] = {
    'hlp': 'Encrypt/seal secret file(s) (age)',
    'ord': 'nrm',
    'fnc': func
}
