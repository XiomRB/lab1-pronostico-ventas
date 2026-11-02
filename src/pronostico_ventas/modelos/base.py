"""Interfaz común y modelos candidatos."""
from typing import Any, Protocol

import numpy as np
import pandas as pd

from pronostico_ventas.features.construccion import CARACTERISTICAS


class Modelo(Protocol):
    nombre: str

    def ajustar(self, panel: pd.DataFrame, y: np.ndarray) -> "Modelo": ...

    def predecir(self, panel: pd.DataFrame) -> np.ndarray: ...


class Baseline:
    """Promedio de los últimos cuatro días equivalentes de la semana."""

    nombre = "baseline"

    def ajustar(self, panel: pd.DataFrame, y: np.ndarray) -> "Baseline":
        return self

    def predecir(self, panel: pd.DataFrame) -> np.ndarray:
        return panel["media_dia_semana"].fillna(panel["media_28"]).fillna(0).to_numpy("float64").clip(0)


class Gradiente:
    """LightGBM o HistGradientBoosting con la misma interfaz."""

    def __init__(self, nombre: str, definicion: dict[str, Any], semilla: int, hilos: int) -> None:
        self.nombre = nombre
        self.objetivo = definicion["objetivo"]
        parametros = dict(definicion["parametros"])
        if definicion["tipo"] == "lightgbm":
            from lightgbm import LGBMRegressor

            if self.objetivo == "poisson":
                parametros["objective"] = "poisson"
            self.modelo = LGBMRegressor(
                **parametros, random_state=semilla, n_jobs=hilos, deterministic=True, force_row_wise=True, verbosity=-1
            )
        elif definicion["tipo"] == "hgb":
            from sklearn.ensemble import HistGradientBoostingRegressor

            self.modelo = HistGradientBoostingRegressor(
                **parametros, loss="poisson" if self.objetivo == "poisson" else "squared_error",
                early_stopping=False, random_state=semilla,
            )
        else:
            raise ValueError(f"Tipo de modelo desconocido: {definicion['tipo']}")

    def _matriz(self, panel: pd.DataFrame) -> np.ndarray:
        return panel[self.columnas].to_numpy("float32")

    def ajustar(self, panel: pd.DataFrame, y: np.ndarray) -> "Gradiente":
        # Una columna sin ningún valor conocido no aporta información y no se entrena con ella.
        self.columnas = [c for c in CARACTERISTICAS if panel[c].notna().any()]
        objetivo = np.log1p(y) if self.objetivo == "log" else y
        self.modelo.fit(self._matriz(panel), objetivo)
        return self

    def predecir(self, panel: pd.DataFrame) -> np.ndarray:
        crudo = self.modelo.predict(self._matriz(panel))
        return (np.expm1(crudo) if self.objetivo == "log" else crudo).astype("float64").clip(0)


def crear(nombre: str, cfg_modelo: dict[str, Any]) -> Modelo:
    if nombre == "baseline":
        return Baseline()
    return Gradiente(nombre, cfg_modelo["candidatos"][nombre], cfg_modelo["semilla"], cfg_modelo["hilos"])
