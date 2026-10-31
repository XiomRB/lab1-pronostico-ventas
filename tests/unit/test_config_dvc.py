"""La configuración versionada de DVC debe ser local y estricta."""
import configparser
import re


def leer_config(raiz):
    # DVC admite comillas en los nombres de sección y sangría en las claves.
    config = configparser.ConfigParser()
    config.read(raiz / ".dvc" / "config", encoding="utf-8")
    return config


def remotos(raiz):
    config = leer_config(raiz)
    return {s: config[s] for s in config.sections() if s.startswith("'remote")}


def test_remoto_por_defecto_es_local(raiz):
    assert leer_config(raiz)["core"]["remote"] == "local"


def test_remoto_es_solo_local(raiz):
    configurados = remotos(raiz)
    assert list(configurados) == ["'remote \"local\"'"]
    url = configurados["'remote \"local\"'"]["url"]
    assert url == "../../dvc-storage/lab1"
    assert not re.match(r"[a-z0-9+.-]+://", url)


def test_verify_true_configurado(raiz):
    assert remotos(raiz)["'remote \"local\"'"]["verify"] == "true"


def test_config_local_no_esta_rastreada(rastreados):
    assert ".dvc/config.local" not in rastreados
