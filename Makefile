# Simple makefile to perform static checks and generate the documentation with
# pandoc.
.PHONY: all doc help clean check %.run-test %.valid test valid

TESTS = $(wildcard tests/test-*)
TEST_TARGETS = $(addsuffix .run-test,$(TESTS))
TEST_LOGS = $(addsuffix .log,$(notdir $(TESTS)))

VALIDS = \
	check-sr-results-schema.yaml__check-sr-results-ir1.yaml \
	check-sr-results-schema.yaml__check-sr-results.yaml \
	check-sr-results-schema.yaml__tests/data/test-check-sr-results/once.yaml \
	check-sr-results-schema.yaml__tests/data/test-check-sr-results/warn-if-not-named.yaml \
	check-sr-results-schema.yaml__tests/data/test-check-sr-results/when-all.yaml \
	check-sr-results-schema.yaml__tests/data/test-check-sr-results/when-any.yaml \
	dt-parser-schema.yaml__dt-parser.yaml \
	dt-parser-schema.yaml__tests/data/test-dt-parser/test-config.yaml \
	ethernet-parser-schema.yaml__ethernet-parser.yaml \
	format-sr-results-schema.yaml__format-sr-results.yaml \
	guid-tool-schema.yaml__guid-tool.yaml \
	identify-schema.yaml__identify.yaml \
	identify-schema.yaml__tests/data/test-check-sr-results/identify.yaml

VALID_TARGETS = $(addsuffix .valid,$(VALIDS))

all: doc

help:
	@echo 'Targets:'
	@echo '  all'
	@echo '  check   Perform sanity checks'
	@echo '  clean'
	@echo '  doc     Generate README.pdf'
	@echo '  help    Print this help.'

doc: README.pdf

%.pdf: %.md pandoc.yaml titlesec.tex
	pandoc -o$@ --include-in-header titlesec.tex $< pandoc.yaml

%.run-test:
	./$(basename $@)

test:	$(TEST_TARGETS)

%.valid:
	./validate.py --schema schemas/$(word 1,$(subst __, ,$@)) \
		$(subst .valid,,$(word 2,$(subst __, ,$@)))


valid:	$(VALID_TARGETS)

check:	test valid
	yamllint .
	flake8
	mypy --strict guid.py validate.py logreader.py guid-tool.py \
		identify.py capsule-tool.py format-sr-results.py \
		ethernet-parser.py
	mypy .
	python3 -m doctest guid.py

clean:
	-rm -f README.pdf $(TEST_LOGS)
