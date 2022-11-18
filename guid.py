#!/usr/bin/env python3

import logging
import re
from dataclasses import dataclass
import uuid
import datetime


@dataclass(frozen=True)
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

        We raise an Exception if given an invalid GUID.

        >>> Guid('Hello')
        Traceback (most recent call last):
            ...
        Exception

        >>> Guid(bytes(123))
        Traceback (most recent call last):
            ...
        Exception

        Guids are frozen, which means assigning to the member `b' directly will
        raise an exception:

        >>> Guid('12345678-1234-5678-1234-56789abcdef0').b = 1234
        Traceback (most recent call last):
            ...
        dataclasses.FrozenInstanceError: cannot assign to field 'b'

        This has the benefit to make Guids hashable and allow to add them to a
        set for example:

        >>> set().add((Guid('12345678-1234-5678-1234-56789abcdef0')))
        """

        if isinstance(x, bytes):
            if len(x) != 16:
                logging.debug(f"Invalid GUID bytes {x}")
                raise Exception

            object.__setattr__(self, 'b', x)

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
            object.__setattr__(self, 'b', bytes(r))

        else:
            logging.debug(f"Invalid GUID type {x}")
            raise Exception

    def __bytes__(self):
        """Return the GUID bytes, which we keep internally.

        >>> bytes(Guid('12345678-1234-5678-1234-56789abcdef0'))
        b'xV4\\x124\\x12xV\\x124Vx\\x9a\\xbc\\xde\\xf0'
        """
        return self.b

    def fields(self):
        """Convert our GUID bytes to integer fields.

        >>> print(Guid('12345678-1234-5678-1234-56789abcdef0').fields())
        (305419896, 4660, 22136, 18, 52, 95075992133360)
        """
        return (
            int.from_bytes(self.b[0:4], byteorder='little'),
            int.from_bytes(self.b[4:6], byteorder='little'),
            int.from_bytes(self.b[6:8], byteorder='little'),
            self.b[8],
            self.b[9],
            int.from_bytes(self.b[10:16], byteorder='big')
        )

    def __str__(self):
        """Convert our GUID bytes to string.

        >>> print(Guid('12345678-1234-5678-1234-56789abcdef0'))
        12345678-1234-5678-1234-56789abcdef0
        """
        f = self.fields()

        return (
            f'{f[0]:08x}-{f[1]:04x}-{f[2]:04x}-'
            f'{f[3]:02x}{f[4]:02x}-{f[5]:12x}')

    def as_uuid(self):
        """Convert to UUID object.

        >>> print(repr(Guid('12345678-1234-5678-1234-56789abcdef0').as_uuid()))
        UUID('12345678-1234-5678-1234-56789abcdef0')
        """
        return uuid.UUID(fields=self.fields())

    def get_datetime(self):
        """Get the time in our GUID as a naive datetime object.

        >>> Guid('fb4e8912-6732-11ed-91ec-525400123456').get_datetime()
        datetime.datetime(2022, 11, 18, 11, 20, 18, 60724)
        """
        ns100 = self.as_uuid().time

        return (datetime.datetime(1582, 10, 15)
                + datetime.timedelta(microseconds=(ns100 / 10)))

    def details(self):
        """Get details about our GUID as a string.
        """
        f = self.fields()
        u = self.as_uuid()
        ver = u.version

        vnames = {
            1: 'time-based',
            2: 'DCE security',
            3: 'name-based MD5',
            4: 'randomly generated',
            5: 'name-based SHA-1'
        }

        vname = vnames[ver] if ver in vnames else 'Unknow'

        r = (
            f"GUID: {self}\n"
            f"  TimeLow: {f[0]:x}\n"
            f"  TimeMid: {f[1]:x}\n"
            f"  TimeHighAndVersion: {f[2]:x}\n"
            f"    timestamp: {u.time}\n"
            f"    version: {ver} ({vname})\n")

        if u.version == 1:
            r += f"    datetime: {self.get_datetime()}\n"

        r += (
            f"  ClockSeqHighAndReserved: {f[3]:x}\n"
            f"  ClockSeqLow: {f[4]:x}\n"
            f"    clock sequence: {u.clock_seq}\n"
            f"    variant: {u.variant}\n"
            f"  Node: {f[5]:x}\n")

        if u.version == 1:
            r += f"    multicast/global: {self.b[10] & 1}\n"

        return r


if __name__ == '__main__':
    import doctest
    doctest.testmod(verbose=True)
