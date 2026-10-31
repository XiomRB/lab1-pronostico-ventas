"""Reglas de disponibilidad por fuente. Son supuestos provisionales y configurables."""
from datetime import date

from pronostico_ventas.simulador.bandeja import (
    cobertura_promociones,
    entrega_diaria,
    entrega_feriado,
    entrega_habil,
    primera_publicacion_promocion,
)

REGLAS = {"tipos_anunciados": ["Transfer", "Bridge"], "anticipacion_anuncio_dias": 14, "patrones_imprevistos": ["Terremoto"]}


def feriado(fecha="2017-03-20", tipo="Holiday", descripcion="Festivo", trasladado="False"):
    return {"date": fecha, "type": tipo, "description": descripcion, "transferred": trasladado}


def test_calendario_por_fuente():
    assert entrega_diaria(date(2017, 4, 2), 1) == date(2017, 4, 3)
    assert entrega_diaria(date(2017, 4, 2), 2) == date(2017, 4, 4)


def test_petroleo_del_viernes_llega_el_lunes():
    assert entrega_habil(date(2017, 4, 7), 1) == date(2017, 4, 10)


def test_petroleo_de_dia_habil_llega_al_dia_siguiente():
    assert entrega_habil(date(2017, 4, 4), 1) == date(2017, 4, 5)


def test_feriado_anual_se_conoce_desde_enero():
    assert entrega_feriado(feriado(), REGLAS) == date(2017, 1, 1)


def test_feriado_respeta_anticipacion():
    assert entrega_feriado(feriado(tipo="Transfer"), REGLAS) == date(2017, 3, 6)
    assert entrega_feriado(feriado(trasladado="True"), REGLAS) == date(2017, 3, 6)


def test_evento_imprevisto_no_se_conoce_antes():
    assert entrega_feriado(feriado(tipo="Event", descripcion="Terremoto Manabi+2"), REGLAS) == date(2017, 3, 20)


def test_plan_de_promociones_cubre_todo_el_horizonte_del_corte():
    cobertura = cobertura_promociones(14, 6, 0)
    assert cobertura == 15
    domingo, lunes = date(2017, 4, 2), date(2017, 4, 3)
    assert primera_publicacion_promocion(date(2017, 4, 3), 6, cobertura) == date(2017, 3, 19)
    assert primera_publicacion_promocion(lunes.replace(day=17), 6, cobertura) == domingo


def test_promocion_siempre_se_publica_antes_de_su_fecha():
    cobertura = cobertura_promociones(14, 6, 0)
    for dia in range(1, 29):
        fecha = date(2017, 5, dia)
        publicacion = primera_publicacion_promocion(fecha, 6, cobertura)
        assert publicacion < fecha
        assert publicacion.weekday() == 6
