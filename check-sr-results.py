#!/usr/bin/env python3

import argparse
import logging
import sys
import os
import curses
import glob
import re
import subprocess
import fnmatch
import tempfile
import shutil
import time
from typing import Final, cast, Any, Optional, Literal, IO, TypedDict
import requests
import yaml
import guid
import logreader

SctParserResultMdType = TypedDict('SctParserResultMdType', {'seq-file': str})

FileType = TypedDict('FileType', {
    'file': str,
    'optional': None,
    'can-be-empty': None,
    'must-have-esp': None,
    'capsuleapp-esrt': None,
    'uefi-capsule': None,
    'devicetree': None,
    'uefi-sniff': None,
    'report-txt': None,
    'min-occurrences': int,
    'warn-if-not-named': str,
    'sct-parser-result-md': SctParserResultMdType,
    'must-contain': list[str],
    'should-contain': list[str],
    'warn-once-if-contains': list[str],
    'warn-if-contains': list[str],
    'error-if-contains': list[str]},
    total=False)

DirType = TypedDict('DirType', {
    'dir': str,
    'optional': None,
    'min-entries': int,
    'max-entries': int,
    'min-occurrences': int,
    'warn-if-not-named': str,
    'tree': 'TreeType'},
    total=False)

TreeType = list[FileType | DirType]
ContextType = list[str]

OverlayType = TypedDict('OverlayType', {
    'when-any': list[str],
    'when-all': list[str],
    'tree': TreeType},
    total=False)

ConfigType = TypedDict('ConfigType', {
    'check-sr-results-configuration': None,
    'tree': TreeType,
    'overlays': list[OverlayType]},
    total=False)

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
        tmp = curses.tigetstr('sgr0')
        normal = tmp.decode() if tmp is not None else ''
        red = curses.tparm(setafb, curses.COLOR_RED).decode() or ''
        yellow = curses.tparm(setafb, curses.COLOR_YELLOW).decode() or ''
        green = curses.tparm(setafb, curses.COLOR_GREEN).decode() or ''
    except Exception:
        pass

# guid-tool.py command.
# This will be set after command line argument parsing.
guid_tool = None

# capsule-tool.py command.
# This will be set after command line argument parsing.
capsule_tool = None

# dtc command.
# This will be set after command line argument parsing.
dtc = None

# dt-parser.py command.
# This will be set after command line argument parsing.
dt_parser = None

# ethernet-parser.py command.
# This will be set after command line argument parsing.
ethernet_parser = None
num_eth_devices = None

# dt-validate command.
# This will be set after command line argument parsing.
dt_validate = None

# (SCT) parser.py command.
# This will be set after command line argument parsing.
parser = None

# compatibles command.
# This will be set after command line argument parsing.
compatibles = None

# Linux tarball URL.
# This will be set after command line argument parsing.
linux_url = None

# Cache dir.
# This will be set after command line argument parsing.
cache_dir = None

# Force re-generating all we can.
# This will be set after command line argument parsing.
force_regen = None

# Output all warnings, including all the ones, which are normally output only
# once.
# This will be set after command line argument parsing.
_all = None

# ESRT GUIDs.
# This is populated when checking the ESRT, and is used later on to check
# capsules.
esrt_guids = set()

# Capsule GUIDs.
# This is populated when checking capsules, and is used during deferred checks
# to verify against ESRT GUIDs.
# Entries are dicts with keys 'guid' and 'filename'.
capsule_guids = []

# Partitions device paths.
# This is populated when checking UEFI logs, and is used during deferred checks
# to verify against ESPs.
# Entries are dicts with keys 'dev-path' and 'filename'.
dev_paths = []

# ESPs device paths.
# This is populated when checking the UEFI sniff test log, and is used later on
# to check some UEFI logs.
# We use a dict for the ESPs device paths to preserve the order in which they
# are added and ensure uniqueness like with a set().
esp_dev_paths: dict[str, None] = {}

# Logs to check for ethernet.
# This is populated when checking for ethernet, and is deferred checked later
# on.
ethernets = set()

# Fields from report.txt.
# This is populated when checking the report.txt, and is used later on.
report_txt: dict[str, Any] = {}

# Linux bindings folder relative path under the cache folder.
BINDINGS_REL_PATH: Final = 'bindings'

# Compatible strings file relative path under the cache folder.
COMPAT_REL_PATH: Final = 'compatible-strings.txt'

# The set of files and dirs, which were not checked.
# This is printed in debug mode, to help create the configuration file.
not_checked = set()

# The set of already reported warnings, which we report only once.
warn_once: set[str] = set()

# Meta data about this run.
meta_data = {}

# Keep track of (min-)occurrences.
occurrences: dict[str, list[str]] = {}


# Compute the plural of a word.
def maybe_plural(n: int, word: str) -> str:
    if n < 2:
        return word

    ll = word[len(word) - 1].lower()

    if ll in ('d', 's'):
        return word

    return f'{word}s'


# A class to account for statistics
class Stats:
    COUNTERS: Final = ['check', 'pass', 'warning', 'error']

    COLORS: Final = {
        'pass': green,
        'warning': yellow,
        'error': red,
    }

    def __init__(self) -> None:
        self.data = {}

        for c in Stats.COUNTERS:
            self.data[c] = 0

    def _counter_str(self, x: str) -> str:
        n = self.data[x]
        color = Stats.COLORS[x] if n and x in Stats.COLORS else ''
        return f'{color}{n} {maybe_plural(n, x)}{normal}'

    def __str__(self) -> str:
        return ', '.join(map(self._counter_str, Stats.COUNTERS))

    # Add the counters of a Stats objects to self.
    def add(self, x: 'Stats') -> None:
        for c in Stats.COUNTERS:
            self.data[c] += x.data[c]

    def _inc(self, x: Literal['pass', 'warning', 'error']) -> None:
        self.data[x] += 1
        self.data['check'] += 1

    # Increment 'pass' counter.
    def inc_pass(self) -> None:
        self._inc('pass')

    # Increment 'warning' counter.
    def inc_warning(self) -> None:
        self._inc('warning')

    # Increment 'error' counter.
    def inc_error(self) -> None:
        self._inc('error')


# Download (possibly large) file from URL.
# We raise an exception in case of issue.
def download_file(url: str, filename: str) -> None:
    logging.debug(f"Download {url} -> `{filename}'")

    with requests.get(url, stream=True, timeout=42) as r:
        r.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)


# Determine the path of a command.
# We ignore the command arguments.
# Return the path or None.
def which(command: str) -> Optional[str]:
    logging.debug(f"Which `{command}'")
    r = shutil.which(re.sub(r' .*', '', command))
    logging.debug(f"`{r}'")
    return r


# Get cached linux folder.
# If necessary, we download the Linux tarball from a URL and extract it.
# We handle file:// URLs, too.
# We raise an exception or exit in case of issue.
# We cache the bindings under cache_dir.
# We re-generate the cache if it more than one hour older than the script. This
# is to make sure cache format is somewhat in sync with the script version,
# while allowing convenient development.
# We return the dir name.
def get_linux_cache() -> str:
    assert linux_url is not None
    linux_ver = re.sub(r'\.tar\..*', '', os.path.basename(linux_url))
    cached = f"{cache_dir}/{linux_ver}"
    stamp = f"{cached}/.stamp"
    one_hour = 60 * 60
    meta_data['linux-version'] = linux_ver

    # Is this a cache hit?
    if not need_regen(stamp, [os.path.realpath(__file__)], margin=one_hour):
        logging.debug(f"Cache hit for `{cached}' (according to `{stamp}')")
        return cached

    # If we arrive here this is a cache miss: re-create cache folder for
    # robustness.
    logging.debug(f"Cache miss: (re-)creating cache dir `{cached}'")
    shutil.rmtree(cached, ignore_errors=True)
    os.makedirs(cached)

    # Download and extract Linux.
    with tempfile.TemporaryDirectory() as tmpdirname:
        if re.match(r'file://', linux_url):
            t = re.sub(r'file://', '', linux_url)
        else:
            t = f"{tmpdirname}/{os.path.basename(linux_url)}"
            logging.info(f"Downloading {linux_url} to `{t}'")
            download_file(linux_url, t)

        # Extract Linux bindings from tarball.
        bindings = f"{cached}/{BINDINGS_REL_PATH}"
        logging.info(f"Extracting Linux bindings from `{t}' to `{bindings}'")

        cp = run(
            f"tar -C '{cached}' --strip-components=3 -xf '{t}' "
            f"'{linux_ver}/Documentation/devicetree/bindings'")

        if cp.returncode:
            logging.error(f"{red}Bad Linux tarball{normal} `{t}'")
            sys.exit(1)

    assert os.path.isdir(bindings)

    # Extract compatible strings.
    compat = f"{cached}/{COMPAT_REL_PATH}"
    logging.info(f"Extracting Linux compatible strings to `{compat}'")
    cp = run(f"{compatibles} '{bindings}' >'{compat}'")

    if cp.returncode:
        logging.error(f"{red}compatibles failed{normal}")
        sys.exit(1)

    # Create stamp.
    # While at it, save our meta-data there.
    logging.debug(f"Creating `{stamp}'")

    with open(stamp, 'w') as f:
        print_meta(f)

    return cached


# Get (cached) bindings folder.
# We return the dir name.
def get_bindings() -> str:
    return get_linux_cache() + f"/{BINDINGS_REL_PATH}"


# Get (cached) compatible strings file.
# We return the file name.
def get_compat() -> str:
    return get_linux_cache() + f"/{COMPAT_REL_PATH}"


# Load YAML configuration file.
# See the README.md for details on the file format.
def load_config(filename: str) -> ConfigType:
    logging.debug(f'Load {filename}')

    with open(filename, 'r') as yamlfile:
        y = yaml.load(yamlfile, **yaml_load_args)
        conf = cast(Optional[ConfigType], y)

    if conf is None:
        conf = {
            'check-sr-results-configuration': None,
            'tree': []
        }

    assert 'check-sr-results-configuration' in conf
    return conf


# Check that a file contains what it must.
# must_contain is a list of strings to look for in the file, in order.
# We can deal with utf-16.
# When error_not_warn is True we issue an error on failure, otherwise we issue
# a warning.
# We return a Stats object.
def check_file_contains(
        must_contain: list[str], filename: str, error_not_warn: bool) -> Stats:

    action = 'error' if error_not_warn else 'warn'
    logging.debug(
        f"Check that file `{filename}' contains {must_contain} and {action}")
    assert len(must_contain)

    q = list(must_contain)
    pat: Optional[str] = q.pop(0)
    logging.debug(f"Looking for `{pat}'")
    assert isinstance(pat, str)
    stats = Stats()

    # Open the file with the proper encoding and look for patterns
    for i, line in enumerate(logreader.LogReader(filename)):
        if line.find(pat) >= 0:
            logging.debug(
                f"`{pat}' {green}found{normal} at line {i + 1}: `{line}'")
            stats.inc_pass()

            if len(q) == 0:
                pat = None
                break

            pat = q.pop(0)
            logging.debug(f"Looking for `{pat}'")

    if pat is not None:
        if error_not_warn:
            logging.error(
                f"{red}Could not find{normal} `{pat}' in `{filename}'")
            stats.inc_error()
        else:
            logging.warning(
                f"{yellow}Could not find{normal} `{pat}' in `{filename}'")
            stats.inc_warning()

    return stats


# Warn or issue an error if a file contains specific patterns.
# strings is a list of strings to look for in the file.
# Order is not taken into account.
# We can deal with utf-16.
# We return a Stats object.
# We report only the first match of each pattern.
# When a match is found, if error_not_warn is True we issue an error, otherwise
# we issue a warning.
# once is an optional set of already reported matches. When this is not None,
# we use it to remember which match was already reported and report matches
# only once (except when using `--all', in which case all the warnings are
# reported).
# A match is the combination of the pattern plus the full matching line.
def if_contains(
        strings: list[str], filename: str, error_not_warn: bool,
        once: Optional[set[str]]) -> Stats:

    action = 'Error' if error_not_warn else 'Warn'
    logging.debug(f"{action} if file `{filename}' contains {strings}")
    stats = Stats()
    # We use a dict for the patterns to preserve the order and be able
    # to remove them like with a set().
    pats = dict.fromkeys(strings)

    # Open the file with the proper encoding and look for patterns
    for i, line in enumerate(logreader.LogReader(filename)):
        if len(pats) == 0:
            break

        for p in list(pats.keys()):
            if p in line:
                match = f"{p}%{line}"

                if error_not_warn:
                    logging.error(
                        f"`{p}' {red}found{normal} in `{filename}' "
                        f"at line {i + 1}: `{line}'")
                    stats.inc_error()
                elif _all or once is None or match not in once:
                    msg = (f"`{p}' {yellow}found{normal} in `{filename}' "
                           f"at line {i + 1}: `{line}'")

                    if once is not None:
                        msg += ' (warning once)'
                        once.add(match)

                    logging.warning(msg)
                    stats.inc_warning()

                del pats[p]

    if len(strings) > 0 and len(strings) == len(pats):
        logging.debug(f"{green}No pattern{normal} in `{filename}'")
        stats.inc_pass()

    return stats


# Warn if a file contains specific patterns.
def warn_if_contains(strings: list[str], filename: str) -> Stats:
    return if_contains(strings, filename, False, None)


# Warn once if a file contains specific patterns.
def warn_once_if_contains(strings: list[str], filename: str) -> Stats:
    return if_contains(strings, filename, False, warn_once)


# Issue an error if a file contains specific patterns.
def error_if_contains(strings: list[str], filename: str) -> Stats:
    return if_contains(strings, filename, True, None)


# subprocess.run() wrapper
def run(cmd: str) -> subprocess.CompletedProcess[bytes]:
    logging.debug(f"Running {cmd}")
    cp = subprocess.run(cmd, shell=True, capture_output=True, check=False)
    logging.debug(cp)
    return cp


# If a file is an archive we know of, check its integrity.
# We know about tar(-gz) for now.
# TODO! More archives types.
# We return a Stats object.
def maybe_check_archive(filename: str) -> Stats:
    stats = Stats()

    if re.match(r'.*\.(tar|tar\.gz|tgz)$', filename):
        logging.debug(f"Checking archive `{filename}'")
        cp = run(f"tar tf '{filename}' >/dev/null")

        if cp.returncode:
            logging.error(f"{red}Bad archive{normal} `{filename}'")
            stats.inc_error()
        else:
            stats.inc_pass()

    return stats


# Identify a GUID
# We return a Stats object.
def identify_guid(guid: guid.Guid, message: str = '') -> Stats:
    logging.debug(f"Identify GUID {guid}")
    stats = Stats()
    cp = run(f"{guid_tool} {guid}")

    if cp.returncode:
        # This could be a malformed GUID so deal with it gracefully.
        logging.error(
            f"{red}Bad{normal} guid tool return code {cp.returncode} "
            f"({cp.args})")
        stats.inc_error()

    else:
        o = cp.stdout.decode().rstrip()

        if o == 'Unknown':
            logging.info(f"GUID `{guid}' {green}unknown{normal}{message}")
            stats.inc_pass()
        else:
            logging.warning(
                f"GUID `{guid}' {yellow}is known{normal}: \"{o}\"{message}")
            stats.inc_warning()

    return stats


# Check the GUIDs in CapsuleApp_ESRT_table_info.log.
# We record the GUIDs for later capsule matching.
# We return a Stats object.
def check_capsuleapp_esrt(filename: str) -> Stats:
    logging.debug(f"Check CapsuleApp ESRT `{filename}'")
    stats = Stats()
    num_guids = 0

    # Open the file with the proper encoding and look for patterns
    with open(filename, encoding='UTF-16', errors='replace') as f:
        for line in f:
            m = re.match(r'\s+FwClass\s+- ([0-9A-F-]+)', line)
            if m:
                g = guid.Guid(m[1])
                stats.add(identify_guid(g, f", in `{filename}'"))
                esrt_guids.add(g)    # Record for later capsule matching.
                num_guids += 1

    # At least one GUID.
    if num_guids:
        logging.debug(
            f"{green}{num_guids} GUID(s){normal} found in `{filename}'")
        stats.inc_pass()
    else:
        logging.error(f"{red}No GUID{normal} found in `{filename}'")
        stats.inc_error()

    return stats


# Check UEFI Capsule binary.
# We return a Stats object.
def check_uefi_capsule(filename: str) -> Stats:
    logging.debug(f"Check UEFI Capsule `{filename}'")
    stats = Stats()
    cp = run(f"{capsule_tool} --print-guid '{filename}'")

    if cp.returncode:
        logging.error(f"Capsule tool {red}failed{normal} on `{filename}'")
        stats.inc_error()
        return stats

    o = cp.stdout.decode().splitlines()
    logging.debug(o)
    e = cp.stderr.decode()

    # Authenticated capsule in FMP format.
    if o[0] == 'Valid authenticated capsule in FMP format':
        logging.debug(f"{green}Valid capsule{normal} `{filename}'")
        stats.inc_pass()
    else:
        logging.error(f"{red}Invalid capsule{normal} `{filename}'")
        stats.inc_error()

    # GUID.
    m = re.match(r'Image type id GUID: ([a-f0-9-]+)', o[1])
    if m:
        g = guid.Guid(m[1])
        logging.debug(f"Capsule image type GUID is `{g}'")

        # Record the GUID for deferred check against the ESRT.
        capsule_guids.append({'guid': g, 'filename': filename})

    else:
        logging.error(
            f"capsule-tool returned {red}no GUID{normal} from `{filename}'!")
        stats.inc_error()

    m = re.search(
        r"Capsule update image type id `([0-9a-f-]+)' is known: "
        r"\"([^\n]+)\"\n", e)
    n = re.search(
        r"Capsule update image type id `([0-9a-f-]+)' is unknown", o[-1])

    if m and not n:
        logging.warning(
            f"Capsule GUID `{m[1]}' {yellow}is known{normal}: \"{m[2]}\", "
            f"in `{filename}'")
        stats.inc_warning()

    elif n and not m:
        logging.info(
            f"Capsule GUID `{n[1]}' {green}is unknown{normal}, "
            f"in `{filename}'")
        stats.inc_pass()

    else:
        logging.error('Bad capsule guid search!')
        sys.exit(1)

    return stats


# Determine if we need to re-generate a file.
# We return True if:
# - Re-generation is forced
# - The file is missing
# - Or the file is older than one of its dependencies
# Dependencies can be files or dirs names.
# A margin (in seconds, zero by default) can be specified to avoid
# re-generating files to often.
# We return False otherwise
def need_regen(filename: str, deps: list[str], margin: int = 0) -> bool:
    logging.debug(f"Need regen `{filename}' <- {deps} (margin: {margin})")

    if force_regen:
        logging.debug(f"Forcing re-generation of `{filename}'")
        return True

    if not os.path.isfile(filename):
        logging.debug(f"`{filename}' does not exist")
        return True

    s = os.stat(filename)

    # Any dependency more recent? (We take margin into account.)
    for f in deps:
        if os.stat(f).st_mtime - margin > s.st_mtime:
            logging.debug(
                f"`{f}' is more recent than `{filename}': re-generate")
            return True

    logging.debug(f"No need to re-generate `{filename}'")
    return False


# Check Devicetree blob.
# We run dtc and dt-validate to produce the log when needed.
# We add markers to the log, which will be ignored by dt-parser.py.
# We return a Stats object.
def check_devicetree(filename: str) -> Stats:
    logging.debug(f"Check Devicetree `{filename}'")
    stats = Stats()
    log = f"{filename}.log"
    bindings = get_bindings()
    assert dtc is not None
    assert dt_validate is not None

    if need_regen(log, [filename, bindings, which(dtc), which(dt_validate)]):
        # Run dtc.
        with open(log, 'w') as f:
            print('+ DTC', file=f)

        cp = run(
            f"{dtc} -o /dev/null -O dts -I dtb -s -f '{filename}' "
            f">>'{log}' 2>&1")

        if cp.returncode:
            logging.error(
                f"dtc {red}failed{normal} on `{filename}' (see {log})")
            stats.inc_error()
            return stats

        # Run dt-validate.
        with open(log, 'a') as f:
            print('+ DT-VALIDATE', file=f)

        cp = run(
            f"{dt_validate} -m -s '{bindings}' '{filename}' "
            f">>'{log}' 2>&1")

        if cp.returncode:
            logging.error(
                f"dt-validate {red}failed{normal} on `{filename}' (see {log})")
            stats.inc_error()
            return stats

        # End marker; while at it, append our meta-data there.
        with open(log, 'a') as f:
            print('+ END', file=f)
            print_meta(f, pre='+ ')

        logging.info(f"{green}Created{normal} `{log}'")

    # Verify the log with dt-parser.
    # We use the compatible strings extracted from Linux bindings to filter out
    # more false positive.
    compat = get_compat()
    cp = run(f"{dt_parser} --compatibles '{compat}' '{log}'")

    if cp.returncode:
        logging.error(f"dt-parser {red}failed{normal} on `{log}'!")
        stats.inc_error()
        return stats

    if re.search(r'Unparsed line', cp.stderr.decode()):
        logging.warning(
            f"dt-parser reports {yellow}unparsed{normal} with `{log}'!")
        stats.inc_warning()

    t = cp.stdout.decode().splitlines()
    logging.debug(t)

    # Look for Summary line.
    for i, line in enumerate(t):
        if line == 'Summary':
            break
    else:
        logging.error(f"{red}No dt-parser Summary{normal} with `{log}'!")
        stats.inc_error()
        return stats

    # Verify underline.
    if not re.match(r'-+$', t[i + 1]):
        logging.error(
            f"{red}bad dt-parser header{normal} `{t[i + 1]}' "
            f"with `{log}'!")
        stats.inc_error()
        return stats

    # Parse Summary statistics.
    for line in t[i + 2:]:
        logging.debug(line)
        m = re.match(r'\s*(\d+)\s+(.+)', line)

        if not m:
            logging.error(
                f"{red}bad dt-parser line{normal} `{line}' with `{log}'!")
            stats.inc_error()
            continue

        num, typ = m[1], m[2]

        if re.search(r'error', typ):
            logging.error(f"{red}{num} dt-parser {typ}{normal} with `{log}'!")
            stats.inc_error()

        elif re.search(r'warning', typ):
            logging.debug(
                f"{yellow}{num} dt-parser {typ}{normal} with `{log}'!")

        elif typ == 'ignored':
            logging.debug(f"{green}{num} dt-parser {typ}{normal} with `{log}'")
            stats.inc_pass()

        else:
            logging.error(
                f"{red}{num} unknown dt-parser type `{typ}'{normal} "
                f"with `{log}'!")
            stats.inc_error()

    return stats


# Check UEFI Shell sniff test log.
# We check if we have at least one ESP.
# We record the ESPs we found for later verification of must-have-esp files.
# We return a Stats object.
def check_uefi_sniff(filename: str) -> Stats:
    logging.debug(f"Check UEFI Shell sniff test log `{filename}'")
    stats = Stats()
    n = 0

    # Open the file with the proper encoding and look for ESPs
    for i, line in enumerate(logreader.LogReader(filename)):
        m = re.match(
            r'\S[0-9a-fA-F]+: DevicePath\([^\)]+\) +(/\S+) '
            r'BlockIO\([^\)]+\).* EFISystemPartition\([^\)]+\)', line)

        if m:
            logging.debug(f"ESP match line {i + 1}, `{line}'")
            esp_dev_paths[m[1]] = None
            esp = re.sub(r'.*/', '', m[1])
            logging.info(f"{green}Found ESP{normal} `{esp}'")
            n += 1

    if n:
        logging.debug(f"{green}Found{normal} {n} ESP(s)")
        stats.inc_pass()
    else:
        logging.error(f"{red}Could not find{normal} an ESP in `{filename}'")
        stats.inc_error()

    return stats


# Check UEFI logs for ESP.
# We record the device paths found for deferred verification against the ESPs.
# We return a Stats object.
def check_must_have_esp(filename: str) -> Stats:
    logging.debug(f"Check must have ESP `{filename}'")
    stats = Stats()
    state = 'await shell'
    # We use a dict for the device paths to preserve the order
    # in which they are added and ensure uniqueness like with a set().
    dp: dict[str, None] = {}

    # Open the file with the proper encoding and look for partitions.
    for i, line in enumerate(logreader.LogReader(filename)):
        match state:
            case 'await shell':
                # UEFI Interactive Shell v2.2
                if line.find('UEFI Interactive Shell v') == 0:
                    logging.debug(f"Matched shell line {i + 1}, `{line}'")
                    state = 'await edk2'

            case 'await edk2':
                # EDK II
                if line.find('EDK II') == 0:
                    logging.debug(f"Matched edk2 line {i + 1}, `{line}'")
                    state = 'await uefi'
                else:
                    state = 'await shell'

            case 'await uefi':
                # UEFI v2.80 (Das U-Boot, 0x20211000)
                if line.find('UEFI v') == 0:
                    logging.debug(f"Matched uefi line {i + 1}, `{line}'")
                    state = 'await map'
                else:
                    state = 'await shell'

            case 'await map':
                # Mapping table
                if line.find('Mapping table') == 0:
                    logging.debug(f"Matched map line {i + 1}, `{line}'")
                    state = 'await alias'
                else:
                    state = 'await shell'

            case 'await alias':
                # FS2: Alias(s):HD0b:;BLK5:
                if line.find('Alias(s):') >= 0:
                    logging.debug(f"Matched alias line {i + 1}, `{line}'")
                    state = 'await path'
                else:
                    logging.debug(f"No alias line {i + 1} -> done")
                    state = 'await shell'

            case 'await path':
                # /VenHw(e61d73b9-a384-4acc-aeab-82e828f3628b)/SD(1)/SD(...
                m = re.match(r'\s+(\S+)$', line)

                if m:
                    logging.debug(f"Matched path line {i + 1}, `{line}'")
                    dp[m[1]] = None
                    state = 'await alias'
                else:
                    state = 'await shell'

            case _:
                raise Exception(f"Bad state {state}")

    if len(dp):
        logging.debug(f"{green}Found{normal} device path(s): `{dp.keys()}'")
        stats.inc_pass()

        # Record the device path(s) for deferred check against the ESPs.
        for x in dp:
            dev_paths.append({'dev-path': x, 'filename': filename})

    else:
        logging.error(
            f"{red}Could not find{normal} a device path in `{filename}'")
        stats.inc_error()

    return stats


# Check template report.txt.
# We extract fields from template report.txt.
# We return a Stats object.
def check_report_txt(filename: str) -> Stats:
    logging.debug(f"Check report txt `{filename}'")
    stats = Stats()

    patterns = [
        r'^- (Total number of network controllers): (\d+)',
    ]

    assert len(report_txt) == 0

    # Open the file with the proper encoding and look for patterns.
    with open(filename, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()

            for pat in patterns:
                m = re.match(pat, line)
                if m:
                    assert m.lastindex == 2
                    logging.debug(f"{green}Matched{normal} `{line}'")
                    logging.info(f"{m[1]} = {m[2]}")
                    assert m[1] not in report_txt
                    report_txt[m[1]] = m[2]
                    stats.inc_pass()

    # Verify that we found everything.
    if len(report_txt) != len(patterns):
        logging.error(
            f"{red}Could not extract all patterns{normal} from `{filename}'")
        stats.inc_error()

    return stats


# Try to re-create result.md with the SCT parser.
# If we do not have parser.py at hand or if parsing fails, we do not treat that
# as an error here but rather rely on subsequent checks.
def sct_parser(conffile: SctParserResultMdType, filename: str) -> None:
    logging.debug(f"SCT parser `{filename}'")
    assert parser is not None
    which_parser = which(parser)

    if which_parser is None:
        logging.debug('No parser')
        return

    # Try to get parser version.
    commit = git_commit(os.path.dirname(which_parser))

    if commit is not None:
        meta_data['sct-parser-commit'] = commit

    seq = conffile['seq-file']
    ekl = 'sct_results/Overall/Summary.ekl'
    d = os.path.dirname(filename)

    if not need_regen(filename, [f"{d}/{seq}", f"{d}/{ekl}", which_parser]):
        return

    cp = run(f"cd '{d}' && {parser} {ekl} '{seq}'")

    if cp.returncode:
        logging.warning(f"SCT parser {yellow}failed{normal} `{filename}'")
    else:
        logging.info(f"{green}Created{normal} `{filename}'")


# Warn if a file or directory name does not match a pattern.
# We return a Stats object.
def warn_if_not_named(name: str, pattern: str) -> Stats:
    stats = Stats()
    bn = os.path.basename(name)

    if fnmatch.fnmatch(bn, pattern):
        logging.debug(f"`{name}' {green}named in{normal} `{pattern}'")
        stats.inc_pass()
    else:
        logging.warning(f"`{name}' {yellow}not named in{normal} `{pattern}'")
        stats.inc_warning()

    return stats


# Check a file
# We check if a file exists and is not empty.
# The following properties in the yaml configuration can relax the check:
# - optional
# - can-be-empty
# If the file has a 'must-contain' property, we look for all signatures in its
# contents in order. Same for 'should-contain', but when this fails it results
# in a warning only.
# We perform some more checks on archives.
# We try to re-create SCT parser result.md files.
# We return a Stats object.
def check_file(conffile: FileType, confpath: str, filename: str) -> Stats:
    logging.debug(f"Check `{filename}' ({confpath})")
    not_checked.discard(filename)
    stats = Stats()

    # Special case for SCT parser result.md: try to re-create it with the
    # parser before complaining.
    if 'sct-parser-result-md' in conffile:
        sct_parser(conffile['sct-parser-result-md'], filename)

    if os.path.isfile(filename):
        logging.debug(f"`{filename}' {green}exists{normal}")
        stats.inc_pass()

        if 'warn-if-not-named' in conffile:
            stats.add(warn_if_not_named(
                filename, conffile['warn-if-not-named']))

        if 'min-occurrences' in conffile:
            add_occurrence(filename, confpath)

        if os.path.getsize(filename) > 0:
            logging.debug(f"`{filename}' {green}not empty{normal}")
            stats.inc_pass()

            if 'must-contain' in conffile:
                stats.add(
                    check_file_contains(conffile['must-contain'], filename,
                                        True))

            if 'should-contain' in conffile:
                stats.add(
                    check_file_contains(conffile['should-contain'], filename,
                                        False))

            if 'warn-if-contains' in conffile:
                stats.add(
                    warn_if_contains(conffile['warn-if-contains'], filename))

            if 'warn-once-if-contains' in conffile:
                stats.add(
                    warn_once_if_contains(
                        conffile['warn-once-if-contains'], filename))

            if 'error-if-contains' in conffile:
                stats.add(
                    error_if_contains(conffile['error-if-contains'], filename))

            # Check archives integrity.
            stats.add(maybe_check_archive(filename))

            if 'capsuleapp-esrt' in conffile:
                # Check CapsuleApp_ESRT_table_info.log.
                stats.add(check_capsuleapp_esrt(filename))

            if 'uefi-capsule' in conffile:
                stats.add(check_uefi_capsule(filename))

            if 'devicetree' in conffile:
                stats.add(check_devicetree(filename))

            if 'ethernet' in conffile:
                logging.debug(
                    f"Record `{filename}' for deferred ethernet check.")
                assert filename not in ethernets
                ethernets.add(filename)

            if 'uefi-sniff' in conffile:
                stats.add(check_uefi_sniff(filename))

            if 'must-have-esp' in conffile:
                stats.add(check_must_have_esp(filename))

            if 'report-txt' in conffile:
                stats.add(check_report_txt(filename))

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


# Record an occurrence of a file or a dir.
def add_occurrence(pathname: str, confpath: str) -> None:
    logging.debug(f"Add occurrence `{pathname}/' ({confpath})")

    if confpath not in occurrences:
        occurrences[confpath] = []

    occurrences[confpath].append(pathname)


# Check a dir
# We check if a dir exists and is not empty (min-entries can override the
# later).
# The following properties in the yaml configuration can modify the check:
# - optional
# - min-entries
# - max-entries
# If the dir has a tree, we recurse with check_tree().
# We return a Stats object.
def check_dir(confdir: DirType, confpath: str, dirname: str) -> Stats:
    logging.debug(f"Check `{dirname}/' ({confpath})")
    not_checked.discard(dirname)
    stats = Stats()

    if os.path.isdir(dirname):
        logging.debug(f"`{dirname}/' {green}exists{normal}")
        stats.inc_pass()

        if 'warn-if-not-named' in confdir:
            stats.add(warn_if_not_named(
                dirname, confdir['warn-if-not-named']))

        if 'min-occurrences' in confdir:
            add_occurrence(dirname, confpath)

        entries = os.listdir(dirname)
        ent = len(entries)
        logging.debug(f"`{dirname}/' has {ent} entrie(s)")

        for e in entries:
            not_checked.add(f"{dirname}/{e}")

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
            stats.add(check_tree(confdir['tree'], confpath, dirname))

    elif 'optional' in confdir:
        logging.debug(f"`{dirname}/' {yellow}missing (optional){normal}")
    else:
        logging.error(f"`{dirname}/' {red}missing{normal}")
        stats.inc_error()

    return stats


# Return True if a string is a glob pattern, False otherwise.
def is_glob(x: str) -> bool:
    e = glob.escape(x)
    return x != e


# Try to identify the results.
# We call the external script `identify.py'.
# Return the list of identified files and the SystemReady version
# or [], None in case of error.
def run_identify(
        dirname: str, identify: str) -> tuple[list[str], Optional[str]]:

    logging.debug(f"Identify {dirname}")

    cp = run(f"{identify} --dir '{dirname}' --known-files")

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
def check_tree(conftree: TreeType, confpath: str, dirname: str) -> Stats:
    logging.debug(f"Check `{dirname}/' ({confpath})")
    assert isinstance(conftree, list)
    stats = Stats()

    for e in conftree:
        if 'file' in e:
            f = cast(FileType, e)
            p = f"{confpath}/{f['file']}"
            pathname = f"{dirname}/{f['file']}"
        elif 'dir' in e:
            d = cast(DirType, e)
            p = f"{confpath}/{d['dir']}"
            pathname = f"{dirname}/{d['dir']}"
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
            if 'file' in e:
                f = cast(FileType, e)
                stats.add(check_file(f, p, x))
            elif 'dir' in e:
                d = cast(DirType, e)
                stats.add(check_dir(d, p, x))

    return stats


# Deferred check that all capsule GUIDs are in the ESRT.
# Those checks are run after checking all files and dirs.
# This allows to decouple checks from the configuration file order.
# We return a Stats object.
def deferred_check_capsule_guids_in_esrt() -> Stats:
    logging.debug('Deferred check capsule GUIDs in ESRT')
    stats = Stats()
    logging.debug(f"Capsule GUIDs: {capsule_guids}")
    logging.debug(f"ESRT GUIDs: {esrt_guids}")

    for x in capsule_guids:
        guid = x['guid']
        filename = x['filename']

        if guid in esrt_guids:
            logging.debug(
                f"GUID `{guid}' from `{filename}' {green}in ESRT{normal}")
            stats.inc_pass()
        else:
            logging.error(
                f"GUID `{guid}' from `{filename}' {red}not in ESRT{normal}")
            stats.inc_error()

    return stats


# Deferred check that some UEFI log files have (a device path corresponding to)
# an ESP.
# Those checks are run after checking all files and dirs.
# This allows to decouple checks from the configuration file order.
# We return a Stats object.
def deferred_check_uefi_logs_esp() -> Stats:
    logging.debug('Deferred check UEFI logs ESP')
    stats = Stats()
    logging.debug(f"ESP device path(s): {esp_dev_paths.keys()}")
    logging.debug(f"Device path(s): {dev_paths}")
    filenames = {}

    for x in dev_paths:
        filename = x['filename']
        dev_path = x['dev-path']

        if filename not in filenames:
            logging.debug(f"`{filename}' must have an ESP")
            filenames[filename] = False

        if dev_path in esp_dev_paths:
            logging.debug(
                f"`{filename}' {green}had an ESP{normal} at `{dev_path}'")
            filenames[filename] = True
            stats.inc_pass()

    # Second path to verify that each log which needed to contain an ESP
    # actually did.
    for k, v in filenames.items():
        if not v:
            logging.error(f"`{k}' {red}did not have an ESP{normal}")
            stats.inc_error()

    return stats


# Check for min-occurrences.
# We return a Stats object.
def check_min_occurences(m: int, confpath: str) -> Stats:
    logging.debug(f"Check >= {m} occurrences for {confpath}")
    stats = Stats()
    o = occurrences.get(confpath, [])
    logging.debug(f"Occurrences {o}")
    n = len(o)

    if n < m:
        logging.error(
            f"{red}Not enough occurrences{normal} of {confpath} ({n} < {m})")

        stats.inc_error()

    return stats


# Deferred check for min-occurrences recurse helper.
# We return a Stats object.
def deferred_check_min_occurrences_recurse(
        conf: TreeType, confpath: str) -> Stats:

    logging.debug(f"Recurse {confpath}")
    stats = Stats()

    for e in conf:
        if 'file' in e:
            f = cast(FileType, e)
            p = f"{confpath}/f{['file']}"

            if 'min-occurrences' in f:
                stats.add(check_min_occurences(f['min-occurrences'], p))

        elif 'dir' in e:
            d = cast(DirType, e)
            p = f"{confpath}/{d['dir']}"

            if 'min-occurrences' in d:
                stats.add(check_min_occurences(d['min-occurrences'], p))

            if 'tree' in d:
                stats.add(deferred_check_min_occurrences_recurse(d['tree'], p))

        else:
            raise Exception

    return stats


# Deferred check for min-occurrences.
# Those checks are run after checking all files and dirs.
# This allows to decouple checks from the configuration file order.
# We return a Stats object.
def deferred_check_min_occurrences(conftree: TreeType) -> Stats:
    logging.debug(f"Deferred check min occurrences {occurrences}")
    return deferred_check_min_occurrences_recurse(conftree, '')


# Deferred check ethernet logs.
# Those checks are run after checking all files and dirs.
# We rely on the "Total number of network controllers" information parsed from
# the report.txt.
# It can also be given from command line with num_eth_devices, which has
# priority.
# We return a Stats object.
def deferred_check_ethernet() -> Stats:
    logging.debug('Deferred check ethernet')
    stats = Stats()

    if num_eth_devices is not None:
        neth = num_eth_devices
    elif 'Total number of network controllers' in report_txt:
        neth = int(report_txt['Total number of network controllers'])
    else:
        logging.debug('Number of ethernet to expect was not given')
        neth = 0

    logging.info(f"We expect {neth} ethernet {maybe_plural(neth, 'device')}.")

    if len(ethernets) > 0 and neth == 0:
        logging.warning(
            f"Number of ethernet devices {yellow}is set to 0{normal}. "
            f"Double check this is correct.")
        stats.inc_warning()
        return stats

    if neth > 0 and len(ethernets) == 0:
        logging.error(
            f"Expected {neth} ethernet {maybe_plural(neth, 'device')} "
            f"but {red}no ethernet log{normal}.")
        stats.inc_error()
        return stats

    for filename in ethernets:
        logging.debug(f"Check Ethernet `{filename}'")
        cp = run(f"{ethernet_parser} {filename} {neth}")

        if cp.returncode:
            logging.error(
                f'ethernet-parser {red}failed{normal} on {filename}')
            stats.inc_error()
            return stats

        logging.debug(f"{green} ethernet-parser {normal} with `{filename}'")
        stats.inc_pass()

    return stats


# Deferred checks
# Those checks are run after checking all files and dirs.
# This allows to decouple checks from the configuration file order.
# Deferred checks:
# - Capsule GUIDs and ESRT.
# - UEFI logs and ESP.
# We return a Stats object.
def deferred_checks(conftree: TreeType) -> Stats:
    logging.debug('Deferred checks')
    stats = Stats()
    stats.add(deferred_check_capsule_guids_in_esrt())
    stats.add(deferred_check_uefi_logs_esp())
    stats.add(deferred_check_min_occurrences(conftree))
    stats.add(deferred_check_ethernet())
    return stats


# Check that we have dt-validate.
# If we do not have it, we try to install it with pip.
# We exit in case of failure.
def check_dt_validate() -> None:
    logging.debug('Checking dt-validate')

    # Check that we have dt-validate.
    assert dt_validate is not None
    w = which(dt_validate)

    if w is None:
        # Install dt-schema (for dt-validate).
        logging.info('Installing dt-schema')

        cp = run(
                f"{sys.executable} -m pip install --break-system-packages "
                "dtschema")

        if cp.returncode:
            logging.error(f"{red}Installing dt-schema failed{normal}")
            sys.exit(1)

    else:
        logging.debug(f"Have dt-validate (`{w}')")

    # Check that dt-validate runs.
    cp = run(f"{dt_validate} --version")

    if cp.returncode:
        logging.error(f"{red}Bad {dt_validate}{normal}")
        sys.exit(1)

    meta_data['dt-validate-version'] = cp.stdout.decode().rstrip()


# Check that we have all we need.
def check_prerequisites() -> None:
    logging.debug('Checking prerequisites')

    # Check that we have tar.
    cp = run('tar --version')

    if cp.returncode:
        logging.error(f"{red}tar not found{normal}")
        sys.exit(1)

    meta_data['tar-version'] = cp.stdout.decode().splitlines()[0]

    # Check that we have guid-tool.
    cp = run(f"{guid_tool} -h")

    if cp.returncode:
        logging.error(f"{red}guid-tool not found{normal}")
        sys.exit(1)

    # Check that we have capsule-tool.
    cp = run(f"{capsule_tool} -h")

    if cp.returncode:
        logging.error(f"{red}capsule-tool not found{normal}")
        sys.exit(1)

    # Check that we have dtc.
    cp = run(f"{dtc} --version")

    if cp.returncode:
        logging.error(f"{red}dtc not found{normal}")
        sys.exit(1)

    dtc_ver = cp.stdout.decode().rstrip()
    dtc_ver = re.sub(r'Version: ', '', dtc_ver)
    meta_data['dtc-version'] = dtc_ver

    # Check that we have dt-validate.
    check_dt_validate()

    # Check that we have dt-parser.
    cp = run(f"{dt_parser} -h")

    if cp.returncode:
        logging.error(f"{red}dt-parser not found{normal}")
        sys.exit(1)

    # Check that we have compatibles.
    cp = run(f"{compatibles} -h")

    if cp.returncode:
        logging.error(f"{red}compatibles not found{normal}")
        sys.exit(1)


# Overlay one property.
# When a property has the special value 'DELETE', we delete it.
def overlay_property(dst: dict[str, Any], k: str, v: Any) -> None:
    if v == 'DELETE':
        logging.debug(f"Deleting {k}")
        del dst[k]
    else:
        logging.debug(f"{k} <- {v}")
        dst[k] = v


# Overlay the src file over the dst file, in-place.
def overlay_file(src: FileType, dst: FileType) -> None:
    logging.debug(f"Overlay file {src['file']}")

    for k, v in src.items():
        overlay_property(cast(dict[str, Any], dst), k, v)


# Overlay the src dir over the dst dir, in-place.
def overlay_dir(src: DirType, dst: DirType) -> None:
    logging.debug(f"Overlay dir {src['dir']}")

    for k, v in src.items():
        # We have a special case when "merging" tree.
        if k == 'tree' and 'tree' in dst:
            overlay_tree(src['tree'], dst['tree'])
            continue

        overlay_property(cast(dict[str, Any], dst), k, v)


# Overlay the src tree over the dst tree, in-place.
def overlay_tree(src: TreeType, dst: TreeType) -> None:
    # Prepare two LUTs.
    files = {}
    dirs = {}

    for x in dst:
        if 'file' in x:
            f = cast(FileType, x)
            files[f['file']] = f
        elif 'dir' in x:
            d = cast(DirType, x)
            dirs[d['dir']] = d
        else:
            raise Exception(f"Bad x not file or dir {x}")

    # Overlay each entry.
    for x in src:
        if 'file' in x:
            f = cast(FileType, x)
            if f['file'] in files:
                overlay_file(f, files[f['file']])
            else:
                logging.debug(f"Adding file {f['file']}")
                dst.append(f)
        elif 'dir' in x:
            d = cast(DirType, x)
            if d['dir'] in dirs:
                overlay_dir(d, dirs[d['dir']])
            else:
                logging.debug(f"Adding dir {d['dir']}")
                dst.append(d)
        else:
            raise Exception(f"Bad x not file or dir {x}")


# Evaluate if a when-condition is true.
def evaluate_when_condition(
        conditions: list[str], context: ContextType, any_not_all: bool = True
        ) -> bool:

    logging.debug(f"Evaluate {conditions}, any_not_all: {any_not_all}")
    found_all = True
    found_some = False

    for c in conditions:
        for d in context:
            if c in d:
                logging.debug(f"`{c}' found in `{d}'")
                found_some = True
                break
        else:
            logging.debug(f"Did not find `{c}'")
            found_all = False

    return bool(not any_not_all and found_all or any_not_all and found_some)


# Apply all the overlays conditionally to the main tree.
def apply_overlays(conf: ConfigType, context: ContextType) -> None:
    for i, o in enumerate(conf['overlays']):
        if ('when-any' in o
           and evaluate_when_condition(o['when-any'], context, True)
           or 'when-all' in o
           and evaluate_when_condition(o['when-all'], context, False)):
            logging.debug(f"Applying overlay {i}")
            overlay_tree(o['tree'], conf['tree'])


# While at it, put our meta-data there as comments.
def dump_config(conf: ConfigType, filename: str) -> None:
    logging.debug(f'Dump {filename}')

    with open(filename, 'w') as yamlfile:
        yaml.dump(conf, yamlfile, Dumper=yaml.CDumper)
        print_meta(f=yamlfile, pre='# ')
        logging.info(f"Dumped `{filename}'")


# Print the list of files and dirs, which were not checked.
# We print through logging.debug() as this is meant to be called in debug mode
# only, to help create the configuration file.
def print_not_checked() -> None:
    logging.debug('Not checked:')

    for x in sorted(not_checked):
        logging.debug(x)


# Get git commit.
# Return None in case of error.
def git_commit(dirname: str) -> Optional[str]:
    cp = run(f"git -C '{dirname}' describe --always --abbrev=12 --dirty")

    if cp.returncode:
        logging.debug(f"No git or {dirname} not versioned")
        return None

    return cp.stdout.decode().rstrip()


# Capture initial meta-data.
def init_meta(argv: list[str], here: str) -> None:
    meta_data['command-line'] = ' '.join(argv)
    meta_data['date'] = f"{time.asctime(time.gmtime())} UTC"
    meta_data['python-version'] = re.sub(r'\n', ' ', sys.version)

    commit = git_commit(here)

    if commit is not None:
        meta_data['git-commit'] = commit

    logging.debug(f"meta-data: {meta_data}")


# Print meta-data
def print_meta(f: IO[str] = sys.stdout, pre: str = '') -> None:
    print(f"{pre}meta-data", file=f)
    print(f"{pre}---------", file=f)

    for k in sorted(meta_data.keys()):
        print(f"{pre}{k}: {meta_data[k]}", file=f)


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
        '--all', action='store_true',
        help='Output all warnings, even the "once" ones.')
    parser.add_argument(
        '--cache-dir', help='Specify cache directory',
        default=f"{os.path.expanduser('~')}/.check-sr-results")
    parser.add_argument(
        '--capsule-tool', help='Specify capsule-tool.py path',
        default=f'{here}/capsule-tool.py')
    parser.add_argument(
        '--cleanup-line-limit', type=int, default=99,
        help='Specify maximum number of iterations for line cleanup')
    parser.add_argument(
        '--compatibles', help='Specify compatibles path',
        default=f"{here}/compatibles")
    parser.add_argument('--config', help='Specify YAML configuration file')
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        '--dir', help='Specify directory to check', default='.')
    parser.add_argument(
        '--detect-file-encoding-limit', type=int, default=999,
        help='Specify file encoding detection limit, in number of lines')
    parser.add_argument('--dtc', help='Specify dtc path', default='dtc')
    parser.add_argument(
        '--dt-parser', help='Specify dt-parser.py path',
        default=f'{here}/dt-parser.py')
    parser.add_argument(
        '--dt-validate', help='Specify dt-validate path',
        default='dt-validate')
    parser.add_argument(
        '--ethernet-parser',
        help='Specify ethernet-parser.py path and arguments',
        default=f'{here}/ethernet-parser.py')
    parser.add_argument(
        '--ethernet-devices', type=int,
        help='Force how many ethernet devices should be checked')
    parser.add_argument('--dump-config', help='Output yaml config filename')
    parser.add_argument(
        '--force-regen', action='store_true',
        help='Force re-generating all we can')
    parser.add_argument(
        '--guid-tool', help='Specify guid-tool.py path',
        default=f'{here}/guid-tool.py')
    parser.add_argument(
        '--identify', help='Specify identify.py path',
        default=f'{here}/identify.py')
    parser.add_argument(
        '--linux-url', help='Specify Linux tarball URL',
        default='https://cdn.kernel.org/pub/linux/kernel/v6.x/'
                'linux-6.12.1.tar.xz')
    parser.add_argument(
        '--parser', help='Specify (SCT) parser.py path',
        default='parser.py')
    parser.add_argument(
        '--print-meta', action='store_true', help='Print meta-data to stdout')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    ln = logging.getLevelName(logging.WARNING)
    logging.addLevelName(logging.WARNING, f"{yellow}{ln}{normal}")
    ln = logging.getLevelName(logging.ERROR)
    logging.addLevelName(logging.ERROR, f"{red}{ln}{normal}")

    logreader.detect_file_encoding_limit = args.detect_file_encoding_limit
    logreader.cleanup_line_limit = args.cleanup_line_limit
    guid_tool = args.guid_tool + (' --debug' if args.debug else '')
    capsule_tool = args.capsule_tool + (' --debug' if args.debug else '')
    dtc = args.dtc
    dt_parser = args.dt_parser + (' --debug' if args.debug else '')
    parser = args.parser + (' --debug' if args.debug else '')
    dt_validate = args.dt_validate
    ethernet_parser = args.ethernet_parser + (' --debug' if args.debug else '')
    num_eth_devices = args.ethernet_devices
    compatibles = args.compatibles
    linux_url = args.linux_url
    cache_dir = args.cache_dir
    force_regen = args.force_regen
    _all = args.all

    # Prepare initial meta-data.
    init_meta(sys.argv, here)

    check_prerequisites()

    me = os.path.realpath(__file__)
    here = os.path.dirname(me)

    # Identify SystemReady version.
    identify = args.identify + (' --debug' if args.debug else '')
    files, ver = run_identify(args.dir, identify)

    # Choose config.
    # We default to IR 2.x.
    # We use IR 1.x when detected.
    # Command line takes precedence in all cases.
    config = f'{here}/check-sr-results.yaml'

    if ver is not None:
        if ('IR v1.' in ver or 'IR 32b v1.' in ver):
            config = f'{here}/check-sr-results-ir1.yaml'
        elif 'SR v2.5' in ver:
            config = f'{here}/check-sr-results-sr.yaml'

    if args.config:
        config = args.config

    conf = load_config(config)

    if 'overlays' in conf:
        context: ContextType = [ver, *files] if ver is not None else []
        apply_overlays(conf, context)
        del conf['overlays']

    if args.dump_config is not None:
        dump_config(conf, args.dump_config)

    stats = check_tree(conf['tree'], '', args.dir)
    stats.add(deferred_checks(conf['tree']))
    logging.info(stats)

    if args.debug:
        print_not_checked()

    if args.print_meta:
        print()
        print_meta()
