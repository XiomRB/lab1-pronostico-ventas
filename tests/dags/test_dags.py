"""Los DAGs existen, solo orquestan y cubren los flujos requeridos."""
import ast
from pathlib import Path

import pytest

CARPETA = Path(__file__).resolve().parents[2] / "dags"
REQUERIDOS = ["ingesta_validacion", "preparacion_datos", "pronostico_pedido", "seguimiento_desempeno", "entrenamiento", "operacion_diaria"]
PERMITIDOS = {"airflow", "datetime", "os", "lab1_comun", "pronostico_ventas"}


@pytest.mark.parametrize("nombre", REQUERIDOS)
def test_dag_requerido_existe(nombre):
    assert (CARPETA / f"{nombre}.py").is_file()


@pytest.mark.parametrize("ruta", sorted(CARPETA.glob("*.py")), ids=lambda r: r.name)
def test_dags_sin_logica_de_negocio(ruta):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            assert {a.name.split(".")[0] for a in nodo.names} <= PERMITIDOS
        if isinstance(nodo, ast.ImportFrom):
            assert nodo.module.split(".")[0] in PERMITIDOS
        if isinstance(nodo, ast.FunctionDef) and ruta.name != "operacion_diaria.py":
            assert len(nodo.body) == 1 and isinstance(nodo.body[0], ast.Return)


def test_tareas_pesadas_en_pool_de_un_cupo():
    for nombre in ("ingesta_validacion", "preparacion_datos", "pronostico_pedido", "seguimiento_desempeno", "entrenamiento"):
        contenido = (CARPETA / f"{nombre}.py").read_text(encoding="utf-8")
        assert contenido.count("PythonOperator(") == contenido.count('pool="pesado"')


def test_orquestador_no_ejecuta_en_paralelo_y_cierra_la_corrida():
    contenido = (CARPETA / "operacion_diaria.py").read_text(encoding="utf-8")
    assert "max_active_runs=1" in contenido and "catchup=True" in contenido
    assert 'task_id="cierre"' in contenido and 'trigger_rule="all_done"' in contenido


def test_dags_importan_en_airflow():
    DagBag = pytest.importorskip("airflow.models").DagBag

    bolsa = DagBag(str(CARPETA), include_examples=False)
    assert bolsa.import_errors == {}
    assert set(REQUERIDOS) <= set(bolsa.dag_ids)


def test_revisiones_son_una_rama_final():
    contenido = (CARPETA / "operacion_diaria.py").read_text(encoding="utf-8")
    assert "ingesta >> revisiones\n" in contenido
    assert "revisiones >> corte" not in contenido
