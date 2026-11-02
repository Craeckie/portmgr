"""Per-stack logs, a results file and a stop file for unattended runs.

All three are opt-in through the environment and change nothing when unset:

PORTMGR_LOG_DIR    each stack's output (portmgr's own and every subprocess's, fd 1
                   and 2) goes to <dir>/<stack, '/' -> '__'>.log; stdout keeps one
                   line per stack: `-> <stack> OK|FAILED|SKIPPED (3m12s)`.
PORTMGR_RESULTS    one JSON line per stack and command is appended to this file.
PORTMGR_STOP_FILE  once this file exists, the stacks not started yet are skipped.
"""
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone


def flush_output():
    """Flush Python's stdout/stderr so text printed so far lands before the
    output of a subprocess that writes to the same file descriptors."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (AttributeError, OSError, ValueError):
            pass


def line_buffer_stdout():
    """Make stdout line-buffered, also when it is a pipe or a file."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except (AttributeError, OSError, ValueError):
            pass


def log_name(relative):
    """File name of a stack's log: 'matrix/web' -> 'matrix__web.log'."""
    name = relative.replace(os.sep, '/').strip('/') or 'stack'
    return name.replace('/', '__') + '.log'


def format_duration(seconds):
    seconds = int(round(seconds))
    if seconds < 60:
        return f'{seconds}s'
    if seconds < 3600:
        return f'{seconds // 60}m{seconds % 60:02d}s'
    return f'{seconds // 3600}h{(seconds % 3600) // 60:02d}m'


_VAR = re.compile(r'\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)(?:(?P<op>:?-)(?P<default>[^}]*))?\}'
                  r'|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))')


def read_env_file(path):
    """KEY=VALUE pairs of a compose .env file; missing or unreadable gives {}."""
    values = {}
    try:
        with open(path) as stream:
            for line in stream:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                if key.startswith('export '):
                    key = key[len('export '):].strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                    value = value[1:-1]
                values[key] = value
    except OSError:
        pass
    return values


def expand_vars(value, env):
    """Expand ${VAR}, ${VAR:-default}, ${VAR-default} and $VAR the way compose
    does; a variable that is not set and has no default is left as written."""
    def repl(match):
        name = match.group('braced') or match.group('plain')
        op = match.group('op')
        current = env.get(name)
        if op == ':-' and not current:
            return match.group('default')
        if op == '-' and current is None:
            return match.group('default')
        return match.group(0) if current is None else current
    return _VAR.sub(repl, value)


def service_images(services, directory='.'):
    """The `image:` of each buildable service, variables expanded from the
    environment and the stack's .env (the shell wins, as in compose)."""
    env = read_env_file(os.path.join(directory, '.env'))
    env.update(os.environ)
    images = []
    for service in (services or {}).values():
        image = service.get('image') if isinstance(service, dict) else None
        if isinstance(image, str) and image:
            images.append(expand_vars(image, env))
    return images


class RunRecorder:
    def __init__(self, environ=None):
        environ = os.environ if environ is None else environ
        self.log_dir = environ.get('PORTMGR_LOG_DIR') or None
        self.results = environ.get('PORTMGR_RESULTS') or None
        self.stop_file = environ.get('PORTMGR_STOP_FILE') or None
        self.stopped = False
        self._written = set()

    def should_skip(self):
        """True once the stop file exists; stays true for the rest of the run."""
        if not self.stopped and self.stop_file and os.path.exists(self.stop_file):
            self.stopped = True
        return self.stopped

    @contextmanager
    def capture(self, relative):
        """Send fd 1 and 2 to the stack's log while the block runs; yields its
        path, or None when PORTMGR_LOG_DIR is not set."""
        if not self.log_dir:
            yield None
            return
        os.makedirs(self.log_dir, exist_ok=True)
        path = os.path.join(self.log_dir, log_name(relative))
        # A second command in the same run (`portmgr br`) appends to the same log.
        mode = 'ab' if path in self._written else 'wb'
        self._written.add(path)
        flush_output()
        saved = os.dup(1), os.dup(2)
        try:
            with open(path, mode) as log:
                os.dup2(log.fileno(), 1)
                os.dup2(log.fileno(), 2)
                try:
                    yield path
                finally:
                    flush_output()
                    os.dup2(saved[0], 1)
                    os.dup2(saved[1], 2)
        finally:
            os.close(saved[0])
            os.close(saved[1])

    def record(self, relative, command, rc, status, start, duration, log=None, images=None):
        if not self.results:
            return
        entry = {
            'stack': relative,
            'command': command,
            'rc': rc,
            'status': status,
            'start': datetime.fromtimestamp(start, timezone.utc).isoformat(timespec='seconds'),
            'duration_s': round(duration, 1),
            'log': log,
            'images': list(images or []),
        }
        directory = os.path.dirname(self.results)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.results, 'a') as stream:
            stream.write(json.dumps(entry) + '\n')

    def run_action(self, action, command, func):
        """Run one command on one stack; return its exit code (None if skipped)."""
        relative = action['relative']
        start = time.time()
        if self.should_skip():
            if self.log_dir:
                print(f'-> {relative} SKIPPED')
            else:
                print(f'-> {relative} SKIPPED (stop file)')
            self.record(relative, command, None, 'skipped', start, 0.0)
            return None

        action.pop('images', None)
        if not self.log_dir:
            print('-> ' + relative)
        with self.capture(relative) as log:
            if log:
                print('-> ' + relative)
            rc = _call(func, action)
        duration = time.time() - start
        status = 'ok' if rc == 0 else 'failed'
        if self.log_dir:
            print(f'-> {relative} {status.upper()} ({format_duration(duration)})')
        self.record(relative, command, rc, status, start, duration, log, action.get('images'))
        return rc


def _call(func, action):
    try:
        rc = func(action)
    except Exception as exc:
        print('Error: ' + str(exc))
        rc = 1
    flush_output()
    return rc
