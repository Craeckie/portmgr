import functools
import os
import re
from datetime import datetime

import yaml

from portmgr import sealing
from portmgr.sealing import (  # noqa: F401 (re-exported for the commands and tests)
    _cache_passphrase,
    _clear_passphrase,
    _load_pyrage,
    get_passphrase,
)

SECRET_KEY_PATTERN = re.compile(
    r"(?i)(PASS(WORD)?|SECRET|TOKEN|KEY|AUTHKEY|APIKEY|CREDENTIAL)"
)


def dckrsub_resolver(plain_path, base_dir, config):
    """Hosts whose dckrsub chain (their `sub` in the recipients file) reaches the
    file's nearest ancestor directory below base_dir."""
    from portmgr import portmgr

    reached = {}
    for host, entry in config["hosts"].items():
        if entry.get("sub"):
            names = tuple(portmgr.parse_sub_names(entry["sub"]))
            reached[host] = _reached_dirs(os.path.normpath(base_dir), names)
    base = os.path.normpath(base_dir)
    directory = os.path.dirname(os.path.abspath(plain_path))
    while directory.startswith(base + os.sep):
        hosts = [h for h, dirs in reached.items() if directory in dirs]
        if hosts:
            return hosts
        directory = os.path.dirname(directory)
    return []


@functools.lru_cache(maxsize=None)
def _reached_dirs(base_dir, names):
    from portmgr import portmgr

    return frozenset(os.path.normpath(p) for kind, p in portmgr.walk(base_dir, list(names)) if kind == 'dir')


def seal(path):
    age_path = sealing.seal(path, resolver=dckrsub_resolver)
    write_migrated(os.path.dirname(os.path.abspath(path)))
    return age_path


def unseal(path_age, force=False):
    return sealing.unseal(path_age, force=force)


def mark_migrated_if_stack(path):
    """after_seal hook for portseal: write .migrated next to a compose file."""
    from portmgr.portmgr import compose_names

    directory = os.path.dirname(path)
    if any(os.path.isfile(os.path.join(directory, name)) for name in compose_names):
        write_migrated(directory)


def find_secret_keys(compose_path):
    if not os.path.isfile(compose_path):
        return []
    with open(compose_path, "r") as fh:
        try:
            doc = yaml.load(fh, Loader=yaml.SafeLoader)
        except yaml.YAMLError:
            return []
    if not isinstance(doc, dict):
        return []
    services = doc.get("services") or {}
    ref_pattern = re.compile(r"^\$\{[^}]+\}$|^\$[A-Za-z_][A-Za-z0-9_]*$")
    results = []
    for svc_name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        env = svc.get("environment")
        if env is None:
            continue
        if isinstance(env, dict):
            items = env.items()
        elif isinstance(env, list):
            items = []
            for entry in env:
                if isinstance(entry, str) and "=" in entry:
                    k, _, v = entry.partition("=")
                    items.append((k, v))
                elif isinstance(entry, str):
                    items.append((entry, None))
        else:
            continue
        for key, value in items:
            if not SECRET_KEY_PATTERN.search(key):
                continue
            if value is None or value == "":
                continue
            if ref_pattern.match(str(value)):
                continue
            results.append((svc_name, key))
    return results


def write_migrated(directory):
    path = os.path.join(directory, ".migrated")
    with open(path, "w") as fh:
        fh.write(datetime.now().isoformat() + "\n")


def service_status(directory):
    from portmgr.portmgr import compose_names

    if os.path.isfile(os.path.join(directory, ".migrated")):
        return ("DONE", [])

    compose_path = None
    for name in compose_names:
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            compose_path = candidate
            break

    secret_keys = find_secret_keys(compose_path) if compose_path else []

    if secret_keys:
        return ("PENDING", secret_keys)
    else:
        return ("CLEAN", [])
