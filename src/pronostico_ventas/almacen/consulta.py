"""Consultas bitemporales: qué se conocía en una fecha de corte."""
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from pronostico_ventas.config import Configuracion

CLAVES = {
    "ventas": ["date", "store_nbr", "family"],
    "transacciones": ["date", "store_nbr"],
    "promociones": ["date", "store_nbr", "family"],
    "petroleo": ["date"],
    "feriados": ["date", "locale", "locale_name", "description"],
    "tiendas": ["store_nbr"],
}
_ENTREGA = re.compile(r"__entrega_(\d{4}-\d{2}-\d{2})__")


def _particiones(cfg: Configuracion, fuente: str, corte: date) -> list[Path]:
    carpeta = cfg.almacen / fuente
    if not carpeta.is_dir():
        return []
    rutas = [r for r in carpeta.glob("*.parquet") if date.fromisoformat(_ENTREGA.search(r.name)[1]) <= corte]
    return sorted(rutas, key=lambda r: (_ENTREGA.search(r.name)[1], r.name))


def as_of(cfg: Configuracion, fuente: str, corte: date, columnas: list[str] | None = None, desde: date | None = None) -> pd.DataFrame:
    """Devuelve la última versión conocida en `corte` de cada registro. Lo no entregado no existe."""
    if fuente not in CLAVES:
        raise ValueError(f"Fuente desconocida: {fuente}")
    filtros = [("fecha_entrega", "<=", pd.Timestamp(corte))]
    con_fecha = fuente != "tiendas"
    if desde is not None and con_fecha:
        filtros.append(("date", ">=", pd.Timestamp(desde)))
    leer = None if columnas is None else list(dict.fromkeys(columnas + CLAVES[fuente] + ["fecha_entrega"]))

    tablas = [pd.read_parquet(cfg.historico / f"{fuente}.parquet", columns=leer, filters=filtros)]
    for ruta in _particiones(cfg, fuente, corte):
        tabla = pd.read_parquet(ruta, columns=leer)
        if desde is not None and con_fecha:
            tabla = tabla[tabla["date"] >= pd.Timestamp(desde)]
        tablas.append(tabla)
    tablas = [t for t in tablas if not t.empty]
    if not tablas:
        return pd.DataFrame(columns=leer or CLAVES[fuente])

    unida = pd.concat(tablas, ignore_index=True).sort_values("fecha_entrega", kind="stable")
    vigente = unida.drop_duplicates(CLAVES[fuente], keep="last").sort_values(CLAVES[fuente], kind="stable")
    return vigente[columnas].reset_index(drop=True) if columnas else vigente.reset_index(drop=True)


def frescura(cfg: Configuracion, corte: date) -> dict[str, dict[str, Any]]:
    """Última fecha conocida por fuente diaria. Un atraso no es un error: se informa."""
    maximo = cfg.validacion["maximo_atraso_dias"]
    estados = {}
    for fuente in ("ventas", "transacciones", "petroleo"):
        fechas = as_of(cfg, fuente, corte, columnas=["date"], desde=corte - timedelta(days=60))["date"]
        if fechas.empty:
            estados[fuente] = {"ultima_fecha": None, "atraso_dias": None, "estado": "sin_datos"}
            continue
        ultima = fechas.max().date()
        atraso = (corte - ultima).days
        estados[fuente] = {
            "ultima_fecha": ultima.isoformat(),
            "atraso_dias": atraso,
            "estado": "critica" if atraso >= maximo else "normal",
        }
    return estados


def completitud_ventas(cfg: Configuracion, corte: date, dias: int) -> pd.DataFrame:
    """Filas conocidas por día. Una fecha ausente aparece con 0 filas, sin inventar ventas."""
    filas_esperadas = pd.read_parquet(cfg.historico / "ventas.parquet", columns=["date"]).groupby("date").size().mode().iloc[0]
    fechas = pd.date_range(corte - timedelta(days=dias), corte - timedelta(days=1))
    conocidas = as_of(cfg, "ventas", corte, columnas=["date"], desde=fechas[0].date()).groupby("date").size()
    resultado = pd.DataFrame({"date": fechas, "filas": conocidas.reindex(fechas, fill_value=0).to_numpy()})
    return resultado.assign(completa=resultado["filas"] >= filas_esperadas)
