"""Controles sobre lo que Git rastrea: estructura, ausencia de datos y de secretos."""
import re
import subprocess

import pytest

OBLIGATORIOS = [
    ".env.example",
    ".github/workflows/ci.yml",
    ".gitignore",
    "CLAUDE.md",
    "DECISIONES.md",
    "Makefile",
    "README.md",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements.txt",
    "src/pronostico_ventas/__init__.py",
]
DOCUMENTOS_LOCALES = ["docs/diseno_tecnico_lab1.md", "docs/instrucciones_lab1.md"]
EXTENSIONES_DE_DATOS = (
    ".csv", ".db", ".feather", ".joblib", ".lgb", ".parquet", ".pickle", ".pkl",
    ".sqlite", ".sqlite3", ".tar", ".tsv", ".zip",
)
TAMANO_MAXIMO = 1024 * 1024

# Los patrones se arman por partes para que este archivo no coincida consigo mismo.
SECRETOS = [
    "gh" + r"[pousr]_[A-Za-z0-9]{20,}",
    "github" + r"_pat_[A-Za-z0-9_]{20,}",
    "AK" + r"IA[0-9A-Z]{16}",
    "BEGIN " + r"[A-Z ]*PRIVATE KEY",
]
PERSONALES = [
    "/ho" + r"me/[a-z][a-z0-9_-]+",
    "C:" + r"\\Users\\[A-Za-z]",
    "/mnt/c/" + "Users",
    "@" + r"(gmail|outlook|hotmail|yahoo)\.",
]
SIN_TEXTO = (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico")


def contenido(raiz, ruta):
    return (raiz / ruta).read_text(encoding="utf-8", errors="replace")


@pytest.mark.parametrize("archivo", OBLIGATORIOS)
def test_archivo_obligatorio_rastreado(archivo, rastreados):
    assert archivo in rastreados


def test_git_no_rastrea_datos_ni_modelos(rastreados):
    prohibidos = [
        r for r in rastreados
        if r.lower().endswith(EXTENSIONES_DE_DATOS) and not r.startswith("tests/fixtures/")
    ]
    assert prohibidos == []


def test_data_y_models_solo_contienen_referencias(rastreados):
    prohibidos = [r for r in rastreados if r.startswith(("data/", "models/")) and not r.endswith(".dvc")]
    assert prohibidos == []


def test_main_no_guarda_referencias_de_publicaciones(rastreados):
    prohibidos = [r for r in rastreados if r.startswith("data/publicado/") or r == "data/almacen.dvc"]
    assert prohibidos == []


def test_git_no_rastrea_secretos_locales(rastreados):
    prohibidos = [r for r in rastreados if re.search(r"(^|/)\.env(\.|$)", r) and r != ".env.example"]
    assert prohibidos == []


@pytest.mark.parametrize("documento", DOCUMENTOS_LOCALES)
def test_documento_local_no_se_publica(documento, raiz, rastreados):
    assert documento not in rastreados
    assert subprocess.run(["git", "check-ignore", "-q", "--no-index", documento], cwd=raiz).returncode == 0


def test_archivos_rastreados_son_pequenos(raiz, rastreados):
    grandes = [r for r in rastreados if (raiz / r).stat().st_size > TAMANO_MAXIMO]
    assert grandes == []


def test_sin_credenciales(raiz, rastreados):
    hallados = [
        r for r in rastreados if not r.endswith(SIN_TEXTO)
        if any(re.search(p, contenido(raiz, r)) for p in SECRETOS)
    ]
    assert hallados == []


def test_sin_rutas_ni_correos_personales(raiz, rastreados):
    hallados = [
        r for r in rastreados if not r.endswith(SIN_TEXTO)
        if any(re.search(p, contenido(raiz, r)) for p in PERSONALES)
    ]
    assert hallados == []


def test_env_example_no_contiene_valores(raiz):
    for linea in contenido(raiz, ".env.example").splitlines():
        if linea and not linea.startswith("#"):
            assert linea.endswith("="), linea


def test_el_zip_de_kaggle_esta_ignorado(raiz):
    r = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "store-sales-time-series-forecasting.zip"], cwd=raiz
    )
    assert r.returncode == 0


def test_dependencias_con_version_exacta(raiz):
    for nombre in ("requirements.txt", "requirements-dev.txt"):
        for linea in contenido(raiz, nombre).splitlines():
            if linea and not linea.startswith(("#", "-r")):
                assert re.fullmatch(r"[A-Za-z0-9._-]+==[0-9][0-9A-Za-z.]*", linea), linea


def test_lightgbm_carga_su_libreria_nativa():
    import lightgbm

    assert lightgbm.__version__
