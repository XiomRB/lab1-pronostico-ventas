# Evidencia de Airflow

Exportaciones por consola de la ejecución limpia sobre `main` en el commit `8e160ad`, en `verificacion_final.txt`. No son capturas de la interfaz.

| Contenido | Resultado |
|---|---|
| Corridas de `operacion_diaria` | 146 de 146 exitosas |
| Ingesta | 399 aceptados, 2 duplicados, 2 rechazados |
| Publicaciones | 21 `RESPALDADA` |
| Hashes de pronóstico y pedido por corte | Incluidos |
| Backfill con `completed` | Misma huella |
| Reproceso del corte 2017-04-17 | Revisión 2 `RESPALDADA`; repetirlo no crea otra |

La publicación del 2017-08-21 usa ventas con 6 días de atraso, dentro del umbral configurado. Una revisión posterior quedó omitida por antigüedad.
