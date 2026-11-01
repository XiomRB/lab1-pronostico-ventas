PYTHON ?= python3.12
VENV := .venv
CONSTRAINTS := https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt

REMOTO := ../dvc-storage/lab1

IMAGEN := lab1-pronostico:3.3.2
EN_IMAGEN := docker run --rm -u $$(id -u):0 -e PYTHONPATH=/opt/lab1/src -e OMP_NUM_THREADS=4 -v $$(pwd):/opt/lab1 -w /opt/lab1 $(IMAGEN)

COMPOSE := docker compose --env-file .env -f airflow/docker-compose.yaml

.PHONY: install test prepare-remote verify-remote simulate ingest image evaluate setup up down backup-dvc restore-dvc

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

image:
	docker build -f airflow/Dockerfile -t $(IMAGEN) .

evaluate:
	$(EN_IMAGEN) python -m pronostico_ventas.evaluacion

setup:
	./scripts/preparar_entorno.sh

# El simulador termina antes de crear los servicios que montan la bandeja.
up: setup
	$(COMPOSE) build
	$(COMPOSE) run --rm simulador
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

backup-dvc:
	./scripts/respaldar_dvc.sh $(DESTINO)

restore-dvc:
	./scripts/restaurar_dvc.sh $(ARCHIVO)

prepare-remote:
	mkdir -p $(REMOTO)
	touch $(REMOTO)/.remoto-lab1

verify-remote:
	@test -f $(REMOTO)/.remoto-lab1 || (echo "Falta el centinela de $(REMOTO)" >&2; exit 1)
	@test "$$($(VENV)/bin/dvc status -c --json)" = "{}" || (echo "Remoto sin sincronizar" >&2; exit 1)
	@echo "Remoto local sincronizado"
