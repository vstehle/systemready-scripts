#!/usr/bin/env python3

import argparse
import logging
import os
import hashlib
from typing import Optional, cast, TypedDict
import yaml


class KnownFileType(TypedDict, total=False):
    sha256: str
    name: str
    path: str
    search: list[str]


class VersionType(TypedDict):
    files: list[str]
    version: str


DbType = TypedDict('DbType', {
    'identify-database': None,
    'known-files': list[KnownFileType],
    'versions': list[VersionType]})

CacheType = dict[str, str]
FilesType = list[dict[str, str]]


# Validate YAML identify database
# We check our magic marker.
def validate_identify_db(db: DbType) -> None:
    logging.debug("Validate identify db")
    assert 'identify-database' in db


# Load YAML identify database
def load_identify_db(filename: str) -> DbType:
    logging.debug(f"Load `{filename}'")

    with open(filename, 'r') as yamlfile:
        y = yaml.load(yamlfile, Loader=yaml.FullLoader)
        db = cast(Optional[DbType], y)

    if db is None:
        db = {
            'identify-database': None,
            'known-files': [],
            'versions': []}

    validate_identify_db(db)
    logging.debug(
        f"{len(db['known-files'])} known-files, "
        f"{len(db['versions'])} versions")
    return db


# Compute the sha256 of a file.
# Return the hash.
def hash_file(filename: str) -> str:
    logging.debug(f"Hash `{filename}'")
    hm = 'sha256'
    hl = hashlib.new(hm)

    with open(filename, 'rb') as f:
        hl.update(f.read())

    h = hl.hexdigest()
    logging.debug(f"{hm} {h} {filename}")
    return h


# Compute the sha256 of a file, with caching.
# cache must be initialized as an empty dict.
def hash_file_cached(filename: str, cache: CacheType) -> str:
    logging.debug(f"Hash/cache `{filename}'")

    if filename in cache:
        logging.debug('Cache hit')
        h = cache[filename]
    else:
        logging.debug('Cache miss')
        h = hash_file(filename)
        cache[filename] = h

    return h


# Search for strings in a file.
# Return the list of strings not found.
def search_file(filename: str, strings: list[str]) -> list[str]:
    logging.debug(f"Search for {strings} in `{filename}'")
    # We use a dict for the strings to preserve the order and be able
    # to remove them like with a set().
    remain = dict.fromkeys(strings)

    with open(filename, 'r') as f:
        for i, line in enumerate(f):
            line = line.rstrip()

            for s in list(remain):
                if s in line:
                    logging.debug(f"""Found "{s}" at line {i + 1}: `{line}'""")
                    del remain[s]

            if len(remain) == 0:
                break

    ret = list(remain.keys())

    if len(ret) > 0:
        logging.debug(f"Did not find {ret}")

    return ret


# Identify all known files, using their paths and details from the db.
# We know how to identify a file with its sha256 sum.
# We know how to identify a file by searching for strings in its contents.
# Return a list of identified files dictionaries:
#   'path': The file path, including dirname.
#   'name': The file identifier.
def identify_files(db: DbType, dirname: str) -> FilesType:
    logging.debug(f"Identify files in `{dirname}/'")
    h_cache: CacheType = {}
    r = []

    for x in db['known-files']:
        filename = f"{dirname}/{x['path']}"

        if not os.path.isfile(filename):
            continue

        if 'sha256' in x:
            if x['sha256'] == hash_file_cached(filename, h_cache):
                logging.debug(f"""Identified `{filename}' as "{x['name']}".""")
                r.append({'path': filename, 'name': x['name']})

        if 'search' in x:
            search = x['search']
            # This does not benefit from caching.
            remain = search_file(filename, search)

            if len(remain) == 0:
                logging.debug(f"""Identified `{filename}' as "{x['name']}".""")
                r.append({'path': filename, 'name': x['name']})

    if len(r) == 0:
        logging.debug('Could not identify any file...')

    return r


# Search for a (sub-)string in a list of strings
# Return True if found or False when not found.
def find_substr(s: str, strings: list[str]) -> bool:
    logging.debug(f"Search for `{s}' in {strings}")

    for x in strings:
        if x.find(s) >= 0:
            logging.debug(f"Found in `{x}'")
            return True

    logging.debug('Not found...')
    return False


# Try to identify the SystemReady version from the list of known files.
# Return None when unknown.
def identify_ver(db: DbType, files: FilesType) -> Optional[str]:
    logging.debug(f"Identify ver from {files}")
    found_names = list(map(lambda f: f['name'], files))

    for x in db['versions']:
        found = True

        for file_name in x['files']:
            # A file name starting with '!' or '~' means that it is an inverted
            # match and we do not want to find the file name anywhere.
            if file_name[0] in ['!', '~']:
                logging.debug(f"`{file_name}' is an inverted match")
                file_name = file_name[1:]
                inv = True
            else:
                inv = False

            fs = find_substr(file_name, found_names)

            if inv and fs or not inv and not fs:
                found = False
                break

        if found:
            logging.debug(f"""Identified as "{x['version']}".""")
            return str(x['version'])

    logging.debug('Could not identify version...')
    return None


if __name__ == '__main__':
    me = os.path.realpath(__file__)
    here = os.path.dirname(me)
    parser = argparse.ArgumentParser(
        description='Identify SystemReady results.',
        epilog='We expect the tree to be layout as described in the '
               'SystemReady IR template '
               '(https://gitlab.arm.com/systemready/systemready-ir-template). '
               'Exit status is 0 if identification succeeded, 1 otherwise.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--bbsr-seq', action='store_true', help='Print the BBSR.seq id')
    parser.add_argument(
        '--sbbr-seq', action='store_true', help='Print the SBBR.seq id')
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        '--dir', help='Specify directory to check', default='.')
    parser.add_argument(
        '--ebbr-seq', action='store_true', help='Print the EBBR.seq id')
    parser.add_argument(
        '--identify-db', help='Identify database YAML file',
        default=f'{here}/identify.yaml')
    parser.add_argument(
        '--known-files', action='store_true',
        help='Print all recognised files')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    db = load_identify_db(args.identify_db)
    files = identify_files(db, args.dir)
    ver = identify_ver(db, files)

    for f in files:
        path = f['path']

        is_ebbr_file = args.ebbr_seq and 'EBBR.seq' in path
        is_bbsr_file = args.bbsr_seq and 'BBSR.seq' in path
        is_sbbr_file = args.sbbr_seq and 'SBBR.seq' in path

        if (args.known_files or is_ebbr_file
           or is_bbsr_file or is_sbbr_file):
            print(f"{path}: {f['name']}")

    if ver is None:
        print('Unknown')
    else:
        print(f"SystemReady {ver}")
