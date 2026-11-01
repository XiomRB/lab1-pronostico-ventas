"""Cuantiles por residuos escalados: un solo modelo puntual y cualquier cuantil sin reentrenar."""
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

GRILLA = np.round(np.arange(0.01, 1.0, 0.01), 2)
LIMITES_VOLUMEN = [0, 10, 100, 1000, np.inf]
_DIARIO = ["family", "volumen", "tramo"]
_PERIODO = ["family", "volumen"]


def _volumen(escala: pd.Series) -> pd.Series:
    return pd.cut(escala, LIMITES_VOLUMEN, labels=False, right=False).astype(int)


def _tabla(datos: pd.DataFrame, grupos: list[str], minimo: int) -> pd.DataFrame:
    conteo = datos.groupby(grupos)["e"].transform("size")
    validos = datos[conteo >= minimo]
    tabla = validos.groupby(grupos)["e"].quantile(list(GRILLA)).unstack()
    tabla.columns = [float(c) for c in tabla.columns]
    return tabla


@dataclass
class Calibrador:
    """Conserva residuos por grupo, con respaldo por familia y global."""

    diario: pd.DataFrame
    diario_familia: pd.DataFrame
    periodo: pd.DataFrame
    periodo_familia: pd.DataFrame
    global_diario: np.ndarray
    global_periodo: np.ndarray

    def _valores(self, datos: pd.DataFrame, nivel: float, fina: pd.DataFrame, grupos: list[str], familia: pd.DataFrame, general: np.ndarray) -> np.ndarray:
        def interpolar(tabla: pd.DataFrame) -> pd.Series:
            return pd.Series({i: np.interp(nivel, GRILLA, fila) for i, fila in zip(tabla.index, tabla.to_numpy())}, dtype="float64")

        claves = pd.MultiIndex.from_frame(datos[grupos])
        fino = interpolar(fina)
        fino.index = fina.index
        resultado = pd.Series(claves.map(fino.to_dict()), index=datos.index, dtype="float64")
        resultado = resultado.fillna(datos["family"].map(interpolar(familia).to_dict()))
        return resultado.fillna(float(np.interp(nivel, GRILLA, general))).to_numpy()

    def cuantil_diario(self, datos: pd.DataFrame, nivel: float) -> np.ndarray:
        marco = datos.assign(volumen=_volumen(datos["escala"]), tramo=(datos["h"] > 7).astype(int))
        ajuste = self._valores(marco, nivel, self.diario, _DIARIO, self.diario_familia, self.global_diario)
        return np.clip(datos["p"].to_numpy() + datos["escala"].to_numpy() * ajuste, 0, None)

    def cuantil_periodo(self, periodo: pd.DataFrame, nivel: float) -> np.ndarray:
        marco = periodo.assign(volumen=_volumen(periodo["escala"] / periodo["dias"]))
        ajuste = self._valores(marco, nivel, self.periodo, _PERIODO, self.periodo_familia, self.global_periodo)
        return np.clip(periodo["p"].to_numpy() + periodo["escala"].to_numpy() * ajuste, 0, None)


def agregar_periodo(datos: pd.DataFrame, desde_dia: int, hasta_dia: int) -> pd.DataFrame:
    """Demanda del periodo de cobertura: suma de ventas y predicciones, nunca de cuantiles diarios."""
    cobertura = datos[datos["h"].between(desde_dia, hasta_dia)]
    columnas = {"p": ("p", "sum"), "escala": ("escala", "sum"), "dias": ("h", "size")}
    if "y" in cobertura.columns:
        columnas["y"] = ("y", lambda s: s.sum(min_count=len(s)))
    claves = [c for c in ("corte", "store_nbr", "family") if c in cobertura.columns]
    periodo = cobertura.groupby(claves, as_index=False, observed=True).agg(**columnas)
    # La escala también crece con la demanda prevista, por ejemplo ante una promoción.
    return periodo.assign(escala=periodo[["escala", "p"]].max(axis=1))


def ajustar(calibracion: pd.DataFrame, cfg_modelo: dict[str, Any]) -> Calibrador:
    """`calibracion` trae p, y, escala y h de cortes posteriores al entrenamiento."""
    minimo = cfg_modelo["minimo_residuos_grupo"]
    cobertura = cfg_modelo["cobertura"]
    datos = calibracion.dropna(subset=["y"]).copy()
    datos["e"] = (datos["y"] - datos["p"]) / datos["escala"]
    datos["volumen"] = _volumen(datos["escala"])
    datos["tramo"] = (datos["h"] > 7).astype(int)

    periodo = agregar_periodo(datos, cobertura["desde_dia"], cobertura["hasta_dia"]).dropna(subset=["y"])
    periodo["e"] = (periodo["y"] - periodo["p"]) / periodo["escala"]
    periodo["volumen"] = _volumen(periodo["escala"] / periodo["dias"])
    return Calibrador(
        diario=_tabla(datos, _DIARIO, minimo),
        diario_familia=_tabla(datos, ["family"], 1),
        periodo=_tabla(periodo, _PERIODO, minimo),
        periodo_familia=_tabla(periodo, ["family"], 1),
        global_diario=np.quantile(datos["e"], GRILLA),
        global_periodo=np.quantile(periodo["e"], GRILLA),
    )
