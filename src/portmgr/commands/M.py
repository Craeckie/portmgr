import os
import tempfile

import yaml

from portmgr import command_list, bcolors
from portmgr import envmove


def _compose_path(directory):
    from portmgr.portmgr import compose_names
    for name in compose_names:
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def _show(entry):
    value = entry.value
    if entry.secret:
        return f"{value[:2]}… ({len(value)} chars)"
    return value if len(value) <= 40 else value[:37] + '...'


def _write_atomic(path, text, new_mode=0o644):
    """Replace `path` via a temp file, keeping its mode (or new_mode if new)."""
    try:
        mode = os.stat(path).st_mode & 0o7777
    except FileNotFoundError:
        mode = new_mode
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.portmgr-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def func(action):
    directory = action['directory']
    relative = action['relative']

    compose_path = _compose_path(directory)
    if not compose_path:
        return 0
    with open(compose_path, encoding='utf-8', newline='') as fh:
        compose_text = fh.read()
    try:
        entries = envmove.collect_env(compose_text)
    except yaml.YAMLError as exc:
        print(f"  {relative}: cannot parse {os.path.basename(compose_path)}: {exc}")
        return 1

    for entry in entries:
        if entry.skip and not entry.quiet:
            print(f"  skip {'/'.join(entry.services)} {entry.key}: {entry.skip}")
    movable = [e for e in entries if not e.skip]
    if not movable:
        print("  nothing to move")
        return 0

    default = {i for i, e in enumerate(movable) if e.secret}
    width = max(len('/'.join(e.services)) for e in movable)
    key_width = max(len(e.key) for e in movable)
    for i, entry in enumerate(movable, 1):
        mark = f"{bcolors.OKGREEN}[x]{bcolors.ENDC}" if i - 1 in default else '[ ]'
        svc = '/'.join(entry.services)
        print(f"  {mark} {i:>2}  {svc:<{width}}  {entry.key:<{key_width}}  {_show(entry)}")

    try:
        while True:
            answer = input("  Move which? [Enter = marked, 1,3-5, a = all, n = none]: ")
            try:
                chosen = envmove.parse_selection(answer, len(movable), default)
                break
            except ValueError as exc:
                print(f"  {exc}")
        if not chosen:
            print("  nothing selected")
            return 0

        dotenv_path = os.path.join(directory, '.env')
        existing = ''
        if os.path.isfile(dotenv_path):
            with open(dotenv_path, encoding='utf-8', newline='') as fh:
                existing = fh.read()
        reserved = envmove.DEFAULT_RESERVED | set(os.environ)
        moves = envmove.plan_moves([movable[i] for i in sorted(chosen)],
                                   envmove.parse_dotenv(existing), compose_text, reserved)

        for move in moves:
            where = 'append to .env' if move.append else 'already in .env'
            print(f"  {'/'.join(move.entry.services)} {move.entry.key} -> ${{{move.name}}}  ({where})")
        if input("  Write .env and update the compose file? [y/N]: ").strip().lower() not in ('y', 'yes'):
            print("  aborted, nothing written")
            return 0
    except EOFError:
        print("\n  no input, nothing written")
        return 1

    pairs = [(m.name, m.entry.value) for m in moves if m.append]
    if pairs:
        # .env first: a compose file referencing a missing variable would
        # silently start the container with an empty value.
        _write_atomic(dotenv_path, envmove.dotenv_append_text(existing, pairs), new_mode=0o600)
    _write_atomic(compose_path, envmove.apply_compose(compose_text, moves))
    print(f"  moved {len(moves)} value(s); seal them with: portmgr E .env")
    return 0


command_list['M'] = {
    'hlp': 'Move literal environment values from the compose file into .env',
    'ord': 'nrm',
    'fnc': func,
}
