"""Recalcula una publicación y compara sus hashes con el manifiesto."""
import argparse
import json
import sys
from datetime import date

from pronostico_ventas import config
from pronostico_ventas.publicacion.reproduccion import reproducir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corte", required=True, type=date.fromisoformat)
    parser.add_argument("--revision", type=int, default=1)
    args = parser.parse_args()
    resultado = reproducir(config.cargar(), args.corte, args.revision)
    print(json.dumps(resultado, indent=2))
    return 0 if resultado["identico"] else 1


if __name__ == "__main__":
    sys.exit(main())
