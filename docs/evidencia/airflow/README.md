# Evidencia de Airflow

Exportaciones por consola, no capturas de la interfaz.

| Archivo | Ejecución | Contenido |
|---|---|---|
| `verificacion_final.txt` | Final, commit `8e160ad` | Corridas, ingesta, hashes por corte, backfill, reproceso y DVC |
| `corridas_resumen.txt` | Ensayo, commit `a193b76` | Corridas por DAG |
| `corridas_operacion_diaria.txt` | Ensayo, commit `a193b76` | Estado de cada corrida diaria |
| `publicaciones.txt` | Ensayo, commit `a193b76` | Estado de las publicaciones |
| `backfill.txt` | Ensayo, commit `a193b76` | Backfill |

## Resultado de la ejecución final

| Medida | Resultado |
|---|---|
| Corridas de `operacion_diaria` | 146 de 146 exitosas |
| Ingesta | 399 aceptados, 2 duplicados, 2 rechazados |
| Publicaciones | 21 `RESPALDADA`, más la revisión 2 del corte 2017-04-17 creada por el reproceso |
| Backfill con `completed` | Misma huella antes y después |
| Reproceso repetido | No crea otra revisión |

Hay un registro de omisión para el corte 2017-08-21, motivo `datos_antiguos:['ventas']` con 7 días de atraso. Las ventas terminan el 2017-08-15. La revisión 1 de ese corte existe y sigue `RESPALDADA`.

## Capturas de la interfaz

Tomadas durante la ejecución final, mientras se procesaba la corrida del 2017-06-05. Muestran un estado intermedio: el resultado final está en `verificacion_final.txt`.

| Archivo | Vista | Qué muestra |
|---|---|---|
| `capturas/airflow1.png` | Inicio | Salud de los componentes, corridas y tareas de las últimas 24 horas |
| `capturas/airflow2.png` | Lista de DAGs | Cinco DAGs del producto con sus corridas recientes; `seguimiento_desempeno` aparece cortado |

El indicador rojo de Triggerer es esperado: el stack no incluye ese servicio porque ningún DAG usa operadores diferibles.
