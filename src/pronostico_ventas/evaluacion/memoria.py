"""Límite de seguridad de memoria para experimentos y entrenamientos."""
import os
import sys
import threading
import time
from types import TracebackType

CODIGO_SALIDA = 3


def memoria_actual_mb() -> int:
    with open("/proc/self/status", encoding="ascii") as estado:
        for linea in estado:
            if linea.startswith("VmRSS"):
                return int(linea.split()[1]) // 1024
    raise RuntimeError("No se pudo leer la memoria del proceso")


class LimiteMemoria:
    """Vigila el proceso y lo detiene si supera `limite_mb`. Registra el pico observado."""

    def __init__(self, limite_mb: int, intervalo: float = 0.05, al_exceder=None) -> None:
        self.limite_mb = limite_mb
        self.intervalo = intervalo
        self.pico_mb = 0
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._vigilar, daemon=True)
        self._al_exceder = al_exceder or self._detener

    def _detener(self, actual: int) -> None:
        print(f"Límite de memoria superado: {actual} MB de {self.limite_mb} MB", file=sys.stderr, flush=True)
        os._exit(CODIGO_SALIDA)

    def _vigilar(self) -> None:
        while not self._parar.is_set():
            actual = memoria_actual_mb()
            self.pico_mb = max(self.pico_mb, actual)
            if actual > self.limite_mb:
                self._al_exceder(actual)
                return
            time.sleep(self.intervalo)

    def __enter__(self) -> "LimiteMemoria":
        self._hilo.start()
        return self

    def __exit__(self, tipo: type | None, valor: BaseException | None, traza: TracebackType | None) -> None:
        self._parar.set()
        self._hilo.join()
