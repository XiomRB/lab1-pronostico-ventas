"""Tareas de operación y seguimiento con datos sintéticos."""
import json
from datetime import date

import pandas as pd
import pytest

from pronostico_ventas import config, operacion
from pronostico_ventas.publicacion import entrenamiento, estado, publicar
from pronostico_ventas.seguimiento import desempeno

CORTE = date(2017, 3, 6)


@pytest.fixture
def cfg(proyecto_modelo, monkeypatch):
    cargar = config.cargar
    monkeypatch.setattr(config, "cargar", lambda raiz=proyecto_modelo: cargar(raiz))
    return config.cargar()


def test_primer_modelo_es_el_elegido_y_se_conserva(cfg):
    assert operacion.tarea_asegurar_modelo(CORTE).startswith("baseline_")
    assert operacion.tarea_asegurar_modelo(date(2017, 3, 7)).startswith("baseline_")


def test_preparacion_solo_trabaja_en_el_corte(cfg):
    assert operacion.tarea_preparacion(date(2017, 3, 7)) == "sin_corte"
    assert operacion.tarea_preparacion(CORTE) == "panel_listo"


def publicado(cfg):
    operacion.tarea_asegurar_modelo(CORTE)
    return operacion.tarea_pronostico(CORTE)


def test_flujo_de_pronostico_es_idempotente(cfg):
    assert publicado(cfg)["resultado"] == "publicada"
    assert operacion.tarea_pronostico(CORTE)["resultado"] == "sin_cambios"


def test_seguimiento_contra_calculo_manual(cfg):
    publicado(cfg)
    informe = desempeno.actualizar(cfg, date(2017, 3, 16))
    medida = informe["publicaciones"][0]
    base = publicar.carpeta(cfg, CORTE, 1)
    pronostico = pd.read_parquet(base / "pronostico.parquet")
    reales = pd.read_parquet(cfg.historico / "ventas.parquet", columns=["date", "store_nbr", "family", "sales"])
    unido = pronostico.merge(reales, on=["date", "store_nbr", "family"])
    esperado = (unido["sales"] - unido["pronostico"]).abs().sum() / unido["sales"].sum()
    assert medida["wape"] == pytest.approx(esperado)
    assert medida["periodo_completo"]


def test_seguimiento_de_ventas_desconocidas_queda_pendiente(cfg):
    publicado(cfg)
    medida = desempeno.actualizar(cfg, CORTE)["publicaciones"][0]
    assert medida["dias_con_real"] == 0 and medida["wape"] is None and medida["costo_pedido"] is None


def test_seguimiento_es_idempotente(cfg):
    publicado(cfg)
    assert desempeno.actualizar(cfg, date(2017, 3, 16)) == desempeno.actualizar(cfg, date(2017, 3, 16))


def test_seguimiento_compara_original_y_ultima_revision(cfg):
    publicado(cfg)
    (cfg.bandeja / "ventas_2017-03-05__entrega_2017-03-07.csv").write_text("date,store_nbr,family,sales,onpromotion\n2017-03-05,1,GROCERY I,9999.0,0\n")
    from pronostico_ventas.ingesta.proceso import ingerir

    ingerir(cfg, date(2017, 3, 17))
    publicar.publicar(cfg, CORTE, reprocesar_en=date(2017, 3, 17))
    medidas = desempeno.actualizar(cfg, date(2017, 3, 17))["publicaciones"]
    assert [m["revision"] for m in medidas] == [1, 2]


def test_reporte_no_contiene_filas_de_datos(cfg):
    publicado(cfg)
    texto = desempeno.reporte(desempeno.actualizar(cfg, date(2017, 3, 16)))
    assert "GROCERY" not in texto and "2017-03-06" in texto


def test_cierre_en_rojo_si_falla_el_respaldo(cfg):
    publicado(cfg)
    assert operacion.tarea_cierre(CORTE) == "ok"
    estado.marcar(cfg, CORTE, 1, "RESPALDO_FALLIDO", "fallo", "push")
    with pytest.raises(RuntimeError):
        operacion.tarea_cierre(CORTE)


def test_revision_automatica_antes_de_la_cobertura(cfg):
    publicado(cfg)
    assert operacion.tarea_revisiones(CORTE) == []
    assert operacion.tarea_revisiones(date(2017, 3, 7))[0]["resultado"] == "sin_cambios"
    assert operacion.tarea_revisiones(date(2017, 3, 8)) == []
