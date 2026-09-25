"""Move literal `environment:` values from a compose file into `.env` (command M).

The compose file is edited as text: yaml.compose() gives the exact span of each
value, and only those spans are replaced with a `${NAME}` reference, so comments,
ordering and formatting survive. Anything whose meaning could shift on the way
(interpolation, YAML re-typing, anchors, multi-line values, characters `.env`
cannot hold) is skipped with a reason rather than guessed at.
"""
import json
import re
from dataclasses import dataclass

import yaml

from portmgr.secrets import SECRET_KEY_PATTERN

# Compose parses YAML 1.2 (go-yaml v3) and hands non-string scalars to the
# container re-rendered: `True` -> "true", `0o17` -> "15", `1.50` -> "1.5".
# Only plain scalars that come back unchanged are safe to move verbatim.
_NULLS = {'', '~', 'null', 'Null', 'NULL'}
_BOOLS = {'true', 'True', 'TRUE', 'false', 'False', 'FALSE'}
_INT_RE = re.compile(r'[-+]?(0b[01_]+|0o[0-7_]+|0x[0-9a-fA-F_]+|[0-9][0-9_]*)')
_FLOAT_RE = re.compile(
    r'[-+]?(\.[0-9_]+|[0-9][0-9_]*(\.[0-9_]*)?)([eE][-+]?[0-9]+)?'
    r'|[-+]?\.(inf|Inf|INF)|\.(nan|NaN|NAN)'
)
_CANONICAL_INT_RE = re.compile(r'0|-?[1-9][0-9]{0,17}')
_CANONICAL_FLOAT_RE = re.compile(r'-?(0|[1-9][0-9]*)\.([0-9]*[1-9])')

_PURE_REF_RE = re.compile(r'\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*')
_REF_NAME_RE = re.compile(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)')
_DOTENV_PLAIN_RE = re.compile(r'[A-Za-z0-9_./:@+-]+')

# Always present in a shell, and a shell variable beats .env in compose.
DEFAULT_RESERVED = {'USER', 'HOME', 'PATH', 'PWD', 'SHELL', 'HOSTNAME', 'LANG', 'TERM', 'UID', 'GID'}


@dataclass
class EnvEntry:
    services: list
    key: str
    value: str | None  # the literal the container sees; None when skipped
    start: int         # span in the compose text replaced by the reference
    end: int
    form: str          # 'dict' or 'list'
    skip: str | None = None
    quiet: bool = False  # skipped for an obvious reason, not worth printing

    @property
    def secret(self):
        return bool(SECRET_KEY_PATTERN.search(self.key))


@dataclass
class Move:
    entry: EnvEntry
    name: str
    append: bool  # False when .env already holds this name with this value


def _canonical_float(raw):
    # Go's %v switches to exponent notation outside 1e-4 <= |x| < 1e6.
    m = _CANONICAL_FLOAT_RE.fullmatch(raw)
    if not m:
        return False
    int_part, frac = m.groups()
    if int_part != '0':
        exp, digits = len(int_part) - 1, len(int_part) + len(frac)
    else:
        lead = len(frac) - len(frac.lstrip('0'))
        exp, digits = -(lead + 1), len(frac) - lead
    return -4 <= exp <= 5 and digits <= 15


def _plain_scalar_problem(raw):
    """Why compose would not pass this plain scalar through verbatim, or None."""
    if raw in _BOOLS:
        kind, ok = 'boolean', raw in ('true', 'false')
    elif _INT_RE.fullmatch(raw):
        kind, ok = 'number', bool(_CANONICAL_INT_RE.fullmatch(raw))
    elif _FLOAT_RE.fullmatch(raw):
        kind, ok = 'number', _canonical_float(raw)
    else:
        return None
    if ok:
        return None
    return f"YAML reads {raw} as a {kind} compose may rewrite; quote it to move it"


def _literal(value):
    """(literal, skip_reason, quiet) for a compose value string."""
    if value == '':
        return None, 'empty value', True
    if '$' in value.replace('$$', ''):
        if _PURE_REF_RE.fullmatch(value):
            return None, 'already a variable reference', True
        return None, 'contains a variable reference', False
    literal = value.replace('$$', '$')
    if any(ord(c) < 32 or ord(c) == 127 for c in literal):
        return None, 'contains a newline or control character', False
    if literal.endswith('\\') or "\\'" in literal:
        return None, "backslash before a quote or at the end can't be written to .env", False
    return literal, None, False


def _span_problem(text, node):
    if text[node.start_mark.index:node.start_mark.index + 1] in ('&', '*', '!'):
        return 'uses a YAML anchor, alias or tag'
    if node.start_mark.line != node.end_mark.line:
        return 'multi-line value'
    return None


def _mapping_get(node, key):
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            if isinstance(k, yaml.ScalarNode) and k.value == key:
                return v
    return None


def collect_env(text):
    """Every `services.*.environment` entry, movable or not (see EnvEntry.skip).

    Raises yaml.YAMLError on an unparsable file.
    """
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    services = _mapping_get(root, 'services')
    if not isinstance(services, yaml.MappingNode):
        return []

    entries = {}  # dedupe nodes shared by several services via an alias

    def add(ident, svc, make):
        if ident in entries:
            entries[ident].services.append(svc)
        else:
            entries[ident] = make()

    for svc_key, svc_node in services.value:
        svc = svc_key.value
        env = _mapping_get(svc_node, 'environment')
        if isinstance(env, yaml.MappingNode):
            for k, v in env.value:
                if not isinstance(k, yaml.ScalarNode) or k.value == '<<':
                    continue
                add((id(k), id(v)), svc, lambda k=k, v=v: _dict_entry(text, svc, k.value, v))
        elif isinstance(env, yaml.SequenceNode):
            for index, item in enumerate(env.value):
                add((id(env), index), svc, lambda item=item: _list_entry(text, svc, item))
    return list(entries.values())


def _dict_entry(text, svc, key, node):
    entry = EnvEntry([svc], key, None, node.start_mark.index, node.end_mark.index, 'dict')
    if not isinstance(node, yaml.ScalarNode):
        entry.skip = 'not a single value'
        return entry
    entry.skip = _span_problem(text, node)
    if entry.skip:
        return entry
    if node.style is None:
        if node.value in _NULLS:
            entry.skip, entry.quiet = 'no value (passed through from the host)', True
            return entry
        entry.skip = _plain_scalar_problem(node.value)
        if entry.skip:
            return entry
    entry.value, entry.skip, entry.quiet = _literal(node.value)
    return entry


def _list_entry(text, svc, node):
    if not isinstance(node, yaml.ScalarNode):
        return EnvEntry([svc], '?', None, node.start_mark.index, node.end_mark.index, 'list',
                        skip='not a single value')
    key, eq, value = node.value.partition('=')
    entry = EnvEntry([svc], key.strip(), None, node.start_mark.index, node.end_mark.index, 'list')
    if not eq:
        entry.skip, entry.quiet = 'no value (passed through from the host)', True
        return entry
    if not entry.key:
        entry.skip = 'no variable name'
        return entry
    entry.skip = _span_problem(text, node)
    if entry.skip:
        return entry
    entry.value, entry.skip, entry.quiet = _literal(value)
    return entry


def dotenv_format(value):
    """A .env line value compose reads back as exactly `value`.

    Single quotes are literal in compose's dotenv (no interpolation, `\\'` is
    the only escape), which is why collect_env skips `\\'` and a trailing `\\`.
    """
    if _DOTENV_PLAIN_RE.fullmatch(value):
        return value
    return "'" + value.replace("'", "\\'") + "'"


def parse_dotenv(text):
    """{name: literal value}; the value is None where this simple reader is unsure."""
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].lstrip()
        name, eq, raw = line.partition('=')
        if not eq:
            continue
        result[name.strip()] = _parse_dotenv_value(raw.strip())
    return result


def _parse_dotenv_value(raw):
    if raw.startswith("'"):
        out, i = [], 1
        while i < len(raw):
            if raw.startswith("\\'", i):
                out.append("'")
                i += 2
            elif raw[i] == "'":
                rest = raw[i + 1:].strip()
                return ''.join(out) if not rest or rest.startswith('#') else None
            else:
                out.append(raw[i])
                i += 1
        return None
    if raw.startswith('"'):
        end = raw.find('"', 1)
        content = raw[1:end]
        if end < 0 or '\\' in content or '$' in content:
            return None
        rest = raw[end + 1:].strip()
        return content if not rest or rest.startswith('#') else None
    value = re.split(r'\s#', raw, maxsplit=1)[0].strip()
    return None if '$' in value else value


def _var_name(text):
    name = re.sub(r'[^A-Za-z0-9_]', '_', text)
    return '_' + name if name[:1].isdigit() else name


def plan_moves(selected, dotenv, compose_text, reserved):
    """Pick a .env name for each selected entry.

    The entry's own key is used where it is free. It is not free when .env
    or an earlier pick holds it with another value, when the shell would
    override it (`reserved`), or when the compose file already references it.
    Then `<SERVICE>_<KEY>` is used, with a counter if even that is taken.
    """
    referenced = set(_REF_NAME_RE.findall(compose_text.replace('$$', '')))
    assigned = {}

    def usable(name, value):
        if name in reserved:
            return False
        if name in assigned:
            return assigned[name] == value
        if name in dotenv:
            return dotenv[name] == value
        return name not in referenced

    moves = []
    for entry in selected:
        base = _var_name(entry.key)
        prefixed = f"{_var_name(entry.services[0]).upper()}_{base}"
        candidates = [base, prefixed]
        n = 2
        while not any(usable(c, entry.value) for c in candidates):
            candidates.append(f"{prefixed}_{n}")
            n += 1
        name = next(c for c in candidates if usable(c, entry.value))
        append = name not in assigned and name not in dotenv
        assigned[name] = entry.value
        moves.append(Move(entry, name, append))
    return moves


def apply_compose(text, moves):
    """The compose text with each moved value replaced by its reference."""
    for move in sorted(moves, key=lambda m: m.entry.start, reverse=True):
        ref = f"${{{move.name}}}"
        if move.entry.form == 'list':
            ref = f"{move.entry.key}={ref}"
        # Double-quoted so it stays valid in flow style ({...}) too; YAML
        # double quotes are a superset of JSON strings.
        text = text[:move.entry.start] + json.dumps(ref) + text[move.entry.end:]
    return text


def dotenv_append_text(existing, pairs):
    """`existing` .env text with `NAME=value` lines appended for each pair."""
    if existing and not existing.endswith('\n'):
        existing += '\n'
    return existing + ''.join(f"{name}={dotenv_format(value)}\n" for name, value in pairs)


def parse_selection(answer, count, default):
    """0-based indexes from '1,3-5' / 'a' (all) / 'n' (none) / '' (default)."""
    answer = answer.strip().lower()
    if not answer:
        return set(default)
    if answer == 'a':
        return set(range(count))
    if answer == 'n':
        return set()
    chosen = set()
    for part in re.split(r'[\s,]+', answer):
        if not part:
            continue
        first, dash, last = part.partition('-')
        if not first.isdigit() or (dash and not last.isdigit()):
            raise ValueError(f"not a number or range: {part}")
        lo, hi = int(first), int(last) if dash else int(first)
        if lo > hi or lo < 1 or hi > count:
            raise ValueError(f"out of range 1-{count}: {part}")
        chosen.update(range(lo - 1, hi))
    return chosen
