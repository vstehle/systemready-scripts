#!/usr/bin/env python3

import argparse
import logging
import os
import yaml
import re
import struct
import sys


# Convert GUID string to bytes.
# We use the right binary representation taking care of endianness, even if we
# don't strictly have to today.
# Return None if s is not a valid GUID.
def guid_bytes(s):
    m = re.match(
        r'([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-'
        r'([0-9a-f]{12})$',
        s, re.IGNORECASE)

    if not m:
        logging.debug(f"Invalid GUID {s}")
        return None

    r = bytearray()
    r += struct.pack('<I', int(m[1], base=16))
    r += struct.pack('<H', int(m[2], base=16))
    r += struct.pack('>H', int(m[3], base=16))
    r += struct.pack('<H', int(m[4], base=16))

    for i in range(0, 12, 2):
        r += struct.pack('<B', int(m[5][i:i + 2], base=16))

    return bytes(r)


# Load YAML GUIDs database
# We create guid-bytes entries.
def load_guids_db(filename):
    logging.debug(f"Load `{filename}'")

    with open(filename, 'r') as yamlfile:
        db = yaml.load(yamlfile, Loader=yaml.FullLoader)

    if db is None:
        db = []

    assert 'guid-tool-database' in db
    logging.debug('{} entries'.format(len(db)))

    # Create guid-bytes entries.
    for x in db['known-guids']:
        x['guid-bytes'] = guid_bytes(x['guid'])

    return db


def lookup_guid(guid, db):
    logging.debug(f"Lookup {guid}")
    r = 'Unknown'
    gb = guid_bytes(guid)

    if gb is None:
        logging.error('Invalid')
        sys.exit(1)

    for x in db['known-guids']:
        if x['guid-bytes'] == gb:
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

    db = load_guids_db(args.guids_db)
    lookup_guid(args.guid, db)
