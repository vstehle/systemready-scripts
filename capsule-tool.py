#!/usr/bin/env python3

import argparse
import logging
import construct
import sys
import random
import os
import guid
import subprocess


# Define the GUID structure so that it is visually similar to the definitions
# in the UEFI specification.
efi_guid = construct.Struct(
    "TimeLow" / construct.Hex(construct.Int32ul),
    "TimeMid" / construct.Hex(construct.Int16ul),
    "TimeHighAndVersion" / construct.Hex(construct.Int16ul),
    "ClockSeqHighAndReserved" / construct.Hex(construct.Int8ul),
    "ClockSeqLow" / construct.Hex(construct.Int8ul),
    "Node" / construct.Hex(construct.Int8ul)[6]
)

EFI_FIRMWARE_MANAGEMENT_CAPSULE_ID_GUID = efi_guid.build(dict(
    TimeLow=0x6dcbd5ed, TimeMid=0xe82d, TimeHighAndVersion=0x4c44,
    ClockSeqHighAndReserved=0xbd, ClockSeqLow=0xa1,
    Node=[0x71, 0x94, 0x19, 0x9a, 0xd9, 0x2a]))

CAPSULE_FLAGS_PERSIST_ACROSS_RESET = 0x10000
CAPSULE_FLAGS_POPULATE_SYSTEM_TABLE = 0x20000
CAPSULE_FLAGS_INITIATE_RESET = 0x40000

CAPSULE_SUPPORT_AUTHENTICATION = 1
CAPSULE_SUPPORT_DEPENDENCY = 2

WIN_CERT_TYPE_EFI_GUID = 0xEF1

EFI_CERT_TYPE_PKCS7_GUID = efi_guid.build(dict(
    TimeLow=0x4aafd29d, TimeMid=0x68df, TimeHighAndVersion=0x49ee,
    ClockSeqHighAndReserved=0x8a, ClockSeqLow=0xa9,
    Node=[0x34, 0x7d, 0x37, 0x56, 0x65, 0xa7]))

efi_capsule = construct.Struct(
    "CapsuleHeader" / construct.Struct(
        "CapsuleGuid" / efi_guid,
        "HeaderSize" / construct.Int32ul,
        "Flags" / construct.Hex(construct.Int32ul),
        "CapsuleImageSize" / construct.Int32ul
    ),
    "Padding" / construct.Hex(construct.Int8ul)[
        lambda this:
            this.CapsuleHeader.HeaderSize
            - this._subcons.CapsuleHeader.sizeof()
    ],
    "CapsuleBody" / construct.Struct(
        "FirmwareManagementCapsuleHeader" / construct.Struct(
            "Version" / construct.Int32ul,
            "EmbeddedDriverCount" / construct.Int16ul,
            "PayloadItemCount" / construct.Int16ul,
            "ItemOffsetList" / construct.Hex(construct.Int64ul)[
                construct.this.EmbeddedDriverCount
                + construct.this.PayloadItemCount]
        ),
        # Optional Drivers not handled.
        # TODO! Pad
        "Payload1" / construct.Struct(
            "FirmwareManagementCapsuleImageHeader"
            / construct.Struct(
                "Version" / construct.Int32ul,
                "UpdateImageTypeId" / efi_guid,
                "UpdateImageIndex" / construct.Int8ul,
                "reserved_bytes" / construct.Hex(construct.Int8ul)[3],
                "UpdateImageSize" / construct.Int32ul,
                "UpdateVendorCodeSize" / construct.Int32ul,
                "UpdateHardwareInstance" / construct.Int64ul,
                "ImageCapsuleSupport" / construct.Hex(construct.Int64ul)
            ),
            "BinaryUpdateImage" / construct.IfThenElse(
                # If the authentication flag is set...
                construct.this.FirmwareManagementCapsuleImageHeader
                .ImageCapsuleSupport & CAPSULE_SUPPORT_AUTHENTICATION,

                # Then: Authenticated firmware image
                construct.Struct(
                    "FirmwareImageAuthentication" / construct.Struct(
                        "MonotonicCount" / construct.Int64ul,
                        "AuthInfo" / construct.Struct(
                            "Hdr" / construct.Struct(
                                "dwLength" / construct.Int32ul,
                                "wRevision" / construct.Hex(construct.Int16ul),
                                "wCertificateType"
                                / construct.Hex(construct.Int16ul),
                            ),
                            "CertType" / efi_guid,
                            "CertData" / construct.Hex(construct.Int8ul)[
                                lambda this:
                                    this.Hdr.dwLength
                                    - this._subcons.Hdr.sizeof()
                                    - this._subcons.CertType.sizeof()
                            ]
                        )
                    ),
                    "FirmwareImage" / construct.Hex(construct.Int8ul)[
                        lambda this:
                            this._.FirmwareManagementCapsuleImageHeader
                            .UpdateImageSize
                            - this._subcons.FirmwareImageAuthentication
                                .MonotonicCount.sizeof()
                            - this.FirmwareImageAuthentication
                                .AuthInfo.Hdr.dwLength
                    ]
                ),

                # Else: Unauthenticated firmware image
                construct.Struct(
                    "FirmwareImage" / construct.Hex(construct.Int8ul)[
                        construct.this._.FirmwareManagementCapsuleImageHeader
                        .UpdateImageSize
                    ]
                )
            )
            # TODO! Multiple binary update images
            # TODO! Vendor code bytes
        )
        # TODO! Multiple payloads
    ),
    "RemainingBytes" / construct.GreedyBytes
)


# Verify capsule sanity
# We expect an authenticated capsule in FMP format
# Return False at the first error, True otherwise.
# When force, we run all checks to the end and return True in all cases.
def sanity_check_capsule(capsule, force=False):
    r = True

    checks = [
        # Capsule header
        # Capsule Guid
        {
            'check':
                lambda c: efi_guid.build(c.CapsuleHeader.CapsuleGuid)
                == EFI_FIRMWARE_MANAGEMENT_CAPSULE_ID_GUID,
            'error': 'Missing EFI_FIRMWARE_MANAGEMENT_CAPSULE_ID_GUID!',
            'debug': 'Found EFI_FIRMWARE_MANAGEMENT_CAPSULE_ID_GUID'
        },
        # Header Size
        {
            'check': lambda c: c.CapsuleHeader.HeaderSize >= 28,
            'error': 'HeaderSize < 28, too small!',
        },
        # Flags
        {
            'check':
                lambda c: not (
                    c.CapsuleHeader.Flags
                    & ~(CAPSULE_FLAGS_PERSIST_ACROSS_RESET
                        | CAPSULE_FLAGS_POPULATE_SYSTEM_TABLE
                        | CAPSULE_FLAGS_INITIATE_RESET)),
            'error': 'Bad Flags!',
        },
        # Capsule Image Size
        {
            'check': lambda c: c.CapsuleHeader.CapsuleImageSize >= 28,
            'error': 'CapsuleImageSize < 28, too small!',
        },
        # No check for Padding.
        # Capsule body
        # Firmware management capsule header
        # Version
        {
            'check':
                lambda c:
                    c.CapsuleBody.FirmwareManagementCapsuleHeader.Version == 1,
            'error': 'Unknown Version not 1!',
            'debug': 'Found Version 1'
        },
        # Embedded Driver Count
        {
            'check':
                lambda c: not c.CapsuleBody.FirmwareManagementCapsuleHeader
                .EmbeddedDriverCount,
            'error': 'Non-zero EmbeddedDriverCount; not implemented!',
            'debug': 'Zero embedded driver'
        },
        # Payload Item Count
        {
            'check':
                lambda c: c.CapsuleBody.FirmwareManagementCapsuleHeader
                .PayloadItemCount == 1,
            'error': 'Not exactly one payload item; not implemented!',
            'debug': 'Exactly one payload'
        },
        # No check for ItemOffsetList.
        # Payload1
        # Firmware management capsule image header
        # Version
        {
            'check':
                lambda c:
                    c.CapsuleBody.Payload1.FirmwareManagementCapsuleImageHeader
                    .Version == 3,
            'error': 'Unknown Version not 3!',
            'debug': 'Found Version 3'
        },
        # UpdateImageTypeId is checked separately by check_capsule_guid.
        # No check for UpdateImageIndex.
        # reserved_bytes
        {
            'check':
                lambda c: tuple(
                    c.CapsuleBody.Payload1.FirmwareManagementCapsuleImageHeader
                    .reserved_bytes) == (0, 0, 0),
            'error': 'Non-zero reserved_bytes!',
            'debug': 'All-zero reserved_bytes'
        },
        # UpdateImageSize
        {
            'check':
                lambda c:
                    c.CapsuleBody.Payload1.FirmwareManagementCapsuleImageHeader
                    .UpdateImageSize > 32,
            'error': 'Invalid UpdateImageSize!',
        },
        # Update Vendor Code Size
        {
            'check':
                lambda c: not c.CapsuleBody.Payload1
                .FirmwareManagementCapsuleImageHeader.UpdateVendorCodeSize,
            'error': 'Non-zero UpdateVendorCodeSize; not implemented!',
            'debug': 'Zero VendorCode byte'
        },
        # No check for UpdateHardwareInstance.
        # Image Capsule Support
        {
            'check':
                lambda c: not (
                    c.CapsuleBody.Payload1
                    .FirmwareManagementCapsuleImageHeader.ImageCapsuleSupport
                    & ~(CAPSULE_SUPPORT_AUTHENTICATION
                        | CAPSULE_SUPPORT_DEPENDENCY)),
            'error': 'Invalid ImageCapsuleSupport!',
        }, {
            'check':
                lambda c: not (
                    c.CapsuleBody.Payload1
                    .FirmwareManagementCapsuleImageHeader.ImageCapsuleSupport
                    & CAPSULE_SUPPORT_DEPENDENCY),
            'error': 'Dependencies not implemented!',
            'debug': 'No dependency'
        }, {
            'check':
                lambda c:
                    c.CapsuleBody.Payload1
                    .FirmwareManagementCapsuleImageHeader.ImageCapsuleSupport
                    & CAPSULE_SUPPORT_AUTHENTICATION,
            'error': 'Missing authentication flag!',
            'debug': 'Found authentication flag'
        },
        # Binary Update Image
        # Firmware Image Authentication
        # No check for MonotonicCount.
        # Auth Info
        # Hdr
        # dwLength
        {
            'check':
                lambda c:
                    c.CapsuleBody.Payload1.BinaryUpdateImage
                    .FirmwareImageAuthentication.AuthInfo.Hdr
                    .dwLength >= 9,
            'error': 'dwLength < 9, too small!',
        },
        # wRevision
        {
            'check':
                lambda c:
                    c.CapsuleBody.Payload1.BinaryUpdateImage
                    .FirmwareImageAuthentication.AuthInfo.Hdr
                    .wRevision == 0x200,
            'error': 'Unknown wRevision not 0x200!',
            'debug': 'Found wRevision 0x200'
        },
        # wCertificateType
        {
            'check':
                lambda c:
                    c.CapsuleBody.Payload1.BinaryUpdateImage
                    .FirmwareImageAuthentication.AuthInfo.Hdr
                    .wCertificateType == WIN_CERT_TYPE_EFI_GUID,
            'error': 'Missing WIN_CERT_TYPE_EFI_GUID!',
            'debug': 'Found WIN_CERT_TYPE_EFI_GUID'
        },
        # CertType
        {
            'check':
                lambda c: efi_guid.build(
                    c.CapsuleBody.Payload1.BinaryUpdateImage
                    .FirmwareImageAuthentication.AuthInfo
                    .CertType) == EFI_CERT_TYPE_PKCS7_GUID,
            'error': 'Missing EFI_CERT_TYPE_PKCS7_GUID!',
            'debug': 'Found EFI_CERT_TYPE_PKCS7_GUID'
        },
        # No check for CertData.
        # TODO! Check FirmwareImage
        # Remaining Bytes
        {
            'check':
                lambda c: not len(c.RemainingBytes),
            'error': 'Remaining byte(s)!',
            'debug': 'No remaining byte'
        },
    ]

    for x in checks:
        try:
            s = x['check'](capsule)
        except Exception:
            s = False

        if not s:
            logging.error(x['error'])
            r = False
        elif 'debug' in x:
            logging.debug(x['debug'])

        if not r and not force:
            break

    if r:
        logging.info('Valid authenticated capsule in FMP format')
    elif force:
        logging.warning('Invalid capsule but forced to continue anyway')
        r = True

    return r


# Identify and check capsule GUID
# Return True if GUID matches the expected GUID (if not None), False otherwise.
# When force, we return True in all cases.
def check_capsule_guid(capsule, guid_tool, exp_guid, force=False):
    logging.debug(f"Check capsule GUID, expected: `{exp_guid}'")

    fmcih = capsule.CapsuleBody.Payload1.FirmwareManagementCapsuleImageHeader
    g = guid.Guid(efi_guid.build(fmcih.UpdateImageTypeId))

    # Identify
    cmd = [guid_tool, f'{g}']
    logging.debug(f"Run {cmd}")
    o = subprocess.check_output(cmd)
    o = o.decode().rstrip()
    logging.debug(o)

    if o == 'Unknown':
        logging.info(f"Capsule update image type id `{g}' is: {o}")
    else:
        logging.warning(f"Capsule update image type id `{g}' is known: {o}")

    # Verify
    r = True

    if exp_guid is not None:
        e = guid.Guid(exp_guid)

        if g == e:
            logging.info("Capsule GUID is the expected one")
        else:
            logging.error(f"Capsule GUID `{g}' while expecting `{e}'!")
            r = False

    if not r and force:
        logging.warning('Bad capsule GUID but forced to continue anyway')

    return r


# Remove capsule authentication.
# We clear the authentication flag and modify the update image size.
# No need to remove the firmware image authentication.
def de_authenticate(capsule):
    logging.info('De-authenticating capsule')

    # Clear flag.
    p1 = capsule.CapsuleBody.Payload1
    fmcih = p1.FirmwareManagementCapsuleImageHeader
    ics = fmcih.ImageCapsuleSupport
    ics &= ~CAPSULE_SUPPORT_AUTHENTICATION
    fmcih.ImageCapsuleSupport = ics

    # Compute the size of the authentication we will remove
    # FIXME! Use sizeof when it will work
    bui = p1.BinaryUpdateImage
    fiasz = (bui.FirmwareImageAuthentication.AuthInfo.Hdr.dwLength
             + 8)     # MonotonicCount

    # Adjust sizes.
    capsule.CapsuleHeader.CapsuleImageSize -= fiasz
    fmcih.UpdateImageSize -= fiasz

    # Delete firmware image authentication.
    del bui['FirmwareImageAuthentication']


# Tamper with capsule
# We invert one bit in the firmware image.
def tamper(capsule):
    logging.info('Tampering with capsule firmware image')
    fi = capsule.CapsuleBody.Payload1.BinaryUpdateImage.FirmwareImage
    s = len(fi)
    n = random.randint(0, s - 1)
    b = random.randint(0, 7)
    logging.debug(f"Inverting bit {b} of firmware image byte {n} / {s}")
    fi[n] ^= 1 << b
    capsule.CapsuleBody.Payload1.BinaryUpdateImage.FirmwareImage = fi


# Extract the firmware image from a capsule and save it to a file.
def extract_image(capsule, filename):
    logging.info(f"Extracting image to `{filename}'")

    with open(filename, 'wb') as f:
        f.write(bytes(
            capsule.CapsuleBody.Payload1.BinaryUpdateImage.FirmwareImage))


if __name__ == '__main__':
    me = os.path.realpath(__file__)
    here = os.path.dirname(me)
    parser = argparse.ArgumentParser(
        description='Manipulate UEFI Capsules.',
        epilog=(
            'We expect authenticated UEFI Capsules in FMP format as input. '
            'When not forcing processing we exit at the first error.'),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--debug', action='store_true', help='Turn on debug messages')
    parser.add_argument(
        '--dump', action='store_true',
        help='Dump parsed capsule to standard output')
    parser.add_argument(
        '--de-authenticate', action='store_true',
        help='Remove capsule authentication')
    parser.add_argument(
        '--expected-guid', help='Specify expected update image type id GUID')
    parser.add_argument('--extract', help='Extract image to file')
    parser.add_argument(
        '--force', action='store_true', help='Force processing')
    parser.add_argument(
        '--guid-tool', help='Specify guid-tool.py path',
        default=f'{here}/guid-tool.py')
    parser.add_argument('--output', help='Capsule output file')
    parser.add_argument(
        '--tamper', action='store_true',
        help='Tamper with capsule firmware image')
    parser.add_argument('capsule', help='Input capsule filename')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(levelname)s %(funcName)s: %(message)s',
        level=logging.DEBUG if args.debug else logging.INFO)

    logging.debug(f"Parsing `{args.capsule}'")
    capsule = efi_capsule.parse_file(args.capsule)

    if not sanity_check_capsule(capsule, args.force):
        logging.error('Invalid capsule; exiting')
        sys.exit(1)

    if not check_capsule_guid(capsule, args.guid_tool, args.expected_guid,
                              args.force):
        logging.error('Bad capsule GUID; exiting')
        sys.exit(1)

    # Options, which modify the capsule.

    if args.de_authenticate:
        de_authenticate(capsule)

    if args.tamper:
        tamper(capsule)

    # Options, which produce an output.
    # We handle all output after modifications, to be able to dump without
    # saving for example.

    if args.dump:
        logging.debug('Dumping')
        print(capsule)

    if args.extract:
        extract_image(capsule, args.extract)

    if args.output:
        logging.info(f"Saving to `{args.output}'")
        efi_capsule.build_file(capsule, args.output)
