"""DAGs de PRUEBA de la Fase 0. No son los definitivos: solo validan mecanismos de Airflow."""
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.python import PythonOperator, ShortCircuitOperator
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import DAG

SALIDA = Path("/opt/lab1/data/spike_r2")
INICIO = datetime(2017, 4, 1)
FIN = datetime.fromisoformat(os.environ.get("F0_FIN", "2017-04-05")) + timedelta(hours=23, minutes=59)


def marca(nombre, logical_date, **_):
    SALIDA.mkdir(parents=True, exist_ok=True)
    with open(SALIDA / "orden.log", "a") as f:
        f.write(f"{time.time():.3f} {logical_date.date()} {nombre}\n")


def pesada(nombre, logical_date, **_):
    marca(f"{nombre}_ini", logical_date)
    time.sleep(3)
    marca(f"{nombre}_fin", logical_date)


def probar_ro(logical_date, **_):
    try:
        Path("/opt/lab1/data/bandeja/intruso.txt").write_text("x")
        res = "ESCRIBIO"
    except OSError as e:
        res = f"RECHAZADO_{e.errno}"
    marca(f"bandeja_{res}", logical_date)


def dvc_estado(logical_date, **_):
    r = subprocess.run(["dvc", "status", "-c", "--json"], cwd="/opt/lab1", capture_output=True, text=True)
    marca(f"dvc_rc{r.returncode}_{r.stdout.strip()[:30]}", logical_date)


def falla_un_dia(logical_date, **_):
    marca("respaldo_intento", logical_date)
    if logical_date.date().isoformat() == "2017-04-03":
        (SALIDA / f"respaldo_fallido_{logical_date.date()}").touch()
        raise RuntimeError("fallo simulado de respaldo")


def cierre(logical_date, **_):
    if (SALIDA / f"respaldo_fallido_{logical_date.date()}").exists():
        raise RuntimeError("publicacion RESPALDO_FALLIDO: corrida en rojo")


for dag_id, fn in [("f0_ingesta", marca), ("f0_pronostico", marca)]:
    with DAG(dag_id, schedule=None, start_date=INICIO, catchup=False, max_active_runs=1) as d:
        PythonOperator(task_id="t", python_callable=fn, op_kwargs={"nombre": dag_id})
    globals()[dag_id] = d

with DAG("f0_ro", schedule=None, start_date=INICIO, catchup=False) as d_ro:
    PythonOperator(task_id="ro", python_callable=probar_ro) >> PythonOperator(task_id="dvc", python_callable=dvc_estado)

with DAG("f0_respaldo", schedule=None, start_date=INICIO, catchup=False) as d_resp:
    PythonOperator(task_id="respaldar", python_callable=falla_un_dia, retries=0)

with DAG("f0_serial", schedule=None, start_date=INICIO, catchup=False) as d_serial:
    for i in range(3):
        PythonOperator(task_id=f"p{i}", python_callable=pesada, op_kwargs={"nombre": f"p{i}"}, pool="pesado")


def hijo(tid, dag_id, **kw):
    return TriggerDagRunOperator(task_id=tid, trigger_dag_id=dag_id, logical_date="{{ logical_date }}",
                                 trigger_run_id=f"{dag_id}__{{{{ ds }}}}", reset_dag_run=True,
                                 wait_for_completion=True, poke_interval=2, **kw)


with DAG("f0_orquestador", schedule="0 6 * * *", start_date=INICIO, end_date=FIN, catchup=True, max_active_runs=1,
         default_args={"retries": 2, "retry_delay": timedelta(seconds=5)}) as orq:
    ing = hijo("ingesta", "f0_ingesta")
    lunes = ShortCircuitOperator(task_id="es_lunes", python_callable=lambda logical_date, **_: logical_date.weekday() == 0,
                                 ignore_downstream_trigger_rules=True)
    pro = hijo("pronostico", "f0_pronostico")
    resp = hijo("respaldo", "f0_respaldo")
    seg = PythonOperator(task_id="seguimiento", python_callable=marca, op_kwargs={"nombre": "seguimiento"}, trigger_rule="all_done")
    fin = PythonOperator(task_id="cierre", python_callable=cierre, trigger_rule="all_done", retries=0)
    ing >> lunes >> pro >> resp >> seg >> fin
