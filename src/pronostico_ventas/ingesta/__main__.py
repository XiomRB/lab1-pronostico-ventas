"""Ingesta de la bandeja: python -m pronostico_ventas.ingesta --fecha YYYY-MM-DD."""
import argparse
import json
from datetime import date

from pronostico_ventas import config
from pronostico_ventas.ingesta.proceso import ingerir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fecha", required=True, type=date.fromisoformat, help="fecha lógica de la ejecución")
    args = parser.parse_args()
    print(json.dumps(ingerir(config.cargar(), args.fecha), indent=2))


if __name__ == "__main__":
    main()
