#!/usr/bin/env python3

import argparse
import logging
import sys
import yaml
import os
import curses
from chardet.universaldetector import UniversalDetector
import glob
import re
import subprocess

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
    try:
        curses.setupterm()
        setafb = curses.tigetstr('setaf') or bytes()
        setaf = setafb.decode()
        normal = curses.tigetstr('sgr0').decode() or ''
        red = curses.tparm(setafb, curses.COLOR_RED).decode() or ''
        yellow = curses.tparm(setafb, curses.COLOR_YELLOW).decode() or ''
        green = curses.tparm(setafb, curses.COLOR_GREEN).decode() or ''
    except Exception:
        pass

# Maximum number of lines to examine for file encoding detection.
# This will be set by the command line argument parser.
detect_file_encoding_limit = None


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

    if conf is None:
        conf = {
            'check-sr-results-configuration': None,
            'tree': []
        }

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

            if i > detect_file_encoding_limit:
                logging.debug('Giving up')
                break

    logging.debug(f"Encoding {enc}")
    return enc


# Cleanup a line
# - Right-strip the line
# - Remove the most annoying escape sequences
# Returns the cleaned-up line.
def cleanup_line(line):
    line = line.rstrip()
    line = re.sub(r'\x1B\[K', '', line)
    line = re.sub(r'\x1B\(B', '', line)
    line = re.sub(r'\x1B\[[\x30-\x3F]*[\x20-\x2F]*[\x40-\x7E]', '', line)

    while re.search(r'\x08', line):
        line = re.sub(r'.?\x08', '', line)

    return line


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
            line = cleanup_line(line)

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


# Warn or issue an error if a file contains specific patterns.
# strings is a list of strings to look for in the file.
# Order is not taken into account.
# We can deal with utf-16.
# We return a Stats object.
# We report only the first match of each pattern.
# When a match is found, if error_not_warn is True we issue an error, otherwise
# we issue a warning.
def if_contains(strings, filename, error_not_warn):
    action = 'Error' if error_not_warn else 'Warn'
    logging.debug(f"{action} if file `{filename}' contains {strings}")
    enc = detect_file_encoding(filename)
    stats = Stats()
    pats = set(strings)

    # Open the file with the proper encoding and look for patterns
    with open(filename, encoding=enc, errors='replace') as f:
        for i, line in enumerate(f):
            line = cleanup_line(line)

            if len(pats) == 0:
                break

            for p in list(pats):
                if p in line:
                    if error_not_warn:
                        logging.error(
                            f"`{p}' {red}found{normal} in `{filename}' "
                            f"at line {i + 1}: `{line}'")
                        stats.inc_error()
                    else:
                        logging.warning(
                            f"`{p}' {yellow}found{normal} in `{filename}' "
                            f"at line {i + 1}: `{line}'")
                        stats.inc_warning()

                    pats.remove(p)

    if len(strings) > 0 and len(strings) == len(pats):
        logging.debug(f"{green}No pattern{normal} in `{filename}'")
        stats.inc_pass()

    return stats


# Warn if a file contains specific patterns.
def warn_if_contains(strings, filename):
    return if_contains(strings, filename, False)


# Issue an error if a file contains specific patterns.
def error_if_contains(strings, filename):
    return if_contains(strings, filename, True)


# subprocess.run() wrapper
def run(*args):
    logging.debug(f"Running {args}")
    cp = subprocess.run(*args, shell=True, capture_output=True)
    logging.debug(cp)
    return cp


# If a file is an archive we know of, check its integrity.
# We know about tar(-gz) for now.
# TODO! More archives types.
# We return a Stats object.
def maybe_check_archive(filename):
    stats = Stats()

    if re.match(r'.*\.(tar|tar\.gz|tgz)$', filename):
        logging.debug(f"Checking archive `{filename}'")
        cp = run(f"tar tf {filename} >/dev/null")

        if cp.returncode:
            logging.error(f"{red}Bad archive{normal} `{filename}'")
            stats.inc_error()
        else:
            stats.inc_pass()

    return stats


# Check a file
# We check if a file exists and is not empty.
# The following properties in the yaml configuration can relax the check:
# - optional
# - can-be-empty
# If the file has a 'must-contain' property, we look for all signatures in its
# contents in order.
# We perform some more checks on archives.
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

            if 'error-if-contains' in conffile:
                stats.add(
                    error_if_contains(conffile['error-if-contains'], filename))

            # Check archives integrity.
            stats.add(maybe_check_archive(filename))

        elif 'can-be-empty' in conffile:
            logging.debug(f"`{filename}' {yellow}empty (allowed){normal}")
        else:
            logging.error(f"`{filename}' {red}empty{normal}")
            stats.inc_error()
    elif 'optional' in conffile:
        logging.debug(f"`{filename}' {yellow}missing (optional){normal}")
    else:
        logging.error(f"`{filename}' {red}missing{normal}")
        stats.inc_error()

    return stats


# Check a dir
# We check if a dir exists and is not empty (min-entries can override the
# later).
# The following properties in the yaml configuration can modify the check:
# - optional
# - min-entries
# - max-entries
# If the dir has a tree, we recurse with check_tree().
# We return a Stats object.
def check_dir(confdir, dirname):
    logging.debug(f"Check `{dirname}/'")
    stats = Stats()

    if os.path.isdir(dirname):
        logging.debug(f"`{dirname}/' {green}exists{normal}")
        stats.inc_pass()
        ent = len(os.listdir(dirname))
        logging.debug(f"`{dirname}/' has {ent} entrie(s)")
        min_ent = confdir['min-entries'] if 'min-entries' in confdir else 1

        if ent >= min_ent:
            logging.debug(
                f"`{dirname}/' {green}has enough entrie(s){normal}: "
                f"{ent} >= {min_ent}")
            stats.inc_pass()
        else:
            logging.error(
                f"`{dirname}/' {red}has too few entrie(s){normal}: "
                f"{ent} < {min_ent}")
            stats.inc_error()

        if 'max-entries' in confdir:
            max_ent = confdir['max-entries']

            if ent <= max_ent:
                logging.debug(
                    f"`{dirname}/' {green}does not have too many "
                    f"entrie(s){normal}: {ent} <= {max_ent}")
                stats.inc_pass()
            else:
                logging.error(
                    f"`{dirname}/' {red}has too many entrie(s){normal}: "
                    f"{ent} > {max_ent}")
                stats.inc_error()

        if ent and 'tree' in confdir:
            stats.add(check_tree(confdir['tree'], dirname))

    elif 'optional' in confdir:
        logging.debug(f"`{dirname}/' {yellow}missing (optional){normal}")
    else:
        logging.error(f"`{dirname}/' {red}missing{normal}")
        stats.inc_error()

    return stats


# Return True if a string is a glob pattern, False otherwise.
def is_glob(x):
    e = glob.escape(x)
    return x != e


# Try to identify the results.
# We call the external script `identify.py'.
# Return the list of identified files and the SystemReady version
# or [], None in case of error.
def run_identify(dirname, identify):
    logging.debug(f"Identify {dirname}")

    cp = run(f"{identify} --dir {dirname} --known-files")

    if cp.returncode:
        logging.error(f"{red}Bad identify{normal} `{identify}'")
        sys.exit(1)

    o = cp.stdout.decode().splitlines()
    logging.debug(o)

    if o is not None and len(o) and 'Unknown' not in o[-1]:
        files = o[0:-1]

        for f in files:
            logging.debug(f"""{green}Identified{normal} {f}.""")

        ver = o[-1]
        logging.info(f"""{green}Identified{normal} as {ver}.""")
        return files, ver

    logging.warning(f"{yellow}Could not identify...{normal}")
    return [], None


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


# Check that we have all we need.
def check_prerequisites():
    logging.debug('Checking prerequisites')

    # Check that we have tar.
    cp = run('tar --version')

    if cp.returncode:
        logging.error(f"{red}tar not found{normal}")
        sys.exit(1)


# Overlay the src file over the dst file, in-place.
def overlay_file(src, dst):
    logging.debug(f"Overlay file {src['file']}")

    for k, v in src.items():
        logging.debug(f"Overlay {k}")
        dst[k] = v


# Overlay the src dir over the dst dir, in-place.
def overlay_dir(src, dst):
    logging.debug(f"Overlay dir {src['dir']}")

    for k, v in src.items():
        logging.debug(f"Overlay {k}")

        # We have a special case when "merging" tree.
        if k == 'tree' and 'tree' in dst:
            overlay_tree(src['tree'], dst['tree'])
            continue

        dst[k] = v


# Overlay the src tree over the dst tree, in-place.
def overlay_tree(src, dst):
    # Prepare two LUTs.
    files = {}
    dirs = {}

    for x in dst:
        if 'file' in x:
            files[x['file']] = x
        elif 'dir' in x:
            dirs[x['dir']] = x
        else:
            raise

    # Overlay each entry.
    for x in src:
        if 'file' in x:
            if x['file'] in files:
                overlay_file(x, files[x['file']])
            else:
                logging.debug(f"Adding file {x['file']}")
                dst.append(x)
        elif 'dir' in x:
            if x['dir'] in dirs:
                overlay_dir(x, dirs[x['dir']])
            else:
                logging.debug(f"Adding dir {x['dir']}")
                dst.append(x)
        else:
            raise


# Evaluate if a when-condition is true.
def evaluate_when_condition(conditions, context, any_not_all=True):
    logging.debug(f"Evaluate {conditions}, any_not_all: {any_not_all}")
    found_all = True
    found_some = False

    for i, c in enumerate(conditions):
        for d in context:
            if c in d:
                logging.debug(f"`{c}' found in `{d}'")
                found_some = True
                break
        else:
            logging.debug(f"Did not find `{c}'")
            found_all = False

    if not any_not_all and found_all or any_not_all and found_some:
        return True
    else:
        return False


# Apply all the overlays conditionaly to the main tree.
def apply_overlays(conf, context):
    for i, o in enumerate(conf['overlays']):

        if ('when-any' in o
           and evaluate_when_condition(o['when-any'], context, True)
           or 'when-all' in o
           and evaluate_when_condition(o['when-all'], context, False)):
            logging.debug(f"Applying overlay {i}")
            overlay_tree(o['tree'], conf['tree'])


def dump_config(conf, filename):
    logging.debug(f'Dump {filename}')

    with open(filename, 'w') as yamlfile:
        yaml.dump(conf, yamlfile, Dumper=yaml.CDumper)


if __name__ == '__main__':
    me = os.path.realpath(__file__)
    here = os.path.dirname(me)
    parser = argparse.ArgumentParser(
        description='Perform a number of verifications on a SystemReady'
                    ' results tree.',
        epilog='We expect the tree to be layout as described in the '
               'SystemReady IR template '
               '(https://gitlab.arm.com/systemready/systemready-ir-template).',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--config', help='Specify YAML configuration file',
        default=f'{here}/check-sr-results.yaml')
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        '--dir', help='Specify directory to check', default='.')
    parser.add_argument(
        '--detect-file-encoding-limit', type=int, default=999,
        help='Specify file encoding detection limit, in number of lines')
    parser.add_argument('--dump-config', help='Output yaml config filename')
    parser.add_argument(
        '--identify', help='Specify identify.py path',
        default=f'{here}/identify.py')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    ln = logging.getLevelName(logging.WARNING)
    logging.addLevelName(logging.WARNING, f"{yellow}{ln}{normal}")
    ln = logging.getLevelName(logging.ERROR)
    logging.addLevelName(logging.ERROR, f"{red}{ln}{normal}")

    detect_file_encoding_limit = args.detect_file_encoding_limit

    check_prerequisites()

    me = os.path.realpath(__file__)
    here = os.path.dirname(me)

    # Identify SystemReady version.
    conf = load_config(args.config)
    identify = args.identify + (' --debug' if args.debug else '')
    files, ver = run_identify(args.dir, identify)

    if 'overlays' in conf:
        context = (ver, *files) if ver is not None else ()
        apply_overlays(conf, context)
        del conf['overlays']

    if args.dump_config is not None:
        dump_config(conf, args.dump_config)

    stats = check_tree(conf['tree'], args.dir)
    logging.info(stats)
