"""Genera la carga histórica y la bandeja: python -m pronostico_ventas.simulador."""
import argparse
import hashlib
import json
import shutil
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
    excluidas = ("raiz", "kaggle", "historico", "bandeja", "almacen", "cuarentena", "validacion")
    parametros = {k: v for k, v in asdict(cfg).items() if k not in excluidas}
    texto = json.dumps(parametros, sort_keys=True, default=str)
    return hashlib.sha256(f"{contenido}{texto}".encode()).hexdigest()


def _nueva(destino: Path) -> Path:
    return destino.with_name(f".{destino.name}.nueva")


def _respaldo(destino: Path) -> Path:
    return destino.with_name(f".{destino.name}.anterior")


def _eliminar(ruta: Path) -> None:
    if ruta.exists():
        shutil.rmtree(ruta)


def _hashes_parquet(carpeta: Path) -> dict[str, str]:
    return {r.name: hashlib.sha256(r.read_bytes()).hexdigest() for r in sorted(carpeta.glob("*.parquet"))}


def _leer_manifiesto(carpeta: Path) -> dict | None:
    """Devuelve el manifiesto, o None si falta o no se puede confiar en él."""
    try:
        manifiesto = json.loads((carpeta / MANIFIESTO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifiesto, dict):
        return None
    secciones = (manifiesto.get("bandeja"), manifiesto.get("historico"))
    if not all(isinstance(s, dict) for s in secciones) or "huella_entrada" not in manifiesto:
        return None
    return manifiesto


def _consistente(cfg: config.Configuracion, manifiesto: dict | None) -> bool:
    return (
        manifiesto is not None
        and cfg.bandeja.is_dir()
        and cfg.historico.is_dir()
        and _huella_carpeta(cfg.bandeja) == manifiesto["bandeja"]
        and _hashes_parquet(cfg.historico) == manifiesto["historico"]
    )


def _vigente(cfg: config.Configuracion, entrada: str) -> bool:
    manifiesto = _leer_manifiesto(cfg.historico)
    return _consistente(cfg, manifiesto) and manifiesto["huella_entrada"] == entrada


def _recuperar(cfg: config.Configuracion) -> None:
    """Deja las salidas en un estado completo tras una ejecución interrumpida."""
    for destino in (cfg.historico, cfg.bandeja):
        _eliminar(_nueva(destino))

    respaldos = [r for r in (_respaldo(cfg.historico), _respaldo(cfg.bandeja)) if r.exists()]
    if not respaldos:
        return
    if _consistente(cfg, _leer_manifiesto(cfg.historico)):
        for respaldo in respaldos:
            _eliminar(respaldo)
        return

    # La instalación no terminó: se vuelve a la versión anterior si coincide con su manifiesto.
    origen = _respaldo(cfg.historico) if _respaldo(cfg.historico).exists() else cfg.historico
    manifiesto = _leer_manifiesto(origen)
    if manifiesto is None or _hashes_parquet(origen) != manifiesto["historico"]:
        raise RuntimeError(f"No se puede recuperar {cfg.historico}: respaldo no verificable")
    respaldo_bandeja = _respaldo(cfg.bandeja)
    if respaldo_bandeja.exists() and _huella_carpeta(respaldo_bandeja) != manifiesto["bandeja"]:
        raise RuntimeError(f"No se puede recuperar {cfg.bandeja}: respaldo no verificable")
    for destino in (cfg.historico, cfg.bandeja):
        if _respaldo(destino).exists():
            _eliminar(destino)
            _respaldo(destino).rename(destino)


def _ajenos(carpeta: Path, propios: dict[str, str], permitidos: tuple[str, ...] = ()) -> list[str]:
    ajenos = []
    for ruta in sorted(carpeta.iterdir()):
        if ruta.name in permitidos:
            continue
        if ruta.is_symlink() or not ruta.is_file():
            ajenos.append(ruta.name)
        elif hashlib.sha256(ruta.read_bytes()).hexdigest() != propios.get(ruta.name):
            ajenos.append(ruta.name)
    return ajenos


def _proteger_salidas(cfg: config.Configuracion) -> None:
    """Solo se reemplazan archivos idénticos a los del manifiesto. `--forzar` no cambia esta regla."""
    manifiesto = _leer_manifiesto(cfg.historico)
    propios = manifiesto or {"bandeja": {}, "historico": {}}
    for carpeta, seccion, permitidos in (
        (cfg.bandeja, "bandeja", ()),
        (cfg.historico, "historico", (MANIFIESTO,) if manifiesto else ()),
    ):
        if carpeta.exists() and not carpeta.is_dir():
            raise RuntimeError(f"{carpeta} no es una carpeta; no se modifica")
        if not carpeta.is_dir():
            continue
        ajenos = _ajenos(carpeta, propios[seccion], permitidos)
        if ajenos:
            motivo = "con contenido distinto al del manifiesto" if manifiesto else "sin un manifiesto válido"
            raise RuntimeError(
                f"{carpeta} tiene archivos no generados por el simulador ({motivo}); "
                f"no se modifica. Restáuralos o muévelos: {ajenos[:3]}"
            )


def _instalar(pares: list[tuple[Path, Path]]) -> None:
    """Instala las carpetas nuevas por renombrado. Ante un fallo, restaura las anteriores."""
    instaladas = []
    try:
        for nueva, destino in pares:
            instaladas.append(destino)
            if destino.exists():
                destino.rename(_respaldo(destino))
            nueva.rename(destino)
    except BaseException:
        for destino in reversed(instaladas):
            if _respaldo(destino).exists():
                _eliminar(destino)
                _respaldo(destino).rename(destino)
        raise
    for _, destino in pares:
        _eliminar(_respaldo(destino))


def ejecutar(cfg: config.Configuracion, forzar: bool = False) -> dict:
    """Genera las salidas. Si ya corresponden a la misma entrada, no cambia nada."""
    cfg.historico.parent.mkdir(parents=True, exist_ok=True)
    cfg.bandeja.parent.mkdir(parents=True, exist_ok=True)
    _recuperar(cfg)

    tablas, contenido = kaggle.leer(cfg.kaggle)
    entrada = _huella_entrada(contenido, cfg)
    if not forzar and _vigente(cfg, entrada):
        return _leer_manifiesto(cfg.historico)

    _proteger_salidas(cfg)
    fin = cfg.fin_bandeja or date.fromisoformat(tablas["train.csv"]["date"].max())
    if fin <= cfg.corte_historico:
        raise ValueError("El corte histórico debe ser anterior al fin de la bandeja")

    entregas = bandeja.construir(tablas, cfg, fin)
    entregas, registro = incidentes.aplicar(entregas, cfg.incidentes, cfg.semilla)

    # Cada carpeta nueva se prepara junto a su destino para instalarla con un renombrado,
    # sin copias parciales aunque BANDEJA_DIR esté en otro sistema de archivos.
    previa_historico, previa_bandeja = _nueva(cfg.historico), _nueva(cfg.bandeja)
    try:
        filas = historico.generar(tablas, cfg, previa_historico)
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
        _instalar([(previa_historico, cfg.historico), (previa_bandeja, cfg.bandeja)])
    finally:
        _eliminar(previa_historico)
        _eliminar(previa_bandeja)
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
