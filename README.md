# SystemReady scripts

A collection of scripts to help with SystemReady compliance.

## Branches

For IR 1.1 certification, git branch `ir1` of this repository should be used.

## Dependencies

The `check-sr-results.py` SystemReady results checker needs the [chardet]
python3 module. On some Linux distros it is available as `python3-chardet`.
The `tar` program must be installed.

The `capsule-tool.py` script needs the [construct] python3 module, which might
be available on your Linux distro as `python3-construct`.

If you want to generate the pdf version of this documentation, you need to
install [pandoc].

[chardet]: https://github.com/chardet/chardet
[construct]: https://construct.readthedocs.io/en/latest/
[pandoc]: https://pandoc.org

## SystemReady results checker

The `check-sr-results.py` script performs a number of verifications in a
SystemReady certification results tree, layout as described in the [SystemReady
IR template].

[SystemReady IR template]: https://gitlab.arm.com/systemready/systemready-ir-template

### Configuration file

The `check-sr-results.yaml` configuration describes the verifications to
perform. It also contains some data to identify the ACS-IR that was used and to
deduce the certification version.

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
    error-if-contains:          # If present, the file contents is checked
      - <string>                # We issue an error if this string is present
      - ...                     # in the file
  - dir: <dirname or pattern>
    optional:                   # If present, the directory can be missing
    can-be-emtpy:               # If present, the directory can be empty
    tree:                       # If present, verification will recurse
      ...
```

Trees can contain files and/or dirs.
Only dirs can contain trees.

When a file has a `must-contain` property, its content is checked to verify that
all entries are present in the file, in order. Files encoded in UTF-16 are
handled correctly automatically.

When a `warn-if-contains` property exists, the first appearance of any of the
strings listed will result in a warning. For an `error-if-contains', this
results in an error.

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
  - ebbr_seq_files: [<seq file id>, ...]
    tree:                       # If the detected seq file id matches, this tree
      ...                       # will be overlayed.
```

All keys are overwritten violently except `tree`, which is overlayed
recursively.

## SystemReady results formatter

The `format-sr-results.py` script produces a report from a SystemReady
certification results tree, layout as described in the [SystemReady IR template].

When specifying the `--md` option, a report in markdown format is produced. It
is then possible to convert the report to pdf or HTML format with [pandoc].

When specifying the `--jira` option, a text file suitable for copy-and-paste into a
Jira ticket is produced.

### Configuration file

The `format-sr-results.yaml` configuration describes the report to produce.

YAML file format:

```{.yaml}
---
format-sr-results-configuration: # Mandatory
subs:
  - heading: <heading name>           # Paragraph's title
    extract:                          # Optional extraction info
      filename: <filename>            # File to extract from
      find: <text>                    # Look for this text in file
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

The file with `filename` is scanned to find the `find` pattern first.

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

### Internal data format

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

## Capsule tool

The `capsule-tool.py` script allows to perform various operations on UEFI
Capsules:

- Validation
- De-authentication
- Tempering

See the online help for all options and the `tests/test-capsule-tool` unit test
for examples.

The `capsule-tool.py` script depends on the `guid-tool.py` script to check the
capsule GUID. Also, see the [Dependencies].

### Validating capsules

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

### De-authenticating capsules

Capsules can be "de-authenticated" using the `--de-authenticate` command line
option. This will turn off the authentication flag and remove the authentication
information. The modified capsule can be saved using the `--output` option:

```{.sh}
$ ./capsule-tool.py --de-authenticate --output output.bin capsule.bin
```

### Tampering with capsules

Capsules can be "tampered with" using the `--tamper` command line option. This
will invert one bit at random in the firmware image part. The modified capsule
can be saved using the `--output` option:

```{.sh}
$ ./capsule-tool.py --tamper --output output.bin capsule.bin
```

## GUID tool

The `guid-tool.py` script allows to verify if a UEFI GUID is in the database of
known GUIDs.

See the online help for all options and the `tests/test-guid-tool` unit test
for examples.

## Devicetree parser

The `dt-parser.py` script allows to parse the logs of Devicetree related tools.

Parsing a log file is done with the following command:

```{.sh}
$ ./dt-parser.py input.log
```

See the online help for all options and see the `tests/test-dt-parser` unit test
for more examples.

### Configuration file format

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

### Rule processing

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

### Filtering data

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

## Identify

The `identify.py` script allows to identify IR results when layout as described
in the [SystemReady IR template].

See the online help for all options and the `tests/test-identify` unit test for
examples.

## Miscellaneous

### Documentation

It is possible to convert this `README.md` into `README.pdf` with [pandoc]
using:

```{.sh}
$ make doc
```

See `make help`.

### Sanity checks

To perform some sanity checks in this repository, run:

```{.sh}
$ make check
```

This will run a number of checkers and reports errors. This validates the
configuration files of the [SystemReady results checker] and of the [SystemReady
results formatter] using the `validate.py` script.

See `make help`.

## License

This work is licensed under the New BSD License (BSD-3-Clause). See the LICENSE
file.
