# Comparación de modelos

Resultados de los 8 cortes de validación, de 2016-08-29 a 2017-03-13, generados con `make evaluate` dentro de la imagen. Ningún dato de la bandeja de reserva participa.

El modelo elegido es **baseline**. Ningún candidato cumple todas las condiciones de `config/modelo.yaml`.

| Modelo | Costo total | Mejora de costo | WAPE | RMSLE | Pinball | Cobertura P10-P90 | Cortes ganados | Pico de memoria |
|---|---|---|---|---|---|---|---|---|
| baseline | 15,106,148 | — | 0.2223 | 0.7063 | 39.88 | 0.752 | — | 813 MB |
| hgb_poisson | 9,809,449 | 35.1% | 0.1933 | 0.6677 | 32.80 | 0.767 | 5 de 8 | 1495 MB |
| lightgbm | 11,039,263 | 26.9% | 0.1937 | 0.5101 | 33.09 | 0.776 | 4 de 8 | 1138 MB |
| lightgbm_poisson | 8,510,258 | 43.7% | 0.1836 | 0.6822 | 31.48 | 0.774 | 6 de 8 | 1055 MB |

## Cobertura de Q* por objetivo

| Modelo | Q* = 0.60 | Q* = 0.67 | Q* = 0.80 |
|---|---|---|---|
| baseline | 0.561 | 0.703 | 0.693 |
| hgb_poisson | 0.605 | 0.712 | 0.762 |
| lightgbm | 0.595 | 0.719 | 0.735 |
| lightgbm_poisson | 0.569 | 0.693 | 0.735 |

## Criterio de reemplazo

| Candidato | Costo | WAPE | Pinball | Cortes ganados | Cobertura P10-P90 | Cobertura de Q* | Reemplaza |
|---|---|---|---|---|---|---|---|
| hgb_poisson | Cumple | Cumple | Cumple | No cumple | Cumple | Cumple | No |
| lightgbm | Cumple | Cumple | Cumple | No cumple | Cumple | No cumple | No |
| lightgbm_poisson | Cumple | Cumple | Cumple | Cumple | Cumple | No cumple | No |

## Calibración

La escala de los residuos del periodo incluye la demanda prevista. Con la escala basada solo en ventas recientes, el costo de lightgbm_poisson fue 8,689,138. El detalle está en `reportes/comparacion_modelos_escala_inicial.json`.
