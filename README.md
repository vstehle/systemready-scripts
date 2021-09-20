# SystemReady scripts

A collection of scripts to help with SystemReady compliance.

## Dependencies

If you want to generate the pdf version of this documentation, you need to
install [pandoc].

[pandoc]: https://pandoc.org

## SystemReady results checker

The `check-sr-results.py` script performs a number of verifications in a
SystemReady certification results tree, layout as described in the [SystemReady
template].

[SystemReady template]: https://gitlab.arm.com/systemready/systemready-template

### Configuration file

The `check-sr-results.yaml` configuration describes the verifications to
perform.

YAML file format:

```{.yaml}
---
check-sr-results-configuration: # Mandatory
tree:
  - file: <filename>
    optional:                   # If present, the file can be missing
    can-be-emtpy:               # If present, the file can be empty
    must-contain:               # If present, the file contents is checked
      - <string>                # This string must be present in the file
      - ...
  - dir: <dirname>
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

This will run a number of checkers and reports errors. See `make help`.
