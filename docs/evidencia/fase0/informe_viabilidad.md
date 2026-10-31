# Informe de viabilidad: Fase 0

**Fecha:** 2026-10-31. **Conclusión:** el diseño es viable con 8 ajustes, ya incorporados a la especificación v1.1.

Las pruebas usaron DAGs de prueba y datos sintéticos. No se procesaron los datos de Kaggle ni se entrenaron modelos. Convención: ✅ comprobado, ⏳ pendiente, 🔶 supuesto.

## Resultado por área

| Área | Estado | Resultado |
|---|---|---|
| Airflow 3.3.2, Compose y LocalExecutor | ✅ | Estable |
| Instalación de LightGBM y `libgomp1` | ✅ | `import lightgbm` falla sin el paquete y funciona con él |
| Git y DVC en contenedor | ✅ | Funcionan con el UID del host; fallan con el UID 50000 por defecto |
| Remoto DVC local | ✅ | `push`, `pull`, `checkout` y recuperación en clon limpio |
| Persistencia | ✅ | Huella idéntica tras `docker compose down -v` |
| Commit con índice temporal | ✅ | Índice, HEAD, rama y estado quedan idénticos |
| Catchup, backfill y serialización | ✅ | Con DAGs de prueba |
| Respaldo `.tar` con SHA-256 | ✅ | Detecta alteraciones y restaura en otra ubicación |
| Memoria de LightGBM con datos reales | ⏳ | Fase 4 |
| Determinismo de LightGBM | ⏳ | Fase 4 |
| Duración real con tareas pesadas | ⏳ | Fases 4 y 6 |
| Construcción en la máquina docente | ⏳ | Fase 9 |

## Entorno comprobado

- Linux sobre WSL 2, con 3,8 GiB de memoria asignada.
- Docker 29.1.3 y Compose v5.0.1.
- Git 2.53 en el host y 2.39.5 en el contenedor, compatibles en estas pruebas.
- Python 3.12.15 en el host y 3.12.14 en la imagen.
- Imagen de 3,37 GB con `lightgbm 4.7.0`, `dvc 3.67.1` y `pandas 3.0.5`. `pip check` no encontró dependencias rotas.

## Mediciones

| Medida | Valor |
|---|---|
| Stack de prueba, pico con tareas triviales | 1.110 MiB |
| Scheduler, pico | 554 MiB |
| Arranque desde cero | Cerca de 2 minutos |
| Orquestación por día normal | Unos 6 s |
| Orquestación por lunes | Unos 16 s |

Estimación 🔶 para 137 días con 20 lunes: cerca de 16 minutos solo de orquestación, sin contar el trabajo real.

## Pruebas

| ID | Prueba | Resultado | Log |
|---|---|---|---|
| T1 | `import lightgbm` sin `libgomp1` | ✅ Falla como se esperaba | `t1_libgomp.log` |
| T1 | Con `libgomp1` | ✅ Funciona | `t1_libgomp.log` |
| T2 | 23 aserciones de DVC y Git | ✅ 0 fallos | `t2_git_dvc.log` |
| T3 | Objeto corrupto con DVC por defecto | ❌ Restaura datos corruptos con `exit=0` | `t3_corrupcion.log` |
| T3 | Objeto corrupto con `verify true` | ✅ `pull` falla con `exit=1` | `t3_corrupcion.log` |
| T4 | Contenedor con UID del host | ✅ `add`, `push` y commit | `t4_contenedor.log` |
| T4 | Contenedor con UID 50000 | ⚠️ `dubious ownership` y `Permission denied` | `t4_entrypoint_omitido.log` |
| T5 | Primer arranque automático | ❌ Primera tarea fallida por carrera con el api-server | `t5_arranque.log` |
| T6 | `down -v` y recreación | ✅ Huella idéntica | `t6_persistencia.log` |
| T7 | Catchup sin intervención | ✅ 5 de 5 días, tras la corrección | `t7_airflow.log` |
| T7 | Pool `pesado` de 1 cupo | ✅ 3 tareas, 0 solapes | `t7_airflow.log` |
| T7 | Escritura en bandeja `:ro` | ✅ Rechazada, errno 30 | `t7_airflow.log` |
| T7 | Fallo simulado de respaldo | ✅ 3 intentos, corrida en rojo | `t7_airflow.log` |
| T8 | Backfill con `completed`, `failed` y `none` | ✅ Comportamiento esperado | `t8_backfill_parcial.log`, `t8_backfill_final.log` |
| T8 | Lote de 7 días posterior a `end_date` | ✅ 7 de 7, en orden y sin solapes | `t8_backfill_final.log` |
| T9 | `.tar` con SHA-256 y restauración | ✅ Detecta alteraciones y restaura | `t9_respaldo_y_montaje.log` |
| T10 | Montar un remoto inexistente | ❌ Docker lo crea como root | `t9_respaldo_y_montaje.log` |
| T10b | `airflow-init` prepara la carpeta | ✅ Escritura correcta y montaje detectado | `t10_montaje_fix.log` |

## Resultados descartados por errores de prueba

- `t2_INVALIDO_flag_file.log`: usó una opción inexistente de `dvc add` y dio resultados sobre datos vacíos.
- `t4_entrypoint_omitido.log`: omitió el entrypoint oficial, por lo que no encontraba `dvc`. Su caso de UID 50000 sí se considera válido.
- `t8_backfill_parcial.log`: el stack se apagó antes de terminar el lote final. Los casos terminados conservan validez y el lote se repitió en `t8_backfill_final.log`.

## Problemas y soluciones

| # | Problema | Solución |
|---|---|---|
| 1 | DVC restaura datos corruptos y reporta éxito | `verify = true` |
| 2 | `dvc status -c` responde `exit=0` aunque haya diferencias | Evaluar `dvc status -c --json` |
| 3 | `dvc status -c` no detecta objetos corruptos | Recalcular hashes antes de `RESPALDADA` |
| 4 | Si falta el remoto, `dvc push` crea uno nuevo y reporta éxito | Centinela y montaje real |
| 5 | El scheduler lanza tareas antes que el api-server | `service_healthy` y reintentos |
| 6 | Docker crea el remoto faltante como root | `airflow-init` lo prepara |
| 7 | DVC rechaza `.dvc` en rutas ignoradas | `.gitignore` con excepción para `.dvc` |
| 8 | Con UID 50000 no se puede escribir | `.env` generado y verificación inicial |
| 9 | Una corrida queda verde con una tarea intermedia fallida | Tarea final `cierre` |
| 10 | `--to-date` sin hora se lee como 00:00 | Usar `T23:59:00` |
| 11 | `end_date` a medianoche excluye la corrida de las 06:00 | `end_date` al final del día |
| 12 | Solo se admite un backfill activo por DAG | Documentarlo y esperar al anterior |
| 13 | `rm -rf data` borra también las referencias `.dvc` | `make limpiar` solo borrará contenido |
| 14 | Los archivos recuperados pierden el modo solo lectura | Inmutabilidad posterior por hash |

## Riesgos abiertos

- Memoria de LightGBM y determinismo: Fase 4.
- Periodo docente: formato y fechas sin confirmar.
- El remoto local no viaja con GitHub: falta acordar la entrega del `.tar`.
- Remoto y proyecto comparten disco: el `.tar` debe guardarse en otro medio físico.
- La imagen requiere acceso a Docker Hub, PyPI, GitHub y `apt` al construirse.
- Máquina docente con otro sistema o UID: ensayo en Fase 9.
