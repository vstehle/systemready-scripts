#!/usr/bin/env python3

import argparse
import logging
import os
import yaml
import sys
import guid


# Validate YAML GUIDs database
# We check our magic marker and also for duplicate descriptions.
def validate_guids_db(db):
    logging.debug("Validate db")

    assert 'guid-tool-database' in db

    h = {}

    for x in db['known-guids']:
        d = x['description']
        g = x['guid']

        if d in h:
            logging.error(
                f"Duplicate description `{d}' for guid `{g}', "
                f"already used for guid `{h[d]}'")
            raise Exception

        h[d] = g


# Load YAML GUIDs database
# We create _Guid entries holding Guid objects.
def load_guids_db(filename):
    logging.debug(f"Load `{filename}'")

    with open(filename, 'r') as yamlfile:
        db = yaml.load(yamlfile, Loader=yaml.FullLoader)

    if db is None:
        db = []

    validate_guids_db(db)
    logging.debug('{} entries'.format(len(db)))

    # Create _Guid entries holding Guid objects.
    for x in db['known-guids']:
        x['_Guid'] = guid.Guid(x['guid'])

    return db


# Find and print the description corresponding to a Guid object
# in our database.
# Print 'Unknown' if not found.
def lookup_guid(g, db):
    logging.debug(f"Lookup {g}")
    r = 'Unknown'

    for x in db['known-guids']:
        if x['_Guid'] == g:
            r = x['description']
            break

    print(r)


if __name__ == '__main__':
    me = os.path.realpath(__file__)
    here = os.path.dirname(me)
    parser = argparse.ArgumentParser(
        description='Check UEFI GUIDs.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        '--guids-db', help='GUIDs database YAML file',
        default=f'{here}/guid-tool.yaml')
    parser.add_argument('guid', help='Input GUID')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    try:
        g = guid.Guid(args.guid)
    except Exception as e:
        logging.debug(f"(Exception `{e}')")
        logging.error(f"Invalid GUID `{args.guid}'!")
        sys.exit(1)

    db = load_guids_db(args.guids_db)
    lookup_guid(g, db)
