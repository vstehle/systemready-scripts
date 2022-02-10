# SystemReady scripts

A collection of scripts to help with SystemReady compliance.

## Dependencies

The `check-sr-results.py` SystemReady results checker needs the [chardet]
python3 module. On some Linux distros it is available as `python3-chardet`.
The `tar` program must be installed.

If you want to generate the pdf version of this documentation, you need to
install [pandoc].

[chardet]: https://github.com/chardet/chardet
[pandoc]: https://pandoc.org

## SystemReady results checker

The `check-sr-results.py` script performs a number of verifications in a
SystemReady certification results tree, layout as described in the [SystemReady
template].

[SystemReady template]: https://gitlab.arm.com/systemready/systemready-template

### Configuration file

The `check-sr-results.yaml` configuration describes the verifications to
perform. It also contains some data to identify the ACS-IR that was used and to
deduce the certification version.

YAML file format:

```{.yaml}
---
check-sr-results-configuration: # Mandatory
ebbr_seq_files:			# A list of known EBBR.seq sequence files
  - sha256: 6b83dbfb...		# sha256 of the sequence file to recognize
    name: ACS-IR vX		# Corresponding ACS-IR identifier
    version: IR vY		# Corresponding cert version
  - ...
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
strings listed will result in a warning.

Filenames and dirnames can be UNIX shell glob patterns, in which case their
parent directory is scanned and all matching entries are considered. If the
file or dir entry with the pattern is not marked `optional', there must be at
least one match.

When a file is detected as a tar archive (according to its filename), its
integrity is automatically checked using `tar`.

The `schemas/check-sr-results-schema.yaml` file describes this configuration
file format and can be used with the `validate.py` script to validate the
configuration. This is run during [Sanity checks].

## SystemReady results formatter

The `format-sr-results.py` script produces a report from a SystemReady
certification results tree, layout as described in the [SystemReady template].

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
