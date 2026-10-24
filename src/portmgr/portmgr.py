#!/usr/bin/python3
import os
import sys
import argparse
import importlib
import re

import yaml


class MyParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write('Error: %s\n' % message)
        self.print_help()
        sys.exit(2)


default_sub_name = 'dckrsub.yml'


def parse_sub_names(value):
    # dckrsub.yml is always followed, after the names from PORTMGR_SUB_NAME
    names = [x for x in re.split('[ ,;]+', value or '') if x]
    if default_sub_name not in names:
        names.append(default_sub_name)
    return names


sub_names = parse_sub_names(os.environ.get('PORTMGR_SUB_NAME'))
compose_names = [x.strip() for x in
                 os.environ.get('PORTMGR_COMPOSE_NAME', 'docker-compose.yml, docker-compose.yaml').split(',')]

# sub_scheme_name = 'dckrsub.schema.yml'

src_path = os.path.dirname(os.path.abspath(__file__))


# conf_scheme_path = os.path.join(src_path, sub_scheme_name)
# sub_scheme_path = os.path.join(src_path, sub_scheme_name)

# conf_scheme = dckrjsn.read_json(conf_scheme_path)
# sub_scheme = dckrjsn.read_json(sub_scheme_path)

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


command_list = {}
action_list = []
command_extra = []


def make_action(cur_directory):
    relative_dir = os.path.relpath(cur_directory, base_directory)
    if relative_dir == '.':
        relative_dir = os.path.basename(os.path.normpath(cur_directory))
    return {
        'directory': cur_directory,
        'relative': relative_dir
    }


def addCommand(cur_directory):
    if not any(action['directory'] == cur_directory for action in action_list):
        action_list.append(make_action(cur_directory))


def read_yaml(path):
    with open(path, 'r') as stream:
        try:
            return yaml.load(stream, Loader=yaml.SafeLoader)
        except yaml.YAMLError as exc:
            print(exc)


class ArgvError(Exception):
    """A command line that doesn't follow the grammar of split_argv()."""


class HelpRequested(Exception):
    """-h/--help came before the arguments."""


COMBINE_HINT = "combine commands as 'pul', '-p -u -l' or 'pu -l'"


def _letters(token, letters, commands):
    for c in letters:
        if c not in commands:
            raise ArgvError(f"unknown command '{c}' in '{token}'")
    return list(letters)


def split_argv(argv, commands):
    """Split a command line into (base_dir, command letters, arguments), the
    way tar and POSIX getopt read theirs:

      portmgr [-B DIR] [WORD] [-GROUP ...] [ARGS...]

    WORD is a bare word of command letters, recognised only as the first
    token (-B DIR doesn't count). Each -GROUP is a dash group of command
    letters. Everything from the first other token on is an argument and is
    never read as a command, even if it starts with '-'; '--' starts the
    arguments explicitly. -B DIR is accepted anywhere.

    Arguments are only accepted when a given command declares 'args': True
    (any) or a tuple of the words it accepts. Raises ArgvError on anything
    else, HelpRequested on -h/--help before the arguments.
    `commands` is the command_list dict.
    """
    base_dir = ''
    letters = []
    args = []
    first = True
    in_args = False
    i = 0
    while i < len(argv):
        tok = argv[i]
        i += 1
        if tok == '-B':
            if i >= len(argv):
                raise ArgvError('-B needs a directory')
            base_dir = argv[i]
            i += 1
            continue
        elif tok.startswith('-B') and not in_args:
            base_dir = tok[2:]
            continue
        elif in_args:
            args.append(tok)
        elif tok in ('-h', '--help'):
            raise HelpRequested()
        elif tok == '--':
            in_args = True
        elif first and tok and not tok.startswith('-'):
            letters += _letters(tok, tok, commands)
        elif len(tok) > 1 and tok.startswith('-') and not tok.startswith('--'):
            letters += _letters(tok, tok[1:], commands)
        else:
            in_args = True
            args.append(tok)
        first = False

    if args:
        takers = [c for c in letters if commands[c].get('args')]
        if not takers:
            raise ArgvError(f"unexpected argument '{args[0]}': {COMBINE_HINT}")
        for c in takers:
            allowed = commands[c]['args']
            if allowed is True:
                continue
            for arg in args:
                if arg not in allowed:
                    words = ', '.join(f"'{a}'" for a in allowed)
                    raise ArgvError(f"{c} takes only {words}, not '{arg}'")
    return base_dir, letters, args


def walk(cur_directory, names=None, _seen=None):
    """Yield ('dir', path) for every directory the sub files reach and
    ('stack', path) where traverse() adds a target, in traversal order.
    `names` defaults to sub_names; no global state is touched."""
    names = sub_names if names is None else names
    seen = set() if _seen is None else _seen
    key = os.path.normpath(cur_directory)
    if key in seen or not os.path.isdir(cur_directory):
        return
    seen.add(key)
    yield 'dir', cur_directory
    for sub_name in names:
        sub_path = os.path.join(cur_directory, sub_name)
        compose_paths = [os.path.join(cur_directory, name) for name in compose_names]

        if os.path.isfile(sub_path):  # has sub folders
            for sub_folder in read_yaml(sub_path) or []:
                yield from walk(os.path.join(cur_directory, sub_folder), names, seen)
        elif any(os.path.isfile(path) for path in compose_paths):  # has a docker-compose file
            yield 'stack', cur_directory


def traverse(cur_directory):
    for kind, directory in walk(cur_directory):
        if kind == 'stack':
            addCommand(directory)


def main():
    # global cli
    global base_directory

    # cli = docker.Client('unix://var/run/docker.sock')

    # Include external source files for commands
    # These fill the m_cmd list
    for file in os.listdir(os.path.join(src_path, 'commands')):
        ext_file = os.path.splitext(file)

        if ext_file[1] == '.py' and not ext_file[0] == '__init__':
            importlib.import_module('portmgr.commands.' + ext_file[0])

    parser = MyParser()
    parser.add_argument('-B',
                        dest='base_directory',
                        action='store',
                        default='',
                        help='Set working directory')
    # parser.add_argument('-R',
    #    dest='recursive',
    #    action='store_true',
    #    help='Use dckrsub.json files to recursively apply operations')

    for cmd in command_list.items():
        parser.add_argument('-' + cmd[0],
                            dest='a_cmd',
                            action='append_const',
                            const=cmd[0],
                            help=cmd[1]['hlp'])

    try:
        base_dir, letters, extra = split_argv(sys.argv[1:], command_list)
    except HelpRequested:
        parser.parse_args(['-h'])
    except ArgvError as exc:
        sys.stderr.write(f'portmgr: {exc}\n')
        sys.exit(2)

    # argparse only sees the command letters; it still builds -h and the help text.
    args = parser.parse_args(['-' + c for c in letters])

    if not args.a_cmd:
        parser.print_help()
        sys.exit(1)

    command_extra.clear()
    command_extra.extend(extra)

    base_directory = os.path.join(os.getcwd(), base_dir)

    # if args.recursive:
    traverse(base_directory)
    # else:
    #    addCommand(base_directory)

    for cmd in args.a_cmd:  # loop over all passed arguments (t, r, u)
        cur_cmd = command_list[cmd]
        cmd_function = cur_cmd['fnc']
        cmd_order = cur_cmd['ord']

        #        if last_cmd == 'r' and cur_cmd == 'u':
        #          print("Waiting 3 seconds.. ")
        #          sleep(3)

        # Some commands (seal/unseal) act on files, not compose stacks, so they
        # should still run in a directory that has no docker-compose.yml.
        actions = action_list
        if not actions and cur_cmd.get('standalone'):
            actions = [make_action(base_directory)]

        if cmd_order == 'nrm':
            action_list_sorted = actions
        elif cmd_order == 'rev':
            action_list_sorted = list(reversed(actions))
        else:
            exit(1)

        failed_list = []

        for action in action_list_sorted:
            origWD = os.getcwd()
            newWD = action['directory']
            os.chdir(newWD)
            print('-> ' + action["relative"])
            try:
                rc = cmd_function(action)
            except Exception as exc:
                print('Error: ' + str(exc))
                rc = 1
            if rc != 0:
                failed_list.append(action)
            os.chdir(origWD)
        if failed_list:
            print('Failed containers:')
            for action in failed_list:
                print('- ' + action['relative'])
            print("")

        fin = cur_cmd.get('fin')
        if fin:
            fin()

    exit(0)


if __name__ == '__main__':
    main()
