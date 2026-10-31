"""Lectura de los archivos permitidos de Kaggle, desde un ZIP o desde CSV sueltos."""
import hashlib
import zipfile
from pathlib import Path

import pandas as pd

PERMITIDOS = ("train.csv", "stores.csv", "holidays_events.csv", "oil.csv", "transactions.csv")


def _zip_en(carpeta: Path) -> Path | None:
    candidatos = sorted(carpeta.glob("*.zip"))
    return candidatos[0] if candidatos else None


def _leer_csv(origen) -> pd.DataFrame:
    # Se conserva el texto original: los valores vuelven a la bandeja sin reformatearse.
    return pd.read_csv(origen, dtype=str, keep_default_na=False)


def leer(carpeta: Path) -> tuple[dict[str, pd.DataFrame], str]:
    """Devuelve las tablas permitidas y una huella del contenido leído."""
    if not carpeta.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de Kaggle: {carpeta}")
    tablas, huella = {}, hashlib.sha256()
    ruta_zip = _zip_en(carpeta)
    if ruta_zip is None:
        faltantes = [n for n in PERMITIDOS if not (carpeta / n).is_file()]
        if faltantes:
            raise FileNotFoundError(f"Faltan archivos de Kaggle en {carpeta}: {faltantes}")
        for nombre in PERMITIDOS:
            ruta = carpeta / nombre
            huella.update(hashlib.sha256(ruta.read_bytes()).digest())
            tablas[nombre] = _leer_csv(ruta)
        return tablas, huella.hexdigest()

    with zipfile.ZipFile(ruta_zip) as archivo:
        faltantes = [n for n in PERMITIDOS if n not in archivo.namelist()]
        if faltantes:
            raise FileNotFoundError(f"Faltan archivos en {ruta_zip.name}: {faltantes}")
        for nombre in PERMITIDOS:
            with archivo.open(nombre) as contenido:
                huella.update(hashlib.sha256(contenido.read()).digest())
            with archivo.open(nombre) as contenido:
                tablas[nombre] = _leer_csv(contenido)
    return tablas, huella.hexdigest()
