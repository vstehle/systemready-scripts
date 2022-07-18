#!/usr/bin/env python3

import argparse
import logging
import sys
import yaml
import os
import curses
import pprint

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

# Colors
normal = ''
red = ''
yellow = ''
green = ''

if os.isatty(sys.stdout.fileno()):
    try:
        curses.setupterm()
        setafb = curses.tigetstr('setaf') or bytes()
        setaf = setafb.decode()
        normal = curses.tigetstr('sgr0').decode() or ''
        red = curses.tparm(setafb, curses.COLOR_RED).decode() or ''
        yellow = curses.tparm(setafb, curses.COLOR_YELLOW).decode() or ''
        green = curses.tparm(setafb, curses.COLOR_GREEN).decode() or ''
    except Exception:
        pass


# Load YAML configuration file.
# See the README.md for details on the file format.
def load_config(filename):
    logging.debug(f'Load {filename}')

    with open(filename, 'r') as yamlfile:
        conf = yaml.load(yamlfile, **yaml_load_args)

    assert('format-sr-results-configuration' in conf)
    assert('subs' in conf)
    return conf


# Handle `extract' directive.
# Return: {'extract': <extracted text>}
# 'last-line' is optional
# When it is not present, we extract until the end of the file
# When it is an integer, we extract until this number of line after the found
# line
# When it is a string, we extract until we reach a line matching it
# When it is None, we extract until an emtpy line
def extract(x, dirname):
    filename = f"{dirname}/{x['filename']}"
    logging.debug(f"Extract from `{filename}'")

    # First pass: find pattern.
    found = 0
    pat = x['find']

    with open(filename) as f:
        for i, line in enumerate(f):
            sline = line.rstrip()
            ln = i + 1

            if line.find(pat) >= 0:
                logging.debug(
                    f"{green}Found{normal} `{pat}' at line {ln}, `{sline}'")
                found = ln
                break

    if not found:
        logging.error(f"{red}Could not find{normal} `{pat}' in `{filename}'")
        return {'extract': f"Could not find `{pat}' in `{filename}'"}

    # Second pass: extract.
    res = ''
    ex = False
    first_line = found + int(x['first-line']) if 'first-line' in x else found

    with open(filename) as f:
        for i, line in enumerate(f):
            sline = line.rstrip()
            ln = i + 1

            if 'last-line' in x and ex:
                ll = x['last-line']

                if isinstance(ll, int) and ln > found + int(ll):
                    break
                elif isinstance(ll, str) and line.find(ll) >= 0:
                    logging.debug(
                        f"{green}Found{normal} `{ll}' at line {ln}, `{sline}'")
                    break
                elif ll is None and sline == '':
                    logging.debug(
                        f"{green}Found{normal} empty line {ln}")
                    break

            if ln < first_line:
                continue

            # Extract this line.
            ex = True
            logging.debug(f"Extracting line {ln}, `{sline}'")
            res += line

    return {'extract': res}


# Perform analysis in one "sub".
# A sub is a heading, with an optional extract, an optional paragraph and
# optional subs, for which we recurse analysis.
# We return a list of elements, which can be:
# {'heading': <title>, 'level': <n>},
# {'extract': <text>},
# {'paragraph': <text>},
def analyze_one_sub(e, dirname, level):
    logging.debug(f"{level} {e['heading']}")
    t = [{'heading': e['heading'], 'level': level}]

    if 'extract' in e:
        t.append(extract(e['extract'], dirname))

    if 'paragraph' in e:
        t.append({'paragraph': e['paragraph']})

    if 'subs' in e:
        # Recurse
        t += analyze_subs(e['subs'], dirname, level + 1)

    return t


# Recurse analysis in all the "subs" we have.
def analyze_subs(subs, dirname, level=1):
    logging.debug(f'{len(subs)} sub(s)')
    t = []

    for e in subs:
        t += analyze_one_sub(e, dirname, level)

    return t


# Output results to markdown report.
def output_markdown(results, filename):
    logging.debug(f"Output markdown `{filename}'")

    with open(filename, 'w') as f:
        for i, e in enumerate(results):
            if i:
                print('', file=f)

            if 'heading' in e:
                print(e['level'] * '#' + ' ' + e['heading'], file=f)
            elif 'extract' in e:
                print('```', file=f)
                print(e['extract'], file=f)
                print('```', file=f)
            elif 'paragraph' in e:
                print(e['paragraph'], file=f)
            else:
                raise Exception


# Output results for Jira.
def output_jira(results, filename):
    logging.debug(f"Output Jira-suitable text `{filename}'")

    with open(filename, 'w') as f:
        for e in results:
            if 'heading' in e:
                print(f"h{e['level']}. {e['heading']}", file=f)
                print('', file=f)
            elif 'extract' in e:
                print('{noformat}', file=f)
                print(e['extract'], end='', file=f)
                print('{noformat}', file=f)
            elif 'paragraph' in e:
                print(e['paragraph'], file=f)
            else:
                raise Exception


# Dump results.
def output_dump(results, filename):
    logging.debug(f"Dump to `{filename}'")

    with open(filename, 'w') as f:
        pp = pprint.PrettyPrinter(stream=f)
        pp.pprint(results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Produce a report from a SystemReady results tree.',
        epilog='We expect the tree to be layout as described in the '
               'SystemReady IR template '
               '(https://gitlab.arm.com/systemready/systemready-ir-template).')
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        '--dir', help='Specify directory to analyze', default='.')
    parser.add_argument(
        '--md', help='Specify markdown output filename')
    parser.add_argument(
        '--jira', help='Specify Jira-suitable text output filename')
    parser.add_argument(
        '--dump', help='Specify dump output filename')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    ln = logging.getLevelName(logging.WARNING)
    logging.addLevelName(logging.WARNING, f"{yellow}{ln}{normal}")
    ln = logging.getLevelName(logging.ERROR)
    logging.addLevelName(logging.ERROR, f"{red}{ln}{normal}")

    me = os.path.realpath(__file__)
    here = os.path.dirname(me)
    conf = load_config(f'{here}/format-sr-results.yaml')
    results = analyze_subs(conf['subs'], args.dir)

    if args.md is not None:
        output_markdown(results, args.md)

    if args.jira is not None:
        output_jira(results, args.jira)

    if args.dump is not None:
        output_dump(results, args.dump)
