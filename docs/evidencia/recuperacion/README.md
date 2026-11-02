# Evidencia de recuperación

Comandos y resultados en una instalación limpia, en `recuperacion.txt`.

| Prueba | Resultado |
|---|---|
| Reproceso del corte 2017-04-17 | Revisión 2 creada con la corrección; revisión 1 intacta |
| Recuperación de 2017-04-03 y 2017-06-12 con Git y DVC | Archivos idénticos byte a byte, incluido el modelo |
| Reproducción dentro de la imagen | Hashes idénticos a los del manifiesto, también en una revisión |
| Respaldo `.tar` y restauración | SHA-256 verificado; recuperación idéntica desde el remoto restaurado |

`dvc_estado.txt` muestra `dvc status -c --json` igual a `{}` tras la última publicación.
