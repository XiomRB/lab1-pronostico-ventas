"""Métricas, cuantiles, pedido y criterio de reemplazo, con casos calculados a mano."""
import numpy as np
import pandas as pd
import pytest

from pronostico_ventas.calibracion import residuos
from pronostico_ventas.evaluacion import metricas, reemplazo
from pronostico_ventas.evaluacion.memoria import LimiteMemoria, memoria_actual_mb
from pronostico_ventas.modelos.base import Baseline
from pronostico_ventas.pedido import politica

COSTOS = {
    "defecto": {"cu": 2.0, "co": 1.0},
    "grupos": {"p": {"cu": 1.5, "co": 1.0, "familias": ["MEATS"]}, "a": {"cu": 4.0, "co": 1.0, "familias": ["GROCERY I"]}},
    "familias_fraccionarias": ["MEATS"],
}
MODELO = {"minimo_residuos_grupo": 5, "cobertura": {"desde_dia": 2, "hasta_dia": 3}}


def calibracion_ejemplo():
    azar = np.random.default_rng(1)
    filas = []
    for corte in pd.date_range("2017-01-02", periods=4, freq="7D"):
        for familia, base in (("GROCERY I", 100.0), ("MEATS", 10.0), ("BOOKS", 1.0)):
            for tienda in range(1, 11):
                for h in (1, 2, 3, 8):
                    filas.append((corte, tienda, familia, h, base, base + azar.normal(0, base / 5), base + 1))
    return pd.DataFrame(filas, columns=["corte", "store_nbr", "family", "h", "p", "y", "escala"])


def test_metricas_con_casos_a_mano():
    y, p = np.array([10.0, 0.0]), np.array([8.0, 1.0])
    assert metricas.wape(y, p) == pytest.approx(0.3)
    assert metricas.pinball(np.array([10.0]), np.array([8.0]), 0.9) == pytest.approx(1.8)
    assert metricas.pinball(np.array([8.0]), np.array([10.0]), 0.9) == pytest.approx(0.2)
    assert metricas.cobertura_intervalo(np.array([1.0, 5.0]), np.array([0.0, 0.0]), np.array([2.0, 2.0])) == 0.5
    assert metricas.rmsle(np.array([0.0]), np.array([0.0])) == 0
    assert metricas.costo_negocio(np.array([10.0, 10.0]), np.array([8.0, 13.0]), np.array([4.0, 4.0]), np.array([1.0, 1.0])) == pytest.approx(11.0)


def test_cuantil_critico():
    assert politica.cuantil_critico(4, 1) == 0.8
    assert politica.cuantil_critico(1.5, 1) == 0.6


@pytest.mark.parametrize(("cu", "co"), [(0, 1), (1, 0), (-1, 1)])
def test_costos_invalidos_rechazados(cu, co):
    with pytest.raises(ValueError):
        politica.cuantil_critico(cu, co)


def test_familia_sin_grupo_usa_el_costo_por_defecto():
    assert politica.parametros_familia("BOOKS", COSTOS) == (2.0, 1.0)


def test_cuantiles_ordenados_y_no_negativos():
    datos = calibracion_ejemplo()
    calibrador = residuos.ajustar(datos, MODELO)
    q10, q50, q90 = (calibrador.cuantil_diario(datos, n) for n in (0.1, 0.5, 0.9))
    assert (q10 <= q50).all() and (q50 <= q90).all()
    assert (q10 >= 0).all()


def test_cuantil_de_grupo_desconocido_usa_respaldo():
    datos = calibracion_ejemplo()
    calibrador = residuos.ajustar(datos, MODELO)
    nuevo = datos.head(1).assign(family="NUEVA")
    assert np.isfinite(calibrador.cuantil_diario(nuevo, 0.9)).all()


def test_periodo_suma_ventas_y_predicciones():
    datos = pd.DataFrame({"corte": 1, "store_nbr": 1, "family": "X", "h": [1, 2, 3, 4], "p": [1.0, 2.0, 3.0, 4.0], "escala": 2.0, "y": [5.0, 6.0, 7.0, 8.0]})
    periodo = residuos.agregar_periodo(datos, 2, 3)
    assert periodo[["p", "y", "escala", "dias"]].iloc[0].tolist() == [5.0, 13.0, 5.0, 2]


def test_periodo_incompleto_no_cuenta_como_cero():
    datos = pd.DataFrame({"corte": 1, "store_nbr": 1, "family": "X", "h": [2, 3], "p": [1.0, 2.0], "escala": 2.0, "y": [5.0, np.nan]})
    assert residuos.agregar_periodo(datos, 2, 3)["y"].isna().all()


def periodo_futuro():
    return residuos.agregar_periodo(calibracion_ejemplo().drop(columns="y"), 2, 3).head(60)


def test_pedido_no_suma_cuantiles_diarios():
    datos = calibracion_ejemplo()
    calibrador = residuos.ajustar(datos, MODELO)
    cobertura = datos[datos["h"].between(2, 3)].copy()
    cobertura["q"] = calibrador.cuantil_diario(cobertura, 0.8)
    suma = cobertura.groupby(["corte", "store_nbr", "family"], as_index=False)["q"].sum()
    pedido = politica.calcular(residuos.agregar_periodo(datos, 2, 3), calibrador, COSTOS)
    comparado = pedido[pedido["family"] == "GROCERY I"].merge(suma, on=["corte", "store_nbr", "family"])
    assert not np.allclose(comparado["demanda_q"], comparado["q"], atol=0.01)


def test_cambiar_costos_cambia_pedido_sin_reentrenar():
    calibrador = residuos.ajustar(calibracion_ejemplo(), MODELO)
    base = politica.calcular(periodo_futuro(), calibrador, COSTOS)
    otros = {**COSTOS, "grupos": {**COSTOS["grupos"], "a": {"cu": 9.0, "co": 1.0, "familias": ["GROCERY I"]}}}
    nuevo = politica.calcular(periodo_futuro(), calibrador, otros)
    a = base[base["family"] == "GROCERY I"]["pedido"].to_numpy()
    b = nuevo[nuevo["family"] == "GROCERY I"]["pedido"].to_numpy()
    assert (b > a).all()


def test_mayor_costo_de_faltante_nunca_reduce_el_pedido():
    calibrador = residuos.ajustar(calibracion_ejemplo(), MODELO)
    bajo = politica.calcular(periodo_futuro(), calibrador, {**COSTOS, "defecto": {"cu": 1.0, "co": 1.0}})
    alto = politica.calcular(periodo_futuro(), calibrador, {**COSTOS, "defecto": {"cu": 9.0, "co": 1.0}})
    assert (alto["pedido"].to_numpy() >= bajo["pedido"].to_numpy()).all()


def test_redondeo_por_familia():
    calibrador = residuos.ajustar(calibracion_ejemplo(), MODELO)
    pedido = politica.calcular(periodo_futuro(), calibrador, COSTOS)
    enteros = pedido[pedido["family"] != "MEATS"]["pedido"]
    assert (enteros == np.ceil(enteros)).all()
    assert (pedido["pedido"] >= 0).all()


def test_baseline_calculo_manual():
    panel = pd.DataFrame({"media_dia_semana": [4.0, np.nan, np.nan], "media_28": [9.0, 2.0, np.nan]})
    assert Baseline().predecir(panel).tolist() == [4.0, 2.0, 0.0]


REGLAS = {"mejora_costo_minima": 0.03, "tolerancia_wape": 0.01, "cortes_ganados_minimo": 6, "cobertura_intervalo": [0.72, 0.88], "tolerancia_q": 0.05}


def resumen(**cambios):
    base = {"costo_por_corte": [90.0] * 8, "wape": 0.2, "pinball": 10.0, "cobertura_intervalo": 0.8, "cobertura_q": [{"objetivo": 0.8, "cobertura": 0.8}]}
    return {**base, **cambios}


VIGENTE = resumen(costo_por_corte=[100.0] * 8)


def test_reemplazo_cumple_todo():
    assert reemplazo.evaluar(resumen(), VIGENTE, REGLAS)["reemplaza"]


@pytest.mark.parametrize(
    ("cambios", "condicion"),
    [
        ({"costo_por_corte": [97.5] * 8}, "costo"),
        ({"wape": 0.2021}, "wape"),
        ({"pinball": 10.01}, "pinball"),
        ({"costo_por_corte": [80.0] * 5 + [101.0] * 3}, "cortes_ganados"),
        ({"cobertura_intervalo": 0.71}, "cobertura_intervalo"),
        ({"cobertura_intervalo": 0.89}, "cobertura_intervalo"),
        ({"cobertura_q": [{"objetivo": 0.8, "cobertura": 0.86}]}, "cobertura_q"),
    ],
)
def test_reemplazo_rechaza_cada_condicion(cambios, condicion):
    decision = reemplazo.evaluar(resumen(**cambios), {**VIGENTE, "wape": 0.2, "pinball": 10.0}, REGLAS)
    assert not decision["reemplaza"]
    assert not decision["condiciones"][condicion]


def test_reemplazo_exige_los_mismos_cortes():
    with pytest.raises(ValueError):
        reemplazo.evaluar(resumen(costo_por_corte=[1.0] * 7), VIGENTE, REGLAS)


def test_limite_de_memoria_detiene_y_registra_el_pico():
    avisos = []
    with LimiteMemoria(1, intervalo=0.001, al_exceder=avisos.append) as limite:
        for _ in range(100000):
            if avisos:
                break
    assert avisos
    assert limite.pico_mb >= memoria_actual_mb() // 2
