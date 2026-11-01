"""Recupera una publicación en una carpeta nueva con Git y el remoto DVC local."""
import argparse
import subprocess
import sys
from pathlib import Path


def correr(*comando: str, cwd: Path | None = None) -> None:
    subprocess.run(comando, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corte", required=True)
    parser.add_argument("--revision", type=int, default=1)
    parser.add_argument("--destino", required=True, type=Path, help="carpeta nueva, junto a dvc-storage o con --remoto")
    parser.add_argument("--remoto", type=Path, help="ruta del remoto DVC, si el destino no está junto a él")
    args = parser.parse_args()
    raiz = Path(__file__).resolve().parents[1]
    etiqueta = f"pub/{args.corte}-r{args.revision}"
    correr("git", "clone", "-q", str(raiz), str(args.destino))
    correr("git", "checkout", "-q", etiqueta, cwd=args.destino)
    if args.remoto:
        correr(sys.executable, "-m", "dvc", "remote", "modify", "--local", "local", "url", str(args.remoto.resolve()), cwd=args.destino)
    correr(sys.executable, "-m", "dvc", "pull", cwd=args.destino)
    print(f"Publicación recuperada en {args.destino}/data/publicado/corte={args.corte}/rev={args.revision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
