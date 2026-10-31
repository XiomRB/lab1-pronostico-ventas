PYTHON ?= python3.12
VENV := .venv
CONSTRAINTS := https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt

.PHONY: instalar test

instalar:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install -q -r requirements-dev.txt --constraint $(CONSTRAINTS)
	$(VENV)/bin/python -m pip check

test:
	$(VENV)/bin/python -m pytest -q
