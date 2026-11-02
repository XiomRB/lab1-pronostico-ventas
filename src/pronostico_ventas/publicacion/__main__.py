"""Publica un corte: python -m pronostico_ventas.publicacion --corte YYYY-MM-DD."""
import argparse
import json
from datetime import date

from pronostico_ventas import config
from pronostico_ventas.publicacion import publicar


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corte", required=True, type=date.fromisoformat)
    parser.add_argument("--reprocesar-en", type=date.fromisoformat, help="crea una revisión con lo conocido en esa fecha")
    args = parser.parse_args()
    resultado = publicar.publicar(config.cargar(), args.corte, args.reprocesar_en)
    print(json.dumps({k: v for k, v in resultado.items() if k != "manifiesto"}, indent=2))


if __name__ == "__main__":
    main()
