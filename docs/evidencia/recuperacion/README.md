# Evidencia de recuperación

Comandos y resultados en `recuperacion.txt`. Cada clon parte sin caché, y los objetos llegan del remoto DVC local.

| Prueba | Resultado |
|---|---|
| Recuperación de `pub/2017-04-03-r1` y `pub/2017-06-12-r1` | Archivos idénticos byte a byte, con datos y modelos |
| Revisión `pub/2017-04-17-r2` | Recuperada |
| Reproducción dentro de la imagen | Hashes idénticos a los del manifiesto |
| Respaldo `.tar` y restauración | SHA-256 verificado; recuperación idéntica |
