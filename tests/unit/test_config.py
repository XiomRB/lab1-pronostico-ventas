"""Validación de la configuración versionada."""
import shutil

import pytest
import yaml

from pronostico_ventas import config


@pytest.fixture
def copia(tmp_path, raiz, monkeypatch):
    monkeypatch.delenv("BANDEJA_DIR", raising=False)
    shutil.copytree(raiz / "config", tmp_path / "config")
    return tmp_path


def editar(raiz, archivo, cambios):
    ruta = raiz / "config" / archivo
    contenido = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    contenido.update(cambios)
    ruta.write_text(yaml.safe_dump(contenido), encoding="utf-8")


def test_config_real_es_valida(raiz, monkeypatch):
    monkeypatch.delenv("BANDEJA_DIR", raising=False)
    cfg = config.cargar(raiz)
    assert cfg.horizonte_dias >= 1
    assert cfg.bandeja == raiz / "data" / "bandeja"


def test_rutas_configurables(copia, monkeypatch, tmp_path):
    otra = tmp_path / "otra_bandeja"
    monkeypatch.setenv("BANDEJA_DIR", str(otra))
    assert config.cargar(copia).bandeja == otra


def test_horizonte_configurable(copia):
    editar(copia, "modelo.yaml", {"horizonte_dias": 21})
    assert config.cargar(copia).horizonte_dias == 21


def test_fechas_de_evaluacion_configurables(copia):
    editar(copia, "simulacion.yaml", {"corte_historico": "2016-12-31", "fin_bandeja": "2017-06-30"})
    cfg = config.cargar(copia)
    assert (cfg.corte_historico.isoformat(), cfg.fin_bandeja.isoformat()) == ("2016-12-31", "2017-06-30")


@pytest.mark.parametrize(
    ("archivo", "cambios"),
    [
        ("modelo.yaml", {"horizonte_dias": 0}),
        ("modelo.yaml", {"dia_corte": 7}),
        ("simulacion.yaml", {"corte_historico": "31/03/2017"}),
        ("simulacion.yaml", {"fin_bandeja": "2017-01-01"}),
    ],
)
def test_configuracion_invalida_se_rechaza(copia, archivo, cambios):
    editar(copia, archivo, cambios)
    with pytest.raises(ValueError):
        config.cargar(copia)


def test_falta_una_fuente(copia):
    ruta = copia / "config" / "fuentes.yaml"
    contenido = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    del contenido["petroleo"]
    ruta.write_text(yaml.safe_dump(contenido), encoding="utf-8")
    with pytest.raises(ValueError):
        config.cargar(copia)
