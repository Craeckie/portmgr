import os
import sys
# import docker
import dckrjsn
import argparse
import importlib

class MyParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write('Error: %s\n' % message)
        self.print_help()
        sys.exit(2)

conf_name = 'dckrcnf.json'
sub_name = 'dckrsub.json'
conf_scheme_name = 'dckrcnf.schema.json'
sub_scheme_name = 'dckrsub.schema.json'

src_path = os.path.dirname(os.path.abspath(__file__))
conf_scheme_path = os.path.join(src_path, sub_scheme_name)
sub_scheme_path = os.path.join(src_path, sub_scheme_name)

conf_scheme = dckrjsn.read_json(conf_scheme_path)
sub_scheme = dckrjsn.read_json(sub_scheme_path)

command_list = {}
action_list = []

def addCommand(cur_directory):
    p_cnf = os.path.join(cur_directory, conf_name)
    # cnf = dckrjsn.read_json(p_cnf, sch = conf_scheme)

    action_list.append({
        'directory': cur_directory
    })

def traverse(cur_directory):
    sub_path = os.path.join(cur_directory, sub_name)

    if os.path.exists(sub_path): # has sub folders
        sub_folders = dckrjsn.read_json(sub_path, sch = sub_scheme)
        for sub_folder in sub_folders:
            if 'folder' in sub:
                next_directory = os.path.join(cur_directory, sub['folder'])
                traverse(next_directory)
    else: # is a leaf
        addCommand(p_cwd)

def main():
    # global cli
    global base_directory

    # cli = docker.Client('unix://var/run/docker.sock')

    # Include external source files for commands
    # These fill the m_cmd list
    for file in os.listdir(os.path.join(src_path, 'commands')):
        ext_file = os.path.splitext(file)

        if ext_file[1] == '.py' and not ext_file[0] == '__init__':
            importlib.import_module('commands.' + ext_file[0])

    parser = MyParser()
    parser.add_argument('-D',
        dest='base_directory',
        action='store',
        default='',
        help='Set working directory')
    parser.add_argument('-R',
        dest='recursive',
        action='store_true',
        help='Use dckrsub.json files to recursively apply operations')

    for cmd in command_list.items():
        parser.add_argument('-' + cmd[0],
            dest='a_cmd',
            action='append_const',
            const=cmd[0],
            help=cmd[1]['hlp'])

    args = parser.parse_args()

    base_directory = os.path.join(os.getcwd(), args.base_directory)

    if args.recursive:
        traverse(base_directory)
    else:
        addCommand(base_directory)

    for cmd in args.a_cmd: # loop over all passed arguments (t, r, c, s)
        cur_cmd = command_list[cmd]
        cmd_function = cur_cmd['fnc']
        cmd_order = cur_cmd['ord'];

        if cmd_order == 'nrm':
            action_list_sorted = action_list
        elif cmd_order == 'rev':
            action_list_sorted = reversed(action_list)
        else:
            exit(1)

        for action in action_list_sorted:
            if cmd_function(action) != 0: # execute the function through reflection
                exit(1)

    exit(0)
