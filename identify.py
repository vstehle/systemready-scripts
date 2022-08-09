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


# Try to identify the EBBR.seq file using its sha256 in a list of known
# versions in db.
# Return the identifier and SystemReady version or None, None.
def identify_ebbr_seq(db, dirname):
    logging.debug(f"Identify EBBR.seq in `{dirname}/'")
    ebbr_seq = f"{dirname}/acs_results/sct_results/Sequence/EBBR.seq"

    if not os.path.isfile(ebbr_seq):
        logging.warning(
            f"Missing `{ebbr_seq}' sequence file...")
        return None, None

    h = hash_file(ebbr_seq)

    # Try to identify the seq file
    for x in db['ebbr_seq_files']:
        if x['sha256'] == h:
            logging.debug(
                f"""Identified `{ebbr_seq}'"""
                f""" as "{x['name']}" (SystemReady {x['version']}).""")
            return x['name'], x['version']

    logging.debug(f"Could not identify `{ebbr_seq}'...")
    return None, None


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
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    db = load_identify_db(args.identify_db)
    seq_id, ver = identify_ebbr_seq(db, args.dir)

    if ver is None:
        logging.error('Unknown')
        sys.exit(1)

    if args.ebbr_seq:
        print(f"EBBR.seq from {seq_id}")

    print(f"SystemReady {ver}")
