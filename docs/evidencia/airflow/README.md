# Evidencia de Airflow

Ejecución completa en una instalación limpia del commit `a193b76`: clon nuevo, ZIP de Kaggle en `data/kaggle/` y `make up`, sin intervención manual.

| Archivo | Contenido |
|---|---|
| `corridas_resumen.txt` | Corridas por DAG: 146 de `operacion_diaria`, todas exitosas |
| `corridas_operacion_diaria.txt` | Estado de cada corrida diaria |
| `pools.txt` | Pool `pesado` de un cupo |
| `publicaciones.txt` | 21 publicaciones `RESPALDADA` |
| `backfill.txt` | Backfill con `completed`: los datos no cambian |

La publicación del 2017-08-21 usa datos con 6 días de atraso, dentro del umbral configurado. Una revisión posterior quedó omitida por antigüedad.
