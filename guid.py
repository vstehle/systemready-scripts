#!/usr/bin/env python3

import logging
import re
from dataclasses import dataclass


@dataclass
class Guid(object):
    """The Guid class handle UEFI GUIDs.

    We store the GUID internally as bytes.
    We use the right binary representation, taking care of endianness.
    """
    b: bytes

    def __init__(self, x):
        """Init GUID from string or bytes.

        When given a string, we convert it to our internal bytes format,
        which is taking care of endianness.

        >>> Guid('12345678-1234-5678-1234-56789abcdef0')
        Guid(b=b'xV4\\x124\\x12xV\\x124Vx\\x9a\\xbc\\xde\\xf0')

        When passed bytes we just copy them.

        >>> Guid(b'xV4\\x124\\x12xV\\x124Vx\\x9a\\xbc\\xde\\xf0')
        Guid(b=b'xV4\\x124\\x12xV\\x124Vx\\x9a\\xbc\\xde\\xf0')

        We raise an Exception if when passed an invalid GUID.

        >>> Guid('Hello')
        Traceback (most recent call last):
            ...
        Exception

        >>> Guid(bytes(123))
        Traceback (most recent call last):
            ...
        Exception
        """

        if isinstance(x, bytes):
            if len(x) != 16:
                logging.debug(f"Invalid GUID bytes {x}")
                raise Exception

            self.b = x

        elif isinstance(x, str):
            m = re.match(
                r'([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-'
                r'([0-9a-f]{12})$',
                x, re.IGNORECASE)

            if not m:
                logging.debug(f"Invalid GUID string {x}")
                raise Exception

            r = bytearray()
            r += int(m[1], base=16).to_bytes(4, byteorder='little')
            r += int(m[2], base=16).to_bytes(2, byteorder='little')
            r += int(m[3], base=16).to_bytes(2, byteorder='little')
            r += int(m[4], base=16).to_bytes(2, byteorder='big')
            r += bytes.fromhex(m[5])
            self.b = bytes(r)

        else:
            logging.debug(f"Invalid GUID type {x}")
            raise Exception

    def __bytes__(self):
        """Return the GUID bytes, which we keep internally.

        >>> bytes(Guid('12345678-1234-5678-1234-56789abcdef0'))
        b'xV4\\x124\\x12xV\\x124Vx\\x9a\\xbc\\xde\\xf0'
        """
        return self.b

    def __str__(self):
        """Convert our GUID bytes to string.

        >>> print(Guid('12345678-1234-5678-1234-56789abcdef0'))
        12345678-1234-5678-1234-56789abcdef0
        """

        TimeLow = int.from_bytes(self.b[0:4], byteorder='little')
        TimeMid = int.from_bytes(self.b[4:6], byteorder='little')
        TimeHighAndVersion = int.from_bytes(self.b[6:8], byteorder='little')
        ClockSeqHighAndReserved = self.b[8:9]
        ClockSeqLow = self.b[9:10]
        Node = self.b[10:16]

        return (
            f'{TimeLow:08x}-{TimeMid:04x}-{TimeHighAndVersion:04x}-'
            f'{ClockSeqHighAndReserved.hex()}{ClockSeqLow.hex()}-{Node.hex()}')


if __name__ == '__main__':
    import doctest
    doctest.testmod(verbose=True)
