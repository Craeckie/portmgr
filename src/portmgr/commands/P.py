import json
import os
import re
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


def _compose_services(directory, interpolate=True):
    args = ['docker', 'compose', 'config', '--format', 'json']
    if not interpolate:
        args.append('--no-interpolate')
    try:
        data = check_output(args, cwd=directory, stderr=PIPE)
        return json.loads(data).get('services', {})
    except Exception:
        return {}


# A value that is exactly one variable reference: $NAME, ${NAME}, ${NAME:-x},
# ${NAME-x}, ${NAME:?x}, ${NAME?x}. `${NAME:+x}` is not the variable's value.
_REF = re.compile(r'^\$(?:\{([A-Za-z_]\w*)(?::?[-?][^}]*)?\}|([A-Za-z_]\w*))$')


def _env_dict(env):
    """`config --no-interpolate` keeps a list-form environment as K=V strings."""
    if isinstance(env, list):
        return dict(e.split('=', 1) if '=' in e else (e, None) for e in env)
    return env or {}


def _env_name(raw_env, key):
    """(.env name, is_reference) for a container key, or (None, raw) if its
    value mixes a reference with other text and can't be rotated."""
    raw = raw_env.get(key)
    if not isinstance(raw, str) or '$' not in raw:
        return key, False
    m = _REF.match(raw)
    if not m:
        return None, raw
    return m.group(1) or m.group(2), True


def _exec(directory, svc, cmd_args):
    return run(
        ['docker', 'compose', 'exec', '-T', svc] + cmd_args,
        cwd=directory, capture_output=True, text=True
    )


def _failure(result):
    output = ' | '.join(o.strip() for o in (result.stderr, result.stdout) if o and o.strip())
    return f'exit {result.returncode}: {output or "(no output)"}'


def _sql_str(value):
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


def _rotate_postgres(directory, svc_name, env, new_password):
    user = env.get('POSTGRES_USER', 'postgres')
    if not env.get('POSTGRES_PASSWORD'):
        return [], 'POSTGRES_PASSWORD not set — skipping'

    new_pass = new_password('POSTGRES_PASSWORD')
    sql = f"ALTER USER {user} WITH PASSWORD '{new_pass}';"
    result = _exec(directory, svc_name, ['psql', '-U', user, '-d', 'postgres', '-c', sql])
    if result.returncode != 0:
        return [], f'psql failed ({_failure(result)}); attempted new={new_pass}'

    return ['POSTGRES_PASSWORD'], None


def _mariadb_client(directory, svc_name):
    """Name of the client in the container: `mariadb`, else `mysql` (mysql/mysql-server
    and older images only ship the latter)."""
    result = _exec(directory, svc_name, ['sh', '-c', 'command -v mariadb || command -v mysql'])
    found = result.stdout.strip().splitlines()
    client = os.path.basename(found[-1]) if found else ''
    if result.returncode != 0 or not client:
        return None, f'no mariadb/mysql client in container ({_failure(result)})'
    return client, None


def _mariadb_alter(directory, svc_name, client, root_pass, user, new_pass):
    """ALTER every host entry of `user` in one statement; returns an error or None."""
    base = [client, '-u', 'root', f'--password={root_pass}', '-N', '-B', '-e']
    result = _exec(directory, svc_name,
                   base + [f"SELECT Host FROM mysql.user WHERE User={_sql_str(user)};"])
    if result.returncode != 0:
        return f'listing hosts of {user} failed ({_failure(result)})'
    hosts = [h for h in result.stdout.splitlines() if h.strip()]
    if not hosts:
        return f'no account named {user} in mysql.user'
    specs = ', '.join(f"{_sql_str(user)}@{_sql_str(h)} IDENTIFIED BY '{new_pass}'"
                      for h in hosts)
    result = _exec(directory, svc_name, base + [f"ALTER USER {specs}; FLUSH PRIVILEGES;"])
    if result.returncode != 0:
        return f'ALTER USER {user} failed ({_failure(result)}); attempted new={new_pass}'
    return None


def _rotate_mariadb(directory, svc_name, env, new_password):
    root_key = 'MARIADB_ROOT_PASSWORD' if 'MARIADB_ROOT_PASSWORD' in env else 'MYSQL_ROOT_PASSWORD'
    old_root = env.get(root_key, '')
    if not old_root:
        return [], f'{root_key} not set — skipping'

    client, err = _mariadb_client(directory, svc_name)
    if err:
        return [], err

    new_root = new_password(root_key)
    err = _mariadb_alter(directory, svc_name, client, old_root, 'root', new_root)
    if err:
        return [], f'mariadb root: {err}'
    rotated = [root_key]

    # App user (optional)
    user_key = next((k for k in ('MARIADB_USER', 'MYSQL_USER') if k in env), None)
    pass_key = next((k for k in ('MARIADB_PASSWORD', 'MYSQL_PASSWORD') if k in env), None)
    if user_key and pass_key and env.get(user_key):
        new_user_pass = new_password(pass_key)
        err = _mariadb_alter(directory, svc_name, client, new_root, env[user_key], new_user_pass)
        if err:
            # Root already rotated; report partial success
            return rotated, f'mariadb user: {err}'
        rotated.append(pass_key)

    return rotated, None


def func(action):
    directory = action['directory']
    relative = action['relative']

    services = _compose_services(directory)
    if not services:
        return 0
    raw_services = _compose_services(directory, interpolate=False)

    dotenv_path = os.path.join(directory, '.env')
    current_dotenv_keys = set(_dotenv_read(dotenv_path).keys())
    all_updates = {}

    for svc_name, svc_cfg in services.items():
        image = svc_cfg.get('image', '')
        db_type = _db_type(image)
        if not db_type:
            continue

        env = svc_cfg.get('environment') or {}
        raw_env = _env_dict((raw_services.get(svc_name) or {}).get('environment'))

        # Map each password key to the .env name it comes from; refuse the whole
        # service if one of them is built from a reference plus other text.
        names, mixed = {}, None
        for key in env:
            if 'PASSWORD' in key:
                name, is_ref = _env_name(raw_env, key)
                if name is None:
                    mixed = f'{key} is {is_ref!r}, not a single ${{VAR}} — not rotating'
                    break
                names[key] = (name, is_ref)
        if mixed:
            print(f'  {relative}/{svc_name}: {mixed}')
            continue

        # Keys that read the same variable must get the same new password.
        by_name = {}

        def new_password(key):
            name = names[key][0]
            if name not in by_name:
                by_name[name] = all_updates.get(name) or _gen_password()
            return by_name[name]

        if db_type == 'postgres':
            rotated, err = _rotate_postgres(directory, svc_name, env, new_password)
        else:
            rotated, err = _rotate_mariadb(directory, svc_name, env, new_password)

        for key in rotated:
            name, is_ref = names[key]
            new = by_name[name]
            all_updates[name] = new
            print(f'  {relative}/{svc_name}: {name}  old={env[key]}  new={new}')
            if name not in current_dotenv_keys:
                if is_ref:
                    print(f'  {relative}/{svc_name}: NOTE — {name} was not in .env before '
                          f'rotation (set in the shell?); a shell value overrides .env')
                else:
                    print(f'  {relative}/{svc_name}: NOTE — {name} was not in .env before '
                          f'rotation; update compose file to use ${{VAR}} references so '
                          f'future restarts pick up the new password')
        if err:
            print(f'  {relative}/{svc_name}: {err}')

    if all_updates:
        _dotenv_write(dotenv_path, all_updates)
        print(f'  {relative}: wrote {len(all_updates)} key(s) to .env')

    return 0


command_list['R'] = {
    'hlp': 'Rotate postgres/mariadb passwords and write new values to .env',
    'ord': 'nrm',
    'fnc': func,
}
