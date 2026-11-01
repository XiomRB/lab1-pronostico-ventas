#!/usr/bin/env bash
# Genera .env y las carpetas que Docker no debe crear como root. No sobrescribe un .env existente.
set -euo pipefail
mkdir -p data/kaggle data/bandeja ../dvc-storage/lab1 airflow/logs
if [ ! -f .env ]; then
  umask 077
  {
    echo "AIRFLOW_UID=$(id -u)"
    echo "AIRFLOW__API_AUTH__JWT_SECRET=$(openssl rand -hex 32)"
    echo "FERNET_KEY=$(openssl rand -base64 32 | tr '+/' '-_')"
    echo "_AIRFLOW_WWW_USER_PASSWORD=$(openssl rand -hex 12)"
    echo "AIRFLOW_PORT=8080"
    echo "LAB1_INICIO=2017-04-01"
    echo "LAB1_FIN=2017-08-24"
    echo "BANDEJA_HOST="
  } > .env
  echo "Se generó .env. La clave de la interfaz de Airflow está en _AIRFLOW_WWW_USER_PASSWORD."
fi
