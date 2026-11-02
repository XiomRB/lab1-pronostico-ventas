"""Compara los modelos con los cortes de validación: python -m pronostico_ventas.evaluacion."""
import argparse

from pronostico_ventas import config
from pronostico_ventas.evaluacion.comparacion import comparar, guardar


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modelos", nargs="*", help="modelos a comparar; por defecto, todos")
    args = parser.parse_args()
    cfg = config.cargar()
    resultado = comparar(cfg, args.modelos)
    guardar(cfg, resultado)
    print(f"Modelo elegido: {resultado['modelo_elegido']}")


if __name__ == "__main__":
    main()
