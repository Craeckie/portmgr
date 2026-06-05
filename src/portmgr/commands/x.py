import os

from portmgr import command_list, command_extra
from portmgr import secrets


def func(action):
    pyrage = secrets._load_pyrage()
    if pyrage is None:
        return 1

    force = '--force' in command_extra
    directory = action['directory']
    relative = action['relative']

    # glob('*.age') skips dotfiles; list and filter manually to catch .env.age etc.
    age_files = sorted(
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.endswith('.age') and os.path.isfile(os.path.join(directory, f))
    )
    if not age_files:
        return 0

    for age_path in age_files:
        target = age_path[:-4]
        if os.path.exists(target) and not force:
            continue
        try:
            result = secrets.unseal(age_path, force=force)
            if result != "skipped":
                print(f"  {relative}: decrypted {os.path.basename(age_path)}")
        except RuntimeError as exc:
            print(f"  {relative}: {exc}")
            return 1
        except Exception as exc:
            print(f"  {relative}: failed to decrypt {os.path.basename(age_path)}: {exc}")
            return 1

    return 0


command_list['x'] = {
    'hlp': 'Decrypt/unseal sealed secret files (age)',
    'ord': 'nrm',
    'fnc': func,
    'standalone': True
}
