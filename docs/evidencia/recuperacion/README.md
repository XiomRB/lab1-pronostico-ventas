# Evidencia de recuperación

`recuperacion.txt` es la prueba vigente. Cada clon local parte sin caché, y los objetos llegan del remoto DVC local.

| Prueba | Resultado |
|---|---|
| `pub/2017-04-03-r1` y `pub/2017-06-12-r1` | Datos y modelos idénticos byte a byte |
| Revisión `pub/2017-04-17-r2` | Recuperada |
| Reproducción dentro de la imagen | Hashes idénticos a los del manifiesto |
| Respaldo `.tar` y restauración | SHA-256 verificado; recuperación idéntica |

`recuperacion_ensayo.txt` y `dvc_estado.txt` son del ensayo sobre el commit `a193b76`. Se conservan como antecedente y no son la prueba vigente.
