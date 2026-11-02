"""Reentrenamiento periódico del modelo vigente."""
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from lab1_comun import INICIO, RAPIDOS
from pronostico_ventas import operacion


def entrenar(logical_date, **_):
    return operacion.tarea_entrenamiento(logical_date.date())


with DAG("entrenamiento", schedule=None, start_date=INICIO, catchup=False, default_args=RAPIDOS):
    PythonOperator(task_id="entrenar", python_callable=entrenar, pool="pesado")
