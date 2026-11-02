# Evidencia de bandeja externa

Ejecución en Airflow con `BANDEJA_HOST`, en una instalación limpia, del 2017-04-01 al 2017-05-03. Los resultados están en `escenario.txt`.

| Situación | Archivo | Resultado |
|---|---|---|
| Archivo tardío | Ventas del 04-19, entregadas el 04-26 | No existe en los cortes del 04-24 y 04-25; aparece el 04-26 |
| Corrección antes de la cobertura | Ventas del 04-20, corregidas el 04-25 | Crea la revisión 2 del corte 04-24 |
| Corrección tras iniciar la cobertura | Ventas del 04-21, corregidas el 04-27 | Se conoce desde el 04-27, sin nueva revisión |

| Comprobación | Resultado |
|---|---|
| Bandeja original | Huella idéntica; escritura rechazada por sistema de solo lectura |
| Publicaciones anteriores | Revisión 1 intacta; reproducción con hashes idénticos |
| Repetición con backfill | Mismos datos y mismas revisiones |
| Recuperación con Git y DVC | Archivos idénticos, incluida la bandeja recibida |
| `dvc status -c --json` | `{}` |
