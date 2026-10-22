"""Seal files with age to per-host keys, independent of compose and dckrsub.

A ``seal-recipients.yml`` in the file's directory or above names the hosts'
public keys, the recovery key(s) every file is sealed to, and path rules that
say which hosts get which file. Without one, files are sealed with the shared
passphrase as before. Nothing here imports the rest of portmgr; callers pass a
``resolver(plain_path, base_dir, config) -> [host, ...]`` to add their own
lookup after the rules.
"""
import argparse
import base64
import fnmatch
import hashlib
import os
import sys

import yaml

RECIPIENTS_NAME = "seal-recipients.yml"
DEFAULT_IDENTITY = "~/.ssh/id_ed25519"

_passphrase = None
_identities = None


class SealError(RuntimeError):
    pass


class NotForThisHost(SealError):
    pass


def _load_pyrage():
    try:
        import pyrage
        return pyrage
    except ImportError:
        print("pyrage is required for secret commands. Install with: pip install portmgr[secrets]")
        return None


def _require_pyrage():
    pyrage = _load_pyrage()
    if pyrage is None:
        raise ImportError("pyrage not available")
    return pyrage


# --- passphrase (old scrypt files) ------------------------------------------

def get_passphrase():
    """Return (passphrase, source) where source is 'cache', 'env', or 'tty'."""
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


def _ask(prompt):
    try:
        with open("/dev/tty", "r") as tty:
            import getpass
            return getpass.getpass(prompt, stream=tty)
    except OSError:
        raise SealError(f"{prompt.rstrip(': ')}: no terminal to ask on")


# --- identities --------------------------------------------------------------

def _clear_identities():
    global _identities
    _identities = None


def _parse_age_keys(text, path):
    pyrage = _require_pyrage()
    keys = [line.strip() for line in text.splitlines() if line.strip().startswith("AGE-SECRET-KEY-")]
    if not keys:
        raise SealError(f"no age or SSH private key in {path}")
    return [pyrage.x25519.Identity.from_str(k) for k in keys]


def _read_identity(path):
    pyrage = _require_pyrage()
    with open(path, "rb") as fh:
        data = fh.read()
    if data.startswith(b"age-encryption.org/v1") or data.startswith(b"-----BEGIN AGE ENCRYPTED FILE"):
        # An identity file protected with `age -p`.
        try:
            text = pyrage.passphrase.decrypt(data, _ask(f"Passphrase for {path}: "))
        except pyrage.DecryptError:
            raise SealError(f"wrong passphrase for {path}")
        return _parse_age_keys(text.decode(), path)
    if b"PRIVATE KEY-----" in data:
        try:
            return [pyrage.ssh.Identity.from_buffer(data)]
        except Exception as exc:
            raise SealError(f"cannot read SSH key {path}: {exc} (passphrase-protected SSH keys are not supported)")
    return _parse_age_keys(data.decode(errors="replace"), path)


def load_identities():
    """Private keys from PORTMGR_IDENTITY (comma-separated paths), else ~/.ssh/id_ed25519."""
    global _identities
    if _identities is not None:
        return _identities
    env = os.environ.get("PORTMGR_IDENTITY")
    if env:
        paths = [os.path.expanduser(p.strip()) for p in env.split(",") if p.strip()]
    else:
        paths = [os.path.expanduser(DEFAULT_IDENTITY)]
    identities = []
    for path in paths:
        if not os.path.isfile(path):
            if env:
                raise SealError(f"identity file not found: {path} (from PORTMGR_IDENTITY)")
            continue
        identities.extend(_read_identity(path))
    _identities = identities
    return identities


# --- recipients file ---------------------------------------------------------

def find_recipients_file(start_dir):
    directory = os.path.abspath(start_dir)
    while True:
        candidate = os.path.join(directory, RECIPIENTS_NAME)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def load_recipients(path):
    with open(path, "r") as fh:
        try:
            doc = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise SealError(f"cannot parse {path}: {exc}")
    if not isinstance(doc, dict):
        raise SealError(f"{path} must be a mapping")
    hosts = doc.get("hosts") or {}
    if not isinstance(hosts, dict) or not all(isinstance(v, dict) for v in hosts.values()):
        raise SealError(f"{path}: 'hosts' must map each host to {{key: ..., sub: ...}}")
    rules = doc.get("rules") or []
    if not isinstance(rules, list) or not all(isinstance(r, dict) and "path" in r for r in rules):
        raise SealError(f"{path}: each entry of 'rules' needs a 'path' and 'hosts'")
    recovery = doc.get("recovery") or []
    if isinstance(recovery, str):
        recovery = [recovery]
    return {"hosts": hosts, "rules": rules, "recovery": recovery}


def expected_recipients(plain_path, recipients_path, config, resolver=None):
    """Return [(name, public key), ...] a file must be sealed to: its hosts, then recovery."""
    base = os.path.dirname(os.path.abspath(recipients_path))
    if not config["recovery"]:
        raise SealError(f"{recipients_path} has no recovery key; refusing to seal")
    relative = os.path.relpath(os.path.abspath(plain_path), base).replace(os.sep, "/")
    hosts = None
    for rule in config["rules"]:
        if fnmatch.fnmatchcase(relative, rule["path"]):
            hosts = list(rule.get("hosts") or [])
            break
    if hosts is None and resolver is not None:
        hosts = list(resolver(plain_path, base, config))
    if not hosts:
        raise SealError(f"no host for {relative}: add a rule to {recipients_path}")
    pairs = []
    for host in hosts:
        key = (config["hosts"].get(host) or {}).get("key")
        if not key:
            raise SealError(f"host {host!r} (for {relative}) has no key in {recipients_path}")
        pairs.append((host, key))
    pairs.extend(("recovery", key) for key in config["recovery"])
    seen = set()
    return [(n, k) for n, k in pairs if not (k in seen or seen.add(k))]


def _recipient(name, key):
    pyrage = _require_pyrage()
    try:
        if key.startswith("ssh-"):
            return pyrage.ssh.Recipient.from_str(key)
        return pyrage.x25519.Recipient.from_str(key)
    except Exception as exc:
        raise SealError(f"invalid public key for {name}: {exc}")


def ssh_tag(public_key):
    """The tag age writes into an ssh stanza: base64 of sha256(key blob)[:4]."""
    blob = base64.b64decode(public_key.split()[1])
    return base64.b64encode(hashlib.sha256(blob).digest()[:4]).decode().rstrip("=")


# --- file header -------------------------------------------------------------

def header_stanzas(data):
    """[(type, [args])] from an age file's header, binary or armored."""
    if data.startswith(b"-----BEGIN AGE ENCRYPTED FILE-----"):
        body = b"".join(line for line in data.splitlines()[1:] if not line.startswith(b"-----"))
        data = base64.b64decode(body)
    stanzas = []
    for line in data.split(b"\n"):
        if line.startswith(b"---"):
            break
        if line.startswith(b"-> "):
            parts = line[3:].decode(errors="replace").split()
            if parts:
                stanzas.append((parts[0], parts[1:]))
    return stanzas


def _is_passphrase(stanzas):
    return any(t == "scrypt" for t, _ in stanzas)


def _ssh_tags(stanzas):
    return sorted(args[0] for t, args in stanzas if t.startswith("ssh-") and args)


def _x25519_count(stanzas):
    return sum(1 for t, _ in stanzas if t == "X25519")


def _matches(stanzas, expected):
    keys = [k for _, k in expected]
    return (_ssh_tags(stanzas) == sorted(ssh_tag(k) for k in keys if k.startswith("ssh-"))
            and _x25519_count(stanzas) == sum(1 for k in keys if not k.startswith("ssh-")))


def _ordered(names, config):
    order = list(config["hosts"]) + ["recovery"] if config else ["recovery"]
    unique = list(dict.fromkeys(names))
    return sorted(unique, key=lambda n: order.index(n) if n in order else len(order))


def _names(stanzas, config, expected):
    tags = {}
    if config:
        for host, entry in config["hosts"].items():
            key = entry.get("key") or ""
            if key.startswith("ssh-"):
                tags[ssh_tag(key)] = host
        for key in config["recovery"]:
            if key.startswith("ssh-"):
                tags[ssh_tag(key)] = "recovery"
    names = [tags.get(tag, "?" + tag) for tag in _ssh_tags(stanzas)]
    count = _x25519_count(stanzas)
    x_names = [n for n, k in (expected or []) if not k.startswith("ssh-")]
    if expected is not None and count == len(x_names):
        names.extend(x_names)
    elif count:
        names.append(f"{count} x25519")
    return _ordered(names, config)


def _inspect(path_age, resolver):
    recipients_path = find_recipients_file(os.path.dirname(os.path.abspath(path_age)))
    config = load_recipients(recipients_path) if recipients_path else None
    expected = error = None
    if config is not None:
        try:
            expected = expected_recipients(path_age[:-4], recipients_path, config, resolver)
        except SealError as exc:
            error = str(exc)
    else:
        error = f"no {RECIPIENTS_NAME} above this file"
    return config, expected, error


# --- operations --------------------------------------------------------------

def _write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def _decrypt(data, path_age):
    pyrage = _require_pyrage()
    name = os.path.basename(path_age)
    if _is_passphrase(header_stanzas(data)):
        while True:
            passphrase, source = get_passphrase()
            try:
                plaintext = pyrage.passphrase.decrypt(data, passphrase)
                break
            except Exception:
                _clear_passphrase()
                if source in ('env', 'cache'):
                    raise ValueError(f"Wrong passphrase for {name}. Check PORTMGR_PASSPHRASE.")
                print(f"Wrong passphrase for {name}, try again.")
        _cache_passphrase(passphrase)
        return plaintext
    identities = load_identities()
    if not identities:
        raise SealError(f"no key to unseal {name}: set PORTMGR_IDENTITY or create {DEFAULT_IDENTITY}")
    try:
        return pyrage.decrypt(data, identities)
    except pyrage.DecryptError:
        raise NotForThisHost(f"{name}: not sealed for this host's key")


def seal(path, resolver=None):
    """Seal ``path`` to ``path.age`` and return the .age path."""
    pyrage = _require_pyrage()
    path = os.path.abspath(path)
    with open(path, "rb") as fh:
        data = fh.read()
    recipients_path = find_recipients_file(os.path.dirname(path))
    if recipients_path is None:
        passphrase, _ = get_passphrase()
        encrypted = pyrage.passphrase.encrypt(data, passphrase)
    else:
        expected = expected_recipients(path, recipients_path, load_recipients(recipients_path), resolver)
        encrypted = pyrage.encrypt(data, [_recipient(n, k) for n, k in expected])
    age_path = path + ".age"
    _write_atomic(age_path, encrypted)
    return age_path


def unseal(path_age, force=False):
    path_age = os.path.abspath(path_age)
    if not path_age.endswith(".age"):
        raise ValueError(f"Not a sealed file: {path_age}")
    target = path_age[:-4]
    if os.path.exists(target) and not force:
        return "skipped"
    with open(path_age, "rb") as fh:
        data = fh.read()
    plaintext = _decrypt(data, path_age)
    with open(target, "wb") as fh:
        fh.write(plaintext)
    return "decrypted"


def status(path_age, resolver=None):
    """{'state': OK|STALE|PASSPHRASE|UNKNOWN, 'hosts', 'expected', 'error'} for one file."""
    with open(path_age, "rb") as fh:
        stanzas = header_stanzas(fh.read())
    config, expected, error = _inspect(path_age, resolver)
    expected_names = _ordered([n for n, _ in expected], config) if expected else None
    if _is_passphrase(stanzas):
        return {"state": "PASSPHRASE", "hosts": [], "expected": expected_names, "error": error}
    hosts = _names(stanzas, config, expected)
    if expected is None:
        state = "UNKNOWN"
    else:
        state = "OK" if _matches(stanzas, expected) else "STALE"
    return {"state": state, "hosts": hosts, "expected": expected_names, "error": error}


def rekey(path_age, resolver=None, force=False):
    """Reseal to the current recipients without writing plaintext; 'rekeyed' or 'current'."""
    pyrage = _require_pyrage()
    with open(path_age, "rb") as fh:
        data = fh.read()
    config, expected, error = _inspect(path_age, resolver)
    if error:
        raise SealError(error)
    stanzas = header_stanzas(data)
    if not force and not _is_passphrase(stanzas) and _matches(stanzas, expected):
        return "current"
    plaintext = _decrypt(data, path_age)
    _write_atomic(path_age, pyrage.encrypt(plaintext, [_recipient(n, k) for n, k in expected]))
    return "rekeyed"


def find_age_files(paths):
    found = []
    for path in paths:
        if os.path.isfile(path):
            if path.endswith(".age"):
                found.append(path)
            continue
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(d for d in dirs if d != ".git")
            found.extend(os.path.join(root, f) for f in sorted(files) if f.endswith(".age"))
    return list(dict.fromkeys(found))


# --- command line ------------------------------------------------------------

_COLORS = {"OK": "\033[92m", "STALE": "\033[91m", "PASSPHRASE": "\033[93m", "UNKNOWN": "\033[91m"}


def _show(path):
    relative = os.path.relpath(path)
    return path if relative.startswith("..") else relative


def _age_files(paths):
    missing = [p for p in paths if not os.path.exists(p)]
    for path in missing:
        print(f"{path}: no such file or directory")
    return find_age_files([p for p in paths if p not in missing]), (1 if missing else 0)


def _cmd_seal(args, resolver, after_seal):
    rc = 0
    for path in args.files:
        if not os.path.isfile(path):
            print(f"{path}: file not found")
            rc = 1
            continue
        try:
            age_path = seal(path, resolver=resolver)
        except Exception as exc:
            print(f"{_show(path)}: {exc}")
            rc = 1
            continue
        if after_seal:
            after_seal(os.path.abspath(path))
        hosts = status(age_path, resolver)["hosts"]
        print(f"sealed {_show(age_path)}" + (f"  [{', '.join(hosts)}]" if hosts else "  (passphrase)"))
    return rc


def _cmd_unseal(args, resolver, after_seal):
    skipped, done = 0, 0
    files, rc = _age_files(args.paths or ["."])
    for path in files:
        try:
            if unseal(path, force=args.force) == "decrypted":
                print(f"decrypted {_show(path)}")
                done += 1
        except NotForThisHost:
            print(f"{_show(path)}: not sealed for this host")
            skipped += 1
        except Exception as exc:
            print(f"{_show(path)}: {exc}")
            rc = 1
    print(f"\n{done} decrypted, {skipped} not sealed for this host")
    return rc


def _cmd_rekey(args, resolver, after_seal):
    counts = {"rekeyed": 0, "current": 0}
    files, rc = _age_files(args.paths or ["."])
    for path in files:
        try:
            result = rekey(path, resolver=resolver, force=args.all)
        except Exception as exc:
            print(f"{_show(path)}: {exc}")
            rc = 1
            continue
        counts[result] += 1
        if result == "rekeyed":
            print(f"rekeyed {_show(path)}  [{', '.join(status(path, resolver)['hosts'])}]")
    print(f"\n{counts['rekeyed']} rekeyed, {counts['current']} already current")
    return rc


def _cmd_status(args, resolver, after_seal):
    color = sys.stdout.isatty()
    counts = {}
    files, rc = _age_files(args.paths or ["."])
    for path in files:
        try:
            info = status(path, resolver)
        except Exception as exc:
            info = {"state": "UNKNOWN", "hosts": [], "expected": None, "error": str(exc)}
        state = info["state"]
        counts[state] = counts.get(state, 0) + 1
        label = f"{_COLORS[state]}{state:<10}\033[0m" if color else f"{state:<10}"
        line = f"  {label}  {_show(path)}"
        if info["hosts"]:
            line += f"  [{', '.join(info['hosts'])}]"
        if state in ("STALE", "PASSPHRASE") and info["expected"]:
            line += f"  -> should be [{', '.join(info['expected'])}]"
        if state == "UNKNOWN" and info["error"]:
            line += f"  ({info['error']})"
        print(line)
    total = sum(counts.values())
    print(f"\n{counts.get('OK', 0)}/{total} OK" + "".join(
        f", {n} {s.lower()}" for s, n in counts.items() if s != "OK"))
    return 0 if rc == 0 and counts.get("OK", 0) == total else 1


def main(argv=None, resolver=None, after_seal=None, prog="portseal"):
    parser = argparse.ArgumentParser(
        prog=prog,
        description=f"Seal files with age to per-host keys listed in {RECIPIENTS_NAME}.")
    sub = parser.add_subparsers(dest="cmd", metavar="command", required=True)
    p = sub.add_parser("e", help="seal file(s) to <file>.age")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=_cmd_seal)
    p = sub.add_parser("d", help="unseal every *.age below the path(s) (default: .)")
    p.add_argument("--force", action="store_true", help="overwrite existing plaintext")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=_cmd_unseal)
    p = sub.add_parser("k", help="reseal *.age files whose recipients changed")
    p.add_argument("--all", action="store_true", help="reseal every file, also current ones")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=_cmd_rekey)
    p = sub.add_parser("s", help="show who can unseal each *.age file")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=_cmd_status)
    args = parser.parse_args(argv)
    if _load_pyrage() is None:
        return 1
    return args.func(args, resolver, after_seal)


if __name__ == "__main__":
    sys.exit(main())
