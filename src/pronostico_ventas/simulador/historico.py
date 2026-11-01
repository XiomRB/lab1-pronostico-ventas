"""Carga histórica: cada registro conserva la fecha en que estuvo disponible."""
from datetime import date
from pathlib import Path

import pandas as pd

from pronostico_ventas.config import Configuracion
from pronostico_ventas.simulador.bandeja import (
    aperturas,
    cobertura_promociones,
    entrega_diaria,
    entrega_feriado,
    entrega_habil,
    primera_publicacion_promocion,
)
from pronostico_ventas.simulador.contrato import COLUMNAS

ENTEROS = {"id", "store_nbr", "onpromotion", "transactions", "cluster"}
DECIMALES = {"sales", "dcoilwtico"}


def tipar(tabla: pd.DataFrame) -> pd.DataFrame:
    tipada = tabla.copy()
    for columna in tipada.columns:
        if columna in ENTEROS:
            tipada[columna] = pd.to_numeric(tipada[columna]).astype("int64")
        elif columna in DECIMALES:
            tipada[columna] = pd.to_numeric(tipada[columna]).astype("float64")
        elif columna == "transferred":
            tipada[columna] = tipada[columna] == "True"
        elif columna == "date":
            tipada[columna] = pd.to_datetime(tipada[columna], format="%Y-%m-%d")
    return tipada


def _con_entrega(tabla: pd.DataFrame, regla) -> pd.DataFrame:
    fechas = {texto: regla(date.fromisoformat(texto)) for texto in tabla["date"].unique()}
    return tabla.assign(fecha_entrega=pd.to_datetime(tabla["date"].map(fechas)))


def _guardar(tabla: pd.DataFrame, destino: Path, claves: list[str]) -> int:
    ordenada = tipar(tabla).sort_values(claves, kind="stable")
    ordenada.to_parquet(destino, index=False, compression="zstd")
    return len(ordenada)


def generar(tablas: dict[str, pd.DataFrame], cfg: Configuracion, destino: Path) -> dict[str, int]:
    """Escribe una tabla Parquet por fuente y devuelve sus filas."""
    destino.mkdir(parents=True)
    corte, fuentes = cfg.corte_historico.isoformat(), cfg.fuentes
    train = tablas["train.csv"]
    previo = train[train["date"] <= corte]
    filas = {}

    ventas = _con_entrega(
        previo[COLUMNAS["ventas"]],
        lambda f: entrega_diaria(f, fuentes["ventas"]["retraso_dias"]),
    )
    filas["ventas"] = _guardar(ventas, destino / "ventas.parquet", ["date", "store_nbr", "family"])

    dia = fuentes["promociones"]["dia_publicacion"]
    cobertura = cobertura_promociones(cfg.horizonte_dias, dia, cfg.dia_corte)
    promociones = _con_entrega(
        previo[COLUMNAS["promociones"]],
        lambda f: primera_publicacion_promocion(f, dia, cobertura),
    )
    filas["promociones"] = _guardar(promociones, destino / "promociones.parquet", ["date", "store_nbr", "family"])

    transacciones = tablas["transactions.csv"]
    transacciones = _con_entrega(
        transacciones[transacciones["date"] <= corte],
        lambda f: entrega_diaria(f, fuentes["transacciones"]["retraso_dias"]),
    )
    filas["transacciones"] = _guardar(transacciones, destino / "transacciones.parquet", ["date", "store_nbr"])

    petroleo = tablas["oil.csv"]
    petroleo = _con_entrega(
        petroleo[petroleo["date"] <= corte],
        lambda f: entrega_habil(f, fuentes["petroleo"]["retraso_dias"]),
    )
    filas["petroleo"] = _guardar(petroleo, destino / "petroleo.parquet", ["date"])

    feriados = tablas["holidays_events.csv"]
    llegada = pd.to_datetime([entrega_feriado(f, fuentes["feriados"]) for f in feriados.to_dict("records")])
    feriados = feriados.assign(fecha_entrega=llegada)
    feriados = feriados[feriados["fecha_entrega"] <= pd.Timestamp(cfg.corte_historico)]
    filas["feriados"] = _guardar(feriados, destino / "feriados.parquet", ["date", "locale_name", "description"])

    apertura = aperturas(train)
    tiendas = tablas["stores.csv"]
    tiendas = tiendas.assign(
        fecha_entrega=pd.to_datetime([apertura.get(int(t)) for t in tiendas["store_nbr"]])
    )
    tiendas = tiendas[tiendas["fecha_entrega"] <= pd.Timestamp(cfg.corte_historico)]
    filas["tiendas"] = _guardar(tiendas, destino / "tiendas.parquet", ["store_nbr"])
    return filas
