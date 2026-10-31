# Evidencia de la Fase 0

Evidencia de la viabilidad técnica. El análisis está en [informe_viabilidad.md](informe_viabilidad.md).

## Contenido

| Ruta | Contenido |
|---|---|
| `logs/` | Salidas de las pruebas |
| `prototipos/` | Dockerfile, Compose y DAGs de prueba. **No son el producto definitivo** |

## Archivos de log

| Archivo | Bytes | Estado |
|---|---|---|
| `build_final.log` | 5.428 | Válido |
| `build_sin_gomp.log` | 47.099 | Válido |
| `mem_muestras.txt` | 17.986 | Válido |
| `t10_montaje_fix.log` | 271 | Válido |
| `t1_libgomp.log` | 669 | Válido |
| `t2_INVALIDO_flag_file.log` | 4.399 | Descartado |
| `t2_git_dvc.log` | 3.349 | Válido |
| `t3_corrupcion.log` | 1.577 | Válido |
| `t4_contenedor.log` | 1.480 | Válido |
| `t4_entrypoint_omitido.log` | 4.155 | Descartado en parte |
| `t5_arranque.log` | 2.183 | Válido |
| `t6_persistencia.log` | 608 | Válido |
| `t7_airflow.log` | 1.087 | Válido |
| `t8_backfill_final.log` | 1.143 | Válido |
| `t8_backfill_parcial.log` | 4.051 | Parcial |
| `t9_respaldo_y_montaje.log` | 1.174 | Válido |

Los motivos de los estados están en el informe.

## Saneamiento

Estos archivos son copias. Los originales permanecen sin cambios en el sandbox local de la Fase 0, que no se publica.

| Original | Copia |
|---|---|
| Ruta del sandbox | `<sandbox>` |
| Carpeta personal | `<home>` |
| Carpeta del usuario dentro del contenedor | `<home-contenedor>` |
| Nombre de usuario local | `<usuario>` |
| Credenciales de prueba y secreto del Compose | `<usuario>`, `<clave>`, `<generado-localmente>` |

Por esos reemplazos, el Compose de `prototipos/` no es ejecutable tal como está.

## Auditoría de seguridad

Cada archivo se revisó por separado, antes y después del saneamiento, buscando tokens, llaves, correos, claves, rutas personales, nombre de usuario, direcciones IP y datos reales.

| Resultado | Detalle |
|---|---|
| Tokens, llaves y correos | Ninguno |
| Datos reales de Kaggle | Ninguno. Los valores de las pruebas son sintéticos |
| Rutas y usuario local | Reemplazados en todas las copias |
| Falso positivo | `1.1.1.2` en `build_sin_gomp.log` es una versión de paquete, no una dirección IP |
| Marcadores | Las coincidencias del Compose son los marcadores de la tabla anterior |
| Información del equipo | Limitada a la memoria asignada y las versiones de software que justifican la viabilidad |
| Otros proyectos | Sin referencias a sus nombres |

## No publicado

El archivo `.env` y los logs internos de Airflow del sandbox.
