"""Nombres de archivo del contrato provisional de la bandeja."""
from datetime import date

import pytest

from pronostico_ventas.simulador.contrato import COLUMNAS, interpretar_nombre, nombre_archivo


def test_nombres_y_contrato_bandeja():
    nombre = nombre_archivo("ventas", date(2017, 4, 2), date(2017, 4, 9))
    assert nombre == "ventas_2017-04-02__entrega_2017-04-09.csv"
    archivo = interpretar_nombre(nombre)
    assert (archivo.fuente, archivo.fecha, archivo.entrega) == ("ventas", date(2017, 4, 2), date(2017, 4, 9))


def test_nombre_sin_entrega_se_acepta():
    archivo = interpretar_nombre("petroleo_2017-04-03.csv")
    assert archivo.fecha == date(2017, 4, 3)
    assert archivo.entrega is None


@pytest.mark.parametrize(
    "nombre",
    ["ventas.csv", "otra_2017-04-02.csv", "ventas_2017-4-2.csv", "ventas_2017-04-02.parquet", "ventas_2017-04-02__entrega_x.csv"],
)
def test_nombre_fuera_de_contrato_se_rechaza(nombre):
    with pytest.raises(ValueError):
        interpretar_nombre(nombre)


def test_contrato_cubre_las_seis_fuentes():
    assert set(COLUMNAS) == {"ventas", "transacciones", "promociones", "petroleo", "feriados", "tiendas"}
