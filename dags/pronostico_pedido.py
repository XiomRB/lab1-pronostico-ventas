"""Pronóstico y pedido sugerido del corte, con su versionado y respaldo."""
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from lab1_comun import INICIO, RAPIDOS
from pronostico_ventas import operacion


def asegurar(logical_date, **_):
    return operacion.tarea_asegurar_modelo(logical_date.date())


def pronosticar(logical_date, **_):
    return operacion.tarea_pronostico(logical_date.date())


def respaldar(logical_date, **_):
    return operacion.tarea_versionado(logical_date.date())


with DAG("pronostico_pedido", schedule=None, start_date=INICIO, catchup=False, default_args=RAPIDOS):
    modelo = PythonOperator(task_id="asegurar_modelo", python_callable=asegurar, pool="pesado")
    publicar = PythonOperator(task_id="publicar", python_callable=pronosticar, pool="pesado")
    versionar = PythonOperator(task_id="versionar_y_respaldar", python_callable=respaldar, pool="pesado")
    modelo >> publicar >> versionar
