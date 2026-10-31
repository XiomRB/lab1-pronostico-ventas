import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def raiz() -> Path:
    return RAIZ


@pytest.fixture(scope="session")
def rastreados() -> list[str]:
    salida = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True)
    return salida.stdout.splitlines()
