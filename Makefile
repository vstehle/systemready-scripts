# Simple makefile to perform static checks and generate the documentation with
# pandoc.
.PHONY: all doc help clean check

all: doc

help:
	@echo 'Targets:'
	@echo '  all'
	@echo '  check   Perform sanity checks'
	@echo '  clean'
	@echo '  doc     Generate README.pdf'
	@echo '  help    Print this help.'

doc: README.pdf

%.pdf: %.md pandoc.yaml
	pandoc -o$@ $< pandoc.yaml

check:
	yamllint .
	flake8

clean:
	-rm -f README.pdf
