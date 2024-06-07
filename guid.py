#!/usr/bin/env python3

import re
from dataclasses import dataclass
import uuid
import datetime


@dataclass(frozen=True)
class Guid():
    """The Guid class handle UEFI GUIDs.

    We store the GUID internally as bytes.
    We use the right binary representation, taking care of endianness.
    """
    b: bytes

    def __init__(self, x: str | bytes) -> None:
        """Init GUID from string or bytes.

        When given a string, we convert it to our internal bytes format,
        which is taking care of endianness.

        >>> Guid('12345678-1234-4678-9234-56789abcdef0')
        Guid(b=b'xV4\\x124\\x12xF\\x924Vx\\x9a\\xbc\\xde\\xf0')

        When passed bytes we just copy them.

        >>> Guid(b'xV4\\x124\\x12xF\\x924Vx\\x9a\\xbc\\xde\\xf0')
        Guid(b=b'xV4\\x124\\x12xF\\x924Vx\\x9a\\xbc\\xde\\xf0')

        We raise an Exception if given an invalid GUID or an invalid type.

        >>> Guid('Hello')
        Traceback (most recent call last):
            ...
        ValueError: Invalid GUID string Hello

        >>> Guid(b'42')
        Traceback (most recent call last):
            ...
        ValueError: Invalid GUID bytes b'42'

        >>> Guid([1, 2, 3])
        Traceback (most recent call last):
            ...
        TypeError: Invalid [1, 2, 3] of type <class 'list'> for GUID

        >>> Guid('12345678-1234-5678-1234-56789abcdef0') # doctest: +ELLIPSIS
        Traceback (most recent call last):
            ...
        ValueError: GUID 1...0: Bad variant reserved for NCS compatibility

        >>> Guid('00000000-0000-1000-91ec-525400123456') # doctest: +ELLIPSIS
        Traceback (most recent call last):
            ...
        ValueError: GUID 0...6: Time 1582-10-15 00:00:00 is too old

        >>> Guid('ffffffff-ffff-1fff-91ec-525400123456') # doctest: +ELLIPSIS
        Traceback (most recent call last):
            ...
        ValueError: GUID ...: Time 5236-03-31 21:21:00.684704 is in the future

        Guids are frozen, which means assigning to the member `b' directly will
        raise an exception:

        >>> Guid('12345678-1234-4678-9234-56789abcdef0').b = 1234
        Traceback (most recent call last):
            ...
        dataclasses.FrozenInstanceError: cannot assign to field 'b'

        This has the benefit to make Guids hashable and allow to add them to a
        set for example:

        >>> set().add((Guid('12345678-1234-4678-9234-56789abcdef0')))

        Guids can be compared:

        >>> a = Guid('12345678-1234-4678-9234-56789abcdef0')
        >>> b = Guid('22345678-1234-4678-9234-56789abcdef0')
        >>> a == b
        False

        The internal field 'b' cannot be assigned or deleted:

        >>> g = Guid('12345678-1234-4678-9234-56789abcdef0')
        >>> g.b = bytes()
        Traceback (most recent call last):
            ...
        dataclasses.FrozenInstanceError: cannot assign to field 'b'
        >>> del g.b
        Traceback (most recent call last):
            ...
        dataclasses.FrozenInstanceError: cannot delete field 'b'
        """
        if isinstance(x, bytes):
            if len(x) != 16:
                raise ValueError(f"Invalid GUID bytes {x!r}")

            object.__setattr__(self, 'b', x)

        elif isinstance(x, str):
            m = re.match(
                r'([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-'
                r'([0-9a-f]{12})$',
                x, re.IGNORECASE)

            if not m:
                raise ValueError(f"Invalid GUID string {x}")

            r = bytearray()
            r += int(m[1], base=16).to_bytes(4, byteorder='little')
            r += int(m[2], base=16).to_bytes(2, byteorder='little')
            r += int(m[3], base=16).to_bytes(2, byteorder='little')
            r += int(m[4], base=16).to_bytes(2, byteorder='big')
            r += bytes.fromhex(m[5])
            object.__setattr__(self, 'b', bytes(r))

        else:
            raise TypeError(f"Invalid {x} of type {type(x)} for GUID")

        u = self.as_uuid()

        # Verify variant.
        var = u.variant

        if var != uuid.RFC_4122:
            raise ValueError(f"GUID {self}: Bad variant {var}")

        # Verify version.
        ver = u.version

        if ver not in [1, 3, 4, 5]:
            raise ValueError(f"GUID {self}: Bad version {ver}")

        # For version 1, verify that time is valid.
        if u.version == 1:
            dt = self.get_datetime()

            if dt < datetime.datetime(1998, 1, 1):
                raise ValueError(f"GUID {self}: Time {dt} is too old")

            # We add a day of margin to account for timezones.
            if dt > datetime.datetime.now() + datetime.timedelta(days=1):
                raise ValueError(f"GUID {self}: Time {dt} is in the future")

    def __bytes__(self) -> bytes:
        """Return the GUID bytes, which we keep internally.

        >>> bytes(Guid('12345678-1234-4678-9234-56789abcdef0'))
        b'xV4\\x124\\x12xF\\x924Vx\\x9a\\xbc\\xde\\xf0'
        """
        return self.b

    def fields(self) -> tuple[int, int, int, int, int, int]:
        """Convert our GUID bytes to integer fields.

        >>> print(Guid('12345678-1234-4678-9234-56789abcdef0').fields())
        (305419896, 4660, 18040, 146, 52, 95075992133360)
        """
        return (
            int.from_bytes(self.b[0:4], byteorder='little'),
            int.from_bytes(self.b[4:6], byteorder='little'),
            int.from_bytes(self.b[6:8], byteorder='little'),
            self.b[8],
            self.b[9],
            int.from_bytes(self.b[10:16], byteorder='big')
        )

    def __str__(self) -> str:
        """Convert our GUID bytes to string.

        >>> print(Guid('12345678-1234-4678-9234-56789abcdef0'))
        12345678-1234-4678-9234-56789abcdef0

        This works fine now with leading zeroes:

        >>> print(Guid('09D7CF52-0720-4710-91D1-08469B7FE9C8'))
        09d7cf52-0720-4710-91d1-08469b7fe9c8
        """
        f = self.fields()

        return (
            f'{f[0]:08x}-{f[1]:04x}-{f[2]:04x}-'
            f'{f[3]:02x}{f[4]:02x}-{f[5]:012x}')

    def as_uuid(self) -> uuid.UUID:
        """Convert to UUID object.

        >>> print(repr(Guid('12345678-1234-4678-9234-56789abcdef0').as_uuid()))
        UUID('12345678-1234-4678-9234-56789abcdef0')
        """
        return uuid.UUID(fields=self.fields())

    def get_datetime(self) -> datetime.datetime:
        """Get the time in our GUID as a naive datetime object.

        >>> Guid('fb4e8912-6732-11ed-91ec-525400123456').get_datetime()
        datetime.datetime(2022, 11, 18, 11, 20, 18, 60724)

        Retrieving the time of our GUID works only with a time-based
        (i.e. version 1) GUID. For all other versions this raises an
        exception:

        >>> g=Guid('12345678-1234-4678-8234-56789abcdef0')
        >>> g.get_datetime() # doctest: +ELLIPSIS
        Traceback (most recent call last):
            ...
        ValueError: GUID 1...0: Invalid get_datetime with version 4
        """
        u = self.as_uuid()
        ver = u.version

        if ver != 1:
            raise ValueError(
                f"GUID {self}: Invalid get_datetime with version {ver}")

        ns100 = u.time

        return (datetime.datetime(1582, 10, 15)
                + datetime.timedelta(microseconds=ns100 / 10))

    def details(self) -> str:
        """Get details about our GUID as a string.

        >>> print(Guid('12345678-1234-4678-9234-56789abcdef0').details())
        GUID: 12345678-1234-4678-9234-56789abcdef0
          TimeLow: 12345678
          TimeMid: 1234
          TimeHighAndVersion: 4678
            timestamp: 466142576285865592
            version: 4 (randomly generated)
          ClockSeqHighAndReserved: 92
          ClockSeqLow: 34
            clock sequence: 4660
            variant: specified in RFC 4122
          Node: 56789abcdef0
        <BLANKLINE>
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

    def as_c_define(self, define_name: str = 'GUID') -> str:
        """Convert to C define, as found in the UEFI specification.

        >>> g = Guid('12345678-1234-4678-9234-06789abcdef0')
        >>> print(g.as_c_define())
        #define GUID \\
        {0x12345678, 0x1234, 0x4678, \\
        {0x92, 0x34, 0x06, 0x78, 0x9a, 0xbc, 0xde, 0xf0}}

        The define's name can be specified:

        >>> g = Guid('12345678-1234-4678-9234-06789abcdef0')
        >>> print(g.as_c_define('MY_GUID'))
        #define MY_GUID \\
        {0x12345678, 0x1234, 0x4678, \\
        {0x92, 0x34, 0x06, 0x78, 0x9a, 0xbc, 0xde, 0xf0}}
        """
        f = self.fields()
        a = self.b[10]
        b = self.b[11]
        c = self.b[12]
        d = self.b[13]
        e = self.b[14]
        g = self.b[15]

        return (
            f"#define {define_name} \\\n"
            f"{{{f[0]:#010x}, {f[1]:#06x}, {f[2]:#06x}, \\\n"
            f"{{{f[3]:#04x}, {f[4]:#04x}, "
            f"{a:#04x}, {b:#04x}, {c:#04x}, {d:#04x}, {e:#04x}, {g:#04x}}}}}")


if __name__ == '__main__':
    import doctest
    doctest.testmod(verbose=True)
