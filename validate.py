#!/usr/bin/env python3

import argparse
import sys
import yaml
import jsonschema

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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Validate a YAML file with a schema.')
    parser.add_argument(
        '--schema', required=True, help='Schema file to use for validation')
    parser.add_argument('yamlfile', help='YAML file to validate')
    args = parser.parse_args()

    # Load YAML file.
    with open(args.yamlfile, 'r') as f:
        data = yaml.load(f, **yaml_load_args)

    # Load YAML jsonschema.
    with open(args.schema, 'r') as f:
        schema = yaml.load(f, **yaml_load_args)

    fc = jsonschema.FormatChecker()
    jsonschema.validate(instance=data, schema=schema, format_checker=fc)
    # If we arrive here, data is valid.
