#!/usr/bin/env python3

import argparse
import logging
import sys
import yaml
import os
import curses
from chardet.universaldetector import UniversalDetector
import glob

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
normal = ''
red = ''
yellow = ''
green = ''

if os.isatty(sys.stdout.fileno()):
    curses.setupterm()
    setafb = curses.tigetstr('setaf') or ''
    setaf = setafb.decode()
    normal = curses.tigetstr('sgr0').decode() or ''
    red = curses.tparm(setafb, curses.COLOR_RED).decode() or ''
    yellow = curses.tparm(setafb, curses.COLOR_YELLOW).decode() or ''
    green = curses.tparm(setafb, curses.COLOR_GREEN).decode() or ''


# Compute the plural of a word.
def maybe_plural(n, word):
    if n < 2:
        return word

    ll = word[len(word) - 1].lower()

    if ll == 'd' or ll == 's':
        return word
    else:
        return f'{word}s'


# A class to account for statistics
class Stats:
    counters = ['check', 'pass', 'warning', 'error']

    colors = {
        'pass': green,
        'warning': yellow,
        'error': red,
    }

    def __init__(self):
        self.data = {}

        for c in Stats.counters:
            self.data[c] = 0

    def _counter_str(self, x):
        n = self.data[x]
        color = Stats.colors[x] if n and x in Stats.colors else ''
        return f'{color}{n} {maybe_plural(n, x)}{normal}'

    def __str__(self):
        return ', '.join(
            map(lambda x: self._counter_str(x), Stats.counters))

    # Add the counters of a Stats objects to self.
    def add(self, x):
        for c in Stats.counters:
            self.data[c] += x.data[c]

    def _inc(self, x):
        self.data[x] += 1
        self.data['check'] += 1

    # Increment 'pass' counter.
    def inc_pass(self):
        self._inc('pass')

    # Increment 'warning' counter.
    def inc_warning(self):
        self._inc('warning')

    # Increment 'error' counter.
    def inc_error(self):
        self._inc('error')


# Load YAML configuration file.
# See the README.md for details on the file format.
def load_config(filename):
    logging.debug(f'Load {filename}')

    with open(filename, 'r') as yamlfile:
        conf = yaml.load(yamlfile, **yaml_load_args)

    assert('check-sr-results-configuration' in conf)
    return conf


# Detect file encoding
# We return the encoding or None
def detect_file_encoding(filename):
    logging.debug(f"Detect encoding of `{filename}'")

    detector = UniversalDetector()
    enc = None

    with open(filename, 'rb') as f:
        for i, line in enumerate(f):
            detector.feed(line)

            if detector.done:
                detector.close()
                enc = detector.result['encoding']
                break

            if i > 999:
                logging.debug('Giving up')
                break

    logging.debug(f"Encoding {enc}")
    return enc


# Check that a file contains what it must.
# must_contain is a list of strings to look for in the file, in order.
# We can deal with utf-16.
# We return a Stats object.
def check_file_contains(must_contain, filename):
    logging.debug(f"Check that file `{filename}' contains {must_contain}")
    assert(len(must_contain))

    enc = detect_file_encoding(filename)

    q = list(must_contain)
    pat = q.pop(0)
    logging.debug(f"Looking for `{pat}'")
    assert(isinstance(pat, str))
    stats = Stats()

    # Open the file with the proper encoding and look for patterns
    with open(filename, encoding=enc, errors='replace') as f:
        for i, line in enumerate(f):
            line = line.rstrip()

            if line.find(pat) >= 0:
                logging.debug(
                    f"`{pat}' {green}found{normal} at line {i + 1}: `{line}'")
                stats.inc_pass()

                if not len(q):
                    pat = None
                    break

                pat = q.pop(0)

    if pat is not None:
        logging.error(f"{red}Could not find{normal} `{pat}' in `{filename}'")
        stats.inc_error()

    return stats


# Warn if a file contains specific patterns.
# warn_if is a list of strings to look for in the file.
# Order is not taken into account.
# We can deal with utf-16.
# We return a Stats object.
# We report only the first match of each pattern.
def warn_if_contains(warn_if, filename):
    logging.debug(f"Warn if file `{filename}' contains {warn_if}")
    enc = detect_file_encoding(filename)
    stats = Stats()
    pats = set(warn_if)

    # Open the file with the proper encoding and look for patterns
    with open(filename, encoding=enc, errors='replace') as f:
        for i, line in enumerate(f):
            line = line.rstrip()

            if len(pats) == 0:
                break

            for p in list(pats):
                if line.find(p) >= 0:
                    logging.warning(
                        f"`{p}' {yellow}found{normal} in `{filename}'"
                        f" at line {i + 1}: `{line}'")
                    stats.inc_warning()
                    pats.remove(p)

    if len(warn_if) > 0 and len(warn_if) == len(pats):
        logging.debug(f"{green}No warning pattern{normal} in `{filename}'")
        stats.inc_pass()

    return stats


# Check a file
# We check if a file exists and is not empty.
# The following properties in the yaml configuration can relax the check:
# - optional
# - can-be-empty
# If the file has a 'must-contain' property, we look for all signatures in its
# contents in order.
# We return a Stats object.
def check_file(conffile, filename):
    logging.debug(f"Check `{filename}'")
    stats = Stats()

    if os.path.isfile(filename):
        logging.debug(f"`{filename}' {green}exists{normal}")
        stats.inc_pass()

        if os.path.getsize(filename) > 0:
            logging.debug(f"`{filename}' {green}not empty{normal}")
            stats.inc_pass()

            if 'must-contain' in conffile:
                stats.add(
                    check_file_contains(conffile['must-contain'], filename))

            if 'warn-if-contains' in conffile:
                stats.add(
                    warn_if_contains(conffile['warn-if-contains'], filename))

        elif 'can-be-empty' in conffile:
            logging.warning(f"`{filename}' {yellow}empty (allowed){normal}")
            stats.inc_warning()
        else:
            logging.error(f"`{filename}' {red}empty{normal}")
            stats.inc_error()
    elif 'optional' in conffile:
        logging.warning(f"`{filename}' {yellow}missing (optional){normal}")
        stats.inc_warning()
    else:
        logging.error(f"`{filename}' {red}missing{normal}")
        stats.inc_error()

    return stats


# Check a dir
# We check is a dir exists and is not empty.
# The following properties in the yaml configuration can relax the check:
# - optional
# - can-be-empty
# If the dir has a tree, we recurse with check_tree().
# We return a Stats object.
def check_dir(confdir, dirname):
    logging.debug(f"Check `{dirname}/'")
    stats = Stats()

    if os.path.isdir(dirname):
        logging.debug(f"`{dirname}/' {green}exists{normal}")
        stats.inc_pass()

        if len(os.listdir(dirname)) > 0:
            logging.debug(f"`{dirname}/' {green}not empty{normal}")
            stats.inc_pass()

            if 'tree' in confdir:
                stats.add(check_tree(confdir['tree'], dirname))
        elif 'can-be-empty' in confdir:
            logging.warning(f"`{dirname}/' {yellow}empty (allowed){normal}")
            stats.inc_warning()
        else:
            logging.error(f"`{dirname}/' {red}empty{normal}")
            stats.inc_error()
    elif 'optional' in confdir:
        logging.warning(f"`{dirname}/' {yellow}missing (optional){normal}")
        stats.inc_warning()
    else:
        logging.error(f"`{dirname}/' {red}missing{normal}")
        stats.inc_error()

    return stats


# Return True if a string is a glob pattern, False otherwise.
def is_glob(x):
    e = glob.escape(x)
    return x != e


# Recursively check a tree
# We return a Stats object.
# Files and directories names may be glob patterns. We need to handle the case
# of glob vs. non-glob explicitly, as a glob pattern may return an empty list.
def check_tree(conftree, dirname):
    logging.debug(f"Check `{dirname}/'")
    assert(isinstance(conftree, list))
    stats = Stats()

    for e in conftree:
        if 'file' in e:
            pathname = f"{dirname}/{e['file']}"
            check = check_file
        elif 'dir' in e:
            pathname = f"{dirname}/{e['dir']}"
            check = check_dir
        else:
            raise Exception

        if is_glob(pathname):
            t = list(glob.glob(pathname))
            logging.debug(f"{pathname} -> {t}")

            if len(t) == 0 and 'optional' not in e:
                logging.error(f"`{pathname}' {red}missing{normal}")
                stats.inc_error()
        else:
            t = [pathname]

        for x in t:
            stats.add(check(e, x))

    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Perform a number of verifications on a SystemReady'
                    ' results tree.',
        epilog='We expect the tree to be layout as described in the'
               ' SystemReady template'
               ' (https://gitlab.arm.com/systemready/systemready-template).')
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        '--dir', help='Specify directory to check', default='.')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    ln = logging.getLevelName(logging.WARNING)
    logging.addLevelName(logging.WARNING, f"{yellow}{ln}{normal}")
    ln = logging.getLevelName(logging.ERROR)
    logging.addLevelName(logging.ERROR, f"{red}{ln}{normal}")

    me = os.path.realpath(__file__)
    here = os.path.dirname(me)
    conf = load_config(f'{here}/check-sr-results.yaml')
    stats = check_tree(conf['tree'], args.dir)
    logging.info(stats)
