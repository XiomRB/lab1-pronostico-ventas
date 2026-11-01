"""Ingesta y validación de las fuentes disponibles en la fecha lógica."""
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from lab1_comun import INICIO, RAPIDOS
from pronostico_ventas import operacion


def ingerir(logical_date, **_):
    return operacion.tarea_ingesta(logical_date.date())


with DAG("ingesta_validacion", schedule=None, start_date=INICIO, catchup=False, default_args=RAPIDOS):
    PythonOperator(task_id="ingerir", python_callable=ingerir, pool="pesado")
