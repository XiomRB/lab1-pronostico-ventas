"""Carga y valida la configuración versionada del proyecto."""
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[2]
FUENTES = ("ventas", "transacciones", "promociones", "petroleo", "feriados", "tiendas")


@dataclass(frozen=True)
class Configuracion:
    raiz: Path
    kaggle: Path
    historico: Path
    bandeja: Path
    almacen: Path
    cuarentena: Path
    corte_historico: date
    fin_bandeja: date | None
    semilla: int
    horizonte_dias: int
    dia_corte: int
    fuentes: dict[str, Any]
    incidentes: dict[str, Any]
    validacion: dict[str, Any]


def _leer(ruta: Path) -> dict[str, Any]:
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def _fecha(valor: Any, nombre: str) -> date:
    try:
        return date.fromisoformat(str(valor))
    except ValueError as error:
        raise ValueError(f"{nombre} debe tener formato YYYY-MM-DD: {valor!r}") from error


def _ruta(raiz: Path, valor: str) -> Path:
    ruta = Path(valor)
    return ruta if ruta.is_absolute() else raiz / ruta


def cargar(raiz: Path = RAIZ) -> Configuracion:
    simulacion = _leer(raiz / "config" / "simulacion.yaml")
    fuentes = _leer(raiz / "config" / "fuentes.yaml")
    modelo = _leer(raiz / "config" / "modelo.yaml")
    validacion = _leer(raiz / "config" / "validacion.yaml")

    faltantes = set(FUENTES) - set(fuentes)
    if faltantes:
        raise ValueError(f"Faltan fuentes en fuentes.yaml: {sorted(faltantes)}")
    if modelo["horizonte_dias"] < 1:
        raise ValueError("horizonte_dias debe ser positivo")
    if modelo["dia_corte"] not in range(7):
        raise ValueError("dia_corte debe estar entre 0 y 6")

    corte = _fecha(simulacion["corte_historico"], "corte_historico")
    fin = simulacion.get("fin_bandeja")
    fin = None if fin is None else _fecha(fin, "fin_bandeja")
    if fin is not None and fin <= corte:
        raise ValueError("fin_bandeja debe ser posterior a corte_historico")

    rutas = simulacion["rutas"]
    return Configuracion(
        raiz=raiz,
        kaggle=_ruta(raiz, rutas["kaggle"]),
        historico=_ruta(raiz, rutas["historico"]),
        bandeja=_ruta(raiz, os.environ.get("BANDEJA_DIR") or rutas["bandeja"]),
        almacen=_ruta(raiz, rutas["almacen"]),
        cuarentena=_ruta(raiz, rutas["cuarentena"]),
        corte_historico=corte,
        fin_bandeja=fin,
        semilla=simulacion["semilla"],
        horizonte_dias=modelo["horizonte_dias"],
        dia_corte=modelo["dia_corte"],
        fuentes=fuentes,
        incidentes=simulacion["incidentes"],
        validacion=validacion,
    )
