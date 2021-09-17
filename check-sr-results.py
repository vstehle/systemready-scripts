#!/usr/bin/env python3

import argparse
import logging
import sys
import yaml
import os
import curses

try:
    from packaging import version
except ImportError:
    print('No packaging. You should install python3-packaging...')

# Not all yaml versions have a Loader argument.
if 'packaging.version' in sys.modules and \
   version.parse(yaml.__version__) >= version.parse('5.1'):
    yaml_load_args = {'Loader': yaml.FullLoader}
else:
    yaml_load_args = {}

# Colors
curses.setupterm()
setafb = curses.tigetstr('setaf') or ''
setaf = setafb.decode()
normal = curses.tigetstr('sgr0').decode() or ''
red = curses.tparm(setafb, curses.COLOR_RED).decode() or ''
yellow = curses.tparm(setafb, curses.COLOR_YELLOW).decode() or ''
green = curses.tparm(setafb, curses.COLOR_GREEN).decode() or ''


# Load YAML configuration file.
# See the README.md for details on the file format.
def load_config(filename):
    logging.debug(f'Load {filename}')

    with open(filename, 'r') as yamlfile:
        conf = yaml.load(yamlfile, **yaml_load_args)

    assert('check-sr-results-configuration' in conf)
    return conf


# Check a file
# We check is a file exists and is not empty.
# The following properties in the yaml configuration can relax the check:
# - optional
# - can-be-empty
def check_file(conffile, dirname):
    filename = f"{dirname}/{conffile['file']}"
    logging.debug(f"Check `{filename}'")

    if os.path.isfile(filename):
        logging.debug(f"`{filename}' {green}exists{normal}")

        if os.path.getsize(filename) > 0:
            logging.debug(f"`{filename}' {green}not empty{normal}")
        elif 'can-be-empty' in conffile:
            logging.error(f"`{filename}' {yellow}empty (allowed){normal}")
        else:
            logging.error(f"`{filename}' {red}empty{normal}")
    elif 'optional' in conffile:
        logging.error(f"`{filename}' {yellow}missing (optional){normal}")
    else:
        logging.error(f"`{filename}' {red}missing{normal}")


# Check a dir
# We check is a dir exists and is not empty.
# The following properties in the yaml configuration can relax the check:
# - optional
# - can-be-empty
def check_dir(confdir, dirname):
    subdir = f"{dirname}/{confdir['dir']}"
    logging.debug(f"Check `{subdir}/'")

    if os.path.isdir(subdir):
        logging.debug(f"`{subdir}/' {green}exists{normal}")

        if len(os.listdir(subdir)) > 0:
            logging.debug(f"`{subdir}/' {green}not empty{normal}")

            if 'tree' in confdir:
                check_tree(confdir['tree'], subdir)
        elif 'can-be-empty' in confdir:
            logging.error(f"`{subdir}/' {yellow}empty (allowed){normal}")
        else:
            logging.error(f"`{subdir}/' {red}empty{normal}")
    elif 'optional' in confdir:
        logging.error(f"`{subdir}/' {yellow}missing (optional){normal}")
    else:
        logging.error(f"`{subdir}/' {red}missing{normal}")


# Recursively check a tree
def check_tree(conftree, dirname):
    logging.debug(f"Check `{dirname}/'")
    assert(isinstance(conftree, list))

    for e in conftree:
        if 'file' in e:
            check_file(e, dirname)
        elif 'dir' in e:
            check_dir(e, dirname)
        else:
            raise Exception


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Perform a number of verifications on a SystemReady'
                    ' results tree.',
        epilog='We expect the tree to be layout as described in the'
               ' SystemReady template'
               ' (https://gitlab.arm.com/systemready/systemready-template).')
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    me = os.path.realpath(__file__)
    here = os.path.dirname(me)
    conf = load_config(f'{here}/check-sr-results.yaml')
    check_tree(conf['tree'], '.')
