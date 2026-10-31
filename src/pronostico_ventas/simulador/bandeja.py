"""Reglas de disponibilidad por fuente y escritura de la bandeja."""
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from pronostico_ventas.config import Configuracion
from pronostico_ventas.simulador.contrato import COLUMNAS, nombre_archivo


@dataclass
class Entrega:
    fuente: str
    fecha: date
    entrega: date
    tabla: pd.DataFrame


def entrega_diaria(fecha: date, retraso_dias: int) -> date:
    return fecha + timedelta(days=retraso_dias)


def entrega_habil(fecha: date, retraso_dias: int) -> date:
    """El dato llega tras `retraso_dias` días hábiles: el del viernes llega el lunes."""
    resultado = fecha
    for _ in range(retraso_dias):
        resultado += timedelta(days=1)
        while resultado.weekday() >= 5:
            resultado += timedelta(days=1)
    return resultado


def entrega_feriado(fila: dict[str, str], reglas: dict[str, Any]) -> date:
    fecha = date.fromisoformat(fila["date"])
    if any(patron in fila["description"] for patron in reglas["patrones_imprevistos"]):
        return fecha
    if fila["type"] in reglas["tipos_anunciados"] or fila["transferred"] == "True":
        return fecha - timedelta(days=reglas["anticipacion_anuncio_dias"])
    return date(fecha.year, 1, 1)


def primera_publicacion_promocion(fecha: date, dia_publicacion: int, cobertura_dias: int) -> date:
    """Primer plan semanal que cubre `fecha`; cada plan cubre los días siguientes a su publicación."""
    limite = fecha - timedelta(days=cobertura_dias)
    return limite + timedelta(days=(dia_publicacion - limite.weekday()) % 7)


def cobertura_promociones(horizonte_dias: int, dia_publicacion: int, dia_corte: int) -> int:
    """Días que cubre un plan para alcanzar todo el horizonte del corte siguiente."""
    return horizonte_dias + (dia_corte - dia_publicacion) % 7


def aperturas(ventas: pd.DataFrame) -> dict[int, date]:
    """Primera fecha con ventas por tienda; solo el simulador conoce este dato completo."""
    con_venta = ventas.loc[pd.to_numeric(ventas["sales"]) > 0, ["store_nbr", "date"]]
    primeras = con_venta.groupby("store_nbr")["date"].min()
    return {int(tienda): date.fromisoformat(fecha) for tienda, fecha in primeras.items()}


def _por_dia(fuente: str, tabla: pd.DataFrame, corte: date, fin: date, entregar) -> list[Entrega]:
    ventana = tabla[(tabla["date"] > corte.isoformat()) & (tabla["date"] <= fin.isoformat())]
    entregas = []
    for fecha_texto, grupo in ventana.groupby("date", sort=True):
        fecha = date.fromisoformat(fecha_texto)
        entregas.append(Entrega(fuente, fecha, entregar(fecha), grupo[COLUMNAS[fuente]]))
    return entregas


def construir(tablas: dict[str, pd.DataFrame], cfg: Configuracion, fin: date) -> list[Entrega]:
    """Crea las entregas regulares de la ventana (corte_historico, fin]."""
    corte, fuentes = cfg.corte_historico, cfg.fuentes
    entregas = _por_dia(
        "ventas", tablas["train.csv"], corte, fin,
        lambda f: entrega_diaria(f, fuentes["ventas"]["retraso_dias"]),
    )
    entregas += _por_dia(
        "transacciones", tablas["transactions.csv"], corte, fin,
        lambda f: entrega_diaria(f, fuentes["transacciones"]["retraso_dias"]),
    )
    entregas += _por_dia(
        "petroleo", tablas["oil.csv"], corte, fin,
        lambda f: entrega_habil(f, fuentes["petroleo"]["retraso_dias"]),
    )
    entregas += _promociones(tablas["train.csv"], cfg, fin)
    entregas += _feriados(tablas["holidays_events.csv"], cfg, fin)
    entregas += _tiendas(tablas["stores.csv"], tablas["train.csv"], cfg, fin)
    return entregas


def _promociones(train: pd.DataFrame, cfg: Configuracion, fin: date) -> list[Entrega]:
    dia = cfg.fuentes["promociones"]["dia_publicacion"]
    cobertura = cobertura_promociones(cfg.horizonte_dias, dia, cfg.dia_corte)
    entregas = []
    actual = cfg.corte_historico + timedelta(days=1)
    actual += timedelta(days=(dia - actual.weekday()) % 7)
    while actual <= fin:
        desde, hasta = actual + timedelta(days=1), min(actual + timedelta(days=cobertura), fin)
        plan = train[(train["date"] >= desde.isoformat()) & (train["date"] <= hasta.isoformat())]
        if not plan.empty:
            entregas.append(Entrega("promociones", actual, actual, plan[COLUMNAS["promociones"]]))
        actual += timedelta(days=7)
    return entregas


def _feriados(tabla: pd.DataFrame, cfg: Configuracion, fin: date) -> list[Entrega]:
    reglas = cfg.fuentes["feriados"]
    llegada = [entrega_feriado(f, reglas) for f in tabla.to_dict("records")]
    con_llegada = tabla.assign(_entrega=llegada)
    ventana = con_llegada[(con_llegada["_entrega"] > cfg.corte_historico) & (con_llegada["_entrega"] <= fin)]
    entregas = []
    for (fecha, llegada_grupo), grupo in ventana.groupby(["date", "_entrega"], sort=True):
        entregas.append(Entrega("feriados", date.fromisoformat(fecha), llegada_grupo, grupo[COLUMNAS["feriados"]]))
    return entregas


def _tiendas(tiendas: pd.DataFrame, train: pd.DataFrame, cfg: Configuracion, fin: date) -> list[Entrega]:
    apertura = aperturas(train)
    entregas = []
    for fila in tiendas.to_dict("records"):
        fecha = apertura.get(int(fila["store_nbr"]))
        if fecha is not None and cfg.corte_historico < fecha <= fin:
            entregas.append(Entrega("tiendas", fecha, fecha, pd.DataFrame([fila])[COLUMNAS["tiendas"]]))
    return entregas


def escribir(entregas: list[Entrega], destino: Path) -> None:
    destino.mkdir(parents=True)
    for item in entregas:
        ruta = destino / nombre_archivo(item.fuente, item.fecha, item.entrega)
        if ruta.exists():
            raise ValueError(f"Entrega repetida: {ruta.name}")
        item.tabla.to_csv(ruta, index=False, lineterminator="\n")
