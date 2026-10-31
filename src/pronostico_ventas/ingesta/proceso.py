"""Registra las entregas disponibles en una fecha lógica. La bandeja solo se lee."""
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from pronostico_ventas.almacen import consulta
from pronostico_ventas.config import Configuracion
from pronostico_ventas.ingesta.validacion import Referencia, validar
from pronostico_ventas.simulador.bandeja import entrega_diaria, entrega_habil
from pronostico_ventas.simulador.contrato import ArchivoBandeja, interpretar_nombre, nombre_archivo
from pronostico_ventas.simulador.historico import tipar


@dataclass(frozen=True)
class Pendiente:
    ruta: Path
    archivo: ArchivoBandeja | None
    entrega: date | None


def _escribir_atomico(ruta: Path, contenido: bytes) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.tmp")
    temporal.write_bytes(contenido)
    os.replace(temporal, ruta)


def _guardar_json(ruta: Path, datos: dict[str, Any]) -> None:
    _escribir_atomico(ruta, json.dumps(datos, indent=2, sort_keys=True, ensure_ascii=False).encode())


def _entrega_prevista(archivo: ArchivoBandeja, fuentes: dict[str, Any]) -> date:
    if archivo.entrega is not None:
        return archivo.entrega
    reglas = fuentes[archivo.fuente]
    if reglas["frecuencia"] == "diaria":
        return entrega_diaria(archivo.fecha, reglas["retraso_dias"])
    if reglas["frecuencia"] == "habil":
        return entrega_habil(archivo.fecha, reglas["retraso_dias"])
    return archivo.fecha


def _disponibles(cfg: Configuracion, fecha_logica: date) -> list[Pendiente]:
    """Archivos ya entregados en la fecha lógica, en orden determinista."""
    if not cfg.bandeja.is_dir():
        return []
    pendientes = []
    for ruta in sorted(r for r in cfg.bandeja.iterdir() if r.is_file()):
        try:
            archivo = interpretar_nombre(ruta.name)
        except ValueError:
            pendientes.append(Pendiente(ruta, None, None))
            continue
        entrega = _entrega_prevista(archivo, cfg.fuentes)
        if entrega <= fecha_logica:
            pendientes.append(Pendiente(ruta, archivo, entrega))
    return sorted(pendientes, key=lambda p: (p.entrega or date.min, p.ruta.name))


def _cargar_registro(cfg: Configuracion) -> dict[str, dict[str, Any]]:
    carpeta = cfg.almacen / "registro"
    if not carpeta.is_dir():
        return {}
    registro = {}
    for ruta in sorted(carpeta.glob("*.json")):
        entrada = json.loads(ruta.read_text(encoding="utf-8"))
        registro[entrada["id"]] = entrada
    return registro


def _estadisticas_historicas(cfg: Configuracion) -> dict[str, Any]:
    """Resumen del histórico, calculado una vez porque el histórico no cambia."""
    ruta = cfg.almacen / "referencia_historica.json"
    if ruta.is_file():
        return json.loads(ruta.read_text(encoding="utf-8"))
    ventas = pd.read_parquet(cfg.historico / "ventas.parquet", columns=["date", "family", "sales"])
    tiendas = pd.read_parquet(cfg.historico / "tiendas.parquet", columns=["store_nbr"])
    estadisticas = {
        "familias": sorted(ventas["family"].unique().tolist()),
        "tiendas": sorted(int(t) for t in tiendas["store_nbr"]),
        "filas_por_dia": int(ventas.groupby("date").size().mode().iloc[0]),
        "umbrales_venta": {
            familia: float(valor)
            for familia, valor in ventas.groupby("family")["sales"].quantile(cfg.validacion["cuantil_extremo"]).items()
        },
    }
    _guardar_json(ruta, estadisticas)
    return estadisticas


def _referencia(cfg: Configuracion, registro: dict[str, dict[str, Any]]) -> Referencia:
    base = _estadisticas_historicas(cfg)
    nuevas = {
        int(tienda)
        for entrada in registro.values()
        if entrada["fuente"] == "tiendas" and entrada["estado"] == "aceptado"
        for tienda in entrada.get("claves", [])
    }
    return Referencia(
        familias=frozenset(base["familias"]),
        tiendas=frozenset(base["tiendas"]) | nuevas,
        filas_por_dia=base["filas_por_dia"],
        umbrales_venta=base["umbrales_venta"],
    )


def _guardar_en_almacen(cfg: Configuracion, fuente: str, fecha: date, entrega: date, huella: str, tabla: pd.DataFrame) -> str:
    nombre = f"{nombre_archivo(fuente, fecha, entrega)[:-4]}__{huella[:8]}.parquet"
    destino = cfg.almacen / fuente / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f".{destino.name}.tmp")
    tipada = tipar(tabla).assign(fecha_entrega=pd.Timestamp(entrega))
    tipada.to_parquet(temporal, index=False, compression="zstd")
    os.replace(temporal, destino)
    return nombre


def _a_cuarentena(cfg: Configuracion, ruta: Path, contenido: bytes, huella: str, motivos: list[str]) -> None:
    carpeta = cfg.cuarentena / huella[:8]
    _escribir_atomico(carpeta / ruta.name, contenido)
    _guardar_json(carpeta / "motivo.json", {"archivo": ruta.name, "hash": huella, "motivos": motivos})


def _procesar(cfg: Configuracion, pendiente: Pendiente, fecha_logica: date, registro: dict, referencia: Referencia) -> dict | None:
    ruta, archivo = pendiente.ruta, pendiente.archivo
    contenido = ruta.read_bytes()
    huella = hashlib.sha256(contenido).hexdigest()
    previa = registro.get(ruta.name)
    if previa is not None and previa["hash"] == huella:
        return None
    identificador = ruta.name if previa is None else f"{ruta.name}__{huella[:8]}"
    if identificador in registro:
        return None

    entrada = {
        "id": identificador, "archivo": ruta.name, "hash": huella, "estado": "rechazado",
        "motivos": [], "advertencias": [], "filas": 0,
        "fuente": archivo.fuente if archivo else None,
        "fecha": archivo.fecha.isoformat() if archivo else None,
        "fecha_entrega": pendiente.entrega.isoformat() if pendiente.entrega else None,
    }
    if archivo is None:
        entrada["motivos"] = ["nombre_fuera_de_contrato"]
        _a_cuarentena(cfg, ruta, contenido, huella, entrada["motivos"])
        return entrada

    # Un archivo que cambia sin cambiar de nombre se conoce desde que se observa el cambio.
    entrega = pendiente.entrega if previa is None else max(pendiente.entrega, fecha_logica)
    entrada["fecha_entrega"] = entrega.isoformat()
    repetido = any(
        r["hash"] == huella and r["fuente"] == archivo.fuente and r["fecha"] == entrada["fecha"] and r["estado"] == "aceptado"
        for r in registro.values()
    )
    if repetido:
        entrada["estado"] = "duplicado"
        return entrada

    resultado = validar(archivo.fuente, archivo.fecha, entrega, contenido, cfg.validacion, referencia)
    entrada["advertencias"] = resultado.advertencias
    if resultado.errores:
        entrada["motivos"] = resultado.errores
        _a_cuarentena(cfg, ruta, contenido, huella, resultado.errores)
        return entrada

    entrada["estado"] = "aceptado"
    entrada["filas"] = len(resultado.tabla)
    entrada["almacen"] = _guardar_en_almacen(cfg, archivo.fuente, archivo.fecha, entrega, huella, resultado.tabla)
    if archivo.fuente == "tiendas":
        entrada["claves"] = sorted(resultado.tabla["store_nbr"].tolist())
    return entrada


def ingerir(cfg: Configuracion, fecha_logica: date) -> dict[str, Any]:
    """Procesa lo disponible en `fecha_logica`. Repetirlo no cambia el resultado."""
    registro = _cargar_registro(cfg)
    disponibles = _disponibles(cfg, fecha_logica)
    resumen = {"fecha_logica": fecha_logica.isoformat(), "disponibles": len(disponibles),
               "aceptado": 0, "duplicado": 0, "rechazado": 0, "sin_cambios": 0, "advertencias": 0}
    if not disponibles:
        return resumen
    referencia = _referencia(cfg, registro)
    for pendiente in disponibles:
        entrada = _procesar(cfg, pendiente, fecha_logica, registro, referencia)
        if entrada is None:
            resumen["sin_cambios"] += 1
            continue
        _guardar_json(cfg.almacen / "registro" / f"{entrada['id']}.json", entrada)
        registro[entrada["id"]] = entrada
        resumen[entrada["estado"]] += 1
        resumen["advertencias"] += len(entrada["advertencias"])
        if entrada["fuente"] == "tiendas" and entrada["estado"] == "aceptado":
            referencia = _referencia(cfg, registro)
    return resumen
