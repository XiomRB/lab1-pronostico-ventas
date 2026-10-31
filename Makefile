PYTHON ?= python3.12
VENV := .venv
CONSTRAINTS := https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt

REMOTO := ../dvc-storage/lab1

.PHONY: instalar test preparar-remoto verificar-remoto

instalar:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install -q -r requirements-dev.txt --constraint $(CONSTRAINTS)
	$(VENV)/bin/python -m pip check

test:
	$(VENV)/bin/python -m pytest -q

preparar-remoto:
	mkdir -p $(REMOTO)
	touch $(REMOTO)/.remoto-lab1

verificar-remoto:
	@test -f $(REMOTO)/.remoto-lab1 || (echo "Falta el centinela de $(REMOTO)" >&2; exit 1)
	@test "$$($(VENV)/bin/dvc status -c --json)" = "{}" || (echo "Remoto sin sincronizar" >&2; exit 1)
	@echo "Remoto local sincronizado"
