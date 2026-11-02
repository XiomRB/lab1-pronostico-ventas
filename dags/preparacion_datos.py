"""Preparación de los datos para el modelo."""
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from lab1_comun import INICIO, RAPIDOS
from pronostico_ventas import operacion


def preparar(logical_date, **_):
    return operacion.tarea_preparacion(logical_date.date())


with DAG("preparacion_datos", schedule=None, start_date=INICIO, catchup=False, default_args=RAPIDOS):
    PythonOperator(task_id="preparar", python_callable=preparar, pool="pesado")
