#!/usr/bin/env python3

import argparse
import re
import logging
import os
import sys
from typing import Any, Dict, List
import yaml
import jsonschema
from jsonschema import validate

DbType = Dict[str, Any]
ResType = List[Dict[str, Any]]  # Now each device result is a dictionary

# Load YAML diagnostics database and validate against schema
def load_diagnostics_db(config_filename: str, schema_filename: str) -> DbType:
    logging.debug(f"Loading configuration file `{config_filename}`")
    logging.debug(f"Loading schema file `{schema_filename}`")

    # Check if the schema file exists
    if not os.path.isfile(schema_filename):
        logging.error(f'Schema file `{schema_filename}` does not exist')
        sys.exit(1)

    # Load the schema from the schema file
    with open(schema_filename, 'r') as schemafile:
        try:
            schema = yaml.load(schemafile, Loader=yaml.FullLoader)
        except yaml.YAMLError as err:
            logging.error(f"Error parsing schema file `{schema_filename}`: {err}")
            sys.exit(1)

    # Check if the configuration file exists
    if not os.path.isfile(config_filename):
        logging.error(f'Configuration file `{config_filename}` does not exist')
        sys.exit(1)

    # Load the configuration file
    with open(config_filename, 'r') as yamlfile:
        try:
            db = yaml.load(yamlfile, Loader=yaml.FullLoader)
        except yaml.YAMLError as err:
            logging.error(f"Error parsing configuration file `{config_filename}`: {err}")
            sys.exit(1)

    # Validate the configuration against the schema
    try:
        jsonschema.validate(instance=db, schema=schema)
    except jsonschema.exceptions.ValidationError as err:
        logging.error(f"YAML file validation error: {err.message}")
        sys.exit(1)

    logging.debug(f"YAML contents: {db}")
    return db

# Detect block devices based on the log file
def detect_block_devices(log_path: str) -> int:
    device_pattern = re.compile(r'INFO: Block device : /dev/\w+')
    device_count = 0
    with open(log_path, 'r') as log_file:
        for line in log_file:
            if device_pattern.search(line):
                device_count += 1
    logging.debug(f'Block devices detected: {device_count}')
    return device_count

# Parse the log file to extract diagnostics results
def parse_diagnostics_log(log_path: str, device_results: ResType) -> None:
    partition_pattern = re.compile(r'INFO: Partition table type : GPT|MBR')
    read_pattern_success = re.compile(r'INFO: Block read on /dev/\w+.*successful')
    read_pattern_fail = re.compile(r'INFO: Block read on /dev/\w+.*failed')
    write_pattern_pass = re.compile(r'INFO: write check passed on /dev/\w+')
    write_pattern_fail = re.compile(r'INFO: write check failed on /dev/\w+')
    write_prompt_pattern = re.compile(r'Do you want to perform a write check on /dev/\w+\?')

    current_device_results = {}
    awaiting_write_check = False

    with open(log_path, 'r') as log_file:
        for line in log_file:
            # Detect block device and process results for the previous device
            if re.search(r'INFO: Block device : /dev/\w+', line):
                logging.debug(f"Detected device: {line.strip()}")
                if current_device_results:
                    # Ensure 'read' is only set to 'FAIL' if not explicitly set to 'PASS'
                    if 'read' not in current_device_results:
                        current_device_results['read'] = 'FAIL'
                    if awaiting_write_check:
                        current_device_results['write'] = 'SKIPPED'
                    # Add the results for the previous device
                    device_results.append(current_device_results)
                current_device_results = {}  # Reset for the next device
                awaiting_write_check = False

            # Check partition table
            if partition_pattern.search(line):
                logging.debug(f"Partition table found: {line.strip()}")
                current_device_results['partition_table'] = 'PASS'
            elif re.search(r'INFO: Invalid partition table', line):
                logging.debug(f"Invalid partition table: {line.strip()}")
                current_device_results['partition_table'] = 'FAIL'

            # Check block read success/failure
            if read_pattern_success.search(line):
                logging.debug(f"Block read success: {line.strip()}")
                current_device_results['read'] = 'PASS'  # Correctly set read status to PASS
            elif read_pattern_fail.search(line):
                logging.debug(f"Block read failure: {line.strip()}")
                current_device_results['read'] = 'FAIL'

            # Detect prompt for write check
            if write_prompt_pattern.search(line):
                logging.debug(f"Write check prompt detected: {line.strip()}")
                awaiting_write_check = True

            # Check write check success/failure
            if write_pattern_pass.search(line):
                logging.debug(f"Write check success: {line.strip()}")
                current_device_results['write'] = 'PASS'
                awaiting_write_check = False
            elif write_pattern_fail.search(line):
                logging.debug(f"Write check failure: {line.strip()}")
                current_device_results['write'] = 'FAIL'
                awaiting_write_check = False

        # Handle the last device in the log if not already processed
        if current_device_results:
            if awaiting_write_check:
                current_device_results['write'] = 'SKIPPED'
            if 'read' not in current_device_results:
                current_device_results['read'] = 'FAIL'
            device_results.append(current_device_results)

    logging.debug(f"Parsed device results: {device_results}")

# Apply criteria from the YAML to the parsed log results
def apply_criteria(db: DbType, num_devices: int, device_results: ResType) -> str:
    logging.debug('Applying criterias from the database')
    num_pass_devices = 0
    num_fail_devices = 0

    for ir in device_results:
        if not ir:
            logging.error(f"Skipping incomplete result: {ir}")
            continue

        found_match = False

        # Iterate over the YAML criteria and match results
        for ii in db['criterias']:
            yaml_criteria = ii['results'][0]

            # Check all fields in yaml_criteria against ir (ignore extra fields in ir)
            if all(key in ir and ir[key] == yaml_criteria.get(key) for key in yaml_criteria):
                logging.debug(f"Match found: {ir}")
                ir['result'] = ii['criteria']
                ir['quality'] = ii['quality']
                ir['recommendation'] = ii['recommendation']
                found_match = True

                if ii['criteria'] == 'PASS':
                    num_pass_devices += 1
                else:
                    num_fail_devices += 1

                break  # Stop checking other criteria once a match is found

        if not found_match:
            logging.error(f"No validating match found for: {ir}")

    # Final result: If at least num_devices passed, result is PASS
    if num_pass_devices >= num_devices:
        result = 'PASS'
        if num_pass_devices > num_devices:
            logging.info(f"More devices passed ({num_pass_devices}) than expected ({num_devices}).")
    else:
        result = 'FAIL'

    logging.info(f"Block-device-diagnostics passed for {num_pass_devices} and requested {num_devices}")
    return result

if __name__ == "__main__":
    me = os.path.realpath(__file__)
    here = os.path.dirname(me)

    parser = argparse.ArgumentParser(
        description='Parse Block Device Diagnostics logs.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--config', help='Configuration filename',
        default=f"{here}/boot_sources_result.yaml")
    parser.add_argument(
        '--schema', help='Schema filename',
        default=f"{here}/boot_sources_result_scehma.yaml")
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        'log', help="Input log filename")
    parser.add_argument(
        'num_devices', type=int,
        help='Number of block devices expected to pass')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    db = load_diagnostics_db(args.config, args.schema)
    num_actual_devices = detect_block_devices(args.log)
    num_expected_devices = args.num_devices

    device_results: ResType = []
    parse_diagnostics_log(args.log, device_results)

    result = apply_criteria(db, num_expected_devices, device_results)

    logging.info(f'Block device diagnostics result is: {result}')
    if result == "PASS":
        sys.exit(0)
    else:
        sys.exit(1)
