"""Métricas técnicas y de negocio."""
import numpy as np


def wape(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.abs(y - p).sum() / max(np.abs(y).sum(), 1e-9))


def rmsle(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean((np.log1p(np.clip(p, 0, None)) - np.log1p(np.clip(y, 0, None))) ** 2)))


def pinball(y: np.ndarray, q: np.ndarray, nivel: float) -> float:
    diferencia = y - q
    return float(np.mean(np.maximum(nivel * diferencia, (nivel - 1) * diferencia)))


def cobertura_intervalo(y: np.ndarray, inferior: np.ndarray, superior: np.ndarray) -> float:
    return float(np.mean((y >= inferior) & (y <= superior)))


def costo_negocio(demanda: np.ndarray, pedido: np.ndarray, cu: np.ndarray, co: np.ndarray) -> float:
    """Costo de faltantes y sobrantes del periodo."""
    return float((cu * np.maximum(demanda - pedido, 0) + co * np.maximum(pedido - demanda, 0)).sum())
