"""Incidentes deterministas sobre las entregas regulares de la bandeja."""
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from pronostico_ventas.simulador.bandeja import Entrega

ORDEN = ("archivo_tardio", "archivo_parcial", "archivo_duplicado", "correccion", "dato_invalido", "fuente_ausente")


def _extremo(entregas: list[Entrega]) -> dict[str, Any]:
    ventas = [e for e in entregas if e.fuente == "ventas"]
    maximos = [(float(pd.to_numeric(e.tabla["sales"]).max()), e) for e in ventas]
    valor, entrega = max(maximos, key=lambda par: (par[0], par[1].fecha))
    fila = entrega.tabla[pd.to_numeric(entrega.tabla["sales"]) == valor].iloc[0]
    return {
        "tipo": "extremo_legitimo",
        "fuente": "ventas",
        "fecha": entrega.fecha.isoformat(),
        "store_nbr": fila["store_nbr"],
        "family": fila["family"],
        "sales": fila["sales"],
    }


def _registro(tipo: str, item: Entrega, entregas: list[date], detalle: str) -> dict[str, Any]:
    return {
        "tipo": tipo,
        "fuente": item.fuente,
        "fecha": item.fecha.isoformat(),
        "entregas": [e.isoformat() for e in entregas],
        "detalle": detalle,
    }


def _tardio(item, regla, rng, salida):
    original = item.entrega
    item.entrega = original + timedelta(days=regla["dias_extra"])
    return _registro("archivo_tardio", item, [item.entrega], f"debía llegar el {original.isoformat()}")


def _parcial(item, regla, rng, salida):
    total = len(item.tabla)
    cantidad = max(1, int(total * regla["fraccion_inicial"]))
    posiciones = np.sort(rng.choice(total, size=cantidad, replace=False))
    resto = np.setdiff1d(np.arange(total), posiciones)
    segunda = item.entrega + timedelta(days=regla["dias_extra"])
    salida.append(Entrega(item.fuente, item.fecha, segunda, item.tabla.iloc[resto]))
    primera, item.tabla = item.entrega, item.tabla.iloc[posiciones]
    return _registro("archivo_parcial", item, [primera, segunda], f"{cantidad} de {total} filas en la primera entrega")


def _duplicado(item, regla, rng, salida):
    repetida = item.entrega + timedelta(days=regla["dias_extra"])
    salida.append(Entrega(item.fuente, item.fecha, repetida, item.tabla))
    return _registro("archivo_duplicado", item, [item.entrega, repetida], "reentrega idéntica")


def _correccion(item, regla, rng, salida):
    corregida = item.entrega + timedelta(days=regla["dias_extra"])
    salida.append(Entrega(item.fuente, item.fecha, corregida, item.tabla))
    filas = min(regla["filas"], len(item.tabla))
    posiciones = np.sort(rng.choice(len(item.tabla), size=filas, replace=False))
    errada = item.tabla.copy()
    columna = errada.columns.get_loc("sales")
    valores = (pd.to_numeric(errada.iloc[posiciones, columna]) + 1) * regla["factor"]
    errada.iloc[posiciones, columna] = [repr(float(v)) for v in valores]
    item.tabla = errada
    return _registro("correccion", item, [item.entrega, corregida], f"{filas} filas erróneas en la primera entrega")


def _invalido(item, regla, rng, salida, variante):
    correcta = item.entrega + timedelta(days=regla["dias_extra"])
    salida.append(Entrega(item.fuente, item.fecha, correcta, item.tabla))
    if variante == 0:
        item.tabla = item.tabla.rename(columns={"sales": "venta"})
        detalle = "columna sales renombrada"
    else:
        rota = item.tabla.copy()
        rota.iloc[0, rota.columns.get_loc("sales")] = "-1.0"
        item.tabla = rota
        detalle = "venta negativa"
    return _registro("dato_invalido", item, [item.entrega, correcta], detalle)


def aplicar(entregas: list[Entrega], reglas: dict[str, Any], semilla: int) -> tuple[list[Entrega], list[dict[str, Any]]]:
    """Aplica los incidentes en fechas distintas. Toda alteración afecta solo a la primera entrega."""
    rng = np.random.default_rng(semilla)
    registro = [_extremo(entregas)] if reglas.get("extremo_legitimo", {}).get("cantidad") else []
    reservadas = {date.fromisoformat(r["fecha"]) for r in registro}
    fechas = sorted({e.fecha for e in entregas if e.fuente == "ventas"} - reservadas)
    total = sum(reglas.get(tipo, {}).get("cantidad", 0) for tipo in ORDEN)
    if total > len(fechas):
        raise ValueError(f"Hay {total} incidentes y solo {len(fechas)} fechas disponibles")
    elegidas = iter(sorted(date.fromisoformat(f) for f in rng.choice([d.isoformat() for d in fechas], size=total, replace=False)))
    orden = rng.permutation(total)
    secuencia = sorted(zip(orden, elegidas))

    indice = {(e.fuente, e.fecha): e for e in entregas if e.fuente in ("ventas", "transacciones")}
    salida = list(entregas)
    posicion = 0
    for tipo in ORDEN:
        regla = reglas.get(tipo, {})
        for numero in range(regla.get("cantidad", 0)):
            fecha = secuencia[posicion][1]
            posicion += 1
            clave = (regla["fuente"], fecha)
            if clave not in indice:
                raise ValueError(f"No hay entrega para el incidente {tipo}: {clave}")
            item = indice[clave]
            if tipo == "fuente_ausente":
                salida.remove(item)
                registro.append(_registro(tipo, item, [], f"{len(item.tabla)} filas no llegan"))
            elif tipo == "dato_invalido":
                registro.append(_invalido(item, regla, rng, salida, numero % 2))
            else:
                funcion = {"archivo_tardio": _tardio, "archivo_parcial": _parcial,
                           "archivo_duplicado": _duplicado, "correccion": _correccion}[tipo]
                registro.append(funcion(item, regla, rng, salida))
    return salida, registro
