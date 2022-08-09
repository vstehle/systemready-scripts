# Simple makefile to perform static checks and generate the documentation with
# pandoc.
.PHONY: all doc help clean check %.run-test

TESTS = $(wildcard tests/test-*)
TEST_TARGETS = $(addsuffix .run-test,$(TESTS))

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

%.run-test: $(basename $@)
	./$(basename $@)

check:	$(TEST_TARGETS)
	yamllint .
	flake8
	./validate.py --schema schemas/check-sr-results-schema.yaml \
		check-sr-results.yaml
	./validate.py --schema schemas/format-sr-results-schema.yaml \
		format-sr-results.yaml
	./validate.py --schema schemas/guid-tool-schema.yaml \
		guid-tool.yaml
	./validate.py --schema schemas/dt-parser-schema.yaml \
		dt-parser.yaml
	./validate.py --schema schemas/dt-parser-schema.yaml \
		tests/data/test-dt-parser/test-config.yaml
	./validate.py --schema schemas/identify-schema.yaml \
		identify.yaml
	python3 -m doctest guid.py

clean:
	-rm -f README.pdf
