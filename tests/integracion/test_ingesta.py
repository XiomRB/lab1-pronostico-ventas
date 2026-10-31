"""Ingesta y control temporal con datos sintéticos, escenario por escenario."""
import hashlib
import json
import os
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from pronostico_ventas import config
from pronostico_ventas.almacen.consulta import as_of, completitud_ventas, frescura
from pronostico_ventas.ingesta.proceso import ingerir
from pronostico_ventas.simulador.contrato import COLUMNAS, interpretar_nombre

FIN = date(2017, 3, 15)
FINAL = date(2017, 4, 30)


@pytest.fixture
def cfg(proyecto_ingesta):
    return config.cargar(proyecto_ingesta)


def manifiesto(cfg):
    return json.loads((cfg.historico / "manifiesto_simulacion.json").read_text(encoding="utf-8"))


def incidente(cfg, tipo):
    return next(i for i in manifiesto(cfg)["incidentes"] if i["tipo"] == tipo)


def huellas(carpeta):
    if not carpeta.exists():
        return {}
    return {str(r.relative_to(carpeta)): hashlib.sha256(r.read_bytes()).hexdigest() for r in sorted(carpeta.rglob("*")) if r.is_file()}


def registro(cfg):
    return [json.loads(r.read_text(encoding="utf-8")) for r in sorted((cfg.almacen / "registro").glob("*.json"))]


def dia(texto):
    return date.fromisoformat(texto)


def valores(tabla):
    return {(f.date().isoformat(), int(t), a): s for f, t, a, s in zip(tabla["date"], tabla["store_nbr"], tabla["family"], tabla["sales"])}


def test_ingesta_normal_acepta_y_solo_rechaza_invalidos(cfg):
    resumen = ingerir(cfg, FINAL)
    assert resumen["rechazado"] == 2
    assert resumen["duplicado"] == 1
    assert resumen["aceptado"] == resumen["disponibles"] - 3
    rechazados = {r["fecha"] for r in registro(cfg) if r["estado"] == "rechazado"}
    assert rechazados == {i["fecha"] for i in manifiesto(cfg)["incidentes"] if i["tipo"] == "dato_invalido"}


def test_solo_procesa_lo_entregado_en_la_fecha_logica(cfg):
    ingerir(cfg, date(2017, 2, 18))
    entregas = [dia(r["fecha_entrega"]) for r in registro(cfg)]
    assert entregas and max(entregas) <= date(2017, 2, 18)


def test_sin_entregas_no_falla(cfg):
    resumen = ingerir(cfg, date(2016, 1, 1))
    assert resumen["disponibles"] == resumen["aceptado"] == 0


def test_bandeja_inexistente_no_falla(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("BANDEJA_DIR", str(tmp_path / "no_existe"))
    assert ingerir(config.cargar(cfg.raiz), FINAL)["disponibles"] == 0


def test_ingesta_es_idempotente(cfg):
    ingerir(cfg, FINAL)
    antes = huellas(cfg.almacen), huellas(cfg.cuarentena)
    resumen = ingerir(cfg, FINAL)
    assert resumen["aceptado"] == resumen["rechazado"] == resumen["duplicado"] == 0
    assert resumen["sin_cambios"] == resumen["disponibles"]
    assert (huellas(cfg.almacen), huellas(cfg.cuarentena)) == antes


def test_ejecucion_diaria_equivale_a_ejecucion_unica(proyecto_ingesta, tmp_path):
    diaria = config.cargar(proyecto_ingesta)
    fecha = date(2017, 2, 15)
    while fecha <= FINAL:
        ingerir(diaria, fecha)
        fecha += timedelta(days=1)
    unica = config.cargar(proyecto_ingesta)
    object.__setattr__(unica, "almacen", tmp_path / "almacen_unico")
    object.__setattr__(unica, "cuarentena", tmp_path / "cuarentena_unica")
    ingerir(unica, FINAL)
    assert huellas(diaria.almacen) == huellas(unica.almacen)
    assert huellas(diaria.cuarentena) == huellas(unica.cuarentena)


def test_archivo_tardio_no_existe_antes_de_llegar(cfg):
    evento = incidente(cfg, "archivo_tardio")
    fecha, llegada = dia(evento["fecha"]), dia(evento["entregas"][0])
    ingerir(cfg, llegada - timedelta(days=1))
    antes = as_of(cfg, "ventas", llegada - timedelta(days=1))
    assert pd.Timestamp(fecha) not in set(antes["date"])
    ingerir(cfg, llegada)
    assert pd.Timestamp(fecha) in set(as_of(cfg, "ventas", llegada)["date"])


def test_archivo_parcial_no_rellena_con_ceros(cfg):
    evento = incidente(cfg, "archivo_parcial")
    fecha, primera, segunda = dia(evento["fecha"]), dia(evento["entregas"][0]), dia(evento["entregas"][1])
    ingerir(cfg, primera)
    parcial = as_of(cfg, "ventas", primera)
    filas = parcial[parcial["date"] == pd.Timestamp(fecha)]
    assert 0 < len(filas) < 6
    assert (filas["sales"].notna()).all()
    assert "archivo_parcial" in " ".join(r for e in registro(cfg) if e["fecha"] == evento["fecha"] for r in e["advertencias"])
    completitud = completitud_ventas(cfg, primera, 3).set_index("date")
    assert not completitud.loc[pd.Timestamp(fecha), "completa"]
    ingerir(cfg, segunda)
    completa = as_of(cfg, "ventas", segunda)
    assert len(completa[completa["date"] == pd.Timestamp(fecha)]) == 6


def test_duplicado_no_crea_una_version_nueva(cfg):
    evento = incidente(cfg, "archivo_duplicado")
    ingerir(cfg, FINAL)
    entradas = [e for e in registro(cfg) if e["fuente"] == "transacciones" and e["fecha"] == evento["fecha"]]
    assert sorted(e["estado"] for e in entradas) == ["aceptado", "duplicado"]
    assert len(list((cfg.almacen / "transacciones").glob(f"transacciones_{evento['fecha']}*"))) == 1


def test_correccion_respeta_lo_conocido_en_cada_fecha(cfg):
    evento = incidente(cfg, "correccion")
    primera, corregida = dia(evento["entregas"][0]), dia(evento["entregas"][1])
    ingerir(cfg, FINAL)
    inicial, final = valores(as_of(cfg, "ventas", corregida - timedelta(days=1))), valores(as_of(cfg, "ventas", corregida))
    cambios = {k for k in final if k[0] == evento["fecha"] and inicial[k] != final[k]}
    assert cambios
    assert len(list((cfg.almacen / "ventas").glob(f"ventas_{evento['fecha']}*"))) == 2
    assert primera < corregida


def test_dato_invalido_no_contamina(cfg):
    ingerir(cfg, FINAL)
    motivos = [json.loads(r.read_text(encoding="utf-8")) for r in sorted(cfg.cuarentena.glob("*/motivo.json"))]
    assert sorted(m["motivos"][0].split(":")[0] for m in motivos) == ["columnas_faltantes", "valor_negativo"]
    assert (as_of(cfg, "ventas", FINAL)["sales"] >= 0).all()


def test_dato_invalido_se_conserva_en_cuarentena_y_el_correcto_entra(cfg):
    ingerir(cfg, FINAL)
    evento = next(i for i in manifiesto(cfg)["incidentes"] if i["tipo"] == "dato_invalido")
    copias = list(cfg.cuarentena.glob(f"*/ventas_{evento['fecha']}*.csv"))
    assert len(copias) == 1
    conocidas = as_of(cfg, "ventas", FINAL)
    assert len(conocidas[conocidas["date"] == pd.Timestamp(evento["fecha"])]) == 6


def test_fuente_ausente_no_falla_ni_inventa_datos(cfg):
    evento = incidente(cfg, "fuente_ausente")
    ingerir(cfg, FINAL)
    assert pd.Timestamp(evento["fecha"]) not in set(as_of(cfg, "transacciones", FINAL)["date"])


def test_fuente_que_no_ha_llegado_se_informa(cfg):
    corte = date(2017, 3, 1)
    ingerir(cfg, corte)
    estados = frescura(cfg, corte + timedelta(days=9))
    ultima = as_of(cfg, "ventas", corte)["date"].max().date()
    assert estados["ventas"]["estado"] == "critica"
    assert estados["ventas"]["atraso_dias"] == (corte + timedelta(days=9) - ultima).days


def test_frescura_normal(cfg):
    ingerir(cfg, date(2017, 3, 6))
    estados = frescura(cfg, date(2017, 3, 6))
    assert estados["ventas"] == {"ultima_fecha": "2017-03-05", "atraso_dias": 1, "estado": "normal"}
    assert estados["transacciones"]["atraso_dias"] == 2
    assert estados["petroleo"]["ultima_fecha"] == "2017-03-03"


def test_dia_sin_operacion_no_aparece_como_error(cfg):
    ingerir(cfg, FINAL)
    assert pd.Timestamp("2017-01-25") not in set(as_of(cfg, "ventas", FINAL)["date"])
    assert not [e for e in registro(cfg) if e["fecha"] == "2017-01-25"]


def test_bandeja_es_de_solo_lectura(cfg):
    antes = huellas(cfg.bandeja)
    os.chmod(cfg.bandeja, 0o555)
    for ruta in cfg.bandeja.iterdir():
        os.chmod(ruta, 0o444)
    try:
        resumen = ingerir(cfg, FINAL)
    finally:
        os.chmod(cfg.bandeja, 0o755)
    assert resumen["aceptado"] > 0
    assert huellas(cfg.bandeja) == antes


def test_nombre_fuera_de_contrato_va_a_cuarentena(cfg):
    (cfg.bandeja / "sin_contrato.csv").write_text("a,b\n1,2\n")
    ingerir(cfg, FINAL)
    entrada = next(e for e in registro(cfg) if e["archivo"] == "sin_contrato.csv")
    assert entrada["estado"] == "rechazado"
    assert entrada["motivos"] == ["nombre_fuera_de_contrato"]


def test_archivo_sin_entrega_usa_el_retraso_de_la_fuente(cfg):
    texto = "date,store_nbr,family,sales,onpromotion\n" + "".join(
        f"2017-03-20,{t},{f},1.0,0\n" for t in (1, 2, 3) for f in ("GROCERY I", "MEATS")
    )
    (cfg.bandeja / "ventas_2017-03-20.csv").write_text(texto)
    ingerir(cfg, date(2017, 3, 20))
    assert pd.Timestamp("2017-03-20") not in set(as_of(cfg, "ventas", date(2017, 3, 20))["date"])
    ingerir(cfg, date(2017, 3, 21))
    assert pd.Timestamp("2017-03-20") in set(as_of(cfg, "ventas", date(2017, 3, 21))["date"])


def test_archivo_cambiado_sin_renombrar_se_conoce_desde_que_se_observa(cfg):
    ruta = sorted(cfg.bandeja.glob("ventas_2017-02-2*"))[0]
    ingerir(cfg, date(2017, 3, 1))
    archivo = interpretar_nombre(ruta.name)
    tabla = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    if "sales" not in tabla:
        pytest.skip("El archivo elegido es un incidente inválido")
    tabla["sales"] = "7.5"
    tabla.to_csv(ruta, index=False)
    ingerir(cfg, date(2017, 3, 5))
    fecha = pd.Timestamp(archivo.fecha)
    antes = as_of(cfg, "ventas", date(2017, 3, 4))
    despues = as_of(cfg, "ventas", date(2017, 3, 5))
    assert not (antes.loc[antes["date"] == fecha, "sales"] == 7.5).all()
    assert (despues.loc[despues["date"] == fecha, "sales"] == 7.5).all()


def test_tienda_nueva_llega_al_abrir(cfg):
    ingerir(cfg, FINAL)
    assert 3 not in set(as_of(cfg, "tiendas", date(2017, 2, 19))["store_nbr"])
    assert 3 in set(as_of(cfg, "tiendas", date(2017, 2, 20))["store_nbr"])


def test_bandeja_externa_con_archivos_sin_entrega(cfg, tmp_path, monkeypatch):
    externa = tmp_path / "externa"
    externa.mkdir()
    (externa / "petroleo_2017-03-14.csv").write_text("date,dcoilwtico\n2017-03-14,44.5\n")
    monkeypatch.setenv("BANDEJA_DIR", str(externa))
    externo = config.cargar(cfg.raiz)
    assert ingerir(externo, FINAL)["aceptado"] == 1
    assert as_of(externo, "petroleo", FINAL)["dcoilwtico"].iloc[-1] == 44.5


def alterar_entregas_futuras(cfg, corte):
    for ruta in cfg.bandeja.iterdir():
        if interpretar_nombre(ruta.name).entrega > corte and ruta.name.startswith("ventas_"):
            tabla = pd.read_csv(ruta, dtype=str, keep_default_na=False)
            if "sales" in tabla:
                tabla["sales"] = "999999.0"
                tabla.to_csv(ruta, index=False)


@pytest.mark.parametrize("fuente", ["ventas", "transacciones", "promociones", "petroleo", "feriados", "tiendas"])
def test_modificar_futuro_no_altera_as_of(proyecto_ingesta, tmp_path, fuente):
    corte = date(2017, 3, 1)
    cfg = config.cargar(proyecto_ingesta)
    ingerir(cfg, FINAL)
    antes = as_of(cfg, fuente, corte)
    otro = config.cargar(proyecto_ingesta)
    object.__setattr__(otro, "almacen", tmp_path / "almacen")
    object.__setattr__(otro, "cuarentena", tmp_path / "cuarentena")
    alterar_entregas_futuras(otro, corte)
    ingerir(otro, FINAL)
    pd.testing.assert_frame_equal(as_of(otro, fuente, corte), antes)


def test_control_modificar_dato_conocido_si_altera_as_of(proyecto_ingesta, tmp_path):
    corte = date(2017, 3, 1)
    cfg = config.cargar(proyecto_ingesta)
    ingerir(cfg, FINAL)
    antes = as_of(cfg, "ventas", corte)
    con_incidente = {i["fecha"] for i in manifiesto(cfg)["incidentes"]}
    ruta = next(r for r in sorted(cfg.bandeja.glob("ventas_2017-02-*")) if interpretar_nombre(r.name).fecha.isoformat() not in con_incidente)
    tabla = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    tabla["sales"] = "999999.0"
    tabla.to_csv(ruta, index=False)
    otro = config.cargar(proyecto_ingesta)
    object.__setattr__(otro, "almacen", tmp_path / "almacen")
    object.__setattr__(otro, "cuarentena", tmp_path / "cuarentena")
    ingerir(otro, FINAL)
    assert not as_of(otro, "ventas", corte)["sales"].equals(antes["sales"])


def test_ventas_as_of_nunca_incluye_el_dia_del_corte(cfg):
    ingerir(cfg, FINAL)
    for corte in (date(2017, 2, 20), date(2017, 3, 6), date(2017, 3, 13)):
        ventas = as_of(cfg, "ventas", corte)
        assert ventas["date"].max() < pd.Timestamp(corte)
        assert (ventas["fecha_entrega"] <= pd.Timestamp(corte)).all()


@pytest.mark.parametrize("fuente", ["ventas", "transacciones", "promociones", "petroleo", "feriados", "tiendas"])
def test_as_of_respeta_el_corte_dentro_del_historico(cfg, fuente):
    corte = date(2017, 2, 1)
    completo = pd.read_parquet(cfg.historico / f"{fuente}.parquet")
    tabla = as_of(cfg, fuente, corte)
    conocido = completo[completo["fecha_entrega"] <= pd.Timestamp(corte)]
    assert (tabla["fecha_entrega"] <= pd.Timestamp(corte)).all()
    assert len(tabla) == len(conocido)


def test_as_of_historico_no_ve_ventas_posteriores_al_corte(cfg):
    corte = date(2017, 2, 1)
    assert as_of(cfg, "ventas", corte)["date"].max() == pd.Timestamp("2017-01-31")
    assert as_of(cfg, "transacciones", corte)["date"].max() == pd.Timestamp("2017-01-30")
    assert as_of(cfg, "petroleo", corte)["date"].max() == pd.Timestamp("2017-01-31")


def test_petroleo_del_viernes_no_se_conoce_el_fin_de_semana(cfg):
    ingerir(cfg, FINAL)
    assert as_of(cfg, "petroleo", date(2017, 3, 5))["date"].max() == pd.Timestamp("2017-03-02")
    assert as_of(cfg, "petroleo", date(2017, 3, 6))["date"].max() == pd.Timestamp("2017-03-03")


def test_evento_imprevisto_no_se_conoce_antes(cfg):
    ingerir(cfg, FINAL)
    assert not as_of(cfg, "feriados", date(2017, 2, 28))["description"].str.contains("Terremoto").any()
    assert as_of(cfg, "feriados", date(2017, 3, 1))["description"].str.contains("Terremoto").any()


def test_feriado_anunciado_aparece_antes_de_ocurrir(cfg):
    ingerir(cfg, FINAL)
    assert not as_of(cfg, "feriados", date(2017, 2, 16))["type"].eq("Transfer").any()
    assert as_of(cfg, "feriados", date(2017, 2, 17))["type"].eq("Transfer").any()


def test_plan_de_promociones_cubre_fechas_futuras(cfg):
    ingerir(cfg, FINAL)
    plan = as_of(cfg, "promociones", date(2017, 2, 19))
    assert plan["date"].max() > pd.Timestamp("2017-02-19")


def test_as_of_respeta_columnas_y_desde(cfg):
    ingerir(cfg, FINAL)
    tabla = as_of(cfg, "ventas", FINAL, columnas=["date", "sales"], desde=date(2017, 3, 1))
    assert list(tabla.columns) == ["date", "sales"]
    assert tabla["date"].min() == pd.Timestamp("2017-03-01")


def test_as_of_rechaza_fuente_desconocida(cfg):
    with pytest.raises(ValueError):
        as_of(cfg, "otra", FINAL)


def test_as_of_es_determinista(cfg):
    ingerir(cfg, FINAL)
    pd.testing.assert_frame_equal(as_of(cfg, "ventas", FINAL), as_of(cfg, "ventas", FINAL))


def test_reconstruye_la_ultima_verdad_de_kaggle(cfg):
    ingerir(cfg, FINAL)
    ventas = as_of(cfg, "ventas", FINAL)
    assert list(ventas.columns[:len(COLUMNAS["ventas"])]) == COLUMNAS["ventas"]
    assert len(ventas) == len(pd.read_parquet(cfg.historico / "ventas.parquet")) + 28 * 6


def test_resultado_no_depende_de_la_hora(proyecto_ingesta, tmp_path, monkeypatch):
    cfg = config.cargar(proyecto_ingesta)
    ingerir(cfg, FINAL)
    primero = as_of(cfg, "ventas", FINAL)
    entradas = registro(cfg)

    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2030, 1, 1)

    monkeypatch.setattr("datetime.datetime", Reloj)
    otro = config.cargar(proyecto_ingesta)
    object.__setattr__(otro, "almacen", tmp_path / "almacen")
    object.__setattr__(otro, "cuarentena", tmp_path / "cuarentena")
    ingerir(otro, FINAL)
    assert registro(otro) == entradas
    pd.testing.assert_frame_equal(as_of(otro, "ventas", FINAL), primero, check_dtype=False)


def test_el_codigo_no_consulta_el_reloj(raiz):
    llamadas = ("datetime.now", "datetime.utcnow", "date.today", "time.time(", "pendulum.now")
    for ruta in (raiz / "src").rglob("*.py"):
        contenido = ruta.read_text(encoding="utf-8")
        assert not [llamada for llamada in llamadas if llamada in contenido], ruta


def test_registro_conserva_trazabilidad(cfg):
    ingerir(cfg, FINAL)
    for entrada in registro(cfg):
        assert len(entrada["hash"]) == 64
        if entrada["estado"] == "aceptado":
            assert (cfg.almacen / entrada["fuente"] / entrada["almacen"]).is_file()
