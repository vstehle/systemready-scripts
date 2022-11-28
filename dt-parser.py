#!/usr/bin/env python3

import argparse
import logging
import os
import re
import pprint
import yaml
import json
import sys


# Load YAML configuration file
def load_config(filename):
    logging.debug(f"Load `{filename}'")

    with open(filename, 'r') as yamlfile:
        conf = yaml.load(yamlfile, Loader=yaml.FullLoader)

    if conf is None:
        conf = []

    logging.debug('{} rules'.format(len(conf)))

    # Verify that rules names are unique.
    s = set()

    for r in conf:
        rule = r['rule']

        if rule in s:
            logging.error(f"Duplicate rule `{rule}'!")
            sys.exit(1)

        s.add(rule)

    return conf


# Cleanup line a bit before adding it to the warning message.
# We remove \t for now.
def clean_line(line):
    return re.sub(r'\t+', ' ', line)


# Parse Devicetree related tools logs.
def parse(filename):
    logging.debug(f"Parse `{filename}'")
    r = []
    dt_val = None

    def flush_dt_val():
        nonlocal dt_val, r
        dt_val['line'] = ''.join(dt_val['dt_validate_lines'])
        r.append(dt_val)
        dt_val = None

    with open(filename) as f:
        for i, line in enumerate(f):
            line = line.rstrip()

            # multi-lines dt-validate warning continuations
            # This must be tried first
            if dt_val is not None:
                #        From schema: /home/vinste01/...
                m = re.match(r'\tFrom schema: (.*)', line)

                if m:
                    logging.debug(
                        f"line {i}: multi-lines dt-validate schema "
                        f"continuation (`{line}')")

                    dt_val['dt_validate_lines'].append(line)
                    assert 'dt_validate_schema' not in dt_val
                    dt_val['dt_validate_schema'] = m[1]
                    continue

                #        'arm,armv8-timer' is not one of [...
                m = re.match(r'\t(.*)', line)

                if m:
                    logging.debug(
                        f"line {i}: multi-lines dt-validate continuation "
                        f"(`{line}')")

                    dt_val['dt_validate_lines'].append(line)
                    dt_val['warning_message'] += clean_line(line)
                    continue

                # If we arrive here it means we were in a dt-validate entry but
                # we are not matching any more: record the entry before
                # continuing to parse.
                flush_dt_val()

            # Ignore shell traces for convenience
            # + ./dt-schema/tools/dt-validate -s linux/...
            m = re.match(r'\+ .*', line)

            if m:
                logging.debug(f"line {i}: shell trace (`{line}')")
                continue

            # dtc warning
            # dump.dts:147.3-28: Warning (clocks_property):
            # /pl011@9040000:clocks: cell 0 is not a phandle reference
            # dump.dts: Warning (avoid_unnecessary_addr_size): /gpio-keys:
            # unnecessary #address-cells/#size-cells without "ranges" or child
            # "reg" property
            m = re.match(
                r'([^:]+):(?:[\d\.]+-[\d\.]+:)? Warning \(([^\)]+)\): '
                r'(.+): (.*)',
                line)

            if m:
                logging.debug(f"line {i}: dtc warning (`{line}')")
                r.append({
                    'devicetree_node': m[3],
                    'dtc_warning_name': m[2],
                    'file': m[1],   # Output file
                    'line': line,
                    'linenum': i + 1,
                    'type': 'dtc warning',
                    'warning_message': m[4]
                })
                continue

            # single-line dt-validate match failure warning
            # qemu.dtb:0:0: /platform@c000000: failed to match any schema with
            # compatible: ['qemu,platform', 'simple-bus']
            m = re.match(r'([^:]+):\d+:\d+: ([^:]+): (.*)', line)

            if m:
                logging.debug(
                    f"line {i}: dt-validate match failure warning (`{line}')")

                r.append({
                    'devicetree_node': m[2],
                    'file': m[1],   # Input file
                    'line': line,
                    'linenum': i + 1,
                    'type': 'dt-validate warning',
                    'warning_message': m[3]
                })
                continue

            # multi-lines dt-validate warning start
            # /home/vinste01/systemreadyir/dt/dump.dtb: pl061@9030000:
            # $nodename:0: 'pl061@9030000' does not match ...
            m = re.match(r'(/[^:]+): ([^:]+): (.*)', line)

            if m:
                logging.debug(
                    f"line {i}: multi-lines dt-validate warning start "
                    f"(`{line}')")

                dt_val = {
                    'devicetree_node': m[2],
                    'dt_validate_lines': [line],
                    'file': m[1],       # Input file
                    'linenum': i + 1,   # First line
                    'type': 'dt-validate warning',
                    'warning_message': m[3]
                }
                continue

            # If we could not parse the line we arrive here and complain.
            logging.warning(f"Unparsed line {i}: `{line}'")

    # Be sure to flush dt_val if we had one in-flight.
    if dt_val is not None:
        flush_dt_val()

    logging.info(f"{len(r)} entries")
    return r


# Evaluate if an entry matches a criteria
# The criteria is a dict of Key-value pairs.
# I.E. crit = {"type": "dt-validate warning", "xxx": "yyy", ...}
# All key-value pairs must be present and match for a test dict to match.
# A test value and a criteria value match if the criteria value string is
# present anywhere in the test value string.
# For example, the test value "abcde" matches the criteria value "cd".
# This allows for more "relaxed" criteria than strict comparison.
def matches_crit(entry, crit):
    for key, value in crit.items():
        if key not in entry or entry[key].find(value) < 0:
            return False

    return True


# Apply all configuration rules to the entries
# We modify parsed in-place
def apply_rules(parsed, conf):
    logging.debug('Apply rules')
    n = 0

    for i, x in enumerate(parsed):
        for j, r in enumerate(conf):
            if not matches_crit(x, r['criteria']):
                continue

            rule = r['rule']

            logging.debug(
                f"Applying rule {j} `{rule}' to entry {i} "
                f"`{x['devicetree_node']}'")

            x.update({
                **r['update'],
                'updated_by_rule': rule,
            })

            n += 1
            break

    logging.info(f"Updated {n} entries with rules")


# Filter entries
# Filter is a python expression, which is evaluated for each entry
# When the expression evaluates to True, the entry is kept
# Otherwise it is dropped
def filter_entries(parsed, Filter):
    logging.debug(f"Filtering with `{Filter}'")
    before = len(parsed)

    # This function "wraps" the filter and is called for each test
    def function(x):
        return eval(Filter)

    r = list(filter(function, parsed))
    after = len(r)
    n = before - after
    logging.info(f"Filtered out {n} entries, kept {after}")
    return r


# Print a table of lines of >=2 columns, with the first column right-justified
# and the right spacing.
def print_table(t, title):
    n = len(t[0]) if len(t) else 0

    # First pass to compute n-1 column sizes.
    s = [0 for i in range(n - 1)]

    for x in t:
        for i in range(n - 1):
            s[i] = max(s[i], len(str(x[i])))

    # Second pass to print.
    print(title)
    print('-' * len(title))

    for x in t:
        p = f'{x[0]:>{s[0]}}'

        for i in range(1, n - 1):
            p += f'  {x[i]:<{s[i]}}'

        print(f'{p}  {x[n - 1]}')


# Compute and print statistics as summary
def print_summary(parsed):
    logging.debug('Summary')
    h = {}

    for x in parsed:
        t = x['type']

        if t not in h:
            h[t] = 0

        h[t] += 1

    t = []

    for k in sorted(h.keys()):
        t.append((h[k], k))

    print('')
    print_table(t, 'Summary')


# Print non-ignored entries
def print_non_ignored(parsed, max_message_len=128):
    logging.debug('Print')
    t = []

    for x in parsed:
        if x['type'] == 'ignored':
            continue

        w = x['warning_message']

        # Limit message width.
        if len(w) > max_message_len:
            w = f"{w[:max_message_len - 3]}..."

        t.append((x['devicetree_node'], x['type'], w))

    print()
    print_table(t, 'Non-ignored entries')


def dump(parsed):
    logging.debug('Dump')
    pp = pprint.PrettyPrinter(indent=2)
    pp.pprint(parsed)


def save_json(parsed, filename):
    logging.debug(f"Save `{filename}'")

    with open(filename, 'w') as jsonfile:
        json.dump(parsed, jsonfile, sort_keys=True, indent=2)


def save_yaml(parsed, filename):
    logging.debug(f"Save `{filename}'")

    with open(filename, 'w') as yamlfile:
        yaml.dump(parsed, yamlfile, Dumper=yaml.CDumper)


if __name__ == '__main__':
    me = os.path.realpath(__file__)
    here = os.path.dirname(me)
    parser = argparse.ArgumentParser(
        description='Parse Devicetree tools logs.',
        epilog="Entries with type `ignored' (after rule processing) "
               "are not printed by option `--print'.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--config', help='Configuration filename',
        default=f"{here}/dt-parser.yaml")
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        '--dump', action='store_true',
        help='Dump parsed information to standard output')
    parser.add_argument('--filter', help='Python expression to filter entries')
    parser.add_argument('--json', help='JSON output filename')
    parser.add_argument(
        '--max-message-len', type=int, help='Maximum message width to print',
        default=128)
    parser.add_argument(
        '--print', action='store_true', help='Print non-ignored entries')
    parser.add_argument('--yaml', help='YAML output filename')
    parser.add_argument('log', help='Input log filename')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    conf = load_config(args.config)
    p = parse(args.log)

    # Modify.

    apply_rules(p, conf)

    if args.filter:
        p = filter_entries(p, args.filter)

    # Output.

    print_summary(p)

    if args.print:
        print_non_ignored(p, args.max_message_len)

    if args.dump:
        dump(p)

    if args.json:
        save_json(p, args.json)

    if args.yaml:
        save_yaml(p, args.yaml)
