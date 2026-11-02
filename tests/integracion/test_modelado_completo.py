"""Modelado completo con datos sintéticos: sin fuga, mismos cortes y reproducible."""
import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
import yaml

from pronostico_ventas import config
from pronostico_ventas.evaluacion.comparacion import comparar, guardar, particiones, preparar
from pronostico_ventas.features.construccion import CARACTERISTICAS, construir, objetivos, obtener
from pronostico_ventas.modelos.base import crear

CORTE = date(2017, 3, 6)


@pytest.fixture
def cfg(proyecto_modelo):
    return config.cargar(proyecto_modelo)


def alterar_ventas(cfg, condicion):
    ruta = cfg.historico / "ventas.parquet"
    tabla = pd.read_parquet(ruta)
    tabla.loc[condicion(tabla), "sales"] = 999999.0
    tabla.to_parquet(ruta, index=False)


def test_panel_cubre_series_y_horizonte(cfg):
    panel = construir(cfg, CORTE)
    assert len(panel) == 6 * 7
    assert sorted(panel["h"].unique()) == [float(h) for h in range(1, 8)]
    assert panel["date"].min() == pd.Timestamp(CORTE) + pd.Timedelta(days=1)


def test_panel_no_cambia_si_se_altera_el_futuro(cfg):
    antes = construir(cfg, CORTE)
    alterar_ventas(cfg, lambda t: t["date"] >= pd.Timestamp(CORTE))
    pd.testing.assert_frame_equal(construir(cfg, CORTE), antes)


def test_panel_si_cambia_si_se_altera_lo_conocido(cfg):
    antes = construir(cfg, CORTE)
    alterar_ventas(cfg, lambda t: t["date"] == pd.Timestamp(CORTE) - pd.Timedelta(days=2))
    assert not construir(cfg, CORTE)["media_7"].equals(antes["media_7"])


def test_venta_del_ultimo_dia_no_se_conoce_antes_de_su_entrega(cfg):
    antes = construir(cfg, CORTE)
    alterar_ventas(cfg, lambda t: t["fecha_entrega"] > pd.Timestamp(CORTE))
    pd.testing.assert_frame_equal(construir(cfg, CORTE), antes)


def test_panel_no_inventa_datos(cfg):
    panel = construir(cfg, date(2017, 1, 3))
    assert panel["lag_364"].isna().all()


def test_promocion_viene_del_plan_publicado(cfg):
    panel = construir(cfg, date(2017, 2, 13))
    assert panel["promociones"].notna().all()


def test_panel_persistido_coincide_y_se_reutiliza(cfg):
    primero = obtener(cfg, CORTE)
    ruta = next((cfg.procesado).rglob("panel_*.parquet"))
    tiempo = ruta.stat().st_mtime_ns
    pd.testing.assert_frame_equal(obtener(cfg, CORTE), primero)
    assert ruta.stat().st_mtime_ns == tiempo


def test_objetivo_ausente_no_es_cero(cfg):
    reales = objetivos(cfg, date(2017, 3, 1), date(2017, 2, 27), date(2017, 3, 5))
    assert reales["date"].max() < pd.Timestamp("2017-03-01")


def test_particiones_no_se_solapan(cfg):
    horizonte = cfg.modelo["horizonte_dias"]
    for parte in particiones(cfg):
        assert max(parte.entrenamiento) + timedelta(days=horizonte) < min(parte.calibracion)
        assert max(parte.calibracion) + timedelta(days=horizonte) < parte.prueba
        assert parte.prueba + timedelta(days=horizonte) <= cfg.corte_historico


def test_validacion_no_puede_usar_la_reserva(proyecto_modelo):
    ruta = proyecto_modelo / "config" / "modelo.yaml"
    modelo = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    modelo["validacion"]["ultimo_corte"] = "2017-03-13"
    ruta.write_text(yaml.safe_dump(modelo), encoding="utf-8")
    with pytest.raises(ValueError):
        particiones(config.cargar(proyecto_modelo))


def test_configuracion_real_no_usa_la_reserva(raiz, monkeypatch):
    monkeypatch.delenv("BANDEJA_DIR", raising=False)
    cfg = config.cargar(raiz)
    grupos = particiones(cfg)
    assert len(grupos) == 8
    assert grupos[-1].prueba + timedelta(days=cfg.modelo["horizonte_dias"]) <= cfg.corte_historico
    assert [g.prueba.isoformat() for g in grupos][0] == "2016-08-29"


@pytest.mark.parametrize("nombre", ["baseline", "lightgbm", "lightgbm_poisson", "hgb_poisson"])
def test_interfaz_comun(cfg, nombre):
    parte = particiones(cfg)[-1]
    modelo = crear(nombre, cfg.modelo)
    calibrador = preparar(modelo, cfg, parte)
    panel = obtener(cfg, parte.prueba).assign(p=lambda d: modelo.predecir(d))
    assert (panel["p"] >= 0).all() and len(panel) == 42
    q10, q90 = calibrador.cuantil_diario(panel, 0.1), calibrador.cuantil_diario(panel, 0.9)
    assert (q10 <= q90).all()


def test_modelos_usan_cortes_identicos(cfg):
    resultado = comparar(cfg)
    cortes = {tuple(c["corte"] for c in r["detalle"]) for r in resultado["modelos"].values()}
    assert len(cortes) == 1
    assert list(next(iter(cortes))) == resultado["cortes"]


def test_comparacion_es_reproducible(cfg):
    uno = comparar(cfg, ["baseline", "lightgbm", "hgb_poisson"])
    dos = comparar(cfg, ["baseline", "lightgbm", "hgb_poisson"])
    for nombre in uno["modelos"]:
        assert [c["hash_predicciones"] for c in uno["modelos"][nombre]["detalle"]] == [c["hash_predicciones"] for c in dos["modelos"][nombre]["detalle"]]


def test_vigente_se_conserva_si_nadie_cumple(cfg):
    cfg.modelo["reemplazo"]["mejora_costo_minima"] = 2.0
    resultado = comparar(cfg, ["baseline", "lightgbm"])
    assert resultado["modelo_elegido"] == "baseline"
    assert not resultado["decisiones"]["lightgbm"]["reemplaza"]


def test_sin_cruces_de_cuantiles(cfg):
    resultado = comparar(cfg, ["baseline", "lightgbm"])
    assert all(r["cruces"] == 0 for r in resultado["modelos"].values())


def test_reporte_no_contiene_filas_de_datos(cfg):
    resultado = comparar(cfg, ["baseline"])
    guardar(cfg, resultado)
    guardado = json.loads((cfg.reportes / "comparacion_modelos.json").read_text(encoding="utf-8"))
    assert guardado["modelo_elegido"] == "baseline"
    assert "store_nbr" not in json.dumps(guardado)
    assert np.isfinite(guardado["modelos"]["baseline"]["costo_total"])
