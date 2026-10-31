PYTHON ?= python3.12
VENV := .venv
CONSTRAINTS := https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt

REMOTO := ../dvc-storage/lab1

.PHONY: install test prepare-remote verify-remote simulate ingest

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install -q -r requirements-dev.txt --constraint $(CONSTRAINTS)
	$(VENV)/bin/python -m pip check

test:
	$(VENV)/bin/python -m pytest -q

simulate:
	PYTHONPATH=src $(VENV)/bin/python -m pronostico_ventas.simulador

ingest:
	PYTHONPATH=src $(VENV)/bin/python -m pronostico_ventas.ingesta --fecha $(FECHA)

prepare-remote:
	mkdir -p $(REMOTO)
	touch $(REMOTO)/.remoto-lab1

verify-remote:
	@test -f $(REMOTO)/.remoto-lab1 || (echo "Falta el centinela de $(REMOTO)" >&2; exit 1)
	@test "$$($(VENV)/bin/dvc status -c --json)" = "{}" || (echo "Remoto sin sincronizar" >&2; exit 1)
	@echo "Remoto local sincronizado"
