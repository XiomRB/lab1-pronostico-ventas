import shutil
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def raiz() -> Path:
    return RAIZ


@pytest.fixture(scope="session")
def rastreados() -> list[str]:
    salida = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True)
    return salida.stdout.splitlines()


TIENDAS = [
    ("1", "Quito", "Pichincha", "D", "13"),
    ("2", "Quito", "Pichincha", "A", "14"),
    ("3", "Cuenca", "Azuay", "B", "6"),
]
FERIADOS = [
    ("2017-01-20", "Holiday", "National", "Ecuador", "Festivo de prueba", "False"),
    ("2017-02-10", "Holiday", "National", "Ecuador", "Festivo trasladado", "True"),
    ("2017-02-27", "Holiday", "National", "Ecuador", "Festivo anual", "False"),
    ("2017-03-01", "Event", "National", "Ecuador", "Terremoto de prueba", "False"),
    ("2017-03-03", "Transfer", "National", "Ecuador", "Traslado de prueba", "False"),
    ("2017-03-30", "Bridge", "National", "Ecuador", "Puente futuro", "False"),
    ("2017-12-25", "Holiday", "National", "Ecuador", "Navidad", "False"),
]


def _csv_kaggle() -> dict[str, str]:
    """Archivos con la forma de Kaggle y valores inventados. Falta un día, como la Navidad real."""
    fechas = [d for d in pd.date_range("2017-01-01", "2017-03-15").strftime("%Y-%m-%d") if d != "2017-01-25"]
    train, transacciones, identificador = ["id,date,store_nbr,family,sales,onpromotion"], ["date,store_nbr,transactions"], 0
    for numero, fecha in enumerate(fechas):
        for tienda in (1, 2, 3):
            abierta = tienda != 3 or fecha >= "2017-02-20"
            for familia, base in (("GROCERY I", 100), ("MEATS", 7.25)):
                venta = float(base * tienda + numero) if abierta else 0.0
                train.append(f"{identificador},{fecha},{tienda},{familia},{venta},{numero % 3 if abierta else 0}")
                identificador += 1
            if abierta:
                transacciones.append(f"{fecha},{tienda},{100 + numero}")
    petroleo = ["date,dcoilwtico"]
    for fecha in pd.bdate_range("2017-01-02", "2017-03-31").strftime("%Y-%m-%d"):
        petroleo.append(f"{fecha},{'' if fecha == '2017-02-20' else '50.25'}")
    return {
        "train.csv": "\n".join(train) + "\n",
        "transactions.csv": "\n".join(transacciones) + "\n",
        "oil.csv": "\n".join(petroleo) + "\n",
        "stores.csv": "store_nbr,city,state,type,cluster\n" + "".join(",".join(f) + "\n" for f in TIENDAS),
        "holidays_events.csv": "date,type,locale,locale_name,description,transferred\n"
        + "".join(",".join(f) + "\n" for f in FERIADOS),
        "test.csv": "no debe leerse\n",
        "sample_submission.csv": "no debe leerse\n",
    }


INCIDENTES_SINTETICOS = {
    "extremo_legitimo": {"cantidad": 1},
    "archivo_tardio": {"cantidad": 1, "fuente": "ventas", "dias_extra": 4},
    "archivo_parcial": {"cantidad": 1, "fuente": "ventas", "fraccion_inicial": 0.5, "dias_extra": 2},
    "archivo_duplicado": {"cantidad": 1, "fuente": "transacciones", "dias_extra": 3},
    "correccion": {"cantidad": 1, "fuente": "ventas", "filas": 2, "factor": 1.5, "dias_extra": 7},
    "dato_invalido": {"cantidad": 2, "fuente": "ventas", "dias_extra": 1},
    "fuente_ausente": {"cantidad": 1, "fuente": "transacciones"},
}


@pytest.fixture
def proyecto_sintetico(tmp_path, raiz, monkeypatch) -> Path:
    """Proyecto temporal con configuración real, fechas de prueba y un ZIP sintético."""
    monkeypatch.delenv("BANDEJA_DIR", raising=False)
    proyecto = tmp_path / "proyecto"
    shutil.copytree(raiz / "config", proyecto / "config")
    simulacion = proyecto / "config" / "simulacion.yaml"
    ajustes = yaml.safe_load(simulacion.read_text(encoding="utf-8"))
    ajustes["corte_historico"] = "2017-02-15"
    ajustes["incidentes"] = INCIDENTES_SINTETICOS
    simulacion.write_text(yaml.safe_dump(ajustes), encoding="utf-8")
    carpeta = proyecto / "data" / "kaggle"
    carpeta.mkdir(parents=True)
    with zipfile.ZipFile(carpeta / "kaggle_sintetico.zip", "w") as archivo:
        for nombre, contenido in _csv_kaggle().items():
            archivo.writestr(nombre, contenido)
    return proyecto
