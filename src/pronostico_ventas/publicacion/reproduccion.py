"""Reproduce una publicación pasada: recalcula con el mismo modelo y lo conocido en su fecha."""
import json
from datetime import date
from typing import Any

from pronostico_ventas.config import Configuracion
from pronostico_ventas.publicacion import entrenamiento
from pronostico_ventas.publicacion.publicar import calcular, canonico, carpeta


def reproducir(cfg: Configuracion, corte: date, revision: int) -> dict[str, Any]:
    """Compara con el manifiesto. No escribe nada en `data/publicado`."""
    manifiesto = json.loads((carpeta(cfg, corte, revision) / "manifest.json").read_text(encoding="utf-8"))
    modelo, calibrador, meta = entrenamiento.cargar(cfg, manifiesto["modelo"]["id"])
    if meta["hash_modelo"] != manifiesto["modelo"]["hash"]:
        raise ValueError("El modelo disponible no es el de la publicación")
    conocido = date.fromisoformat(manifiesto["datos"]["as_of"])
    pronostico, pedido = calcular(cfg, corte, modelo, calibrador, conocido)
    resultado = {
        "hash_pronostico": canonico(pronostico),
        "hash_pedido": canonico(pedido),
        "esperado_pronostico": manifiesto["hash_pronostico"],
        "esperado_pedido": manifiesto["hash_pedido"],
    }
    resultado["identico"] = (
        resultado["hash_pronostico"] == resultado["esperado_pronostico"]
        and resultado["hash_pedido"] == resultado["esperado_pedido"]
    )
    return resultado
