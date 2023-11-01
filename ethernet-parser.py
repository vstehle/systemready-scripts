#!/usr/bin/env python3


import re
import sys
import logging
import os
import yaml
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


def parse_eth_log(db: DbType, log_path, num_devices, debug):
    ethtool_pattern = re.compile(r'The test result is (PASS|FAIL)')
    ping_pattern = re.compile(r'Ping to www.arm.com is (successful|failed)')

    device_count = 0
    ethtool_pattern_count = 0
    ping_pattern_count = 0
    expectping = True
    lookforping = False

    with open(log_path, 'r') as log_file:
        for line in log_file:
            if lookforping is False:
                match = ethtool_pattern.search(line)
                if match:
                    device_count += 1
                    result = match.group(1)
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

            # if ethtool fails there won't be a ping ?????
            if lookforping is True:
                match = ping_pattern.search(line)
                if match:
                    result = match.group(1)
                    lookforping = False
                    if result == 'successful':
                        logging.debug(f" Ping: device {device_count}, PASSED")
                        device_results[device_count-1].append({'ping': 'PASS'})
                        ping_pattern_count += 1
                    elif result == 'failed':
                        logging.debug(f" Ping: device {device_count}, FAILED")
                        device_results[device_count-1].append({'ping': 'FAIL'})
            else:
                match = ethtool_pattern.search(line)


def apply_criteria(db: DbType):
    logging.debug('apply criterias from the database')
    result = 'PASS'
    # look for the different combinations PASS/FAIL
    # and update the device register with the criteria
    # and recomendations from the database
    for index, i in enumerate(device_results):
        found_match = False

        for ii in db['criterias']:
            if i == ii['results']:
                logging.debug(f"match found: {i}")
                device_results[index].append({'result': ii['criteria']})
                device_results[index].append({'quality': ii['quality']})
                device_results[index].append({'recomendation':
                                              ii['recomendation']})
                found_match = True
                # don't care what other devices are. the end result is FAIL
                if result == 'FAIL':
                    result = 'FAIL'
                # if new device result is BAD,
                # the end result gets downgraded to overall
                elif (ii['quality'] == 'BAD'):
                    result = 'FAIL'
                elif (result == 'PASS' and (ii['quality'] == 'POOR' or
                                            ii['quality'] == 'GOOD')):
                    result = 'PASS'
                break

        if not found_match:
            logging.error(f"not validating match found for: {i}")

    return result


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python script.py <log_path> <num_devices> <debug>")
        sys.exit(1)

    me = os.path.realpath(__file__)
    here = os.path.dirname(me)

    log_path = sys.argv[1]
    num_devices = int(sys.argv[2])
    debug = int(sys.argv[3])
    device_results: List[List[List]] = [[] for _ in range(num_devices)]

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if debug else logging.INFO)

    db = load_ethernet_db(f'{here}/ethernet-parser.yaml')
    parse_eth_log(db, log_path, num_devices, debug)
    result = apply_criteria(db)

    for i in range(num_devices):
        logging.info(f"{device_results[i]}")

    print(f'Ethernet parser tests result is: {result}')
