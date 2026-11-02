"""Entrena un modelo para producción y lo deja listo para publicar."""
import hashlib
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import joblib

from pronostico_ventas.calibracion import residuos
from pronostico_ventas.config import Configuracion
from pronostico_ventas.evaluacion.comparacion import con_objetivo
from pronostico_ventas.evaluacion.memoria import LimiteMemoria
from pronostico_ventas.modelos.base import crear


def cortes_de_entrenamiento(cfg: Configuracion, referencia: date) -> tuple[list[date], list[date]]:
    """Cortes de entrenamiento y calibración cuyos objetivos ya se conocen en `referencia`."""
    horizonte = cfg.modelo["horizonte_dias"]
    separacion = horizonte // 7 + 1
    dias = (referencia.weekday() - cfg.modelo["dia_corte"]) % 7
    ultimo = referencia - timedelta(days=dias)
    calibrar = [ultimo - timedelta(weeks=separacion + i) for i in range(cfg.modelo["validacion"]["cortes_calibracion"])][::-1]
    entrenamiento = cfg.modelo["entrenamiento"]
    primero = date.fromisoformat(entrenamiento["primer_corte"])
    semanas = entrenamiento["paso_semanas"]
    limite = calibrar[0] - timedelta(days=horizonte + 1)
    todos = [primero + timedelta(weeks=semanas * i) for i in range(10_000)]
    return [c for c in todos if c <= limite], calibrar


def hash_archivo(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def entrenar(cfg: Configuracion, nombre: str, referencia: date) -> dict[str, Any]:
    """Calibra fuera de muestra y después reentrena con todo lo conocido en `referencia`."""
    identificador = f"{nombre}_{referencia.isoformat()}"
    carpeta = cfg.modelos / identificador
    if (carpeta / "meta.json").is_file():
        return json.loads((carpeta / "meta.json").read_text(encoding="utf-8"))

    entrenar_cortes, calibrar_cortes = cortes_de_entrenamiento(cfg, referencia)
    with LimiteMemoria(cfg.modelo["limite_memoria_mb"]) as limite:
        modelo = crear(nombre, cfg.modelo)
        datos = con_objetivo(cfg, entrenar_cortes, calibrar_cortes[0]).dropna(subset=["y"])
        modelo.ajustar(datos, datos["y"].to_numpy("float64"))
        del datos
        calibracion = con_objetivo(cfg, calibrar_cortes, referencia)
        calibracion["p"] = modelo.predecir(calibracion)
        calibrador = residuos.ajustar(calibracion, cfg.modelo)
        del calibracion
        final = crear(nombre, cfg.modelo)
        completos = con_objetivo(cfg, entrenar_cortes + calibrar_cortes, referencia).dropna(subset=["y"])
        final.ajustar(completos, completos["y"].to_numpy("float64"))

    carpeta.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, carpeta / "modelo.joblib", compress=3)
    joblib.dump(calibrador, carpeta / "calibrador.joblib", compress=3)
    meta = {
        "id": identificador,
        "nombre": nombre,
        "referencia": referencia.isoformat(),
        "hash_modelo": hash_archivo(carpeta / "modelo.joblib"),
        "hash_calibrador": hash_archivo(carpeta / "calibrador.joblib"),
        "pico_memoria_mb": limite.pico_mb,
    }
    temporal = carpeta / ".meta.json.tmp"
    temporal.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporal, carpeta / "meta.json")
    return meta


def fijar_vigente(cfg: Configuracion, identificador: str) -> None:
    cfg.modelos.mkdir(parents=True, exist_ok=True)
    temporal = cfg.modelos / ".vigente.json.tmp"
    temporal.write_text(json.dumps({"id": identificador}, sort_keys=True), encoding="utf-8")
    os.replace(temporal, cfg.modelos / "vigente.json")


def leer_vigente(cfg: Configuracion) -> str:
    return json.loads((cfg.modelos / "vigente.json").read_text(encoding="utf-8"))["id"]


def cargar(cfg: Configuracion, identificador: str) -> tuple[Any, residuos.Calibrador, dict[str, Any]]:
    carpeta = cfg.modelos / identificador
    meta = json.loads((carpeta / "meta.json").read_text(encoding="utf-8"))
    return joblib.load(carpeta / "modelo.joblib"), joblib.load(carpeta / "calibrador.joblib"), meta
