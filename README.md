# The SystemReady scripts

A collection of scripts to help with SystemReady compliance.

## Branches

For IR 1.1 certification, git branch `ir1` of this repository should be used.

## Dependencies

The `check-sr-results.py` SystemReady results checker needs the [chardet] and
[requests] python3 modules. On some Linux distros they are available as
`python3-chardet` and `python3-requests`.
The results checker also needs the external programs `tar`, `dtc` and
`dt-validate` (from [dt-schema]) to be installed. It will try to install
`dt-schema` automatically with `pip` when `dt-validate` is not found.

The `capsule-tool.py` script needs the [construct] python3 module, which might
be available on your Linux distro as `python3-construct`.

The `compatibles` script needs `bash`, `find`, `grep`, `xargs`, `sed` and
`sort`.

If you want to generate the pdf version of this documentation, you need to
install [pandoc].

To run the [Sanity checks] you will also need: `yamllint`, `flake8`,
`mkeficapsule` and `openssl`.

[chardet]: https://github.com/chardet/chardet
[construct]: https://construct.readthedocs.io/en/latest/
[pandoc]: https://pandoc.org
[requests]: https://requests.readthedocs.io/en/latest/
[dt-schema]: https://github.com/devicetree-org/dt-schema

# SystemReady results checker

The `check-sr-results.py` script performs a number of verifications in a
SystemReady certification results tree, layout as described in the [SystemReady
IR template].

The `check-sr-results.py` script depends on the `identify.py` script, on the
`guid-tool.py` script to check the GUIDs, on `capsule-tool.py` to verify the
capsule and on `dt-parser.py` to check the Devicetree blob.

[SystemReady IR template]: https://gitlab.arm.com/systemready/systemready-ir-template

## Configuration file

The `check-sr-results.yaml` configuration describes the verifications to
perform. It also contains some data to identify the ACS-IR that was used and to
deduce the certification version.
For IR v1.x results, the `check-sr-results-ir1.yaml` configuration is used.

The `schemas/check-sr-results-schema.yaml` file describes this configuration
file format and can be used with the `validate.py` script to validate the
configuration. This is run during [Sanity checks].

The YAML configuration file starts with:

```{.yaml}
---
check-sr-results-configuration: # Mandatory
```

A section contains data, which allow to determine the ACS-IR version and IR
certification version from the EBBR.seq sequence file hash:

```{.yaml}
ebbr_seq_files:                 # A list of known EBBR.seq sequence files
  - sha256: 6b83dbfb...         # sha256 of the sequence file to recognize
    name: ACS-IR vX             # Corresponding ACS-IR identifier
    version: IR vY              # Corresponding cert version
  - ...
```

The main section describes the file and dirs tree, with checks:

```{.yaml}
tree:
  - file: <filename or pattern>
    optional:                   # If present, the file can be missing
    can-be-emtpy:               # If present, the file can be empty
    must-contain:               # If present, the file contents is checked
      - <string>                # This string must be present in the file
      - ...
    warn-if-contains:           # If present, the file contents is checked
      - <string>                # We warn if this string is present in the file
      - ...
    warn-once-if-contains:      # Similar to warn-if-contains but a warning
      - <string>                # is issued only once
      - ...
    error-if-contains:          # If present, the file contents is checked
      - <string>                # We issue an error if this string is present
      - ...                     # in the file
    capsuleapp-esrt:            # If present, the file is
                                # CapsuleApp_ESRT_table_info.log and we check
                                # its GUIDs
    uefi-capsule:               # If present, the file is a UEFI Capsule and we
                                # verify it with capsule-tool.py
    devicetree:                 # If present, the file is a Devicetree blob and
                                # we verify it with dtc and dt-parser.py
    sct-parser-result-md:       # If present, the file is the result.md produced
      seq-file: <filename>      # by the SCT parser and we treat it specially
                                # (see below)
    warn-if-not-named: <pat>    # If present we issue warnings when the file
                                # name does not match the pattern
    uefi-sniff:                 # If present, the file is a UEFI Shell sniff
                                # test log and we check that we have at least
                                # one ESP
    must-have-esp:              # If present, the file is a log of UEFI commands
                                # and we check that we have at least one ESP.
                                # We must have a file with a uefi-sniff property
				# for this to work

  - dir: <dirname or pattern>
    optional:                   # If present, the directory can be missing
    min-entries: <integer>      # Optional
    max-entries: <integer>      # Optional
    warn-if-not-named: <pat>    # Same as for files
    tree:                       # If present, verification will recurse
      ...
```

Trees can contain files and/or dirs.
Only dirs can contain trees.

When a file has a `must-contain` property, its content is checked to verify that
all entries are present in the file, in order. Files encoded in UTF-16 are
handled correctly automatically.

When a `warn-if-contains` property exists, the first appearance of any of the
strings listed will result in a warning. The `warn-once-if-contains` property
is similar but outputs a warning only once (except when the option `--all` is
used). For an `error-if-contains', this results in an error.

Filenames and dirnames can be UNIX shell glob patterns, in which case their
parent directory is scanned and all matching entries are considered. If the
file or dir entry with the pattern is not marked `optional', there must be at
least one match.

When a file is detected as a tar archive (according to its filename), its
integrity is automatically checked using `tar`.

The overlays section describes trees definitions, which can be overlayed to the
main tree section, depending on the detected ACS-IR version:

```{.yaml}
overlays:
  - when-any: [<condition>, ...]
    tree:                       # If any condition is true, this tree
      ...                       # will be overlayed.

  - when-all: [<condition>, ...]
    tree:                       # If all conditions are true, this tree
      ...                       # will be overlayed.
```

The conditions are strings. A condition is true when its string matches
(partially or in full) with the set of strings (the context) made of:

* The SystemReady version
* The files recognized by `identify.py --known-files`

All keys are overwritten violently except `tree`, which is overlayed
recursively. Also, when a key has the special value `DELETE` the property is
deleted.

### SCT parser result.md

A file marked with the `sct-parser-result-md` property is treated specially:

* If the file is missing we try to re-create it with the SCT parser, using the
  specified sequence file and the `sct_result/Overall/Summary.ekl` file.

### Automatic checks

A number of checks are performed automatically, without being described in the
configuration file:

* Integrity of tar/gzip archives

### Deferred checks

Some checks are postponed until after all files and directories have been
analyzed.

This makes sure that all the necessary data to perform the checks have been
collected and allows to decouple the checks from the order in which files appear
in the configuration file.

## Checking IR 1.x results

By default the `check-sr-results.py` script targets the latest IR version (at
the time of writing: IR 2.0).

The recommended method to verify IR v1.x results is to use branch `ir1` of this
repository.

Nevertheless, a `check-sr-results-ir1.yaml` configuration file is kept here for
convenience. It allows to check IR v1.x results with the latest version of the
script.

# SystemReady results formatter

The `format-sr-results.py` script produces a report from a SystemReady
certification results tree, layout as described in the [SystemReady IR template].

When specifying the `--md` option, a report in markdown format is produced. It
is then possible to convert the report to pdf or HTML format with [pandoc].

When specifying the `--jira` option, a text file suitable for copy-and-paste into a
Jira ticket is produced.

## Configuration file

The `format-sr-results.yaml` configuration describes the report to produce.

YAML file format:

```{.yaml}
---
format-sr-results-configuration:      # Mandatory
subs:
  - heading: <heading name>           # Paragraph's title
    extract:                          # Optional extraction info
      filename: <filename>            # File to extract from
      find: <text>                    # Optional; look for this text in file
      first-line: <n>                 # Extract from this relative line
      last-line: <n or text or None>  # Optional; when to stop extract
    paragraph: <paragraph text>       # Paragraph's contents
    subs:                             # If present, analysis will recurse
      - heading: <sub-heading name>   # This title is one level lower
      ...
  - heading: <heading name>
  ...
```

An `extract` block allows to specify that part of a file needs to be extracted
and output to the report.

When `find` is specified, the file with `filename` is scanned to find the
`find` pattern first. Otherwise the first line of the file is considered as
matching.

The contents of `filename` is then extracted, started from `first-line`. The
`first-line` line number is relative to the matching line (line 0) and can be
negative. If `first-line` is omitted, it defaults to 0, which means "extract
starting from matching line".

* If `last-line` is specified, the extraction stops at this line and it is not
  included in the extracted text. Otherwise extraction continues until the end
  of the file.

* If `last-line` is a number, it is a relative line number similar to
  `first-line`.

* If `last-line` is a text, extraction stops when reaching a line, which matches
  this text.

* If `last-line` is empty, extraction stops when reaching an empty line.

The `schemas/format-sr-results-schema.yaml` file describes this configuration
file format and can be used with the `validate.py` script to validate the
configuration. This is run during [Sanity checks].

## Internal data format

The internal python data format corresponds closely to a flattened view of the
results obtained as per the YAML configuration file:

```{.py}
[
  {'heading': <title>, 'level': <n>},
  {'extract': <text>},
  {'paragraph': <text>},
  ...
]
```

The internal data can be dumped to file with the `--dump` option.

# Capsule tool

The `capsule-tool.py` script allows to perform various operations on UEFI
Capsules:

- Validation
- De-authentication
- Tempering

See the online help for all options and the `tests/test-capsule-tool` unit test
for examples.

The `capsule-tool.py` script depends on the `guid-tool.py` script to check the
capsule GUID. Also, see the [Dependencies].

It is used by `check-sr-results.py`.

## Validating capsules

Validation is done by default on the input capsule:

```{.sh}
$ ./capsule-tool.py capsule.bin
```

The capsule GUID can be verified to match a specific GUID passed with the
`--expected-guid` option.

The `--force` command line option can be used to force processing even in the
case of validation error:

```{.sh}
$ ./capsule-tool.py --force capsule.bin ...
```

## De-authenticating capsules

Capsules can be "de-authenticated" using the `--de-authenticate` command line
option. This will turn off the authentication flag and remove the authentication
information. The modified capsule can be saved using the `--output` option:

```{.sh}
$ ./capsule-tool.py --de-authenticate --output output.bin capsule.bin
```

## Tampering with capsules

Capsules can be "tampered with" using the `--tamper` command line option. This
will invert one bit at random in the firmware image part. The modified capsule
can be saved using the `--output` option:

```{.sh}
$ ./capsule-tool.py --tamper --output output.bin capsule.bin
```

# GUID tool

The `guid-tool.py` script allows to verify if a UEFI GUID is in the database of
known GUIDs.

See the online help for all options and the `tests/test-guid-tool` unit test
for examples.

It is used by `check-sr-results.py` and `capsule-tool.py`.

# Devicetree parser

The `dt-parser.py` script allows to parse the logs of Devicetree related tools.

It is used by `check-sr-results.py`.

Parsing a log file is done with the following command:

```{.sh}
$ ./dt-parser.py input.log
```

See the online help for all options and see the `tests/test-dt-parser` unit test
for more examples.

## Configuration file format

The `dt-parser.yaml` configuration is used by default (this can be changed with
the `--config` option). The configuration file is in [YAML] format. It contains
a list of rules:

``` {.yaml}
- rule: name/description
  criteria:
    key1: value1
    key2: value2
    ...
  update:
    key3: value3
    key4: value4
    ...
- rule...
```

Rules name/description must be unique. There are constraints on the allowed
key/values pairs. See the `schemas/dt-parser-schema.yaml` schema for exact file
format.

[YAML]: https://yaml.org

## Rule processing

The rules from the configuration will be applied to each entry one by one in the
following manner:

* An attempt is made at matching all the keys/values of the rule's 'criteria'
  dict to the keys/values of the entry dict. Matching entry and criteria is done
  with a "relaxed" comparison (more below).
  - If there is no match, processing moves on to the next rule.
  - If there is a match:
    1. The entry dict is updated with the 'update' dict of the rule.
    2. An 'updated_by_rule' key is set in the entry dict to the rule name.
    3. Finally, no more rule is applied to that entry.

An entry value and a criteria value match if the criteria value string is
present anywhere in the entry value string.
For example, the entry value "abcde" matches the criteria value "cd".

You can use `--debug` to see more details about which rules are applied to the
entries.

## Filtering data

The `--filter` option allows to specify a python3 expression, which is used as a
filter. The expression is evaluated for each entry; if it evaluates to True the
entry is kept, otherwise it is omitted. The expression has access to the entry
as dict "x".

Example command, which keeps only the entries with a message containing "failed
to match":

``` {.sh}
$ ./dt-parser.py --filter "'failed to match' in x['warning_message']" ...
```

Filtering takes place after the configuration rules, which are described above,
and before any output. Therefore entries can be filtered before saving to a YAML
file for example:

``` {.sh}
$ ./dt-parser.py --filter "x['type'] != 'ignored'" --yaml out.yaml ...
```

# Identify

The `identify.py` script allows to identify IR results when layout as described
in the [SystemReady IR template].

This script is used by the `check-sr-results.py` script.

See the online help for all options and the `tests/test-identify` unit test for
examples.

## Configuration file

The `identify.yaml` configuration describes how to identify SystemReady versions
from ACS results.

The `known-files` section describes how to identify specific files with their
sha256 sum or by searching for specific strings in their contents.

The `versions` section describes how to deduce the SystemReady version when a
number of specific files are all found.
Each `versions' entry is considered in order.
When all the filenames listed in `files' match with a (substring of) known
files found, the SystemReady version is identified as `version'.
A file name starting with '!' or '~' means that it is an inverted match and it
must not match with any (substring) of the known files found for the version to
be selected.

The `schemas/identify.yaml` file describes this configuration file format and
can be used with the `validate.py` script to validate the configuration. This is
run during [Sanity checks].

# Compatibles

The `compatibles` script allows to extract the list of (potential) compatibles
strings mentioned in Linux bindings.

See the `tests/test-compatible` unit test for examples.

At this point it is not perfect; some compatible strings can be missed and some
others can be reported spuriously, but this is a reasonable approximation
already.

# Miscellaneous

## Documentation

It is possible to convert this `README.md` into `README.pdf` with [pandoc]
using:

```{.sh}
$ make doc
```

See `make help`.

## Sanity checks

To perform some sanity checks in this repository, run:

```{.sh}
$ make check
```

This will run a number of checkers and reports errors. This validates the
configuration files of the [SystemReady results checker] and of the [SystemReady
results formatter] using the `validate.py` script.

See `make help` and [Dependencies].

## Guid class

The `guid.py` script contains the `Guid` class definition. It is used by the
`guid-tool.py` and `capsule-tool.py` scripts.

# License

This work is licensed under the New BSD License (BSD-3-Clause). See the LICENSE
file.
