#!/usr/bin/env python3

import argparse
import logging
import os
import yaml
import hashlib
import sys


# Validate YAML identify database
# We check our magic marker.
def validate_identify_db(db):
    logging.debug("Validate identify db")
    assert 'identify-database' in db


# Load YAML identify database
def load_identify_db(filename):
    logging.debug(f"Load `{filename}'")

    with open(filename, 'r') as yamlfile:
        db = yaml.load(yamlfile, Loader=yaml.FullLoader)

    if db is None:
        db = []

    validate_identify_db(db)
    logging.debug('{} entries'.format(len(db)))
    return db


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


# Compute the sha256 of a file, with caching.
# cache must be initialized as an empty dict.
def hash_file_cached(filename, cache):
    logging.debug(f"Hash/cache `{filename}'")

    if filename in cache:
        logging.debug('Cache hit')
        h = cache[filename]
    else:
        logging.debug('Cache miss')
        h = hash_file(filename)
        cache[filename] = h

    return h


# Identify all known files, using their paths and details from the db.
# We know how to identify a file with its sha256 sum.
# Return a list of identified files dictionaries:
#   'path': The file path, including dirname.
#   'name': The file identifier.
def identify_files(db, dirname):
    logging.debug(f"Identify files in `{dirname}/'")
    h_cache = {}
    r = []

    for x in db['known-files']:
        filename = f"{dirname}/{x['path']}"

        if not os.path.isfile(filename):
            continue

        if 'sha256' in x:
            if x['sha256'] == hash_file_cached(filename, h_cache):
                logging.debug(f"""Identified `{filename}' as "{x['name']}".""")
                r.append({'path': filename, 'name': x['name']})

    if not len(r):
        logging.debug('Could not identify any file...')

    return r


# Try to identify the SystemReady version from the list of known files.
# Return None when unknown.
def identify_ver(db, files):
    logging.debug(f"Identify ver from {files}")
    found_names = set()

    for f in files:
        found_names.add(f['name'])

    for x in db['versions']:
        found = True

        for file_name in x['files']:
            if file_name not in found_names:
                found = False
                break

        if found:
            logging.debug(f"""Identified as "{x['version']}".""")
            return x['version']

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

        if args.known_files or args.ebbr_seq and 'EBBR.seq' in path:
            print(f"{path}: {f['name']}")

    if ver is None:
        logging.error('Unknown')
        sys.exit(1)

    print(f"SystemReady {ver}")
