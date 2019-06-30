PYTHON_SOURCES = genconf

.PHONY: all
all: typecheck pep8

.PHONY: typecheck
typecheck: $(PYTHON_SOURCES)
	mypy $^

.PHONY: pep8
pep8: $(PYTHON_SOURCES)
	pycodestyle $^
