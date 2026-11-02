"""Pedido por cuantil crítico: Q* = Cu / (Cu + Co) sobre la demanda acumulada del periodo."""
from typing import Any

import numpy as np
import pandas as pd

from pronostico_ventas.calibracion.residuos import Calibrador


def parametros_familia(familia: str, costos: dict[str, Any]) -> tuple[float, float]:
    for grupo in costos["grupos"].values():
        if familia in grupo["familias"]:
            return grupo["cu"], grupo["co"]
    return costos["defecto"]["cu"], costos["defecto"]["co"]


def cuantil_critico(cu: float, co: float) -> float:
    if cu <= 0 or co <= 0:
        raise ValueError("Cu y Co deben ser positivos")
    return cu / (cu + co)


def tabla_costos(familias: pd.Series, costos: dict[str, Any]) -> pd.DataFrame:
    unicas = pd.Series(familias.unique())
    valores = [parametros_familia(f, costos) for f in unicas]
    return pd.DataFrame({
        "family": unicas,
        "cu": [v[0] for v in valores],
        "co": [v[1] for v in valores],
        "q_critico": [cuantil_critico(*v) for v in valores],
    })


def calcular(periodo: pd.DataFrame, calibrador: Calibrador, costos: dict[str, Any]) -> pd.DataFrame:
    """Agrega el pedido a `periodo`. Sin datos de inventario, el resultado es necesidad bruta."""
    salida = periodo.merge(tabla_costos(periodo["family"], costos), on="family")
    salida["demanda_q"] = np.nan
    for nivel, indices in salida.groupby("q_critico").groups.items():
        salida.loc[indices, "demanda_q"] = calibrador.cuantil_periodo(salida.loc[indices], float(nivel))
    fraccionarias = salida["family"].isin(costos["familias_fraccionarias"])
    salida["pedido"] = np.where(fraccionarias, salida["demanda_q"].round(3), np.ceil(salida["demanda_q"]))
    return salida
