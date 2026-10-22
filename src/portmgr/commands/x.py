import os

from portmgr import command_list, command_extra
from portmgr import sealing, secrets


def func(action):
    pyrage = secrets._load_pyrage()
    if pyrage is None:
        return 1

    force = '--force' in command_extra
    directory = action['directory']
    relative = action['relative']

    # Also catches dotfiles (.env.age) and files in subdirectories (config/*.age).
    age_files = sealing.find_age_files([directory])
    if not age_files:
        return 0

    for age_path in age_files:
        target = age_path[:-4]
        if os.path.exists(target) and not force:
            continue
        try:
            result = secrets.unseal(age_path, force=force)
            if result != "skipped":
                print(f"  {relative}: decrypted {os.path.relpath(age_path, directory)}")
        except sealing.NotForThisHost:
            print(f"  {relative}: {os.path.relpath(age_path, directory)} is not sealed for this host, skipped")
        except RuntimeError as exc:
            print(f"  {relative}: {exc}")
            return 1
        except Exception as exc:
            print(f"  {relative}: failed to decrypt {os.path.relpath(age_path, directory)}: {exc}")
            return 1

    return 0


command_list['D'] = {
    'hlp': 'Decrypt/unseal sealed secret files (age)',
    'ord': 'nrm',
    'fnc': func,
    'standalone': True
}
