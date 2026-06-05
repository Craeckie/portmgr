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


sub_names = [x.strip() for x in re.split('[ ,;]+', os.environ.get('PORTMGR_SUB_NAME', 'dckrsub.yml'))]
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


def normalize_argv(argv, commands):
    """Convert bare command letters/strings to flag form so argparse can parse
    them (e.g. 'u' -> '-u', 'dul' -> '-dul', '-D /path m' -> '-D /path -m').

    Strings are only converted when every character is a registered command
    letter. The -D value is consumed verbatim first to avoid misidentifying it.
    `commands` is the command_list dict (membership-tested per character).
    """
    new_argv = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '-D':
            new_argv.append(arg)
            i += 1
            if i < len(argv):
                new_argv.append(argv[i])
                i += 1
        elif not arg.startswith('-') and arg and all(c in commands for c in arg):
            new_argv.append('-' + arg)
            i += 1
        else:
            new_argv.append(arg)
            i += 1
    return new_argv


def traverse(cur_directory):
    # print("Traversing in " + cur_directory)
    for sub_name in sub_names:
        sub_path = os.path.join(cur_directory, sub_name)
        compose_paths = [os.path.join(cur_directory, name) for name in compose_names]

        # print("Checking file at " + sub_path)
        if os.path.isfile(sub_path):  # has sub folders
            # print("Has sub folders!")
            # sub_folders = dckrjsn.read_json(sub_path, sch = sub_scheme)
            sub_folders = read_yaml(sub_path)
            for sub_folder in sub_folders:
                # print("Checking out " + sub_folder)
                next_directory = os.path.join(cur_directory, sub_folder)
                traverse(next_directory)
        elif any(os.path.isfile(path) for path in compose_paths):  # has a docker-compose file
            addCommand(cur_directory)


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
    parser.add_argument('-D',
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

    argv = normalize_argv(sys.argv[1:], command_list)

    args, extra = parser.parse_known_args(argv)

    if len(sys.argv) == 1 or not args.a_cmd:
        parser.print_help()
        sys.exit(1)

    command_extra.clear()
    command_extra.extend(extra)

    base_directory = os.path.join(os.getcwd(), args.base_directory)

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
