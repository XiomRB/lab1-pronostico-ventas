"""Seguimiento de los pronósticos publicados frente a las ventas reales."""
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from lab1_comun import INICIO, RAPIDOS
from pronostico_ventas import operacion


def seguir(logical_date, **_):
    return operacion.tarea_seguimiento(logical_date.date())


with DAG("seguimiento_desempeno", schedule=None, start_date=INICIO, catchup=False, default_args=RAPIDOS):
    PythonOperator(task_id="actualizar", python_callable=seguir, pool="pesado")
