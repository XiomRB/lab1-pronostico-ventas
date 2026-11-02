"""Fallos del simulador: interrupciones al escribir y archivos que no le pertenecen.

Los fallos se inyectan en `Path.rename` y `shutil`, no en funciones internas del simulador.
"""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from pronostico_ventas import config
from pronostico_ventas.simulador import __main__ as simulador

MANIFIESTO = "manifiesto_simulacion.json"
RENOMBRAR = Path.rename
ELIMINAR = shutil.rmtree
MOVER = shutil.move


class Caida(BaseException):
    """Simula la muerte del proceso: nada posterior puede completarse."""


def correr(proyecto, **opciones):
    return simulador.ejecutar(config.cargar(proyecto), **opciones)


def huellas(carpeta):
    return {r.name: hashlib.sha256(r.read_bytes()).hexdigest() for r in sorted(carpeta.iterdir()) if r.is_file()}


def bandeja(proyecto):
    return proyecto / "data" / "bandeja"


def historico(proyecto):
    return proyecto / "data" / "historico"


def estado(proyecto):
    return huellas(bandeja(proyecto)), huellas(historico(proyecto))


def residuos(proyecto):
    return sorted(r.name for r in (proyecto / "data").iterdir() if r.name.startswith("."))


def cambiar_semilla(proyecto):
    ruta = proyecto / "config" / "simulacion.yaml"
    ruta.write_text(ruta.read_text(encoding="utf-8").replace("semilla: 20170331", "semilla: 99"), encoding="utf-8")


def primer_archivo(proyecto):
    return sorted(bandeja(proyecto).glob("ventas_*.csv"))[0]


def consistente(proyecto):
    manifiesto = json.loads((historico(proyecto) / MANIFIESTO).read_text(encoding="utf-8"))
    parquet = {n: h for n, h in huellas(historico(proyecto)).items() if n != MANIFIESTO}
    return huellas(bandeja(proyecto)) == manifiesto["bandeja"] and parquet == manifiesto["historico"]


def fallar_una_vez(monkeypatch, nombre):
    """Provoca un error recuperable la primera vez que algo se mueve a `nombre`."""
    pendiente = {"activo": True}

    def filtrar(destino):
        if pendiente["activo"] and Path(destino).name == nombre:
            pendiente["activo"] = False
            raise OSError("fallo simulado")

    def renombrar(self, destino):
        filtrar(destino)
        return RENOMBRAR(self, destino)

    def mover(origen, destino, *args, **kwargs):
        filtrar(destino)
        return MOVER(origen, destino, *args, **kwargs)

    monkeypatch.setattr(Path, "rename", renombrar)
    monkeypatch.setattr(shutil, "move", mover)


def caer_en_paso(monkeypatch, paso):
    """Mata el proceso en el renombrado número `paso`; después ninguna operación se completa."""
    vivos = {"pasos": 0, "muerto": False}

    def comprobar():
        if vivos["muerto"]:
            raise Caida
        vivos["pasos"] += 1
        if vivos["pasos"] == paso:
            vivos["muerto"] = True
            raise Caida

    def renombrar(self, destino):
        comprobar()
        return RENOMBRAR(self, destino)

    def mover(origen, destino, *args, **kwargs):
        comprobar()
        return MOVER(origen, destino, *args, **kwargs)

    def eliminar(ruta, *args, **kwargs):
        if vivos["muerto"]:
            raise Caida
        return ELIMINAR(ruta, *args, **kwargs)

    monkeypatch.setattr(Path, "rename", renombrar)
    monkeypatch.setattr(shutil, "move", mover)
    monkeypatch.setattr(shutil, "rmtree", eliminar)


def test_fallo_al_reemplazar_conserva_la_bandeja(proyecto_sintetico, monkeypatch):
    correr(proyecto_sintetico)
    antes = estado(proyecto_sintetico)
    with monkeypatch.context() as parche:
        fallar_una_vez(parche, "bandeja")
        with pytest.raises(OSError):
            correr(proyecto_sintetico, forzar=True)
    assert estado(proyecto_sintetico) == antes
    assert residuos(proyecto_sintetico) == []


def test_respaldo_huerfano_no_bloquea(proyecto_sintetico):
    correr(proyecto_sintetico)
    antes = estado(proyecto_sintetico)
    huerfano = proyecto_sintetico / "data" / ".bandeja.anterior"
    huerfano.mkdir()
    (huerfano / "resto.csv").write_text("x\n")
    correr(proyecto_sintetico, forzar=True)
    assert estado(proyecto_sintetico) == antes
    assert residuos(proyecto_sintetico) == []


def test_respaldo_no_verificable_no_destruye_nada(proyecto_sintetico):
    correr(proyecto_sintetico)
    huerfano = proyecto_sintetico / "data" / ".bandeja.anterior"
    huerfano.mkdir()
    (huerfano / "resto.csv").write_text("x\n")
    alterado = primer_archivo(proyecto_sintetico)
    alterado.write_text("CONTENIDO AJENO\n")
    with pytest.raises(RuntimeError):
        correr(proyecto_sintetico, forzar=True)
    assert alterado.read_text() == "CONTENIDO AJENO\n"
    assert (huerfano / "resto.csv").exists()


@pytest.mark.parametrize("paso", [1, 2, 3, 4])
def test_recupera_interrupcion_previa(proyecto_sintetico, monkeypatch, paso):
    correr(proyecto_sintetico)
    anterior = estado(proyecto_sintetico)
    cambiar_semilla(proyecto_sintetico)
    with monkeypatch.context() as parche:
        caer_en_paso(parche, paso)
        with pytest.raises(Caida):
            correr(proyecto_sintetico)
    simulador._recuperar(config.cargar(proyecto_sintetico))
    assert consistente(proyecto_sintetico)
    assert estado(proyecto_sintetico) == anterior
    assert residuos(proyecto_sintetico) == []
    correr(proyecto_sintetico)
    assert consistente(proyecto_sintetico)
    assert estado(proyecto_sintetico) != anterior


def test_caida_durante_la_limpieza_conserva_lo_nuevo(proyecto_sintetico, monkeypatch):
    correr(proyecto_sintetico)
    cambiar_semilla(proyecto_sintetico)
    with monkeypatch.context() as parche:
        def caer(ruta, *args, **kwargs):
            if ".anterior" in str(ruta):
                raise Caida
            return ELIMINAR(ruta, *args, **kwargs)

        parche.setattr(shutil, "rmtree", caer)
        with pytest.raises(Caida):
            correr(proyecto_sintetico)
    nuevo = estado(proyecto_sintetico)
    simulador._recuperar(config.cargar(proyecto_sintetico))
    assert estado(proyecto_sintetico) == nuevo
    assert consistente(proyecto_sintetico)
    assert residuos(proyecto_sintetico) == []


def test_interrupcion_en_la_primera_ejecucion_se_completa(proyecto_sintetico, monkeypatch):
    with monkeypatch.context() as parche:
        caer_en_paso(parche, 2)
        with pytest.raises(Caida):
            correr(proyecto_sintetico)
    correr(proyecto_sintetico)
    assert consistente(proyecto_sintetico)
    assert residuos(proyecto_sintetico) == []


def test_fallo_entre_salidas_restaura_ambas(proyecto_sintetico, monkeypatch):
    correr(proyecto_sintetico)
    antes = estado(proyecto_sintetico)
    cambiar_semilla(proyecto_sintetico)
    # Sea cual sea el orden de instalación, el fallo llega con la otra salida ya reemplazada.
    with monkeypatch.context() as parche:
        pasos = {"n": 0}

        def renombrar(self, destino):
            if Path(destino).name in ("bandeja", "historico") and not self.name.endswith(".anterior"):
                pasos["n"] += 1
                if pasos["n"] == 2:
                    raise OSError("fallo simulado")
            return RENOMBRAR(self, destino)

        def mover(origen, destino, *args, **kwargs):
            pasos["n"] += 1
            if pasos["n"] == 2:
                raise OSError("fallo simulado")
            return MOVER(origen, destino, *args, **kwargs)

        parche.setattr(Path, "rename", renombrar)
        parche.setattr(shutil, "move", mover)
        with pytest.raises(OSError):
            correr(proyecto_sintetico)
    assert estado(proyecto_sintetico) == antes
    assert consistente(proyecto_sintetico)
    assert residuos(proyecto_sintetico) == []


@pytest.fixture
def otro_sistema(tmp_path):
    if not os.path.isdir("/dev/shm"):
        pytest.skip("No hay un segundo sistema de archivos")
    with tempfile.TemporaryDirectory(dir="/dev/shm") as carpeta:
        if os.stat(carpeta).st_dev == os.stat(tmp_path).st_dev:
            pytest.skip("Ambas rutas están en el mismo sistema de archivos")
        yield Path(carpeta)


def test_otro_sistema_de_archivos_no_deja_copia_parcial(proyecto_sintetico, otro_sistema, monkeypatch):
    externa = otro_sistema / "bandeja"
    monkeypatch.setenv("BANDEJA_DIR", str(externa))
    correr(proyecto_sintetico)
    antes = huellas(externa)

    copiar = shutil.copytree
    copiados = {"n": 0}

    def copia_que_falla(origen, destino, **opciones):
        def una_copia(fuente, final, **extra):
            copiados["n"] += 1
            if copiados["n"] > 10:
                raise OSError("disco lleno simulado")
            return shutil.copy2(fuente, final, **extra)

        opciones["copy_function"] = una_copia
        return copiar(origen, destino, **opciones)

    with monkeypatch.context() as parche:
        parche.setattr(shutil, "copytree", copia_que_falla)
        try:
            correr(proyecto_sintetico, forzar=True)
        except (OSError, shutil.Error):
            pass
    assert huellas(externa) == antes
    assert sorted(r.name for r in otro_sistema.iterdir()) == ["bandeja"]


def test_error_al_escribir_la_bandeja_no_toca_las_salidas(proyecto_sintetico, monkeypatch):
    correr(proyecto_sintetico)
    antes = estado(proyecto_sintetico)
    with monkeypatch.context() as parche:
        def escribir(entregas, destino):
            destino.mkdir(parents=True)
            (destino / "a_medias.csv").write_text("x\n")
            raise OSError("disco lleno simulado")

        parche.setattr(simulador.bandeja, "escribir", escribir)
        with pytest.raises(OSError):
            correr(proyecto_sintetico, forzar=True)
    assert estado(proyecto_sintetico) == antes
    assert residuos(proyecto_sintetico) == []


def test_archivo_alterado_no_se_sobrescribe(proyecto_sintetico):
    correr(proyecto_sintetico)
    alterado = primer_archivo(proyecto_sintetico)
    alterado.write_text("CONTENIDO AJENO\n")
    with pytest.raises(RuntimeError, match=alterado.name):
        correr(proyecto_sintetico, forzar=True)
    assert alterado.read_text() == "CONTENIDO AJENO\n"


def test_cambio_de_semilla_no_sobrescribe_alterado(proyecto_sintetico):
    correr(proyecto_sintetico)
    alterado = primer_archivo(proyecto_sintetico)
    alterado.write_text("CONTENIDO AJENO\n")
    cambiar_semilla(proyecto_sintetico)
    with pytest.raises(RuntimeError):
        correr(proyecto_sintetico)
    assert alterado.read_text() == "CONTENIDO AJENO\n"


def test_alterado_sin_cambios_de_entrada_no_se_acepta(proyecto_sintetico):
    correr(proyecto_sintetico)
    primer_archivo(proyecto_sintetico).write_text("CONTENIDO AJENO\n")
    with pytest.raises(RuntimeError):
        correr(proyecto_sintetico)


def test_historico_alterado_no_se_sobrescribe(proyecto_sintetico):
    correr(proyecto_sintetico)
    alterado = historico(proyecto_sintetico) / "ventas.parquet"
    alterado.write_bytes(b"ajeno")
    with pytest.raises(RuntimeError, match="ventas.parquet"):
        correr(proyecto_sintetico, forzar=True)
    assert alterado.read_bytes() == b"ajeno"


def test_historico_alterado_sin_cambios_de_entrada_no_se_acepta(proyecto_sintetico):
    correr(proyecto_sintetico)
    alterado = historico(proyecto_sintetico) / "ventas.parquet"
    alterado.write_bytes(b"ajeno")
    with pytest.raises(RuntimeError, match="ventas.parquet"):
        correr(proyecto_sintetico)
    assert alterado.read_bytes() == b"ajeno"


def test_respaldo_de_bandeja_sin_destino_se_verifica(proyecto_sintetico):
    correr(proyecto_sintetico)
    bandeja(proyecto_sintetico).rename(proyecto_sintetico / "data" / ".bandeja.anterior")
    primer = sorted((proyecto_sintetico / "data" / ".bandeja.anterior").glob("ventas_*.csv"))[0]
    primer.write_text("CONTENIDO AJENO\n")
    with pytest.raises(RuntimeError, match="respaldo no verificable"):
        correr(proyecto_sintetico, forzar=True)
    assert primer.read_text() == "CONTENIDO AJENO\n"


def test_bandeja_externa_con_nombres_iguales_se_conserva(proyecto_sintetico, tmp_path, monkeypatch):
    manifiesto = correr(proyecto_sintetico)
    externa = tmp_path / "bandeja_docente"
    externa.mkdir()
    nombres = sorted(manifiesto["bandeja"])[:3]
    for nombre in nombres:
        (externa / nombre).write_text("datos del sistema externo\n")
    monkeypatch.setenv("BANDEJA_DIR", str(externa))
    with pytest.raises(RuntimeError):
        correr(proyecto_sintetico, forzar=True)
    assert sorted(r.name for r in externa.iterdir()) == nombres
    assert all((externa / n).read_text() == "datos del sistema externo\n" for n in nombres)


@pytest.mark.parametrize(
    "contenido",
    [None, "{no es json", "[1, 2]", '{"bandeja": []}', '{"bandeja": {}, "historico": {}}'],
    ids=["ausente", "invalido", "lista", "seccion_erronea", "sin_huella"],
)
def test_manifiesto_corrupto_no_se_considera_propio(proyecto_sintetico, contenido):
    correr(proyecto_sintetico)
    ruta = historico(proyecto_sintetico) / MANIFIESTO
    if contenido is None:
        ruta.unlink()
    else:
        ruta.write_text(contenido, encoding="utf-8")
    antes = huellas(bandeja(proyecto_sintetico))
    with pytest.raises(RuntimeError, match="manifiesto válido"):
        correr(proyecto_sintetico, forzar=True)
    assert huellas(bandeja(proyecto_sintetico)) == antes


def test_archivo_propio_faltante_se_regenera(proyecto_sintetico):
    correr(proyecto_sintetico)
    antes = estado(proyecto_sintetico)
    primer_archivo(proyecto_sintetico).unlink()
    correr(proyecto_sintetico)
    assert estado(proyecto_sintetico) == antes


def test_archivo_faltante_con_ajeno_no_destruye_el_ajeno(proyecto_sintetico):
    correr(proyecto_sintetico)
    primer_archivo(proyecto_sintetico).unlink()
    ajeno = bandeja(proyecto_sintetico) / "ventas_2030-01-01.csv"
    ajeno.write_text("ajeno\n")
    with pytest.raises(RuntimeError):
        correr(proyecto_sintetico, forzar=True)
    assert ajeno.read_text() == "ajeno\n"


def test_enlace_simbolico_no_se_considera_propio(proyecto_sintetico, tmp_path):
    manifiesto = correr(proyecto_sintetico)
    objetivo = tmp_path / "objetivo.csv"
    ruta = primer_archivo(proyecto_sintetico)
    objetivo.write_bytes(ruta.read_bytes())
    ruta.unlink()
    ruta.symlink_to(objetivo)
    assert ruta.name in manifiesto["bandeja"]
    with pytest.raises(RuntimeError):
        correr(proyecto_sintetico, forzar=True)
    assert objetivo.exists()


def test_regeneracion_forzada_sigue_funcionando(proyecto_sintetico):
    primero = correr(proyecto_sintetico)
    assert correr(proyecto_sintetico, forzar=True) == primero
    assert residuos(proyecto_sintetico) == []


def test_solo_historico_no_genera_bandeja(proyecto_sintetico):
    manifiesto = simulador.ejecutar(config.cargar(proyecto_sintetico), solo_historico=True)
    assert manifiesto["bandeja"] == {}
    assert list(bandeja(proyecto_sintetico).iterdir()) == []
    assert (historico(proyecto_sintetico) / "ventas.parquet").is_file()


def test_solo_historico_es_idempotente(proyecto_sintetico):
    simulador.ejecutar(config.cargar(proyecto_sintetico), solo_historico=True)
    antes = huellas(historico(proyecto_sintetico))
    simulador.ejecutar(config.cargar(proyecto_sintetico), solo_historico=True)
    assert huellas(historico(proyecto_sintetico)) == antes
