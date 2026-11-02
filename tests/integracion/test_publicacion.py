"""Publicación, revisiones y respaldo con Git y DVC reales, en un proyecto temporal."""
import json
import os
import shutil
import subprocess
import sys
from datetime import date

import pandas as pd
import pytest
import yaml

from pronostico_ventas import config
from pronostico_ventas.publicacion import entrenamiento, estado, publicar, versionado

CORTE = date(2017, 3, 6)
CAMPOS = {"commit", "arbol_limpio", "datos", "modelo", "hash_configuracion", "hash_costos", "corte", "horizonte_dias", "cobertura", "revision", "revisa_a", "hash_pronostico", "hash_pedido"}


def git(cfg, *args):
    return subprocess.run(["git", *args], cwd=cfg.raiz, capture_output=True, text=True, check=True).stdout.strip()


def dvc(cfg, *args):
    return subprocess.run([sys.executable, "-m", "dvc", *args], cwd=cfg.raiz, capture_output=True, text=True, check=True)


@pytest.fixture
def cfg(proyecto_modelo, raiz, monkeypatch):
    monkeypatch.delenv("REMOTO_MONTADO", raising=False)
    cfg = config.cargar(proyecto_modelo)
    meta = entrenamiento.entrenar(cfg, "lightgbm", date(2017, 3, 6))
    entrenamiento.fijar_vigente(cfg, meta["id"])
    return cfg


@pytest.fixture
def repo(cfg, raiz):
    git(cfg, "init", "-q", "-b", "main")
    git(cfg, "config", "user.name", "pruebas")
    git(cfg, "config", "user.email", "pruebas@example.invalid")
    dvc(cfg, "init", "-q")
    shutil.copy(raiz / ".gitignore", cfg.raiz / ".gitignore")
    shutil.copy(raiz / ".dvc" / "config", cfg.raiz / ".dvc" / "config")
    remoto = versionado.ruta_remoto(cfg)
    remoto.mkdir(parents=True)
    (remoto / versionado.CENTINELA).touch()
    git(cfg, "add", "-A")
    git(cfg, "commit", "-q", "-m", "base")
    return cfg


def publicada(cfg, corte=CORTE, revision=1):
    base = publicar.carpeta(cfg, corte, revision)
    return pd.read_parquet(base / "pronostico.parquet"), pd.read_parquet(base / "pedido.parquet"), json.loads((base / "manifest.json").read_text(encoding="utf-8"))


def test_pronostico_con_cuantiles_y_pedido(cfg):
    publicar.publicar(cfg, CORTE)
    pronostico, pedido, _ = publicada(cfg)
    assert len(pronostico) == 42 and len(pedido) == 6
    assert ((pronostico["p10"] <= pronostico["p50"]) & (pronostico["p50"] <= pronostico["p90"])).all()
    assert (pedido["pedido"] >= 0).all()


def test_manifiesto_campos_obligatorios(cfg):
    publicar.publicar(cfg, CORTE)
    manifiesto = publicada(cfg)[2]
    assert CAMPOS <= set(manifiesto)
    assert manifiesto["revision"] == 1 and manifiesto["revisa_a"] is None
    assert manifiesto["datos"]["as_of"] == CORTE.isoformat()
    assert len(manifiesto["modelo"]["hash"]) == 64


def test_publicar_dos_veces_no_cambia_nada(cfg):
    publicar.publicar(cfg, CORTE)
    antes = publicada(cfg)
    assert publicar.publicar(cfg, CORTE)["resultado"] == "sin_cambios"
    assert publicada(cfg)[2] == antes[2]


def test_publicacion_no_se_sobrescribe(cfg):
    publicar.publicar(cfg, CORTE)
    base = publicar.carpeta(cfg, CORTE, 1)
    with pytest.raises(PermissionError):
        (base / "pedido.parquet").write_bytes(b"x")
    with pytest.raises(PermissionError):
        (base / "nuevo").write_text("x")


def test_cambiar_costos_cambia_pedido_sin_cambiar_codigo(proyecto_modelo, cfg):
    publicar.publicar(cfg, CORTE)
    base = publicada(cfg)[1]
    ruta = proyecto_modelo / "config" / "costos.yaml"
    costos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    costos["grupos"]["alta_rotacion"]["cu"] = 20.0
    ruta.write_text(yaml.safe_dump(costos), encoding="utf-8")
    otro = config.cargar(proyecto_modelo)
    modelo, calibrador, _ = entrenamiento.cargar(otro, entrenamiento.leer_vigente(otro))
    _, nuevo = publicar.calcular(otro, CORTE, modelo, calibrador)
    actual = nuevo[nuevo["family"] == "GROCERY I"]["pedido"].to_numpy()
    assert (actual > base[base["family"] == "GROCERY I"]["pedido"].to_numpy()).all()


def test_reprocesar_crea_revision_y_conserva_la_original(cfg):
    publicar.publicar(cfg, CORTE)
    original = publicada(cfg)
    (cfg.bandeja / "ventas_2017-03-05__entrega_2017-03-07.csv").write_text(
        "date,store_nbr,family,sales,onpromotion\n2017-03-05,1,GROCERY I,9999.0,0\n"
    )
    from pronostico_ventas.ingesta.proceso import ingerir

    ingerir(cfg, date(2017, 3, 17))
    resultado = publicar.publicar(cfg, CORTE, reprocesar_en=date(2017, 3, 17))
    assert resultado["revision"] == 2
    assert resultado["manifiesto"]["revisa_a"] == 1
    assert resultado["manifiesto"]["modelo"]["id"] == original[2]["modelo"]["id"]
    assert publicada(cfg)[2] == original[2]
    pd.testing.assert_frame_equal(publicada(cfg)[0], original[0])


def test_reproceso_conserva_el_modelo_original(cfg):
    from pronostico_ventas.ingesta.proceso import ingerir

    publicar.publicar(cfg, CORTE)
    original = entrenamiento.leer_vigente(cfg)
    nuevo = entrenamiento.entrenar(cfg, "baseline", date(2017, 3, 13))
    entrenamiento.fijar_vigente(cfg, nuevo["id"])
    (cfg.bandeja / "ventas_2017-03-05__entrega_2017-03-07.csv").write_text(
        "date,store_nbr,family,sales,onpromotion\n2017-03-05,1,GROCERY I,9999.0,0\n"
    )
    ingerir(cfg, date(2017, 3, 17))
    resultado = publicar.publicar(cfg, CORTE, reprocesar_en=date(2017, 3, 17))
    assert resultado["manifiesto"]["modelo"]["id"] == original


def test_reproceso_idempotente(cfg):
    publicar.publicar(cfg, CORTE)
    assert publicar.publicar(cfg, CORTE, reprocesar_en=CORTE)["resultado"] == "sin_cambios"


def test_datos_nuevos_sin_efecto_no_crean_revision(cfg):
    publicar.publicar(cfg, CORTE)
    from pronostico_ventas.ingesta.proceso import ingerir

    (cfg.bandeja / "ventas_2017-03-12__entrega_2017-03-13.csv").write_text(
        "date,store_nbr,family,sales,onpromotion\n2017-03-12,1,GROCERY I,1.0,0\n"
    )
    ingerir(cfg, date(2017, 3, 17))
    assert publicar.publicar(cfg, CORTE, reprocesar_en=date(2017, 3, 17))["resultado"] == "sin_cambios"
    assert publicar.revisiones(cfg, CORTE) == [1]


def test_publicacion_omitida_con_motivo(cfg):
    resultado = publicar.publicar(cfg, date(2017, 3, 27))
    assert resultado["resultado"] == "omitida"
    assert "datos_antiguos" in resultado["motivo"]
    assert (cfg.estado_publicaciones / "corte=2017-03-27_omitida.json").is_file()


def test_tienda_cerrada_y_serie_inactiva_no_reciben_pedido(cfg):
    modelo, calibrador, _ = entrenamiento.cargar(cfg, entrenamiento.leer_vigente(cfg))
    _, pedido = publicar.calcular(cfg, date(2017, 2, 13), modelo, calibrador)
    tienda = pedido[pedido["store_nbr"] == 3]
    assert (tienda["marca"] == "tienda_cerrada").all()
    assert (tienda["pedido"] == 0).all()


def test_flujo_completo_respaldada_y_recuperable(repo, tmp_path):
    cfg = repo
    publicar.publicar(cfg, CORTE)
    versionado.versionar(cfg, CORTE, 1)
    assert estado.leer(cfg, CORTE, 1)["estado"] == "VERSIONADA"
    versionado.respaldar(cfg, CORTE, 1)
    assert estado.leer(cfg, CORTE, 1)["estado"] == "RESPALDADA"
    assert git(cfg, "rev-parse", "pub/2017-03-06-r1")
    assert estado.pendientes(cfg) == []
    clon = cfg.raiz.parent / "clon"
    subprocess.run(["git", "clone", "-q", str(cfg.raiz), str(clon)], check=True)
    subprocess.run(["git", "checkout", "-q", "pub/2017-03-06-r1"], cwd=clon, check=True)
    subprocess.run([sys.executable, "-m", "dvc", "pull"], cwd=clon, check=True, capture_output=True)
    copia = clon / "data" / "publicado" / "corte=2017-03-06" / "rev=1" / "manifest.json"
    assert json.loads(copia.read_text(encoding="utf-8")) == publicada(cfg)[2]


def test_commit_de_publicacion_no_toca_el_repositorio_de_trabajo(repo):
    cfg = repo
    publicar.publicar(cfg, CORTE)
    indice = (cfg.raiz / ".git" / "index").read_bytes()
    cabeza, rama = git(cfg, "rev-parse", "HEAD"), git(cfg, "branch", "--show-current")
    versionado.versionar(cfg, CORTE, 1)
    assert (cfg.raiz / ".git" / "index").read_bytes() == indice
    assert git(cfg, "rev-parse", "HEAD") == cabeza and git(cfg, "branch", "--show-current") == rama


def test_fallo_dvc_add_no_respalda(repo, monkeypatch):
    cfg = repo
    publicar.publicar(cfg, CORTE)
    monkeypatch.setattr(versionado, "_dvc", lambda c, *a: subprocess.CompletedProcess(a, 1, "", "falla"))
    with pytest.raises(versionado.ErrorRespaldo):
        versionado.versionar(cfg, CORTE, 1)
    assert estado.leer(cfg, CORTE, 1)["estado"] == "RESPALDO_FALLIDO"
    assert estado.hay_fallo(cfg, CORTE)


def test_centinela_y_montaje_requeridos(repo, monkeypatch):
    cfg = repo
    publicar.publicar(cfg, CORTE)
    versionado.versionar(cfg, CORTE, 1)
    (versionado.ruta_remoto(cfg) / versionado.CENTINELA).unlink()
    with pytest.raises(versionado.ErrorRespaldo, match="centinela"):
        versionado.respaldar(cfg, CORTE, 1)
    assert estado.leer(cfg, CORTE, 1)["paso"] == "centinela"
    (versionado.ruta_remoto(cfg) / versionado.CENTINELA).touch()
    monkeypatch.setenv("REMOTO_MONTADO", "/ruta/que/no/existe")
    with pytest.raises(versionado.ErrorRespaldo, match="montaje"):
        versionado.respaldar(cfg, CORTE, 1)


def test_fallo_push_registra_error(repo, monkeypatch):
    cfg = repo
    publicar.publicar(cfg, CORTE)
    versionado.versionar(cfg, CORTE, 1)
    real = versionado._dvc
    monkeypatch.setattr(versionado, "_dvc", lambda c, *a: subprocess.CompletedProcess(a, 1, "", "sin espacio") if a[0] == "push" else real(c, *a))
    with pytest.raises(versionado.ErrorRespaldo):
        versionado.respaldar(cfg, CORTE, 1)
    assert estado.leer(cfg, CORTE, 1)["estado"] == "RESPALDO_FALLIDO"


def test_status_cloud_usa_json(repo, monkeypatch):
    cfg = repo
    publicar.publicar(cfg, CORTE)
    versionado.versionar(cfg, CORTE, 1)
    real = versionado._dvc
    monkeypatch.setattr(versionado, "_dvc", lambda c, *a: subprocess.CompletedProcess(a, 0, '{"x": "new"}', "") if a[0] == "status" else real(c, *a))
    with pytest.raises(versionado.ErrorRespaldo, match="sincronia"):
        versionado.respaldar(cfg, CORTE, 1)


def test_objeto_corrupto_impide_respaldada(repo):
    cfg = repo
    publicar.publicar(cfg, CORTE)
    versionado.versionar(cfg, CORTE, 1)
    versionado.respaldar(cfg, CORTE, 1)
    remoto = versionado.ruta_remoto(cfg)
    indice = yaml.safe_load(publicar.carpeta(cfg, CORTE, 1).with_name("rev=1.dvc").read_text(encoding="utf-8"))["outs"][0]["md5"]
    archivos = json.loads((remoto / "files" / "md5" / indice[:2] / indice[2:]).read_text(encoding="utf-8"))
    objeto = remoto / "files" / "md5" / archivos[0]["md5"][:2] / archivos[0]["md5"][2:]
    objeto.chmod(0o644)
    objeto.write_bytes(b"corrupto")
    with pytest.raises(versionado.ErrorRespaldo, match="hashes"):
        versionado.respaldar(cfg, CORTE, 1)
    assert estado.leer(cfg, CORTE, 1)["estado"] == "RESPALDO_FALLIDO"


def test_respaldo_pendiente_se_reconcilia(repo, monkeypatch):
    cfg = repo
    publicar.publicar(cfg, CORTE)
    versionado.versionar(cfg, CORTE, 1)
    (versionado.ruta_remoto(cfg) / versionado.CENTINELA).unlink()
    with pytest.raises(versionado.ErrorRespaldo):
        versionado.respaldar(cfg, CORTE, 1)
    (versionado.ruta_remoto(cfg) / versionado.CENTINELA).touch()
    assert versionado.reconciliar(cfg) == ["2017-03-06-r1"]
    assert estado.leer(cfg, CORTE, 1)["estado"] == "RESPALDADA"
    assert versionado.reconciliar(cfg) == []


def test_reproducir_hash_identico(cfg):
    from pronostico_ventas.publicacion.reproduccion import reproducir

    publicar.publicar(cfg, CORTE)
    assert reproducir(cfg, CORTE, 1)["identico"]


def test_reproducir_no_cambia_por_datos_posteriores(cfg):
    from pronostico_ventas.ingesta.proceso import ingerir
    from pronostico_ventas.publicacion.reproduccion import reproducir

    publicar.publicar(cfg, CORTE)
    (cfg.bandeja / "ventas_2017-03-05__entrega_2017-03-07.csv").write_text(
        "date,store_nbr,family,sales,onpromotion\n2017-03-05,1,GROCERY I,9999.0,0\n"
    )
    ingerir(cfg, date(2017, 3, 20))
    assert reproducir(cfg, CORTE, 1)["identico"]


def test_reproducir_detecta_otro_modelo(cfg):
    from pronostico_ventas.publicacion.reproduccion import reproducir

    publicar.publicar(cfg, CORTE)
    ruta = cfg.modelos / entrenamiento.leer_vigente(cfg) / "meta.json"
    meta = json.loads(ruta.read_text(encoding="utf-8"))
    meta["hash_modelo"] = "otro"
    ruta.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError):
        reproducir(cfg, CORTE, 1)


def test_tar_alterado_se_rechaza(tmp_path, raiz):
    remoto = tmp_path / "origen" / "lab1"
    remoto.mkdir(parents=True)
    (remoto / "objeto").write_text("datos")
    subprocess.run([raiz / "scripts/respaldar_dvc.sh", tmp_path / "copia", remoto], check=True, capture_output=True)
    archivo = next((tmp_path / "copia").glob("*.tar"))
    with open(archivo, "ab") as contenido:
        contenido.write(b"x")
    r = subprocess.run([raiz / "scripts/restaurar_dvc.sh", archivo, tmp_path / "destino"], capture_output=True)
    assert r.returncode != 0
    assert not (tmp_path / "destino" / "lab1").exists()


def test_restauracion_desde_tar(tmp_path, raiz):
    remoto = tmp_path / "origen" / "lab1"
    remoto.mkdir(parents=True)
    (remoto / "objeto").write_text("datos")
    subprocess.run([raiz / "scripts/respaldar_dvc.sh", tmp_path / "copia", remoto], check=True, capture_output=True)
    archivo = next((tmp_path / "copia").glob("*.tar"))
    subprocess.run([raiz / "scripts/restaurar_dvc.sh", archivo, tmp_path / "destino"], check=True, capture_output=True)
    assert (tmp_path / "destino" / "lab1" / "objeto").read_text() == "datos"
    r = subprocess.run([raiz / "scripts/restaurar_dvc.sh", archivo, tmp_path / "destino"], capture_output=True)
    assert r.returncode != 0
