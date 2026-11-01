"""Reglas de validación de cada fuente, con archivos en memoria."""
from datetime import date

import pytest
import yaml

from pronostico_ventas.config import RAIZ
from pronostico_ventas.ingesta.validacion import Referencia, validar

CFG = yaml.safe_load((RAIZ / "config" / "validacion.yaml").read_text(encoding="utf-8"))
FECHA = date(2017, 4, 3)
ENTREGA = date(2017, 4, 4)
VENTAS = (
    "id,date,store_nbr,family,sales,onpromotion\n"
    "1,2017-04-03,1,GROCERY I,10.5,0\n"
    "2,2017-04-03,1,MEATS,2.0,3\n"
)
REFERENCIA = Referencia(
    familias=frozenset({"GROCERY I", "MEATS"}),
    tiendas=frozenset({1}),
    filas_por_dia=2,
    umbrales_venta={"GROCERY I": 100.0, "MEATS": 100.0},
)


def ventas(texto=VENTAS, entrega=ENTREGA, referencia=REFERENCIA):
    return validar("ventas", FECHA, entrega, texto.encode(), CFG, referencia)


def test_ventas_validas():
    resultado = ventas()
    assert resultado.errores == []
    assert resultado.advertencias == []
    assert len(resultado.tabla) == 2


def test_id_es_opcional():
    resultado = ventas("date,store_nbr,family,sales,onpromotion\n2017-04-03,1,MEATS,2.0,0\n2017-04-03,1,GROCERY I,1.0,0\n")
    assert resultado.errores == []


@pytest.mark.parametrize(
    ("texto", "error"),
    [
        (VENTAS.replace("sales", "venta"), "columnas_faltantes:sales"),
        (VENTAS.replace("10.5", "-1.0"), "valor_negativo:sales"),
        (VENTAS.replace("10.5", "abc"), "valor_no_numerico:sales"),
        (VENTAS.replace("10.5", ""), "valor_no_numerico:sales"),
        (VENTAS.replace("10.5", "inf"), "valor_no_numerico:sales"),
        (VENTAS.replace("10.5", "nan"), "valor_no_numerico:sales"),
        (VENTAS.replace(",1,GROCERY", ",1.5,GROCERY"), "valor_no_entero:store_nbr"),
        (VENTAS.replace("1,2017-04-03,1,GROCERY", "1,04/03/2017,1,GROCERY"), "fecha_invalida"),
        (VENTAS.replace("1,2017-04-03,1,GROCERY", "1,2017-02-31,1,GROCERY"), "fecha_invalida"),
        (VENTAS.replace("1,2017-04-03,1,GROCERY", "1,2017-04-02,1,GROCERY"), "fecha_distinta_al_nombre"),
        (VENTAS.replace("2,2017-04-03,1,MEATS,2.0", "2,2017-04-03,1,GROCERY I,2.0"), "claves_en_conflicto"),
        ("id,date,store_nbr,family,sales,onpromotion\n", "archivo_vacio"),
        ("", "archivo_ilegible:EmptyDataError"),
    ],
)
def test_datos_invalidos_se_rechazan(texto, error):
    resultado = ventas(texto)
    assert error in resultado.errores
    assert resultado.tabla is None


def test_entrega_anterior_a_la_venta_se_rechaza():
    assert "entrega_anterior_a_la_fecha" in ventas(entrega=date(2017, 4, 2)).errores


def test_filas_identicas_repetidas_no_son_error():
    linea = "1,2017-04-03,1,GROCERY I,10.5,0\n"
    resultado = ventas(VENTAS + linea)
    assert resultado.errores == []
    assert resultado.advertencias == ["filas_repetidas:1"]
    assert len(resultado.tabla) == 2


def test_columna_extra_se_ignora_con_advertencia():
    resultado = ventas(VENTAS.replace("onpromotion\n", "onpromotion,extra\n").replace(",0\n", ",0,x\n").replace(",3\n", ",3,y\n"))
    assert resultado.errores == []
    assert "extra" not in resultado.tabla.columns
    assert resultado.advertencias == ["columnas_ignoradas:extra"]


def test_extremo_legitimo_solo_advierte():
    resultado = ventas(VENTAS.replace("10.5", "124717.0"))
    assert resultado.errores == []
    assert resultado.advertencias == ["valor_extremo:1"]


def test_archivo_parcial_solo_advierte():
    resultado = ventas(VENTAS, referencia=Referencia(filas_por_dia=1782))
    assert resultado.errores == []
    assert resultado.advertencias == ["archivo_parcial:2_de_1782"]


def test_tienda_y_familia_nuevas_solo_advierten():
    texto = VENTAS.replace(",1,GROCERY I", ",9,NUEVA")
    resultado = ventas(texto)
    assert resultado.errores == []
    assert set(resultado.advertencias) == {"familia_desconocida", "tienda_desconocida"}


def test_tienda_sin_ventas_no_advierte():
    assert ventas(VENTAS.replace(",1,GROCERY I,10.5", ",9,GROCERY I,0.0")).advertencias == []


def test_petroleo_admite_nulo_y_rechaza_texto():
    base = "date,dcoilwtico\n2017-04-03,{}\n"
    assert validar("petroleo", FECHA, ENTREGA, base.format("").encode(), CFG, Referencia()).errores == []
    assert validar("petroleo", FECHA, ENTREGA, base.format("x").encode(), CFG, Referencia()).errores == ["valor_no_numerico:dcoilwtico"]


def test_feriado_puede_entregarse_antes_de_su_fecha():
    texto = "date,type,locale,locale_name,description,transferred\n2017-04-03,Holiday,National,Ecuador,X,False\n"
    assert validar("feriados", FECHA, date(2017, 1, 1), texto.encode(), CFG, Referencia()).errores == []


@pytest.mark.parametrize(
    ("original", "nuevo", "error"),
    [("Holiday", "Otro", "tipo_de_feriado_desconocido"), ("National", "Mundo", "alcance_de_feriado_desconocido"), ("False", "x", "transferred_invalido")],
)
def test_feriado_invalido(original, nuevo, error):
    texto = "date,type,locale,locale_name,description,transferred\n2017-04-03,Holiday,National,Ecuador,X,False\n"
    assert error in validar("feriados", FECHA, ENTREGA, texto.replace(original, nuevo).encode(), CFG, Referencia()).errores


def test_plan_no_puede_incluir_fechas_ya_ocurridas():
    texto = "date,store_nbr,family,onpromotion\n2017-04-03,1,MEATS,1\n"
    assert validar("promociones", FECHA, FECHA, texto.encode(), CFG, Referencia()).errores == ["plan_incluye_fechas_ya_ocurridas"]
    posterior = texto.replace("2017-04-03", "2017-04-04")
    assert validar("promociones", FECHA, FECHA, posterior.encode(), CFG, Referencia()).errores == []


def test_tienda_duplicada_con_datos_distintos():
    texto = "store_nbr,city,state,type,cluster\n1,A,B,C,2\n1,A,B,C,3\n"
    assert validar("tiendas", FECHA, FECHA, texto.encode(), CFG, Referencia()).errores == ["claves_en_conflicto"]
