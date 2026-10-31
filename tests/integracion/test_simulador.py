"""Simulador completo sobre un ZIP sintético, sin datos de Kaggle."""
import hashlib
import json
import zipfile
from datetime import date, datetime

import pandas as pd
import pytest

from pronostico_ventas import config
from pronostico_ventas.simulador import __main__ as simulador
from pronostico_ventas.simulador import kaggle
from pronostico_ventas.simulador.contrato import COLUMNAS, interpretar_nombre


def correr(proyecto, **opciones):
    return simulador.ejecutar(config.cargar(proyecto), **opciones)


def huellas(carpeta):
    return {r.name: hashlib.sha256(r.read_bytes()).hexdigest() for r in sorted(carpeta.iterdir())}


def archivos(proyecto):
    return [interpretar_nombre(r.name) for r in sorted((proyecto / "data" / "bandeja").iterdir())]


def leer(proyecto, fuente):
    return [
        pd.read_csv(r, dtype=str, keep_default_na=False)
        for r in sorted((proyecto / "data" / "bandeja").glob(f"{fuente}_*.csv"))
    ]


def historico(proyecto, fuente):
    return pd.read_parquet(proyecto / "data" / "historico" / f"{fuente}.parquet")


def incidentes(manifiesto, tipo):
    return [i for i in manifiesto["incidentes"] if i["tipo"] == tipo]


def original(proyecto, nombre):
    with zipfile.ZipFile(proyecto / "data" / "kaggle" / "kaggle_sintetico.zip") as archivo:
        with archivo.open(nombre) as contenido:
            return pd.read_csv(contenido, dtype=str, keep_default_na=False)


def test_todos_los_nombres_cumplen_el_contrato(proyecto_sintetico):
    correr(proyecto_sintetico)
    assert {a.fuente for a in archivos(proyecto_sintetico)} == set(COLUMNAS)


def test_misma_semilla_mismo_hash(proyecto_sintetico, tmp_path):
    primero = correr(proyecto_sintetico)
    a = huellas(proyecto_sintetico / "data" / "bandeja")
    segundo = correr(proyecto_sintetico, forzar=True)
    assert primero == segundo
    assert a == huellas(proyecto_sintetico / "data" / "bandeja")


def test_doble_ejecucion_no_cambia_nada(proyecto_sintetico):
    correr(proyecto_sintetico)
    bandeja = proyecto_sintetico / "data" / "bandeja"
    tiempos = {r.name: r.stat().st_mtime_ns for r in bandeja.iterdir()}
    correr(proyecto_sintetico)
    assert tiempos == {r.name: r.stat().st_mtime_ns for r in bandeja.iterdir()}


def test_semilla_distinta_cambia_los_incidentes(proyecto_sintetico):
    primero = correr(proyecto_sintetico)
    ruta = proyecto_sintetico / "config" / "simulacion.yaml"
    ruta.write_text(ruta.read_text(encoding="utf-8").replace("semilla: 20170331", "semilla: 99"), encoding="utf-8")
    assert correr(proyecto_sintetico)["incidentes"] != primero["incidentes"]


def test_historico_mas_bandeja_reconstruye_kaggle(proyecto_sintetico):
    manifiesto = correr(proyecto_sintetico)
    corte = manifiesto["corte_historico"]
    train = original(proyecto_sintetico, "train.csv")
    invalidas = {i["fecha"] for i in incidentes(manifiesto, "dato_invalido")}
    corregidas = {i["fecha"] for i in incidentes(manifiesto, "correccion")}

    reconstruida = {}
    for ruta in sorted((proyecto_sintetico / "data" / "bandeja").glob("ventas_*.csv")):
        tabla = pd.read_csv(ruta, dtype=str, keep_default_na=False)
        if "sales" not in tabla.columns or (tabla["sales"].astype(float) < 0).any():
            continue
        for fila in tabla.to_dict("records"):
            reconstruida[fila["id"]] = fila["sales"]  # gana la entrega más reciente
    ventana = train[train["date"] > corte]
    assert reconstruida == dict(zip(ventana["id"], ventana["sales"]))
    assert invalidas and corregidas

    previa = historico(proyecto_sintetico, "ventas")
    assert len(previa) == (train["date"] <= corte).sum()
    assert previa["sales"].sum() == pytest.approx(pd.to_numeric(train.loc[train["date"] <= corte, "sales"]).sum())


def test_cada_incidente_generado(proyecto_sintetico):
    manifiesto = correr(proyecto_sintetico)
    tipos = {i["tipo"] for i in manifiesto["incidentes"]}
    assert tipos == {"extremo_legitimo", "archivo_tardio", "archivo_parcial", "archivo_duplicado",
                     "correccion", "dato_invalido", "fuente_ausente"}


def test_fuente_ausente_no_tiene_archivo(proyecto_sintetico):
    manifiesto = correr(proyecto_sintetico)
    fecha = date.fromisoformat(incidentes(manifiesto, "fuente_ausente")[0]["fecha"])
    assert not [a for a in archivos(proyecto_sintetico) if a.fuente == "transacciones" and a.fecha == fecha]


def test_petroleo_sin_datos_futuros(proyecto_sintetico):
    manifiesto = correr(proyecto_sintetico)
    fin = date.fromisoformat(manifiesto["fin_bandeja"])
    fechas = [a.fecha for a in archivos(proyecto_sintetico) if a.fuente == "petroleo"]
    assert fechas and max(fechas) <= fin
    assert pd.concat(leer(proyecto_sintetico, "petroleo"))["dcoilwtico"].eq("").any()


def test_feriado_posterior_al_fin_no_se_entrega(proyecto_sintetico):
    manifiesto = correr(proyecto_sintetico)
    fin = date.fromisoformat(manifiesto["fin_bandeja"])
    entregas = [a for a in archivos(proyecto_sintetico) if a.fuente == "feriados"]
    assert entregas and all(a.entrega <= fin for a in entregas)
    assert not pd.concat(leer(proyecto_sintetico, "feriados"))["type"].eq("Bridge").any()


def test_feriado_conocido_al_corte_queda_en_historico(proyecto_sintetico):
    correr(proyecto_sintetico)
    feriados = historico(proyecto_sintetico, "feriados")
    corte = pd.Timestamp("2017-02-15")
    assert (feriados["fecha_entrega"] <= corte).all()
    assert (feriados["date"] > corte).any()
    assert not feriados["description"].str.contains("Terremoto").any()


def test_tienda_aparece_al_abrir(proyecto_sintetico):
    correr(proyecto_sintetico)
    assert 3 not in set(historico(proyecto_sintetico, "tiendas")["store_nbr"])
    apertura = [a for a in archivos(proyecto_sintetico) if a.fuente == "tiendas"]
    assert [(a.fecha, a.entrega) for a in apertura] == [(date(2017, 2, 20), date(2017, 2, 20))]


def test_plan_de_promociones_llega_antes_de_las_fechas_que_cubre(proyecto_sintetico):
    correr(proyecto_sintetico)
    bandeja = proyecto_sintetico / "data" / "bandeja"
    planes = sorted(bandeja.glob("promociones_*.csv"))
    assert planes
    for ruta in planes:
        plan = pd.read_csv(ruta, dtype=str)
        assert interpretar_nombre(ruta.name).entrega.isoformat() < plan["date"].min()


def test_historico_conserva_fecha_de_entrega(proyecto_sintetico):
    correr(proyecto_sintetico)
    ventas = historico(proyecto_sintetico, "ventas")
    assert (ventas["fecha_entrega"] == ventas["date"] + pd.Timedelta(days=1)).all()


def test_resultado_no_depende_de_la_hora(proyecto_sintetico, monkeypatch):
    primero = correr(proyecto_sintetico)

    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2030, 1, 1)

    monkeypatch.setattr("datetime.datetime", Reloj)
    assert correr(proyecto_sintetico, forzar=True) == primero


def test_no_lee_archivos_excluidos(proyecto_sintetico, monkeypatch):
    abiertos = []
    original_open = zipfile.ZipFile.open

    def espiar(self, nombre, *args, **kwargs):
        abiertos.append(nombre)
        return original_open(self, nombre, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", espiar)
    tablas, _ = kaggle.leer(proyecto_sintetico / "data" / "kaggle")
    assert set(tablas) == set(kaggle.PERMITIDOS)
    assert not {"test.csv", "sample_submission.csv"} & set(abiertos)


def test_acepta_csv_sueltos(proyecto_sintetico):
    carpeta = proyecto_sintetico / "data" / "kaggle"
    ruta_zip = next(carpeta.glob("*.zip"))
    con_zip, huella_zip = kaggle.leer(carpeta)
    with zipfile.ZipFile(ruta_zip) as archivo:
        archivo.extractall(carpeta, members=kaggle.PERMITIDOS)
    ruta_zip.unlink()
    sueltos, huella_csv = kaggle.leer(carpeta)
    assert huella_zip == huella_csv
    assert sueltos["train.csv"].equals(con_zip["train.csv"])


def test_falta_archivo_de_kaggle(proyecto_sintetico):
    carpeta = proyecto_sintetico / "data" / "kaggle"
    next(carpeta.glob("*.zip")).unlink()
    with pytest.raises(FileNotFoundError):
        kaggle.leer(carpeta)


def test_bandeja_externa_no_se_modifica(proyecto_sintetico, tmp_path, monkeypatch):
    externa = tmp_path / "bandeja_docente"
    externa.mkdir()
    (externa / "ventas_2017-09-01.csv").write_text("x\n")
    monkeypatch.setenv("BANDEJA_DIR", str(externa))
    with pytest.raises(RuntimeError):
        correr(proyecto_sintetico, forzar=True)
    assert [r.name for r in externa.iterdir()] == ["ventas_2017-09-01.csv"]


def test_manifiesto_describe_las_salidas(proyecto_sintetico):
    manifiesto = correr(proyecto_sintetico)
    guardado = json.loads((proyecto_sintetico / "data" / "historico" / "manifiesto_simulacion.json").read_text(encoding="utf-8"))
    assert guardado == manifiesto
    assert set(manifiesto["bandeja"]) == {r.name for r in (proyecto_sintetico / "data" / "bandeja").iterdir()}
