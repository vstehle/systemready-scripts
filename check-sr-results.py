#!/usr/bin/env python3

import argparse
import logging
import sys
import yaml
import os
import curses
from chardet.universaldetector import UniversalDetector
import glob
import hashlib
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
        line = re.sub(r'.\x08', '', line)

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
            line = cleanup_line(line)

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


# subprocess.run() wrapper
def run(*args, **kwargs):
    logging.debug(f"Running {args} {kwargs}")
    cp = subprocess.run(*args, **kwargs)
    logging.debug(f"{cp}")
    return cp


# If a file is an archive we know of, check its integrity.
# We know about tar(-gz) for now.
# TODO! More archives types.
# We return a Stats object.
def maybe_check_archive(filename):
    stats = Stats()

    if re.match(r'.*\.(tar|tar\.gz|tgz)$', filename):
        logging.debug(f"Checking archive `{filename}'")

        cp = run(
            f"tar tf {filename} >/dev/null", shell=True,
            capture_output=True)

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
            logging.debug(f"`{dirname}/' {yellow}empty (allowed){normal}")
        else:
            logging.error(f"`{dirname}/' {red}empty{normal}")
            stats.inc_error()
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


# Compute the sha256 of a file.
# Return the hash or None.
def hash_file(filename):
    logging.debug(f"Hash `{filename}'")
    hm = 'sha256'
    hl = hashlib.new(hm)

    with open(filename, 'rb') as f:
        hl.update(f.read())

    h = hl.hexdigest()
    logging.debug(f"{hm} {h} {filename}")
    return h


# Try to identify the EBBR.seq file using its sha256 in a list of known
# versions in conf.
# Return the identifier and SystemReady version or None, None.
def identify_ebbr_seq(conf, dirname):
    logging.debug(f"Identify EBBR.seq in `{dirname}/'")
    ebbr_seq = f"{dirname}/acs_results/sct_results/Sequence/EBBR.seq"

    if not os.path.isfile(ebbr_seq):
        logging.warning(
            f"{yellow}Missing{normal} `{ebbr_seq}' sequence file...")
        return None, None

    h = hash_file(ebbr_seq)

    # Try to identify the seq file
    for x in conf['ebbr_seq_files']:
        if x['sha256'] == h:
            logging.info(
                f"""{green}Identified{normal} `{ebbr_seq}'"""
                f""" as "{x['name']}" (SystemReady {x['version']}).""")
            return x['name'], x['version']

    logging.warning(f"{yellow}Could not identify{normal} `{ebbr_seq}'...")
    return None, None


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
    cp = run('tar --version', shell=True, capture_output=True)

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


# Apply all the overlays matching the seq_id to the main tree.
def apply_overlays(conf, seq_id):
    for i, o in enumerate(conf['overlays']):
        if seq_id not in o['ebbr_seq_files']:
            continue

        logging.debug(f"Applying overlay {i}")
        overlay_tree(o['tree'], conf['tree'])


def dump_config(conf, filename):
    logging.debug(f'Dump {filename}')

    with open(filename, 'w') as yamlfile:
        yaml.dump(conf, yamlfile, Dumper=yaml.CDumper)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Perform a number of verifications on a SystemReady'
                    ' results tree.',
        epilog='We expect the tree to be layout as described in the'
               ' SystemReady template'
               ' (https://gitlab.arm.com/systemready/systemready-template).',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        '--dir', help='Specify directory to check', default='.')
    parser.add_argument(
        '--detect-file-encoding-limit', type=int, default=999,
        help='Specify file encoding detection limit, in number of lines')
    parser.add_argument('--dump-config', help='Output yaml config filename')
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

    # Identify EBBR.seq to detect SystemReady version.
    conf = load_config(f'{here}/check-sr-results.yaml')
    seq_id, ver = identify_ebbr_seq(conf, args.dir)

    if 'overlays' in conf:
        apply_overlays(conf, seq_id)
        del conf['overlays']

    if args.dump_config is not None:
        dump_config(conf, args.dump_config)

    stats = check_tree(conf['tree'], args.dir)
    logging.info(stats)
