"""Orquestador: fija el orden de los flujos y permite repetir un día con un solo backfill."""
from datetime import timedelta

from airflow.providers.standard.operators.python import PythonOperator, ShortCircuitOperator
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import DAG
from lab1_comun import FIN, INICIO
from pronostico_ventas import operacion


def flujo(tarea, dag_id, **opciones):
    return TriggerDagRunOperator(
        task_id=tarea, trigger_dag_id=dag_id, logical_date="{{ logical_date }}",
        trigger_run_id=f"{dag_id}__{{{{ ds }}}}", reset_dag_run=True,
        wait_for_completion=True, poke_interval=3, **opciones,
    )


def es_lunes(logical_date, **_):
    return operacion.es_corte(logical_date.date())


def revisar(logical_date, **_):
    return operacion.tarea_revisiones(logical_date.date())


def cerrar(logical_date, **_):
    return operacion.tarea_cierre(logical_date.date())


with DAG(
    "operacion_diaria", schedule="0 6 * * *", start_date=INICIO, end_date=FIN, catchup=True, max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(seconds=15)},
):
    ingesta = flujo("ingesta", "ingesta_validacion")
    revisiones = PythonOperator(task_id="revisiones", python_callable=revisar, pool="pesado")
    corte = ShortCircuitOperator(task_id="es_corte", python_callable=es_lunes, ignore_downstream_trigger_rules=True)
    preparacion = flujo("preparacion", "preparacion_datos")
    pronostico = flujo("pronostico", "pronostico_pedido")
    seguimiento = flujo("seguimiento", "seguimiento_desempeno", trigger_rule="all_done")
    entrenar = flujo("entrenamiento", "entrenamiento")
    cierre = PythonOperator(task_id="cierre", python_callable=cerrar, trigger_rule="all_done", retries=0)
    # Las revisiones son una rama final: si fallan, la corrida queda en rojo sin bloquear el corte.
    ingesta >> revisiones
    ingesta >> corte >> preparacion >> pronostico >> seguimiento >> entrenar >> cierre
