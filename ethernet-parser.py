#!/usr/bin/env python3

import argparse
import re
import logging
import os
import sys
from typing import Any, Optional, cast
import yaml

DbType = dict[str, Any]
ResType = list[list[dict[str, Any]]]


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
        db = {'ethernet_parser-database': None}

    assert 'ethernet_parser-database' in db
    return db


def detect_eth_devices(log_path: str) -> int:
    ethtool_pattern = re.compile(r'INFO: Running "ethtool ')
    device_count = 0
    with open(log_path, 'r') as log_file:
        for line in log_file:
            match_device = ethtool_pattern.search(line)
            if match_device:
                logging.debug(f"Got `{line.rstrip()}'")
                device_count += 1
    logging.debug(f' ethernet devices detected: {device_count}')
    return device_count


def parse_eth_log(log_path: str, device_results: ResType) -> None:
    ethtool_pattern = re.compile(r'The test result is (PASS|FAIL)')
    unsup_pattern = re.compile(r" doesn't supports ethtool self test")
    ping_pattern = re.compile(r'Ping to www.arm.com is (successful|.*)')
    link_pattern = re.compile(r'INFO: Link not detected')

    device_count = 0
    lookforping = False

    with open(log_path, 'r') as log_file:
        for line in log_file:
            if lookforping is False:
                match_ethtool = ethtool_pattern.search(line)
                match_unsup = unsup_pattern.search(line)
                if match_ethtool:
                    logging.debug(f"Got `{line.rstrip()}'")
                    device_count += 1
                    result = match_ethtool.group(1)
                    device_results[device_count-1].append({'ethtool': result})
                    if result == 'PASS':
                        logging.debug(f" Ethtool: device {device_count},"
                                      f" PASSED")
                    elif result == 'FAIL':
                        logging.debug(f" Ethtool: device {device_count}, "
                                      f" FAILED")
                    lookforping = True
                elif match_unsup:
                    logging.debug(f"Got `{line.rstrip()}'")
                    device_count += 1
                    logging.debug(
                        f" Ethtool: device {device_count}, "
                        "selftest unsupported")
                    device_results[device_count-1].append(
                        {'ethtool': 'FAIL'})
                    lookforping = True

            if lookforping is True:
                match_no_link = link_pattern.search(line)
                match_ping = ping_pattern.search(line)
                if match_no_link:
                    logging.debug(f"Got `{line.rstrip()}'")
                    logging.debug(f" Ping: device {device_count}, FAILED")
                    device_results[device_count-1].append({'ping': 'FAIL'})
                    lookforping = False
                elif match_ping:
                    logging.debug(f"Got `{line.rstrip()}'")
                    result = match_ping.group(1)
                    lookforping = False
                    if result == 'successful':
                        logging.debug(f" Ping: device {device_count}, PASSED")
                        device_results[device_count-1].append({'ping': 'PASS'})
                    elif result != 'successful':
                        logging.debug(f" Ping: device {device_count}, FAILED")
                        device_results[device_count-1].append({'ping': 'FAIL'})


def apply_criteria(
        db: DbType, num_devices: int, device_results: ResType) -> str:

    logging.debug('apply criterias from the database')
    result = 'PASS'
    num_pass_devices = 0
    # look for the different combinations PASS/FAIL
    # and update the device register with the criteria
    # and recommendations from the database
    for dr in device_results:
        found_match = False

        for ii in db['criterias']:
            if dr == ii['results']:
                logging.debug(f"match found: {dr}")
                dr.append({'result': ii['criteria']})
                dr.append({'quality': ii['quality']})
                dr.append({'recommendation': ii['recommendation']})
                found_match = True
                # don't care what other devices are. the end result is FAIL
                if result == 'FAIL':
                    result = 'FAIL'
                # if new device result is BAD,
                # the end result gets downgraded to overall
                elif ii['quality'] == 'BAD':
                    result = 'FAIL'
                elif (result == 'PASS' and (ii['quality'] == 'POOR' or
                                            ii['quality'] == 'BEST')):
                    result = 'PASS'
                    num_pass_devices += 1
                break

        if not found_match:
            logging.error(f"not validating match found for: {dr}")

    if num_pass_devices == num_devices:
        logging.info(f"ethernet-parser passed for "
                     f"{num_pass_devices} and requested {num_devices}")
        return "PASS"

    logging.error(f"ethernet-parser passed for "
                  f"{num_pass_devices} and requested {num_devices}")
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
        'num_devices', type=int,
        help='Number of Ethernet devices to be parsed')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    db = load_ethernet_db(args.config)
    num_actual_devices = detect_eth_devices(args.log)
    num_expected_devices = args.num_devices

    device_results: ResType = [[] for _ in
                               range(num_actual_devices)]
    if num_expected_devices > num_actual_devices:
        logging.error(f'detected {num_actual_devices} '
                      f'and expected a bigger number of ethernets: '
                      f'{num_expected_devices}')
        result = 'FAIL'
    else:
        parse_eth_log(args.log, device_results)
        result = apply_criteria(db, args.num_devices, device_results)

    logging.info(f'Ethernet parser tests result is: {result}')
    if result == "PASS":
        sys.exit(0)
    else:
        sys.exit(1)
