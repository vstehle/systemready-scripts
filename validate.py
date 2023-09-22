#!/usr/bin/env python3

import argparse
import sys
import yaml
import jsonschema
import os
import logging
from typing import Any

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

# The folder of the schema.
schema_folder = None


def load_yaml(filename: str) -> Any:
    logging.debug(f"Loading `{filename}'")
    with open(filename, 'r') as f:
        return yaml.load(f, **yaml_load_args)


def handler(uri: str) -> Any:
    f = f"{schema_folder}/{os.path.basename(uri)}"
    logging.debug(f"Resolving URI `{uri}' as `{f}'")
    return load_yaml(f)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Validate a YAML file with a schema.')
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        '--schema', required=True, help='Schema file to use for validation')
    parser.add_argument('yamlfile', help='YAML file to validate')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    schema_folder = os.path.dirname(args.schema)

    # Load YAML file.
    data = load_yaml(args.yamlfile)

    # Load YAML jsonschema.
    schema = load_yaml(args.schema)

    fc = jsonschema.FormatChecker()

    resolver = jsonschema.validators.RefResolver.from_schema(
        schema, handlers={'http': handler, 'https': handler})

    jsonschema.validate(
        instance=data, schema=schema, format_checker=fc, resolver=resolver)
    # If we arrive here, data is valid.
