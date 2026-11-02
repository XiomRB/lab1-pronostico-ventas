"""Versionado de publicaciones con Git y DVC, y criterio estricto de respaldo."""
import configparser
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import yaml

from pronostico_ventas.config import Configuracion
from pronostico_ventas.publicacion import estado
from pronostico_ventas.publicacion.publicar import carpeta

CENTINELA = ".remoto-lab1"


class ErrorRespaldo(RuntimeError):
    """Una condición de respaldo no se cumplió."""


def _correr(cfg: Configuracion, *comando: str, entorno: dict | None = None, entrada: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(comando, cwd=cfg.raiz, capture_output=True, text=True, env={**os.environ, **(entorno or {})}, input=entrada)


def _dvc(cfg: Configuracion, *argumentos: str) -> subprocess.CompletedProcess:
    return _correr(cfg, sys.executable, "-m", "dvc", *argumentos)


def _exigir(resultado: subprocess.CompletedProcess, paso: str) -> str:
    if resultado.returncode != 0:
        raise ErrorRespaldo(f"{paso}: {(resultado.stderr or resultado.stdout).strip()[-300:]}")
    return resultado.stdout


def ruta_remoto(cfg: Configuracion) -> Path:
    config = configparser.ConfigParser()
    config.read(cfg.raiz / ".dvc" / "config", encoding="utf-8")
    return (cfg.raiz / ".dvc" / config["'remote \"local\"'"]["url"]).resolve()


def commit_publicacion(cfg: Configuracion, etiqueta: str) -> str:
    """Une el código actual con las referencias .dvc, sin tocar el índice ni la rama de trabajo."""
    base = _exigir(_correr(cfg, "git", "rev-parse", "HEAD"), "git").strip()
    previo = _correr(cfg, "git", "rev-parse", "-q", "--verify", "refs/heads/publicaciones").stdout.strip()
    with tempfile.TemporaryDirectory() as temporal:
        entorno = {"GIT_INDEX_FILE": str(Path(temporal) / "indice")}
        _exigir(_correr(cfg, "git", "read-tree", base, entorno=entorno), "read-tree")
        if previo:
            lista = _exigir(_correr(cfg, "git", "ls-tree", "-r", previo, "--", "data", "models.dvc"), "ls-tree")
            _exigir(_correr(cfg, "git", "update-index", "--index-info", entorno=entorno, entrada=lista), "update-index")
        referencias = sorted(str(r.relative_to(cfg.raiz)) for r in [*cfg.raiz.glob("*.dvc"), *(cfg.raiz / "data").rglob("*.dvc")])
        _exigir(_correr(cfg, "git", "add", "-f", "--", *referencias, entorno=entorno), "add")
        arbol = _exigir(_correr(cfg, "git", "write-tree", entorno=entorno), "write-tree").strip()
    padres = ["-p", previo] if previo else []
    if not previo or _correr(cfg, "git", "merge-base", "--is-ancestor", base, previo).returncode != 0:
        padres += ["-p", base]
    if previo and _correr(cfg, "git", "rev-parse", f"{previo}^{{tree}}").stdout.strip() == arbol:
        nuevo = previo
    else:
        nuevo = _exigir(_correr(cfg, "git", "commit-tree", arbol, *padres, "-m", f"Publicación {etiqueta}"), "commit-tree").strip()
        _exigir(_correr(cfg, "git", "update-ref", "refs/heads/publicaciones", nuevo), "update-ref")
    _correr(cfg, "git", "tag", "-f", etiqueta, nuevo)
    return nuevo


def versionar(cfg: Configuracion, corte: date, revision: int) -> None:
    """Registra publicación, almacén, procesados y modelos en DVC, y crea el commit de publicación."""
    destino = carpeta(cfg, corte, revision)
    objetivos = [cfg.kaggle, cfg.historico, destino, cfg.almacen, cfg.cuarentena, cfg.procesado, cfg.seguimiento, cfg.modelos]
    if not os.environ.get("BANDEJA_HOST"):
        objetivos.append(cfg.bandeja)
    relativas = [str(p.relative_to(cfg.raiz)) for p in objetivos if p.exists()]
    try:
        # Sin reenlazar: la bandeja se monta en solo lectura y sus archivos no deben reemplazarse.
        _exigir(_dvc(cfg, "add", "--no-relink", *relativas), "dvc add")
        commit_publicacion(cfg, f"pub/{corte.isoformat()}-r{revision}")
    except ErrorRespaldo as error:
        estado.marcar(cfg, corte, revision, "RESPALDO_FALLIDO", str(error), "versionar")
        raise
    estado.marcar(cfg, corte, revision, "VERSIONADA")


def _objetos_publicacion(cfg: Configuracion, corte: date, revision: int, remoto: Path) -> None:
    referencia = carpeta(cfg, corte, revision).with_name(f"rev={revision}.dvc")
    digesto = yaml.safe_load(referencia.read_text(encoding="utf-8"))["outs"][0]["md5"]
    indice = remoto / "files" / "md5" / digesto[:2] / digesto[2:]
    if not indice.is_file():
        raise ErrorRespaldo(f"hashes: falta el índice {digesto}")
    for archivo in json.loads(indice.read_text(encoding="utf-8")):
        objeto = remoto / "files" / "md5" / archivo["md5"][:2] / archivo["md5"][2:]
        if not objeto.is_file() or hashlib.md5(objeto.read_bytes()).hexdigest() != archivo["md5"]:
            raise ErrorRespaldo(f"hashes: objeto alterado {archivo['relpath']}")


def respaldar(cfg: Configuracion, corte: date, revision: int) -> None:
    """Marca RESPALDADA solo si se cumplen las cinco condiciones."""
    remoto = ruta_remoto(cfg)
    try:
        exigido = os.environ.get("REMOTO_MONTADO")
        if exigido and f" {exigido} " not in Path("/proc/mounts").read_text(encoding="utf-8"):
            raise ErrorRespaldo(f"montaje: {exigido} no es un montaje real")
        if not (remoto / CENTINELA).is_file():
            raise ErrorRespaldo(f"centinela: falta {CENTINELA}")
        _exigir(_dvc(cfg, "push"), "dvc push")
        sincronia = _exigir(_dvc(cfg, "status", "-c", "--json"), "dvc status")
        if json.loads(sincronia.strip().splitlines()[-1]) != {}:
            raise ErrorRespaldo("sincronia: el remoto difiere de la caché")
        _objetos_publicacion(cfg, corte, revision, remoto)
    except ErrorRespaldo as error:
        estado.marcar(cfg, corte, revision, "RESPALDO_FALLIDO", str(error), str(error).split(":")[0])
        raise
    estado.marcar(cfg, corte, revision, "RESPALDADA")


def reconciliar(cfg: Configuracion) -> list[str]:
    """Reintenta las publicaciones pendientes. Es idempotente."""
    resueltas = []
    for pendiente in estado.pendientes(cfg):
        corte, revision = date.fromisoformat(pendiente["corte"]), pendiente["revision"]
        versionar(cfg, corte, revision)
        respaldar(cfg, corte, revision)
        resueltas.append(f"{pendiente['corte']}-r{revision}")
    return resueltas
