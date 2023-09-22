#!/usr/bin/env python3

import logging
from chardet.universaldetector import UniversalDetector
import re
import collections.abc
import sys
from typing import Optional

# Maximum number of lines to examine for file encoding detection.
detect_file_encoding_limit = 999


# Detect file encoding
# We return the encoding or None
def logreader_detect_file_encoding(filename: str) -> Optional[str]:
    logging.debug(f"Detect encoding of `{filename}'")

    detector = UniversalDetector()
    enc = None

    with open(filename, 'rb') as f:
        for i, line in enumerate(f):
            detector.feed(line)

            if detector.done:
                detector.close()
                enc = detector.result['encoding']
                break

            if i > detect_file_encoding_limit:
                logging.debug('Giving up')
                break

    logging.debug(f"Encoding {enc}")
    return enc


# Cleanup a line
# - Right-strip the line
# - Remove the most annoying escape sequences
# Returns the cleaned-up line.
def logreader_cleanup_line(line: str) -> str:
    line = line.rstrip()
    line = re.sub(r'\x1B\[K', '', line)
    line = re.sub(r'\x1B\(B', '', line)
    line = re.sub(r'\x07', '', line)
    line = re.sub(r'\x1B\[[\x30-\x3F]*[\x20-\x2F]*[\x40-\x7E]', '', line)

    while True:
        m = re.search(r'\x08|\r', line)

        if not m:
            break

        if m[0] == '\r':
            line = line[m.start() + 1:]
        elif m[0] == '\x08':
            line = re.sub(r'.?\x08', '', line, count=1)
        else:
            raise

    line = re.sub(r'\x00', ' ', line)
    return line


# An iterator class to easily read from a log in a loop.
# We detect file encoding and cleanup the lines (which includes
# right-stripping).
class LogReader(collections.abc.Iterator[str]):
    def __init__(self, filename: str) -> None:
        logging.debug(f"LogReader `{filename}'")
        enc = logreader_detect_file_encoding(filename)

        # Open the file with the proper encoding
        f = open(filename, encoding=enc, errors='replace', newline='\n')

        self.i = iter(f)

    def __next__(self) -> str:
        # Cleanup each line
        return logreader_cleanup_line(self.i.__next__())


if __name__ == '__main__':
    # This script can be run from command line for testing purposes. It will
    # dump the file contents as seen when going through the LogReader.
    # Usage: logreader.py <logfile>
    if len(sys.argv) == 2:
        for line in LogReader(sys.argv[1]):
            print(line)
