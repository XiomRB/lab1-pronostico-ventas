"""Genera la carga histórica y la bandeja: python -m pronostico_ventas.simulador."""
import argparse
import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict
from datetime import date
from pathlib import Path

from pronostico_ventas import config
from pronostico_ventas.simulador import bandeja, historico, incidentes, kaggle

MANIFIESTO = "manifiesto_simulacion.json"


def _huella_carpeta(carpeta: Path) -> dict[str, str]:
    return {r.name: hashlib.sha256(r.read_bytes()).hexdigest() for r in sorted(carpeta.iterdir()) if r.is_file()}


def _huella_total(archivos: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(archivos, sort_keys=True).encode()).hexdigest()


def _huella_entrada(contenido: str, cfg: config.Configuracion) -> str:
    parametros = {k: v for k, v in asdict(cfg).items() if k not in ("raiz", "kaggle", "historico", "bandeja")}
    texto = json.dumps(parametros, sort_keys=True, default=str)
    return hashlib.sha256(f"{contenido}{texto}".encode()).hexdigest()


def _vigente(cfg: config.Configuracion, entrada: str) -> bool:
    ruta = cfg.historico / MANIFIESTO
    if not ruta.is_file() or not cfg.bandeja.is_dir():
        return False
    previo = json.loads(ruta.read_text(encoding="utf-8"))
    actuales = {r.name: r for r in cfg.historico.glob("*.parquet")}
    return (
        previo["huella_entrada"] == entrada
        and _huella_carpeta(cfg.bandeja) == previo["bandeja"]
        and {n: hashlib.sha256(r.read_bytes()).hexdigest() for n, r in actuales.items()} == previo["historico"]
    )


def _proteger_bandeja_externa(cfg: config.Configuracion) -> None:
    """La bandeja es un sistema externo: solo se reemplaza la que generó este simulador."""
    if not cfg.bandeja.is_dir() or not any(cfg.bandeja.iterdir()):
        return
    ruta = cfg.historico / MANIFIESTO
    propios = json.loads(ruta.read_text(encoding="utf-8"))["bandeja"] if ruta.is_file() else {}
    ajenos = sorted(r.name for r in cfg.bandeja.iterdir() if r.name not in propios)
    if ajenos:
        raise RuntimeError(f"La bandeja {cfg.bandeja} contiene archivos ajenos; no se modifica: {ajenos[:3]}")


def _reemplazar(origen: Path, destino: Path) -> None:
    respaldo = destino.with_name(f".{destino.name}.anterior")
    if destino.exists():
        destino.rename(respaldo)
    shutil.move(origen, destino)
    if respaldo.exists():
        shutil.rmtree(respaldo)


def ejecutar(cfg: config.Configuracion, forzar: bool = False) -> dict:
    """Genera las salidas. Si ya corresponden a la misma entrada, no cambia nada."""
    tablas, contenido = kaggle.leer(cfg.kaggle)
    entrada = _huella_entrada(contenido, cfg)
    if not forzar and _vigente(cfg, entrada):
        return json.loads((cfg.historico / MANIFIESTO).read_text(encoding="utf-8"))

    _proteger_bandeja_externa(cfg)
    fin = cfg.fin_bandeja or date.fromisoformat(tablas["train.csv"]["date"].max())
    if fin <= cfg.corte_historico:
        raise ValueError("El corte histórico debe ser anterior al fin de la bandeja")

    entregas = bandeja.construir(tablas, cfg, fin)
    entregas, registro = incidentes.aplicar(entregas, cfg.incidentes, cfg.semilla)

    cfg.historico.parent.mkdir(parents=True, exist_ok=True)
    cfg.bandeja.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cfg.historico.parent, prefix=".simulacion_") as temporal:
        previa_historico = Path(temporal) / "historico"
        filas = historico.generar(tablas, cfg, previa_historico)
        previa_bandeja = Path(temporal) / "bandeja"
        bandeja.escribir(entregas, previa_bandeja)

        archivos_bandeja = _huella_carpeta(previa_bandeja)
        archivos_historico = _huella_carpeta(previa_historico)
        manifiesto = {
            "huella_entrada": entrada,
            "corte_historico": cfg.corte_historico.isoformat(),
            "fin_bandeja": fin.isoformat(),
            "semilla": cfg.semilla,
            "filas_historico": filas,
            "historico": archivos_historico,
            "bandeja": archivos_bandeja,
            "huella_salida": _huella_total({**archivos_historico, **archivos_bandeja}),
            "incidentes": registro,
        }
        (previa_historico / MANIFIESTO).write_text(
            json.dumps(manifiesto, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )
        _reemplazar(previa_bandeja, cfg.bandeja)
        _reemplazar(previa_historico, cfg.historico)
    return manifiesto


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forzar", action="store_true", help="regenera aunque las salidas estén vigentes")
    args = parser.parse_args()
    manifiesto = ejecutar(config.cargar(), forzar=args.forzar)
    print(json.dumps({k: manifiesto[k] for k in ("corte_historico", "fin_bandeja", "filas_historico", "huella_salida")}, indent=2))
    print(f"Archivos en la bandeja: {len(manifiesto['bandeja'])}")
    print(f"Incidentes: {len(manifiesto['incidentes'])}")


if __name__ == "__main__":
    main()
