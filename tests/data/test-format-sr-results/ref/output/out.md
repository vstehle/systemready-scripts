# Firmware

TBD

## Setup

TBD

## U-Boot sniff test

TBD

## UEFI sniff test

TBD

### EFI System Partition (ESP)

```
`xxx/tests/data/test-format-sr-results/ref/input/fw/uefi-sniff.log' not found.
```

TBD

# EBBR Compliance

TBD

## SCT

```
|Dropped:|0|
|Failure:|0|
|Ignored:|55|
|Known Acs Limitation:|1|
|Known U-Boot Limitation:|3|
|Pass:|10586|
|Warning:|0|

```

TBD

## FWTS

```
Test Failure Summary
================================================================================

Critical failures: NONE

High failures: NONE

Medium failures: NONE

Low failures: NONE

Other failures: NONE

Test           |Pass |Fail |Abort|Warn |Skip |Info |
---------------+-----+-----+-----+-----+-----+-----+
esrt           |    1|     |     |     |     |     |
uefibootpath   |     |     |     |     |    1|     |
uefirtmisc     |    1|     |     |     |    8|     |
uefirttime     |    4|     |     |     |   35|     |
uefirtvariable |    2|     |     |     |   10|     |
uefivarinfo    |     |     |     |     |    1|     |
---------------+-----+-----+-----+-----+-----+-----+
Total:         |    8|    0|    0|    0|   55|    0|
---------------+-----+-----+-----+-----+-----+-----+

```

TBD

## Capsule update

```
`xxx/tests/data/test-format-sr-results/ref/input/fw/capsule-on-disk.log' not found.
```

TBD

## ESRT

```
EFI_SYSTEM_RESOURCE_TABLE:
FwResourceCount    - 0x1
FwResourceCountMax - 0x1
FwResourceVersion  - 0x1
EFI_SYSTEM_RESOURCE_ENTRY (0):
  FwClass                  - E2BB9C06-70E9-4B14-97A3-5A7913176E3F
  FwType                   - 0x0 (Unknown)
  FwVersion                - 0x0
  LowestSupportedFwVersion - 0x0
  CapsuleFlags             - 0x0
  LastAttemptVersion       - 0x0
  LastAttemptStatus        - 0x0 (Success)

```

TBD

## Devicetree

TBD

### Linux bindings

```
`xxx/tests/data/test-format-sr-results/ref/input/acs_results/uefi/BsaDevTree.dtb.log' not found.
```

TBD

## PSCI

```
`xxx/tests/data/test-format-sr-results/ref/input/acs_results/linux_dump/firmware/devicetree/base/psci/compatible' not found.
```

TBD

# BBSR Compliance

Security Interface Extension (SIE).
TBD


## SIE SCT

```
`xxx/tests/data/test-format-sr-results/ref/input/acs_results/SIE/result.md' not found.
```

TBD

## SIE FWTS

```
`xxx/tests/data/test-format-sr-results/ref/input/acs_results/SIE/fwts/FWTSResults.log' not found.
```

TBD

# BSA Compliance (informative)

TBD

## Bsa.efi (informative)

```
     -------------------------------------------------------
     Total Tests run  =   41  Tests Passed  =   23  Tests Failed =   10
     -------------------------------------------------------

```

TBD

## Linux bsa (informative)

```
`xxx/tests/data/test-format-sr-results/ref/input/acs_results/linux_acs/bsa_acs_app/BsaResultsKernel.log' not found.
```

TBD

# OS Installs

TBD
