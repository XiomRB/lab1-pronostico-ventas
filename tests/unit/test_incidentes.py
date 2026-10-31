"""Cada incidente altera solo la entrega inicial y conserva el valor real."""
from datetime import date, timedelta

import pandas as pd
import pytest

from pronostico_ventas.simulador.bandeja import Entrega
from pronostico_ventas.simulador.incidentes import aplicar


def tabla(fecha):
    return pd.DataFrame({
        "id": [str(i) for i in range(4)],
        "date": fecha.isoformat(),
        "store_nbr": ["1", "1", "2", "2"],
        "family": ["A", "B", "A", "B"],
        "sales": ["1.0", "2.5", "3.0", "4.0"],
        "onpromotion": "0",
    })


@pytest.fixture
def entregas():
    fechas = [date(2017, 4, 1) + timedelta(days=i) for i in range(20)]
    return [Entrega("ventas", f, f + timedelta(days=1), tabla(f)) for f in fechas]


def regla(tipo, **extra):
    return {tipo: {"cantidad": 1, "fuente": "ventas", **extra}}


def test_extremo_no_altera_el_dato(entregas):
    entregas[3].tabla.loc[0, "sales"] = "999.5"
    salida, registro = aplicar(entregas, {"extremo_legitimo": {"cantidad": 1}}, 1)
    assert registro[0]["sales"] == "999.5"
    assert salida[3].tabla.loc[0, "sales"] == "999.5"


def test_tardio_mueve_la_entrega(entregas):
    originales = {e.fecha: e.entrega for e in entregas}
    salida, registro = aplicar(entregas, regla("archivo_tardio", dias_extra=4), 1)
    fecha = date.fromisoformat(registro[0]["fecha"])
    item = next(e for e in salida if e.fecha == fecha)
    assert item.entrega == originales[fecha] + timedelta(days=4)


def test_parcial_se_completa_con_la_segunda_entrega(entregas):
    salida, registro = aplicar(entregas, regla("archivo_parcial", fraccion_inicial=0.5, dias_extra=2), 1)
    partes = [e for e in salida if e.fecha.isoformat() == registro[0]["fecha"]]
    assert len(partes) == 2
    assert sorted(pd.concat(p.tabla for p in partes)["id"]) == ["0", "1", "2", "3"]
    assert len(partes[0].tabla) == 2


def test_duplicado_es_identico(entregas):
    salida, registro = aplicar(entregas, regla("archivo_duplicado", dias_extra=3), 1)
    partes = [e for e in salida if e.fecha.isoformat() == registro[0]["fecha"]]
    assert len(partes) == 2
    assert partes[0].tabla.equals(partes[1].tabla)
    assert partes[0].entrega != partes[1].entrega


def test_correccion_recupera_valor_real(entregas):
    real = {e.fecha: e.tabla.copy() for e in entregas}
    salida, registro = aplicar(entregas, regla("correccion", filas=2, factor=1.5, dias_extra=7), 1)
    fecha = date.fromisoformat(registro[0]["fecha"])
    primera, corregida = sorted((e for e in salida if e.fecha == fecha), key=lambda e: e.entrega)
    assert not primera.tabla.equals(real[fecha])
    assert corregida.tabla.equals(real[fecha])


def test_dato_invalido_tiene_ambas_variantes_y_archivo_correcto(entregas):
    salida, registro = aplicar(entregas, {"dato_invalido": {"cantidad": 2, "fuente": "ventas", "dias_extra": 1}}, 1)
    assert {r["detalle"] for r in registro} == {"columna sales renombrada", "venta negativa"}
    for evento in registro:
        primera, correcta = sorted((e for e in salida if e.fecha.isoformat() == evento["fecha"]), key=lambda e: e.entrega)
        invalida = "sales" not in primera.tabla.columns or (primera.tabla["sales"] == "-1.0").any()
        assert invalida
        assert correcta.tabla.equals(tabla(primera.fecha))


def test_fuente_ausente_elimina_la_entrega(entregas):
    total = len(entregas)
    salida, registro = aplicar(entregas, regla("fuente_ausente"), 1)
    assert len(salida) == total - 1
    assert registro[0]["fecha"] not in {e.fecha.isoformat() for e in salida}


def test_incidentes_usan_fechas_distintas(entregas):
    reglas = {
        "archivo_tardio": {"cantidad": 3, "fuente": "ventas", "dias_extra": 1},
        "correccion": {"cantidad": 3, "fuente": "ventas", "filas": 1, "factor": 2, "dias_extra": 1},
    }
    _, registro = aplicar(entregas, reglas, 1)
    assert len({r["fecha"] for r in registro}) == 6


def test_misma_semilla_elige_lo_mismo():
    def correr():
        fechas = [date(2017, 4, 1) + timedelta(days=i) for i in range(20)]
        base = [Entrega("ventas", f, f, tabla(f)) for f in fechas]
        return aplicar(base, regla("correccion", filas=2, factor=1.5, dias_extra=1), 7)[1]

    assert correr() == correr()


def test_demasiados_incidentes_se_rechazan(entregas):
    with pytest.raises(ValueError):
        aplicar(entregas, {"archivo_tardio": {"cantidad": 30, "fuente": "ventas", "dias_extra": 1}}, 1)
