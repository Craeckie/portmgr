import os
import sys
import docker
import dckrjsn
import argparse
import importlib


conf_name = 'dckrcnf.json'
sub_name = 'dckrsub.json'
conf_scheme_name = 'dckrcnf.schema.json'
sub_scheme_name = 'dckrsub.schema.json'

src_path = os.path.dirname(os.path.abspath(__file__))
conf_scheme_path = os.path.join(src_path, sub_scheme_name)
sub_scheme_path = os.path.join(src_path, sub_scheme_name)

conf_scheme = dckrjsn.read_json(conf_scheme_path)
sub_scheme = dckrjsn.read_json(sub_scheme_path)

command_list = []

def addCommand(p_cwd):
    p_cnf = os.path.join(p_cwd, conf_name)
    cnf = dckrjsn.read_json(p_cnf, sch = conf_scheme)

    command_list.append({
        'p_cwd': p_cwd,
        'cnf': cnf
    })

def traverse(p_cwd):
    p_sub = os.path.join(p_cwd, sub_name)
    a_sub = dckrjsn.read_json(p_sub, sch = sub_scheme)

    for sub in a_sub:
        if 'folder' in sub:
            p_cwd_nxt = os.path.join(p_cwd, sub['folder'])
            traverse(p_cwd_nxt)
        else:
            addCommand(p_cwd)

def main():
    global cli
    global base_directory

    cli = docker.Client('unix://var/run/docker.sock')

    # Include external source files for commands
    # These fill the m_cmd list
    m_cmd = {}
    for file in os.listdir(os.path.join(src_path, 'commands')):
        ext_file = os.path.splitext(file)

        if ext_file[1] == '.py' and not ext_file[0] == '__init__':
            importlib.import_module('commands.' + ext_file[0])

    parser = argparse.ArgumentParser()
    parser.add_argument('-D',
        dest='base_directory',
        action='store',
        default='',
        help='Set working directory')
    parser.add_argument('-R',
        dest='recursive',
        action='store_true',
        help='Use dckrsub.json files to recursively apply operations')

    for cmd in m_cmd.items():
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

    for cmd in args.a_cmd:
        cur_cmd = m_cmd[cmd];
        cmd_order = cur_cmd['ord'];
        if cmd_order == 'nrm':
            command_list_sorted = command_list
        elif cmd_order == 'rev':
            command_list_sorted = reversed(command_list)
        else:
            exit(1)

        for command in command_list_sorted:
            cmd_function = cur_cmd['fnc']
            if cmd_function(command) != 0: # execute the function through reflection
                exit(1)

    exit(0)
