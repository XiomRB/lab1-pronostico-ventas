"""Publicación inmutable de un pronóstico y su pedido sugerido."""
import hashlib
import json
import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from pronostico_ventas.almacen.consulta import frescura
from pronostico_ventas.calibracion import residuos
from pronostico_ventas.config import Configuracion
from pronostico_ventas.features.construccion import construir, obtener
from pronostico_ventas.pedido import politica
from pronostico_ventas.publicacion import entrenamiento, estado

DIAS_INACTIVIDAD = 28
CODIGO = ("src", "dags", "config", "airflow", "dvc.yaml", "requirements.txt", "requirements-dev.txt")


def carpeta(cfg: Configuracion, corte: date, revision: int) -> Path:
    return cfg.publicado / f"corte={corte.isoformat()}" / f"rev={revision}"


def revisiones(cfg: Configuracion, corte: date) -> list[int]:
    base = cfg.publicado / f"corte={corte.isoformat()}"
    if not base.is_dir():
        return []
    return sorted(int(r.name.split("=")[1]) for r in base.iterdir() if r.is_dir() and r.name.startswith("rev="))


def _hash_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def huella_datos(cfg: Configuracion, conocido: date) -> str:
    """Identifica las observaciones aceptadas conocidas en una fecha."""
    entradas = []
    for ruta in sorted((cfg.almacen / "registro").glob("*.json")):
        entrada = json.loads(ruta.read_text(encoding="utf-8"))
        if entrada["estado"] == "aceptado" and entrada["conocido_desde"] <= conocido.isoformat():
            entradas.append((entrada["id"], entrada["hash"]))
    manifiesto = cfg.historico / "manifiesto_simulacion.json"
    historico = json.loads(manifiesto.read_text(encoding="utf-8"))["historico"] if manifiesto.is_file() else {}
    return _hash_texto(json.dumps([sorted(entradas), historico], sort_keys=True))


def hash_configuracion(cfg: Configuracion) -> str:
    return _hash_texto(json.dumps({"modelo": cfg.modelo, "fuentes": cfg.fuentes, "validacion": cfg.validacion}, sort_keys=True))


def commit_actual(cfg: Configuracion) -> tuple[str, bool]:
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=cfg.raiz, capture_output=True, text=True)

    salida = git("rev-parse", "HEAD")
    if salida.returncode != 0:
        return "desconocido", False
    existentes = [c for c in CODIGO if (cfg.raiz / c).exists()]
    return salida.stdout.strip(), git("diff", "--quiet", "HEAD", "--", *existentes).returncode == 0


def _marcas(pedido: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Series sin demanda reciente o tiendas cerradas no reciben pedido; se deja la razón."""
    series = panel.drop_duplicates(["store_nbr", "family"])[["store_nbr", "family", "dias_sin_venta", "media_7", "media_91", "tipo_tienda"]]
    tiendas = series.groupby("store_nbr")["media_7"].sum().rename("venta_tienda_7").reset_index()
    salida = pedido.merge(series, on=["store_nbr", "family"]).merge(tiendas, on="store_nbr")
    salida["marca"] = "normal"
    salida.loc[salida["media_91"].isna() | salida["tipo_tienda"].isna(), "marca"] = "baja_confianza"
    salida.loc[salida["dias_sin_venta"].isna() | (salida["dias_sin_venta"] > DIAS_INACTIVIDAD), "marca"] = "sin_actividad"
    salida.loc[salida["venta_tienda_7"] == 0, "marca"] = "tienda_cerrada"
    salida.loc[salida["marca"].isin(["sin_actividad", "tienda_cerrada"]), "pedido"] = 0.0
    return salida.drop(columns=["dias_sin_venta", "media_7", "media_91", "tipo_tienda", "venta_tienda_7", "escala", "dias"])


def calcular(cfg: Configuracion, corte: date, modelo: Any, calibrador: residuos.Calibrador, conocido: date | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pronóstico diario con cuantiles y pedido del periodo. No escribe nada."""
    panel = obtener(cfg, corte) if conocido is None else construir(cfg, corte, conocido)
    panel["p"] = modelo.predecir(panel)
    pronostico = panel[["corte", "date", "store_nbr", "family", "h", "p"]].rename(columns={"p": "pronostico"}).copy()
    for nivel in cfg.modelo["niveles_cuantil"]:
        pronostico[f"p{round(nivel * 100)}"] = calibrador.cuantil_diario(panel, nivel)
    cobertura = cfg.modelo["cobertura"]
    periodo = residuos.agregar_periodo(panel, cobertura["desde_dia"], cobertura["hasta_dia"])
    pedido = _marcas(politica.calcular(periodo, calibrador, cfg.costos), panel)
    orden = ["store_nbr", "family"]
    return pronostico.sort_values(["date", *orden], ignore_index=True), pedido.sort_values(orden, ignore_index=True)


def canonico(tabla: pd.DataFrame) -> str:
    """Hash estable: valores redondeados y orden fijo, sin metadatos del archivo."""
    decimales = tabla.select_dtypes("number").columns
    return _hash_texto(tabla.assign(**{c: tabla[c].round(6) for c in decimales}).to_csv(index=False, lineterminator="\n"))


def canonico_igual(pronostico: pd.DataFrame, pedido: pd.DataFrame, previo: dict[str, Any]) -> bool:
    """Una revisión solo tiene sentido si cambia lo publicado."""
    return _canonico(pronostico) == previo["hash_pronostico"] and _canonico(pedido) == previo["hash_pedido"]


def _escribir_publicacion(destino: Path, pronostico: pd.DataFrame, pedido: pd.DataFrame, manifiesto: dict[str, Any]) -> None:
    temporal = destino.with_name(f".{destino.name}.tmp")
    temporal.mkdir(parents=True, exist_ok=True)
    pronostico.to_parquet(temporal / "pronostico.parquet", index=False, compression="zstd")
    pedido.to_parquet(temporal / "pedido.parquet", index=False, compression="zstd")
    (temporal / "manifest.json").write_text(json.dumps(manifiesto, indent=2, sort_keys=True), encoding="utf-8")
    os.rename(temporal, destino)
    for ruta in destino.iterdir():
        ruta.chmod(0o444)
    destino.chmod(0o555)


def publicar(cfg: Configuracion, corte: date, reprocesar_en: date | None = None) -> dict[str, Any]:
    """Publica `corte`. Con `reprocesar_en` crea una revisión con los datos conocidos en esa fecha."""
    existentes = revisiones(cfg, corte)
    conocido = reprocesar_en or corte
    if existentes and reprocesar_en is None:
        return {"resultado": "sin_cambios", "corte": corte.isoformat(), "revision": existentes[0]}

    fuentes = frescura(cfg, conocido)
    criticas = [f for f, e in fuentes.items() if f == "ventas" and e["estado"] != "normal"]
    if criticas:
        motivo = {"resultado": "omitida", "corte": corte.isoformat(), "motivo": f"datos_antiguos:{criticas}", "frescura": fuentes}
        estado.guardar_omision(cfg, corte, motivo)
        return motivo

    previo = None
    if reprocesar_en is None:
        identificador, revision, revisa = entrenamiento.leer_vigente(cfg), 1, None
    else:
        revisa = existentes[-1] if existentes else None
        previo = json.loads((carpeta(cfg, corte, revisa) / "manifest.json").read_text(encoding="utf-8")) if revisa else None
        identificador, revision = (previo["modelo"]["id"] if previo else entrenamiento.leer_vigente(cfg)), (revisa or 0) + 1
    huella = huella_datos(cfg, conocido)
    if revisa is not None and previo["datos"]["huella"] == huella:
        return {"resultado": "sin_cambios", "corte": corte.isoformat(), "revision": revisa}

    modelo, calibrador, meta = entrenamiento.cargar(cfg, identificador)
    pronostico, pedido = calcular(cfg, corte, modelo, calibrador, None if reprocesar_en is None else conocido)
    if previo and canonico_igual(pronostico, pedido, previo):
        return {"resultado": "sin_cambios", "corte": corte.isoformat(), "revision": revisa}

    commit, limpio = commit_actual(cfg)
    manifiesto = {
        "commit": commit,
        "arbol_limpio": limpio,
        "datos": {"huella": huella, "as_of": conocido.isoformat()},
        "modelo": {"id": identificador, "nombre": meta["nombre"], "hash": meta["hash_modelo"], "hash_calibrador": meta["hash_calibrador"]},
        "hash_configuracion": hash_configuracion(cfg),
        "hash_costos": _hash_texto(json.dumps(cfg.costos, sort_keys=True)),
        "corte": corte.isoformat(),
        "horizonte_dias": cfg.modelo["horizonte_dias"],
        "cobertura": cfg.modelo["cobertura"],
        "revision": revision,
        "revisa_a": revisa,
        "hash_pronostico": canonico(pronostico),
        "hash_pedido": canonico(pedido),
    }
    destino = carpeta(cfg, corte, revision)
    destino.parent.mkdir(parents=True, exist_ok=True)
    _escribir_publicacion(destino, pronostico, pedido, manifiesto)
    estado.marcar(cfg, corte, revision, "PUBLICADA")
    return {"resultado": "publicada", "corte": corte.isoformat(), "revision": revision, "manifiesto": manifiesto}
