import os
import re
from datetime import datetime

import yaml

_passphrase = None


def _load_pyrage():
    try:
        import pyrage
        return pyrage
    except ImportError:
        print("pyrage is required for secret commands. Install with: pip install portmgr[secrets]")
        return None


def get_passphrase():
    """Return (passphrase, source) where source is 'cache', 'env', or 'tty'."""
    global _passphrase
    if _passphrase is not None:
        return _passphrase, 'cache'
    env = os.environ.get("PORTMGR_PASSPHRASE")
    if env:
        return env, 'env'
    try:
        with open("/dev/tty", "r") as tty:
            import getpass
            return getpass.getpass("Passphrase: ", stream=tty), 'tty'
    except OSError:
        raise RuntimeError(
            "No passphrase available: set PORTMGR_PASSPHRASE or run interactively"
        )


def _cache_passphrase(value):
    global _passphrase
    _passphrase = value


def _clear_passphrase():
    global _passphrase
    _passphrase = None


def seal(path):
    pyrage = _load_pyrage()
    if pyrage is None:
        raise ImportError("pyrage not available")
    path = os.path.abspath(path)
    with open(path, "rb") as fh:
        data = fh.read()
    passphrase, _ = get_passphrase()
    encrypted = pyrage.passphrase.encrypt(data, passphrase)
    age_path = path + ".age"
    with open(age_path, "wb") as fh:
        fh.write(encrypted)
    directory = os.path.dirname(path)
    gitignore_append(directory, os.path.basename(path))
    write_migrated(directory)


def unseal(path_age, force=False):
    pyrage = _load_pyrage()
    if pyrage is None:
        raise ImportError("pyrage not available")
    path_age = os.path.abspath(path_age)
    if not path_age.endswith(".age"):
        raise ValueError(f"Not a sealed file: {path_age}")
    target = path_age[:-4]
    if os.path.exists(target) and not force:
        return "skipped"
    with open(path_age, "rb") as fh:
        data = fh.read()
    while True:
        passphrase, source = get_passphrase()
        try:
            plaintext = pyrage.passphrase.decrypt(data, passphrase)
            break
        except Exception:
            _clear_passphrase()
            if source in ('env', 'cache'):
                raise ValueError(
                    f"Wrong passphrase for {os.path.basename(path_age)}. "
                    f"Check PORTMGR_PASSPHRASE."
                )
            print(f"Wrong passphrase for {os.path.basename(path_age)}, try again.")
    with open(target, "wb") as fh:
        fh.write(plaintext)
    _cache_passphrase(passphrase)
    return "decrypted"


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
    pattern = re.compile(
        r"(?i)(PASS(WORD)?|SECRET|TOKEN|KEY|AUTHKEY|APIKEY|CREDENTIAL)"
    )
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
            if not pattern.search(key):
                continue
            if value is None or value == "":
                continue
            if ref_pattern.match(str(value)):
                continue
            results.append((svc_name, key))
    return results


def gitignore_append(directory, name):
    path = os.path.join(directory, ".gitignore")
    existing_lines = []
    if os.path.isfile(path):
        with open(path, "r") as fh:
            existing_lines = fh.read().splitlines()
    if name in existing_lines:
        return
    with open(path, "a") as fh:
        if existing_lines and existing_lines[-1] != "":
            fh.write("\n")
        fh.write(name + "\n")


def write_migrated(directory):
    path = os.path.join(directory, ".migrated")
    with open(path, "w") as fh:
        fh.write(datetime.now().isoformat() + "\n")


def service_status(directory):
    from portmgr.portmgr import compose_names

    compose_path = None
    for name in compose_names:
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            compose_path = candidate
            break

    migrated = os.path.isfile(os.path.join(directory, ".migrated"))
    secret_keys = find_secret_keys(compose_path) if compose_path else []

    if migrated and not secret_keys:
        return ("DONE", [])
    elif migrated and secret_keys:
        return ("INCONSISTENT", secret_keys)
    elif not migrated and secret_keys:
        return ("PENDING", secret_keys)
    else:
        return ("CLEAN", [])
