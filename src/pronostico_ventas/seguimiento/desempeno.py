"""Seguimiento: compara lo publicado con las ventas reales conocidas en una fecha."""
import json
import os
from datetime import date
from typing import Any

import pandas as pd

from pronostico_ventas.config import Configuracion
from pronostico_ventas.evaluacion import metricas
from pronostico_ventas.features.construccion import objetivos
from pronostico_ventas.publicacion.publicar import carpeta, revisiones

CLAVES = ["date", "store_nbr", "family"]


def _cortes(cfg: Configuracion) -> list[date]:
    if not cfg.publicado.is_dir():
        return []
    return sorted(date.fromisoformat(r.name.split("=")[1]) for r in cfg.publicado.glob("corte=*") if r.is_dir())


def _medir(cfg: Configuracion, corte: date, revision: int, reales: pd.DataFrame) -> dict[str, Any]:
    base = carpeta(cfg, corte, revision)
    pronostico = pd.read_parquet(base / "pronostico.parquet")
    pedido = pd.read_parquet(base / "pedido.parquet")
    unido = pronostico.merge(reales, on=CLAVES)  # una venta aún desconocida no se compara ni cuenta como 0
    medida: dict[str, Any] = {
        "corte": corte.isoformat(), "revision": revision, "dias_con_real": int(unido["date"].nunique()),
        "filas_comparadas": len(unido), "filas_publicadas": len(pronostico), "wape": None, "cobertura_p10_p90": None,
        "pinball_p50": None, "costo_pedido": None, "periodo_completo": False,
    }
    if unido.empty:
        return medida
    y, p = unido["sales"].to_numpy("float64"), unido["pronostico"].to_numpy("float64")
    medida.update({
        "wape": metricas.wape(y, p),
        "cobertura_p10_p90": metricas.cobertura_intervalo(y, unido["p10"].to_numpy(), unido["p90"].to_numpy()),
        "pinball_p50": metricas.pinball(y, unido["p50"].to_numpy("float64"), 0.5),
    })
    desde, hasta = cfg.modelo["cobertura"]["desde_dia"], cfg.modelo["cobertura"]["hasta_dia"]
    dias = hasta - desde + 1
    cubiertos = unido[unido["h"].between(desde, hasta)]
    demanda = cubiertos.groupby(["store_nbr", "family"], as_index=False, observed=True).agg(real=("sales", "sum"), dias=("h", "size"))
    demanda = demanda[demanda["dias"] == dias]
    if len(demanda) == len(pedido):
        cruzado = pedido.merge(demanda, on=["store_nbr", "family"])
        real, ordenado = cruzado["real"].to_numpy("float64"), cruzado["pedido"].to_numpy("float64")
        medida.update({
            "periodo_completo": True,
            "costo_pedido": metricas.costo_negocio(real, ordenado, cruzado["cu"].to_numpy(), cruzado["co"].to_numpy()),
            "cobertura_q": float((real <= ordenado).mean()),
        })
    return medida


def actualizar(cfg: Configuracion, fecha: date) -> dict[str, Any]:
    """Recalcula el seguimiento con lo conocido en `fecha`. Repetirlo da el mismo resultado."""
    cortes = [c for c in _cortes(cfg) if c <= fecha]
    medidas = []
    if cortes:
        reales = objetivos(cfg, fecha, cortes[0], fecha)
        for corte in cortes:
            existentes = revisiones(cfg, corte)
            for revision in sorted({existentes[0], existentes[-1]}):
                medidas.append(_medir(cfg, corte, revision, reales))
    informe = {"fecha": fecha.isoformat(), "publicaciones": medidas}
    cfg.seguimiento.mkdir(parents=True, exist_ok=True)
    destino = cfg.seguimiento / f"seguimiento_{fecha.isoformat()}.json"
    temporal = destino.with_name(f".{destino.name}.tmp")
    temporal.write_text(json.dumps(informe, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporal, destino)
    return informe


def reporte(informe: dict[str, Any]) -> str:
    """Resumen legible, sin filas de datos."""
    filas = ["| Corte | Rev. | Días con real | WAPE | Cobertura P10-P90 | Costo del pedido | Cobertura Q* |", "|---|---|---|---|---|---|---|"]
    cifra = lambda v, f: "pendiente" if v is None else format(v, f)
    for m in informe["publicaciones"]:
        filas.append(f"| {m['corte']} | {m['revision']} | {m['dias_con_real']} | {cifra(m['wape'], '.3f')} | {cifra(m['cobertura_p10_p90'], '.3f')} | {cifra(m['costo_pedido'], ',.0f')} | {cifra(m.get('cobertura_q'), '.3f')} |")
    return f"# Seguimiento del desempeño al {informe['fecha']}\n\n" + "\n".join(filas) + "\n"
