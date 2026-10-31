"""Comportamiento real de Git y DVC, en un repositorio temporal con datos sintéticos."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SINTETICO = "tienda,familia,ventas\n1,GROCERY I,10\n"


def correr(args, cwd, verificar=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if verificar:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


def dvc(*args, cwd, verificar=True):
    return correr([sys.executable, "-m", "dvc", *args], cwd, verificar)


def git(*args, cwd):
    return correr(["git", *args], cwd)


def sincronia(cwd):
    return json.loads(dvc("status", "-c", "--json", cwd=cwd).stdout)


@pytest.fixture
def proyecto(tmp_path, raiz) -> Path:
    repo = tmp_path / "lab1"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("config", "user.name", "pruebas", cwd=repo)
    git("config", "user.email", "pruebas@example.invalid", cwd=repo)
    dvc("init", "-q", cwd=repo)
    shutil.copy(raiz / ".gitignore", repo / ".gitignore")
    shutil.copy(raiz / ".dvc" / "config", repo / ".dvc" / "config")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "base", cwd=repo)
    salida = repo / "data" / "publicado" / "corte=2017-04-03" / "rev=1"
    salida.mkdir(parents=True)
    (salida / "pronostico.csv").write_text(SINTETICO)
    return repo


RUTA = "data/publicado/corte=2017-04-03/rev=1"


def test_git_solo_ve_la_referencia_dvc(proyecto):
    dvc("add", RUTA, cwd=proyecto)
    visibles = git("status", "--porcelain", "-uall", cwd=proyecto).stdout.split("\n")
    assert [v[3:] for v in visibles if v] == [f"{RUTA}.dvc"]


def test_git_ignora_datos_y_modelos(proyecto):
    (proyecto / "models").mkdir()
    (proyecto / "models" / "modelo.txt").write_text("x")
    (proyecto / "kaggle.zip").write_text("x")
    (proyecto / ".env").write_text("CLAVE=1")
    assert git("status", "--porcelain", "-uall", cwd=proyecto).stdout == ""


def test_dvc_add_admite_publicacion_en_solo_lectura(proyecto):
    salida = proyecto / RUTA
    (salida / "pronostico.csv").chmod(0o444)
    salida.chmod(0o555)
    try:
        dvc("add", RUTA, cwd=proyecto)
    finally:
        salida.chmod(0o755)
    assert (proyecto / f"{RUTA}.dvc").is_file()


def test_status_json_detecta_desincronizacion(proyecto):
    dvc("add", RUTA, cwd=proyecto)
    assert sincronia(proyecto) != {}
    dvc("push", cwd=proyecto)
    assert sincronia(proyecto) == {}


def test_recuperacion_en_clon_limpio(proyecto, tmp_path):
    dvc("add", RUTA, cwd=proyecto)
    dvc("push", cwd=proyecto)
    git("add", "-f", f"{RUTA}.dvc", cwd=proyecto)
    git("commit", "-q", "-m", "publicacion", cwd=proyecto)
    git("clone", "-q", str(proyecto), str(tmp_path / "clon"), cwd=tmp_path)
    clon = tmp_path / "clon"
    dvc("pull", cwd=clon)
    assert (clon / RUTA / "pronostico.csv").read_text() == SINTETICO


def test_verify_rechaza_objeto_corrupto(proyecto, tmp_path):
    dvc("add", RUTA, cwd=proyecto)
    dvc("push", cwd=proyecto)
    git("add", "-f", f"{RUTA}.dvc", cwd=proyecto)
    git("commit", "-q", "-m", "publicacion", cwd=proyecto)
    remoto = tmp_path / "dvc-storage" / "lab1"
    objetos = [o for o in remoto.rglob("*") if o.is_file() and not o.name.endswith(".dir")]
    assert objetos
    for objeto in objetos:
        objeto.chmod(0o644)
        objeto.write_text("corrupto")
    git("clone", "-q", str(proyecto), str(tmp_path / "clon"), cwd=tmp_path)
    r = dvc("pull", cwd=tmp_path / "clon", verificar=False)
    assert r.returncode != 0
    assert not (tmp_path / "clon" / RUTA / "pronostico.csv").exists()
