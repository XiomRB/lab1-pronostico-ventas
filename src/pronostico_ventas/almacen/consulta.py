"""Consultas bitemporales: qué se conocía en una fecha de corte."""
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from pronostico_ventas.config import Configuracion
from pronostico_ventas.simulador.bandeja import entrega_habil

CLAVES = {
    "ventas": ["date", "store_nbr", "family"],
    "transacciones": ["date", "store_nbr"],
    "promociones": ["date", "store_nbr", "family"],
    "petroleo": ["date"],
    "feriados": ["date", "locale", "locale_name", "description"],
    "tiendas": ["store_nbr"],
}
_OBSERVACION = re.compile(r"__obs_(\d{4}-\d{2}-\d{2})__sec_(\d+)")


def _particiones(cfg: Configuracion, fuente: str, corte: date) -> list[Path]:
    carpeta = cfg.almacen / fuente
    if not carpeta.is_dir():
        return []
    rutas = [r for r in carpeta.glob("*.parquet") if date.fromisoformat(_OBSERVACION.search(r.name)[1]) <= corte]
    return sorted(rutas, key=lambda r: int(_OBSERVACION.search(r.name)[2]))


def as_of(cfg: Configuracion, fuente: str, corte: date, columnas: list[str] | None = None, desde: date | None = None) -> pd.DataFrame:
    """Devuelve la última versión conocida en `corte` de cada registro. Lo no entregado no existe."""
    if fuente not in CLAVES:
        raise ValueError(f"Fuente desconocida: {fuente}")
    filtros = [("fecha_entrega", "<=", pd.Timestamp(corte))]
    con_fecha = fuente != "tiendas"
    if desde is not None and con_fecha:
        filtros.append(("date", ">=", pd.Timestamp(desde)))
    propias = None if columnas is None else [c for c in columnas if c != "conocido_desde"]
    leer = None if columnas is None else list(dict.fromkeys(propias + CLAVES[fuente] + ["fecha_entrega"]))

    historico = pd.read_parquet(cfg.historico / f"{fuente}.parquet", columns=leer, filters=filtros)
    tablas = [historico.assign(conocido_desde=historico["fecha_entrega"], secuencia=0)]
    extra = None if leer is None else leer + ["conocido_desde", "secuencia"]
    for ruta in _particiones(cfg, fuente, corte):
        tabla = pd.read_parquet(ruta, columns=extra)
        if desde is not None and con_fecha:
            tabla = tabla[tabla["date"] >= pd.Timestamp(desde)]
        tablas.append(tabla)
    vacia = tablas[0].iloc[0:0].drop(columns="secuencia")
    tablas = [t for t in tablas if not t.empty]
    if not tablas:
        return vacia[columnas] if columnas else vacia

    unida = pd.concat(tablas, ignore_index=True).sort_values(["conocido_desde", "secuencia"], kind="stable")
    vigente = unida.drop_duplicates(CLAVES[fuente], keep="last").sort_values(CLAVES[fuente], kind="stable")
    vigente = vigente.drop(columns="secuencia")
    return vigente[columnas].reset_index(drop=True) if columnas else vigente.reset_index(drop=True)


def series_esperadas(cfg: Configuracion) -> pd.DataFrame:
    """Pares tienda y familia que componen un día completo según el final del histórico."""
    return (
        pd.read_parquet(cfg.historico / "ventas.parquet", columns=["store_nbr", "family"],
                        filters=[("date", ">=", pd.Timestamp(cfg.corte_historico - timedelta(days=7)))])
        .drop_duplicates()
        .sort_values(["store_nbr", "family"], ignore_index=True)
    )


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
    """Series esperadas conocidas por día. Una fecha ausente aparece con 0, sin inventar ventas."""
    esperadas = series_esperadas(cfg)
    fechas = pd.date_range(corte - timedelta(days=dias), corte - timedelta(days=1))
    conocidas = as_of(cfg, "ventas", corte, columnas=["date", "store_nbr", "family"], desde=fechas[0].date())
    filas = conocidas.merge(esperadas, on=["store_nbr", "family"]).groupby("date").size()
    resultado = pd.DataFrame({"date": fechas, "filas": filas.reindex(fechas, fill_value=0).to_numpy()})
    return resultado.assign(completa=resultado["filas"] >= len(esperadas))


def avisos_completitud(cfg: Configuracion, corte: date) -> list[str]:
    """Faltantes recientes según la frecuencia y el retraso de cada fuente, sin ausencias esperadas."""
    dias = cfg.validacion["dias_revision_completitud"]
    sin_operacion = set(cfg.validacion["dias_sin_operacion"])
    inicio = corte - timedelta(days=dias)
    avisos = []

    limite_ventas = corte - timedelta(days=cfg.fuentes["ventas"]["retraso_dias"])
    for fila in completitud_ventas(cfg, corte, dias).itertuples():
        fecha = fila.date.date()
        if fecha <= limite_ventas and not fila.completa and fecha.strftime("%m-%d") not in sin_operacion:
            avisos.append(f"ventas:{fecha}:{fila.filas}_series")

    limite = corte - timedelta(days=cfg.fuentes["transacciones"]["retraso_dias"])
    ventas = as_of(cfg, "ventas", corte, columnas=["date", "store_nbr", "sales"], desde=inicio)
    con_venta = ventas[(ventas["sales"] > 0) & (ventas["date"] <= pd.Timestamp(limite))][["date", "store_nbr"]].drop_duplicates()
    conocidas = as_of(cfg, "transacciones", corte, columnas=["date", "store_nbr"], desde=inicio)
    faltantes = con_venta.merge(conocidas, how="left", on=["date", "store_nbr"], indicator=True)
    faltantes = faltantes[faltantes["_merge"] == "left_only"].groupby("date").size()
    avisos += [f"transacciones:{f.date()}:{n}_tiendas" for f, n in faltantes.items()]

    precios = set(as_of(cfg, "petroleo", corte, columnas=["date"], desde=inicio)["date"].dt.date)
    retraso = cfg.fuentes["petroleo"]["retraso_dias"]
    for dia in pd.bdate_range(inicio, corte).date:
        if dia not in precios and entrega_habil(dia, retraso) <= corte:
            avisos.append(f"petroleo:{dia}:sin_precio")
    return avisos
