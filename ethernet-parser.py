#!/usr/bin/env python3

import argparse
import re
import logging
import os
import yaml
import sys
from typing import List, Any, Optional, cast


# Colors
normal = ''
red = ''
yellow = ''
green = ''

DbType = dict[str, Any]


# Load YAML ethernet_checks database
def load_ethernet_db(filename: str) -> DbType:
    logging.debug(f"Load `{filename}'")

    if os.path.isfile(filename):
        with open(filename, 'r') as yamlfile:
            y = yaml.load(yamlfile, Loader=yaml.FullLoader)
            db = cast(Optional[DbType], y)
    else:
        logging.error(f'filename {filename} does not exist')

    if db is None:
        db = {}

    return db


def detect_eth_devices(log_path: str) -> int:
    ethtool_pattern = re.compile(r'INFO: Running "ethtool ')
    device_count = 0
    with open(log_path, 'r') as log_file:
        for line in log_file:
            match_device = ethtool_pattern.search(line)
            if match_device:
                device_count += 1
    logging.debug(f' ethernet devices detected: {device_count}')
    return device_count


def parse_eth_log(db: DbType, log_path: str, num_devices: int) -> None:
    ethtool_pattern = re.compile(r'The test result is (PASS|FAIL)')
    ping_pattern = re.compile(r'Ping to www.arm.com is (successful|.*)')
    link_pattern = re.compile(r'INFO: Link not detected')

    device_count = 0
    ethtool_pattern_count = 0
    ping_pattern_count = 0
    expectping = True
    lookforping = False

    with open(log_path, 'r') as log_file:
        for line in log_file:
            match_ethtool = ethtool_pattern.search(line)
            match_ping = ping_pattern.search(line)
            match_no_link = link_pattern.search(line)
            if lookforping is False:
                if match_ethtool:
                    device_count += 1
                    result = match_ethtool.group(1)
                    device_results[device_count-1].append({'ethtool': result})
                    if result == 'PASS':
                        logging.debug(f" Ethtool: device {device_count},"
                                      f" PASSED")
                        ethtool_pattern_count += 1
                        lookforping = True | expectping
                    elif result == 'FAIL':
                        logging.debug(f" Ethtool: device {device_count}, "
                                      f" FAILED")
                        lookforping = False | expectping

            if lookforping is True:
                if match_no_link:
                    logging.debug(f" Ping: device {device_count}, FAILED")
                    device_results[device_count-1].append({'ping': 'FAIL'})
                    lookforping = False
                elif match_ping:
                    result = match_ping.group(1)
                    lookforping = False
                    if result == 'successful':
                        logging.debug(f" Ping: device {device_count}, PASSED")
                        device_results[device_count-1].append({'ping': 'PASS'})
                        ping_pattern_count += 1
                    elif result != 'successful':
                        logging.debug(f" Ping: device {device_count}, FAILED")
                        device_results[device_count-1].append({'ping': 'FAIL'})


def apply_criteria(db: DbType) -> str:
    logging.debug('apply criterias from the database')
    result = 'PASS'
    num_pass_devices = 0
    # look for the different combinations PASS/FAIL
    # and update the device register with the criteria
    # and recommendations from the database
    for index, i in enumerate(device_results):
        found_match = False

        for ii in db['criterias']:
            if i == ii['results']:
                logging.debug(f"match found: {i}")
                device_results[index].append({'result': ii['criteria']})
                device_results[index].append({'quality': ii['quality']})
                device_results[index].append({'recommendation':
                                              ii['recommendation']})
                found_match = True
                # don't care what other devices are. the end result is FAIL
                if result == 'FAIL':
                    result = 'FAIL'
                # if new device result is BAD,
                # the end result gets downgraded to overall
                elif (ii['quality'] == 'BAD'):
                    result = 'FAIL'
                elif (result == 'PASS' and (ii['quality'] == 'POOR' or
                                            ii['quality'] == 'BEST')):
                    result = 'PASS'
                    num_pass_devices += 1
                break

        if not found_match:
            logging.error(f"not validating match found for: {i}")

    if num_pass_devices == int(args.num_devices):
        logging.info("ethernet-parser passed for",
                     f"{num_pass_devices} and requested {args.num_devices}")
        return "PASS"
    else:
        logging.error("ethernet-parser passed for",
                      f"{num_pass_devices} and requested {args.num_devices}")
        return "FAIL"


if __name__ == "__main__":

    me = os.path.realpath(__file__)
    here = os.path.dirname(me)

    parser = argparse.ArgumentParser(
        description='Parse Ethernet tools logs.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--config', help='Configuration filename',
        default=f"{here}/ethernet-parser.yaml")
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        'log', help="Input log filename")
    parser.add_argument(
        'num_devices', help='Number of Ethernet devices to be parsed')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    db = load_ethernet_db(args.config)
    num_actual_devices = detect_eth_devices(args.log)
    num_expected_devices = int(args.num_devices)

    device_results: List[List[Any]] = [[] for _ in
                                       range(num_actual_devices)]
    if num_expected_devices > num_actual_devices:
        logging.error(f'detected {num_actual_devices} ',
                      'and expected a bigger number of ethernets:',
                      f'{num_expected_devices}')
    else:
        parse_eth_log(db, args.log, num_actual_devices)
        result = apply_criteria(db)

    logging.info(f'Ethernet parser tests result is: {result}')
    if result == "PASS":
        sys.exit(0)
    else:
        sys.exit(1)
