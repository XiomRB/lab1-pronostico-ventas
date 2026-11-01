"""Comparación de modelos con los mismos cortes temporales."""
import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from pronostico_ventas.calibracion import residuos
from pronostico_ventas.config import Configuracion
from pronostico_ventas.evaluacion import metricas, reemplazo
from pronostico_ventas.evaluacion.memoria import LimiteMemoria
from pronostico_ventas.features.construccion import obtener, objetivos
from pronostico_ventas.modelos.base import crear
from pronostico_ventas.pedido import politica

CLAVES = ["date", "store_nbr", "family"]


@dataclass(frozen=True)
class Particion:
    prueba: date
    calibracion: list[date]
    entrenamiento: list[date]


def particiones(cfg: Configuracion) -> list[Particion]:
    """Mismos cortes para todos los modelos. Entrenamiento, calibración y prueba no se solapan."""
    validacion, entrenamiento = cfg.modelo["validacion"], cfg.modelo["entrenamiento"]
    horizonte = cfg.modelo["horizonte_dias"]
    ultimo = date.fromisoformat(validacion["ultimo_corte"])
    if ultimo + timedelta(days=horizonte) > cfg.corte_historico:
        raise ValueError("Los cortes de validación no pueden usar el periodo de reserva")
    pruebas = [ultimo - timedelta(weeks=validacion["paso_semanas"] * i) for i in range(validacion["cortes"])][::-1]
    separacion = horizonte // 7 + 1
    primero = date.fromisoformat(entrenamiento["primer_corte"])
    resultado = []
    for prueba in pruebas:
        calibrar = [prueba - timedelta(weeks=separacion + i) for i in range(validacion["cortes_calibracion"])][::-1]
        limite = calibrar[0] - timedelta(days=horizonte + 1)
        semanas = entrenamiento["paso_semanas"]
        cortes = [primero + timedelta(weeks=semanas * i) for i in range(10_000) if primero + timedelta(weeks=semanas * i) <= limite]
        resultado.append(Particion(prueba, calibrar, cortes))
    return resultado


def con_objetivo(cfg: Configuracion, cortes: list[date], conocido: date) -> pd.DataFrame:
    paneles = pd.concat([obtener(cfg, c) for c in cortes], ignore_index=True)
    reales = objetivos(cfg, conocido, cortes[0], max(cortes) + timedelta(days=cfg.modelo["horizonte_dias"]))
    unido = paneles.merge(reales.rename(columns={"sales": "y"}), how="left", on=CLAVES)
    return unido.astype({"y": "float32"})


def preparar(modelo: Any, cfg: Configuracion, particion: Particion) -> residuos.Calibrador:
    """Entrena con cortes previos y calibra con cortes posteriores al entrenamiento."""
    inicio_calibracion = particion.calibracion[0]
    entrenar = con_objetivo(cfg, particion.entrenamiento, inicio_calibracion).dropna(subset=["y"])
    modelo.ajustar(entrenar, entrenar["y"].to_numpy("float64"))
    del entrenar
    calibrar = con_objetivo(cfg, particion.calibracion, particion.prueba)
    calibrar["p"] = modelo.predecir(calibrar)
    return residuos.ajustar(calibrar, cfg.modelo)


def medir_corte(modelo: Any, calibrador: residuos.Calibrador, cfg: Configuracion, prueba: date) -> dict[str, Any]:
    horizonte, cobertura = cfg.modelo["horizonte_dias"], cfg.modelo["cobertura"]
    datos = con_objetivo(cfg, [prueba], prueba + timedelta(days=horizonte + 1)).dropna(subset=["y"])
    datos["p"] = modelo.predecir(datos)
    y, p = datos["y"].to_numpy("float64"), datos["p"].to_numpy()
    cuantiles = {n: calibrador.cuantil_diario(datos, n) for n in cfg.modelo["niveles_cuantil"]}
    niveles = sorted(cuantiles)
    periodo = residuos.agregar_periodo(datos, cobertura["desde_dia"], cobertura["hasta_dia"]).dropna(subset=["y"])
    pedido = politica.calcular(periodo, calibrador, cfg.costos)
    demanda = pedido["y"].to_numpy("float64")
    costo = metricas.costo_negocio(demanda, pedido["pedido"].to_numpy(), pedido["cu"].to_numpy(), pedido["co"].to_numpy())
    grupos = [
        {"objetivo": float(q), "cubiertos": int((g["y"] <= g["pedido"]).sum()), "total": len(g)}
        for q, g in pedido.groupby("q_critico")
    ]
    return {
        "corte": prueba.isoformat(),
        "filas": len(datos),
        "suma_abs_error": float(np.abs(y - p).sum()),
        "suma_real": float(y.sum()),
        "rmsle": metricas.rmsle(y, p),
        "pinball": {str(n): metricas.pinball(y, c, n) for n, c in cuantiles.items()},
        "dentro_intervalo": int(((y >= cuantiles[niveles[0]]) & (y <= cuantiles[niveles[-1]])).sum()),
        "cruces": int(sum((cuantiles[a] > cuantiles[b] + 1e-9).sum() for a, b in zip(niveles, niveles[1:]))),
        "costo": costo,
        "grupos_q": grupos,
        "hash_predicciones": hashlib.sha256(np.round(p, 6).tobytes()).hexdigest()[:16],
    }


def resumir(cortes: list[dict[str, Any]]) -> dict[str, Any]:
    filas = sum(c["filas"] for c in cortes)
    pinball = np.mean([np.mean(list(c["pinball"].values())) for c in cortes])
    objetivos_q = sorted({g["objetivo"] for c in cortes for g in c["grupos_q"]})
    return {
        "wape": sum(c["suma_abs_error"] for c in cortes) / sum(c["suma_real"] for c in cortes),
        "rmsle": float(np.mean([c["rmsle"] for c in cortes])),
        "pinball": float(pinball),
        "cobertura_intervalo": sum(c["dentro_intervalo"] for c in cortes) / filas,
        "cobertura_q": [
            {
                "objetivo": q,
                "cobertura": sum(g["cubiertos"] for c in cortes for g in c["grupos_q"] if g["objetivo"] == q)
                / sum(g["total"] for c in cortes for g in c["grupos_q"] if g["objetivo"] == q),
            }
            for q in objetivos_q
        ],
        "costo_por_corte": [c["costo"] for c in cortes],
        "costo_total": sum(c["costo"] for c in cortes),
        "cruces": sum(c["cruces"] for c in cortes),
    }


def comparar(cfg: Configuracion, nombres: list[str] | None = None) -> dict[str, Any]:
    """Evalúa cada modelo en serie, bajo el límite de memoria, y aplica el criterio de reemplazo."""
    nombres = nombres or [cfg.modelo["vigente_inicial"], *cfg.modelo["candidatos"]]
    grupos = particiones(cfg)
    salida: dict[str, Any] = {"cortes": [p.prueba.isoformat() for p in grupos], "modelos": {}}
    for nombre in nombres:
        with LimiteMemoria(cfg.modelo["limite_memoria_mb"]) as limite:
            cortes = []
            for particion in grupos:
                modelo = crear(nombre, cfg.modelo)
                calibrador = preparar(modelo, cfg, particion)
                cortes.append(medir_corte(modelo, calibrador, cfg, particion.prueba))
                print(f"{nombre} {particion.prueba}: costo {cortes[-1]['costo']:.0f}", flush=True)
        salida["modelos"][nombre] = {**resumir(cortes), "pico_memoria_mb": limite.pico_mb, "detalle": cortes}
    vigente = salida["modelos"][cfg.modelo["vigente_inicial"]]
    decisiones = {
        n: reemplazo.evaluar(r, vigente, cfg.modelo["reemplazo"])
        for n, r in salida["modelos"].items() if n != cfg.modelo["vigente_inicial"]
    }
    aprobados = [n for n, d in decisiones.items() if d["reemplaza"]]
    salida["decisiones"] = decisiones
    salida["modelo_elegido"] = min(aprobados, key=lambda n: salida["modelos"][n]["costo_total"]) if aprobados else cfg.modelo["vigente_inicial"]
    return salida


def guardar(cfg: Configuracion, resultado: dict[str, Any]) -> None:
    cfg.reportes.mkdir(parents=True, exist_ok=True)
    ruta = cfg.reportes / "comparacion_modelos.json"
    ruta.write_text(json.dumps(resultado, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
