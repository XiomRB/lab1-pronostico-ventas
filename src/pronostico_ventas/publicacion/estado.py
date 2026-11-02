"""Estado operativo de cada publicación, separado del manifiesto inmutable."""
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from pronostico_ventas.config import Configuracion

ESTADOS = ("PUBLICADA", "VERSIONADA", "RESPALDADA", "RESPALDO_FALLIDO")


def _ruta(cfg: Configuracion, corte: date, revision: int) -> Path:
    return cfg.estado_publicaciones / f"corte={corte.isoformat()}_rev={revision}.json"


def _escribir(ruta: Path, datos: dict[str, Any]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.tmp")
    temporal.write_text(json.dumps(datos, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporal, ruta)


def marcar(cfg: Configuracion, corte: date, revision: int, nombre: str, error: str | None = None, paso: str | None = None) -> None:
    if nombre not in ESTADOS:
        raise ValueError(f"Estado desconocido: {nombre}")
    _escribir(_ruta(cfg, corte, revision), {
        "corte": corte.isoformat(), "revision": revision, "estado": nombre, "error": error, "paso": paso,
    })


def leer(cfg: Configuracion, corte: date, revision: int) -> dict[str, Any] | None:
    ruta = _ruta(cfg, corte, revision)
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else None


def guardar_omision(cfg: Configuracion, corte: date, motivo: dict[str, Any]) -> None:
    _escribir(cfg.estado_publicaciones / f"corte={corte.isoformat()}_omitida.json", motivo)


def pendientes(cfg: Configuracion) -> list[dict[str, Any]]:
    """Publicaciones que todavía no están respaldadas."""
    if not cfg.estado_publicaciones.is_dir():
        return []
    registros = (json.loads(r.read_text(encoding="utf-8")) for r in sorted(cfg.estado_publicaciones.glob("corte=*_rev=*.json")))
    return [r for r in registros if r["estado"] != "RESPALDADA"]


def hay_fallo(cfg: Configuracion, corte: date) -> bool:
    return any(r["corte"] == corte.isoformat() and r["estado"] == "RESPALDO_FALLIDO" for r in pendientes(cfg))
