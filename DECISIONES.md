# Decisiones técnicas y de producto

Registro de decisiones, alternativas y justificación. Este documento crecerá en cada fase.

## Fase 0: viabilidad

| Decisión | Alternativas | Justificación |
|---|---|---|
| DVC exclusivamente local, en `../dvc-storage/lab1` | Servicios en la nube | Decisión del proyecto: sin credenciales ni dependencias externas |
| Respaldo `.tar` con SHA-256 en otro medio físico | Confiar en el remoto local | El remoto comparte disco con el proyecto |
| `verify = true` en el remoto | Valor por defecto | Con el valor por defecto, DVC restauró un objeto corrupto y reportó éxito |
| Sincronía con `dvc status -c --json` | Código de salida | `dvc status -c` responde `exit=0` aunque haya diferencias |
| Centinela y comprobación de montaje | Confiar en `dvc push` | Si el remoto falta, `dvc push` crea uno nuevo y reporta éxito |
| `.dvc` junto a cada salida, con excepción en `.gitignore` | Ignorar `/data/` | DVC rechaza crear un `.dvc` en una ruta ignorada |
| Commit de publicación con índice temporal | `git worktree` | No altera índice, HEAD, rama ni estado de trabajo |
| Scheduler espera al api-server sano | Arranque simultáneo | La primera tarea falló con `Connection refused` |
| Tarea final `cierre` en el orquestador | Confiar en el estado de la corrida | Una corrida quedó verde pese a una tarea intermedia fallida |

## Fase 1: repositorio

| Decisión | Alternativas | Justificación |
|---|---|---|
| Repositorio público | Privado | Protección de `main` y acceso docente, sin datos ni credenciales |
| Correo `noreply` de GitHub, configurado solo en este repositorio | Correo personal | Evita publicar un correo personal |
| Entorno propio en `.venv` | Reutilizar un entorno existente | Las versiones deben coincidir con la imagen de Airflow |
| `pytest==8.4.2` | Versión más reciente | Ya usada junto a Airflow 3.3.2; no figura en las constraints |
| Puerto web solo en `127.0.0.1` y secretos en `.env` | Publicar en todas las interfaces | Evita exponer Airflow y credenciales en un repositorio público |
| Reglas de `/models/**` iguales a las de `/data/**` | Reglas solo para datos | Git tampoco debe aceptar modelos |
| Enunciado y especificación solo en local, ignorados por Git | Publicarlos en `docs/` | Decisión del estudiante; el enunciado requiere autorización docente |

## Limitaciones conocidas

- La memoria de LightGBM con datos reales y su determinismo quedan pendientes hasta la Fase 4.
- Los costos y las fechas de publicación son supuestos académicos.
