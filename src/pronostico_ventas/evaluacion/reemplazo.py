"""Criterio explícito para reemplazar el modelo vigente."""
from typing import Any


def evaluar(candidato: dict[str, Any], vigente: dict[str, Any], reglas: dict[str, Any]) -> dict[str, Any]:
    """Compara resúmenes con los mismos cortes. El candidato debe cumplir todas las condiciones."""
    costos_c, costos_v = candidato["costo_por_corte"], vigente["costo_por_corte"]
    if len(costos_c) != len(costos_v):
        raise ValueError("Los modelos deben compararse con los mismos cortes")
    total_c, total_v = sum(costos_c), sum(costos_v)
    mejora = 1 - total_c / total_v
    ganados = sum(c < v for c, v in zip(costos_c, costos_v))
    inferior, superior = reglas["cobertura_intervalo"]
    tolerancia = reglas["tolerancia_q"]
    condiciones = {
        "costo": mejora >= reglas["mejora_costo_minima"],
        "wape": candidato["wape"] <= vigente["wape"] * (1 + reglas["tolerancia_wape"]),
        "pinball": candidato["pinball"] <= vigente["pinball"],
        "cortes_ganados": ganados >= reglas["cortes_ganados_minimo"],
        "cobertura_intervalo": inferior <= candidato["cobertura_intervalo"] <= superior,
        "cobertura_q": all(abs(g["cobertura"] - g["objetivo"]) <= tolerancia for g in candidato["cobertura_q"]),
    }
    return {"reemplaza": all(condiciones.values()), "condiciones": condiciones, "mejora_costo": mejora, "cortes_ganados": ganados}
