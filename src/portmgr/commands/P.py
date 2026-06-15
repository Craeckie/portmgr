import json
import os
import secrets as pysecrets
import string
from subprocess import run, check_output, PIPE

from portmgr import command_list

_ALPHABET = string.ascii_letters + string.digits
_PW_LEN = 32

_POSTGRES_IMGS = ('postgres', 'postgresql')
_MARIADB_IMGS = ('mariadb', 'mysql')


def _gen_password():
    return ''.join(pysecrets.choice(_ALPHABET) for _ in range(_PW_LEN))


def _db_type(image):
    img = (image or '').lower()
    if any(k in img for k in _POSTGRES_IMGS):
        return 'postgres'
    if any(k in img for k in _MARIADB_IMGS):
        return 'mariadb'
    return None


def _dotenv_write(path, updates):
    """Update existing .env keys in-place; append unknown ones at the end."""
    lines = []
    seen = set()
    if os.path.isfile(path):
        with open(path) as f:
            for line in f:
                stripped = line.rstrip('\n')
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    k = stripped.partition('=')[0].strip()
                    if k in updates:
                        lines.append(f'{k}={updates[k]}\n')
                        seen.add(k)
                        continue
                lines.append(line if line.endswith('\n') else line + '\n')
    for k, v in updates.items():
        if k not in seen:
            lines.append(f'{k}={v}\n')
    with open(path, 'w') as f:
        f.writelines(lines)


def _dotenv_read(path):
    result = {}
    if not os.path.isfile(path):
        return result
    with open(path) as f:
        for line in f:
            stripped = line.rstrip('\n')
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                continue
            k, _, v = stripped.partition('=')
            result[k.strip()] = v
    return result


def _compose_services(directory):
    try:
        data = check_output(
            ['docker', 'compose', 'config', '--format', 'json'],
            cwd=directory, stderr=PIPE
        )
        return json.loads(data).get('services', {})
    except Exception:
        return {}


def _exec(directory, svc, cmd_args):
    return run(
        ['docker', 'compose', 'exec', '-T', svc] + cmd_args,
        cwd=directory, capture_output=True, text=True
    )


def _rotate_postgres(directory, svc_name, env):
    user = env.get('POSTGRES_USER', 'postgres')
    if not env.get('POSTGRES_PASSWORD'):
        return {}, 'POSTGRES_PASSWORD not set — skipping'

    new_pass = _gen_password()
    sql = f"ALTER USER {user} WITH PASSWORD '{new_pass}';"
    result = _exec(directory, svc_name, ['psql', '-U', user, '-c', sql])
    if result.returncode != 0:
        return {}, f'psql failed: {result.stderr.strip()}'

    return {'POSTGRES_PASSWORD': new_pass}, None


def _rotate_mariadb(directory, svc_name, env):
    root_key = 'MARIADB_ROOT_PASSWORD' if 'MARIADB_ROOT_PASSWORD' in env else 'MYSQL_ROOT_PASSWORD'
    old_root = env.get(root_key, '')
    if not old_root:
        return {}, f'{root_key} not set — skipping'

    updates = {}
    new_root = _gen_password()

    sql = f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{new_root}'; FLUSH PRIVILEGES;"
    result = _exec(directory, svc_name,
                   ['mariadb', '-u', 'root', f'--password={old_root}', '-e', sql])
    if result.returncode != 0:
        return {}, f'mariadb root ALTER failed: {result.stderr.strip()}'
    updates[root_key] = new_root

    # App user (optional)
    user_key = next((k for k in ('MARIADB_USER', 'MYSQL_USER') if k in env), None)
    pass_key = next((k for k in ('MARIADB_PASSWORD', 'MYSQL_PASSWORD') if k in env), None)
    if user_key and pass_key and env.get(user_key):
        app_user = env[user_key]
        new_user_pass = _gen_password()
        sql2 = f"ALTER USER '{app_user}'@'%' IDENTIFIED BY '{new_user_pass}'; FLUSH PRIVILEGES;"
        result2 = _exec(directory, svc_name,
                        ['mariadb', '-u', 'root', f'--password={new_root}', '-e', sql2])
        if result2.returncode != 0:
            # Root already rotated; report partial success
            return updates, f'mariadb user ALTER failed: {result2.stderr.strip()}'
        updates[pass_key] = new_user_pass

    return updates, None


def func(action):
    directory = action['directory']
    relative = action['relative']

    services = _compose_services(directory)
    if not services:
        return 0

    dotenv_path = os.path.join(directory, '.env')
    current_dotenv_keys = set(_dotenv_read(dotenv_path).keys())
    all_updates = {}

    for svc_name, svc_cfg in services.items():
        image = svc_cfg.get('image', '')
        db_type = _db_type(image)
        if not db_type:
            continue

        env = svc_cfg.get('environment') or {}

        if db_type == 'postgres':
            updates, err = _rotate_postgres(directory, svc_name, env)
        else:
            updates, err = _rotate_mariadb(directory, svc_name, env)

        if err:
            print(f'  {relative}/{svc_name}: {err}')
        if updates:
            all_updates.update(updates)
            print(f'  {relative}/{svc_name}: rotated {", ".join(updates.keys())}')
            hardcoded = [k for k in updates if k not in current_dotenv_keys]
            if hardcoded:
                print(f'  {relative}/{svc_name}: NOTE — {", ".join(hardcoded)} '
                      f'was not in .env before rotation; update compose file to '
                      f'use ${{VAR}} references so future restarts pick up the new password')

    if all_updates:
        _dotenv_write(dotenv_path, all_updates)
        print(f'  {relative}: wrote {len(all_updates)} key(s) to .env')

    return 0


command_list['R'] = {
    'hlp': 'Rotate postgres/mariadb passwords and write new values to .env',
    'ord': 'nrm',
    'fnc': func,
}
