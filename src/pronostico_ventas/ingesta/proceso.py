"""Registra las entregas disponibles en una fecha lógica. La bandeja solo se lee."""
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from pronostico_ventas.almacen.consulta import avisos_completitud, series_esperadas
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
    ventas = pd.read_parquet(cfg.historico / "ventas.parquet", columns=["family", "sales"])
    tiendas = pd.read_parquet(cfg.historico / "tiendas.parquet", columns=["store_nbr"])
    estadisticas = {
        "familias": sorted(ventas["family"].unique().tolist()),
        "tiendas": sorted(int(t) for t in tiendas["store_nbr"]),
        "series": [[int(t), f] for t, f in series_esperadas(cfg).itertuples(index=False)],
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
        series=frozenset((t, f) for t, f in base["series"]),
        umbrales_venta=base["umbrales_venta"],
    )


def _guardar_en_almacen(cfg: Configuracion, entrada: dict[str, Any], tabla: pd.DataFrame) -> str:
    fecha, entrega = date.fromisoformat(entrada["fecha"]), date.fromisoformat(entrada["fecha_entrega"])
    conocido = date.fromisoformat(entrada["conocido_desde"])
    nombre = f"{nombre_archivo(entrada['fuente'], fecha, entrega)[:-4]}__obs_{conocido}__sec_{entrada['secuencia']:06d}.parquet"
    destino = cfg.almacen / entrada["fuente"] / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f".{destino.name}.tmp")
    tipada = tipar(tabla).assign(
        fecha_entrega=pd.Timestamp(entrega),
        conocido_desde=pd.Timestamp(conocido),
        secuencia=entrada["secuencia"],
    )
    tipada.to_parquet(temporal, index=False, compression="zstd")
    os.replace(temporal, destino)
    return nombre


def _a_cuarentena(cfg: Configuracion, ruta: Path, contenido: bytes, huella: str, motivos: list[str]) -> None:
    carpeta = cfg.cuarentena / huella[:8]
    _escribir_atomico(carpeta / ruta.name, contenido)
    _guardar_json(carpeta / "motivo.json", {"archivo": ruta.name, "hash": huella, "motivos": motivos})


def _ultima_observacion(registro: dict, archivo: str) -> dict | None:
    entradas = [e for e in registro.values() if e["archivo"] == archivo]
    return max(entradas, key=lambda e: e["secuencia"]) if entradas else None


def _version_vigente(registro: dict, fuente: str, fecha: str) -> str | None:
    aceptadas = [e for e in registro.values() if e["fuente"] == fuente and e["fecha"] == fecha and e["estado"] == "aceptado"]
    return max(aceptadas, key=lambda e: e["secuencia"])["hash"] if aceptadas else None


def _conocido_desde(entrega: date, nueva: bool, fecha_logica: date, ultima_fecha: date | None) -> date:
    """Lo que ya pudo consultarse no cambia: un archivo tardío se conoce desde que se observa."""
    if nueva and (ultima_fecha is None or entrega > ultima_fecha):
        return entrega
    return max(entrega, fecha_logica, ultima_fecha or fecha_logica)


def _procesar(cfg: Configuracion, pendiente: Pendiente, fecha_logica: date, ultima_fecha: date | None, registro: dict, referencia: Referencia) -> dict | None:
    ruta, archivo = pendiente.ruta, pendiente.archivo
    contenido = ruta.read_bytes()
    huella = hashlib.sha256(contenido).hexdigest()
    previa = _ultima_observacion(registro, ruta.name)
    if previa is not None and previa["hash"] == huella:
        return None

    secuencia = max((e["secuencia"] for e in registro.values()), default=0) + 1
    entrada = {
        "id": ruta.name if previa is None else f"{ruta.name}__{secuencia:06d}",
        "secuencia": secuencia, "archivo": ruta.name, "hash": huella, "estado": "rechazado",
        "motivos": [], "advertencias": [], "filas": 0,
        "fuente": archivo.fuente if archivo else None,
        "fecha": archivo.fecha.isoformat() if archivo else None,
        "fecha_entrega": pendiente.entrega.isoformat() if pendiente.entrega else None,
    }
    if archivo is None:
        entrada["motivos"] = ["nombre_fuera_de_contrato"]
        _a_cuarentena(cfg, ruta, contenido, huella, entrada["motivos"])
        return entrada

    conocido = _conocido_desde(pendiente.entrega, previa is None, fecha_logica, ultima_fecha)
    entrada["conocido_desde"] = conocido.isoformat()
    if _version_vigente(registro, archivo.fuente, entrada["fecha"]) == huella:
        entrada["estado"] = "duplicado"
        return entrada

    try:
        resultado = validar(archivo.fuente, archivo.fecha, pendiente.entrega, contenido, cfg.validacion, referencia)
        entrada["advertencias"] = resultado.advertencias
        if not resultado.errores:
            entrada["almacen"] = _guardar_en_almacen(cfg, entrada, resultado.tabla)
        errores = resultado.errores
    except Exception as error:
        # Un archivo problemático nunca debe detener las demás entregas.
        errores = [f"error_al_procesar:{type(error).__name__}"]
    if errores:
        entrada["motivos"] = errores
        _a_cuarentena(cfg, ruta, contenido, huella, errores)
        return entrada

    entrada["estado"] = "aceptado"
    entrada["filas"] = len(resultado.tabla)
    if archivo.fuente == "tiendas":
        entrada["claves"] = sorted(resultado.tabla["store_nbr"].tolist())
    return entrada


def _leer_estado(cfg: Configuracion) -> date | None:
    ruta = cfg.almacen / "estado.json"
    if not ruta.is_file():
        return None
    return date.fromisoformat(json.loads(ruta.read_text(encoding="utf-8"))["ultima_fecha_logica"])


def ingerir(cfg: Configuracion, fecha_logica: date) -> dict[str, Any]:
    """Procesa lo disponible en `fecha_logica`. Repetirlo no cambia el resultado."""
    registro = _cargar_registro(cfg)
    disponibles = _disponibles(cfg, fecha_logica)
    resumen = {"fecha_logica": fecha_logica.isoformat(), "disponibles": len(disponibles),
               "aceptado": 0, "duplicado": 0, "rechazado": 0, "sin_cambios": 0, "advertencias": 0, "avisos_completitud": []}
    ultima_fecha = _leer_estado(cfg)
    if disponibles:
        referencia = _referencia(cfg, registro)
        for pendiente in disponibles:
            entrada = _procesar(cfg, pendiente, fecha_logica, ultima_fecha, registro, referencia)
            if entrada is None:
                resumen["sin_cambios"] += 1
                continue
            _guardar_json(cfg.almacen / "registro" / f"{entrada['id']}.json", entrada)
            registro[entrada["id"]] = entrada
            resumen[entrada["estado"]] += 1
            resumen["advertencias"] += len(entrada["advertencias"])
            if entrada["fuente"] == "tiendas" and entrada["estado"] == "aceptado":
                referencia = _referencia(cfg, registro)
        if ultima_fecha is None or fecha_logica > ultima_fecha:
            _guardar_json(cfg.almacen / "estado.json", {"ultima_fecha_logica": fecha_logica.isoformat()})
        resumen["avisos_completitud"] = avisos_completitud(cfg, fecha_logica)
    return resumen
