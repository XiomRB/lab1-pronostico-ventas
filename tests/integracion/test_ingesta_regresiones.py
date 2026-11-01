"""Regresiones de la ingesta: versiones, observación tardía, completitud y claves."""
import json
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from pronostico_ventas import config
from pronostico_ventas.almacen.consulta import as_of, avisos_completitud, completitud_ventas
from pronostico_ventas.ingesta.proceso import ingerir

FINAL = date(2017, 4, 30)
FECHA = "2017-03-20"
NOMBRE = "ventas_2017-03-20__entrega_"
SERIES = [(t, f) for t in (1, 2, 3) for f in ("GROCERY I", "MEATS")]


@pytest.fixture
def cfg(proyecto_ingesta):
    return config.cargar(proyecto_ingesta)


def csv_ventas(valor, series=SERIES, fecha=FECHA):
    return "date,store_nbr,family,sales,onpromotion\n" + "".join(f"{fecha},{t},{f},{valor},0\n" for t, f in series)


def registro(cfg):
    return [json.loads(r.read_text(encoding="utf-8")) for r in sorted((cfg.almacen / "registro").glob("*.json"))]


def venta(cfg, corte=FINAL, fecha=FECHA, tienda=1, familia="GROCERY I"):
    tabla = as_of(cfg, "ventas", corte)
    fila = tabla[(tabla["date"] == pd.Timestamp(fecha)) & (tabla["store_nbr"] == tienda) & (tabla["family"] == familia)]
    return float(fila["sales"].iloc[0]) if len(fila) else None


def entradas(cfg, fecha=FECHA, fuente="ventas"):
    return sorted((e for e in registro(cfg) if e["fecha"] == fecha and e["fuente"] == fuente), key=lambda e: e["secuencia"])


# D1: correcciones que vuelven a un contenido anterior


def test_a_b_a_en_archivos_distintos_deja_a_vigente(cfg):
    for dia, valor in (("21", 1.0), ("28", 2.0)):
        (cfg.bandeja / f"{NOMBRE}2017-03-{dia}.csv").write_text(csv_ventas(valor))
    (cfg.bandeja / f"{NOMBRE}2017-04-02.csv").write_text(csv_ventas(1.0))
    ingerir(cfg, FINAL)
    assert venta(cfg) == 1.0
    assert venta(cfg, date(2017, 3, 30)) == 2.0
    assert venta(cfg, date(2017, 3, 25)) == 1.0
    assert [e["estado"] for e in entradas(cfg)] == ["aceptado", "aceptado", "aceptado"]
    assert len(list((cfg.almacen / "ventas").glob(f"ventas_{FECHA}*"))) == 3


def test_a_b_a_con_el_mismo_nombre_deja_a_vigente(cfg):
    ruta = cfg.bandeja / f"{NOMBRE}2017-03-21.csv"
    for valor, dia in ((1.0, 22), (2.0, 24), (1.0, 26)):
        ruta.write_text(csv_ventas(valor))
        ingerir(cfg, date(2017, 3, dia))
    assert venta(cfg, date(2017, 3, 26)) == 1.0
    assert venta(cfg, date(2017, 3, 25)) == 2.0
    assert len(entradas(cfg)) == 3


def test_reentrega_de_la_version_vigente_es_duplicado(cfg):
    (cfg.bandeja / f"{NOMBRE}2017-03-21.csv").write_text(csv_ventas(1.0))
    (cfg.bandeja / f"{NOMBRE}2017-03-28.csv").write_text(csv_ventas(1.0))
    ingerir(cfg, FINAL)
    assert [e["estado"] for e in entradas(cfg)] == ["aceptado", "duplicado"]


# D2: archivos descubiertos después de un corte


def test_archivo_descubierto_tarde_no_cambia_un_corte_pasado(cfg):
    ingerir(cfg, date(2017, 3, 10))
    corte = date(2017, 3, 1)
    antes = as_of(cfg, "ventas", corte)
    tardio = "ventas_2017-02-20__entrega_2017-02-25.csv"
    (cfg.bandeja / tardio).write_text(csv_ventas(777.0, fecha="2017-02-20"))
    ingerir(cfg, date(2017, 3, 11))
    pd.testing.assert_frame_equal(as_of(cfg, "ventas", corte), antes)
    pd.testing.assert_frame_equal(as_of(cfg, "ventas", date(2017, 3, 10)), as_of(cfg, "ventas", date(2017, 3, 10)))
    assert venta(cfg, date(2017, 3, 11), "2017-02-20") == 777.0
    assert venta(cfg, date(2017, 3, 10), "2017-02-20") != 777.0


def test_conserva_entrega_original_y_primera_observacion(cfg):
    ingerir(cfg, date(2017, 3, 10))
    (cfg.bandeja / "ventas_2017-02-20__entrega_2017-02-25.csv").write_text(csv_ventas(777.0, fecha="2017-02-20"))
    ingerir(cfg, date(2017, 3, 11))
    entrada = next(e for e in registro(cfg) if e["archivo"] == "ventas_2017-02-20__entrega_2017-02-25.csv")
    assert entrada["fecha_entrega"] == "2017-02-25"
    assert entrada["conocido_desde"] == "2017-03-11"


def test_archivo_descubierto_en_reproceso_tampoco_cambia_el_pasado(cfg):
    ingerir(cfg, date(2017, 3, 10))
    (cfg.bandeja / "ventas_2017-02-20__entrega_2017-02-25.csv").write_text(csv_ventas(777.0, fecha="2017-02-20"))
    ingerir(cfg, date(2017, 3, 5))
    entrada = next(e for e in registro(cfg) if e["archivo"] == "ventas_2017-02-20__entrega_2017-02-25.csv")
    assert entrada["conocido_desde"] == "2017-03-10"


def test_saltar_dias_no_marca_entregas_normales_como_tardias(cfg):
    ingerir(cfg, date(2017, 2, 20))
    ingerir(cfg, date(2017, 3, 1))
    normales = [e for e in registro(cfg) if e["fuente"] == "ventas" and e["estado"] == "aceptado"]
    assert all(e["conocido_desde"] == e["fecha_entrega"] for e in normales)


def test_as_of_puede_devolver_conocido_desde(cfg):
    ingerir(cfg, date(2017, 3, 10))
    tabla = as_of(cfg, "ventas", date(2017, 3, 10), columnas=["conocido_desde"])
    assert (tabla["conocido_desde"] <= pd.Timestamp("2017-03-10")).all()
    vacia = as_of(cfg, "ventas", date(2010, 1, 1), columnas=["conocido_desde"])
    assert vacia.empty and list(vacia.columns) == ["conocido_desde"]


# D3: completitud por series


def test_filas_sustituidas_por_otra_tienda_no_estan_completas(cfg):
    series = [(1, "GROCERY I"), (1, "MEATS"), (3, "GROCERY I"), (3, "MEATS"), (99, "GROCERY I"), (99, "MEATS")]
    (cfg.bandeja / f"{NOMBRE}2017-03-21.csv").write_text(csv_ventas(0.0, series))
    ingerir(cfg, FINAL)
    entrada = entradas(cfg)[0]
    assert entrada["estado"] == "aceptado"
    assert "archivo_parcial:4_de_6" in entrada["advertencias"]
    assert "series_no_esperadas:2" in entrada["advertencias"]
    completitud = completitud_ventas(cfg, date(2017, 3, 22), 3).set_index("date")
    assert not completitud.loc[pd.Timestamp(FECHA), "completa"]


def test_familia_faltante_no_esta_completa(cfg):
    (cfg.bandeja / f"{NOMBRE}2017-03-21.csv").write_text(csv_ventas(1.0, SERIES[:-1] + [(3, "BEVERAGES")]))
    ingerir(cfg, FINAL)
    assert any(a.startswith("archivo_parcial:5_de_6") for a in entradas(cfg)[0]["advertencias"])
    assert not completitud_ventas(cfg, date(2017, 3, 22), 3).set_index("date").loc[pd.Timestamp(FECHA), "completa"]


def test_filas_inventadas_no_suman_completitud(cfg):
    series = [(1, "GROCERY I")] + [(90 + i, "GROCERY I") for i in range(5)]
    (cfg.bandeja / f"{NOMBRE}2017-03-21.csv").write_text(csv_ventas(1.0, series))
    ingerir(cfg, FINAL)
    fila = completitud_ventas(cfg, date(2017, 3, 22), 3).set_index("date").loc[pd.Timestamp(FECHA)]
    assert fila["filas"] == 1
    assert not fila["completa"]


def test_duplicado_no_suma_completitud(cfg):
    texto = csv_ventas(1.0, SERIES[:5]) + f"{FECHA},3,GROCERY I,1.0,0\n"
    (cfg.bandeja / f"{NOMBRE}2017-03-21.csv").write_text(texto)
    ingerir(cfg, FINAL)
    assert not completitud_ventas(cfg, date(2017, 3, 22), 3).set_index("date").loc[pd.Timestamp(FECHA), "completa"]


# D4: identificadores inválidos


@pytest.mark.parametrize("identificador", ["abc", "1.5", "-1", "", "99999999999999999999999"])
def test_id_invalido_va_a_cuarentena_y_el_resto_continua(cfg, identificador):
    texto = csv_ventas(1.0).replace("date,store_nbr", "id,date,store_nbr").replace(f"{FECHA},", f"{identificador},{FECHA},")
    (cfg.bandeja / f"{NOMBRE}2017-03-21.csv").write_text(texto)
    (cfg.bandeja / "ventas_2017-03-21__entrega_2017-03-22.csv").write_text(csv_ventas(2.0, fecha="2017-03-21"))
    resumen = ingerir(cfg, FINAL)
    assert entradas(cfg)[0]["estado"] == "rechazado"
    assert list(cfg.cuarentena.glob(f"*/{NOMBRE}2017-03-21.csv"))
    assert resumen["aceptado"] >= 1
    assert venta(cfg, fecha="2017-03-21") == 2.0
    assert venta(cfg) is None


def test_error_inesperado_de_un_archivo_no_detiene_la_ingesta(cfg, monkeypatch):
    (cfg.bandeja / f"{NOMBRE}2017-03-21.csv").write_text(csv_ventas(1.0))
    from pronostico_ventas.ingesta import proceso

    real = proceso.tipar

    def fallar(tabla):
        if (tabla.get("date") == FECHA).any():
            raise TypeError("fallo inesperado")
        return real(tabla)

    monkeypatch.setattr(proceso, "tipar", fallar)
    resumen = ingerir(cfg, FINAL)
    assert entradas(cfg)[0]["motivos"] == ["error_al_procesar:TypeError"]
    assert resumen["aceptado"] > 0


# D5: empates de fecha de entrega


def test_empate_gana_la_ultima_observacion_y_no_el_hash(proyecto_ingesta):
    for primero, segundo in ((1.0, 2.0), (2.0, 1.0)):
        cfg = config.cargar(proyecto_ingesta)
        object.__setattr__(cfg, "almacen", proyecto_ingesta / f"almacen_{primero}")
        object.__setattr__(cfg, "cuarentena", proyecto_ingesta / f"cuarentena_{primero}")
        ruta = cfg.bandeja / f"{NOMBRE}2017-03-21.csv"
        ruta.write_text(csv_ventas(primero))
        ingerir(cfg, date(2017, 3, 21))
        ruta.write_text(csv_ventas(segundo))
        ingerir(cfg, date(2017, 3, 21))
        assert venta(cfg, date(2017, 3, 21)) == segundo
        ruta.unlink()


def test_empate_no_depende_del_orden_de_lectura(proyecto_ingesta, monkeypatch):
    original = Path.iterdir
    resultados = []
    for semilla in range(3):
        cfg = config.cargar(proyecto_ingesta)
        object.__setattr__(cfg, "almacen", proyecto_ingesta / f"almacen_{semilla}")
        object.__setattr__(cfg, "cuarentena", proyecto_ingesta / f"cuarentena_{semilla}")
        (cfg.bandeja / f"{NOMBRE}2017-03-21.csv").write_text(csv_ventas(1.0))
        (cfg.bandeja / "ventas_2017-03-20.csv").write_text(csv_ventas(2.0))
        azar = random.Random(semilla)

        def desordenar(self, azar=azar):
            archivos = list(original(self))
            azar.shuffle(archivos)
            return iter(archivos)

        with monkeypatch.context() as parche:
            parche.setattr(Path, "iterdir", desordenar)
            ingerir(cfg, FINAL)
        resultados.append((venta(cfg), [(e["archivo"], e["secuencia"]) for e in entradas(cfg)]))
    assert resultados[0] == resultados[1] == resultados[2]


# D6: claves inválidas


@pytest.mark.parametrize("familia", ["", " MEATS", "MEATS ", "meats", "MEA?TS"])
def test_clave_invalida_no_crea_series(cfg, familia):
    (cfg.bandeja / f"{NOMBRE}2017-03-21.csv").write_text(csv_ventas(1.0, [(1, familia), (2, "MEATS")]))
    ingerir(cfg, FINAL)
    assert entradas(cfg)[0]["estado"] == "rechazado"
    assert set(as_of(cfg, "ventas", FINAL)["family"]) == {"GROCERY I", "MEATS"}


@pytest.mark.parametrize("tienda", ["1.0", " 1", "uno"])
def test_tienda_con_formato_invalido_se_rechaza(cfg, tienda):
    (cfg.bandeja / f"{NOMBRE}2017-03-21.csv").write_text(csv_ventas(1.0).replace(f"{FECHA},1,", f"{FECHA},{tienda},"))
    ingerir(cfg, FINAL)
    assert entradas(cfg)[0]["estado"] == "rechazado"


# D7: completitud por frecuencia


@pytest.fixture
def cfg_limpio(tmp_path, proyecto_sintetico):
    """Proyecto sin incidentes, para que cualquier aviso sea atribuible a la prueba."""
    import yaml

    from pronostico_ventas.simulador.__main__ import ejecutar

    ruta = proyecto_sintetico / "config" / "simulacion.yaml"
    ajustes = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    ajustes["incidentes"] = {}
    ruta.write_text(yaml.safe_dump(ajustes), encoding="utf-8")
    cfg = config.cargar(proyecto_sintetico)
    ejecutar(cfg)
    return cfg


@pytest.mark.parametrize("corte", [date(2017, 3, 4), date(2017, 3, 5), date(2017, 3, 6), date(2017, 3, 7), date(2017, 3, 13)])
def test_frecuencias_distintas_no_generan_falsas_ausencias(cfg_limpio, corte):
    ingerir(cfg_limpio, corte)
    assert avisos_completitud(cfg_limpio, corte) == []


def test_dia_sin_operacion_no_avisa(cfg_limpio):
    cfg = cfg_limpio
    ingerir(cfg, date(2017, 2, 5))
    assert [a for a in avisos_completitud(cfg, date(2017, 2, 5)) if "2017-01-25" in a and a.startswith("transacciones")] == []


def test_transaccion_faltante_avisa_solo_para_tienda_con_ventas(cfg_limpio):
    cfg = cfg_limpio
    (next(cfg.bandeja.glob("transacciones_2017-03-02__*"))).unlink()
    ingerir(cfg, date(2017, 3, 6))
    assert avisos_completitud(cfg, date(2017, 3, 6)) == ["transacciones:2017-03-02:3_tiendas"]


def test_transaccion_dentro_de_su_retraso_no_avisa(cfg_limpio):
    cfg = cfg_limpio
    (next(cfg.bandeja.glob("transacciones_2017-03-05__*"))).unlink()
    ingerir(cfg, date(2017, 3, 6))
    assert avisos_completitud(cfg, date(2017, 3, 6)) == []
    ingerir(cfg, date(2017, 3, 7))
    assert avisos_completitud(cfg, date(2017, 3, 7)) == ["transacciones:2017-03-05:3_tiendas"]


def test_petroleo_faltante_avisa_y_el_fin_de_semana_no(cfg_limpio):
    cfg = cfg_limpio
    (next(cfg.bandeja.glob("petroleo_2017-03-03__*"))).unlink()
    ingerir(cfg, date(2017, 3, 5))
    assert avisos_completitud(cfg, date(2017, 3, 5)) == []
    ingerir(cfg, date(2017, 3, 6))
    assert avisos_completitud(cfg, date(2017, 3, 6)) == ["petroleo:2017-03-03:sin_precio"]


def test_ventas_faltantes_avisan(cfg_limpio):
    cfg = cfg_limpio
    (next(cfg.bandeja.glob("ventas_2017-03-02__*"))).unlink()
    resumen = ingerir(cfg, date(2017, 3, 6))
    assert "ventas:2017-03-02:0_series" in resumen["avisos_completitud"]


def test_sin_datos_en_la_ventana_no_falla(cfg_limpio):
    assert isinstance(avisos_completitud(cfg_limpio, date(2016, 1, 1)), list)
