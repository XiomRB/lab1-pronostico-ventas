"""Tareas del producto, sin dependencia de Airflow. Los DAGs solo las invocan."""
import json
from datetime import date, timedelta
from typing import Any

from pronostico_ventas import config
from pronostico_ventas.evaluacion.comparacion import comparar, guardar
from pronostico_ventas.features.construccion import obtener
from pronostico_ventas.ingesta.proceso import ingerir
from pronostico_ventas.publicacion import entrenamiento, estado, publicar, versionado
from pronostico_ventas.seguimiento import desempeno


def es_corte(fecha: date, cfg: config.Configuracion | None = None) -> bool:
    return fecha.weekday() == (cfg or config.cargar()).modelo["dia_corte"]


def tarea_ingesta(fecha: date) -> dict[str, Any]:
    return ingerir(config.cargar(), fecha)


def tarea_preparacion(fecha: date) -> str:
    """Construye el panel del corte. Es idempotente: el pasado conocido no cambia."""
    cfg = config.cargar()
    if not es_corte(fecha, cfg):
        return "sin_corte"
    obtener(cfg, fecha)
    return "panel_listo"


def _elegido(cfg: config.Configuracion) -> str:
    ruta = cfg.reportes / "comparacion_modelos.json"
    if ruta.is_file():
        return json.loads(ruta.read_text(encoding="utf-8"))["modelo_elegido"]
    return cfg.modelo["vigente_inicial"]


def tarea_asegurar_modelo(fecha: date) -> str:
    """En la primera ejecución entrena el modelo elegido con lo conocido al corte histórico."""
    cfg = config.cargar()
    if (cfg.modelos / "vigente.json").is_file():
        return entrenamiento.leer_vigente(cfg)
    meta = entrenamiento.entrenar(cfg, _elegido(cfg), cfg.corte_historico)
    entrenamiento.fijar_vigente(cfg, meta["id"])
    return meta["id"]


def tarea_pronostico(fecha: date) -> dict[str, Any]:
    cfg = config.cargar()
    resultado = publicar.publicar(cfg, fecha)
    return {k: v for k, v in resultado.items() if k != "manifiesto"}


def tarea_reproceso(fecha: date, corte: date) -> dict[str, Any]:
    cfg = config.cargar()
    resultado = publicar.publicar(cfg, corte, reprocesar_en=fecha)
    return {k: v for k, v in resultado.items() if k != "manifiesto"}


def tarea_revisiones(fecha: date) -> list[dict[str, Any]]:
    """Revisa el último corte si una corrección llegó antes de que empiece su cobertura."""
    cfg = config.cargar()
    ultimo = fecha - timedelta(days=(fecha.weekday() - cfg.modelo["dia_corte"]) % 7)
    inicio = ultimo + timedelta(days=cfg.modelo["cobertura"]["desde_dia"])
    if fecha >= inicio or fecha == ultimo or not publicar.revisiones(cfg, ultimo):
        return []
    resultado = publicar.publicar(cfg, ultimo, reprocesar_en=fecha)
    return [{k: v for k, v in resultado.items() if k != "manifiesto"}]


def tarea_versionado(fecha: date) -> list[str]:
    """Versiona y respalda lo pendiente. Un fallo queda registrado y la tarea termina en error."""
    return versionado.reconciliar(config.cargar())


def tarea_seguimiento(fecha: date) -> int:
    cfg = config.cargar()
    informe = desempeno.actualizar(cfg, fecha)
    cfg.reportes.mkdir(parents=True, exist_ok=True)
    (cfg.reportes / "seguimiento.md").write_text(desempeno.reporte(informe), encoding="utf-8")
    return len(informe["publicaciones"])


def tarea_entrenamiento(fecha: date) -> str:
    """Cada cuatro semanas entrena un modelo nuevo del tipo elegido, solo con lo conocido."""
    cfg = config.cargar()
    semanas = (fecha - cfg.corte_historico).days // 7
    if not es_corte(fecha, cfg) or semanas == 0 or semanas % 4 != 0:
        return "sin_entrenamiento"
    vigente = entrenamiento.leer_vigente(cfg)
    meta = entrenamiento.entrenar(cfg, vigente.rsplit("_", 1)[0], fecha)
    entrenamiento.fijar_vigente(cfg, meta["id"])
    return meta["id"]


def tarea_cierre(fecha: date) -> str:
    """Deja la corrida en rojo si alguna publicación del día no quedó respaldada."""
    cfg = config.cargar()
    if estado.hay_fallo(cfg, fecha):
        raise RuntimeError(f"Publicación del {fecha} con RESPALDO_FALLIDO")
    return "ok"
