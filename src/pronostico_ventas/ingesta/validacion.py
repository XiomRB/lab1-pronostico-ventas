"""Validación de un archivo de la bandeja. No escribe nada."""
import re
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd

FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass
class Resultado:
    tabla: pd.DataFrame | None = None
    errores: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Referencia:
    """Conocimiento previo para distinguir situaciones esperadas de datos inválidos."""

    familias: frozenset[str] = frozenset()
    tiendas: frozenset[int] = frozenset()
    filas_por_dia: int = 0
    umbrales_venta: dict[str, float] = field(default_factory=dict)


def _numeros(serie: pd.Series) -> pd.Series:
    numeros = pd.to_numeric(serie.where(serie != ""), errors="coerce")
    return numeros.where(np.isfinite(numeros))


def _validar_fechas(tabla: pd.DataFrame, regla: str, fecha: date, errores: list[str]) -> None:
    if regla == "ninguna":
        return
    valores = tabla["date"]
    if not valores.map(lambda v: bool(FECHA.fullmatch(v))).all() or pd.to_datetime(valores, errors="coerce", format="%Y-%m-%d").isna().any():
        errores.append("fecha_invalida")
    elif regla == "nombre" and (valores != fecha.isoformat()).any():
        errores.append("fecha_distinta_al_nombre")
    elif regla == "posterior" and (valores <= fecha.isoformat()).any():
        errores.append("plan_incluye_fechas_ya_ocurridas")


def _validar_numeros(tabla: pd.DataFrame, reglas: dict[str, Any], errores: list[str]) -> None:
    nulos = set(reglas.get("admite_nulos", []))
    for columna in reglas.get("enteras", []) + reglas.get("decimales", []):
        numeros = _numeros(tabla[columna])
        invalidos = numeros.isna()
        if columna in nulos:
            invalidos &= tabla[columna] != ""
        if invalidos.any():
            errores.append(f"valor_no_numerico:{columna}")
        elif columna in reglas.get("enteras", []) and (numeros.dropna() % 1 != 0).any():
            errores.append(f"valor_no_entero:{columna}")
    for columna in reglas.get("no_negativas", []):
        if (_numeros(tabla[columna]) < 0).any():
            errores.append(f"valor_negativo:{columna}")


def _validar_categorias(fuente: str, tabla: pd.DataFrame, cfg: dict[str, Any], errores: list[str]) -> None:
    if fuente != "feriados":
        return
    if not tabla["type"].isin(cfg["tipos_feriado"]).all():
        errores.append("tipo_de_feriado_desconocido")
    if not tabla["locale"].isin(cfg["locales_feriado"]).all():
        errores.append("alcance_de_feriado_desconocido")
    if not tabla["transferred"].isin(["True", "False"]).all():
        errores.append("transferred_invalido")


def _advertir_ventas(tabla: pd.DataFrame, referencia: Referencia, advertencias: list[str]) -> None:
    ventas = _numeros(tabla["sales"])
    if referencia.filas_por_dia and len(tabla) < referencia.filas_por_dia:
        advertencias.append(f"archivo_parcial:{len(tabla)}_de_{referencia.filas_por_dia}")
    umbrales = tabla["family"].map(referencia.umbrales_venta)
    if (ventas > umbrales).any():
        advertencias.append(f"valor_extremo:{int((ventas > umbrales).sum())}")
    if referencia.familias and not set(tabla["family"]) <= referencia.familias:
        advertencias.append("familia_desconocida")
    con_venta = _numeros(tabla["store_nbr"])[ventas > 0]
    if referencia.tiendas and not set(con_venta.astype(int)) <= referencia.tiendas:
        advertencias.append("tienda_desconocida")


def validar(fuente: str, fecha: date, entrega: date, contenido: bytes, cfg: dict[str, Any], referencia: Referencia) -> Resultado:
    """Devuelve la tabla válida, o los errores que la dejan en cuarentena."""
    reglas = cfg["fuentes"][fuente]
    resultado = Resultado()
    try:
        tabla = pd.read_csv(BytesIO(contenido), dtype=str, keep_default_na=False)
    except (ValueError, UnicodeDecodeError, pd.errors.EmptyDataError) as error:
        resultado.errores.append(f"archivo_ilegible:{type(error).__name__}")
        return resultado

    faltantes = [c for c in reglas["requeridas"] if c not in tabla.columns]
    if faltantes:
        resultado.errores.append(f"columnas_faltantes:{','.join(faltantes)}")
        return resultado
    conocidas = reglas["requeridas"] + reglas.get("opcionales", [])
    extras = [c for c in tabla.columns if c not in conocidas]
    if extras:
        resultado.advertencias.append(f"columnas_ignoradas:{','.join(extras)}")
    tabla = tabla[[c for c in conocidas if c in tabla.columns]]
    if tabla.empty:
        resultado.errores.append("archivo_vacio")
        return resultado

    if reglas.get("entrega_posterior") and entrega < fecha:
        resultado.errores.append("entrega_anterior_a_la_fecha")
    _validar_fechas(tabla, reglas["fecha"], fecha, resultado.errores)
    _validar_numeros(tabla, reglas, resultado.errores)
    _validar_categorias(fuente, tabla, cfg, resultado.errores)

    filas = len(tabla)
    tabla = tabla.drop_duplicates()
    if len(tabla) < filas:
        resultado.advertencias.append(f"filas_repetidas:{filas - len(tabla)}")
    if tabla.duplicated(reglas["clave"]).any():
        resultado.errores.append("claves_en_conflicto")

    if resultado.errores:
        return resultado
    if fuente == "ventas":
        _advertir_ventas(tabla, referencia, resultado.advertencias)
    resultado.tabla = tabla
    return resultado
