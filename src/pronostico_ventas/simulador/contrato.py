"""Contrato provisional de la bandeja: nombres de archivo y columnas por fuente."""
import re
from dataclasses import dataclass
from datetime import date

COLUMNAS = {
    "ventas": ["id", "date", "store_nbr", "family", "sales", "onpromotion"],
    "transacciones": ["date", "store_nbr", "transactions"],
    "promociones": ["date", "store_nbr", "family", "onpromotion"],
    "petroleo": ["date", "dcoilwtico"],
    "feriados": ["date", "type", "locale", "locale_name", "description", "transferred"],
    "tiendas": ["store_nbr", "city", "state", "type", "cluster"],
}
_NOMBRE = re.compile(
    r"(?P<fuente>[a-z]+)_(?P<fecha>\d{4}-\d{2}-\d{2})(?:__entrega_(?P<entrega>\d{4}-\d{2}-\d{2}))?\.csv"
)


@dataclass(frozen=True)
class ArchivoBandeja:
    fuente: str
    fecha: date
    entrega: date | None


def nombre_archivo(fuente: str, fecha: date, entrega: date) -> str:
    return f"{fuente}_{fecha.isoformat()}__entrega_{entrega.isoformat()}.csv"


def interpretar_nombre(nombre: str) -> ArchivoBandeja:
    """Interpreta un nombre con o sin entrega explícita. Sin ella, `entrega` es None."""
    coincidencia = _NOMBRE.fullmatch(nombre)
    if coincidencia is None or coincidencia["fuente"] not in COLUMNAS:
        raise ValueError(f"Nombre fuera de contrato: {nombre}")
    entrega = coincidencia["entrega"]
    return ArchivoBandeja(
        fuente=coincidencia["fuente"],
        fecha=date.fromisoformat(coincidencia["fecha"]),
        entrega=date.fromisoformat(entrega) if entrega else None,
    )
